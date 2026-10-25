"""Command line.

    agent-regress run tests/agent_suite.py                 run, compare with the baseline if there is one
    agent-regress run tests/agent_suite.py --save-baseline  run and keep the result as the new baseline
    agent-regress compare new.json baseline.json            compare two saved results
    agent-regress import langfuse <trace-id>                turn a production trace into a test case
    agent-regress import otel spans.json                    the same, from OpenTelemetry spans

Exit codes: 0 all good, 1 something regressed (or failed, with --fail-on failure), 2 bad usage.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

from .compare import Comparison, compare
from .report import markdown, text
from .suite import Suite, SuiteResult

DEFAULT_DIR = Path(".agent-regress")


def _load_suites(path: Path) -> list[Suite]:
    if not path.is_file():
        raise SystemExit(f"no such file: {path}")
    sys.path.insert(0, str(path.resolve().parent))
    spec = importlib.util.spec_from_file_location(f"agent_regress_suite_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suites = [v for v in vars(module).values() if isinstance(v, Suite)]
    if not suites:
        raise SystemExit(f"{path} defines no Suite; create one at module level, e.g. suite = Suite(agent=..., cases=[...])")
    return suites


def _slug(name: str) -> str:
    """A suite name that is safe as a file name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "suite"


def _outcome(result: SuiteResult, comparison: Comparison | None, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    if fail_on == "failure" and not result.ok:
        return 1
    return 1 if comparison is not None and not comparison.ok else 0


def _publish(md: str, markdown_path: str | None) -> None:
    targets = [markdown_path] if markdown_path else []
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        targets.append(os.environ["GITHUB_STEP_SUMMARY"])
    for target in targets:
        with open(target, "a", encoding="utf-8") as f:
            f.write(md + "\n")


def _cmd_run(args: argparse.Namespace) -> int:
    code = 0
    for suite in _load_suites(Path(args.suite)):
        result = suite.run(only=args.case or None, repeats=args.repeats)
        out_dir = Path(args.dir)
        result.save(out_dir / f"{_slug(suite.name)}.latest.json")
        baseline_path = Path(args.baseline) if args.baseline else out_dir / f"{_slug(suite.name)}.baseline.json"
        comparison = None
        if baseline_path.exists() and not args.save_baseline:
            comparison = compare(result, SuiteResult.load(baseline_path), args.tolerance, args.max_cost_increase, args.max_latency_increase)
        print(text(result, comparison))
        if args.save_baseline:
            result.save(baseline_path)
            print(f"\nsaved as the baseline: {baseline_path}")
        elif comparison is None:
            print(f"\nno baseline yet; save this run as one with --save-baseline ({baseline_path})")
        _publish(markdown(result, comparison), args.markdown)
        code = max(code, _outcome(result, comparison, args.fail_on))
    return code


def _cmd_compare(args: argparse.Namespace) -> int:
    result = SuiteResult.load(args.new)
    comparison = compare(result, SuiteResult.load(args.baseline), args.tolerance, args.max_cost_increase, args.max_latency_increase)
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
    p.add_argument("--tolerance", type=float, default=0.3, help="pass rate drop that counts as a regression (default 0.3)")
    p.add_argument("--max-cost-increase", type=float, default=None, help="fail if mean cost grows by more than this, e.g. 0.25")
    p.add_argument("--max-latency-increase", type=float, default=None, help="fail if mean time grows by more than this, e.g. 0.5")
    p.add_argument("--fail-on", choices=["regression", "failure", "never"], default="regression")
    p.add_argument("--markdown", default=None, help="also write a Markdown report here (GITHUB_STEP_SUMMARY is used automatically)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent-regress", description="Regression tests for AI agents.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a suite file")
    r.add_argument("suite")
    r.add_argument("--repeats", type=int, default=None, help="runs per case (default: the suite's setting)")
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
    except (ValueError, FileNotFoundError) as e:
        print(f"agent-regress: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
