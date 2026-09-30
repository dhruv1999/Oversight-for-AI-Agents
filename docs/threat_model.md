# Threat model

## What it protects against

An agent that is about to do something harmful, because it misunderstood the task, was tricked by text it read (prompt injection), or is simply wrong. The system decides who must look before the action runs.

## What it trusts and what it does not

The tool name and parameters are trusted as a description of what will actually run. The agent's own description of the action is not trusted: the risk score ignores it, and the automatic checker is told to judge the parameters, not the explanation.

## Known gaps

**Splitting.** A harmful plan broken into steps that each look harmless is not caught. Each action is judged on its own; there is no memory across actions yet.

**Disguise.** Harm hidden inside a low risk tool, such as writing a script file that deletes backups when it runs later, scores low and is never reviewed. Rules in `tools.yaml` for your own tools are the main defence.

**Draining attention.** An agent that triggers many harmless high risk actions can use up the interrupt budget. After that, high risk actions go to the automatic checker with a stricter bar, and critical actions still go to a person. The budget protects the person's attention, not the checker's accuracy.

**Tricking the checker.** Text inside an action could try to talk an AI checker into approving it. The action is passed as clearly marked untrusted data and the answer must match a fixed format, which reduces but does not remove this risk.

**Local state.** The Claude Code hook keeps its state in `.oversight/`. Anything that can edit those files can reset the budget. The hook is a guardrail inside a trusted environment, not a sandbox.

**Unknown tools** get cautious defaults (high risk), so they reach a person or the checker rather than running unchecked.
