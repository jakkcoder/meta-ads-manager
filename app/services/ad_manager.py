from sqlalchemy.orm import Session

from app.config import Settings
from app.db import repositories as repo
from app.db.models import AdSet
from app.meta.client import MetaClient


class AdManagerService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.client = MetaClient(settings)

    def pause_ad(self, ad_id: str) -> dict:
        return self._update_ad_status(ad_id, "PAUSED")

    def activate_ad(self, ad_id: str) -> dict:
        return self._update_ad_status(ad_id, "ACTIVE")

    def _update_ad_status(self, ad_id: str, status: str) -> dict:
        result = self.client.update_object_status(ad_id, status)
        repo.update_ad_status(self.db, ad_id, status)
        repo.add_audit_log(
            self.db,
            action=f"ad_{status.lower()}",
            object_type="ad",
            object_id=ad_id,
            payload={"status": status, "meta_response": result},
        )
        self.db.commit()
        return {"id": ad_id, "status": status, "success": result.get("success", True)}

    def pause_campaign(self, campaign_id: str) -> dict:
        result = self.client.update_object_status(campaign_id, "PAUSED")
        repo.update_campaign_status(self.db, campaign_id, "PAUSED")
        repo.add_audit_log(
            self.db,
            action="campaign_paused",
            object_type="campaign",
            object_id=campaign_id,
            payload={"status": "PAUSED", "meta_response": result},
        )
        self.db.commit()
        return {"id": campaign_id, "status": "PAUSED", "success": result.get("success", True)}

    def activate_campaign(self, campaign_id: str) -> dict:
        result = self.client.update_object_status(campaign_id, "ACTIVE")
        repo.update_campaign_status(self.db, campaign_id, "ACTIVE")
        repo.add_audit_log(
            self.db,
            action="campaign_activated",
            object_type="campaign",
            object_id=campaign_id,
            payload={"status": "ACTIVE", "meta_response": result},
        )
        self.db.commit()
        return {"id": campaign_id, "status": "ACTIVE", "success": result.get("success", True)}

    def update_ad_set_daily_budget(self, ad_set_id: str, daily_budget: int) -> dict:
        result = self.client.update_ad_set_budget(ad_set_id, daily_budget)
        ad_set = self.db.get(AdSet, ad_set_id)
        if ad_set:
            ad_set.daily_budget = str(daily_budget)
        repo.add_audit_log(
            self.db,
            action="adset_budget_update",
            object_type="ad_set",
            object_id=ad_set_id,
            payload={"daily_budget": daily_budget, "meta_response": result},
        )
        self.db.commit()
        return {"id": ad_set_id, "daily_budget": daily_budget, "success": result.get("success", True)}
