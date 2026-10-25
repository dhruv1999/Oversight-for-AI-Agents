# Why agent-regress

## The question

Which agent evaluation problem, as of late 2026, is big, painful, and still mostly solved by paid tools?

## Four pain points we weighed

| Pain point | How it is solved today | Gap for open source |
|---|---|---|
| **1. Scoring a single run** (was this answer good, was the tool call right) | Many open source options: DeepEval, Ragas, Inspect, Phoenix evals | Small. Well covered. |
| **2. Multi turn simulation** (a fake user talks to the agent) | Paid: Maxim, Coval. Open source: LangWatch Scenario (Apache 2.0) | Medium. A solid open source option exists. |
| **3. Catching regressions in CI** (did this change make the agent worse) | Paid platforms lead: Braintrust, LangSmith. promptfoo is now owned by OpenAI and focuses on prompts and red teaming. Open source agent focused options are small and young. | **Large.** |
| **4. Turning production traces into tests** | Partly covered by Langfuse datasets, and by the paid platforms | Medium, and it only matters once you have a regression suite to feed. |

**We picked 3.** It is the moment every team hits: someone changes a prompt or upgrades the model, and nobody knows what broke until a customer finds it. The paid platforms solve it well, inside their clouds and at per seat prices. We folded 4 into it as a feature, because production traces are the best source of new regression cases.

## Three solutions we weighed

| Option | How it works | Trade off |
|---|---|---|
| **A. Record and replay** | Record tool results once, replay them so runs are repeatable | Great for speed and cost, but replayed runs can hide real changes in behaviour. Small projects exist (replayd, agent replay, replayproof, Chronicle). |
| **B. Behaviour contracts, repeated runs, baseline diff** | Write what the agent must and must not do, run each case several times, compare pass rates with a saved baseline | Works with any framework and any model, needs no hosted service, and handles randomness honestly. Costs real model calls per run. |
| **C. Model judge comparing old and new answers** | A model decides whether the new answer is worse than the old one | Easy to start, but noisy, costly, and it misses failures in the steps when the answer reads fine. |

**We picked B**, with C available as an optional check (`expect.judge`) and A on the roadmap.

- Contracts check the steps, not just the answer, which is where agent failures hide.
- Repeated runs and intervals make "it passed once" into "it passes 5 out of 5".
- A baseline file in the repository keeps everything local, reviewable and free.

## Which frameworks

We support the most used agent frameworks by GitHub activity in 2026, plus the two tracing formats teams already export.

- CrewAI, LangGraph, OpenAI Agents SDK, Google ADK, Claude Agent SDK
- Langfuse (open source tracing) and OpenTelemetry GenAI spans (the vendor neutral format)
- Plain loops on the OpenAI, Anthropic and Gemini SDKs, through a decorator

## Sources

- Agent evaluation landscape: [Future AGI guide](https://futureagi.substack.com/p/the-definitive-guide-to-ai-agent), [LangChain on agent evals](https://www.langchain.com/resources/agent-evals), [Morph](https://www.morphllm.com/ai-agent-evaluation), [MLflow on agent evaluation frameworks](https://mlflow.org/top-5-agent-evaluation-frameworks/)
- Platform comparisons: [MarkTechPost, August 2026](https://www.marktechpost.com/2026/08/09/top-llm-observability-and-evaluation-platforms-in-2026-langfuse-langsmith-braintrust-arize-and-more-compared/), [Atlan](https://atlan.com/know/ai-agent/ai-agent-evals/best-ai-agent-evaluation-platforms/), [Latitude vs Braintrust](https://latitude.so/blog/agent-first-comparison-guide-vs-braintrust)
- promptfoo acquisition: [Security Boulevard, March 2026](https://securityboulevard.com/2026/03/openai-acquires-security-startup-promptfoo-to-fortify-ai-agents)
- Simulation tools: [Future AGI on open source simulation tools](https://futureagi.com/blog/open-source-ai-agent-simulation-tools/)
- Record and replay: [agent replay](https://github.com/xeeshan16/agent-replay), [Chronicle (arXiv 2609.20625)](https://arxiv.org/pdf/2609.20625)
- OpenTelemetry GenAI conventions: [TrueFoundry overview](https://www.truefoundry.com/blog/opentelemetry-genai-semantic-conventions)
- Framework popularity: [Agentailor, 2026](https://blog.agentailor.com/posts/top-ai-agent-frameworks-github-2026), [DEV Community](https://dev.to/devopsdaily/top-5-ai-agent-frameworks-in-2026-30dj)
