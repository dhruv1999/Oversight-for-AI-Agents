"""Command line entry point.

    oversight check pay_invoice '{"vendor": "Acme", "amount": 420}'
    oversight serve --port 8321 --state .oversight
    oversight hook                      # Claude Code PreToolUse hook (reads the event on stdin)

`check` exits 0 when the action may run, 2 when blocked, 3 when a person must decide, 4 when it
must wait for a person, so shell scripts and CI jobs can branch on it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gate import Outcome
from .guard import Oversight
from .policies import DEFAULT_POLICY, DEFAULT_TOOLS

EXIT = {Outcome.EXECUTE: 0, Outcome.BLOCK: 2, Outcome.ASK_HUMAN: 3, Outcome.DEFER: 4}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="oversight", description="Decide who must approve an AI agent's action.")
    ap.add_argument("--policy", default=str(DEFAULT_POLICY))
    ap.add_argument("--tools", default=str(DEFAULT_TOOLS))
    ap.add_argument("--state", default=None, help="directory for a shared interrupt budget (default: this process only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check one action and explain the decision")
    c.add_argument("tool")
    c.add_argument("params", nargs="?", default="{}", help="JSON object")
    c.add_argument("--json", action="store_true", help="print the decision as JSON")
    s = sub.add_parser("serve", help="run the HTTP service")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8321)
    sub.add_parser("hook", help="run as a Claude Code PreToolUse hook")
    args = ap.parse_args(argv)

    if args.cmd == "hook":
        from .integrations.claude_code_hook import main as hook_main

        hook_main()
        return 0

    guard = Oversight(policy=args.policy, tools=args.tools, state=Path(args.state) if args.state else None)
    if args.cmd == "check":
        try:
            params = json.loads(args.params)
            if not isinstance(params, dict):
                raise ValueError
        except ValueError:
            print("params must be a JSON object", file=sys.stderr)
            return 64
        check = guard.check(args.tool, params)
        if args.json:
            print(json.dumps({"outcome": check.outcome.value, "risk": check.risk, "reason": check.reason, "reasons": list(check.result.decision.reasons)}))
        else:
            print(check.explain())
        return EXIT[check.outcome]

    from .server import serve

    server = serve(args.host, args.port, guard)
    print(f"oversight listening on http://{args.host}:{server.server_port}  (rules {guard.rules_id})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
