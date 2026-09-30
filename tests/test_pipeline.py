import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_quick_experiment_run(tmp_path):
    out = tmp_path / "r"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "run_experiments.py"), "--quick", "--out", str(out)], check=True, capture_output=True)
    rows = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    strategies = {r["strategy"] for r in rows}
    assert strategies == {"no_oversight", "always_model", "static_risk", "adaptive", "always_human"}
    none = [r for r in rows if r["strategy"] == "no_oversight"]
    assert all(r["harm_executed_pct"] == 100 for r in none)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["pool_size"] > 0 and m["seeds"] == [0]


def test_committed_results_match_report():
    """The README/results numbers must come from the committed JSON (no hand-edited results)."""
    rows = json.loads((ROOT / "results" / "heuristic" / "summary.json").read_text(encoding="utf-8"))
    static = next(r for r in rows if r["fatigue"] == "on" and r["profile"] == "all" and r["strategy"] == "static_risk")
    text = (ROOT / "docs" / "results.md").read_text(encoding="utf-8")
    assert f"{static['interrupts_per_day']:.1f}" in text


def test_hand_written_docs_quote_committed_numbers():
    """docs/research.md quotes a few results in prose; fail if the committed results no longer say that."""
    res = json.loads((ROOT / "results" / "heuristic" / "research.json").read_text(encoding="utf-8"))
    rob = json.loads((ROOT / "results" / "heuristic" / "robustness.json").read_text(encoding="utf-8"))
    doc = (ROOT / "docs" / "research.md").read_text(encoding="utf-8")

    def sweep(strat, recall):
        return next(x for x in res["checker_sweep"] if x["fatigue"] == "on" and x["strategy"] == strat and x["recall"] == recall)["harm_pct"]

    def attack(strat, k):
        return next(x for x in rob["budget_drain_attack"] if x["human"] == "fatigue on" and x["strategy"] == strat and x["burst"] == k)["success_pct"]

    assert f"{sweep('adaptive_approve', 0.2):.0f}% of harmful actions versus {sweep('static_risk', 0.2):.0f}%" in doc
    assert f"from {attack('static_risk', 0):.0f}% to {attack('static_risk', 12):.0f}%" in doc
    assert max(attack("adaptive", k) for k in (0, 3, 6, 12)) < 13.5  # "stayed near 13% or lower"
    assert f"across {sum(v['kind'] != 'design' for v in rob['variants']) - 1} changes" in doc
