"""Deterministic caching and replay infrastructure for candidate generations and critic reviews."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


class ReplayCacheMissError(RuntimeError):
    """Raised when --replay mode is active and no cached response is found."""


def _normalize_params(generation_params: Optional[Dict[str, Any]]) -> str:
    """Produce a deterministic string representation of generation parameters."""
    if not generation_params:
        return "{}"
    cleaned = {
        str(k): generation_params[k]
        for k in sorted(generation_params.keys())
        if k not in ("use_cache", "no_cache", "replay", "cache_dir")
    }
    return str(cleaned)


def compute_candidate_cache_key(
    model_alias: str,
    prompt: str,
    system_instruction: Optional[str] = None,
    generation_params: Optional[Dict[str, Any]] = None,
) -> str:
    """Compute SHA256(model_alias + prompt + system_instruction + str(generation_params))."""
    sys_inst = system_instruction or ""
    params_str = _normalize_params(generation_params)
    raw_payload = f"{model_alias}{prompt}{sys_inst}{params_str}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


def compute_critic_cache_key(
    critic_alias: str,
    target_artifact_hash: str,
    template_version: str = "v1",
) -> str:
    """Compute SHA256(critic_alias + target_artifact_hash + template_version)."""
    raw_payload = f"{critic_alias}{target_artifact_hash}{template_version}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


def compute_artifact_hash(artifact_content: str) -> str:
    """Compute deterministic SHA256 hash of a candidate artifact string."""
    return hashlib.sha256(artifact_content.encode("utf-8")).hexdigest()


class ResponseCache:
    """Manages deterministic candidate model generation caches on disk.

    Cache layout:
        artifacts/cache/{model_alias}/{cache_key}.json
    """

    def __init__(
        self,
        base_dir: Optional[str | Path] = None,
        no_cache: bool = False,
        replay: bool = False,
    ) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path("artifacts/cache")
        self.no_cache = no_cache
        self.replay = replay

    def get_cache_path(self, model_alias: str, cache_key: str) -> Path:
        safe_alias = model_alias.replace("/", "_")
        return self.base_dir / safe_alias / f"{cache_key}.json"

    def get(
        self,
        model_alias: str,
        prompt: str,
        system_instruction: Optional[str] = None,
        generation_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a cached candidate response if available."""
        if self.no_cache and not self.replay:
            return None

        cache_key = compute_candidate_cache_key(
            model_alias=model_alias,
            prompt=prompt,
            system_instruction=system_instruction,
            generation_params=generation_params,
        )
        cache_path = self.get_cache_path(model_alias, cache_key)
        if cache_path.exists():
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                if self.replay:
                    raise ReplayCacheMissError(
                        f"Corrupted cache file at {cache_path} during --replay mode."
                    )
                return None

        if self.replay:
            # In replay mode, check if there is any cached response matching the same
            # model_alias and prompt (e.g. if minor runtime flags differed) before raising
            alias_dir = self.base_dir / model_alias.replace("/", "_")
            if alias_dir.exists():
                for candidate_file in sorted(alias_dir.glob("*.json")):
                    try:
                        data = json.loads(candidate_file.read_text(encoding="utf-8"))
                        if data.get("prompt") == prompt:
                            return data
                    except (json.JSONDecodeError, OSError):
                        continue
            raise ReplayCacheMissError(
                f"Replay cache miss for model '{model_alias}' (key={cache_key}). "
                f"Expected file at {cache_path}. Run without --replay first to populate cache."
            )

        return None

    def set(
        self,
        model_alias: str,
        prompt: str,
        system_instruction: Optional[str],
        generation_params: Optional[Dict[str, Any]],
        response_data: Dict[str, Any],
    ) -> Path:
        """Persist a candidate generation response to disk."""
        cache_key = compute_candidate_cache_key(
            model_alias=model_alias,
            prompt=prompt,
            system_instruction=system_instruction,
            generation_params=generation_params,
        )
        cache_path = self.get_cache_path(model_alias, cache_key)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_key": cache_key,
            "model_alias": model_alias,
            "prompt": prompt,
            "system_instruction": system_instruction or "",
            "generation_params": generation_params or {},
            "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "response": response_data,
        }
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return cache_path


class CriticCache:
    """Manages deterministic Actor-Critic evaluation caches on disk.

    Cache layout:
        artifacts/cache/critics/{critic_alias}/{cache_key}.json
    """

    def __init__(
        self,
        base_dir: Optional[str | Path] = None,
        no_cache: bool = False,
        replay: bool = False,
    ) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path("artifacts/cache/critics")
        self.no_cache = no_cache
        self.replay = replay

    def get_cache_path(self, critic_alias: str, cache_key: str) -> Path:
        safe_alias = critic_alias.replace("/", "_")
        return self.base_dir / safe_alias / f"{cache_key}.json"

    def get(
        self,
        critic_alias: str,
        target_artifact_hash: str,
        template_version: str = "v1",
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a cached critic evaluation if available."""
        if self.no_cache and not self.replay:
            return None

        cache_key = compute_critic_cache_key(
            critic_alias=critic_alias,
            target_artifact_hash=target_artifact_hash,
            template_version=template_version,
        )
        cache_path = self.get_cache_path(critic_alias, cache_key)
        if cache_path.exists():
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                if self.replay:
                    raise ReplayCacheMissError(
                        f"Corrupted critic cache file at {cache_path} during --replay."
                    )
                return None

        if self.replay:
            alias_dir = self.base_dir / critic_alias.replace("/", "_")
            if alias_dir.exists():
                for candidate_file in sorted(alias_dir.glob("*.json")):
                    try:
                        data = json.loads(candidate_file.read_text(encoding="utf-8"))
                        if data.get("target_artifact_hash") == target_artifact_hash:
                            return data
                    except (json.JSONDecodeError, OSError):
                        continue
            raise ReplayCacheMissError(
                f"Replay critic cache miss for critic '{critic_alias}' (key={cache_key}). "
                f"Expected file at {cache_path}."
            )

        return None

    def set(
        self,
        critic_alias: str,
        target_artifact_hash: str,
        template_version: str,
        evaluation_data: Dict[str, Any],
    ) -> Path:
        """Persist a critic evaluation result to disk."""
        cache_key = compute_critic_cache_key(
            critic_alias=critic_alias,
            target_artifact_hash=target_artifact_hash,
            template_version=template_version,
        )
        cache_path = self.get_cache_path(critic_alias, cache_key)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_key": cache_key,
            "critic_alias": critic_alias,
            "target_artifact_hash": target_artifact_hash,
            "template_version": template_version,
            "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "evaluation": evaluation_data,
        }
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return cache_path
