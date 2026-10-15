"""Local agent-harness detection and headless execution for devbench.

A *harness* is the coding agent (Antigravity, Jetski, Claude Code, OpenCode, Codex, Gemini CLI,
or any user-registered CLI) that hosts the Model-in-Question (MIQ) during an evaluation.
Harnesses must already be installed on the machine running devbench; this module detects
them and runs them non-interactively, routed to Vertex AI in the user's linked GCP project.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from devbench.harbor.packager import (
    get_agent_harness_spec,
    list_agent_harnesses,
    normalize_agent_harness,
)

_EXTRA_BIN_DIRS = (
    Path.home() / ".local" / "bin",
    Path.home() / ".npm-global" / "bin",
    Path.home() / ".bun" / "bin",
    Path.home() / ".cargo" / "bin",
    Path.home() / ".opencode" / "bin",
    Path.home() / ".claude" / "local",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)


class HarnessExecutionError(RuntimeError):
    """Raised when a harness CLI is missing or fails to produce a candidate."""


def find_cli_binary(names: Iterable[str]) -> Optional[str]:
    """Resolve the first available executable among ``names`` (PATH + common install dirs)."""
    for name in names:
        if not name:
            continue
        if os.path.isabs(name) and os.access(name, os.X_OK):
            return name
        found = shutil.which(name)
        if found:
            return found
        for d in _EXTRA_BIN_DIRS:
            candidate = d / name
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def detect_harness(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate a harness spec with local installation status."""
    out = dict(spec)
    if spec.get("builtin"):
        out.update({"installed": True, "binary_path": None, "install_status": "Built into devbench"})
        return out
    names = list(spec.get("cli_binaries") or []) or [spec.get("cli_binary") or spec.get("id")]
    path = find_cli_binary(names)
    out["installed"] = bool(path)
    out["binary_path"] = path
    out["install_status"] = (
        f"Installed: {path}" if path else f"Not found on this machine (looked for: {', '.join(n for n in names if n)})"
    )
    out["runs_headless"] = bool(spec.get("headless_command"))
    return out


def list_detected_harnesses() -> List[Dict[str, Any]]:
    """Return all harnesses (built-in + custom) annotated with local install status."""
    return [detect_harness(h) for h in list_agent_harnesses()]


def harness_model_arg(harness_id: str, model: Dict[str, Any]) -> str:
    """Translate an MIQ registry entry into the model identifier each harness CLI expects."""
    model_name = str(model.get("model_name") or model.get("id") or "")
    publisher = str(model.get("publisher") or "")
    brand = str(model.get("brand") or "")
    if harness_id == "opencode":
        if brand == "anthropic" or publisher == "anthropic":
            return f"google-vertex-anthropic/{model_name}"
        return f"google-vertex/{model_name}"
    return model_name


def check_harness_model_compat(harness_id: str, model: Dict[str, Any]) -> Optional[str]:
    """Return a human-readable incompatibility reason, or ``None`` if the pairing is supported."""
    spec = get_agent_harness_spec(harness_id)
    brands = spec.get("supported_brands") or []
    if brands and str(model.get("brand", "")).lower() not in brands:
        return (
            f"{spec['name']} can only host {', '.join(brands)} models, but the selected MIQ "
            f"'{model.get('name', model.get('id'))}' is a {model.get('brand', 'unknown')} model."
        )
    return None


def build_harness_env(project_id: str, location: str, model: Dict[str, Any]) -> Dict[str, str]:
    """Environment that routes harness CLIs to Vertex AI in the linked project."""
    model_location = str(model.get("location") or location)
    env = dict(os.environ)
    env.update(
        {
            "GOOGLE_CLOUD_PROJECT": project_id,
            "GOOGLE_CLOUD_LOCATION": model_location,
            "VERTEX_PROJECT_ID": project_id,
            "VERTEX_LOCATION": model_location,
            "VERTEXAI_PROJECT": project_id,
            "VERTEXAI_LOCATION": model_location,
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "CLAUDE_CODE_USE_VERTEX": "1",
            "ANTHROPIC_VERTEX_PROJECT_ID": project_id,
            "CLOUD_ML_REGION": model_location,
            "CLOUDSDK_CORE_PROJECT": project_id,
            "DEVBENCH_MIQ": str(model.get("id", "")),
        }
    )
    return env


def _walk(obj: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


_INPUT_KEYS = ("input_tokens", "prompt_tokens", "prompttokencount", "inputtokens", "prompt", "input")
_OUTPUT_KEYS = ("output_tokens", "completion_tokens", "candidatestokencount", "outputtokens", "candidates", "output")
_TEXT_KEYS = ("result", "response", "text", "output_text", "content", "message", "final_response")


def parse_harness_output(stdout: str) -> Dict[str, Any]:
    """Extract candidate text and token usage from a harness CLI's stdout (JSON, JSONL or text)."""
    text = (stdout or "").strip()
    docs: List[Any] = []
    try:
        docs = [json.loads(text)]
    except (json.JSONDecodeError, ValueError):
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    docs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    candidate = ""
    in_tok = 0
    out_tok = 0
    cost: Optional[float] = None
    if docs:
        for doc in docs:
            if isinstance(doc, dict):
                for key in _TEXT_KEYS:
                    val = doc.get(key)
                    if isinstance(val, str) and val.strip():
                        candidate = val
                        break
            for k, v in _walk(doc):
                kl = k.lower()
                if isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)):
                    if kl in _INPUT_KEYS and kl not in ("prompt", "input"):
                        in_tok = max(in_tok, int(v))
                    elif kl in ("prompt", "input") and in_tok == 0:
                        in_tok = int(v)
                    elif kl in _OUTPUT_KEYS and kl not in ("candidates", "output"):
                        out_tok = max(out_tok, int(v))
                    elif kl in ("candidates", "output") and out_tok == 0:
                        out_tok = int(v)
                    elif kl in ("total_cost_usd", "cost_usd") and cost is None:
                        cost = float(v)
    if not candidate:
        candidate = text
    reported = in_tok > 0 or out_tok > 0
    return {
        "candidate_output": candidate,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "reported_cost_usd": cost,
        "token_source": "harness_reported" if reported else "estimated",
    }


def run_harness_headless(
    harness_id: str,
    prompt: str,
    model: Dict[str, Any],
    project_id: str,
    location: str,
    workdir: Path,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the selected harness CLI non-interactively and return the candidate + usage."""
    canonical = normalize_agent_harness(harness_id)
    spec = detect_harness(get_agent_harness_spec(canonical))
    template = spec.get("headless_command")
    if not template:
        raise HarnessExecutionError(f"Harness '{canonical}' has no headless command configured.")
    if not spec.get("installed"):
        raise HarnessExecutionError(f"Harness '{spec['name']}' is not installed: {spec['install_status']}")

    model_arg = harness_model_arg(canonical, model)
    argv: List[str] = []
    skip_next = False
    for i, part in enumerate(template):
        if skip_next:
            skip_next = False
            continue
        if part == "{model}" and not model_arg:
            continue
        # Drop a "--model"/"-m" flag whose value would be empty.
        if part in ("--model", "-m") and i + 1 < len(template) and template[i + 1] == "{model}" and not model_arg:
            skip_next = True
            continue
        argv.append(
            part.replace("{binary}", str(spec["binary_path"]))
            .replace("{prompt}", prompt)
            .replace("{model}", model_arg)
        )

    workdir.mkdir(parents=True, exist_ok=True)
    timeout = int(timeout_seconds or os.environ.get("DEVBENCH_HARNESS_TIMEOUT", "900"))
    env = build_harness_env(project_id, location, model)
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise HarnessExecutionError(f"{spec['name']} timed out after {timeout}s") from exc
    latency_ms = round((time.perf_counter() - start) * 1000.0, 3)

    (workdir / "harness_stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (workdir / "harness_stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    if proc.returncode != 0:
        raise HarnessExecutionError(
            f"{spec['name']} exited with code {proc.returncode}: {(proc.stderr or proc.stdout or '').strip()[-600:]}"
        )

    parsed = parse_harness_output(proc.stdout or "")
    if parsed["token_source"] == "estimated":
        parsed["input_tokens"] = max(1, int(len(prompt.split()) * 1.3))
        parsed["output_tokens"] = max(1, int(len(parsed["candidate_output"].split()) * 1.3))
    parsed.update(
        {
            "harness": canonical,
            "harness_name": spec["name"],
            "binary_path": spec["binary_path"],
            "argv": [a if a != prompt else "<prompt>" for a in argv],
            "model_arg": model_arg,
            "latency_ms": latency_ms,
            "workdir": str(workdir),
        }
    )
    return parsed
