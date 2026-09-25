"""Vertex AI Anthropic provider for Claude models served via Vertex AI."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from benchmaxxer.models.base import BaseModelClient, ModelResponse, synthesize_mock_response


class VertexAnthropicClient(BaseModelClient):
    """Integrates Anthropic Claude models served via Google Cloud Vertex AI."""

    def __init__(
        self,
        alias: str = "claude-3-5-sonnet",
        model_name: str = "claude-3-5-sonnet-v2@20241022",
        mode: str = "mock",
        project_id: str = "benchmaxxer-eval-sandbox",
        location: str = "us-east5",
        sdk_client: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            alias=alias,
            model_name=model_name,
            provider="vertex_anthropic",
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
            raw = self.sdk_client.messages_create(
                model=self.model_name,
                max_tokens=int(params.get("max_output_tokens", 4096)),
                temperature=float(params.get("temperature", 0.0)),
                system=system_instruction or "",
                messages=[{"role": "user", "content": prompt}],
            )
            text = getattr(raw, "text", str(raw))
            latency = (time.perf_counter() - start) * 1000.0
            return ModelResponse(
                text=text,
                raw_response={"sdk": "injected_anthropic_vertex", "model": self.model_name},
                input_tokens=len(prompt.split()),
                output_tokens=len(text.split()),
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )

        from anthropic import AnthropicVertex  # type: ignore

        client = AnthropicVertex(project_id=self.project_id, region=self.location)
        create_kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": int(params.get("max_output_tokens", 4096)),
            "temperature": float(params.get("temperature", 0.0)),
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            create_kwargs["system"] = system_instruction
        resp = client.messages.create(**create_kwargs)
        latency = (time.perf_counter() - start) * 1000.0
        content_blocks = getattr(resp, "content", [])
        text = "".join(getattr(b, "text", "") for b in content_blocks)
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "input_tokens", len(prompt.split())))
        out_tok = int(getattr(usage, "output_tokens", len(text.split())))
        return ModelResponse(
            text=text,
            raw_response={"sdk": "anthropic-vertex", "model": self.model_name},
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=round(latency, 3),
            finish_reason=str(getattr(resp, "stop_reason", "STOP")),
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
