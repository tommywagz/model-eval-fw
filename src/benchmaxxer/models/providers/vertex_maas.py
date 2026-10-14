"""Vertex AI Model-as-a-Service (MaaS) provider for partner/open models (Mistral, Llama, DeepSeek, Qwen).

Uses the Vertex AI OpenAI-compatible endpoint
``https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/endpoints/openapi``
authenticated with the linked project's Application Default Credentials.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from benchmaxxer.models.base import ModelResponse
from benchmaxxer.models.providers.openai_compat import OpenAICompatibleClient


class VertexMaaSClient(OpenAICompatibleClient):
    """OpenAI-compatible chat completions against Vertex AI MaaS using an ADC bearer token."""

    def __init__(
        self,
        alias: str = "mistral-large",
        model_name: str = "mistralai/mistral-large-2411",
        mode: str = "mock",
        project_id: str = "benchmaxxer-eval-sandbox",
        location: str = "us-central1",
        **kwargs: Any,
    ) -> None:
        kwargs.pop("base_url", None)
        from benchmaxxer.gcp.model_garden import vertex_host

        base_url = f"{vertex_host(location)}/v1/projects/{project_id}/locations/{location}/endpoints/openapi"
        super().__init__(
            alias=alias,
            model_name=model_name,
            base_url=base_url,
            api_key="adc-token-resolved-at-call-time",
            mode=mode,
            project_id=project_id,
            location=location,
            **kwargs,
        )
        self.provider = "vertex_maas"

    def _invoke_live(
        self,
        prompt: str,
        system_instruction: Optional[str],
        params: Dict[str, Any],
    ) -> ModelResponse:
        from benchmaxxer.gcp.model_garden import get_access_token

        token, _ = get_access_token()
        self.api_key = token
        return super()._invoke_live(prompt, system_instruction, params)
