"""Hierarchical Timer Utilities for Test, Suite, and Framework Level Execution Telemetry."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class ExecutionTimer:
    """High-precision monotonic stopwatch and context manager for test, suite, and framework runs."""

    name: str = "execution"
    level: str = "test"
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0
    duration_seconds: float = 0.0
    phase_timings_ms: Dict[str, float] = field(default_factory=dict)
    _start_perf: Optional[float] = field(default=None, init=False, repr=False)

    def start(self) -> "ExecutionTimer":
        self.started_at = _utc_now_iso()
        self._start_perf = time.perf_counter()
        return self

    def stop(self) -> "ExecutionTimer":
        if self._start_perf is not None:
            elapsed_sec = max(0.0, time.perf_counter() - self._start_perf)
            self.duration_ms = round(elapsed_sec * 1000.0, 3)
            self.duration_seconds = round(elapsed_sec, 6)
            self._start_perf = None
        if not self.completed_at:
            self.completed_at = _utc_now_iso()
        return self

    def __enter__(self) -> "ExecutionTimer":
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

    @contextmanager
    def phase(self, phase_name: str) -> Iterator[None]:
        """Measure a named sub-phase inside this timer and record its duration in milliseconds."""
        p_start = time.perf_counter()
        try:
            yield
        finally:
            p_elapsed_ms = round(max(0.0, (time.perf_counter() - p_start) * 1000.0), 3)
            self.phase_timings_ms[phase_name] = round(
                self.phase_timings_ms.get(phase_name, 0.0) + p_elapsed_ms, 3
            )

    def record_phase(self, phase_name: str, duration_ms: float) -> None:
        self.phase_timings_ms[phase_name] = round(float(duration_ms), 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round(float(self.duration_ms), 3),
            "duration_seconds": round(float(self.duration_seconds), 6),
            "phase_timings_ms": dict(self.phase_timings_ms),
        }


def build_test_timing_result(
    scenario_id: str,
    suite_slug: str,
    suite_name: str,
    timer: ExecutionTimer,
    model_latency_ms: float = 0.0,
    critic_latency_ms: float = 0.0,
) -> Dict[str, Any]:
    """Build standardized test-level timing telemetry dictionary."""
    return {
        "level": "test",
        "scenario_id": scenario_id,
        "suite_slug": suite_slug,
        "suite_name": suite_name,
        "started_at": timer.started_at,
        "completed_at": timer.completed_at,
        "duration_ms": round(float(timer.duration_ms), 3),
        "duration_seconds": round(float(timer.duration_seconds), 6),
        "model_latency_ms": round(float(model_latency_ms), 3),
        "critic_latency_ms": round(float(critic_latency_ms), 3),
        "phase_timings_ms": dict(timer.phase_timings_ms),
    }


def build_suite_timing_result(
    suite_slug: str,
    suite_name: str,
    timer: ExecutionTimer,
    test_timings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate individual test timings into a suite-level timing result."""
    durations = [float(t.get("duration_ms", 0.0)) for t in test_timings]
    sum_test_ms = round(sum(durations), 3)
    count = len(durations)
    avg_test_ms = round(sum_test_ms / count, 3) if count > 0 else 0.0
    min_test_ms = round(min(durations), 3) if count > 0 else 0.0
    max_test_ms = round(max(durations), 3) if count > 0 else 0.0
    total_ms = round(max(float(timer.duration_ms), sum_test_ms), 3)
    total_sec = round(total_ms / 1000.0, 6)

    return {
        "level": "suite",
        "suite_slug": suite_slug,
        "suite_name": suite_name,
        "started_at": timer.started_at,
        "completed_at": timer.completed_at,
        "test_count": count,
        "total_duration_ms": total_ms,
        "total_duration_seconds": total_sec,
        "wall_clock_duration_ms": round(float(timer.duration_ms), 3),
        "sum_test_duration_ms": sum_test_ms,
        "average_test_duration_ms": avg_test_ms,
        "min_test_duration_ms": min_test_ms,
        "max_test_duration_ms": max_test_ms,
        "per_test_timings": [
            {
                "scenario_id": t.get("scenario_id"),
                "duration_ms": round(float(t.get("duration_ms", 0.0)), 3),
                "duration_seconds": round(float(t.get("duration_seconds", 0.0)), 6),
                "model_latency_ms": round(float(t.get("model_latency_ms", 0.0)), 3),
                "critic_latency_ms": round(float(t.get("critic_latency_ms", 0.0)), 3),
                "phase_timings_ms": t.get("phase_timings_ms", {}),
            }
            for t in test_timings
        ],
    }


def build_framework_timing_result(
    timer: ExecutionTimer,
    suite_timings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate suite-level and test-level timings into a framework-level timing result."""
    suite_durations = [float(s.get("total_duration_ms", 0.0)) for s in suite_timings]
    sum_suite_ms = round(sum(suite_durations), 3)
    suite_count = len(suite_timings)

    all_tests: List[Dict[str, Any]] = []
    for s in suite_timings:
        for t in s.get("per_test_timings", []):
            entry = dict(t)
            entry.setdefault("suite_slug", s.get("suite_slug"))
            entry.setdefault("suite_name", s.get("suite_name"))
            all_tests.append(entry)

    test_durations = [float(t.get("duration_ms", 0.0)) for t in all_tests]
    sum_test_ms = round(sum(test_durations), 3)
    test_count = len(all_tests)

    avg_suite_ms = round(sum_suite_ms / suite_count, 3) if suite_count > 0 else 0.0
    avg_test_ms = round(sum_test_ms / test_count, 3) if test_count > 0 else 0.0
    total_ms = round(max(float(timer.duration_ms), sum_suite_ms), 3)
    total_sec = round(total_ms / 1000.0, 6)

    return {
        "level": "framework",
        "started_at": timer.started_at,
        "completed_at": timer.completed_at,
        "suite_count": suite_count,
        "test_count": test_count,
        "total_duration_ms": total_ms,
        "total_duration_seconds": total_sec,
        "wall_clock_duration_ms": round(float(timer.duration_ms), 3),
        "sum_suite_duration_ms": sum_suite_ms,
        "sum_test_duration_ms": sum_test_ms,
        "average_suite_duration_ms": avg_suite_ms,
        "average_test_duration_ms": avg_test_ms,
        "per_suite_timings": [
            {
                "suite_slug": s.get("suite_slug"),
                "suite_name": s.get("suite_name"),
                "test_count": s.get("test_count", 0),
                "total_duration_ms": s.get("total_duration_ms", 0.0),
                "total_duration_seconds": s.get("total_duration_seconds", 0.0),
                "average_test_duration_ms": s.get("average_test_duration_ms", 0.0),
            }
            for s in suite_timings
        ],
        "per_test_timings": all_tests,
    }
