"""Backlog manager for BenchMaxxer Orchestrator.

Ingests SCENARIOS.MD to generate canonical job manifests, populates jobs/pending,
and produces jobs/BACKLOG.md with comprehensive guidance for the Test Creator agent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from benchmaxxer.orchestrator.parser import ParsedScenario, parse_scenarios_markdown


class BacklogManager:
    """Manages the lifecycle of jobs, manifests, and backlog generation from SCENARIOS.MD."""

    def __init__(
        self,
        jobs_dir: Optional[str | Path] = None,
        scenarios_file: Optional[str | Path] = None,
    ) -> None:
        self.jobs_dir = Path(jobs_dir) if jobs_dir else Path("jobs")
        self.scenarios_file = Path(scenarios_file) if scenarios_file else Path("SCENARIOS.MD")

        self.manifests_dir = self.jobs_dir / "manifests"
        self.pending_dir = self.jobs_dir / "pending"
        self.active_creator_dir = self.jobs_dir / "active" / "creator"
        self.active_test_creator_dir = self.jobs_dir / "active" / "test_creator"
        self.active_tester_dir = self.jobs_dir / "active" / "tester"
        self.active_test_tester_dir = self.jobs_dir / "active" / "test_tester"
        self.verification_queue_dir = self.jobs_dir / "verification_queue"
        self.completed_dir = self.jobs_dir / "completed"
        self.failed_dir = self.jobs_dir / "failed"

    def ensure_directories(self) -> None:
        """Create the required jobs/ hierarchy."""
        for d in (
            self.manifests_dir,
            self.pending_dir,
            self.active_creator_dir,
            self.active_test_creator_dir,
            self.active_tester_dir,
            self.active_test_tester_dir,
            self.verification_queue_dir,
            self.completed_dir,
            self.failed_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def populate_backlog_from_scenarios(self) -> List[Dict[str, Any]]:
        """Parse SCENARIOS.MD, write canonical manifests to jobs/manifests/,
        create symlinks in jobs/pending/, and generate jobs/BACKLOG.md.
        """
        self.ensure_directories()
        scenarios: List[ParsedScenario] = parse_scenarios_markdown(self.scenarios_file)
        manifest_dicts: List[Dict[str, Any]] = []

        for sc in scenarios:
            m_dict = sc.to_manifest_dict()
            m_dict["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            manifest_path = self.manifests_dir / f"{sc.job_id}.json"
            manifest_path.write_text(json.dumps(m_dict, indent=2), encoding="utf-8")
            manifest_dicts.append(m_dict)

            # Create atomic symlink in jobs/pending/
            pending_link = self.pending_dir / f"{sc.job_id}.json"
            if pending_link.is_symlink() or pending_link.exists():
                pending_link.unlink()
            try:
                # Relative link from jobs/pending/ to ../manifests/<job_id>.json
                pending_link.symlink_to(Path("..") / "manifests" / f"{sc.job_id}.json")
            except OSError:
                # Fallback to copy if symlinks are restricted
                pending_link.write_text(json.dumps(m_dict, indent=2), encoding="utf-8")

        # Generate jobs/BACKLOG.md with complete details for Creator and Tester agents
        self._write_backlog_markdown(scenarios)
        # Generate jobs/backlog.json
        (self.jobs_dir / "backlog.json").write_text(
            json.dumps(
                {
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "scenarios_source": str(self.scenarios_file),
                    "total_scenarios": len(manifest_dicts),
                    "scenarios": manifest_dicts,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return manifest_dicts

    def _write_backlog_markdown(self, scenarios: List[ParsedScenario]) -> None:
        lines: List[str] = [
            "# BenchMaxxer Orchestrator Scenario Backlog",
            "",
            f"> Auto-generated from [`{self.scenarios_file.name}`]({self.scenarios_file.name}) at {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())}.",
            "> This backlog provides the Test Creator and Test Tester agents with comprehensive scenario requirements, features under test, and evaluation guidance.",
            "",
            "## Summary Table",
            "",
            "| # | Job ID | Suite / Pillar | Scenario Name | Difficulty | Target Metric(s) |",
            "|---|---|---|---|---|---|",
        ]

        for s in scenarios:
            metrics_display = "<br>".join(
                f"**{m['name']}**: `{m['formula']}`" for m in s.target_metrics
            ) or s.raw_metrics
            lines.append(
                f"| {s.sequence_number} | `{s.job_id}` | {s.suite} | {s.test_name} | **{s.difficulty}** | {metrics_display} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Detailed Scenario Specifications for Test Creator")
        lines.append("")

        for s in scenarios:
            lines.extend(
                [
                    f"### {s.sequence_number}. {s.test_name} (`{s.job_id}`)",
                    "",
                    f"- **Pillar / Suite**: {s.suite} (`{s.pillar_slug}`)",
                    f"- **Difficulty Tier**: {s.difficulty}",
                    f"- **Scenario Slug**: `{s.scenario_slug}`",
                    f"- **Target Directory**: `tests/suites/{s.pillar_slug}/{s.scenario_slug}/`",
                    "",
                    "#### Scenario Description",
                    f"> {s.scenario_description}",
                    "",
                    "#### Features Under Test",
                ]
            )
            for f in s.features_under_test:
                lines.append(f"- {f}")

            lines.extend(
                [
                    "",
                    "#### Target Evaluation Metrics",
                ]
            )
            for m in s.target_metrics:
                lines.append(f"- **{m['name']}** ({m.get('unit', '%')}): `{m.get('formula', '')}`")

            guidance = s.creator_guidance
            if guidance:
                lines.extend(
                    [
                        "",
                        "#### Test Creator Harness Guidance",
                        f"- **Required Mocks / Fixtures**: `{', '.join(guidance.get('required_mocks', []))}`",
                        f"- **Positive Fixture Expectation**: {guidance.get('positive_fixture_expectation', '')}",
                        f"- **Negative Fixture Expectation**: {guidance.get('negative_fixture_expectation', '')}",
                        f"- **Scoring Rule**: {guidance.get('scoring_rule', '')}",
                    ]
                )
            lines.append("")

        (self.jobs_dir / "BACKLOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def dispatch_next_job(
        self,
        worker_dir_name: str = "test_creator",
    ) -> Optional[Dict[str, Any]]:
        """Atomically dispatch the next pending manifest to the active worker directory."""
        self.ensure_directories()
        pending_files = sorted(self.pending_dir.glob("*.json"))
        if not pending_files:
            return None

        next_job_link = pending_files[0]
        job_id = next_job_link.stem

        # Support both 'test_creator' and 'creator' directory paths
        worker_dirs = [
            self.jobs_dir / "active" / worker_dir_name,
        ]
        if worker_dir_name == "test_creator":
            worker_dirs.append(self.jobs_dir / "active" / "creator")
        elif worker_dir_name == "test_tester":
            worker_dirs.append(self.jobs_dir / "active" / "tester")

        manifest_file = self.manifests_dir / f"{job_id}.json"
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest_data["status"] = f"active_{worker_dir_name}"
        manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        for wdir in worker_dirs:
            wdir.mkdir(parents=True, exist_ok=True)
            active_link = wdir / "current_job.json"
            if active_link.is_symlink() or active_link.exists():
                active_link.unlink()
            try:
                active_link.symlink_to(Path("..") / ".." / "manifests" / f"{job_id}.json")
            except OSError:
                active_link.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

        # Remove from pending
        next_job_link.unlink()
        return manifest_data


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="BenchMaxxer Orchestrator: Ingest SCENARIOS.MD to build and manage job backlog."
    )
    parser.add_argument(
        "--init",
        action="store_true",
        default=True,
        help="Parse SCENARIOS.MD and generate canonical job manifests and backlog",
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        default="SCENARIOS.MD",
        help="Path to SCENARIOS.MD (default: SCENARIOS.MD)",
    )
    parser.add_argument(
        "--jobs-dir",
        type=str,
        default="jobs",
        help="Path to jobs coordination directory (default: jobs)",
    )
    parser.add_argument(
        "--dispatch-next",
        action="store_true",
        help="Dispatch the next pending job to jobs/active/test_creator/current_job.json",
    )

    args = parser.parse_args(argv)
    manager = BacklogManager(jobs_dir=args.jobs_dir, scenarios_file=args.scenarios)

    if args.init:
        manifests = manager.populate_backlog_from_scenarios()
        print(
            f"[ORCHESTRATOR] Successfully parsed {len(manifests)} scenarios from {args.scenarios}."
        )
        print(f"[ORCHESTRATOR] Generated manifests in: {manager.manifests_dir}")
        print(f"[ORCHESTRATOR] Generated backlog documentation in: {manager.jobs_dir / 'BACKLOG.md'}")
        print(f"[ORCHESTRATOR] Populated pending queue in: {manager.pending_dir}")

    if args.dispatch_next:
        dispatched = manager.dispatch_next_job("test_creator")
        if dispatched:
            print(f"[ORCHESTRATOR] Dispatched job '{dispatched['job_id']}' to Test Creator.")
        else:
            print("[ORCHESTRATOR] No pending jobs to dispatch.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
