# Integrations

Every integration goes through the same `Oversight.check`, so the rules, the interruption budget and the audit log behave the same way everywhere.

```
pip install git+https://github.com/dhruv1999/Oversight-for-AI-Agents
```

## Python

Put `@guard.protect` under whatever decorator your agent framework uses. The tool keeps its signature, so the framework still builds the right schema, and when a call is refused the agent receives a sentence explaining why.

```python
from oversight import Oversight

guard = Oversight()
guard.register_tool("read_report", category="read", blast_radius="self")  # tell it about your own tools


@function_tool  # OpenAI Agents SDK, or @tool for LangChain, or nothing at all
@guard.protect(ask=ask_on_slack)  # ask_on_slack(check) returns True or False; you decide how people are asked
def pay_invoice(vendor: str, amount: float) -> str: ...
```

You can also call it directly. `guard.check(tool, params)` tells you whether the action may run, needs a person, has to wait, or is blocked, and `check.explain()` gives the reasons. Call `guard.person_away()` and `guard.person_back()` when the reviewer steps out, and `guard.record_answer(check, approved=True)` to log what they decided.

Working examples, which CI runs against the real frameworks:

* [OpenAI Agents SDK](../examples/frameworks/openai_agents_tools.py)
* [LangChain](../examples/frameworks/langchain_tools.py)
* [Claude tool use loop](../examples/agent_loop.py)

## MCP

Run the proxy in place of the server. It starts the real server, offers exactly the same tools, and checks every call before forwarding it. When a person is needed it asks through the client's own approval prompt (MCP elicitation). A client that cannot ask gets a refusal that says why.

```json
{"mcpServers": {"filesystem": {"command": "oversight",
  "args": ["mcp", "--", "npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/project"]}}}
```

This needs the optional MCP dependency:

```
pip install "oversight-for-ai-agents[mcp] @ git+https://github.com/dhruv1999/Oversight-for-AI-Agents"
```

Tool names the rules do not recognise start as high risk. Declare them in your own copy of `oversight/policies/tools.yaml` and pass it with `oversight --tools your_tools.yaml mcp -- <server command>`.

## HTTP, for any language

Run it as a small service and call it from anything that can send a request. A typed [TypeScript client](../examples/typescript/oversight.mts) is included.

```
oversight serve --port 8321 --state .oversight

curl -s localhost:8321/check -d '{"tool": "pay_invoice", "params": {"vendor": "Acme", "amount": 420}}'
{"call_id": "call-c7250ed81fc4", "outcome": "ask_human", "risk": "high",
 "reason": "high risk: escalate to human (human available within budget)", "reasons": [...], "rules": "223d398e6450+feb5c71ca9ae"}
```

The service also accepts `POST /answer` to record a person's decision and `POST /person` to mark them away or back. It listens on localhost only unless told otherwise, and `OVERSIGHT_TOKEN` turns on bearer token authentication.

## Claude Code

Claude Code's permission prompt becomes the person, and the budget decides how often it asks. Add this to `.claude/settings.json` in your project:

```json
{"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "oversight hook", "timeout": 30}]}]}}
```

The hook never approves anything by itself. It can only add a question or a block on top of what Claude Code already does. Decisions are logged in `.oversight/` in your project, with secrets removed.

## Command line

```
oversight check run_sql '{"query": "DROP TABLE orders"}'
```

This prints the decision and its reasons, then exits with 0 when the action may run, 2 when it is blocked, 3 when a person must decide, and 4 when it has to wait. Shell scripts and CI jobs can branch on that.
