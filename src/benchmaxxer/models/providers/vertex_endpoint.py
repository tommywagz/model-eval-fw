"""Vertex AI Endpoint provider for deployed Model Garden models (critic-qwen)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from benchmaxxer.models.base import BaseModelClient, ModelResponse, synthesize_mock_response


class VertexEndpointClient(BaseModelClient):
    """Sends prediction requests to dedicated Vertex AI Endpoints."""

    def __init__(
        self,
        alias: str = "critic-qwen",
        model_name: str = "Qwen/Qwen2.5-72B-Instruct",
        endpoint_resource_name: Optional[str] = None,
        mode: str = "mock",
        project_id: str = "benchmaxxer-eval-sandbox",
        location: str = "us-central1",
        sdk_client: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            alias=alias,
            model_name=model_name,
            provider="vertex_endpoint",
            mode=mode,
            project_id=project_id,
            location=location,
            **kwargs,
        )
        if endpoint_resource_name:
            import re
            ep = str(endpoint_resource_name)
            if project_id and "benchmaxxer-eval-sandbox" in ep and project_id != "benchmaxxer-eval-sandbox":
                ep = re.sub(r"projects/[^/]+/", f"projects/{project_id}/", ep)
            if location and location != "us-central1":
                ep = re.sub(r"locations/[^/]+/", f"locations/{location}/", ep)
            self.endpoint_resource_name = ep
        else:
            self.endpoint_resource_name = f"projects/{project_id}/locations/{location}/endpoints/{alias}-ep"
        self.sdk_client = sdk_client

    def _invoke_live(
        self,
        prompt: str,
        system_instruction: Optional[str],
        params: Dict[str, Any],
    ) -> ModelResponse:
        start = time.perf_counter()
        full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
        instance = {
            "prompt": full_prompt,
            "temperature": float(params.get("temperature", 0.0)),
            "max_tokens": int(params.get("max_output_tokens", 4096)),
            "seed": int(params.get("seed", 42)),
        }

        if self.auth_mode in ("curl", "vertex_rest", "rest"):
            from benchmaxxer.models.vertex_rest import execute_vertex_rest_prompt

            return execute_vertex_rest_prompt(
                model_name=self.model_name,
                prompt=prompt,
                project_id=self.project_id,
                location=self.location,
                system_instruction=system_instruction,
                params=params,
                endpoint_resource_name=self.endpoint_resource_name,
            )

        if self.sdk_client is not None:
            prediction = self.sdk_client.predict(instances=[instance], parameters=params)
            preds = getattr(prediction, "predictions", [str(prediction)])
            text = str(preds[0]) if preds else ""
            latency = (time.perf_counter() - start) * 1000.0
            return ModelResponse(
                text=text,
                raw_response={
                    "sdk": "injected_vertex_endpoint",
                    "endpoint": self.endpoint_resource_name,
                },
                input_tokens=len(full_prompt.split()),
                output_tokens=len(text.split()),
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )

        try:
            from google.cloud import aiplatform  # type: ignore

            aiplatform.init(project=self.project_id, location=self.location)
            endpoint = aiplatform.Endpoint(self.endpoint_resource_name)
            prediction = endpoint.predict(instances=[instance], parameters=params)
            latency = (time.perf_counter() - start) * 1000.0
            preds = getattr(prediction, "predictions", [])
            if preds and isinstance(preds[0], dict):
                text = str(preds[0].get("content") or preds[0].get("output") or preds[0].get("text") or preds[0])
            elif preds:
                text = str(preds[0])
            else:
                text = ""
            return ModelResponse(
                text=text,
                raw_response={
                    "sdk": "vertex_endpoint",
                    "endpoint": self.endpoint_resource_name,
                },
                input_tokens=len(full_prompt.split()),
                output_tokens=len(text.split()),
                latency_ms=round(latency, 3),
                finish_reason="STOP",
            )
        except ImportError:
            from benchmaxxer.models.vertex_rest import execute_vertex_rest_prompt

            return execute_vertex_rest_prompt(
                model_name=self.model_name,
                prompt=prompt,
                project_id=self.project_id,
                location=self.location,
                system_instruction=system_instruction,
                params=params,
                endpoint_resource_name=self.endpoint_resource_name,
            )
        except Exception as exc:
            err_str = str(exc)
            if any(k in err_str.lower() for k in ("permission", "denied", "not found", "403", "404")):
                from benchmaxxer.models.base import VertexModelAccessError

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
        """Return the equivalent shell curl command to prompt this endpoint via Vertex AI."""
        from benchmaxxer.models.vertex_rest import build_vertex_curl_command

        params = self._merge_params(kwargs)
        return build_vertex_curl_command(
            model_name=self.model_name,
            prompt=prompt,
            project_id=self.project_id,
            location=self.location,
            system_instruction=system_instruction,
            params=params,
            endpoint_resource_name=self.endpoint_resource_name,
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
