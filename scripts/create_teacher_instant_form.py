#!/usr/bin/env python3
"""Create the Gharka Guru teacher registration Meta Instant Form.

Creates only the lead form. It deliberately does not modify any campaign, ad
set, or ad; attach the returned form ID to a teacher campaign after review.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.meta.client import MetaAPIError, MetaClient
from app.meta.leads_sync import ensure_page_token

FORM_NAME = "Teacher Registration — Subjects, Classes & Area"
PRIVACY_URL = "https://www.gharkaguru.com/"
FOLLOW_UP_URL = "https://www.gharkaguru.com/"


def build_questions() -> list[dict]:
    """Keep high-signal matching data required while the form stays short."""
    return [
        {"type": "FULL_NAME", "key": "full_name"},
        {"type": "PHONE", "key": "phone_number"},
        {
            "type": "CUSTOM",
            "key": "teaching_mode",
            "label": "Which teaching mode do you prefer?",
            "options": [
                {"key": "home_tuition", "value": "Home tuition"},
                {"key": "online", "value": "Online"},
                {"key": "both", "value": "Both home tuition and online"},
            ],
        },
        {
            "type": "CUSTOM",
            "key": "areas_can_teach",
            "label": "Which area(s) / locality can you teach in?",
        },
        {
            "type": "CUSTOM",
            "key": "pin_code",
            "label": "What is your PIN code?",
        },
        {
            "type": "CUSTOM",
            "key": "subjects",
            "label": "Which subject(s) can you teach? (Example: Maths, Science, English)",
        },
        {
            "type": "CUSTOM",
            "key": "class_range",
            "label": "Up to which class can you teach?",
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
            "key": "qualification",
            "label": "What is your highest qualification?",
        },
        {
            "type": "CUSTOM",
            "key": "teaching_experience",
            "label": "How many years of teaching experience do you have?",
            "options": [
                {"key": "fresher", "value": "Fresher"},
                {"key": "1_2", "value": "1–2 years"},
                {"key": "3_5", "value": "3–5 years"},
                {"key": "6_plus", "value": "6+ years"},
            ],
        },
    ]


def build_payload() -> dict[str, str]:
    return {
        "name": FORM_NAME,
        "locale": "en_US",
        "follow_up_action_url": FOLLOW_UP_URL,
        "question_page_custom_headline": "Register as a Gharka Guru Teacher",
        "privacy_policy": json.dumps(
            {"url": PRIVACY_URL, "link_text": "Gharka Guru Privacy Policy"}
        ),
        "context_card": json.dumps(
            {
                "title": "Find students near you",
                "style": "LIST_STYLE",
                "content": [
                    "Teach at home, online, or both",
                    "Choose the subjects and class levels you teach",
                    "Tell us the localities where you can teach",
                    "Our team will verify your profile before matching",
                ],
            }
        ),
        "thank_you_page": json.dumps(
            {
                "title": "Thank you for registering!",
                "body": "Our team will review your profile and contact you shortly.",
                "button_type": "VIEW_WEBSITE",
                "button_text": "Visit Gharka Guru",
                "website_url": FOLLOW_UP_URL,
            }
        ),
        "questions": json.dumps(build_questions()),
        "is_optimized_for_quality": "true",
    }


def create_teacher_form(*, dry_run: bool = False) -> dict:
    settings = get_settings()
    client = MetaClient(settings)
    page_id, page_token = ensure_page_token(settings, client)
    client = MetaClient(settings, page_access_token=page_token)
    payload = build_payload()
    if dry_run:
        return {"dry_run": True, "page_id": page_id, "payload": payload}
    result = client._request(
        "POST",
        f"{page_id}/leadgen_forms",
        data=payload,
        use_page_token=True,
    )
    return {
        "form_id": result["id"],
        "form_name": FORM_NAME,
        "page_id": page_id,
        "questions": build_questions(),
        "next_step": "Attach this form ID to a teacher lead campaign/ad after reviewing it in Meta Ads Manager.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print payload without creating")
    args = parser.parse_args()
    try:
        print(json.dumps(create_teacher_form(dry_run=args.dry_run), indent=2))
    except MetaAPIError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code, "subcode": exc.subcode}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
