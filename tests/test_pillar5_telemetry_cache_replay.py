"""Tests for Pillar 5: Telemetry, Deterministic Caching & Replay Infrastructure."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from benchmaxxer.critics.evaluator import CriticEvaluator
from benchmaxxer.models.factory import get_model_client
from benchmaxxer.telemetry.cache import (
    CriticCache,
    ReplayCacheMissError,
    ResponseCache,
    compute_candidate_cache_key,
    compute_critic_cache_key,
)
from benchmaxxer.telemetry.logger import RunRecord, TelemetryLogger


def test_deterministic_candidate_and_critic_cache_files_and_replay(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    critic_cache_dir = tmp_path / "cache" / "critics"

    # 1. Initial candidate call writes to artifacts/cache/{model_alias}/{cache_key}.json
    client = get_model_client(alias="gemini-1.5-pro", mode="mock", cache_dir=cache_dir)
    prompt = "Generate a modular skill for BigQuery synthesis."
    sys_inst = "Act as an ADK architect."
    resp1 = client.generate(prompt=prompt, system_instruction=sys_inst)
    assert client.call_count == 1

    expected_key = compute_candidate_cache_key(
        model_alias="gemini-1.5-pro",
        prompt=prompt,
        system_instruction=sys_inst,
        generation_params=client.last_generation_params,
    )
    expected_file = cache_dir / "gemini-1.5-pro" / f"{expected_key}.json"
    assert expected_file.exists()

    # 2. Replay client reads strictly from cache without calling model inference (call_count == 0)
    replay_client = get_model_client(
        alias="gemini-1.5-pro",
        mode="mock",
        replay=True,
        cache_dir=cache_dir,
    )
    resp_replay = replay_client.generate(prompt=prompt, system_instruction=sys_inst)
    assert replay_client.call_count == 0
    assert resp_replay.text == resp1.text
    assert resp_replay.raw_response["cached"] is True

    # 3. Replay miss raises ReplayCacheMissError
    with pytest.raises(ReplayCacheMissError):
        replay_client.generate(prompt="Uncached prompt never seen before")

    # 4. Critic Evaluation Cache writes to artifacts/cache/critics/{critic_alias}/{cache_key}.json
    critic_cache = CriticCache(base_dir=critic_cache_dir)
    evaluator = CriticEvaluator(
        critic_name="qwen",
        critic_alias="critic-qwen",
        mode="mock",
        critic_cache=critic_cache,
        model_client=get_model_client("critic-qwen", mode="mock", cache_dir=cache_dir),
    )
    ev1 = evaluator.evaluate(
        scenario_id="complex_skill_synthesis",
        prompt=prompt,
        candidate_output=resp1.text,
        test_context={"status": "PASS"},
    )
    assert evaluator.client.call_count == 1
    critic_files = list((critic_cache_dir / "critic-qwen").glob("*.json"))
    assert len(critic_files) == 1

    # Replay critic evaluator makes 0 model calls
    replay_critic_cache = CriticCache(base_dir=critic_cache_dir, replay=True)
    replay_evaluator = CriticEvaluator(
        critic_name="qwen",
        critic_alias="critic-qwen",
        mode="mock",
        replay=True,
        critic_cache=replay_critic_cache,
        model_client=get_model_client("critic-qwen", mode="mock", replay=True, cache_dir=cache_dir),
    )
    ev_replay = replay_evaluator.evaluate(
        scenario_id="complex_skill_synthesis",
        prompt=prompt,
        candidate_output=resp1.text,
        test_context={"status": "PASS"},
    )
    assert replay_evaluator.client.call_count == 0
    assert ev_replay.score == ev1.score


def test_structured_run_logging_sqlite_and_jsonl(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    logger = TelemetryLogger(base_dir=telemetry_dir)

    record = RunRecord(
        run_id="test-run-001",
        timestamp="2026-09-24T18:00:00Z",
        model_alias="gemini-1.5-pro",
        scenario_id="complex_skill_synthesis",
        execution_mode="mock",
        latency_ms=42.5,
        input_tokens=120,
        output_tokens=340,
        estimated_cost_usd=0.00185,
        metrics_dict={"actor_critic_quality_score": 100.0, "execution_completeness_rate": 100.0},
        actor_critic_scores={
            "composite_score": 5.0,
            "composite_normalized_score": 100.0,
            "critics": {
                "qwen": {"score": 5},
                "minimax": {"score": 5},
                "kimi_k": {"score": 5},
            },
        },
        exit_code=0,
        trace_path=str(telemetry_dir / "traces" / "test-run-001.json"),
    )
    logger.log_run(record)

    # Verify SQLite database
    assert logger.db_path.exists()
    with sqlite3.connect(logger.db_path) as conn:
        row = conn.execute("SELECT run_id, model_alias, scenario_id, exit_code FROM runs").fetchone()
    assert row == ("test-run-001", "gemini-1.5-pro", "complex_skill_synthesis", 0)

    # Verify JSONL file
    assert logger.jsonl_path.exists()
    lines = logger.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["run_id"] == "test-run-001"
    assert parsed["actor_critic_scores"]["composite_score"] == 5.0
