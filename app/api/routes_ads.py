from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import repositories as repo
from app.db.session import get_db
from app.services.ad_manager import AdManagerService

router = APIRouter(prefix="/api/ads", tags=["ads"])


class StatusUpdate(BaseModel):
    status: str


@router.get("/campaigns")
def get_campaigns(db: Session = Depends(get_db)):
    campaigns = repo.list_campaigns(db)
    return [
        {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "effective_status": c.effective_status,
            "objective": c.objective,
            "updated_time": c.updated_time.isoformat() if c.updated_time else None,
        }
        for c in campaigns
    ]


@router.get("/ad-sets")
def get_ad_sets(campaign_id: str | None = None, db: Session = Depends(get_db)):
    ad_sets = repo.list_ad_sets(db, campaign_id=campaign_id)
    return [
        {
            "id": a.id,
            "campaign_id": a.campaign_id,
            "name": a.name,
            "status": a.status,
            "effective_status": a.effective_status,
            "daily_budget": a.daily_budget,
            "updated_time": a.updated_time.isoformat() if a.updated_time else None,
        }
        for a in ad_sets
    ]


@router.get("")
def get_ads(ad_set_id: str | None = None, db: Session = Depends(get_db)):
    ads = repo.list_ads(db, ad_set_id=ad_set_id)
    return [
        {
            "id": a.id,
            "ad_set_id": a.ad_set_id,
            "name": a.name,
            "status": a.status,
            "effective_status": a.effective_status,
            "updated_time": a.updated_time.isoformat() if a.updated_time else None,
        }
        for a in ads
    ]


@router.patch("/{ad_id}/status")
def update_ad_status(
    ad_id: str,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    service = AdManagerService(db, settings)
    status = body.status.upper()
    if status not in {"ACTIVE", "PAUSED"}:
        raise HTTPException(status_code=400, detail="status must be ACTIVE or PAUSED")
    try:
        if status == "PAUSED":
            return service.pause_ad(ad_id)
        return service.activate_ad(ad_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/campaigns/{campaign_id}/status")
def update_campaign_status(
    campaign_id: str,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    service = AdManagerService(db, settings)
    status = body.status.upper()
    if status not in {"ACTIVE", "PAUSED"}:
        raise HTTPException(status_code=400, detail="status must be ACTIVE or PAUSED")
    try:
        if status == "PAUSED":
            return service.pause_campaign(campaign_id)
        return service.activate_campaign(campaign_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
