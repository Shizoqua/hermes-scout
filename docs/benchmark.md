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
| hybrid | 93% | 100% | 0.97 | 100% | 100% | 89% |
| semantic | 93% | 100% | 0.97 | 100% | 100% | 89% |
| keyword | 63% | 83% | 0.72 | 100% | 100% | 39% |

- **hit@1**: the right file is the first result. **hit@5**: it is among the first five files.
  **MRR**: mean reciprocal rank of the right file, where 1.0 is perfect.
- Searching by meaning finds the right file first for 28 of 30 questions, and in the top five for
  all of them, including questions that share no words with the answer.
- Keyword search alone misses most paraphrased questions (39%), which is why hermes-scout embeds.
- Hybrid ranking, the default, matches the best result: it ranks questions in words by meaning and
  leads with exact words only for queries made of code-like names. Getting there took three measured
  steps: dropping filler words from the keyword half (77% to 77% first place, 93% to 97% top five),
  merging by score instead of by rank (to 83%), then routing questions to meaning (to 93%).

Two runs of the same code gave identical numbers, so the measurement is stable.

## Run it yourself

```bash
ollama pull nomic-embed-text
python scripts/benchmark.py --base-url http://localhost:11434/v1 --model nomic-embed-text
```

## Limits

30 questions over 23 files is small, so differences of one or two questions (3 to 7 points) are
noise. The questions were written by the project author, not drawn from real usage, and a different
embedding model will give different numbers.
