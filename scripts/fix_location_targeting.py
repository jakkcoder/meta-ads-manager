#!/usr/bin/env python3
"""Fix deprecated Meta location_types targeting (error #1870194 / #1870199)."""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.meta.client import MetaClient, MetaAPIError

# Delhi NCT region key (preferred over city + location_types).
DELHI_REGION_KEY = "1728"
DEFAULT_ADSET_ID = "120244317980760227"


def build_targeting(current: dict) -> dict:
    geo = dict(current.get("geo_locations") or {})
    geo.pop("location_types", None)
    geo.pop("cities", None)
    geo.pop("custom_locations", None)
    geo.pop("places", None)
    geo["regions"] = [{"key": DELHI_REGION_KEY}]

    return {
        "age_min": current.get("age_min", 28),
        "age_max": current.get("age_max", 55),
        "genders": current.get("genders", [2]),
        "geo_locations": geo,
        "targeting_automation": current.get(
            "targeting_automation", {"advantage_audience": 0}
        ),
        "publisher_platforms": current.get(
            "publisher_platforms", ["facebook", "instagram"]
        ),
        "facebook_positions": current.get(
            "facebook_positions", ["feed", "story", "facebook_reels", "marketplace"]
        ),
        "instagram_positions": current.get(
            "instagram_positions", ["stream", "story", "reels", "profile_feed"]
        ),
        "device_platforms": current.get("device_platforms", ["mobile"]),
    }


def fix_adset(client: MetaClient, adset_id: str, *, dry_run: bool = False) -> dict:
    current = client._request("GET", adset_id, params={"fields": "name,targeting"})
    targeting = build_targeting(current["targeting"])
    payload = {"targeting": json.dumps(targeting)}

    if dry_run:
        return {
            "adset_id": adset_id,
            "name": current["name"],
            "dry_run": True,
            "targeting": targeting,
        }

    client._request("POST", adset_id, data=payload)
    updated = client._request(
        "GET",
        adset_id,
        params={"fields": "name,effective_status,targeting,issues_info"},
    )
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adset-id", default=DEFAULT_ADSET_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = MetaClient(get_settings())
    try:
        result = fix_adset(client, args.adset_id, dry_run=args.dry_run)
    except MetaAPIError as exc:
        print(f"Meta API error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
