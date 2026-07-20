from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Ad,
    AdSet,
    AuditLog,
    Campaign,
    Lead,
    LeadEvent,
    LeadField,
    LeadgenForm,
    OpsAlert,
    ParentBooking,
    SyncCursor,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_meta_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def get_cursor(db: Session, resource_type: str) -> SyncCursor | None:
    return db.get(SyncCursor, resource_type)


def upsert_cursor(
    db: Session,
    resource_type: str,
    cursor_value: str | None,
    error: str | None = None,
) -> None:
    row = db.get(SyncCursor, resource_type)
    if row is None:
        row = SyncCursor(resource_type=resource_type)
        db.add(row)
    row.cursor_value = cursor_value
    row.last_sync_at = _utcnow()
    row.last_error = error


def upsert_campaign(db: Session, data: dict) -> None:
    campaign = db.get(Campaign, data["id"])
    if campaign is None:
        campaign = Campaign(id=data["id"])
        db.add(campaign)
    campaign.name = data.get("name")
    campaign.status = data.get("status")
    campaign.effective_status = data.get("effective_status")
    campaign.objective = data.get("objective")
    campaign.created_time = parse_meta_datetime(data.get("created_time"))
    campaign.updated_time = parse_meta_datetime(data.get("updated_time"))
    campaign.synced_at = _utcnow()


def upsert_ad_set(db: Session, data: dict) -> None:
    ad_set = db.get(AdSet, data["id"])
    if ad_set is None:
        ad_set = AdSet(id=data["id"], campaign_id=data.get("campaign_id", ""))
        db.add(ad_set)
    ad_set.campaign_id = data.get("campaign_id", ad_set.campaign_id)
    ad_set.name = data.get("name")
    ad_set.status = data.get("status")
    ad_set.effective_status = data.get("effective_status")
    ad_set.daily_budget = data.get("daily_budget")
    ad_set.lifetime_budget = data.get("lifetime_budget")
    ad_set.targeting = data.get("targeting")
    ad_set.created_time = parse_meta_datetime(data.get("created_time"))
    ad_set.updated_time = parse_meta_datetime(data.get("updated_time"))
    ad_set.synced_at = _utcnow()


def upsert_ad(db: Session, data: dict) -> None:
    creative = data.get("creative") or {}
    ad = db.get(Ad, data["id"])
    if ad is None:
        ad = Ad(id=data["id"], ad_set_id=data.get("adset_id") or data.get("ad_set_id", ""))
        db.add(ad)
    ad.ad_set_id = data.get("adset_id") or data.get("ad_set_id", ad.ad_set_id)
    ad.name = data.get("name")
    ad.status = data.get("status")
    ad.effective_status = data.get("effective_status")
    ad.creative_id = creative.get("id") if isinstance(creative, dict) else data.get("creative_id")
    ad.leadgen_form_id = _extract_leadgen_form_id(creative)
    ad.created_time = parse_meta_datetime(data.get("created_time"))
    ad.updated_time = parse_meta_datetime(data.get("updated_time"))
    ad.synced_at = _utcnow()


def _extract_leadgen_form_id(creative: object) -> str | None:
    """Extract the Instant Form ID from a Meta ad creative's story spec."""
    if not isinstance(creative, dict):
        return None
    spec = creative.get("object_story_spec") or {}
    if isinstance(spec, str):
        try:
            import json

            spec = json.loads(spec)
        except (TypeError, ValueError):
            return None
    if not isinstance(spec, dict):
        return None
    for section in ("link_data", "video_data"):
        payload = spec.get(section) or {}
        cta = payload.get("call_to_action") or {}
        value = cta.get("value") or {}
        form_id = value.get("lead_gen_form_id")
        if form_id:
            return str(form_id)
    return None


def upsert_leadgen_form(db: Session, page_id: str, data: dict) -> None:
    form = db.get(LeadgenForm, data["id"])
    if form is None:
        form = LeadgenForm(id=data["id"], page_id=page_id)
        db.add(form)
    form.page_id = page_id
    form.name = data.get("name")
    form.status = data.get("status")
    form.leads_count = int(data["leads_count"]) if data.get("leads_count") is not None else None
    form.synced_at = _utcnow()


def upsert_lead(db: Session, data: dict) -> bool:
    lead_id = data["id"]
    created_time = parse_meta_datetime(data.get("created_time"))
    existing = db.get(Lead, lead_id)
    if existing:
        existing.form_id = data.get("form_id") or existing.form_id
        existing.created_time = created_time or existing.created_time
        existing.ad_id = data.get("ad_id") or existing.ad_id
        existing.adset_id = data.get("adset_id") or existing.adset_id
        existing.campaign_id = data.get("campaign_id") or existing.campaign_id
        existing.platform = data.get("platform") or existing.platform
        existing.is_organic = data.get("is_organic") if data.get("is_organic") is not None else existing.is_organic
        existing.raw_json = data
        existing.synced_at = _utcnow()
        return False

    lead = Lead(
        id=lead_id,
        form_id=data.get("form_id", ""),
        created_time=created_time,
        ad_id=data.get("ad_id"),
        adset_id=data.get("adset_id"),
        campaign_id=data.get("campaign_id"),
        platform=data.get("platform"),
        is_organic=data.get("is_organic"),
        raw_json=data,
        synced_at=_utcnow(),
    )
    db.add(lead)

    for field in data.get("field_data", []):
        name = field.get("name", "")
        values = field.get("values") or []
        value = values[0] if values else None
        db.add(LeadField(lead_id=lead_id, field_name=name, field_value=value))

    return True


def update_ad_status(db: Session, ad_id: str, status: str) -> None:
    ad = db.get(Ad, ad_id)
    if ad:
        ad.status = status
        ad.synced_at = _utcnow()


def update_campaign_status(db: Session, campaign_id: str, status: str) -> None:
    campaign = db.get(Campaign, campaign_id)
    if campaign:
        campaign.status = status
        campaign.synced_at = _utcnow()


def add_audit_log(
    db: Session,
    action: str,
    object_type: str,
    object_id: str,
    payload: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            action=action,
            object_type=object_type,
            object_id=object_id,
            payload=payload,
        )
    )


def list_campaigns(db: Session) -> list[Campaign]:
    return list(db.scalars(select(Campaign).order_by(Campaign.updated_time.desc())).all())


def list_ad_sets(db: Session, campaign_id: str | None = None) -> list[AdSet]:
    stmt = select(AdSet).order_by(AdSet.updated_time.desc())
    if campaign_id:
        stmt = stmt.where(AdSet.campaign_id == campaign_id)
    return list(db.scalars(stmt).all())


def list_ads(db: Session, ad_set_id: str | None = None) -> list[Ad]:
    stmt = select(Ad).order_by(Ad.updated_time.desc())
    if ad_set_id:
        stmt = stmt.where(Ad.ad_set_id == ad_set_id)
    return list(db.scalars(stmt).all())


def list_leadgen_forms(db: Session) -> list[LeadgenForm]:
    stmt = (
        select(LeadgenForm)
        .where(LeadgenForm.leads_count > 0)
        .order_by(LeadgenForm.name)
    )
    return list(db.scalars(stmt).all())


def delete_forms_without_leads(db: Session) -> list[str]:
    """Remove leadgen forms that have zero leads in the local DB."""
    deleted: list[str] = []
    forms = list(db.scalars(select(LeadgenForm)).all())
    for form in forms:
        lead_count = len(list(db.scalars(select(Lead).where(Lead.form_id == form.id)).all()))
        meta_count = form.leads_count or 0
        if lead_count == 0 and meta_count == 0:
            cursor = db.get(SyncCursor, f"leads:{form.id}")
            if cursor:
                db.delete(cursor)
            db.delete(form)
            deleted.append(form.id)
    return deleted


def list_leads(
    db: Session,
    *,
    form_id: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Lead]:
    stmt = select(Lead).order_by(Lead.created_time.desc()).limit(limit).offset(offset)
    if form_id:
        stmt = stmt.where(Lead.form_id == form_id)
    leads = list(db.scalars(stmt).all())
    if search:
        search_lower = search.lower()
        filtered = []
        for lead in leads:
            for field in lead.fields:
                if field.field_value and search_lower in field.field_value.lower():
                    filtered.append(lead)
                    break
        return filtered
    return leads


def get_lead(db: Session, lead_id: str) -> Lead | None:
    return db.get(Lead, lead_id)


def set_lead_annotation(
    db: Session,
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
    demo_at: datetime | None = None,
    demo_review_status: str | None = None,
) -> Lead | None:
    lead = db.get(Lead, lead_id)
    if lead is None:
        return None
    if is_junk is not None:
        lead.is_junk = bool(is_junk)
    if note is not None:
        lead.note = note
    if budget is not None:
        lead.budget = budget
    if student_class is not None:
        lead.student_class = student_class
    previous_status = lead.status
    if status is not None:
        lead.status = status
    if mode is not None:
        lead.mode = mode
    if location is not None:
        lead.location = location
    if follow_up_count is not None:
        previous_follow_up_count = int(lead.follow_up_count or 0)
        lead.follow_up_count = int(follow_up_count)
        if follow_up_count > previous_follow_up_count:
            if lead.first_follow_up_at is None:
                lead.first_follow_up_at = _utcnow()
            lead.last_follow_up_at = _utcnow()
            db.add(
                LeadEvent(
                    lead_id=lead.id,
                    event_type="follow_up",
                    payload={"count": int(follow_up_count)},
                )
            )
    if demo_at is not None:
        lead.demo_at = demo_at
    if demo_review_status is not None:
        lead.demo_review_status = demo_review_status
        db.add(
            LeadEvent(
                lead_id=lead.id,
                event_type="demo_reviewed",
                payload={"status": demo_review_status},
            )
        )
    if status == "Demo scheduled" and previous_status != "Demo scheduled":
        lead.gold_transition_at = _utcnow()
        db.add(
            LeadEvent(
                lead_id=lead.id,
                event_type="moved_to_gold",
                payload={"previous_status": previous_status},
            )
        )
    elif previous_status == "Demo scheduled" and status is not None and status != "Demo scheduled":
        db.add(
            LeadEvent(
                lead_id=lead.id,
                event_type="left_gold",
                payload={"next_status": status},
            )
        )
    lead.annotation_updated_at = _utcnow()
    db.commit()
    return lead


def add_lead_event(
    db: Session, lead_id: str, event_type: str, payload: dict | None = None
) -> None:
    db.add(LeadEvent(lead_id=lead_id, event_type=event_type, payload=payload))


def alert_seen(db: Session, alert_key: str) -> bool:
    return db.scalar(select(OpsAlert.id).where(OpsAlert.alert_key == alert_key)) is not None


def record_alert(
    db: Session, alert_key: str, alert_type: str, payload: dict | None = None
) -> None:
    db.add(OpsAlert(alert_key=alert_key, alert_type=alert_type, payload=payload))
    db.commit()


def count_leads_today(db: Session) -> int:
    today = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(Lead).where(Lead.created_time >= today)
    return len(list(db.scalars(stmt).all()))


def count_active_campaigns(db: Session) -> int:
    stmt = select(Campaign).where(Campaign.effective_status == "ACTIVE")
    return len(list(db.scalars(stmt).all()))


def get_sync_status(db: Session) -> list[SyncCursor]:
    return list(db.scalars(select(SyncCursor)).all())


def list_parent_bookings(
    db: Session,
    *,
    search: str | None = None,
    limit: int = 200,
) -> list[ParentBooking]:
    stmt = select(ParentBooking).order_by(ParentBooking.created_at.desc()).limit(limit)
    bookings = list(db.scalars(stmt).all())
    if not search:
        return bookings
    q = search.lower()
    return [
        b
        for b in bookings
        if q in b.parent_name.lower()
        or q in b.child_name.lower()
        or q in (b.phone or "")
        or q in b.child_class.lower()
    ]
