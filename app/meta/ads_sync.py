from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import repositories as repo
from app.meta.client import MetaClient


def _unix_ts_from_cursor(cursor_value: str | None) -> int | None:
    if not cursor_value:
        return None
    try:
        dt = datetime.fromisoformat(cursor_value)
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def sync_ads(db: Session, settings: Settings, *, full_sync: bool = False) -> dict:
    client = MetaClient(settings)
    results = {"campaigns": 0, "ad_sets": 0, "ads": 0}

    sync_steps = [
        ("campaigns", client.get_campaigns, repo.upsert_campaign),
        ("ad_sets", client.get_ad_sets, repo.upsert_ad_set),
        ("ads", client.get_ads, repo.upsert_ad),
    ]

    for resource_type, fetch_fn, upsert_fn in sync_steps:
        cursor = repo.get_cursor(db, resource_type)
        updated_since = None if full_sync else _unix_ts_from_cursor(cursor.cursor_value if cursor else None)

        try:
            items = fetch_fn(updated_since=updated_since, full_sync=full_sync)
            max_updated: datetime | None = None

            for item in items:
                upsert_fn(db, item)
                updated = repo.parse_meta_datetime(item.get("updated_time"))
                if updated and (max_updated is None or updated > max_updated):
                    max_updated = updated

            new_cursor = (
                max_updated.isoformat()
                if max_updated
                else (cursor.cursor_value if cursor and cursor.cursor_value else datetime.now(timezone.utc).replace(tzinfo=None).isoformat())
            )
            repo.upsert_cursor(db, resource_type, new_cursor)
            results[resource_type if resource_type != "ad_sets" else "ad_sets"] = len(items)
        except Exception as exc:
            repo.upsert_cursor(
                db,
                resource_type,
                cursor.cursor_value if cursor else None,
                error=str(exc),
            )
            db.commit()
            raise

    db.commit()
    return results
