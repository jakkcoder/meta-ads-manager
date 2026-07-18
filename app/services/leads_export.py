import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Lead, LeadgenForm
from app.services import gcs_store

logger = logging.getLogger(__name__)

TUTOR_FORM_IDS = {
    "1332755172115131",  # Trusted Teacher
    "3888828671411723",  # Generated form 05/23/2026
    "2512058025921166",  # find_Tutors — findmyteacher ads (Gharkaguru_teacher_focus, 06/26/2026)
}

# Explicit parent allowlist (mirrors TUTOR_FORM_IDS). Forms in neither list are
# left unclassified rather than silently counted as parents, so new/unknown
# forms surface in the export result instead of skewing the parent segment.
PARENT_FORM_IDS = {
    "4495668977342555",  # getparent_new — parent_page ad (Gharkaguru_parent_instant, 06/26/2026)
    "1501785071409085",  # For parents only
    "2023094392418250",  # Parents Only - Qualified (2026-06)
    "1477904857469616",  # Book Demo - Delhi Parents (Date + Phone) — Book_Demo ad
    "2007957593939594",  # find_tutors_parent (archived)
}
TUTORS_FILENAME = "tutors.json"
PARENTS_FILENAME = "parents.json"

# A parent lead becomes "gold" once a demo is scheduled. Gold leads live on the
# dedicated Gold Leads page and are excluded from the parents.json export.
GOLD_STATUS = "Demo scheduled"

# Screening question on the qualified parent form ("I am a...").
# When present, the lead's own answer decides routing and overrides form-id mapping,
# so anyone selecting "Student"/"Teacher" is moved to the tutor segment.
SEGMENT_QUESTION_KEY = "i_am_a"
PARENT_ANSWER_KEYWORD = "parent"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _lead_record(lead: Lead, form_names: dict[str, str]) -> dict:
    fields = {field.field_name: field.field_value for field in lead.fields}
    return {
        "id": lead.id,
        "form_id": lead.form_id,
        "form_name": form_names.get(lead.form_id),
        "created_time": lead.created_time.isoformat() if lead.created_time else None,
        "ad_id": lead.ad_id,
        "adset_id": lead.adset_id,
        "campaign_id": lead.campaign_id,
        "platform": lead.platform,
        "is_organic": lead.is_organic,
        "is_junk": bool(getattr(lead, "is_junk", False)),
        "note": getattr(lead, "note", None),
        "budget": getattr(lead, "budget", None),
        "student_class": getattr(lead, "student_class", None),
        "status": getattr(lead, "status", None),
        "mode": getattr(lead, "mode", None),
        "location": getattr(lead, "location", None),
        "follow_up_count": int(getattr(lead, "follow_up_count", 0) or 0),
        "first_follow_up_at": lead.first_follow_up_at.isoformat() if lead.first_follow_up_at else None,
        "last_follow_up_at": lead.last_follow_up_at.isoformat() if lead.last_follow_up_at else None,
        "gold_transition_at": lead.gold_transition_at.isoformat() if lead.gold_transition_at else None,
        "demo_at": lead.demo_at.isoformat() if lead.demo_at else None,
        "demo_review_status": lead.demo_review_status,
        "annotation_updated_at": (
            lead.annotation_updated_at.isoformat() if lead.annotation_updated_at else None
        ),
        "fields": fields,
    }


def _all_leads(db: Session) -> list[Lead]:
    return list(db.scalars(select(Lead).order_by(Lead.created_time.desc())).all())


def _form_name_map(db: Session) -> dict[str, str]:
    forms = db.scalars(select(LeadgenForm)).all()
    return {form.id: form.name or form.id for form in forms}


def lead_segment(form_id: str, fields: dict[str, str] | None) -> str | None:
    """Return "tutors", "parents", or None (unclassified) for a lead.

    Routing precedence:
    1. The lead's own "I am a..." screening answer, when the new qualified form
       captured it. A "Parent..." answer keeps the lead in parents; any other
       answer ("Student"/"Teacher") moves it to tutors.
    2. Explicit form-id allowlists (TUTOR_FORM_IDS / PARENT_FORM_IDS). A form in
       neither list returns None so it is surfaced rather than silently counted.
    """
    answer = (fields or {}).get(SEGMENT_QUESTION_KEY)
    if answer:
        return "parents" if PARENT_ANSWER_KEYWORD in answer.strip().lower() else "tutors"
    if form_id in TUTOR_FORM_IDS:
        return "tutors"
    if form_id in PARENT_FORM_IDS:
        return "parents"
    return None


def _segment_for_record(record: dict) -> str | None:
    return lead_segment(record["form_id"], record.get("fields"))


def _split_leads(records: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    tutors: list[dict] = []
    parents: list[dict] = []
    unclassified: list[dict] = []
    for record in records:
        segment = _segment_for_record(record)
        if segment == "tutors":
            tutors.append(record)
        elif segment == "parents":
            parents.append(record)
        else:
            unclassified.append(record)
    return tutors, parents, unclassified


def _build_json_payload(records: list[dict], *, segment: str) -> dict:
    return {
        "segment": segment,
        "exported_at": _utcnow().isoformat(),
        "lead_count": len(records),
        "leads": records,
    }


def _unclassified_form_counts(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        label = f"{record.get('form_name') or '?'} ({record['form_id']})"
        counts[label] = counts.get(label, 0) + 1
    return counts


def list_parent_lead_records(db: Session, *, include_junk: bool = False) -> list[dict]:
    """Parent-segment lead records enriched with form_name, is_junk and note."""
    form_names = _form_name_map(db)
    records = [_lead_record(lead, form_names) for lead in _all_leads(db)]
    _tutors, parents, _unclassified = _split_leads(records)
    if include_junk:
        return parents
    return [record for record in parents if not record.get("is_junk")]


def build_segment_exports(
    db: Session,
) -> tuple[list[dict], list[dict], list[dict], dict, dict]:
    form_names = _form_name_map(db)
    records = [_lead_record(lead, form_names) for lead in _all_leads(db)]
    tutors, parents, unclassified = _split_leads(records)
    # Junked and gold (demo scheduled) parent leads are excluded from the
    # downstream parents.json export so the dashboard only shows fresh leads.
    parents = [
        record
        for record in parents
        if not record.get("is_junk") and record.get("status") != GOLD_STATUS
    ]
    if unclassified:
        logger.warning(
            "leads_export: %d lead(s) from forms not in TUTOR_FORM_IDS or "
            "PARENT_FORM_IDS were left unclassified: %s",
            len(unclassified),
            _unclassified_form_counts(unclassified),
        )
    return (
        tutors,
        parents,
        unclassified,
        _build_json_payload(tutors, segment="tutors"),
        _build_json_payload(parents, segment="parents"),
    )


def _leads_path(settings: Settings, filename: str) -> str:
    return f"{settings.gcs_leads_prefix}/{filename}"


def export_leads_to_gcs(db: Session, settings: Settings) -> dict:
    if not settings.gcs_leads_bucket:
        raise ValueError("GCS_LEADS_BUCKET is not set in .env")

    tutors, parents, unclassified, tutors_payload, parents_payload = build_segment_exports(db)

    tutors_path = _leads_path(settings, TUTORS_FILENAME)
    parents_path = _leads_path(settings, PARENTS_FILENAME)

    tutors_url = gcs_store.write_json(settings, tutors_path, tutors_payload)
    parents_url = gcs_store.write_json(settings, parents_path, parents_payload)

    # Keep the durable annotations store; only prune stale per-lead/segment files.
    from app.services.lead_annotations import ANNOTATIONS_FILENAME

    annotations_path = _leads_path(settings, ANNOTATIONS_FILENAME)
    gcs_store.delete_blobs_except(
        settings,
        settings.gcs_leads_prefix,
        {tutors_path, parents_path, annotations_path},
    )

    gcs_store.update_manifest_sync(
        settings,
        "leads",
        result={
            "tutor_count": len(tutors),
            "parent_count": len(parents),
            "tutors_url": tutors_url,
            "parents_url": parents_url,
        },
    )

    return {
        "tutor_count": len(tutors),
        "parent_count": len(parents),
        "unclassified_count": len(unclassified),
        "total_count": len(tutors) + len(parents),
        "bucket": settings.gcs_leads_bucket,
        "prefix": settings.gcs_leads_prefix,
        "tutors_url": tutors_url,
        "parents_url": parents_url,
    }


def load_leads_segments(settings: Settings) -> tuple[list[dict], list[dict]]:
    tutors_raw = gcs_store.read_json(settings, _leads_path(settings, TUTORS_FILENAME))
    parents_raw = gcs_store.read_json(settings, _leads_path(settings, PARENTS_FILENAME))
    tutors = tutors_raw.get("leads", []) if isinstance(tutors_raw, dict) else []
    parents = parents_raw.get("leads", []) if isinstance(parents_raw, dict) else []
    return tutors, parents
