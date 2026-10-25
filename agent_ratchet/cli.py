"""Command line.

    agent-ratchet run tests/agent_suite.py                 run, and compare with the baseline if there is one
    agent-ratchet run tests/agent_suite.py --save-baseline  run and keep the result as the new baseline
    agent-ratchet compare new.json baseline.json            compare two saved results
    agent-ratchet import langfuse <trace-id>                turn a production trace into a test case
    agent-ratchet import otel spans.json                    the same, from OpenTelemetry spans

Exit codes: 0 all good; 1 a case regressed or a must pass case failed (or any failure, with
--fail-on failure); 2 bad usage, or the suite file could not be loaded.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import subprocess
import sys
import traceback
from pathlib import Path

from .compare import Comparison, compare
from .report import markdown, text
from .suite import DEFAULT_DIR, Suite, SuiteResult, baseline_path, slug


class UsageError(Exception):
    pass


def _load_suites(path: Path) -> list[Suite]:
    if not path.is_file():
        raise UsageError(f"no such file: {path}")
    sys.path.insert(0, str(path.resolve().parent))
    module_name = f"agent_ratchet_suite_{slug(path.stem)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise UsageError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # dataclasses and pickling look classes up by module
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        traceback.print_exc()
        raise UsageError(f"could not load {path}: {type(e).__name__}: {e}") from e
    suites = list({id(v): v for v in vars(module).values() if isinstance(v, Suite)}.values())
    if not suites:
        raise UsageError(f"{path} defines no Suite; create one at module level, e.g. suite = Suite(agent=..., cases=[...])")
    slugs = [slug(s.name) for s in suites]
    clashes = sorted({s for s in slugs if slugs.count(s) > 1})
    if clashes:
        raise UsageError(f"more than one suite is named {clashes}; give each a different name= so their baselines stay separate")
    return suites


def _provenance() -> dict[str, str]:
    """Which commit and Python produced a baseline, for when someone asks where it came from."""
    info = {"python": platform.python_version()}
    commit = os.environ.get("GITHUB_SHA")
    if not commit:
        try:
            commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, encoding="utf-8", timeout=5, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            commit = ""
    if commit:
        info["commit"] = commit
    return info


def _save_latest(result: SuiteResult, out_dir: Path) -> None:
    """The full run, for debugging. Kept out of git: it holds inputs, answers and tool data."""
    result.save(out_dir / f"{slug(result.name)}.latest.json")
    ignore = out_dir / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*.latest.json\n", encoding="utf-8")


def _outcome(result: SuiteResult, comparison: Comparison | None, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    if fail_on == "failure":
        return 0 if result.ok else 1
    if result.must_pass_failures:
        return 1
    return 1 if comparison is not None and not comparison.ok else 0


def _publish(md: str, markdown_path: str | None) -> None:
    targets = [markdown_path] if markdown_path else []
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        targets.append(os.environ["GITHUB_STEP_SUMMARY"])
    for target in targets:
        with open(target, "a", encoding="utf-8") as f:
            f.write(md + "\n")


def _progress(line: str) -> None:
    print(f"  {line}", file=sys.stderr, flush=True)


def _cmd_run(args: argparse.Namespace) -> int:
    code = 0
    out_dir = Path(args.dir)
    for suite in _load_suites(Path(args.suite)):
        if args.max_repeats is not None:
            suite.max_repeats = max(args.max_repeats, suite.repeats)
        path = Path(args.baseline) if args.baseline else baseline_path(suite.name, out_dir)
        if args.save_baseline:
            repeats = args.repeats or suite.max_repeats  # a baseline is a one time cost, and more runs make every later comparison sharper
            print(f"{suite.name}: saving a baseline, {repeats} runs per case", file=sys.stderr)
            result = suite.run(only=args.case, repeats=repeats, progress=_progress)
            _save_latest(result, out_dir)
            keep = SuiteResult.load(path).merged(result) if args.case and path.exists() else result
            keep.meta.update(_provenance())
            keep.save(path, full=False)
            print(text(result) + f"\n\nsaved as the baseline: {path}")
            _publish(markdown(result), args.markdown)
            code = max(code, _outcome(result, None, args.fail_on))
            continue
        baseline = SuiteResult.load(path) if path.exists() else None
        if baseline is not None and args.case:
            baseline = baseline.subset(args.case)
        print(f"{suite.name}: running {len(args.case or suite.cases)} cases", file=sys.stderr)
        result = suite.run(only=args.case, repeats=args.repeats, baseline=baseline, progress=_progress)
        _save_latest(result, out_dir)
        comparison = compare(result, baseline, args.confidence, args.max_cost_increase, args.max_latency_increase) if baseline else None
        print(text(result, comparison))
        if comparison is None:
            print(f"\nno baseline yet; save one with --save-baseline ({path})")
        _publish(markdown(result, comparison), args.markdown)
        code = max(code, _outcome(result, comparison, args.fail_on))
    return code


def _cmd_compare(args: argparse.Namespace) -> int:
    result = SuiteResult.load(args.new)
    comparison = compare(result, SuiteResult.load(args.baseline), args.confidence, args.max_cost_increase, args.max_latency_increase)
    print(text(result, comparison))
    _publish(markdown(result, comparison), args.markdown)
    return _outcome(result, comparison, args.fail_on)


def _cmd_import(args: argparse.Namespace) -> int:
    from .snapshot import case_code

    if args.source == "langfuse":
        from .integrations.langfuse import fetch_trace, from_trace

        traj = from_trace(fetch_trace(args.ref))
    else:
        from .integrations.otel import from_spans, load_otlp_json

        traj = from_spans(load_otlp_json(args.ref))
    print(case_code(traj, name=args.name or f"from {args.source} {Path(args.ref).name}"))
    return 0


def _comparison_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--confidence", type=float, default=0.95, help="how sure a drop must be before it fails the build (default 0.95)")
    p.add_argument("--max-cost-increase", type=float, default=None, help="fail if mean cost grows by more than this, e.g. 0.25")
    p.add_argument("--max-latency-increase", type=float, default=None, help="fail if mean time grows by more than this, e.g. 0.5")
    p.add_argument("--fail-on", choices=["regression", "failure", "never"], default="regression")
    p.add_argument("--markdown", default=None, help="also write a Markdown report here (GITHUB_STEP_SUMMARY is used automatically)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent-ratchet", description="Regression tests for AI agents.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a suite file")
    r.add_argument("suite")
    r.add_argument("--repeats", type=int, default=None, help="runs per case (default: the suite's setting)")
    r.add_argument("--max-repeats", type=int, default=None, help="most runs for a case that looks worse, and runs per case for a baseline (default 10)")
    r.add_argument("--case", action="append", help="run only this case (repeatable)")
    r.add_argument("--dir", default=str(DEFAULT_DIR), help="where results and baselines are kept")
    r.add_argument("--baseline", default=None, help="baseline file (default: <dir>/<suite>.baseline.json)")
    r.add_argument("--save-baseline", action="store_true", help="save this run as the baseline")
    _comparison_options(r)
    c = sub.add_parser("compare", help="compare two saved results")
    c.add_argument("new")
    c.add_argument("baseline")
    _comparison_options(c)
    i = sub.add_parser("import", help="turn a production trace into a test case")
    i.add_argument("source", choices=["langfuse", "otel"])
    i.add_argument("ref", help="Langfuse trace id, or a file of OpenTelemetry spans (OTLP JSON)")
    i.add_argument("--name", default=None)
    args = ap.parse_args(argv)
    try:
        return {"run": _cmd_run, "compare": _cmd_compare, "import": _cmd_import}[args.cmd](args)
    except (UsageError, ValueError, OSError) as e:
        print(f"agent-ratchet: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
