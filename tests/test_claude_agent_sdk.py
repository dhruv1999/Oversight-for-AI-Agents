"""Claude Agent SDK messages, built by hand: running the SDK for real needs the Claude Code CLI and a key."""

import pytest

pytest.importorskip("claude_agent_sdk")

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage  # noqa: E402

from agent_ratchet import Case, Suite, expect  # noqa: E402


def messages(is_error=False):
    return [
        AssistantMessage(content=[TextBlock("Let me check."), ToolUseBlock("t1", "lookup_order", {"order_id": "42"})], model="claude"),
        UserMessage(content=[ToolResultBlock("t1", "order 42: shipped", False)]),
        AssistantMessage(content=[ToolUseBlock("t2", "issue_refund", {"order_id": "42"})], model="claude"),
        UserMessage(content=[ToolResultBlock("t2", "refunds are disabled", True)]),
        AssistantMessage(content=[TextBlock("Order 42 has shipped.")], model="claude"),
        ResultMessage(
            subtype="error_during_execution" if is_error else "success",
            duration_ms=1200,
            duration_api_ms=1000,
            is_error=is_error,
            num_turns=3,
            session_id="s",
            total_cost_usd=0.012,
            usage={"input_tokens": 300, "output_tokens": 60},
            result="Order 42 has shipped.",
        ),
    ]


def test_messages_become_a_trajectory():
    async def agent(message):
        return messages()

    result = Suite(agent, [Case("status", "x", [expect.calls_in_order("lookup_order", "issue_refund"), expect.output_contains("shipped")])], repeats=1).run()
    assert result.ok
    t = result.cases[0].runs[0].trajectory
    assert t.source == "claude-agent-sdk" and t.tool_calls[0].result == "order 42: shipped"
    assert t.tool_calls[1].error == "refunds are disabled"
    assert (t.cost_usd, t.input_tokens, t.output_tokens, t.llm_calls) == (0.012, 300, 60, 3)


def test_error_result_fails_the_run():
    c = Suite(lambda m: messages(is_error=True), [Case("a", "x")], repeats=1).run().cases[0]
    assert c.passes == 0 and "error_during_execution" in c.example_failure("run crashed")
