"""Google Cloud project linking and Vertex AI Model Garden discovery for BenchMaxxer."""

from __future__ import annotations

from benchmaxxer.gcp.model_garden import (
    GcpAuthError,
    discover_model_garden,
    get_access_token,
    verify_gcp_project,
)

__all__ = [
    "GcpAuthError",
    "discover_model_garden",
    "get_access_token",
    "verify_gcp_project",
]
