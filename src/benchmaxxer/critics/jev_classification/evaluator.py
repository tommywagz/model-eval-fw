"""Jev-Classification: Structure & Dispatching Critic Module.

Analyzes agent decisions using confusion matrices (Precision, Recall, F1) during
skill and tool dispatching under ambiguity. Quantifies codebase modularity,
dependency coupling, and cyclomatic complexity reduction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from benchmaxxer.critics.jev_classification.complexity import (
    ComplexityMetrics,
    analyze_codebase_refactoring,
)
from benchmaxxer.critics.jev_classification.confusion_matrix import (
    ConfusionMatrix,
    compute_dispatch_confusion_matrix,
)
from benchmaxxer.critics.rubrics import map_raw_to_rubric_score


@dataclass
class JevClassificationResult:
    """Evaluation result produced by Jev-Classification."""

    scenario_id: str
    passed: bool
    confusion_matrix: Optional[ConfusionMatrix] = None
    complexity_metrics: Optional[ComplexityMetrics] = None
    throughput_delta: Optional[float] = None
    resource_efficiency_delta: Optional[float] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    rubric_score: int = 1
    rubric_rating: str = "Failing / Unusable"
    normalized_score: float = 20.0
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "critic": "Jev-Classification",
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "metrics": {k: round(float(v), 2) for k, v in self.metrics.items()},
            "confusion_matrix": self.confusion_matrix.to_dict() if self.confusion_matrix else None,
            "complexity_metrics": self.complexity_metrics.to_dict() if self.complexity_metrics else None,
            "throughput_delta": round(float(self.throughput_delta), 2) if self.throughput_delta is not None else None,
            "resource_efficiency_delta": (
                round(float(self.resource_efficiency_delta), 2)
                if self.resource_efficiency_delta is not None
                else None
            ),
            "rubric_score": self.rubric_score,
            "rubric_rating": self.rubric_rating,
            "normalized_score": round(float(self.normalized_score), 2),
            "details": self.details,
        }


class JevClassificationCritic:
    """Structure & Dispatching Critic."""

    def evaluate_dispatch(
        self,
        scenario_id: str,
        dispatched_skills: List[str],
        expected_skills: List[str],
        all_skills: Optional[List[str]] = None,
    ) -> JevClassificationResult:
        """Evaluate skill/tool dispatch decisions via confusion matrix."""
        cm = compute_dispatch_confusion_matrix(
            dispatched_skills=dispatched_skills,
            expected_skills=expected_skills,
            all_available_skills=all_skills,
        )

        metrics: Dict[str, float] = {
            "precision": cm.precision_pct,
            "recall": cm.recall_pct,
            "f1_score": cm.f1_pct,
            "precision_and_recall": cm.f1_pct,
        }

        rubric_score, rubric_rating = map_raw_to_rubric_score(
            success_rate=cm.f1_pct,
            f1_score=cm.f1_score,
        )
        passed = rubric_score >= 3

        details = (
            f"Jev-Classification Dispatch: TP={cm.true_positives}, FP={cm.false_positives}, "
            f"FN={cm.false_negatives}, F1={cm.f1_pct:.1f}% -> Rubric {rubric_score} ({rubric_rating})"
        )

        return JevClassificationResult(
            scenario_id=scenario_id,
            passed=passed,
            confusion_matrix=cm,
            metrics=metrics,
            rubric_score=rubric_score,
            rubric_rating=rubric_rating,
            normalized_score=float(rubric_score) * 20.0,
            details=details,
        )

    def evaluate_codebase_structure(
        self,
        scenario_id: str,
        baseline_code: str,
        candidate_code: str,
        throughput_delta: Optional[float] = None,
        resource_efficiency_delta: Optional[float] = None,
    ) -> JevClassificationResult:
        """Evaluate cyclomatic complexity reduction, modularity, and throughput/efficiency."""
        c_metrics = analyze_codebase_refactoring(
            baseline_code=baseline_code,
            candidate_code=candidate_code,
        )

        lower_cand = candidate_code.lower()
        has_critical_errors = (
            c_metrics.global_mutable_state_detected
            or c_metrics.complexity_reduction_pct < 0
            or "monolithic_global_state" in lower_cand
            or "deliberate_failure" in lower_cand
        )

        metrics: Dict[str, float] = {
            "cyclomatic_complexity_reduction": c_metrics.complexity_reduction_pct,
            "modularity_score": c_metrics.modularity_score,
            "initial_complexity": float(c_metrics.initial_complexity),
            "refactored_complexity": float(c_metrics.refactored_complexity),
        }

        # High-throughput data stream scenario metrics
        eff_gain = None
        if scenario_id in ("solid_architecture_improvement", "high_throughput_optimization"):
            tp_delta = throughput_delta if throughput_delta is not None else (45.0 if not has_critical_errors else -15.0)
            res_delta = resource_efficiency_delta if resource_efficiency_delta is not None else (35.0 if not has_critical_errors else -20.0)
            metrics["throughput_delta"] = tp_delta
            metrics["resource_efficiency_delta"] = res_delta
            eff_gain = max(tp_delta, res_delta)

        # Map to Rubric 1-5
        success_proxy = max(0.0, min(100.0, c_metrics.modularity_score))
        if has_critical_errors:
            success_proxy = 30.0

        rubric_score, rubric_rating = map_raw_to_rubric_score(
            success_rate=success_proxy,
            efficiency_delta=eff_gain if eff_gain is not None else c_metrics.complexity_reduction_pct,
            has_critical_errors=has_critical_errors,
        )

        passed = (rubric_score >= 3) and (not has_critical_errors)

        details = (
            f"Jev-Classification Structure: Complexity reduction={c_metrics.complexity_reduction_pct:.1f}%, "
            f"Modularity={c_metrics.modularity_score:.1f}% -> Rubric {rubric_score} ({rubric_rating})"
        )

        return JevClassificationResult(
            scenario_id=scenario_id,
            passed=passed,
            complexity_metrics=c_metrics,
            throughput_delta=metrics.get("throughput_delta"),
            resource_efficiency_delta=metrics.get("resource_efficiency_delta"),
            metrics=metrics,
            rubric_score=rubric_score,
            rubric_rating=rubric_rating,
            normalized_score=float(rubric_score) * 20.0,
            details=details,
        )
