# Contributing

Thanks for looking. A few things keep this project trustworthy, so please keep them in mind.

**Run `make check` before sending anything.** It runs lint, formatting, type checks and the tests, and fails on file handling that would break on Windows.

**Numbers come from scripts.** Nothing in the README or `docs/results.md` is typed by hand. If you change something that affects results, run `make reproduce` and commit the new `results/` and `figures/` with your change.

**The router stays deterministic.** No model calls, clocks or randomness in `policy.py`, `attention.py` or `allocator.py`. Model calls belong in `safety_model.py`, provider SDKs in `oversight/adapters/`. Tests enforce this.

**Fail closed.** Any new failure path should end in "ask a person", never in "allow".

**Synthetic data only.** Use reserved domains (`.test`, `.example`) and documentation IP ranges. Never add real names, emails, keys or logs.

Good first contributions: a new provider adapter, a Redis `StateStore`, rules for your own tools in `tools.yaml`, or new harmful action templates in `oversight/sim/scenarios.py`.
