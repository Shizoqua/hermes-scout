"""Tool schema: what the model reads to decide when to call ``scout_search``."""

SEMANTIC_SEARCH = {
    "name": "scout_search",
    "description": (
        "Search a folder of local text files (notes, docs, source code) by meaning rather than exact "
        "words, using embeddings. Returns the most relevant passages with file path, line range and a "
        "similarity score. The first search of a folder builds an index, which can take a while for "
        "large folders; later searches only re-read files that changed. Use it when the user asks where "
        "something is discussed or implemented and the exact wording is unknown."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for, in natural language (e.g. 'how retries back off after a 429').",
            },
            "path": {
                "type": "string",
                "description": (
                    "Folder to search. Relative paths resolve against the working directory. Defaults to it."
                ),
            },
            "glob": {
                "type": "string",
                "description": (
                    "Only search files matching these patterns, relative to the folder, separated by "
                    "commas (e.g. '*.md', 'docs/', 'src/**/*.py'). Defaults to every indexed file."
                ),
            },
            "top_k": {
                "type": "integer",
                "description": "How many passages to return (1-20). Defaults to the plugin's top_k setting.",
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["query"],
    },
}
