"""Tests for Test, Suite, and Framework Level Timers, Project .env, and @.agents/scripts/tokens Cost Assessment."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from benchmaxxer.scenarios.runner import (
    execute_framework_run,
    execute_scenario_run,
    execute_suite_run,
)
from benchmaxxer.telemetry.timer import ExecutionTimer
from benchmaxxer.telemetry.tokens import (
    TokensScriptBridge,
    load_project_dotenv,
    resolve_project_dotenv,
)


def test_project_dotenv_and_tokens_script_integration() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    dotenv_path = resolve_project_dotenv()
    assert dotenv_path == repo_root / ".env"
    assert dotenv_path.is_file()

    info = load_project_dotenv(dotenv_path)
    assert info["exists"] is True

    required_keys = [
        "TOKEN_OVERLAY_REFRESH_SECONDS",
        "OPENAI_ADMIN_KEY",
        "ANTHROPIC_ADMIN_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_ACCESS_TOKEN",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "QWEN_API_KEY",
        "MINIMAX_API_KEY",
        "KIMI_API_KEY",
        "MOONSHOT_API_KEY",
    ]
    for key in required_keys:
        assert key in info["loaded_keys"], f"Expected key '{key}' in project .env"

    # Verify .agents/scripts/tokens --check executes cleanly using the project .env
    tokens_script = repo_root / ".agents" / "scripts" / "tokens"
    assert tokens_script.is_file()
    proc = subprocess.run(
        [str(tokens_script), "--check"],
        capture_output=True,
        text=True,
        check=True,
    )
    readings = json.loads(proc.stdout)
    assert isinstance(readings, list)
    assert len(readings) == 4
    provider_names = {r["name"] for r in readings}
    assert provider_names == {
        "Google AI Studio",
        "Google Cloud Console",
        "Claude Platform",
        "OpenAI Platform",
    }


def test_execution_timer_phases_and_hierarchy() -> None:
    with ExecutionTimer(name="unit_test_timer", level="test") as timer:
        with timer.phase("candidate_generation"):
            _ = sum(range(1000))
        with timer.phase("sandbox_execution"):
            _ = sum(range(1000))
        with timer.phase("actor_critic_evaluation"):
            _ = sum(range(1000))

    data = timer.to_dict()
    assert data["level"] == "test"
    assert data["duration_ms"] >= 0.0
    assert data["duration_seconds"] >= 0.0
    assert set(data["phase_timings_ms"].keys()) == {
        "candidate_generation",
        "sandbox_execution",
        "actor_critic_evaluation",
    }


def test_test_suite_and_framework_level_time_and_token_cost_results(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    critic_cache_dir = tmp_path / "critic_cache"
    telemetry_dir = tmp_path / "telemetry"

    # 1. Test-level execution
    test_res = execute_scenario_run(
        scenario_id="oauth_api_enablement",
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=cache_dir,
        critic_cache_dir=critic_cache_dir,
        telemetry_dir=telemetry_dir,
    )
    assert test_res["duration_ms"] > 0.0
    assert test_res["duration_seconds"] > 0.0
    assert test_res["timing"]["level"] == "test"
    assert test_res["timing"]["suite_slug"] == "cloud_tool_writing"
    assert "candidate_generation" in test_res["timing"]["phase_timings_ms"]
    assert "sandbox_execution" in test_res["timing"]["phase_timings_ms"]
    assert "actor_critic_evaluation" in test_res["timing"]["phase_timings_ms"]

    assert test_res["token_usage"]["level"] == "test"
    assert test_res["token_usage"]["total_tokens"] > test_res["input_tokens"] + test_res["output_tokens"]
    assert test_res["token_usage"]["critics"]["total_tokens"] > 0
    assert test_res["token_usage"]["total_estimated_cost_usd"] > 0.0
    assert "providers" in test_res["token_usage"]["tokens_script_telemetry"]

    # 2. Suite-level execution
    suite_res = execute_suite_run(
        suite_id="agent_skill_creation",
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=cache_dir,
        critic_cache_dir=critic_cache_dir,
        telemetry_dir=telemetry_dir,
    )
    assert suite_res["level"] == "suite"
    assert suite_res["suite_slug"] == "agent_skill_creation"
    assert suite_res["test_count"] == 4
    assert suite_res["passed_count"] == 4
    assert suite_res["duration_ms"] > 0.0
    assert suite_res["timing"]["level"] == "suite"
    assert len(suite_res["timing"]["per_test_timings"]) == 4
    assert suite_res["token_usage"]["level"] == "suite"
    assert suite_res["token_usage"]["total_tokens"] > 0
    assert suite_res["token_usage"]["total_estimated_cost_usd"] > 0.0
    assert len(suite_res["token_usage"]["per_test_tokens"]) == 4

    # 3. Framework-level execution across all 3 suites (13 tests total)
    fw_res = execute_framework_run(
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=cache_dir,
        critic_cache_dir=critic_cache_dir,
        telemetry_dir=telemetry_dir,
    )
    assert fw_res["level"] == "framework"
    assert fw_res["suite_count"] == 3
    assert fw_res["test_count"] == 13
    assert fw_res["passed_count"] == 13
    assert fw_res["duration_ms"] > 0.0
    assert fw_res["timing"]["level"] == "framework"
    assert len(fw_res["timing"]["per_suite_timings"]) == 3
    assert len(fw_res["timing"]["per_test_timings"]) == 13
    assert fw_res["token_usage"]["level"] == "framework"
    assert fw_res["token_usage"]["total_tokens"] > suite_res["token_usage"]["total_tokens"]
    assert fw_res["token_usage"]["total_estimated_cost_usd"] > suite_res["token_usage"]["total_estimated_cost_usd"]
    assert len(fw_res["token_usage"]["per_suite_tokens"]) == 3
    assert len(fw_res["token_usage"]["per_test_tokens"]) == 13

    # 4. Verify .agents/scripts/tokens --benchmaxxer summarizes test, suite, and framework costs
    repo_root = Path(__file__).resolve().parent.parent
    tokens_script = repo_root / ".agents" / "scripts" / "tokens"
    proc_bm = subprocess.run(
        [str(tokens_script), "--benchmaxxer", "--telemetry-dir", str(telemetry_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    bm_summary = json.loads(proc_bm.stdout)
    assert "framework_level" in bm_summary
    assert "suite_level" in bm_summary
    assert "test_level" in bm_summary
    assert bm_summary["framework_level"]["total_tokens"] > 0
    assert bm_summary["framework_level"]["total_estimated_cost_usd"] > 0.0


def test_tokens_script_bridge_delta_calculation() -> None:
    before = {
        "timestamp": "2026-09-28T18:00:00Z",
        "script_path": ".agents/scripts/tokens",
        "dotenv_path": ".env",
        "configured_providers": ["OpenAI Platform"],
        "providers": [
            {
                "name": "OpenAI Platform",
                "tokens": 1000,
                "credits": 10.0,
                "detail": "ok",
                "status": "ok",
            }
        ],
    }
    after = {
        "timestamp": "2026-09-28T18:01:00Z",
        "script_path": ".agents/scripts/tokens",
        "dotenv_path": ".env",
        "configured_providers": ["OpenAI Platform"],
        "providers": [
            {
                "name": "OpenAI Platform",
                "tokens": 1450,
                "credits": 9.85,
                "detail": "ok",
                "status": "ok",
            }
        ],
    }
    delta = TokensScriptBridge.compute_delta(before, after)
    assert delta["total_provider_token_delta"] == 450
    assert delta["total_provider_credit_delta_usd"] == 0.15
    assert delta["provider_deltas"]["OpenAI Platform"]["token_delta"] == 450
    assert delta["provider_deltas"]["OpenAI Platform"]["credit_used_usd"] == 0.15
