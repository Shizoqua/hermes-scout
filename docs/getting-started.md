# Getting started

## 1. Start an embeddings server

hermes-scout needs a server that turns text into embeddings. The easiest is [Ollama](https://ollama.com):

```bash
ollama pull nomic-embed-text
ollama serve            # if it is not already running
```

Any other OpenAI-compatible server works too; see [Configuration](configuration.md#embedding-servers).

## 2. Install hermes-scout

=== "Hermes plugin"

    ```bash
    hermes plugins install hermes-scout
    hermes plugins enable hermes-scout
    ```

    Then ask Hermes something like *"Search my notes in ~/notes for how I set up backups."*
    See [Use with Hermes](hermes.md).

=== "Command line"

    ```bash
    pipx install hermes-scout      # or: pip install hermes-scout
    hermes-scout search "how I set up backups" ~/notes
    ```

    See [Command line](cli.md).

## 3. Search

The first search of a folder builds its index, which takes a while for a large folder. Later searches
only re-embed files that changed, so they are fast.
