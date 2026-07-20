#!/usr/bin/env python3
"""Create a complete Meta test lead for the new teacher Instant Form."""

from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.meta.client import MetaAPIError, MetaClient
from app.meta.leads_sync import ensure_page_token

FORM_ID = "38248227824775801"
TEST_FIELDS = {
    "full_name": "Pipeline Test Teacher",
    "phone_number": "9876543210",
    "teaching_mode": "Both home tuition and online",
    "areas_can_teach": "Dwarka Sector 12, New Delhi",
    "pin_code": "110075",
    "subjects": "Maths, Science",
    "class_range": "Class 9 to 10",
    "qualification": "B.Sc, B.Ed",
    "teaching_experience": "3–5 years",
}


def main() -> None:
    settings = get_settings()
    bootstrap = MetaClient(settings)
    _page_id, page_token = ensure_page_token(settings, bootstrap)
    client = MetaClient(settings, page_access_token=page_token)
    try:
        result = client._request(
            "POST",
            f"{FORM_ID}/test_leads",
            data={
                "field_data": json.dumps(
                    [
                        {"name": name, "values": [value]}
                        for name, value in TEST_FIELDS.items()
                    ]
                )
            },
            use_page_token=True,
        )
        print(json.dumps({"status": "ok", "form_id": FORM_ID, "result": result}, indent=2))
    except MetaAPIError as exc:
        print(
            json.dumps(
                {"status": "error", "error": str(exc), "code": exc.code, "subcode": exc.subcode},
                indent=2,
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
