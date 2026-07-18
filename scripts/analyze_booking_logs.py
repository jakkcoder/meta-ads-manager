#!/usr/bin/env python3
"""Analyze Cloud Run logs for parent booking funnel."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from urllib.parse import parse_qs, urlparse


def fetch_logs(limit: int = 500) -> list[dict]:
    cmd = [
        "gcloud",
        "logging",
        "read",
        (
            'resource.type="cloud_run_revision" AND '
            'resource.labels.service_name="meta-ads-manager" AND '
            '(httpRequest.requestUrl=~"/book/" OR httpRequest.requestUrl=~"/api/book/")'
        ),
        "--project=vertex-ai-learning-487906",
        f"--limit={limit}",
        "--format=json",
        "--freshness=7d",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout or "[]")


def is_bot(ua: str) -> bool:
    return "facebookexternalhit" in ua or "Facebot" in ua


def is_internal(ua: str) -> bool:
    return any(x in ua for x in ("curl/", "python-httpx", "Macintosh"))


def main() -> int:
    entries = fetch_logs()
    print(f"Total log entries scanned: {len(entries)}")

    posts: list[tuple] = []
    bots = 0
    form_by_fbclid: dict[str, dict] = {}
    slot_times: list[str] = []
    form_loads_real = 0

    for entry in entries:
        hr = entry.get("httpRequest", {})
        url = hr.get("requestUrl", "")
        path = urlparse(url).path
        qs = parse_qs(urlparse(url).query)
        method = hr.get("requestMethod", "")
        status = hr.get("status", "")
        ua = hr.get("userAgent", "")
        ts = entry.get("timestamp", "")
        fbclid = (qs.get("fbclid") or [""])[0]

        if is_bot(ua):
            bots += 1
            continue
        if is_internal(ua):
            continue

        if method == "POST" and path == "/api/book/parent":
            posts.append((ts, status, ua[:80]))
        elif path == "/api/book/parent/slots" and method == "GET":
            slot_times.append(ts)
        elif path == "/book/parent" and method == "GET":
            form_loads_real += 1
            key = fbclid or f"no-fbclid:{ts}"
            row = form_by_fbclid.setdefault(
                key,
                {"first": ts, "loads": 0, "ua": ua[:90], "has_fbclid": bool(fbclid)},
            )
            row["loads"] += 1
            if ts < row["first"]:
                row["first"] = ts

    paid = {k: v for k, v in form_by_fbclid.items() if v["has_fbclid"]}

    print("\n=== SUMMARY ===")
    print(f"Meta crawler requests skipped: {bots}")
    print(f"Real GET /book/parent loads: {form_loads_real}")
    print(f"Unique visitors with fbclid (paid ad): {len(paid)}")
    print(f"GET /api/book/parent/slots (form JS ran): {len(slot_times)}")
    print(f"POST /api/book/parent (submissions): {len(posts)}")

    print("\n=== PAID AD VISITORS WHO HIT THE FORM ===")
    for i, (fbclid, info) in enumerate(
        sorted(paid.items(), key=lambda x: x[1]["first"]), 1
    ):
        device = "Instagram/Facebook WebView" if "wv" in info["ua"] else info["ua"][:40]
        print(f"{i}. {info['first']}")
        print(f"   loads={info['loads']} | {device}")

    if posts:
        print("\n=== FORM SUBMISSIONS ===")
        for post in posts:
            print(" ", post)
    else:
        print("\nNo POST /api/book/parent submissions in logs.")

    print("\n=== FUNNEL ===")
    print(f"Paid clicks that opened form page: {len(paid)}")
    print(f"Form became interactive (slots API): {len(slot_times)}")
    print(f"Completed booking: {len(posts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
