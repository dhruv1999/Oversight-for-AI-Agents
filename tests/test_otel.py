import json

import pytest

from agent_ratchet.integrations.otel import from_spans, load_otlp_json


def attr(key, value):
    kind = "intValue" if isinstance(value, int) else "stringValue"
    return {"key": key, "value": {kind: str(value) if kind == "intValue" else value}}


def span(name, start, error=False, **attrs):
    s = {"name": name, "startTimeUnixNano": str(start), "attributes": [attr(k.replace("__", "."), v) for k, v in attrs.items()]}
    if error:
        s["status"] = {"code": 2, "message": "timeout"}
    return s


SPANS = [
    span("invoke_agent support", 1, gen_ai__operation__name="invoke_agent"),
    span(
        "chat",
        2,
        gen_ai__operation__name="chat",
        gen_ai__usage__input_tokens=100,
        gen_ai__usage__output_tokens=20,
        gen_ai__input__messages=json.dumps([{"role": "user", "parts": [{"type": "text", "content": "Where is order 42?"}]}]),
    ),
    span(
        "execute_tool lookup_order",
        3,
        gen_ai__operation__name="execute_tool",
        gen_ai__tool__name="lookup_order",
        gen_ai__tool__call__arguments='{"order_id": "42"}',
        gen_ai__tool__call__result="shipped",
    ),
    span("execute_tool notify", 4, error=True, gen_ai__operation__name="execute_tool", gen_ai__tool__name="notify"),
    span(
        "chat",
        5,
        gen_ai__operation__name="chat",
        gen_ai__usage__input_tokens=150,
        gen_ai__usage__output_tokens=10,
        gen_ai__output__messages=json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": "It has shipped."}]}]),
    ),
]


def test_otlp_json_file(tmp_path):
    doc = {"resourceSpans": [{"scopeSpans": [{"spans": SPANS}]}]}
    pretty, lines = tmp_path / "pretty.json", tmp_path / "lines.jsonl"
    pretty.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    lines.write_text(json.dumps(doc) + "\n" + json.dumps(doc) + "\n", encoding="utf-8")
    assert len(load_otlp_json(pretty)) == 5 and len(load_otlp_json(lines)) == 10
    t = from_spans(list(reversed(load_otlp_json(pretty))))
    assert t.tools == ["lookup_order", "notify"] and t.tool_calls[0].args == {"order_id": "42"} and t.tool_calls[0].result == "shipped"
    assert t.tool_calls[1].error == "timeout"
    assert (t.input, t.output, t.llm_calls, t.input_tokens, t.output_tokens) == ("Where is order 42?", "It has shipped.", 2, 250, 30)


def test_spans_from_the_opentelemetry_sdk(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("invoke_agent", attributes={"gen_ai.operation.name": "invoke_agent", "gen_ai.usage.input_tokens": 7}):
        tool_attrs = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "search", "gen_ai.tool.call.arguments": '{"q": "x"}'}
        with tracer.start_as_current_span("execute_tool search", attributes=tool_attrs):
            pass
    t = from_spans(exporter.get_finished_spans())
    assert t.tools == ["search"] and t.tool_calls[0].args == {"q": "x"} and t.input_tokens == 7
