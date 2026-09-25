"""Structured run logging to SQLite (runs.db), JSONL (runs.jsonl), and trace files."""

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
    prompt: str = ""
    system_instruction: str = ""
    candidate_output: str = ""
    baseline_code: str = ""
    assertions: List[Dict[str, Any]] = field(default_factory=list)
    cached: bool = False
    replayed: bool = False

    def to_db_dict(self) -> Dict[str, Any]:
        """Return the core telemetry dictionary for JSONL and SQLite storage."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "model_alias": self.model_alias,
            "scenario_id": self.scenario_id,
            "execution_mode": self.execution_mode,
            "latency_ms": round(float(self.latency_ms), 3),
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "estimated_cost_usd": round(float(self.estimated_cost_usd), 6),
            "metrics_dict": self.metrics_dict,
            "actor_critic_scores": self.actor_critic_scores,
            "exit_code": int(self.exit_code),
            "trace_path": self.trace_path,
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """Return full run payload including trace details for inspector UI."""
        data = asdict(self)
        data["latency_ms"] = round(float(self.latency_ms), 3)
        data["estimated_cost_usd"] = round(float(self.estimated_cost_usd), 6)
        return data


class TelemetryLogger:
    """Manages SQLite (`runs.db`), JSONL (`runs.jsonl`), and trace JSON persistence."""

    def __init__(self, base_dir: Optional[str | Path] = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path("artifacts/telemetry")
        self.db_path = self.base_dir / "runs.db"
        self.jsonl_path = self.base_dir / "runs.jsonl"
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
