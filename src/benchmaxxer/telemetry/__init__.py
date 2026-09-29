"""Telemetry, deterministic caching, hierarchical timing, token cost assessment, and structured run logging for BenchMaxxer."""

from benchmaxxer.telemetry.cache import (
    CriticCache,
    ReplayCacheMissError,
    ResponseCache,
    compute_candidate_cache_key,
    compute_critic_cache_key,
)
from benchmaxxer.telemetry.logger import RunRecord, TelemetryLogger
from benchmaxxer.telemetry.timer import (
    ExecutionTimer,
    build_framework_timing_result,
    build_suite_timing_result,
    build_test_timing_result,
)
from benchmaxxer.telemetry.tokens import (
    TokensScriptBridge,
    build_framework_token_result,
    build_suite_token_result,
    build_test_token_result,
    load_project_dotenv,
    resolve_project_dotenv,
    summarize_logged_token_costs,
)

__all__ = [
    "CriticCache",
    "ExecutionTimer",
    "ReplayCacheMissError",
    "ResponseCache",
    "RunRecord",
    "TelemetryLogger",
    "TokensScriptBridge",
    "build_framework_timing_result",
    "build_framework_token_result",
    "build_suite_timing_result",
    "build_suite_token_result",
    "build_test_timing_result",
    "build_test_token_result",
    "compute_candidate_cache_key",
    "compute_critic_cache_key",
    "load_project_dotenv",
    "resolve_project_dotenv",
    "summarize_logged_token_costs",
]
