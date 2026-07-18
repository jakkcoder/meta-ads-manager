from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.services.sync_all import (
    get_sync_status,
    run_ads_sync,
    run_all_sync,
    run_insights_sync,
    run_leads_sync,
)
from app.services.sync_jobs import JobAlreadyRunningError, get_job_status, start_sync_job

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncResult(BaseModel):
    success: bool
    result: dict


class JobStartRequest(BaseModel):
    type: str = Field(..., pattern="^(insights|leads|all)$")
    full: bool = False


class JobResponse(BaseModel):
    success: bool
    job: dict | None = None


@router.get("/status")
def sync_status(settings: Settings = Depends(get_settings)):
    return get_sync_status(settings)


@router.get("/job", response_model=JobResponse)
def sync_job_status(settings: Settings = Depends(get_settings)):
    return JobResponse(success=True, job=get_job_status(settings))


@router.post("/job", response_model=JobResponse)
def sync_job_start(
    body: JobStartRequest,
    settings: Settings = Depends(get_settings),
):
    try:
        job = start_sync_job(settings, body.type, full=body.full)  # type: ignore[arg-type]
        return JobResponse(success=True, job=job)
    except JobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/insights", response_model=SyncResult)
def trigger_insights_sync(
    full: bool = False,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        result = run_insights_sync(db, settings, full=full)
        return SyncResult(success=True, result=result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ads", response_model=SyncResult)
def trigger_ads_sync(
    full: bool = False,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        result = run_ads_sync(db, settings, full=full)
        return SyncResult(success=True, result=result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/leads", response_model=SyncResult)
def trigger_leads_sync(
    full: bool = False,
    export: bool = True,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        result = run_leads_sync(db, settings, full=full, export=export)
        return SyncResult(success=True, result=result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/all", response_model=SyncResult)
def trigger_all_sync(
    full: bool = False,
    export: bool = True,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        result = run_all_sync(db, settings, full=full, export=export)
        return SyncResult(success=True, result=result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
