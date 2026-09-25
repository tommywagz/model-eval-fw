"""Tests for Pillar 4: Tiered Execution (Hermetic Mocks vs. Live GCP Sandboxing) & Teardown Harness."""

from __future__ import annotations

import pytest

from benchmaxxer.execution import ExecutionSandbox, teardown_fixture


def test_execution_sandbox_mode_switch() -> None:
    mock_sandbox = ExecutionSandbox(mode="mock")
    assert mock_sandbox.mode == "mock"
    assert mock_sandbox.verify_credentials_if_live()["adc_required"] is False

    live_sandbox = ExecutionSandbox(mode="live")
    assert live_sandbox.mode == "live"
    assert live_sandbox.verify_credentials_if_live()["adc_required"] is True

    with pytest.raises(ValueError):
        ExecutionSandbox(mode="invalid-mode")


def test_teardown_fixture_destroys_resources_on_success() -> None:
    sandbox = ExecutionSandbox(mode="mock")
    with teardown_fixture(mode="mock") as lifecycle:
        sandbox.cloud_run.deploy_service("svc-alpha", "gcr.io/demo/alpha:v1")
        lifecycle.register(
            "cloud_run",
            "svc-alpha",
            lambda: sandbox.cloud_run.delete_service("svc-alpha"),
        )
        sandbox.gke_vertex.create_gke_cluster("swarm-cluster")
        lifecycle.register(
            "gke_cluster",
            "swarm-cluster",
            lambda: sandbox.gke_vertex.delete_gke_cluster("swarm-cluster"),
        )
        assert "svc-alpha" in sandbox.cloud_run.services
        assert "swarm-cluster" in sandbox.gke_vertex.gke_clusters

    assert lifecycle.all_destroyed is True
    assert "svc-alpha" not in sandbox.cloud_run.services
    assert "swarm-cluster" not in sandbox.gke_vertex.gke_clusters


def test_teardown_fixture_guarantees_cleanup_on_assertion_failure() -> None:
    sandbox = ExecutionSandbox(mode="mock")
    captured_lifecycle = None

    with pytest.raises(AssertionError):
        with teardown_fixture(mode="mock") as lifecycle:
            captured_lifecycle = lifecycle
            sandbox.cloud_run.deploy_service("svc-failing", "gcr.io/demo/fail:v1")
            lifecycle.register(
                "cloud_run",
                "svc-failing",
                lambda: sandbox.cloud_run.delete_service("svc-failing"),
            )
            sandbox.gke_vertex.mount_filestore("tpu-dataset-mount")
            lifecycle.register(
                "filestore",
                "tpu-dataset-mount",
                lambda: sandbox.gke_vertex.unmount_filestore("tpu-dataset-mount"),
            )
            # Simulate an assertion failure mid-test
            assert False, "Deliberate test assertion failure during deployment verification"

    assert captured_lifecycle is not None
    assert captured_lifecycle.all_destroyed is True
    assert "svc-failing" not in sandbox.cloud_run.services
    assert "tpu-dataset-mount" not in sandbox.gke_vertex.filestore_mounts
