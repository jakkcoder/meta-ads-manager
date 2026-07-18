from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    meta_access_token: str = Field(validation_alias="Meta_Access_token")
    ad_account_id: str = "1579547858935909"
    page_id: str | None = None
    page_access_token: str | None = None
    database_url: str = "sqlite:///./data/meta_ads.db"
    meta_api_version: str = "v25.0"
    sync_leads_interval_minutes: int = 15
    api_key: str | None = None
    google_cloud_project: str | None = None
    gcs_leads_bucket: str | None = None
    gcs_leads_prefix: str = "meta-ads/leads"
    gcs_insights_prefix: str = "meta-ads/insights/daily"
    gcs_manifest_path: str = "meta-ads/manifest.json"
    gcs_structure_path: str = "meta-ads/structure/snapshot.json"
    gcs_exports_prefix: str = "meta-ads/exports"
    gcs_tutors_url: str | None = None
    gcs_parents_url: str | None = None
    insights_backfill_days: int = 90
    insights_overlap_days: int = 3
    leads_overlap_seconds: int = 3600
    sync_insights_interval_minutes: int = 60
    tracked_campaign_prefixes: str = "Gharkaguru_"
    meta_pixel_id: str | None = None
    ops_alert_webhook_url: str | None = None
    ops_alert_interval_minutes: int = 15

    @property
    def ad_account_path(self) -> str:
        account_id = self.ad_account_id
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"
        return account_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
