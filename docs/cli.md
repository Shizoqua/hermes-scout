# Command line

The `hermes-scout` command runs the same search engine without Hermes.

```bash
pipx install hermes-scout
```

## Search

```bash
hermes-scout search "where do we handle rate limits" ~/project
```

```text
0.82  src/client/backoff.py:40-71
      def backoff(attempt):
0.64  docs/api-errors.md:5-19
      ## 429 Too Many Requests
```

Add `--json` for machine-readable output, or `-k 10` for more results.

Limit a search to some files with `-g` (repeatable):

```bash
hermes-scout search "retry policy" ~/project -g "*.md" -g "src/**/*.py"
```

By default a search ranks by meaning and by exact words together (`--mode hybrid`). Use
`--mode semantic` for meaning only, or `--mode keyword` for exact words only, which needs no
embeddings server for the query.

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
| `-g`, `--glob` | (none) | every indexed file |
| `--mode` (search) | (none) | `hybrid` |

Exit codes: `0` success, `1` the embeddings server failed, `2` the folder does not exist.
