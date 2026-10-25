import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent_ratchet.integrations.langfuse import fetch_trace, from_trace

TRACE = {
    "id": "tr-1",
    "input": "Refund order 77",
    "output": {"role": "assistant", "content": "Passed to a manager."},
    "latency": 2.5,
    "totalCost": 0.004,
    "observations": [
        {"id": "o3", "type": "TOOL", "name": "escalate", "startTime": "2026-10-01T10:00:03Z", "input": '{"order_id": "77"}', "output": "ticket"},
        {"id": "o1", "type": "GENERATION", "name": "plan", "startTime": "2026-10-01T10:00:01Z", "usageDetails": {"input": 300, "output": 40}},
        {"id": "o2", "type": "TOOL", "name": "lookup_order", "startTime": "2026-10-01T10:00:02Z", "input": {"order_id": "77"}, "output": {"amount": 900}},
        {"id": "o4", "type": "TOOL", "name": "notify", "startTime": "2026-10-01T10:00:04Z", "level": "ERROR", "statusMessage": "timeout"},
    ],
}


def test_from_trace_camel_case():
    t = from_trace(TRACE)
    assert t.tools == ["lookup_order", "escalate", "notify"]
    assert t.tool_calls[1].args == {"order_id": "77"} and t.tool_calls[2].error == "timeout"
    assert (t.input, t.output, t.cost_usd, t.latency_s) == ("Refund order 77", "Passed to a manager.", 0.004, 2.5)
    assert (t.llm_calls, t.input_tokens, t.output_tokens) == (1, 300, 40)


def test_from_trace_snake_case_sums_generation_cost():
    trace = {
        "id": "t",
        "observations": [
            {"type": "GENERATION", "start_time": "1", "usage_details": {"input": 10, "output": 2}, "calculated_total_cost": 0.001},
            {"type": "GENERATION", "start_time": "2", "usage": {"prompt_tokens": 5, "completion_tokens": 1}, "calculated_total_cost": 0.002},
        ],
    }
    t = from_trace(trace)
    assert (t.llm_calls, t.input_tokens, t.output_tokens) == (2, 15, 3) and t.cost_usd == pytest.approx(0.003)


@pytest.fixture
def langfuse(monkeypatch):
    seen = {"paths": [], "auth": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            seen["auth"] = self.headers["Authorization"]
            seen["paths"].append(self.path)
            self._send(TRACE if self.path == "/api/public/traces/tr-1" else {})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LANGFUSE_HOST", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    yield seen
    server.shutdown()


def test_fetch_a_production_trace(langfuse):
    assert from_trace(fetch_trace("tr-1")).tools == ["lookup_order", "escalate", "notify"]
    assert langfuse["auth"] == "Basic " + base64.b64encode(b"pk:sk").decode()
    fetch_trace("../scores?x=1")  # an id is never read as a path
    assert langfuse["paths"][-1] == "/api/public/traces/..%2Fscores%3Fx%3D1"


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    with pytest.raises(ValueError):
        fetch_trace("x")
