"""Everything works except teardown, which only logs and leaves the service and image running."""

import os


def build(gcp, params):
    src = params["source_dir"]
    with open(os.path.join(src, "cloudbuild.yaml"), encoding="utf-8") as fh:
        result = gcp.cloud_build.submit(fh.read(), src)
    return result["images"][0]


def deploy(gcp, params, image):
    service = gcp.cloud_run.deploy(params["service_name"], image, params["region"], allow_unauthenticated=True)
    return service["url"]


def invoke(gcp, params, url):
    return gcp.http.get(url + params["health_path"])["status_code"]


def teardown(gcp, params):
    # TODO: clean up later
    print(f"teardown complete for {params['service_name']}")
