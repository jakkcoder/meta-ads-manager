#!/usr/bin/env python3
"""Batch entrypoint for incremental Meta → GCS teacher lead ingestion."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from app.config import get_settings
from app.db.session import SessionLocal, init_db
from app.services.sync_all import run_ads_sync, run_insights_sync, run_leads_sync


def main() -> None:
    init_db()
    settings = get_settings()
    db = SessionLocal()
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        # Ads are a small inventory; full refresh guarantees every enabled ad,
        # ad set, campaign, creative, and attached lead form is current.
        result = {
            "started_at": started_at,
            "ads": run_ads_sync(db, settings, full=True),
            # Lead cursor survives job restarts through GCS manifest cursors.
            "leads": run_leads_sync(db, settings, full=False, export=True),
            "insights": run_insights_sync(db, settings, full=False),
            "status": "ok",
        }
        print(json.dumps(result, indent=2, default=str))
    except Exception as exc:
        print(json.dumps({"started_at": started_at, "status": "error", "error": str(exc)}))
        raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
