"""Command line entry point.

    oversight check pay_invoice '{"vendor": "Acme", "amount": 420}'
    oversight serve --port 8321 --state .oversight
    oversight hook                      # Claude Code PreToolUse hook (reads the event on stdin)
    oversight mcp -- <server command>   # put oversight in front of any MCP server
    oversight --checker gemini --model <model> --price 0.75,3.75 serve   # an AI model as the checker

`check` exits 0 when the action may run, 2 when blocked, 3 when a person must decide, 4 when it
must wait for a person, so shell scripts and CI jobs can branch on it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .adapters import PROVIDERS
from .gate import Outcome
from .guard import Oversight
from .policies import DEFAULT_POLICY, DEFAULT_TOOLS
from .safety_model import build_checker

EXIT = {Outcome.EXECUTE: 0, Outcome.BLOCK: 2, Outcome.ASK_HUMAN: 3, Outcome.DEFER: 4}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="oversight", description="Decide who must approve an AI agent's action.")
    ap.add_argument("--policy", default=str(DEFAULT_POLICY))
    ap.add_argument("--tools", default=str(DEFAULT_TOOLS))
    ap.add_argument("--state", default=None, help="directory for a shared interrupt budget (default: this process only)")
    ap.add_argument(
        "--checker",
        choices=["rules", *PROVIDERS],
        default=os.environ.get("OVERSIGHT_REVIEWER") or "rules",
        help="who reviews medium risk actions: the free rules checker (default) or an AI model",
    )
    ap.add_argument("--model", default=os.environ.get("OVERSIGHT_MODEL"), help="model for an AI checker (on Azure, the deployment name)")
    ap.add_argument("--price", default=os.environ.get("OVERSIGHT_PRICE"), help="model price as 'input,output' USD per million tokens")
    ap.add_argument("--max-spend", type=float, default=float(os.environ.get("MAX_SPEND_USD", "1.0")), help="stop spending at this many USD")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check one action and explain the decision")
    c.add_argument("tool")
    c.add_argument("params", nargs="?", default="{}", help="JSON object")
    c.add_argument("--json", action="store_true", help="print the decision as JSON")
    s = sub.add_parser("serve", help="run the HTTP service")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8321)
    sub.add_parser("hook", help="run as a Claude Code PreToolUse hook")
    m = sub.add_parser("mcp", help="run in front of an MCP server: oversight mcp -- <server command>")
    m.add_argument("server", nargs=argparse.REMAINDER, help="the MCP server command and its arguments")
    args = ap.parse_args(argv)

    if args.cmd == "hook":
        from .integrations.claude_code_hook import main as hook_main

        hook_main()
        return 0

    try:
        checker = build_checker(args.checker, args.model, args.price, Path(args.state or ".oversight"), args.max_spend)
    except Exception as e:  # missing price, model, SDK or key: say what is wrong instead of a traceback
        print(f"could not set up the {args.checker} checker: {e}", file=sys.stderr)
        return 64
    guard = Oversight(policy=args.policy, tools=args.tools, state=Path(args.state) if args.state else None, safety_model=checker)
    if args.cmd == "mcp":
        command = [a for a in args.server if a != "--"]
        if not command:
            print("usage: oversight mcp -- <server command> [args...]", file=sys.stderr)
            return 64
        import anyio

        from .integrations.mcp_proxy import run_proxy

        anyio.run(run_proxy, command[0], command[1:], guard)
        return 0
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
    url = f"http://{args.host}:{server.server_port}"
    print(f"oversight listening on {url}  (rules {guard.rules_id})", flush=True)
    print(f"review page: {url}/", flush=True)
    if not server.token and not server.loopback:
        print("warning: reachable from other machines without a token; set OVERSIGHT_TOKEN", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
