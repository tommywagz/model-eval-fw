"""Rich Terminal Inspector UI and Interactive Manual Calibration Mode for BenchMaxxer."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from benchmaxxer.telemetry.logger import TelemetryLogger


def _build_side_by_side_diff_table(
    baseline_code: str,
    candidate_code: str,
) -> Table:
    """Build a rich side-by-side comparison table for code refactoring/translation."""
    table = Table(
        title="Side-by-Side Code Comparison (Baseline vs. Candidate Completion)",
        expand=True,
        show_lines=False,
    )
    table.add_column("Line", style="dim", width=5, justify="right")
    table.add_column("Baseline / Original Reference", style="yellow", ratio=1)
    table.add_column("Line", style="dim", width=5, justify="right")
    table.add_column("Candidate Model Output", style="green", ratio=1)

    base_lines = (baseline_code or "# No baseline reference code provided").splitlines()
    cand_lines = (candidate_code or "# Empty candidate output").splitlines()

    matcher = difflib.SequenceMatcher(None, base_lines, cand_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        max_span = max(i2 - i1, j2 - j1)
        for offset in range(max_span):
            b_idx = i1 + offset if (i1 + offset) < i2 else None
            c_idx = j1 + offset if (j1 + offset) < j2 else None
            b_text = base_lines[b_idx] if b_idx is not None else ""
            c_text = cand_lines[c_idx] if c_idx is not None else ""

            b_style = "red" if tag in ("delete", "replace") and b_text else "dim"
            c_style = "bright_green" if tag in ("insert", "replace") and c_text else "white"

            table.add_row(
                str(b_idx + 1) if b_idx is not None else "",
                Text(b_text, style=b_style),
                str(c_idx + 1) if c_idx is not None else "",
                Text(c_text, style=c_style),
            )
    return table


def render_run_inspection(
    run_data: Dict[str, Any],
    console: Optional[Console] = None,
) -> str:
    """Render a comprehensive Rich terminal inspection view of a benchmark run."""
    buffer = StringIO()
    out_console = console or Console(file=buffer, force_terminal=True, width=120)

    run_id = run_data.get("run_id", "unknown")
    scenario_id = run_data.get("scenario_id", "unknown")
    model_alias = run_data.get("model_alias", "gemini-1.5-pro")
    difficulty = run_data.get("difficulty", "Hard")
    pillar = run_data.get("pillar", "Agent Skill Creation + Use")
    exec_mode = run_data.get("execution_mode", "mock")
    exit_code = int(run_data.get("exit_code", 0))
    status_badge = "[bold green]PASSED (0)[/bold green]" if exit_code == 0 else f"[bold red]FAILED ({exit_code})[/bold red]"

    # 1. Header & Scenario Metadata Panel
    meta_table = Table.grid(padding=(0, 2))
    meta_table.add_column(style="bold cyan")
    meta_table.add_column(style="white")
    meta_table.add_column(style="bold cyan")
    meta_table.add_column(style="white")

    meta_table.add_row(
        "Run ID:", str(run_id),
        "Scenario ID:", str(scenario_id),
    )
    meta_table.add_row(
        "Candidate Model:", f"[bold magenta]{model_alias}[/bold magenta]",
        "Difficulty Tier:", f"[bold yellow]{difficulty}[/bold yellow]",
    )
    meta_table.add_row(
        "Pillar:", str(pillar),
        "Execution Mode:", f"{exec_mode.upper()} | Status: {status_badge}",
    )
    meta_table.add_row(
        "Latency / Tokens:",
        f"{run_data.get('latency_ms', 0.0)} ms | in={run_data.get('input_tokens', 0)}, out={run_data.get('output_tokens', 0)}",
        "Estimated Cost:",
        f"${float(run_data.get('estimated_cost_usd', 0.0)):.6f} USD",
    )

    out_console.print(
        Panel(
            meta_table,
            title="[bold white]BenchMaxxer Run Inspector[/bold white]",
            subtitle=f"Timestamp: {run_data.get('timestamp', '')}",
            border_style="cyan",
        )
    )

    # 2. Input Prompt & Raw Candidate Completion
    prompt_text = str(run_data.get("prompt", "(Prompt not recorded in trace)"))
    candidate_output = str(run_data.get("candidate_output", "(Candidate completion not recorded)"))

    prompt_panel = Panel(
        Text(prompt_text),
        title="[bold blue]Input Prompt[/bold blue]",
        border_style="blue",
    )
    completion_panel = Panel(
        Syntax(candidate_output, "markdown", theme="monokai", word_wrap=True),
        title=f"[bold green]Raw Model Completion ({model_alias})[/bold green]",
        border_style="green",
    )
    out_console.print(Columns([prompt_panel, completion_panel], equal=True, expand=True))

    # 3. Side-by-Side Terminal Diffs
    baseline_code = str(
        run_data.get("baseline_code")
        or "# Baseline monolithic/unconfigured state\ndef legacy_handler(req):\n    return None"
    )
    out_console.print(_build_side_by_side_diff_table(baseline_code, candidate_output))

    # 4. Automated Test Assertions & Calculated Deterministic Metrics
    metrics_dict = run_data.get("metrics_dict") or {}
    assertions = run_data.get("assertions") or []

    metrics_table = Table(title="Deterministic Metrics & Automated Assertions", expand=True)
    metrics_table.add_column("Metric / Assertion", style="bold white")
    metrics_table.add_column("Value / Verdict", justify="right")
    metrics_table.add_column("Details", style="dim")

    for k, v in metrics_dict.items():
        val_str = f"{v:.2f}%" if isinstance(v, float) else str(v)
        metrics_table.add_row(f"Metric: {k}", f"[bold cyan]{val_str}[/bold cyan]", "RFC Deterministic Formula")

    for item in assertions:
        passed = bool(item.get("passed", True))
        verdict = "[bold green]PASS[/bold green]" if passed else "[bold red]FAIL[/bold red]"
        metrics_table.add_row(
            f"Assertion: {item.get('name', 'check')}",
            verdict,
            str(item.get("detail", "")),
        )
    out_console.print(metrics_table)

    # 5. Actor-Critic Panel Breakdown (Qwen, MiniMax, Kimi K)
    ac_data = run_data.get("actor_critic_scores") or {}
    critics_map = ac_data.get("critics") or {}
    composite_score = ac_data.get("composite_score", 0.0)
    composite_norm = ac_data.get("composite_normalized_score", 0.0)

    ac_table = Table(
        title=(
            f"Actor-Critic Panel Breakdown | Composite Score: {composite_score}/5.0 "
            f"({composite_norm:.1f}%)"
        ),
        expand=True,
        show_lines=True,
    )
    ac_table.add_column("Critic Model", style="bold magenta", width=18)
    ac_table.add_column("Rubric Dimension", style="cyan", width=26)
    ac_table.add_column("Score (1-5)", justify="center", width=12)
    ac_table.add_column("Normalized", justify="right", width=12)
    ac_table.add_column("Qualitative Critique & Remediation", ratio=2)
    ac_table.add_column("Detected Anomalies", style="yellow", ratio=1)

    critic_labels = [
        ("qwen", "Qwen (ArchitecturalCritic)"),
        ("minimax", "MiniMax (TestHarnessCritic)"),
        ("kimi_k", "Kimi K (PlatformComplianceCritic)"),
    ]

    for key, label in critic_labels:
        c_eval = critics_map.get(key)
        if not c_eval:
            continue
        score_val = int(c_eval.get("score", 0))
        norm_val = float(c_eval.get("normalized_score", 0.0))
        score_style = "bold green" if score_val >= 4 else ("bold yellow" if score_val == 3 else "bold red")
        anomalies_list = c_eval.get("detected_anomalies") or []
        anomalies_str = "\n".join(f"• {a}" for a in anomalies_list) if anomalies_list else "None"
        critique_str = str(c_eval.get("qualitative_critique", ""))
        remediation = c_eval.get("remediation_advice")
        if remediation:
            critique_str += f"\n[dim]Advice: {remediation}[/dim]"

        ac_table.add_row(
            label,
            str(c_eval.get("dimension", "")),
            f"[{score_style}]{score_val} / 5[/{score_style}]",
            f"{norm_val:.1f}%",
            critique_str,
            anomalies_str,
        )

    out_console.print(ac_table)

    if console is None:
        rendered = buffer.getvalue()
        print(rendered)
        return rendered
    return ""


def run_manual_calibration(
    run_data: Dict[str, Any],
    reports_dir: Optional[str | Path] = None,
    input_fn: Optional[Callable[[str], str]] = None,
    human_score: Optional[int] = None,
    notes: Optional[str] = None,
    override_score: Optional[bool] = None,
    override_value: Optional[float] = None,
    override_rationale: Optional[str] = None,
) -> Dict[str, Any]:
    """Interactive Calibration & Audit Mode (--manual-eval).

    Prompts the human evaluator for a 1-5 score, reviewer feedback notes, and an
    override toggle, then logs human ratings alongside Actor-Critic scores to
    `reports/manual_evals/<run_id>.json`.
    """
    prompt_reader = input_fn or input
    run_id = str(run_data.get("run_id", "manual-run"))

    if human_score is None:
        try:
            raw_score = prompt_reader("Enter human calibration score (1-5) [default=5]: ").strip()
            human_score = int(raw_score) if raw_score else 5
        except (EOFError, ValueError):
            human_score = 5
    human_score = max(1, min(5, int(human_score)))

    if notes is None:
        try:
            raw_notes = prompt_reader("Enter reviewer feedback notes: ").strip()
            notes = raw_notes or "Manual calibration audit completed; rubric alignment verified."
        except EOFError:
            notes = "Manual calibration audit completed (non-interactive default)."

    if override_score is None:
        try:
            raw_override = prompt_reader("Override automated score? (y/N): ").strip().lower()
            override_score = raw_override in ("y", "yes", "true", "1")
        except EOFError:
            override_score = False

    if override_score and override_rationale is None:
        try:
            override_rationale = (
                prompt_reader("Enter override rationale: ").strip()
                or "Human auditor override applied."
            )
        except EOFError:
            override_rationale = "Human auditor override applied."

    ac_scores = run_data.get("actor_critic_scores") or {}
    panel_composite = float(ac_scores.get("composite_score", 5.0))
    human_normalized = round(float(human_score) * 20.0, 2)
    score_delta = round(abs(float(human_score) - panel_composite), 3)
    inter_rater_agreement = round(max(0.0, 1.0 - (score_delta / 4.0)), 3)
    critic_bias_detected = score_delta >= 1.5

    report_payload: Dict[str, Any] = {
        "run_id": run_id,
        "scenario_id": run_data.get("scenario_id", "unknown"),
        "model_alias": run_data.get("model_alias", "gemini-1.5-pro"),
        "audited_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "human_evaluation": {
            "score": human_score,
            "normalized_score": human_normalized,
            "notes": notes,
            "override_enabled": bool(override_score),
            "override_value": override_value if override_value is not None else (human_normalized if override_score else None),
            "override_rationale": override_rationale,
        },
        "actor_critic_panel": ac_scores,
        "inter_rater_reliability": {
            "human_score": human_score,
            "panel_composite_score": panel_composite,
            "absolute_score_delta": score_delta,
            "agreement_index": inter_rater_agreement,
            "critic_bias_detected": critic_bias_detected,
        },
    }

    target_dir = Path(reports_dir) if reports_dir else Path("reports/manual_evals")
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / f"{run_id}.json"
    report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
    report_payload["report_path"] = str(report_path)
    return report_payload


def main(argv: Optional[List[str]] = None) -> int:
    """CLI Entrypoint for `python3 -m benchmaxxer.ui.inspector`."""
    parser = argparse.ArgumentParser(
        description="BenchMaxxer Rich Terminal Inspector & Manual Calibration Tool"
    )
    parser.add_argument("--run-id", type=str, default=None, help="Specific run_id to inspect")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Inspect the most recently logged benchmark run",
    )
    parser.add_argument(
        "--telemetry-dir",
        type=str,
        default=None,
        help="Optional custom telemetry directory path",
    )
    parser.add_argument(
        "--manual-eval",
        action="store_true",
        help="Launch interactive calibration & manual audit prompt after inspection",
    )
    args = parser.parse_args(argv)

    logger = TelemetryLogger(base_dir=args.telemetry_dir)
    if args.run_id:
        run_data = logger.get_run(args.run_id)
    else:
        run_data = logger.get_latest_run()

    if not run_data:
        Console().print(
            "[bold red]No benchmark telemetry runs found. Execute `test_runner.py` first.[/bold red]"
        )
        return 1

    render_run_inspection(run_data)

    if args.manual_eval:
        report = run_manual_calibration(run_data)
        Console().print(
            f"[bold green]Saved manual evaluation calibration report to: {report['report_path']}[/bold green]"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
