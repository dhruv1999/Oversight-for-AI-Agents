"""OpenAI, Azure OpenAI and Gemini checkers, driven through the real SDKs against a local stub server.

Proves each SDK accepts our arguments, shows the exact request each provider would receive, and
checks how refusals, token counts and prices are handled. No network, no keys, no spend.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from oversight import Oversight
from oversight.adapters import make_client
from oversight.safety_model import VERDICT_SCHEMA

openai = pytest.importorskip("openai")
genai = pytest.importorskip("google.genai")
from google.genai import types  # noqa: E402

VERDICT = '{"verdict": "allow", "confidence": 0.9, "rationale": "routine test run"}'


def chat_reply(content=VERDICT, refusal=None, finish="stop", model="gpt-test-2026"):
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content, "refusal": refusal}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 400, "completion_tokens": 60, "total_tokens": 460},
    }


def gemini_reply(text=VERDICT, finish="STOP", thought=None, block=None):
    parts = ([{"text": thought, "thought": True}] if thought else []) + [{"text": text}]
    reply = {
        "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
        "usageMetadata": {"promptTokenCount": 400, "candidatesTokenCount": 60, "thoughtsTokenCount": 140, "totalTokenCount": 600},
        "modelVersion": "gemini-test-001",
    }
    if block:
        reply = {"promptFeedback": {"blockReason": block}, "usageMetadata": {"promptTokenCount": 400, "totalTokenCount": 400}}
    return reply


class Stub:
    def __init__(self):
        self.requests = []
        self.reply = {}
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                stub.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                out = json.dumps(stub.reply).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    @property
    def last(self):
        return self.requests[-1]


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    s = Stub()
    threading.Thread(target=s.server.serve_forever, daemon=True).start()
    yield s
    s.server.shutdown()


def openai_sdk(stub):
    return openai.OpenAI(api_key="test-key", base_url=stub.url + "/v1", max_retries=0)


def gemini_sdk(stub):
    return genai.Client(api_key="test-key", http_options=types.HttpOptions(base_url=stub.url))


# --- OpenAI ---------------------------------------------------------------------------------


def test_openai_request_and_response(stub):
    stub.reply = chat_reply()
    r = make_client("openai", "gpt-test", json_schema=VERDICT_SCHEMA, client=openai_sdk(stub)).complete("SYS", "USER")
    req = stub.last
    assert req["path"] == "/v1/chat/completions" and req["headers"]["authorization"] == "Bearer test-key"
    body = req["body"]
    assert body["model"] == "gpt-test"
    assert body["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "USER"}]
    assert body["max_completion_tokens"] == 2048 and body["reasoning_effort"] == "low"
    assert body["response_format"] == {"type": "json_schema", "json_schema": {"name": "verdict", "schema": VERDICT_SCHEMA, "strict": True}}
    assert (r.text, r.input_tokens, r.output_tokens, r.model, r.stop_reason) == (VERDICT, 400, 60, "gpt-test-2026", "stop")


def test_openai_reasoning_effort_can_be_left_out_for_older_models(stub):
    stub.reply = chat_reply()
    make_client("openai", "gpt-test", client=openai_sdk(stub), reasoning_effort=None).complete("s", "u")
    assert "reasoning_effort" not in stub.last["body"] and "response_format" not in stub.last["body"]


@pytest.mark.parametrize(
    "reply, stop",
    [
        (chat_reply(content=None, refusal="I can't help with that."), "refusal"),
        (chat_reply(content="", finish="content_filter"), "refusal"),
        (chat_reply(content='{"verdict": "al', finish="length"), "max_tokens"),
    ],
)
def test_openai_refusals_and_cut_off_replies(stub, reply, stop):
    stub.reply = reply
    assert make_client("openai", "gpt-test", client=openai_sdk(stub)).complete("s", "u").stop_reason == stop


# --- Azure OpenAI ---------------------------------------------------------------------------


def test_azure_request_goes_to_the_deployment(stub):
    stub.reply = chat_reply(model="gpt-test-2026")
    sdk = openai.AzureOpenAI(api_key="test-key", azure_endpoint=stub.url, api_version="2024-10-21", max_retries=0)
    r = make_client("azure", "oversight-checker", json_schema=VERDICT_SCHEMA, client=sdk).complete("SYS", "USER")
    req = stub.last
    assert req["path"] == "/openai/deployments/oversight-checker/chat/completions?api-version=2024-10-21"
    assert req["headers"]["api-key"] == "test-key"
    assert req["body"]["response_format"]["json_schema"]["strict"] is True
    assert r.stop_reason == "stop" and r.text == VERDICT


def test_azure_reads_its_settings_from_the_environment(stub, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", stub.url)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_API_VERSION", "2024-10-21")
    stub.reply = chat_reply()
    make_client("azure", "my-deployment").complete("s", "u")
    assert stub.last["path"].startswith("/openai/deployments/my-deployment/") and stub.last["headers"]["api-key"] == "env-key"


# --- Gemini ---------------------------------------------------------------------------------


def test_gemini_request_and_response(stub):
    stub.reply = gemini_reply(thought="thinking it over")
    r = make_client("gemini", "gemini-test", json_schema=VERDICT_SCHEMA, client=gemini_sdk(stub)).complete("SYS", "USER")
    req = stub.last
    assert req["path"].endswith("/models/gemini-test:generateContent") and req["headers"]["x-goog-api-key"] == "test-key"
    body = req["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert body["contents"][0]["parts"][0]["text"] == "USER"
    config = body["generationConfig"]
    assert config["maxOutputTokens"] == 2048 and config["responseMimeType"] == "application/json"
    thinking = config["thinkingConfig"]  # this SDK version sends the snake_case name; the API accepts both spellings
    assert thinking.get("thinkingLevel", thinking.get("thinking_level")) == "LOW"
    assert "additionalProperties" not in json.dumps(config["responseJsonSchema"])
    assert config["responseJsonSchema"]["required"] == ["verdict", "confidence", "rationale"]
    assert r.text == VERDICT  # the thought part is not part of the answer
    assert (r.input_tokens, r.output_tokens, r.model, r.stop_reason) == (400, 200, "gemini-test-001", "stop")  # thinking is billed as output


@pytest.mark.parametrize("reply", [gemini_reply(text="", finish="SAFETY"), gemini_reply(block="PROHIBITED_CONTENT")])
def test_gemini_blocked_answers_are_refusals(stub, reply):
    stub.reply = reply
    assert make_client("gemini", "gemini-test", client=gemini_sdk(stub)).complete("s", "u").stop_reason == "refusal"


# --- One way in for every provider ----------------------------------------------------------


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_checker_end_to_end_with_custom_price_and_cache(stub, tmp_path, provider):
    stub.reply = chat_reply() if provider == "openai" else gemini_reply()
    sdk = openai_sdk(stub) if provider == "openai" else gemini_sdk(stub)
    guard = Oversight.with_llm(provider, model="test-model", price_per_mtok=(1.0, 2.0), state_dir=tmp_path, client=sdk)
    check = guard.check("run_tests", {"path": "tests/"})
    assert check.allowed and check.summary == "The automatic checker reviewed it and found nothing wrong."
    assert guard.check("run_tests", {"path": "tests/"}).allowed and len(stub.requests) == 1  # the second answer came from the cache
    ledger = [json.loads(line) for line in (tmp_path / "spend_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    out = 60 if provider == "openai" else 200
    assert ledger == [{"model": "test-model", "input_tokens": 400, "output_tokens": out, "cost_usd": (400 * 1.0 + out * 2.0) / 1e6}]


def test_refusal_from_any_provider_means_a_person_decides(stub, tmp_path):
    stub.reply = chat_reply(content=None, refusal="no")
    guard = Oversight.with_llm("openai", model="test-model", price_per_mtok=(1.0, 2.0), state_dir=tmp_path, client=openai_sdk(stub))
    assert guard.check("run_tests", {}).needs_person


def test_spending_cap_applies_to_custom_prices(stub, tmp_path):
    stub.reply = chat_reply()
    guard = Oversight.with_llm("openai", model="test-model", price_per_mtok=(1000.0, 1000.0), max_spend_usd=0.01, state_dir=tmp_path, client=openai_sdk(stub))
    assert guard.check("run_tests", {}).needs_person and stub.requests == []  # refused before any call


def test_a_price_is_required_for_models_without_a_built_in_one(tmp_path):
    with pytest.raises(ValueError, match="price_per_mtok"):
        Oversight.with_llm("openai", model="gpt-test", state_dir=tmp_path, client=object())
    free = Oversight.with_llm("openai", model="local-model", price_per_mtok=(0, 0), state_dir=tmp_path, client=object())
    assert free.safety_model.client.price_per_mtok == (0, 0)


def test_bad_provider_or_missing_model_is_a_clear_error():
    with pytest.raises(ValueError, match="unknown provider"):
        make_client("cohere", "x")
    with pytest.raises(ValueError, match="Azure deployment name"):
        make_client("azure")
    assert make_client("anthropic", client=object()).model == "claude-opus-5-5"
