#!/usr/bin/env python3
"""Create a paused Education Counselor hiring campaign with Instant Form.

Uploads job_hiring.png, creates a lead form (name, phone, education, experience),
then campaign → ad set → ad. Defaults to PAUSED so nothing spends until review.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path

import httpx

from app.config import get_settings
from app.meta.client import MetaAPIError, MetaClient
from app.meta.leads_sync import ensure_page_token

PAGE_ID = "347244005670587"
INSTAGRAM_USER_ID = "17841477211412438"
PRIVACY_URL = "https://www.gharkaguru.com/"
FOLLOW_UP_URL = "https://www.gharkaguru.com/"

CAMPAIGN_NAME = "Gharkaguru_counselor_hiring"
ADSET_NAME = "Delhi NCR - Education Counselor"
AD_NAME = "delhi_counselor_hiring"
FORM_NAME = "Education Counselor Application"
DEFAULT_IMAGE = Path("/Users/jayshankar/Desktop/The Codex/gharguru/job_hiring.png")

# ₹300/day — Meta INR budgets are in paise
DAILY_BUDGET_PAISE = 30_000

# Job ads must use EMPLOYMENT. Age/gender/zip targeting is not allowed.
HIRING_TARGETING = {
    "geo_locations": {
        "regions": [{"key": "1728"}],
    },
    "publisher_platforms": ["facebook", "instagram"],
    "facebook_positions": ["feed", "story", "facebook_reels"],
    "instagram_positions": ["stream", "story", "reels", "profile_feed"],
    "device_platforms": ["mobile"],
    "targeting_automation": {"advantage_audience": 0},
}

PRIMARY_TEXT = (
    "HIRING ALERT! Join Ghar Ka Guru as an Education Counselor.\n\n"
    "Earn up to ₹5.5 LPA (₹2.5 LPA fixed + ₹3 LPA variable).\n"
    "Guide students from Class 6 to 12 and grow your career in education.\n\n"
    "Minimum qualification: Bachelor's degree. Apply now — our team will call you."
)
HEADLINE = "Education Counselor | Up to ₹5.5 LPA"
DESCRIPTION = "Fixed ₹2.5 LPA + variable ₹3 LPA. Apply in 1 minute."


def build_form_questions() -> list[dict]:
    return [
        {"type": "FULL_NAME", "key": "full_name"},
        {"type": "PHONE", "key": "phone_number"},
        {"type": "EMAIL", "key": "email"},
        {
            "type": "CUSTOM",
            "key": "highest_qualification",
            "label": "What is your highest qualification?",
            "options": [
                {"key": "bachelors", "value": "Bachelor's degree"},
                {"key": "masters", "value": "Master's degree"},
                {"key": "b_ed", "value": "B.Ed / M.Ed"},
                {"key": "other", "value": "Other"},
            ],
        },
        {
            "type": "CUSTOM",
            "key": "education_details",
            "label": "Education details (degree, college, year)",
        },
        {
            "type": "CUSTOM",
            "key": "experience",
            "label": "How many years of counseling / education / sales experience do you have?",
            "options": [
                {"key": "fresher", "value": "Fresher"},
                {"key": "1_2", "value": "1–2 years"},
                {"key": "3_5", "value": "3–5 years"},
                {"key": "6_plus", "value": "6+ years"},
            ],
        },
        {
            "type": "CUSTOM",
            "key": "city_locality",
            "label": "Which city / locality are you based in?",
        },
        {
            "type": "CUSTOM",
            "key": "notice_period",
            "label": "When can you join?",
            "options": [
                {"key": "immediate", "value": "Immediately"},
                {"key": "15_days", "value": "Within 15 days"},
                {"key": "30_days", "value": "Within 30 days"},
                {"key": "60_days", "value": "60 days or more"},
            ],
        },
    ]


def build_form_payload() -> dict[str, str]:
    return {
        "name": FORM_NAME,
        "locale": "en_US",
        "follow_up_action_url": FOLLOW_UP_URL,
        "question_page_custom_headline": "Apply as Education Counselor",
        "privacy_policy": json.dumps(
            {"url": PRIVACY_URL, "link_text": "Ghar Ka Guru Privacy Policy"}
        ),
        "context_card": json.dumps(
            {
                "title": "Join Ghar Ka Guru as an Education Counselor",
                "style": "LIST_STYLE",
                "content": [
                    "Earn up to ₹5.5 LPA (₹2.5 LPA fixed + ₹3 LPA variable)",
                    "Counsel students from Class 6 to 12",
                    "Great career growth in education",
                    "Bachelor's degree required — apply in 1 minute",
                ],
            }
        ),
        "thank_you_page": json.dumps(
            {
                "title": "Application received!",
                "body": "Our hiring team will review your details and call you shortly.",
                "button_type": "VIEW_WEBSITE",
                "button_text": "Visit Ghar Ka Guru",
                "website_url": FOLLOW_UP_URL,
            }
        ),
        "questions": json.dumps(build_form_questions()),
        "is_optimized_for_quality": "true",
    }


def upload_image(client: MetaClient, path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    token = client.settings.meta_access_token
    account = client.settings.ad_account_path
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    with path.open("rb") as handle:
        response = httpx.post(
            f"https://graph.facebook.com/{client.settings.meta_api_version}/{account}/adimages",
            data={"filename": path.name, "access_token": token},
            files={"source": (path.name, handle, mime)},
            timeout=120.0,
        )
    payload = response.json()
    if "error" in payload:
        raise MetaAPIError(payload["error"].get("message", "Image upload failed"))
    images = payload.get("images") or {}
    entry = images.get(path.name) or next(iter(images.values()), {})
    image_hash = entry.get("hash")
    if not image_hash:
        raise MetaAPIError(f"Upload succeeded but no hash returned: {payload}")
    return {"hash": image_hash, "url": entry.get("url"), "width": entry.get("width"), "height": entry.get("height")}


def create_lead_form(client: MetaClient, page_id: str, *, dry_run: bool = False) -> dict:
    payload = build_form_payload()
    if dry_run:
        return {"dry_run": True, "page_id": page_id, "form": payload, "questions": build_form_questions()}
    return client._request(
        "POST",
        f"{page_id}/leadgen_forms",
        data=payload,
        use_page_token=True,
    )


def create_hiring_campaign(
    client: MetaClient,
    *,
    form_id: str,
    image_hash: str,
    daily_budget: int = DAILY_BUDGET_PAISE,
    status: str = "PAUSED",
    dry_run: bool = False,
) -> dict:
    account = client.settings.ad_account_path

    campaign_payload = {
        "name": CAMPAIGN_NAME,
        "objective": "OUTCOME_LEADS",
        "status": status,
        "special_ad_categories": json.dumps(["EMPLOYMENT"]),
        "special_ad_category_country": json.dumps(["IN"]),
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
        "targeting": json.dumps(HIRING_TARGETING),
        "status": status,
        "promoted_object": json.dumps({"page_id": PAGE_ID}),
        "regional_regulated_categories": json.dumps([]),
    }

    creative_payload = {
        "name": f"Hiring form — {AD_NAME}",
        "object_story_spec": json.dumps(
            {
                "page_id": PAGE_ID,
                "instagram_user_id": INSTAGRAM_USER_ID,
                "link_data": {
                    "link": "http://fb.me/",
                    "message": PRIMARY_TEXT,
                    "name": HEADLINE,
                    "description": DESCRIPTION,
                    "image_hash": image_hash,
                    "attachment_style": "link",
                    "call_to_action": {
                        "type": "APPLY_NOW",
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
            "image_hash": image_hash,
        }

    campaign = client._request("POST", f"{account}/campaigns", data=campaign_payload)
    campaign_id = campaign["id"]

    adset_payload["campaign_id"] = campaign_id
    adset = client._request("POST", f"{account}/adsets", data=adset_payload)
    adset_id = adset["id"]

    created = {
        "campaign_id": campaign_id,
        "campaign_name": CAMPAIGN_NAME,
        "adset_id": adset_id,
        "adset_name": ADSET_NAME,
        "form_id": form_id,
        "form_name": FORM_NAME,
        "image_hash": image_hash,
        "status": status,
        "daily_budget_inr": daily_budget / 100,
        "ads_manager_url": (
            "https://adsmanager.facebook.com/adsmanager/manage/campaigns"
            f"?act=1579547858935909&selected_campaign_ids={campaign_id}"
        ),
    }

    try:
        creative = client._request("POST", f"{account}/adcreatives", data=creative_payload)
        creative_id = creative["id"]
        ad_payload["adset_id"] = adset_id
        ad_payload["creative"] = json.dumps({"creative_id": creative_id})
        ad = client._request("POST", f"{account}/ads", data=ad_payload)
    except MetaAPIError as exc:
        created["ad_error"] = {
            "message": str(exc),
            "code": exc.code,
            "subcode": exc.subcode,
            "next_step": (
                "Meta blocked API ad creation because the app is in Development mode "
                "(#1885183). In Ads Manager, open this paused campaign, create the ad, "
                f"use image hash {image_hash} / job_hiring.png, and attach Instant Form {form_id}."
            ),
        }
        return created

    created["creative_id"] = creative_id
    created["ad_id"] = ad["id"]
    created["ad_name"] = AD_NAME
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=str(DEFAULT_IMAGE), help="Path to hiring creative")
    parser.add_argument("--form-id", help="Reuse an existing Instant Form instead of creating one")
    parser.add_argument("--image-hash", help="Reuse an uploaded image hash")
    parser.add_argument("--budget", type=int, default=DAILY_BUDGET_PAISE, help="Daily budget in paise")
    parser.add_argument("--status", default="PAUSED", choices=["ACTIVE", "PAUSED"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    client = MetaClient(settings)
    page_id, page_token = ensure_page_token(settings, client)
    page_client = MetaClient(settings, page_access_token=page_token)

    try:
        if args.image_hash:
            image = {"hash": args.image_hash, "reused": True}
        elif args.dry_run:
            image = {"hash": "dry_run_placeholder", "dry_run": True}
        else:
            image = upload_image(client, Path(args.image))

        if args.form_id:
            form_result = {"id": args.form_id, "reused": True}
        else:
            form_result = create_lead_form(page_client, page_id, dry_run=args.dry_run)
            if args.dry_run:
                print(json.dumps({"image": image, "form": form_result}, indent=2))
                return

        form_id = form_result["id"]
        result = create_hiring_campaign(
            client,
            form_id=form_id,
            image_hash=image["hash"],
            daily_budget=args.budget,
            status=args.status,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            result["form"] = form_result
            result["image"] = image
        print(json.dumps(result, indent=2))
    except MetaAPIError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "code": exc.code,
                    "subcode": exc.subcode,
                    "hint": (
                        "If Meta blocks creative creation in Development mode (#1885183), "
                        "create the ad in Ads Manager and attach this Instant Form manually."
                    ),
                },
                indent=2,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
