"""A small HTTP service so agents in any language can ask before they act.

    oversight serve --port 8321 --state .oversight

    POST /check   {"tool": "pay_invoice", "params": {...}, "description": "...", "call_id": "..."}
                  -> {"call_id", "outcome", "risk", "reason", "summary", "reasons", "rules"}
    POST /answer  {"call_id": "...", "approved": true, "note": "..."}     record what the person decided
    POST /person  {"available": false}                                      person stepped away / came back
    GET  /checks/<call_id>   -> {"status": "waiting" | "approved" | "rejected"}   for agents waiting on a person
    GET  /inbox              -> what the review page shows: attention left, actions waiting, recent decisions
    GET  /                   the review page, where the person approves or rejects waiting actions
    GET  /health

Binds to 127.0.0.1 by default. Set OVERSIGHT_TOKEN to require `Authorization: Bearer <token>`.
Without a token the service only answers requests addressed to localhost, and it refuses requests
that other web sites make from the person's browser, so a page they happen to visit cannot read
or answer their queue.
If a check fails inside the server, the answer is outcome "ask_human" with status 500: a client
that only reads `outcome` still fails safe.
Standard library only; one process can serve many agents because decisions go through the StateStore.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
from collections import OrderedDict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .gate import Outcome
from .guard import Check, Oversight
from .redact import redact, redact_text

MAX_BODY = 1_000_000
MAX_PENDING = 10_000
MAX_RECENT = 50
PAGE = Path(__file__).with_name("review.html")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _event(check: Check) -> str:
    if check.allowed:
        return "ran" if check.result.verdict is None else "checked"
    return {Outcome.BLOCK: "blocked", Outcome.ASK_HUMAN: "asked", Outcome.DEFER: "queued"}[check.outcome]


def _view(check: Check) -> dict[str, Any]:
    """A waiting action as the review page shows it. Secrets are removed; the person does not need them."""
    a = check.action
    return {
        "call_id": a.id,
        "tool": a.tool,
        "risk": check.risk,
        "outcome": check.outcome.value,
        "summary": check.summary,
        "reasons": list(check.result.decision.reasons),
        "params": redact(a.params),
        "description": "" if a.description == f"call {a.tool}" else redact_text(a.description),
        "asked_at": check.result.decision.timestamp,
    }


class OversightServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], guard: Oversight, token: str | None = None):
        super().__init__(address, _Handler)
        self.guard = guard
        self.token = token
        self.loopback = address[0] in LOOPBACK or address[0].startswith("127.")
        self.page = PAGE.read_text(encoding="utf-8")
        self.pending: OrderedDict[str, Check] = OrderedDict()  # call_id -> check awaiting a person's answer
        self.answers: OrderedDict[str, dict[str, Any]] = OrderedDict()  # call_id -> what the person decided
        self.recent: deque[dict[str, Any]] = deque(maxlen=MAX_RECENT)  # newest first
        self.pending_lock = threading.Lock()

    def remember(self, check: Check) -> None:
        with self.pending_lock:
            self.pending[check.action.id] = check
            while len(self.pending) > MAX_PENDING:
                self.pending.popitem(last=False)

    def note(self, check: Check, event: str, at: float, summary: str) -> None:
        with self.pending_lock:
            self.recent.appendleft({"call_id": check.action.id, "tool": check.action.tool, "risk": check.risk, "event": event, "summary": summary, "at": at})

    def answer(self, call_id: str, approved: bool, note: str) -> bool:
        with self.pending_lock:
            check = self.pending.pop(call_id, None)
        if check is None:
            return False
        self.guard.record_answer(check, approved, note)
        with self.pending_lock:
            self.answers[call_id] = {"status": "approved" if approved else "rejected", "note": note}
            while len(self.answers) > MAX_PENDING:
                self.answers.popitem(last=False)
        self.note(check, "approved" if approved else "rejected", self.guard.attention()["now"], note)
        return True

    def status(self, call_id: str) -> dict[str, Any] | None:
        with self.pending_lock:
            if call_id in self.pending:
                return {"call_id": call_id, "status": "waiting"}
            if call_id in self.answers:
                return {"call_id": call_id, **self.answers[call_id]}
        return None

    def inbox(self) -> dict[str, Any]:
        attention = self.guard.attention()
        with self.pending_lock:
            pending = [_view(c) for c in self.pending.values()]
            recent = list(self.recent)
        return {"rules": self.guard.rules_id, "attention": attention, "pending": pending, "recent": recent}


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
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _send_page(self) -> None:
        nonce = secrets.token_urlsafe(16)
        data = self.server.page.replace("__NONCE__", nonce).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; img-src data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.send_header("X-Frame-Options", "DENY")  # nobody can frame the page and trick a click on Approve
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self) -> bool:
        if not self.server.token:
            return True
        got = self.headers.get("Authorization", "")
        return hmac.compare_digest(got, f"Bearer {self.server.token}")

    def _host_ok(self) -> bool:
        """Without a token, answer only requests addressed to localhost (stops DNS rebinding)."""
        if self.server.token or not self.server.loopback:
            return True
        return (urlsplit("//" + self.headers.get("Host", "")).hostname or "") in LOOPBACK

    def _origin_ok(self) -> bool:
        """Browsers send Origin on cross site requests; refuse any that come from another site."""
        origin = self.headers.get("Origin")
        return origin is None or urlsplit(origin).netloc == self.headers.get("Host", "")

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
        if not self._host_ok():
            self._send(403, {"error": "this service only answers requests addressed to localhost; set OVERSIGHT_TOKEN to serve other names"})
            return
        path = urlsplit(self.path).path
        if path == "/health":
            self._send(200, {"ok": True, "rules": self.server.guard.rules_id})
        elif path == "/":
            self._send_page()  # the page holds no data; it calls /inbox, which needs the token
        elif not self._authorised():
            self._send(401, {"error": "missing or wrong bearer token"})
        elif path == "/inbox":
            self._send(200, self.server.inbox())
        elif path.startswith("/checks/"):
            status = self.server.status(unquote(path[len("/checks/") :]))
            if status:
                self._send(200, status)
            else:
                self._send(404, {"error": "unknown call_id (never asked, or expired)"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._host_ok() or not self._origin_ok():
            self._send(403, {"error": "request refused: wrong host, or sent by another web site"})
            return
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
            self.server.note(check, _event(check), check.result.decision.timestamp, check.summary)
            self._send(
                200,
                {
                    "call_id": check.action.id,
                    "outcome": check.outcome.value,
                    "risk": check.risk,
                    "reason": check.reason,
                    "summary": check.summary,
                    "reasons": list(check.result.decision.reasons),
                    "rules": guard.rules_id,
                },
            )
        elif self.path == "/answer":
            if not isinstance(body.get("approved"), bool):
                self._send(400, {"error": "'approved' must be true or false"})
                return
            if not self.server.answer(str(body.get("call_id")), body["approved"], str(body.get("note", ""))[:500]):
                self._send(404, {"error": "unknown call_id (never asked, already answered, or expired)"})
                return
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
