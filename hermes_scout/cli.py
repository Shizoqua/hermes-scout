"""Command line for using hermes-scout without Hermes.

    hermes-scout search "where do we handle rate limits" ~/notes
    hermes-scout search "backup schedule" ~/notes --glob "*.md"
    hermes-scout similar notes/backups.md --in ~/notes
    hermes-scout index ~/notes
    hermes-scout doctor
    hermes-scout status
    hermes-scout clear ~/notes

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
from typing import Any

from . import __version__, checks, embeddings, engine, patterns


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
    common.add_argument("--no-gitignore", action="store_true", help="also index files that .gitignore files ignore")

    parser = argparse.ArgumentParser(
        prog="hermes-scout", description="Search local files by meaning, using embeddings."
    )
    parser.add_argument("--version", action="version", version=f"hermes-scout {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", parents=[common], help="search a folder by meaning")
    search.add_argument("query", help="what to look for, in natural language")
    search.add_argument("path", nargs="?", default=".", help="folder to search (default: current folder)")
    search.add_argument("-k", "--top-k", type=int, default=5, help="passages to show (default: 5)")
    search.add_argument(
        "-g",
        "--glob",
        action="append",
        default=[],
        help="only search matching files, e.g. '*.md', 'docs/' or 'src/**/*.py' (repeatable)",
    )
    search.add_argument(
        "--ranking",
        choices=engine.RANKINGS,
        default="hybrid",
        help="hybrid: meaning and exact words together (default); semantic: meaning only; keyword: words only",
    )
    search.add_argument("--json", action="store_true", help="print the result as JSON")

    similar = sub.add_parser("similar", parents=[common], help="find files related to a file or a passage")
    similar.add_argument("file", nargs="?", help="a file in the folder to find related files for")
    similar.add_argument("--text", help="a passage to find related files for, instead of a file")
    similar.add_argument("--lines", help="only use this part of the file, e.g. 10-40")
    similar.add_argument("--in", dest="path", default=".", help="folder to look in (default: current folder)")
    similar.add_argument("-k", "--top-k", type=int, default=5, help="related files to show (default: 5)")
    similar.add_argument("-g", "--glob", action="append", default=[], help="only consider matching files (repeatable)")
    similar.add_argument("--json", action="store_true", help="print the result as JSON")

    index = sub.add_parser("index", parents=[common], help="build or refresh the index for a folder")
    index.add_argument("path", nargs="?", default=".", help="folder to index (default: current folder)")

    sub.add_parser("doctor", parents=[common], help="check the embeddings server, the model and keyword search")
    sub.add_parser("status", parents=[common], help="list the indexed folders")
    clear = sub.add_parser("clear", parents=[common], help="forget a folder's index (or every index with --all)")
    clear.add_argument("path", nargs="?", help="folder whose index to forget")
    clear.add_argument("--all", action="store_true", help="forget every folder's index")
    return parser


def _maintenance(args: argparse.Namespace, embed: engine.Embedder) -> int:
    """``doctor``, ``status`` and ``clear``: commands about the index rather than one folder's search."""
    index_path = args.index or default_index_path()
    if args.command == "clear" and bool(args.path) == bool(args.all):
        print("error: give a FOLDER or --all", file=sys.stderr)
        return 2
    conn = _open_index(index_path)
    try:
        if args.command == "doctor":
            found = checks.run_checks(
                base_url=args.base_url, model=args.model, embed=embed, conn=conn, index_path=index_path
            )
            print(checks.format_checks(found))
            return 0 if all(c.ok for c in found) else 1
        if args.command == "status":
            print(checks.format_status(conn))
            return 0
        root = None if args.all else Path(args.path).expanduser().resolve()
        forgotten = engine.clear_index(conn, root)
        print(f"Forgot the index of {'every folder' if root is None else root} ({forgotten} files).")
        return 0
    finally:
        conn.close()


def _open_index(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    engine.ensure_schema(conn)
    return conn


def _print_results(results: list[dict[str, Any]]) -> None:
    if not results:
        print("No matching passages.")
        return
    for result in results:
        score = "  -  " if result["score"] is None else f"{result['score']:.2f}"
        print(f"{score}  {result['path']}:{result['lines']}")
        first = next((line.strip() for line in result["text"].splitlines() if line.strip()), "")
        print(f"      {first[:100]}")


def _similar(args: argparse.Namespace, conn: sqlite3.Connection, root: Path, embed: engine.Embedder) -> Any:
    """Results for ``similar``, or an error message (str) when the input is unusable."""
    if bool(args.file) == bool(args.text):
        return "give either a FILE or --text, not both"
    path_filter = patterns.PathFilter(args.glob)
    top_k = max(1, args.top_k)
    if args.text:
        return engine.similar(conn, root, args.model, embed([args.text])[0], top_k, path_filter)
    target = Path(args.file).expanduser()
    target = (target if target.is_absolute() else Path.cwd() / target).resolve()
    if not target.is_relative_to(root):
        target = (root / args.file).resolve()  # also accept a path relative to the folder
    if not target.is_relative_to(root):
        return f"{args.file} is not inside {root}"
    rel = target.relative_to(root).as_posix()
    lines = None
    if args.lines:
        first, _, last = args.lines.partition("-")
        try:
            lines = (int(first), int(last or first))
        except ValueError:
            return f"--lines must look like 10-40, got {args.lines!r}"
    vector = engine.file_vector(conn, root, args.model, rel, lines)
    if vector is None:
        return f"{rel} is not in the index (check its extension, size and .gitignore, and --lines)"
    return engine.similar(conn, root, args.model, vector, top_k, path_filter, exclude_path=rel)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    api_key = os.environ.get("SCOUT_API_KEY") or None

    def embed(texts: list[str]) -> list[list[float]]:
        return embeddings.embed_texts(texts, base_url=args.base_url, model=args.model, api_key=api_key)

    if args.command in ("doctor", "status", "clear"):
        return _maintenance(args, embed)
    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a folder: {root}", file=sys.stderr)
        return 2

    files = list(
        engine.iter_files(
            root,
            max_files=max(1, args.max_files),
            max_file_bytes=max(1, args.max_file_kb) * 1024,
            respect_gitignore=not args.no_gitignore,
        )
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
        if args.command == "similar":
            results = _similar(args, conn, root, embed)
            if isinstance(results, str):
                print(f"error: {results}", file=sys.stderr)
                return 2
            head: dict[str, Any] = {
                "source": {"file": args.file, "lines": args.lines} if args.file else {"text": args.text}
            }
        else:
            ranking, note = engine.effective_ranking(conn, args.ranking)
            if note:
                print(f"note: {note}", file=sys.stderr)
            vector = embed([args.query])[0] if ranking != "keyword" else None
            results = engine.search(
                conn,
                root,
                args.model,
                vector,
                max(1, args.top_k),
                patterns.PathFilter(args.glob),
                query=args.query,
                ranking=ranking,
            )
            head = {"query": args.query, "ranking": ranking}
            if note:
                head["note"] = note
    except embeddings.EmbeddingError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    if args.json:
        payload = {**head, "root": str(root), "model": args.model, "results": results, "index": stats}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_results(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
