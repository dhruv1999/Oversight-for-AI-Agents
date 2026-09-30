# Design

## Flow

1. The agent proposes a tool call: a tool name, parameters and a short description.
2. `ToolRegistry` turns it into an `Action` with risk metadata. Rules in `oversight/policies/tools.yaml` can only raise risk, and unknown tools get cautious defaults.
3. `Policy` scores the action and assigns a tier.
4. `Allocator` picks a route from the tier and the `AttentionTracker`.
5. `OversightGate` runs the safety model when the route calls for it and returns one of: execute, block, ask a human, or defer.
6. The caller owns the human channel (a console prompt, Claude Code's permission prompt, or the simulated human) and reports the answer back to the gate for logging.

## Modules

| Module | Job |
|---|---|
| `guard.py` | `Oversight`, the simple entry point: one object, one call per tool call, thread safe |
| `schema.py` | Action, Decision, SafetyVerdict and the enums |
| `policy.py` | loads and checks the policy file, scores actions |
| `registry.py` | risk metadata from tool name and parameters |
| `attention.py` | availability, interrupt budget, minimum gap; time is always passed in |
| `allocator.py` | the adaptive router |
| `baselines.py` | routers used for comparison |
| `gate.py` | ties routing, safety model and logging together |
| `safety_model.py` | LLM reviewer and rule based reviewer, the only place model calls start |
| `adapters/` | provider SDK code (Anthropic today) |
| `cache.py`, `spend.py`, `pricing.py` | response cache and spending cap |
| `human.py` | console reviewer and simulated reviewer |
| `redact.py` | removes secrets from everything written to disk |
| `sim/` | synthetic actions, workdays, availability schedules, simulator |
| `integrations/claude_code_hook.py` | Claude Code PreToolUse hook |

## Rules the tests enforce

Provider SDKs are imported only inside `adapters/`. A crashing, missing or over budget checker becomes "ask a person", never "allow". Secrets are removed from logs. Parallel Claude Code hooks share the interrupt budget through a file lock. The router, policy and attention code import no model code and never read the clock or use randomness. Model calls go only through the safety model.

## Simulation

A workday is eight hours of agent actions (about one every five minutes, 8% harmful) drawn from a fixed pool of 295 synthetic actions. The human is available according to one of three schedules: focused, in meetings, or away. The simulated human catches 95% of harmful actions when fresh and loses accuracy after more than six reviews in an hour. Actions that wait for an absent human are reviewed together when the human comes back, which counts as one interrupt. Anything still waiting at the end of the day does not run.
