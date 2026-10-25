"""Run a suite from pytest, next to your other tests.

    from agent_ratchet.testing import assert_no_regressions

    def test_support_agent():
        assert_no_regressions(suite)

The baseline is .agent-ratchet/<suite>.baseline.json. Create or refresh it with
AGENT_RATCHET_UPDATE=1 pytest, then commit it. On a developer machine a missing baseline is created
on the first run; in CI (where the CI environment variable is set) a missing baseline fails the test,
so a forgotten baseline never passes silently.
"""

from __future__ import annotations

import os
from pathlib import Path

from .compare import compare
from .report import text
from .suite import Suite, SuiteResult, baseline_path


def assert_no_regressions(suite: Suite, baseline: str | Path | None = None, *, confidence: float = 0.95) -> SuiteResult:
    path = Path(baseline) if baseline else baseline_path(suite.name)
    update = os.environ.get("AGENT_RATCHET_UPDATE", "") not in ("", "0")
    if update or (not path.exists() and not os.environ.get("CI")):
        result = suite.run(repeats=suite.max_repeats)
        result.save(path, full=False)
        if result.must_pass_failures:
            raise AssertionError("\n" + text(result))
        return result
    if not path.exists():
        raise AssertionError(f"no baseline for {suite.name} at {path}; create one with AGENT_RATCHET_UPDATE=1 pytest and commit it")
    before = SuiteResult.load(path)
    result = suite.run(baseline=before)
    comparison = compare(result, before, confidence)
    if result.must_pass_failures or not comparison.ok:
        raise AssertionError("\n" + text(result, comparison))
    return result
