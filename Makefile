.PHONY: check reproduce bench

# everything CI runs; stops at the first failure
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run python -X warn_default_encoding -W error::EncodingWarning -m pytest -q

# every number and chart in the README and docs/results.md
reproduce:
	uv run python scripts/run_experiments.py
	uv run python scripts/run_robustness.py
	uv run python scripts/make_report.py

bench:
	uv run python scripts/benchmark.py
