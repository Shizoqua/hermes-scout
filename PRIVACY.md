# Privacy

hermes-scout searches files on your own machine. This page says exactly what it reads, what it
stores, and what, if anything, leaves your machine.

## What it reads

- Text files, PDFs and Word (`.docx`) files under the folder you ask it to search.
- It skips hidden files and folders, dependency and build folders, anything a `.gitignore` ignores,
  binary files, files over the size limits and, inside Hermes, every path Hermes's own file tools
  refuse to read (such as `.env` files and credential stores).
- It never writes to, moves or deletes your files.

## What it stores

- One index database: in Hermes, under the plugin's own data folder
  (`<hermes home>/plugin-data/hermes-scout/index.db`); on the command line, in your user cache
  folder (`~/.cache/hermes-scout/index.db` on Linux).
- The index holds text chunks of the files it read and their embedding vectors. Delete it any time
  with `/scout clear all`, `hermes-scout clear --all`, or by deleting the file.

## What leaves your machine

- Text chunks and your search queries go to the embeddings server you configure, and nowhere else.
- The default server is Ollama on `localhost`, so by default **nothing leaves your machine**.
- If you point `base_url` at a hosted service, that service receives the text of the files you
  search. Check its privacy terms first.
- `/scout doctor` and `hermes-scout doctor` send one fixed test sentence to that same server.

## What it never does

- No telemetry, analytics or usage reporting.
- No background processes, shell commands or self-updating.
- No accounts. The optional API key, for hosted servers only, is read through Hermes's secret store
  (or `SCOUT_API_KEY` on the command line) and sent only to the configured server. It is dropped if
  that server redirects to another origin.

## Questions

Open an [issue](https://github.com/Shizoqua/hermes-scout/issues/new/choose). Report security problems
privately as described in [SECURITY.md](SECURITY.md).
