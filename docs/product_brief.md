# Product brief

## The problem

Companies are giving AI agents real permissions: send the email, run the migration, pay the invoice, merge the fix. Everyone agrees a person should approve the risky ones. Nobody has a good answer for how many approvals a person can give before they stop reading.

Approval prompts today are all or nothing. Either every sensitive action asks (and people learn to click "yes"), or the agent is trusted with a list of allowed tools (and nobody looks at what it does with them). In hospitals, where this has been measured for twenty years, clinicians override most safety alerts, and each extra alert makes the next one less likely to be taken seriously. Agent approvals are heading the same way.

## Who has it

**Teams shipping agents** into operations, finance, support and engineering, who need a person in the loop for compliance or trust, but whose agents do hundreds of things a day.

**Developers running coding agents** who either approve every command or turn prompts off entirely.

**Platform and security teams** who have to show auditors why an agent was allowed to do something.

## What success looks like

The number that matters is harmful actions that got through. The number the user feels is how often they were interrupted. The product wins if it lowers the second without raising the first, and it is honest about what it costs (actions that have to wait).

Measured in simulation (see [results](results.md)): about half the interruptions of fixed approval rules, with no more harm getting through, across 11 changes to the underlying assumptions. The cost is a longer queue of actions waiting for the person.

## Decisions I made, and what I traded

**Treat attention as a budget, not a setting.** Existing tools ask "does this action need approval?". This one also asks "can this person still give a good approval right now?". That second question is the product.

**Critical actions always wait for a person.** Even if it means an agent sits idle overnight. Some decisions should never be delegated to software, and the product should not make that easy.

**When the person is out of attention, the automatic checker may stop things but not approve them.** This was a data driven change. In simulation, letting a merely decent checker approve risky actions made outcomes worse than having no smart routing at all. The cost is more waiting; I chose safety over throughput and made it a single, visible setting.

**Explain every decision in plain words.** Every answer comes with the steps that produced it, and every log line names the version of the rules that made it. People trust what they can audit.

**Meet developers where they are.** A decorator for any Python agent framework, a proxy for any MCP server, an HTTP service for everything else, a command line for scripts, and a ready made hook for Claude Code. Adoption dies if the first step is "rewrite your agent".

**Advisory before enforcement.** In Claude Code the hook can only add questions or blocks by default; it never approves anything on its own. A new safety tool has to earn the right to remove prompts.

## Why now

Agent frameworks are shipping tool use and human approval as built in features, and coding agents already run commands on developers' machines. The approval step exists everywhere; the attention behind it is not managed anywhere.

## Risks

**Wrong risk scores.** If the rules call a harmful action low risk, nobody reviews it. Mitigation: unknown tools start high, rules can only raise risk, and every decision is logged so bad scores can be found and fixed.

**The checker is only as good as it is.** The measured rules checker catches under half of the harmful actions in the test set. Mitigation: it may only block during takeover; an LLM checker plugs into the same interface.

**Simulated evidence.** The results come from made up workdays and a simulated person. The next step is a pilot with real approval logs.

## What comes next

1. Run the full evaluation with AI checkers from Anthropic, OpenAI, Azure and Google, and compare them on catch rate, false alarms and cost (all four are built; Claude is costed at about $4; needs API keys).
2. Pilot with one team's real approval logs to measure actual interruption and override rates.
3. Learn risk scores from those logs instead of hand setting them.
4. Support on call rotations: several reviewers, one shared budget each.
5. Score sequences of actions, not only single ones, to catch harm split into innocent looking steps.
