from types import SimpleNamespace as NS

from oversight.adapters.anthropic_client import FALLBACK_BETA, AnthropicClient


class FakeSDK:
    """Mimics client.beta.messages.create."""

    def __init__(self, blocks, stop_reason="end_turn"):
        self.kwargs = None
        self.beta = NS(messages=self)
        self._blocks = blocks
        self._stop = stop_reason

    def create(self, **kwargs):
        self.kwargs = kwargs
        return NS(content=self._blocks, usage=NS(input_tokens=11, output_tokens=7), model="claude-opus-5-5", stop_reason=self._stop)


def test_request_shape():
    sdk = FakeSDK([NS(type="text", text='{"verdict":"allow"}')])
    AnthropicClient(model="claude-opus-5-5", max_tokens=123, effort="low", client=sdk).complete("SYS", "USER")
    k = sdk.kwargs
    assert k["model"] == "claude-opus-5-5" and k["max_tokens"] == 123
    assert k["system"] == "SYS" and k["messages"] == [{"role": "user", "content": "USER"}]
    assert k["output_config"]["effort"] == "low"
    assert k["betas"] == [FALLBACK_BETA] and k["fallbacks"] == "default"
    assert "temperature" not in k and "thinking" not in k


def test_json_schema_passed_through():
    sdk = FakeSDK([NS(type="text", text="{}")])
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    AnthropicClient(client=sdk, json_schema=schema).complete("s", "u")
    assert sdk.kwargs["output_config"]["format"] == {"type": "json_schema", "schema": schema}


def test_fallbacks_can_be_disabled():
    sdk = FakeSDK([NS(type="text", text="x")])
    AnthropicClient(client=sdk, fallbacks=False).complete("s", "u")
    assert "fallbacks" not in sdk.kwargs and "betas" not in sdk.kwargs


def test_response_mapping_joins_text_blocks_only():
    sdk = FakeSDK([NS(type="thinking", thinking=""), NS(type="text", text="a"), NS(type="fallback"), NS(type="text", text="b")], stop_reason="refusal")
    r = AnthropicClient(client=sdk).complete("s", "u")
    assert (r.text, r.input_tokens, r.output_tokens, r.model, r.stop_reason) == ("ab", 11, 7, "claude-opus-5-5", "refusal")


def test_settings_identify_request_shape():
    c = AnthropicClient(model="claude-opus-5-5", max_tokens=99, effort="low", client=FakeSDK([]))
    assert c.settings["max_tokens"] == 99 and c.settings["effort"] == "low" and c.settings["fallbacks"] is True
