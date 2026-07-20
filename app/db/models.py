from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))
    effective_status: Mapped[str | None] = mapped_column(String(32))
    objective: Mapped[str | None] = mapped_column(String(64))
    created_time: Mapped[datetime | None] = mapped_column(DateTime)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    ad_sets: Mapped[list["AdSet"]] = relationship(back_populates="campaign")


class AdSet(Base):
    __tablename__ = "ad_sets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(String(64), ForeignKey("campaigns.id"), index=True)
    name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))
    effective_status: Mapped[str | None] = mapped_column(String(32))
    daily_budget: Mapped[str | None] = mapped_column(String(32))
    lifetime_budget: Mapped[str | None] = mapped_column(String(32))
    targeting: Mapped[dict | None] = mapped_column(JSON)
    created_time: Mapped[datetime | None] = mapped_column(DateTime)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="ad_sets")
    ads: Mapped[list["Ad"]] = relationship(back_populates="ad_set")


class Ad(Base):
    __tablename__ = "ads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ad_set_id: Mapped[str] = mapped_column(String(64), ForeignKey("ad_sets.id"), index=True)
    name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))
    effective_status: Mapped[str | None] = mapped_column(String(32))
    creative_id: Mapped[str | None] = mapped_column(String(64))
    leadgen_form_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_time: Mapped[datetime | None] = mapped_column(DateTime)
    updated_time: Mapped[datetime | None] = mapped_column(DateTime)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    ad_set: Mapped["AdSet"] = relationship(back_populates="ads")


class LeadgenForm(Base):
    __tablename__ = "leadgen_forms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    page_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str | None] = mapped_column(String(32))
    leads_count: Mapped[int | None] = mapped_column(Integer)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    leads: Mapped[list["Lead"]] = relationship(back_populates="form")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    form_id: Mapped[str] = mapped_column(String(64), ForeignKey("leadgen_forms.id"), index=True)
    created_time: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    ad_id: Mapped[str | None] = mapped_column(String(64))
    adset_id: Mapped[str | None] = mapped_column(String(64))
    campaign_id: Mapped[str | None] = mapped_column(String(64))
    platform: Mapped[str | None] = mapped_column(String(32))
    is_organic: Mapped[bool | None] = mapped_column(Boolean)
    raw_json: Mapped[dict | None] = mapped_column(JSON)
    is_junk: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    note: Mapped[str | None] = mapped_column(Text)
    budget: Mapped[str | None] = mapped_column(String(128))
    student_class: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(64))
    mode: Mapped[str | None] = mapped_column(String(16))
    location: Mapped[str | None] = mapped_column(String(128))
    follow_up_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    gold_transition_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    demo_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    demo_review_status: Mapped[str | None] = mapped_column(String(32), index=True)
    annotation_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    form: Mapped["LeadgenForm"] = relationship(back_populates="leads")
    fields: Mapped[list["LeadField"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    events: Mapped[list["LeadEvent"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


class LeadField(Base):
    __tablename__ = "lead_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(256), index=True)
    field_value: Mapped[str | None] = mapped_column(Text)

    lead: Mapped["Lead"] = relationship(back_populates="fields")


class LeadEvent(Base):
    """Immutable operational events for parent lead SLA and funnel reporting."""

    __tablename__ = "lead_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
    payload: Mapped[dict | None] = mapped_column(JSON)

    lead: Mapped["Lead"] = relationship(back_populates="events")


class OpsAlert(Base):
    """Durable alert deliveries, used to deduplicate scheduled notifications."""

    __tablename__ = "ops_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_key: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SyncCursor(Base):
    __tablename__ = "sync_cursors"

    resource_type: Mapped[str] = mapped_column(String(128), primary_key=True)
    cursor_value: Mapped[str | None] = mapped_column(String(64))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ParentBooking(Base):
    __tablename__ = "parent_bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_class: Mapped[str] = mapped_column(String(64))
    parent_name: Mapped[str] = mapped_column(String(256))
    child_name: Mapped[str] = mapped_column(String(256))
    phone: Mapped[str | None] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16))  # online | offline
    tutor_gender: Mapped[str] = mapped_column(String(16))  # male | female | any
    slot_date: Mapped[str] = mapped_column(String(32))
    slot_time: Mapped[str] = mapped_column(String(32))
    platform: Mapped[str | None] = mapped_column(String(32))
    utm_source: Mapped[str | None] = mapped_column(String(128))
    utm_medium: Mapped[str | None] = mapped_column(String(128))
    utm_campaign: Mapped[str | None] = mapped_column(String(256))
    fbclid: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
