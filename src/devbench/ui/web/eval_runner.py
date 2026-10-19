"""Evaluation run orchestration for the devbench Evaluation Studio web UI.

Takes the user's selections (linked GCP project, Model-in-Question, agent harness, and the
chosen standard + custom tests), validates them, runs every test (optionally inside Harbor
sandboxes), and produces a per-test report with pass/fail, scores, wall time, token usage and
cost.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from devbench.scenarios.runner import (
    SCENARIO_CATALOG,
    execute_scenario_run,
    get_scenario_spec,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


class EvalRequestError(ValueError):
    """Raised for invalid evaluation requests (mapped to HTTP 400)."""

    def __init__(
        self,
        message: str,
        error_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.details = details or {}


def _is_custom(scenario_id: str) -> bool:
    return scenario_id.startswith("argon_") or bool(SCENARIO_CATALOG.get(scenario_id, {}).get("is_custom"))


def resolve_eval_request(payload: Dict[str, Any], gcp_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize an ``/api/eval/run`` payload. Raises :class:`EvalRequestError`."""
    from devbench.harbor import (
        check_harness_model_compat,
        detect_harness,
        get_agent_harness_spec,
        get_internal_google_default_permissions,
        normalize_agent_harness,
    )
    from devbench.models.factory import load_model_registry

    warnings: List[str] = []

    # ---- Tests (all / some / one standard tests and/or custom tests) ----
    scenario_ids_raw = payload.get("scenario_ids")
    if isinstance(scenario_ids_raw, list):
        scenario_list = []
        for s in scenario_ids_raw:
            sid = str(s).strip()
            if sid == "oauth":
                sid = "oauth_api_enablement"
            if sid and sid not in scenario_list:
                scenario_list.append(sid)
        if not scenario_list:
            raise EvalRequestError(
                "Your test suite is empty. Add at least one standard test or one custom test scenario."
            )
    else:
        raw_s = str(payload.get("scenario_id") or "storage_operations").strip()
        if raw_s == "oauth":
            raw_s = "oauth_api_enablement"
        scenario_list = [raw_s]
    unknown = [s for s in scenario_list if s not in SCENARIO_CATALOG]
    if unknown:
        raise EvalRequestError(f"Unknown test scenario(s): {', '.join(unknown)}")

    mode = str(payload.get("mode", "mock")).lower()
    if mode not in ("mock", "live"):
        raise EvalRequestError("Field 'mode' must be 'mock' or 'live'.")

    # ---- Model in Question (must be enabled in the linked project) ----
    model_alias = str(payload.get("model_alias") or "gemini-3.5-flash")
    models_by_id = {m["id"]: m for m in gcp_snapshot.get("models", [])}
    model_entry = models_by_id.get(model_alias)
    link_status = gcp_snapshot.get("link_status") or {}
    auth_mode = str(payload.get("auth_mode", "gcp")).lower()
    if model_entry is None:
        if model_alias not in load_model_registry():
            raise EvalRequestError(
                f"Model '{model_alias}' is not available in linked project {gcp_snapshot.get('project_id')}."
            )
        model_entry = {"id": model_alias, "name": model_alias, "brand": "vertex", "enabled": True}
    elif not model_entry.get("enabled"):
        if auth_mode in ("curl", "api", "api_key"):
            warnings.append(
                f"Model '{model_entry.get('name', model_alias)}' is not enabled in linked GCP project {gcp_snapshot.get('project_id')}; "
                f"proceeding with {auth_mode.upper()} auth."
            )
        else:
            proj_id = gcp_snapshot.get("project_id", "")
            loc = model_entry.get("location") or gcp_snapshot.get("location", "us-central1")
            raise EvalRequestError(
                f"Model '{model_entry.get('name', model_alias)}' is not enabled in linked project "
                f"{proj_id}: {model_entry.get('status_detail') or 'enable it in Vertex AI Model Garden'}.",
                error_type="MODEL_ACCESS_DENIED",
                details={
                    "model_id": model_alias,
                    "model_name": model_entry.get("name", model_alias),
                    "project_id": proj_id,
                    "location": loc,
                    "remediation": (
                        f"1. Run `gcloud auth application-default login` on your local terminal.\n"
                        f"2. Open Vertex AI Model Garden to enable '{model_alias}' in project '{proj_id}':\n"
                        f"   https://console.cloud.google.com/vertex-ai/model-garden?project={proj_id}\n"
                        f"3. Ensure your GCP identity has the 'roles/aiplatform.user' role on project '{proj_id}'."
                    ),
                    "model_garden_url": f"https://console.cloud.google.com/vertex-ai/model-garden?project={proj_id}",
                },
            )
    if mode == "live":
        if link_status.get("source") != "discovered" or not model_entry.get("discovered"):
            raise EvalRequestError(
                "Live runs require a linked GCP project. Click 'Link & Discover Models', then pick a model "
                "discovered in that project."
            )

    # ---- Harness ----
    agent_type = normalize_agent_harness(payload.get("agent_type", payload.get("harness", "agy")))
    harness_spec = detect_harness(get_agent_harness_spec(agent_type))
    host_harness = bool(harness_spec.get("headless_command"))
    if host_harness and not harness_spec.get("installed"):
        msg = f"Harness '{harness_spec['name']}' is not installed on this machine ({harness_spec['install_status']})."
        if mode == "live":
            raise EvalRequestError(msg + " Install it or pick another harness.")
        warnings.append(msg + " Mock mode simulates it.")
    compat = check_harness_model_compat(agent_type, model_entry)
    if compat:
        if mode == "live":
            raise EvalRequestError(compat)
        warnings.append(compat)

    use_harbor = bool(payload.get("harbor", False))
    environment_type = str(payload.get("environment_type", payload.get("env", "podman")))
    auth_mode = str(payload.get("auth_mode") or "auto").lower().strip()

    raw_critic = payload.get("critic_model") or payload.get("critic")
    no_critics = bool(payload.get("no_critics", False) or raw_critic in ("none", "no_critics", "disabled"))
    critic_model = None if (no_critics or raw_critic in ("auto", "default", "none", None, "")) else str(raw_critic).strip()

    return {
        "scenario_list": scenario_list,
        "scenario_id": scenario_list[0],
        "model_alias": model_alias,
        "model_entry": model_entry,
        "critic_model": critic_model,
        "no_critics": no_critics,
        "mode": mode,
        "auth_mode": auth_mode,
        "agent_type": agent_type,
        "harness_spec": harness_spec,
        "run_harness_on_host": bool(mode == "live" and host_harness and harness_spec.get("installed")),
        "use_harbor": use_harbor,
        "environment_type": environment_type,
        "suite_name": payload.get("suite_name"),
        "candidate_override": payload.get("candidate_override"),
        "warnings": warnings,
        "gcp_project_id": gcp_snapshot.get("project_id"),
        "gcp_location": gcp_snapshot.get("location"),
        "actor_project_id": payload.get("actor_project_id") or gcp_snapshot.get("project_id"),
        "actor_location": payload.get("actor_location") or gcp_snapshot.get("location"),
        "critic_project_id": payload.get("critic_project_id") or os.environ.get("CRITIC_PROJECT_ID"),
        "critic_location": payload.get("critic_location") or os.environ.get("CRITIC_LOCATION"),
        "internal_google_permissions": get_internal_google_default_permissions(
            project_id=gcp_snapshot.get("project_id"),
            location=gcp_snapshot.get("location"),
            agent_type=agent_type,
        ),
    }


def build_test_metrics(
    scenario_id: str,
    res: Optional[Dict[str, Any]],
    wall_seconds: float,
    agent_type: str,
    harness_run: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Flatten one test's result into the report row shown at the bottom of the UI."""
    spec = SCENARIO_CATALOG.get(scenario_id, {})
    base = {
        "scenario_id": scenario_id,
        "scenario_name": spec.get("scenario_name") or scenario_id,
        "suite_slug": spec.get("suite_slug", ""),
        "difficulty": spec.get("difficulty", "Medium"),
        "is_custom": _is_custom(scenario_id),
        "agent_harness": agent_type,
        "wall_seconds": round(wall_seconds, 3),
    }
    if res is None:
        base.update(
            {
                "run_id": None,
                "status": "ERROR",
                "passed": False,
                "error": error or "Unknown error",
                "rubric_score": 0.0,
                "composite_score": 0.0,
                "duration_seconds": round(wall_seconds, 3),
                "phase_timings_ms": {},
                "input_tokens": int((harness_run or {}).get("input_tokens", 0)),
                "output_tokens": int((harness_run or {}).get("output_tokens", 0)),
                "critic_tokens": 0,
                "total_tokens": int((harness_run or {}).get("input_tokens", 0)) + int((harness_run or {}).get("output_tokens", 0)),
                "candidate_cost_usd": 0.0,
                "critic_cost_usd": 0.0,
                "estimated_cost_usd": 0.0,
                "token_source": (harness_run or {}).get("token_source", "n/a"),
            }
        )
        return base

    tok = res.get("token_usage") or {}
    timing = res.get("timing") or {}
    harbor = res.get("harbor") if isinstance(res.get("harbor"), dict) else {}
    ac = res.get("actor_critic_scores") or {}
    in_tok = int(res.get("input_tokens", tok.get("input_tokens", 0)) or 0)
    out_tok = int(res.get("output_tokens", tok.get("output_tokens", 0)) or 0)
    critic_tok = int((tok.get("critics") or {}).get("total_tokens", 0) or (tok.get("actor_critic_scores") or {}).get("total_tokens", 0) or 0)
    cand_cost = float(tok.get("candidate_cost_usd", res.get("estimated_cost_usd", 0.0)) or 0.0)
    critic_cost = float(tok.get("critic_cost_usd", 0.0) or 0.0)
    total_cost = float(tok.get("total_estimated_cost_usd", cand_cost + critic_cost) or 0.0)
    passed = bool(res.get("passed", False))

    if harness_run:
        token_source = harness_run.get("token_source", "estimated")
    elif res.get("execution_mode") == "live":
        token_source = "model_reported"
    else:
        token_source = "simulated (mock)"

    base.update(
        {
            "run_id": res.get("run_id"),
            "status": "PASSED" if passed else "FAILED",
            "passed": passed,
            "error": None,
            "rubric_score": float(res.get("rubric_score", 0.0) or 0.0),
            "composite_score": float(ac.get("composite_normalized_score", 0.0) or 0.0),
            "duration_seconds": float(res.get("duration_seconds", timing.get("duration_seconds", 0.0)) or 0.0),
            "phase_timings_ms": dict(timing.get("phase_timings_ms") or {}),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "critic_tokens": critic_tok,
            "total_tokens": in_tok + out_tok + critic_tok,
            "candidate_cost_usd": round(cand_cost, 6),
            "critic_cost_usd": round(critic_cost, 6),
            "estimated_cost_usd": round(total_cost, 6),
            "token_source": token_source,
            "harbor_tasks_passed": harbor.get("tasks_passed"),
            "harbor_tasks_total": harbor.get("tasks_total"),
            "execution_backend": harbor.get("execution_backend") or ("harness_cli" if harness_run else "direct_model_client"),
        }
    )
    return base


def summarize_report(per_test: List[Dict[str, Any]], req: Dict[str, Any], started_at: float) -> Dict[str, Any]:
    n = len(per_test)
    passed = sum(1 for t in per_test if t["status"] == "PASSED")
    errored = sum(1 for t in per_test if t["status"] == "ERROR")
    scored = [t["composite_score"] for t in per_test if t["status"] != "ERROR"]
    return {
        "total_tests": n,
        "passed_tests": passed,
        "failed_tests": n - passed - errored,
        "errored_tests": errored,
        "pass_rate": round(100.0 * passed / max(1, n), 1),
        "standard_tests": sum(1 for t in per_test if not t["is_custom"]),
        "custom_tests": sum(1 for t in per_test if t["is_custom"]),
        "total_wall_seconds": round(sum(t["wall_seconds"] for t in per_test), 3),
        "elapsed_seconds": round(time.time() - started_at, 3),
        "total_input_tokens": sum(t["input_tokens"] for t in per_test),
        "total_output_tokens": sum(t["output_tokens"] for t in per_test),
        "total_critic_tokens": sum(t["critic_tokens"] for t in per_test),
        "total_tokens": sum(t["total_tokens"] for t in per_test),
        "total_candidate_cost_usd": round(sum(t["candidate_cost_usd"] for t in per_test), 6),
        "total_critic_cost_usd": round(sum(t["critic_cost_usd"] for t in per_test), 6),
        "total_cost_usd": round(sum(t["estimated_cost_usd"] for t in per_test), 6),
        "avg_composite_score": round(sum(scored) / len(scored), 2) if scored else 0.0,
        "model_alias": req["model_alias"],
        "model_name": req["model_entry"].get("name", req["model_alias"]),
        "harness": req["agent_type"],
        "harness_name": req["harness_spec"].get("name", req["agent_type"]),
        "harness_executed_on_host": req["run_harness_on_host"],
        "gcp_project_id": req["gcp_project_id"],
        "gcp_location": req["gcp_location"],
        "execution_mode": req["mode"],
        "harbor": req["use_harbor"],
        "environment_type": req["environment_type"] if req["use_harbor"] else None,
        "critic_model": req.get("critic_model") or ("None (Deterministic Only)" if req.get("no_critics") else "Auto Cross-Evaluator"),
        "no_critics": req.get("no_critics", False),
        "warnings": req["warnings"],
    }


def run_evaluation(
    run_id: str,
    req: Dict[str, Any],
    active_runs: Dict[str, Dict[str, Any]],
    runs_lock: threading.Lock,
) -> None:
    """Execute every selected test and store progress + the final report in ``active_runs[run_id]``."""
    from devbench.harbor import run_harbor_scenario_job, run_harness_headless

    scenario_list: List[str] = req["scenario_list"]
    agent_type: str = req["agent_type"]
    start_time = time.time()
    with runs_lock:
        active_runs[run_id] = {
            "run_id": run_id,
            "scenario_id": req["scenario_id"],
            "scenario_ids": scenario_list,
            "suite_name": req["suite_name"],
            "model_alias": req["model_alias"],
            "gcp_project_id": req["gcp_project_id"],
            "gcp_location": req["gcp_location"],
            "execution_mode": req["mode"],
            "harbor": req["use_harbor"],
            "environment_type": req["environment_type"] if req["use_harbor"] else "podman",
            "harness": agent_type,
            "agent_harness": agent_type,
            "harness_spec": req["harness_spec"],
            "critic_model": req.get("critic_model") or ("None (Deterministic Only)" if req.get("no_critics") else "Auto Cross-Evaluator"),
            "no_critics": req.get("no_critics", False),
            "internal_google_permissions": req["internal_google_permissions"],
            "warnings": req["warnings"],
            "status": "RUNNING",
            "start_time": start_time,
            "elapsed_seconds": 0.0,
            "current_phase": "starting",
            "completed_tests": 0,
            "total_tests": len(scenario_list),
            "test_results": [],
            "passed": None,
        }

    per_test: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    try:
        for idx, sc_item in enumerate(scenario_list):
            with runs_lock:
                active_runs[run_id]["current_phase"] = f"running ({idx + 1}/{len(scenario_list)}): {sc_item}"
                active_runs[run_id]["completed_tests"] = idx
                active_runs[run_id]["elapsed_seconds"] = round(time.time() - start_time, 2)

            t0 = time.perf_counter()
            res: Optional[Dict[str, Any]] = None
            harness_run: Optional[Dict[str, Any]] = None
            error: Optional[str] = None
            try:
                candidate_override = req.get("candidate_override")
                candidate_usage: Optional[Dict[str, Any]] = None
                if req["run_harness_on_host"]:
                    model_entry = req["model_entry"]
                    harness_run = run_harness_headless(
                        harness_id=agent_type,
                        prompt=str(get_scenario_spec(sc_item)["prompt"]),
                        model=model_entry,
                        project_id=str(req["gcp_project_id"]),
                        location=str(req["gcp_location"]),
                        workdir=REPO_ROOT / "artifacts" / "harness_runs" / run_id / sc_item,
                    )
                    candidate_override = harness_run["candidate_output"]
                    reported_cost = harness_run.get("reported_cost_usd")
                    candidate_usage = {
                        "input_tokens": harness_run["input_tokens"],
                        "output_tokens": harness_run["output_tokens"],
                        "latency_ms": harness_run["latency_ms"],
                        "reported_cost_usd": reported_cost,
                        "estimated_cost_usd": reported_cost or 0.0,
                    }

                if req["use_harbor"]:
                    res = run_harbor_scenario_job(
                        scenario_id=sc_item,
                        model_alias=req["model_alias"],
                        mode=req["mode"],
                        agent_type=agent_type,
                        environment_type=req["environment_type"],
                        candidate_override=candidate_override,
                        candidate_usage=candidate_usage,
                        critic_model=req.get("critic_model"),
                        no_critics=req.get("no_critics", False),
                        project_id=str(req["gcp_project_id"]),
                        location=str(req["gcp_location"]),
                        critic_project_id=req.get("critic_project_id"),
                        critic_location=req.get("critic_location"),
                        use_vertex=True,
                    )
                else:
                    res = execute_scenario_run(
                        scenario_id=sc_item,
                        model_alias=req["model_alias"],
                        mode=req["mode"],
                        candidate_override=candidate_override,
                        candidate_usage=candidate_usage,
                        project_id=str(req["gcp_project_id"]),
                        location=str(req["gcp_location"]),
                        actor_project_id=req.get("actor_project_id"),
                        actor_location=req.get("actor_location"),
                        critic_project_id=req.get("critic_project_id"),
                        critic_location=req.get("critic_location"),
                        critic_model=req.get("critic_model"),
                        no_critics=req.get("no_critics", False),
                        use_vertex=True,
                    )
            except Exception as ex:  # noqa: BLE001 - one failing test must not abort the suite
                error = f"{type(ex).__name__}: {ex}"
                from devbench.models.base import VertexModelAccessError

                if isinstance(ex, VertexModelAccessError):
                    with runs_lock:
                        active_runs[run_id]["model_access_error"] = ex.to_dict()

            metrics = build_test_metrics(
                scenario_id=sc_item,
                res=res,
                wall_seconds=time.perf_counter() - t0,
                agent_type=agent_type,
                harness_run=harness_run,
                error=error,
            )
            per_test.append(metrics)
            if res is not None:
                results.append(res)
            with runs_lock:
                active_runs[run_id]["test_results"] = list(per_test)
                active_runs[run_id]["completed_tests"] = idx + 1
                active_runs[run_id]["report"] = summarize_report(per_test, req, start_time)

        final = _aggregate(results, per_test, req)
        report = summarize_report(per_test, req, start_time)
        with runs_lock:
            active_runs[run_id].update(final)
            active_runs[run_id]["test_results"] = per_test
            active_runs[run_id]["report"] = report
            active_runs[run_id]["completed_tests"] = len(scenario_list)
            active_runs[run_id]["elapsed_seconds"] = round(time.time() - start_time, 2)
            active_runs[run_id]["current_phase"] = "complete"
            if results:
                active_runs[run_id]["status"] = "COMPLETED"
            else:
                active_runs[run_id]["status"] = "FAILED"
                active_runs[run_id]["error"] = "; ".join(t["error"] for t in per_test if t.get("error"))
    except Exception as ex:  # noqa: BLE001
        with runs_lock:
            active_runs[run_id]["status"] = "FAILED"
            active_runs[run_id]["error"] = str(ex)
            active_runs[run_id]["test_results"] = per_test
            active_runs[run_id]["report"] = summarize_report(per_test, req, start_time)
            active_runs[run_id]["elapsed_seconds"] = round(time.time() - start_time, 2)


def _aggregate(results: List[Dict[str, Any]], per_test: List[Dict[str, Any]], req: Dict[str, Any]) -> Dict[str, Any]:
    """Suite-level aggregate fields (keeps the shape expected by telemetry cards and repo export)."""
    agent_type = req["agent_type"]
    common = {
        "scenario_id": req["scenario_id"],
        "scenario_ids": req["scenario_list"],
        "model_alias": req["model_alias"],
        "harness": agent_type,
        "agent_harness": agent_type,
        "harness_spec": req["harness_spec"],
        "internal_google_permissions": req["internal_google_permissions"],
        "gcp_project_id": req["gcp_project_id"],
        "gcp_location": req["gcp_location"],
    }
    if not results:
        return {**common, "passed": False, "exit_code": 1}

    total_cand_ms = sum(float((r.get("timing") or {}).get("phase_timings_ms", {}).get("candidate_generation", 0.0)) for r in results)
    total_sand_ms = sum(float((r.get("timing") or {}).get("phase_timings_ms", {}).get("sandbox_execution", 0.0)) for r in results)
    total_crit_ms = sum(float((r.get("timing") or {}).get("phase_timings_ms", {}).get("actor_critic_evaluation", 0.0)) for r in results)
    total_in = sum(t["input_tokens"] for t in per_test)
    total_out = sum(t["output_tokens"] for t in per_test)
    total_crit_tok = sum(t["critic_tokens"] for t in per_test)
    total_cand_cost = sum(t["candidate_cost_usd"] for t in per_test)
    total_cost = sum(t["estimated_cost_usd"] for t in per_test)
    total_wall_s = sum(t["wall_seconds"] for t in per_test)

    def _avg_eval(name: str) -> Dict[str, Any]:
        scores = []
        rationale = ""
        for r in results:
            ev = ((r.get("actor_critic_scores") or {}).get("evaluations") or {}).get(name)
            if ev:
                scores.append(float(ev.get("normalized_score", 0.0)))
                rationale = ev.get("rationale", rationale)
        return {"normalized_score": round(sum(scores) / len(scores), 2) if scores else 0.0, "rationale": rationale}

    comp_scores = [
        float((r.get("actor_critic_scores") or {}).get("composite_normalized_score"))
        for r in results
        if (r.get("actor_critic_scores") or {}).get("composite_normalized_score") is not None
    ]
    all_passed = all(t["status"] == "PASSED" for t in per_test)

    combined_outputs = []
    for idx, r in enumerate(results):
        sc = r.get("scenario_id", "")
        combined_outputs.append(
            "// =========================================================================\n"
            f"// Test [{idx + 1}/{len(results)}]: {sc} "
            f"({'Custom Test' if _is_custom(sc) else 'Standard Test'})\n"
            f"// Harness: {agent_type} | GCP Project: {req['gcp_project_id']}\n"
            "// =========================================================================\n"
            f"{r.get('candidate_output', '')}"
        )

    result = dict(results[0]) if len(results) == 1 else {
        k: v for k, v in results[0].items() if k in ("harbor", "suite_slug", "pillar", "difficulty", "execution_mode")
    }
    total_dur_ms = round(total_cand_ms + total_sand_ms + total_crit_ms, 2)
    result.update(common)
    result.update(
        {
            "suite_name": req["suite_name"] or (f"Custom Suite ({len(per_test)} Tests)" if len(per_test) > 1 else None),
            "passed": all_passed,
            "exit_code": 0 if all_passed else 1,
            "duration_ms": total_dur_ms,
            "duration_seconds": round(total_dur_ms / 1000.0, 3),
            "wall_seconds": round(total_wall_s, 3),
            "input_tokens": total_in,
            "output_tokens": total_out,
            "total_tokens": total_in + total_out + total_crit_tok,
            "estimated_cost_usd": round(total_cost, 6),
            "candidate_output": results[0].get("candidate_output", "") if len(results) == 1 else "\n\n".join(combined_outputs),
            "timing": {
                "duration_ms": total_dur_ms,
                "duration_seconds": round(total_dur_ms / 1000.0, 3),
                "wall_seconds": round(total_wall_s, 3),
                "phase_timings_ms": {
                    "candidate_generation": round(total_cand_ms, 2),
                    "sandbox_execution": round(total_sand_ms, 2),
                    "actor_critic_evaluation": round(total_crit_ms, 2),
                },
            },
            "token_usage": {
                "input_tokens": total_in,
                "output_tokens": total_out,
                "candidate_input_tokens": total_in,
                "candidate_output_tokens": total_out,
                "candidate_cost_usd": round(total_cand_cost, 6),
                "critic_cost_usd": round(total_cost - total_cand_cost, 6),
                "total_estimated_cost_usd": round(total_cost, 6),
                "total_tokens": total_in + total_out + total_crit_tok,
                "actor_critic_scores": {"total_tokens": total_crit_tok},
            },
            "actor_critic_scores": {
                "composite_normalized_score": round(sum(comp_scores) / len(comp_scores), 2) if comp_scores else 0.0,
                "evaluations": {
                    "qwen": _avg_eval("qwen"),
                    "minimax": _avg_eval("minimax"),
                    "kimi_k": _avg_eval("kimi_k"),
                },
            },
        }
    )
    if len(results) == 1:
        result["run_id_test"] = results[0].get("run_id")
    result.pop("run_id", None)
    return result
