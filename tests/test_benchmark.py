"""The benchmark script: its data is consistent and it scores rankings correctly."""

import importlib.util
import json
from pathlib import Path

from test_cli import server  # noqa: F401  (pytest fixture)
from test_engine import toy_embed

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("benchmark", REPO / "scripts" / "benchmark.py")
assert _spec and _spec.loader
benchmark = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(benchmark)


def _questions():
    return json.loads((REPO / "benchmarks" / "questions.json").read_text(encoding="utf-8"))["questions"]


def test_every_answer_is_a_file_in_the_corpus():
    corpus = REPO / "benchmarks" / "corpus"
    questions = _questions()
    assert len(questions) == 30
    assert {q["kind"] for q in questions} == {"paraphrase", "exact", "mixed"}
    for q in questions:
        assert (corpus / q["answer"]).is_file(), q["answer"]


def test_ranked_files_keeps_the_first_passage_of_each_file():
    results = [{"path": "a.md"}, {"path": "b.md"}, {"path": "a.md"}, {"path": "c.md"}]
    assert benchmark.ranked_files(results) == ["a.md", "b.md", "c.md"]


def test_keyword_ranking_finds_every_exact_identifier_first():
    report = benchmark.evaluate(REPO / "benchmarks" / "corpus", _questions(), toy_embed, "toy")
    assert set(report["modes"]) == {"hybrid", "semantic", "keyword"}
    assert report["modes"]["keyword"]["by_kind"]["exact"]["hit@1"] == 1.0
    for mode in report["modes"].values():
        scores = mode["overall"]
        assert 0 <= scores["hit@1"] <= scores["hit@5"] <= 1 and 0 <= scores["mrr"] <= 1
    table = benchmark.markdown(report)
    assert table.count("\n| ") == 4  # header plus one row per ranking mode


def test_main_writes_the_table_json_and_job_summary(server, tmp_path, monkeypatch, capsys):  # noqa: F811
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    out = tmp_path / "results.json"
    assert benchmark.main(["--base-url", server["url"], "--model", "toy", "--json", str(out)]) == 0
    assert "| hybrid |" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["questions"] == 30
    assert summary.read_text(encoding="utf-8").startswith("## hermes-scout benchmark")


def test_main_reports_an_unreachable_server(capsys):
    assert benchmark.main(["--base-url", "http://127.0.0.1:9/v1"]) == 1
    assert "cannot reach the embeddings server" in capsys.readouterr().err
