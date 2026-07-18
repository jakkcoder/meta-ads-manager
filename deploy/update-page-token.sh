#!/usr/bin/env bash
# Fetch Page Access Token from Meta and update Secret Manager + optional .env
#
# Usage:
#   ./deploy/update-page-token.sh
#   ./deploy/update-page-token.sh --no-env   # skip local .env update

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-vertex-ai-learning-487906}"
REGION="${CLOUD_RUN_REGION:-asia-south1}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-meta-ads-manager}"
UPDATE_ENV=1

if [[ "${1:-}" == "--no-env" ]]; then
  UPDATE_ENV=0
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

PAGE_TOKEN="$(python -c "
from app.config import get_settings
from app.meta.client import MetaClient

s = get_settings()
c = MetaClient(s)
pages = c.get_pages()
page_id = s.page_id or '347244005670587'
page = next(p for p in pages if p['id'] == page_id)
print(page['access_token'])
")"

echo "==> Updating PAGE_ACCESS_TOKEN secret (version added)"
printf '%s' "${PAGE_TOKEN}" | gcloud secrets versions add PAGE_ACCESS_TOKEN \
  --project="${PROJECT_ID}" \
  --data-file=-

if [[ "${UPDATE_ENV}" -eq 1 && -f .env ]]; then
  PAGE_TOKEN_FOR_UPDATE="${PAGE_TOKEN}" python -c "
import os
from pathlib import Path
token = os.environ['PAGE_TOKEN_FOR_UPDATE']
p = Path('.env')
lines = []
for line in p.read_text().splitlines():
    if line.startswith('PAGE_ACCESS_TOKEN='):
        lines.append(f'PAGE_ACCESS_TOKEN={token}')
    else:
        lines.append(line)
p.write_text('\n'.join(lines) + '\n')
"
  echo "==> Updated .env PAGE_ACCESS_TOKEN"
fi

echo "==> Rolling Cloud Run to pick up new secret"
gcloud run services update "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --update-secrets="Meta_Access_token=Meta_Access_token:latest,PAGE_ACCESS_TOKEN=PAGE_ACCESS_TOKEN:latest" \
  --quiet

echo "Done. Retry Pull Leads / Pull All on the dashboard."
