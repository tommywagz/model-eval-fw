"""Abstract Model Interface and Response Dataclass for BenchMaxxer."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from benchmaxxer.telemetry.cache import ResponseCache, compute_candidate_cache_key


@dataclass
class ModelResponse:
    """Standardized response envelope returned by all BenchMaxxer model providers."""

    text: str
    raw_response: Any
    input_tokens: int
    output_tokens: int
    latency_ms: float
    finish_reason: str = "STOP"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "raw_response": (
                self.raw_response
                if isinstance(self.raw_response, (dict, list, str, int, float, bool, type(None)))
                else str(self.raw_response)
            ),
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "latency_ms": float(self.latency_ms),
            "finish_reason": str(self.finish_reason),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelResponse":
        return cls(
            text=str(data.get("text", "")),
            raw_response=data.get("raw_response", {}),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            latency_ms=float(data.get("latency_ms", 0.0)),
            finish_reason=str(data.get("finish_reason", "STOP")),
        )


class BaseModelClient(ABC):
    """Abstract base client for all Vertex AI, Anthropic, Endpoint, and OpenAI-compatible models."""

    def __init__(
        self,
        alias: str,
        model_name: str,
        provider: str,
        mode: str = "mock",
        project_id: str = "benchmaxxer-eval-sandbox",
        location: str = "us-central1",
        generation_defaults: Optional[Dict[str, Any]] = None,
        cache: Optional[ResponseCache] = None,
        no_cache: bool = False,
        replay: bool = False,
        cost_per_1k_input_usd: float = 0.001,
        cost_per_1k_output_usd: float = 0.002,
        **extra_config: Any,
    ) -> None:
        self.alias = alias
        self.model_name = model_name
        self.provider = provider
        self.mode = mode.lower()
        self.project_id = project_id
        self.location = location
        self.generation_defaults: Dict[str, Any] = {
            "temperature": 0.0,
            "max_output_tokens": 4096,
            "seed": 42,
        }
        if generation_defaults:
            self.generation_defaults.update(generation_defaults)
        self.no_cache = no_cache
        self.replay = replay
        self.cache = cache or ResponseCache(no_cache=no_cache, replay=replay)
        self.cost_per_1k_input_usd = cost_per_1k_input_usd
        self.cost_per_1k_output_usd = cost_per_1k_output_usd
        self.extra_config = extra_config
        self.call_count = 0
        self.last_generation_params: Dict[str, Any] = {}

    def _merge_params(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(self.generation_defaults)
        for k, v in kwargs.items():
            if k not in ("use_cache", "no_cache", "replay"):
                merged[k] = v
        self.last_generation_params = merged
        return merged

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Compute estimated USD cost based on token counts and configured pricing."""
        in_cost = (input_tokens / 1000.0) * self.cost_per_1k_input_usd
        out_cost = (output_tokens / 1000.0) * self.cost_per_1k_output_usd
        return round(in_cost + out_cost, 6)

    def _execute_with_cache(
        self,
        prompt: str,
        system_instruction: Optional[str],
        params: Dict[str, Any],
        live_or_mock_fn: Callable[[], ModelResponse],
    ) -> ModelResponse:
        """Execute generation with deterministic SHA256 cache lookup and replay guard."""
        use_cache = not self.no_cache
        if use_cache or self.replay:
            cached_entry = self.cache.get(
                model_alias=self.alias,
                prompt=prompt,
                system_instruction=system_instruction,
                generation_params=params,
            )
            if cached_entry and "response" in cached_entry:
                resp = ModelResponse.from_dict(cached_entry["response"])
                raw = dict(resp.raw_response) if isinstance(resp.raw_response, dict) else {"raw": resp.raw_response}
                raw["cached"] = True
                raw["cache_key"] = cached_entry.get("cache_key")
                resp.raw_response = raw
                return resp

        # Perform actual model invocation (mock or live)
        self.call_count += 1
        response = live_or_mock_fn()

        # Persist to cache unless disabled
        if not self.no_cache:
            cache_key = compute_candidate_cache_key(
                model_alias=self.alias,
                prompt=prompt,
                system_instruction=system_instruction,
                generation_params=params,
            )
            raw = dict(response.raw_response) if isinstance(response.raw_response, dict) else {"raw": response.raw_response}
            raw["cache_key"] = cache_key
            raw["cached"] = False
            response.raw_response = raw
            self.cache.set(
                model_alias=self.alias,
                prompt=prompt,
                system_instruction=system_instruction,
                generation_params=params,
                response_data=response.to_dict(),
            )

        return response

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        """Generate a single completion from a prompt and optional system instruction."""

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> ModelResponse:
        """Generate a multi-turn chat completion from a list of role/content message dicts."""


def synthesize_mock_response(
    alias: str,
    model_name: str,
    provider: str,
    prompt: str,
    system_instruction: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> ModelResponse:
    """Deterministic synthetic response generator for offline/hermetic mock execution."""
    start = time.perf_counter()
    sys_text = (system_instruction or "").lower()
    prompt_lower = prompt.lower()

    # Check if this is an Actor-Critic invocation
    is_critic = (
        alias.startswith("critic-")
        or "criticevaluation" in sys_text
        or "criticevaluation" in prompt_lower
        or "rubric anchors" in prompt_lower
    )

    if is_critic:
        text_out = _synthesize_critic_json(alias, prompt, system_instruction)
    else:
        text_out = _synthesize_candidate_completion(alias, prompt)

    elapsed_ms = max(1.25, (time.perf_counter() - start) * 1000.0 + 12.5)
    in_tokens = max(16, len(prompt.split()) + len((system_instruction or "").split()))
    out_tokens = max(24, len(text_out.split()))

    return ModelResponse(
        text=text_out,
        raw_response={
            "provider": provider,
            "model_alias": alias,
            "model_name": model_name,
            "mode": "mock",
            "params": params or {},
        },
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        latency_ms=round(elapsed_ms, 3),
        finish_reason="STOP",
    )


def _synthesize_critic_json(
    alias: str,
    prompt: str,
    system_instruction: Optional[str] = None,
) -> str:
    """Produce deterministic CriticEvaluation JSON for Qwen, MiniMax, and Kimi K."""
    prompt_lower = prompt.lower()
    sys_lower = (system_instruction or "").lower()

    # Determine which critic persona is active
    if "qwen" in alias.lower() or "architecturalcritic" in sys_lower:
        critic_name = "qwen"
        dimension = "Architectural Coherence & Modularity"
    elif "minimax" in alias.lower() or "testharnesscritic" in sys_lower:
        critic_name = "minimax"
        dimension = "Execution Correctness & Test Rigor"
    elif "kimi" in alias.lower() or "platformcompliancecritic" in sys_lower:
        critic_name = "kimi_k"
        dimension = "Factual Grounding & Platform Compliance"
    else:
        critic_name = alias
        dimension = "Architectural Coherence & Modularity"

    # Detect negative / defective markers in candidate artifact
    # Isolate candidate artifact section if present so rubric instructions don't false-trigger
    artifact_section = prompt
    if "### Candidate Artifact" in prompt and "### Deterministic Test Results" in prompt:
        artifact_section = prompt.split("### Candidate Artifact", 1)[1].split(
            "### Rubric Anchors", 1
        )[0]
    artifact_lower = artifact_section.lower()

    negative_markers = [
        "monolithic_global_state",
        "global_mutable_state",
        "hallucinated_flag",
        "invalid_iam_role",
        "unhandled_crash",
        "false_pass",
        "syntax_error",
        "deliberate_failure",
        "negative_fixture",
        "status: fail",
        "passed: false",
        "circular_dependency",
        "roles/owner_all_wildcards",
    ]
    detected_markers = [m for m in negative_markers if m in artifact_lower]

    if detected_markers:
        score = 1
        normalized_score = 20.0
        if critic_name == "qwen":
            critique = (
                "Candidate artifact retains monolithic anti-patterns, global mutable state, "
                "and tight coupling across service boundaries without clean lifecycle separation."
            )
            anomalies = [
                "Monolithic global state and circular module dependencies detected",
                f"Triggered architectural failure markers: {', '.join(detected_markers)}",
            ]
            remediation = (
                "Decouple domain logic into isolated service modules, eliminate global mutable state, "
                "and inject cloud dependencies via interfaces."
            )
        elif critic_name == "minimax":
            critique = (
                "Candidate test execution exhibits unhandled error paths, missing negative-test "
                "invariance assertions, and incomplete resource teardown coverage."
            )
            anomalies = [
                "Missing negative boundary assertions or unhandled runtime failure",
                f"Triggered test rigor failure markers: {', '.join(detected_markers)}",
            ]
            remediation = (
                "Add strict negative test invariance checks, catch invalid inputs cleanly, "
                "and wrap cloud resources in a deterministic teardown_fixture."
            )
        else:
            critique = (
                "Candidate artifact contains hallucinated GCP/ADK API parameters, over-permissive "
                "or invalid IAM bindings, and schema compliance violations."
            )
            anomalies = [
                "Hallucinated GCP/ADK flags or non-compliant IAM schema bindings",
                f"Triggered compliance failure markers: {', '.join(detected_markers)}",
            ]
            remediation = (
                "Replace invalid API flags with verified Vertex AI / Cloud Run SDK schemas "
                "and enforce least-privilege IAM roles."
            )
    else:
        score = 5
        normalized_score = 100.0
        if critic_name == "qwen":
            critique = (
                "Candidate demonstrates idiomatic, fully decoupled modular architecture with clean "
                "boundary separation, low cyclomatic complexity, and verified lifecycle management."
            )
            anomalies = []
            remediation = "Architecture meets Score 5 reference standards; no structural changes required."
        elif critic_name == "minimax":
            critique = (
                "Exhaustive blackbox test assertions verified across both positive and negative "
                "fixtures with strict negative invariance and guaranteed resource teardown."
            )
            anomalies = []
            remediation = "Test harness rigor meets Score 5 reference standards."
        else:
            critique = (
                "100% schema-compliant GCP and ADK platform integrations with accurate IAM permissions, "
                "validated OAuth scopes, and deterministic error handling."
            )
            anomalies = []
            remediation = "Platform compliance and factual grounding meet Score 5 standards."

    payload = {
        "critic_name": critic_name,
        "dimension": dimension,
        "score": score,
        "qualitative_critique": critique,
        "detected_anomalies": anomalies,
        "remediation_advice": remediation,
        "normalized_score": normalized_score,
    }
    return json.dumps(payload, indent=2)


def _synthesize_candidate_completion(alias: str, prompt: str) -> str:
    """Produce realistic, verifiable candidate completions for benchmark scenarios."""
    prompt_lower = prompt.lower()

    if "complex_skill_synthesis" in prompt_lower or "skill" in prompt_lower:
        return (
            "---\n"
            "name: multi-cloud-telemetry-synthesizer\n"
            "description: Orchestrates multi-step GCP telemetry extraction, BigQuery aggregation, and structured ADK reporting.\n"
            "version: 1.0.0\n"
            "parameters:\n"
            "  project_id:\n"
            "    type: string\n"
            "    required: true\n"
            "  dataset_id:\n"
            "    type: string\n"
            "    required: true\n"
            "---\n\n"
            "# Multi-Cloud Telemetry Synthesizer Skill\n\n"
            "```python\n"
            "from dataclasses import dataclass\n"
            "from typing import Dict, List, Any\n\n"
            "@dataclass\n"
            "class SynthesisReport:\n"
            "    project_id: str\n"
            "    aggregated_metrics: Dict[str, float]\n"
            "    verified_schema: bool\n\n"
            "class TelemetrySynthesisOrchestrator:\n"
            "    \"\"\"Decoupled orchestrator for multi-step ADK research and synthesis.\"\"\"\n\n"
            "    def __init__(self, bq_client: Any, gcs_client: Any) -> None:\n"
            "        self.bq_client = bq_client\n"
            "        self.gcs_client = gcs_client\n\n"
            "    def execute_pipeline(self, project_id: str, dataset_id: str) -> SynthesisReport:\n"
            "        if not project_id or not dataset_id:\n"
            "            raise ValueError('project_id and dataset_id are required')\n"
            "        rows = self.bq_client.query(f'SELECT metric, value FROM `{project_id}.{dataset_id}.events`')\n"
            "        summary = {'total_events': float(len(rows)), 'completeness': 100.0}\n"
            "        self.gcs_client.upload_json(f'gs://{project_id}-reports/summary.json', summary)\n"
            "        return SynthesisReport(project_id=project_id, aggregated_metrics=summary, verified_schema=True)\n"
            "```\n"
        )

    if "oauth" in prompt_lower or "iam" in prompt_lower:
        return json.dumps(
            {
                "service_account": "benchmaxxer-sa@benchmaxxer-eval-sandbox.iam.gserviceaccount.com",
                "enabled_apis": [
                    "aiplatform.googleapis.com",
                    "run.googleapis.com",
                    "bigquery.googleapis.com",
                ],
                "granted_roles": [
                    "roles/aiplatform.user",
                    "roles/run.invoker",
                    "roles/bigquery.dataViewer",
                ],
                "oauth_scopes": [
                    "https://www.googleapis.com/auth/cloud-platform",
                ],
                "least_privilege_verified": True,
            },
            indent=2,
        )

    return (
        "```python\n"
        "class ModularServiceAdapter:\n"
        "    \"\"\"Idiomatic refactored service module generated by candidate model.\"\"\"\n\n"
        "    def __init__(self, client: object) -> None:\n"
        "        self._client = client\n\n"
        "    def process(self, payload: dict) -> dict:\n"
        "        if not isinstance(payload, dict) or 'id' not in payload:\n"
        "            raise ValueError('Invalid payload schema: missing id')\n"
        "        return {'status': 'ok', 'id': payload['id'], 'processed_by': '" + alias + "'}\n"
        "```\n"
    )
