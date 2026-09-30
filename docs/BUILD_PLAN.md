# Build plan

The original plan was written in a separate chat. Phases 2 to 7 below were rebuilt from the project principles and are all done.

| Phase | What | Status |
|---|---|---|
| 0 | Requirements, risk taxonomy, harmful action families, safety model choice | done (`docs/PRD.md`, `docs/risk_taxonomy.md`) |
| 1 | Core library: schema, policy, attention, allocator, log, metrics, demo | done |
| 2 | Safety model layer: LLM and rule based reviewers, Anthropic adapter, cache, spending cap | done |
| 3 | Tool registry, synthetic action pool, workday episodes, availability schedules | done |
| 4 | Gate, comparison routers, simulated human, simulator | done |
| 5 | Experiments, chart, generated results report | done |
| 6 | Claude Code hook and a gated Claude agent example | done |
| 7 | Docs, CI, license | done |

## Next

Run the experiments with Claude as the safety model and publish those results next to the rule based ones. Try the hook on real coding sessions and measure how often it asks. Add adapters for other providers.
