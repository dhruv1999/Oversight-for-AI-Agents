import json

from conftest import traj

from agent_ratchet import ToolCall, expect, judges, snapshot
from agent_ratchet.snapshot import case_code


def test_snapshot_makes_a_case_the_run_passes():
    t = traj(ToolCall("lookup", {"id": 1}), "refund", output="Refunded.")
    case = snapshot(t, "refund flow")
    assert case.input == "hi" and all(c(t).passed for c in case.expect)
    assert not all(c(traj("refund", "lookup")).passed for c in case.expect)
    code = case_code(t, "refund flow")
    assert "expect.calls_in_order('lookup', 'refund')" in code and "Refunded." in code
    from agent_ratchet import Case  # noqa: F401  the generated code must evaluate

    assert eval(code.rstrip(",")).name == "refund flow"


def test_judge_parses_and_fails_safe():
    prompts = []

    def grader(answer):
        def llm(prompt):
            prompts.append(prompt)
            return answer

        return llm

    t = traj("lookup", output="Order 42 shipped.")
    assert expect.judge("answers the question", grader('{"passed": true, "reason": "fine"}'))(t).passed
    assert "Order 42 shipped." in prompts[0] and "answers the question" in prompts[0]
    r = expect.judge("x", grader('Sure! ```{"passed": false, "reason": "rude"}```'))(t)
    assert not r.passed and r.detail == "rude"
    assert not expect.judge("x", grader("I think it passed"))(t).passed
    assert not expect.judge("x", grader('{"passed": "yes"}'))(t).passed

    def refuses(prompt):
        raise judges.JudgeError("declined")

    r = expect.judge("x", refuses)(t)
    assert not r.passed and "declined" in r.detail


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeAnthropic:
    def __init__(self, stop_reason="end_turn"):
        self.kwargs = None
        self.beta = Obj(messages=Obj(create=self.create))
        self.stop_reason = stop_reason

    def create(self, **kwargs):
        self.kwargs = kwargs
        return Obj(stop_reason=self.stop_reason, content=[Obj(type="text", text=json.dumps({"passed": True, "reason": "ok"}))])


class FakeOpenAI:
    def __init__(self, refusal=None):
        self.kwargs = None
        self.chat = Obj(completions=Obj(create=self.create))
        self.refusal = refusal

    def create(self, **kwargs):
        self.kwargs = kwargs
        return Obj(choices=[Obj(message=Obj(content='{"passed": false, "reason": "no"}', refusal=self.refusal))])


def test_anthropic_grader_request():
    client = FakeAnthropic()
    assert expect.judge("x", judges.anthropic(client=client))(traj()).passed
    k = client.kwargs
    assert k["model"] == "claude-opus-5-5" and k["output_config"]["format"]["type"] == "json_schema"
    assert k["fallbacks"] == "default" and k["betas"] == ["server-side-fallback-2026-07-01"]
    r = expect.judge("x", judges.anthropic(client=FakeAnthropic("refusal")))(traj())
    assert not r.passed and "declined" in r.detail


def test_openai_grader_request():
    client = FakeOpenAI()
    r = expect.judge("x", judges.openai("some-model", client=client))(traj())
    assert not r.passed and r.detail == "no"
    assert client.kwargs["response_format"]["json_schema"]["strict"] is True
    assert "reasoning_effort" not in client.kwargs  # models without reasoning reject it
    expect.judge("x", judges.openai("some-model", client=client, reasoning_effort="low"))(traj())
    assert client.kwargs["reasoning_effort"] == "low"
    assert not expect.judge("x", judges.openai("m", client=FakeOpenAI(refusal="no")))(traj()).passed
