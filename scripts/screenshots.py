"""Take the README screenshots from the real review page and the real command line.

    uv run python scripts/screenshots.py

Starts the HTTP service in this process with a fixed clock, plays a short morning of agent actions
through its API, then photographs the review page with Playwright and Chromium. The terminal
picture shows the actual output of `oversight check`. Nothing on either picture is typed by hand.
Needs Node with the playwright package (npm install -g playwright).
"""

from __future__ import annotations

import html
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from oversight import Oversight  # noqa: E402
from oversight.server import serve  # noqa: E402

START = datetime(2026, 10, 8, 9, 0, tzinfo=UTC).timestamp()


class Clock:
    def __init__(self) -> None:
        self.t = START

    def __call__(self) -> float:
        return self.t


# (seconds after 9:00, endpoint, body): a morning of an accounts payable agent.
# Answers refer to an earlier check by its call_id.
MORNING: list[tuple[int, str, dict]] = [
    (0, "/check", {"tool": "read_file", "params": {"path": "invoices/INV-2207.pdf"}}),
    (90, "/check", {"tool": "send_email", "params": {"to": "maria@example-corp.test", "subject": "Invoices due this week"}}),
    (
        240,
        "/check",
        {
            "tool": "pay_invoice",
            "call_id": "inv-2207",
            "params": {"vendor": "Northwind Paper", "amount": 1250, "invoice": "INV 2207"},
            "description": "Pay Northwind's September invoice",
        },
    ),
    (
        252,
        "/check",
        {"tool": "delete_file", "params": {"path": "invoices/", "scope": "delete all invoices before 2025"}, "description": "Tidy up the invoices folder"},
    ),
    (330, "/answer", {"call_id": "inv-2207", "approved": True, "note": "Matches PO 4471"}),
    (
        900,
        "/check",
        {
            "tool": "pay_invoice",
            "call_id": "inv-0912",
            "params": {"vendor": "Brightline Consulting", "amount": 3400, "invoice": "INV 0912"},
            "description": "Pay Brightline's consulting invoice",
        },
    ),
    (960, "/answer", {"call_id": "inv-0912", "approved": False, "note": "No purchase order on file"}),
    (1500, "/person", {"available": False}),
    (
        1620,
        "/check",
        {"tool": "pay_invoice", "params": {"vendor": "Acme Supplies", "amount": 18500, "invoice": "INV 2210"}, "description": "Pay Acme's October invoice"},
    ),
    (
        1700,
        "/check",
        {
            "tool": "update_vendor",
            "params": {"vendor": "Acme Supplies", "bank_account": "GB29 NWBK 6016 1331 9268 19"},
            "description": "Vendor emailed new bank details",
        },
    ),
    (2400, "/person", {"available": True}),
    (
        2560,
        "/check",
        {
            "tool": "pay_invoice",
            "params": {"vendor": "Acme Supplies", "amount": 12800, "invoice": "INV 2213"},
            "description": "Pay Acme's quarterly supplies invoice",
        },
    ),
    (
        2600,
        "/check",
        {"tool": "pay_invoice", "params": {"vendor": "Acme Supplies", "amount": 420, "invoice": "INV 2214"}, "description": "Pay Acme's small parts invoice"},
    ),
    (2610, "/check", {"tool": "read_file", "params": {"path": "invoices/INV-2214.pdf"}}),
]
NOW = 2640

TERMINAL = [
    ["oversight", "check", "read_file", '{"path": "invoices/INV-2214.pdf"}'],
    ["oversight", "check", "pay_invoice", '{"vendor": "Acme Supplies", "amount": 18500}'],
]


def post(url: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def terminal_page(out: Path) -> None:
    """Run the real CLI and lay its output out like a terminal window."""
    blocks = []
    for cmd in TERMINAL:
        r = subprocess.run([sys.executable, "-m", "oversight.cli", *cmd[1:]], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        blocks.append(
            f'<div><span class="p">$</span> {html.escape(shlex.join(cmd))}</div><pre>{html.escape(r.stdout.rstrip())}</pre>'
            f'<div class="exit">exit code {r.returncode}</div>'
        )
    out.write_text(
        """<!doctype html><meta charset="utf-8"><style>
body { margin: 0; background: #f9f9f7; padding: 24px; }
.win { background: #1a1a19; border-radius: 12px; box-shadow: 0 1px 2px rgba(0,0,0,.08), 0 8px 24px rgba(0,0,0,.10); overflow: hidden; }
.bar { display: flex; gap: 8px; padding: 12px 14px; background: #262624; }
.bar span { width: 12px; height: 12px; border-radius: 50%; background: #4a4a47; }
.body { padding: 16px 20px 20px; color: #e8e7e0; font: 14px/1.6 "JetBrains Mono", "DejaVu Sans Mono", monospace; }
.p { color: #3987e5; } pre { margin: 4px 0 2px; font: inherit; color: #c3c2b7; white-space: pre-wrap; }
.exit { color: #898781; margin-bottom: 14px; } .body > :last-child { margin-bottom: 0; }
</style><div class="win"><div class="bar"><span></span><span></span><span></span></div><div class="body">"""
        + "".join(blocks)
        + "</div></div>",
        encoding="utf-8",
    )


def main() -> None:
    clock = Clock()
    srv = serve("127.0.0.1", 0, Oversight(clock=clock), token="")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}"
    for offset, path, body in MORNING:
        clock.t = START + offset
        post(url, path, body)
    clock.t = START + NOW

    figures = ROOT / "figures"
    with tempfile.TemporaryDirectory() as tmp:
        term = Path(tmp) / "terminal.html"
        terminal_page(term)
        shots = [
            {"url": url + "/", "out": str(figures / "review_page.png"), "width": 1180, "height": 900, "waitFor": ".card", "until": "section"},
            {"url": url + "/", "out": str(figures / "review_history.png"), "width": 1180, "height": 900, "waitFor": ".card", "section": 2},
            {"url": term.as_uri(), "out": str(figures / "terminal.png"), "width": 860, "height": 400, "until": ".win"},
        ]
        if os.environ.get("SCREENSHOT_CHECKS"):  # dark mode and phone width, for eyeballing only
            shots += [
                {"url": url + "/", "out": str(Path(tmp) / "dark.png"), "width": 1180, "scheme": "dark", "waitFor": ".card"},
                {"url": url + "/", "out": str(Path(tmp) / "phone.png"), "width": 390, "height": 844, "waitFor": ".card"},
            ]
        node_path = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
        env = {**os.environ, "NODE_PATH": os.pathsep.join(p for p in (os.environ.get("NODE_PATH"), node_path) if p)}
        subprocess.run(["node", str(ROOT / "scripts" / "screenshot.cjs"), json.dumps(shots)], check=True, env=env)
        if os.environ.get("SCREENSHOT_CHECKS"):
            for name in ("dark.png", "phone.png"):
                shutil.copy(Path(tmp) / name, Path(os.environ["SCREENSHOT_CHECKS"]) / name)
    srv.shutdown()
    for s in shots[:3]:
        print("wrote", Path(s["out"]).relative_to(ROOT))


if __name__ == "__main__":
    main()
