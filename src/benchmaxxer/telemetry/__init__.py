"""Telemetry, deterministic caching, and structured run logging for BenchMaxxer."""

from benchmaxxer.telemetry.cache import (
    CriticCache,
    ReplayCacheMissError,
    ResponseCache,
    compute_candidate_cache_key,
    compute_critic_cache_key,
)
from benchmaxxer.telemetry.logger import RunRecord, TelemetryLogger

__all__ = [
    "CriticCache",
    "ReplayCacheMissError",
    "ResponseCache",
    "RunRecord",
    "TelemetryLogger",
    "compute_candidate_cache_key",
    "compute_critic_cache_key",
]
