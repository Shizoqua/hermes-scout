# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Documentation

- A real demo recorded with `nomic-embed-text` by a new `demo` workflow (raw recording in
  `docs/demo.cast`), replacing the illustration; problem and solution cards and an architecture
  picture from real output; and a landing page for the docs site.
- One look for every picture in the README: black background, grey rounded panels and gradient
  icon tiles. The architecture picture shows how your folder becomes a searchable index.
  Screenshots have bigger text and tighter framing.
- A new docs home page that does not repeat the README: a one-line hero with tabbed install
  commands, a "Try it" playground that plays back real results (with a switch to compare keyword
  search), three steps to a first search, examples for Hermes and the terminal, animated benchmark
  bars and an honest "Good for, and not for".
- A "What's inside" table and a "Repository layout" section in the README; the architecture picture
  is near the top.

### Security

- CI installs its tools (ruff, mypy, pytest, MkDocs, build) from hash-locked requirement files, and
  Dependabot keeps them current.
- The PDF and Word readers are fuzzed with Atheris every week and on every change to them.

### Fixed

- The hash-locked CI files carry the command that rebuilds them, so Dependabot keeps each tool
  within its range (pytest 8) and keeps the Windows-only packages the tests need.
- The line-range parser for `scout_similar` no longer assigns a value it never reads.

## [0.4.0] - 2026-11-23

### Added

- PDF and Word (`.docx`) files are indexed by their text, extracted locally with the standard
  library, with a `[page N]` line before each PDF page. Files up to 20 MB; scanned or encrypted
  PDFs are skipped. A `read_documents` setting and a `--no-documents` flag turn it off.
- `/scout` command in Hermes: `doctor` checks the embeddings server, the model and keyword search
  and names the fix for anything that fails; `status` lists indexed folders; `index [folder]` builds
  an index ahead of time; `clear <folder|all>` forgets an index.
- `hermes-scout doctor`, `status` and `clear` on the command line, with the same checks.
- A bundled `scout` skill that tells the agent when to search by meaning and how to cite results.
- A retrieval benchmark: a synthetic project, 30 questions with known answers and
  `scripts/benchmark.py`, which reports hit@1, hit@5 and MRR for each ranking mode. A `benchmark`
  workflow runs it against a real model in a pinned Ollama container.

### Changed

- Hybrid ranking ignores filler words such as "how" and "the" in the keyword half.
- Hybrid ranking picks by query: questions in words are ranked by meaning, which the new benchmark
  measured as the most accurate for them; queries made only of code-like names such as `ERR_4291`
  merge both rankings by score (relative score fusion) with keywords at 75%, so exact names still
  come first when the embedding model blurs them.

### Fixed

- The command line no longer sends `SCOUT_API_KEY` to another site when a hosted embeddings server
  redirects there; the key now follows redirects only within the same origin, as it already did
  inside Hermes.
- The "cannot reach the embeddings server" hint names `--base-url` for command line users.

### Documentation

- README: what's new, example questions, what hermes-scout is and is not, screenshots of real
  output, and a PRIVACY.md that answers what is read, stored and sent.
- Added a README guide to choosing hybrid, semantic or keyword ranking, with CLI examples.
- Improved issue forms to distinguish Hermes plugin from standalone CLI reports and request clearer examples.
- Expanded README troubleshooting tips for missing results, indexing limits and Ollama model checks.
- Clarified first-run setup checks for both Hermes and CLI users, with example filtered and keyword searches in the README.

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

[Unreleased]: https://github.com/Shizoqua/hermes-scout/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Shizoqua/hermes-scout/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Shizoqua/hermes-scout/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Shizoqua/hermes-scout/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/Shizoqua/hermes-scout/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Shizoqua/hermes-scout/releases/tag/v0.1.0
