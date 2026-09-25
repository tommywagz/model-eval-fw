"""OpenAI-Compatible provider supporting vLLM, MaaS, and local inference servers (MiniMax, Qwen, Kimi K)."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional

from benchmaxxer.models.base import BaseModelClient, ModelResponse, synthesize_mock_response


class OpenAICompatibleClient(BaseModelClient):
    """Standard OpenAI-compatible chat/completions provider for vLLM, MaaS, and open/distilled critics."""

    def __init__(
        self,
        alias: str = "critic-minimax",
        model_name: str = "MiniMax-Text-01",
        base_url: str = "http://localhost:8000/v1",
        api_key: Optional[str] = None,
        mode: str = "mock",
        sdk_client: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            alias=alias,
            model_name=model_name,
            provider="openai_compatible",
            mode=mode,
            **kwargs,
        )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "mock-api-key")
        self.sdk_client = sdk_client

    def _invoke_live(
        self,
        prompt: str,
        system_instruction: Optional[str],
        params: Dict[str, Any],
    ) -> ModelResponse:
        start = time.perf_counter()
        messages: List[Dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        if self.sdk_client is not None:
            resp = self.sdk_client.chat_completions_create(
                model=self.model_name,
                messages=messages,
                temperature=float(params.get("temperature", 0.0)),
                max_tokens=int(params.get("max_output_tokens", 4096)),
                seed=int(params.get("seed", 42)),
            )
            text = getattr(resp, "text", str(resp))
            latency = (time.perf_counter() - start) * 1000.0
            return ModelResponse(
                text=text,
                raw_response={"sdk": "injected_openai_compat", "base_url": self.base_url},
                input_tokens=len(prompt.split()),
                output_tokens=len(text.split()),
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )

        payload = json.dumps(
            {
                "model": self.model_name,
                "messages": messages,
                "temperature": float(params.get("temperature", 0.0)),
                "max_tokens": int(params.get("max_output_tokens", 4096)),
                "seed": int(params.get("seed", 42)),
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        latency = (time.perf_counter() - start) * 1000.0
        choice = (body.get("choices") or [{}])[0]
        text = choice.get("message", {}).get("content", "")
        usage = body.get("usage", {})
        return ModelResponse(
            text=text,
            raw_response=body,
            input_tokens=int(usage.get("prompt_tokens", len(prompt.split()))),
            output_tokens=int(usage.get("completion_tokens", len(text.split()))),
            latency_ms=round(latency, 3),
            finish_reason=str(choice.get("finish_reason", "STOP")),
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
