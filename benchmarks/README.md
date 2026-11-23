# Retrieval benchmark

A small, fully synthetic benchmark that measures how often hermes-scout puts the right file first.

- `corpus/` is a made-up project ("Larkspur", a task-sync service): 23 docs, notes, config and source
  files, plus a few unrelated personal notes as distractors. No real data.
- `questions.json` holds 30 questions, each with the one file that answers it:
  - 18 **paraphrase** questions that avoid the answer's own wording ("how is a user's secret phrase
    stored safely" for the password hashing code),
  - 8 **exact** questions that name an identifier, error code or tool (`E4021`, `pg_dump`),
  - 4 **mixed** questions that do both.

`scripts/benchmark.py` indexes the corpus, asks every question under each ranking mode and reports:

| Metric | Meaning |
|---|---|
| hit@1 | The right file is the first result |
| hit@5 | The right file is among the first five files |
| MRR | Mean reciprocal rank of the right file (1.0 is perfect) |

## Run it

With Ollama:

```bash
ollama pull nomic-embed-text
python scripts/benchmark.py --base-url http://localhost:11434/v1 --model nomic-embed-text
```

Any OpenAI-compatible embeddings server works; pass its `--base-url` and `--model`.

The `benchmark` workflow runs the same thing on GitHub Actions in a pinned Ollama container whenever
the benchmark or the ranking code changes, and shows the table in the job summary.

## Limits

30 questions over 23 files is small: treat differences of one or two questions (3 to 7 points) as
noise. The questions were written by the project author, not drawn from real usage.
