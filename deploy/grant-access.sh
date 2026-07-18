#!/usr/bin/env bash
# Grant a Google account access to the Meta Ads Manager Cloud Run service.
# Does NOT enable IAP (use setup-iap-oauth.sh for that).
#
# Usage:
#   ./deploy/grant-access.sh jayshankar.me1@gmail.com

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-vertex-ai-learning-487906}"
REGION="${CLOUD_RUN_REGION:-asia-south1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-meta-ads-manager}"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <email> [email...]"
  exit 1
fi

for EMAIL in "$@"; do
  MEMBER="user:${EMAIL}"
  echo "==> Granting roles/run.invoker to ${EMAIL}"
  gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --member="${MEMBER}" \
    --role="roles/run.invoker" \
    --quiet

  echo "==> Granting roles/iap.httpsResourceAccessor to ${EMAIL}"
  if gcloud alpha iap web add-iam-policy-binding \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --resource-type=cloud-run \
    --service="${SERVICE_NAME}" \
    --member="${MEMBER}" \
    --role="roles/iap.httpsResourceAccessor" \
    --quiet 2>/dev/null; then
    echo "    IAP access granted"
  else
    echo "    WARN: IAP binding failed — install alpha: gcloud components install alpha"
  fi
done

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')"

echo "Done. Access: ${SERVICE_URL}/cmo/"
