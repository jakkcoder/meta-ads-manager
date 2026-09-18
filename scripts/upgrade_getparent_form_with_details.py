#!/usr/bin/env python3
"""Create parent instant form with matching fields (name, phone, mode, area, subjects, class, demo); switch active ads."""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.meta.client import MetaClient, MetaAPIError

PAGE_ID = "347244005670587"
OLD_FORM_ID = "4495668977342555"
REFERENCE_FORM_ID = "4495668977342555"  # getparent_new — copy intro/branding from this form
COVER_PHOTO_ID = "1648320410636676"  # context_card background on getparent_new
PRIVACY_URL = "https://gharkaguru.com/privacy"
FOLLOW_UP_URL = "https://www.gharkaguru.com/"
FORM_NAME = "getparent_new_with_details_v5"


def _subject_options() -> list[dict[str, str]]:
    return [
        {"key": "all_subjects", "value": "All subjects"},
        {"key": "maths", "value": "Maths"},
        {"key": "science", "value": "Science"},
        {"key": "english", "value": "English"},
        {"key": "other", "value": "Other"},
    ]


def _demo_date_options() -> list[dict[str, str]]:
    return [
        {"key": "this_week", "value": "This week"},
        {"key": "next_week", "value": "Next week"},
    ]


def build_context_card() -> dict:
    """Match getparent_new intro card: list bullets + cover photo background."""
    return {
        "title": "Get 2 FREE Home Tuition Classes",
        "style": "LIST_STYLE",
        "content": [
            "1-on-1 home  tuition for all classes & subjects",
            "Verified, experienced tutors (IIT/NIT backgrounds)",
            "Affordable: starting at just ₹200/hour",
        ],
        "cover_photo_id": COVER_PHOTO_ID,
    }


def build_form_questions() -> list[dict]:
    """Mirror teacher matching fields (no pincode): mode, area, subjects, class, demo timing."""
    return [
        {"type": "FULL_NAME", "key": "full_name"},
        {"type": "PHONE", "key": "phone_number"},
        {
            "type": "CUSTOM",
            "key": "teaching_mode",
            "label": "What type of tuition do you need?",
            "options": [
                {"key": "home_tuition", "value": "Home tuition"},
                {"key": "online", "value": "Online"},
                {"key": "both", "value": "Both home tuition and online"},
            ],
        },
        {
            "type": "CUSTOM",
            "key": "area_locality",
            "label": "Which area / locality do you need tuition in?",
        },
        {
            "type": "CUSTOM",
            "key": "subjects",
            "label": "Which subject(s) does your child need?",
            "options": _subject_options(),
        },
        {
            "type": "CUSTOM",
            "key": "class_range",
            "label": "Which class is your child in?",
            "options": [
                {"key": "pre_primary_5", "value": "Pre-primary to Class 5"},
                {"key": "class_6_8", "value": "Class 6 to 8"},
                {"key": "class_9_10", "value": "Class 9 to 10"},
                {"key": "class_11_12", "value": "Class 11 to 12"},
                {"key": "college_competitive", "value": "College / competitive exams"},
            ],
        },
        {
            "type": "CUSTOM",
            "key": "when_do_you_want_the_demo_for_your_child?",
            "label": "When do you want the demo for your child?",
            "options": _demo_date_options(),
        },
    ]


def create_form(client: MetaClient, *, dry_run: bool = False) -> dict:
    payload = {
        "name": FORM_NAME,
        "locale": "en_US",
        "follow_up_action_url": FOLLOW_UP_URL,
        "question_page_custom_headline": "Match your child with a suitable verified tutor",
        "privacy_policy": json.dumps(
            {"url": PRIVACY_URL, "link_text": "GharKaGuru Privacy Policy"}
        ),
        "context_card": json.dumps(build_context_card()),
        "questions": json.dumps(build_form_questions()),
        "block_display_for_non_targeted_viewer": "true",
        "allow_organic_lead": "false",
        "is_optimized_for_quality": "false",
    }
    if dry_run:
        return {
            "dry_run": True,
            "questions": build_form_questions(),
            "context_card": build_context_card(),
            "payload_keys": list(payload.keys()),
        }
    return client._request(
        "POST",
        f"{PAGE_ID}/leadgen_forms",
        data=payload,
        use_page_token=True,
    )


def list_ads_on_form(client: MetaClient, form_id: str) -> list[str]:
    account = client.settings.ad_account_path
    ads = client._paginate(
        f"{account}/ads",
        params={
            "fields": "id,name,status,effective_status,creative{object_story_spec}",
            "limit": 100,
        },
    )
    out: list[str] = []
    for ad in ads:
        creative = (ad.get("creative") or {}).get("object_story_spec") or {}
        link = creative.get("link_data") or {}
        cta = link.get("call_to_action") or {}
        fid = (cta.get("value") or {}).get("lead_gen_form_id")
        if str(fid) == str(form_id) and ad.get("effective_status") in ("ACTIVE", "PAUSED", None):
            out.append(ad["id"])
    return out


def switch_ad(client: MetaClient, ad_id: str, form_id: str, *, dry_run: bool = False) -> dict:
    ad = client._request(
        "GET",
        ad_id,
        params={"fields": "id,name,status,creative{id,name,object_story_spec}"},
    )
    creative = ad.get("creative") or {}
    spec = creative.get("object_story_spec") or {}
    link_data = dict(spec.get("link_data") or {})
    page_id = spec.get("page_id") or PAGE_ID
    instagram_user_id = spec.get("instagram_user_id")
    if not link_data:
        raise RuntimeError(f"Unexpected creative structure for ad {ad_id}")

    new_link_data = {
        "link": "http://fb.me/",
        "message": link_data.get("message") or "Home Tutors for Your Child — 2 Free Demos",
        "name": link_data.get("name") or "Book a Free Demo Class",
        "description": link_data.get("description") or "Help Your Child Learn at Home",
        "call_to_action": {
            "type": "SIGN_UP",
            "value": {"lead_gen_form_id": form_id},
        },
    }
    if link_data.get("image_hash"):
        new_link_data["image_hash"] = link_data["image_hash"]
    if link_data.get("attachment_style"):
        new_link_data["attachment_style"] = link_data["attachment_style"]

    object_story_spec: dict = {"page_id": page_id, "link_data": new_link_data}
    if instagram_user_id:
        object_story_spec["instagram_user_id"] = instagram_user_id

    payload = {
        "name": f"Instant form — {ad.get('name', ad_id)}",
        "object_story_spec": json.dumps(object_story_spec),
    }
    if dry_run:
        return {"dry_run": True, "ad_id": ad_id, "form_id": form_id, "payload": object_story_spec}

    account = client.settings.ad_account_path
    new_creative = client._request("POST", f"{account}/adcreatives", data=payload)
    creative_id = new_creative["id"]
    updated = client._request(
        "POST",
        ad_id,
        data={"creative": json.dumps({"creative_id": creative_id})},
    )
    return {
        "ad_id": ad_id,
        "form_id": form_id,
        "new_creative_id": creative_id,
        "meta_response": updated,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ad-id", action="append", dest="ad_ids", help="Ad to switch (default: auto-detect)")
    parser.add_argument("--skip-create", action="store_true", help="Use --form-id instead of creating")
    parser.add_argument("--form-id", help="Existing form id when --skip-create")
    args = parser.parse_args()

    client = MetaClient(get_settings())
    try:
        if args.skip_create:
            if not args.form_id:
                raise SystemExit("--form-id required with --skip-create")
            new_form_id = args.form_id
            created = {"id": new_form_id, "skipped_create": True}
        else:
            created = create_form(client, dry_run=args.dry_run)
            if args.dry_run:
                print(json.dumps({"create": created}, indent=2))
                return
            new_form_id = created["id"]

        ad_ids = args.ad_ids or list_ads_on_form(client, OLD_FORM_ID)
        switched = []
        switch_errors: list[str] = []
        for ad_id in ad_ids:
            try:
                switched.append(switch_ad(client, ad_id, new_form_id, dry_run=args.dry_run))
            except MetaAPIError as exc:
                switch_errors.append(f"{ad_id}: {exc} (code={exc.code}, subcode={exc.subcode})")

        print(
            json.dumps(
                {
                    "new_form_id": new_form_id,
                    "old_form_id": OLD_FORM_ID,
                    "form_create": created,
                    "ads_switched": switched,
                    "switch_errors": switch_errors,
                    "add_to_PARENT_FORM_IDS": new_form_id,
                    "manual_step": (
                        "If ad switch failed (Meta dev mode), attach this form in Ads Manager "
                        "to ad parent_page, then set PARENT_FORM_IDS_EXTRA to new_form_id."
                    ),
                },
                indent=2,
            )
        )
        if switch_errors and not switched:
            sys.exit(0)
    except MetaAPIError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code, "subcode": exc.subcode}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
