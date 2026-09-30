import pytest

from oversight.policy import Policy, PolicyError, Tier


def test_loads_default(policy_path):
    p = Policy.load(policy_path)
    assert p.version == 1


def test_low_risk_read(policy_path, act):
    r = Policy.load(policy_path).assess(act())
    assert r.score == 0 and r.tier == Tier.LOW


def test_score_is_sum_of_weights(policy_path, act):
    a = act(category="write", reversibility="costly", blast_radius="project", sensitivity="internal")
    r = Policy.load(policy_path).assess(a)
    assert r.score == 2 + 2 + 1 + 1
    assert r.tier == Tier.MEDIUM


def test_tier_boundaries_inclusive(policy_path, act):
    p = Policy.load(policy_path)
    # exec(4) alone -> medium boundary
    assert p.assess(act(category="exec")).tier == Tier.MEDIUM
    # financial(5)+costly(2)+project(1) = 8 -> high boundary
    assert p.assess(act(category="financial", reversibility="costly", blast_radius="project")).tier == Tier.HIGH


def test_override_raises_tier(policy_path, act):
    a = act(category="admin", reversibility="irreversible")  # score 9 -> high, override -> critical
    r = Policy.load(policy_path).assess(a)
    assert r.score == 9
    assert r.tier == Tier.CRITICAL
    assert any("irreversible-admin" in s for s in r.reasons)


def test_override_never_lowers_tier(policy_path, act):
    a = act(category="admin", reversibility="irreversible", blast_radius="external", sensitivity="secret")
    assert Policy.load(policy_path).assess(a).tier == Tier.CRITICAL


def test_reasons_explain_score(policy_path, act):
    r = Policy.load(policy_path).assess(act(category="network"))
    assert r.reasons and any("category=network" in s for s in r.reasons)


def test_assess_is_deterministic(policy_path, act):
    p = Policy.load(policy_path)
    a = act(category="comms", blast_radius="org")
    assert p.assess(a) == p.assess(a)


def test_unknown_value_rejected(policy_path, act):
    with pytest.raises(PolicyError):
        Policy.load(policy_path).assess(act(category="teleport"))


def test_bad_policy_rejected(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("version: 1\nweights: {}\n", encoding="utf-8")
    with pytest.raises(PolicyError):
        Policy.load(f)


def test_tiers_must_be_ordered(tmp_path, policy_path):
    text = policy_path.read_text(encoding="utf-8").replace("medium: 4", "medium: 20")
    f = tmp_path / "bad.yaml"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(PolicyError):
        Policy.load(f)


def test_bad_override_tier_is_policy_error(tmp_path, policy_path):
    text = policy_path.read_text(encoding="utf-8").replace("tier: critical\n    reason: irreversible", "tier: catastrophic\n    reason: irreversible")
    f = tmp_path / "bad.yaml"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(PolicyError):
        Policy.load(f)


def test_override_needs_name_reason_and_known_keys(tmp_path, policy_path):
    text = policy_path.read_text(encoding="utf-8").replace("match: {category: admin, reversibility: irreversible}", "match: {colour: red}")
    f = tmp_path / "bad.yaml"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(PolicyError):
        Policy.load(f)


def test_action_notes_flow_into_reasons(policy_path, act):
    r = Policy.load(policy_path).assess(act(notes=("catalog: destructive shell pattern",)))
    assert "note: catalog: destructive shell pattern" in r.reasons
