"""Client for an OpenAI-compatible ``POST /embeddings`` endpoint. Standard library only.

Works with Ollama (``http://localhost:11434/v1``), LM Studio, llama.cpp's server, vLLM and hosted
OpenAI-compatible APIs.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

USER_AGENT = "hermes-scout/0.5.0"
DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama's OpenAI-compatible API
DEFAULT_MODEL = "nomic-embed-text"
Opener = Callable[..., Any]


def _origin(url: str) -> tuple[str, str]:
    parts = urllib.parse.urlsplit(url)
    return parts.scheme.lower(), parts.netloc.lower()


class _SameOriginCredentials(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but never carry the Authorization header to another origin."""

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and _origin(newurl) != _origin(req.full_url):
            for name in [k for k in new.headers if k.lower() == "authorization"]:
                del new.headers[name]
            new.unredirected_hdrs.pop("Authorization", None)
        return new


_default_opener = urllib.request.build_opener(_SameOriginCredentials()).open


class EmbeddingError(RuntimeError):
    """The embeddings server could not be reached or answered with something unusable."""


def _detail(err: urllib.error.HTTPError) -> str:
    try:
        body = err.read(2000).decode("utf-8", "replace")
    except OSError:
        return ""
    try:
        message = json.loads(body).get("error")
    except (ValueError, AttributeError):
        return body.strip()[:300]
    if isinstance(message, dict):
        message = message.get("message")
    return str(message or body.strip())[:300]


def embed_texts(
    texts: list[str],
    *,
    base_url: str,
    model: str,
    api_key: str | None = None,
    timeout: float = 60.0,
    opener: Opener | None = None,
) -> list[list[float]]:
    """One embedding vector per text, in input order.

    ``opener`` defaults to a standard-library opener that drops the API key on a redirect to another
    origin; Hermes passes its own credential-safe opener.
    """
    if not texts:
        return []
    url = base_url.rstrip("/") + "/embeddings"
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url, data=json.dumps({"model": model, "input": texts}).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with (opener or _default_opener)(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        hint = " Check the model name (for Ollama: `ollama pull " + model + "`)." if err.code in (400, 404) else ""
        raise EmbeddingError(
            f"embeddings server at {base_url} answered HTTP {err.code}: {_detail(err)}.{hint}"
        ) from err
    except urllib.error.URLError as err:
        raise EmbeddingError(
            f"cannot reach the embeddings server at {base_url} ({err.reason}). Start it (for Ollama: "
            f"`ollama serve`, then `ollama pull {model}`) or point base_url (the plugin setting, or --base-url "
            "on the command line) at another OpenAI-compatible embeddings endpoint."
        ) from err
    except (TimeoutError, ValueError) as err:
        raise EmbeddingError(f"embeddings server at {base_url} gave no usable answer: {err}") from err
    return _parse(payload, len(texts), base_url)


def _parse(payload: Any, expected: int, base_url: str) -> list[list[float]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or len(data) != expected:
        got = len(data) if isinstance(data, list) else "no"
        raise EmbeddingError(f"embeddings server at {base_url} returned {got} embeddings for {expected} inputs")
    # The spec allows any order; ``index`` says which input each vector belongs to.
    ordered = sorted(data, key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0)
    vectors: list[list[float]] = []
    for item in ordered:
        vector = item.get("embedding") if isinstance(item, dict) else None
        if (
            not isinstance(vector, list)
            or not vector
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vector)
        ):
            raise EmbeddingError(f"embeddings server at {base_url} returned a malformed embedding")
        vectors.append([float(v) for v in vector])
    if len({len(v) for v in vectors}) != 1:
        raise EmbeddingError(f"embeddings server at {base_url} returned embeddings of different sizes")
    return vectors
