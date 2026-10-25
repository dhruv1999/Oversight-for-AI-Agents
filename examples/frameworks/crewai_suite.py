"""CrewAI. Needs OPENAI_API_KEY (CrewAI's default model).   agent-regress run examples/frameworks/crewai_suite.py"""

from crewai import Agent, Crew, Task
from crewai.tools import tool

from agent_regress import Case, Suite, expect
from agent_regress.integrations.crewai import wrap


@tool("lookup_order")
def lookup_order(order_id: str) -> str:
    """Look up an order's status and amount."""
    return {"42": "shipped, $40", "77": "delivered, $900"}.get(order_id, "not found")


def build_crew(message: str) -> Crew:
    agent = Agent(role="Support agent", goal="Answer order questions", backstory="Careful and brief.", tools=[lookup_order])
    task = Task(description="Customer message: {input}", expected_output="A short reply to the customer", agent=agent)
    return Crew(agents=[agent], tasks=[task])


suite = Suite(
    agent=wrap(build_crew),
    name="support_crew",
    cases=[Case("order status", "Where is order 42?", [expect.calls("lookup_order", order_id="42"), expect.output_contains("shipped")])],
)
