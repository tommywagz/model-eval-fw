"""End-to-end coverage of the Evaluation Studio workflow requirements.

1. Link a user-chosen GCP project (verified + Model Garden discovery).
2. Choose any model enabled in the LINKED project as the Model in Question (MIQ).
3. Choose the harness (Antigravity default; Jetski, Claude Code, OpenCode, Codex, custom CLIs)
   as long as it is installed locally.
4. Run all / some / one / none of the standard tests plus optional custom tests.
5. A per-test report (metrics, token cost, time) is produced.

All Google Cloud calls are faked; no network or spend.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pytest

from devbench.gcp import model_garden
from devbench.harbor import (
    detect_harness,
    list_detected_harnesses,
    register_custom_agent_harness,
    run_harness_headless,
)
from devbench.harbor.harnesses import parse_harness_output
from devbench.models.factory import get_model_client, register_runtime_models
from devbench.scenarios.runner import SCENARIO_CATALOG
from devbench.ui.web import server as web_server_module

PROJECT = "my-linked-eval-proj"
LOCATION = "us-central1"


def _fake_http(method: str, url: str, body: Optional[Dict[str, Any]], headers: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    """Minimal fake of the Google Cloud REST surface used by model_garden."""
    assert headers.get("Authorization", "").startswith("Bearer ")
    if "cloudresourcemanager" in url:
        return 200, {"projectId": PROJECT, "projectNumber": "123456789", "name": "Linked Eval", "lifecycleState": "ACTIVE"}
    if "serviceusage" in url:
        return 200, {"state": "ENABLED"}
    if "/publishers/google/models?" in url:
        return 200, {
            "publisherModels": [
                {"name": "publishers/google/models/gemini-2.5-pro", "launchStage": "GA"},
                {"name": "publishers/google/models/gemini-2.5-flash", "launchStage": "GA"},
                {"name": "publishers/google/models/text-embedding-005", "launchStage": "GA"},
                {"name": "publishers/google/models/imagen-4.0-generate-001", "launchStage": "GA"},
            ]
        }
    if "/publishers/anthropic/models?" in url:
        return 200, {
            "publisherModels": [
                {"name": "publishers/anthropic/models/claude-sonnet-4-5", "launchStage": "GA"},
                {"name": "publishers/anthropic/models/claude-opus-4-1", "launchStage": "GA"},
            ]
        }
    if "/publishers/" in url and "/models?" in url:
        return 200, {"publisherModels": []}
    if url.endswith("/endpoints?pageSize=100"):
        return 200, {
            "endpoints": [
                {
                    "name": f"projects/{PROJECT}/locations/{LOCATION}/endpoints/987654321",
                    "displayName": "llama-ep",
                    "deployedModels": [{"displayName": "llama-3.3-70b-instruct", "model": "projects/x/models/1"}],
                },
                {"name": f"projects/{PROJECT}/locations/{LOCATION}/endpoints/111", "displayName": "empty", "deployedModels": []},
            ]
        }
    if url.endswith(":countTokens"):
        return 200, {"totalTokens": 1}
    if "count-tokens:rawPredict" in url:
        # Sonnet is enabled for this project, Opus is not.
        if body and body.get("model") == "claude-sonnet-4-5":
            return 200, {"input_tokens": 1}
        return 403, {"error": {"message": "Publisher model not enabled. Please enable it in Model Garden (accept terms)."}}
    return 404, {"error": {"message": f"unexpected url {url}"}}


# ----------------------------------------------------------------------------
# Requirement 1 & 2: project verification + Model Garden discovery
# ----------------------------------------------------------------------------


def test_verify_project_and_discover_models_enabled_in_linked_project() -> None:
    ver = model_garden.verify_gcp_project(PROJECT, token="tok", http=_fake_http)
    assert ver["accessible"] is True
    assert ver["vertex_api_enabled"] is True
    assert ver["project_number"] == "123456789"

    disc = model_garden.discover_model_garden(
        PROJECT, LOCATION, token="tok", verify_access=True, verify_partner_access=True, http=_fake_http
    )
    by_id = {m["id"]: m for m in disc["models"]}

    # Non-generative models are filtered out.
    assert "text-embedding-005" not in by_id
    assert "imagen-4.0-generate-001" not in by_id

    # First-party Gemini usable; partner enablement verified per project; endpoint usable.
    assert by_id["gemini-2.5-pro"]["enabled"] is True
    assert by_id["gemini-2.5-pro"]["backend_provider"] == "vertex_genai"
    assert by_id["claude-sonnet-4-5"]["enabled"] is True
    assert by_id["claude-sonnet-4-5"]["backend_provider"] == "vertex_anthropic"
    assert by_id["claude-opus-4-1"]["enabled"] is False
    assert by_id["claude-opus-4-1"]["enablement"] == "not_enabled"
    endpoint = next(m for m in disc["models"] if m["source"] == "vertex_endpoint")
    assert endpoint["enabled"] is True
    assert endpoint["endpoint_resource_name"].endswith("/endpoints/987654321")

    # Every model is bound to the linked project and has pricing.
    for m in disc["models"]:
        assert m["project_id"] == PROJECT
        assert m["cost_per_1k_input_usd"] > 0
    assert by_id["gemini-2.5-pro"]["pricing_source"] == "list_price"

    # Only enabled models are featured.
    assert all(m["enabled"] for m in disc["models"] if m["is_default"])
    assert disc["counts"]["enabled"] == 4


def test_discovered_models_resolve_to_linked_project_clients() -> None:
    disc = model_garden.discover_model_garden(PROJECT, LOCATION, token="tok", verify_access=False, http=_fake_http)
    try:
        register_runtime_models({m["id"]: model_garden.registry_entry_for(m) for m in disc["models"]})
        client = get_model_client("gemini-2.5-pro", mode="mock", no_cache=True)
        assert client.project_id == PROJECT
        assert client.model_name == "gemini-2.5-pro"
        claude = get_model_client("claude-sonnet-4-5", mode="mock", no_cache=True)
        assert claude.provider == "vertex_anthropic"
        assert claude.project_id == PROJECT
    finally:
        register_runtime_models({}, replace=True)


# ----------------------------------------------------------------------------
# Requirement 3: harness detection + headless execution
# ----------------------------------------------------------------------------


def test_harness_catalog_detection_and_custom_registration(tmp_path: Path) -> None:
    harnesses = {h["id"]: h for h in list_detected_harnesses()}
    for hid in ("agy", "jetski", "claude-code", "opencode", "codex", "gemini-cli", "devbench", "oracle"):
        assert hid in harnesses
        assert "installed" in harnesses[hid]
    assert harnesses["agy"]["is_default"] is True
    assert harnesses["agy"]["harbor_agent_name"] == "antigravity-cli"
    assert harnesses["devbench"]["installed"] is True  # built-in

    missing = register_custom_agent_harness(name="Ghost Agent", cli_binary="definitely-not-installed-xyz")
    assert detect_harness(missing)["installed"] is False


def test_run_custom_harness_headless_reports_tokens(tmp_path: Path) -> None:
    script = tmp_path / "fake-agent"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "print(json.dumps({'result': 'def solve():\\n    return 42  # ' + os.environ['GOOGLE_CLOUD_PROJECT'],"
        " 'usage': {'input_tokens': 321, 'output_tokens': 123}, 'total_cost_usd': 0.0042, 'argv': sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    spec = register_custom_agent_harness(
        name="Fake Agent",
        cli_binary=str(script),
        headless_command=["{binary}", "--print", "{prompt}", "--model", "{model}"],
    )
    assert detect_harness(spec)["installed"] is True

    out = run_harness_headless(
        harness_id=spec["id"],
        prompt="Write solve()",
        model={"id": "gemini-2.5-pro", "model_name": "gemini-2.5-pro", "brand": "gemini", "publisher": "google"},
        project_id=PROJECT,
        location=LOCATION,
        workdir=tmp_path / "work",
    )
    assert PROJECT in out["candidate_output"]
    assert out["input_tokens"] == 321
    assert out["output_tokens"] == 123
    assert out["reported_cost_usd"] == pytest.approx(0.0042)
    assert out["token_source"] == "harness_reported"
    assert "--model" in out["argv"] and "gemini-2.5-pro" in out["argv"]


def test_parse_harness_output_variants() -> None:
    gemini_like = json.dumps({"response": "ok", "stats": {"models": {"g": {"tokens": {"prompt": 10, "candidates": 5}}}}})
    parsed = parse_harness_output(gemini_like)
    assert parsed["candidate_output"] == "ok"
    assert parsed["input_tokens"] == 10 and parsed["output_tokens"] == 5
    plain = parse_harness_output("just text output")
    assert plain["candidate_output"] == "just text output"
    assert plain["token_source"] == "estimated"


# ----------------------------------------------------------------------------
# Full web workflow (link -> pick MIQ -> pick harness -> pick tests -> report)
# ----------------------------------------------------------------------------


@pytest.fixture()
def linked_server(monkeypatch: pytest.MonkeyPatch):
    import socket

    monkeypatch.setattr(model_garden, "get_access_token", lambda force_refresh=False: ("tok", "test-adc"))
    real_verify = model_garden.verify_gcp_project
    real_discover = model_garden.discover_model_garden
    monkeypatch.setattr(
        model_garden, "verify_gcp_project", lambda project_id, token=None, http=None: real_verify(project_id, token=token, http=_fake_http)
    )
    monkeypatch.setattr(
        model_garden,
        "discover_model_garden",
        lambda **kw: real_discover(**{**kw, "http": _fake_http}),
    )

    saved_state = web_server_module.GCP_RUNTIME_STATE
    web_server_module.GCP_RUNTIME_STATE = None
    from devbench.scenarios.runner import SUITE_CATALOG
    import copy as _copy

    saved_scenarios = dict(SCENARIO_CATALOG)
    saved_suites = _copy.deepcopy(SUITE_CATALOG)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    httpd = web_server_module.start_web_server(host="127.0.0.1", port=port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()
    httpd.server_close()
    web_server_module.GCP_RUNTIME_STATE = saved_state
    register_runtime_models({}, replace=True)
    (Path(os.environ["DEVBENCH_STATE_DIR"]) / "gcp_link.json").unlink(missing_ok=True)
    # Undo custom (Argon) test registrations so other test modules see the stock catalogs.
    SCENARIO_CATALOG.clear()
    SCENARIO_CATALOG.update(saved_scenarios)
    SUITE_CATALOG.clear()
    SUITE_CATALOG.update(saved_suites)


def _post(base: str, path: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    req = urllib.request.Request(
        f"{base}{path}", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_full_studio_workflow_link_select_run_and_report(linked_server: str) -> None:
    base = linked_server

    # 1. Link the user's project -> discovery replaces the offline catalog.
    status, data = _post(base, "/api/gcp/link", {"project_id": PROJECT, "location": LOCATION, "verify_partner_access": True})
    assert status == 200, data
    assert data["success"] is True
    assert data["project_id"] == PROJECT
    assert data["link_status"]["source"] == "discovered"
    ids = {m["id"] for m in data["models"]}
    assert "gemini-2.5-pro" in ids and "gemini-3.1-pro" not in ids  # demo catalog gone
    enabled_ids = {m["id"] for m in data["enabled_models"]}
    assert "claude-opus-4-1" not in enabled_ids

    # Persisted for the next server start (isolated state dir from conftest).
    persisted = Path(os.environ["DEVBENCH_STATE_DIR"]) / "gcp_link.json"
    assert json.loads(persisted.read_text())["project_id"] == PROJECT

    # 2. A model that is not enabled in the linked project cannot be the MIQ.
    status, err = _post(base, "/api/eval/run", {"scenario_ids": ["oauth_api_enablement"], "model_alias": "claude-opus-4-1", "async": False})
    assert status == 400 and "not enabled" in err["error"]

    # 4. "None" of the tests -> rejected; custom-only and mixed suites are accepted.
    status, err = _post(base, "/api/eval/run", {"scenario_ids": [], "model_alias": "gemini-2.5-pro", "async": False})
    assert status == 400 and "empty" in err["error"]

    status, gen = _post(base, "/api/scenarios/generate", {"prompt": "Create an agent skill that validates JSON records and alerts Pub/Sub", "title": "Workflow Custom Test"})
    assert status == 200
    custom_id = gen["suite_spec"]["scenario_id"]

    # 3 + 5. Run 2 standard tests + 1 custom test with the Antigravity default harness in Harbor.
    suite = ["oauth_api_enablement", "storage_operations", custom_id]
    status, run = _post(
        base,
        "/api/eval/run",
        {
            "scenario_ids": suite,
            "model_alias": "gemini-2.5-pro",
            "agent_type": "agy",
            "harbor": True,
            "environment_type": "podman",
            "mode": "mock",
            "async": False,
        },
    )
    assert status == 200, run
    assert run["status"] == "COMPLETED"
    assert run["model_alias"] == "gemini-2.5-pro"
    assert run["agent_harness"] == "agy"
    assert run["gcp_project_id"] == PROJECT

    rows = run["test_results"]
    assert [r["scenario_id"] for r in rows] == suite
    assert [r["is_custom"] for r in rows] == [False, False, True]
    for r in rows:
        assert r["status"] in ("PASSED", "FAILED")
        assert r["wall_seconds"] > 0
        assert r["input_tokens"] > 0 and r["output_tokens"] > 0
        assert r["total_tokens"] >= r["input_tokens"] + r["output_tokens"]
        assert r["estimated_cost_usd"] >= r["candidate_cost_usd"] > 0
        assert r["harbor_tasks_total"] is not None

    report = run["report"]
    assert report["total_tests"] == 3
    assert report["standard_tests"] == 2 and report["custom_tests"] == 1
    assert report["total_cost_usd"] == pytest.approx(sum(r["estimated_cost_usd"] for r in rows), abs=1e-6)
    assert report["total_tokens"] == sum(r["total_tokens"] for r in rows)
    assert report["harness"] == "agy"
    assert report["gcp_project_id"] == PROJECT

    # One standard test only (no Harbor) also works.
    status, single = _post(base, "/api/eval/run", {"scenario_ids": ["storage_operations"], "model_alias": "claude-sonnet-4-5", "agent_type": "claude-code", "async": False})
    assert status == 200 and len(single["test_results"]) == 1
    assert single["report"]["model_alias"] == "claude-sonnet-4-5"


def test_live_runs_require_installed_harness_and_compatible_model(linked_server: str) -> None:
    base = linked_server
    status, _ = _post(base, "/api/gcp/link", {"project_id": PROJECT, "location": LOCATION})
    assert status == 200

    register_custom_agent_harness(name="Missing Agent", cli_binary="definitely-not-installed-xyz")
    status, err = _post(
        base,
        "/api/eval/run",
        {"scenario_ids": ["oauth_api_enablement"], "model_alias": "gemini-2.5-pro", "agent_type": "missing-agent", "mode": "live", "async": False},
    )
    assert status == 400 and "not installed" in err["error"]

    # Claude Code can only host Anthropic models.
    status, err = _post(
        base,
        "/api/eval/run",
        {"scenario_ids": ["oauth_api_enablement"], "model_alias": "gemini-2.5-pro", "agent_type": "claude-code", "mode": "live", "async": False},
    )
    assert status == 400
    assert ("only host" in err["error"]) or ("not installed" in err["error"])


def test_live_runs_require_linked_project() -> None:
    from devbench.ui.web.eval_runner import EvalRequestError, resolve_eval_request

    snapshot = {
        "project_id": "devbench-eval-sandbox",
        "location": LOCATION,
        "link_status": {"source": "offline_catalog"},
        "models": [{"id": "gemini-3.1-pro", "name": "Gemini 3.1 Pro", "brand": "gemini", "enabled": True}],
    }
    with pytest.raises(EvalRequestError, match="linked GCP project"):
        resolve_eval_request({"scenario_ids": ["oauth_api_enablement"], "model_alias": "gemini-3.1-pro", "mode": "live", "agent_type": "devbench"}, snapshot)
    with pytest.raises(EvalRequestError, match="Unknown test"):
        resolve_eval_request({"scenario_ids": ["nope_not_a_test"], "model_alias": "gemini-3.1-pro"}, snapshot)
