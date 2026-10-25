import re

import pytest
from conftest import traj

from agent_ratchet import ToolCall, expect


def test_calls_with_exact_regex_and_callable_args():
    t = traj(ToolCall("lookup", {"order_id": "42", "amount": 900}))
    assert expect.calls("lookup")(t).passed
    assert expect.calls("lookup", order_id="42")(t).passed
    assert expect.calls("lookup", order_id=re.compile(r"^\d+$"))(t).passed
    assert expect.calls("lookup", amount=lambda a: a > 500)(t).passed
    r = expect.calls("lookup", order_id="7")(t)
    assert not r.passed and "called lookup with" in r.detail
    r = expect.calls("refund")(t)
    assert not r.passed and "never called refund" in r.detail


def test_type_matchers_and_long_details():
    t = traj(ToolCall("refund", {"amount": 40, "note": "x" * 1000}))
    assert expect.calls("refund", amount=int)(t).passed
    assert not expect.calls("refund", amount=str)(t).passed
    assert expect.calls("refund", amount=int).name == "calls refund(amount=any int)"
    assert len(expect.calls("refund", amount=7)(t).detail) <= 300


def test_rules_need_a_tool_name():
    for rule in (expect.never_calls, expect.only_calls, expect.calls_in_order):
        with pytest.raises(ValueError):
            rule()


def test_calls_counts():
    t = traj("search", "search", "answer")
    assert expect.calls("search", times=2)(t).passed
    assert not expect.calls("search", times=1)(t).passed
    assert not expect.calls("search", at_least=3)(t).passed


def test_never_only_and_order():
    t = traj("lookup", "log", "refund")
    assert not expect.never_calls("refund", "delete")(t).passed
    assert expect.never_calls("delete")(t).passed
    assert expect.only_calls("lookup", "log", "refund")(t).passed
    r = expect.only_calls("lookup")(t)
    assert not r.passed and "log" in r.detail
    assert expect.calls_in_order("lookup", "refund")(t).passed
    assert not expect.calls_in_order("refund", "lookup")(t).passed


def test_tool_errors():
    assert expect.no_tool_errors()(traj("a")).passed
    r = expect.no_tool_errors()(traj(ToolCall("a", error="ValueError: no")))
    assert not r.passed and "ValueError" in r.detail


def test_output_checks():
    t = traj(output="Refunds over $500 need a Manager.")
    assert expect.output_contains("manager", "$500")(t).passed
    assert not expect.output_contains("manager", case_sensitive=True)(t).passed
    assert expect.output_not_contains("refunded")(t).passed
    assert not expect.output_not_contains("refunds")(t).passed
    assert expect.output_matches(r"\$\d+")(t).passed
    assert not expect.output_contains("x")(traj(output=None)).passed


def test_budgets():
    t = traj("a", "b", llm_calls=3, input_tokens=100, output_tokens=50, latency_s=2.0)
    assert expect.max_tool_calls(2)(t).passed and not expect.max_tool_calls(1)(t).passed
    assert expect.max_llm_calls(3)(t).passed and not expect.max_llm_calls(2)(t).passed
    assert expect.max_tokens(150)(t).passed and not expect.max_tokens(149)(t).passed
    assert expect.max_latency(2)(t).passed
    r = expect.max_cost(1.0)(t)
    assert not r.passed and "not reported" in r.detail
    t.cost_usd = 0.5
    assert expect.max_cost(1.0)(t).passed


def test_custom_checks_and_broken_checks_fail():
    assert expect.check(lambda t: len(t.tools) == 1, name="one tool")(traj("a")).name == "one tool"
    r = expect.check(lambda t: (False, "nope"))(traj())
    assert not r.passed and r.detail == "nope"
    r = expect.check(lambda t: 1 / 0)(traj())
    assert not r.passed and "ZeroDivisionError" in r.detail
