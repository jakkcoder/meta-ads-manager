#!/usr/bin/env python3
"""Switch a Meta website-traffic ad to use a Meta Instant Form (lead gen on ad)."""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.meta.client import MetaClient, MetaAPIError

DEFAULT_AD_ID = "120244318006400227"
DEFAULT_FORM_ID = "1477904857469616"  # Book Demo - Delhi Parents (Date + Phone)
PAGE_ID = "347244005670587"


def switch_ad_to_instant_form(
    client: MetaClient,
    ad_id: str,
    form_id: str,
    *,
    dry_run: bool = False,
) -> dict:
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
        return {
            "dry_run": True,
            "ad_id": ad_id,
            "form_id": form_id,
            "payload": json.loads(payload["object_story_spec"]),
            "payload_name": payload["name"],
        }

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
        "ad_name": ad.get("name"),
        "form_id": form_id,
        "old_creative_id": creative.get("id"),
        "new_creative_id": creative_id,
        "meta_response": updated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Switch Meta ad from website URL to Meta Instant Form"
    )
    parser.add_argument("--ad-id", default=DEFAULT_AD_ID)
    parser.add_argument("--form-id", default=DEFAULT_FORM_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = MetaClient(get_settings())
    try:
        result = switch_ad_to_instant_form(
            client,
            args.ad_id,
            args.form_id,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
    except MetaAPIError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "code": exc.code,
                    "subcode": exc.subcode,
                    "hint": (
                        "Meta blocks ad creative creation while the app is in "
                        "Development mode (#1885183). Create the ad in Ads Manager "
                        "and attach the instant form manually."
                    ),
                },
                indent=2,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
