import pytest

from agent_ratchet.stats import fisher_worse, min_p_worse, tarone


def test_fisher_exact_values():
    assert fisher_worse(3, 3, 0, 3) == pytest.approx(1 / 20)
    assert fisher_worse(10, 10, 0, 10) == pytest.approx(1 / 184756)
    assert fisher_worse(10, 10, 10, 10) == pytest.approx(1.0)
    assert fisher_worse(5, 10, 8, 10) > 0.5  # the new runs did better
    assert fisher_worse(10, 10, 7, 10) == pytest.approx(19448 / 184756)  # 100% -> 70% at 10 runs is still within chance


def test_min_p_is_one_when_nothing_failed():
    assert min_p_worse(10, 10, 3, 3) == 1.0  # no failures anywhere: a regression is impossible
    assert min_p_worse(10, 10, 0, 3) == pytest.approx(1 / 286)
    assert min_p_worse(10, 10, 0, 3) <= fisher_worse(10, 10, 0, 3)


def test_tarone_only_counts_cases_that_could_regress():
    assert tarone(0.05, []) == 0.05
    assert tarone(0.05, [1.0] * 50 + [1e-6]) == 0.05  # 50 stable cases do not dilute the one that matters
    assert tarone(0.05, [0.001] * 10) == pytest.approx(0.005)
    assert tarone(0.05, [1e-9] * 100) == pytest.approx(0.0005)
