# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
