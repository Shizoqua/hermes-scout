"""Chunking, file selection, incremental indexing and ranking, with a deterministic toy embedder."""

import hashlib
import os
import re
import sqlite3

import pytest

import engine

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
    for (_, prev_end, _), (next_start, _, _) in zip(chunks, chunks[1:]):
        assert next_start == prev_end - 1  # two shared lines


def test_an_overlong_line_is_truncated_not_dropped():
    [(start, end, body)] = engine.chunk_text("x" * 5000, max_chars=100)
    assert (start, end, len(body)) == (1, 1, 100)


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

    found = list(engine.iter_files(tmp_path, max_file_bytes=2000,
                                   is_blocked=lambda p: "blocked" if p.parent.name == "private" else None))
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
