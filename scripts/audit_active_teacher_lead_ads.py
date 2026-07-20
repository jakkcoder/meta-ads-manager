#!/usr/bin/env python3
"""Audit enabled Meta lead ads and report the Instant Form attached to each."""

from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.meta.client import MetaAPIError, MetaClient
from app.services.leads_export import TUTOR_FORM_IDS


def lead_form_id(ad: dict) -> str | None:
    creative = ad.get("creative") or {}
    spec = creative.get("object_story_spec") or {}
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except (TypeError, ValueError):
            return None
    for key in ("link_data", "video_data"):
        value = (
            ((spec.get(key) or {}).get("call_to_action") or {}).get("value") or {}
        )
        if value.get("lead_gen_form_id"):
            return str(value["lead_gen_form_id"])
    return None


def is_enabled(item: dict | None) -> bool:
    if not item:
        return False
    return (item.get("effective_status") or item.get("status") or "").upper() == "ACTIVE"


def audit() -> dict:
    client = MetaClient(get_settings())
    campaigns = {item["id"]: item for item in client.get_campaigns(full_sync=True)}
    adsets = {item["id"]: item for item in client.get_ad_sets(full_sync=True)}
    ads = client.get_ads(full_sync=True)

    active_ads = []
    for ad in ads:
        adset = adsets.get(ad.get("adset_id"))
        campaign = campaigns.get((adset or {}).get("campaign_id"))
        form_id = lead_form_id(ad)
        if not (is_enabled(ad) and is_enabled(adset) and is_enabled(campaign)):
            continue
        active_ads.append(
            {
                "ad_id": ad["id"],
                "ad_name": ad.get("name"),
                "adset_id": ad.get("adset_id"),
                "adset_name": (adset or {}).get("name"),
                "campaign_id": (campaign or {}).get("id"),
                "campaign_name": (campaign or {}).get("name"),
                "leadgen_form_id": form_id,
                "is_teacher_form": form_id in TUTOR_FORM_IDS if form_id else False,
            }
        )

    teacher_ads = [row for row in active_ads if row["is_teacher_form"]]
    return {
        "active_campaigns": sum(1 for item in campaigns.values() if is_enabled(item)),
        "active_adsets": sum(1 for item in adsets.values() if is_enabled(item)),
        "active_ads": active_ads,
        "active_teacher_lead_ads": teacher_ads,
        "new_teacher_form_id": "38248227824775801",
        "new_teacher_form_attached": any(
            row["leadgen_form_id"] == "38248227824775801" for row in active_ads
        ),
    }


if __name__ == "__main__":
    try:
        print(json.dumps(audit(), indent=2))
    except MetaAPIError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code, "subcode": exc.subcode}))
        sys.exit(1)
