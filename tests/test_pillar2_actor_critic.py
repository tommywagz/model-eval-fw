"""Tests for Pillar 2: Standardized Actor-Critic Evaluation Engine (Qwen, MiniMax, Kimi K)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmaxxer.critics import (
    DIMENSION_1_QWEN,
    DIMENSION_2_MINIMAX,
    DIMENSION_3_KIMI_K,
    INVARIANCE_SEED,
    INVARIANCE_TEMPERATURE,
    ActorCriticPanel,
    ArchitecturalCritic,
    CriticEvaluation,
    PlatformComplianceCritic,
    TestHarnessCritic,
    get_rubric_for_critic,
    load_critic_prompt_template,
)
from benchmaxxer.telemetry.cache import CriticCache


def test_rubric_dimensions_and_scoring_anchors() -> None:
    # Dimension 1: Architectural Coherence & Modularity - Qwen
    assert DIMENSION_1_QWEN.critic_name == "qwen"
    assert "Monolithic anti-patterns retained" in DIMENSION_1_QWEN.get_anchor_description(1)
    assert "Acceptable modular separation" in DIMENSION_1_QWEN.get_anchor_description(3)
    assert "Fully decoupled, idiomatic architecture" in DIMENSION_1_QWEN.get_anchor_description(5)

    # Dimension 2: Execution Correctness & Test Rigor - MiniMax
    assert DIMENSION_2_MINIMAX.critic_name == "minimax"
    assert "False passes, unhandled crashes" in DIMENSION_2_MINIMAX.get_anchor_description(1)
    assert "Catches primary errors, but misses boundary conditions" in DIMENSION_2_MINIMAX.get_anchor_description(3)
    assert "Exhaustive blackbox assertions" in DIMENSION_2_MINIMAX.get_anchor_description(5)

    # Dimension 3: Factual Grounding & Platform Compliance - Kimi K
    assert DIMENSION_3_KIMI_K.critic_name == "kimi_k"
    assert "Hallucinated API flags, invalid IAM permissions" in DIMENSION_3_KIMI_K.get_anchor_description(1)
    assert "Functionally compliant with minor schema discrepancies" in DIMENSION_3_KIMI_K.get_anchor_description(3)
    assert "100% schema-compliant API integrations" in DIMENSION_3_KIMI_K.get_anchor_description(5)

    assert get_rubric_for_critic("critic-qwen") == DIMENSION_1_QWEN
    assert get_rubric_for_critic("critic-minimax") == DIMENSION_2_MINIMAX
    assert get_rubric_for_critic("critic-kimi-k") == DIMENSION_3_KIMI_K


def test_versioned_prompt_templates_and_invariance_controls() -> None:
    for name in ("qwen", "minimax", "kimi_k"):
        tpl = load_critic_prompt_template(name, version="v1")
        assert tpl["version"] == "v1"
        assert tpl["invariance_controls"]["temperature"] == INVARIANCE_TEMPERATURE == 0.0
        assert tpl["invariance_controls"]["seed"] == INVARIANCE_SEED == 42
        assert "{candidate_output}" in tpl["prompt_template"]


def test_critic_evaluation_pydantic_validation() -> None:
    valid = CriticEvaluation(
        critic_name="qwen",
        dimension="Architectural Coherence & Modularity",
        score=5,
        qualitative_critique="Clean modular separation.",
        detected_anomalies=[],
        remediation_advice="None",
        normalized_score=100.0,
    )
    assert valid.score == 5
    assert valid.normalized_score == 100.0

    # Score out of bounds (must be 1..5)
    with pytest.raises(ValidationError):
        CriticEvaluation(
            critic_name="qwen",
            dimension="Architectural Coherence & Modularity",
            score=6,
            qualitative_critique="Invalid score",
            detected_anomalies=[],
            normalized_score=100.0,
        )

    # Normalized score out of bounds (must be 0.0..100.0)
    with pytest.raises(ValidationError):
        CriticEvaluation(
            critic_name="minimax",
            dimension="Execution Correctness & Test Rigor",
            score=4,
            qualitative_critique="Invalid normalized score",
            detected_anomalies=[],
            normalized_score=120.0,
        )


def test_actor_critic_panel_positive_vs_negative_discrimination(tmp_path: Path) -> None:
    critic_cache = CriticCache(base_dir=tmp_path / "critic_cache")
    panel = ActorCriticPanel(mode="mock", critic_cache=critic_cache)

    assert isinstance(panel.qwen, ArchitecturalCritic)
    assert isinstance(panel.minimax, TestHarnessCritic)
    assert isinstance(panel.kimi_k, PlatformComplianceCritic)

    # 1. Evaluate a well-structured positive artifact
    pos_summary = panel.evaluate_candidate(
        scenario_id="complex_skill_synthesis",
        prompt="Synthesize modular ADK skill.",
        candidate_output=(
            "class CleanTelemetryService:\n"
            "    def __init__(self, bq_client):\n"
            "        self.bq_client = bq_client\n"
        ),
        test_context={"status": "PASS", "teardown_verified": True},
    )
    assert pos_summary.composite_score == 5.0
    assert pos_summary.composite_normalized_score == 100.0
    assert pos_summary.passed_threshold is True
    assert pos_summary.anomaly_count == 0
    assert set(pos_summary.evaluations.keys()) == {"qwen", "minimax", "kimi_k"}
    assert panel.qwen.evaluator.last_call_params == {"temperature": 0.0, "seed": 42}

    # 2. Evaluate a defective negative artifact
    neg_summary = panel.evaluate_candidate(
        scenario_id="complex_skill_synthesis",
        prompt="Synthesize modular ADK skill.",
        candidate_output=(
            "MONOLITHIC_GLOBAL_STATE = {}\n"
            "# HALLUCINATED_FLAG roles/owner_all_wildcards UNHANDLED_CRASH"
        ),
        test_context={"status": "FAIL", "teardown_verified": False},
    )
    assert neg_summary.composite_score == 1.0
    assert neg_summary.composite_normalized_score == 20.0
    assert neg_summary.passed_threshold is False
    assert neg_summary.anomaly_count >= 3


def test_resolve_frontier_critic_model_avoids_candidate_and_provisioned_throughput() -> None:
    from benchmaxxer.critics import resolve_frontier_critic_model

    # Gemini candidate models resolve to Claude frontier model on Vertex
    assert resolve_frontier_critic_model("gemini-1.5-pro") == "claude-3-5-sonnet"
    assert resolve_frontier_critic_model("gemini-1.5-flash") == "claude-3-5-sonnet"

    # Claude candidate models resolve to Gemini frontier model on Vertex
    assert resolve_frontier_critic_model("claude-3-5-sonnet") == "gemini-1.5-pro"
    assert resolve_frontier_critic_model("claude-3-5-haiku") == "gemini-1.5-pro"

    # Other open-weight / candidate models resolve to Claude 3.5 Sonnet
    assert resolve_frontier_critic_model("llama-3.1-70b") == "claude-3-5-sonnet"
    assert resolve_frontier_critic_model(None) == "claude-3-5-sonnet"

    # Preferred critic override respected as long as it differs from candidate
    assert resolve_frontier_critic_model("gemini-1.5-pro", preferred_critic="claude-3-5-haiku") == "claude-3-5-haiku"
    assert resolve_frontier_critic_model("gemini-1.5-pro", preferred_critic="gemini-1.5-pro") == "claude-3-5-sonnet"


def test_actor_critic_panel_switches_to_frontier_model_different_from_candidate(tmp_path: Path) -> None:
    critic_cache = CriticCache(base_dir=tmp_path / "cache")

    # 1. Candidate is Gemini -> Critics automatically switch to Claude 3.5 Sonnet
    panel_gemini = ActorCriticPanel(
        mode="mock",
        critic_cache=critic_cache,
        candidate_model="gemini-1.5-pro",
    )
    assert panel_gemini.critic_alias == "claude-3-5-sonnet"
    for critic in panel_gemini.critics:
        assert critic.critic_alias == "claude-3-5-sonnet"

    # 2. Candidate is Claude -> Critics automatically switch to Gemini 1.5 Pro
    panel_claude = ActorCriticPanel(
        mode="mock",
        critic_cache=critic_cache,
        candidate_model="claude-3-5-sonnet",
    )
    assert panel_claude.critic_alias == "gemini-1.5-pro"
    for critic in panel_claude.critics:
        assert critic.critic_alias == "gemini-1.5-pro"


def test_scenario_execution_with_frontier_critics_and_no_critics_mode(tmp_path: Path) -> None:
    from benchmaxxer.scenarios.runner import execute_scenario_run

    # 1. Run with frontier critics (candidate=gemini-1.5-pro -> critics use claude-3-5-sonnet)
    res_frontier = execute_scenario_run(
        scenario_id="oauth_api_enablement",
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=tmp_path / "cache1",
        critic_cache_dir=tmp_path / "ccache1",
        telemetry_dir=tmp_path / "telemetry1",
    )
    assert res_frontier["passed"] is True
    assert res_frontier["token_usage"]["critics"]["total_tokens"] > 0
    assert res_frontier["jev_evaluation"]["passed"] is True

    # 2. Run with no_critics=True -> Jev handles 100% of evaluation without LLM critic overhead
    res_no_critics = execute_scenario_run(
        scenario_id="oauth_api_enablement",
        model_alias="gemini-1.5-pro",
        mode="mock",
        no_critics=True,
        cache_dir=tmp_path / "cache2",
        critic_cache_dir=tmp_path / "ccache2",
        telemetry_dir=tmp_path / "telemetry2",
    )
    assert res_no_critics["passed"] is True
    assert res_no_critics["actor_critic_scores"] is None
    assert res_no_critics["token_usage"]["critics"]["total_tokens"] == 0
    assert res_no_critics["token_usage"]["critic_cost_usd"] == 0.0
    assert res_no_critics["jev_evaluation"]["passed"] is True
    assert res_no_critics["rubric_score"] == 5
