# Guide

## The pieces

- **Case**: one input and the checks the agent must pass on it.
- **Suite**: your agent plus its cases. Each case runs several times, because agents are random.
- **Trajectory**: what one run did. Tool calls with arguments, results and errors, the final answer, model calls, tokens, cost and time.
- **Baseline**: pass rates from a version you trust, saved in your repo. New runs are compared with it.

## Checks

All checks come from `expect` and run without calling a model.

| Check | Passes when |
|---|---|
| `calls(tool, **args)` | the tool is called at least once with matching arguments |
| `calls(tool, times=2)` | the tool is called exactly twice |
| `never_calls(*tools)` | none of these tools is called |
| `only_calls(*tools)` | no other tool is called |
| `calls_in_order(*tools)` | these tools are called in this order (others may come in between) |
| `no_tool_errors()` | no tool call failed |
| `output_contains(*texts)` | the final answer contains every text (case insensitive by default) |
| `output_not_contains(*texts)` | the final answer contains none of them |
| `output_matches(pattern)` | the final answer matches a regular expression |
| `max_tool_calls(n)`, `max_llm_calls(n)`, `max_tokens(n)` | the run stays within the limit |
| `max_cost(usd)`, `max_latency(seconds)` | the run stays within the budget |
| `check(fn, name)` | your own function of the trajectory returns True |
| `judge(rubric, grader)` | a model says the run meets the rubric |

Argument values in `calls` can be exact values, regular expressions, types, or functions:

```python
import re
expect.calls("search", query=re.compile("refund policy", re.I))
expect.calls("issue_refund", amount=lambda a: a <= 500)
expect.calls("create_ticket", priority=int)
```

A check that raises an exception fails. It never passes silently.

## Must pass cases

Some behaviours are guardrails: never refund without an order number, never delete an account. Mark them and any failed run fails the build, with or without a baseline.

```python
Case("refund needs an order number", "Refund my last order", [expect.never_calls("issue_refund")], must_pass=True)
```

## Recording tool calls from plain Python

If your agent is a plain function, decorate its tools. Inside a test run every call is recorded. Outside a run the decorator does nothing, so it can stay in production code.

```python
from agent_ratchet import tool, record_response

@tool
def lookup_order(order_id: str) -> dict: ...

def my_agent(message: str) -> str:
    response = client.messages.create(...)   # OpenAI, Anthropic or Gemini SDK
    record_response(response)                 # tokens, for cost checks
    ...
    return answer
```

Async tools and async agents work the same way.

## Baselines

```bash
agent-ratchet run suite.py --save-baseline    # run each case 10 times and keep the result
agent-ratchet run suite.py                    # compare with it
```

- The baseline runs every case `max_repeats` times (10 by default). It is a one time cost, and more runs make every later comparison sharper.
- Results go to `.agent-ratchet/`. Commit `<suite>.baseline.json`. It holds check names, pass or fail, cost and time: no prompts, answers or tool data.
- `<suite>.latest.json` holds the full last run for debugging, and a `.gitignore` keeps it out of git.
- Update the baseline on purpose, when a change is meant to alter behaviour. Saving with `--case` updates only those cases.
- If you edit a case's input or checks, it shows as **changed** until you save a new baseline, instead of being compared with numbers that no longer fit it.

## How a case is judged

| Status | Meaning |
|---|---|
| **ok** | every run passed |
| **flaky** | some runs passed, and that is no worse than the baseline |
| **failing** | no run passed, and that is no worse than the baseline |
| **REGRESSED** | the pass rate dropped by more than chance explains. Fails the build |
| **FAILED (must pass)** | a must pass case failed at least once. Fails the build |
| **improved** | the pass rate rose by more than chance explains |
| **new**, **changed**, **removed** | the case is new, was edited, or is gone since the baseline |

The steps:

1. Each case runs `repeats` times (3 by default).
2. A case whose pass rate is below its baseline's gets more runs, up to `max_repeats`. Cases that look fine cost nothing extra.
3. Each case gets a one sided Fisher exact test: how likely is a drop this large if nothing changed?
4. The threshold is 5%, divided across the cases that could have regressed (Tarone's method). Cases with no failures on either side cannot regress and do not count, so a big suite of stable cases keeps full sensitivity.
5. A case that dropped but not by enough is reported as "could be chance", with a hint to run more.

`--confidence 0.99` makes the bar stricter.

### What to expect

From [benchmarks/gate_simulation.py](../benchmarks/gate_simulation.py), 2,000 simulated pull requests per row:

| Suite with no real change | Pull requests that fail |
|---|---|
| 50 cases, all stable | 0.0% |
| 50 cases, 10 pass 90% of the time | 0.4% |
| 50 cases, 10 at 90%, 10 at 70% | 2.4% |
| 200 cases, 30 at 90%, 20 at 60% | 3.0% |
| 50 cases, every one at 50% | 2.7% |

| One case gets worse, among 49 others (19 flaky) | Caught, up to 10 runs | Caught, up to 20 runs |
|---|---|---|
| 100% to 0% | 100% | 100% |
| 100% to 30% | 84% | 98% |
| 100% to 50% | 37% | 85% |
| 100% to 70% | 5% | 31% |
| 90% to 50% | 19% | 45% |

Big breaks are caught cheaply. Smaller drops need more runs: `--max-repeats 20`, or a larger `max_repeats` on the suite. For behaviour that must never break, use must pass instead of waiting for statistics.

The test assumes runs are independent. Provider errors are retried so they do not count against the agent, but a long outage during a run can still make failures cluster.

## Reliability

- **Timeouts.** A run that takes longer than `timeout` seconds (300 by default) is stopped and counted as failed, so a hung call never stalls CI.
- **Retries.** A run that hits a provider error, such as a rate limit, an overload or a dropped connection, is retried up to `retries` times (2 by default) with a growing wait. Errors from your own code are not retried.
- **Concurrency.** `concurrency` runs at a time (4 by default).

```python
Suite(agent=..., cases=[...], repeats=3, max_repeats=10, timeout=300, retries=2, concurrency=4)
```

## Cost

Some frameworks report cost (Claude Agent SDK, Langfuse). For the rest, give the suite your model's price per million tokens:

```python
Suite(agent=..., cases=[...], price_per_mtok=(5.0, 25.0))   # input, output
```

Cost and time changes are always shown. To fail on them:

```bash
agent-ratchet run suite.py --max-cost-increase 0.25 --max-latency-increase 0.5
```

## Command line

```text
agent-ratchet run SUITE [--repeats N] [--max-repeats N] [--case NAME] [--save-baseline] [--baseline FILE]
                        [--dir DIR] [--confidence 0.95] [--max-cost-increase X] [--max-latency-increase X]
                        [--fail-on regression|failure|never] [--markdown FILE]
agent-ratchet compare NEW.json BASELINE.json
agent-ratchet import langfuse TRACE_ID [--name NAME]
agent-ratchet import otel SPANS.json [--name NAME]
```

Exit codes: 0 all good; 1 a regression, a failed must pass case, or any failure with `--fail-on failure`; 2 bad usage or a suite file that could not be loaded.

## CI

On GitHub Actions the Markdown report is added to the job summary automatically. See [examples/github_workflow.yml](../examples/github_workflow.yml).

- Commit the baseline, and refresh it from your main branch now and then: providers update models behind the same name. Reports remind you when a baseline is over 30 days old.
- Keep suites focused on behaviour that matters: refunds, escalations, data access, anything a customer would notice.
- Add a case for every bug you fix.

## pytest

```python
from agent_ratchet import assert_no_regressions
from agent_suite import suite

def test_support_agent():
    assert_no_regressions(suite)
```

- `AGENT_RATCHET_UPDATE=1 pytest` saves or refreshes the baseline.
- On your machine a missing baseline is created on the first run. In CI (when `CI` is set) a missing baseline fails the test, so a forgotten baseline never passes silently.
- The helper is synchronous. Inside async tests, use `await suite.arun(baseline=...)` and `compare`.

## Model graders

For things rules cannot capture, such as tone or the correctness of free text:

```python
from agent_ratchet import expect, judges

expect.judge("The reply apologises and gives a delivery date.", judges.anthropic())
expect.judge("...", judges.openai(model="<model>"))
expect.judge("...", judges.openai(model="<deployment>", client=openai.AzureOpenAI(...)))
expect.judge("...", judges.gemini(model="<model>"))
expect.judge("...", my_function)   # any function: prompt in, text out
```

- Install the SDK you need: `pip install "agent-ratchet[anthropic]"`, `[openai]` or `[gemini]`. Keys come from the usual environment variables.
- Graders ask for structured output and treat the run as data. A grader that refuses, errors or answers in a way that cannot be read fails the check.
- For OpenAI reasoning models, pass `reasoning_effort`. It is off by default because other models reject it.
- Graders send the run to the model provider, cost money, and add noise of their own. Use rules where they fit.

## Running from Python

```python
result = suite.run(baseline=".agent-ratchet/support.baseline.json")   # or: await suite.arun(...)
comparison = compare(result, SuiteResult.load(".agent-ratchet/support.baseline.json"))
print(report.text(result, comparison))
```

`result.ok`, `result.must_pass_failures`, `comparison.ok` and `comparison.regressions` give you the same verdicts the command line uses.
