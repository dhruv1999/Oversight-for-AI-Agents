"""A small HTTP service so agents in any language can ask before they act.

    oversight serve --port 8321 --state .oversight

    POST /check   {"tool": "pay_invoice", "params": {...}, "description": "...", "call_id": "..."}
                  -> {"call_id", "outcome", "risk", "reason", "reasons", "rules"}
    POST /answer  {"call_id": "...", "approved": true, "note": "..."}     record what the person decided
    POST /person  {"available": false}                                      person stepped away / came back
    GET  /health

Binds to 127.0.0.1 by default. Set OVERSIGHT_TOKEN to require `Authorization: Bearer <token>`.
If a check fails inside the server, the answer is outcome "ask_human" with status 500: a client
that only reads `outcome` still fails safe.
Standard library only; one process can serve many agents because decisions go through the StateStore.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .guard import Check, Oversight

MAX_BODY = 1_000_000
MAX_PENDING = 10_000


class OversightServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], guard: Oversight, token: str | None = None):
        super().__init__(address, _Handler)
        self.guard = guard
        self.token = token
        self.pending: OrderedDict[str, Check] = OrderedDict()  # call_id -> check awaiting a person's answer
        self.pending_lock = threading.Lock()

    def remember(self, check: Check) -> None:
        with self.pending_lock:
            self.pending[check.action.id] = check
            while len(self.pending) > MAX_PENDING:
                self.pending.popitem(last=False)


class _Handler(BaseHTTPRequestHandler):
    server: OversightServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # quiet by default; decisions go to the audit log
        pass

    def _send(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self) -> bool:
        if not self.server.token:
            return True
        got = self.headers.get("Authorization", "")
        return hmac.compare_digest(got, f"Bearer {self.server.token}")

    def _body(self) -> dict[str, Any] | None:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return None
        try:
            data = json.loads(self.rfile.read(n))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True, "rules": self.server.guard.rules_id})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authorised():
            self._send(401, {"error": "missing or wrong bearer token"})
            return
        body = self._body()
        if body is None:
            self._send(400, {"error": f"body must be a JSON object under {MAX_BODY} bytes"})
            return
        guard = self.server.guard
        if self.path == "/check":
            tool = body.get("tool")
            params = body.get("params", {})
            if not isinstance(tool, str) or not tool or not isinstance(params, dict):
                self._send(400, {"error": "'tool' (string) is required and 'params' must be an object"})
                return
            try:
                check = guard.check(tool, params, str(body.get("description", "")), body.get("call_id"))
            except Exception as e:  # fail safe: never answer 'execute' when something broke
                self._send(500, {"outcome": "ask_human", "error": f"{type(e).__name__}: {e}"})
                return
            if check.needs_person or check.waiting:
                self.server.remember(check)
            self._send(
                200,
                {
                    "call_id": check.action.id,
                    "outcome": check.outcome.value,
                    "risk": check.risk,
                    "reason": check.reason,
                    "reasons": list(check.result.decision.reasons),
                    "rules": guard.rules_id,
                },
            )
        elif self.path == "/answer":
            with self.server.pending_lock:
                check = self.server.pending.pop(str(body.get("call_id")), None)
            if check is None or not isinstance(body.get("approved"), bool):
                self._send(404 if check is None else 400, {"error": "unknown call_id, or 'approved' is not true/false"})
                return
            guard.record_answer(check, body["approved"], str(body.get("note", "")))
            self._send(200, {"ok": True})
        elif self.path == "/person":
            if not isinstance(body.get("available"), bool):
                self._send(400, {"error": "'available' must be true or false"})
                return
            guard.person_back() if body["available"] else guard.person_away()
            self._send(200, {"ok": True, "available": body["available"]})
        else:
            self._send(404, {"error": "not found"})


def serve(host: str = "127.0.0.1", port: int = 8321, guard: Oversight | None = None, token: str | None = None) -> OversightServer:
    """Create (but do not start) a server. Call .serve_forever() to run it."""
    return OversightServer((host, port), guard or Oversight(), token if token is not None else os.environ.get("OVERSIGHT_TOKEN"))
