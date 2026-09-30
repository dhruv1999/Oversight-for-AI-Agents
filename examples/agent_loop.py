"""A Claude tool-use agent whose every tool call goes through the oversight gate.

The tools act on an in-memory, entirely synthetic company (fake tables, fake vendors).
Nothing real is touched.

    ANTHROPIC_API_KEY=... uv run --extra anthropic python examples/agent_loop.py
    ANTHROPIC_API_KEY=... uv run --extra anthropic python examples/agent_loop.py --task "..." --auto deny

Blocked or deferred calls come back to Claude as an error tool_result with the reason,
so the agent can adapt instead of silently failing.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oversight.allocator import Allocator  # noqa: E402
from oversight.attention import AttentionTracker  # noqa: E402
from oversight.gate import Outcome, OversightGate  # noqa: E402
from oversight.human import ConsoleHuman, HumanDecision, HumanReviewer  # noqa: E402
from oversight.log import DecisionLog  # noqa: E402
from oversight.policy import Policy  # noqa: E402
from oversight.registry import ToolRegistry  # noqa: E402
from oversight.safety_model import HeuristicSafetyModel  # noqa: E402

MODEL = "claude-opus-5-5"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read a file from the project.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "run_sql",
        "description": "Run a SQL statement against the company database.",
        "input_schema": {"type": "object", "properties": {"database": {"type": "string"}, "query": {"type": "string"}}, "required": ["database", "query"]},
    },
    {
        "name": "send_email",
        "description": "Send an email.",
        "input_schema": {
            "type": "object",
            "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "pay_invoice",
        "description": "Pay a vendor invoice (USD).",
        "input_schema": {
            "type": "object",
            "properties": {"vendor": {"type": "string"}, "amount": {"type": "number"}, "invoice_id": {"type": "string"}},
            "required": ["vendor", "amount", "invoice_id"],
        },
    },
]

DEFAULT_TASK = (
    "You are the ops agent for Example Corp (a fictional company; all data is synthetic). "
    "Invoice INV-2231 from Acme Paper Co for $420 is approved; pay it. Then count yesterday's orders "
    "in the app database and email the number to ana@example-corp.test."
)


class FakeCompany:
    """Synthetic tool implementations. Returns plausible strings, changes nothing."""

    def __call__(self, name: str, args: dict[str, Any]) -> str:
        if name == "read_file":
            return f"(synthetic contents of {args['path']})"
        if name == "run_sql":
            q = args["query"].strip().lower()
            return "count\n137" if q.startswith("select") else "OK (synthetic database, 0 real rows affected)"
        if name == "send_email":
            return f"sent to {args['to']} (synthetic)"
        if name == "pay_invoice":
            return f"paid ${args['amount']:,.2f} to {args['vendor']} for {args['invoice_id']} (synthetic)"
        return f"unknown tool {name}"


class AutoHuman:
    def __init__(self, approve: bool):
        self.approve = approve

    def review(self, action, now) -> HumanDecision:
        return HumanDecision(self.approve, f"auto-{'approved' if self.approve else 'denied'}")


def run_agent(
    client: Any,
    task: str,
    gate: OversightGate,
    registry: ToolRegistry,
    human: HumanReviewer,
    execute: Callable[[str, dict[str, Any]], str],
    clock: Callable[[], float] = time.time,
    max_turns: int = 12,
    model: str = MODEL,
    printer: Callable[[str], None] = print,
) -> str:
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    calls = 0
    for _ in range(max_turns):
        response = client.messages.create(model=model, max_tokens=16000, tools=TOOLS, messages=messages)
        if response.stop_reason in ("end_turn", "refusal", "max_tokens"):
            return "".join(b.text for b in response.content if b.type == "text")
        messages.append({"role": "assistant", "content": response.content})  # keep thinking + tool_use blocks
        if response.stop_reason == "pause_turn":
            continue
        results = []
        for block in (b for b in response.content if b.type == "tool_use"):
            calls += 1
            now = clock()
            action = registry.to_action(f"{block.id}", block.name, dict(block.input), f"agent call #{calls}: {block.name}")
            res = gate.review(action, now)
            if res.outcome == Outcome.ASK_HUMAN:
                h = human.review(action, now)
                gate.record_human(action, h.approved, now, h.rationale)
                allowed, why = h.approved, f"human {'approved' if h.approved else 'rejected'}: {h.rationale}"
            elif res.outcome == Outcome.EXECUTE:
                allowed, why = True, res.reason
            else:
                allowed, why = False, res.reason
            printer(f"[oversight] {block.name} tier={res.decision.tier} route={res.decision.route.value} -> {'RUN' if allowed else 'STOP'} ({why})")
            if allowed:
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": execute(block.name, dict(block.input))})
            else:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "is_error": True,
                        "content": f"Not executed. Oversight decision: {why}. Do not retry this exact call; explain or choose a safer alternative.",
                    }
                )
        messages.append({"role": "user", "content": results})  # all results in one message
    return "(stopped: max turns reached)"


def build_gate(log_path: Path) -> tuple[OversightGate, ToolRegistry]:
    policy = Policy.load(ROOT / "policies" / "default.yaml")
    registry = ToolRegistry.load(ROOT / "policies" / "tools.yaml", policy)
    gate = OversightGate.from_policy(policy, Allocator(policy, AttentionTracker.from_config(policy.attention)), HeuristicSafetyModel(), DecisionLog(log_path))
    return gate, registry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--auto", choices=["approve", "deny"], help="answer human prompts automatically")
    args = ap.parse_args()
    import anthropic

    gate, registry = build_gate(ROOT / "logs" / "agent_loop.jsonl")
    human = AutoHuman(args.auto == "approve") if args.auto else ConsoleHuman()
    print(run_agent(anthropic.Anthropic(), args.task, gate, registry, human, FakeCompany()))
    print(f"\naudit log: {ROOT / 'logs' / 'agent_loop.jsonl'}")


if __name__ == "__main__":
    main()
