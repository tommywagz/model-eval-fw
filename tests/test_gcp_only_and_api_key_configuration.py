"""Tests verifying pipeline usability with ONLY a GCP project and endpoint location,
and configurable routing between Vertex (GCP) and direct API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from devbench.critics.panel import ActorCriticPanel
from devbench.models.base import BaseModelClient
from devbench.models.factory import get_model_client, load_model_registry
from devbench.models.providers import (
    OpenAICompatibleClient,
    VertexAnthropicClient,
    VertexEndpointClient,
    VertexGenAIClient,
    VertexMaaSClient,
)
from devbench.scenarios.runner import execute_scenario_run
from test_runner import build_arg_parser, main as top_level_runner_main


def test_only_gcp_project_and_location_resolves_all_models_to_vertex(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ensure that when ONLY GCP project and endpoint location are configured (no API keys),
    all models cleanly configure to use Vertex AI with the provided project and location.
    """
    # Clear all API keys and set ONLY GCP project and endpoint location
    api_key_vars = [
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "QWEN_API_KEY",
        "DASHSCOPE_API_KEY",
        "MINIMAX_API_KEY",
        "KIMI_API_KEY",
        "MOONSHOT_API_KEY",
    ]
    for v in api_key_vars:
        monkeypatch.delenv(v, raising=False)

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "gemini-api-505408")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.setenv("VERTEX_PROJECT_ID", "gemini-api-505408")
    monkeypatch.setenv("VERTEX_LOCATION", "global")

    # 1. Gemini candidate
    gemini_client = get_model_client("gemini-1.5-pro", mode="mock", cache_dir=tmp_path)
    assert isinstance(gemini_client, VertexGenAIClient)
    assert gemini_client.project_id == "gemini-api-505408"
    assert gemini_client.location == "global"
    assert gemini_client.resolve_use_vertex() is True

    # 2. Claude candidate / critic
    claude_client = get_model_client("claude-3-5-sonnet", mode="mock", cache_dir=tmp_path)
    assert isinstance(claude_client, VertexAnthropicClient)
    assert claude_client.project_id == "gemini-api-505408"
    assert claude_client.resolve_use_vertex() is True

    # 3. Dedicated Endpoint / MaaS candidate
    endpoint_client = get_model_client("mistral-large-latest", mode="mock", cache_dir=tmp_path)
    assert isinstance(endpoint_client, VertexEndpointClient)
    assert endpoint_client.project_id == "gemini-api-505408"
    assert "gemini-api-505408" in endpoint_client.endpoint_resource_name

    # 4. OpenAI compatible client with ONLY GCP project and location resolves to Vertex MaaS
    openai_client = get_model_client("critic-minimax", mode="mock", cache_dir=tmp_path)
    assert isinstance(openai_client, OpenAICompatibleClient)
    assert openai_client.resolve_use_vertex() is True


def test_configurable_routing_vertex_vs_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ensure a user can configure if they want to use a model via Vertex (GCP) or direct API key."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "custom-gcp-project")
    monkeypatch.setenv("VERTEX_LOCATION", "us-central1")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-anthropic-key")

    # A. Gemini routing configuration
    # Default with both GCP and API key -> defaults to Vertex
    gemini_default = get_model_client("gemini-1.5-pro", mode="mock", cache_dir=tmp_path)
    assert gemini_default.resolve_use_vertex() is True

    # Explicitly configure Vertex via use_vertex=True
    gemini_vertex = get_model_client("gemini-1.5-pro", mode="mock", use_vertex=True, cache_dir=tmp_path)
    assert gemini_vertex.resolve_use_vertex() is True

    # Explicitly configure API key via use_vertex=False
    gemini_key = get_model_client("gemini-1.5-pro", mode="mock", use_vertex=False, cache_dir=tmp_path)
    assert gemini_key.resolve_use_vertex() is False

    # Explicitly configure via auth_mode="api_key" vs "vertex"
    gemini_auth_key = get_model_client("gemini-1.5-pro", mode="mock", auth_mode="api_key", cache_dir=tmp_path)
    assert gemini_auth_key.resolve_use_vertex() is False

    gemini_auth_vertex = get_model_client("gemini-1.5-pro", mode="mock", auth_mode="vertex", cache_dir=tmp_path)
    assert gemini_auth_vertex.resolve_use_vertex() is True

    # B. Claude routing configuration
    claude_vertex = get_model_client("claude-3-5-sonnet", mode="mock", use_vertex=True, cache_dir=tmp_path)
    assert claude_vertex.resolve_use_vertex() is True

    claude_key = get_model_client("claude-3-5-sonnet", mode="mock", use_vertex=False, cache_dir=tmp_path)
    assert claude_key.resolve_use_vertex() is False

    claude_auth_key = get_model_client("claude-3-5-sonnet", mode="mock", auth_mode="api_key", cache_dir=tmp_path)
    assert claude_auth_key.resolve_use_vertex() is False


def test_live_invocations_respect_vertex_vs_api_key_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify live mode uses the right SDK and sets raw_response metadata for Vertex vs. API key."""
    class DummyGenAISDK:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def generate_content(self, **kwargs: Any) -> Any:
            class Resp:
                text = "gemini-output"
            return Resp()

    class DummyAnthropicSDK:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def messages_create(self, **kwargs: Any) -> Any:
            class Resp:
                text = "claude-output"
            return Resp()

    # 1. Gemini in Vertex mode
    client_v = VertexGenAIClient(
        mode="live",
        sdk_client=DummyGenAISDK(),
        project_id="test-proj",
        location="us-central1",
        use_vertex=True,
        no_cache=True,
    )
    resp_v = client_v.generate("test prompt")
    assert resp_v.text == "gemini-output"
    assert resp_v.raw_response.get("mode") == "vertex"

    # 2. Gemini in API key mode
    client_k = VertexGenAIClient(
        mode="live",
        sdk_client=DummyGenAISDK(),
        api_key="my-api-key",
        use_vertex=False,
        no_cache=True,
    )
    resp_k = client_k.generate("test prompt")
    assert resp_k.text == "gemini-output"
    assert resp_k.raw_response.get("mode") == "api_key"

    # 3. Claude in Vertex mode
    claude_v = VertexAnthropicClient(
        mode="live",
        sdk_client=DummyAnthropicSDK(),
        project_id="test-proj",
        location="us-east5",
        use_vertex=True,
        no_cache=True,
    )
    c_resp_v = claude_v.generate("test prompt")
    assert c_resp_v.text == "claude-output"
    assert c_resp_v.raw_response.get("mode") == "vertex"

    # 4. Claude in API key mode
    claude_k = VertexAnthropicClient(
        mode="live",
        sdk_client=DummyAnthropicSDK(),
        api_key="my-anthropic-key",
        use_vertex=False,
        no_cache=True,
    )
    c_resp_k = claude_k.generate("test prompt")
    assert c_resp_k.text == "claude-output"
    assert c_resp_k.raw_response.get("mode") == "api_key"


def test_actor_critic_panel_and_scenario_with_only_gcp_project_and_location(tmp_path: Path) -> None:
    """Verify that execute_scenario_run runs end-to-end with ONLY project_id and location specified,
    and both candidate and critic panel resolve to the specified GCP project and endpoint location.
    """
    cache_dir = tmp_path / "cache"
    critic_cache_dir = tmp_path / "critic_cache"
    telemetry_dir = tmp_path / "telemetry"

    res = execute_scenario_run(
        scenario_id="oauth_api_enablement",
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=cache_dir,
        critic_cache_dir=critic_cache_dir,
        telemetry_dir=telemetry_dir,
        project_id="gemini-api-505408",
        location="global",
        assess_provider_tokens=False,
    )
    assert res["passed"] is True
    assert res["execution_mode"] == "mock"
    assert res["actor_critic_scores"] is not None
    assert res["jev_evaluation"]["passed"] is True


def test_cli_flags_for_project_location_and_routing(tmp_path: Path) -> None:
    """Verify top-level test_runner.py parser supports --project, --location, --use-vertex, --use-api-key."""
    parser = build_arg_parser()
    args = parser.parse_args([
        "--scenario", "oauth_api_enablement",
        "--project", "my-gcp-proj",
        "--location", "europe-west4",
        "--use-vertex",
    ])
    assert args.project_id == "my-gcp-proj"
    assert args.location == "europe-west4"
    assert args.use_vertex is True

    args_key = parser.parse_args([
        "--scenario", "oauth_api_enablement",
        "--use-api-key",
        "--auth-mode", "api_key",
    ])
    assert args_key.use_api_key is True
    assert args_key.auth_mode == "api_key"

    # Test top-level runner execution with CLI project and location flags
    rc = top_level_runner_main([
        "--scenario", "oauth_api_enablement",
        "--model", "gemini-1.5-pro",
        "--mode", "mock",
        "--project", "gemini-api-505408",
        "--location", "global",
        "--cache-dir", str(tmp_path / "cli_cache"),
        "--telemetry-dir", str(tmp_path / "cli_telemetry"),
    ])
    assert rc == 0


def test_devbench_cli_dispatcher_with_project_and_location(tmp_path: Path) -> None:
    """Verify `devbench run` CLI accepts --project and --location flags."""
    from devbench.cli import main as cli_main

    rc = cli_main([
        "run",
        "--scenario", "oauth_api_enablement",
        "--model", "gemini-1.5-pro",
        "--mode", "mock",
        "--project", "gemini-api-505408",
        "--location", "global",
        "--cache-dir", str(tmp_path / "devbench_cache"),
        "--telemetry-dir", str(tmp_path / "devbench_telemetry"),
    ])
    assert rc == 0


def test_web_ui_initializes_from_env_gcp_project_and_location(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify web server initializes GCP runtime state from GOOGLE_CLOUD_PROJECT / VERTEX_LOCATION."""
    import devbench.ui.web.server as web_server

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "env-project-xyz")
    monkeypatch.setenv("VERTEX_LOCATION", "europe-west1")

    # Reset in-memory cached runtime state to force re-initialization
    with web_server.GCP_STATE_LOCK:
        web_server.GCP_RUNTIME_STATE = None

    state = web_server._ensure_gcp_runtime_state()
    assert state["project_id"] == "env-project-xyz"
    assert state["location"] == "europe-west1"
    assert "europe-west1" in state["available_locations"]

