import io
import json
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
from google.cloud import storage

from app.config import Settings

MANIFEST_DEFAULT: dict[str, Any] = {
    "version": 1,
    "updated_at": None,
    "cursors": {},
    "last_sync": {},
    "jobs": {"current": None, "history": []},
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _client(settings: Settings) -> storage.Client:
    project = settings.google_cloud_project
    return storage.Client(project=project) if project else storage.Client()


def _bucket(settings: Settings) -> storage.Bucket:
    if not settings.gcs_leads_bucket:
        raise ValueError("GCS_LEADS_BUCKET is not set")
    return _client(settings).bucket(settings.gcs_leads_bucket)


def _blob_path(settings: Settings, relative_path: str) -> str:
    return relative_path.strip("/")


def public_url(settings: Settings, relative_path: str) -> str:
    return (
        f"https://storage.googleapis.com/{settings.gcs_leads_bucket}/"
        f"{_blob_path(settings, relative_path)}"
    )


def read_json(settings: Settings, relative_path: str) -> dict[str, Any] | list[Any] | None:
    blob = _bucket(settings).blob(_blob_path(settings, relative_path))
    if not blob.exists():
        return None
    return json.loads(blob.download_as_text(encoding="utf-8"))


def write_json(
    settings: Settings,
    relative_path: str,
    payload: dict[str, Any] | list[Any],
    *,
    content_type: str = "application/json",
) -> str:
    blob = _bucket(settings).blob(_blob_path(settings, relative_path))
    data = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    blob.upload_from_string(data, content_type=content_type)
    return public_url(settings, relative_path)


def read_text(settings: Settings, relative_path: str) -> str | None:
    blob = _bucket(settings).blob(_blob_path(settings, relative_path))
    if not blob.exists():
        return None
    return blob.download_as_text(encoding="utf-8")


def write_text(
    settings: Settings,
    relative_path: str,
    content: str,
    *,
    content_type: str = "text/plain",
) -> str:
    blob = _bucket(settings).blob(_blob_path(settings, relative_path))
    blob.upload_from_string(content, content_type=content_type)
    return public_url(settings, relative_path)


def list_blobs(settings: Settings, prefix: str) -> list[str]:
    prefix = _blob_path(settings, prefix)
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return [blob.name for blob in _bucket(settings).list_blobs(prefix=prefix)]


def delete_blobs_except(settings: Settings, prefix: str, keep_paths: set[str]) -> list[str]:
    keep_normalized = {_blob_path(settings, p) for p in keep_paths}
    deleted: list[str] = []
    for blob_name in list_blobs(settings, prefix):
        if blob_name not in keep_normalized:
            _bucket(settings).blob(blob_name).delete()
            deleted.append(blob_name)
    return deleted


def read_manifest(settings: Settings) -> dict[str, Any]:
    raw = read_json(settings, settings.gcs_manifest_path)
    if not isinstance(raw, dict):
        return dict(MANIFEST_DEFAULT)
    merged = dict(MANIFEST_DEFAULT)
    merged.update(raw)
    if "cursors" not in merged or not isinstance(merged["cursors"], dict):
        merged["cursors"] = {}
    if "last_sync" not in merged or not isinstance(merged["last_sync"], dict):
        merged["last_sync"] = {}
    if "jobs" not in merged or not isinstance(merged["jobs"], dict):
        merged["jobs"] = {"current": None, "history": []}
    return merged


def write_manifest(settings: Settings, manifest: dict[str, Any]) -> str:
    manifest = dict(manifest)
    manifest["updated_at"] = _utcnow().isoformat()
    return write_json(settings, settings.gcs_manifest_path, manifest)


def update_manifest_sync(
    settings: Settings,
    resource: str,
    *,
    cursor: str | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    manifest = read_manifest(settings)
    if cursor is not None:
        manifest["cursors"][resource] = cursor
        if resource == "insights":
            manifest["cursors"]["insights:last_date"] = cursor
    manifest["last_sync"][resource] = {
        "at": _utcnow().isoformat(),
        "result": result or {},
        "error": error,
    }
    write_manifest(settings, manifest)
    return manifest


def _parquet_blob_name(settings: Settings, day: date) -> str:
    return _blob_path(settings, f"{settings.gcs_insights_prefix}/date={day.isoformat()}.parquet")


INSIGHT_ROW_KEY = ["date", "level", "object_id"]


def read_parquet_partition(settings: Settings, day: date) -> pd.DataFrame:
    blob_path = _parquet_blob_name(settings, day)
    blob = _bucket(settings).blob(blob_path)
    if not blob.exists():
        return pd.DataFrame()
    data = blob.download_as_bytes()
    return pd.read_parquet(io.BytesIO(data), engine="pyarrow")


def write_parquet_partition(settings: Settings, day: date, df: pd.DataFrame) -> str:
    if df.empty:
        return public_url(settings, _parquet_blob_name(settings, day))

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    blob_path = _parquet_blob_name(settings, day)
    blob = _bucket(settings).blob(blob_path)
    blob.upload_from_file(buffer, content_type="application/octet-stream")
    return public_url(settings, blob_path)


def merge_parquet_partition(settings: Settings, day: date, df: pd.DataFrame) -> str:
    """Merge incoming insight rows into the daily partition (same object/day gets refreshed)."""
    if df.empty:
        return public_url(settings, _parquet_blob_name(settings, day))

    incoming = df.copy()
    if "date" in incoming.columns:
        incoming["date"] = pd.to_datetime(incoming["date"]).dt.date

    existing = read_parquet_partition(settings, day)
    if existing.empty:
        merged = incoming
    else:
        if "date" in existing.columns:
            existing["date"] = pd.to_datetime(existing["date"]).dt.date
        merged = pd.concat([existing, incoming], ignore_index=True)
        key_cols = [c for c in INSIGHT_ROW_KEY if c in merged.columns]
        if key_cols:
            merged = merged.drop_duplicates(subset=key_cols, keep="last")

    return write_parquet_partition(settings, day, merged.reset_index(drop=True))


def _parse_insights_partition_day(blob_name: str, prefix: str) -> date | None:
    marker = f"{prefix.rstrip('/')}/date="
    if marker not in blob_name or not blob_name.endswith(".parquet"):
        return None
    date_str = blob_name.rsplit("date=", 1)[-1].removesuffix(".parquet")
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None


def read_parquet_range(
    settings: Settings,
    *,
    start: date,
    end: date,
) -> pd.DataFrame:
    prefix = _blob_path(settings, settings.gcs_insights_prefix)
    frames: list[pd.DataFrame] = []
    bucket = _bucket(settings)

    for blob_name in list_blobs(settings, prefix):
        day = _parse_insights_partition_day(blob_name, prefix)
        if day is None or day < start or day > end:
            continue
        data = bucket.blob(blob_name).download_as_bytes()
        frames.append(pd.read_parquet(io.BytesIO(data), engine="pyarrow"))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def write_insights_export(settings: Settings, df: pd.DataFrame, stamp: str) -> str:
    if df.empty:
        path = f"{settings.gcs_exports_prefix}/insights_report_{stamp}.parquet"
        write_json(settings, path.replace(".parquet", ".json"), {"rows": 0, "exported_at": stamp})
        return public_url(settings, path.replace(".parquet", ".json"))

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)
    path = f"{settings.gcs_exports_prefix}/insights_report_{stamp}.parquet"
    blob = _bucket(settings).blob(_blob_path(settings, path))
    blob.upload_from_file(buffer, content_type="application/octet-stream")
    return public_url(settings, path)


def read_job_status(settings: Settings) -> dict[str, Any] | None:
    manifest = read_manifest(settings)
    current = manifest.get("jobs", {}).get("current")
    return current if isinstance(current, dict) else None


def write_job_status(settings: Settings, job: dict[str, Any] | None) -> dict[str, Any]:
    manifest = read_manifest(settings)
    jobs = manifest.setdefault("jobs", {"current": None, "history": []})
    if job is None:
        if jobs.get("current"):
            history = jobs.setdefault("history", [])
            history.insert(0, jobs["current"])
            jobs["history"] = history[:5]
        jobs["current"] = None
    else:
        jobs["current"] = job
    write_manifest(settings, manifest)
    return job or {}


def update_job_progress(
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
    manifest = read_manifest(settings)
    current = manifest.get("jobs", {}).get("current") or {}
    if current.get("job_id") != job_id:
        return
    current.update(
        {
            "status": status,
            "stage": stage,
            "progress": progress,
            "message": message,
            "error": error,
        }
    )
    if status in ("done", "error"):
        current["finished_at"] = _utcnow().isoformat()
    if result:
        current["result"] = result
    manifest.setdefault("jobs", {})["current"] = current
    write_manifest(settings, manifest)
