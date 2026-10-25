# agent-ratchet

[![CI](https://github.com/dhruv1999/Oversight-for-AI-Agents/actions/workflows/ci.yml/badge.svg)](https://github.com/dhruv1999/Oversight-for-AI-Agents/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

**Regression tests for AI agents. Your agent can get better. It can't quietly get worse.**

agent-ratchet runs each test case several times, compares the pass rates with a baseline saved in your repo, and fails a pull request only when a behaviour got worse by more than chance explains.

```text
case                            passed  baseline  status     cost     time
------------------------------  ------  --------  ---------  -------  ----
order status                    3/3     10/10     ok         $0.0019  0.0s
small refund is handled         3/3     10/10     ok         $0.0019  0.0s
large refund goes to a manager  0/10    10/10     REGRESSED  $0.0019  0.0s
asks for the order number       3/3     10/10     ok         $0.0019  0.0s

large refund goes to a manager: passed 0/10, baseline 10/10. A drop this large happens by chance under 0.1% of the time.
  calls escalate_to_human(order_id='77'): failed 10/10, baseline 0/10 (never called escalate_to_human; called ['lookup_order', 'issue_refund'])
  never calls issue_refund: failed 10/10, baseline 0/10 (called issue_refund)
```

## The problem

- **Agents are random.** The same test passes on Monday and fails on Tuesday. A check that fails at random gets ignored, then switched off.
- **Averages hide breakage.** A suite score can stay flat while the one flow your customers rely on breaks.
- **Enough runs cost money.** Running every case ten times on every pull request is expensive, so teams run too few and end up reading noise.

## Who it is for

- **Teams with an agent in production** that change prompts, models or tools every week.
- **Engineers who review agent changes in pull requests** and want a check they can trust like a unit test.
- **Teams that can't send traces to a hosted eval vendor.** Everything runs in your CI, and the baseline is a file in your repo.

## How it compares

Several tools can now gate agent changes in CI. Each is good at something different.

| Tool | Good at | Choose agent-ratchet if you want |
|---|---|---|
| Braintrust, LangSmith (paid) | Hosted experiments, dashboards and team review | It free, local and inside your repo |
| Langfuse experiments (open source, CI gates since May 2026) | Gating on scores when you already run Langfuse | Verdicts per behaviour, with no server to run |
| promptfoo (open source, owned by OpenAI) | Prompt comparisons and red teaming | Tests about agent steps, written in Python |
| DeepEval, Google ADK eval (open source) | pytest style metrics against fixed thresholds | Pass rates compared with your own baseline |
| llmci, agent-regress-cli, AgentAssay (open source) | Statistical gates, built on YAML configs, 50 runs per version, or an AGPL license | Readable checks in Python, extra runs only where needed, MIT |

The reasoning and sources are in [docs/why.md](docs/why.md).

## What it does

- **Behaviour checks.** Say what the agent must and must not do: which tools, with which arguments, in what order, and what the answer says. *(deterministic, no model calls)*
- **Repeated runs, extra runs only where unclear.** Every case runs 3 times. A case that looks worse than its baseline runs up to 10 times before anything is decided. *(adaptive sampling)*
- **Verdicts you can trust.** A drop fails the build only when it is too large to be chance, with the bar set so a suite with no real change fails less than 5% of the time. *(Fisher exact test, suite wide false alarm control)*
- **Must pass cases.** Mark a guardrail and any single failure fails the build. *(zero tolerance)*
- **Cost and speed budgets.** Fail when a change makes the agent much slower or more expensive. *(token cost, latency)*
- **Works where you already test.** A command line, a pytest helper and a summary on every GitHub pull request.
- **Production traces to tests.** Turn a Langfuse or OpenTelemetry trace into a test case in one command.

## Quickstart

No API key needed. The example agent is a few lines of plain Python.

```bash
git clone https://github.com/dhruv1999/Oversight-for-AI-Agents && cd Oversight-for-AI-Agents
pip install -e .
agent-ratchet run examples/quickstart/suite.py --save-baseline
AGENT_VERSION=2 agent-ratchet run examples/quickstart/suite.py
```

The second run simulates a prompt change that makes the agent refund large orders itself instead of passing them to a manager. It prints the table at the top of this page and exits with code 1.

To use it in your own project:

```bash
pip install git+https://github.com/dhruv1999/Oversight-for-AI-Agents
```

## Writing a suite

A suite is a Python file with your agent and the cases it must handle.

```python
from agent_ratchet import Case, Suite, expect
from agent_ratchet.integrations.langgraph import wrap
from my_app import graph

suite = Suite(
    agent=wrap(graph),
    cases=[
        Case("order status", "Where is order 42?", [
            expect.calls("lookup_order", order_id="42"),
            expect.output_contains("shipped"),
        ]),
        Case("large refund", "Refund order 77", [
            expect.calls("escalate_to_human"),
            expect.never_calls("issue_refund"),
        ], must_pass=True),
    ],
)
```

```bash
agent-ratchet run tests/agent_suite.py --save-baseline   # once, on a version you trust
agent-ratchet run tests/agent_suite.py                   # on every change
```

Commit `.agent-ratchet/*.baseline.json`. It holds check names, pass or fail, cost and time: no prompts, answers or tool data. The full results of the last run stay in `*.latest.json`, which is kept out of git automatically.

## Running in CI or pytest

GitHub Actions:

```yaml
- run: agent-ratchet run tests/agent_suite.py
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

The results table appears on the pull request's checks page. A full workflow is in [examples/github_workflow.yml](examples/github_workflow.yml).

pytest:

```python
from agent_ratchet import assert_no_regressions
from agent_suite import suite

def test_support_agent():
    assert_no_regressions(suite)
```

Run `AGENT_RATCHET_UPDATE=1 pytest` to save or refresh the baseline.

## How it decides

1. Each case runs 3 times. The baseline ran it 10 times, once.
2. A case that does worse than its baseline gets more runs, up to 10. Cases that look fine cost nothing extra.
3. A case regresses when its drop is too large to be chance. The bar adjusts for how many cases could have regressed, so adding stable cases never makes the check less sensitive.
4. A must pass case fails the build on any failed run.
5. A case whose input or checks changed is reported as changed, not compared.

What that means, from 2,000 simulated pull requests per row ([benchmarks/gate_simulation.py](benchmarks/gate_simulation.py)):

- **False alarms:** 3% or less in every simulated suite, from 50 stable cases to 200 cases with 50 flaky ones.
- **Real drops,** one case among 49 others, 19 of them flaky:

| A case that passed... | ...now passes | Caught (default, up to 10 runs) | Caught (up to 20 runs) |
|---|---|---|---|
| 100% | 0% | 100% | 100% |
| 100% | 30% | 84% | 98% |
| 100% | 50% | 37% | 85% |
| 100% | 70% | 5% | 31% |

Big breaks are caught cheaply. Smaller drops need more runs, which you can buy with `--max-repeats 20`.

## What it costs to run

- **Every pull request:** cases × 3 runs, plus up to 7 more for each case that looks worse. A 50 case suite with some flaky cases averaged about 210 agent runs.
- **A baseline:** cases × 10 runs, once.
- The report shows the total cost of each run.

## Integrations

| Framework or tool | How |
|---|---|
| LangGraph and LangChain | `integrations.langgraph.wrap(graph)` |
| CrewAI | `integrations.crewai.wrap(build_crew)` |
| OpenAI Agents SDK | `integrations.openai_agents.wrap(agent)` |
| Google ADK | `integrations.google_adk.wrap(agent)` |
| Claude Agent SDK | `integrations.claude_agent_sdk.wrap(options)` |
| Langfuse | `agent-ratchet import langfuse <trace-id>` |
| OpenTelemetry GenAI | `agent-ratchet import otel spans.json` |
| Plain Python on the OpenAI, Anthropic or Gemini SDKs | `@tool` on your tool functions and `record_response(response)` |

Each integration is tested against the real framework with a scripted model. Examples are in [examples/frameworks](examples/frameworks) and setup notes in [docs/integrations.md](docs/integrations.md). For checks that rules can't express, model graders on Claude, OpenAI, Azure OpenAI and Gemini are built in.

## Roadmap

- Record and replay tool results, so CI runs never touch real systems.
- Stop early when a result is already clear, to cut runs further.
- Multi turn cases with a simulated user.

## Docs

- [Guide](docs/guide.md): checks, baselines, verdicts, budgets, CI, pytest and model graders
- [Integrations](docs/integrations.md): setup for every framework
- [Why this exists](docs/why.md): the problem we picked, what changed, and the options we weighed
- [Contributing](CONTRIBUTING.md)

MIT licensed.
