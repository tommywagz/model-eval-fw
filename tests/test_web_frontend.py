"""Automated Regression Suite for BenchMaxxer Web Frontend, Argon Suite Creator, Telemetry, and Repo Inserter."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from benchmaxxer.ui.web.argon_agent import ArgonSuiteCreator
from benchmaxxer.ui.web.repo_inserter import RepoInserter
from benchmaxxer.ui.web.server import (
    BenchMaxxerRequestHandler,
    load_frontend_config,
    start_web_server,
)


@pytest.fixture(scope="module")
def web_server():
    """Start an ephemeral test instance of the BenchMaxxer ThreadingHTTPServer on a random free port."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    httpd = start_web_server(host="127.0.0.1", port=port, open_browser=False)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    # Wait for server ready
    ready = False
    for _ in range(20):
        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1.0) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.05)

    assert ready, "Web server failed to start within timeout"
    yield base_url

    httpd.shutdown()
    httpd.server_close()


# ============================================================================
# User Story 1: Frontier Model Garden Selection Toggle
# ============================================================================

def test_frontend_config_and_model_garden_models(web_server: str) -> None:
    """Verify that GCP Model Garden models are correctly configured and exposed via /api/models."""
    cfg = load_frontend_config()
    assert "model_garden" in cfg
    models = cfg["model_garden"]
    assert len(models) >= 3

    model_ids = {m["id"] for m in models}
    assert "gemini-1.5-pro" in model_ids
    assert "gemini-1.5-flash" in model_ids
    assert "claude-3-5-sonnet" in model_ids

    # Test REST API endpoint
    req = urllib.request.Request(f"{web_server}/api/models")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "models" in data
        retrieved_ids = {m["id"] for m in data["models"]}
        assert "gemini-1.5-pro" in retrieved_ids

        # Validate pricing attributes exist for non-technical users
        for m in data["models"]:
            assert "cost_per_1k_input_usd" in m
            assert "cost_per_1k_output_usd" in m
            assert "provider" in m
            assert "description" in m


# ============================================================================
# User Story 2: Argon-Backed Agent Dynamic Test Suite Creation
# ============================================================================

def test_argon_agent_suite_synthesis_and_registration(web_server: str) -> None:
    """Verify that the Argon-backed agent synthesizes a full test suite from natural language and registers it."""
    argon = ArgonSuiteCreator()

    # 1. Test Pillar & Difficulty Classification
    skill_classification = argon.classify_pillar_and_difficulty(
        "Build a complex multi-step ADK skill that validates API payload schemas."
    )
    assert skill_classification["pillar"] == "Agent Skill Creation + Use"
    assert skill_classification["suite_slug"] == "agent_skill_creation"
    assert skill_classification["difficulty"] in ("Medium", "Hard")

    gcp_classification = argon.classify_pillar_and_difficulty(
        "Deploy a containerized microservice to Cloud Run and configure IAM service account roles."
    )
    assert gcp_classification["pillar"] == "Google Cloud Platform (GCP) Operations"
    assert gcp_classification["suite_slug"] == "cloud_tool_writing"

    trans_classification = argon.classify_pillar_and_difficulty(
        "Translate a monolithic Node.js backend into a modular Go Gin microservice."
    )
    assert trans_classification["pillar"] == "Codebase Conversion & Refactoring Ability"
    assert trans_classification["suite_slug"] == "codebase_translation"

    # 2. Test via REST API endpoint /api/scenarios/generate
    payload = json.dumps({
        "prompt": "Create an agent skill that queries BigQuery logs and publishes anomalies to Pub/Sub.",
        "title": "BigQuery PubSub Alerting Skill",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{web_server}/api/scenarios/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res_data = json.loads(resp.read().decode("utf-8"))
        assert res_data["success"] is True
        spec = res_data["suite_spec"]

        assert spec["scenario_id"].startswith("argon_")
        assert "BigQuery" in spec["scenario_name"] or "Alerting" in spec["scenario_name"]
        assert spec["pillar"] in ("Agent Skill Creation + Use", "Google Cloud Platform (GCP) Operations")
        assert len(spec["assertions"]) >= 3
        assert len(spec["primary_metrics"]) >= 2
        assert "prompt" in spec
        assert "baseline_code" in spec


# ============================================================================
# User Story 3: Complete Time and Token Cost Telemetry
# ============================================================================

def test_eval_run_time_and_token_cost_telemetry(web_server: str) -> None:
    """Verify that running an evaluation accurately captures hierarchical timers and token costs."""
    # Execute synchronous evaluation for deterministic testing
    payload = json.dumps({
        "scenario_id": "oauth_api_enablement",
        "model_alias": "gemini-1.5-pro",
        "mode": "mock",
        "async": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{web_server}/api/eval/run",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        run_data = json.loads(resp.read().decode("utf-8"))
        assert run_data["status"] == "COMPLETED"
        assert run_data["scenario_id"] == "oauth_api_enablement"
        assert run_data["model_alias"] == "gemini-1.5-pro"

        # Validate Timers
        assert "duration_ms" in run_data or "duration_seconds" in run_data
        timing = run_data.get("timing", {})
        assert "phase_timings_ms" in timing
        phases = timing["phase_timings_ms"]
        assert "candidate_generation" in phases
        assert "sandbox_execution" in phases
        assert "actor_critic_evaluation" in phases

        # Validate Token Costs
        token_usage = run_data.get("token_usage", {})
        assert "input_tokens" in token_usage
        assert "output_tokens" in token_usage
        assert "candidate_cost_usd" in token_usage
        assert "total_estimated_cost_usd" in token_usage
        assert token_usage["candidate_cost_usd"] >= 0.0


        # Validate Run Retrieval via GET /api/runs/<run_id>
        run_id = run_data["run_id"]
        get_req = urllib.request.Request(f"{web_server}/api/runs/{run_id}")
        with urllib.request.urlopen(get_req) as get_resp:
            assert get_resp.status == 200
            retrieved = json.loads(get_resp.read().decode("utf-8"))
            assert retrieved["run_id"] == run_id
            assert retrieved["scenario_id"] == "oauth_api_enablement"


# ============================================================================
# User Story 4: Repository Insertion of Test Results
# ============================================================================

def test_repo_inserter_skill_workflow_and_translation(tmp_path: Path) -> None:
    """Verify RepoInserter formats and commits Skills, GCP Workflows, and Translated Codebases."""
    inserter = RepoInserter()

    # 1. Test Skill Artifact Formatting
    skill_run_data = {
        "run_id": "run-skill-123",
        "scenario_id": "argon_ticket_summarizer",
        "suite_slug": "agent_skill_creation",
        "model_alias": "gemini-1.5-pro",
        "candidate_output": "def execute_skill(): return {'status': 'processed'}",
        "prompt": "Synthesize a ticket summarizer ADK skill.",
        "duration_seconds": 1.25,
        "total_tokens": 420,
        "estimated_cost_usd": 0.0015,
    }
    skill_artifacts = inserter.prepare_artifacts(skill_run_data, custom_subpath="skills/ticket_summarizer")
    assert "skills/ticket_summarizer/Skill.md" in skill_artifacts
    assert "skills/ticket_summarizer/skill.py" in skill_artifacts
    assert "skills/ticket_summarizer/test_skill.py" in skill_artifacts

    # 2. Test GCP Workflow Artifact Formatting
    workflow_run_data = {
        "run_id": "run-workflow-456",
        "scenario_id": "argon_cloudrun_deploy",
        "suite_slug": "cloud_tool_writing",
        "model_alias": "claude-3-5-sonnet",
        "candidate_output": "import google.cloud\ndef deploy(): pass",
        "duration_seconds": 2.10,
        "total_tokens": 680,
        "estimated_cost_usd": 0.0082,
    }
    wf_artifacts = inserter.prepare_artifacts(workflow_run_data, custom_subpath="workflows/cloudrun_deploy")
    assert "workflows/cloudrun_deploy/cloudbuild.yaml" in wf_artifacts
    assert "workflows/cloudrun_deploy/Dockerfile" in wf_artifacts
    assert "workflows/cloudrun_deploy/workflow.py" in wf_artifacts

    # 3. Test Commit to a Target Git Repository
    target_repo = tmp_path / "user_test_repo"
    target_repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(target_repo), check=True, capture_output=True)

    result = inserter.insert_into_repository(
        repo_address=str(target_repo),
        run_data=skill_run_data,
        branch="main",
        target_dir="skills/ticket_summarizer",
    )

    assert result["success"] is True
    assert result["branch"] == "main"
    assert result["commit_hash"] != "uncommitted"
    assert len(result["inserted_files"]) == 3

    # Check files on disk in target repo
    skill_file = target_repo / "skills" / "ticket_summarizer" / "Skill.md"
    assert skill_file.is_file()
    assert "argon_ticket_summarizer" in skill_file.read_text(encoding="utf-8")

    # Check git log in target repo
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=str(target_repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "benchmaxxer: insert argon_ticket_summarizer" in log
    assert "gemini-1.5-pro" in log


def test_repo_export_via_web_api(web_server: str, tmp_path: Path) -> None:
    """Verify inserting test results into a repository via the POST /api/export/repo endpoint."""
    # First, run an evaluation to get a valid run_id
    run_payload = json.dumps({
        "scenario_id": "oauth_api_enablement",
        "model_alias": "gemini-1.5-pro",
        "mode": "mock",
        "async": False,
    }).encode("utf-8")

    run_req = urllib.request.Request(
        f"{web_server}/api/eval/run",
        data=run_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(run_req) as resp:
        run_data = json.loads(resp.read().decode("utf-8"))
        run_id = run_data["run_id"]

    # Target Git Repository
    dest_repo = tmp_path / "exported_repo"
    dest_repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(dest_repo), check=True, capture_output=True)

    # Call POST /api/export/repo
    export_payload = json.dumps({
        "repo_address": str(dest_repo),
        "run_id": run_id,
        "branch": "main",
        "target_dir": "cloud_workflows/oauth_enablement",
    }).encode("utf-8")

    export_req = urllib.request.Request(
        f"{web_server}/api/export/repo",
        data=export_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(export_req) as exp_resp:
        assert exp_resp.status == 200
        res = json.loads(exp_resp.read().decode("utf-8"))
        assert res["success"] is True
        assert len(res["inserted_files"]) > 0

    # Verify committed files in target repository
    wf_file = dest_repo / "cloud_workflows" / "oauth_enablement" / "cloudbuild.yaml"
    assert wf_file.is_file()


# ============================================================================
# Static Files & SPA Routing
# ============================================================================

def test_static_files_and_spa(web_server: str) -> None:
    """Verify that index.html, styles.css, and app.js are correctly served."""
    with urllib.request.urlopen(f"{web_server}/") as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "BenchMaxxer Evaluation Studio" in html
        assert 'id="model-cards-container"' in html
        assert 'id="generate-suite-btn"' in html
        assert 'id="run-eval-btn"' in html
        assert 'id="insert-repo-btn"' in html

    with urllib.request.urlopen(f"{web_server}/styles.css") as resp:
        assert resp.status == 200
        css = resp.read().decode("utf-8")
        assert ".studio-section" in css

    with urllib.request.urlopen(f"{web_server}/app.js") as resp:
        assert resp.status == 200
        js = resp.read().decode("utf-8")
        assert "generateArgonSuite" in js
        assert "exportToRepository" in js
