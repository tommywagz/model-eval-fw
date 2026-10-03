"""Argon-Backed Agent for Dynamic Test Suite Creation from Natural Language Scenarios."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional



def _slugify(text: str) -> str:
    """Convert arbitrary text into a clean snake_case identifier."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:40] if slug else f"scenario_{int(time.time())}"


class ArgonSuiteCreator:
    """Argon Engine Agent that synthesizes and verifies a BenchMaxxer test suite from a user use case."""

    def __init__(self) -> None:
        pass

    def classify_pillar_and_difficulty(self, prompt: str) -> Dict[str, str]:
        """Classify the use case into one of BenchMaxxer's three core pillars and assign a difficulty tier."""
        lower = prompt.lower()

        # Pillar classification
        cloud_keywords = ["gcp", "cloud run", "bigquery", "pub/sub", "pubsub", "storage", "gcs", "iam", "tpu", "gke", "docker", "cloudbuild", "service account"]
        trans_keywords = ["translate", "rewrite", "refactor", "port", "convert", "rust", "go", "gin", "monolith", "decouple", "throughput", "caching"]
        skill_keywords = ["skill", "adk", "agent", "tool", "dispatch", "scaffold", "prompt", "persona"]

        cloud_score = sum(1 for k in cloud_keywords if k in lower)
        trans_score = sum(1 for k in trans_keywords if k in lower)
        skill_score = sum(1 for k in skill_keywords if k in lower)

        if trans_score > cloud_score and trans_score > skill_score:
            pillar = "Codebase Conversion & Refactoring Ability"
            suite_slug = "codebase_translation"
            suite_name = "Translation"
        elif cloud_score > trans_score and cloud_score > skill_score:
            pillar = "Google Cloud Platform (GCP) Operations"
            suite_slug = "cloud_tool_writing"
            suite_name = "Cloud Tool Writing Proficiency"
        else:
            pillar = "Agent Skill Creation + Use"
            suite_slug = "agent_skill_creation"
            suite_name = "Skill Creation + Use"

        # Difficulty classification
        hard_keywords = ["complex", "swarm", "multi-step", "high-throughput", "concurrency", "distributed", "monolith"]
        med_keywords = ["rewrite", "refactor", "dispatch", "fine-tune", "training", "pipeline", "validate"]

        if any(k in lower for k in hard_keywords):
            difficulty = "Hard"
        elif any(k in lower for k in med_keywords):
            difficulty = "Medium"
        else:
            difficulty = "Easy"

        return {
            "pillar": pillar,
            "suite_slug": suite_slug,
            "suite_name": suite_name,
            "difficulty": difficulty,
        }

    def generate_suite(
        self,
        user_prompt: str,
        title: Optional[str] = None,
        register: bool = True,
    ) -> Dict[str, Any]:
        """Generate a complete test suite specification reflecting the user's scenario."""
        cleaned_prompt = user_prompt.strip()
        if not cleaned_prompt:
            raise ValueError("Scenario description cannot be empty.")

        classification = self.classify_pillar_and_difficulty(cleaned_prompt)
        pillar = classification["pillar"]
        suite_slug = classification["suite_slug"]
        suite_name = classification["suite_name"]
        difficulty = classification["difficulty"]

        scenario_title = title.strip() if title and title.strip() else cleaned_prompt.split(".")[0][:50]
        raw_slug = _slugify(scenario_title)
        scenario_id = f"argon_{raw_slug}"

        # Extract features under test
        features = [
            f"Adherence to {pillar} best practices and runtime safety invariants",
            f"Deterministic execution and verification under {difficulty} operational conditions",
            "Structured completion formatting with typed parameters and zero unhandled exceptions",
        ]

        # Synthesize baseline code and prompts based on pillar
        if suite_slug == "agent_skill_creation":
            baseline_code = (
                "# Baseline Agent Skill Scaffolding\n"
                "from typing import Any, Dict\n\n"
                "class GeneratedSkill:\n"
                "    '''Unimplemented baseline stub for agent skill.'''\n"
                "    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:\n"
                "        raise NotImplementedError('Baseline stub')\n"
            )
            candidate_prompt = (
                f"Scenario: {scenario_id}\n"
                f"Pillar: {pillar} (Difficulty: {difficulty})\n"
                f"Requirement: {cleaned_prompt}\n\n"
                f"Instructions: Generate a complete, production-ready ADK skill with Skill.md metadata, "
                f"parameter schemas, clean dependency boundaries, and input validation."
            )
            primary_metrics = ["actor_critic_quality_score", "execution_completeness_rate", "test_pass_rate"]
        elif suite_slug == "cloud_tool_writing":
            baseline_code = (
                "# Baseline GCP Operations Script\n"
                "def provision_resources():\n"
                "    # Unconfigured GCP provider stubs\n"
                "    return {'status': 'unconfigured'}\n"
            )
            candidate_prompt = (
                f"Scenario: {scenario_id}\n"
                f"Pillar: {pillar} (Difficulty: {difficulty})\n"
                f"Requirement: {cleaned_prompt}\n\n"
                f"Instructions: Provide the complete GCP workflow including IAM least-privilege configuration, "
                f"cloud resource provisioning specifications, health probes, and automated cleanup."
            )
            primary_metrics = ["average_pass_rate", "deployment_lifecycle_pass_rate"]
        else:
            baseline_code = (
                "// Legacy baseline reference implementation\n"
                "function legacyHandler(req, res) {\n"
                "    // Tightly coupled state and blocking operations\n"
                "    res.json({ status: 'legacy' });\n"
                "}\n"
            )
            candidate_prompt = (
                f"Scenario: {scenario_id}\n"
                f"Pillar: {pillar} (Difficulty: {difficulty})\n"
                f"Requirement: {cleaned_prompt}\n\n"
                f"Instructions: Refactor and translate the codebase to meet modern architectural standards, "
                f"eliminating anti-patterns and optimizing throughput and error resilience."
            )
            primary_metrics = ["refactoring_quality_score", "average_pass_rate"]

        spec: Dict[str, Any] = {
            "scenario_id": scenario_id,
            "scenario_name": scenario_title,
            "pillar": pillar,
            "suite_slug": suite_slug,
            "suite_name": suite_name,
            "difficulty": difficulty,
            "timeout_seconds": 120,
            "scenario_summary": cleaned_prompt,
            "features_under_test": features,
            "prompt": candidate_prompt,
            "baseline_code": baseline_code,
            "primary_metrics": primary_metrics,
            "created_by": "Argon-Backed Agent (BenchMaxxer Test Synthesizer)",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "assertions": [
                {"name": "schema_and_syntax_validation", "description": "Output adheres to syntactic and structural requirements."},
                {"name": "deterministic_execution_pass", "description": "Candidate passes all deterministic assertion checks."},
                {"name": "resource_safety_and_teardown", "description": "Zero leaked cloud resources or lingering global state."},
                {"name": "critic_composite_threshold", "description": "Actor-Critic multi-model panel scores >= 3.0 / 5.0 normalized rubric."},
            ],
            "fixtures": {
                "positive_expectation": f"Candidate fully satisfies: '{cleaned_prompt}' with 100% deterministic test pass rate.",
                "negative_expectation": "Malformed or over-permissive candidate fails cleanly without crashing the test harness.",
            },
        }

        if register:
            self.register_scenario(spec)

        return spec

    def register_scenario(self, spec: Dict[str, Any]) -> None:
        """Register the dynamically generated scenario into the active SCENARIO_CATALOG and SUITE_CATALOG."""
        from benchmaxxer.scenarios.runner import SCENARIO_CATALOG, SUITE_CATALOG

        scenario_id = spec["scenario_id"]

        suite_slug = spec["suite_slug"]

        SCENARIO_CATALOG[scenario_id] = {
            "pillar": spec["pillar"],
            "suite_name": spec["suite_name"],
            "suite_slug": suite_slug,
            "difficulty": spec["difficulty"],
            "prompt": spec["prompt"],
            "baseline_code": spec["baseline_code"],
            "primary_metrics": spec["primary_metrics"],
        }

        if suite_slug in SUITE_CATALOG:
            if scenario_id not in SUITE_CATALOG[suite_slug]["scenarios"]:
                SUITE_CATALOG[suite_slug]["scenarios"].append(scenario_id)
