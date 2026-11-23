# Benchmark

How often does hermes-scout put the right file first? The benchmark in
[`benchmarks/`](https://github.com/Shizoqua/hermes-scout/tree/main/benchmarks) answers that with a
synthetic project of 23 files and 30 questions whose correct file is known:

- 18 **paraphrase** questions avoid the answer's own wording ("how is a user's secret phrase stored
  safely" for the password hashing code),
- 8 **exact** questions name an identifier, error code or tool (`E4021`, `pg_dump`),
- 4 **mixed** questions do both.

## Results

`nomic-embed-text` on Ollama 0.40.15, run by the
[benchmark workflow](https://github.com/Shizoqua/hermes-scout/actions/workflows/benchmark.yml)
on 23 November 2026:

| Ranking | hit@1 | hit@5 | MRR | exact hit@1 | mixed hit@1 | paraphrase hit@1 |
|---|---|---|---|---|---|---|
| hybrid | 77% | 93% | 0.83 | 100% | 100% | 61% |
| semantic | 93% | 100% | 0.97 | 100% | 100% | 89% |
| keyword | 60% | 87% | 0.70 | 100% | 100% | 33% |

- **hit@1**: the right file is the first result. **hit@5**: it is among the first five files.
  **MRR**: mean reciprocal rank of the right file, where 1.0 is perfect.
- Searching by meaning finds the right file first for 28 of 30 questions, and in the top five for
  all of them, including questions that share no words with the answer.
- Keyword search alone misses most paraphrased questions (33%), which is why hermes-scout embeds.
- On this set, hybrid ranking scores below meaning alone: when a question shares no words with its
  answer, the keyword ranking adds noise to the merge. Improving how the two rankings are combined
  is the next step, and this benchmark is how the change will be measured.

## Run it yourself

```bash
ollama pull nomic-embed-text
python scripts/benchmark.py --base-url http://localhost:11434/v1 --model nomic-embed-text
```

## Limits

30 questions over 23 files is small, so differences of one or two questions (3 to 7 points) are
noise. The questions were written by the project author, not drawn from real usage, and a different
embedding model will give different numbers.
