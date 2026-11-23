"""Health checks and index status, shared by the ``/scout`` command and ``hermes-scout doctor``.

Standard library only; no Hermes imports, so the command line can use it on its own.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import embeddings, engine


@dataclass(frozen=True)
class Check:
    ok: bool
    label: str
    detail: str


def run_checks(
    *,
    base_url: str,
    model: str,
    embed: Callable[[list[str]], list[list[float]]],
    conn: sqlite3.Connection,
    index_path: Path | None = None,
) -> list[Check]:
    """Everything a search needs: the embeddings server and model, keyword search, the index."""
    checks: list[Check] = []
    try:
        [vector] = embed(["hermes-scout health check"])
        checks.append(Check(True, "Embeddings", f"{base_url} answered with {len(vector)}-number vectors from {model}"))
    except embeddings.EmbeddingError as err:
        checks.append(Check(False, "Embeddings", str(err)))

    if engine.has_keyword_index(conn):
        checks.append(Check(True, "Keyword search", "SQLite full-text search (FTS5) is available"))
    else:
        checks.append(Check(False, "Keyword search", engine.NO_KEYWORD_NOTE))

    folders = engine.index_overview(conn)
    where = f" at {index_path}" if index_path else ""
    size = ""
    if index_path is not None and index_path.exists():
        size = f", {index_path.stat().st_size / 1_048_576:.1f} MB"
    checks.append(Check(True, "Index", f"{len(folders)} folder(s) indexed{where}{size}"))
    return checks


def format_checks(checks: list[Check]) -> str:
    lines = [f"{'OK  ' if c.ok else 'FAIL'}  {c.label}: {c.detail}" for c in checks]
    failed = sum(not c.ok for c in checks)
    lines.append("All checks passed." if not failed else f"{failed} check(s) failed; see above for how to fix them.")
    return "\n".join(lines)


def format_status(conn: sqlite3.Connection) -> str:
    folders = engine.index_overview(conn)
    if not folders:
        return "No folders indexed yet. The first search of a folder indexes it."
    lines = [f"{len(folders)} folder(s) indexed:"]
    lines += [f"  {f['root']}  ({f['model']}): {f['files']} files, {f['chunks']} chunks" for f in folders]
    return "\n".join(lines)
