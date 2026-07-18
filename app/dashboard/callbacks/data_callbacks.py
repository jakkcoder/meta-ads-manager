from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from dash import Input, Output, callback

from app.config import Settings
from app.services import gcs_store
from app.services.leads_export import load_leads_segments

INSIGHT_COLUMNS = [
    "date",
    "level",
    "segment",
    "object_id",
    "object_name",
    "spend",
    "leads",
    "impressions",
    "clicks",
    "ctr",
    "cpc",
    "cpl",
    "daily_budget",
    "budget_utilization",
]

_LOADING_VISIBLE = {"display": "block"}
_LOADING_HIDDEN = {"display": "none"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_range(start_date, end_date) -> tuple:
    end = _utcnow().date()
    if start_date and end_date:
        start = pd.Timestamp(start_date).date()
        end = pd.Timestamp(end_date).date()
    else:
        start = end - timedelta(days=29)
    return start, end


def _insights_payload(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"rows": []}
    slim = df[[c for c in INSIGHT_COLUMNS if c in df.columns]].copy()
    slim["date"] = pd.to_datetime(slim["date"]).dt.strftime("%Y-%m-%d")
    return {"rows": slim.to_dict(orient="records")}


def load_insights_df(settings: Settings, start, end) -> pd.DataFrame:
    if isinstance(start, str):
        start = pd.Timestamp(start).date()
    if isinstance(end, str):
        end = pd.Timestamp(end).date()
    df = gcs_store.read_parquet_range(settings, start=start, end=end)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df


def register_data_callbacks(dash_app, settings: Settings) -> None:
    @callback(
        Output("insights-store", "data"),
        Output("last-updated", "children"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("data-refresh-token", "data"),
        running=[
            (Output("data-loading-bar", "style"), _LOADING_VISIBLE, _LOADING_HIDDEN),
            (Output("data-loading-msg", "style"), _LOADING_VISIBLE, _LOADING_HIDDEN),
            (Output("data-loading-bar", "animated"), True, False),
            (Output("data-loading-bar", "striped"), True, False),
        ],
        prevent_initial_call=False,
    )
    def load_insights(start_date, end_date, _token):
        start, end = _resolve_range(start_date, end_date)
        try:
            df = load_insights_df(settings, start, end)
            updated = f"Data as of {_utcnow().strftime('%H:%M UTC')} · {len(df):,} rows"
            return _insights_payload(df), updated
        except Exception as exc:
            return {"rows": [], "error": str(exc)}, f"Load error: {exc}"

    @callback(
        Output("leads-store", "data"),
        Output("manifest-store", "data"),
        Input("data-refresh-token", "data"),
        Input("refresh-interval", "n_intervals"),
        prevent_initial_call=False,
    )
    def load_leads_and_manifest(_token, _n):
        try:
            tutors, parents = load_leads_segments(settings)
            manifest = gcs_store.read_manifest(settings)
            return {"tutors": tutors, "parents": parents}, manifest
        except Exception as exc:
            return {"tutors": [], "parents": [], "error": str(exc)}, {}

    @callback(
        Output("date-range", "start_date"),
        Output("date-range", "end_date"),
        Input("date-preset", "value"),
        prevent_initial_call=False,
    )
    def sync_date_picker(preset):
        end = _utcnow().date()
        start = end - timedelta(days=(preset or 30) - 1)
        return start.isoformat(), end.isoformat()
