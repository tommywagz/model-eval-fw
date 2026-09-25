"""Unified Model Provider & Endpoint Abstraction Layer for BenchMaxxer."""

from benchmaxxer.models.base import BaseModelClient, ModelResponse
from benchmaxxer.models.factory import get_model_client, load_model_registry
from benchmaxxer.models.providers import (
    OpenAICompatibleClient,
    VertexAnthropicClient,
    VertexEndpointClient,
    VertexGenAIClient,
)

__all__ = [
    "BaseModelClient",
    "ModelResponse",
    "OpenAICompatibleClient",
    "VertexAnthropicClient",
    "VertexEndpointClient",
    "VertexGenAIClient",
    "get_model_client",
    "load_model_registry",
]
