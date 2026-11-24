# Command line

The `hermes-scout` command runs the same search engine without Hermes.

```bash
pipx install hermes-scout
```

## Search

```bash
hermes-scout search "how do we keep a copy of the database in case it gets lost" benchmarks/corpus -k 3
```

```text
0.63  docs/backups.md:1-15
      # Backups and restores
0.57  src/storage/cache.py:1-19
      """Read-through cache in front of the primary store."""
0.54  notes/meeting-2026-05-12.md:1-15
      # Platform meeting, 12 May
```

Real output with `nomic-embed-text` on Ollama, on the benchmark project in the repository.

Add `--json` for machine-readable output, or `-k 10` for more results.

Limit a search to some files with `-g` (repeatable):

```bash
hermes-scout search "retry policy" ~/project -g "*.md" -g "src/**/*.py"
```

By default (`--ranking hybrid`) a question is ranked by meaning, and a query made only of code-like
names such as `ERR_4291` puts exact matches first. Use `--ranking semantic` for meaning only, or
`--ranking keyword` for exact words only, which needs no embeddings server for the query (only for
files not indexed yet). If Python's SQLite lacks full-text search (FTS5), the search falls
back to meaning only and prints a one-line note.

## Find similar files

```bash
hermes-scout similar notes/backups.md --in ~/notes
hermes-scout similar src/client.py --lines 40-71 --in ~/project
hermes-scout similar --text "salted pasta water" --in ~/recipes
```

Each related file appears once, with its best-matching passage; the source file is left out.
`FILE` can be relative to the current folder or to `--in`.

## Index ahead of time

```bash
hermes-scout index ~/project
```

## Check your setup

```bash
hermes-scout doctor
```

Checks the embeddings server, the model and keyword search, and prints the fix for anything that
fails. It exits with status 1 when a check fails, so scripts can use it.

## Manage the index

```bash
hermes-scout status            # indexed folders with file and chunk counts
hermes-scout clear ~/project   # forget one folder's index
hermes-scout clear --all       # forget every index
```

## Options

| Flag | Environment variable | Default |
|---|---|---|
| `--base-url` | `SCOUT_BASE_URL` | `http://localhost:11434/v1` |
| `--model` | `SCOUT_MODEL` | `nomic-embed-text` |
| (none) | `SCOUT_API_KEY` | not set |
| `--index` | (none) | `~/.cache/hermes-scout/index.db` (`%LOCALAPPDATA%` on Windows) |
| `--chunk-chars` | (none) | `1200` |
| `--max-files` | (none) | `2000` |
| `--max-file-kb` | (none) | `1000` |
| `--no-gitignore` | (none) | off: files `.gitignore` ignores are skipped |
| `--no-documents` | (none) | off: PDF, Word, Excel, PowerPoint and OpenDocument files are indexed |
| `-g`, `--glob` | (none) | every indexed file |
| `--ranking` (search) | (none) | `hybrid` |

Exit codes: `0` success, `1` the embeddings server failed (or, for `doctor`, a check failed), `2` a
usage problem, such as a folder or file that does not exist.
