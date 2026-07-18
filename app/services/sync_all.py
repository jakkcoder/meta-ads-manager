from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.config import Settings
from app.meta.insights_sync import sync_insights
from app.meta.leads_sync import sync_leads
from app.services import gcs_store
from app.services.leads_export import export_leads_to_gcs
from app.services.structure_export import sync_ads_and_structure


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_insights_sync(db: Session, settings: Settings, *, full: bool = False) -> dict:
    return sync_insights(db, settings, full_sync=full)


def run_leads_sync(db: Session, settings: Settings, *, full: bool = False, export: bool = False) -> dict:
    result = sync_leads(db, settings, full_sync=full)
    if export:
        result["gcs_export"] = export_leads_to_gcs(db, settings)
    return result


def run_ads_sync(db: Session, settings: Settings, *, full: bool = False) -> dict:
    return sync_ads_and_structure(db, settings, full_sync=full)


def _export_insights_snapshot(settings: Settings) -> dict:
    df = gcs_store.read_parquet_range(
        settings,
        start=(_utcnow().date() - timedelta(days=settings.insights_backfill_days)),
        end=_utcnow().date(),
    )
    stamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    export_url = gcs_store.write_insights_export(settings, df, stamp)
    return {"url": export_url, "rows": len(df)}


def run_incremental_sync_to_gcs(db: Session, settings: Settings) -> dict:
    """Incremental Meta → GCS pull: ads structure, leads, insights (with overlap windows)."""
    results: dict = {}
    results["ads"] = run_ads_sync(db, settings, full=False)
    results["leads"] = run_leads_sync(db, settings, full=False, export=True)
    results["insights"] = run_insights_sync(db, settings, full=False)
    results["insights_export"] = _export_insights_snapshot(settings)
    gcs_store.update_manifest_sync(settings, "all", result=results)
    return results


def run_all_sync(db: Session, settings: Settings, *, full: bool = False, export: bool = True) -> dict:
    if not full and export:
        return run_incremental_sync_to_gcs(db, settings)

    results: dict = {}
    results["ads"] = run_ads_sync(db, settings, full=full)
    results["leads"] = run_leads_sync(db, settings, full=full, export=export)
    results["insights"] = run_insights_sync(db, settings, full=full)

    if export:
        results["insights_export"] = _export_insights_snapshot(settings)

    gcs_store.update_manifest_sync(settings, "all", result=results)
    return results


def get_sync_status(settings: Settings) -> dict:
    return gcs_store.read_manifest(settings)
