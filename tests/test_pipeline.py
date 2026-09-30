import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_quick_experiment_run(tmp_path):
    out = tmp_path / "r"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "run_experiments.py"), "--quick", "--out", str(out)], check=True, capture_output=True)
    rows = json.loads((out / "summary.json").read_text())
    strategies = {r["strategy"] for r in rows}
    assert strategies == {"no_oversight", "always_model", "static_risk", "adaptive", "always_human"}
    none = [r for r in rows if r["strategy"] == "no_oversight"]
    assert all(r["harm_executed_pct"] == 100 for r in none)
    m = json.loads((out / "manifest.json").read_text())
    assert m["pool_size"] > 0 and m["seeds"] == [0]


def test_committed_results_match_report():
    """The README/results numbers must come from the committed JSON (no hand-edited results)."""
    rows = json.loads((ROOT / "results" / "heuristic" / "summary.json").read_text())
    static = next(r for r in rows if r["fatigue"] == "on" and r["profile"] == "all" and r["strategy"] == "static_risk")
    text = (ROOT / "docs" / "results.md").read_text()
    assert f"{static['interrupts_per_day']:.1f}" in text
