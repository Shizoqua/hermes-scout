"""The OpenAI-compatible client against a local HTTP server. No outside network."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import embeddings


@pytest.fixture
def server():
    state = {"requests": [], "reply": None, "status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append({"path": self.path, "body": body, "headers": dict(self.headers)})
            reply = state["reply"](body) if callable(state["reply"]) else state["reply"]
            raw = json.dumps(reply).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state["base_url"] = f"http://127.0.0.1:{httpd.server_port}/v1"
    yield state
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def openai_reply(body, reverse=False):
    data = [{"object": "embedding", "index": i, "embedding": [float(i), 1.0]} for i in range(len(body["input"]))]
    return {"object": "list", "data": list(reversed(data)) if reverse else data, "model": body["model"]}


def test_vectors_come_back_in_input_order_even_when_the_server_shuffles(server):
    server["reply"] = lambda body: openai_reply(body, reverse=True)
    vectors = embeddings.embed_texts(["a", "b", "c"], base_url=server["base_url"], model="m")
    assert vectors == [[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]]
    [request] = server["requests"]
    assert request["path"] == "/v1/embeddings"
    assert request["body"] == {"model": "m", "input": ["a", "b", "c"]}


def test_api_key_is_sent_only_when_configured(server):
    server["reply"] = openai_reply
    embeddings.embed_texts(["a"], base_url=server["base_url"], model="m")
    embeddings.embed_texts(["a"], base_url=server["base_url"], model="m", api_key="test-key")
    first, second = (r["headers"] for r in server["requests"])
    assert "Authorization" not in first
    assert second["Authorization"] == "Bearer test-key"


def test_http_error_names_the_status_and_the_server_message(server):
    server["status"] = 404
    server["reply"] = {"error": {"message": "model 'm' not found"}}
    with pytest.raises(embeddings.EmbeddingError, match=r"HTTP 404: model 'm' not found.*ollama pull m"):
        embeddings.embed_texts(["a"], base_url=server["base_url"], model="m")


def test_wrong_number_of_embeddings_is_an_error(server):
    server["reply"] = {"data": [{"index": 0, "embedding": [1.0]}]}
    with pytest.raises(embeddings.EmbeddingError, match="1 embeddings for 2 inputs"):
        embeddings.embed_texts(["a", "b"], base_url=server["base_url"], model="m")


@pytest.mark.parametrize("vector", [[], ["x"], [True], [float("nan")]])
def test_malformed_embedding_is_an_error(server, vector):
    server["reply"] = {"data": [{"index": 0, "embedding": vector}]}
    with pytest.raises(embeddings.EmbeddingError, match="malformed"):
        embeddings.embed_texts(["a"], base_url=server["base_url"], model="m")


def test_unreachable_server_explains_how_to_fix_it():
    expected = r"cannot reach the embeddings server at http://127\.0\.0\.1:9/v1.*ollama pull m"
    with pytest.raises(embeddings.EmbeddingError, match=expected):
        embeddings.embed_texts(["a"], base_url="http://127.0.0.1:9/v1", model="m", timeout=2)


def test_no_texts_makes_no_request():
    assert embeddings.embed_texts([], base_url="http://127.0.0.1:9/v1", model="m") == []
