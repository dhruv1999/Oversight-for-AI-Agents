"""Check production traces in Langfuse with the same rules as your test suite, and save the
results as Langfuse scores. Needs LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST.

    python examples/frameworks/langfuse_production.py <trace-id>

To turn a trace into a new test case instead:   agent-regress import langfuse <trace-id>
"""

import sys

from agent_regress import expect
from agent_regress.integrations.langfuse import evaluate_trace

RULES = [expect.never_calls("delete_account"), expect.no_tool_errors(), expect.max_tool_calls(10)]

for result in evaluate_trace(sys.argv[1], RULES):
    print("pass" if result.passed else "FAIL", result.name, result.detail)
