"""Claude Agent SDK. Needs the Claude Code CLI and ANTHROPIC_API_KEY.
agent-regress run examples/frameworks/claude_agent_sdk_suite.py"""

from claude_agent_sdk import ClaudeAgentOptions

from agent_regress import Case, Suite, expect
from agent_regress.integrations.claude_agent_sdk import wrap

options = ClaudeAgentOptions(allowed_tools=["Read", "Grep", "Glob"], permission_mode="default", max_turns=8)

suite = Suite(
    agent=wrap(options),
    name="repo_helper",
    repeats=3,
    cases=[
        Case(
            "reads before answering",
            "Which license does this project use? Answer in one word.",
            [expect.calls("Read"), expect.never_calls("Bash", "Write", "Edit"), expect.output_contains("MIT"), expect.max_cost(0.20)],
        ),
    ],
)
