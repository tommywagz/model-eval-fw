"""Tests for Vertex CLI curl requests, direct REST prompting, model access error trapping, and UI pop-up metadata."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from devbench.models.base import VertexModelAccessError
from devbench.models.factory import get_model_client
from devbench.models.providers.vertex_anthropic import VertexAnthropicClient
from devbench.models.providers.vertex_genai import VertexGenAIClient
from devbench.models.vertex_rest import (
    build_vertex_curl_command,
    execute_vertex_rest_prompt,
)
from devbench.ui.web.server import (
    get_gcp_config_Snapshot,
    link_gcp_project,
    update_gcp_config,
    verify_model_access,
)


def test_build_vertex_curl_commands():
    """Verify equivalent shell curl commands are generated with gcloud auth application-default print-access-token."""
    # 1. Gemini
    gemini_cmd = build_vertex_curl_command(
        model_name="gemini-1.5-pro",
        prompt="Explain cloud architecture",
        project_id="test-proj-123",
        location="us-central1",
        system_instruction="You are a cloud architect.",
        publisher="google",
    )
    assert "curl -X POST" in gemini_cmd
    assert "us-central1-aiplatform.googleapis.com" in gemini_cmd
    assert "projects/test-proj-123/locations/us-central1/publishers/google/models/gemini-1.5-pro:generateContent" in gemini_cmd
    assert 'Authorization: Bearer $(gcloud auth application-default print-access-token)' in gemini_cmd
    assert "Explain cloud architecture" in gemini_cmd
    assert "You are a cloud architect." in gemini_cmd

    # 2. Anthropic Claude
    claude_cmd = build_vertex_curl_command(
        model_name="claude-3-5-sonnet-v2@20241022",
        prompt="Synthesize an agent skill",
        project_id="test-proj-123",
        location="us-east5",
        publisher="anthropic",
    )
    assert "publishers/anthropic/models/claude-3-5-sonnet-v2@20241022:rawPredict" in claude_cmd
    assert 'Authorization: Bearer $(gcloud auth application-default print-access-token)' in claude_cmd
    assert "vertex-2023-10-16" in claude_cmd

    # 3. Model-as-a-Service (Mistral / Llama)
    maas_cmd = build_vertex_curl_command(
        model_name="mistralai/mistral-large-2411",
        prompt="Refactor this function",
        project_id="test-proj-123",
        location="us-central1",
        publisher="mistralai",
    )
    assert "endpoints/openapi/chat/completions" in maas_cmd
    assert 'Authorization: Bearer $(gcloud auth application-default print-access-token)' in maas_cmd


def test_client_as_curl_command_method():
    """Test that model clients expose `as_curl_command` for easy CLI execution."""
    gemini_client = VertexGenAIClient(
        model_name="gemini-1.5-flash",
        project_id="my-gcp-project",
        location="us-central1",
    )
    cmd = gemini_client.as_curl_command("Hello Gemini", system_instruction="Be concise")
    assert "gemini-1.5-flash:generateContent" in cmd
    assert "gcloud auth application-default print-access-token" in cmd
    assert "Be concise" in cmd

    claude_client = VertexAnthropicClient(
        model_name="claude-3-5-sonnet-v2@20241022",
        project_id="my-gcp-project",
        location="us-east5",
    )
    claude_cmd = claude_client.as_curl_command("Hello Claude")
    assert "claude-3-5-sonnet-v2@20241022:rawPredict" in claude_cmd


def test_execute_vertex_rest_prompt_success():
    """Test executing a prompt directly via HTTP REST mock."""
    gemini_mock_resp = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Cloud Run scales automatically."}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 15,
            "candidatesTokenCount": 6,
        },
    }

    mock_resp_obj = MagicMock()
    mock_resp_obj.read.return_value = json.dumps(gemini_mock_resp).encode("utf-8")
    mock_resp_obj.__enter__.return_value = mock_resp_obj

    with patch("urllib.request.urlopen", return_value=mock_resp_obj):
        resp = execute_vertex_rest_prompt(
            model_name="gemini-1.5-pro",
            prompt="How does Cloud Run scale?",
            project_id="my-proj",
            location="us-central1",
            access_token="mock-oauth-token",
            publisher="google",
        )

    assert resp.text == "Cloud Run scales automatically."
    assert resp.input_tokens == 15
    assert resp.output_tokens == 6
    assert resp.raw_response["engine"] == "vertex_rest"


def test_execute_vertex_rest_prompt_permission_denied_raises_model_access_error():
    """Test that GCP 403 / PERMISSION_DENIED is caught and converted to VertexModelAccessError."""
    error_body = json.dumps(
        {
            "error": {
                "code": 403,
                "message": "Vertex AI Model Garden model 'publishers/anthropic/models/claude-3-5-sonnet' has not been enabled for project '123456'.",
                "status": "PERMISSION_DENIED",
            }
        }
    ).encode("utf-8")

    mock_http_err = urllib.error.HTTPError(
        url="https://us-east5-aiplatform.googleapis.com/...",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=MagicMock(read=MagicMock(return_value=error_body)),
    )

    with patch("urllib.request.urlopen", side_effect=mock_http_err):
        with pytest.raises(VertexModelAccessError) as exc_info:
            execute_vertex_rest_prompt(
                model_name="claude-3-5-sonnet",
                prompt="Ping",
                project_id="test-proj-403",
                location="us-east5",
                access_token="mock-token",
                publisher="anthropic",
            )

    err = exc_info.value
    assert err.status_code == 403
    assert err.error_status == "PERMISSION_DENIED"
    assert "has not been enabled for project" in err.message
    assert "gcloud auth application-default login" in err.remediation
    assert "https://console.cloud.google.com/vertex-ai/model-garden?project=test-proj-403" in err.remediation

    d = err.to_dict()
    assert d["error_type"] == "MODEL_ACCESS_DENIED"
    assert d["model_id"] == "claude-3-5-sonnet"
    assert d["project_id"] == "test-proj-403"


def test_vertex_genai_and_anthropic_clients_support_curl_auth_mode():
    """Verify clients invoke the REST/curl engine when auth_mode='vertex_rest' or 'curl'."""
    with patch("devbench.models.vertex_rest.execute_vertex_rest_prompt") as mock_exec:
        from devbench.models.base import ModelResponse

        mock_exec.return_value = ModelResponse(
            text="Mocked REST output",
            raw_response={"engine": "vertex_rest"},
            input_tokens=10,
            output_tokens=5,
            latency_ms=12.5,
        )

        client = get_model_client(
            alias="gemini-1.5-pro",
            mode="live",
            no_cache=True,
            auth_mode="vertex_rest",
            project_id="test-proj-curl",
            location="us-central1",
        )
        resp = client.generate("Test prompt via curl/REST unique 9999")
        assert resp.text == "Mocked REST output"
        assert mock_exec.called
        kwargs = mock_exec.call_args[1]
        assert kwargs["project_id"] == "test-proj-curl"
        assert kwargs["location"] == "us-central1"


def test_web_ui_model_verify_returns_model_access_denied_structure():
    """Verify /api/gcp/models/verify returns error_type: MODEL_ACCESS_DENIED when access fails."""
    import copy
    import devbench.ui.web.server as srv

    srv._ensure_gcp_runtime_state()
    with srv.GCP_STATE_LOCK:
        saved_state = copy.deepcopy(srv.GCP_RUNTIME_STATE)

    fake_catalog = [
        {
            "id": "claude-3-5-sonnet",
            "name": "Claude 3.5 Sonnet",
            "model_name": "claude-3-5-sonnet-v2@20241022",
            "publisher": "anthropic",
            "discovered": True,
            "enabled": True,
            "location": "us-east5",
        }
    ]

    try:
        with patch("devbench.gcp.model_garden.get_access_token", return_value=("mock-token", "mock-src")):
            with patch("devbench.gcp.model_garden.probe_model_access") as mock_probe:
                mock_probe.return_value = {
                    "enabled": False,
                    "enablement": "not_enabled",
                    "detail": "Not enabled for this project — enable it in Vertex AI Model Garden",
                }
                update_gcp_config(project_id="pop-up-test-proj", location="us-east5")
                with srv.GCP_STATE_LOCK:
                    srv.GCP_RUNTIME_STATE["models"] = fake_catalog

                result = verify_model_access("claude-3-5-sonnet")
                assert result["enabled"] is False
                assert result["error_type"] == "MODEL_ACCESS_DENIED"
                assert "gcloud auth application-default login" in result["remediation"]
                assert "https://console.cloud.google.com/vertex-ai/model-garden?project=pop-up-test-proj" in result["model_garden_url"]
    finally:
        with srv.GCP_STATE_LOCK:
            srv.GCP_RUNTIME_STATE = saved_state


def test_web_ui_static_contains_popup_modal_and_adc_instructions():
    """Verify index.html and app.js include the modal and gcloud auth application-default login instructions."""
    from pathlib import Path

    static_dir = Path(__file__).resolve().parents[1] / "src" / "devbench" / "ui" / "web" / "static"
    index_html = (static_dir / "index.html").read_text(encoding="utf-8")
    app_js = (static_dir / "app.js").read_text(encoding="utf-8")
    styles_css = (static_dir / "styles.css").read_text(encoding="utf-8")

    # index.html checks
    assert 'id="model-access-modal"' in index_html
    assert "gcloud auth application-default login" in index_html
    assert 'id="modal-model-garden-link"' in index_html
    assert 'id="modal-reverify-btn"' in index_html

    # app.js checks
    assert "showModelAccessModal" in app_js
    assert "closeModelAccessModal" in app_js
    assert "retryModelVerificationFromModal" in app_js
    assert "gcloud auth application-default login" in app_js

    # styles.css checks
    assert ".modal-overlay" in styles_css
    assert ".modal-card" in styles_css
    assert ".gcp-adc-instructions-card" in styles_css
