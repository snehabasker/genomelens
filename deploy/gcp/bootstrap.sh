#!/usr/bin/env bash
# One-time GCP setup: APIs, Artifact Registry, runtime service account, secret.
# Usage: PROJECT_ID=my-proj REGION=us-central1 ANTHROPIC_API_KEY=sk-ant-... ./deploy/gcp/bootstrap.sh
set -euo pipefail
: "${PROJECT_ID:?}" "${ANTHROPIC_API_KEY:?}"
REGION="${REGION:-us-central1}"; SVC=genome-lens
SA="${SVC}-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories describe "$SVC" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$SVC" --repository-format=docker --location "$REGION"

# Least privilege: the runtime identity can only read this one secret.
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 ||
  gcloud iam service-accounts create "${SVC}-run" --display-name "Genome Lens runtime"

if gcloud secrets describe anthropic-api-key >/dev/null 2>&1; then
  printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets versions add anthropic-api-key --data-file=-
else
  printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-
fi
gcloud secrets add-iam-policy-binding anthropic-api-key \
  --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor

# Cloud Build's identity must be allowed to deploy and to act as the runtime SA.
PN=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
CB="${PN}-compute@developer.gserviceaccount.com"
for r in roles/run.admin roles/artifactregistry.writer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$CB" --role "$r" --condition=None >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$SA" --member "serviceAccount:$CB" --role roles/iam.serviceAccountUser
echo "Done. Next: gcloud builds submit --config deploy/gcp/cloudbuild.yaml --substitutions=_OIDC_AUDIENCE=<client-id>"
