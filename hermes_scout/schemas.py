"""Tool schemas: what the model reads to decide when to call each tool."""

from typing import Any

_PATH = {
    "type": "string",
    "description": "Folder to search. Relative paths resolve against the working directory. Defaults to it.",
}
_GLOB = {
    "type": "string",
    "description": (
        "Only consider files matching these patterns, relative to the folder, separated by commas "
        "(e.g. '*.md', 'docs/', 'src/**/*.py'). Defaults to every indexed file."
    ),
}
_TOP_K = {
    "type": "integer",
    "description": "How many results to return (1-20). Defaults to the plugin's top_k setting.",
    "minimum": 1,
    "maximum": 20,
}

SCOUT_SEARCH: dict[str, Any] = {
    "name": "scout_search",
    "description": (
        "Search a folder of local files (notes, docs, source code, and PDF, Word, Excel, PowerPoint and "
        "OpenDocument files) by meaning and by keywords, using embeddings and full-text search together. "
        "Returns the most relevant passages with file path, line range and a similarity score (empty for "
        "keyword-only ranking); a passage from a document starts with its [page N], [slide N] or "
        "[sheet Name] line. The first search of a folder builds an index, which "
        "can take a while for large folders; later searches only re-read files that changed. Use it when "
        "the user asks where something is discussed or implemented and the exact wording is unknown."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for, in natural language (e.g. 'how retries back off after a 429').",
            },
            "path": _PATH,
            "glob": _GLOB,
            "ranking": {
                "type": "string",
                "enum": ["hybrid", "semantic", "keyword"],
                "description": (
                    "'hybrid' ranks questions by meaning and puts exact matches first when the query is only "
                    "code-like names (error codes, identifiers); 'semantic' by meaning only; 'keyword' by "
                    "exact words only. Defaults to the plugin's ranking setting (hybrid unless changed)."
                ),
            },
            "top_k": _TOP_K,
        },
        "required": ["query"],
    },
}

SCOUT_SIMILAR: dict[str, Any] = {
    "name": "scout_similar",
    "description": (
        "Find the files in a local folder most related in meaning to a given file (or part of one) or "
        "to a passage of text. Returns each related file's best-matching passage with path, line range "
        "and similarity score, best first, never the source file itself. Use it for 'what else is like "
        "this', related notes, duplicate or overlapping docs, and code that does something similar."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "A file in the folder to find related files for, relative to the folder.",
            },
            "lines": {
                "type": "string",
                "description": "Only use this part of the file, e.g. '10-40'. Defaults to the whole file.",
            },
            "text": {
                "type": "string",
                "description": "A passage to find related files for, instead of a file.",
            },
            "path": _PATH,
            "glob": _GLOB,
            "top_k": _TOP_K,
        },
    },
}
