"""Tests for Orchestrator SCENARIOS.MD parsing and backlog management."""

from __future__ import annotations

import json
from pathlib import Path

from benchmaxxer.orchestrator.backlog import BacklogManager
from benchmaxxer.orchestrator.parser import parse_scenarios_markdown


def test_parse_scenarios_markdown_extracts_all_13_scenarios() -> None:
    scenarios = parse_scenarios_markdown("SCENARIOS.MD")
    assert len(scenarios) == 13

    # Check first scenario
    s1 = scenarios[0]
    assert s1.sequence_number == 1
    assert s1.job_id == "job-01-oauth-api-enablement"
    assert s1.suite == "Cloud Tool Writing Proficiency"
    assert s1.difficulty == "Easy"
    assert "Provide the model with access to a service account" in s1.scenario_description
    assert len(s1.features_under_test) >= 3
    assert len(s1.target_metrics) >= 1
    assert s1.target_metrics[0]["name"] == "Average Pass Rate"
    assert "MockIAMOAuthService" in s1.creator_guidance["required_mocks"]

    # Check complex skill synthesis scenario
    s13 = scenarios[12]
    assert s13.sequence_number == 13
    assert s13.job_id == "job-13-complex-skill-synthesis"
    assert s13.difficulty == "Hard"
    assert "Synthesize a multi-step research and analysis skill" in s13.scenario_description
    assert len(s13.features_under_test) >= 4
    metric_names = [m["name"] for m in s13.target_metrics]
    assert "Actor-Critic Quality Score" in metric_names


def test_backlog_manager_populates_manifests_symlinks_and_backlog_md(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"
    manager = BacklogManager(jobs_dir=jobs_dir, scenarios_file="SCENARIOS.MD")

    manifest_dicts = manager.populate_backlog_from_scenarios()
    assert len(manifest_dicts) == 13

    # Verify manifests directory
    manifest_files = sorted(jobs_dir.glob("manifests/*.json"))
    assert len(manifest_files) == 13

    # Verify pending symlinks
    pending_files = sorted(jobs_dir.glob("pending/*.json"))
    assert len(pending_files) == 13

    # Verify BACKLOG.md and backlog.json exist
    backlog_md = jobs_dir / "BACKLOG.md"
    assert backlog_md.exists()
    content_md = backlog_md.read_text(encoding="utf-8")
    assert "BenchMaxxer Orchestrator Scenario Backlog" in content_md
    assert "job-01-oauth-api-enablement" in content_md
    assert "job-13-complex-skill-synthesis" in content_md

    backlog_json = jobs_dir / "backlog.json"
    assert backlog_json.exists()
    data_json = json.loads(backlog_json.read_text(encoding="utf-8"))
    assert data_json["total_scenarios"] == 13

    # Test dispatch_next_job
    dispatched = manager.dispatch_next_job("test_creator")
    assert dispatched is not None
    assert dispatched["job_id"] == "job-01-oauth-api-enablement"

    # Pending count should decrease by 1
    remaining_pending = sorted(jobs_dir.glob("pending/*.json"))
    assert len(remaining_pending) == 12

    # Active creator directory should contain current_job.json
    active_job_file = jobs_dir / "active" / "test_creator" / "current_job.json"
    assert active_job_file.exists()
    active_data = json.loads(active_job_file.read_text(encoding="utf-8"))
    assert active_data["job_id"] == "job-01-oauth-api-enablement"
    assert active_data["features_under_test"] is not None
