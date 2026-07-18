from app.config import Settings
from app.meta.client import MetaClient

REQUIRED_AD_PERMISSIONS = {"ads_read"}
REQUIRED_LEAD_PERMISSIONS = {"leads_retrieval", "pages_show_list"}


def check_permissions(settings: Settings) -> dict:
    client = MetaClient(settings)
    granted = {
        item["permission"]
        for item in client.get_permissions()
        if item.get("status") == "granted"
    }

    missing_ads = sorted(REQUIRED_AD_PERMISSIONS - granted)
    missing_leads = sorted(REQUIRED_LEAD_PERMISSIONS - granted)

    pages: list[dict] = []
    page_error: str | None = None
    try:
        pages = client.get_pages()
    except Exception as exc:
        page_error = str(exc)

    return {
        "granted": sorted(granted),
        "missing_ads": missing_ads,
        "missing_leads": missing_leads,
        "can_sync_ads": not missing_ads,
        "can_sync_leads": not missing_leads,
        "pages": [{"id": p["id"], "name": p.get("name")} for p in pages],
        "page_error": page_error,
        "fix_steps": _fix_steps(missing_leads),
    }


def _fix_steps(missing_leads: list[str]) -> list[str]:
    if not missing_leads:
        return []

    steps = [
        "Open Meta Developer Console → your app → App Review → Permissions and Features.",
        "Add and request the 'leads_retrieval' permission (available in Development mode for app admins).",
        "Regenerate your access token with leads_retrieval included (Graph API Explorer or Access Token Tool).",
        "Update Meta_Access_token in .env with the new token.",
        "Optionally set PAGE_ID=347244005670587 and PAGE_ACCESS_TOKEN in .env for page Tinnkoralearn.",
    ]
    if "pages_show_list" in missing_leads:
        steps.insert(2, "Also include pages_show_list when generating the new token.")
    return steps
