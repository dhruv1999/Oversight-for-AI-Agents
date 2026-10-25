"""agent-ratchet: regression tests for AI agents. Your agent can get better; it cannot quietly get worse.

    from agent_ratchet import Case, Suite, expect

    suite = Suite(agent=my_agent, cases=[
        Case("refund needs an order number", "Refund my last order",
             expect=[expect.never_calls("issue_refund"), expect.output_contains("order number")]),
    ])

Save a baseline with `agent-ratchet run suite.py --save-baseline`. Later runs fail when a case
gets worse by more than chance explains, or when a must pass case fails.
"""

__version__ = "0.1.0"

from . import checks as expect  # noqa: E402
from . import judges  # noqa: E402
from .checks import Check, CheckResult  # noqa: E402
from .compare import Comparison, compare  # noqa: E402
from .recording import record_response, record_usage, recording, tool  # noqa: E402
from .snapshot import snapshot  # noqa: E402
from .suite import Case, CaseResult, RunResult, Suite, SuiteResult  # noqa: E402
from .testing import assert_no_regressions  # noqa: E402
from .trajectory import ToolCall, Trajectory  # noqa: E402

__all__ = [
    "Case",
    "CaseResult",
    "Check",
    "CheckResult",
    "Comparison",
    "RunResult",
    "Suite",
    "SuiteResult",
    "ToolCall",
    "Trajectory",
    "assert_no_regressions",
    "compare",
    "expect",
    "judges",
    "record_response",
    "record_usage",
    "recording",
    "snapshot",
    "tool",
]
