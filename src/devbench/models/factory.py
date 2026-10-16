"""Model Factory and Registry Loader for devbench."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional, Type

import yaml

from devbench.models.base import BaseModelClient
from devbench.models.providers import (
    OpenAICompatibleClient,
    VertexAnthropicClient,
    VertexEndpointClient,
    VertexGenAIClient,
    VertexMaaSClient,
)
from devbench.telemetry.cache import ResponseCache

PROVIDER_MAP: Dict[str, Type[BaseModelClient]] = {
    "vertex_genai": VertexGenAIClient,
    "vertex_anthropic": VertexAnthropicClient,
    "vertex_endpoint": VertexEndpointClient,
    "vertex_maas": VertexMaaSClient,
    "openai_compatible": OpenAICompatibleClient,
}

# Models discovered at runtime from the user's linked GCP project (Vertex AI Model Garden).
# These take precedence over static configs so the selected MIQ always targets the linked project.
_RUNTIME_MODELS: Dict[str, Dict[str, Any]] = {}
_RUNTIME_LOCK = threading.Lock()


def register_runtime_models(models: Dict[str, Dict[str, Any]], replace: bool = True) -> None:
    """Register model alias configs discovered at runtime (e.g. from a linked GCP project)."""
    with _RUNTIME_LOCK:
        if replace:
            _RUNTIME_MODELS.clear()
        for alias, cfg in models.items():
            _RUNTIME_MODELS[alias] = dict(cfg)


def get_runtime_models() -> Dict[str, Dict[str, Any]]:
    with _RUNTIME_LOCK:
        return {k: dict(v) for k, v in _RUNTIME_MODELS.items()}


DEFAULT_MODELS_FALLBACK: Dict[str, Dict[str, Any]] = {
    "gemini-3.1-pro": {
        "provider": "vertex_genai",
        "model_name": "gemini-3.1-pro-preview",
        "project_id": "devbench-eval-sandbox",
        "location": "global",
        "cost_per_1k_input_usd": 0.00150,
        "cost_per_1k_output_usd": 0.00600,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 16384, "seed": 42},
    },
    "gemini-3.8-flash": {
        "provider": "vertex_genai",
        "model_name": "gemini-3.8-flash",
        "project_id": "devbench-eval-sandbox",
        "location": "global",
        "cost_per_1k_input_usd": 0.00015,
        "cost_per_1k_output_usd": 0.00060,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "claude-opus-5.1": {
        "provider": "vertex_anthropic",
        "model_name": "claude-opus-5-1@20260601",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00500,
        "cost_per_1k_output_usd": 0.02500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192},
    },
    "claude-sonnet-5.5": {
        "provider": "vertex_anthropic",
        "model_name": "claude-sonnet-5-5",
        "project_id": "devbench-eval-sandbox",
        "location": "global",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192},
    },
    "mistral-large-latest": {
        "provider": "vertex_endpoint",
        "model_name": "mistralai/mistral-large-3-latest",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/europe-west4/endpoints/mistral-large-3-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "europe-west4",
        "cost_per_1k_input_usd": 0.00200,
        "cost_per_1k_output_usd": 0.00600,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "gemini-4-argon": {
        "provider": "vertex_genai",
        "model_name": "gemini-4-argon",
        "project_id": "devbench-eval-sandbox",
        "location": "global",
        "cost_per_1k_input_usd": 0.00200,
        "cost_per_1k_output_usd": 0.00800,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 16384, "seed": 42},
    },
    "fable-5.1": {
        "provider": "vertex_endpoint",
        "model_name": "fable-ai/fable-5.1-frontier",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/us-central1/endpoints/fable-5-1-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00250,
        "cost_per_1k_output_usd": 0.01000,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "sonnet-5.5": {
        "provider": "vertex_anthropic",
        "model_name": "claude-sonnet-5-5",
        "project_id": "devbench-eval-sandbox",
        "location": "global",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192},
    },
    "gemini-3.5-pro": {
        "provider": "vertex_genai",
        "model_name": "gemini-3.5-pro-002",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00125,
        "cost_per_1k_output_usd": 0.00500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "gemini-1.5-pro": {
        "provider": "vertex_genai",
        "model_name": "gemini-1.5-pro-002",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00125,
        "cost_per_1k_output_usd": 0.00500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "gemini-1.5-flash": {
        "provider": "vertex_genai",
        "model_name": "gemini-1.5-flash-002",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.000075,
        "cost_per_1k_output_usd": 0.00030,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "claude-3-5-sonnet": {
        "provider": "vertex_anthropic",
        "model_name": "claude-3-5-sonnet-v2@20241022",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096},
    },
    "claude-3-5-haiku": {
        "provider": "vertex_anthropic",
        "model_name": "claude-3-5-haiku@20241022",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00080,
        "cost_per_1k_output_usd": 0.00400,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096},
    },
    "llama-4-405b": {
        "provider": "vertex_endpoint",
        "model_name": "meta/llama-4-405b-instruct",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/us-central1/endpoints/llama-4-405b-instruct-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00150,
        "cost_per_1k_output_usd": 0.00450,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "llama-3.1-70b": {
        "provider": "vertex_endpoint",
        "model_name": "meta/llama-3.1-70b-instruct",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/us-central1/endpoints/llama-31-70b-instruct-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00080,
        "cost_per_1k_output_usd": 0.00080,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096, "seed": 42},
    },
    "deepseek-r2": {
        "provider": "vertex_endpoint",
        "model_name": "deepseek-ai/deepseek-r2-reasoning",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/us-central1/endpoints/deepseek-r2-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00055,
        "cost_per_1k_output_usd": 0.00220,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "mistral-large-3": {
        "provider": "vertex_endpoint",
        "model_name": "mistralai/mistral-large-3",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/europe-west4/endpoints/mistral-large-3-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "europe-west4",
        "cost_per_1k_input_usd": 0.00200,
        "cost_per_1k_output_usd": 0.00600,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "qwen-3-72b": {
        "provider": "vertex_endpoint",
        "model_name": "Qwen/Qwen3-72B-Instruct",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/us-central1/endpoints/qwen3-72b-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00080,
        "cost_per_1k_output_usd": 0.00160,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "critic-qwen": {
        "provider": "vertex_endpoint",
        "model_name": "Qwen/Qwen2.5-72B-Instruct",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/us-central1/endpoints/critic-qwen-25-72b-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00080,
        "cost_per_1k_output_usd": 0.00080,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 2048, "seed": 42},
    },
    "critic-minimax": {
        "provider": "openai_compatible",
        "model_name": "MiniMax-Text-01",
        "base_url": "http://localhost:8000/v1",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00040,
        "cost_per_1k_output_usd": 0.00110,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 2048, "seed": 42},
    },
    "critic-kimi-k": {
        "provider": "openai_compatible",
        "model_name": "Kimi-K1.5-Instruct",
        "base_url": "http://localhost:8001/v1",
        "endpoint_resource_name": "projects/devbench-eval-sandbox/locations/us-central1/endpoints/critic-kimi-k-ep",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00060,
        "cost_per_1k_output_usd": 0.00120,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 2048, "seed": 42},
    },
}


def _resolve_registry_path(config_path: Optional[str | Path] = None) -> Optional[Path]:
    if config_path:
        p = Path(config_path)
        if p.exists():
            return p
    candidates = [
        Path("configs/models.yaml"),
        Path(__file__).resolve().parents[3] / "configs" / "models.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_model_registry(config_path: Optional[str | Path] = None) -> Dict[str, Dict[str, Any]]:
    """Load the model catalog from configs/models.yaml with built-in fallbacks."""
    from devbench.telemetry.tokens import load_project_dotenv

    load_project_dotenv()
    registry = {k: dict(v) for k, v in DEFAULT_MODELS_FALLBACK.items()}
    resolved = _resolve_registry_path(config_path)
    if resolved:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        defaults = raw.get("defaults", {})
        models_section = raw.get("models", {})
        for alias, cfg in models_section.items():
            merged = dict(defaults)
            merged.update(cfg)
            registry[alias] = merged
    runtime = get_runtime_models()
    for alias, cfg in runtime.items():
        cfg = dict(cfg)
        cfg["_runtime"] = True
        registry[alias] = cfg
    return registry


def get_model_client(
    alias: str = "gemini-1.5-pro",
    mode: str = "mock",
    config_path: Optional[str | Path] = None,
    no_cache: bool = False,
    replay: bool = False,
    cache_dir: Optional[str | Path] = None,
    dotenv_path: Optional[str | Path] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None,
    use_vertex: Optional[bool] = None,
    auth_mode: Optional[str] = None,
    **overrides: Any,
) -> BaseModelClient:
    """Factory method returning a configured BaseModelClient instance for the given alias."""
    import os
    import re
    from devbench.telemetry.tokens import load_project_dotenv

    load_project_dotenv(dotenv_path=dotenv_path)
    registry = load_model_registry(config_path=config_path)
    if alias not in registry:
        raise KeyError(
            f"Unknown model alias '{alias}'. Available aliases: {sorted(registry.keys())}"
        )

    cfg = dict(registry[alias])
    is_runtime = bool(cfg.pop("_runtime", False))

    env_project = (
        project_id
        or overrides.get("project_id")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("VERTEX_PROJECT_ID")
        or os.environ.get("GCP_PROJECT")
        or os.environ.get("GCP_PROJECT_ID")
        or os.environ.get("CLOUDSDK_CORE_PROJECT")
    )
    if env_project and "project_id" not in overrides and not (is_runtime and cfg.get("project_id") and not project_id):
        cfg["project_id"] = env_project

    env_location = (
        location
        or overrides.get("location")
        or os.environ.get("VERTEX_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("GCP_LOCATION")
        or os.environ.get("CLOUD_ML_REGION")
    )
    if env_location and "location" not in overrides and not (is_runtime and cfg.get("location") and not location):
        cfg["location"] = env_location

    if use_vertex is not None:
        cfg["use_vertex"] = use_vertex
    elif "use_vertex" in overrides:
        cfg["use_vertex"] = overrides["use_vertex"]

    if auth_mode is not None:
        cfg["auth_mode"] = auth_mode
    elif "auth_mode" in overrides:
        cfg["auth_mode"] = overrides["auth_mode"]

    cfg.update(overrides)
    cfg = {k: v for k, v in cfg.items() if v is not None}

    if "endpoint_id_or_name" in cfg and "endpoint_resource_name" not in cfg:
        cfg["endpoint_resource_name"] = cfg.pop("endpoint_id_or_name")

    # Dynamically rewrite endpoint resource name if custom project or location was provided
    if "endpoint_resource_name" in cfg and cfg.get("project_id"):
        ep = str(cfg["endpoint_resource_name"]).strip()
        proj = str(cfg["project_id"])
        loc = str(cfg.get("location", "us-central1"))
        if not ep.startswith("projects/"):
            if ep.startswith("endpoints/"):
                ep = f"projects/{proj}/locations/{loc}/{ep}"
            else:
                ep = f"projects/{proj}/locations/{loc}/endpoints/{ep}"
        else:
            if "devbench-eval-sandbox" in ep and proj != "devbench-eval-sandbox":
                ep = re.sub(r"projects/[^/]+/", f"projects/{proj}/", ep)
            if loc != "us-central1" and f"locations/{loc}" not in ep:
                ep = re.sub(r"locations/[^/]+/", f"locations/{loc}/", ep)
        cfg["endpoint_resource_name"] = ep

    provider_key = str(cfg.pop("provider", "vertex_genai"))
    if provider_key not in PROVIDER_MAP:
        raise ValueError(
            f"Unsupported provider '{provider_key}' for model alias '{alias}'. "
            f"Supported providers: {sorted(PROVIDER_MAP.keys())}"
        )

    provider_cls = PROVIDER_MAP[provider_key]
    model_name = str(cfg.pop("model_name", alias))
    cache = ResponseCache(base_dir=cache_dir, no_cache=no_cache, replay=replay)

    return provider_cls(
        alias=alias,
        model_name=model_name,
        mode=mode,
        no_cache=no_cache,
        replay=replay,
        cache=cache,
        **cfg,
    )
