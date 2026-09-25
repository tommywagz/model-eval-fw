"""Deterministic Prompt Execution Contract and Pydantic Schema for Actor-Critic Evaluations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from benchmaxxer.critics.rubrics import get_rubric_for_critic, normalize_rubric_score
from benchmaxxer.models.base import BaseModelClient
from benchmaxxer.models.factory import get_model_client
from benchmaxxer.telemetry.cache import CriticCache, compute_artifact_hash

INVARIANCE_TEMPERATURE: float = 0.0
INVARIANCE_SEED: int = 42


class CriticEvaluation(BaseModel):
    """Structured Pydantic output contract for every individual Actor-Critic review."""

    critic_name: str
    dimension: str
    score: int = Field(ge=1, le=5)
    qualitative_critique: str
    detected_anomalies: List[str] = Field(default_factory=list)
    remediation_advice: Optional[str] = None
    normalized_score: float = Field(ge=0.0, le=100.0)


class PanelEvaluationSummary(BaseModel):
    """Aggregated multi-perspective Actor-Critic panel report across Qwen, MiniMax, and Kimi K."""

    composite_score: float = Field(ge=1.0, le=5.0)
    composite_normalized_score: float = Field(ge=0.0, le=100.0)
    invariance_controls: Dict[str, Any] = Field(
        default_factory=lambda: {"temperature": INVARIANCE_TEMPERATURE, "seed": INVARIANCE_SEED}
    )
    evaluations: Dict[str, CriticEvaluation]
    anomaly_count: int = 0
    passed_threshold: bool = True

    def to_telemetry_dict(self) -> Dict[str, Any]:
        return {
            "composite_score": round(self.composite_score, 3),
            "composite_normalized_score": round(self.composite_normalized_score, 2),
            "invariance_controls": self.invariance_controls,
            "anomaly_count": self.anomaly_count,
            "passed_threshold": self.passed_threshold,
            "critics": {
                k: v.model_dump() for k, v in self.evaluations.items()
            },
        }


def load_critic_prompt_template(
    critic_name: str,
    version: str = "v1",
    configs_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Load versioned prompt template from configs/critics/{critic_name}_{version}.json."""
    normalized_name = critic_name.strip().lower().replace("-", "_")
    short_map = {
        "critic_qwen": "qwen",
        "architecturalcritic": "qwen",
        "critic_minimax": "minimax",
        "testharnesscritic": "minimax",
        "critic_kimi_k": "kimi_k",
        "platformcompliancecritic": "kimi_k",
    }
    canonical = short_map.get(normalized_name, normalized_name)

    search_roots = []
    if configs_dir:
        search_roots.append(Path(configs_dir))
    search_roots.extend(
        [
            Path("configs/critics"),
            Path(__file__).resolve().parents[3] / "configs" / "critics",
        ]
    )

    candidate_filenames = [
        f"{critic_name}_{version}.json",
        f"{canonical}_{version}.json",
    ]
    for root in search_roots:
        for fname in candidate_filenames:
            path = root / fname
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))

    # Fallback built-in versioned template if file is missing in custom working dir
    rubric = get_rubric_for_critic(canonical)
    return {
        "critic_name": canonical,
        "critic_alias": rubric.critic_alias,
        "persona": rubric.persona,
        "version": version,
        "dimension": rubric.display_name,
        "invariance_controls": {"temperature": INVARIANCE_TEMPERATURE, "seed": INVARIANCE_SEED},
        "system_instruction": (
            f"You are {rubric.persona} ({rubric.critic_name}). Evaluate {rubric.display_name} "
            f"strictly on a 1-5 scale and return valid JSON matching CriticEvaluation."
        ),
        "rubric_anchors": {str(k): v for k, v in rubric.anchors.items()},
        "prompt_template": (
            "### Scenario Context\nScenario ID: {scenario_id}\nTask Prompt:\n{prompt}\n\n"
            "### Candidate Artifact\n```\n{candidate_output}\n```\n\n"
            "### Deterministic Test Results\n{test_context}\n\n"
            "### Rubric Anchors\n" + rubric.format_anchors_text()
        ),
    }


def parse_critic_evaluation_json(
    raw_text: str,
    default_critic_name: str,
    default_dimension: str,
) -> CriticEvaluation:
    """Strictly parse and validate JSON output into a CriticEvaluation Pydantic model."""
    cleaned = raw_text.strip()
    # Extract fenced JSON block if wrapped in markdown
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fenced_match:
        cleaned = fenced_match.group(1).strip()
    else:
        brace_match = re.search(r"(\{.*\})", cleaned, flags=re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(1).strip()

    data = json.loads(cleaned)
    score = int(data.get("score", 3))
    score = max(1, min(5, score))
    norm_score = float(data.get("normalized_score", normalize_rubric_score(score)))
    norm_score = max(0.0, min(100.0, norm_score))

    return CriticEvaluation(
        critic_name=str(data.get("critic_name") or default_critic_name),
        dimension=str(data.get("dimension") or default_dimension),
        score=score,
        qualitative_critique=str(data.get("qualitative_critique", "Evaluated against rubric anchors.")),
        detected_anomalies=list(data.get("detected_anomalies", [])),
        remediation_advice=data.get("remediation_advice"),
        normalized_score=norm_score,
    )


class CriticEvaluator:
    """Executes a single critic evaluation under strict invariance controls and caching."""

    def __init__(
        self,
        critic_name: str,
        critic_alias: str,
        mode: str = "mock",
        template_version: str = "v1",
        no_cache: bool = False,
        replay: bool = False,
        critic_cache: Optional[CriticCache] = None,
        model_client: Optional[BaseModelClient] = None,
        configs_dir: Optional[str | Path] = None,
    ) -> None:
        self.critic_name = critic_name
        self.critic_alias = critic_alias
        self.mode = mode
        self.template_version = template_version
        self.no_cache = no_cache
        self.replay = replay
        self.rubric = get_rubric_for_critic(critic_name)
        self.template_data = load_critic_prompt_template(
            critic_name=critic_name,
            version=template_version,
            configs_dir=configs_dir,
        )
        self.critic_cache = critic_cache or CriticCache(no_cache=no_cache, replay=replay)
        self.client = model_client or get_model_client(
            alias=critic_alias,
            mode=mode,
            no_cache=no_cache,
            replay=replay,
        )
        self.last_call_params: Dict[str, Any] = {}

    def evaluate(
        self,
        scenario_id: str,
        prompt: str,
        candidate_output: str,
        test_context: Optional[Dict[str, Any]] = None,
    ) -> CriticEvaluation:
        """Evaluate a candidate artifact with forced temperature=0.0 and seed=42."""
        context_str = json.dumps(test_context or {}, indent=2, sort_keys=True)
        artifact_composite = f"{scenario_id}::{candidate_output}::{context_str}"
        target_artifact_hash = compute_artifact_hash(artifact_composite)

        # 1. Check Critic Evaluation Cache first
        if not self.no_cache or self.replay:
            cached = self.critic_cache.get(
                critic_alias=self.critic_alias,
                target_artifact_hash=target_artifact_hash,
                template_version=self.template_version,
            )
            if cached and "evaluation" in cached:
                return CriticEvaluation.model_validate(cached["evaluation"])

        # 2. Format versioned prompt
        rendered_prompt = self.template_data["prompt_template"].format(
            scenario_id=scenario_id,
            prompt=prompt,
            candidate_output=candidate_output,
            test_context=context_str,
        )
        system_instruction = self.template_data.get("system_instruction", "")

        # 3. Enforce Invariance Controls: temperature = 0.0, seed = 42
        call_params = {
            "temperature": INVARIANCE_TEMPERATURE,
            "seed": INVARIANCE_SEED,
        }
        self.last_call_params = dict(call_params)

        response = self.client.generate(
            prompt=rendered_prompt,
            system_instruction=system_instruction,
            **call_params,
        )

        evaluation = parse_critic_evaluation_json(
            raw_text=response.text,
            default_critic_name=self.critic_name,
            default_dimension=self.rubric.display_name,
        )

        # 4. Store in Critic Evaluation Cache
        if not self.no_cache:
            self.critic_cache.set(
                critic_alias=self.critic_alias,
                target_artifact_hash=target_artifact_hash,
                template_version=self.template_version,
                evaluation_data=evaluation.model_dump(),
            )

        return evaluation


def aggregate_panel_evaluations(
    evaluations: Dict[str, CriticEvaluation],
    passing_normalized_threshold: float = 60.0,
) -> PanelEvaluationSummary:
    """Compute a composite Actor-Critic score across the critic panel."""
    if not evaluations:
        raise ValueError("Cannot aggregate an empty critic evaluation dictionary.")

    scores = [ev.score for ev in evaluations.values()]
    norm_scores = [ev.normalized_score for ev in evaluations.values()]
    anomalies = sum(len(ev.detected_anomalies) for ev in evaluations.values())

    avg_score = round(sum(scores) / len(scores), 3)
    avg_norm = round(sum(norm_scores) / len(norm_scores), 2)

    return PanelEvaluationSummary(
        composite_score=avg_score,
        composite_normalized_score=avg_norm,
        invariance_controls={
            "temperature": INVARIANCE_TEMPERATURE,
            "seed": INVARIANCE_SEED,
        },
        evaluations=evaluations,
        anomaly_count=anomalies,
        passed_threshold=avg_norm >= passing_normalized_threshold,
    )
