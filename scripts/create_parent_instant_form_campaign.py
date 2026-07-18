#!/usr/bin/env python3
"""Create Gharkaguru parent lead-gen campaign with Meta Instant Form (book demo)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.meta.client import MetaClient, MetaAPIError

PAGE_ID = "347244005670587"
INSTAGRAM_USER_ID = "17841477211412438"
# Same image as delhi_ncr_parents_web ad
IMAGE_HASH = "e0a4d4cbd05771b29322b727c678491b"
PRIVACY_URL = "http://www.gharkaguru.com/"
FOLLOW_UP_URL = "http://www.gharkaguru.com/"

CAMPAIGN_NAME = "Gharkaguru_parent_instant"
ADSET_NAME = "Delhi Parents - Instant Form"
AD_NAME = "delhi_parents_instant_form"
FORM_NAME = "Book Demo - Delhi Parents (Date + Phone)"
DEFAULT_FORM_ID = "1477904857469616"

DAILY_BUDGET_PAISE = 50_000  # ₹500/day

PARENT_TARGETING = {
    "age_min": 28,
    "age_max": 55,
    "genders": [2],
    "geo_locations": {
        "regions": [{"key": "1728"}],
    },
    "publisher_platforms": ["facebook", "instagram"],
    "facebook_positions": ["feed", "story", "facebook_reels", "marketplace"],
    "instagram_positions": ["stream", "story", "reels", "profile_feed"],
    "device_platforms": ["mobile"],
    "targeting_automation": {"advantage_audience": 0},
}




def _demo_date_options() -> list[dict[str, str]]:
    tz = ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date()
    options = []
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        options.append(
            {
                "key": day.isoformat(),
                "value": day.strftime("%a, %d %b"),
            }
        )
    return options


def build_form_questions() -> list[dict]:
    """Short instant form: demo date and phone only."""
    return [
        {
            "type": "CUSTOM",
            "key": "demo_date",
            "label": "When would you like the demo?",
            "options": _demo_date_options(),
        },
        {
            "type": "PHONE",
            "key": "phone_number",
        },
    ]


def create_lead_form(client: MetaClient, *, dry_run: bool = False) -> dict:
    payload = {
        "name": FORM_NAME,
        "locale": "en_US",
        "follow_up_action_url": FOLLOW_UP_URL,
        "question_page_custom_headline": "Book a FREE demo class for your child",
        "privacy_policy": json.dumps(
            {"url": PRIVACY_URL, "link_text": "GharKaGuru Privacy Policy"}
        ),
        "context_card": json.dumps(
            {
                "title": "Expert Home Tutors for Your Child",
                "style": "LIST_STYLE",
                "content": [
                    "1-on-1 learning at home or online",
                    "Verified tutors from IIT / NIT",
                    "2 FREE demo classes for your child",
                    "Classes from ₹150/hr",
                ],
            }
        ),
        "thank_you_page": json.dumps(
            {
                "title": "Demo booked! Our team will call you shortly.",
                "body": (
                    "We will call you to confirm your preferred demo date."
                ),
                "button_type": "VIEW_WEBSITE",
                "button_text": "Visit GharKaGuru",
                "website_url": FOLLOW_UP_URL,
            }
        ),
        "questions": json.dumps(build_form_questions()),
        "is_optimized_for_quality": "true",
    }

    if dry_run:
        return {"dry_run": True, "form": payload, "questions": build_form_questions()}

    return client._request(
        "POST",
        f"{PAGE_ID}/leadgen_forms",
        data=payload,
        use_page_token=True,
    )


def create_parent_instant_campaign(
    client: MetaClient,
    *,
    form_id: str,
    daily_budget: int = DAILY_BUDGET_PAISE,
    status: str = "ACTIVE",
    dry_run: bool = False,
) -> dict:
    account = client.settings.ad_account_path

    campaign_payload = {
        "name": CAMPAIGN_NAME,
        "objective": "OUTCOME_LEADS",
        "status": status,
        "special_ad_categories": json.dumps([]),
        "is_adset_budget_sharing_enabled": "false",
        "daily_budget": str(daily_budget),
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    }

    adset_payload = {
        "name": ADSET_NAME,
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "LEAD_GENERATION",
        "destination_type": "ON_AD",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "targeting": json.dumps(PARENT_TARGETING),
        "status": status,
        "promoted_object": json.dumps({"page_id": PAGE_ID}),
        "regional_regulated_categories": json.dumps([]),
    }

    creative_payload = {
        "name": f"Instant form — {AD_NAME}",
        "object_story_spec": json.dumps(
            {
                "page_id": PAGE_ID,
                "instagram_user_id": INSTAGRAM_USER_ID,
                "link_data": {
                    "link": "http://fb.me/",
                    "message": "Home Tutors for Your Child — 2 Free Demos",
                    "name": "Book a Free Demo Class",
                    "description": "Help Your Child Learn at Home",
                    "image_hash": IMAGE_HASH,
                    "attachment_style": "link",
                    "call_to_action": {
                        "type": "SIGN_UP",
                        "value": {"lead_gen_form_id": form_id},
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
            "form_id": form_id,
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
        "campaign_name": CAMPAIGN_NAME,
        "adset_id": adset_id,
        "adset_name": ADSET_NAME,
        "creative_id": creative_id,
        "ad_id": ad["id"],
        "ad_name": AD_NAME,
        "form_id": form_id,
        "form_name": FORM_NAME,
        "image_hash": IMAGE_HASH,
        "status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--form-id",
        default=DEFAULT_FORM_ID,
        help="Use an existing lead form instead of creating one",
    )
    parser.add_argument("--budget", type=int, default=DAILY_BUDGET_PAISE)
    parser.add_argument("--status", default="ACTIVE", choices=["ACTIVE", "PAUSED"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = MetaClient(get_settings())
    try:
        if args.form_id:
            form_id = args.form_id
            form_result = {"id": form_id, "reused": True}
        else:
            form_result = create_lead_form(client, dry_run=args.dry_run)
            if args.dry_run:
                print(json.dumps(form_result, indent=2))
                return
            form_id = form_result["id"]

        result = create_parent_instant_campaign(
            client,
            form_id=form_id,
            daily_budget=args.budget,
            status=args.status,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            result["form"] = form_result
        print(json.dumps(result, indent=2))
    except MetaAPIError as exc:
        print(
            json.dumps(
                {"error": str(exc), "code": exc.code, "subcode": exc.subcode},
                indent=2,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
