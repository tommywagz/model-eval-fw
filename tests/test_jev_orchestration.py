"""Tests for Jev Evaluation Framework & Orchestration Suite.

Validates:
1. Jev-Noul (State & Blackbox Verification)
2. Jev-Classification (Structure, Modularity & Dispatch Accuracy)
3. Jev-Confidence Vector (Compliance, IAM Boundaries & Schema Grounding)
4. Normalized Rubric Mapping (1-5 Scale)
5. Difficulty-Weighted Composite Scoring Formula (Easy 20%, Medium 30%, Hard 50%)
6. Multi-Scenario and Multi-Model Evaluation Telemetry
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmaxxer.critics import (
    DIFFICULTY_WEIGHTS,
    RUBRIC_RATINGS,
    SCENARIO_EVALUATION_SPECS,
    ComplexityMetrics,
    ComplianceCheckReport,
    ConfusionMatrix,
    JevAggregateEvaluation,
    JevClassificationCritic,
    JevClassificationResult,
    JevConfidenceVectorCritic,
    JevConfidenceVectorResult,
    JevNoulCritic,
    JevNoulResult,
    JevOrchestrator,
    JevScenarioEvaluation,
    analyze_codebase_refactoring,
    calculate_ast_cyclomatic_complexity,
    compute_composite_score,
    compute_dispatch_confusion_matrix,
    load_rubric_weights,
    map_raw_to_rubric_score,
)
from benchmaxxer.execution.sandbox import ExecutionSandbox
from benchmaxxer.scenarios.runner import (
    execute_framework_run,
    execute_scenario_run,
    execute_suite_run,
)


def test_rubric_weights_config_loading() -> None:
    weights = load_rubric_weights()
    assert weights["Easy"] == 0.20
    assert weights["Medium"] == 0.30
    assert weights["Hard"] == 0.50


def test_normalized_rubric_mapping_criteria() -> None:
    # Score 1: Success rate < 50% or critical errors
    s1, r1 = map_raw_to_rubric_score(success_rate=45.0)
    assert s1 == 1
    assert r1 == RUBRIC_RATINGS[1]

    s1_crit, _ = map_raw_to_rubric_score(success_rate=98.0, has_critical_errors=True)
    assert s1_crit == 1

    # Score 2: Success rate 50%-69% or minor schema violations
    s2, r2 = map_raw_to_rubric_score(success_rate=65.0)
    assert s2 == 2
    assert r2 == RUBRIC_RATINGS[2]

    s2_schema, _ = map_raw_to_rubric_score(success_rate=92.0, has_minor_schema_violations=True)
    assert s2_schema == 2

    # Score 3: Success rate 70%-84%
    s3, r3 = map_raw_to_rubric_score(success_rate=78.0)
    assert s3 == 3
    assert r3 == RUBRIC_RATINGS[3]

    # Score 4: Success rate 85%-94% or high F1 (> 0.85)
    s4, r4 = map_raw_to_rubric_score(success_rate=90.0, f1_score=0.90)
    assert s4 == 4
    assert r4 == RUBRIC_RATINGS[4]

    # Score 5: Success rate >= 95%, 100% deterministic test pass
    s5, r5 = map_raw_to_rubric_score(success_rate=99.0, f1_score=1.0, efficiency_delta=60.0)
    assert s5 == 5
    assert r5 == RUBRIC_RATINGS[5]


def test_composite_scoring_formula() -> None:
    # 3 difficulty tiers: Easy (5.0), Medium (4.0), Hard (3.0)
    # Expected: 5.0*0.20 + 4.0*0.30 + 3.0*0.50 = 1.0 + 1.2 + 1.5 = 3.7
    scores = {
        "Easy": [5.0, 5.0],
        "Medium": [4.0],
        "Hard": [3.0, 3.0],
    }
    composite = compute_composite_score(scores, DIFFICULTY_WEIGHTS)
    assert composite == pytest.approx(3.7, abs=1e-3)


def test_jev_noul_state_and_blackbox_verification() -> None:
    critic = JevNoulCritic(mode="mock")
    sandbox = ExecutionSandbox(mode="mock")

    with sandbox.lifecycle_scope() as lifecycle:
        # Provision services
        sandbox.cloud_run.deploy_service("svc-test", "gcr.io/test/img:v1")
        sandbox.storage.bq_insert_rows("tbl", [{"col": "val"}])
        sandbox.storage.gcs_upload_json("gs://test-bucket/file.json", {"k": "v"})
        lifecycle.register(
            resource_type="cloud_run_service",
            resource_id="svc-test",
            cleanup_fn=lambda: sandbox.cloud_run.delete_service("svc-test"),
        )

    assertions = [
        {"name": "mock_assert_1", "passed": True, "detail": "Assertion 1 ok"},
        {"name": "mock_assert_2", "passed": True, "detail": "Assertion 2 ok"},
    ]

    result = critic.evaluate_state_and_assertions(
        scenario_id="storage_operations",
        candidate_output="def store_record(clients, record):\n    pass\n",
        sandbox=sandbox,
        lifecycle=lifecycle,
        assertions=assertions,
    )

    assert isinstance(result, JevNoulResult)
    assert result.passed is True
    assert result.rubric_score >= 4
    assert "storage_success_rate" in result.metrics
    assert "retrieval_success_rate" in result.metrics
    assert result.metrics["storage_success_rate"] == 100.0



def test_jev_noul_catches_deliberate_failures() -> None:
    critic = JevNoulCritic(mode="mock")
    result = critic.evaluate_state_and_assertions(
        scenario_id="oauth_api_enablement",
        candidate_output="DELIBERATE_FAILURE roles/owner_all_wildcards",
    )
    assert result.passed is False
    assert result.rubric_score == 1
    assert result.has_critical_errors is True


def test_jev_classification_confusion_matrix() -> None:
    critic = JevClassificationCritic()
    # Scenario: 3 expected skills, model dispatched 2 correct and 1 wrong
    res = critic.evaluate_dispatch(
        scenario_id="tool_skill_dispatching",
        dispatched_skills=["gcs_uploader", "bq_query", "wrong_skill"],
        expected_skills=["gcs_uploader", "bq_query", "vertex_search"],
    )

    assert isinstance(res, JevClassificationResult)
    cm = res.confusion_matrix
    assert cm is not None
    assert cm.true_positives == 2
    assert cm.false_positives == 1
    assert cm.false_negatives == 1
    assert cm.precision == pytest.approx(2 / 3, abs=1e-2)
    assert cm.recall == pytest.approx(2 / 3, abs=1e-2)
    assert cm.f1_score == pytest.approx(2 / 3, abs=1e-2)
    assert "precision_and_recall" in res.metrics


def test_jev_classification_cyclomatic_complexity_reduction() -> None:
    critic = JevClassificationCritic()
    baseline = "GLOBAL_STATE = {}\ndef monolith(req):\n    GLOBAL_STATE['k'] = req\n    return GLOBAL_STATE\n"
    refactored = (
        "class OrderService:\n"
        "    def __init__(self, repo):\n"
        "        self.repo = repo\n"
        "    def handle(self, req):\n"
        "        return self.repo.save(req)\n"
    )

    res = critic.evaluate_codebase_structure(
        scenario_id="bad_architecture_conversion",
        baseline_code=baseline,
        candidate_code=refactored,
    )
    assert isinstance(res, JevClassificationResult)
    assert res.passed is True
    assert res.rubric_score >= 3
    assert res.metrics["cyclomatic_complexity_reduction"] > 0.0
    assert res.complexity_metrics is not None
    assert res.complexity_metrics.global_mutable_state_detected is False


def test_jev_confidence_vector_compliance() -> None:
    critic = JevConfidenceVectorCritic()

    # 1. Valid compliant output
    valid_output = (
        "---\n"
        "name: test-skill\n"
        "description: Valid agent skill metadata.\n"
        "---\n\n"
        "def run_skill():\n"
        "    return {'status': 'ok'}\n"
    )
    res_valid = critic.evaluate_compliance(
        scenario_id="skill_scaffolding",
        candidate_output=valid_output,
    )
    assert isinstance(res_valid, JevConfidenceVectorResult)
    assert res_valid.passed is True
    assert res_valid.rubric_score >= 4
    assert res_valid.confidence_vector["iam_boundary"] == 100.0
    assert res_valid.confidence_vector["schema_adherence"] == 100.0

    # 2. Non-compliant output with wildcard role
    bad_output = '{"granted_roles": ["roles/owner_all_wildcards"]}'
    res_bad = critic.evaluate_compliance(
        scenario_id="oauth_api_enablement",
        candidate_output=bad_output,
    )
    assert res_bad.passed is False
    assert res_bad.rubric_score == 1
    assert res_bad.compliance_report.iam_boundary_valid is False


def test_jev_orchestrator_scenario_dispatch_and_weights() -> None:
    orchestrator = JevOrchestrator(mode="mock")

    # Evaluate Easy scenario
    easy_eval = orchestrator.evaluate_scenario(
        scenario_id="oauth_api_enablement",
        candidate_output='{"granted_roles": ["roles/aiplatform.user"]}',
    )
    assert easy_eval.difficulty == "Easy"
    assert easy_eval.difficulty_weight == 0.20
    assert easy_eval.passed is True
    assert easy_eval.rubric_score >= 3
    assert "average_pass_rate" in easy_eval.target_metrics

    # Evaluate Hard scenario
    hard_eval = orchestrator.evaluate_scenario(
        scenario_id="complex_skill_synthesis",
        candidate_output="class TelemetryOrchestrator:\n    pass\n",
    )
    assert hard_eval.difficulty == "Hard"
    assert hard_eval.difficulty_weight == 0.50
    assert hard_eval.passed is True


def test_end_to_end_suite_and_framework_jev_metrics(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    telemetry_dir = tmp_path / "telemetry"

    # Execute suite
    suite_res = execute_suite_run(
        suite_id="cloud_tool_writing",
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=cache_dir,
        telemetry_dir=telemetry_dir,
    )
    assert suite_res["passed"] is True
    assert suite_res["exit_code"] == 0
    assert "composite_score" in suite_res
    assert suite_res["composite_score"] >= 4.0
    assert "jev_evaluation" in suite_res
    assert len(suite_res["tests"]) == 5

    # Execute full framework
    fw_res = execute_framework_run(
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=cache_dir,
        telemetry_dir=telemetry_dir,
    )
    assert fw_res["passed"] is True
    assert fw_res["exit_code"] == 0
    assert fw_res["composite_score"] >= 4.0
    assert "difficulty_scores" in fw_res
    assert set(fw_res["difficulty_scores"].keys()) == {"Easy", "Medium", "Hard"}
    assert "target_metrics_summary" in fw_res
    assert "average_pass_rate" in fw_res["target_metrics_summary"]
    assert "storage_success_rate" in fw_res["target_metrics_summary"]
    assert "deployment_lifecycle_pass_rate" in fw_res["target_metrics_summary"]
    assert "pipeline_progress_score" in fw_res["target_metrics_summary"]
