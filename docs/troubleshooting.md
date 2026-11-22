# Troubleshooting

| Message | Fix |
|---|---|
| `cannot reach the embeddings server at http://localhost:11434/v1` | Start Ollama (`ollama serve`) or point `base_url` at your server. |
| `answered HTTP 404 ... model not found` | Pull the model (`ollama pull nomic-embed-text`) or set the model to one the server has. |
| `answered HTTP 401` | A hosted endpoint needs an API key (`SCOUT_API_KEY`). |
| No results for files you expected | Check the file's extension and size, and that it is not hidden or in a skipped folder. |
| The first search is slow | Expected for a large folder: every file is embedded once. Later searches only embed changes. |

Still stuck? [Open an issue](https://github.com/Shizoqua/hermes-scout/issues/new/choose).
