"""Drives the real anthropic SDK against a local stub server: proves the SDK accepts our kwargs
and shows the exact JSON body + beta header that would go to the API. No network, no spend."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

anthropic = pytest.importorskip("anthropic")

from oversight.adapters.anthropic_client import FALLBACK_BETA, AnthropicClient  # noqa: E402
from oversight.safety_model import VERDICT_SCHEMA  # noqa: E402

CAPTURED = {}
REPLY = {
    "id": "msg_stub",
    "type": "message",
    "role": "assistant",
    "model": "claude-opus-5-5",
    "content": [{"type": "text", "text": '{"verdict":"block","confidence":0.9,"rationale":"x"}'}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 321, "output_tokens": 45},
}


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers["content-length"])
        CAPTURED["path"] = self.path
        CAPTURED["beta"] = self.headers.get("anthropic-beta")
        CAPTURED["body"] = json.loads(self.rfile.read(n))
        out = json.dumps(REPLY).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_real_sdk_request_and_response(server):
    sdk = anthropic.Anthropic(api_key="test-key", base_url=server, max_retries=0)
    r = AnthropicClient(client=sdk, json_schema=VERDICT_SCHEMA).complete("SYS", "USER")
    body = CAPTURED["body"]
    assert CAPTURED["path"].startswith("/v1/messages")
    assert FALLBACK_BETA in CAPTURED["beta"]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert body["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": VERDICT_SCHEMA}}
    assert body["system"] == "SYS" and body["messages"] == [{"role": "user", "content": "USER"}]
    assert (r.input_tokens, r.output_tokens, r.stop_reason) == (321, 45, "end_turn")
    assert json.loads(r.text)["verdict"] == "block"
