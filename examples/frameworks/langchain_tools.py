"""Oversight on LangChain tools. Stack @tool on top of @guard.protect.

    uv run --with langchain-core python examples/frameworks/langchain_tools.py

Works the same with LangGraph agents, since they call these tools. Set handle_tool_error=True on a
tool (pay_invoice.handle_tool_error = True) to return a refusal to the model as text instead of raising it.
"""

from langchain_core.tools import tool

from oversight import ActionBlocked, Oversight

guard = Oversight()
guard.register_tool("read_report", category="read", blast_radius="self")  # your own tool: say how risky it is


@tool
@guard.protect()
def read_report(name: str) -> str:
    """Read a sales report."""
    return f"(made up contents of {name})"


@tool
@guard.protect()
def pay_invoice(vendor: str, amount: float) -> str:
    """Pay an approved vendor invoice."""
    return f"paid ${amount:,.2f} to {vendor}"


if __name__ == "__main__":
    print(read_report.invoke({"name": "q3_sales"}))
    try:
        print(pay_invoice.invoke({"vendor": "Acme Paper Co", "amount": 420}))
    except ActionBlocked as e:
        print(e)
