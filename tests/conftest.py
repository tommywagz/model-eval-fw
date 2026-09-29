"""Pytest session hooks for individual test, suite (module), and framework (session) timing telemetry."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest


class _PytestHierarchyTimerPlugin:
    """Tracks per-test, per-suite (module), and framework-wide execution times during pytest runs."""

    def __init__(self) -> None:
        self.session_start_perf: float = 0.0
        self.session_started_at: str = ""
        self.test_starts: Dict[str, float] = {}
        self.test_timings: List[Dict[str, Any]] = []

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        self.session_started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.session_start_perf = time.perf_counter()

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        self.test_starts[item.nodeid] = time.perf_counter()

    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]) -> None:
        if call.when != "call":
            return
        start = self.test_starts.get(item.nodeid, call.start)
        duration_sec = max(0.0, time.perf_counter() - start)
        duration_ms = round(duration_sec * 1000.0, 3)
        suite_name = item.nodeid.split("::")[0]
        test_name = item.nodeid.split("::")[-1]
        self.test_timings.append(
            {
                "nodeid": item.nodeid,
                "suite": suite_name,
                "test": test_name,
                "passed": call.excinfo is None,
                "duration_ms": duration_ms,
                "duration_seconds": round(duration_sec, 6),
            }
        )

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        total_sec = max(0.0, time.perf_counter() - self.session_start_perf)
        total_ms = round(total_sec * 1000.0, 3)
        completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        suites_map: Dict[str, List[Dict[str, Any]]] = {}
        for t in self.test_timings:
            suites_map.setdefault(t["suite"], []).append(t)

        suite_summaries: List[Dict[str, Any]] = []
        for s_name, items in suites_map.items():
            s_ms = round(sum(float(i["duration_ms"]) for i in items), 3)
            suite_summaries.append(
                {
                    "suite": s_name,
                    "test_count": len(items),
                    "total_duration_ms": s_ms,
                    "total_duration_seconds": round(s_ms / 1000.0, 6),
                    "average_test_duration_ms": round(s_ms / max(1, len(items)), 3),
                    "tests": items,
                }
            )

        payload = {
            "framework_level": {
                "started_at": self.session_started_at,
                "completed_at": completed_at,
                "suite_count": len(suite_summaries),
                "test_count": len(self.test_timings),
                "total_duration_ms": total_ms,
                "total_duration_seconds": round(total_sec, 6),
                "sum_test_duration_ms": round(sum(float(t["duration_ms"]) for t in self.test_timings), 3),
            },
            "suite_level": suite_summaries,
            "test_level": self.test_timings,
        }

        try:
            out_dir = Path(__file__).resolve().parent.parent / "artifacts" / "telemetry"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "pytest_timing_summary.json").write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass


def pytest_configure(config: pytest.Config) -> None:
    if not config.pluginmanager.has_plugin("benchmaxxer_hierarchy_timer"):
        config.pluginmanager.register(_PytestHierarchyTimerPlugin(), "benchmaxxer_hierarchy_timer")
