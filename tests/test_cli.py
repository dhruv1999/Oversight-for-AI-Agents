import json
import os
import textwrap

from agent_regress.cli import main

SUITE = """
import os
from agent_regress import Case, Suite, expect, tool

@tool
def escalate(order_id: str) -> str:
    return "ok"

def agent(message):
    if os.environ.get("BROKEN") != "1":
        escalate("77")
    return "passed to a manager"

suite = Suite(agent, [Case("large refund", "refund 77", [expect.calls("escalate")]), Case("hello", "hi")], repeats=2, name="My Agent/v1")
"""


def write_suite(tmp_path):
    path = tmp_path / "suite.py"
    path.write_text(textwrap.dedent(SUITE), encoding="utf-8")
    return str(path)


def test_baseline_then_regression(tmp_path, monkeypatch, capsys):
    suite, out = write_suite(tmp_path), str(tmp_path / "results")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("BROKEN", raising=False)

    assert main(["run", suite, "--dir", out]) == 0
    assert "no baseline yet" in capsys.readouterr().out
    assert main(["run", suite, "--dir", out, "--save-baseline"]) == 0
    assert os.path.exists(f"{out}/My_Agent_v1.baseline.json")

    monkeypatch.setenv("BROKEN", "1")
    md = tmp_path / "report.md"
    assert main(["run", suite, "--dir", out, "--markdown", str(md)]) == 1
    printed = capsys.readouterr().out
    assert "REGRESSED" in printed and "never called escalate" in printed
    assert "regressed" in md.read_text(encoding="utf-8") and "regressed" in summary.read_text(encoding="utf-8")

    assert main(["run", suite, "--dir", out, "--fail-on", "never"]) == 0
    assert main(["run", suite, "--dir", out, "--case", "hello"]) == 0
    assert main(["compare", f"{out}/My_Agent_v1.latest.json", f"{out}/My_Agent_v1.baseline.json"]) == 0  # latest only ran "hello"


def test_fail_on_failure_without_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("BROKEN", "1")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    suite = write_suite(tmp_path)
    assert main(["run", suite, "--dir", str(tmp_path)]) == 0
    assert main(["run", suite, "--dir", str(tmp_path), "--fail-on", "failure"]) == 1


def test_usage_errors(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    suite = write_suite(tmp_path)
    assert main(["run", suite, "--dir", str(tmp_path), "--case", "nope"]) == 2
    assert main(["compare", str(tmp_path / "a.json"), str(tmp_path / "b.json")]) == 2


def test_import_otel(tmp_path, capsys):
    spans = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "execute_tool lookup_order",
                                "startTimeUnixNano": "1",
                                "attributes": [
                                    {"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
                                    {"key": "gen_ai.tool.name", "value": {"stringValue": "lookup_order"}},
                                    {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": '{"order_id": "42"}'}},
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    path = tmp_path / "spans.json"
    path.write_text(json.dumps(spans), encoding="utf-8")
    assert main(["import", "otel", str(path), "--name", "order lookup"]) == 0
    out = capsys.readouterr().out
    assert "Case('order lookup'" in out and "expect.calls('lookup_order')" in out
