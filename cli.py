import typer

from app.config import get_settings
from app.db import repositories as repo
from app.db.session import SessionLocal, init_db
from app.meta.insights_sync import sync_insights
from app.meta.leads_sync import sync_leads
from app.meta.client import MetaClient
from app.meta.permissions import check_permissions
from app.services.ad_manager import AdManagerService
from app.services.form_manager import archive_empty_forms_on_meta
from app.services.leads_export import export_leads_to_gcs
from app.services.sync_all import run_all_sync
from app.services.structure_export import sync_ads_and_structure

app = typer.Typer(help="Meta Ads Manager CLI")
sync_app = typer.Typer(help="Sync data from Meta API")
ad_app = typer.Typer(help="Manage ads programmatically")
app.add_typer(sync_app, name="sync")
app.add_typer(ad_app, name="ad")


@sync_app.command("ads")
def sync_ads_cmd(full: bool = typer.Option(False, help="Full resync ignoring watermarks")):
    """Sync campaigns, ad sets, ads, and export structure snapshot to GCS."""
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        result = sync_ads_and_structure(db, settings, full_sync=full)
        typer.echo(f"Synced: {result}")
    finally:
        db.close()


@sync_app.command("insights")
def sync_insights_cmd(full: bool = typer.Option(False, help="Full backfill ignoring manifest")):
    """Sync Meta insights time series to GCS parquet."""
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        result = sync_insights(db, settings, full_sync=full)
        typer.echo(f"Synced: {result}")
    finally:
        db.close()


@sync_app.command("all")
def sync_all_cmd(
    full: bool = typer.Option(False, help="Full resync ignoring watermarks"),
    export: bool = typer.Option(True, help="Export leads and insights to GCS"),
):
    """Sync ads, leads, and insights; export to GCS."""
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        result = run_all_sync(db, settings, full=full, export=export)
        typer.echo(f"Synced: {result}")
    finally:
        db.close()


@sync_app.command("leads")
def sync_leads_cmd(
    full: bool = typer.Option(False, help="Full resync ignoring watermarks"),
    export: bool = typer.Option(False, help="Export all leads to GCS after sync"),
):
    """Sync lead gen forms and leads incrementally."""
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        result = sync_leads(db, settings, full_sync=full)
        typer.echo(f"Synced: {result}")
        if export:
            export_result = export_leads_to_gcs(db, settings)
            typer.echo(f"Exported: {export_result}")
    finally:
        db.close()


@sync_app.command("export-leads")
def export_leads_cmd():
    """Export all local leads to the configured GCS bucket."""
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        result = export_leads_to_gcs(db, settings)
        typer.echo(f"Exported: {result}")
    finally:
        db.close()


@app.command("cleanup")
def cleanup(
    empty_forms: bool = typer.Option(False, "--empty-forms", help="Delete empty forms from local DB"),
    meta: bool = typer.Option(False, "--meta", help="Also archive empty forms on Meta (requires --empty-forms)"),
):
    """Clean up local database and Meta lead forms."""
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        if meta and not empty_forms:
            typer.echo("Use --empty-forms with --meta to archive empty forms on Meta.")
            raise typer.Exit(1)
        if meta:
            result = archive_empty_forms_on_meta(db, settings)
            for item in result["archived"]:
                typer.echo(f"Archived on Meta: {item['name']} ({item['id']})")
            for item in result["skipped"]:
                typer.echo(f"Skipped: {item['name']} — {item['reason']}")
            for err in result["errors"]:
                typer.echo(f"Error: {err}")
        elif empty_forms:
            deleted = repo.delete_forms_without_leads(db)
            db.commit()
            if deleted:
                typer.echo(f"Deleted {len(deleted)} empty form(s) locally: {', '.join(deleted)}")
            else:
                typer.echo("No empty forms to delete locally.")
        else:
            typer.echo("Specify what to clean up, e.g. --empty-forms or --empty-forms --meta")
    finally:
        db.close()


@ad_app.command("pause")
def pause_ad(ad_id: str):
    """Pause an ad by ID."""
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        result = AdManagerService(db, settings).pause_ad(ad_id)
        typer.echo(result)
    finally:
        db.close()


@ad_app.command("activate")
def activate_ad(ad_id: str):
    """Activate an ad by ID."""
    init_db()
    settings = get_settings()
    db = SessionLocal()
    try:
        result = AdManagerService(db, settings).activate_ad(ad_id)
        typer.echo(result)
    finally:
        db.close()


@app.command("check-permissions")
def check_permissions_cmd():
    """Check which Meta API permissions are granted on the current token."""
    settings = get_settings()
    result = check_permissions(settings)
    typer.echo(f"Granted: {', '.join(result['granted'])}")
    if result["can_sync_ads"]:
        typer.echo("Ads sync: OK")
    else:
        typer.echo(f"Ads sync: MISSING {result['missing_ads']}")
    if result["can_sync_leads"]:
        typer.echo("Leads sync: OK")
    else:
        typer.echo(f"Leads sync: MISSING {result['missing_leads']}")
        typer.echo("")
        typer.echo("Fix steps:")
        for i, step in enumerate(result["fix_steps"], 1):
            typer.echo(f"  {i}. {step}")
    if result["pages"]:
        page = result["pages"][0]
        typer.echo(f"Page: {page['name']} ({page['id']})")


@app.command("health")
def health_check():
    """Verify Meta API connectivity."""
    settings = get_settings()
    client = MetaClient(settings)
    account = client.get_ad_account()
    perms = check_permissions(settings)
    typer.echo(f"Connected to: {account.get('name')} ({account.get('id')})")
    if not perms["can_sync_leads"]:
        typer.echo(f"Warning: leads sync unavailable — missing {perms['missing_leads']}")
        typer.echo("Run: python cli.py check-permissions")


if __name__ == "__main__":
    app()
