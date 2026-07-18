from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import repositories as repo
from app.meta.ads_sync import sync_ads
from app.services import gcs_store


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def export_structure_snapshot(db: Session, settings: Settings) -> dict:
    campaigns = repo.list_campaigns(db)
    ad_sets = repo.list_ad_sets(db)
    ads = repo.list_ads(db)

    payload = {
        "exported_at": _utcnow().isoformat(),
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "effective_status": c.effective_status,
                "objective": c.objective,
            }
            for c in campaigns
        ],
        "ad_sets": [
            {
                "id": a.id,
                "campaign_id": a.campaign_id,
                "name": a.name,
                "status": a.status,
                "effective_status": a.effective_status,
                "daily_budget": a.daily_budget,
            }
            for a in ad_sets
        ],
        "ads": [
            {
                "id": a.id,
                "ad_set_id": a.ad_set_id,
                "name": a.name,
                "status": a.status,
                "effective_status": a.effective_status,
            }
            for a in ads
        ],
    }

    url = gcs_store.write_json(settings, settings.gcs_structure_path, payload)
    gcs_store.update_manifest_sync(settings, "structure", result={"url": url, "campaigns": len(campaigns)})
    return {"url": url, "campaigns": len(campaigns), "ad_sets": len(ad_sets), "ads": len(ads)}


def sync_ads_and_structure(db: Session, settings: Settings, *, full_sync: bool = False) -> dict:
    ads_result = sync_ads(db, settings, full_sync=full_sync)
    structure_result = export_structure_snapshot(db, settings)
    return {"ads": ads_result, "structure": structure_result}
