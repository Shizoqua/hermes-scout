# Use with Hermes

The plugin adds one tool, `semantic_search`, that the agent calls when you ask where something is
discussed or implemented.

## Install

```bash
hermes plugins install hermes-scout
hermes plugins enable hermes-scout
```

## What the agent receives

```json
{
  "query": "how does the client handle rate limiting and retries",
  "root": "/home/me/project",
  "model": "nomic-embed-text",
  "results": [
    {"path": "notes/retries.md", "lines": "1-3", "score": 0.5948,
     "text": "Retry policy\n\nWhen the API answers 429 the client waits with exponential backoff..."}
  ],
  "index": {"indexed_files": 0, "reused_files": 2, "removed_files": 0, "chunks": 2}
}
```

| Argument | Meaning |
|---|---|
| `query` | What to look for, in natural language. Required. |
| `path` | Folder to search; relative paths resolve against the agent's working directory. |
| `top_k` | Passages to return, 1 to 20. |

## Settings

Change them in the Desktop app (**Settings → Plugins → hermes-scout**) or with
`hermes plugins config hermes-scout`. See [Configuration](configuration.md).

## Safety

Inside Hermes, every file is checked against Hermes's own file-safety rules, so paths Hermes's file
tools refuse to read (credential stores, `.env` files and similar) are never indexed. An optional API
key is read through Hermes's secret store as `SCOUT_API_KEY`.
