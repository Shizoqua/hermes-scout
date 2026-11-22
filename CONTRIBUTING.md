# Contributing

Thanks for helping improve semantic-search. Bug reports, ideas and pull requests are all welcome.

## Reporting a bug

Open an [issue](https://github.com/Shizoqua/hermes-semantic-search/issues/new/choose) with:

- your Hermes version (`hermes --version`) and operating system,
- the embeddings server and model you use (for example Ollama with `nomic-embed-text`),
- what you asked, what you expected and what the tool returned (remove anything private).

## Making a change

1. Fork the repository and create a branch from `main`.
2. Keep `engine.py` and `embeddings.py` free of Hermes imports and third-party packages, so they stay
   testable on their own. Hermes wiring belongs in `__init__.py`.
3. Add or update tests in `tests/` for the behaviour you change, and run them:

   ```bash
   python -m pip install "pytest>=8,<9" "pytest-cov>=6,<8" "ruff==0.15.10"
   python -m pytest tests --cov=.
   ruff check . && ruff format --check .
   ```

   CI fails if coverage drops below 90%.

4. If you changed `__init__.py` or `plugin.yaml`, also run the checks the Hermes catalog runs:

   ```bash
   hermes plugins validate . --install-deps
   hermes plugins doctor . --ci
   ```

5. Add a line to `CHANGELOG.md` under "Unreleased" and open a pull request describing what changed
   and why.

## Design rules

- No new runtime dependencies. The plugin ships as standard-library Python.
- Never read credentials from files. Secrets come only through Hermes's secret store.
- Never read a path Hermes's file tools refuse (the plugin checks every file with Hermes's own
  file-safety rules).
- Anything that sends data off the machine must be described in the README's Disclosure section.
