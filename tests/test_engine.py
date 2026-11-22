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
