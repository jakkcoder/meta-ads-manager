from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import ParentBooking
from app.db.session import get_db
from app.services import gcs_store

router = APIRouter(prefix="/api/book", tags=["booking"])

_PHONE_DIGITS = re.compile(r"\D")


def normalize_indian_phone(raw: str) -> str:
    digits = _PHONE_DIGITS.sub("", raw.strip())
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return digits[2:]
    raise ValueError("Enter a valid 10-digit Indian mobile number")


class ParentBookingRequest(BaseModel):
    phone: str = Field(..., min_length=10)
    slot_date: str = Field(..., min_length=8)
    slot_time: str = Field(..., min_length=3)
    user_timezone: str | None = None
    child_class: str = "Not specified"
    parent_name: str = "Not specified"
    child_name: str = "Not specified"
    mode: str = "not_specified"
    tutor_gender: str = "any"
    platform: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    fbclid: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return normalize_indian_phone(value)


@router.post("/parent")
def submit_parent_booking(
    body: ParentBookingRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    booking = ParentBooking(
        child_class=body.child_class,
        parent_name=body.parent_name.strip(),
        child_name=body.child_name.strip(),
        phone=body.phone,
        mode=body.mode,
        tutor_gender=body.tutor_gender,
        slot_date=body.slot_date,
        slot_time=(
            f"{body.slot_time} ({body.user_timezone})"
            if body.user_timezone
            else body.slot_time
        ),
        platform=body.platform,
        utm_source=body.utm_source,
        utm_medium=body.utm_medium,
        utm_campaign=body.utm_campaign,
        fbclid=body.fbclid,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    record = {
        "id": booking.id,
        "child_class": booking.child_class,
        "parent_name": booking.parent_name,
        "child_name": booking.child_name,
        "phone": booking.phone,
        "mode": booking.mode,
        "tutor_gender": booking.tutor_gender,
        "slot_date": booking.slot_date,
        "slot_time": booking.slot_time,
        "platform": booking.platform,
        "utm_source": booking.utm_source,
        "utm_medium": booking.utm_medium,
        "utm_campaign": booking.utm_campaign,
        "fbclid": booking.fbclid,
        "created_at": booking.created_at.isoformat() if booking.created_at else None,
        "source": "web_book_parent",
    }

    if settings.gcs_leads_bucket:
        try:
            path = f"{settings.gcs_leads_prefix}/parent_bookings.json"
            existing = gcs_store.read_json(settings, path)
            rows = existing.get("bookings", []) if isinstance(existing, dict) else []
            rows.insert(0, record)
            gcs_store.write_json(
                settings,
                path,
                {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "bookings": rows[:500],
                },
            )
        except Exception:
            pass

    return {"success": True, "booking_id": booking.id}


@router.get("/parent/slots")
def parent_booking_slots():
    """Slot metadata — dates/times are rendered in the visitor's local timezone on the client."""
    return {
        "hours": list(range(10, 22)),
        "days_ahead": 7,
        "client_local": True,
    }


@router.get("/parent")
def list_parent_bookings_api(
    search: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    from app.db import repositories as repo

    bookings = repo.list_parent_bookings(db, search=search, limit=limit)
    return {
        "count": len(bookings),
        "bookings": [
            {
                "id": b.id,
                "child_class": b.child_class,
                "parent_name": b.parent_name,
                "child_name": b.child_name,
                "phone": b.phone,
                "mode": b.mode,
                "tutor_gender": b.tutor_gender,
                "slot_date": b.slot_date,
                "slot_time": b.slot_time,
                "platform": b.platform,
                "utm_source": b.utm_source,
                "utm_medium": b.utm_medium,
                "utm_campaign": b.utm_campaign,
                "fbclid": b.fbclid,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bookings
        ],
    }
