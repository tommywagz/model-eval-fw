"""Resource Teardown & Lifecycle Harness (teardown_fixture) for BenchMaxxer."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Tuple

from benchmaxxer.execution.mocks import ProvisionedResource


@dataclass
class ResourceLifecycleManager:
    """Tracks provisioned resources and guarantees cleanup in LIFO order."""

    mode: str = "mock"
    provisioned: List[ProvisionedResource] = field(default_factory=list)
    cleanup_callbacks: List[Tuple[ProvisionedResource, Callable[[], Any]]] = field(
        default_factory=list
    )
    teardown_log: List[Dict[str, Any]] = field(default_factory=list)
    teardown_completed: bool = False
    errors_during_teardown: List[str] = field(default_factory=list)

    def register(
        self,
        resource_type: str,
        resource_id: str,
        cleanup_fn: Callable[[], Any],
        metadata: Dict[str, Any] | None = None,
    ) -> ProvisionedResource:
        """Register a provisioned resource and its cleanup callback."""
        resource = ProvisionedResource(
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
            destroyed=False,
        )
        self.provisioned.append(resource)
        self.cleanup_callbacks.append((resource, cleanup_fn))
        return resource

    def teardown_all(self) -> List[Dict[str, Any]]:
        """Destroy all registered resources in reverse order of creation."""
        for resource, callback in reversed(self.cleanup_callbacks):
            if resource.destroyed:
                continue
            try:
                callback()
                resource.destroyed = True
                self.teardown_log.append(
                    {
                        "resource_type": resource.resource_type,
                        "resource_id": resource.resource_id,
                        "status": "DESTROYED",
                        "mode": self.mode,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                err_msg = f"Failed to teardown {resource.resource_type}:{resource.resource_id}: {exc}"
                self.errors_during_teardown.append(err_msg)
                self.teardown_log.append(
                    {
                        "resource_type": resource.resource_type,
                        "resource_id": resource.resource_id,
                        "status": "ERROR",
                        "error": str(exc),
                        "mode": self.mode,
                    }
                )
        self.teardown_completed = True
        return self.teardown_log

    @property
    def all_destroyed(self) -> bool:
        return self.teardown_completed and all(r.destroyed for r in self.provisioned)


@contextmanager
def teardown_fixture(mode: str = "mock") -> Iterator[ResourceLifecycleManager]:
    """Context manager guaranteeing that all provisioned resources are destroyed
    even if an assertion fails or execution is interrupted.
    """
    manager = ResourceLifecycleManager(mode=mode)
    try:
        yield manager
    finally:
        manager.teardown_all()
