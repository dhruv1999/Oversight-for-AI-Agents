"""Put oversight in front of any MCP server.

    oversight mcp -- npx -y @modelcontextprotocol/server-filesystem ~/project

Point your MCP client (Claude Desktop, Cursor, an agent framework) at this command instead of the
real server. The proxy starts the real server, offers exactly the same tools, and checks every call:

    may run      forwarded to the real server
    blocked      not forwarded; the client gets an error explaining why
    ask a person the proxy asks through MCP elicitation, so the client shows the user a yes or no
                 prompt; clients without elicitation get a refusal that says a person must approve
    must wait    not forwarded; the client is told the person is out of attention

Tool names are looked up in the tool registry, so a server whose tools are called `read_file` or
`write_file` gets those rules. Declare other tools with --tools (your own tools.yaml).
Needs the optional dependency: pip install "oversight-for-ai-agents[mcp]".
"""

from __future__ import annotations

from typing import Any

from ..guard import Check, Oversight

APPROVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"approve": {"type": "boolean", "title": "Approve this action?"}},
    "required": ["approve"],
}


def _refusal(text: str) -> Any:
    from mcp import types

    return types.CallToolResult(content=[types.TextContent(text=text)], is_error=True)


async def _ask_person(ctx: Any, check: Check) -> bool | None:
    """True/False from the person via elicitation, or None if the client cannot ask."""
    message = f"An agent wants to run {check.action.tool} ({check.risk} risk).\n\n{check.explain()}"
    try:
        result = await ctx.session.elicit(message, APPROVE_SCHEMA)
    except Exception:
        return None
    return result.action == "accept" and bool((result.content or {}).get("approve"))


def build_server(downstream: Any, tools: list[Any], guard: Oversight) -> Any:
    """An MCP server that offers `tools` and forwards allowed calls to the `downstream` session."""
    from mcp import types
    from mcp.server import Server

    async def on_list_tools(ctx: Any, params: Any) -> Any:
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx: Any, params: Any) -> Any:
        args = dict(params.arguments or {})
        check = guard.check(params.name, args, description=f"MCP tool call: {params.name}")
        if check.allowed:
            return await downstream.call_tool(params.name, args)
        if check.needs_person:
            approved = await _ask_person(ctx, check)
            if approved is None:
                return _refusal(f"{params.name} was not run: a person must approve it ({check.risk} risk), and this client cannot ask them.")
            guard.record_answer(check, approved, "answered through MCP elicitation")
            if approved:
                return await downstream.call_tool(params.name, args)
            return _refusal(f"{params.name} was not run: the person declined.")
        if check.waiting:
            return _refusal(f"{params.name} was not run: it needs a person, who is away or out of attention. Try again later.")
        return _refusal(f"{params.name} was not run: {check.reason}")

    return Server("oversight-proxy", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def run_proxy(command: str, args: list[str], guard: Oversight) -> None:
    from mcp import ClientSession, types
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.server.stdio import stdio_server

    params = StdioServerParameters(command=command, args=args)
    async with stdio_client(params) as (down_read, down_write), ClientSession(down_read, down_write) as downstream:
        await downstream.initialize()
        tools: list[Any] = []
        cursor = None
        while True:
            page = await downstream.list_tools(params=None if cursor is None else types.PaginatedRequestParams(cursor=cursor))
            tools.extend(page.tools)
            cursor = page.next_cursor
            if not cursor:
                break
        server = build_server(downstream, tools, guard)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
