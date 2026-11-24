# Use with Hermes

The plugin adds two tools:

- **`scout_search`** finds passages when you ask where something is discussed or implemented.
- **`scout_similar`** finds the files most related to a file, part of a file, or a passage.

## Install

```bash
hermes plugins install Shizoqua/hermes-scout/hermes_scout
hermes plugins enable hermes-scout
```

## What the agent receives

For the question *"how do we keep a copy of the database in case it gets lost"* on the benchmark
project (paths, lines and counts exact, scores as recorded to two decimals, passage cut short):

```json
{
  "query": "how do we keep a copy of the database in case it gets lost",
  "ranking": "hybrid",
  "root": "/home/me/hermes-scout/benchmarks/corpus",
  "model": "nomic-embed-text",
  "results": [
    {"path": "docs/backups.md", "lines": "1-15", "score": 0.63,
     "text": "# Backups and restores\n\n## Nightly dumps\n\nA scheduled job runs `pg_dump` at 02:00 UTC ..."}
  ],
  "index": {"indexed_files": 0, "reused_files": 23, "removed_files": 0, "chunks": 23}
}
```

A passage from a document starts with its `[page N]`, `[slide N]` or `[sheet Name]` line. For
documents, `lines` counts lines of the extracted text, so cite the page, slide or sheet instead.

| Argument | Meaning |
|---|---|
| `query` | What to look for, in natural language. Required. |
| `path` | Folder to search; relative paths resolve against the agent's working directory. |
| `top_k` | Passages to return, 1 to 20. |
| `glob` | Only search matching files, such as `*.md`, `docs/` or `src/**/*.py`; separate several with commas. |
| `ranking` | `hybrid`: meaning for questions, exact words first for code names like `ERR_4291`; `semantic`: meaning only; `keyword`: exact words only. Defaults to the `ranking` setting. |

## Find related files

```json
{"file": "notes/backups.md", "path": "~/notes", "top_k": 5}
```

| Argument | Meaning |
|---|---|
| `file` | A file in the folder to find related files for. Give this or `text`. |
| `lines` | Only use part of the file, e.g. `10-40`. |
| `text` | A passage to find related files for, instead of a file. |
| `path`, `glob`, `top_k` | As for `scout_search`. |

Each related file appears once, with its best-matching passage; the source file is never returned.

## The `/scout` command

| Command | What it does |
|---|---|
| `/scout doctor` | Checks the embeddings server, the model and keyword search, with the fix for anything that fails |
| `/scout status` | Lists the indexed folders with file and chunk counts |
| `/scout index [folder]` | Builds or refreshes a folder's index now (default: the working directory) |
| `/scout clear <folder>`, `/scout clear all` | Forgets a folder's index, or every index |

These run directly, without asking the model.

## The `scout` skill

The plugin ships a skill, `hermes-scout:scout`, that tells the agent when searching by meaning beats
a plain text search, how to narrow a search with `glob`, and to open and cite the best file before
answering.

## Settings

Change them in the Desktop app (**Settings → Plugins → hermes-scout**) or with
`hermes plugins config hermes-scout`. See [Configuration](configuration.md).

## Safety

Inside Hermes, every file is checked against Hermes's own file-safety rules, so paths Hermes's file
tools refuse to read (credential stores, `.env` files and similar) are never indexed. An optional API
key is read through Hermes's secret store as `SCOUT_API_KEY`.

The passages a search returns become part of the conversation, so the model Hermes uses reads them,
as it would any file Hermes opens. With a hosted model, that provider sees them.
