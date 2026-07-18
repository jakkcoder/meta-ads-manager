from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import repositories as repo
from app.meta.client import MetaAPIError, MetaClient


def _default_leads_since() -> int:
    since = datetime.now(timezone.utc) - timedelta(days=90)
    return int(since.timestamp())


def _parse_cursor_ts(cursor_value: str | None) -> int | None:
    if not cursor_value:
        return None
    try:
        dt = datetime.fromisoformat(cursor_value)
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        try:
            return int(cursor_value)
        except ValueError:
            return None


def ensure_page_token(settings: Settings, client: MetaClient) -> tuple[str, str]:
    page_id = settings.page_id
    page_token = settings.page_access_token

    # User/marketing token cannot call leadgen endpoints (Meta error #190).
    if page_token and page_token == settings.meta_access_token:
        page_token = None

    if page_id and page_token:
        return page_id, page_token

    pages = client.get_pages()
    if not pages:
        raise MetaAPIError(
            "No Facebook Pages found. Set PAGE_ID and PAGE_ACCESS_TOKEN in .env for lead sync."
        )

    page = next((p for p in pages if p.get("id") == page_id), pages[0]) if page_id else pages[0]
    page_id = page_id or page["id"]
    page_token = page_token or page.get("access_token") or client.get_page_access_token(page_id)
    return page_id, page_token


def sync_leads(db: Session, settings: Settings, *, full_sync: bool = False) -> dict:
    page_id, page_token = ensure_page_token(settings, MetaClient(settings))
    client = MetaClient(settings, page_access_token=page_token)

    forms = [
        form
        for form in client.get_leadgen_forms(page_id)
        if int(form.get("leads_count") or 0) > 0
    ]
    for form in forms:
        repo.upsert_leadgen_form(db, page_id, form)

    repo.delete_forms_without_leads(db)
    db.commit()

    total_new = 0
    total_seen = 0
    errors: list[str] = []

    for form in forms:
        form_id = form["id"]
        resource_type = f"leads:{form_id}"
        cursor = repo.get_cursor(db, resource_type)

        since_ts = (
            _default_leads_since()
            if full_sync
            else (_parse_cursor_ts(cursor.cursor_value if cursor else None) or _default_leads_since())
        )
        overlap = settings.leads_overlap_seconds

        try:
            leads = client.get_leads(
                form_id,
                time_created_since=since_ts,
                full_sync=full_sync,
                overlap_seconds=overlap,
            )
            max_created: datetime | None = None
            new_count = 0

            for lead_data in leads:
                total_seen += 1
                if not lead_data.get("form_id"):
                    lead_data["form_id"] = form_id
                if repo.upsert_lead(db, lead_data):
                    new_count += 1
                created = repo.parse_meta_datetime(lead_data.get("created_time"))
                if created and (max_created is None or created > max_created):
                    max_created = created

            if max_created:
                repo.upsert_cursor(db, resource_type, max_created.isoformat())
            else:
                repo.upsert_cursor(db, resource_type, str(since_ts))

            total_new += new_count
            db.commit()
        except Exception as exc:
            repo.upsert_cursor(db, resource_type, cursor.cursor_value if cursor else None, error=str(exc))
            errors.append(f"{form_id}: {exc}")
            db.commit()

    # Re-attach durable junk/note annotations from GCS so they survive a rebuilt
    # (ephemeral) local DB on Cloud Run cold starts.
    annotations_applied = 0
    if settings.gcs_leads_bucket:
        from app.services.lead_annotations import apply_annotations_to_db

        try:
            annotations_applied = apply_annotations_to_db(db, settings)
        except Exception:
            annotations_applied = 0

    return {
        "forms": len(forms),
        "leads_seen": total_seen,
        "leads_new": total_new,
        "annotations_applied": annotations_applied,
        "errors": errors,
        "page_id": page_id,
    }
