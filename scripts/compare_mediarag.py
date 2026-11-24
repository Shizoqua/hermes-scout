"""Score mediarag on the hermes-scout benchmark: same 30 questions, same files, same scoring.

One-off comparison run by .github/workflows/compare-mediarag.yml. Two modes:

- ``shipped``: mediarag indexes the benchmark folder as it is. It reads .md and .txt text files
  but not source code or YAML, so answers in those files cannot be found; that is how a user
  would experience it.
- ``same-text``: every .py and .yaml file is copied as ``<name>.txt`` so mediarag indexes the
  same text hermes-scout does, and results are mapped back to the original file names.

    python scripts/compare_mediarag.py --mediarag path/to/mediarag --mode same-text --json out.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark import _by_kind, _score  # noqa: E402  (same scoring as the scout benchmark)

RENAMED = (".py", ".yaml")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mediarag", type=Path, required=True, help="a checkout of mediarag")
    parser.add_argument("--mode", choices=["shipped", "same-text"], required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.mediarag.resolve()))
    from core import tools  # mediarag's own tool functions, as its MCP server calls them

    questions = json.loads((ROOT / "benchmarks" / "questions.json").read_text(encoding="utf-8"))["questions"]
    with tempfile.TemporaryDirectory() as tmp:
        corpus = Path(tmp) / "corpus"
        shutil.copytree(ROOT / "benchmarks" / "corpus", corpus)
        if args.mode == "same-text":
            for path in list(corpus.rglob("*")):
                if path.suffix in RENAMED:
                    path.rename(path.with_name(path.name + ".txt"))
        store = str(Path(tmp) / "store")
        started = time.perf_counter()
        ingest = tools.tool_ingest_dir(str(corpus), root=store)
        index_seconds = time.perf_counter() - started

        def original(uri: str) -> str:
            rel = Path(uri).resolve().relative_to(corpus.resolve()).as_posix()
            if args.mode == "same-text" and rel.endswith(tuple(s + ".txt" for s in RENAMED)):
                rel = rel[: -len(".txt")]
            return rel

        rows = []
        for q in questions:
            hits = tools.tool_search(q["question"], k=20, root=store, include_thumbnails=False)["results"]
            ranked: list[str] = []
            for hit in hits:
                name = original(hit["uri"])
                if name not in ranked:
                    ranked.append(name)
            rank = ranked.index(q["answer"]) + 1 if q["answer"] in ranked else None
            rows.append({**q, "rank": rank, "top": ranked[:5]})
    report = {
        "tool": "mediarag",
        "mode": args.mode,
        "ingest": {k: v for k, v in ingest.items() if not isinstance(v, list)} if isinstance(ingest, dict) else ingest,
        "index_seconds": round(index_seconds, 2),
        "overall": _score(rows),
        "by_kind": _by_kind(rows),
        "questions": rows,
    }
    args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"mediarag {args.mode}: {json.dumps(report['overall'])} by kind {json.dumps(report['by_kind'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
