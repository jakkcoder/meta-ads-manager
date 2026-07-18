from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.config import Settings
from app.meta.client import MetaClient
from app.services import gcs_store

LEAD_ACTION_TYPES = {
    "lead",
    "onsite_conversion.lead_grouped",
    "offsite_conversion.fb_pixel_lead",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _extract_leads(row: dict[str, Any]) -> int:
    total = 0
    for action in row.get("actions") or []:
        if action.get("action_type") in LEAD_ACTION_TYPES:
            total += int(float(action.get("value") or 0))
    return total


def _extract_cpl(row: dict[str, Any], leads: int) -> float | None:
    if leads <= 0:
        return None
    for item in row.get("cost_per_action_type") or []:
        if item.get("action_type") in LEAD_ACTION_TYPES:
            return _parse_float(item.get("value"))
    spend = _parse_float(row.get("spend"))
    return spend / leads if leads else None


def _normalize_insight_row(
    row: dict[str, Any],
    *,
    level: str,
    object_id: str,
    object_name: str,
    campaign_id: str | None = None,
    campaign_name: str | None = None,
    daily_budget: float | None = None,
    segment: str | None = None,
) -> dict[str, Any]:
    leads = _extract_leads(row)
    spend = _parse_float(row.get("spend"))
    impressions = int(_parse_float(row.get("impressions")))
    clicks = int(_parse_float(row.get("clicks")))
    cpl = _extract_cpl(row, leads)
    budget_utilization = (spend / daily_budget) if daily_budget and daily_budget > 0 else None

    return {
        "date": row.get("date_start") or row.get("date_stop"),
        "level": level,
        "object_id": object_id,
        "object_name": object_name,
        "campaign_id": campaign_id or object_id if level == "campaign" else campaign_id,
        "campaign_name": campaign_name or (object_name if level == "campaign" else campaign_name),
        "segment": segment,
        "spend": spend,
        "impressions": impressions,
        "clicks": clicks,
        "reach": int(_parse_float(row.get("reach"))),
        "leads": leads,
        "cpl": cpl,
        "ctr": _parse_float(row.get("ctr")),
        "cpc": _parse_float(row.get("cpc")),
        "cpm": _parse_float(row.get("cpm")),
        "daily_budget": daily_budget,
        "budget_utilization": budget_utilization,
    }


def _segment_for_campaign(name: str) -> str:
    lower = (name or "").lower()
    if "teacher" in lower or "tutor" in lower:
        return "tutors"
    if "parent" in lower:
        return "parents"
    return "other"


def _tracked_campaigns(client: MetaClient, settings: Settings) -> list[dict[str, Any]]:
    prefixes = [p.strip() for p in settings.tracked_campaign_prefixes.split(",") if p.strip()]
    campaigns = client.get_campaigns_with_budget()
    tracked = [
        c
        for c in campaigns
        if any((c.get("name") or "").startswith(prefix) for prefix in prefixes)
    ]
    return tracked


def _insights_cursor(manifest: dict[str, Any]) -> str | None:
    cursors = manifest.get("cursors") or {}
    return cursors.get("insights") or cursors.get("insights:last_date")


def _date_range(full_sync: bool, settings: Settings) -> tuple[date, date]:
    end = _utcnow().date()
    manifest = gcs_store.read_manifest(settings)
    last_date_raw = _insights_cursor(manifest)

    if full_sync or not last_date_raw:
        start = end - timedelta(days=settings.insights_backfill_days)
        return start, end

    try:
        last_date = date.fromisoformat(str(last_date_raw))
    except ValueError:
        last_date = end - timedelta(days=settings.insights_backfill_days)

    start = last_date - timedelta(days=settings.insights_overlap_days)
    return start, end


def _fetch_objects_for_campaign(client: MetaClient, campaign_id: str) -> list[tuple[str, str, str]]:
    objects: list[tuple[str, str, str]] = []

    adsets = client._paginate(
        f"{campaign_id}/adsets",
        params={"fields": "id,name", "limit": 100},
    )
    for adset in adsets:
        objects.append(("adset", adset["id"], adset.get("name") or adset["id"]))
        ads = client._paginate(
            f"{adset['id']}/ads",
            params={"fields": "id,name", "limit": 100},
        )
        for ad in ads:
            objects.append(("ad", ad["id"], ad.get("name") or ad["id"]))

    return objects


def sync_insights(db: Session, settings: Settings, *, full_sync: bool = False) -> dict:
    del db  # insights stored in GCS, not SQLite
    client = MetaClient(settings)
    campaigns = _tracked_campaigns(client, settings)
    start, end = _date_range(full_sync, settings)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    since = start.isoformat()
    until = end.isoformat()

    for campaign in campaigns:
        campaign_id = campaign["id"]
        campaign_name = campaign.get("name") or campaign_id
        daily_budget = _parse_float(campaign.get("daily_budget")) / 100 if campaign.get("daily_budget") else None
        segment = _segment_for_campaign(campaign_name)

        fetch_targets: list[tuple[str, str, str]] = [
            ("campaign", campaign_id, campaign_name),
            *_fetch_objects_for_campaign(client, campaign_id),
        ]

        for level, object_id, object_name in fetch_targets:
            try:
                insight_rows = client.get_insights(
                    object_id,
                    since=since,
                    until=until,
                    time_increment=1,
                )
                for insight in insight_rows:
                    rows.append(
                        _normalize_insight_row(
                            insight,
                            level=level,
                            object_id=object_id,
                            object_name=object_name,
                            campaign_id=campaign_id,
                            campaign_name=campaign_name,
                            daily_budget=daily_budget if level == "campaign" else None,
                            segment=segment if level == "campaign" else segment,
                        )
                    )
            except Exception as exc:
                errors.append(f"{level}:{object_id}: {exc}")

    if not rows:
        result = {
            "campaigns": len(campaigns),
            "rows": 0,
            "start": since,
            "end": until,
            "errors": errors,
        }
        gcs_store.update_manifest_sync(settings, "insights", cursor=end.isoformat(), result=result)
        return result

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    partitions_written = 0
    for day_value, group in df.groupby("date"):
        day = day_value if isinstance(day_value, date) else pd.Timestamp(day_value).date()
        gcs_store.merge_parquet_partition(settings, day, group.reset_index(drop=True))
        partitions_written += 1

    result = {
        "campaigns": len(campaigns),
        "rows": len(df),
        "partitions_written": partitions_written,
        "start": since,
        "end": until,
        "errors": errors,
    }
    gcs_store.update_manifest_sync(
        settings,
        "insights",
        cursor=end.isoformat(),
        result=result,
    )
    return result
