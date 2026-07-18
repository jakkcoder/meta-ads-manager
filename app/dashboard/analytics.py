from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go

SEGMENT_COLORS = {"tutors": "#3b82f6", "parents": "#f59e0b", "other": "#6b7280"}
CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="#111827",
    plot_bgcolor="#1f2937",
    font={"color": "#e5e7eb", "family": "Inter, system-ui, sans-serif"},
    margin=dict(l=48, r=24, t=52, b=44),
    uirevision="cmo",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)

AXIS_STYLE = dict(
    gridcolor="#374151",
    zerolinecolor="#374151",
    tickfont=dict(color="#9ca3af", size=11),
    title_font=dict(color="#d1d5db", size=12),
)


def campaign_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["level"] == "campaign"].copy()


def daily_campaign_series(df: pd.DataFrame) -> pd.DataFrame:
    """One row per date × campaign with recomputed rates."""
    camp = campaign_df(df)
    if camp.empty:
        return camp
    grouped = (
        camp.groupby(["date", "object_name", "segment"], as_index=False)
        .agg(
            spend=("spend", "sum"),
            leads=("leads", "sum"),
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
        )
    )
    grouped["cpl"] = grouped["spend"] / grouped["leads"].replace(0, pd.NA)
    grouped["ctr"] = grouped["clicks"] / grouped["impressions"].replace(0, pd.NA) * 100
    grouped["cpc"] = grouped["spend"] / grouped["clicks"].replace(0, pd.NA)
    return grouped


def apply_chart_layout(fig: go.Figure, *, title: str, height: int) -> go.Figure:
    fig.update_layout(**CHART_LAYOUT, title=dict(text=title, x=0, xanchor="left"), height=height)
    fig.update_xaxes(**AXIS_STYLE)
    fig.update_yaxes(**AXIS_STYLE)
    return fig


def ad_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df["level"] == "ad"].copy()


def filter_segment(df: pd.DataFrame, segment: str) -> pd.DataFrame:
    if df.empty or segment == "all":
        return df
    return df[df["segment"] == segment].copy()


def period_slices(df: pd.DataFrame, days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty or "date" not in df.columns:
        return df, df
    end = df["date"].max()
    start = end - pd.Timedelta(days=days - 1)
    prior_end = start - pd.Timedelta(days=1)
    prior_start = prior_end - pd.Timedelta(days=days - 1)
    current = df[(df["date"] >= start) & (df["date"] <= end)]
    prior = df[(df["date"] >= prior_start) & (df["date"] <= prior_end)]
    return current, prior


def pct_delta(current: float, prior: float) -> float | None:
    if prior == 0:
        return None if current == 0 else 100.0
    return ((current - prior) / prior) * 100


def compute_kpis(df: pd.DataFrame, days: int = 30) -> list[dict[str, Any]]:
    camp = campaign_df(df)
    if camp.empty:
        return []
    current, prior = period_slices(camp, days)

    def agg(frame: pd.DataFrame) -> dict[str, float]:
        if frame.empty:
            return {"spend": 0, "leads": 0, "impressions": 0, "clicks": 0}
        return {
            "spend": float(frame["spend"].sum()),
            "leads": float(frame["leads"].sum()),
            "impressions": float(frame["impressions"].sum()),
            "clicks": float(frame["clicks"].sum()),
        }

    cur, prv = agg(current), agg(prior)
    cpl = cur["spend"] / cur["leads"] if cur["leads"] else 0
    prior_cpl = prv["spend"] / prv["leads"] if prv["leads"] else 0

    daily = current.groupby("date", as_index=False).agg({"spend": "sum", "leads": "sum"})

    def spark(values: list[float]) -> go.Figure:
        fig = go.Figure(go.Scatter(x=list(range(len(values))), y=values, mode="lines", line={"width": 2}))
        fig.update_layout(
            height=40,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis={"visible": False},
            yaxis={"visible": False},
            showlegend=False,
        )
        return fig

    return [
        {
            "label": "Spend",
            "value": f"₹{cur['spend']:,.0f}",
            "delta": pct_delta(cur["spend"], prv["spend"]),
            "spark": spark(daily["spend"].tail(7).tolist()),
        },
        {
            "label": "Leads",
            "value": f"{int(cur['leads']):,}",
            "delta": pct_delta(cur["leads"], prv["leads"]),
            "spark": spark(daily["leads"].tail(7).tolist()),
        },
        {
            "label": "CPL",
            "value": f"₹{cpl:,.2f}" if cur["leads"] else "—",
            "delta": pct_delta(cpl, prior_cpl) if cur["leads"] and prv["leads"] else None,
            "spark": spark((daily["spend"] / daily["leads"].replace(0, pd.NA)).fillna(0).tail(7).tolist()),
        },
        {
            "label": "Impressions",
            "value": f"{int(cur['impressions']):,}",
            "delta": pct_delta(cur["impressions"], prv["impressions"]),
            "spark": spark(
                current.groupby("date")["impressions"].sum().tail(7).tolist()
                if not current.empty
                else []
            ),
        },
    ]


def funnel_metrics(df: pd.DataFrame) -> dict[str, float]:
    camp = campaign_df(df)
    if camp.empty:
        return {}
    impressions = float(camp["impressions"].sum())
    clicks = float(camp["clicks"].sum())
    leads = float(camp["leads"].sum())
    return {
        "impressions": impressions,
        "clicks": clicks,
        "leads": leads,
        "ctr": (clicks / impressions * 100) if impressions else 0,
        "click_to_lead": (leads / clicks * 100) if clicks else 0,
        "impression_to_lead": (leads / impressions * 100) if impressions else 0,
    }


def ad_performance_table(df: pd.DataFrame) -> pd.DataFrame:
    ads = ad_df(df)
    if ads.empty:
        return ads
    grouped = (
        ads.groupby(["object_id", "object_name", "segment"], as_index=False)
        .agg(
            spend=("spend", "sum"),
            leads=("leads", "sum"),
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            ctr=("ctr", "mean"),
            cpc=("cpc", "mean"),
        )
    )
    grouped["cpl"] = grouped.apply(
        lambda r: r["spend"] / r["leads"] if r["leads"] else None,
        axis=1,
    )
    return grouped.sort_values("leads", ascending=False)


def leads_daily_df(tutors: list[dict], parents: list[dict]) -> pd.DataFrame:
    frames = []
    for leads, segment in [(tutors, "tutors"), (parents, "parents")]:
        if not leads:
            continue
        frame = pd.DataFrame(leads)
        frame["date"] = pd.to_datetime(frame["created_time"]).dt.date
        grouped = frame.groupby("date").size().reset_index(name="leads")
        grouped["segment"] = segment
        frames.append(grouped)
    if not frames:
        return pd.DataFrame(columns=["date", "leads", "segment"])
    return pd.concat(frames, ignore_index=True)


def recent_leads_table(tutors: list[dict], parents: list[dict], limit: int = 50) -> pd.DataFrame:
    rows = []
    for segment, leads in (("tutors", tutors), ("parents", parents)):
        for lead in leads:
            fields = lead.get("fields") or {}
            rows.append(
                {
                    "segment": segment,
                    "created_time": lead.get("created_time"),
                    "form_name": lead.get("form_name"),
                    "name": fields.get("full_name") or fields.get("name"),
                    "phone": fields.get("phone_number"),
                    "platform": lead.get("platform"),
                }
            )
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).sort_values("created_time", ascending=False).head(limit)
    return frame


def cpl_style(cpl: float | None) -> dict[str, str]:
    if cpl is None or pd.isna(cpl):
        return {"color": "#9ca3af"}
    if cpl < 5:
        return {"color": "#22c55e", "fontWeight": "600"}
    if cpl < 10:
        return {"color": "#f59e0b", "fontWeight": "600"}
    return {"color": "#ef4444", "fontWeight": "600"}
