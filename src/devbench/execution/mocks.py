"""Hermetic local mocks for GCP APIs (Cloud Run, IAM/OAuth, GCS, BigQuery, Firestore, GKE, Vertex AI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProvisionedResource:
    """Represents a cloud resource tracked by the sandbox and teardown harness."""

    resource_type: str
    resource_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    destroyed: bool = False


class MockIAMOAuthService:
    """Hermetic mock for GCP IAM permissions, API enablement, and OAuth 2.0 scopes."""

    def __init__(self) -> None:
        self.enabled_apis: List[str] = []
        self.granted_roles: Dict[str, List[str]] = {}
        self.oauth_scopes: List[str] = []

    def enable_api(self, api_name: str) -> bool:
        if not api_name.endswith(".googleapis.com"):
            return False
        if api_name not in self.enabled_apis:
            self.enabled_apis.append(api_name)
        return True

    def grant_iam_role(self, member: str, role: str) -> bool:
        if not role.startswith("roles/") or "wildcard" in role or role == "roles/owner_all_wildcards":
            return False
        self.granted_roles.setdefault(member, []).append(role)
        return True

    def configure_oauth_scopes(self, scopes: List[str]) -> bool:
        if not scopes or any(not s.startswith("https://www.googleapis.com/auth/") for s in scopes):
            return False
        self.oauth_scopes = list(scopes)
        return True


class MockCloudRunService:
    """Hermetic mock for Cloud Run microservice deployment, health checks, and teardown."""

    def __init__(self) -> None:
        self.services: Dict[str, Dict[str, Any]] = {}

    def deploy_service(self, service_name: str, image: str, region: str = "us-central1") -> Dict[str, Any]:
        record = {
            "service_name": service_name,
            "image": image,
            "region": region,
            "url": f"https://{service_name}-mock.a.run.app",
            "status": "READY",
        }
        self.services[service_name] = record
        return record

    def invoke_health_check(self, service_name: str) -> Dict[str, Any]:
        if service_name not in self.services or self.services[service_name]["status"] != "READY":
            return {"status_code": 503, "healthy": False}
        return {"status_code": 200, "healthy": True}

    def delete_service(self, service_name: str) -> bool:
        if service_name in self.services:
            self.services[service_name]["status"] = "DELETED"
            del self.services[service_name]
            return True
        return False


class MockStorageSuiteService:
    """Hermetic mock for BigQuery, GCS buckets, and Firestore document storage."""

    def __init__(self) -> None:
        self.gcs_objects: Dict[str, Any] = {}
        self.bq_tables: Dict[str, List[Dict[str, Any]]] = {}
        self.firestore_docs: Dict[str, Dict[str, Any]] = {}

    def gcs_upload_json(self, uri: str, payload: Dict[str, Any]) -> bool:
        self.gcs_objects[uri] = payload
        return True

    def gcs_download_json(self, uri: str) -> Optional[Dict[str, Any]]:
        return self.gcs_objects.get(uri)

    def bq_insert_rows(self, table_id: str, rows: List[Dict[str, Any]]) -> bool:
        self.bq_tables.setdefault(table_id, []).extend(rows)
        return True

    def bq_query(self, sql: str) -> List[Dict[str, Any]]:
        return [
            {"metric": "latency_p95", "value": 42.5},
            {"metric": "error_rate", "value": 0.0},
            {"metric": "throughput_qps", "value": 1250.0},
        ]

    def firestore_set_doc(self, collection: str, doc_id: str, data: Dict[str, Any]) -> bool:
        self.firestore_docs[f"{collection}/{doc_id}"] = data
        return True

    def firestore_get_doc(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        return self.firestore_docs.get(f"{collection}/{doc_id}")


class MockGKEVertexService:
    """Hermetic mock for GKE clusters, Filestore mounts, TPU nodes, and Vertex AI Vector Search."""

    def __init__(self) -> None:
        self.gke_clusters: Dict[str, Dict[str, Any]] = {}
        self.vector_indexes: Dict[str, Dict[str, Any]] = {}
        self.filestore_mounts: Dict[str, Dict[str, Any]] = {}

    def create_gke_cluster(self, cluster_name: str, num_nodes: int = 3) -> Dict[str, Any]:
        info = {"cluster_name": cluster_name, "num_nodes": num_nodes, "status": "RUNNING"}
        self.gke_clusters[cluster_name] = info
        return info

    def delete_gke_cluster(self, cluster_name: str) -> bool:
        return self.gke_clusters.pop(cluster_name, None) is not None

    def create_vector_index(self, index_name: str, dimensions: int = 768) -> Dict[str, Any]:
        info = {"index_name": index_name, "dimensions": dimensions, "status": "DEPLOYED"}
        self.vector_indexes[index_name] = info
        return info

    def delete_vector_index(self, index_name: str) -> bool:
        return self.vector_indexes.pop(index_name, None) is not None

    def mount_filestore(self, mount_name: str, share_path: str = "/mnt/filestore") -> Dict[str, Any]:
        info = {"mount_name": mount_name, "share_path": share_path, "mounted": True}
        self.filestore_mounts[mount_name] = info
        return info

    def unmount_filestore(self, mount_name: str) -> bool:
        return self.filestore_mounts.pop(mount_name, None) is not None
