"""Deployment tool that pins the Cloud Run service to an immutable image digest."""

import os

REGISTRY_REPO = "gcr.io/{project}/inventory-api"


def build(gcp, params):
    source_dir = params["source_dir"]
    with open(os.path.join(source_dir, "cloudbuild.yaml"), encoding="utf-8") as fh:
        result = gcp.cloud_build.submit(fh.read(), source_dir)
    stable = next(img for img in result["results"]["images"] if img["name"].endswith(":stable"))
    repo = stable["name"].rsplit(":", 1)[0]
    return f"{repo}@{stable['digest']}"  # digest reference: immune to tag moves


def deploy(gcp, params, image):
    service = gcp.cloud_run.deploy(
        params["service_name"],
        image,
        region=params["region"],
        port=params["container_port"],
        allow_unauthenticated=True,
        env={"APP_ENV": "production"},
    )
    if service["status"] != "READY":
        raise RuntimeError(f"service not ready: {service}")
    return service["url"]


def invoke(gcp, params, url):
    return gcp.http.get(url + params["health_path"], timeout=2.0)["status_code"]


def teardown(gcp, params):
    errors = []
    service = gcp.cloud_run.get(params["service_name"], params["region"])
    if service is not None:
        gcp.cloud_run.delete(service["name"], service["region"])
    repo = REGISTRY_REPO.format(project=params["project_id"])
    for image in gcp.artifact_registry.list_images():
        if image["repository"] == repo:
            gcp.artifact_registry.delete_image(image["uri"])
        else:
            errors.append(image["uri"])
    if errors or gcp.cloud_run.list():
        raise RuntimeError(f"unexpected leftovers: {errors}")
