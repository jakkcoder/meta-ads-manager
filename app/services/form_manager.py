from sqlalchemy.orm import Session

from app.config import Settings
from app.db import repositories as repo
from app.db.models import LeadgenForm, SyncCursor
from app.meta.client import MetaClient
from app.meta.leads_sync import ensure_page_token


def archive_empty_forms_on_meta(db: Session, settings: Settings) -> dict:
    client = MetaClient(settings)
    page_id, page_token = ensure_page_token(settings, client)
    client = MetaClient(settings, page_access_token=page_token)

    archived: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    errors: list[str] = []

    for form in client.get_leadgen_forms(page_id):
        form_id = form["id"]
        name = form.get("name", form_id)
        leads_count = int(form.get("leads_count") or 0)
        status = form.get("status", "")

        if leads_count > 0:
            skipped.append({"id": form_id, "name": name, "reason": f"{leads_count} leads"})
            continue

        if status == "ARCHIVED":
            skipped.append({"id": form_id, "name": name, "reason": "already archived"})
            repo.delete_forms_without_leads(db)
            db.commit()
            continue

        try:
            client.archive_leadgen_form(form_id)
            archived.append({"id": form_id, "name": name})
            cursor = db.get(SyncCursor, f"leads:{form_id}")
            if cursor:
                db.delete(cursor)
            form_row = db.get(LeadgenForm, form_id)
            if form_row:
                db.delete(form_row)
            db.commit()
        except Exception as exc:
            errors.append(f"{form_id}: {exc}")

    return {
        "page_id": page_id,
        "archived": archived,
        "skipped": skipped,
        "errors": errors,
    }
