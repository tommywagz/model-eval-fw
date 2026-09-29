"""Token Usage & Cost Assessment Bridge integrating project .env and @.agents/scripts/tokens."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOTENV_PATH = REPO_ROOT / ".env"
DEFAULT_TOKENS_SCRIPT_PATH = REPO_ROOT / ".agents" / "scripts" / "tokens"


def resolve_project_dotenv(dotenv_path: Optional[str | Path] = None) -> Path:
    """Locate the project-level .env file."""
    if dotenv_path:
        return Path(dotenv_path)
    env_override = os.environ.get("TOKEN_OVERLAY_ENV")
    if env_override:
        p = Path(env_override)
        if p.exists():
            return p
    for candidate in (DEFAULT_DOTENV_PATH, Path.cwd() / ".env"):
        if candidate.exists():
            return candidate
    return DEFAULT_DOTENV_PATH


def load_project_dotenv(
    dotenv_path: Optional[str | Path] = None,
    override: bool = False,
) -> Dict[str, Any]:
    """Load the project-level .env file into os.environ using the same strict parser as .agents/scripts/tokens.

    Returns metadata about the loaded environment without exposing secret values.
    """
    path = resolve_project_dotenv(dotenv_path)
    loaded_keys: List[str] = []
    configured_keys: List[str] = []

    if not path.is_file():
        return {
            "dotenv_path": str(path),
            "exists": False,
            "loaded_keys": [],
            "configured_keys": [],
        }

    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"Invalid .env assignment on line {number} in {path}")
        try:
            parts = shlex.split(value, comments=True)
        except ValueError:
            raise ValueError(f"Invalid .env quoting on line {number} in {path}") from None
        if len(parts) > 1:
            raise ValueError(f"Quote values containing spaces in .env line {number} in {path}")
        parsed_val = parts[0] if parts else ""
        if override or key not in os.environ:
            os.environ[key] = parsed_val
        loaded_keys.append(key)
        if os.environ.get(key):
            configured_keys.append(key)

    os.environ.setdefault("TOKEN_OVERLAY_ENV", str(path))
    return {
        "dotenv_path": str(path),
        "exists": True,
        "loaded_keys": loaded_keys,
        "configured_keys": configured_keys,
    }


class TokensScriptBridge:
    """Executes and parses telemetry snapshots from `@.agents/scripts/tokens --check`."""

    def __init__(
        self,
        script_path: Optional[str | Path] = None,
        dotenv_path: Optional[str | Path] = None,
        enabled: bool = True,
    ) -> None:
        self.script_path = Path(script_path) if script_path else DEFAULT_TOKENS_SCRIPT_PATH
        self.dotenv_path = resolve_project_dotenv(dotenv_path)
        self.enabled = enabled

    def capture_snapshot(self, timeout: float = 15.0) -> Dict[str, Any]:
        """Run `.agents/scripts/tokens --check` and return normalized provider token/credit readings."""
        load_info = load_project_dotenv(self.dotenv_path)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if not self.enabled or not self.script_path.exists():
            return {
                "timestamp": timestamp,
                "script_path": str(self.script_path),
                "dotenv_path": str(self.dotenv_path),
                "dotenv_exists": load_info["exists"],
                "available": False,
                "exit_code": -1,
                "providers": [],
                "configured_providers": [],
            }

        env = dict(os.environ)
        env["TOKEN_OVERLAY_ENV"] = str(self.dotenv_path)

        try:
            proc = subprocess.run(
                [str(self.script_path), "--check"],
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
                check=False,
            )
            providers: List[Dict[str, Any]] = []
            if proc.stdout.strip():
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    providers = [p for p in parsed if isinstance(p, dict)]

            configured_providers = [
                str(p.get("name"))
                for p in providers
                if p.get("status") == "ok"
            ]
            return {
                "timestamp": timestamp,
                "script_path": str(self.script_path),
                "dotenv_path": str(self.dotenv_path),
                "dotenv_exists": load_info["exists"],
                "available": True,
                "exit_code": int(proc.returncode),
                "providers": providers,
                "configured_providers": configured_providers,
            }
        except Exception as exc:
            return {
                "timestamp": timestamp,
                "script_path": str(self.script_path),
                "dotenv_path": str(self.dotenv_path),
                "dotenv_exists": load_info["exists"],
                "available": False,
                "exit_code": -1,
                "error": str(exc),
                "providers": [],
                "configured_providers": [],
            }

    @staticmethod
    def compute_delta(
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compute provider token usage and credit balance deltas between two `tokens --check` snapshots."""
        if not before or not after:
            return {
                "provider_deltas": {},
                "total_provider_token_delta": 0,
                "total_provider_credit_delta_usd": 0.0,
                "providers": (after or before or {}).get("providers", []),
            }

        before_map = {
            str(p.get("name")): p for p in before.get("providers", []) if isinstance(p, dict)
        }
        after_map = {
            str(p.get("name")): p for p in after.get("providers", []) if isinstance(p, dict)
        }

        provider_deltas: Dict[str, Dict[str, Any]] = {}
        total_tok_delta = 0
        total_cred_delta = 0.0

        for name, after_item in after_map.items():
            before_item = before_map.get(name, {})
            b_tok = before_item.get("tokens")
            a_tok = after_item.get("tokens")
            b_cred = before_item.get("credits")
            a_cred = after_item.get("credits")

            tok_delta: Optional[int] = None
            if isinstance(b_tok, (int, float)) and isinstance(a_tok, (int, float)):
                tok_delta = max(0, int(a_tok) - int(b_tok))
                total_tok_delta += tok_delta

            cred_delta: Optional[float] = None
            if isinstance(b_cred, (int, float)) and isinstance(a_cred, (int, float)):
                cred_delta = round(float(b_cred) - float(a_cred), 6)
                total_cred_delta += max(0.0, cred_delta)

            provider_deltas[name] = {
                "status": after_item.get("status", "setup"),
                "before_tokens": b_tok,
                "after_tokens": a_tok,
                "token_delta": tok_delta,
                "before_credits_usd": b_cred,
                "after_credits_usd": a_cred,
                "credit_used_usd": cred_delta,
                "detail": after_item.get("detail", ""),
            }

        return {
            "script_path": after.get("script_path"),
            "dotenv_path": after.get("dotenv_path"),
            "before_timestamp": before.get("timestamp"),
            "after_timestamp": after.get("timestamp"),
            "configured_providers": after.get("configured_providers", []),
            "total_provider_token_delta": total_tok_delta,
            "total_provider_credit_delta_usd": round(total_cred_delta, 6),
            "provider_deltas": provider_deltas,
            "providers": after.get("providers", []),
        }


def build_test_token_result(
    scenario_id: str,
    suite_slug: str,
    suite_name: str,
    model_alias: str,
    candidate_input_tokens: int,
    candidate_output_tokens: int,
    candidate_cost_usd: float,
    actor_critic_scores: Optional[Dict[str, Any]] = None,
    tokens_script_telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build standardized test-level token usage and cost assessment."""
    ac = actor_critic_scores or {}
    critics_map = ac.get("critics") or {}

    critic_in = int(ac.get("total_input_tokens", 0))
    critic_out = int(ac.get("total_output_tokens", 0))
    critic_cost = float(ac.get("total_estimated_cost_usd", 0.0))

    by_critic: Dict[str, Dict[str, Any]] = {}
    if critics_map:
        recalc_in = 0
        recalc_out = 0
        recalc_cost = 0.0
        for cname, cdata in critics_map.items():
            if not isinstance(cdata, dict):
                continue
            cin = int(cdata.get("input_tokens", 0))
            cout = int(cdata.get("output_tokens", 0))
            ccost = float(cdata.get("estimated_cost_usd", 0.0))
            recalc_in += cin
            recalc_out += cout
            recalc_cost += ccost
            by_critic[cname] = {
                "input_tokens": cin,
                "output_tokens": cout,
                "total_tokens": cin + cout,
                "estimated_cost_usd": round(ccost, 6),
            }
        if critic_in == 0 and recalc_in > 0:
            critic_in = recalc_in
        if critic_out == 0 and recalc_out > 0:
            critic_out = recalc_out
        if critic_cost == 0.0 and recalc_cost > 0.0:
            critic_cost = recalc_cost

    cand_total = int(candidate_input_tokens) + int(candidate_output_tokens)
    critic_total = critic_in + critic_out
    total_in = int(candidate_input_tokens) + critic_in
    total_out = int(candidate_output_tokens) + critic_out
    total_tokens = total_in + total_out
    total_cost = round(float(candidate_cost_usd) + critic_cost, 6)

    return {
        "level": "test",
        "scenario_id": scenario_id,
        "suite_slug": suite_slug,
        "suite_name": suite_name,
        "model_alias": model_alias,
        "candidate": {
            "input_tokens": int(candidate_input_tokens),
            "output_tokens": int(candidate_output_tokens),
            "total_tokens": cand_total,
            "estimated_cost_usd": round(float(candidate_cost_usd), 6),
        },
        "critics": {
            "input_tokens": critic_in,
            "output_tokens": critic_out,
            "total_tokens": critic_total,
            "estimated_cost_usd": round(critic_cost, 6),
            "by_critic": by_critic,
        },
        "input_tokens": int(candidate_input_tokens),
        "output_tokens": int(candidate_output_tokens),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_tokens,
        "candidate_cost_usd": round(float(candidate_cost_usd), 6),
        "critic_cost_usd": round(critic_cost, 6),
        "total_estimated_cost_usd": total_cost,
        "tokens_script_telemetry": tokens_script_telemetry or {},
    }


def build_suite_token_result(
    suite_slug: str,
    suite_name: str,
    model_alias: str,
    test_token_results: List[Dict[str, Any]],
    tokens_script_telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate test-level token usage & costs into a suite-level token assessment."""
    count = len(test_token_results)
    cand_in = sum(int(t.get("candidate", {}).get("input_tokens", t.get("input_tokens", 0))) for t in test_token_results)
    cand_out = sum(int(t.get("candidate", {}).get("output_tokens", t.get("output_tokens", 0))) for t in test_token_results)
    cand_cost = round(
        sum(float(t.get("candidate", {}).get("estimated_cost_usd", t.get("candidate_cost_usd", 0.0))) for t in test_token_results),
        6,
    )

    crit_in = sum(int(t.get("critics", {}).get("input_tokens", 0)) for t in test_token_results)
    crit_out = sum(int(t.get("critics", {}).get("output_tokens", 0)) for t in test_token_results)
    crit_cost = round(
        sum(float(t.get("critics", {}).get("estimated_cost_usd", t.get("critic_cost_usd", 0.0))) for t in test_token_results),
        6,
    )

    total_in = cand_in + crit_in
    total_out = cand_out + crit_out
    total_tokens = total_in + total_out
    total_cost = round(cand_cost + crit_cost, 6)

    return {
        "level": "suite",
        "suite_slug": suite_slug,
        "suite_name": suite_name,
        "model_alias": model_alias,
        "test_count": count,
        "candidate": {
            "input_tokens": cand_in,
            "output_tokens": cand_out,
            "total_tokens": cand_in + cand_out,
            "estimated_cost_usd": cand_cost,
        },
        "critics": {
            "input_tokens": crit_in,
            "output_tokens": crit_out,
            "total_tokens": crit_in + crit_out,
            "estimated_cost_usd": crit_cost,
        },
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_tokens,
        "candidate_cost_usd": cand_cost,
        "critic_cost_usd": crit_cost,
        "total_estimated_cost_usd": total_cost,
        "average_tokens_per_test": round(total_tokens / count, 2) if count > 0 else 0.0,
        "average_cost_per_test_usd": round(total_cost / count, 6) if count > 0 else 0.0,
        "per_test_tokens": [
            {
                "scenario_id": t.get("scenario_id"),
                "candidate_tokens": int(t.get("candidate", {}).get("total_tokens", 0)),
                "critic_tokens": int(t.get("critics", {}).get("total_tokens", 0)),
                "total_tokens": int(t.get("total_tokens", 0)),
                "candidate_cost_usd": round(float(t.get("candidate_cost_usd", 0.0)), 6),
                "critic_cost_usd": round(float(t.get("critic_cost_usd", 0.0)), 6),
                "total_estimated_cost_usd": round(float(t.get("total_estimated_cost_usd", 0.0)), 6),
            }
            for t in test_token_results
        ],
        "tokens_script_telemetry": tokens_script_telemetry or {},
    }


def build_framework_token_result(
    model_alias: str,
    suite_token_results: List[Dict[str, Any]],
    tokens_script_telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate suite-level and test-level token usage & costs into a framework-level token assessment."""
    suite_count = len(suite_token_results)
    all_tests: List[Dict[str, Any]] = []
    for s in suite_token_results:
        for t in s.get("per_test_tokens", []):
            entry = dict(t)
            entry.setdefault("suite_slug", s.get("suite_slug"))
            entry.setdefault("suite_name", s.get("suite_name"))
            all_tests.append(entry)
    test_count = len(all_tests)

    cand_in = sum(int(s.get("candidate", {}).get("input_tokens", 0)) for s in suite_token_results)
    cand_out = sum(int(s.get("candidate", {}).get("output_tokens", 0)) for s in suite_token_results)
    cand_cost = round(sum(float(s.get("candidate_cost_usd", 0.0)) for s in suite_token_results), 6)

    crit_in = sum(int(s.get("critics", {}).get("input_tokens", 0)) for s in suite_token_results)
    crit_out = sum(int(s.get("critics", {}).get("output_tokens", 0)) for s in suite_token_results)
    crit_cost = round(sum(float(s.get("critic_cost_usd", 0.0)) for s in suite_token_results), 6)

    total_in = cand_in + crit_in
    total_out = cand_out + crit_out
    total_tokens = total_in + total_out
    total_cost = round(cand_cost + crit_cost, 6)

    return {
        "level": "framework",
        "model_alias": model_alias,
        "suite_count": suite_count,
        "test_count": test_count,
        "candidate": {
            "input_tokens": cand_in,
            "output_tokens": cand_out,
            "total_tokens": cand_in + cand_out,
            "estimated_cost_usd": cand_cost,
        },
        "critics": {
            "input_tokens": crit_in,
            "output_tokens": crit_out,
            "total_tokens": crit_in + crit_out,
            "estimated_cost_usd": crit_cost,
        },
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_tokens,
        "candidate_cost_usd": cand_cost,
        "critic_cost_usd": crit_cost,
        "total_estimated_cost_usd": total_cost,
        "average_tokens_per_suite": round(total_tokens / suite_count, 2) if suite_count > 0 else 0.0,
        "average_cost_per_suite_usd": round(total_cost / suite_count, 6) if suite_count > 0 else 0.0,
        "average_tokens_per_test": round(total_tokens / test_count, 2) if test_count > 0 else 0.0,
        "average_cost_per_test_usd": round(total_cost / test_count, 6) if test_count > 0 else 0.0,
        "per_suite_tokens": [
            {
                "suite_slug": s.get("suite_slug"),
                "suite_name": s.get("suite_name"),
                "test_count": s.get("test_count", 0),
                "total_tokens": s.get("total_tokens", 0),
                "candidate_cost_usd": s.get("candidate_cost_usd", 0.0),
                "critic_cost_usd": s.get("critic_cost_usd", 0.0),
                "total_estimated_cost_usd": s.get("total_estimated_cost_usd", 0.0),
            }
            for s in suite_token_results
        ],
        "per_test_tokens": all_tests,
        "tokens_script_telemetry": tokens_script_telemetry or {},
    }


def summarize_logged_token_costs(
    telemetry_dir: Optional[str | Path] = None,
    provider_readings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Aggregate test, suite, and framework level token costs & timings from logged telemetry."""
    from benchmaxxer.telemetry.logger import TelemetryLogger

    logger = TelemetryLogger(base_dir=telemetry_dir)
    runs = logger.list_runs(limit=500)

    if provider_readings is None:
        bridge = TokensScriptBridge()
        snap = bridge.capture_snapshot()
        provider_readings = snap.get("providers", [])

    from benchmaxxer.scenarios.runner import SCENARIO_CATALOG, SUITE_ALIAS_MAP, SUITE_CATALOG

    suites_grouped: Dict[str, List[Dict[str, Any]]] = {}
    test_summaries: List[Dict[str, Any]] = []

    for r in reversed(runs):
        sc_id = str(r.get("scenario_id", "unknown"))
        spec = SCENARIO_CATALOG.get(sc_id, {})
        raw_slug = str(r.get("suite_slug") or spec.get("suite_slug") or r.get("pillar", "agent_skill_creation"))
        suite_slug = SUITE_ALIAS_MAP.get(raw_slug.strip().lower(), raw_slug.strip().lower().replace(" ", "_"))
        suite_name = str(
            SUITE_CATALOG.get(suite_slug, {}).get("suite_name")
            or spec.get("suite_name")
            or r.get("pillar", "BenchMaxxer Core Evaluation")
        )
        model_alias = str(r.get("model_alias", "gemini-1.5-pro"))

        token_usage = r.get("token_usage")
        if not isinstance(token_usage, dict) or not token_usage:
            token_usage = build_test_token_result(
                scenario_id=sc_id,
                suite_slug=suite_slug,
                suite_name=suite_name,
                model_alias=model_alias,
                candidate_input_tokens=int(r.get("input_tokens", 0)),
                candidate_output_tokens=int(r.get("output_tokens", 0)),
                candidate_cost_usd=float(r.get("estimated_cost_usd", 0.0)),
                actor_critic_scores=r.get("actor_critic_scores"),
            )

        timing_info = r.get("timing") or {
            "duration_ms": float(r.get("duration_ms", r.get("latency_ms", 0.0))),
            "duration_seconds": round(float(r.get("duration_ms", r.get("latency_ms", 0.0))) / 1000.0, 6),
        }

        entry = {
            "run_id": r.get("run_id"),
            "timestamp": r.get("timestamp"),
            "scenario_id": sc_id,
            "suite_slug": suite_slug,
            "suite_name": suite_name,
            "model_alias": model_alias,
            "duration_ms": timing_info.get("duration_ms", 0.0),
            "duration_seconds": timing_info.get("duration_seconds", 0.0),
            "token_usage": token_usage,
        }
        test_summaries.append(entry)
        suites_grouped.setdefault(suite_slug, []).append(entry)

    suite_token_results: List[Dict[str, Any]] = []
    suite_time_summaries: Dict[str, Dict[str, Any]] = {}
    for s_slug, entries in suites_grouped.items():
        s_name = entries[0]["suite_name"]
        m_alias = entries[-1]["model_alias"]
        t_tokens = [e["token_usage"] for e in entries]
        suite_tok = build_suite_token_result(
            suite_slug=s_slug,
            suite_name=s_name,
            model_alias=m_alias,
            test_token_results=t_tokens,
        )
        suite_dur_ms = round(sum(float(e.get("duration_ms", 0.0)) for e in entries), 3)
        suite_tok["total_duration_ms"] = suite_dur_ms
        suite_tok["total_duration_seconds"] = round(suite_dur_ms / 1000.0, 6)
        suite_token_results.append(suite_tok)
        suite_time_summaries[s_slug] = {
            "suite_slug": s_slug,
            "suite_name": s_name,
            "test_count": len(entries),
            "total_duration_ms": suite_dur_ms,
            "total_duration_seconds": round(suite_dur_ms / 1000.0, 6),
        }

    framework_tok = build_framework_token_result(
        model_alias=test_summaries[-1]["model_alias"] if test_summaries else "gemini-1.5-pro",
        suite_token_results=suite_token_results,
        tokens_script_telemetry={"providers": provider_readings},
    )
    fw_dur_ms = round(sum(float(e.get("duration_ms", 0.0)) for e in test_summaries), 3)
    framework_tok["total_duration_ms"] = fw_dur_ms
    framework_tok["total_duration_seconds"] = round(fw_dur_ms / 1000.0, 6)

    return {
        "framework_level": framework_tok,
        "suite_level": suite_token_results,
        "test_level": [
            {
                "run_id": e["run_id"],
                "scenario_id": e["scenario_id"],
                "suite_slug": e["suite_slug"],
                "suite_name": e["suite_name"],
                "model_alias": e["model_alias"],
                "duration_ms": e["duration_ms"],
                "duration_seconds": e["duration_seconds"],
                "total_tokens": e["token_usage"]["total_tokens"],
                "total_estimated_cost_usd": e["token_usage"]["total_estimated_cost_usd"],
                "candidate_cost_usd": e["token_usage"]["candidate_cost_usd"],
                "critic_cost_usd": e["token_usage"]["critic_cost_usd"],
            }
            for e in test_summaries
        ],
        "provider_readings": provider_readings,
    }
