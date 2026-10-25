# Guide

## The pieces

- **Case**: one input and the checks the agent must pass on it.
- **Suite**: your agent plus its cases. Each case runs `repeats` times.
- **Trajectory**: what one run did. Tool calls with arguments, results and errors, the final answer, model calls, tokens, cost and time.
- **Baseline**: a saved result from a version you trust. New runs are compared with it.

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

Argument values in `calls` can be exact values, compiled regular expressions or functions:

```python
import re
expect.calls("search", query=re.compile("refund policy", re.I))
expect.calls("issue_refund", amount=lambda a: a <= 500)
```

A check that raises an exception fails. It never passes silently.

## Recording tool calls from plain Python

If your agent is a plain function, decorate its tools. Inside a test run every call is recorded. Outside a run the decorator does nothing, so it can stay in production code.

```python
from agent_regress import tool, record_response

@tool
def lookup_order(order_id: str) -> dict: ...

def my_agent(message: str) -> str:
    response = client.messages.create(...)   # OpenAI, Anthropic or Gemini SDK
    record_response(response)                 # tokens, for cost checks
    ...
    return answer
```

Async tools and async agents work the same way.

## Cost

Some frameworks report cost (Claude Agent SDK, Langfuse). For the rest, give the suite your model's price per million tokens and cost is worked out from token counts:

```python
Suite(agent=..., cases=[...], price_per_mtok=(5.0, 25.0))   # input, output
```

## Baselines and regressions

```bash
agent-regress run suite.py --save-baseline    # keep this run as the baseline
agent-regress run suite.py                    # compare with it
```

Results go to `.agent-regress/`: `<suite>.latest.json` for the last run and `<suite>.baseline.json` for the baseline. Commit the baseline. Update it on purpose, when a change is meant to alter behaviour.

How a case is judged:

- **ok**: every run passed
- **flaky**: some runs passed
- **failing**: no run passed
- **regressed**: the pass rate dropped by `--tolerance` or more (0.3 by default)
- **improved**: the pass rate rose by that much
- **new** or **removed**: the case is only in one of the two results

Each pass rate has a 95% interval. When the drop could still be chance at this many runs, the report adds "check with more repeats". With 3 runs only a big drop is clear; with 10 runs smaller drops are.

## Budgets

Cost and time changes are always shown. To fail on them:

```bash
agent-regress run suite.py --max-cost-increase 0.25 --max-latency-increase 0.5
```

## Command line

```text
agent-regress run SUITE [--repeats N] [--case NAME] [--save-baseline] [--baseline FILE] [--dir DIR]
                        [--tolerance 0.3] [--max-cost-increase X] [--max-latency-increase X]
                        [--fail-on regression|failure|never] [--markdown FILE]
agent-regress compare NEW.json BASELINE.json
agent-regress import langfuse TRACE_ID [--name NAME]
agent-regress import otel SPANS.json [--name NAME]
```

Exit codes: 0 all good, 1 a regression (or any failure with `--fail-on failure`), 2 bad usage.

`--fail-on failure` is useful before you have a baseline: it fails whenever any run fails.

## CI

On GitHub Actions the Markdown report is added to the job summary automatically. See [examples/github_workflow.yml](../examples/github_workflow.yml).

Tips:

- Use 5 or more repeats in CI.
- Keep suites small and focused on behaviour that matters: refunds, escalations, data access, anything a customer would notice.
- Add a case for every bug you fix.

## Model graders

For things rules cannot capture, such as tone or correctness of free text:

```python
from agent_regress import expect, judges

expect.judge("The reply apologises and gives a delivery date.", judges.anthropic())
expect.judge("...", judges.openai(model="<model>"))
expect.judge("...", judges.openai(model="<deployment>", client=openai.AzureOpenAI(...)))
expect.judge("...", judges.gemini(model="<model>"))
expect.judge("...", my_function)   # any function: prompt in, text out
```

Install the SDK you need: `pip install "agent-regress[anthropic]"`, `[openai]` or `[gemini]`. Keys come from the usual environment variables.

Graders ask for structured output and treat the run as data. A grader that refuses, errors or answers in a way that cannot be read fails the check. Graders cost money and add noise of their own, so use rules where they fit.

## Running from Python

```python
result = suite.run()                # or: await suite.arun()
print(result.ok)
for case in result.cases:
    print(case.name, case.passes, case.n)
```

`agent_regress.compare(new, baseline)` and `agent_regress.report.text(...)` give you the same comparison and table the command line prints.
