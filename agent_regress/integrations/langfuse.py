"""Langfuse: turn production traces into test cases, and check production traces with the same rules.

    agent-regress import langfuse <trace-id>          prints a Case to paste into your suite

    from agent_regress.integrations.langfuse import evaluate_trace
    evaluate_trace("<trace-id>", [expect.never_calls("issue_refund")])   # results also saved as Langfuse scores

Uses Langfuse's public REST API directly, so the Langfuse SDK is not required. Credentials come
from LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST (or LANGFUSE_BASE_URL).
"""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Any

from ..checks import Check, CheckResult
from ..trajectory import ToolCall, Trajectory, text_of
from ._util import as_args, get


def _dump(obj: Any) -> Any:
    return obj.model_dump() if hasattr(obj, "model_dump") else obj.dict() if hasattr(obj, "dict") else obj


def from_trace(trace: Any) -> Trajectory:
    """A Langfuse trace (the API's JSON, or an SDK object) as a Trajectory."""
    trace = _dump(trace)
    traj = Trajectory(input=get(trace, "input"), source="langfuse", meta={"trace_id": get(trace, "id")})
    output = get(trace, "output")
    traj.output = output if isinstance(output, str) or output is None else text_of(get(output, "content", "output", default=json.dumps(output)))
    observations = [_dump(o) for o in get(trace, "observations", default=[])]
    observations.sort(key=lambda o: str(get(o, "startTime", "start_time", default="")))
    cost = 0.0
    for o in observations:
        kind = str(get(o, "type", default="")).upper()
        if kind == "GENERATION":
            traj.llm_calls += 1
            usage = get(o, "usageDetails", "usage_details", "usage") or {}
            traj.input_tokens += int(get(usage, "input", "promptTokens", "prompt_tokens", "input_tokens", default=0))
            traj.output_tokens += int(get(usage, "output", "completionTokens", "completion_tokens", "output_tokens", default=0))
            cost += float(get(o, "calculatedTotalCost", "calculated_total_cost", default=0) or 0)
        elif kind == "TOOL":
            call = ToolCall(get(o, "name", default="tool"), as_args(get(o, "input")), result=get(o, "output"), id=get(o, "id"))
            if str(get(o, "level", default="")).upper() == "ERROR":
                call.error = get(o, "statusMessage", "status_message", default="tool failed")
            traj.tool_calls.append(call)
    total = get(trace, "totalCost", "total_cost")
    traj.cost_usd = float(total) if total is not None else (cost or None)
    latency = get(trace, "latency")
    traj.latency_s = float(latency) if latency is not None else None
    return traj


def _api(path: str, body: dict[str, Any] | None = None, host: str | None = None, public_key: str | None = None, secret_key: str | None = None) -> Any:
    host = (host or os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com").rstrip("/")
    pk = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY")
    sk = secret_key or os.environ.get("LANGFUSE_SECRET_KEY")
    if not pk or not sk:
        raise ValueError("set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY (or pass public_key and secret_key)")
    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    req = urllib.request.Request(
        f"{host}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def fetch_trace(trace_id: str, **auth: Any) -> dict[str, Any]:
    """Download one trace with all its observations."""
    return _api(f"/api/public/traces/{trace_id}", **auth)


def evaluate_trace(trace_id: str, checks: list[Check], push: bool = True, **auth: Any) -> list[CheckResult]:
    """Run checks on a production trace. With push=True each result is saved on the trace as a
    Langfuse score (1 passed, 0 failed) named after the check."""
    traj = from_trace(fetch_trace(trace_id, **auth))
    results = [c(traj) for c in checks]
    if push:
        for r in results:
            score = {"traceId": trace_id, "name": r.name, "value": 1 if r.passed else 0, "dataType": "BOOLEAN", "comment": r.detail or None}
            _api("/api/public/scores", score, **auth)
    return results
