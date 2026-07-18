from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _migrate_parent_bookings(engine) -> None:
    if "parent_bookings" not in inspect(engine).get_table_names():
        return
    existing = {c["name"] for c in inspect(engine).get_columns("parent_bookings")}
    additions = {
        "platform": "VARCHAR(32)",
        "utm_source": "VARCHAR(128)",
        "utm_medium": "VARCHAR(128)",
        "utm_campaign": "VARCHAR(256)",
        "fbclid": "VARCHAR(256)",
    }
    with engine.begin() as conn:
        for name, col_type in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE parent_bookings ADD COLUMN {name} {col_type}"))


def _migrate_leads(engine) -> None:
    if "leads" not in inspect(engine).get_table_names():
        return
    existing = {c["name"] for c in inspect(engine).get_columns("leads")}
    additions = {
        "is_junk": "BOOLEAN DEFAULT 0",
        "note": "TEXT",
        "budget": "VARCHAR(128)",
        "student_class": "VARCHAR(128)",
        "status": "VARCHAR(64)",
        "mode": "VARCHAR(16)",
        "location": "VARCHAR(128)",
        "follow_up_count": "INTEGER DEFAULT 0",
        "first_follow_up_at": "DATETIME",
        "last_follow_up_at": "DATETIME",
        "gold_transition_at": "DATETIME",
        "demo_at": "DATETIME",
        "demo_review_status": "VARCHAR(32)",
        "annotation_updated_at": "DATETIME",
    }
    with engine.begin() as conn:
        for name, col_type in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN {name} {col_type}"))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_parent_bookings(engine)
    _migrate_leads(engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
