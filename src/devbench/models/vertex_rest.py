"""Vertex AI direct REST and CLI curl execution engine for model prompting.

Enables zero-heavyweight-SDK prompting against Google Cloud Vertex AI:
- First-party Gemini: POST /v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent
- Anthropic Claude Partner: POST /v1/projects/{project}/locations/{location}/publishers/anthropic/models/{model}:rawPredict
- Model-as-a-Service (Mistral, Llama, Qwen): POST /v1/projects/{project}/locations/{location}/endpoints/openapi/chat/completions
- Deployed Endpoints: POST /v1/{endpoint_resource_name}:predict

Uses OAuth Bearer tokens resolved from Application Default Credentials (ADC) or
`gcloud auth application-default print-access-token`.

Catches permission and model-enablement issues (HTTP 403 / 404 / PERMISSION_DENIED)
and raises structured `VertexModelAccessError` with actionable remediation guidance.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from devbench.gcp.model_garden import get_access_token, vertex_host
from devbench.models.base import ModelResponse, VertexModelAccessError


def _classify_publisher(model_name: str, publisher: Optional[str] = None) -> str:
    """Classify the model publisher into 'google', 'anthropic', or 'maas'."""
    if publisher:
        pub = publisher.lower().strip()
        if pub in ("google", "gemini"):
            return "google"
        if pub in ("anthropic", "claude"):
            return "anthropic"
        return pub

    m = model_name.lower()
    if m.startswith("gemini") or m.startswith("gemma") or "publishers/google" in m:
        return "google"
    if m.startswith("claude") or "publishers/anthropic" in m:
        return "anthropic"
    if any(p in m for p in ("mistral", "llama", "deepseek", "qwen")):
        return "maas"
    return "google"


def _normalize_endpoint_resource_name(endpoint_name_or_id: str, project_id: str, location: str) -> str:
    """Normalize an endpoint ID or partial path to projects/{project}/locations/{location}/endpoints/{id}."""
    ep = str(endpoint_name_or_id).strip("/")
    if not ep.startswith("projects/"):
        if ep.startswith("endpoints/"):
            return f"projects/{project_id}/locations/{location}/{ep}"
        return f"projects/{project_id}/locations/{location}/endpoints/{ep}"
    return ep


def _clean_model_name(model_name: str, publisher: str) -> str:
    """Strip leading publisher path if full resource name was provided."""
    m = model_name.strip()
    prefix = f"publishers/{publisher}/models/"
    if m.startswith(prefix):
        return m[len(prefix):]
    if m.startswith("publishers/google/models/"):
        return m[len("publishers/google/models/"):]
    return m


def build_vertex_curl_command(
    model_name: str,
    prompt: str,
    project_id: str,
    location: str = "us-central1",
    system_instruction: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    publisher: Optional[str] = None,
    endpoint_resource_name: Optional[str] = None,
) -> str:
    """Generate the equivalent shell `curl` command for prompting a model via Vertex AI."""
    pub = _classify_publisher(model_name, publisher)
    loc = location or "us-central1"
    host = vertex_host(loc)
    gen_params = params or {}
    temp = float(gen_params.get("temperature", 0.0))
    max_tokens = int(gen_params.get("max_output_tokens", 4096))

    if endpoint_resource_name:
        ep_name = _normalize_endpoint_resource_name(endpoint_resource_name, project_id, loc)
        url = f"{host}/v1/{ep_name}:predict"
        body = {
            "instances": [
                {
                    "prompt": f"{system_instruction}\n\n{prompt}" if system_instruction else prompt,
                    "max_tokens": max_tokens,
                    "temperature": temp,
                }
            ],
            "parameters": {"temperature": temp, "maxOutputTokens": max_tokens},
        }
    elif pub == "google":
        clean_model = _clean_model_name(model_name, "google")
        url = f"{host}/v1/projects/{project_id}/locations/{loc}/publishers/google/models/{clean_model}:generateContent"
        contents: List[Dict[str, Any]] = [{"role": "user", "parts": [{"text": prompt}]}]
        body = {
            "contents": contents,
            "generationConfig": {"temperature": temp, "maxOutputTokens": max_tokens},
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    elif pub == "anthropic":
        # Anthropic is served on the global endpoint and on regions such as us-east5
        anthropic_loc = loc or "us-east5"
        anthropic_host = vertex_host(anthropic_loc)
        url = f"{anthropic_host}/v1/projects/{project_id}/locations/{anthropic_loc}/publishers/anthropic/models/{model_name}:rawPredict"
        body = {
            "anthropic_version": "vertex-2023-10-16",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temp,
        }
        if system_instruction:
            body["system"] = system_instruction
    else:
        # MaaS OpenAPI endpoint
        url = f"{host}/v1/projects/{project_id}/locations/{loc}/endpoints/openapi/chat/completions"
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": model_name,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
        }

    body_json = json.dumps(body)
    curl_parts = [
        "curl -X POST",
        shlex.quote(url),
        '-H "Authorization: Bearer $(gcloud auth application-default print-access-token)"',
        '-H "Content-Type: application/json"',
        f"-d '{body_json}'",
    ]
    return " \\\n  ".join(curl_parts)


def execute_vertex_rest_prompt(
    model_name: str,
    prompt: str,
    project_id: str,
    location: str = "us-central1",
    system_instruction: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    publisher: Optional[str] = None,
    access_token: Optional[str] = None,
    endpoint_resource_name: Optional[str] = None,
    timeout: float = 300.0,
) -> ModelResponse:
    """Prompt a Vertex AI model directly via HTTP REST using Google Cloud OAuth credentials.

    Raises:
        VertexModelAccessError: When the GCP project does not have access / permission to the model.
        RuntimeError: On other HTTP / invocation failures.
    """
    token = access_token
    token_source = "provided"
    if not token:
        token, token_source = get_access_token()

    pub = _classify_publisher(model_name, publisher)
    loc = location or "us-central1"
    host = vertex_host(loc)
    gen_params = params or {}
    temp = float(gen_params.get("temperature", 0.0))
    max_tokens = int(gen_params.get("max_output_tokens", 4096))
    start = time.perf_counter()

    if endpoint_resource_name:
        ep_name = _normalize_endpoint_resource_name(endpoint_resource_name, project_id, loc)
        url = f"{host}/v1/{ep_name}:predict"
        body = {
            "instances": [
                {
                    "prompt": f"{system_instruction}\n\n{prompt}" if system_instruction else prompt,
                    "max_tokens": max_tokens,
                    "temperature": temp,
                }
            ],
            "parameters": {"temperature": temp, "maxOutputTokens": max_tokens},
        }
    elif pub == "google":
        clean_model = _clean_model_name(model_name, "google")
        url = f"{host}/v1/projects/{project_id}/locations/{loc}/publishers/google/models/{clean_model}:generateContent"
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        body = {
            "contents": contents,
            "generationConfig": {"temperature": temp, "maxOutputTokens": max_tokens},
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    elif pub == "anthropic":
        anthropic_loc = loc or "us-east5"
        anthropic_host = vertex_host(anthropic_loc)
        url = f"{anthropic_host}/v1/projects/{project_id}/locations/{anthropic_loc}/publishers/anthropic/models/{model_name}:rawPredict"
        body = {
            "anthropic_version": "vertex-2023-10-16",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temp,
        }
        if system_instruction:
            body["system"] = system_instruction
    else:
        url = f"{host}/v1/projects/{project_id}/locations/{loc}/endpoints/openapi/chat/completions"
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": model_name,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tokens,
        }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-goog-user-project": project_id,
        },
        method="POST",
    )

    # Retry rate limits and transient unavailability with backoff before surfacing the error.
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_body = json.loads(resp.read().decode("utf-8") or "{}")
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < max_attempts:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0 ** attempt
                time.sleep(min(delay, 30.0))
                continue
            raw_err = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            try:
                err_json = json.loads(raw_err) if raw_err else {}
            except json.JSONDecodeError:
                err_json = {"error": {"message": raw_err or str(exc)}}
            _raise_vertex_rest_error(
                status_code=exc.code,
                payload=err_json,
                model_name=model_name,
                project_id=project_id,
                location=loc,
            )

    latency_ms = (time.perf_counter() - start) * 1000.0

    # Parse response payload by publisher format
    if pub == "google":
        candidates = resp_body.get("candidates") or []
        first = candidates[0] if candidates else {}
        parts = (first.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        usage = resp_body.get("usageMetadata") or {}
        in_tok = int(usage.get("promptTokenCount", len(prompt.split())))
        out_tok = int(usage.get("candidatesTokenCount", len(text.split())))
        finish = str(first.get("finishReason", "STOP"))
    elif pub == "anthropic":
        content_blocks = resp_body.get("content") or []
        text = "".join(b.get("text", "") for b in content_blocks if isinstance(b, dict))
        usage = resp_body.get("usage") or {}
        in_tok = int(usage.get("input_tokens", len(prompt.split())))
        out_tok = int(usage.get("output_tokens", len(text.split())))
        finish = str(resp_body.get("stop_reason", "STOP"))
    elif endpoint_resource_name:
        predictions = resp_body.get("predictions") or []
        first = predictions[0] if predictions else ""
        text = first.get("content") or first.get("text") or str(first) if isinstance(first, dict) else str(first)
        in_tok = len(prompt.split())
        out_tok = len(text.split())
        finish = "STOP"
    else:
        # MaaS OpenAPI chat format
        choices = resp_body.get("choices") or []
        first = choices[0] if choices else {}
        text = (first.get("message") or {}).get("content", "")
        usage = resp_body.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens", len(prompt.split())))
        out_tok = int(usage.get("completion_tokens", len(text.split())))
        finish = str(first.get("finish_reason", "STOP"))

    return ModelResponse(
        text=text,
        raw_response={
            "engine": "vertex_rest",
            "url": url,
            "model": model_name,
            "project_id": project_id,
            "location": loc,
            "credential_source": token_source,
            "raw": resp_body,
        },
        input_tokens=in_tok,
        output_tokens=out_tok,
        latency_ms=round(latency_ms, 3),
        finish_reason=finish,
    )


def _raise_vertex_rest_error(
    status_code: int,
    payload: Dict[str, Any],
    model_name: str,
    project_id: str,
    location: str,
) -> None:
    """Inspect the GCP error payload and raise VertexModelAccessError or RuntimeError."""
    err_dict = payload.get("error") if isinstance(payload.get("error"), dict) else payload
    msg = str(err_dict.get("message") or payload.get("message") or payload)
    err_status = str(err_dict.get("status") or ("PERMISSION_DENIED" if status_code == 403 else f"HTTP_{status_code}"))

    # Determine if this error indicates missing access, unaccepted terms, or model not enabled
    is_access_denied = (
        status_code in (403, 404)
        or "permission" in msg.lower()
        or "denied" in msg.lower()
        or "not enabled" in msg.lower()
        or "enable" in msg.lower()
        or "terms" in msg.lower()
        or "eula" in msg.lower()
        or "marketplace" in msg.lower()
        or "not found" in msg.lower()
    )

    if is_access_denied:
        remediation = (
            f"1. Run `gcloud auth application-default login` on your local terminal.\n"
            f"2. Open Vertex AI Model Garden to enable '{model_name}' in project '{project_id}':\n"
            f"   https://console.cloud.google.com/vertex-ai/model-garden?project={project_id}\n"
            f"3. Ensure your GCP identity has the 'roles/aiplatform.user' role on project '{project_id}'."
        )
        raise VertexModelAccessError(
            model_id=model_name,
            project_id=project_id,
            location=location,
            message=msg,
            status_code=status_code,
            error_status=err_status,
            remediation=remediation,
        )

    raise RuntimeError(f"Vertex AI REST request failed (HTTP {status_code} {err_status}): {msg}")
