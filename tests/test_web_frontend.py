"""Automated Regression Suite for devbench Web Frontend, Argon Suite Creator, GCP MIQ Config, Custom Suites, Telemetry, and Repo Inserter."""

from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from devbench.ui.web.argon_agent import ArgonSuiteCreator
from devbench.ui.web.repo_inserter import RepoInserter
from devbench.ui.web.server import (
    devbenchRequestHandler,
    load_frontend_config,
    start_web_server,
)


@pytest.fixture(scope="module")
def web_server():
    """Start an ephemeral test instance of the devbench ThreadingHTTPServer on a random free port."""
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
# User Story 1: Frontier Model Garden Selection (4 Defaults + Enabled Dropdown)
# ============================================================================

def test_frontend_config_and_model_garden_models(web_server: str) -> None:
    """Verify that the 5 default Frontier Models (Gemini 3.1 Pro, Gemini 3.8 Flash, Claude Opus 5.1, Claude Sonnet 5.5, Mistral Large 3) and GCP dropdown models are exposed."""
    cfg = load_frontend_config()
    assert "model_garden" in cfg
    models = cfg["model_garden"]
    assert len(models) >= 8

    model_ids = {m["id"] for m in models}
    # Verify frontier models including default Gemini 3.5 Flash and Claude 4.6 Sonnet
    assert "gemini-3.5-flash" in model_ids
    assert "gemini-3.1-pro" in model_ids
    assert "gemini-3.8-flash" in model_ids
    assert "claude-opus-5.1" in model_ids
    assert "claude-sonnet-5.5" in model_ids
    assert "claude-sonnet-4-6" in model_ids
    assert "mistral-large-3" in model_ids
    # Verify additional GCP models (Gemini 3+, Claude 4.5+, cheap serverless partner models)
    assert "gemini-3-pro" in model_ids
    assert "gemini-3-flash" in model_ids
    assert "claude-sonnet-4-5" in model_ids
    assert "grok-2-mini" in model_ids
    assert "llama-3.1-8b" in model_ids
    assert "muse" in model_ids
    assert "mistral-small" in model_ids
    assert "eleven-labs" in model_ids

    # Test REST API endpoint /api/models
    req = urllib.request.Request(f"{web_server}/api/models")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "models" in data
        assert "default_models" in data
        assert "dropdown_models" in data

        default_ids = [m["id"] for m in data["default_models"]]
        assert "gemini-3.5-flash" in default_ids
        assert "gemini-3.1-pro" in default_ids
        assert "gemini-3.8-flash" in default_ids
        assert "claude-opus-5.1" in default_ids
        assert "claude-sonnet-5.5" in default_ids
        assert "claude-sonnet-4-6" in default_ids
        assert "mistral-large-3" in default_ids
        assert len(data["dropdown_models"]) >= 3

        # Validate pricing and brand attributes exist
        for m in data["models"]:
            assert "cost_per_1k_input_usd" in m
            assert "cost_per_1k_output_usd" in m
            assert "provider" in m
            assert "description" in m
            assert "brand" in m


def test_gcp_project_location_and_miq_enablement(web_server: str) -> None:
    """Verify that a web user can configure the GCP project, location, and enable MIQ models that populate the dropdown."""
    # 1. Update GCP project and location and enable deepseek-r2 + gemini-3.5-pro
    payload = json.dumps({
        "project_id": "vertex-frontier-eval-prod",
        "location": "europe-west4",
        "enabled_model_ids": [
            "gemini-3.1-pro",
            "gemini-3.8-flash",
            "claude-opus-5.1",
            "claude-sonnet-5.5",
            "mistral-large-3",
            "gemini-3.5-pro",
            "deepseek-r2",
            # Later tests run gemini-4-argon; only models enabled in the linked project may be the MIQ.
            "gemini-4-argon",
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{web_server}/api/gcp/config",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert data["project_id"] == "vertex-frontier-eval-prod"
        assert data["location"] == "europe-west4"
        dropdown_ids = {m["id"] for m in data["dropdown_models"]}
        assert "deepseek-r2" in dropdown_ids
        assert "gemini-3.5-pro" in dropdown_ids

    # 2. Toggle an individual MIQ model via /api/gcp/models/toggle
    toggle_payload = json.dumps({
        "model_id": "qwen-3-72b",
        "enabled": True,
    }).encode("utf-8")
    toggle_req = urllib.request.Request(
        f"{web_server}/api/gcp/models/toggle",
        data=toggle_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(toggle_req) as resp:
        assert resp.status == 200
        toggle_data = json.loads(resp.read().decode("utf-8"))
        dropdown_ids_after = {m["id"] for m in toggle_data["dropdown_models"]}
        assert "qwen-3-72b" in dropdown_ids_after


# ============================================================================
# User Story 2: Argon-Backed Agent & Custom Multi-Test Suite Builder
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


def test_custom_composite_test_suite_creation_and_execution(web_server: str) -> None:
    """Verify creating a custom test suite with 1+ standard benchmark scenarios AND 1+ custom use cases, then executing it."""
    suite_payload = json.dumps({
        "suite_name": "Hybrid Enterprise Cloud & Custom Skill Suite",
        "standard_scenarios": ["oauth_api_enablement", "easy_deployment"],
        "custom_use_cases": [
            {
                "title": "Custom Firestore Schema Validator Skill",
                "prompt": "Create an ADK agent skill that validates Firestore document schemas and logs errors to BigQuery.",
            }
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{web_server}/api/suites/custom",
        data=suite_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res_data = json.loads(resp.read().decode("utf-8"))
        assert res_data["success"] is True
        suite = res_data["suite"]
        assert suite["is_custom"] is True
        assert len(suite["standard_scenarios"]) == 2
        assert len(suite["custom_scenarios"]) == 1
        assert len(suite["scenarios"]) == 3

        scenario_ids = suite["scenarios"]

    # Execute the composite suite against Gemini 4 Argon
    eval_payload = json.dumps({
        "scenario_ids": scenario_ids,
        "suite_name": "Hybrid Enterprise Cloud & Custom Skill Suite",
        "model_alias": "gemini-4-argon",
        "mode": "mock",
        "async": False,
    }).encode("utf-8")

    eval_req = urllib.request.Request(
        f"{web_server}/api/eval/run",
        data=eval_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(eval_req) as eval_resp:
        assert eval_resp.status == 200
        run_data = json.loads(eval_resp.read().decode("utf-8"))
        assert run_data["status"] == "COMPLETED"
        assert run_data["model_alias"] == "gemini-4-argon"
        assert len(run_data["test_results"]) == 3
        assert any(tr["is_custom"] for tr in run_data["test_results"])
        assert any(not tr["is_custom"] for tr in run_data["test_results"])


# ============================================================================
# User Story 3: Complete Time and Token Cost Telemetry
# ============================================================================

def test_eval_run_time_and_token_cost_telemetry(web_server: str) -> None:
    """Verify that running an evaluation accurately captures hierarchical timers and token costs."""
    # Execute synchronous evaluation for deterministic testing
    payload = json.dumps({
        "scenario_id": "oauth_api_enablement",
        "model_alias": "gemini-4-argon",
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
        assert run_data["model_alias"] == "gemini-4-argon"

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
        "model_alias": "gemini-4-argon",
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
        "model_alias": "sonnet-5.5",
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
    assert "devbench: insert argon_ticket_summarizer" in log
    assert "gemini-4-argon" in log


def test_repo_export_via_web_api(web_server: str, tmp_path: Path) -> None:
    """Verify inserting test results into a repository via the POST /api/export/repo endpoint."""
    # First, run an evaluation to get a valid run_id
    run_payload = json.dumps({
        "scenario_id": "oauth_api_enablement",
        "model_alias": "gemini-4-argon",
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
    """Verify that index.html, styles.css, and app.js are correctly served with all required components."""
    with urllib.request.urlopen(f"{web_server}/") as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "DevBench Evaluation Studio" in html
        assert "Select Frontier Models" in html
        assert 'id="model-cards-container"' in html
        assert 'id="enabled-models-dropdown"' in html
        assert 'id="section-select-harness"' in html
        assert 'id="harness-cards-container"' in html
        assert 'id="additional-harnesses-dropdown"' in html
        assert 'id="harbor-sandbox-toggle"' in html
        assert 'id="internal-google-permissions-bar"' in html
        assert 'id="gcp-config-panel"' in html
        assert 'id="custom-suite-builder"' in html
        assert 'id="harbor-logo-badge"' in html
        assert 'id="jev-logo-badge"' in html
        assert 'id="generate-suite-btn"' in html
        assert 'id="run-eval-btn"' in html
        assert 'id="insert-repo-btn"' in html

    with urllib.request.urlopen(f"{web_server}/styles.css") as resp:
        assert resp.status == 200
        css = resp.read().decode("utf-8")
        assert ".studio-section" in css
        assert ".harness-cards-grid" in css
        assert "--google-blue" in css

    with urllib.request.urlopen(f"{web_server}/app.js") as resp:
        assert resp.status == 200
        js = resp.read().decode("utf-8")
        assert "generateArgonSuite" in js
        assert "exportToRepository" in js
        assert "getBrandLogoSvg" in js
        assert "fetchHarnesses" in js
        assert "selectHarness" in js
        assert "saveGcpConfiguration" in js
        assert "saveCustomTestSuite" in js


def test_agent_harness_api_and_harbor_sandbox_eval(web_server: str) -> None:
    """Verify /api/harnesses, /api/harbor/status, and /api/eval/run with agent harnesses (agy, jetski, claude-code, opencode, codex)."""
    with urllib.request.urlopen(f"{web_server}/api/harnesses") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["default_harness"] == "agy"
        supported = data["supported_harnesses"]
        for h in ["agy", "jetski", "claude-code", "opencode", "codex"]:
            assert h in supported
        perms = data["internal_google_default_permissions"]
        assert perms["enabled"] is True
        assert perms["adc_credentials_path"] == "/var/run/secrets/google/adc.json"

    with urllib.request.urlopen(f"{web_server}/api/harbor/status") as resp:
        assert resp.status == 200
        st = json.loads(resp.read().decode("utf-8"))
        for h in ["agy", "jetski", "claude-code", "opencode", "codex"]:
            assert h in st["supported_harnesses"]
        assert st["internal_google_default_permissions"]["enabled"] is True

    # Run evaluation via POST /api/eval/run with Jetski harness inside Harbor sandbox
    payload = json.dumps({
        "scenario_id": "oauth_api_enablement",
        "model_alias": "gemini-3.1-pro",
        "agent_type": "jetski",
        "harbor": True,
        "environment_type": "podman",
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
        assert run_data["agent_harness"] == "jetski"
        assert run_data["internal_google_permissions"]["enabled"] is True
        assert run_data["harbor"]["agent_harness"] == "jetski"


def test_assessment_mode_sidebar_and_model_pagination(web_server: str) -> None:
    """Verify assessment mode sidebar (GCP, curl, API), auth displays, and model pagination controls."""
    # 1. Verify index.html static markup contains sidebar and pagination elements
    with urllib.request.urlopen(f"{web_server}/") as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert 'id="assessment-mode-sidebar"' in html
        assert 'id="mode-card-gcp"' in html
        assert 'id="mode-card-curl"' in html
        assert 'id="mode-card-api"' in html
        assert 'id="auth-panel-gcp"' in html
        assert 'id="auth-panel-curl"' in html
        assert 'id="auth-panel-api"' in html
        assert 'id="toggle-miq-collapse-btn"' in html
        assert 'id="miq-collapsible-body"' in html
        assert 'id="miq-pagination-bar-top"' in html
        assert 'id="miq-page-size-select"' in html
        assert 'id="miq-pagination-bar-bottom"' in html
        assert 'id="miq-collapsed-summary"' in html

    # 2. Verify styles.css contains sidebar, pagination, and enlarged box classes
    with urllib.request.urlopen(f"{web_server}/styles.css") as resp:
        assert resp.status == 200
        css = resp.read().decode("utf-8")
        assert ".assessment-mode-sidebar" in css
        assert ".mode-select-card" in css
        assert ".miq-collapsible-body" in css
        assert ".miq-pagination-bar" in css
        assert ".page-pill-btn" in css
        assert ".miq-toggle-item" in css

    # 3. Verify app.js contains interaction controllers
    with urllib.request.urlopen(f"{web_server}/app.js") as resp:
        assert resp.status == 200
        js = resp.read().decode("utf-8")
        assert "selectAssessmentMode" in js
        assert "toggleMiqSectionCollapse" in js
        assert "changeMiqPage" in js
        assert "changeMiqPageSize" in js
        assert "saveDirectApiKeys" in js

    # 4. Verify /api/auth/status returns current mode and key status
    with urllib.request.urlopen(f"{web_server}/api/auth/status") as resp:
        assert resp.status == 200
        auth_status = json.loads(resp.read().decode("utf-8"))
        assert "mode" in auth_status
        assert "keys_configured" in auth_status
        assert "adc_authenticated" in auth_status

    # 5. Verify /api/auth/mode updates the mode (GCP, curl only, API)
    for mode in ["gcp", "curl", "api"]:
        mode_req = urllib.request.Request(
            f"{web_server}/api/auth/mode",
            data=json.dumps({"mode": mode}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(mode_req) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["success"] is True
            assert res["mode"] == mode

    # 6. Verify /api/auth/keys saves provider keys
    keys_req = urllib.request.Request(
        f"{web_server}/api/auth/keys",
        data=json.dumps({
            "gemini_api_key": "AIzaSy_fake_test_key",
            "anthropic_api_key": "sk-ant_fake_test_key",
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(keys_req) as resp:
        assert resp.status == 200
        keys_res = json.loads(resp.read().decode("utf-8"))
        assert keys_res["success"] is True
        assert keys_res["keys_configured"]["gemini"] is True
        assert keys_res["keys_configured"]["anthropic"] is True


def test_error_message_handles_list_payloads_and_edge_cases():
    """Verify that _error_message in model_garden handles list error payloads without raising AttributeError."""
    from devbench.gcp.model_garden import _error_message, probe_model_access

    # 1. OpenAPI error format returned as a list of error objects
    list_payload = [{"error": {"code": 404, "message": "Publisher model not found", "status": "NOT_FOUND"}}]
    msg = _error_message(list_payload)
    assert "Publisher model not found" in msg

    # 2. Empty list, strings, and scalar payloads
    assert _error_message([]) == ""
    assert _error_message("plain string error") == "plain string error"
    assert _error_message(None) == "None"

    # 3. probe_model_access with mock http_fn returning list payload
    def mock_http_list(method, url, body, headers):
        return 404, [{"error": {"code": 404, "message": "Not found in region", "status": "NOT_FOUND"}}]

    res = probe_model_access(
        project_id="test-proj",
        location="global",
        publisher="xai",
        model_id="grok-4.6",
        token="fake-token",
        http=mock_http_list,
    )
    assert res["enabled"] is False
    assert res["enablement"] == "not_available"
    assert "Not available in global" in res["detail"]



