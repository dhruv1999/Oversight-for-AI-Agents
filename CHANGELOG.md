# Changelog

## 0.2.0

- `Oversight`: one object, one call per tool call; `protect` decorator for any Python agent framework; `register_tool` for your own tools.
- HTTP service (`oversight serve`), command line (`oversight check`), TypeScript client.
- Shared attention state across processes (`state=".oversight"`), with locking that works on Linux, macOS and Windows.
- Checkers fail closed on errors, refusals and the spending cap; secrets are removed from logs; every log line names the rules that decided.
- `takeover: veto` is the new default: when a person is out of attention, the checker may block high risk actions but not approve them.
- Evidence: paired statistics, robustness to 11 changed assumptions, ablations, a budget drain attack, a checker quality sweep and pacing.

## 0.1.0

- Risk scoring, attention budget, router, audit log, simulation and first results.
