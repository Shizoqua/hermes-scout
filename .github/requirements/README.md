# CI tool requirements

Each `.in` file lists the tools one CI job needs; the matching `.txt` file pins every package with
its SHA-256 hashes, and the workflows install it with `pip install --require-hashes -r <file>.txt`.
Dependabot proposes updates monthly. To regenerate a lock by hand (for example after editing an
`.in` file), with [uv](https://docs.astral.sh/uv/):

```bash
uv pip compile test.in --generate-hashes --universal --python-version 3.11 --no-header -o test.txt
```

`fuzz.txt` is compiled for Python 3.13 (Atheris wheels are Linux and Python 3.12 or later).
