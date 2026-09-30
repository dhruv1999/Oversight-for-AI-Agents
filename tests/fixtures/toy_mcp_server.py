"""A tiny MCP server with made up tools, used to test the oversight proxy."""

from mcp.server.mcpserver import MCPServer

app = MCPServer("toy")


@app.tool()
def read_file(path: str) -> str:
    """Read a file."""
    return f"contents of {path}"


@app.tool()
def pay_invoice(vendor: str, amount: float) -> str:
    """Pay an invoice."""
    return f"paid {amount} to {vendor}"


@app.tool()
def run_sql(database: str, query: str) -> str:
    """Run SQL."""
    return f"ran {query}"


if __name__ == "__main__":
    app.run()
