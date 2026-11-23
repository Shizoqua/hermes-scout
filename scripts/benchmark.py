"""Measure how often hermes-scout finds the right file, for each ranking mode.

Indexes the synthetic project in ``benchmarks/corpus`` with a real embeddings server, asks the
questions in ``benchmarks/questions.json`` (each has one correct file), and reports per ranking mode:

- hit@1: the correct file is the first result,
- hit@5: the correct file is among the first five files,
- MRR: mean reciprocal rank of the correct file (1.0 is perfect).

    python scripts/benchmark.py --base-url http://localhost:11434/v1 --model nomic-embed-text

Writes a Markdown table to stdout (and to the GitHub job summary when run in Actions) and, with
``--json``, the full results to a file. Standard library and hermes_scout only.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_scout import embeddings, engine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "benchmarks"
Embed = Callable[[list[str]], list[list[float]]]


def ranked_files(results: list[dict[str, Any]]) -> list[str]:
    """Distinct file paths in the order their best passage appears."""
    seen: list[str] = []
    for result in results:
        if result["path"] not in seen:
            seen.append(result["path"])
    return seen


def evaluate(corpus: Path, questions: list[dict[str, str]], embed: Embed, model: str) -> dict[str, Any]:
    """Index ``corpus`` once, then score every question under every ranking mode."""
    with tempfile.TemporaryDirectory() as tmp:
        conn = sqlite3.connect(Path(tmp) / "bench.db")
        try:
            engine.ensure_schema(conn)
            root = corpus.resolve()
            files = list(engine.iter_files(root, max_files=10_000, max_file_bytes=1_000_000))
            started = time.perf_counter()
            stats = engine.update_index(conn, root, model, embed, files)
            index_seconds = time.perf_counter() - started
            vectors = embed([q["question"] for q in questions])
            modes: dict[str, Any] = {}
            for ranking in engine.RANKINGS:
                ranking_used, _ = engine.effective_ranking(conn, ranking)
                rows = []
                for q, vector in zip(questions, vectors, strict=True):
                    results = engine.search(
                        conn,
                        root,
                        model,
                        None if ranking_used == "keyword" else vector,
                        20,
                        query=q["question"],
                        ranking=ranking_used,
                    )
                    files_ranked = ranked_files(results)
                    rank = files_ranked.index(q["answer"]) + 1 if q["answer"] in files_ranked else None
                    rows.append({**q, "rank": rank, "top": files_ranked[:5]})
                modes[ranking] = {"overall": _score(rows), "by_kind": _by_kind(rows), "questions": rows}
        finally:
            conn.close()
    return {
        "model": model,
        "files": len(files),
        "chunks": stats["chunks"],
        "questions": len(questions),
        "index_seconds": round(index_seconds, 2),
        "modes": modes,
    }


def _score(rows: list[dict[str, Any]]) -> dict[str, float]:
    n = len(rows) or 1
    return {
        "hit@1": round(sum(r["rank"] == 1 for r in rows) / n, 3),
        "hit@5": round(sum(r["rank"] is not None and r["rank"] <= 5 for r in rows) / n, 3),
        "mrr": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3),
    }


def _by_kind(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    kinds = sorted({r["kind"] for r in rows})
    return {kind: _score([r for r in rows if r["kind"] == kind]) for kind in kinds}


def markdown(report: dict[str, Any]) -> str:
    kinds = sorted(next(iter(report["modes"].values()))["by_kind"])
    lines = [
        f"Model `{report['model']}`, {report['files']} files ({report['chunks']} chunks), "
        f"{report['questions']} questions, indexed in {report['index_seconds']} s.",
        "",
        "| Ranking | hit@1 | hit@5 | MRR | " + " | ".join(f"{k} hit@1" for k in kinds) + " |",
        "|---|---|---|---|" + "---|" * len(kinds),
    ]
    for ranking, mode in report["modes"].items():
        o = mode["overall"]
        per_kind = " | ".join(f"{mode['by_kind'][k]['hit@1']:.0%}" for k in kinds)
        lines.append(f"| {ranking} | {o['hit@1']:.0%} | {o['hit@5']:.0%} | {o['mrr']:.2f} | {per_kind} |")
    return "\n".join(lines)


def _wait_for(embed: Embed, seconds: float) -> None:
    """Retry until the server answers; a fresh model server can take a moment to load the model."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            embed(["ready"])
            return
        except embeddings.EmbeddingError:
            if time.monotonic() > deadline:
                raise
            time.sleep(3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=os.environ.get("SCOUT_BASE_URL", embeddings.DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.environ.get("SCOUT_MODEL", embeddings.DEFAULT_MODEL))
    parser.add_argument("--corpus", type=Path, default=ROOT / "corpus")
    parser.add_argument("--questions", type=Path, default=ROOT / "questions.json")
    parser.add_argument("--json", type=Path, help="also write the full results to this file")
    parser.add_argument("--wait", type=float, default=0, help="seconds to wait for the server to come up")
    args = parser.parse_args(argv)

    api_key = os.environ.get("SCOUT_API_KEY") or None

    def embed(texts: list[str]) -> list[list[float]]:
        return embeddings.embed_texts(texts, base_url=args.base_url, model=args.model, api_key=api_key)

    try:
        _wait_for(embed, args.wait)
        questions = json.loads(args.questions.read_text(encoding="utf-8"))["questions"]
        report = evaluate(args.corpus, questions, embed, args.model)
    except embeddings.EmbeddingError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    table = markdown(report)
    print(table)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## hermes-scout benchmark\n\n" + table + "\n")
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
