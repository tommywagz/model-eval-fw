"""Vertex AI Model Garden discovery for a user-linked Google Cloud project.

Linking flow used by the devbench Evaluation Studio:

1. Obtain an OAuth access token from Application Default Credentials (``google-auth`` if
   installed, otherwise ``gcloud auth application-default print-access-token`` /
   ``gcloud auth print-access-token``).
2. Verify the project exists / is accessible (Cloud Resource Manager) and that the
   Vertex AI API (``aiplatform.googleapis.com``) is enabled (Service Usage).
3. Discover the Models-in-Question (MIQs) usable from that project + region:
   * First-party Google (Gemini) publisher models -> usable whenever Vertex AI is enabled.
   * Partner / MaaS publisher models (Anthropic, Mistral, Meta, ...) -> listed from the
     Model Garden catalog, and optionally verified per-project with a free
     ``countTokens`` call or a 1-token request (these require "Enable" in Model Garden).
   * Self-deployed Model Garden models on Vertex AI Endpoints in the project.

Every network call is guarded; failures are reported back as structured errors so the UI
can explain exactly why a model is not available.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Publishers whose generative models we surface from the Model Garden catalog.
PUBLISHERS: Tuple[str, ...] = ("google", "anthropic", "xai", "meta", "mistralai", "elevenlabs", "deepseek-ai", "qwen", "ai21")

PUBLISHER_BRANDS: Dict[str, str] = {
    "google": "gemini",
    "anthropic": "anthropic",
    "xai": "xai",
    "mistralai": "mistral",
    "meta": "meta",
    "elevenlabs": "elevenlabs",
    "deepseek-ai": "deepseek",
    "qwen": "qwen",
    "ai21": "vertex",
}

PUBLISHER_LABELS: Dict[str, str] = {
    "google": "Google (Vertex AI Model Garden)",
    "anthropic": "Anthropic (Vertex AI Partner Model)",
    "xai": "xAI (Vertex AI Model Garden MaaS)",
    "mistralai": "Mistral AI (Vertex AI Partner Model)",
    "meta": "Meta (Vertex AI Model Garden MaaS)",
    "elevenlabs": "ElevenLabs (Vertex AI Partner Model)",
    "deepseek-ai": "DeepSeek (Vertex AI Model Garden MaaS)",
    "qwen": "Qwen (Vertex AI Model Garden MaaS)",
    "ai21": "AI21 Labs (Vertex AI Partner Model)",
}

# Approximate public list prices (USD per 1K tokens: input, output). Longest prefix wins.
PRICE_TABLE_PER_1K: Dict[str, Tuple[float, float]] = {
    "gemini-3.5-flash": (0.00010, 0.00040),
    "gemini-3-pro": (0.00200, 0.01200),
    "gemini-3-flash": (0.00050, 0.00300),
    "claude-opus-5": (0.00500, 0.02500),
    "claude-sonnet-5": (0.00300, 0.01500),
    "claude-opus-4-5": (0.00500, 0.02500),
    "claude-sonnet-4-6": (0.00300, 0.01500),
    "claude-sonnet-4-5": (0.00300, 0.01500),
    "claude-haiku-4-5": (0.00100, 0.00500),
    "grok-2-mini": (0.00020, 0.00100),
    "grok": (0.00020, 0.00100),
    "llama-3.1-8b": (0.00015, 0.00060),
    "llama-3.2": (0.00010, 0.00040),
    "llama": (0.00015, 0.00060),
    "muse": (0.00010, 0.00030),
    "mistral-small": (0.00010, 0.00030),
    "mistral-large": (0.00200, 0.00600),
    "mistral-medium": (0.00040, 0.00200),
    "elevenlabs": (0.00015, 0.00050),
    "eleven": (0.00015, 0.00050),
    "codestral": (0.00030, 0.00090),
    "deepseek-r1": (0.00135, 0.00540),
    "deepseek-v3": (0.00060, 0.00170),
    "qwen3": (0.00025, 0.00100),
}

DEFAULT_PRICE_PER_1K: Tuple[float, float] = (0.00100, 0.00200)

_NON_GENERATIVE_MARKERS = (
    "embedding", "embed", "imagen", "veo", "chirp", "tts", "image-generation", "imagegeneration",
    "multimodalembedding", "textembedding", "text-bison", "chat-bison", "code-bison", "codechat",
    "gecko", "lyria", "speech", "live-", "-live", "native-audio", "computer-use", "segmentation",
    "vision", "ocr", "guard", "prompt-guard", "safety",
)

_TOKEN_CACHE: Dict[str, Any] = {"token": None, "source": None, "expires_at": 0.0}
_TOKEN_LOCK = threading.Lock()


class GcpAuthError(RuntimeError):
    """Raised when no usable Google Cloud credentials can be obtained."""


# ----------------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------------


def _find_gcloud() -> Optional[str]:
    found = shutil.which("gcloud")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/gcloud", "/usr/local/bin/gcloud", "/usr/bin/gcloud"):
        if os.path.exists(candidate):
            return candidate
    return None


def get_access_token(force_refresh: bool = False) -> Tuple[str, str]:
    """Return ``(access_token, credential_source)`` using ADC or the gcloud CLI.

    Raises :class:`GcpAuthError` with remediation instructions when no credentials exist.
    """
    with _TOKEN_LOCK:
        if (
            not force_refresh
            and _TOKEN_CACHE["token"]
            and time.time() < float(_TOKEN_CACHE["expires_at"])
        ):
            return str(_TOKEN_CACHE["token"]), str(_TOKEN_CACHE["source"])

        errors: List[str] = []
        token: Optional[str] = None
        source = ""

        env_token = os.environ.get("DEVBENCH_GCP_ACCESS_TOKEN") or os.environ.get("GOOGLE_ACCESS_TOKEN")
        if env_token and env_token.strip():
            token, source = env_token.strip(), "env:GCP_ACCESS_TOKEN"

        if not token:
            try:
                import google.auth  # type: ignore
                import google.auth.transport.requests  # type: ignore

                creds, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
                creds.refresh(google.auth.transport.requests.Request())
                if creds.token:
                    token, source = str(creds.token), "google-auth (Application Default Credentials)"
            except ImportError:
                errors.append("google-auth not installed")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"google-auth ADC: {exc}")

        if not token:
            gcloud = _find_gcloud()
            if not gcloud:
                errors.append("gcloud CLI not found on PATH")
            else:
                for args, label in (
                    (["auth", "application-default", "print-access-token"], "gcloud ADC"),
                    (["auth", "print-access-token"], "gcloud user credentials"),
                ):
                    try:
                        proc = subprocess.run(
                            [gcloud, *args],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            check=False,
                        )
                        out = (proc.stdout or "").strip()
                        if proc.returncode == 0 and out:
                            token, source = out.splitlines()[-1].strip(), label
                            break
                        errors.append(f"{label}: {(proc.stderr or out).strip()[:200]}")
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{label}: {exc}")

        if not token:
            raise GcpAuthError(
                "No Google Cloud credentials available. Run `gcloud auth application-default login` "
                "(and `gcloud auth login`) on the machine running devbench, then link the project again. "
                f"Details: {'; '.join(errors)}"
            )

        _TOKEN_CACHE.update({"token": token, "source": source, "expires_at": time.time() + 300})
        return token, source


# ----------------------------------------------------------------------------
# HTTP helpers
# ----------------------------------------------------------------------------


HttpFn = Callable[[str, str, Optional[Dict[str, Any]], Dict[str, str]], Tuple[int, Any]]


def _http_json(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]],
    headers: Dict[str, str],
    timeout: float = 20.0,
) -> Tuple[int, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return exc.code, payload
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": {"message": str(exc)}}


def _error_message(payload: Any) -> str:
    if isinstance(payload, list):
        if not payload:
            return ""
        return "; ".join(_error_message(item) for item in payload if item)[:300]
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("status") or err)[:300]
        if isinstance(err, list):
            return _error_message(err)
        if err:
            return str(err)[:300]
        if "raw" in payload:
            return str(payload["raw"])[:300]
        if "message" in payload:
            return str(payload["message"])[:300]
        return str(payload)[:300]
    return str(payload)[:300]


def vertex_host(location: str) -> str:
    loc = (location or "us-central1").strip()
    return "https://aiplatform.googleapis.com" if loc == "global" else f"https://{loc}-aiplatform.googleapis.com"


def _auth_headers(token: str, project_id: str, quota_project: bool = False) -> Dict[str, str]:
    """Bearer auth headers. ``quota_project`` bills non-project-scoped calls (the global Model
    Garden catalog) to the linked project; project-scoped URLs don't need it."""
    headers = {"Authorization": f"Bearer {token}"}
    if quota_project:
        headers["x-goog-user-project"] = project_id
    return headers


# ----------------------------------------------------------------------------
# Project verification
# ----------------------------------------------------------------------------


def verify_gcp_project(
    project_id: str,
    token: Optional[str] = None,
    http: Optional[HttpFn] = None,
) -> Dict[str, Any]:
    """Verify that ``project_id`` is accessible and Vertex AI is enabled on it."""
    http_fn = http or _http_json
    credential_source = "provided"
    if token is None:
        token, credential_source = get_access_token()
    headers = _auth_headers(token, project_id)

    result: Dict[str, Any] = {
        "project_id": project_id,
        "accessible": False,
        "project_number": None,
        "display_name": None,
        "vertex_api_enabled": False,
        "credential_source": credential_source,
        "errors": [],
    }

    status, payload = http_fn(
        "GET",
        f"https://cloudresourcemanager.googleapis.com/v1/projects/{urllib.parse.quote(project_id)}",
        None,
        headers,
    )
    if status == 200:
        result["accessible"] = True
        result["project_number"] = payload.get("projectNumber")
        result["display_name"] = payload.get("name")
        result["lifecycle_state"] = payload.get("lifecycleState")
    else:
        result["errors"].append(
            f"Project lookup failed (HTTP {status}): {_error_message(payload)}"
        )

    status, payload = http_fn(
        "GET",
        f"https://serviceusage.googleapis.com/v1/projects/{urllib.parse.quote(project_id)}/services/aiplatform.googleapis.com",
        None,
        headers,
    )
    if status == 200:
        result["vertex_api_enabled"] = payload.get("state") == "ENABLED"
        if not result["vertex_api_enabled"]:
            result["errors"].append(
                "Vertex AI API (aiplatform.googleapis.com) is not enabled. Enable it with "
                f"`gcloud services enable aiplatform.googleapis.com --project {project_id}`."
            )
        # Service Usage succeeding also proves the project is reachable.
        result["accessible"] = True
    else:
        result["errors"].append(
            f"Could not read Vertex AI API state (HTTP {status}): {_error_message(payload)}"
        )
    return result


# ----------------------------------------------------------------------------
# Model Garden discovery
# ----------------------------------------------------------------------------


def lookup_price_per_1k(model_id: str, catalog_prices: Optional[Dict[str, Tuple[float, float]]] = None) -> Tuple[float, float, str]:
    """Return ``(input_per_1k, output_per_1k, pricing_source)`` for a model id."""
    mid = model_id.lower().split("@")[0]
    if catalog_prices and mid in catalog_prices:
        cin, cout = catalog_prices[mid]
        return cin, cout, "catalog"
    best = ""
    for prefix in PRICE_TABLE_PER_1K:
        if mid.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    if best:
        cin, cout = PRICE_TABLE_PER_1K[best]
        return cin, cout, "list_price"
    return DEFAULT_PRICE_PER_1K[0], DEFAULT_PRICE_PER_1K[1], "estimate"


def _humanize(model_id: str) -> str:
    base = model_id.split("@")[0]
    parts = re.split(r"[-_]", base)
    out = []
    for p in parts:
        if re.fullmatch(r"\d+(\.\d+)?[bkm]?", p, flags=re.I):
            out.append(p.upper() if p[-1:].isalpha() else p)
        else:
            out.append(p.capitalize())
    return " ".join(out)


def is_model_configurable(publisher: str, model_id: str) -> bool:
    """Ensure the oldest models that can be configured are Claude 4.5 and Gemini 3."""
    mid = model_id.lower()
    pub = publisher.lower()

    # Reject Gemini versions older than Gemini 3 (e.g. 1.0, 1.5, 2.0, 2.5)
    if pub == "google" or "gemini" in mid:
        if re.search(r"gemini[-_]?[12](\.|$)", mid) or any(
            v in mid for v in ("gemini-1.5", "gemini-1.0", "gemini-2.0", "gemini-2.5")
        ):
            return False

    # Reject Claude versions older than Claude 4.5 (e.g. Claude 3, 3.5, 3.7, 4.0, 4.1)
    if pub == "anthropic" or "claude" in mid:
        m = re.search(r"claude[-_]?(?:opus[-_]|sonnet[-_]|haiku[-_])?([0-9]+(?:\.[0-9]+|-?[0-9]+)?)", mid)
        if m:
            ver_str = m.group(1).replace("-", ".")
            try:
                ver_parts = [int(p) for p in ver_str.split(".") if p.isdigit()]
                if ver_parts:
                    major = ver_parts[0]
                    minor = ver_parts[1] if len(ver_parts) > 1 else 0
                    if major < 4 or (major == 4 and minor < 5):
                        return False
            except Exception:
                pass
        elif any(v in mid for v in ("claude-3", "claude-3-5", "claude-3.5", "claude-3-7", "claude-4-0", "claude-4-1")):
            return False

    return True


def _is_generative(publisher: str, model_id: str) -> bool:
    mid = model_id.lower()
    if publisher != "elevenlabs" and any(marker in mid for marker in _NON_GENERATIVE_MARKERS):
        return False
    if not is_model_configurable(publisher, model_id):
        return False
    if publisher == "google":
        return mid.startswith("gemini") or mid.startswith("gemma") or mid.startswith("muse")
    return True


def backend_provider_for(publisher: str) -> str:
    if publisher == "google":
        return "vertex_genai"
    if publisher == "anthropic":
        return "vertex_anthropic"
    return "vertex_maas"


def list_publisher_models(
    project_id: str,
    location: str,
    token: str,
    publishers: Tuple[str, ...] = PUBLISHERS,
    http: Optional[HttpFn] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """List generative publisher models from the Model Garden catalog."""
    http_fn = http or _http_json
    host = vertex_host(location)
    headers = _auth_headers(token, project_id, quota_project=True)
    found: List[Dict[str, Any]] = []
    errors: List[str] = []

    for pub in publishers:
        page_token = ""
        for _ in range(10):  # hard page cap
            qs = {"pageSize": "200", "listAllVersions": "false"}
            if page_token:
                qs["pageToken"] = page_token
            url = f"{host}/v1beta1/publishers/{pub}/models?{urllib.parse.urlencode(qs)}"
            status, payload = http_fn("GET", url, None, headers)
            if status == 403 and "x-goog-user-project" in headers:
                # Caller can't bill the catalog lookup to the project; retry with the ADC quota project.
                headers = _auth_headers(token, project_id, quota_project=False)
                status, payload = http_fn("GET", url, None, headers)
            if status != 200:
                errors.append(f"publishers/{pub}: HTTP {status} {_error_message(payload)}")
                break
            for pm in payload.get("publisherModels", []) or []:
                name = str(pm.get("name", ""))
                model_id = name.rsplit("/", 1)[-1]
                if not model_id or not _is_generative(pub, model_id):
                    continue
                stage = str(pm.get("launchStage", "") or "")
                if stage in ("DEPRECATED", "LAUNCH_STAGE_UNSPECIFIED"):
                    continue
                found.append(
                    {
                        "publisher": pub,
                        "model_id": model_id,
                        "version_id": pm.get("versionId"),
                        "launch_stage": stage or "UNKNOWN",
                        "resource_name": name,
                    }
                )
            page_token = str(payload.get("nextPageToken") or "")
            if not page_token:
                break
    return found, errors


def list_deployed_endpoints(
    project_id: str,
    location: str,
    token: str,
    http: Optional[HttpFn] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """List Vertex AI Endpoints (self-deployed Model Garden models) in project/location."""
    if location == "global":
        return [], []
    http_fn = http or _http_json
    host = vertex_host(location)
    url = f"{host}/v1/projects/{project_id}/locations/{location}/endpoints?pageSize=100"
    status, payload = http_fn("GET", url, None, _auth_headers(token, project_id))
    if status != 200:
        return [], [f"endpoints: HTTP {status} {_error_message(payload)}"]
    endpoints: List[Dict[str, Any]] = []
    for ep in payload.get("endpoints", []) or []:
        deployed = ep.get("deployedModels") or []
        if not deployed:
            continue
        dm = deployed[0]
        endpoints.append(
            {
                "endpoint_resource_name": ep.get("name"),
                "endpoint_display_name": ep.get("displayName") or ep.get("name", "").rsplit("/", 1)[-1],
                "deployed_model_display_name": dm.get("displayName") or dm.get("model", "").rsplit("/", 1)[-1],
                "model_resource": dm.get("model"),
            }
        )
    return endpoints, []


def probe_model_access(
    project_id: str,
    location: str,
    publisher: str,
    model_id: str,
    token: str,
    http: Optional[HttpFn] = None,
) -> Dict[str, Any]:
    """Check whether a publisher model is usable from the project.

    Gemini and Anthropic use free token-counting endpoints; other MaaS partners use a
    1-token chat completion (fractions of a cent).
    """
    http_fn = http or _http_json
    host = vertex_host(location)
    headers = _auth_headers(token, project_id)
    base = f"{host}/v1/projects/{project_id}/locations/{location}"

    if publisher == "google":
        url = f"{base}/publishers/google/models/{model_id}:countTokens"
        body: Dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": "ping"}]}]}
        method_label = "countTokens (free)"
    elif publisher == "anthropic":
        url = f"{base}/publishers/anthropic/models/count-tokens:rawPredict"
        body = {"model": model_id, "messages": [{"role": "user", "content": "ping"}]}
        method_label = "count-tokens (free)"
    else:
        url = f"{base}/endpoints/openapi/chat/completions"
        body = {
            "model": f"{publisher}/{model_id}",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        method_label = "1-token chat completion"

    status, payload = http_fn("POST", url, body, headers)
    if status in (200, 429):
        return {"enabled": True, "enablement": "enabled", "detail": f"Verified via {method_label}"}
    msg = _error_message(payload)
    if status in (403, 400) and re.search(r"enable|terms|eula|marketplace|not been used|permission", msg, re.I):
        return {
            "enabled": False,
            "enablement": "not_enabled",
            "detail": f"Not enabled for this project — enable it in Vertex AI Model Garden ({msg})",
        }
    if status == 404:
        return {
            "enabled": False,
            "enablement": "not_available",
            "detail": f"Not available in {location} for this project ({msg})",
        }
    return {"enabled": False, "enablement": "error", "detail": f"HTTP {status}: {msg}"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-") or "model"


def _featured_rank(entry: Dict[str, Any]) -> Tuple[int, str]:
    mid = entry["id"].lower()
    order = [
        ("gemini", "pro"),
        ("gemini", "flash"),
        ("claude", "opus"),
        ("claude", "sonnet"),
        ("mistral", "large"),
        ("llama", ""),
    ]
    for idx, (a, b) in enumerate(order):
        if a in mid and b in mid:
            return idx, mid
    return len(order), mid


def discover_model_garden(
    project_id: str,
    location: str,
    token: Optional[str] = None,
    verify_access: bool = True,
    verify_partner_access: bool = False,
    catalog_prices: Optional[Dict[str, Tuple[float, float]]] = None,
    http: Optional[HttpFn] = None,
    max_featured: int = 5,
) -> Dict[str, Any]:
    """Discover the MIQs usable from ``project_id`` in ``location``.

    Returns a dict with ``models`` (UI/registry-ready entries), ``errors`` and summary counts.
    """
    if token is None:
        token, _ = get_access_token()

    publisher_models, pub_errors = list_publisher_models(project_id, location, token, http=http)
    endpoints, ep_errors = list_deployed_endpoints(project_id, location, token, http=http)

    entries: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for pm in publisher_models:
        pub = pm["publisher"]
        mid = pm["model_id"]
        alias = _slug(mid)
        if alias in seen:
            alias = _slug(f"{pub}-{mid}")
        if alias in seen:
            continue
        seen.add(alias)
        cin, cout, price_src = lookup_price_per_1k(mid, catalog_prices)
        is_first_party = pub == "google"
        entries.append(
            {
                "id": alias,
                "name": _humanize(mid),
                "brand": PUBLISHER_BRANDS.get(pub, "vertex"),
                "provider": PUBLISHER_LABELS.get(pub, f"{pub} (Vertex AI Model Garden)"),
                "publisher": pub,
                "backend_provider": backend_provider_for(pub),
                "model_name": mid if pub in ("google", "anthropic") else f"{pub}/{mid}",
                "source": "model_garden_publisher",
                "launch_stage": pm.get("launch_stage"),
                "badge": "First-Party Gemini" if is_first_party else "Partner / MaaS",
                "tags": [t for t in [pm.get("launch_stage"), "Vertex AI", pub] if t],
                "description": f"{_humanize(mid)} from the Vertex AI Model Garden ({pub}) served in {location}.",
                "cost_per_1k_input_usd": cin,
                "cost_per_1k_output_usd": cout,
                "pricing_source": price_src,
                "location": location,
                "project_id": project_id,
                # Gemini is usable whenever Vertex AI is enabled; partners need explicit enablement.
                "enabled": is_first_party,
                "enablement": "enabled" if is_first_party else "unverified",
                "status_detail": (
                    "First-party model — available with the Vertex AI API"
                    if is_first_party
                    else "Partner model — enable it in Model Garden, then click Verify"
                ),
                "is_default": False,
                "discovered": True,
            }
        )

    for ep in endpoints:
        disp_name = str(ep["deployed_model_display_name"])
        if not is_model_configurable("", disp_name):
            continue
        ep_id = str(ep["endpoint_resource_name"]).rsplit("/", 1)[-1]
        alias = _slug(f"endpoint-{ep['deployed_model_display_name']}-{ep_id[-6:]}")
        if alias in seen:
            continue
        seen.add(alias)
        cin, cout, price_src = lookup_price_per_1k(str(ep["deployed_model_display_name"]), catalog_prices)
        entries.append(
            {
                "id": alias,
                "name": f"{ep['deployed_model_display_name']} (Endpoint)",
                "brand": "vertex",
                "provider": f"Self-deployed Vertex AI Endpoint ({ep['endpoint_display_name']})",
                "publisher": "endpoint",
                "backend_provider": "vertex_endpoint",
                "model_name": ep["deployed_model_display_name"],
                "endpoint_resource_name": ep["endpoint_resource_name"],
                "source": "vertex_endpoint",
                "badge": "Deployed Endpoint",
                "tags": ["Deployed", "Vertex AI Endpoint"],
                "description": f"Model deployed to endpoint {ep['endpoint_display_name']} in {project_id}/{location}.",
                "cost_per_1k_input_usd": cin,
                "cost_per_1k_output_usd": cout,
                "pricing_source": price_src if price_src != "estimate" else "endpoint_compute_billed",
                "location": location,
                "project_id": project_id,
                "enabled": True,
                "enablement": "enabled",
                "status_detail": "Deployed in your project",
                "is_default": False,
                "discovered": True,
            }
        )

    # Optional access verification (Gemini via free countTokens; partners opt-in).
    to_probe = [
        e
        for e in entries
        if e["source"] == "model_garden_publisher"
        and ((e["publisher"] == "google" and verify_access) or (e["publisher"] != "google" and verify_partner_access))
    ]
    if to_probe:
        def _probe(entry: Dict[str, Any]) -> None:
            mid = entry["model_name"].split("/", 1)[-1] if entry["publisher"] not in ("google", "anthropic") else entry["model_name"]
            res = probe_model_access(project_id, location, entry["publisher"], mid, token, http=http)
            entry["enabled"] = bool(res["enabled"])
            entry["enablement"] = res["enablement"]
            entry["status_detail"] = res["detail"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_probe, to_probe))

    enabled_sorted = sorted([e for e in entries if e["enabled"]], key=_featured_rank)
    for e in enabled_sorted[:max_featured]:
        e["is_default"] = True

    entries.sort(key=lambda e: (not e["enabled"], not e["is_default"], _featured_rank(e)))
    return {
        "project_id": project_id,
        "location": location,
        "models": entries,
        "errors": pub_errors + ep_errors,
        "counts": {
            "total": len(entries),
            "enabled": sum(1 for e in entries if e["enabled"]),
            "publisher_models": len(publisher_models),
            "endpoints": len(endpoints),
        },
        "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def registry_entry_for(model: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a discovered model entry into a ``configs/models.yaml``-style registry config."""
    cfg: Dict[str, Any] = {
        "provider": model.get("backend_provider", "vertex_genai"),
        "model_name": model.get("model_name", model["id"]),
        "project_id": model.get("project_id"),
        "location": model.get("location"),
        "cost_per_1k_input_usd": float(model.get("cost_per_1k_input_usd", DEFAULT_PRICE_PER_1K[0])),
        "cost_per_1k_output_usd": float(model.get("cost_per_1k_output_usd", DEFAULT_PRICE_PER_1K[1])),
        "generation_defaults": {"temperature": 0.0, "max_output_tokens": 8192, "seed": 42},
    }
    if model.get("endpoint_resource_name"):
        cfg["endpoint_resource_name"] = model["endpoint_resource_name"]
    return cfg
