#!/usr/bin/env python3
"""Create Gharkaguru parent campaign → ad set → ad pointing to the website booking form."""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.meta.client import MetaClient, MetaAPIError

PAGE_ID = "347244005670587"
INSTAGRAM_USER_ID = "17841477211412438"
IMAGE_HASH = "8bb194c7837bd61c209856189b07b27f"
BOOKING_URL = (
    "https://meta-ads-manager-lmquvtnfja-el.a.run.app/book/instagram"
    "?utm_campaign=Gharkaguru_parent_web"
)

CAMPAIGN_NAME = "Gharkaguru_parent_web"
ADSET_NAME = "Delhi Parents - Website"
AD_NAME = "delhi_ncr_parents_web"

# ₹500/day — Meta INR budgets are in paise
DAILY_BUDGET_PAISE = 50_000

PARENT_TARGETING = {
    "age_min": 28,
    "age_max": 55,
    "genders": [2],
    # Delhi NCT region — do not set location_types (Meta error #1870194 / #1870199).
    "geo_locations": {
        "regions": [{"key": "1728"}],
    },
    "publisher_platforms": ["facebook", "instagram"],
    "facebook_positions": ["feed", "story", "facebook_reels", "marketplace"],
    "instagram_positions": ["stream", "story", "reels", "profile_feed"],
    "device_platforms": ["mobile"],
    "targeting_automation": {"advantage_audience": 0},
}


def create_parent_website_campaign(
    client: MetaClient,
    *,
    booking_url: str = BOOKING_URL,
    daily_budget: int = DAILY_BUDGET_PAISE,
    status: str = "ACTIVE",
    dry_run: bool = False,
) -> dict:
    account = client.settings.ad_account_path

    campaign_payload = {
        "name": CAMPAIGN_NAME,
        "objective": "OUTCOME_TRAFFIC",
        "status": status,
        "special_ad_categories": json.dumps([]),
        "is_adset_budget_sharing_enabled": "false",
        "daily_budget": str(daily_budget),
    }

    adset_payload = {
        "name": ADSET_NAME,
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "LINK_CLICKS",
        "bid_strategy": "LOWEST_COST_WITH_BID_CAP",
        "bid_amount": "8000",
        "destination_type": "WEBSITE",
        "targeting": json.dumps(PARENT_TARGETING),
        "status": status,
        "promoted_object": json.dumps({"page_id": PAGE_ID}),
    }

    creative_payload = {
        "name": f"Website booking — {AD_NAME}",
        "object_story_spec": json.dumps(
            {
                "page_id": PAGE_ID,
                "instagram_user_id": INSTAGRAM_USER_ID,
                "link_data": {
                    "link": booking_url,
                    "message": "Home Tutors for Your Child — 2 Free Demos",
                    "name": "2 Free demo class at your place",
                    "description": (
                        "Parents: get a verified IIT/NIT home tutor for your child. "
                        "1-on-1 classes at home from ₹150/hr. Book 2 FREE demo classes today."
                    ),
                    "image_hash": IMAGE_HASH,
                    "attachment_style": "link",
                    "call_to_action": {
                        "type": "SIGN_UP",
                        "value": {"link": booking_url},
                    },
                },
            }
        ),
    }

    ad_payload = {
        "name": AD_NAME,
        "status": status,
    }

    if dry_run:
        return {
            "dry_run": True,
            "campaign": campaign_payload,
            "adset": adset_payload,
            "creative": json.loads(creative_payload["object_story_spec"]),
            "ad": ad_payload,
            "booking_url": booking_url,
        }

    campaign = client._request("POST", f"{account}/campaigns", data=campaign_payload)
    campaign_id = campaign["id"]

    adset_payload["campaign_id"] = campaign_id
    adset = client._request("POST", f"{account}/adsets", data=adset_payload)
    adset_id = adset["id"]

    creative = client._request("POST", f"{account}/adcreatives", data=creative_payload)
    creative_id = creative["id"]

    ad_payload["adset_id"] = adset_id
    ad_payload["creative"] = json.dumps({"creative_id": creative_id})
    ad = client._request("POST", f"{account}/ads", data=ad_payload)

    return {
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad["id"],
        "booking_url": booking_url,
        "status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=BOOKING_URL)
    parser.add_argument("--budget", type=int, default=DAILY_BUDGET_PAISE, help="Daily budget in paise (50000 = ₹500)")
    parser.add_argument("--status", default="ACTIVE", choices=["ACTIVE", "PAUSED"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    client = MetaClient(settings)
    try:
        result = create_parent_website_campaign(
            client,
            booking_url=args.url,
            daily_budget=args.budget,
            status=args.status,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
    except MetaAPIError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code, "subcode": exc.subcode}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
