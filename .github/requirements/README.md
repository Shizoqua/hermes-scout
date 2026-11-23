# CI tool requirements

Each `.in` file lists the tools one CI job needs; the matching `.txt` file pins every package with
its SHA-256 hashes, and the workflows install it with `pip install --require-hashes -r <file>.txt`.
Dependabot proposes updates monthly and rebuilds a lock with the command in its header, so keep the
header and the `--universal` flag: the test lock must also hold the Windows-only packages.
To regenerate a lock by hand (for example after editing an `.in` file), with
[uv](https://docs.astral.sh/uv/), run the command shown at the top of that `.txt` file, e.g.

```bash
uv pip compile test.in --generate-hashes --universal --python-version 3.11 -o test.txt
```

`fuzz.txt` is compiled for Python 3.13 (Atheris wheels are Linux and Python 3.12 or later).
