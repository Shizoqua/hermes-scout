---
name: scout
description: "When to search local files with scout_search and scout_similar instead of grep or reading files one by one."
version: 1.0.0
tags: [search, files, notes, code, retrieval]
---

# Searching local files (hermes-scout)

`scout_search` finds passages in a folder of notes, docs or code by meaning and exact words together.
`scout_similar` finds the files most related to a file or a passage.

## When to use

- The user asks **where** something is discussed, decided or implemented, and the exact wording is
  unknown ("where do we handle rate limits?", "which note covers the backup plan?").
- A plain text search would need many guesses at synonyms (throttling, back off, 429, retry).
- The user wants **related** material: "what else is like this", overlapping docs, similar code,
  notes on the same topic. Use `scout_similar`.

## When not to use

- The exact string is known and short (a function name, an error code) and the folder is small:
  `scout_search` with `ranking: keyword`, or a plain text search, is enough.
- The user named one specific file: read it directly.
- The files are images or other binaries: they are not indexed. Documents are: PDF, Word (.docx),
  Excel (.xlsx), PowerPoint (.pptx) and OpenDocument (.odt, .ods, .odp). A result from one starts
  with a `[page N]`, `[slide N]` or `[sheet Name]` line that says where to cite.

## How to use it well

1. Pass the folder as `path` when it is not the working directory.
2. Write the query as a plain question or description, not a keyword list.
3. Narrow with `glob` when the user names a kind of file: `*.md`, `docs/`, `src/**/*.py`.
4. Read the returned passages, then open the best file at the given line range before answering.
   Cite the file path and lines in the answer. For documents, the lines count lines of the
   extracted text, so cite the page, slide or sheet from the result's first line instead.
5. If a result looks off, try `ranking: keyword` for names and codes, or `ranking: semantic` for
   loosely worded ideas.

## If it fails

The error message names the fix. The most common ones:

- "cannot reach the embeddings server": the local server is not running (`ollama serve`).
- "HTTP 404 ... model": the model is not pulled (`ollama pull nomic-embed-text`).
- The user can run `/scout doctor` to check everything at once.

The first search of a large folder builds its index and can take a while; say so instead of
retrying.
