"""HTTP handlers for inventory-api (stdlib only)."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, Optional, Type


def load_config(path: str) -> Optional[Dict[str, Any]]:
    """Return the parsed settings, or None when the file is missing or invalid (service stays unhealthy)."""
    if not os.path.isfile(path):
        print(f"config not found: {path}", file=sys.stderr, flush=True)
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"config unreadable: {exc}", file=sys.stderr, flush=True)
        return None
    return data if isinstance(data, dict) else None


def make_handler(config: Optional[Dict[str, Any]]) -> Type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "inventory-api/1.0"

        def _send(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http.server naming
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                if config is None:
                    self._send(503, {"status": "unavailable", "reason": "config/settings.json not loaded"})
                else:
                    self._send(200, {"status": "ok", "service": config.get("service_name"), "version": config.get("version")})
            elif path == "/":
                self._send(200, {"service": (config or {}).get("service_name", "inventory-api"), "message": "hello from Cloud Run"})
            elif path == "/items" and config is not None:
                self._send(200, {"items": config.get("items", [])})
            else:
                self._send(404, {"error": "not found", "path": path})

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("request: " + (fmt % args) + "\n")

    return Handler
