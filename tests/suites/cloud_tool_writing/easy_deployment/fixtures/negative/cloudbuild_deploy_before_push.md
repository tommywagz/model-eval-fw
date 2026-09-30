Cloud Build handles both the build and the rollout, so the tool stays thin.

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
USER nobody
EXPOSE 8080
CMD ["python", "main.py"]
```

```yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args: ["build", "-t", "gcr.io/$PROJECT_ID/inventory-api:v1", "."]
  # Deploy right after the build; the image gets pushed via `images:` below.
  - name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args: ["run", "deploy", "inventory-api", "--image", "gcr.io/$PROJECT_ID/inventory-api:v1",
           "--region", "us-central1", "--platform", "managed", "--allow-unauthenticated"]
images:
  - gcr.io/$PROJECT_ID/inventory-api:v1
```

```python
import os


def build(gcp, params):
    src = params["source_dir"]
    with open(os.path.join(src, "cloudbuild.yaml"), encoding="utf-8") as fh:
        result = gcp.cloud_build.submit(fh.read(), src)
    return result["images"][0]


def deploy(gcp, params, image):
    service = gcp.cloud_run.get(params["service_name"], params["region"])
    if service is None:
        raise RuntimeError("Cloud Build did not deploy the service")
    return service["url"]


def invoke(gcp, params, url):
    return gcp.http.get(url + params["health_path"])["status_code"]


def teardown(gcp, params):
    for svc in gcp.cloud_run.list():
        gcp.cloud_run.delete(svc["name"], svc["region"])
    for img in gcp.artifact_registry.list_images():
        gcp.artifact_registry.delete_image(img["uri"])
```
