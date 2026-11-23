"""Chunking, file selection, incremental indexing and ranking, with a deterministic toy embedder."""

import hashlib
import os
import re
import sqlite3

import pytest

from hermes_scout import engine

DIM = 64


def toy_embed(texts):
    """Bag of words hashed into DIM buckets: texts sharing words score high, unrelated ones near 0."""
    out = []
    for text in texts:
        vec = [0.0] * DIM
        for word in re.findall(r"[a-z]+", text.lower()):
            vec[int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIM] += 1.0
        out.append(vec)
    return out


class CountingEmbedder:
    def __init__(self):
        self.texts = []

    def __call__(self, texts):
        self.texts.extend(texts)
        return toy_embed(texts)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    engine.ensure_schema(connection)
    yield connection
    connection.close()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ── chunking ────────────────────────────────────────────────────────────────


def test_chunks_cover_every_line_within_the_size_cap_and_overlap():
    text = "\n".join(f"line number {i:03d}" for i in range(1, 101))
    chunks = engine.chunk_text(text, max_chars=200, overlap_lines=2)
    assert all(len(body) <= 200 for _, _, body in chunks)
    covered = set()
    for start, end, _ in chunks:
        covered.update(range(start, end + 1))
    assert covered == set(range(1, 101))
    for (_, prev_end, _), (next_start, _, _) in zip(chunks, chunks[1:], strict=False):
        assert next_start == prev_end - 1  # two shared lines


def test_an_overlong_line_is_split_and_nothing_is_lost():
    words = [f"word{i:04d}" for i in range(400)]
    text = "intro\n" + " ".join(words) + "\noutro"
    chunks = engine.chunk_text(text, max_chars=200)
    assert all(len(body) <= 200 for _, _, body in chunks)
    found = " ".join(body for _, _, body in chunks).split()
    assert set(words) <= set(found) and {"intro", "outro"} <= set(found)
    # Pieces of the long line all report line 2.
    assert {(s, e) for s, e, body in chunks if "word0200" in body} <= {(2, 2), (1, 2), (2, 3)}


def test_a_line_without_spaces_is_cut_at_the_limit():
    chunks = engine.chunk_text("x" * 450, max_chars=100)
    assert [len(body) for _, _, body in chunks] == [100, 100, 100, 100, 50]
    assert all((s, e) == (1, 1) for s, e, _ in chunks)


def test_long_lines_are_not_embedded_twice():
    text = "\n".join(chr(97 + i) * 590 for i in range(10))
    chunks = engine.chunk_text(text, max_chars=1200)
    assert sum(len(body) for _, _, body in chunks) <= len(text) * 1.25
    covered = set()
    for start, end, _ in chunks:
        covered.update(range(start, end + 1))
    assert covered == set(range(1, 11))


def test_blank_text_has_no_chunks():
    assert engine.chunk_text("\n\n   \n") == []


# ── file selection ──────────────────────────────────────────────────────────


def test_iter_files_skips_hidden_dependency_binary_oversized_and_blocked(tmp_path):
    keep = write(tmp_path / "notes" / "plan.md", "roadmap")
    write(tmp_path / ".git" / "config.md", "hidden dir")
    write(tmp_path / ".secret.md", "hidden file")
    write(tmp_path / "node_modules" / "pkg" / "readme.md", "dependency")
    write(tmp_path / "photo.png", "not a text extension")
    (tmp_path / "data.txt").write_bytes(b"bin\0ary")
    write(tmp_path / "big.txt", "y" * 3000)
    write(tmp_path / "private" / "keys.txt", "blocked by the host")

    found = list(
        engine.iter_files(
            tmp_path, max_file_bytes=2000, is_blocked=lambda p: "blocked" if p.parent.name == "private" else None
        )
    )
    assert found == [keep]


def test_iter_files_stops_at_max_files(tmp_path):
    for i in range(5):
        write(tmp_path / f"f{i}.txt", "content")
    assert len(list(engine.iter_files(tmp_path, max_files=3))) == 3


# ── indexing and search ─────────────────────────────────────────────────────


def test_search_ranks_the_matching_file_first(tmp_path, conn):
    write(tmp_path / "retry.md", "When the server answers 429 the client backs off with jitter before it retries.")
    write(tmp_path / "pasta.md", "Boil the pasta in salted water and add garlic and olive oil.")
    write(tmp_path / "garden.md", "Water the tomatoes in the morning and prune the basil.")
    files = list(engine.iter_files(tmp_path))
    engine.update_index(conn, tmp_path, "toy", toy_embed, files)

    results = engine.search(conn, tmp_path, "toy", toy_embed(["how does the client retry after 429"])[0], top_k=2)
    assert [r["path"] for r in results][0] == "retry.md"
    assert results[0]["lines"] == "1-1"
    assert results[0]["score"] >= results[1]["score"]


def test_reindex_embeds_only_changed_files_and_drops_deleted_ones(tmp_path, conn):
    a = write(tmp_path / "a.md", "alpha topic")
    b = write(tmp_path / "b.md", "beta topic")
    embedder = CountingEmbedder()
    first = engine.update_index(conn, tmp_path, "toy", embedder, list(engine.iter_files(tmp_path)))
    assert (first["indexed_files"], first["reused_files"], first["chunks"]) == (2, 0, 2)

    embedder.texts.clear()
    a.write_text("alpha topic, revised", encoding="utf-8")
    os.utime(a, ns=(a.stat().st_atime_ns, a.stat().st_mtime_ns + 1_000_000_000))
    b.unlink()
    second = engine.update_index(conn, tmp_path, "toy", embedder, list(engine.iter_files(tmp_path)))
    assert (second["indexed_files"], second["reused_files"], second["removed_files"], second["chunks"]) == (1, 0, 1, 1)
    assert embedder.texts == ["alpha topic, revised"]

    embedder.texts.clear()
    third = engine.update_index(conn, tmp_path, "toy", embedder, list(engine.iter_files(tmp_path)))
    assert (third["indexed_files"], third["reused_files"]) == (0, 1)
    assert embedder.texts == []


def test_indexes_for_different_models_do_not_mix(tmp_path, conn):
    write(tmp_path / "a.md", "alpha topic")
    files = list(engine.iter_files(tmp_path))
    engine.update_index(conn, tmp_path, "model-one", toy_embed, files)
    assert engine.search(conn, tmp_path, "model-two", toy_embed(["alpha"])[0]) == []
    assert len(engine.search(conn, tmp_path, "model-one", toy_embed(["alpha"])[0])) == 1


def test_embedder_returning_the_wrong_count_fails_loudly(tmp_path, conn):
    write(tmp_path / "a.md", "alpha topic")
    with pytest.raises(ValueError, match="1 texts"):
        engine.update_index(conn, tmp_path, "toy", lambda texts: [], list(engine.iter_files(tmp_path)))


def test_zero_query_vector_returns_nothing(tmp_path, conn):
    write(tmp_path / "a.md", "alpha topic")
    engine.update_index(conn, tmp_path, "toy", toy_embed, list(engine.iter_files(tmp_path)))
    assert engine.search(conn, tmp_path, "toy", [0.0] * DIM) == []


# ── .gitignore and filters ──────────────────────────────────────────────────


def test_iter_files_respects_gitignore_files_at_every_level(tmp_path):
    write(tmp_path / ".gitignore", "*.log.md\ngenerated/\n!important.log.md\n")
    keep = write(tmp_path / "notes.md", "keep")
    write(tmp_path / "debug.log.md", "ignored by pattern")
    important = write(tmp_path / "important.log.md", "re-included")
    write(tmp_path / "generated" / "api.md", "ignored folder")
    write(tmp_path / "sub" / ".gitignore", "draft.md\n")
    write(tmp_path / "sub" / "draft.md", "ignored below sub")
    sub_keep = write(tmp_path / "sub" / "final.md", "keep")
    other_draft = write(tmp_path / "other" / "draft.md", "not under sub")
    found = set(engine.iter_files(tmp_path))
    assert found == {keep, important, sub_keep, other_draft}


def test_iter_files_can_ignore_gitignore(tmp_path):
    write(tmp_path / ".gitignore", "*.md\n")
    note = write(tmp_path / "a.md", "text")
    assert list(engine.iter_files(tmp_path)) == []
    assert list(engine.iter_files(tmp_path, respect_gitignore=False)) == [note]


def test_search_path_filter_limits_results(tmp_path, conn):
    files = [
        write(tmp_path / "docs" / "retries.md", "retries back off after a rate limit"),
        write(tmp_path / "src" / "retries.py", "retries back off after a rate limit"),
    ]
    engine.update_index(conn, tmp_path, "toy", toy_embed, files)
    query = toy_embed(["rate limit retries"])[0]
    assert len(engine.search(conn, tmp_path, "toy", query)) == 2
    only_docs = engine.search(conn, tmp_path, "toy", query, path_filter=engine.patterns.PathFilter("docs/"))
    assert [r["path"] for r in only_docs] == ["docs/retries.md"]


# ── hybrid search and find similar ──────────────────────────────────────────


def _rule_embed(texts):
    """Meaning that ignores identifiers: anything about backoff (and the bare identifier query) points
    one way, everything else mostly another."""
    return [[1.0, 0.0] if ("backoff" in t or t == "ERR_4291") else [0.6, 0.8] for t in texts]


@pytest.fixture
def mixed(tmp_path, conn):
    files = [
        write(tmp_path / "backoff.md", "The client uses exponential backoff between retries."),
        write(tmp_path / "errors.md", "The server raises ERR_4291 when the quota is exhausted."),
        write(tmp_path / "pasta.md", "Boil pasta in salted water."),
    ]
    engine.update_index(conn, tmp_path, "rule", _rule_embed, files)
    return tmp_path


def test_hybrid_puts_an_exact_identifier_match_first(mixed, conn):
    vec = _rule_embed(["ERR_4291"])[0]
    semantic = engine.search(conn, mixed, "rule", vec, 3, query="ERR_4291", ranking="semantic")
    assert semantic[0]["path"] == "backoff.md"
    hybrid = engine.search(conn, mixed, "rule", vec, 3, query="ERR_4291")
    assert hybrid[0]["path"] == "errors.md"
    assert hybrid[0]["score"] is not None  # the score stays the cosine similarity


def test_keyword_mode_needs_no_query_vector_and_only_returns_matches(mixed, conn):
    results = engine.search(conn, mixed, "rule", None, 5, query="pasta water", ranking="keyword")
    assert [(r["path"], r["score"]) for r in results] == [("pasta.md", None)]
    assert engine.search(conn, mixed, "rule", None, 5, query="???", ranking="keyword") == []


def test_keyword_search_stems_words(mixed, conn):
    results = engine.search(conn, mixed, "rule", None, 5, query="retry", ranking="keyword")
    assert [r["path"] for r in results] == ["backoff.md"]


def test_hybrid_without_query_text_is_semantic(mixed, conn):
    vec = _rule_embed(["ERR_4291"])[0]
    assert engine.search(conn, mixed, "rule", vec, 1)[0]["path"] == "backoff.md"


def test_unknown_mode_is_rejected(mixed, conn):
    with pytest.raises(ValueError, match="ranking must be one of"):
        engine.search(conn, mixed, "rule", None, 1, query="x", ranking="fuzzy")


def test_keyword_query_quotes_every_word():
    assert engine.keyword_query('say "hi" OR NEAR x') == '"say" OR "hi" OR "near"'
    assert engine.keyword_query("a ! ?") == ""


def test_keyword_query_drops_function_words_unless_nothing_else_is_left():
    assert engine.keyword_query("how do we handle the rate limits") == '"handle" OR "rate" OR "limits"'
    assert engine.keyword_query("E4021") == '"e4021"'
    assert engine.keyword_query("what is this") == '"what" OR "is" OR "this"'


def test_keyword_index_follows_changes_and_deletions(mixed, conn):
    (mixed / "pasta.md").write_text("Toast bread instead.", encoding="utf-8")
    (mixed / "errors.md").unlink()
    engine.update_index(conn, mixed, "rule", _rule_embed, sorted(mixed.glob("*.md")))
    find = lambda q: [r["path"] for r in engine.search(conn, mixed, "rule", None, 5, query=q, ranking="keyword")]  # noqa: E731
    assert find("pasta") == [] and find("toast") == ["pasta.md"] and find("ERR_4291") == []
    chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0] == chunks


def test_an_index_from_before_keyword_search_gets_its_keyword_rows(tmp_path):
    old = sqlite3.connect(":memory:")
    old.executescript(engine._SCHEMA)  # the 0.2 schema: no keyword table
    files = [write(tmp_path / "a.md", "quarterly budget review")]
    engine.update_index(old, tmp_path, "toy", toy_embed, files)
    assert not engine.has_keyword_index(old)
    assert engine.search(old, tmp_path, "toy", None, 5, query="budget", ranking="keyword") == []
    engine.ensure_schema(old)
    results = engine.search(old, tmp_path, "toy", None, 5, query="budget", ranking="keyword")
    assert [r["path"] for r in results] == ["a.md"]
    old.close()


def test_mismatched_keyword_rows_are_rebuilt(mixed, conn):
    conn.execute("DELETE FROM chunks_fts")
    engine.ensure_schema(conn)
    assert [r["path"] for r in engine.search(conn, mixed, "rule", None, 5, query="pasta", ranking="keyword")] == [
        "pasta.md"
    ]


def test_similar_returns_other_files_once_each(tmp_path, conn):
    files = [
        write(tmp_path / "rates.md", "rate limit retries\n\n" + "rate limit retry backoff\n" * 40),
        write(tmp_path / "client.md", "the client retries after a rate limit"),
        write(tmp_path / "limits.md", "rate limit notes\n" + "rate limit window\n" * 80),
        write(tmp_path / "pasta.md", "boil pasta in salted water"),
    ]
    engine.update_index(conn, tmp_path, "toy", toy_embed, files, max_chars=200)
    vec = engine.file_vector(conn, tmp_path, "toy", "rates.md")
    results = engine.similar(conn, tmp_path, "toy", vec, 5, exclude_path="rates.md")
    paths = [r["path"] for r in results]
    assert "rates.md" not in paths and len(paths) == len(set(paths)) == 3
    assert paths[-1] == "pasta.md"
    assert engine.similar(conn, tmp_path, "toy", vec, 0) == []


def test_file_vector_respects_line_ranges_and_missing_files(tmp_path, conn):
    files = [write(tmp_path / "a.md", "\n".join(f"line {i}" for i in range(200)))]
    engine.update_index(conn, tmp_path, "toy", toy_embed, files, max_chars=100)
    assert engine.file_vector(conn, tmp_path, "toy", "a.md", (1, 5)) is not None
    assert engine.file_vector(conn, tmp_path, "toy", "a.md", (5000, 6000)) is None
    assert engine.file_vector(conn, tmp_path, "toy", "missing.md") is None


# ── ranking: RRF, fallbacks and upgrades ────────────────────────────────────


def test_bm25_finds_an_exact_identifier_the_vector_search_misses(mixed, conn):
    vec = _rule_embed(["ERR_4291"])[0]
    [top_meaning] = engine.search(conn, mixed, "rule", vec, 1, query="ERR_4291", ranking="semantic")
    [top_words] = engine.search(conn, mixed, "rule", None, 1, query="ERR_4291", ranking="keyword")
    assert top_meaning["path"] != "errors.md" and top_words["path"] == "errors.md"


def test_rrf_merge_orders_by_summed_reciprocal_ranks():
    # a: 1/61 (first in meaning only); b: 1/62 + 1/62; c: 1/63 + 1/61, so c > b > a.
    assert engine.rrf_merge([[1, 2, 3], [3, 2]]) == [3, 2, 1]
    # appearing in both lists beats topping only one: 2 scores 1/3 + 1/3 against 1/2 for 1 and 3
    assert engine.rrf_merge([[1, 2], [3, 2]], k=1) == [2, 1, 3]
    # equal scores keep the order in which ids were first seen
    assert engine.rrf_merge([[1, 2], [2, 1]]) == [1, 2]
    assert engine.rrf_merge([]) == [] and engine.rrf_merge([[5]]) == [5]


class _NoFTS5(sqlite3.Connection):
    """A connection whose SQLite build lacks FTS5, like some minimal Python builds."""

    def execute(self, sql, *args):
        if "fts5" in sql.lower():
            raise sqlite3.OperationalError("no such module: fts5")
        return super().execute(sql, *args)


def test_without_fts5_every_ranking_falls_back_to_meaning_with_a_note(tmp_path):
    conn = sqlite3.connect(":memory:", factory=_NoFTS5)
    engine.ensure_schema(conn)  # must not raise
    assert not engine.has_keyword_index(conn)
    files = [write(tmp_path / "a.md", "budget review"), write(tmp_path / "b.md", "pasta water")]
    engine.update_index(conn, tmp_path, "toy", toy_embed, files)
    for ranking in ("hybrid", "keyword"):
        assert engine.effective_ranking(conn, ranking) == ("semantic", engine.NO_KEYWORD_NOTE)
    assert engine.effective_ranking(conn, "semantic") == ("semantic", None)
    results = engine.search(conn, tmp_path, "toy", toy_embed(["budget"])[0], 1, query="budget")
    assert results[0]["path"] == "a.md"
    with pytest.raises(ValueError, match="ranking must be one of"):
        engine.effective_ranking(conn, "fuzzy")
    conn.close()


def test_an_old_index_upgrades_without_re_embedding(tmp_path):
    old = sqlite3.connect(":memory:")
    old.executescript(engine._SCHEMA)  # the 0.2 schema: vectors only
    files = [write(tmp_path / "a.md", "quarterly budget review"), write(tmp_path / "b.md", "pasta water")]
    engine.update_index(old, tmp_path, "toy", toy_embed, files)

    def must_not_embed(texts):
        raise AssertionError(f"re-embedded {texts!r}")

    engine.ensure_schema(old)
    stats = engine.update_index(old, tmp_path, "toy", must_not_embed, files)
    assert stats["indexed_files"] == 0 and stats["reused_files"] == 2
    results = engine.search(old, tmp_path, "toy", None, 5, query="budget", ranking="keyword")
    assert [r["path"] for r in results] == ["a.md"]
    old.close()


def test_index_overview_and_clear(tmp_path):
    conn = sqlite3.connect(":memory:")
    engine.ensure_schema(conn)
    roots = []
    for name in ("one", "two"):
        root = tmp_path / name
        root.mkdir()
        (root / "a.md").write_text("alpha beta", encoding="utf-8")
        (root / "b.md").write_text("gamma delta", encoding="utf-8")
        engine.update_index(conn, root, "m", toy_embed, sorted(root.iterdir()))
        roots.append(root)
    overview = engine.index_overview(conn)
    assert sorted(f["root"] for f in overview) == sorted(str(r) for r in roots)
    assert all(f["files"] == 2 and f["chunks"] == 2 for f in overview)

    assert engine.clear_index(conn, roots[0]) == 2
    assert [f["root"] for f in engine.index_overview(conn)] == [str(roots[1])]
    vector = toy_embed(["gamma"])[0]
    hits = engine.search(conn, roots[1], "m", vector, 5, query="gamma", ranking="hybrid")
    assert hits[0]["path"] == "b.md"  # the keyword index still lines up after the clear

    assert engine.clear_index(conn) == 2
    assert engine.index_overview(conn) == []
    conn.close()


def test_rrf_merge_weights_each_ranking():
    assert engine.rrf_merge([[1, 2, 3], [3]]) == [3, 1, 2]
    assert engine.rrf_merge([[1, 2, 3], [3]], weights=[1.0, 0.01]) == [1, 2, 3]
    with pytest.raises(ValueError, match="one weight per ranking"):
        engine.rrf_merge([[1], [2]], weights=[1.0])
