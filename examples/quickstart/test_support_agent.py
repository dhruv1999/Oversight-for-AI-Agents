"""The same suite under pytest.

AGENT_RATCHET_UPDATE=1 pytest examples/quickstart     # save or refresh the baseline
pytest examples/quickstart                            # fails if a case regressed
"""

from suite import suite

from agent_ratchet import assert_no_regressions


def test_support_agent():
    assert_no_regressions(suite)
