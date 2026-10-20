#!/usr/bin/env bash
# ==============================================================================
# Deploy DevBench Evaluation Studio to Google Cloud Run
# ==============================================================================
# Usage:
#   ./scripts/deploy_cloud_run.sh [PROJECT_ID] [REGION] [SERVICE_NAME]
#
# Examples:
#   ./scripts/deploy_cloud_run.sh my-gcp-project us-central1
#   ./scripts/deploy_cloud_run.sh
#
# Security & Multi-Tenancy Guarantee:
#   - Zero hardcoded personal secrets or local credentials are included.
#   - Container runtime service account has MINIMAL hosting permissions (logging only).
#   - The container does NOT have Vertex AI / Agent Platform permissions, ensuring
#     that the host project never incurs model inference costs for visitors.
#   - Each user accessing the studio links their OWN GCP project in the UI to run
#     agent evaluations with their own credentials/quota.
# ==============================================================================

set -euo pipefail

# 1. Resolve project and deployment parameters
PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}}"
REGION="${2:-${GOOGLE_CLOUD_LOCATION:-us-central1}}"
SERVICE_NAME="${3:-devbench-studio}"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Error: No GCP Project ID specified."
  echo "Usage: $0 <PROJECT_ID> [REGION] [SERVICE_NAME]"
  exit 1
fi

echo "=========================================================="
echo " Deploying DevBench Evaluation Studio to Cloud Run"
echo " Project:      ${PROJECT_ID}"
echo " Region:       ${REGION}"
echo " Service Name: ${SERVICE_NAME}"
echo "=========================================================="

# 2. Ensure required Google Cloud services are enabled in target project
echo "--> Enabling required APIs in ${PROJECT_ID}..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="${PROJECT_ID}"

# 3. Create or verify dedicated hosting service account (Zero Vertex AI perms)
SA_NAME="${SERVICE_NAME}-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "--> Creating runtime service account ${SA_EMAIL}..."
  gcloud iam service-accounts create "${SA_NAME}" \
    --project="${PROJECT_ID}" \
    --description="DevBench Studio container runtime service account with minimal hosting permissions" \
    --display-name="DevBench Studio Runtime SA"
fi

# Assign least-privilege logging role
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/logging.logWriter" \
  --condition=None \
  --quiet >/dev/null 2>&1 || true

# 4. Deploy container image via Cloud Build & Cloud Run
echo "--> Building and deploying container to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5 \
  --port 8080 \
  --set-env-vars "HOST=0.0.0.0,DEVBENCH_STATE_DIR=/tmp/devbench_state,GOOGLE_CLOUD_PROJECT=,VERTEX_PROJECT_ID=" \
  --allow-unauthenticated \
  --quiet

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project="${PROJECT_ID}" --region="${REGION}" --format="value(status.url)")

echo "=========================================================="
echo " Deployment Complete!"
echo " Service URL: ${SERVICE_URL}"
echo " Hosting Project: ${PROJECT_ID} (Zero inference cost)"
echo " Users run evaluations against their own linked GCP projects"
echo "=========================================================="
