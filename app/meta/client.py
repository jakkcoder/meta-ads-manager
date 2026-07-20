import json
import time
from typing import Any

import httpx

from app.config import Settings


class MetaAPIError(Exception):
    def __init__(self, message: str, *, code: int | None = None, subcode: int | None = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode


class MetaClient:
    CAMPAIGN_FIELDS = (
        "id,name,status,effective_status,objective,created_time,updated_time"
    )
    ADSET_FIELDS = (
        "id,name,status,effective_status,campaign_id,daily_budget,lifetime_budget,"
        "targeting,created_time,updated_time"
    )
    AD_FIELDS = (
        "id,name,status,effective_status,adset_id,"
        "creative{id,name,object_story_spec},created_time,updated_time"
    )
    FORM_FIELDS = "id,name,status,leads_count,created_time"
    LEAD_FIELDS = (
        "id,created_time,field_data,ad_id,ad_name,adset_id,adset_name,"
        "campaign_id,campaign_name,form_id,platform,is_organic"
    )
    INSIGHTS_FIELDS = (
        "spend,impressions,clicks,reach,cpc,cpm,ctr,actions,cost_per_action_type,"
        "date_start,date_stop"
    )
    CAMPAIGN_FIELDS_WITH_BUDGET = (
        "id,name,status,effective_status,objective,daily_budget,created_time,updated_time"
    )

    def __init__(
        self,
        settings: Settings,
        *,
        page_access_token: str | None = None,
    ):
        self.settings = settings
        self.page_access_token = page_access_token or settings.page_access_token
        self.base_url = f"https://graph.facebook.com/{settings.meta_api_version}"

    def _token(self, use_page_token: bool = False) -> str:
        if use_page_token and self.page_access_token:
            return self.page_access_token
        return self.settings.meta_access_token

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        use_page_token: bool = False,
        max_retries: int = 5,
    ) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        if "access_token=" in url:
            request_params = None
        else:
            request_params = dict(params or {})
            request_params.setdefault("access_token", self._token(use_page_token))

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=60.0) as client:
                    response = client.request(method, url, params=request_params, data=data)
                    payload = response.json()
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue

            if "error" in payload:
                error = payload["error"]
                code = error.get("code")
                subcode = error.get("error_subcode")
                message = error.get("message", "Meta API error")
                if code in (2, 17, 32, 4) or subcode in (244, 1892058):
                    time.sleep(2**attempt)
                    last_error = MetaAPIError(message, code=code, subcode=subcode)
                    continue
                raise MetaAPIError(message, code=code, subcode=subcode)

            return payload

        if last_error:
            raise last_error
        raise MetaAPIError("Meta API request failed after retries")

    def _paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        use_page_token: bool = False,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        next_url: str | None = None
        first = True

        while first or next_url:
            first = False
            if next_url:
                payload = self._request("GET", next_url)
            else:
                payload = self._request("GET", path, params=params, use_page_token=use_page_token)

            results.extend(payload.get("data", []))
            next_url = payload.get("paging", {}).get("next")

        return results

    def get_permissions(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "me/permissions")
        return payload.get("data", [])

    def get_ad_account(self) -> dict[str, Any]:
        return self._request(
            "GET",
            self.settings.ad_account_path,
            params={"fields": "id,name,account_status,currency,amount_spent"},
        )

    def get_campaigns(
        self,
        *,
        updated_since: int | None = None,
        full_sync: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"fields": self.CAMPAIGN_FIELDS, "limit": 100}
        if updated_since and not full_sync:
            params["filtering"] = json.dumps(
                [
                    {
                        "field": "campaign.updated_time",
                        "operator": "GREATER_THAN",
                        "value": updated_since,
                    }
                ]
            )
        return self._paginate(f"{self.settings.ad_account_path}/campaigns", params=params)

    def get_ad_sets(
        self,
        *,
        updated_since: int | None = None,
        full_sync: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"fields": self.ADSET_FIELDS, "limit": 100}
        if updated_since and not full_sync:
            params["filtering"] = json.dumps(
                [
                    {
                        "field": "adset.updated_time",
                        "operator": "GREATER_THAN",
                        "value": updated_since,
                    }
                ]
            )
        return self._paginate(f"{self.settings.ad_account_path}/adsets", params=params)

    def get_ads(
        self,
        *,
        updated_since: int | None = None,
        full_sync: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"fields": self.AD_FIELDS, "limit": 100}
        if updated_since and not full_sync:
            params["filtering"] = json.dumps(
                [
                    {
                        "field": "ad.updated_time",
                        "operator": "GREATER_THAN",
                        "value": updated_since,
                    }
                ]
            )
        return self._paginate(f"{self.settings.ad_account_path}/ads", params=params)

    def get_pages(self) -> list[dict[str, Any]]:
        return self._paginate("me/accounts", params={"fields": "id,name,access_token", "limit": 100})

    def get_page_access_token(self, page_id: str) -> str:
        payload = self._request("GET", page_id, params={"fields": "access_token"})
        token = payload.get("access_token")
        if not token:
            raise MetaAPIError(f"Could not retrieve page access token for page {page_id}")
        return token

    def get_leadgen_forms(self, page_id: str) -> list[dict[str, Any]]:
        params = {"fields": self.FORM_FIELDS, "limit": 100}
        return self._paginate(f"{page_id}/leadgen_forms", params=params, use_page_token=True)

    def get_leads(
        self,
        form_id: str,
        *,
        time_created_since: int | None = None,
        full_sync: bool = False,
        overlap_seconds: int = 3600,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"fields": self.LEAD_FIELDS, "limit": 100}
        if time_created_since and not full_sync:
            params["filtering"] = json.dumps(
                [
                    {
                        "field": "time_created",
                        "operator": "GREATER_THAN",
                        "value": max(0, time_created_since - overlap_seconds),
                    }
                ]
            )
        return self._paginate(f"{form_id}/leads", params=params, use_page_token=True)

    def update_object_status(self, object_id: str, status: str) -> dict[str, Any]:
        return self._request("POST", object_id, data={"status": status})

    def archive_leadgen_form(self, form_id: str) -> dict[str, Any]:
        return self._request("POST", form_id, data={"status": "ARCHIVED"}, use_page_token=True)

    def update_ad_set_budget(self, ad_set_id: str, daily_budget: int) -> dict[str, Any]:
        return self._request("POST", ad_set_id, data={"daily_budget": str(daily_budget)})

    def get_insights(
        self,
        object_id: str,
        *,
        since: str,
        until: str,
        time_increment: int = 1,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "fields": self.INSIGHTS_FIELDS,
            "time_range": json.dumps({"since": since, "until": until}),
            "time_increment": str(time_increment),
            "limit": 100,
        }
        return self._paginate(f"{object_id}/insights", params=params)

    def get_campaigns_with_budget(self) -> list[dict[str, Any]]:
        params = {"fields": self.CAMPAIGN_FIELDS_WITH_BUDGET, "limit": 100}
        return self._paginate(f"{self.settings.ad_account_path}/campaigns", params=params)
