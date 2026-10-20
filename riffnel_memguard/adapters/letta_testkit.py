"""Test support for Letta: a tiny OpenAI-compatible /v1/embeddings server backed by the offline hash embedder.

It lets a real Letta server embed passages without network access or an API key (a stand-in for a real embedding
service, like `OfflineHashEmbedder` is for Mem0). Not for production use.
    python -m riffnel_memguard.adapters.letta_testkit 8765
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from sklearn.feature_extraction.text import HashingVectorizer

DIMS = 512
VEC = HashingVectorizer(analyzer="char", ngram_range=(2, 3), n_features=DIMS, norm="l2", alternate_sign=False)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        texts = body.get("input", [])
        texts = [texts] if isinstance(texts, str) else texts
        data = [{"object": "embedding", "index": i, "embedding": VEC.transform([t]).toarray()[0].tolist()}
                for i, t in enumerate(texts)]
        out = json.dumps({"object": "list", "data": data, "model": body.get("model", "hash"),
                          "usage": {"prompt_tokens": 0, "total_tokens": 0}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):  # keep test output quiet
        pass


def start_hash_embedding_server(port: int = 0) -> tuple[HTTPServer, str]:
    """Serve embeddings from a background thread. Returns (server, base_url_for_letta); call server.shutdown() when done."""
    srv = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"


def embedding_config(base_url: str) -> dict:
    return {"embedding_endpoint_type": "openai", "embedding_endpoint": base_url, "embedding_model": "hash",
            "embedding_dim": DIMS, "embedding_chunk_size": 300}


def create_test_agent(client, embed_url: str, name: str = "riffnel"):
    """A Letta agent whose archival memory is embedded by the stand-in. The LLM is never called, so its endpoint is a dummy."""
    llm = {"model": "unused", "model_endpoint_type": "openai", "model_endpoint": "http://127.0.0.1:9/v1",
           "context_window": 8000}
    return client.agents.create(name=name, llm_config=llm, embedding_config=embedding_config(embed_url),
                                memory_blocks=[], include_base_tools=False)


def delete_agent_and_archives(client, agent_id: str) -> None:
    """Deleting a Letta agent does NOT delete its archive or the archived passages (observed on Letta 0.16.7), so delete
    the archives first, then the agent."""
    for archive in list(client.archives.list(agent_id=agent_id, limit=100)):
        client.archives.delete(archive.id)
    client.agents.delete(agent_id)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), Handler).serve_forever()
