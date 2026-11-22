"""Command line for using hermes-scout without Hermes.

    hermes-scout search "where do we handle rate limits" ~/notes
    hermes-scout index ~/notes

Settings come from flags, then the environment (SCOUT_BASE_URL, SCOUT_MODEL, SCOUT_API_KEY),
then the defaults (a local Ollama server with nomic-embed-text).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import __version__, embeddings, engine


def default_index_path() -> Path:
    """Per-user cache location: ``$XDG_CACHE_HOME``, ``%LOCALAPPDATA%`` on Windows, else ``~/.cache``."""
    base = os.environ.get("XDG_CACHE_HOME") or (os.environ.get("LOCALAPPDATA") if os.name == "nt" else None)
    return (Path(base) if base else Path.home() / ".cache") / "hermes-scout" / "index.db"


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--base-url",
        default=os.environ.get("SCOUT_BASE_URL", embeddings.DEFAULT_BASE_URL),
        help="OpenAI-compatible embeddings base URL (default: %(default)s)",
    )
    common.add_argument(
        "--model",
        default=os.environ.get("SCOUT_MODEL", embeddings.DEFAULT_MODEL),
        help="embedding model name (default: %(default)s)",
    )
    common.add_argument("--index", type=Path, default=None, help=f"index database (default: {default_index_path()})")
    common.add_argument("--chunk-chars", type=int, default=1200, help="chunk size in characters (default: 1200)")
    common.add_argument("--max-files", type=int, default=2000, help="files indexed per folder (default: 2000)")
    common.add_argument("--max-file-kb", type=int, default=1000, help="skip larger files (default: 1000)")

    parser = argparse.ArgumentParser(
        prog="hermes-scout", description="Search local files by meaning, using embeddings."
    )
    parser.add_argument("--version", action="version", version=f"hermes-scout {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", parents=[common], help="search a folder by meaning")
    search.add_argument("query", help="what to look for, in natural language")
    search.add_argument("path", nargs="?", default=".", help="folder to search (default: current folder)")
    search.add_argument("-k", "--top-k", type=int, default=5, help="passages to show (default: 5)")
    search.add_argument("--json", action="store_true", help="print the result as JSON")

    index = sub.add_parser("index", parents=[common], help="build or refresh the index for a folder")
    index.add_argument("path", nargs="?", default=".", help="folder to index (default: current folder)")
    return parser


def _open_index(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    engine.ensure_schema(conn)
    return conn


def _print_results(results: list[dict]) -> None:
    if not results:
        print("No matching passages.")
        return
    for result in results:
        print(f"{result['score']:.2f}  {result['path']}:{result['lines']}")
        first = next((line.strip() for line in result["text"].splitlines() if line.strip()), "")
        print(f"      {first[:100]}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a folder: {root}", file=sys.stderr)
        return 2
    api_key = os.environ.get("SCOUT_API_KEY") or None

    def embed(texts: list[str]) -> list[list[float]]:
        return embeddings.embed_texts(texts, base_url=args.base_url, model=args.model, api_key=api_key)

    files = list(
        engine.iter_files(root, max_files=max(1, args.max_files), max_file_bytes=max(1, args.max_file_kb) * 1024)
    )
    conn = _open_index(args.index or default_index_path())
    try:
        stats = engine.update_index(conn, root, args.model, embed, files, max_chars=max(1, args.chunk_chars))
        if args.command == "index":
            print(
                f"Indexed {stats['indexed_files']} new or changed files, reused {stats['reused_files']}, "
                f"removed {stats['removed_files']}; {stats['chunks']} chunks in the index."
            )
            return 0
        results = engine.search(conn, root, args.model, embed([args.query])[0], top_k=max(1, args.top_k))
    except embeddings.EmbeddingError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    if args.json:
        print(
            json.dumps(
                {"query": args.query, "root": str(root), "model": args.model, "results": results, "index": stats},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
