# Cloud Run deployment for Meta Ads Manager + CMO Dashboard
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project vertex-ai-learning-487906
#
# Usage:
#   ./deploy/deploy.sh

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-vertex-ai-learning-487906}"
REGION="${CLOUD_RUN_REGION:-asia-south1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-meta-ads-manager}"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
SERVICE_ACCOUNT="${CLOUD_RUN_SA:-meta-ads-manager-sa}"
BUCKET="${GCS_LEADS_BUCKET:-vertex-ai-learning-487906-gharka-leads}"
SCHEDULER_JOB="${SCHEDULER_JOB:-meta-sync-hourly}"

echo "==> Enabling required APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com --quiet

echo "==> Building image ${IMAGE}"
gcloud builds submit --tag "${IMAGE}" .

echo "==> Ensuring service account ${SERVICE_ACCOUNT}"
if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
    --display-name="Meta Ads Manager Cloud Run"
fi

SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> Granting GCS access on gs://${BUCKET}"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin" \
  --quiet

echo "==> Granting Cloud Run viewer (list all services for /services page)"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.viewer" \
  --quiet

echo "==> Granting Secret Manager access"
for SECRET in Meta_Access_token PAGE_ACCESS_TOKEN; do
  if gcloud secrets describe "${SECRET}" >/dev/null 2>&1; then
    gcloud secrets add-iam-policy-binding "${SECRET}" \
      --member="serviceAccount:${SA_EMAIL}" \
      --role="roles/secretmanager.secretAccessor" \
      --quiet
  else
    echo "WARN: Secret ${SECRET} not found — create it before production deploy"
  fi
done

echo "==> Deploying Cloud Run service ${SERVICE_NAME}"
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --service-account "${SA_EMAIL}" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 3 \
  --no-allow-unauthenticated \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GCS_LEADS_BUCKET=${BUCKET},GCS_LEADS_PREFIX=meta-ads/leads,GCS_INSIGHTS_PREFIX=meta-ads/insights/daily,GCS_MANIFEST_PATH=meta-ads/manifest.json,GCS_STRUCTURE_PATH=meta-ads/structure/snapshot.json,GCS_EXPORTS_PREFIX=meta-ads/exports,GCS_TUTORS_URL=https://storage.googleapis.com/${BUCKET}/meta-ads/leads/tutors.json,GCS_PARENTS_URL=https://storage.googleapis.com/${BUCKET}/meta-ads/leads/parents.json,AD_ACCOUNT_ID=1579547858935909,PAGE_ID=347244005670587,META_API_VERSION=v25.0,SYNC_LEADS_INTERVAL_MINUTES=15,SYNC_INSIGHTS_INTERVAL_MINUTES=60,INSIGHTS_BACKFILL_DAYS=90,INSIGHTS_OVERLAP_DAYS=3,LEADS_OVERLAP_SECONDS=3600,TRACKED_CAMPAIGN_PREFIXES=Gharkaguru_" \
  --set-secrets "Meta_Access_token=Meta_Access_token:latest,PAGE_ACCESS_TOKEN=PAGE_ACCESS_TOKEN:latest"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.url)')"
echo "==> Deployed: ${SERVICE_URL}"
echo "==> CMO Dashboard: ${SERVICE_URL}/cmo/"

# `gcloud run deploy` does not support --iap and silently drops IAP from the
# service config, which breaks Google-login access. Re-assert it every deploy.
echo "==> Re-enabling IAP on ${SERVICE_NAME}"
gcloud beta run services update "${SERVICE_NAME}" \
  --region "${REGION}" \
  --iap \
  --quiet

echo "==> Creating Cloud Scheduler job ${SCHEDULER_JOB}"
if gcloud scheduler jobs describe "${SCHEDULER_JOB}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULER_JOB}" \
    --location="${REGION}" \
    --schedule="0 * * * *" \
    --uri="${SERVICE_URL}/api/sync/all?export=true" \
    --http-method=POST \
    --oidc-service-account-email="${SA_EMAIL}" \
    --oidc-token-audience="${SERVICE_URL}" \
    --quiet
else
  gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
    --location="${REGION}" \
    --schedule="0 * * * *" \
    --uri="${SERVICE_URL}/api/sync/all?export=true" \
    --http-method=POST \
    --oidc-service-account-email="${SA_EMAIL}" \
    --oidc-token-audience="${SERVICE_URL}" \
    --quiet
fi

gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.invoker" \
  --quiet

cat <<EOF

Next steps — IAP (allowlisted emails):
  1. Open: https://console.cloud.google.com/security/iap?project=${PROJECT_ID}
  2. Enable IAP for Cloud Run service ${SERVICE_NAME}
  3. Add allowlisted users (e.g. jayudemy23@gmail.com)
  4. Configure OAuth consent screen if prompted

Dashboard URL (after IAP):
  ${SERVICE_URL}/cmo/

EOF
