from __future__ import annotations

import hashlib
import logging

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import repositories as repo
from app.db.session import get_db
from app.services.ops_reporting import build_alerts, build_parent_ops_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ops", tags=["operations"])


@router.get("/report")
def ops_report(db: Session = Depends(get_db)):
    return build_parent_ops_report(db)


@router.post("/check-alerts")
def check_alerts(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
):
    report = build_parent_ops_report(db)
    alerts = build_alerts(report)
    delivered: list[dict] = []
    for alert in alerts:
        digest = hashlib.sha256(
            f"{alert['type']}:{','.join(sorted(alert['lead_ids']))}".encode()
        ).hexdigest()[:24]
        alert_key = f"{alert['type']}:{digest}"
        if repo.alert_seen(db, alert_key):
            continue
        if settings.ops_alert_webhook_url:
            try:
                response = httpx.post(
                    settings.ops_alert_webhook_url,
                    json={"report_generated_at": report["generated_at"], **alert},
                    timeout=10,
                )
                response.raise_for_status()
            except Exception as exc:
                logger.exception("Failed to deliver operational alert: %s", exc)
                continue
        repo.record_alert(db, alert_key, alert["type"], alert)
        delivered.append(alert)
    return {"alerts": alerts, "newly_delivered": delivered, "report": report["kpis"]}
