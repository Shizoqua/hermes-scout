# semantic-search for Hermes Agent

Find passages in your local files by meaning, not just exact words. Ask "where do we handle
rate limits?" and get back the relevant paragraphs from your notes, docs or code, with file
paths, line numbers and a similarity score.

The plugin adds one tool, `semantic_search`, to [Hermes Agent](https://github.com/NousResearch/hermes-agent).
Embeddings come from any OpenAI-compatible `/embeddings` endpoint. By default that is a local
[Ollama](https://ollama.com) server, so nothing leaves your machine and nothing costs money.

## Install

```bash
hermes plugins install semantic-search
hermes plugins enable semantic-search
```

Then start an embeddings server. With Ollama:

```bash
ollama pull nomic-embed-text
ollama serve            # if it is not already running
```

Ask Hermes something like *"Search my notes in ~/notes for how I set up backups"*.

## How it works

1. **Chunking.** Text files under the folder are split into chunks of whole lines (1,200 characters
   by default). Neighbouring chunks share two lines, so a passage that straddles a boundary is still
   found whole.
2. **Embedding.** Each chunk is sent to the embeddings endpoint in batches of 32 and stored as a
   float32 vector with its precomputed norm.
3. **Incremental index.** The index lives in SQLite in the plugin's own data folder
   (`<hermes home>/plugin-data/semantic-search/index.db`), keyed by folder and embedding model. On
   each search only new or changed files (by modification time and size) are re-embedded, and deleted
   files are dropped.
4. **Ranking.** The query is embedded the same way and chunks are ranked by cosine similarity.

Indexes for different embedding models are kept apart, so switching models never mixes vectors.

### What gets indexed

Common text, documentation, code and config extensions (`.md`, `.txt`, `.py`, `.ts`, `.json`, `.yaml`,
...). Skipped: hidden files and folders (names starting with `.`), dependency and build folders
(`node_modules`, `venv`, `dist`, `build`, ...), symlinks, binary files, files over the size limit,
and every path Hermes's own file tools refuse to read (credential stores, `.env` files and similar).

## Settings

Edit them in the Desktop app (Settings → Plugins → semantic-search) or with
`hermes plugins config semantic-search`.

| Setting | Default | Meaning |
|---|---|---|
| `base_url` | `http://localhost:11434/v1` | OpenAI-compatible base URL; the plugin calls `<base_url>/embeddings` |
| `embedding_model` | `nomic-embed-text` | Model name the endpoint serves |
| `api_key` | not set | Only for hosted endpoints; stored by Hermes as `SEMANTIC_SEARCH_API_KEY` |
| `top_k` | 5 | Passages returned per search (the model may ask for 1 to 20) |
| `chunk_chars` | 1200 | Chunk size in characters; applies to files indexed afterwards |
| `max_files` | 2000 | Files indexed per folder |
| `max_file_kb` | 1000 | Larger files are skipped |

Works with Ollama (`http://localhost:11434/v1`), LM Studio (`http://localhost:1234/v1`), llama.cpp's
server, vLLM, and hosted OpenAI-compatible APIs.

## Disclosure

- **Network:** file contents (chunks) and search queries are sent to the embeddings endpoint you
  configure. The default is a server on your own machine. If you point `base_url` at a hosted API,
  that service receives the text of the files you search.
- **Files read:** text files under the folder the model asks to search, minus the skipped paths
  listed above. The plugin never writes to that folder.
- **Files written:** the index database in the plugin's own data folder only.
- **Credentials:** the optional API key is read through Hermes's secret store and sent only to the
  configured endpoint. It is dropped if the endpoint redirects to another origin.
- No telemetry, no background processes, no shell commands, no self-updating.

## Development

The search engine (`engine.py`) and the HTTP client (`embeddings.py`) use only the Python standard
library and do not import Hermes, so the tests run without a Hermes install or network access:

```bash
python -m pytest tests
```

`__init__.py` holds the Hermes wiring (tool registration, settings, file-safety checks, storage).
Before a release, check the plugin the way the catalog does:

```bash
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
```

## License

MIT, see [LICENSE](LICENSE).
