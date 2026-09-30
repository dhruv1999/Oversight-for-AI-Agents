# Build plan

The original plan lived in a separate chat. Phases 2 to 7 were rebuilt from the project principles; everything after that came from reviewing the work the way senior engineers, researchers and product leaders would.

| Phase | What | Status |
|---|---|---|
| 0 | Product brief, risk levels, harmful action families, checker choice | done ([product brief](product_brief.md), [risk levels](risk_taxonomy.md)) |
| 1 | Core: schema, policy, attention, router, log, metrics, demo | done |
| 2 | Checkers: LLM and rules, Anthropic adapter, answer cache, spending cap | done |
| 3 | Tool registry, synthetic action pool, workdays, availability schedules | done |
| 4 | Gate, comparison routers, simulated person, simulator | done |
| 5 | Experiments, charts, generated results report | done |
| 6 | Claude Code hook, Claude agent example | done |
| 7 | Docs, CI, license | done |
| 8 | Review fixes: fail closed on checker errors, secrets out of logs, race free shared state, packaged rules | done |
| 9 | Works with any agent: decorator, HTTP service, command line, TypeScript client, OpenAI Agents SDK and LangChain examples | done |
| 10 | Evidence: paired statistics, 11 assumption changes, ablations, budget drain attack, checker quality sweep, pacing | done |
| 11 | Engineering: Windows and macOS CI, latency benchmark, versioned audit log, architecture doc | done |

## Next

1. Full evaluation with an LLM checker (needs an API key; about $4).
2. Pilot on real approval logs.
3. Learn risk scores from logged decisions.
4. Several reviewers per team.
5. Score sequences of actions.
