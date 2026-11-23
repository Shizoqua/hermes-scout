# hermes-scout

**Search your local files by meaning, not just keywords.**

hermes-scout adds two tools to Hermes Agent:

- **`scout_search`**: ask *"where do we handle rate limits?"* and Hermes gets back the most relevant
  passages from your notes, docs or code, with the file path, line range and a similarity score,
  even when the files never use the words "rate limit". It ranks by meaning and by exact words
  together, so names and error codes are found too.
- **`scout_similar`**: point at a file (or part of one) or a passage, and get the most related
  files: related notes, overlapping docs, code that does something similar.

Embeddings come from any OpenAI-compatible `/embeddings` endpoint. By default that is a local
[Ollama](https://ollama.com) server, so your files never leave your machine.

## Quick start

1. Start a local embeddings server:

   ```bash
   ollama pull nomic-embed-text
   ollama serve
   ```

2. Install and enable the plugin:

   ```bash
   hermes plugins install hermes-scout
   hermes plugins enable hermes-scout
   ```

3. Ask Hermes: *Search my notes in ~/notes for how I set up backups.*

The first search of a folder builds an index. Later searches only re-embed files that changed.

## How it works

- Text files are split into overlapping chunks of whole lines (1,200 characters by default).
- Chunks are embedded in batches and stored in a SQLite index in the plugin's data folder, keyed
  by folder and embedding model. Only new or changed files are embedded again.
- Your question is embedded the same way and ranked by cosine similarity, and its words are looked
  up in a keyword index (SQLite full-text search, BM25). The two rankings are merged, so passages
  that match in meaning and in exact words come first.
- Files that `.gitignore` files ignore are skipped, and a search can be narrowed with a filter such
  as `*.md` or `docs/`.
- Python standard library only: no dependencies to install.

## Settings

Edit them in the Desktop app (**Settings, Plugins, hermes-scout**) or with
`hermes plugins config hermes-scout`.

| Setting | Default | Meaning |
|---|---|---|
| `base_url` | `http://localhost:11434/v1` | OpenAI-compatible base URL; the plugin calls `<base_url>/embeddings` |
| `embedding_model` | `nomic-embed-text` | Model name the endpoint serves |
| `api_key` | not set | Only for hosted endpoints; stored by Hermes as `SCOUT_API_KEY` |
| `top_k` | `5` | Passages returned per search (1 to 20) |
| `chunk_chars` | `1200` | Chunk size in characters |
| `max_files` | `2000` | Files indexed per folder |
| `max_file_kb` | `1000` | Larger files are skipped |
| `respect_gitignore` | `true` | Skip files and folders that `.gitignore` files in the searched folder ignore |
| `ranking` | `hybrid` | `hybrid`: meaning and exact words together; `semantic`: meaning only; `keyword`: exact words only |

Works with Ollama, LM Studio, llama.cpp's server, vLLM and hosted OpenAI-compatible APIs.

## Commands

- `/scout doctor`: check the embeddings server, the model and keyword search, with fixes.
- `/scout status`: list the indexed folders.
- `/scout index [folder]`: build or refresh a folder's index now.
- `/scout clear <folder|all>`: forget a folder's index, or every index.

A bundled `scout` skill tells the agent when to search by meaning and how to cite results.

## Disclosure

- **Network:** file chunks and search queries are sent to the embeddings endpoint you configure.
  The default is a server on your own machine. A hosted endpoint receives the text of the files
  you search.
- **Files read:** text files under the folder Hermes asks to search. Hidden files, dependency and
  build folders, anything a `.gitignore` ignores, binaries, oversized files and every path Hermes's
  file tools refuse (such as `.env` files) are skipped. The plugin never writes to that folder.
- **Files written:** the index database in the plugin's own data folder only. `/scout clear`
  deletes rows from it; nothing else is ever deleted.
- **Health check:** `/scout doctor` sends one fixed test sentence to the embeddings endpoint.
- **Credentials:** the optional `SCOUT_API_KEY` is read through Hermes's secret store and sent only
  to the configured endpoint. It is dropped if the endpoint redirects to another origin.
- No telemetry, no background processes, no shell commands.

## More

- Documentation: https://shizoqua.github.io/hermes-scout/
- Source, issues and the standalone `hermes-scout` command line tool:
  https://github.com/Shizoqua/hermes-scout
- License: MIT
