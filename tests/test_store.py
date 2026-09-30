import json

import pytest

from oversight import Oversight
from oversight.store import FileStore, MemoryStore, fresh_state


@pytest.mark.parametrize("make", [lambda p: MemoryStore(), lambda p: FileStore(p)])
def test_transaction_persists_changes(tmp_path, make):
    s = make(tmp_path)
    with s.transaction() as st:
        st["interrupt_times"].append(5.0)
    with s.transaction() as st:
        assert st["interrupt_times"] == [5.0] and st["available"] is True


def test_file_store_does_not_save_a_failed_transaction(tmp_path):
    s = FileStore(tmp_path)
    with s.transaction() as st:
        st["available"] = False
    with pytest.raises(RuntimeError), s.transaction() as st:
        st["available"] = True
        raise RuntimeError("crash mid decision")
    with s.transaction() as st:
        assert st["available"] is False


def test_file_store_recovers_from_corrupt_state(tmp_path):
    (tmp_path / "state.json").write_text("{not json")
    with FileStore(tmp_path).transaction() as st:
        assert st == fresh_state()
    (tmp_path / "state.json").write_text("[1, 2]")
    with FileStore(tmp_path).transaction() as st:
        assert st == fresh_state()


def test_no_temp_files_left_behind(tmp_path):
    s = FileStore(tmp_path)
    for _ in range(5):
        with s.transaction() as st:
            st["interrupt_times"].append(1)
    assert sorted(p.name for p in tmp_path.iterdir()) == [".lock", "state.json"]


def test_two_guards_share_one_persons_budget(tmp_path):
    pol = tmp_path / "p.yaml"
    from oversight.policies import DEFAULT_POLICY

    pol.write_text(DEFAULT_POLICY.read_text().replace("max_interrupts_per_window: 6", "max_interrupts_per_window: 1"))
    a = Oversight(policy=pol, state=tmp_path / "s", clock=lambda: 1000.0)
    b = Oversight(policy=pol, state=tmp_path / "s", clock=lambda: 2000.0)
    payment = ("pay_invoice", {"vendor": "Acme", "amount": 420})
    assert a.check(*payment).needs_person
    assert not b.check(*payment).needs_person  # budget already spent by the other agent
    a.person_away()
    assert not b.is_person_available()
    state = json.loads((tmp_path / "s" / "state.json").read_text())
    assert state["interrupt_times"] == [1000.0] and state["available"] is False


def test_logs_name_the_rules_that_decided(tmp_path):
    g = Oversight(log_path=tmp_path / "log.jsonl")
    g.check("read_file", {"path": "a"})
    rec = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[0])
    assert rec["log_version"] == 1 and rec["rules"] == g.rules_id and len(g.rules_id) == 25


def test_policy_validation_catches_bad_attention(tmp_path):
    from oversight.policies import DEFAULT_POLICY
    from oversight.policy import Policy, PolicyError

    f = tmp_path / "p.yaml"
    f.write_text(DEFAULT_POLICY.read_text().replace("  min_gap_seconds: 30\n", ""))
    with pytest.raises(PolicyError):
        Policy.load(f)
    f.write_text(DEFAULT_POLICY.read_text().replace("min_allow_confidence: 0.6", "min_allow_confidence: 6"))
    with pytest.raises(PolicyError):
        Policy.load(f)
