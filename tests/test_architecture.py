"""Guardrails for the project's design rules; they fail if someone breaks them."""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent / "oversight"
DETERMINISTIC_CORE = ("policy", "attention", "allocator", "baselines")


def top_level_imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_provider_sdks_only_imported_inside_adapters():
    for f in ROOT.rglob("*.py"):
        if "adapters" in f.parts:
            continue
        assert "anthropic" not in top_level_imports(f), f


def test_deterministic_core_never_imports_models_or_adapters():
    for name in DETERMINISTIC_CORE:
        f = ROOT / f"{name}.py"
        if f.exists():
            assert not ({"safety_model", "adapters", "gate"} & top_level_imports(f)), f


def test_deterministic_core_has_no_clock_or_randomness():
    for name in ("policy", "attention", "allocator"):
        src = (ROOT / f"{name}.py").read_text()
        assert not re.search(r"\b(import random|time\.time|datetime|monotonic)\b", src), name


def test_model_calls_only_via_safety_model_and_adapters():
    for f in ROOT.rglob("*.py"):
        if "adapters" in f.parts or f.name == "safety_model.py":
            continue
        assert not re.search(r"\.complete\(", f.read_text()), f
