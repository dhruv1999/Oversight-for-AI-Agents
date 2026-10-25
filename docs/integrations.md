# Integrations

agent-ratchet has no required dependencies. Each integration uses the framework you already have installed.

Your suite's `agent` can be:

- a `wrap(...)` from one of the integrations below, which runs the agent for you
- your own function (plain or async) that returns whatever your framework returns: it is read automatically
- your own function that returns a string, with tools decorated by `@tool`

## LangGraph and LangChain

```python
from agent_ratchet.integrations.langgraph import wrap
suite = Suite(agent=wrap(graph), cases=[...])
```

Works with any compiled graph whose state has a `messages` list, including agents from `langchain.agents.create_agent`. Reads tool calls, tool errors (`ToolMessage` status), the final answer and token usage. Every run gets its own `thread_id`, so with a checkpointer one run never sees another's messages. Example: [langgraph_suite.py](../examples/frameworks/langgraph_suite.py).

## CrewAI

```python
from agent_ratchet.integrations.crewai import wrap
suite = Suite(agent=wrap(build_crew), cases=[...])   # build_crew(input) returns a fresh Crew
```

The input is passed as `inputs={"input": ...}`, so use `{input}` in a task description (change the key with `input_key=`). Tool calls are read from CrewAI's event bus during the run. Crew runs are serialised because that bus is shared by the process. Example: [crewai_suite.py](../examples/frameworks/crewai_suite.py).

## OpenAI Agents SDK

```python
from agent_ratchet.integrations.openai_agents import wrap
suite = Suite(agent=wrap(agent), cases=[...])        # extra Runner.run options: wrap(agent, max_turns=5)
```

Reads tool calls, handoffs, tool errors, the final output and usage. Example: [openai_agents_suite.py](../examples/frameworks/openai_agents_suite.py).

## Google ADK

```python
from agent_ratchet.integrations.google_adk import wrap
suite = Suite(agent=wrap(root_agent), cases=[...])
```

Each run uses a fresh in memory session. Reads function calls and responses, the final response and token usage (thinking tokens included). Example: [google_adk_suite.py](../examples/frameworks/google_adk_suite.py).

## Claude Agent SDK

```python
from agent_ratchet.integrations.claude_agent_sdk import wrap
suite = Suite(agent=wrap(ClaudeAgentOptions(...)), cases=[...])
```

Reads tool use and results (including errors), the final result, cost, tokens and turns. A run that ends with an error result counts as a failed run. Example: [claude_agent_sdk_suite.py](../examples/frameworks/claude_agent_sdk_suite.py).

## Plain Python on the OpenAI, Anthropic or Gemini SDKs

Decorate your tools with `@tool` and pass each model response to `record_response`:

```python
from agent_ratchet import tool, record_response

@tool
def lookup_order(order_id: str) -> str: ...

response = client.messages.create(...)          # or client.chat.completions.create, or client.models.generate_content
record_response(response)
```

Example: [raw_sdk_suite.py](../examples/frameworks/raw_sdk_suite.py).

## Langfuse

Turn a production trace into a test case:

```bash
export LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=... LANGFUSE_HOST=https://cloud.langfuse.com
agent-ratchet import langfuse <trace-id> --name "refund over limit"
```

It prints a `Case(...)` to paste into your suite: the same tools, in the same order, without errors. Tighten it by hand. This is the fastest way to build a suite: start from the conversations that went wrong in production.

Uses Langfuse's public API directly, so the Langfuse SDK is not needed. Tools are read from observations of type TOOL, and model calls from GENERATION. To read a trace in Python:

```python
from agent_ratchet.integrations.langfuse import fetch_trace, from_trace
traj = from_trace(fetch_trace("<trace-id>"))
```

## OpenTelemetry GenAI

For any tool that exports spans following the OpenTelemetry GenAI conventions:

```bash
agent-ratchet import otel spans.json
```

```python
from agent_ratchet.integrations.otel import from_spans, load_otlp_json
traj = from_spans(load_otlp_json("spans.json"))          # OTLP JSON, one document or one per line
traj = from_spans(exporter.get_finished_spans())         # spans captured in a test
```

Reads `execute_tool` spans as tool calls and `chat` spans for usage and messages. The GenAI conventions are still marked as in development, so attribute names may change.

## Something else

Return a `Trajectory` from your agent function and every check works:

```python
from agent_ratchet import ToolCall, Trajectory

def my_agent(message):
    ...
    return Trajectory(output=answer, tool_calls=[ToolCall("search", {"q": message}, result=hits)])
```
