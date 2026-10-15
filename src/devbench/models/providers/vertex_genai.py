"""Vertex AI GenAI provider for first-party Gemini models (gemini-1.5-pro, gemini-1.5-flash)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from devbench.models.base import BaseModelClient, ModelResponse, synthesize_mock_response


class VertexGenAIClient(BaseModelClient):
    """Integrates google-genai / vertexai for first-party Gemini models."""

    def __init__(
        self,
        alias: str = "gemini-1.5-pro",
        model_name: str = "gemini-1.5-pro-002",
        mode: str = "mock",
        project_id: str = "devbench-eval-sandbox",
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
        use_vertex = self.resolve_use_vertex()

        # If curl or vertex_rest mode is requested, use the direct REST/curl engine
        if use_vertex and self.auth_mode in ("curl", "vertex_rest", "rest"):
            from devbench.models.vertex_rest import execute_vertex_rest_prompt

            return execute_vertex_rest_prompt(
                model_name=self.model_name,
                prompt=prompt,
                project_id=self.project_id,
                location=self.location,
                system_instruction=system_instruction,
                params=params,
                publisher="google",
            )

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
                raw_response={
                    "sdk": "injected_vertex_genai",
                    "mode": "vertex" if use_vertex else "api_key",
                    "model": self.model_name,
                },
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )

        import os

        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore

            if use_vertex:
                client = genai.Client(vertexai=True, project=self.project_id, location=self.location)
            else:
                api_key = self.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                client = genai.Client(api_key=api_key)

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
                raw_response={
                    "sdk": "google-genai",
                    "mode": "vertex" if use_vertex else "api_key",
                    "model": self.model_name,
                    "project_id": self.project_id if use_vertex else None,
                    "location": self.location if use_vertex else None,
                },
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )
        except ImportError:
            if use_vertex:
                try:
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
                        raw_response={
                            "sdk": "vertexai",
                            "mode": "vertex",
                            "model": self.model_name,
                        },
                        input_tokens=len(prompt.split()),
                        output_tokens=len(text.split()),
                        latency_ms=round(latency, 3),
                        finish_reason="STOP",
                    )
                except ImportError:
                    # If neither google-genai nor vertexai is installed, fallback cleanly to direct REST/curl
                    from devbench.models.vertex_rest import execute_vertex_rest_prompt

                    return execute_vertex_rest_prompt(
                        model_name=self.model_name,
                        prompt=prompt,
                        project_id=self.project_id,
                        location=self.location,
                        system_instruction=system_instruction,
                        params=params,
                        publisher="google",
                    )
            else:
                import google.generativeai as gai  # type: ignore

                api_key = self.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                gai.configure(api_key=api_key)
                model = gai.GenerativeModel(self.model_name, system_instruction=system_instruction)
                gen_cfg = {
                    "temperature": float(params.get("temperature", 0.0)),
                    "max_output_tokens": int(params.get("max_output_tokens", 4096)),
                }
                resp = model.generate_content(prompt, generation_config=gen_cfg)
                latency = (time.perf_counter() - start) * 1000.0
                text = resp.text or ""
                return ModelResponse(
                    text=text,
                    raw_response={
                        "sdk": "google-generativeai",
                        "mode": "api_key",
                        "model": self.model_name,
                    },
                    input_tokens=len(prompt.split()),
                    output_tokens=len(text.split()),
                    latency_ms=round(latency, 3),
                    finish_reason="STOP",
                )
        except Exception as exc:
            # Trap model permission and access denied errors
            err_str = str(exc)
            if use_vertex and any(k in err_str.lower() for k in ("permission", "denied", "not enabled", "403", "404")):
                from devbench.models.base import VertexModelAccessError

                raise VertexModelAccessError(
                    model_id=self.model_name,
                    project_id=self.project_id,
                    location=self.location,
                    message=err_str,
                ) from exc
            raise

    def as_curl_command(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Return the equivalent shell curl command to prompt this model via Vertex AI."""
        from devbench.models.vertex_rest import build_vertex_curl_command

        params = self._merge_params(kwargs)
        return build_vertex_curl_command(
            model_name=self.model_name,
            prompt=prompt,
            project_id=self.project_id,
            location=self.location,
            system_instruction=system_instruction,
            params=params,
            publisher="google",
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
