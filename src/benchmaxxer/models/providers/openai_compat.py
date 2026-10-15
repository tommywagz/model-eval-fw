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
        alias_lower = alias.lower()
        env_key: Optional[str] = None
        if "minimax" in alias_lower:
            env_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("OPENAI_API_KEY")
        elif "kimi" in alias_lower or "moonshot" in alias_lower:
            env_key = (
                os.environ.get("KIMI_API_KEY")
                or os.environ.get("MOONSHOT_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
            )
        elif "qwen" in alias_lower:
            env_key = (
                os.environ.get("QWEN_API_KEY")
                or os.environ.get("DASHSCOPE_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
            )
        else:
            env_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_ADMIN_KEY")
        self.api_key = api_key or env_key or "mock-api-key"
        self.sdk_client = sdk_client

    def _invoke_live(
        self,
        prompt: str,
        system_instruction: Optional[str],
        params: Dict[str, Any],
    ) -> ModelResponse:
        start = time.perf_counter()
        use_vertex = self.resolve_use_vertex()

        if use_vertex:
            from benchmaxxer.gcp.model_garden import get_access_token, vertex_host

            token, _ = get_access_token()
            self.api_key = token
            loc = self.location if self.location else "us-central1"
            proj = self.project_id if self.project_id else "benchmaxxer-eval-sandbox"
            self.base_url = f"{vertex_host(loc)}/v1/projects/{proj}/locations/{loc}/endpoints/openapi"

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
                raw_response={
                    "sdk": "injected_openai_compat",
                    "mode": "vertex_maas" if use_vertex else "api_key",
                    "base_url": self.base_url,
                },
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

        req_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if use_vertex and self.project_id:
            req_headers["x-goog-user-project"] = self.project_id

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers=req_headers,
            method="POST",
        )
        import urllib.error

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw_err = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            try:
                err_json = json.loads(raw_err) if raw_err else {}
            except Exception:
                err_json = {"error": {"message": raw_err or str(exc)}}
            err_dict = err_json.get("error", {}) if isinstance(err_json.get("error"), dict) else err_json
            err_msg = str(err_dict.get("message") or err_json)

            if use_vertex or exc.code in (403, 404):
                from benchmaxxer.models.base import VertexModelAccessError

                loc = self.location if self.location else "us-central1"
                proj = self.project_id if self.project_id else "gcp-project"
                raise VertexModelAccessError(
                    model_id=self.model_name,
                    project_id=proj,
                    location=loc,
                    message=err_msg,
                    status_code=exc.code,
                ) from exc
            raise RuntimeError(f"OpenAI-compatible request failed ({exc.code}): {err_msg}") from exc

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

    def as_curl_command(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Return the equivalent shell curl command to prompt this model."""
        import json
        import shlex

        params = self._merge_params(kwargs)
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model_name,
            "messages": messages,
            "temperature": float(params.get("temperature", 0.0)),
            "max_tokens": int(params.get("max_output_tokens", 4096)),
        }
        body_json = json.dumps(body)
        auth_hdr = (
            '-H "Authorization: Bearer $(gcloud auth application-default print-access-token)"'
            if self.resolve_use_vertex()
            else f'-H "Authorization: Bearer {self.api_key}"'
        )
        parts = [
            "curl -X POST",
            shlex.quote(f"{self.base_url}/chat/completions"),
            auth_hdr,
            '-H "Content-Type: application/json"',
            f"-d '{body_json}'",
        ]
        return " \\\n  ".join(parts)

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
