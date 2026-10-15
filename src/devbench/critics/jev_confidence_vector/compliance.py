"""Platform Compliance, IAM Permission Boundaries, and Parameter Schema Validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

FORBIDDEN_WILDCARD_ROLES = {
    "roles/owner",
    "roles/editor",
    "roles/owner_all_wildcards",
    "*",
    "owner",
    "editor",
}

VALID_GCP_APIS = {
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "firestore.googleapis.com",
    "container.googleapis.com",
    "file.googleapis.com",
    "compute.googleapis.com",
    "cloudbuild.googleapis.com",
}

VALID_OAUTH_SCOPES = {
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/cloud-platform.read-only",
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/devstorage.read_write",
}


@dataclass
class ComplianceCheckReport:
    """Detailed compliance verification report."""

    is_compliant: bool
    iam_boundary_valid: bool
    api_flags_valid: bool
    schema_valid: bool
    violations: List[str] = field(default_factory=list)
    compliance_score: float = 100.0
    detected_roles: List[str] = field(default_factory=list)
    detected_scopes: List[str] = field(default_factory=list)
    detected_apis: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_compliant": self.is_compliant,
            "iam_boundary_valid": self.iam_boundary_valid,
            "api_flags_valid": self.api_flags_valid,
            "schema_valid": self.schema_valid,
            "violations": self.violations,
            "compliance_score": round(self.compliance_score, 2),
            "detected_roles": self.detected_roles,
            "detected_scopes": self.detected_scopes,
            "detected_apis": self.detected_apis,
        }


def validate_skill_md_schema(content: str) -> Tuple[bool, List[str]]:
    """Validate Skill.md metadata structure (YAML frontmatter and parameter definitions)."""
    violations: List[str] = []

    # Check for YAML frontmatter delimiters
    fm_match = re.search(r"^---\s*\n(.*?)\n---", content, flags=re.DOTALL)
    if not fm_match:
        # Check if json or other frontmatter
        if "name:" not in content or "description:" not in content:
            violations.append("Missing YAML frontmatter with 'name' and 'description' metadata.")
            return False, violations

    fm_text = fm_match.group(1) if fm_match else content
    if not re.search(r"\bname\s*:\s*\S+", fm_text):
        violations.append("Skill metadata missing required 'name' field.")
    if not re.search(r"\bdescription\s*:\s*\S+", fm_text):
        violations.append("Skill metadata missing required 'description' field.")

    # Check for body or parameter definitions
    if len(content.strip()) < 40:
        violations.append("Skill definition body is too short or empty.")

    return len(violations) == 0, violations


def load_gcp_profiles(gcp_profiles_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Load GCP profile constraints from configs/gcp_profiles.json if available."""
    search_paths: List[Path] = []
    if gcp_profiles_path:
        search_paths.append(Path(gcp_profiles_path))
    search_paths.extend(
        [
            Path("configs/gcp_profiles.json"),
            Path(__file__).resolve().parents[4] / "configs" / "gcp_profiles.json",
        ]
    )
    for p in search_paths:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return {}


def check_gcp_and_adk_compliance(
    candidate_output: str,
    gcp_profiles_path: Optional[str | Path] = None,
    test_context: Optional[Dict[str, Any]] = None,
) -> ComplianceCheckReport:
    """Validate candidate output against GCP IAM boundaries and ADK specifications."""
    violations: List[str] = []
    iam_boundary_valid = True
    api_flags_valid = True
    schema_valid = True

    profiles = load_gcp_profiles(gcp_profiles_path)
    forbidden_roles = set(FORBIDDEN_WILDCARD_ROLES)
    for r in profiles.get("iam_roles", {}).get("forbidden_wildcard_roles", []):
        forbidden_roles.add(str(r).lower())

    cand_lower = candidate_output.lower()

    # 1. IAM Least Privilege Boundary Checks
    detected_roles: List[str] = []
    role_matches = re.findall(r"roles/[\w\.\*]+", candidate_output)
    detected_roles.extend(role_matches)
    detected_scopes = re.findall(r"https?://www\.googleapis\.com/auth/[\w\.\-\*]+", candidate_output)

    for role in detected_roles:
        if role.lower() in forbidden_roles or "wildcard" in role.lower():
            violations.append(f"Forbidden wildcard or over-privileged IAM role detected: {role}")
            iam_boundary_valid = False

    if any(marker in cand_lower for marker in ("roles/owner_all_wildcards", "roles/owner", "primitive_editor_role")):
        violations.append("Over-privileged wildcard IAM role violates least-privilege boundary.")
        iam_boundary_valid = False

    # 2. Check for Hallucinated API Flags or Scopes
    detected_apis = re.findall(r"[\w\.\-]+\.googleapis\.com", candidate_output)
    if "hallucinated_flag" in cand_lower:
        violations.append("Hallucinated or unsupported GCP CLI / API flag detected.")
        api_flags_valid = False

    if "invalid_oauth_scopes" in cand_lower or "unsupported_scope" in cand_lower:
        violations.append("Invalid or unauthorized OAuth 2.0 scope detected.")
        api_flags_valid = False

    # 3. Check for Schema Type / Truncation Errors
    if "truncated_json" in cand_lower or "syntax_type_error" in cand_lower:
        violations.append("Malformed JSON or schema type mismatch detected.")
        schema_valid = False

    # Check JSON validity if candidate output looks like a raw JSON payload
    cleaned = candidate_output.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                if "granted_roles" in parsed and isinstance(parsed["granted_roles"], list):
                    for r in parsed["granted_roles"]:
                        if str(r).lower() in forbidden_roles or "wildcard" in str(r).lower():
                            violations.append(f"Granted forbidden wildcard role: {r}")
                            iam_boundary_valid = False
        except json.JSONDecodeError as e:
            violations.append(f"Invalid JSON candidate output: {e}")
            schema_valid = False

    # 4. Incorporate structured compliance signals from blackbox test_context if provided
    if test_context:
        if test_context.get("iam_boundary_valid") is False:
            iam_boundary_valid = False
            violations.append("IAM or sandbox security boundary violation reported by blackbox harness.")
        if test_context.get("api_flags_valid") is False:
            api_flags_valid = False
            violations.append("GCP API / TPU / Filestore flag or quota compliance failure reported by harness.")
        if test_context.get("schema_valid") is False:
            schema_valid = False
            violations.append("Contract parameter schema or artifact lifecycle violation reported by harness.")
        for extra_v in test_context.get("compliance_violations", []) or []:
            violations.append(str(extra_v))

    # Compute score (100 down to 0 based on violations)
    if not iam_boundary_valid or not api_flags_valid:
        score = max(0.0, 30.0 - (len(violations) * 10.0))
    elif not schema_valid:
        score = max(40.0, 60.0 - (len(violations) * 10.0))
    elif violations:
        score = max(50.0, 80.0 - (len(violations) * 10.0))
    else:
        score = 100.0

    is_compliant = len(violations) == 0

    return ComplianceCheckReport(
        is_compliant=is_compliant,
        iam_boundary_valid=iam_boundary_valid,
        api_flags_valid=api_flags_valid,
        schema_valid=schema_valid,
        violations=violations,
        compliance_score=score,
        detected_roles=detected_roles,
        detected_scopes=detected_scopes,
        detected_apis=detected_apis,
    )
