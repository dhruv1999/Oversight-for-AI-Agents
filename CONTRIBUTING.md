# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Setup

```bash
git clone https://github.com/dhruv1999/Oversight-for-AI-Agents && cd Oversight-for-AI-Agents
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Without uv: `pip install -e . pytest ruff mypy`.

The core tests need no API keys and no frameworks. Framework tests skip unless the framework is installed. To run them:

```bash
uv pip install openai-agents langgraph langchain-core google-adk claude-agent-sdk opentelemetry-sdk
uv run pytest
```

CrewAI runs in its own CI job because of its dependency pins.

## Guidelines

- Keep the core free of dependencies. Framework code goes in `agent_regress/integrations/` and imports the framework inside functions.
- Test integrations against the real framework with a scripted model, not mocks of the framework, so changes in the framework show up.
- Checks must never call a model unless they are a judge, and a check that cannot decide must fail.
- Keep messages and reports plain and short.

## Adding an integration

1. Add `agent_regress/integrations/<name>.py` with a function that turns the framework's output into a `Trajectory`, and a `wrap()` that runs the agent.
2. If the framework's return value is easy to recognise, add it to `integrations/auto.py`.
3. Add a test in `tests/` and an example in `examples/frameworks/`.
4. Add a row to the README and a section to `docs/integrations.md`.
