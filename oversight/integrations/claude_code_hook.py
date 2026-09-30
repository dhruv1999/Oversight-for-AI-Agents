"""Claude Code PreToolUse hook: put adaptive oversight in front of Claude Code's own tool calls.

The "human" channel is Claude Code's permission prompt. The attention budget limits how
often the hook asks; the safety model covers what the budget cannot.

    .claude/settings.json
    {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": "uv run --project /path/to/adaptive-oversight python -m oversight.integrations.claude_code_hook", "timeout": 30}
    ]}]}}

Modes (env OVERSIGHT_MODE):
  advisory (default)  never auto-approves: routine calls fall through to Claude Code's normal
                      permission flow ("defer"); the hook only adds "deny" and "ask".
  enforce             routine calls and safety-model approvals are allowed without a prompt.

Fails safe: any internal error produces "ask", never "allow".
State (attention budget, audit log, deferred queue) lives in $OVERSIGHT_STATE_DIR (default .oversight/).
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..allocator import Allocator
from ..attention import AttentionTracker
from ..gate import Outcome, OversightGate
from ..log import DecisionLog
from ..policies import DEFAULT_POLICY, DEFAULT_TOOLS
from ..policy import Policy
from ..redact import redact
from ..registry import ToolRegistry
from ..safety_model import HeuristicSafetyModel, SafetyModel


def to_registry_call(tool_name: str, tool_input: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    """Map a Claude Code tool call onto the registry's tool vocabulary."""
    ti = tool_input or {}
    if tool_name in ("Read", "NotebookRead"):
        return "read_file", {"path": ti.get("file_path", "")}, f"Read {ti.get('file_path', '')}"
    if tool_name in ("Glob", "Grep", "LS"):
        return "search_code", {"query": ti.get("pattern", ""), "path": ti.get("path", "")}, f"Search for {ti.get('pattern', '')}"
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        content = ti.get("content") or ti.get("new_string") or json.dumps(ti.get("edits", ""))[:4000]
        return "write_file", {"path": ti.get("file_path") or ti.get("notebook_path", ""), "content": content}, f"{tool_name} {ti.get('file_path', '')}"
    if tool_name == "Bash":
        return "run_shell", {"command": ti.get("command", "")}, ti.get("description") or "Run a shell command"
    if tool_name in ("WebFetch", "WebSearch"):
        return "http_get", {"url": ti.get("url") or f"search:{ti.get('query', '')}"}, f"{tool_name}"
    return tool_name, ti, f"Call {tool_name}"  # unknown -> registry's conservative defaults


def _load_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"interrupt_times": []}


def _reviewer(state_dir: Path) -> SafetyModel:
    if os.environ.get("OVERSIGHT_REVIEWER") != "anthropic":
        return HeuristicSafetyModel()
    from ..adapters.anthropic_client import AnthropicClient
    from ..cache import ResponseCache
    from ..safety_model import VERDICT_SCHEMA, LLMSafetyModel
    from ..spend import SpendTracker

    return LLMSafetyModel(
        AnthropicClient(model=os.environ.get("OVERSIGHT_MODEL", "claude-opus-5-5"), json_schema=VERDICT_SCHEMA),
        cache=ResponseCache(state_dir / "review_cache.jsonl"),
        spend=SpendTracker.from_env(default=1.0, ledger_path=state_dir / "spend_ledger.jsonl"),
    )


@contextmanager
def _locked(state_dir: Path) -> Iterator[None]:
    """Claude Code can run tool calls in parallel, so each hook process holds an exclusive
    lock while it reads, decides and writes. Otherwise two hooks could both spend the last
    interrupt in the budget."""
    with (state_dir / ".lock").open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def handle(payload: dict[str, Any], state_dir: Path, now: float, mode: str = "advisory", safety_model: SafetyModel | None = None) -> dict[str, Any]:
    policy = Policy.load(os.environ.get("OVERSIGHT_POLICY", DEFAULT_POLICY))
    registry = ToolRegistry.load(os.environ.get("OVERSIGHT_TOOLS", DEFAULT_TOOLS), policy)
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "state.json"
    tool, params, desc = to_registry_call(payload.get("tool_name", ""), payload.get("tool_input", {}))

    with _locked(state_dir):
        state = _load_state(state_path)
        att = AttentionTracker.from_config(policy.attention)
        att.restore(t for t in state["interrupt_times"] if now - t < att.window_seconds)
        gate = OversightGate.from_policy(policy, Allocator(policy, att), safety_model or _reviewer(state_dir), DecisionLog(state_dir / "decisions.jsonl"))
        action = registry.to_action(payload.get("tool_use_id") or f"cc-{now}", tool, params, desc)
        res = gate.review(action, now)
        state["interrupt_times"] = att.interrupt_times()
        _write_atomic(state_path, json.dumps(state))
        if res.outcome == Outcome.DEFER:
            with (state_dir / "deferred.jsonl").open("a") as f:
                f.write(json.dumps({"timestamp": now, "tool_name": payload.get("tool_name"), "tool_input": redact(payload.get("tool_input", {}))}) + "\n")

    tier = res.decision.tier
    if res.outcome == Outcome.EXECUTE:
        decision = "allow" if mode == "enforce" else "defer"
        reason = f"oversight: {tier} risk; {res.reason}"
    elif res.outcome == Outcome.BLOCK:
        decision, reason = "deny", f"oversight blocked ({tier} risk): {res.reason}"
    elif res.outcome == Outcome.ASK_HUMAN:
        decision, reason = "ask", f"oversight wants a human ({tier} risk): {res.decision.reasons[-1]}"
    else:  # DEFER: no attention left for a non-critical action -> parked above, tell Claude why
        decision, reason = "deny", f"oversight deferred ({tier} risk): human attention budget used up; queued in {state_dir}/deferred.jsonl for later review"
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        state_dir = Path(os.environ.get("OVERSIGHT_STATE_DIR", Path(payload.get("cwd", ".")) / ".oversight"))
        out = handle(payload, state_dir, time.time(), os.environ.get("OVERSIGHT_MODE", "advisory"))
    except Exception as e:  # never fail open
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": f"oversight hook error ({type(e).__name__}): {e}",
            }
        }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
