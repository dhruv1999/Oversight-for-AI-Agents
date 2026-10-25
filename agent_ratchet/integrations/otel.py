"""OpenTelemetry GenAI spans: the vendor neutral format many tools can export (including
OpenLLMetry, Logfire and frameworks that follow the OpenTelemetry GenAI semantic conventions).

    from agent_ratchet.integrations.otel import from_spans, load_otlp_json
    traj = from_spans(load_otlp_json("trace.json"))     # spans exported as OTLP JSON
    traj = from_spans(memory_exporter.get_finished_spans())   # or spans captured in a test

Reads tool spans (gen_ai.operation.name = "execute_tool") and model spans (chat and similar).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..trajectory import ToolCall, Trajectory
from ._util import as_args

MODEL_OPERATIONS = {"chat", "text_completion", "generate_content"}


def _value(v: dict[str, Any]) -> Any:
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in v:
            return int(v[key]) if key == "intValue" else v[key]
    if "arrayValue" in v:
        return [_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def _normalise(span: Any) -> dict[str, Any]:
    """Spans as plain dicts: name, start (ns), attributes, error."""
    if isinstance(span, dict):
        attrs = {a["key"]: _value(a["value"]) for a in span.get("attributes", [])}
        status = span.get("status", {}) or {}
        error = status.get("code") in (2, "STATUS_CODE_ERROR", "ERROR")
        return {"name": span.get("name", ""), "start": int(span.get("startTimeUnixNano", 0)), "attrs": attrs, "error": error, "message": status.get("message")}
    status = getattr(span, "status", None)
    code = getattr(getattr(status, "status_code", None), "name", "")
    return {
        "name": span.name,
        "start": span.start_time or 0,
        "attrs": dict(span.attributes or {}),
        "error": code == "ERROR",
        "message": getattr(status, "description", None),
    }


def _text_from_messages(raw: Any) -> str | None:
    """Text of the last assistant message in gen_ai.output.messages (a JSON string)."""
    try:
        messages = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return raw if isinstance(raw, str) else None
    if not isinstance(messages, list):
        return None
    for m in reversed(messages):
        parts = m.get("parts", []) if isinstance(m, dict) else []
        text = "".join(str(p.get("content", "")) for p in parts if isinstance(p, dict) and p.get("type") == "text")
        if text:
            return text
    return None


def from_spans(spans: list[Any]) -> Trajectory:
    rows = sorted((_normalise(s) for s in spans), key=lambda r: r["start"])
    traj = Trajectory(source="otel")
    model_rows = [r for r in rows if r["attrs"].get("gen_ai.operation.name") in MODEL_OPERATIONS]
    usage_rows = model_rows or [r for r in rows if r["attrs"].get("gen_ai.operation.name") == "invoke_agent"]
    for r in rows:
        a = r["attrs"]
        if a.get("gen_ai.operation.name") == "execute_tool" or ("gen_ai.tool.name" in a and a.get("gen_ai.operation.name") is None):
            call = ToolCall(
                a.get("gen_ai.tool.name") or r["name"],
                as_args(a.get("gen_ai.tool.call.arguments")),
                result=a.get("gen_ai.tool.call.result"),
                id=a.get("gen_ai.tool.call.id"),
            )
            if r["error"]:
                call.error = r["message"] or a.get("error.type") or "tool failed"
            traj.tool_calls.append(call)
    for r in usage_rows:
        traj.input_tokens += int(r["attrs"].get("gen_ai.usage.input_tokens", 0) or 0)
        traj.output_tokens += int(r["attrs"].get("gen_ai.usage.output_tokens", 0) or 0)
    traj.llm_calls = len(model_rows)
    for r in reversed(model_rows + [x for x in rows if x["attrs"].get("gen_ai.operation.name") == "invoke_agent"]):
        text = _text_from_messages(r["attrs"].get("gen_ai.output.messages"))
        if text:
            traj.output = text
            break
    for r in rows:
        text = _text_from_messages(r["attrs"].get("gen_ai.input.messages"))
        if text:
            traj.input = text
            break
    if rows and any(r["error"] for r in rows if r["attrs"].get("gen_ai.operation.name") == "invoke_agent"):
        traj.error = "agent span ended with an error"
    return traj


def load_otlp_json(path: str | Path) -> list[dict[str, Any]]:
    """Spans from an OTLP JSON export (one document, or one document per line)."""
    text = Path(path).read_text(encoding="utf-8").strip()
    try:
        docs = [json.loads(text)]
    except ValueError:
        docs = [json.loads(line) for line in text.splitlines() if line.strip()]
    spans: list[dict[str, Any]] = []
    for doc in docs:
        for d in doc if isinstance(doc, list) else [doc]:
            for rs in d.get("resourceSpans", []):
                for ss in rs.get("scopeSpans", []):
                    spans.extend(ss.get("spans", []))
    return spans
