# Why agent-ratchet

## The question we started with

Which agent evaluation problem is big, painful, and still mostly solved by paid tools? Pick one, and solve it well.

## Four pain points

| Pain point | How it is solved | Open source gap |
|---|---|---|
| **1. Scoring a single run** | Many open source options: DeepEval, Ragas, Inspect, Phoenix evals | Small |
| **2. Multi turn simulation** | Paid: Maxim, Coval. Open source: LangWatch Scenario | Medium |
| **3. Catching regressions before merge** | Led by paid platforms: Braintrust, LangSmith | Looked large |
| **4. Turning production traces into tests** | Partly Langfuse datasets, mostly paid platforms | Medium, and only useful once you have a regression suite |

We picked **3**, with 4 folded in as a feature: production traces are the best source of new regression cases.

## Three solutions

| Option | Trade off |
|---|---|
| A. Record and replay tool results | Fast and cheap, but replayed runs can hide real changes in behaviour |
| **B. Behaviour checks, repeated runs, a baseline diff** | Works with any framework and model, no hosted service, handles randomness. Costs real model calls |
| C. A model judge comparing old and new answers | Easy to start, but noisy, costly, and blind to failures in the steps |

We picked **B**. C is available as an optional check. A is on the roadmap, as a way to make B cheaper and safer.

## What changed when we checked again

By October 2026 the open source gap in point 3 had mostly closed:

- **Langfuse** (MIT) added CI gates for experiments in May 2026, with a GitHub Action that marks a pull request as passed or regressed.
- **promptfoo** (open source, acquired by OpenAI in March 2026) has a GitHub Action that compares results before and after a change.
- **llmci** (Apache 2.0, May 2026) is a gate before merge, with baselines, confidence intervals and agent tool constraints, driven by YAML.
- **AgentAssay** (AGPL, March 2026, with a paper) does statistical agent regression testing with adaptive run counts.
- **agent-regress-cli** (Apache 2.0, July 2026) compares two versions with about 50 runs each and tests whether the difference is significant.

So by our own rule, regression gating is no longer an open source gap. We weighed two options: move to another problem, or stay and win a narrower position.

## Why we stayed

The problem is still real, and what remains unsolved is specific:

- **Most gates check an average.** Langfuse's own guide warns that a better average can hide a regression on a critical case. agent-ratchet gives a verdict per behaviour.
- **The statistical tools are costly or restrictive.** Fixed runs of about 50 per version are expensive on every pull request. AGPL rules out many companies. agent-ratchet adds runs only where a case looks worse, and it is MIT licensed.
- **Setup is heavy.** Most need a server, a hosted dataset or a YAML config. agent-ratchet is Python checks and a baseline file, with native capture for six frameworks.

Moving to another problem without users would restart the clock. Shipping a sharper version of this one gets real feedback sooner.

## What review caught

- **Our first rule was the problem we set out to solve.** It ran each case 3 times and failed on any 30 point drop. In simulation, a suite with just 10 cases that pass 90% of the time failed 89% of pull requests where nothing changed. The current rule uses a Fisher exact test per case, adjusts the bar across the suite (Tarone's method), and reruns only cases that look worse. In the same simulations, false alarms stay at 3% or less.
- **The name clashed.** agent-regress-cli already uses the import name `agent_regress`, so installing both would break one. We renamed the project agent-ratchet before its first release.
- **Baselines leaked data.** They stored full runs and were meant to be committed. They now hold only check names, pass or fail, cost and time.

## What we will not build

- Production monitoring and scoring dashboards. That is a different job, done well by Langfuse and the paid platforms.
- A hosted service.
- Prompt optimisation.

## How we will know it works

- A new user gets a working gate in under 10 minutes.
- False alarms stay under 5% in real repositories, not only in simulation.
- Early users report regressions it caught before merge.
- Repositories keep it switched on in CI after a month.

## Which frameworks

The most used agent frameworks by GitHub activity in 2026, plus the two trace formats teams already export:

- CrewAI, LangGraph, OpenAI Agents SDK, Google ADK, Claude Agent SDK
- Langfuse and OpenTelemetry GenAI spans
- Plain loops on the OpenAI, Anthropic and Gemini SDKs

## Sources

- Agent evaluation landscape: [Future AGI guide](https://futureagi.substack.com/p/the-definitive-guide-to-ai-agent), [LangChain on agent evals](https://www.langchain.com/resources/agent-evals), [MLflow on agent evaluation frameworks](https://mlflow.org/top-5-agent-evaluation-frameworks/)
- Platform comparisons: [MarkTechPost, August 2026](https://www.marktechpost.com/2026/08/09/top-llm-observability-and-evaluation-platforms-in-2026-langfuse-langsmith-braintrust-arize-and-more-compared/), [Atlan](https://atlan.com/know/ai-agent/ai-agent-evals/best-ai-agent-evaluation-platforms/)
- Langfuse CI gates: [experiments in CI/CD](https://langfuse.com/docs/evaluation/experiments/experiments-ci-cd), [changelog](https://langfuse.com/changelog/2026-05-25-experiment-ci-cd-gates), [comparing experiments](https://langfuse.com/docs/evaluation/experiments/compare-experiments)
- promptfoo: [CI/CD integration](https://promptfoo.dev/docs/integrations/ci-cd/), [acquisition, March 2026](https://securityboulevard.com/2026/03/openai-acquires-security-startup-promptfoo-to-fortify-ai-agents)
- Statistical gates: [llmci](https://pypi.org/project/llmci/), [agent-regress-cli](https://pypi.org/project/agent-regress-cli/), [AgentAssay](https://pypi.org/project/agentassay/)
- Thresholds in other tools: [DeepEval in CI](https://mer.vin/2026/06/deepeval-explained-pytest-style-llm-evals-for-agents-rag-and-ci-cd/), [Google ADK evaluation codelab](https://codelabs.developers.google.com/adk-eval/instructions)
- Simulation tools: [Future AGI on open source simulation tools](https://futureagi.com/blog/open-source-ai-agent-simulation-tools/)
- Framework popularity: [Agentailor, 2026](https://blog.agentailor.com/posts/top-ai-agent-frameworks-github-2026)
- Statistics: Fisher's exact test; R. E. Tarone, "A modified Bonferroni method for discrete data", Biometrics, 1990
