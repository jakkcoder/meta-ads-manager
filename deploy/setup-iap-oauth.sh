#!/usr/bin/env bash
# Configure IAP OAuth credentials for Cloud Run (fixes "Empty OAuth client ID/secret").
#
# You must create an OAuth Web client in the console FIRST (one-time, ~2 min):
#   https://console.cloud.google.com/auth/clients?project=vertex-ai-learning-487906
#
#   1. Configure consent screen if prompted (External, add test users)
#   2. Create client → Web application → name "Meta Ads Manager IAP"
#   3. Authorized redirect URI (replace CLIENT_ID after create):
#        https://iap.googleapis.com/v1/oauth/clientIds/CLIENT_ID:handleRedirect
#   4. Copy Client ID and Client secret
#
# Then run:
#   ./deploy/setup-iap-oauth.sh YOUR_CLIENT_ID YOUR_CLIENT_SECRET
#   ./deploy/setup-iap-oauth.sh YOUR_CLIENT_ID YOUR_CLIENT_SECRET jayshankar.me1@gmail.com
#
# Or via env:
#   IAP_OAUTH_CLIENT_ID=... IAP_OAUTH_CLIENT_SECRET=... ./deploy/setup-iap-oauth.sh

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-vertex-ai-learning-487906}"
REGION="${CLOUD_RUN_REGION:-asia-south1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-meta-ads-manager}"

CLIENT_ID="${1:-${IAP_OAUTH_CLIENT_ID:-${CLIENT_ID:-}}}"
CLIENT_SECRET="${2:-${IAP_OAUTH_CLIENT_SECRET:-${CLIENT_SECRET:-}}}"
shift 2 2>/dev/null || true
EMAILS=("$@")

# Load from .env in repo root if still empty
if [[ -z "${CLIENT_ID}" || -z "${CLIENT_SECRET}" ]]; then
  ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"
  if [[ -f "${ENV_FILE}" ]]; then
    CLIENT_ID="${CLIENT_ID:-$(grep '^CLIENT_ID=' "${ENV_FILE}" | cut -d= -f2- | xargs)}"
    CLIENT_SECRET="${CLIENT_SECRET:-$(grep '^CLIENT_SECRET=' "${ENV_FILE}" | cut -d= -f2- | xargs)}"
  fi
fi

if [[ -z "${CLIENT_ID}" || -z "${CLIENT_SECRET}" ]]; then
  echo "Usage: $0 CLIENT_ID CLIENT_SECRET [email...]"
  echo "   or: IAP_OAUTH_CLIENT_ID=... IAP_OAUTH_CLIENT_SECRET=... $0 [email...]"
  exit 1
fi

if [[ ${#EMAILS[@]} -eq 0 ]]; then
  EMAILS=("jayshankar.me1@gmail.com")
fi

echo "==> Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  iap.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="${PROJECT_ID}" \
  --quiet

SETTINGS_FILE="$(mktemp)"
trap 'rm -f "${SETTINGS_FILE}"' EXIT

cat > "${SETTINGS_FILE}" <<EOF
access_settings:
  oauth_settings:
    client_id: ${CLIENT_ID}
    client_secret: ${CLIENT_SECRET}
EOF

echo "==> Applying IAP OAuth settings at project level"
gcloud iap settings set "${SETTINGS_FILE}" --project="${PROJECT_ID}" --quiet

echo "==> Enabling IAP on Cloud Run service ${SERVICE_NAME}"
gcloud beta run services update "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --iap \
  --quiet

for EMAIL in "${EMAILS[@]}"; do
  echo "==> Granting run.invoker to ${EMAIL}"
  gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --member="user:${EMAIL}" \
    --role="roles/run.invoker" \
    --quiet

  echo "==> Granting IAP access to ${EMAIL}"
  gcloud alpha iap web add-iam-policy-binding \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --resource-type=cloud-run \
    --service="${SERVICE_NAME}" \
    --member="user:${EMAIL}" \
    --role="roles/iap.httpsResourceAccessor" \
    --quiet
done

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.url)')"

cat <<EOF

IAP OAuth configured. Users can sign in at:

  ${SERVICE_URL}/cmo/

Allowlist more users anytime:
  ./deploy/grant-access.sh other@gmail.com

EOF
