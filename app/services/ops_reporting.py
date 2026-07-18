"""Parent-lead operational reporting and alert evaluation."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.leads_export import GOLD_STATUS, list_parent_lead_records

FIRST_FOLLOW_UP_SLA_MINUTES = 15
GOLD_STALE_DAYS = 3
REVIEWABLE_DEMO_STATUSES = {"pending", "rescheduled"}
FINAL_DEMO_STATUSES = {"completed", "converted", "not_converted", "cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _phone(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits if len(digits) == 10 else None


def _age_hours(when: datetime | None, now: datetime) -> float | None:
    if when is None:
        return None
    return max(0.0, (now - when).total_seconds() / 3600)


def build_parent_ops_report(db: Session) -> dict[str, Any]:
    """Return current parent-lead queue, SLA, repeat, gold and demo-review metrics."""
    now = _now()
    records = [
        record
        for record in list_parent_lead_records(db, include_junk=False)
        if not record.get("is_junk")
    ]

    phone_groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        phone = _phone((record.get("fields") or {}).get("phone_number"))
        if phone:
            phone_groups.setdefault(phone, []).append(record)

    repeat_leads = []
    for phone, grouped in phone_groups.items():
        if len(grouped) > 1:
            repeat_leads.append(
                {
                    "phone": phone,
                    "count": len(grouped),
                    "lead_ids": [lead["id"] for lead in grouped],
                    "latest_created_at": max(
                        (lead.get("created_time") or "" for lead in grouped), default=""
                    ),
                }
            )
    repeat_leads.sort(key=lambda item: (-item["count"], item["latest_created_at"]), reverse=True)

    overdue_follow_ups = []
    gold_aging = []
    demos_pending_review = []
    today = now.date()
    for lead in records:
        created_at = _as_datetime(lead.get("created_time"))
        first_follow_up = _as_datetime(lead.get("first_follow_up_at"))
        hours_open = _age_hours(created_at, now)
        if (
            lead.get("status") != GOLD_STATUS
            and not first_follow_up
            and hours_open is not None
            and hours_open >= FIRST_FOLLOW_UP_SLA_MINUTES / 60
        ):
            overdue_follow_ups.append({**lead, "hours_open": round(hours_open, 1)})

        gold_at = _as_datetime(lead.get("gold_transition_at"))
        if lead.get("status") == GOLD_STATUS:
            age_days = int((_age_hours(gold_at, now) or 0) // 24)
            gold_aging.append({**lead, "gold_age_days": age_days})

        demo_at = _as_datetime(lead.get("demo_at"))
        review_status = (lead.get("demo_review_status") or "pending").lower()
        if demo_at and demo_at.date() <= today and review_status not in FINAL_DEMO_STATUSES:
            demos_pending_review.append({**lead, "demo_review_status": review_status})

    overdue_follow_ups.sort(key=lambda lead: lead["hours_open"], reverse=True)
    gold_aging.sort(key=lambda lead: lead["gold_age_days"], reverse=True)
    demos_pending_review.sort(key=lambda lead: lead.get("demo_at") or "")
    stale_gold = [lead for lead in gold_aging if lead["gold_age_days"] >= GOLD_STALE_DAYS]

    leads_today = sum(
        1
        for record in records
        if (created_at := _as_datetime(record.get("created_time"))) is not None
        and created_at.date() == today
    )
    return {
        "generated_at": now.isoformat(),
        "thresholds": {
            "first_follow_up_minutes": FIRST_FOLLOW_UP_SLA_MINUTES,
            "gold_stale_days": GOLD_STALE_DAYS,
        },
        "kpis": {
            "parent_leads_total": len(records),
            "parent_leads_today": leads_today,
            "repeat_phone_groups": len(repeat_leads),
            "overdue_first_follow_ups": len(overdue_follow_ups),
            "gold_leads": len(gold_aging),
            "stale_gold_leads": len(stale_gold),
            "demos_pending_review": len(demos_pending_review),
        },
        "repeat_leads": repeat_leads[:50],
        "overdue_follow_ups": overdue_follow_ups[:100],
        "gold_aging": gold_aging[:100],
        "demos_pending_review": demos_pending_review[:100],
    }


def build_alerts(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return actionable alert payloads suitable for a webhook or scheduled check."""
    alerts: list[dict[str, Any]] = []
    kpis = report["kpis"]
    if kpis["overdue_first_follow_ups"]:
        alerts.append(
            {
                "type": "overdue_first_follow_up",
                "count": kpis["overdue_first_follow_ups"],
                "lead_ids": [lead["id"] for lead in report["overdue_follow_ups"]],
            }
        )
    if kpis["stale_gold_leads"]:
        alerts.append(
            {
                "type": "stale_gold",
                "count": kpis["stale_gold_leads"],
                "lead_ids": [
                    lead["id"]
                    for lead in report["gold_aging"]
                    if lead["gold_age_days"] >= GOLD_STALE_DAYS
                ],
            }
        )
    if kpis["demos_pending_review"]:
        alerts.append(
            {
                "type": "demos_pending_review",
                "count": kpis["demos_pending_review"],
                "lead_ids": [lead["id"] for lead in report["demos_pending_review"]],
            }
        )
    return alerts
