from __future__ import annotations

from dash import Input, Output, State, callback, no_update

from app.config import Settings
from app.dashboard.components.kpi_cards import sync_progress_bar
from app.services.sync_jobs import JobAlreadyRunningError, get_job_status, start_sync_job


def register_sync_callbacks(dash_app, settings: Settings) -> None:
    @callback(
        Output("sync-job-store", "data"),
        Output("sync-poll", "disabled"),
        Output("sync-toast", "is_open"),
        Output("sync-toast", "children"),
        Output("sync-toast", "color"),
        Output("btn-insights", "disabled"),
        Output("btn-leads", "disabled"),
        Output("btn-pull-all", "disabled"),
        Output("data-refresh-token", "data"),
        Input("insights-store", "data"),
        Input("btn-insights", "n_clicks"),
        Input("btn-leads", "n_clicks"),
        Input("btn-pull-all", "n_clicks"),
        Input("sync-poll", "n_intervals"),
        State("sync-job-store", "data"),
        State("data-refresh-token", "data"),
        prevent_initial_call=True,
    )
    def handle_sync(_insights_loaded, n_insights, n_leads, n_pull_all, _poll, job_store, refresh_token):
        from dash import ctx

        triggered = ctx.triggered_id
        job = job_store or get_job_status(settings)
        token = refresh_token or 0
        buttons_locked = True, True, True

        if triggered == "insights-store":
            job = get_job_status(settings)
            if job and job.get("status") == "running":
                return job, False, False, "", "success", *buttons_locked, token
            return job, True, no_update, no_update, no_update, False, False, False, token

        if triggered in ("btn-insights", "btn-leads", "btn-pull-all"):
            job_type = (
                "insights"
                if triggered == "btn-insights"
                else "leads"
                if triggered == "btn-leads"
                else "all"
            )
            try:
                job = start_sync_job(settings, job_type, full=False)
                return job, False, False, "", "success", *buttons_locked, token
            except JobAlreadyRunningError as exc:
                return job, True, True, str(exc), "warning", *buttons_locked, token

        job = get_job_status(settings) or job
        if not job:
            return None, True, no_update, no_update, no_update, False, False, False, token

        status = job.get("status")
        if status == "running":
            return job, False, False, "", "success", *buttons_locked, token

        if status == "done":
            msg = job.get("message", "Sync complete")
            return job, True, True, msg, "success", False, False, False, token + 1

        if status == "error":
            return job, True, True, job.get("error", "Sync failed"), "danger", False, False, False, token

        return job, True, no_update, no_update, no_update, False, False, False, token

    @callback(
        Output("sync-progress-container", "children"),
        Output("sync-pill", "children"),
        Output("sync-pill", "color"),
        Input("sync-job-store", "data"),
        Input("sync-poll", "n_intervals"),
    )
    def render_progress(job_store, _poll):
        job = get_job_status(settings) or job_store
        if not job or job.get("status") != "running":
            color = "success" if job and job.get("status") == "done" else "secondary"
            label = "Ready" if not job or job.get("status") not in ("error",) else "Failed"
            if job and job.get("status") == "error":
                color = "danger"
            return sync_progress_bar(0, "", False), label, color

        progress = job.get("progress", 0)
        message = job.get("message", "Syncing…")
        return sync_progress_bar(progress, message, True), "Syncing", "warning"
