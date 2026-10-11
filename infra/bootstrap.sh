#!/usr/bin/env bash
# One-time setup that has to exist before OpenTofu can run:
# the APIs OpenTofu itself calls, and the bucket that stores its state.
# Usage: ./bootstrap.sh <project-id> [region]
set -euo pipefail

PROJECT="${1:?usage: ./bootstrap.sh <project-id> [region]}"
REGION="${2:-asia-southeast1}"
BUCKET="${PROJECT}-tfstate"

gcloud services enable --project "$PROJECT" \
  serviceusage.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  storage.googleapis.com

if ! gcloud storage buckets describe "gs://${BUCKET}" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET}" --project "$PROJECT" \
    --location "$REGION" --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://${BUCKET}" --versioning

echo "Ready. Next: tofu init && tofu plan"
