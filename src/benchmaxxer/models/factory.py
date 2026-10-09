"""Model Factory and Registry Loader for BenchMaxxer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Type

import yaml

from benchmaxxer.models.base import BaseModelClient
from benchmaxxer.models.providers import (
    OpenAICompatibleClient,
    VertexAnthropicClient,
    VertexEndpointClient,
    VertexGenAIClient,
)
from benchmaxxer.telemetry.cache import ResponseCache

PROVIDER_MAP: Dict[str, Type[BaseModelClient]] = {
    "vertex_genai": VertexGenAIClient,
    "vertex_anthropic": VertexAnthropicClient,
    "vertex_endpoint": VertexEndpointClient,
    "openai_compatible": OpenAICompatibleClient,
}

DEFAULT_MODELS_FALLBACK: Dict[str, Dict[str, Any]] = {
    "gemini-4-argon": {
        "provider": "vertex_genai",
        "model_name": "gemini-4-argon-001",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00200,
        "cost_per_1k_output_usd": 0.00800,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 16384, "seed": 42},
    },
    "gemini-3.8-flash": {
        "provider": "vertex_genai",
        "model_name": "gemini-3.8-flash-001",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00015,
        "cost_per_1k_output_usd": 0.00060,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "fable-5.1": {
        "provider": "vertex_endpoint",
        "model_name": "fable-ai/fable-5.1-frontier",
        "endpoint_resource_name": "projects/benchmaxxer-eval-sandbox/locations/us-central1/endpoints/fable-5-1-ep",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00250,
        "cost_per_1k_output_usd": 0.01000,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "sonnet-5.5": {
        "provider": "vertex_anthropic",
        "model_name": "claude-sonnet-5-5@20260514",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192},
    },
    "gemini-3.5-pro": {
        "provider": "vertex_genai",
        "model_name": "gemini-3.5-pro-002",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00125,
        "cost_per_1k_output_usd": 0.00500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "gemini-1.5-pro": {
        "provider": "vertex_genai",
        "model_name": "gemini-1.5-pro-002",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00125,
        "cost_per_1k_output_usd": 0.00500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "gemini-1.5-flash": {
        "provider": "vertex_genai",
        "model_name": "gemini-1.5-flash-002",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.000075,
        "cost_per_1k_output_usd": 0.00030,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "claude-3-5-sonnet": {
        "provider": "vertex_anthropic",
        "model_name": "claude-3-5-sonnet-v2@20241022",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096},
    },
    "claude-3-5-haiku": {
        "provider": "vertex_anthropic",
        "model_name": "claude-3-5-haiku@20241022",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00080,
        "cost_per_1k_output_usd": 0.00400,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096},
    },
    "llama-4-405b": {
        "provider": "vertex_endpoint",
        "model_name": "meta/llama-4-405b-instruct",
        "endpoint_resource_name": "projects/benchmaxxer-eval-sandbox/locations/us-central1/endpoints/llama-4-405b-instruct-ep",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00150,
        "cost_per_1k_output_usd": 0.00450,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "llama-3.1-70b": {
        "provider": "vertex_endpoint",
        "model_name": "meta/llama-3.1-70b-instruct",
        "endpoint_resource_name": "projects/benchmaxxer-eval-sandbox/locations/us-central1/endpoints/llama-31-70b-instruct-ep",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00080,
        "cost_per_1k_output_usd": 0.00080,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096, "seed": 42},
    },
    "deepseek-r2": {
        "provider": "vertex_endpoint",
        "model_name": "deepseek-ai/deepseek-r2-reasoning",
        "endpoint_resource_name": "projects/benchmaxxer-eval-sandbox/locations/us-central1/endpoints/deepseek-r2-ep",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00055,
        "cost_per_1k_output_usd": 0.00220,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "mistral-large-3": {
        "provider": "vertex_endpoint",
        "model_name": "mistralai/mistral-large-3",
        "endpoint_resource_name": "projects/benchmaxxer-eval-sandbox/locations/europe-west4/endpoints/mistral-large-3-ep",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "europe-west4",
        "cost_per_1k_input_usd": 0.00200,
        "cost_per_1k_output_usd": 0.00600,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "qwen-3-72b": {
        "provider": "vertex_endpoint",
        "model_name": "Qwen/Qwen3-72B-Instruct",
        "endpoint_resource_name": "projects/benchmaxxer-eval-sandbox/locations/us-central1/endpoints/qwen3-72b-ep",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00080,
        "cost_per_1k_output_usd": 0.00160,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "critic-qwen": {
        "provider": "vertex_endpoint",
        "model_name": "Qwen/Qwen2.5-72B-Instruct",
        "endpoint_resource_name": "projects/benchmaxxer-eval-sandbox/locations/us-central1/endpoints/critic-qwen-25-72b-ep",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00080,
        "cost_per_1k_output_usd": 0.00080,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 2048, "seed": 42},
    },
    "critic-minimax": {
        "provider": "openai_compatible",
        "model_name": "MiniMax-Text-01",
        "base_url": "http://localhost:8000/v1",
        "project_id": "benchmaxxer-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00040,
        "cost_per_1k_output_usd": 0.00110,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 2048, "seed": 42},
    },
    "critic-kimi-k": {
        "provider": "openai_compatible",
        "model_name": "Kimi-K1.5-Instruct",
        "base_url": "http://localhost:8001/v1",
        "endpoint_resource_name": "projects/benchmaxxer-eval-sandbox/locations/us-central1/endpoints/critic-kimi-k-ep",
        "project_id": "benchmaxxer-eval-sandbox",
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
    from benchmaxxer.telemetry.tokens import load_project_dotenv

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
    return registry


def get_model_client(
    alias: str = "gemini-1.5-pro",
    mode: str = "mock",
    config_path: Optional[str | Path] = None,
    no_cache: bool = False,
    replay: bool = False,
    cache_dir: Optional[str | Path] = None,
    dotenv_path: Optional[str | Path] = None,
    **overrides: Any,
) -> BaseModelClient:
    """Factory method returning a configured BaseModelClient instance for the given alias."""
    import os
    from benchmaxxer.telemetry.tokens import load_project_dotenv

    load_project_dotenv(dotenv_path=dotenv_path)
    registry = load_model_registry(config_path=config_path)
    if alias not in registry:
        raise KeyError(
            f"Unknown model alias '{alias}'. Available aliases: {sorted(registry.keys())}"
        )

    cfg = dict(registry[alias])
    env_project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("VERTEX_PROJECT_ID")
    if env_project and "project_id" not in overrides:
        cfg["project_id"] = env_project
    env_location = os.environ.get("VERTEX_LOCATION")
    if env_location and "location" not in overrides and "location" not in registry[alias]:
        cfg["location"] = env_location
    cfg.update(overrides)

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
