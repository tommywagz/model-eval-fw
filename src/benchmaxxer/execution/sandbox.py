"""Execution Mode Switch (--mode mock|live) and Sandbox Environment for BenchMaxxer."""

from __future__ import annotations

import os
from typing import Any, Dict

from benchmaxxer.execution.lifecycle import ResourceLifecycleManager, teardown_fixture
from benchmaxxer.execution.mocks import (
    MockCloudRunService,
    MockGKEVertexService,
    MockIAMOAuthService,
    MockStorageSuiteService,
)


class ExecutionSandbox:
    """Routes GCP operations to hermetic local mocks (`mock`) or live ADC services (`live`)."""

    VALID_MODES = ("mock", "live")

    def __init__(self, mode: str = "mock", project_id: str = "benchmaxxer-eval-sandbox") -> None:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in self.VALID_MODES:
            raise ValueError(
                f"Invalid execution mode '{mode}'. Expected one of {self.VALID_MODES}."
            )
        self.mode = normalized_mode
        self.project_id = project_id

        # Initialize hermetic services
        self.iam_oauth = MockIAMOAuthService()
        self.cloud_run = MockCloudRunService()
        self.storage = MockStorageSuiteService()
        self.gke_vertex = MockGKEVertexService()

    def verify_credentials_if_live(self) -> Dict[str, Any]:
        """Verify Application Default Credentials (ADC) when running in live mode."""
        if self.mode == "mock":
            return {"mode": "mock", "adc_required": False, "authenticated": True}

        adc_env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if adc_env and os.path.exists(adc_env):
            return {
                "mode": "live",
                "adc_required": True,
                "authenticated": True,
                "credentials_source": adc_env,
            }

        try:
            import google.auth  # type: ignore

            creds, proj = google.auth.default()
            return {
                "mode": "live",
                "adc_required": True,
                "authenticated": creds is not None,
                "detected_project": proj or self.project_id,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "mode": "live",
                "adc_required": True,
                "authenticated": False,
                "error": str(exc),
            }

    def lifecycle_scope(self):
        """Return a `teardown_fixture` context manager bound to this sandbox's execution mode."""
        return teardown_fixture(mode=self.mode)
