"""agent-regress: regression tests for AI agents.

    from agent_regress import Case, Suite, expect

    suite = Suite(agent=my_agent, repeats=3, cases=[
        Case("refund needs an order number", "Refund my last order",
             expect=[expect.never_calls("issue_refund"), expect.output_contains("order number")]),
    ])

Run it with `agent-regress run suite.py`; save a baseline with `--save-baseline`; later runs
fail when a case gets worse.
"""

__version__ = "0.1.0"

from . import checks as expect  # noqa: E402
from . import judges  # noqa: E402
from .checks import Check, CheckResult  # noqa: E402
from .compare import Comparison, compare  # noqa: E402
from .recording import record_response, record_usage, recording, tool  # noqa: E402
from .snapshot import snapshot  # noqa: E402
from .suite import Case, CaseResult, RunResult, Suite, SuiteResult  # noqa: E402
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
    "compare",
    "expect",
    "judges",
    "record_response",
    "record_usage",
    "recording",
    "snapshot",
    "tool",
]
