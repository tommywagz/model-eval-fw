"""Tests for Pillar 1: Unified Model Provider & Endpoint Abstraction Layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from devbench.models.base import BaseModelClient, ModelResponse
from devbench.models.factory import get_model_client, load_model_registry
from devbench.models.providers import (
    OpenAICompatibleClient,
    VertexAnthropicClient,
    VertexEndpointClient,
    VertexGenAIClient,
    VertexMaaSClient,
)


def test_model_response_dataclass_fields() -> None:
    resp = ModelResponse(
        text="Generated completion",
        raw_response={"id": "resp-123"},
        input_tokens=42,
        output_tokens=84,
        latency_ms=15.5,
        finish_reason="STOP",
    )
    assert resp.text == "Generated completion"
    assert resp.raw_response == {"id": "resp-123"}
    assert resp.input_tokens == 42
    assert resp.output_tokens == 84
    assert resp.latency_ms == 15.5
    assert resp.finish_reason == "STOP"


def test_base_model_client_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseModelClient(alias="test", model_name="test", provider="test")  # type: ignore[abstract]


def test_model_registry_contains_candidates_and_critics() -> None:
    registry = load_model_registry()
    expected_aliases = [
        "gemini-3.5-flash",
        "gemini-3.1-pro",
        "gemini-3.8-flash",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "critic-qwen",
        "critic-minimax",
        "critic-kimi-k",
        "grok-2-mini",
        "llama-3.1-8b",
        "muse",
        "mistral-small",
        "eleven-labs",
    ]
    for alias in expected_aliases:
        assert alias in registry, f"Missing model alias '{alias}' in configs/models.yaml"
        assert registry[alias]["generation_defaults"]["temperature"] == 0.0


@pytest.mark.parametrize(
    "alias,expected_cls",
    [
        ("gemini-3.5-flash", VertexGenAIClient),
        ("gemini-3.1-pro", VertexGenAIClient),
        ("claude-sonnet-4-6", VertexAnthropicClient),
        ("claude-sonnet-4-5", VertexAnthropicClient),
        ("grok-2-mini", VertexMaaSClient),
        ("llama-3.1-8b", VertexMaaSClient),
        ("muse", VertexMaaSClient),
        ("mistral-small", VertexMaaSClient),
        ("eleven-labs", VertexMaaSClient),
        ("critic-qwen", VertexEndpointClient),
        ("critic-minimax", OpenAICompatibleClient),
        ("critic-kimi-k", OpenAICompatibleClient),
    ],
)
def test_factory_get_model_client_instantiates_correct_provider(
    alias: str,
    expected_cls: type[BaseModelClient],
    tmp_path: Path,
) -> None:
    client = get_model_client(alias=alias, mode="mock", cache_dir=tmp_path)
    assert isinstance(client, expected_cls)
    assert isinstance(client, BaseModelClient)

    gen_resp = client.generate("Write a modular service handler.", system_instruction="Be concise.")
    assert isinstance(gen_resp, ModelResponse)
    assert len(gen_resp.text) > 0
    assert gen_resp.input_tokens > 0
    assert gen_resp.output_tokens > 0
    assert gen_resp.latency_ms > 0.0
    assert gen_resp.finish_reason == "STOP"

    chat_resp = client.chat(
        [
            {"role": "system", "content": "You are a helpful cloud architect."},
            {"role": "user", "content": "Design an OAuth 2.0 flow."},
        ]
    )
    assert isinstance(chat_resp, ModelResponse)
    assert len(chat_resp.text) > 0


@pytest.mark.parametrize(
    "older_alias",
    [
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "claude-3-5-sonnet",
        "claude-3-5-haiku",
    ],
)
def test_older_models_cannot_be_configured(older_alias: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot be configured"):
        get_model_client(alias=older_alias, mode="mock", cache_dir=tmp_path)


def test_providers_live_mode_with_injected_sdk_mocks(tmp_path: Path) -> None:
    class DummyGenAISDK:
        def generate_content(self, **kwargs: Any) -> Any:
            class Resp:
                text = "live-gemini-response"
            return Resp()

    class DummyAnthropicSDK:
        def messages_create(self, **kwargs: Any) -> Any:
            class Resp:
                text = "live-claude-response"
            return Resp()

    class DummyEndpointSDK:
        def predict(self, **kwargs: Any) -> Any:
            class Resp:
                predictions = ["live-endpoint-response"]
            return Resp()

    class DummyOpenAISDK:
        def chat_completions_create(self, **kwargs: Any) -> Any:
            class Resp:
                text = "live-openai-compat-response"
            return Resp()

    genai_client = VertexGenAIClient(mode="live", sdk_client=DummyGenAISDK(), no_cache=True)
    assert genai_client.generate("ping").text == "live-gemini-response"

    anthropic_client = VertexAnthropicClient(mode="live", sdk_client=DummyAnthropicSDK(), no_cache=True)
    assert anthropic_client.generate("ping").text == "live-claude-response"

    endpoint_client = VertexEndpointClient(mode="live", sdk_client=DummyEndpointSDK(), no_cache=True)
    assert endpoint_client.generate("ping").text == "live-endpoint-response"

    openai_client = OpenAICompatibleClient(mode="live", sdk_client=DummyOpenAISDK(), no_cache=True)
    assert openai_client.generate("ping").text == "live-openai-compat-response"
