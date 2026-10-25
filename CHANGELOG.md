# Changelog

## 0.1.0

First release of agent-ratchet.

- Behaviour checks for tool calls, arguments, order, errors, answers, cost, tokens and time
- Repeated runs per case, with extra runs only for cases that look worse than the baseline
- Verdicts from a Fisher exact test per case, with Tarone's adjustment so a suite with no real change rarely fails
- Must pass cases that fail the build on any failed run
- Baselines that hold no prompts, answers or tool data, safe to commit
- Run timeouts, and retries for provider errors such as rate limits
- Command line with CI exit codes and a Markdown summary for GitHub Actions, plus a pytest helper
- Integrations for LangGraph, CrewAI, OpenAI Agents SDK, Google ADK, Claude Agent SDK, Langfuse and OpenTelemetry GenAI
- `@tool` and `record_response` for plain Python agents on the OpenAI, Anthropic and Gemini SDKs
- Optional model graders on Claude, OpenAI, Azure OpenAI and Gemini
- Turn a production trace into a test case
