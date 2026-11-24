# Troubleshooting

| Message | Fix |
|---|---|
| Not sure what is wrong | Run `/scout doctor` in Hermes or `hermes-scout doctor` in a terminal. It checks everything and names the fix. |
| `cannot reach the embeddings server at http://localhost:11434/v1` | Start Ollama (`ollama serve`) or point `base_url` at your server. |
| `answered HTTP 404 ... model not found` | Pull the model (`ollama pull nomic-embed-text`) or set the model to one the server has. |
| `answered HTTP 401` | A hosted endpoint needs an API key (`SCOUT_API_KEY`). |
| No results for files you expected | Check the file's extension and size (`max_file_kb`), that it is not hidden or in a skipped folder, and that no `.gitignore` ignores it. |
| A document never shows up in results | A scanned PDF (pictures of pages) or an encrypted file has no text to read, older `.doc`, `.xls` and `.ppt` files are not read, and anything over 20 MB is skipped. Check that `read_documents` is on. |
| Fewer files than expected | A folder with more than `max_files` (2,000 by default) is cut off there; narrow the folder or raise the limit. |
| The first search is slow | Expected for a large folder: every file is embedded once. Later searches only embed changes. |

Still stuck? [Open an issue](https://github.com/Shizoqua/hermes-scout/issues/new/choose).
