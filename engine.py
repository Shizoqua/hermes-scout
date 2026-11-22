"""Chunking, incremental indexing and cosine ranking. Standard library only.

The embedder is injected (``Embedder``: a list of texts in, one vector per text out), so this module
has no network or Hermes dependency and is tested on its own.
"""

from __future__ import annotations

import array
import math
import os
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

Embedder = Callable[[list[str]], list[list[float]]]
BlockCheck = Callable[[Path], "str | None"]

DEFAULT_EXTENSIONS = frozenset({
    ".md", ".markdown", ".txt", ".rst", ".org", ".tex", ".adoc",
    ".py", ".ipynb", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".scala", ".go", ".rs", ".rb",
    ".php", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".swift", ".sh", ".sql", ".r", ".jl",
    ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv",
})
# Dependency, build and VCS folders: large, generated, and never what a person means by "my files".
SKIP_DIRS = frozenset({
    "node_modules", "__pycache__", "venv", "env", "dist", "build", "target", "site-packages",
})
_SNIFF_BYTES = 4096

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    root TEXT NOT NULL, model TEXT NOT NULL, path TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL,
    PRIMARY KEY (root, model, path)
);
CREATE TABLE IF NOT EXISTS chunks (
    root TEXT NOT NULL, model TEXT NOT NULL, path TEXT NOT NULL,
    start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
    text TEXT NOT NULL, vec BLOB NOT NULL, norm REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_by_file ON chunks (root, model, path);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def chunk_text(text: str, max_chars: int = 1200, overlap_lines: int = 2) -> list[tuple[int, int, str]]:
    """``(start_line, end_line, text)`` chunks of whole lines, each at most ``max_chars``.

    Consecutive chunks share ``overlap_lines`` lines, so a passage that straddles a boundary is
    still found whole in one of them. A single line longer than ``max_chars`` is truncated.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    lines = text.splitlines()
    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(lines):
        end, size = start, 0
        while end < len(lines) and (end == start or size + len(lines[end]) + 1 <= max_chars):
            size += len(lines[end]) + 1
            end += 1
        body = "\n".join(lines[start:end]).strip()
        if body:
            chunks.append((start + 1, end, body[:max_chars]))
        if end >= len(lines):
            break
        start = max(end - overlap_lines, start + 1)
    return chunks


def _is_text(path: Path) -> bool:
    with path.open("rb") as fh:
        return b"\0" not in fh.read(_SNIFF_BYTES)


def iter_files(root: Path, *, extensions: frozenset[str] = DEFAULT_EXTENSIONS, max_file_bytes: int = 1_000_000,
               max_files: int = 2000, is_blocked: BlockCheck | None = None) -> Iterator[Path]:
    """Text files under ``root`` worth indexing, in a stable order, at most ``max_files``.

    Hidden entries (dot-names), dependency/build folders, symlinks, binary and oversized files and
    any path ``is_blocked`` refuses are skipped.
    """
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if name.startswith(".") or path.suffix.lower() not in extensions or path.is_symlink():
                continue
            try:
                if path.stat().st_size > max_file_bytes or not _is_text(path):
                    continue
            except OSError:
                continue
            if is_blocked is not None and is_blocked(path):
                continue
            yield path
            count += 1
            if count >= max_files:
                return


def _pack(vector: list[float]) -> tuple[bytes, float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return array.array("f", vector).tobytes(), norm


def _embed_all(embedder: Embedder, texts: list[str], batch_size: int) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        out = embedder(batch)
        if len(out) != len(batch):
            raise ValueError(f"embedder returned {len(out)} vectors for {len(batch)} texts")
        vectors.extend(out)
    return vectors


def update_index(conn: sqlite3.Connection, root: Path, model: str, embedder: Embedder, files: list[Path], *,
                 max_chars: int = 1200, batch_size: int = 32) -> dict[str, int]:
    """Bring the ``(root, model)`` index in line with ``files``: embed new or changed files, keep
    unchanged ones, drop files that are gone. Returns counts for the caller to report."""
    key = str(root)
    known = {row[0]: (row[1], row[2]) for row in conn.execute(
        "SELECT path, mtime_ns, size FROM files WHERE root = ? AND model = ?", (key, model))}
    stats = {"indexed_files": 0, "reused_files": 0, "removed_files": 0}
    seen: set[str] = set()
    for path in files:
        rel = path.relative_to(root).as_posix()
        seen.add(rel)
        try:
            st = path.stat()
        except OSError:
            continue
        if known.get(rel) == (st.st_mtime_ns, st.st_size):
            stats["reused_files"] += 1
            continue
        chunks = chunk_text(path.read_text(encoding="utf-8", errors="replace"), max_chars=max_chars)
        vectors = _embed_all(embedder, [text for _, _, text in chunks], batch_size) if chunks else []
        with conn:
            conn.execute("DELETE FROM chunks WHERE root = ? AND model = ? AND path = ?", (key, model, rel))
            conn.executemany(
                "INSERT INTO chunks (root, model, path, start_line, end_line, text, vec, norm)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(key, model, rel, start, end, text, *_pack(vec)) for (start, end, text), vec in zip(chunks, vectors)])
            conn.execute("INSERT OR REPLACE INTO files (root, model, path, mtime_ns, size) VALUES (?, ?, ?, ?, ?)",
                         (key, model, rel, st.st_mtime_ns, st.st_size))
        stats["indexed_files"] += 1
    gone = [rel for rel in known if rel not in seen]
    with conn:
        for rel in gone:
            conn.execute("DELETE FROM chunks WHERE root = ? AND model = ? AND path = ?", (key, model, rel))
            conn.execute("DELETE FROM files WHERE root = ? AND model = ? AND path = ?", (key, model, rel))
    stats["removed_files"] = len(gone)
    stats["chunks"] = conn.execute("SELECT COUNT(*) FROM chunks WHERE root = ? AND model = ?", (key, model)).fetchone()[0]
    return stats


def search(conn: sqlite3.Connection, root: Path, model: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
    """The ``top_k`` chunks most similar to ``query_vector`` by cosine similarity, best first."""
    q_norm = math.sqrt(sum(v * v for v in query_vector))
    if q_norm == 0 or top_k < 1:
        return []
    scored: list[tuple[float, str, int, int, str]] = []
    for path, start, end, text, blob, norm in conn.execute(
            "SELECT path, start_line, end_line, text, vec, norm FROM chunks WHERE root = ? AND model = ?",
            (str(root), model)):
        if norm == 0:
            continue
        vec = array.array("f")
        vec.frombytes(blob)
        if len(vec) != len(query_vector):
            continue  # indexed with another embedding size under the same model name; re-indexing fixes it
        score = sum(a * b for a, b in zip(query_vector, vec)) / (q_norm * norm)
        scored.append((score, path, start, end, text))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [{"path": path, "lines": f"{start}-{end}", "score": round(score, 4), "text": text}
            for score, path, start, end, text in scored[:top_k]]
