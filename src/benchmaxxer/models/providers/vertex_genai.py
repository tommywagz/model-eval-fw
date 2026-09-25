"""Vertex AI GenAI provider for first-party Gemini models (gemini-1.5-pro, gemini-1.5-flash)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from benchmaxxer.models.base import BaseModelClient, ModelResponse, synthesize_mock_response


class VertexGenAIClient(BaseModelClient):
    """Integrates google-genai / vertexai for first-party Gemini models."""

    def __init__(
        self,
        alias: str = "gemini-1.5-pro",
        model_name: str = "gemini-1.5-pro-002",
        mode: str = "mock",
        project_id: str = "benchmaxxer-eval-sandbox",
        location: str = "us-central1",
        sdk_client: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            alias=alias,
            model_name=model_name,
            provider="vertex_genai",
            mode=mode,
            project_id=project_id,
            location=location,
            **kwargs,
        )
        self.sdk_client = sdk_client

    def _invoke_live(
        self,
        prompt: str,
        system_instruction: Optional[str],
        params: Dict[str, Any],
    ) -> ModelResponse:
        start = time.perf_counter()
        if self.sdk_client is not None:
            raw = self.sdk_client.generate_content(
                model=self.model_name,
                contents=prompt,
                system_instruction=system_instruction,
                generation_config=params,
            )
            text = getattr(raw, "text", str(raw))
            usage = getattr(raw, "usage_metadata", None)
            in_tok = int(getattr(usage, "prompt_token_count", len(prompt.split())))
            out_tok = int(getattr(usage, "candidates_token_count", len(text.split())))
            latency = (time.perf_counter() - start) * 1000.0
            return ModelResponse(
                text=text,
                raw_response={"sdk": "injected_vertex_genai", "model": self.model_name},
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )

        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore

            client = genai.Client(vertexai=True, project=self.project_id, location=self.location)
            cfg = types.GenerateContentConfig(
                temperature=float(params.get("temperature", 0.0)),
                max_output_tokens=int(params.get("max_output_tokens", 4096)),
                seed=int(params.get("seed", 42)),
                system_instruction=system_instruction,
            )
            resp = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=cfg,
            )
            latency = (time.perf_counter() - start) * 1000.0
            usage = getattr(resp, "usage_metadata", None)
            in_tok = int(getattr(usage, "prompt_token_count", len(prompt.split())))
            out_tok = int(getattr(usage, "candidates_token_count", len((resp.text or "").split())))
            return ModelResponse(
                text=resp.text or "",
                raw_response={"sdk": "google-genai", "model": self.model_name},
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )
        except ImportError:
            import vertexai  # type: ignore
            from vertexai.generative_models import GenerationConfig, GenerativeModel  # type: ignore

            vertexai.init(project=self.project_id, location=self.location)
            model = GenerativeModel(self.model_name, system_instruction=system_instruction)
            gen_cfg = GenerationConfig(
                temperature=float(params.get("temperature", 0.0)),
                max_output_tokens=int(params.get("max_output_tokens", 4096)),
            )
            resp = model.generate_content(prompt, generation_config=gen_cfg)
            latency = (time.perf_counter() - start) * 1000.0
            text = resp.text or ""
            return ModelResponse(
                text=text,
                raw_response={"sdk": "vertexai", "model": self.model_name},
                input_tokens=len(prompt.split()),
                output_tokens=len(text.split()),
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        params = self._merge_params(kwargs)

        def _call() -> ModelResponse:
            if self.mode == "live":
                return self._invoke_live(prompt, system_instruction, params)
            return synthesize_mock_response(
                alias=self.alias,
                model_name=self.model_name,
                provider=self.provider,
                prompt=prompt,
                system_instruction=system_instruction,
                params=params,
            )

        return self._execute_with_cache(prompt, system_instruction, params, _call)

    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ModelResponse:
        system_parts: List[str] = []
        turn_lines: List[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                turn_lines.append(f"[{role.upper()}]: {content}")
        combined_prompt = "\n".join(turn_lines)
        sys_inst = "\n".join(system_parts) if system_parts else kwargs.pop("system_instruction", None)
        return self.generate(prompt=combined_prompt, system_instruction=sys_inst, **kwargs)
