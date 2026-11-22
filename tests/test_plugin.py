"""The Hermes wiring in __init__.py, run against stand-ins for the Hermes helpers it imports."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest
from test_engine import toy_embed

ROOT = Path(__file__).resolve().parents[1]


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

    spec = importlib.util.spec_from_file_location(
        "semantic_search_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "semantic_search_plugin", module)
    spec.loader.exec_module(module)

    calls = []

    def fake_embed(texts, **kwargs):
        calls.append((texts, kwargs))
        return toy_embed(texts)

    monkeypatch.setattr(module.embeddings, "embed_texts", fake_embed)
    module.work, module.calls = work, calls
    return module


def _call(plugin, args, settings=None):
    ctx = FakeCtx(settings)
    plugin.register(ctx)
    [tool] = ctx.tools
    return json.loads(tool["handler"](args))


def test_registers_exactly_the_declared_tool(plugin):
    ctx = FakeCtx()
    plugin.register(ctx)
    [tool] = ctx.tools
    assert (tool["name"], tool["schema"]["name"]) == ("semantic_search", "semantic_search")
    assert tool["schema"]["parameters"]["required"] == ["query"]


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
