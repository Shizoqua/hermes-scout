# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-11-23

### Added

- Hybrid search: results are ranked by meaning and by exact words together (SQLite full-text
  search with BM25, merged by reciprocal rank fusion with k=60), so names, error codes and
  identifiers are found as well as paraphrases. A new `ranking` setting, the tool's `ranking`
  argument and the command line's `--ranking` choose `hybrid` (default), `semantic` or `keyword`.
  Existing indexes gain their keyword index on first use, without re-embedding anything. Without
  FTS5 in Python's SQLite, search falls back to meaning only and adds a one-line note.
- `scout_similar` tool and `hermes-scout similar` command: the files most related to a file, part of
  a file (`lines`) or a passage (`text`), one result per file.
- A logo, also used as the docs site's favicon.
- Strict type checking with mypy in CI.
- An OpenSSF Scorecard workflow and badge.

## [0.2.0] - 2026-11-22

### Added

- Files and folders that `.gitignore` files ignore are left out of the index, the way git does it:
  nested `.gitignore` files, anchored and folder-only patterns, `**` and `!` re-includes. Turn it
  off with the new `respect_gitignore` setting or `--no-gitignore`.
- Search filters: the tool's `glob` argument and the command line's `-g`/`--glob` limit a search to
  files such as `*.md`, `docs/` or `src/**/*.py`, without re-indexing.
- Tests run on macOS and Windows as well as Linux (77 tests).

## [0.1.1] - 2026-11-22

### Changed

- The Hermes tool is now called `scout_search` (toolset `hermes_scout`), so it no longer clashes
  with another plugin's `semantic_search` tool.

### Fixed

- Lines longer than the chunk size are split into pieces instead of cut off, so the rest of a long
  line (a one-line paragraph, minified JSON) is searchable too.
- Chunks overlap less when lines are long, so text is no longer embedded twice.

### Added

- A README inside the plugin folder, shown on the plugin's Hermes Marketplace page.

## [0.1.0] - 2026-11-22

### Added

- `semantic_search` tool: search a folder of local text files by meaning.
- Line-aligned, overlapping chunking with a configurable chunk size.
- Embeddings from any OpenAI-compatible `/embeddings` endpoint, local Ollama by default.
- Incremental SQLite index in the plugin's data folder, keyed by folder and embedding model.
- Cosine-similarity ranking with file path, line range and score in every result.
- Settings form (`base_url`, `embedding_model`, `api_key`, `top_k`, `chunk_chars`, `max_files`,
  `max_file_kb`).
- Skips hidden, dependency, binary and oversized files and every path Hermes's file tools refuse.
- `hermes-scout` command line tool (`search` and `index`), installable from PyPI.
- Documentation site built with MkDocs Material.
- Tests for the engine, the HTTP client, the command line and the Hermes wiring (34 tests, over 90%
  coverage), run in CI on Python 3.11 to 3.14 with ruff lint and CodeQL analysis.

[Unreleased]: https://github.com/Shizoqua/hermes-scout/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Shizoqua/hermes-scout/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Shizoqua/hermes-scout/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/Shizoqua/hermes-scout/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Shizoqua/hermes-scout/releases/tag/v0.1.0
