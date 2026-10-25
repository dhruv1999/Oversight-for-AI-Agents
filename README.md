# agent-regress

[![CI](https://github.com/dhruv1999/Oversight-for-AI-Agents/actions/workflows/ci.yml/badge.svg)](https://github.com/dhruv1999/Oversight-for-AI-Agents/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

**Regression tests for AI agents.** Catch the prompt change, model upgrade or tool edit that quietly breaks your agent, before it ships.

```bash
pip install agent-regress
```

## The problem

Agents break in ways normal tests miss.

- **Small changes have side effects.** A tweak to fix one conversation changes how the agent handles ten others.
- **Model upgrades shift behaviour.** The new model is better on average and worse on the one flow your customers rely on.
- **Runs are random.** The same input passes on Monday and fails on Tuesday, so a single passing run proves little.
- **Failures are in the steps, not the answer.** The reply reads fine, but the agent skipped a lookup or called the refund tool it should never call.

## Who it is for

- **Engineers shipping agents** who want a check on every pull request, like unit tests.
- **Teams on LangGraph, CrewAI, OpenAI Agents SDK, Google ADK or Claude Agent SDK** who want one tool across frameworks.
- **Teams already tracing in Langfuse or OpenTelemetry** who want production traces to become tests.

## Why another tool

Regression testing in CI is where agent evaluation is still mostly paid.

| Tool | What it is | For regression testing in CI |
|---|---|---|
| Braintrust | Paid platform | Strong experiment diffs and CI gates, in their cloud |
| LangSmith | Paid platform, per seat | Datasets and comparisons, tied to their platform |
| promptfoo | Open source, owned by OpenAI since March 2026 | Built for prompts and red teaming more than agent steps |
| DeepEval, Ragas, Inspect | Open source | Score single runs well; comparing runs over time is left to you or a paid add on |
| Langfuse | Open source tracing | Great for seeing production; not a test runner for pull requests |
| **agent-regress** | **Open source, MIT, runs locally** | **Repeated runs, a saved baseline and a pass or fail for every pull request** |

More detail and sources in [docs/why.md](docs/why.md).

## What it does

- **Behaviour checks.** Write what the agent must and must not do: which tools, with which arguments, in which order, and what the answer says. *(deterministic, no model calls)*
- **Repeated runs.** Every case runs several times, so you see pass rates instead of one lucky result. *(pass^k, 95% intervals)*
- **Baseline diff.** Each run is compared with the last good one, and only real drops fail the build. *(saved JSON baseline, tolerance)*
- **Cost and speed budgets.** Fail when a change makes the agent much slower or more expensive. *(token cost, latency)*
- **CI ready.** Exit code 1 on a regression and a Markdown summary on the pull request. *(GitHub Actions summary)*
- **Production to tests.** Turn a Langfuse or OpenTelemetry trace into a test case in one command.
- **Optional model graders.** For things rules cannot capture, with Claude, OpenAI, Azure OpenAI or Gemini. *(LLM as judge)*

## Quickstart

No API key needed. The example agent is a few lines of plain Python.

```bash
git clone https://github.com/dhruv1999/Oversight-for-AI-Agents && cd Oversight-for-AI-Agents
pip install -e .
agent-regress run examples/quickstart/suite.py --save-baseline
AGENT_VERSION=2 agent-regress run examples/quickstart/suite.py
```

The second command simulates a prompt change that makes the agent refund large orders itself instead of passing them to a manager:

```text
case                            passed  baseline  status
------------------------------  ------  --------  -------------------------------------
order status                    3/3     3/3       ok
small refund is handled         3/3     3/3       ok
large refund goes to a manager  0/3     3/3       REGRESSED (check with more repeats)
asks for the order number       3/3     3/3       ok

large refund goes to a manager: pass rate 100% -> 0%
  calls escalate_to_human(order_id='77'): failed 3/3 (never called escalate_to_human; called ['lookup_order', 'issue_refund'])
  never calls issue_refund: failed 3/3 (called issue_refund)

9/12 runs passed across 4 cases; 1 regressed
```

It exits with code 1, so CI fails.

## Writing a suite

A suite is a Python file with your agent and the cases it must handle.

```python
from agent_regress import Case, Suite, expect
from agent_regress.integrations.langgraph import wrap
from my_app import graph

suite = Suite(
    agent=wrap(graph),
    repeats=5,
    cases=[
        Case("order status", "Where is order 42?", [
            expect.calls("lookup_order", order_id="42"),
            expect.output_contains("shipped"),
        ]),
        Case("large refund", "Refund order 77", [
            expect.calls("escalate_to_human"),
            expect.never_calls("issue_refund"),
            expect.max_cost(0.05),
        ]),
    ],
)
```

```bash
agent-regress run tests/agent_suite.py --save-baseline   # once, on a version you trust
agent-regress run tests/agent_suite.py                   # on every change
```

Commit the baseline in `.agent-regress/` so CI compares against it. The full list of checks is in [docs/guide.md](docs/guide.md).

## Integrations

| Framework or tool | How |
|---|---|
| LangGraph and LangChain | `integrations.langgraph.wrap(graph)` |
| CrewAI | `integrations.crewai.wrap(build_crew)` |
| OpenAI Agents SDK | `integrations.openai_agents.wrap(agent)` |
| Google ADK | `integrations.google_adk.wrap(agent)` |
| Claude Agent SDK | `integrations.claude_agent_sdk.wrap(options)` |
| Langfuse | `agent-regress import langfuse <trace-id>`, or score production traces |
| OpenTelemetry GenAI | `agent-regress import otel spans.json` |
| Plain Python on the OpenAI, Anthropic or Gemini SDKs | `@tool` on your tool functions and `record_response(response)` |

Each integration is tested against the real framework with a scripted model. Examples for each are in [examples/frameworks](examples/frameworks), and details in [docs/integrations.md](docs/integrations.md).

## Running in CI

```yaml
- run: pip install agent-regress
- run: agent-regress run tests/agent_suite.py --repeats 5
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

The results table appears on the pull request's checks page. A full workflow is in [examples/github_workflow.yml](examples/github_workflow.yml).

## How randomness is handled

- Every case runs `repeats` times (3 by default; 5 to 10 is better for CI).
- A case is **ok** when every run passes, **flaky** when some do, and **failing** when none do.
- A case has **regressed** when its pass rate drops by 30 points or more compared with the baseline. Change this with `--tolerance`.
- When the drop could still be noise at this sample size, the report says "check with more repeats" instead of overstating it.

## Roadmap

- Record and replay tool results, so suites run without calling live systems.
- Multi turn cases with a simulated user.
- A pytest plugin.
- Parallel runs across CI machines for large suites.

## Docs

- [Why this exists](docs/why.md): the problem we picked and the options we weighed
- [Guide](docs/guide.md): checks, baselines, budgets, CI and model graders
- [Integrations](docs/integrations.md): setup for every framework
- [Contributing](CONTRIBUTING.md)

MIT licensed.
