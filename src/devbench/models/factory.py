"""Model Factory and Registry Loader for devbench."""

from __future__ import annotations

import re
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
    "gemini-3.5-flash": {
        "provider": "vertex_genai",
        "model_name": "gemini-3.5-flash-001",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00010,
        "cost_per_1k_output_usd": 0.00040,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "gemini-3.1-pro": {
        "provider": "vertex_genai",
        "model_name": "gemini-3.1-pro-001",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00150,
        "cost_per_1k_output_usd": 0.00600,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 16384, "seed": 42},
    },
    "gemini-3.8-flash": {
        "provider": "vertex_genai",
        "model_name": "gemini-3.8-flash-001",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
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
        "model_name": "claude-sonnet-5-5@20260514",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
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
        "model_name": "gemini-4-argon-001",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
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
        "model_name": "claude-sonnet-5-5@20260514",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
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
    "gemini-3-pro": {
        "provider": "vertex_genai",
        "model_name": "gemini-3-pro-001",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00200,
        "cost_per_1k_output_usd": 0.01200,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "gemini-3-flash": {
        "provider": "vertex_genai",
        "model_name": "gemini-3-flash-001",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00050,
        "cost_per_1k_output_usd": 0.00300,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "claude-sonnet-4.6": {
        "provider": "vertex_anthropic",
        "model_name": "claude-sonnet-4-6",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192},
    },
    "claude-sonnet-4-6": {
        "provider": "vertex_anthropic",
        "model_name": "claude-sonnet-4-6",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192},
    },
    "claude-sonnet-4.5": {
        "provider": "vertex_anthropic",
        "model_name": "claude-sonnet-4-5",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192},
    },
    "claude-sonnet-4-5": {
        "provider": "vertex_anthropic",
        "model_name": "claude-sonnet-4-5",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00300,
        "cost_per_1k_output_usd": 0.01500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192},
    },
    "claude-haiku-4.5": {
        "provider": "vertex_anthropic",
        "model_name": "claude-haiku-4-5",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00100,
        "cost_per_1k_output_usd": 0.00500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096},
    },
    "claude-haiku-4-5": {
        "provider": "vertex_anthropic",
        "model_name": "claude-haiku-4-5",
        "project_id": "devbench-eval-sandbox",
        "location": "us-east5",
        "cost_per_1k_input_usd": 0.00100,
        "cost_per_1k_output_usd": 0.00500,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096},
    },
    "grok-2-mini": {
        "provider": "vertex_maas",
        "model_name": "xai/grok-2-mini",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00020,
        "cost_per_1k_output_usd": 0.00100,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "grok": {
        "provider": "vertex_maas",
        "model_name": "xai/grok-2-mini",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00020,
        "cost_per_1k_output_usd": 0.00100,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "llama-3.1-8b": {
        "provider": "vertex_maas",
        "model_name": "meta/llama-3.1-8b-instruct",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00015,
        "cost_per_1k_output_usd": 0.00060,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "llama": {
        "provider": "vertex_maas",
        "model_name": "meta/llama-3.1-8b-instruct",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00015,
        "cost_per_1k_output_usd": 0.00060,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "muse": {
        "provider": "vertex_maas",
        "model_name": "google/muse",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00010,
        "cost_per_1k_output_usd": 0.00030,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "mistral-small": {
        "provider": "vertex_maas",
        "model_name": "mistralai/mistral-small-latest",
        "project_id": "devbench-eval-sandbox",
        "location": "europe-west4",
        "cost_per_1k_input_usd": 0.00010,
        "cost_per_1k_output_usd": 0.00030,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "mistral-large-3": {
        "provider": "vertex_maas",
        "model_name": "mistralai/mistral-large-3",
        "project_id": "devbench-eval-sandbox",
        "location": "europe-west4",
        "cost_per_1k_input_usd": 0.00200,
        "cost_per_1k_output_usd": 0.00600,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    },
    "eleven-labs": {
        "provider": "vertex_maas",
        "model_name": "elevenlabs/eleven-turbo-v2",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00015,
        "cost_per_1k_output_usd": 0.00050,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096, "seed": 42},
    },
    "eleven-turbo-v2": {
        "provider": "vertex_maas",
        "model_name": "elevenlabs/eleven-turbo-v2",
        "project_id": "devbench-eval-sandbox",
        "location": "us-central1",
        "cost_per_1k_input_usd": 0.00015,
        "cost_per_1k_output_usd": 0.00050,
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 4096, "seed": 42},
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


def validate_model_version(alias: str, model_name: str = "") -> None:
    """Enforce that the oldest configurable Gemini model is Gemini 3 and Claude is Claude 4.5."""
    check_str = f"{alias} {model_name}".lower()

    # Check Gemini: reject versions older than Gemini 3 (e.g. 1.0, 1.5, 2.0, 2.5)
    if "gemini" in check_str:
        if re.search(r"gemini[-_]?[12](\.|$)", check_str) or any(
            v in check_str for v in ("gemini-1.5", "gemini-1.0", "gemini-2.0", "gemini-2.5")
        ):
            raise ValueError(
                f"Model '{alias}' cannot be configured: the oldest configurable Gemini model is Gemini 3 "
                "(e.g. gemini-3.1-pro, gemini-3.8-flash, gemini-3-pro)."
            )

    # Check Claude: reject versions older than Claude 4.5 (e.g. Claude 3, 3.5, 3.7, 4.0, 4.1)
    if "claude" in check_str:
        m = re.search(r"claude[-_]?(?:opus[-_]|sonnet[-_]|haiku[-_])?([0-9]+(?:\.[0-9]+|-?[0-9]+)?)", check_str)
        if m:
            ver_str = m.group(1).replace("-", ".")
            try:
                ver_parts = [int(p) for p in ver_str.split(".") if p.isdigit()]
                if ver_parts:
                    major = ver_parts[0]
                    minor = ver_parts[1] if len(ver_parts) > 1 else 0
                    if major < 4 or (major == 4 and minor < 5):
                        raise ValueError(
                            f"Model '{alias}' cannot be configured: the oldest configurable Claude model is Claude 4.5 "
                            "(e.g. claude-sonnet-4.5, claude-haiku-4.5, claude-opus-5.1)."
                        )
            except ValueError:
                raise
            except Exception:
                pass
        elif any(v in check_str for v in ("claude-3", "claude-3-5", "claude-3.5", "claude-3-7", "claude-4-0", "claude-4-1")):
            raise ValueError(
                f"Model '{alias}' cannot be configured: the oldest configurable Claude model is Claude 4.5 "
                "(e.g. claude-sonnet-4.5, claude-haiku-4.5, claude-opus-5.1)."
            )


def get_model_client(
    alias: str = "gemini-3.5-flash",
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

    validate_model_version(alias, overrides.get("model_name", ""))
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
