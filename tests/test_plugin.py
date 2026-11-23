"""The Hermes wiring in __init__.py, run against stand-ins for the Hermes helpers it imports."""

import json
import sys
import types
from pathlib import Path

import pytest
from test_engine import toy_embed


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.tools = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)


def _module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    """The plugin package with Hermes's helpers replaced: the working directory is ``tmp_path/work``,
    plugin data goes to ``tmp_path/data``, ``.env`` files are read-blocked and no secret is set."""
    work, data = tmp_path / "work", tmp_path / "data"
    work.mkdir()
    for package in ("agent", "plugins", "hermes_cli"):
        _module(monkeypatch, package)
    _module(monkeypatch, "agent.runtime_cwd", resolve_agent_cwd=lambda: work)
    _module(
        monkeypatch,
        "agent.file_safety",
        get_read_block_error=lambda path: "blocked by Hermes" if path.endswith(".env") else None,
    )
    _module(monkeypatch, "agent.secret_scope", get_secret=lambda name, default=None: None)

    def plugin_data_dir(name):
        data.mkdir(exist_ok=True)
        return data

    _module(monkeypatch, "plugins.plugin_storage", plugin_data_dir=plugin_data_dir)

    import hermes_scout as module

    calls = []

    def fake_embed(texts, **kwargs):
        calls.append((texts, kwargs))
        return toy_embed(texts)

    monkeypatch.setattr(module.embeddings, "embed_texts", fake_embed)
    module.work, module.calls = work, calls
    return module


def _call(plugin, args, settings=None, tool="scout_search"):
    ctx = FakeCtx(settings)
    plugin.register(ctx)
    [found] = [t for t in ctx.tools if t["name"] == tool]
    return json.loads(found["handler"](args))


def test_registers_exactly_the_declared_tools(plugin):
    ctx = FakeCtx()
    plugin.register(ctx)
    assert [(t["name"], t["schema"]["name"], t["toolset"]) for t in ctx.tools] == [
        ("scout_search", "scout_search", "hermes_scout"),
        ("scout_similar", "scout_similar", "hermes_scout"),
    ]
    manifest = (Path(plugin.__file__).parent / "plugin.yaml").read_text(encoding="utf-8")
    assert "  - scout_search\n  - scout_similar\n" in manifest
    assert ctx.tools[0]["schema"]["parameters"]["required"] == ["query"]


def test_search_resolves_relative_paths_and_ranks_results(plugin):
    notes = plugin.work / "notes"
    notes.mkdir()
    (notes / "retries.md").write_text("The client backs off and retries after a 429 rate limit.", encoding="utf-8")
    (notes / "pasta.md").write_text("Boil pasta in salted water.", encoding="utf-8")

    out = _call(plugin, {"query": "how are rate limit retries handled", "path": "notes", "top_k": 1})
    assert out["root"] == str(notes.resolve())
    assert [r["path"] for r in out["results"]] == ["retries.md"]
    assert out["index"]["indexed_files"] == 2


def test_settings_reach_the_embeddings_client(plugin):
    (plugin.work / "a.md").write_text("alpha", encoding="utf-8")
    settings = {"base_url": "http://127.0.0.1:1234/v1", "embedding_model": "my-embedder"}
    out = _call(plugin, {"query": "alpha"}, settings)
    assert out["model"] == "my-embedder"
    _, kwargs = plugin.calls[-1]
    assert (kwargs["base_url"], kwargs["model"], kwargs["api_key"]) == ("http://127.0.0.1:1234/v1", "my-embedder", None)


def test_blocked_files_are_never_embedded(plugin):
    (plugin.work / "notes.txt").write_text("public notes", encoding="utf-8")
    (plugin.work / "secrets.env").write_text("KEY=value", encoding="utf-8")
    _call(plugin, {"query": "notes"})
    embedded = [text for texts, _ in plugin.calls for text in texts]
    assert "KEY=value" not in embedded and "public notes" in embedded


def test_invalid_numeric_settings_fall_back_to_defaults(plugin):
    (plugin.work / "a.md").write_text("alpha", encoding="utf-8")
    out = _call(plugin, {"query": "alpha"}, {"top_k": "lots", "max_files": None})
    assert len(out["results"]) == 1


@pytest.mark.parametrize(
    "args,message",
    [
        ({}, "query is required"),
        ({"query": "x", "path": "missing-folder"}, "not a folder"),
    ],
)
def test_bad_arguments_return_an_error(plugin, args, message):
    assert message in _call(plugin, args)["error"]


def test_embedding_errors_come_back_as_a_tool_error(plugin, monkeypatch):
    (plugin.work / "a.md").write_text("alpha", encoding="utf-8")

    def unreachable(texts, **kwargs):
        raise plugin.embeddings.EmbeddingError("cannot reach the embeddings server at http://x")

    monkeypatch.setattr(plugin.embeddings, "embed_texts", unreachable)
    assert _call(plugin, {"query": "alpha"}) == {"error": "cannot reach the embeddings server at http://x"}


def test_glob_filters_results_and_gitignore_is_respected(plugin):
    (plugin.work / ".gitignore").write_text("private/\n", encoding="utf-8")
    for folder in ("docs", "src", "private"):
        (plugin.work / folder).mkdir()
    (plugin.work / "docs" / "a.md").write_text("alpha notes", encoding="utf-8")
    (plugin.work / "src" / "a.py").write_text("alpha code", encoding="utf-8")
    (plugin.work / "private" / "a.md").write_text("alpha private", encoding="utf-8")
    out = _call(plugin, {"query": "alpha", "glob": "*.md"})
    assert [r["path"] for r in out["results"]] == ["docs/a.md"] and out["glob"] == ["*.md"]
    out = _call(plugin, {"query": "alpha", "glob": "*.md"}, {"respect_gitignore": "false"})
    assert sorted(r["path"] for r in out["results"]) == ["docs/a.md", "private/a.md"]


def _notes(plugin):
    folder = plugin.work / "notes"
    folder.mkdir()
    (folder / "retries.md").write_text("The client retries after a 429 rate limit.", encoding="utf-8")
    (folder / "limits.md").write_text("Rate limit windows reset every minute.", encoding="utf-8")
    (folder / "pasta.md").write_text("Boil pasta in salted water.", encoding="utf-8")
    return folder


def test_search_rankings(plugin):
    _notes(plugin)
    out = _call(plugin, {"query": "pasta", "path": "notes", "ranking": "keyword"})
    assert out["ranking"] == "keyword" and [r["path"] for r in out["results"]] == ["pasta.md"]
    out = _call(plugin, {"query": "rate limit", "path": "notes"})
    assert out["ranking"] == "hybrid" and out["results"][0]["path"] in {"retries.md", "limits.md"}
    assert "ranking must be one of" in _call(plugin, {"query": "x", "ranking": "fuzzy"})["error"]


def test_similar_from_a_file_skips_the_file_itself(plugin):
    _notes(plugin)
    out = _call(plugin, {"file": "retries.md", "path": "notes", "top_k": 2}, tool="scout_similar")
    assert out["source"] == {"file": "retries.md", "lines": None}
    assert [r["path"] for r in out["results"]] == ["limits.md", "pasta.md"]
    out = _call(plugin, {"file": "retries.md", "lines": "1-1", "path": "notes"}, tool="scout_similar")
    assert out["source"]["lines"] == "1-1" and "retries.md" not in [r["path"] for r in out["results"]]


def test_similar_from_text(plugin):
    _notes(plugin)
    out = _call(plugin, {"text": "salted pasta water", "path": "notes", "top_k": 1}, tool="scout_similar")
    assert out["source"] == {"text": "salted pasta water"} and out["results"][0]["path"] == "pasta.md"


@pytest.mark.parametrize(
    "args,message",
    [
        ({}, "give either file"),
        ({"file": "a.md", "text": "x"}, "give either file"),
        ({"file": "retries.md", "lines": "9-2"}, "lines must look like"),
        ({"file": "retries.md", "lines": "x"}, "lines must look like"),
        ({"file": "../outside.md"}, "not inside the folder"),
        ({"file": "missing.md"}, "is not in the index"),
        ({"file": "retries.md", "path": "missing-folder"}, "not a folder"),
    ],
)
def test_similar_rejects_bad_input(plugin, args, message):
    _notes(plugin)
    out = _call(plugin, {"path": "notes", **args}, tool="scout_similar")
    assert message in out["error"]


def test_ranking_setting_is_the_default_and_bad_values_fall_back(plugin):
    _notes(plugin)
    out = _call(plugin, {"query": "pasta", "path": "notes"}, {"ranking": "keyword"})
    assert out["ranking"] == "keyword" and [r["path"] for r in out["results"]] == ["pasta.md"]
    out = _call(plugin, {"query": "pasta", "path": "notes", "ranking": "semantic"}, {"ranking": "keyword"})
    assert out["ranking"] == "semantic"
    assert _call(plugin, {"query": "pasta", "path": "notes"}, {"ranking": "nonsense"})["ranking"] == "hybrid"


def test_without_fts5_search_notes_the_fallback(plugin, monkeypatch):
    _notes(plugin)
    monkeypatch.setattr(plugin.engine, "has_keyword_index", lambda conn: False)
    out = _call(plugin, {"query": "pasta", "path": "notes", "ranking": "keyword"})
    assert out["ranking"] == "semantic" and out["note"] == plugin.engine.NO_KEYWORD_NOTE
    assert out["results"]
