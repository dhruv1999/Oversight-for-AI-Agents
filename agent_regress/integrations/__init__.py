"""Integrations: turn each framework's run into a Trajectory.

Each module works on the objects the framework already returns, so the framework itself is not a
dependency of agent-regress. `wrap(...)` helpers also do the running for you.

    openai_agents      OpenAI Agents SDK      wrap(agent), from_run_result(result)
    langgraph          LangGraph / LangChain   wrap(graph), from_state(state)
    crewai             CrewAI                  wrap(crew or crew factory)
    google_adk         Google ADK              wrap(agent), from_events(events)
    claude_agent_sdk   Claude Agent SDK        wrap(options), from_messages(messages)
    langfuse           Langfuse traces         fetch_trace, from_trace, evaluate_trace
    otel               OpenTelemetry GenAI     from_spans, load_otlp_json
"""
