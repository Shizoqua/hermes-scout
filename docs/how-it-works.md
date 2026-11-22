# How it works

```mermaid
flowchart LR
    A[Folder of text files] --> B[Split into overlapping<br/>line-aligned chunks]
    B --> C{New or changed<br/>since last search?}
    C -- yes --> D[Embed via<br/>/embeddings endpoint]
    C -- no --> E[(SQLite index)]
    D --> E
    Q[Your question] --> F[Embed the question]
    E --> G[Rank chunks by<br/>cosine similarity]
    F --> G
    G --> R[Top passages with<br/>path, lines, score]
```

1. **Chunking.** Text files are split into chunks of whole lines (1,200 characters by default).
   Neighbouring chunks share up to two lines, so a passage that straddles a boundary is still found
   whole. A line longer than the chunk size is split into pieces, so nothing is cut off.
2. **Embedding.** Chunks are sent in batches of 32 and stored as float32 vectors with precomputed norms.
3. **Incremental index.** The SQLite index is keyed by folder and embedding model. Only new or changed
   files (by modification time and size) are re-embedded, and deleted files are dropped.
4. **Ranking.** The question is embedded the same way and chunks are ranked by cosine similarity,
   `score = (q · c) / (‖q‖ ‖c‖)`.

Indexes for different embedding models are kept apart, so switching models never mixes vectors.

## What gets indexed

Common text, documentation, code and config extensions (`.md`, `.txt`, `.py`, `.ts`, `.go`, `.rs`,
`.json`, `.yaml`, ...). Skipped: hidden files and folders, dependency and build folders
(`node_modules`, `venv`, `dist`, `build`, ...), symlinks, binary files and files over the size limit.
Inside Hermes, paths Hermes's file tools refuse to read are skipped as well.
