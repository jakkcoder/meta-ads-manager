from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from app.config import Settings
from app.db.session import SessionLocal, init_db
from app.services import gcs_store
from app.services.sync_all import _export_insights_snapshot, run_ads_sync, run_insights_sync, run_leads_sync

JobType = Literal["insights", "leads", "all"]

_lock = threading.Lock()
_local_job: dict[str, Any] | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _use_gcs(settings: Settings) -> bool:
    return bool(settings.gcs_leads_bucket)


def get_job_status(settings: Settings) -> dict[str, Any] | None:
    global _local_job
    if _use_gcs(settings):
        return gcs_store.read_job_status(settings)
    with _lock:
        return dict(_local_job) if _local_job else None


def _set_job(settings: Settings, job: dict[str, Any] | None) -> None:
    global _local_job
    if _use_gcs(settings):
        gcs_store.write_job_status(settings, job)
    else:
        with _lock:
            _local_job = job


def _update_job(
    settings: Settings,
    job_id: str,
    *,
    progress: int,
    stage: str,
    message: str,
    status: str = "running",
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    if _use_gcs(settings):
        gcs_store.update_job_progress(
            settings,
            job_id,
            progress=progress,
            stage=stage,
            message=message,
            status=status,
            error=error,
            result=result,
        )
        return

    global _local_job
    with _lock:
        if not _local_job or _local_job.get("job_id") != job_id:
            return
        _local_job.update(
            {
                "status": status,
                "stage": stage,
                "progress": progress,
                "message": message,
                "error": error,
            }
        )
        if status in ("done", "error"):
            _local_job["finished_at"] = _utcnow().isoformat()
        if result:
            _local_job["result"] = result


class JobAlreadyRunningError(Exception):
    pass


def start_sync_job(
    settings: Settings,
    job_type: JobType,
    *,
    full: bool = False,
) -> dict[str, Any]:
    current = get_job_status(settings)
    if current and current.get("status") == "running":
        raise JobAlreadyRunningError("A sync job is already running")

    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "type": job_type,
        "status": "running",
        "stage": "starting",
        "progress": 0,
        "message": "Starting sync job…",
        "started_at": _utcnow().isoformat(),
        "finished_at": None,
        "error": None,
        "result": None,
    }
    _set_job(settings, job)

    thread = threading.Thread(
        target=_run_job,
        args=(settings, job_id, job_type, full),
        daemon=True,
        name=f"sync-job-{job_type}",
    )
    thread.start()
    return job


def _run_job(settings: Settings, job_id: str, job_type: JobType, full: bool) -> None:
    init_db()
    db = SessionLocal()
    try:
        if job_type == "insights":
            _update_job(settings, job_id, progress=20, stage="insights", message="Fetching Meta insights…")
            result = run_insights_sync(db, settings, full=full)
            _update_job(
                settings,
                job_id,
                progress=100,
                stage="done",
                message="Insights sync complete",
                status="done",
                result=result,
            )
        elif job_type == "leads":
            _update_job(settings, job_id, progress=30, stage="leads", message="Syncing leads from Meta…")
            result = run_leads_sync(db, settings, full=full, export=True)
            _update_job(
                settings,
                job_id,
                progress=100,
                stage="done",
                message="Leads sync complete",
                status="done",
                result=result,
            )
        else:
            _update_job(settings, job_id, progress=5, stage="ads", message="Syncing ad structure from Meta…")
            ads_result = run_ads_sync(db, settings, full=full)
            _update_job(settings, job_id, progress=30, stage="leads", message="Syncing leads from Meta → GCS…")
            leads_result = run_leads_sync(db, settings, full=full, export=True)
            _update_job(settings, job_id, progress=60, stage="insights", message="Syncing insights from Meta → GCS…")
            insights_result = run_insights_sync(db, settings, full=full)
            _update_job(settings, job_id, progress=85, stage="export", message="Exporting insights snapshot to GCS…")
            result = {
                "ads": ads_result,
                "leads": leads_result,
                "insights": insights_result,
                "insights_export": _export_insights_snapshot(settings),
            }
            gcs_store.update_manifest_sync(settings, "all", result=result)
            done_msg = "Full pull complete — all data in GCS" if full else "Incremental pull complete — all data in GCS"
            _update_job(
                settings,
                job_id,
                progress=100,
                stage="done",
                message=done_msg,
                status="done",
                result=result,
            )
    except Exception as exc:
        _update_job(
            settings,
            job_id,
            progress=100,
            stage="error",
            message=str(exc),
            status="error",
            error=str(exc),
        )
    finally:
        db.close()
