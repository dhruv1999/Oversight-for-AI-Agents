# Threat model

## What it protects against

An agent that is about to do something harmful, because it misunderstood the task, was tricked by text it read (prompt injection), or is simply wrong. The system decides who must look before the action runs.

## What it trusts and what it does not

The tool name and parameters are trusted as a description of what will actually run. The agent's own description of the action is not trusted: the risk score ignores it, and the automatic checker is told to judge the parameters, not the explanation.

## Known gaps

**Splitting.** A harmful plan broken into steps that each look harmless is not caught. Each action is judged on its own; there is no memory across actions yet.

**Disguise.** Harm hidden inside a low risk tool, such as writing a script file that deletes backups when it runs later, scores low and is never reviewed. Rules in `tools.yaml` for your own tools are the main defence.

**Draining attention.** An agent that triggers many harmless high risk actions can use up the interrupt budget. After that, high risk actions go to the automatic checker, which by default may block them but not approve them, so they wait for the person; critical actions still go straight to a person. In simulation this kept a scripted drain attack from getting easier ([results](results.md#can-an-agent-game-it)). An attacker that also fools the checker's block decision is not covered.

**Tricking the checker.** Text inside an action could try to talk an AI checker into approving it. The action is passed as clearly marked untrusted data and the answer must match a fixed format, which reduces but does not remove this risk.

**Local state.** The Claude Code hook keeps its state in `.oversight/`. Anything that can edit those files can reset the budget. The hook is a guardrail inside a trusted environment, not a sandbox.

**Unknown tools** get cautious defaults (high risk), so they reach a person or the checker rather than running unchecked.

## The review page

The page that `oversight serve` shows the person is a target in its own right, because whoever can press Approve there can let an action run.

**Markup from the agent.** Parameters and descriptions come from the agent and could contain HTML meant to mislead the reviewer. The page only ever inserts them as text, never as markup (a test fails if the page uses `innerHTML` or similar), and a strict content security policy with a fresh nonce on every load blocks any script the page did not ship with. A browser test plants markup in an action and checks it is shown as plain text.

**Other web sites.** A page the person happens to visit could send requests to the service on localhost. Without a token the service only answers requests addressed to localhost, which defeats DNS rebinding, and it refuses any request whose `Origin` is another site. With a token, every data request needs it, and a browser on another site cannot add it.

**Framing.** The page cannot be shown inside another site's frame (`frame-ancestors 'none'` and `X-Frame-Options: DENY`), so nobody can overlay it and trick a click on Approve.

**Not covered.** Anyone who can open the page from the same machine without a token can answer the queue. Set `OVERSIGHT_TOKEN` wherever more than one person can reach the service, and put it behind TLS if it leaves the machine.
