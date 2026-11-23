"""Chunking, incremental indexing and cosine ranking. Standard library only.

The embedder is injected (``Embedder``: a list of texts in, one vector per text out), so this module
has no network or Hermes dependency and is tested on its own.
"""

from __future__ import annotations

import array
import math
import os
import re
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from . import documents, patterns

Embedder = Callable[[list[str]], list[list[float]]]
BlockCheck = Callable[[Path], "str | None"]

DEFAULT_EXTENSIONS = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".rst",
        ".org",
        ".tex",
        ".adoc",
        ".py",
        ".ipynb",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".kt",
        ".scala",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".cs",
        ".swift",
        ".sh",
        ".sql",
        ".r",
        ".jl",
        ".html",
        ".css",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".csv",
    }
)
# Dependency, build and VCS folders: large, generated, and never what a person means by "my files".
SKIP_DIRS = frozenset(
    {
        "node_modules",
        "__pycache__",
        "venv",
        "env",
        "dist",
        "build",
        "target",
        "site-packages",
    }
)
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


# Keyword index for hybrid search: SQLite's built-in full-text search, keyed by the chunk's rowid.
# Python's sqlite3 ships with FTS5 on every mainstream platform; without it, search falls back to
# meaning alone.
_FTS_TABLE = "chunks_fts"
RANKINGS = ("hybrid", "semantic", "keyword")
NO_KEYWORD_NOTE = (
    "Keyword search is not available in this Python's SQLite (no FTS5), so results are ranked by meaning only."
)
# Hybrid ranking routes by query: questions in words are ranked by meaning, which the benchmark
# measured as the most accurate for them; queries made only of code-like names (ERR_4291, pg_dump,
# getUserById), which embedding models often blur, merge both rankings by score with keywords at
# 0.75 and meaning at 0.25 (relative score fusion).
_CODE_MEANING_WEIGHT = 0.25
_CODE_TERM = re.compile(r"\d|_|-|[a-z][A-Z]|^[A-Z]{2,}$")
_KEYWORD_CANDIDATES = 200
_WORD = re.compile(r"\w+", re.UNICODE)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    try:
        with conn:
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {_FTS_TABLE} USING fts5(text, tokenize='porter unicode61')"
            )
            # Rebuild the keyword rows when they do not line up with the chunks: an index built before
            # keyword search existed, or one whose rowids were renumbered (for example by VACUUM).
            chunks = conn.execute("SELECT COUNT(*), COALESCE(SUM(rowid), 0) FROM chunks").fetchone()
            keyword = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(rowid), 0) FROM {_FTS_TABLE}").fetchone()
            if chunks != keyword:
                conn.execute(f"DELETE FROM {_FTS_TABLE}")
                conn.execute(f"INSERT INTO {_FTS_TABLE} (rowid, text) SELECT rowid, text FROM chunks")
    except sqlite3.OperationalError:
        pass  # no FTS5 in this SQLite build: search uses meaning alone


def has_keyword_index(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (_FTS_TABLE,)).fetchone()
    return row is not None


def index_overview(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """One entry per indexed folder and embedding model: file and chunk counts, largest first."""
    rows = conn.execute(
        "SELECT f.root, f.model, COUNT(*),"
        " (SELECT COUNT(*) FROM chunks c WHERE c.root = f.root AND c.model = f.model)"
        " FROM files f GROUP BY f.root, f.model ORDER BY 4 DESC, 1"
    ).fetchall()
    return [{"root": root, "model": model, "files": files, "chunks": chunks} for root, model, files, chunks in rows]


def clear_index(conn: sqlite3.Connection, root: Path | None = None) -> int:
    """Forget the index of ``root`` (every model), or of every folder when ``root`` is None.
    Returns the number of files forgotten. The next search of a folder indexes it again."""
    where, params = ("WHERE root = ?", (str(root),)) if root is not None else ("", ())
    with conn:
        forgotten = conn.execute(f"SELECT COUNT(*) FROM files {where}", params).fetchone()[0]
        if has_keyword_index(conn):
            conn.execute(f"DELETE FROM {_FTS_TABLE} WHERE rowid IN (SELECT rowid FROM chunks {where})", params)
        conn.execute(f"DELETE FROM chunks {where}", params)
        conn.execute(f"DELETE FROM files {where}", params)
    conn.execute("VACUUM")
    ensure_schema(conn)  # VACUUM may renumber chunk rowids; this re-aligns the keyword index
    return int(forgotten)


def _delete_chunks(conn: sqlite3.Connection, key: str, model: str, rel: str, fts: bool) -> None:
    where = "root = ? AND model = ? AND path = ?"
    if fts:
        conn.execute(
            f"DELETE FROM {_FTS_TABLE} WHERE rowid IN (SELECT rowid FROM chunks WHERE {where})", (key, model, rel)
        )
    conn.execute(f"DELETE FROM chunks WHERE {where}", (key, model, rel))


def chunk_text(text: str, max_chars: int = 1200, overlap_lines: int = 2) -> list[tuple[int, int, str]]:
    """``(start_line, end_line, text)`` chunks of whole lines, each at most ``max_chars``.

    Consecutive chunks share up to ``overlap_lines`` lines, so a passage that straddles a boundary
    is still found whole in one of them. The overlap shrinks when lines are long, so no text is
    embedded twice over. A line longer than ``max_chars`` is split into pieces (at a space where it
    can be), and every piece keeps that line's number.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    # (line number, text) pieces, each at most max_chars long.
    pieces: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        pieces.extend((number, part) for part in _split_line(line, max_chars))
    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(pieces):
        end, size = start, 0
        while end < len(pieces) and (end == start or size + len(pieces[end][1]) + 1 <= max_chars):
            size += len(pieces[end][1]) + 1
            end += 1
        body = "\n".join(part for _, part in pieces[start:end]).strip()
        if body:
            chunks.append((pieces[start][0], pieces[end - 1][0], body))
        if end >= len(pieces):
            break
        # Overlap at most a third of the chunk's pieces and a quarter of its size.
        overlap = min(overlap_lines, (end - start) // 3)
        while overlap and sum(len(part) + 1 for _, part in pieces[end - overlap : end]) > max_chars // 4:
            overlap -= 1
        start = end - overlap
    return chunks


def _split_line(line: str, max_chars: int) -> list[str]:
    """``line`` cut into pieces of at most ``max_chars``, at the last space before the limit when
    there is one."""
    parts: list[str] = []
    while len(line) > max_chars:
        cut = line.rfind(" ", 1, max_chars + 1)
        if cut <= 0:
            cut = max_chars
        parts.append(line[:cut])
        line = line[cut:].lstrip(" ")
    parts.append(line)
    return parts


def _is_text(path: Path) -> bool:
    with path.open("rb") as fh:
        return b"\0" not in fh.read(_SNIFF_BYTES)


def read_file(path: Path) -> str:
    """The text to index for ``path``: the extracted text of a PDF or .docx file (empty when it cannot
    be read, so a broken document is skipped rather than failing the search), else the file itself."""
    if path.suffix.lower() in documents.DOCUMENT_EXTENSIONS:
        try:
            return documents.extract_text(path)
        except documents.DocumentError:
            return ""
    return path.read_text(encoding="utf-8", errors="replace")


def iter_files(
    root: Path,
    *,
    extensions: frozenset[str] = DEFAULT_EXTENSIONS,
    max_file_bytes: int = 1_000_000,
    max_files: int = 2000,
    is_blocked: BlockCheck | None = None,
    respect_gitignore: bool = True,
    read_documents: bool = True,
) -> Iterator[Path]:
    """Text files under ``root`` worth indexing, in a stable order, at most ``max_files``. With
    ``read_documents``, PDF and Word (.docx) files up to ``documents.MAX_DOCUMENT_BYTES`` are included.

    Hidden entries (dot-names), dependency/build folders, symlinks, binary and oversized files and
    any path ``is_blocked`` refuses are skipped, and so is anything a ``.gitignore`` file in the
    folder tree ignores (unless ``respect_gitignore`` is false).
    """
    count = 0
    rules_by_dir: dict[str, list[patterns.Rule]] = {str(root): []}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else rel_dir + "/"
        rules = rules_by_dir.pop(dirpath, [])
        if respect_gitignore:
            rules = rules + patterns.load_gitignore(Path(dirpath), prefix.rstrip("/"))
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".") and d not in SKIP_DIRS and not patterns.is_ignored(rules, prefix + d, True)
        )
        for d in dirnames:
            rules_by_dir[os.path.join(dirpath, d)] = rules
        for name in sorted(filenames):
            path = Path(dirpath) / name
            suffix = path.suffix.lower()
            is_document = read_documents and suffix in documents.DOCUMENT_EXTENSIONS
            if name.startswith(".") or not (is_document or suffix in extensions) or path.is_symlink():
                continue
            if patterns.is_ignored(rules, prefix + name, False):
                continue
            try:
                if is_document:
                    if path.stat().st_size > documents.MAX_DOCUMENT_BYTES:
                        continue
                elif path.stat().st_size > max_file_bytes or not _is_text(path):
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
        batch = texts[i : i + batch_size]
        out = embedder(batch)
        if len(out) != len(batch):
            raise ValueError(f"embedder returned {len(out)} vectors for {len(batch)} texts")
        vectors.extend(out)
    return vectors


def update_index(
    conn: sqlite3.Connection,
    root: Path,
    model: str,
    embedder: Embedder,
    files: list[Path],
    *,
    max_chars: int = 1200,
    batch_size: int = 32,
) -> dict[str, int]:
    """Bring the ``(root, model)`` index in line with ``files``: embed new or changed files, keep
    unchanged ones, drop files that are gone. Returns counts for the caller to report."""
    key = str(root)
    known = {
        row[0]: (row[1], row[2])
        for row in conn.execute("SELECT path, mtime_ns, size FROM files WHERE root = ? AND model = ?", (key, model))
    }
    stats = {"indexed_files": 0, "reused_files": 0, "removed_files": 0}
    fts = has_keyword_index(conn)
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
        chunks = chunk_text(read_file(path), max_chars=max_chars)
        vectors = _embed_all(embedder, [text for _, _, text in chunks], batch_size) if chunks else []
        with conn:
            _delete_chunks(conn, key, model, rel, fts)
            conn.executemany(
                "INSERT INTO chunks (root, model, path, start_line, end_line, text, vec, norm)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (key, model, rel, start, end, text, *_pack(vec))
                    for (start, end, text), vec in zip(chunks, vectors, strict=True)
                ],
            )
            if fts:
                conn.execute(
                    f"INSERT INTO {_FTS_TABLE} (rowid, text)"
                    " SELECT rowid, text FROM chunks WHERE root = ? AND model = ? AND path = ?",
                    (key, model, rel),
                )
            conn.execute(
                "INSERT OR REPLACE INTO files (root, model, path, mtime_ns, size) VALUES (?, ?, ?, ?, ?)",
                (key, model, rel, st.st_mtime_ns, st.st_size),
            )
        stats["indexed_files"] += 1
    gone = [rel for rel in known if rel not in seen]
    with conn:
        for rel in gone:
            _delete_chunks(conn, key, model, rel, fts)
            conn.execute("DELETE FROM files WHERE root = ? AND model = ? AND path = ?", (key, model, rel))
    stats["removed_files"] = len(gone)
    stats["chunks"] = conn.execute("SELECT COUNT(*) FROM chunks WHERE root = ? AND model = ?", (key, model)).fetchone()[
        0
    ]
    return stats


Row = tuple[int, str, int, int, str]  # rowid, path, start line, end line, text


def _vector_scores(
    conn: sqlite3.Connection,
    root: Path,
    model: str,
    query_vector: list[float],
    path_filter: patterns.PathFilter | None,
    exclude_path: str | None = None,
) -> list[tuple[float, Row]]:
    """Cosine similarity of every indexed chunk to ``query_vector``, best first."""
    q_norm = math.sqrt(sum(v * v for v in query_vector))
    if q_norm == 0:
        return []
    scored: list[tuple[float, Row]] = []
    for rowid, path, start, end, text, blob, norm in conn.execute(
        "SELECT rowid, path, start_line, end_line, text, vec, norm FROM chunks WHERE root = ? AND model = ?",
        (str(root), model),
    ):
        if norm == 0 or path == exclude_path or (path_filter and not path_filter.matches(path)):
            continue
        vec = array.array("f")
        vec.frombytes(blob)
        if len(vec) != len(query_vector):
            continue  # indexed with another embedding size under the same model name; re-indexing fixes it
        score = sum(a * b for a, b in zip(query_vector, vec, strict=True)) / (q_norm * norm)
        scored.append((score, (rowid, path, start, end, text)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


# English function words: they appear in almost every passage, so matching them ranks passages by
# chance. Left out of the keyword query unless the query has nothing else.
_STOP_WORDS_TEXT = """
    a about above after again against all am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have
    having he her here hers herself him himself his how i if in into is it its itself just me more most
    my myself no nor not now of off on once only or other our ours ourselves out over own same she
    should so some such than that the their theirs them themselves then there these they this those
    through to too under until up very was we were what when where which while who whom why will with
    would you your yours yourself yourselves us get got gets make makes made use used using one ones
    something someone anything anyone
"""
STOP_WORDS = frozenset(_STOP_WORDS_TEXT.split())


def keyword_query(text: str) -> str:
    """An FTS5 query matching any meaningful word of ``text``: function words such as "how" or "the"
    are dropped unless nothing else is left. Every word is quoted, so no input is FTS5 syntax."""
    words = list(dict.fromkeys(w.lower() for w in _WORD.findall(text) if len(w) > 1))
    words = [w for w in words if w not in STOP_WORDS] or words
    return " OR ".join('"' + w.replace('"', '""') + '"' for w in words[:32])


def looks_like_code(query: str) -> bool:
    """True for a query of one to three names that look like code rather than prose: each has a digit,
    an underscore or hyphen, an inner capital (camelCase) or is all capitals."""
    terms = query.split()
    return 0 < len(terms) <= 3 and all(_CODE_TERM.search(term) for term in terms)


def _keyword_ranking(
    conn: sqlite3.Connection, root: Path, model: str, query: str, path_filter: patterns.PathFilter | None
) -> list[tuple[float, Row]]:
    """Chunks matching ``query``'s words with their BM25 relevance (higher is better), best first."""
    match = keyword_query(query)
    if not match or not has_keyword_index(conn):
        return []
    rows = conn.execute(
        f"SELECT -bm25({_FTS_TABLE}), c.rowid, c.path, c.start_line, c.end_line, c.text FROM {_FTS_TABLE} f"
        " JOIN chunks c ON c.rowid = f.rowid"
        f" WHERE {_FTS_TABLE} MATCH ? AND c.root = ? AND c.model = ?"
        f" ORDER BY bm25({_FTS_TABLE}) LIMIT ?",
        (match, str(root), model, _KEYWORD_CANDIDATES * 5),
    )
    ranked: list[tuple[float, Row]] = [
        (float(score), (rowid, path, start, end, text))
        for score, rowid, path, start, end, text in rows
        if not (path_filter and not path_filter.matches(path))
    ]
    return ranked[:_KEYWORD_CANDIDATES]


def _result(row: Row, score: float | None) -> dict[str, Any]:
    _, path, start, end, text = row
    return {"path": path, "lines": f"{start}-{end}", "score": None if score is None else round(score, 4), "text": text}


def effective_ranking(conn: sqlite3.Connection, ranking: str) -> tuple[str, str | None]:
    """The ranking a search can actually use, and a note for the user when it differs: without a
    keyword index (no FTS5 in this SQLite build), every ranking falls back to ``semantic``."""
    if ranking not in RANKINGS:
        raise ValueError(f"ranking must be one of {', '.join(RANKINGS)}")
    if ranking != "semantic" and not has_keyword_index(conn):
        return "semantic", NO_KEYWORD_NOTE
    return ranking, None


def search(
    conn: sqlite3.Connection,
    root: Path,
    model: str,
    query_vector: list[float] | None,
    top_k: int = 5,
    path_filter: patterns.PathFilter | None = None,
    *,
    query: str = "",
    ranking: str = "hybrid",
) -> list[dict[str, Any]]:
    """The ``top_k`` best chunks for a query, best first, limited to files ``path_filter`` matches.

    ``semantic`` ranks by cosine similarity to ``query_vector``; ``keyword`` ranks the chunks that
    contain ``query``'s words by BM25; ``hybrid`` (the default) ranks questions by meaning and, for
    queries made only of code-like names (see ``looks_like_code``), merges both rankings with
    keywords leading (see ``fuse_scores``), so an exact name or error code comes first even when the
    embedding model blurs it. ``score`` is always the cosine similarity when there is a query vector.
    """
    if ranking not in RANKINGS:
        raise ValueError(f"ranking must be one of {', '.join(RANKINGS)}")
    if top_k < 1:
        return []
    vector = (
        _vector_scores(conn, root, model, query_vector, path_filter) if query_vector and ranking != "keyword" else []
    )
    cosine = {row[0]: score for score, row in vector}
    if ranking == "semantic" or (ranking == "hybrid" and not looks_like_code(query)):
        return [_result(row, score) for score, row in vector[:top_k]]
    keyword = _keyword_ranking(conn, root, model, query, path_filter)
    if ranking == "keyword":
        return [_result(row, cosine.get(row[0])) for _, row in keyword[:top_k]]
    rows = {row[0]: row for _, row in keyword} | {row[0]: row for _, row in vector}
    best = fuse_scores(
        [(score, row[0]) for score, row in vector], [(score, row[0]) for score, row in keyword], _CODE_MEANING_WEIGHT
    )
    return [_result(rows[rowid], cosine.get(rowid)) for rowid in best[:top_k]]


def fuse_scores(meaning: list[tuple[float, int]], keyword: list[tuple[float, int]], meaning_weight: float) -> list[int]:
    """Relative score fusion: scale each list's scores to 0..1 (best is 1, worst is 0; all 1 when they
    are equal), weight meaning by ``meaning_weight`` and keywords by the rest, add the two for each id
    (0 for a list it is missing from) and return the ids best first. Ties keep the meaning order."""
    fused: dict[int, float] = {}
    for ranked, weight in ((meaning, meaning_weight), (keyword, 1.0 - meaning_weight)):
        if not ranked:
            continue
        high, low = max(score for score, _ in ranked), min(score for score, _ in ranked)
        for score, item in ranked:
            scaled = (score - low) / (high - low) if high > low else 1.0
            fused[item] = fused.get(item, 0.0) + weight * scaled
    return sorted(fused, key=lambda item: fused[item], reverse=True)


def file_vector(
    conn: sqlite3.Connection, root: Path, model: str, rel_path: str, lines: tuple[int, int] | None = None
) -> list[float] | None:
    """The mean direction of a file's indexed chunks (only those overlapping ``lines`` when given),
    or ``None`` when the file, or that part of it, is not in the index."""
    total: list[float] = []
    count = 0
    for start, end, blob, norm in conn.execute(
        "SELECT start_line, end_line, vec, norm FROM chunks WHERE root = ? AND model = ? AND path = ?",
        (str(root), model, rel_path),
    ):
        if norm == 0 or (lines and (end < lines[0] or start > lines[1])):
            continue
        vec = array.array("f")
        vec.frombytes(blob)
        if not total:
            total = [0.0] * len(vec)
        if len(vec) != len(total):
            continue
        for i, v in enumerate(vec):
            total[i] += v / norm
        count += 1
    return [v / count for v in total] if count else None


def similar(
    conn: sqlite3.Connection,
    root: Path,
    model: str,
    vector: list[float],
    top_k: int = 5,
    path_filter: patterns.PathFilter | None = None,
    *,
    exclude_path: str | None = None,
) -> list[dict[str, Any]]:
    """Other files most similar to ``vector``: each file's best chunk, best first. ``exclude_path``
    leaves out the file the vector came from."""
    if top_k < 1:
        return []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, row in _vector_scores(conn, root, model, vector, path_filter, exclude_path):
        if row[1] in seen:
            continue
        seen.add(row[1])
        results.append(_result(row, score))
        if len(results) >= top_k:
            break
    return results
