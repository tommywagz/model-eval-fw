"""Confusion Matrix and Dispatch Accuracy Analysis for Jev-Classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Set


@dataclass
class ConfusionMatrix:
    """Confusion matrix metrics for skill and tool dispatching."""

    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    f1_score: float
    precision_pct: float
    recall_pct: float
    f1_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "true_negatives": self.true_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "precision_pct": round(self.precision_pct, 2),
            "recall_pct": round(self.recall_pct, 2),
            "f1_pct": round(self.f1_pct, 2),
        }


def compute_dispatch_confusion_matrix(
    dispatched_skills: Iterable[str],
    expected_skills: Iterable[str],
    all_available_skills: Optional[Iterable[str]] = None,
) -> ConfusionMatrix:
    """Calculate confusion matrix (TP, FP, FN, TN) and F1 for skill/tool dispatch."""
    dispatched: Set[str] = {s.strip().lower() for s in dispatched_skills if s and s.strip()}
    expected: Set[str] = {s.strip().lower() for s in expected_skills if s and s.strip()}

    tp = len(dispatched & expected)
    fp = len(dispatched - expected)
    fn = len(expected - dispatched)

    if all_available_skills is not None:
        all_skills: Set[str] = {s.strip().lower() for s in all_available_skills}
        tn = len(all_skills - (dispatched | expected))
    else:
        # Default TN based on evaluated pool
        tn = max(0, 10 - (tp + fp + fn))

    precision = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if not expected and not dispatched else 0.0)
    recall = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if not expected and not dispatched else 0.0)
    if (precision + recall) > 0:
        f1 = (2.0 * precision * recall) / (precision + recall)
    else:
        f1 = 0.0

    return ConfusionMatrix(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=precision,
        recall=recall,
        f1_score=f1,
        precision_pct=precision * 100.0,
        recall_pct=recall * 100.0,
        f1_pct=f1 * 100.0,
    )
