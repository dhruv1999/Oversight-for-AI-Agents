"""A small corporate card approval app built on the library.

    python examples/corporate_card/app.py        then open http://127.0.0.1:8400

Employees submit card expenses and invoices (submissions.json). An AI expense agent processes
each one, and Oversight decides who approves it: small spend with a receipt goes through on its
own, the automatic checker reviews the middle, and the finance approver only sees what needs them.
The risk rules are in expense_rules.yaml. The company, people and merchants are made up, and the
sample morning is replayed on a fixed clock so the page always looks the same.
"""

from __future__ import annotations

import html
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from oversight import Check, Oversight

HERE = Path(__file__).parent
START = 1_791_450_000.0  # 9:00 on the sample morning
LIMITS = [("over-5000", "Over $5,000"), ("over-1000", "Over $1,000"), ("over-100", "Over $100"), ("no-receipt", "No receipt")]


def why(check: Check) -> tuple[str, str]:
    """The approver's view of a decision: the policy limit it hit, and what that means for them."""
    hit = next((label for name, label in LIMITS if any(n.startswith(f"rule {name}:") for n in check.action.notes)), "Within policy")
    if check.waiting:
        return hit, "Held until you are back."
    if check.risk == "critical":
        return hit, "A person always approves spend this large."
    return hit, "Above the automatic approval limit, so it comes to you."


class Desk:
    """Every submission, what Oversight decided, and what the approver answered."""

    def __init__(self) -> None:
        self.guard = Oversight(tools=HERE / "expense_rules.yaml")
        self.items: list[dict[str, Any]] = []
        self.now = START
        for s in json.loads((HERE / "submissions.json").read_text(encoding="utf-8")):
            self.submit(s)

    def submit(self, s: dict[str, Any]) -> None:
        self.now = START + 60 * s["minute"]
        params = {k: s[k] for k in ("employee", "merchant", "amount", "category", "receipt")}
        check = self.guard.check(s["tool"], params, s["memo"], now=self.now)  # the agent asks before it acts
        if check.allowed:
            status = "Approved by the agent" if check.result.verdict is None else "Approved after an automatic check"
        elif check.blocked:
            status = "Blocked by the automatic check"
        else:
            status = "waiting"
        self.items.append({**s, "check": check, "status": status, "note": ""})
        if "answer" in s:
            self.decide(len(self.items) - 1, s["answer"]["approved"], s["answer"]["note"], START + 60 * s["answer"]["minute"])

    def decide(self, i: int, approved: bool, note: str = "", now: float | None = None) -> None:
        item = self.items[i]
        if item["status"] != "waiting":
            return
        self.now = max(self.now, now or self.now)
        self.guard.record_answer(item["check"], approved, note, now=self.now)
        item["status"], item["note"] = ("Approved by you" if approved else "Rejected by you"), note

    @staticmethod
    def row(x: dict[str, Any]) -> str:
        e = html.escape
        who = "you" if "you" in x["status"] else "agent"
        note = f"<small>{e(x['note'])}</small>" if x["note"] else ""
        return (
            f'<tr><td>{e(x["employee"])}</td><td>{e(x["merchant"])}</td><td class="num">${x["amount"]:,.2f}</td>'
            f'<td><span class="status {who}">{e(x["status"])}</span>{note}</td></tr>'
        )

    def page(self) -> str:
        e = html.escape
        waiting = sorted((i for i, x in enumerate(self.items) if x["status"] == "waiting"), key=lambda i: -self.items[i]["amount"])
        handled = [x for x in self.items if x["status"] != "waiting"]
        by_agent = [x for x in handled if "you" not in x["status"]]
        att = self.guard.attention(now=self.now + 180)
        meter = "".join(f'<i class="{"on" if k < att["asked"] else ""}"></i>' for k in range(att["limit"]))

        cards = []
        for i in waiting:
            x = self.items[i]
            limit, meaning = why(x["check"])
            initials = "".join(w[0] for w in x["employee"].split()[:2])
            receipt = "receipt" if "attached" in x["receipt"] else "receipt missing"
            receipt_label = {"attached": "Receipt attached", "missing": "No receipt"}.get(x["receipt"], x["receipt"].capitalize())
            cards.append(f"""
      <article class="card">
        <div class="who"><span class="avatar a{i % 5}">{e(initials)}</span>
          <div><b>{e(x["employee"])}</b><small>{e(x["team"])}</small></div></div>
        <div class="what"><b>{e(x["merchant"])}</b>
          <small>{e(x["category"])} · {e(x["memo"])}</small>
          <span class="chips"><span class="chip {receipt.replace(" ", "-")}">{e(receipt_label)}</span>
          <span class="chip limit">{e(limit)}</span></span>
          <small class="why">{e(meaning)}</small></div>
        <div class="amount">${x["amount"]:,.2f}</div>
        <form method="post" action="/decide" class="actions">
          <input type="hidden" name="i" value="{i}">
          <button name="approved" value="no">Reject</button>
          <button name="approved" value="yes" class="primary">Approve</button>
        </form>
      </article>""")

        rows = "".join(self.row(x) for x in reversed(handled))
        return PAGE.format(
            waiting=len(waiting),
            agent=len(by_agent),
            agent_total=f"{sum(x['amount'] for x in by_agent):,.2f}",
            submitted=len(self.items),
            asked=att["asked"],
            limit=att["limit"],
            meter=meter,
            cards="".join(cards) or '<p class="empty">Nothing needs you right now.</p>',
            rows=rows,
        )


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acme Corp · Card approvals</title>
<style>
:root {{ --ink: #14161a; --ink2: #5b616b; --muted: #8a909a; --line: #e6e8ec; --page: #f6f7f9; --card: #fff;
  --accent: #2a78d6; --good: #0f7b3f; --goodbg: #e7f5ec; --warn: #9a5b00; --warnbg: #fdf1dc; --bad: #b42318; --badbg: #fde8e7; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Arial, sans-serif; }}
header {{ display: flex; align-items: center; gap: 28px; padding: 0 32px; height: 60px; background: var(--card); border-bottom: 1px solid var(--line); }}
.logo {{ display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 16px; }}
.logo span {{ width: 28px; height: 28px; border-radius: 8px; background: #1f2a44; color: #fff; display: grid; place-items: center; font-size: 14px; }}
nav {{ display: flex; gap: 22px; color: var(--ink2); font-size: 14px; height: 100%; }}
nav a {{ display: flex; align-items: center; border-bottom: 2px solid transparent; }}
nav a.on {{ color: var(--ink); font-weight: 600; border-color: var(--accent); }}
.me {{ margin-left: auto; display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--ink2); }}
.me b {{ color: var(--ink); font-weight: 600; }}
main {{ max-width: 1120px; margin: 0 auto; padding: 28px 32px 40px; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
.lead {{ color: var(--ink2); margin: 0 0 22px; }}
.tiles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 28px; }}
.tile {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; }}
.tile small {{ display: block; color: var(--ink2); font-size: 13px; }}
.tile b {{ display: block; font-size: 28px; margin: 4px 0 2px; }}
.tile span {{ color: var(--muted); font-size: 13px; }}
.meter {{ display: flex; gap: 3px; margin: 8px 0 6px; }}
.meter i {{ flex: 1; height: 6px; border-radius: 3px; background: #dbe7f8; }}
.meter i.on {{ background: var(--accent); }}
h2 {{ font-size: 16px; margin: 0 0 12px; }}
.card {{ display: grid; grid-template-columns: 210px 1fr 130px 190px; gap: 18px; align-items: center;
  background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; margin-bottom: 10px; }}
.who {{ display: flex; gap: 12px; align-items: center; }}
.who small, .what small {{ display: block; color: var(--ink2); font-size: 13px; }}
.avatar {{ width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: 13px; color: #fff; }}
.a0 {{ background: #2a78d6; }} .a1 {{ background: #0f8a7e; }} .a2 {{ background: #7a5af5; }} .a3 {{ background: #d1673a; }} .a4 {{ background: #3d4b66; }}
.chips {{ display: flex; gap: 6px; margin: 6px 0 4px; }}
.chip {{ font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; }}
.chip.receipt {{ background: var(--goodbg); color: var(--good); }}
.chip.receipt-missing {{ background: var(--badbg); color: var(--bad); }}
.chip.limit {{ background: var(--warnbg); color: var(--warn); }}
.what .why {{ color: var(--muted); }}
.amount {{ font-size: 20px; font-weight: 700; text-align: right; font-variant-numeric: tabular-nums; }}
.actions {{ display: flex; gap: 8px; justify-content: flex-end; }}
button {{ font: inherit; font-weight: 600; padding: 8px 16px; border-radius: 8px; border: 1px solid var(--line); background: #fff; cursor: pointer; }}
button.primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.handled {{ margin-top: 28px; background: var(--card); border: 1px solid var(--line); border-radius: 12px; overflow-x: auto; }}
.handled h2 {{ padding: 16px 18px 0; }}
table {{ width: 100%; min-width: 620px; border-collapse: collapse; font-size: 14px; }}
td {{ padding: 10px 18px; border-top: 1px solid var(--line); vertical-align: top; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
td small {{ display: block; color: var(--ink2); }}
.status {{ font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; }}
.status.agent {{ background: #eef2f7; color: #3d4b66; }}
.status.you {{ background: #e8f0fb; color: #1f5fae; }}
.empty {{ color: var(--muted); }}
footer {{ color: var(--muted); font-size: 12px; text-align: center; padding: 0 0 28px; }}
@media (max-width: 860px) {{ .card {{ grid-template-columns: 1fr; }} .amount {{ text-align: left; }}
  .tiles {{ grid-template-columns: 1fr; }} header {{ padding: 0 16px; }} nav {{ display: none; }} main {{ padding: 20px 16px; }}
  .actions {{ justify-content: stretch; }} .actions button {{ flex: 1; }} }}
</style></head>
<body>
<header><div class="logo"><span>A</span>Acme Corp</div>
  <nav><a>Cards</a><a class="on">Approvals</a><a>Reimbursements</a><a>Reports</a></nav>
  <div class="me"><span class="avatar a4">JB</span><div><b>Jordan Blake</b> · Finance approver</div></div></header>
<main>
  <h1>Approvals</h1>
  <p class="lead">Your AI expense agent processed {submitted} card expenses and invoices this morning. These need you.</p>
  <div class="tiles">
    <div class="tile"><small>Needs your approval</small><b>{waiting}</b><span>Largest first</span></div>
    <div class="tile"><small>Approved without you</small><b>{agent}</b><span>${agent_total} within policy</span></div>
    <div class="tile"><small>Your questions this hour</small><b>{asked} of {limit}</b><div class="meter">{meter}</div>
      <span>Small requests never interrupt you</span></div>
  </div>
  <h2>Needs your approval</h2>
  {cards}
  <section class="handled"><h2>Handled this morning</h2><table>{rows}</table></section>
</main>
<footer>Example app built on the Oversight library. People, company and merchants are made up.</footer>
</body></html>"""


def make_server(port: int = 8400, desk: Desk | None = None) -> ThreadingHTTPServer:
    desk = desk or Desk()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            body = desk.page().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())
            if self.path == "/decide" and form.get("i", [""])[0].isdigit():
                i = int(form["i"][0])
                if i < len(desk.items):
                    desk.decide(i, form.get("approved", [""])[0] == "yes")
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    server = make_server(int(sys.argv[1]) if len(sys.argv) > 1 else 8400)
    print(f"Card approvals running on http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()
