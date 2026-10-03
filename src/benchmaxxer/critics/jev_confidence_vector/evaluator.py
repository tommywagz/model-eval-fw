"""Jev-Confidence Vector: Compliance & Grounding Critic Module.

Validates API flags, IAM permission boundaries, and parameter schemas against
official GCP and ADK specifications. Scores factual grounding and actor-critic
consistency for multi-step agent skills.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from benchmaxxer.critics.jev_confidence_vector.compliance import (
    ComplianceCheckReport,
    check_gcp_and_adk_compliance,
    validate_skill_md_schema,
)
from benchmaxxer.critics.rubrics import map_raw_to_rubric_score


@dataclass
class JevConfidenceVectorResult:
    """Evaluation result produced by Jev-Confidence Vector."""

    scenario_id: str
    passed: bool
    confidence_vector: Dict[str, float]
    compliance_report: ComplianceCheckReport
    metrics: Dict[str, float] = field(default_factory=dict)
    rubric_score: int = 1
    rubric_rating: str = "Failing / Unusable"
    normalized_score: float = 20.0
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "critic": "Jev-Confidence Vector",
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "confidence_vector": {k: round(float(v), 2) for k, v in self.confidence_vector.items()},
            "compliance_report": self.compliance_report.to_dict(),
            "metrics": {k: round(float(v), 2) for k, v in self.metrics.items()},
            "rubric_score": self.rubric_score,
            "rubric_rating": self.rubric_rating,
            "normalized_score": round(float(self.normalized_score), 2),
            "details": self.details,
        }


class JevConfidenceVectorCritic:
    """Compliance & Parameter Grounding Critic."""

    def evaluate_compliance(
        self,
        scenario_id: str,
        candidate_output: str,
        gcp_profiles_path: Optional[str | Path] = None,
        actor_critic_score: Optional[float] = None,
    ) -> JevConfidenceVectorResult:
        """Validate GCP API/IAM compliance, parameter schemas, and grounding consistency."""
        report = check_gcp_and_adk_compliance(
            candidate_output=candidate_output,
            gcp_profiles_path=gcp_profiles_path,
        )

        # Dimension vector components
        iam_score = 100.0 if report.iam_boundary_valid else 20.0
        api_score = 100.0 if report.api_flags_valid else 20.0
        schema_score = 100.0 if report.schema_valid else 40.0

        # Skill.md specific schema validation for skill_scaffolding scenario
        if scenario_id == "skill_scaffolding" or "skill.md" in candidate_output.lower():
            sk_valid, sk_violations = validate_skill_md_schema(candidate_output)
            if not sk_valid:
                schema_score = min(schema_score, 45.0)
                report.violations.extend(sk_violations)

        grounding_score = actor_critic_score if actor_critic_score is not None else report.compliance_score

        confidence_vector: Dict[str, float] = {
            "iam_boundary": iam_score,
            "api_compliance": api_score,
            "schema_adherence": schema_score,
            "factual_grounding": grounding_score,
        }

        # Composite vector average
        vector_avg = sum(confidence_vector.values()) / len(confidence_vector)

        metrics: Dict[str, float] = {
            "platform_compliance_score": report.compliance_score,
            "confidence_vector_mean": vector_avg,
        }

        if scenario_id == "skill_scaffolding":
            metrics["scaffolding_success_rate"] = vector_avg
        elif scenario_id == "complex_skill_synthesis":
            metrics["actor_critic_quality_score"] = vector_avg

        has_critical = (not report.iam_boundary_valid) or (not report.api_flags_valid)
        has_minor_schema = (not report.schema_valid) and (not has_critical)

        rubric_score, rubric_rating = map_raw_to_rubric_score(
            success_rate=vector_avg,
            has_critical_errors=has_critical,
            has_minor_schema_violations=has_minor_schema,
        )

        passed = (rubric_score >= 3) and (not has_critical)

        details = (
            f"Jev-Confidence Vector: Compliance={report.compliance_score:.1f}%, "
            f"Violations={len(report.violations)} -> Rubric {rubric_score} ({rubric_rating})"
        )

        return JevConfidenceVectorResult(
            scenario_id=scenario_id,
            passed=passed,
            confidence_vector=confidence_vector,
            compliance_report=report,
            metrics=metrics,
            rubric_score=rubric_score,
            rubric_rating=rubric_rating,
            normalized_score=float(rubric_score) * 20.0,
            details=details,
        )
