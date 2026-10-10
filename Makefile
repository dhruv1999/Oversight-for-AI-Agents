.PHONY: check reproduce bench screenshots llm-estimate llm

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

# the review page and terminal pictures in the README (needs node with playwright)
screenshots:
	uv run python scripts/screenshots.py

# the same experiments with an AI model as the checker; spending stops at MAX_SPEND_USD
#   make llm                                                     Claude (needs ANTHROPIC_API_KEY)
#   make llm PROVIDER=gemini MODEL=<model> PRICE=0.75,3.75       also openai and azure (MODEL = deployment)
PROVIDER ?= anthropic
MODEL ?= claude-opus-5-5
PRICE ?=
LLM_ARGS = --reviewer $(PROVIDER) --model $(MODEL) $(if $(PRICE),--price $(PRICE))

llm-estimate:
	uv run python scripts/run_experiments.py $(LLM_ARGS) --estimate

llm:
	uv run python scripts/run_experiments.py $(LLM_ARGS)
	uv run python scripts/make_report.py --tag llm_$(PROVIDER)_$(MODEL)
