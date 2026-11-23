"""hermes-scout: find passages in local files by meaning, using embeddings.

Hermes wiring only. The search itself lives in ``engine`` (chunking, index, ranking) and the HTTP
client in ``embeddings``; both are standard library only.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import embeddings, engine, patterns, schemas

logger = logging.getLogger(__name__)

__version__ = "0.2.0"

PLUGIN_ID = "hermes-scout"
API_KEY_ENV = "SCOUT_API_KEY"
DEFAULTS: dict[str, Any] = {
    "base_url": embeddings.DEFAULT_BASE_URL,
    "embedding_model": embeddings.DEFAULT_MODEL,
    "top_k": 5,
    "chunk_chars": 1200,
    "max_files": 2000,
    "max_file_kb": 1000,
    "respect_gitignore": True,
}
# One indexing pass at a time: two concurrent first searches of a big folder would embed it twice.
_INDEX_LOCK = threading.Lock()


def _setting(ctx: Any, key: str) -> Any:
    value = ctx.get_config(key, default=DEFAULTS[key])
    default = DEFAULTS[key]
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.strip().lower() not in ("false", "no", "off", "0", "")
        return default if value is None else bool(value)
    if isinstance(default, int):
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return default
    return str(value).strip() or default


def _resolve_root(raw: Any) -> Path:
    from agent.runtime_cwd import resolve_agent_cwd

    base = resolve_agent_cwd()
    path = Path(str(raw)).expanduser() if raw else base
    return (path if path.is_absolute() else base / path).resolve()


def _read_blocked(path: Path) -> str | None:
    from agent.file_safety import get_read_block_error

    error: str | None = get_read_block_error(str(path))
    return error


def _connect() -> sqlite3.Connection:
    from plugins.plugin_storage import plugin_data_dir

    conn = sqlite3.connect(plugin_data_dir(PLUGIN_ID) / "index.db", timeout=30)
    engine.ensure_schema(conn)
    return conn


def _embedder(ctx: Any) -> tuple[str, engine.Embedder]:
    from agent.secret_scope import get_secret

    base_url, model = _setting(ctx, "base_url"), _setting(ctx, "embedding_model")
    api_key = get_secret(API_KEY_ENV)
    opener = None
    if api_key:
        from hermes_cli.urllib_security import open_credentialed_url

        opener = open_credentialed_url
    return model, lambda texts: embeddings.embed_texts(
        texts, base_url=base_url, model=model, api_key=api_key, opener=opener
    )


def _search(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    root = _resolve_root(args.get("path"))
    if not root.is_dir():
        return {"error": f"not a folder: {root}"}
    if blocked := _read_blocked(root):
        return {"error": blocked}
    top_k = min(20, max(1, int(args.get("top_k") or _setting(ctx, "top_k"))))
    model, embed = _embedder(ctx)
    files = list(
        engine.iter_files(
            root,
            max_files=_setting(ctx, "max_files"),
            max_file_bytes=_setting(ctx, "max_file_kb") * 1024,
            is_blocked=_read_blocked,
            respect_gitignore=_setting(ctx, "respect_gitignore"),
        )
    )
    path_filter = patterns.PathFilter(args.get("glob"))
    conn = _connect()
    try:
        with _INDEX_LOCK:
            stats = engine.update_index(conn, root, model, embed, files, max_chars=_setting(ctx, "chunk_chars"))
        results = engine.search(conn, root, model, embed([query])[0], top_k=top_k, path_filter=path_filter)
    finally:
        conn.close()
    out = {"query": query, "root": str(root), "model": model, "results": results, "index": stats}
    if path_filter:
        out["glob"] = path_filter.globs
    return out


def _make_handler(ctx: Any) -> Callable[..., str]:
    def handler(args: dict[str, Any], **_kwargs: Any) -> str:
        try:
            return json.dumps(_search(ctx, args or {}), ensure_ascii=False)
        except embeddings.EmbeddingError as err:
            return json.dumps({"error": str(err)})
        except (OSError, ValueError, sqlite3.Error) as err:
            logger.warning("scout_search failed", exc_info=True)
            return json.dumps({"error": f"semantic search failed: {err}"})

    return handler


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="scout_search",
        toolset="hermes_scout",
        schema=schemas.SEMANTIC_SEARCH,
        handler=_make_handler(ctx),
        description="Search local files by meaning",
        emoji="🔎",
    )
