#!/bin/bash
# Simple deployment script for the OCR backend on Google Cloud

# Usage: ./deploy.sh <project-id> <bucket-name> <processor-id> [processor-location]
# Example: ./deploy.sh axon-tbi-automation tbi-ocr-uploads 26145f8a54ef762a us

set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <project-id> <bucket-name> <processor-id> [processor-location]" >&2
  exit 1
fi

PROJECT_ID="$1"
BUCKET_NAME="$2"
PROCESSOR_ID="$3"
PROCESSOR_LOCATION="${4:-us}"

echo "\nCreating Cloud Storage bucket (if it does not already exist)…"
gsutil ls -b "gs://${BUCKET_NAME}" >/dev/null 2>&1 || gsutil mb -l "${PROCESSOR_LOCATION}" -p "${PROJECT_ID}" "gs://${BUCKET_NAME}"

echo "\nBuilding container image…"
gcloud builds submit --tag "gcr.io/${PROJECT_ID}/ocr-backend" ./ocr_app

echo "\nDeploying Cloud Run service…"
gcloud run deploy tbi-backend \
  --image "gcr.io/${PROJECT_ID}/ocr-backend" \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "PROJECT_ID=${PROJECT_ID},PROCESSOR_ID=${PROCESSOR_ID},PROCESSOR_LOCATION=${PROCESSOR_LOCATION},BUCKET_NAME=${BUCKET_NAME}"

echo "\nDeployment complete. Remember to grant the Cloud Run service account the roles: Document AI API User, Storage Object Admin, and Datastore User."