# Changelog

## 0.1.0

First release of agent-regress.

- Behaviour checks for tool calls, arguments, order, errors, answers, cost, tokens and time
- Repeated runs per case with pass rates and 95% intervals
- Baseline comparison that flags regressions and improvements, with cost and time budgets
- Command line with CI exit codes and a Markdown summary for GitHub Actions
- Integrations for LangGraph, CrewAI, OpenAI Agents SDK, Google ADK, Claude Agent SDK, Langfuse and OpenTelemetry GenAI
- `@tool` and `record_response` for plain Python agents on the OpenAI, Anthropic and Gemini SDKs
- Optional model graders on Claude, OpenAI, Azure OpenAI and Gemini
- Turn a production trace into a test case
