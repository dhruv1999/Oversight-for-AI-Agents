import pytest

from oversight.policy import Policy, PolicyError, Tier
from oversight.registry import ToolRegistry

TOOLS = __import__("pathlib").Path(__file__).parent.parent / "policies" / "tools.yaml"


@pytest.fixture
def reg(policy_path):
    return ToolRegistry.load(TOOLS, Policy.load(policy_path))


@pytest.fixture
def pol(policy_path):
    return Policy.load(policy_path)


def tier(reg, pol, tool, params, desc="x"):
    return pol.assess(reg.to_action("1", tool, params, desc)).tier


def test_defaults(reg):
    a = reg.to_action("1", "read_file", {"path": "README.md"}, "read")
    assert (a.category, a.reversibility, a.blast_radius, a.sensitivity) == ("read", "reversible", "self", "none")
    assert a.notes == ()


def test_select_stays_low_writes_go_high(reg, pol):
    assert tier(reg, pol, "run_sql", {"query": "SELECT count(*) FROM orders WHERE day = '2026-01-02'"}) == Tier.LOW
    assert tier(reg, pol, "run_sql", {"query": "UPDATE orders SET status='shipped' WHERE id=9"}) == Tier.HIGH


def test_drop_table_is_critical(reg, pol):
    a = reg.to_action("1", "run_sql", {"query": "DROP TABLE orders"}, "x")
    assert pol.assess(a).tier == Tier.CRITICAL
    assert any("sql-ddl" in n for n in a.notes)


def test_external_destination_raises_blast_radius(reg):
    internal = reg.to_action("1", "http_post", {"url": "https://hooks.example-corp.test/ci"}, "x")
    external = reg.to_action("2", "http_post", {"url": "https://paste.example.net/new"}, "x")
    ip = reg.to_action("3", "http_get", {"url": "http://203.0.113.7/ping"}, "x")
    assert internal.blast_radius == "project"
    assert external.blast_radius == "external" and ip.blast_radius == "external"


def test_email_to_internal_vs_external(reg):
    assert reg.to_action("1", "send_email", {"to": "ana@example-corp.test"}, "x").blast_radius == "project"
    assert reg.to_action("1", "send_email", {"to": "someone@mail.example"}, "x").blast_radius == "external"


def test_rules_only_raise(reg, policy_path, tmp_path):
    text = TOOLS.read_text() + """
  - name: try-to-lower
    tool: update_iam
    any_param_regex: '.'
    set: {category: read, reversibility: reversible}
"""
    f = tmp_path / "t.yaml"
    f.write_text(text)
    r = ToolRegistry.load(f, Policy.load(policy_path))
    a = r.to_action("1", "update_iam", {"policy": "x"}, "x")
    assert a.category == "admin" and a.reversibility == "costly"


def test_large_payment_threshold(reg, pol):
    assert tier(reg, pol, "pay_invoice", {"vendor": "v", "amount": 900}) == Tier.HIGH
    assert tier(reg, pol, "pay_invoice", {"vendor": "v", "amount": 25000}) == Tier.CRITICAL


def test_unknown_tool_is_conservative(reg, pol):
    a = reg.to_action("1", "launch_rocket", {}, "x")
    assert pol.assess(a).tier >= Tier.HIGH and "unknown tool" in a.notes[0]


def test_bad_registry_values_rejected(policy_path, tmp_path):
    f = tmp_path / "t.yaml"
    f.write_text(TOOLS.read_text().replace("read_file:       {category: read,", "read_file:       {category: teleport,"))
    with pytest.raises(PolicyError):
        ToolRegistry.load(f, Policy.load(policy_path))
