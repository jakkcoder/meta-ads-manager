"""Durable, GCS-backed per-lead annotations (junk flag + free-text note).

The local SQLite DB is a cache that is rebuilt from Meta on every sync, and
Cloud Run's filesystem is ephemeral. User-generated junk/note data therefore
lives in a single GCS object so it survives restarts, and is overlaid back onto
the `leads` table after each sync (and on page load).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Lead
from app.services import gcs_store

logger = logging.getLogger(__name__)

ANNOTATIONS_FILENAME = "annotations.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _annotations_path(settings: Settings) -> str:
    return f"{settings.gcs_leads_prefix}/{ANNOTATIONS_FILENAME}"


def load_annotations(settings: Settings) -> dict[str, dict[str, Any]]:
    """Return the `{lead_id: {is_junk, note, updated_at}}` map from GCS."""
    if not settings.gcs_leads_bucket:
        return {}
    try:
        raw = gcs_store.read_json(settings, _annotations_path(settings))
    except Exception as exc:  # GCS/auth issues should not break the UI
        logger.warning("lead_annotations: could not read annotations.json: %s", exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    annotations = raw.get("annotations")
    return annotations if isinstance(annotations, dict) else {}


def _write_annotations(settings: Settings, annotations: dict[str, dict[str, Any]]) -> None:
    payload = {"updated_at": _utcnow_iso(), "annotations": annotations}
    gcs_store.write_json(settings, _annotations_path(settings), payload)


def save_annotation(
    settings: Settings,
    lead_id: str,
    *,
    is_junk: bool | None = None,
    note: str | None = None,
    budget: str | None = None,
    student_class: str | None = None,
    status: str | None = None,
    mode: str | None = None,
    location: str | None = None,
    follow_up_count: int | None = None,
    first_follow_up_at: datetime | None = None,
    last_follow_up_at: datetime | None = None,
    gold_transition_at: datetime | None = None,
    demo_at: datetime | None = None,
    demo_review_status: str | None = None,
    event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-modify-write a single lead's annotation in GCS and return it."""
    if not settings.gcs_leads_bucket:
        raise ValueError("GCS_LEADS_BUCKET is not set in .env")

    annotations = load_annotations(settings)
    current = dict(annotations.get(lead_id) or {})
    if is_junk is not None:
        current["is_junk"] = bool(is_junk)
    if note is not None:
        current["note"] = note
    if budget is not None:
        current["budget"] = budget
    if student_class is not None:
        current["student_class"] = student_class
    if status is not None:
        current["status"] = status
    if mode is not None:
        current["mode"] = mode
    if location is not None:
        current["location"] = location
    if follow_up_count is not None:
        current["follow_up_count"] = int(follow_up_count)
    for key, value in {
        "first_follow_up_at": first_follow_up_at,
        "last_follow_up_at": last_follow_up_at,
        "gold_transition_at": gold_transition_at,
        "demo_at": demo_at,
    }.items():
        if value is not None:
            current[key] = value.isoformat()
    if demo_review_status is not None:
        current["demo_review_status"] = demo_review_status
    if event is not None:
        events = list(current.get("events") or [])
        events.append({"occurred_at": _utcnow_iso(), **event})
        current["events"] = events[-100:]
    current["updated_at"] = _utcnow_iso()

    annotations[lead_id] = current
    _write_annotations(settings, annotations)
    return current


def apply_annotations_to_db(db: Session, settings: Settings) -> int:
    """Overlay GCS annotations onto local `Lead` rows. Returns rows updated."""
    annotations = load_annotations(settings)
    if not annotations:
        return 0

    updated = 0
    leads = db.scalars(select(Lead).where(Lead.id.in_(list(annotations.keys())))).all()
    for lead in leads:
        ann = annotations.get(lead.id) or {}
        lead.is_junk = bool(ann.get("is_junk", False))
        lead.note = ann.get("note")
        lead.budget = ann.get("budget")
        lead.student_class = ann.get("student_class")
        lead.status = ann.get("status")
        lead.mode = ann.get("mode")
        lead.location = ann.get("location")
        lead.follow_up_count = int(ann.get("follow_up_count", 0) or 0)
        lead.first_follow_up_at = _parse_iso(ann.get("first_follow_up_at"))
        lead.last_follow_up_at = _parse_iso(ann.get("last_follow_up_at"))
        lead.gold_transition_at = _parse_iso(ann.get("gold_transition_at"))
        lead.demo_at = _parse_iso(ann.get("demo_at"))
        lead.demo_review_status = ann.get("demo_review_status")
        lead.annotation_updated_at = _parse_iso(ann.get("updated_at"))
        updated += 1

    if updated:
        db.commit()
    return updated


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None
