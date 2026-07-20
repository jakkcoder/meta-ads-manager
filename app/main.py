import threading
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from a2wsgi import WSGIMiddleware

from app.api import routes_ads, routes_booking, routes_leads, routes_ops, routes_sync
from app.config import Settings, get_settings
from app.dashboard.cmo_dash import create_dash_app
from app.db import repositories as repo
from app.db.session import SessionLocal, get_db, init_db
from app.meta.ads_sync import sync_ads
from app.meta.leads_sync import sync_leads
from app.meta.permissions import check_permissions
from app.services.cloud_run_catalog import list_cloud_run_services
from app.services.leads_export import export_leads_to_gcs
from app.services.sync_all import run_all_sync, run_insights_sync
from app.services.ops_reporting import build_alerts, build_parent_ops_report

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Meta Ads Manager", version="1.0.0")
app.include_router(routes_ads.router)
app.include_router(routes_booking.router)
app.include_router(routes_leads.router)
app.include_router(routes_ops.router)
app.include_router(routes_sync.router)

dash_app = create_dash_app()
app.mount("/cmo", WSGIMiddleware(dash_app.server))


@app.get("/cmo")
def cmo_redirect():
    return RedirectResponse(url="/cmo/", status_code=307)

scheduler = BackgroundScheduler()


def verify_api_key(
    settings: Settings = Depends(get_settings),
    x_api_key: str | None = Header(default=None),
) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.on_event("startup")
def on_startup() -> None:
    Path("data").mkdir(exist_ok=True)
    init_db()

    settings = get_settings()
    if settings.sync_leads_interval_minutes > 0:

        def scheduled_leads_sync() -> None:
            db = SessionLocal()
            try:
                sync_leads(db, settings)
                # Export to GCS after each sync to keep downstream current
                export_leads_to_gcs(db, settings)
            except Exception:
                pass
            finally:
                db.close()

        scheduler.add_job(
            scheduled_leads_sync,
            "interval",
            minutes=settings.sync_leads_interval_minutes,
            id="leads_sync",
            replace_existing=True,
        )

    if settings.sync_insights_interval_minutes > 0:

        def scheduled_insights_sync() -> None:
            db = SessionLocal()
            try:
                run_insights_sync(db, settings)
            except Exception:
                pass
            finally:
                db.close()

        scheduler.add_job(
            scheduled_insights_sync,
            "interval",
            minutes=settings.sync_insights_interval_minutes,
            id="insights_sync",
            replace_existing=True,
        )

    if settings.ops_alert_interval_minutes > 0:

        def scheduled_ops_alerts() -> None:
            db = SessionLocal()
            try:
                # Use the API implementation so alert delivery and deduplication
                # remain identical for scheduled and manually-triggered checks.
                from app.api.routes_ops import check_alerts

                check_alerts(db, settings)
            except Exception:
                pass
            finally:
                db.close()

        scheduler.add_job(
            scheduled_ops_alerts,
            "interval",
            minutes=settings.ops_alert_interval_minutes,
            id="ops_alerts",
            replace_existing=True,
        )

    if scheduler.get_jobs():
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown()


@app.get("/health")
def health(settings: Settings = Depends(get_settings)):
    perms = check_permissions(settings)
    return {
        "status": "ok",
        "ad_account": settings.ad_account_path,
        "can_sync_ads": perms["can_sync_ads"],
        "can_sync_leads": perms["can_sync_leads"],
        "missing_lead_permissions": perms["missing_leads"],
    }


@app.get("/api/permissions")
def permissions(settings: Settings = Depends(get_settings)):
    return check_permissions(settings)


@app.get("/api/cloud-run/services")
def cloud_run_services_api(settings: Settings = Depends(get_settings)):
    return list_cloud_run_services(settings)


@app.get("/services", response_class=HTMLResponse)
def services_page(request: Request, settings: Settings = Depends(get_settings)):
    catalog = list_cloud_run_services(settings)
    return templates.TemplateResponse(
        request,
        "services.html",
        {"catalog": catalog},
    )


@app.get("/bookings/parent", response_class=HTMLResponse)
def parent_bookings_page(
    request: Request,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    bookings = repo.list_parent_bookings(db, search=search)
    return templates.TemplateResponse(
        request,
        "parent_bookings.html",
        {"bookings": bookings, "search": search or ""},
    )


@app.get("/ops", response_class=HTMLResponse)
def operations_page(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.lead_annotations import apply_annotations_to_db

    _ensure_leads_populated(db, settings)
    if settings.gcs_leads_bucket:
        try:
            apply_annotations_to_db(db, settings)
        except Exception:
            pass
    report = build_parent_ops_report(db)
    return templates.TemplateResponse(request, "ops_dashboard.html", report)


@app.get("/book/parent", response_class=HTMLResponse)
def book_parent_page(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(
        request,
        "book_parent.html",
        {"meta_pixel_id": settings.meta_pixel_id},
    )


@app.get("/book/instagram")
def book_instagram_page(request: Request):
    """Instagram ad landing URL — tags traffic and opens the parent booking form."""
    from urllib.parse import urlencode

    params = dict(request.query_params)
    params.setdefault("utm_source", "instagram")
    params.setdefault("utm_medium", "paid_social")
    query = urlencode(params)
    return RedirectResponse(url=f"/book/parent?{query}", status_code=302)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    sync_status = repo.get_sync_status(db)
    perms = check_permissions(settings)
    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "leads_today": repo.count_leads_today(db),
            "active_campaigns": repo.count_active_campaigns(db),
            "sync_status": sync_status,
            "permissions": perms,
            "cmo_dashboard_url": "/cmo/",
        },
    )


@app.get("/leads", response_class=HTMLResponse)
def leads_page(
    request: Request,
    form_id: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    leads = repo.list_leads(db, form_id=form_id, search=search, limit=200)
    forms = repo.list_leadgen_forms(db)
    form_names = {form.id: form.name or form.id for form in forms}
    serialized_leads = []
    for lead in leads:
        fields = {f.field_name: f.field_value for f in lead.fields}
        serialized_leads.append(
            {
                "lead": lead,
                "fields": fields,
                "form_name": form_names.get(lead.form_id, lead.form_id),
            }
        )
    return templates.TemplateResponse(
        request,
        "leads.html",
        {
            "leads": serialized_leads,
            "forms": forms,
            "selected_form_id": form_id,
            "search": search or "",
        },
    )


_leads_sync_lock = threading.Lock()


def _ensure_leads_populated(db: Session, settings: Settings) -> None:
    """Cloud Run scales to zero with an ephemeral DB, so a fresh instance starts
    empty. When the leads table is empty, sync once on-demand (the request gives
    the instance full CPU, unlike a throttled background thread)."""
    if not settings.gcs_leads_bucket:
        return
    from sqlalchemy import select

    from app.db.models import Lead

    if db.scalar(select(Lead.id).limit(1)) is not None:
        return
    if not _leads_sync_lock.acquire(blocking=False):
        return
    try:
        sync_leads(db, settings)
        export_leads_to_gcs(db, settings)
    except Exception:
        pass
    finally:
        _leads_sync_lock.release()


@app.get("/leads/parents", response_class=HTMLResponse)
def parent_leads_page(
    request: Request,
    search: str | None = None,
    form_id: str | None = None,
    show_junk: bool = False,
    tab: str = "latest",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.lead_annotations import apply_annotations_to_db
    from app.services.leads_export import GOLD_STATUS, list_parent_lead_records

    # Populate the DB on a fresh Cloud Run instance, then re-attach durable
    # annotations so the page is correct even right after a cold start.
    _ensure_leads_populated(db, settings)
    if settings.gcs_leads_bucket:
        try:
            apply_annotations_to_db(db, settings)
        except Exception:
            pass

    tab = tab if tab in ("latest", "older") else "latest"

    # Gold leads (a demo has been scheduled) live on the dedicated /leads/gold
    # page and are hidden from the parent list.
    all_records = [
        r
        for r in list_parent_lead_records(db, include_junk=True)
        if r.get("status") != GOLD_STATUS
    ]

    # The "latest form" is whichever parent form has the most recent lead.
    # Records are ordered newest-first, so the first record names that form.
    latest_form_id = all_records[0]["form_id"] if all_records else None
    latest_form_name = all_records[0].get("form_name") if all_records else None

    if tab == "latest":
        scoped = [r for r in all_records if r["form_id"] == latest_form_id]
    else:
        scoped = [r for r in all_records if r["form_id"] != latest_form_id]
        if form_id:
            scoped = [r for r in scoped if r["form_id"] == form_id]

    if search:
        q = search.lower()
        scoped = [
            r
            for r in scoped
            if any(v and q in str(v).lower() for v in (r.get("fields") or {}).values())
        ]

    visible = [r for r in scoped if show_junk or not r.get("is_junk")]
    junk_count = sum(1 for r in scoped if r.get("is_junk"))

    from app.services.leads_export import PARENT_FORM_IDS

    forms = repo.list_leadgen_forms(db)
    # Older-forms dropdown excludes the latest form.
    older_forms = [
        f for f in forms if f.id in PARENT_FORM_IDS and f.id != latest_form_id
    ]

    latest_count = sum(1 for r in all_records if r["form_id"] == latest_form_id)
    older_count = sum(1 for r in all_records if r["form_id"] != latest_form_id)

    return templates.TemplateResponse(
        request,
        "parent_leads.html",
        {
            "leads": visible,
            "forms": older_forms,
            "selected_form_id": form_id,
            "search": search or "",
            "show_junk": show_junk,
            "junk_count": junk_count,
            "total_count": len(scoped),
            "tab": tab,
            "latest_form_name": latest_form_name or latest_form_id or "—",
            "latest_count": latest_count,
            "older_count": older_count,
        },
    )


@app.get("/leads/gold", response_class=HTMLResponse)
def gold_leads_page(
    request: Request,
    search: str | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.lead_annotations import apply_annotations_to_db
    from app.services.leads_export import GOLD_STATUS, list_parent_lead_records

    _ensure_leads_populated(db, settings)
    if settings.gcs_leads_bucket:
        try:
            apply_annotations_to_db(db, settings)
        except Exception:
            pass

    # Gold = parent lead with a scheduled demo. Junked leads are not shown here.
    records = [
        r
        for r in list_parent_lead_records(db, include_junk=False)
        if r.get("status") == GOLD_STATUS
    ]

    if search:
        q = search.lower()
        records = [
            r
            for r in records
            if any(v and q in str(v).lower() for v in (r.get("fields") or {}).values())
        ]

    return templates.TemplateResponse(
        request,
        "gold_leads.html",
        {"leads": records, "search": search or ""},
    )


@app.get("/ads", response_class=HTMLResponse)
def ads_page(
    request: Request,
    db: Session = Depends(get_db),
):
    campaigns = repo.list_campaigns(db)
    ad_sets = repo.list_ad_sets(db)
    ads = repo.list_ads(db)
    ad_sets_by_campaign = {}
    for ad_set in ad_sets:
        ad_sets_by_campaign.setdefault(ad_set.campaign_id, []).append(ad_set)
    ads_by_ad_set = {}
    for ad in ads:
        ads_by_ad_set.setdefault(ad.ad_set_id, []).append(ad)
    return templates.TemplateResponse(
        request,
        "ads.html",
        {
            "campaigns": campaigns,
            "ad_sets_by_campaign": ad_sets_by_campaign,
            "ads_by_ad_set": ads_by_ad_set,
        },
    )


@app.post("/sync/ads")
def web_sync_ads(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    # The Ads page is an operational inventory, so refresh all ads/creatives
    # and their attached Instant Forms instead of relying on an incremental cursor.
    sync_ads(db, settings, full_sync=True)
    return RedirectResponse(url="/ads", status_code=303)


@app.post("/sync/leads")
def web_sync_leads(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    sync_leads(db, settings)
    return RedirectResponse(url="/leads", status_code=303)


@app.post("/ads/{ad_id}/pause")
def web_pause_ad(
    ad_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.ad_manager import AdManagerService

    AdManagerService(db, settings).pause_ad(ad_id)
    return RedirectResponse(url="/ads", status_code=303)


@app.post("/ads/{ad_id}/activate")
def web_activate_ad(
    ad_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    from app.services.ad_manager import AdManagerService

    AdManagerService(db, settings).activate_ad(ad_id)
    return RedirectResponse(url="/ads", status_code=303)
