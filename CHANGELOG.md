# Changelog

## Unreleased

- Review page in `oversight serve`: the person sees how much attention they have left, approves or rejects waiting and queued actions with a note for the audit log, and steps away or comes back. Protected against markup from the agent, other web sites and framing; tested in a real browser.
- `GET /checks/<call_id>` so an agent can wait for the answer given on the page; `"review-page"` option in the TypeScript client.
- `Check.summary`: one plain sentence saying what happens to an action and why. `Oversight.attention()`: questions used, limit and when the next one may come.
- Screenshots in the README, taken from the real page by `scripts/screenshots.py`.

## 0.2.0

- `Oversight`: one object, one call per tool call; `protect` decorator for any Python agent framework; `register_tool` for your own tools.
- HTTP service (`oversight serve`), command line (`oversight check`), TypeScript client.
- MCP proxy (`oversight mcp -- <server>`): oversight in front of any MCP server, asking people through MCP elicitation.
- Shared attention state across processes (`state=".oversight"`), with locking that works on Linux, macOS and Windows.
- Checkers fail closed on errors, refusals and the spending cap; secrets are removed from logs; every log line names the rules that decided.
- `takeover: veto` is the new default: when a person is out of attention, the checker may block high risk actions but not approve them.
- Evidence: paired statistics, robustness to 11 changed assumptions, ablations, a budget drain attack, a checker quality sweep and pacing.

## 0.1.0

- Risk scoring, attention budget, router, audit log, simulation and first results.
