"""Structured run logging to SQLite (runs.db), JSONL (runs.jsonl, suite_runs.jsonl, framework_runs.jsonl), and trace files."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunRecord:
    """Canonical data structure representing a single BenchMaxxer evaluation run."""

    run_id: str
    timestamp: str
    model_alias: str
    scenario_id: str
    execution_mode: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    metrics_dict: Dict[str, Any]
    actor_critic_scores: Dict[str, Any]
    exit_code: int
    trace_path: str
    # Extended fields persisted in trace file for rich inspection
    difficulty: str = "Medium"
    pillar: str = "Agent Skill Creation + Use"
    suite_slug: str = "agent_skill_creation"
    prompt: str = ""
    system_instruction: str = ""
    candidate_output: str = ""
    baseline_code: str = ""
    assertions: List[Dict[str, Any]] = field(default_factory=list)
    cached: bool = False
    replayed: bool = False
    duration_ms: float = 0.0
    duration_seconds: float = 0.0
    total_tokens: int = 0
    timing: Dict[str, Any] = field(default_factory=dict)
    token_usage: Dict[str, Any] = field(default_factory=dict)

    def to_db_dict(self) -> Dict[str, Any]:
        """Return the core telemetry dictionary for JSONL and SQLite storage."""
        eff_dur_ms = float(self.duration_ms) if self.duration_ms > 0 else float(self.latency_ms)
        eff_dur_sec = float(self.duration_seconds) if self.duration_seconds > 0 else round(eff_dur_ms / 1000.0, 6)
        eff_total_tok = int(self.total_tokens) if self.total_tokens > 0 else int(self.input_tokens) + int(self.output_tokens)
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "model_alias": self.model_alias,
            "scenario_id": self.scenario_id,
            "suite_slug": self.suite_slug,
            "pillar": self.pillar,
            "execution_mode": self.execution_mode,
            "latency_ms": round(float(self.latency_ms), 3),
            "duration_ms": round(eff_dur_ms, 3),
            "duration_seconds": round(eff_dur_sec, 6),
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "total_tokens": eff_total_tok,
            "estimated_cost_usd": round(float(self.estimated_cost_usd), 6),
            "timing": self.timing,
            "token_usage": self.token_usage,
            "metrics_dict": self.metrics_dict,
            "actor_critic_scores": self.actor_critic_scores,
            "exit_code": int(self.exit_code),
            "trace_path": self.trace_path,
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """Return full run payload including trace details for inspector UI."""
        data = asdict(self)
        eff_dur_ms = float(self.duration_ms) if self.duration_ms > 0 else float(self.latency_ms)
        eff_dur_sec = float(self.duration_seconds) if self.duration_seconds > 0 else round(eff_dur_ms / 1000.0, 6)
        eff_total_tok = int(self.total_tokens) if self.total_tokens > 0 else int(self.input_tokens) + int(self.output_tokens)
        data["latency_ms"] = round(float(self.latency_ms), 3)
        data["duration_ms"] = round(eff_dur_ms, 3)
        data["duration_seconds"] = round(eff_dur_sec, 6)
        data["total_tokens"] = eff_total_tok
        data["estimated_cost_usd"] = round(float(self.estimated_cost_usd), 6)
        return data


class TelemetryLogger:
    """Manages SQLite (`runs.db`), JSONL (`runs.jsonl`, `suite_runs.jsonl`, `framework_runs.jsonl`), and trace JSON persistence."""

    def __init__(self, base_dir: Optional[str | Path] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path("artifacts/telemetry")
        self.db_path = self.base_dir / "runs.db"
        self.jsonl_path = self.base_dir / "runs.jsonl"
        self.suite_jsonl_path = self.base_dir / "suite_runs.jsonl"
        self.framework_jsonl_path = self.base_dir / "framework_runs.jsonl"
        self.traces_dir = self.base_dir / "traces"
        self._init_storage()

    def _init_storage(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    model_alias TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    metrics_dict TEXT NOT NULL,
                    actor_critic_scores TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    trace_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS suite_runs (
                    suite_run_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    suite_slug TEXT NOT NULL,
                    suite_name TEXT NOT NULL,
                    model_alias TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    test_count INTEGER NOT NULL,
                    passed_count INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    duration_seconds REAL NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    total_estimated_cost_usd REAL NOT NULL,
                    timing_json TEXT NOT NULL,
                    token_usage_json TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    trace_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS framework_runs (
                    framework_run_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    model_alias TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    suite_count INTEGER NOT NULL,
                    test_count INTEGER NOT NULL,
                    passed_count INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    duration_seconds REAL NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    total_estimated_cost_usd REAL NOT NULL,
                    timing_json TEXT NOT NULL,
                    token_usage_json TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    trace_path TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def generate_run_id(scenario_id: str = "run") -> str:
        short_uuid = uuid.uuid4().hex[:8]
        ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        return f"{scenario_id}-{ts}-{short_uuid}"

    def log_run(self, record: RunRecord) -> RunRecord:
        """Persist a RunRecord to trace file, SQLite database, and JSONL log."""
        self._init_storage()

        if not record.trace_path:
            trace_file = self.traces_dir / f"{record.run_id}.json"
            record.trace_path = str(trace_file)
        else:
            trace_file = Path(record.trace_path)
            trace_file.parent.mkdir(parents=True, exist_ok=True)

        # 1. Save full trace JSON
        trace_file.write_text(
            json.dumps(record.to_full_dict(), indent=2),
            encoding="utf-8",
        )

        # 2. Save to SQLite database (artifacts/telemetry/runs.db)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id,
                    timestamp,
                    model_alias,
                    scenario_id,
                    execution_mode,
                    latency_ms,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    metrics_dict,
                    actor_critic_scores,
                    exit_code,
                    trace_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.timestamp,
                    record.model_alias,
                    record.scenario_id,
                    record.execution_mode,
                    float(record.latency_ms),
                    int(record.input_tokens),
                    int(record.output_tokens),
                    float(record.estimated_cost_usd),
                    json.dumps(record.metrics_dict),
                    json.dumps(record.actor_critic_scores),
                    int(record.exit_code),
                    record.trace_path,
                ),
            )
            conn.commit()

        # 3. Append to JSONL (artifacts/telemetry/runs.jsonl)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_db_dict()) + "\n")

        return record

    def log_suite_run(self, suite_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a suite-level execution record with timing and token cost telemetry."""
        self._init_storage()
        suite_run_id = str(suite_payload.get("suite_run_id") or self.generate_run_id(f"suite-{suite_payload.get('suite_slug', 'suite')}"))
        suite_payload["suite_run_id"] = suite_run_id
        trace_file = self.traces_dir / f"{suite_run_id}.json"
        suite_payload["trace_path"] = str(trace_file)

        trace_file.write_text(json.dumps(suite_payload, indent=2), encoding="utf-8")

        timing = suite_payload.get("timing", {})
        token_usage = suite_payload.get("token_usage", {})
        dur_ms = float(suite_payload.get("duration_ms", timing.get("total_duration_ms", 0.0)))
        dur_sec = float(suite_payload.get("duration_seconds", timing.get("total_duration_seconds", 0.0)))
        tot_tok = int(suite_payload.get("total_tokens", token_usage.get("total_tokens", 0)))
        tot_cost = float(suite_payload.get("estimated_cost_usd", token_usage.get("total_estimated_cost_usd", 0.0)))

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO suite_runs (
                    suite_run_id,
                    timestamp,
                    suite_slug,
                    suite_name,
                    model_alias,
                    execution_mode,
                    test_count,
                    passed_count,
                    duration_ms,
                    duration_seconds,
                    total_tokens,
                    total_estimated_cost_usd,
                    timing_json,
                    token_usage_json,
                    exit_code,
                    trace_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suite_run_id,
                    str(suite_payload.get("timestamp", "")),
                    str(suite_payload.get("suite_slug", "")),
                    str(suite_payload.get("suite_name", "")),
                    str(suite_payload.get("model_alias", "gemini-1.5-pro")),
                    str(suite_payload.get("execution_mode", "mock")),
                    int(suite_payload.get("test_count", 0)),
                    int(suite_payload.get("passed_count", 0)),
                    dur_ms,
                    dur_sec,
                    tot_tok,
                    tot_cost,
                    json.dumps(timing),
                    json.dumps(token_usage),
                    int(suite_payload.get("exit_code", 0)),
                    str(trace_file),
                ),
            )
            conn.commit()

        with self.suite_jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(suite_payload) + "\n")

        return suite_payload

    def log_framework_run(self, framework_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a framework-level execution record with timing and token cost telemetry."""
        self._init_storage()
        fw_run_id = str(framework_payload.get("framework_run_id") or self.generate_run_id("framework"))
        framework_payload["framework_run_id"] = fw_run_id
        trace_file = self.traces_dir / f"{fw_run_id}.json"
        framework_payload["trace_path"] = str(trace_file)

        trace_file.write_text(json.dumps(framework_payload, indent=2), encoding="utf-8")

        timing = framework_payload.get("timing", {})
        token_usage = framework_payload.get("token_usage", {})
        dur_ms = float(framework_payload.get("duration_ms", timing.get("total_duration_ms", 0.0)))
        dur_sec = float(framework_payload.get("duration_seconds", timing.get("total_duration_seconds", 0.0)))
        tot_tok = int(framework_payload.get("total_tokens", token_usage.get("total_tokens", 0)))
        tot_cost = float(framework_payload.get("estimated_cost_usd", token_usage.get("total_estimated_cost_usd", 0.0)))

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO framework_runs (
                    framework_run_id,
                    timestamp,
                    model_alias,
                    execution_mode,
                    suite_count,
                    test_count,
                    passed_count,
                    duration_ms,
                    duration_seconds,
                    total_tokens,
                    total_estimated_cost_usd,
                    timing_json,
                    token_usage_json,
                    exit_code,
                    trace_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fw_run_id,
                    str(framework_payload.get("timestamp", "")),
                    str(framework_payload.get("model_alias", "gemini-1.5-pro")),
                    str(framework_payload.get("execution_mode", "mock")),
                    int(framework_payload.get("suite_count", 0)),
                    int(framework_payload.get("test_count", 0)),
                    int(framework_payload.get("passed_count", 0)),
                    dur_ms,
                    dur_sec,
                    tot_tok,
                    tot_cost,
                    json.dumps(timing),
                    json.dumps(token_usage),
                    int(framework_payload.get("exit_code", 0)),
                    str(trace_file),
                ),
            )
            conn.commit()

        with self.framework_jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(framework_payload) + "\n")

        return framework_payload

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        for json_col in ("metrics_dict", "actor_critic_scores"):
            if isinstance(item.get(json_col), str):
                try:
                    item[json_col] = json.loads(item[json_col])
                except json.JSONDecodeError:
                    item[json_col] = {}
        trace_path = item.get("trace_path")
        if trace_path and Path(trace_path).exists():
            try:
                trace_data = json.loads(Path(trace_path).read_text(encoding="utf-8"))
                # Merge extended trace fields while preserving canonical DB values
                trace_data.update(item)
                return trace_data
            except (json.JSONDecodeError, OSError):
                pass
        return item

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific run by run_id from SQLite / trace storage."""
        if not self.db_path.exists():
            return None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def get_latest_run(self) -> Optional[Dict[str, Any]]:
        """Retrieve the most recently logged run."""
        if not self.db_path.exists():
            return None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM runs ORDER BY rowid DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent benchmark runs ordered most recent first."""
        if not self.db_path.exists():
            return []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM runs ORDER BY rowid DESC LIMIT ?", (limit,)
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
