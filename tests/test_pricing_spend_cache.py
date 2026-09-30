import pytest

from oversight.cache import ResponseCache, make_key
from oversight.pricing import UnknownModelPricing, cost_usd
from oversight.spend import SpendLimitExceeded, SpendTracker


def test_cost_usd_haiku():
    # $1 in / $5 out per Mtok
    assert cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000) == pytest.approx(6.0)


def test_dated_model_ids_normalise():
    assert cost_usd("claude-haiku-4-5-20251001", 1000, 0) == cost_usd("claude-haiku-4-5", 1000, 0)


def test_unknown_model_fails_closed():
    with pytest.raises(UnknownModelPricing):
        cost_usd("mystery-model", 1, 1)


def test_spend_records_and_sums():
    s = SpendTracker(max_usd=1.0)
    c = s.record("claude-haiku-4-5", 1000, 100)
    assert c == pytest.approx(0.0015)
    assert s.spent_usd == pytest.approx(0.0015)
    assert s.remaining_usd == pytest.approx(1.0 - 0.0015)


def test_spend_check_blocks_when_worst_case_exceeds_cap():
    s = SpendTracker(max_usd=0.001)
    with pytest.raises(SpendLimitExceeded):
        s.check("claude-haiku-4-5", est_input_tokens=1000, max_output_tokens=500)


def test_spend_check_allows_when_under_cap():
    SpendTracker(max_usd=1.0).check("claude-haiku-4-5", est_input_tokens=1000, max_output_tokens=500)


def test_ledger_is_cumulative_across_instances(tmp_path):
    p = tmp_path / "ledger.jsonl"
    SpendTracker(1.0, ledger_path=p).record("claude-haiku-4-5", 1_000_000, 0)
    s2 = SpendTracker(1.0, ledger_path=p)
    assert s2.spent_usd == pytest.approx(1.0)
    with pytest.raises(SpendLimitExceeded):
        s2.check("claude-haiku-4-5", 10, 10)


def test_from_env(monkeypatch):
    monkeypatch.setenv("MAX_SPEND_USD", "0.25")
    assert SpendTracker.from_env().max_usd == 0.25
    monkeypatch.delenv("MAX_SPEND_USD")
    assert SpendTracker.from_env(default=1.0).max_usd == 1.0


def test_make_key_stable_and_sensitive():
    a = make_key("m", "sys", "user", {"max_tokens": 10})
    assert a == make_key("m", "sys", "user", {"max_tokens": 10})
    assert a != make_key("m2", "sys", "user", {"max_tokens": 10})
    assert a != make_key("m", "sys", "user2", {"max_tokens": 10})
    assert a != make_key("m", "sys", "user", {"max_tokens": 11})


def test_cache_roundtrip_persists(tmp_path):
    p = tmp_path / "c.jsonl"
    c = ResponseCache(p)
    assert c.get("k") is None
    c.put("k", {"text": "hi", "input_tokens": 1, "output_tokens": 2, "model": "m", "stop_reason": None, "cost_usd": 0.1})
    assert ResponseCache(p).get("k")["text"] == "hi"
    assert len(ResponseCache(p)) == 1


def test_in_memory_cache():
    c = ResponseCache()
    c.put("k", {"text": "x"})
    assert c.get("k") == {"text": "x"}
