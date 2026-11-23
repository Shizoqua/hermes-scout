"""The standalone ``hermes-scout`` command against a local stub embeddings server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_engine import toy_embed

from hermes_scout import cli


@pytest.fixture
def server():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body["input"])
            data = [{"index": i, "embedding": vec} for i, vec in enumerate(toy_embed(body["input"]))]
            raw = json.dumps({"data": data}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield {"url": f"http://127.0.0.1:{httpd.server_port}/v1", "calls": calls}
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


@pytest.fixture
def notes(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "retries.md").write_text("The client backs off and retries after a 429 rate limit.", encoding="utf-8")
    (folder / "pasta.md").write_text("Boil pasta in salted water.", encoding="utf-8")
    return folder


def _run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_search_prints_ranked_passages(server, notes, tmp_path, capsys):
    code, out, _ = _run(
        capsys,
        "search",
        "how are rate limit retries handled",
        str(notes),
        "--base-url",
        server["url"],
        "--index",
        str(tmp_path / "i.db"),
    )
    assert code == 0
    first, second = (line for line in out.splitlines() if not line.startswith(" "))
    assert first.endswith("retries.md:1-1") and second.endswith("pasta.md:1-1")


def test_json_output_and_incremental_index(server, notes, tmp_path, capsys):
    args = [
        "search",
        "rate limit",
        str(notes),
        "--base-url",
        server["url"],
        "--index",
        str(tmp_path / "i.db"),
        "--json",
    ]
    _run(capsys, *args)
    code, out, _ = _run(capsys, *args)
    result = json.loads(out)
    assert code == 0
    assert result["index"]["indexed_files"] == 0 and result["index"]["reused_files"] == 2
    assert result["results"][0]["path"] == "retries.md"


def test_index_command_reports_counts(server, notes, tmp_path, capsys):
    code, out, _ = _run(capsys, "index", str(notes), "--base-url", server["url"], "--index", str(tmp_path / "i.db"))
    assert code == 0
    assert "Indexed 2 new or changed files" in out


def test_unreachable_server_is_a_clear_error(notes, tmp_path, capsys):
    code, _, err = _run(
        capsys, "search", "x", str(notes), "--base-url", "http://127.0.0.1:9/v1", "--index", str(tmp_path / "i.db")
    )
    assert code == 1
    assert "cannot reach the embeddings server" in err


def test_missing_folder_is_rejected(tmp_path, capsys):
    code, _, err = _run(capsys, "search", "x", str(tmp_path / "nope"), "--index", str(tmp_path / "i.db"))
    assert code == 2
    assert "not a folder" in err


def test_default_index_honours_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cli.default_index_path() == tmp_path / "hermes-scout" / "index.db"


def test_glob_and_no_gitignore_flags(server, notes, tmp_path, capsys):
    (notes / ".gitignore").write_text("pasta.md\n", encoding="utf-8")
    index = str(tmp_path / "index.db")
    common = ("--base-url", server["url"], "--index", index, "--json")
    _, out, _ = _run(capsys, "search", "pasta", str(notes), *common)
    assert [r["path"] for r in json.loads(out)["results"]] == ["retries.md"]
    _, out, _ = _run(capsys, "search", "pasta", str(notes), "--no-gitignore", "-g", "pasta*", *common)
    assert [r["path"] for r in json.loads(out)["results"]] == ["pasta.md"]


def test_search_ranking_flag(server, notes, tmp_path, capsys):
    index = str(tmp_path / "index.db")
    code, out, _ = _run(
        capsys, "search", "pasta", str(notes), "--ranking", "keyword", "--base-url", server["url"], "--index", index
    )
    assert code == 0 and "pasta.md" in out and "retries.md" not in out and "  -  " in out


def test_similar_command(server, notes, tmp_path, capsys, monkeypatch):
    common = ("--in", str(notes), "--base-url", server["url"], "--index", str(tmp_path / "index.db"))
    code, out, _ = _run(capsys, "similar", "retries.md", *common, "--json")
    assert code == 0
    payload = json.loads(out)
    assert payload["source"] == {"file": "retries.md", "lines": None}
    assert [r["path"] for r in payload["results"]] == ["pasta.md"]
    monkeypatch.chdir(notes)
    code, out, _ = _run(capsys, "similar", "retries.md", *common, "--lines", "1-1")
    assert code == 0 and "pasta.md" in out
    code, out, _ = _run(capsys, "similar", "--text", "salted water", *common)
    assert code == 0 and "pasta.md" in out


@pytest.mark.parametrize(
    "argv,message",
    [
        (("similar",), "either a FILE or --text"),
        (("similar", "retries.md", "--lines", "a-b"), "--lines must look like"),
        (("similar", "missing.md"), "is not in the index"),
        (("similar", "/etc/hostname"), "is not inside"),
    ],
)
def test_similar_command_errors(server, notes, tmp_path, capsys, argv, message):
    common = ("--in", str(notes), "--base-url", server["url"], "--index", str(tmp_path / "index.db"))
    code, _, err = _run(capsys, *argv, *common)
    assert code == 2 and message in err


def test_without_fts5_the_command_line_notes_the_fallback(server, notes, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli.engine, "has_keyword_index", lambda conn: False)
    common = ("--base-url", server["url"], "--index", str(tmp_path / "index.db"))
    code, out, err = _run(capsys, "search", "pasta", str(notes), *common, "--json")
    assert code == 0 and "note: Keyword search is not available" in err
    payload = json.loads(out)
    assert payload["ranking"] == "semantic" and payload["note"] == cli.engine.NO_KEYWORD_NOTE
