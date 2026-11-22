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

Exit codes: `0` success, `1` the embeddings server failed, `2` the folder does not exist.
