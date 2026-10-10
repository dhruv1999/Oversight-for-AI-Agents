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

Checker (env OVERSIGHT_REVIEWER): rules (default), anthropic, openai, azure or gemini; see _reviewer.

Fails safe: any internal error produces "ask", never "allow".
State (attention budget, audit log, deferred queue) lives in $OVERSIGHT_STATE_DIR (default .oversight/).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from ..guard import Oversight
from ..policies import DEFAULT_POLICY, DEFAULT_TOOLS
from ..redact import redact
from ..safety_model import SafetyModel, build_checker


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


def _reviewer(state_dir: Path) -> SafetyModel:
    """OVERSIGHT_REVIEWER picks the checker: rules (default), anthropic, openai, azure or gemini.
    OVERSIGHT_MODEL names the model, OVERSIGHT_PRICE gives its price as 'input,output' per million
    tokens (needed for anything but Claude), and MAX_SPEND_USD caps spending."""
    return build_checker(
        os.environ.get("OVERSIGHT_REVIEWER"),
        os.environ.get("OVERSIGHT_MODEL"),
        os.environ.get("OVERSIGHT_PRICE"),
        state_dir,
        float(os.environ.get("MAX_SPEND_USD", "1.0")),
    )


def handle(payload: dict[str, Any], state_dir: Path, now: float, mode: str = "advisory", safety_model: SafetyModel | None = None) -> dict[str, Any]:
    """One hook call. Claude Code may run tool calls in parallel; the FileStore lock makes every
    hook process read, decide and write the shared interrupt budget one at a time."""
    guard = Oversight(
        policy=os.environ.get("OVERSIGHT_POLICY", DEFAULT_POLICY),
        tools=os.environ.get("OVERSIGHT_TOOLS", DEFAULT_TOOLS),
        safety_model=safety_model or _reviewer(state_dir),
        log_path=state_dir / "decisions.jsonl",
        clock=lambda: now,
        state=state_dir,
    )
    tool, params, desc = to_registry_call(payload.get("tool_name", ""), payload.get("tool_input", {}))
    check = guard.check(tool, params, desc, call_id=payload.get("tool_use_id") or f"cc-{now}")
    res = check.result
    if check.waiting:
        with (state_dir / "deferred.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": now, "tool_name": payload.get("tool_name"), "tool_input": redact(payload.get("tool_input", {}))}) + "\n")

    tier = check.risk
    if check.allowed:
        decision = "allow" if mode == "enforce" else "defer"
        reason = f"oversight: {tier} risk; {res.reason}"
    elif check.blocked:
        decision, reason = "deny", f"oversight blocked ({tier} risk): {res.reason}"
    elif check.needs_person:
        decision, reason = "ask", f"oversight wants a human ({tier} risk): {res.decision.reasons[-1]}"
    else:  # waiting: no attention left for a non critical action; parked above, tell Claude why
        decision = "deny"
        reason = f"oversight deferred ({tier} risk): human attention budget used up; queued in {state_dir}/deferred.jsonl for later review"
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
