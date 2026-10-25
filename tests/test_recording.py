import asyncio
import threading

import pytest

from agent_ratchet import record_response, record_usage, recording, tool


@tool
def add(a: int, b: int = 1) -> int:
    return a + b


@tool(name="fetch")
async def fetch_async(url: str) -> str:
    return f"<{url}>"


@tool
def broken() -> None:
    raise ValueError("nope")


def test_does_nothing_outside_a_run():
    assert add(1) == 2
    record_usage(10, 10)  # no error


def test_records_args_results_and_errors():
    with recording("q") as t:
        add(2, b=3)
        with pytest.raises(ValueError):
            broken()
        asyncio.run(fetch_async("x"))
        record_usage(100, 20, cost_usd=0.01)
    assert t.tools == ["add", "broken", "fetch"]
    assert t.tool_calls[0].args == {"a": 2, "b": 3} and t.tool_calls[0].result == 5
    assert t.tool_calls[1].error == "ValueError: nope"
    assert t.tool_calls[2].result == "<x>"
    assert (t.llm_calls, t.input_tokens, t.output_tokens, t.cost_usd) == (1, 100, 20, 0.01)


def test_runs_do_not_leak_between_threads():
    seen = {}

    def worker(i):
        with recording(i) as t:
            for _ in range(i):
                add(i)
        seen[i] = len(t.tool_calls)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert seen == {i: i for i in range(1, 6)}


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_record_response_reads_each_sdk_shape():
    with recording() as t:
        record_response(Obj(usage=Obj(input_tokens=10, output_tokens=2)))  # Anthropic, OpenAI Responses
        record_response(Obj(usage=Obj(prompt_tokens=5, completion_tokens=1)))  # OpenAI Chat Completions
        record_response(Obj(usage_metadata=Obj(prompt_token_count=7, candidates_token_count=3, thoughts_token_count=4)))  # Gemini
        record_response(Obj(usage=Obj(input_tokens=5, output_tokens=1, cache_read_input_tokens=100, cache_creation_input_tokens=20)))
    assert (t.llm_calls, t.input_tokens, t.output_tokens) == (4, 147, 11)
