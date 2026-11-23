# Contributing

Thanks for helping improve hermes-scout. Bug reports, ideas and pull requests are all welcome.

## Reporting a bug

Open an [issue](https://github.com/Shizoqua/hermes-scout/issues/new/choose) with:

- your Hermes version (`hermes --version`) and operating system,
- the embeddings server and model you use (for example Ollama with `nomic-embed-text`),
- what you asked, what you expected and what the tool returned (remove anything private).

## Making a change

1. Fork the repository and create a branch from `main`.
2. Keep `hermes_scout/engine.py`, `hermes_scout/embeddings.py` and `hermes_scout/cli.py` free of Hermes
   imports and third-party packages, so they stay testable on their own. Hermes wiring belongs in
   `hermes_scout/__init__.py`.
3. Add or update tests in `tests/` for the behaviour you change, and run them:

   ```bash
   python -m pip install --require-hashes -r .github/requirements/test.txt -r .github/requirements/lint.txt
   python -m pytest --cov=hermes_scout
   ruff check . && ruff format --check .
   mypy
   ```

   CI fails if coverage drops below 90%.

4. If you changed `hermes_scout/__init__.py` or `hermes_scout/plugin.yaml`, also run the checks the Hermes catalog runs:

   ```bash
   hermes plugins validate hermes_scout --install-deps
   hermes plugins doctor hermes_scout --ci
   ```

5. If you changed the docs, preview them with
   `pip install --require-hashes -r .github/requirements/docs.txt && mkdocs serve`.
   If you changed `hermes_scout/documents.py`, fuzz it for a minute (Linux, Python 3.12 or later):
   `pip install --require-hashes -r .github/requirements/fuzz.txt && python fuzz/fuzz_documents.py -max_total_time=60 fuzz/corpus`.

6. Add a line to `CHANGELOG.md` under "Unreleased" and open a pull request describing what changed
   and why.

## Design rules

- No new runtime dependencies. The plugin ships as standard-library Python.
- Never read credentials from files. Secrets come only through Hermes's secret store.
- Never read a path Hermes's file tools refuse (the plugin checks every file with Hermes's own
  file-safety rules).
- Anything that sends data off the machine must be described in the README's Disclosure section.
