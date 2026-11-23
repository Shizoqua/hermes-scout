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

from . import checks, embeddings, engine, patterns, schemas

logger = logging.getLogger(__name__)

__version__ = "0.4.0"

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
    "read_documents": True,
    "ranking": "hybrid",
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


def _index_path() -> Path:
    from plugins.plugin_storage import plugin_data_dir

    return Path(plugin_data_dir(PLUGIN_ID)) / "index.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_index_path(), timeout=30)
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


Prepared = tuple[Path, str, "engine.Embedder", patterns.PathFilter, sqlite3.Connection, dict[str, int]]


def _prepare(ctx: Any, args: dict[str, Any]) -> Prepared | dict[str, Any]:
    """Resolve and check the folder, refresh its index and open it: what both tools start with.
    Returns an error dict instead when the folder is unusable."""
    root = _resolve_root(args.get("path"))
    if not root.is_dir():
        return {"error": f"not a folder: {root}"}
    if blocked := _read_blocked(root):
        return {"error": blocked}
    model, embed = _embedder(ctx)
    files = list(
        engine.iter_files(
            root,
            max_files=_setting(ctx, "max_files"),
            max_file_bytes=_setting(ctx, "max_file_kb") * 1024,
            is_blocked=_read_blocked,
            respect_gitignore=_setting(ctx, "respect_gitignore"),
            read_documents=_setting(ctx, "read_documents"),
        )
    )
    conn = _connect()
    try:
        with _INDEX_LOCK:
            stats = engine.update_index(conn, root, model, embed, files, max_chars=_setting(ctx, "chunk_chars"))
    except BaseException:
        conn.close()
        raise
    return root, model, embed, patterns.PathFilter(args.get("glob")), conn, stats


def _top_k(ctx: Any, args: dict[str, Any]) -> int:
    return min(20, max(1, int(args.get("top_k") or _setting(ctx, "top_k"))))


def _search(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    if args.get("ranking"):
        ranking = str(args["ranking"]).strip().lower()
        if ranking not in engine.RANKINGS:
            return {"error": f"ranking must be one of {', '.join(engine.RANKINGS)}"}
    else:  # the setting; an unknown value there falls back to the default instead of failing every search
        ranking = str(_setting(ctx, "ranking")).strip().lower()
        if ranking not in engine.RANKINGS:
            ranking = DEFAULTS["ranking"]
    top_k = _top_k(ctx, args)
    prepared = _prepare(ctx, args)
    if isinstance(prepared, dict):
        return prepared
    root, model, embed, path_filter, conn, stats = prepared
    try:
        ranking, note = engine.effective_ranking(conn, ranking)
        vector = embed([query])[0] if ranking != "keyword" else None
        results = engine.search(conn, root, model, vector, top_k, path_filter, query=query, ranking=ranking)
    finally:
        conn.close()
    out = {"query": query, "ranking": ranking, "root": str(root), "model": model, "results": results, "index": stats}
    if note:
        out["note"] = note
    if path_filter:
        out["glob"] = path_filter.globs
    return out


def _parse_lines(raw: Any) -> tuple[int, int] | None:
    """``"10-40"`` or ``"12"`` as an inclusive line range; ``None`` for no range."""
    text = str(raw or "").strip()
    if not text:
        return None
    first, _, last = text.partition("-")
    try:
        start, end = int(first), int(last or first)
    except ValueError:
        start = end = 0
    if start < 1 or end < start:
        raise ValueError(f"lines must look like '10-40', got {text!r}")
    return start, end


def _similar(ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
    file_arg = str(args.get("file") or "").strip()
    text = str(args.get("text") or "").strip()
    if bool(file_arg) == bool(text):
        return {"error": "give either file (a file in the folder) or text (a passage), not both"}
    try:
        lines = _parse_lines(args.get("lines"))
    except ValueError as err:
        return {"error": str(err)}
    top_k = _top_k(ctx, args)
    prepared = _prepare(ctx, args)
    if isinstance(prepared, dict):
        return prepared
    root, model, embed, path_filter, conn, stats = prepared
    try:
        rel = None
        if file_arg:
            target = Path(file_arg).expanduser()
            target = (target if target.is_absolute() else root / target).resolve()
            try:
                rel = target.relative_to(root).as_posix()
            except ValueError:
                return {"error": f"file is not inside the folder {root}: {file_arg}"}
            vector = engine.file_vector(conn, root, model, rel, lines)
            if vector is None:
                return {
                    "error": f"{rel} is not in the index (check its extension, size and .gitignore, and the line range)"
                }
        else:
            vector = embed([text])[0]
        results = engine.similar(conn, root, model, vector, top_k, path_filter, exclude_path=rel)
    finally:
        conn.close()
    out: dict[str, Any] = {"root": str(root), "model": model, "results": results, "index": stats}
    out["source"] = {"file": rel, "lines": args.get("lines") or None} if rel else {"text": text}
    if path_filter:
        out["glob"] = path_filter.globs
    return out


def _make_handler(ctx: Any, name: str, run: Callable[[Any, dict[str, Any]], dict[str, Any]]) -> Callable[..., str]:
    def handler(args: dict[str, Any], **_kwargs: Any) -> str:
        try:
            return json.dumps(run(ctx, args or {}), ensure_ascii=False)
        except embeddings.EmbeddingError as err:
            return json.dumps({"error": str(err)})
        except (OSError, ValueError, sqlite3.Error) as err:
            logger.warning("%s failed", name, exc_info=True)
            return json.dumps({"error": f"{name} failed: {err}"})

    return handler


COMMAND_HELP = """/scout status: list the indexed folders
/scout doctor: check the embeddings server, the model and keyword search
/scout index [folder]: build or refresh a folder's index now (default: the working directory)
/scout clear [folder|all]: forget a folder's index, or every index"""


def _command(ctx: Any, raw_args: str) -> str:
    """``/scout``: status, health checks and index upkeep without asking the model."""
    action, _, rest = (raw_args or "").strip().partition(" ")
    action, rest = action.lower(), rest.strip()
    try:
        if action == "status":
            conn = _connect()
            try:
                return checks.format_status(conn)
            finally:
                conn.close()
        if action == "doctor":
            model, embed = _embedder(ctx)
            conn = _connect()
            try:
                found = checks.run_checks(
                    base_url=_setting(ctx, "base_url"), model=model, embed=embed, conn=conn, index_path=_index_path()
                )
            finally:
                conn.close()
            return checks.format_checks(found)
        if action == "index":
            prepared = _prepare(ctx, {"path": rest or None})
            if isinstance(prepared, dict):
                return f"error: {prepared['error']}"
            root, *_, conn, stats = prepared
            conn.close()
            return (
                f"{root}: indexed {stats['indexed_files']} new or changed files, reused {stats['reused_files']}, "
                f"removed {stats['removed_files']}; {stats['chunks']} chunks in the index."
            )
        if action == "clear":
            if not rest:
                return "Say which index to forget: /scout clear <folder>, or /scout clear all"
            target: Path | None = None if rest.lower() == "all" else _resolve_root(rest)
            conn = _connect()
            try:
                with _INDEX_LOCK:
                    forgotten = engine.clear_index(conn, target)
            finally:
                conn.close()
            where = "every folder" if target is None else str(target)
            return f"Forgot the index of {where} ({forgotten} files). The next search indexes it again."
    except embeddings.EmbeddingError as err:
        return f"error: {err}"
    except (OSError, ValueError, sqlite3.Error) as err:
        logger.warning("/scout %s failed", action, exc_info=True)
        return f"error: /scout {action} failed: {err}"
    return COMMAND_HELP


_SKILL_MD = Path(__file__).parent / "skills" / "scout" / "SKILL.md"


def _register_skill(ctx: Any) -> None:
    """The bundled skill, on Hermes versions that support plugin skills; never fatal."""
    if not hasattr(ctx, "register_skill") or not _SKILL_MD.is_file():
        return
    try:
        ctx.register_skill("scout", _SKILL_MD, description="When to search local files with the scout tools")
    except Exception:  # a skill must never take the tools down
        logger.debug("hermes-scout skill not registered", exc_info=True)


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="scout_search",
        toolset="hermes_scout",
        schema=schemas.SCOUT_SEARCH,
        handler=_make_handler(ctx, "scout_search", _search),
        description="Search local files by meaning and keywords",
        emoji="🔎",
    )
    ctx.register_tool(
        name="scout_similar",
        toolset="hermes_scout",
        schema=schemas.SCOUT_SIMILAR,
        handler=_make_handler(ctx, "scout_similar", _similar),
        description="Find files related to a file or passage",
        emoji="🧭",
    )
    if hasattr(ctx, "register_command"):
        ctx.register_command(
            "scout",
            handler=lambda raw_args="": _command(ctx, raw_args),
            description="hermes-scout index status, health checks and upkeep",
            args_hint="[status|doctor|index [folder]|clear <folder|all>]",
        )
    _register_skill(ctx)
