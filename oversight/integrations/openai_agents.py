"""OpenAI Agents SDK support.

Since version 0.23 the SDK hides tool exceptions from the model and returns a generic message.
That is the right default for unexpected errors, but an oversight refusal is written for the agent
to read: it says why the action was stopped, so the agent can choose another way. Pass this helper
as the tool's failure_error_function:

    from oversight.integrations.openai_agents import tool_error_message

    @function_tool(failure_error_function=tool_error_message)
    @guard.protect()
    def pay_invoice(vendor: str, amount: float) -> str: ...

Oversight refusals reach the model; every other error stays hidden behind the SDK's generic text.
No import of the SDK is needed here.
"""

from __future__ import annotations

from typing import Any

from ..guard import ActionBlocked

GENERIC = "An error occurred while running the tool. Please try again."


def tool_error_message(ctx: Any, error: BaseException) -> str:
    seen: set[int] = set()
    e: BaseException | None = error
    while e is not None and id(e) not in seen:  # the SDK may wrap the original exception
        if isinstance(e, ActionBlocked):
            return str(e)
        seen.add(id(e))
        e = e.__cause__ or e.__context__
    return GENERIC
