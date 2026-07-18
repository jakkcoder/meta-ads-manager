# Meta Ads Manager

Private tooling to manage Meta (Facebook) ad account `act_1579547858935909` via the Marketing API. Syncs campaigns, ad sets, ads, lead-gen leads, and **daily insights** into GCS with an interactive **CMO Dashboard** for spend and conversion optimization.

**Production (Cloud Run):** https://meta-ads-manager-lmquvtnfja-el.a.run.app  
**CMO Dashboard:** https://meta-ads-manager-lmquvtnfja-el.a.run.app/cmo/  
*(Requires IAP — see [deploy/iap-setup.md](deploy/iap-setup.md))*

## Features

- Incremental sync of campaigns, ad sets, and ads
- Incremental lead polling from Lead Gen forms (upserted by lead ID, overlap window to avoid misses)
- **Meta Insights sync** — daily spend, leads, CPL, CTR time series → GCS Parquet (partition merge, no data loss)
- **CMO Dashboard** (`/cmo/`) — Plotly Dash + Bootstrap UI with KPI deltas, sparklines, and drill-down charts
- **Background sync jobs** — non-blocking pull with live progress bar
- GCS export: `tutors.json` + `parents.json` + daily insights partitions
- Web dashboard: overview, leads table, ads tree with pause/activate
- REST API for programmatic access and Cloud Scheduler
- Typer CLI for cron jobs and scripting
- Cloud Run deployment (asia-south1) with IAP + hourly auto-sync

## Quick start (local)

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in values. For GCS access locally:

```bash
gcloud auth application-default login
gcloud config set project vertex-ai-learning-487906
```

Key variables:

```env
Meta_Access_token=your_token
GCS_LEADS_BUCKET=vertex-ai-learning-487906-gharka-leads
GOOGLE_CLOUD_PROJECT=vertex-ai-learning-487906
PAGE_ID=347244005670587
```

### 3. Initialize database

```bash
mkdir -p data
alembic upgrade head
```

### 4. Verify Meta API connection

```bash
python cli.py health
python cli.py check-permissions
```

### 5. Sync data

```bash
# Incremental pipeline: ads + leads + insights → GCS
python cli.py sync all --export

# Or individually:
python cli.py sync ads
python cli.py sync leads --export
python cli.py sync insights
```

### 6. Start the app

```bash
uvicorn app.main:app --reload --port 8080
```

| URL | Description |
|-----|-------------|
| http://localhost:8080 | Overview dashboard |
| http://localhost:8080/cmo/ | **CMO Dashboard** (interactive charts) |
| http://localhost:8080/leads | Leads table |
| http://localhost:8080/ads | Ads tree |

## CMO Dashboard

Interactive Plotly Dash app at `/cmo/` with six sections:

| Tab | Content |
|-----|---------|
| **Executive** | KPI cards (deltas + sparklines), spend vs leads, rolling CPL |
| **Campaigns** | CPL trends, spend share, budget gauges, period comparison |
| **Funnel** | Impressions → clicks → leads, CTR/CPC trends, weekday heatmap |
| **Leads** | Tutor vs parent volume, cumulative curve, recent leads table |
| **Ad Performance** | Top ads chart + sortable ad-level table with CPL formatting |
| **Data Ops** | Manifest, sync job history, GCS file links |

**Sync buttons (top bar):**

| Button | Action |
|--------|--------|
| **Pull All → GCS** | Incremental background job: ads structure → leads → insights → export |
| **Pull Insights** | Incremental Meta insights → GCS parquet (3-day overlap, partition merge) |
| **Pull Leads** | Incremental leads sync + export tutors/parents JSON |

Sync runs in a **background thread** with an animated progress bar — the UI never blocks during Meta API calls.

## GCS data layout

```
gs://vertex-ai-learning-487906-gharka-leads/meta-ads/
  manifest.json              # cursors, last_sync, job status
  structure/snapshot.json
  insights/daily/date=YYYY-MM-DD.parquet
  leads/tutors.json
  leads/parents.json
  exports/insights_report_*.parquet
```

## CLI commands

| Command | Description |
|---------|-------------|
| `python cli.py health` | Verify Meta API connectivity |
| `python cli.py sync all --export` | Incremental sync ads + leads + insights → GCS |
| `python cli.py sync insights` | Incremental insights sync |
| `python cli.py sync insights --full` | 90-day backfill |
| `python cli.py sync leads --export` | Leads sync + GCS export |
| `python cli.py sync export-leads` | Export local leads to GCS only |
| `python cli.py sync ads` | Ads sync + structure snapshot |
| `python cli.py ad pause <ad_id>` | Pause an ad |
| `python cli.py ad activate <ad_id>` | Activate an ad |

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/sync/status` | GET | GCS manifest / last sync times |
| `/api/sync/job` | GET | Current background sync job status |
| `/api/sync/job` | POST | Start background job `{type: "insights"\|"leads"\|"all"}` |
| `/api/sync/all` | POST | Sync ads + leads + insights (+ export) |
| `/api/sync/insights` | POST | Incremental insights sync |
| `/api/sync/leads` | POST | Leads sync (+ GCS export) |
| `/api/sync/ads` | POST | Ads sync + structure snapshot |
| `/api/ads/campaigns` | GET | List campaigns |
| `/api/leads` | GET | List leads |
| `/api/leads/export.csv` | GET | Export leads as CSV |

## Cloud Run deployment

### Prerequisites

```bash
gcloud auth login
gcloud config set project vertex-ai-learning-487906
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com
```

### Secrets (create once)

Store tokens in Secret Manager (never commit `.env`):

```bash
# From your local .env values:
printf '%s' "$Meta_Access_token" | gcloud secrets create Meta_Access_token \
  --replication-policy=automatic --data-file=-

printf '%s' "$PAGE_ACCESS_TOKEN" | gcloud secrets create PAGE_ACCESS_TOKEN \
  --replication-policy=automatic --data-file=-
```

If `PAGE_ACCESS_TOKEN` is empty locally, the deploy script falls back to the Meta token for lead form access.

### One-command deploy

```bash
./deploy/deploy.sh
```

This will:

1. Build and push the container to `gcr.io/vertex-ai-learning-487906/meta-ads-manager`
2. Create service account `meta-ads-manager-sa` with GCS + Secret Manager access
3. Deploy Cloud Run (`meta-ads-manager`, 1 GiB RAM, 300s timeout, **no public access**)
4. Create Cloud Scheduler hourly job → `POST /api/sync/all?export=true`

Override defaults with env vars: `GOOGLE_CLOUD_PROJECT`, `CLOUD_RUN_REGION`, `GCS_LEADS_BUCKET`, etc.

### Current deployment

| Setting | Value |
|---------|-------|
| Service | `meta-ads-manager` |
| Region | `asia-south1` |
| URL | https://meta-ads-manager-lmquvtnfja-el.a.run.app |
| CMO Dashboard | https://meta-ads-manager-lmquvtnfja-el.a.run.app/cmo/ |
| Scheduler | `meta-sync-hourly` — every hour, incremental sync |
| Service account | `meta-ads-manager-sa@vertex-ai-learning-487906.iam.gserviceaccount.com` |

### IAP (required for dashboard access)

See [deploy/iap-setup.md](deploy/iap-setup.md):

1. Enable IAP on the Cloud Run service
2. Allowlist business team emails (e.g. `jayudemy23@gmail.com`)
3. Access the dashboard at `https://meta-ads-manager-lmquvtnfja-el.a.run.app/cmo/`

Cloud Scheduler uses OIDC (service account) — no IAP session needed for automated syncs.

### Redeploy after code changes

```bash
./deploy/deploy.sh
```

## Cron / Scheduler

| Job | Schedule | Action |
|-----|----------|--------|
| Cloud Scheduler `meta-sync-hourly` | `0 * * * *` (UTC) | `POST /api/sync/all?export=true` |
| In-app leads scheduler | every 15 min | `sync_leads` (configurable) |
| In-app insights scheduler | every 60 min | `sync_insights` (configurable) |

## Incremental sync guarantees

- **Insights:** Re-fetches with a 3-day overlap window; daily parquet partitions are **merged** (not wiped)
- **Leads:** 1-hour lookback overlap from last cursor; leads upserted by Meta lead ID
- **GCS export:** Full snapshot of all leads in DB on each export — nothing removed

## Meta API permissions

| Permission | Purpose |
|------------|---------|
| `ads_read` | Read campaigns, ad sets, ads, insights |
| `ads_management` | Pause/activate ads, update budgets |
| `leads_retrieval` | Fetch lead form submissions |
| `pages_show_list` | Discover managed Pages |

Use a **long-lived** or **System User** token for production. See Meta Business Settings.

## Security

- Never commit `.env` or access tokens
- Cloud Run deployed with `--no-allow-unauthenticated`
- IAP allowlists business team emails
- Tokens stored in Secret Manager for production
- GCS bucket IAM limited to service account

## Project structure

```
app/
  main.py              # FastAPI + Dash mount + schedulers
  config.py            # Settings from .env / Cloud Run env
  dashboard/
    cmo_dash.py        # Dash factory
    analytics.py       # KPI / funnel computations
    components/        # Layout, charts, tables, KPI cards
    callbacks/         # Data load, sync polling, chart render
  meta/
    client.py          # Meta API client (+ insights)
    ads_sync.py
    leads_sync.py
    insights_sync.py   # Daily insights → GCS parquet
  services/
    gcs_store.py       # GCS read/write (parquet merge, manifest, jobs)
    sync_jobs.py       # Background sync job runner
    leads_export.py    # Tutors/parents JSON export
    structure_export.py
    sync_all.py        # Orchestrated sync pipeline
  api/                 # REST routes
  db/                  # SQLAlchemy (local leads cache)
  templates/           # Jinja2 pages
deploy/
  deploy.sh            # Cloud Run + Scheduler deploy
  iap-setup.md         # IAP instructions
Dockerfile
cli.py
```
