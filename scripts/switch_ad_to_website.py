#!/usr/bin/env python3
"""Switch a Meta lead-gen ad to use the Gharkaguru website booking form."""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.meta.client import MetaClient

DEFAULT_AD_ID = "120244310809090227"
DEFAULT_BOOKING_URL = (
    "https://meta-ads-manager-lmquvtnfja-el.a.run.app/book/instagram"
    "?utm_campaign=Gharkaguru_parent_delhi_ncr"
)


def switch_ad_to_website(
    client: MetaClient,
    ad_id: str,
    booking_url: str,
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

    page_id = spec.get("page_id")
    instagram_user_id = spec.get("instagram_user_id")
    if not page_id or not link_data:
        raise RuntimeError(f"Unexpected creative structure for ad {ad_id}")

    new_link_data = {
        "link": booking_url,
        "message": link_data.get("message") or "Home Tutors for Your Child — 2 Free Demos",
        "name": link_data.get("name") or "Book a free demo class",
        "description": link_data.get("description")
        or "Parents: book 2 FREE demo classes. Class 1–12, online or at home.",
        "call_to_action": {
            "type": "LEARN_MORE",
            "value": {"link": booking_url},
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
        "name": f"Website booking — {ad.get('name', ad_id)}",
        "object_story_spec": json.dumps(object_story_spec),
    }

    if dry_run:
        return {"dry_run": True, "ad_id": ad_id, "payload": json.loads(payload["object_story_spec"]), "payload_name": payload["name"]}

    account = client.settings.ad_account_path
    new_creative = client._request("POST", f"{account}/adcreatives", data=payload)
    creative_id = new_creative["id"]

    updated = client._request("POST", ad_id, data={"creative": json.dumps({"creative_id": creative_id})})
    return {
        "ad_id": ad_id,
        "ad_name": ad.get("name"),
        "old_creative_id": creative.get("id"),
        "new_creative_id": creative_id,
        "booking_url": booking_url,
        "meta_response": updated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Switch Meta ad from instant form to website booking URL")
    parser.add_argument("--ad-id", default=DEFAULT_AD_ID)
    parser.add_argument("--url", default=DEFAULT_BOOKING_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    client = MetaClient(settings)
    result = switch_ad_to_website(client, args.ad_id, args.url, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
