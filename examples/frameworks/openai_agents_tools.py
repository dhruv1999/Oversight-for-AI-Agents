"""Oversight on OpenAI Agents SDK tools. Stack @function_tool on top of @guard.protect.

    uv run --with openai-agents python examples/frameworks/openai_agents_tools.py

The SDK still builds the tool schema from the original signature. When oversight refuses a call,
the SDK hands the refusal message back to the model as the tool result, so the agent can adapt.
Add an Agent(tools=[...]) and Runner.run(...) as usual; nothing else changes.
"""

import asyncio

from agents import function_tool
from agents.tool_context import ToolContext

from oversight import Oversight

guard = Oversight()
guard.register_tool("read_report", category="read", blast_radius="self")  # your own tool: say how risky it is


def ask_on_call(check) -> bool:
    """Replace with Slack, email or a button in your app."""
    print(f"  [person asked] {check.explain().splitlines()[0]} -> approved")
    return True


@function_tool
@guard.protect()
def read_report(name: str) -> str:
    """Read a sales report."""
    return f"(made up contents of {name})"


@function_tool
@guard.protect(ask=ask_on_call)
def pay_invoice(vendor: str, amount: float) -> str:
    """Pay an approved vendor invoice."""
    return f"paid ${amount:,.2f} to {vendor}"


@function_tool
@guard.protect(tool="run_sql")
def run_sql(database: str, query: str) -> str:
    """Run SQL against the company database."""
    return "ok"


async def main() -> None:
    for tool, args in [
        (read_report, '{"name": "q3_sales"}'),
        (pay_invoice, '{"vendor": "Acme Paper Co", "amount": 420}'),
        (run_sql, '{"database": "app_production", "query": "DROP TABLE orders"}'),
    ]:
        ctx = ToolContext(context=None, tool_name=tool.name, tool_call_id="demo", tool_arguments=args)
        print(f"{tool.name}: {await tool.on_invoke_tool(ctx, args)}")


if __name__ == "__main__":
    asyncio.run(main())
