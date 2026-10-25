import json
import textwrap

from agent_ratchet.cli import main

SUITE = """
from __future__ import annotations

import os
from dataclasses import dataclass

from agent_ratchet import Case, Suite, expect, tool


@dataclass
class Order:  # a dataclass in a suite file used to crash the loader
    id: str


@tool
def escalate(order_id: str) -> str:
    return "ok"


def agent(message):
    if os.environ.get("BROKEN") != "1":
        escalate(Order("77").id)
    return "passed to a manager"


suite = Suite(
    agent,
    [Case("large refund", "refund 77", [expect.calls("escalate")]), Case("hello", "hi")],
    repeats=2,
    max_repeats=4,
    name="My Agent/v1",
)
"""


def write(tmp_path, body=SUITE, name="suite.py"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


def test_baseline_then_regression(tmp_path, monkeypatch, capsys):
    suite, out = write(tmp_path), tmp_path / "results"
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("BROKEN", raising=False)

    assert main(["run", suite, "--dir", str(out)]) == 0
    assert "no baseline yet" in capsys.readouterr().out
    assert main(["run", suite, "--dir", str(out), "--save-baseline"]) == 0
    baseline = json.loads((out / "My_Agent_v1.baseline.json").read_text(encoding="utf-8"))
    assert [c["n"] for c in baseline["cases"]] == [4, 4]  # baselines use max_repeats
    assert "refund 77" not in json.dumps(baseline) and "python" in baseline["meta"]
    assert (out / ".gitignore").read_text(encoding="utf-8") == "*.latest.json\n"

    monkeypatch.setenv("BROKEN", "1")
    md = tmp_path / "report.md"
    assert main(["run", suite, "--dir", str(out), "--markdown", str(md)]) == 1
    captured = capsys.readouterr()
    assert "REGRESSED" in captured.out and "never called escalate" in captured.out
    assert "large refund: 0/4 passed" in captured.err  # rerun to max_repeats before deciding
    assert "regressed" in md.read_text(encoding="utf-8") and "regressed" in summary.read_text(encoding="utf-8")
    assert main(["run", suite, "--dir", str(out), "--fail-on", "never"]) == 0


def test_partial_runs_keep_the_rest_of_the_baseline(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("BROKEN", raising=False)
    suite, out = write(tmp_path), str(tmp_path)
    assert main(["run", suite, "--dir", out, "--save-baseline"]) == 0
    assert main(["run", suite, "--dir", out, "--save-baseline", "--case", "hello", "--repeats", "1"]) == 0
    baseline = json.loads((tmp_path / "My_Agent_v1.baseline.json").read_text(encoding="utf-8"))
    assert [(c["name"], c["n"]) for c in baseline["cases"]] == [("large refund", 4), ("hello", 1)]
    capsys.readouterr()
    assert main(["run", suite, "--dir", out, "--case", "hello"]) == 0
    assert "removed" not in capsys.readouterr().out


def test_must_pass_fails_without_a_baseline(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setenv("BROKEN", "1")
    plain = write(tmp_path)
    strict = write(tmp_path, SUITE.replace('[expect.calls("escalate")])', '[expect.calls("escalate")], must_pass=True)'), "strict.py")
    assert main(["run", plain, "--dir", str(tmp_path)]) == 0
    assert main(["run", plain, "--dir", str(tmp_path), "--fail-on", "failure"]) == 1
    assert main(["run", strict, "--dir", str(tmp_path / "s")]) == 1


def test_usage_errors_exit_with_2(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    suite = write(tmp_path)
    assert main(["run", suite, "--dir", str(tmp_path), "--case", "nope"]) == 2
    assert main(["compare", str(tmp_path / "a.json"), str(tmp_path / "b.json")]) == 2
    assert main(["run", str(tmp_path / "missing.py")]) == 2
    assert main(["run", write(tmp_path, "import not_a_real_module\n", "broken.py")]) == 2
    assert main(["run", write(tmp_path, "x = 1\n", "empty.py")]) == 2
    twins = SUITE + "\nother = Suite(agent, [Case('a', 'b')], name='My Agent/v1')\n"
    assert main(["run", write(tmp_path, twins, "twins.py"), "--dir", str(tmp_path)]) == 2
    assert "not_a_real_module" in capsys.readouterr().err


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
