"""Tests for Pillar 3: Manual Assessment & Inspection Mode (Human-in-the-Loop)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from rich.console import Console

from benchmaxxer.scenarios.runner import execute_scenario_run
from benchmaxxer.ui.inspector import (
    main as inspector_main,
    render_run_inspection,
    run_manual_calibration,
)


def test_inspector_ui_renders_metadata_diffs_and_critic_panel(tmp_path: Path) -> None:
    run_result = execute_scenario_run(
        scenario_id="complex_skill_synthesis",
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=tmp_path / "cache",
        critic_cache_dir=tmp_path / "critic_cache",
        telemetry_dir=tmp_path / "telemetry",
    )

    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=120)
    render_run_inspection(run_result, console=console)
    output = buf.getvalue()

    assert "BenchMaxxer Run Inspector" in output
    assert "complex_skill_synthesis" in output
    assert "gemini-1.5-pro" in output
    assert "Side-by-Side Code Comparison" in output
    assert "Actor-Critic Panel Breakdown" in output
    assert "Qwen" in output
    assert "MiniMax" in output
    assert "Kimi K" in output


def test_inspector_cli_latest_and_run_id(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    run_result = execute_scenario_run(
        scenario_id="oauth_api_enablement",
        model_alias="gemini-1.5-pro",
        mode="mock",
        cache_dir=tmp_path / "cache",
        critic_cache_dir=tmp_path / "critic_cache",
        telemetry_dir=telemetry_dir,
    )

    exit_latest = inspector_main(["--latest", "--telemetry-dir", str(telemetry_dir)])
    assert exit_latest == 0

    exit_by_id = inspector_main(
        ["--run-id", run_result["run_id"], "--telemetry-dir", str(telemetry_dir)]
    )
    assert exit_by_id == 0


def test_interactive_manual_calibration_saves_report(tmp_path: Path) -> None:
    reports_dir = tmp_path / "manual_evals"
    responses = iter(["4", "Reviewed architecture and verified ADK schema grounding.", "y", "Calibrated minor edge case."])

    run_result = execute_scenario_run(
        scenario_id="complex_skill_synthesis",
        model_alias="gemini-1.5-pro",
        mode="mock",
        manual_eval=True,
        cache_dir=tmp_path / "cache",
        critic_cache_dir=tmp_path / "critic_cache",
        telemetry_dir=tmp_path / "telemetry",
        reports_dir=reports_dir,
        manual_input_fn=lambda _prompt: next(responses),
    )

    report_file = reports_dir / f"{run_result['run_id']}.json"
    assert report_file.exists()
    report_data = json.loads(report_file.read_text(encoding="utf-8"))

    assert report_data["run_id"] == run_result["run_id"]
    assert report_data["human_evaluation"]["score"] == 4
    assert report_data["human_evaluation"]["override_enabled"] is True
    assert "inter_rater_reliability" in report_data
    assert "actor_critic_panel" in report_data
