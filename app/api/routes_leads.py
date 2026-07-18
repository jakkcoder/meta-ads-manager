import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import repositories as repo
from app.db.session import get_db
from app.services import lead_annotations

router = APIRouter(prefix="/api/leads", tags=["leads"])


class LeadAnnotationUpdate(BaseModel):
    is_junk: bool | None = None
    note: str | None = None
    budget: str | None = None
    student_class: str | None = None
    status: str | None = None
    mode: str | None = None
    location: str | None = None
    increment_follow_up: bool | None = None
    demo_at: datetime | None = None
    demo_review_status: str | None = None


def _serialize_lead(lead) -> dict:
    fields = {f.field_name: f.field_value for f in lead.fields}
    return {
        "id": lead.id,
        "form_id": lead.form_id,
        "created_time": lead.created_time.isoformat() if lead.created_time else None,
        "ad_id": lead.ad_id,
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
        "full_name": fields.get("full_name"),
        "email": fields.get("email"),
        "phone_number": fields.get("phone_number"),
        "fields": fields,
    }


@router.get("")
def get_leads(
    form_id: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    leads = repo.list_leads(db, form_id=form_id, search=search, limit=limit, offset=offset)
    return [_serialize_lead(lead) for lead in leads]


@router.patch("/{lead_id}")
def update_lead_annotation(
    lead_id: str,
    payload: LeadAnnotationUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if (
        payload.is_junk is None
        and payload.note is None
        and payload.budget is None
        and payload.student_class is None
        and payload.status is None
        and payload.mode is None
        and payload.location is None
        and not payload.increment_follow_up
        and payload.demo_at is None
        and payload.demo_review_status is None
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide an annotation, follow-up, demo date, or demo review status",
        )

    # Resolve the new follow-up count server-side so the counter is authoritative.
    new_follow_up: int | None = None
    if payload.increment_follow_up:
        existing = repo.get_lead(db, lead_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        new_follow_up = int(getattr(existing, "follow_up_count", 0) or 0) + 1

    lead = repo.set_lead_annotation(
        db,
        lead_id,
        is_junk=payload.is_junk,
        note=payload.note,
        budget=payload.budget,
        student_class=payload.student_class,
        status=payload.status,
        mode=payload.mode,
        location=payload.location,
        follow_up_count=new_follow_up,
        demo_at=payload.demo_at,
        demo_review_status=payload.demo_review_status,
    )
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Persist durably to GCS so the annotation survives DB rebuilds.
    if settings.gcs_leads_bucket:
        try:
            event = None
            if payload.increment_follow_up:
                event = {"event_type": "follow_up", "count": new_follow_up}
            elif payload.status == "Demo scheduled":
                event = {"event_type": "moved_to_gold"}
            elif payload.demo_review_status:
                event = {
                    "event_type": "demo_reviewed",
                    "status": payload.demo_review_status,
                }
            lead_annotations.save_annotation(
                settings,
                lead_id,
                is_junk=payload.is_junk,
                note=payload.note,
                budget=payload.budget,
                student_class=payload.student_class,
                status=payload.status,
                mode=payload.mode,
                location=payload.location,
                follow_up_count=new_follow_up,
                first_follow_up_at=lead.first_follow_up_at,
                last_follow_up_at=lead.last_follow_up_at,
                gold_transition_at=lead.gold_transition_at,
                demo_at=lead.demo_at,
                demo_review_status=lead.demo_review_status,
                event=event,
            )
        except Exception as exc:  # surface but don't lose the local update
            raise HTTPException(
                status_code=502,
                detail=f"Saved locally but failed to persist to GCS: {exc}",
            )

    return _serialize_lead(lead)


@router.get("/forms")
def get_forms(db: Session = Depends(get_db)):
    forms = repo.list_leadgen_forms(db)
    return [
        {
            "id": f.id,
            "page_id": f.page_id,
            "name": f.name,
            "status": f.status,
            "leads_count": f.leads_count,
        }
        for f in forms
    ]


@router.get("/export.csv")
def export_leads_csv(
    form_id: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    leads = repo.list_leads(db, form_id=form_id, search=search, limit=10000, offset=0)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["id", "created_time", "form_id", "full_name", "email", "phone_number", "campaign_id", "platform"]
    )
    for lead in leads:
        data = _serialize_lead(lead)
        writer.writerow(
            [
                data["id"],
                data["created_time"],
                data["form_id"],
                data["full_name"],
                data["email"],
                data["phone_number"],
                data["campaign_id"],
                data["platform"],
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )
