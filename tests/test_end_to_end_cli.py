"""End-to-End Acceptance Tests for test_runner.py and benchmaxxer CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_end_to_end_runner_and_replay_and_inspector(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    cache_dir = tmp_path / "cache"
    telemetry_dir = tmp_path / "telemetry"

    # 1. Execute test_runner.py in mock mode
    cmd_run = [
        sys.executable,
        str(repo_root / "test_runner.py"),
        "--scenario",
        "complex_skill_synthesis",
        "--model",
        "gemini-1.5-pro",
        "--mode",
        "mock",
        "--cache-dir",
        str(cache_dir),
        "--telemetry-dir",
        str(telemetry_dir),
    ]
    proc1 = subprocess.run(cmd_run, capture_output=True, text=True, check=True)
    out1 = json.loads(proc1.stdout)
    assert out1["scenario_id"] == "complex_skill_synthesis"
    assert out1["model_alias"] == "gemini-1.5-pro"
    assert out1["passed"] is True
    assert out1["exit_code"] == 0
    assert out1["actor_critic_scores"]["composite_score"] == 5.0
    assert set(out1["actor_critic_scores"]["critics"].keys()) == {"qwen", "minimax", "kimi_k"}

    # 2. Execute test_runner.py with --replay against cached outputs
    cmd_replay = cmd_run + ["--replay"]
    proc2 = subprocess.run(cmd_replay, capture_output=True, text=True, check=True)
    out2 = json.loads(proc2.stdout)
    assert out2["replayed"] is True
    assert out2["cached"] is True
    assert out2["metrics_dict"] == out1["metrics_dict"]

    # 3. Execute negative fixture verification (must return non-zero exit code and clean failure)
    cmd_neg = [
        sys.executable,
        str(repo_root / "test_runner.py"),
        "--scenario",
        "complex_skill_synthesis",
        "--model",
        "gemini-1.5-pro",
        "--mode",
        "mock",
        "--fixtures",
        str(repo_root / "fixtures" / "negative"),
        "--cache-dir",
        str(cache_dir),
        "--telemetry-dir",
        str(telemetry_dir),
    ]
    proc_neg = subprocess.run(cmd_neg, capture_output=True, text=True, check=False)
    assert proc_neg.returncode != 0
    out_neg = json.loads(proc_neg.stdout)
    assert out_neg["passed"] is False
    assert out_neg["actor_critic_scores"]["composite_score"] == 1.0
