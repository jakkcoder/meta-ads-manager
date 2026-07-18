#!/usr/bin/env python3
"""List, upload, and delete images in the Meta ad account image library."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path

import httpx

from app.config import get_settings
from app.meta.client import MetaAPIError, MetaClient

PARENT_AD_ID = "120244318006400227"
HOMETUTOR_HASH = "8bb194c7837bd61c209856189b07b27f"

DEFAULT_UPLOADS = [
    Path("/Users/jay/Downloads/hometutor.png"),
    Path("/Users/jay/Downloads/Gemini_Generated_Image_6dju0z6dju0z6dju.png"),
    Path("/Users/jay/Downloads/Gemini_Generated_Image_v85fg0v85fg0v85f.png"),
    Path("/Users/jay/Downloads/Gemini_Generated_Image_tq9djftq9djftq9d.png"),
    Path("/Users/jay/Downloads/Gemini_Generated_Image_3amzor3amzor3amz.png"),
    Path("/Users/jay/Downloads/WhatsApp Image 2026-06-13 at 09.40.50.jpeg"),
    Path("/Users/jay/Downloads/WhatsApp Image 2026-06-13 at 09.51.48.jpeg"),
]


def list_images(client: MetaClient) -> list[dict]:
    return client._paginate(
        f"{client.settings.ad_account_path}/adimages",
        params={"fields": "hash,name,url,created_time,width,height,status"},
    )


def hashes_in_use(client: MetaClient) -> set[str]:
    used: set[str] = set()
    ads = client._paginate(
        f"{client.settings.ad_account_path}/ads",
        params={"fields": "creative{object_story_spec}"},
    )
    for ad in ads:
        spec = (ad.get("creative") or {}).get("object_story_spec") or {}
        for block in (spec.get("link_data"), spec.get("video_data")):
            if block and block.get("image_hash"):
                used.add(block["image_hash"])
    return used


def upload_image(client: MetaClient, path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)
    token = client.settings.meta_access_token
    account = client.settings.ad_account_path
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        response = httpx.post(
            f"https://graph.facebook.com/{client.settings.meta_api_version}/{account}/adimages",
            data={"filename": path.name, "access_token": token},
            files={"source": (path.name, handle, mime)},
            timeout=120.0,
        )
    payload = response.json()
    if "error" in payload:
        raise MetaAPIError(payload["error"].get("message", "Upload failed"))
    images = payload.get("images") or {}
    entry = images.get(path.name) or next(iter(images.values()), {})
    return {
        "file": str(path),
        "hash": entry.get("hash"),
        "url": entry.get("url"),
        "width": entry.get("width"),
        "height": entry.get("height"),
    }


def delete_image(client: MetaClient, image_hash: str) -> dict:
    token = client.settings.meta_access_token
    account = client.settings.ad_account_path
    response = httpx.delete(
        f"https://graph.facebook.com/{client.settings.meta_api_version}/{account}/adimages",
        params={"hash": image_hash, "access_token": token},
        timeout=60.0,
    )
    payload = response.json()
    if "error" in payload:
        raise MetaAPIError(payload["error"].get("message", "Delete failed"))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Meta ad account images")
    parser.add_argument("action", choices=["list", "upload", "delete-unused", "use-on-parent-ad"])
    parser.add_argument("paths", nargs="*", help="Image files to upload")
    parser.add_argument("--hash", help="Image hash to target")
    parser.add_argument("--keep", nargs="*", help="Hashes to keep when deleting unused")
    args = parser.parse_args()

    settings = get_settings()
    client = MetaClient(settings)

    if args.action == "list":
        used = hashes_in_use(client)
        rows = []
        for img in list_images(client):
            rows.append(
                {
                    **img,
                    "in_use": img["hash"] in used,
                }
            )
        print(json.dumps({"count": len(rows), "images": rows}, indent=2))
        return

    if args.action == "upload":
        paths = [Path(p) for p in args.paths] if args.paths else DEFAULT_UPLOADS
        results = []
        for path in paths:
            if not path.exists():
                results.append({"file": str(path), "error": "not found"})
                continue
            try:
                results.append(upload_image(client, path))
            except (MetaAPIError, OSError) as exc:
                results.append({"file": str(path), "error": str(exc)})
        print(json.dumps({"uploaded": results}, indent=2))
        return

    if args.action == "delete-unused":
        used = hashes_in_use(client)
        keep = set(args.keep or []) | used
        deleted = []
        skipped = []
        errors = []
        for img in list_images(client):
            h = img["hash"]
            if h in keep:
                skipped.append({"hash": h, "name": img.get("name"), "reason": "in_use_or_keep"})
                continue
            try:
                delete_image(client, h)
                deleted.append({"hash": h, "name": img.get("name")})
            except MetaAPIError as exc:
                errors.append({"hash": h, "name": img.get("name"), "error": str(exc)})
        print(json.dumps({"deleted": deleted, "skipped": skipped, "errors": errors}, indent=2))
        return

    if args.action == "use-on-parent-ad":
        image_hash = args.hash or HOMETUTOR_HASH
        from scripts.switch_ad_to_website import switch_ad_to_website

        booking_url = (
            "https://meta-ads-manager-lmquvtnfja-el.a.run.app/book/instagram"
            "?utm_campaign=Gharkaguru_parent_web"
        )
        ad = client._request(
            "GET",
            PARENT_AD_ID,
            params={"fields": "creative{object_story_spec}"},
        )
        spec = dict(ad["creative"]["object_story_spec"])
        spec["link_data"] = dict(spec["link_data"])
        spec["link_data"]["image_hash"] = image_hash
        spec["link_data"]["link"] = booking_url
        spec["link_data"]["call_to_action"] = {
            "type": "SIGN_UP",
            "value": {"link": booking_url},
        }
        account = client.settings.ad_account_path
        payload = {
            "name": "Website booking — hometutor image",
            "object_story_spec": json.dumps(spec),
        }
        try:
            creative = client._request("POST", f"{account}/adcreatives", data=payload)
            updated = client._request(
                "POST",
                PARENT_AD_ID,
                data={"creative": json.dumps({"creative_id": creative["id"]})},
            )
            print(json.dumps({"success": True, "creative_id": creative["id"], "image_hash": image_hash, "ad": updated}, indent=2))
        except MetaAPIError as exc:
            print(json.dumps({"success": False, "error": str(exc), "image_hash": image_hash, "manual": "Update image in Ads Manager"}, indent=2))
            sys.exit(1)


if __name__ == "__main__":
    main()
