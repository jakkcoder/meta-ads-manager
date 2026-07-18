from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.dashboard.analytics import (
    SEGMENT_COLORS,
    apply_chart_layout,
    campaign_df,
    daily_campaign_series,
    funnel_metrics,
)

GRAPH_CONFIG = {"displayModeBar": True, "displaylogo": False, "responsive": True}


def empty_fig(title: str, message: str = "Pull data to get started") -> go.Figure:
    fig = go.Figure()
    apply_chart_layout(fig, title=title, height=320)
    fig.update_layout(
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 14, "color": "#9ca3af"},
            }
        ],
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return fig


def _segment_label(name: str, segment: str) -> str:
    short = {"tutors": "Tutors", "parents": "Parents"}.get(segment, segment.title())
    return short if name.startswith("Gharkaguru_") else name


def spend_vs_leads_fig(df: pd.DataFrame) -> go.Figure:
    daily = daily_campaign_series(df)
    if daily.empty:
        return empty_fig("Spend vs Leads")
    totals = daily.groupby("date", as_index=False).agg({"spend": "sum", "leads": "sum"})
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=totals["date"],
            y=totals["spend"],
            name="Spend",
            mode="lines+markers",
            line={"color": "#60a5fa", "width": 2.5},
            marker={"size": 5},
            fill="tozeroy",
            fillcolor="rgba(96,165,250,0.12)",
            hovertemplate="₹%{y:,.0f}<extra>Spend</extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=totals["date"],
            y=totals["leads"],
            name="Leads",
            opacity=0.75,
            marker={"color": "#34d399", "line": {"width": 0}},
            hovertemplate="%{y}<extra>Leads</extra>",
        ),
        secondary_y=True,
    )
    apply_chart_layout(fig, title="Spend vs Leads", height=400)
    fig.update_yaxes(title_text="Spend (₹)", tickformat=",.0f", secondary_y=False)
    fig.update_yaxes(title_text="Leads", tickformat=",d", secondary_y=True)
    fig.update_xaxes(tickformat="%d %b")
    return fig


def rolling_cpl_fig(df: pd.DataFrame) -> go.Figure:
    daily = daily_campaign_series(df)
    if daily.empty:
        return empty_fig("Rolling CPL")
    totals = daily.groupby("date", as_index=False).agg({"spend": "sum", "leads": "sum"})
    totals["cpl"] = pd.to_numeric(
        totals["spend"] / totals["leads"].replace(0, pd.NA), errors="coerce"
    ).astype("float64")
    # Guard: an all-NaN cpl column (e.g. zero leads for every day) makes
    # rolling().mean() raise "No numeric types to aggregate".
    if totals["cpl"].notna().any():
        totals["cpl_7d"] = totals["cpl"].rolling(7, min_periods=1).mean()
    else:
        totals["cpl_7d"] = totals["cpl"]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=totals["date"],
            y=totals["cpl"],
            name="Daily CPL",
            line={"dash": "dot", "color": "#9ca3af", "width": 1.5},
            hovertemplate="₹%{y:,.2f}<extra>Daily</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=totals["date"],
            y=totals["cpl_7d"],
            name="7-day avg",
            line={"color": "#fbbf24", "width": 3},
            hovertemplate="₹%{y:,.2f}<extra>7-day avg</extra>",
        )
    )
    apply_chart_layout(fig, title="Rolling CPL (7-day)", height=340)
    fig.update_yaxes(title_text="CPL (₹)", tickformat=",.0f")
    fig.update_xaxes(tickformat="%d %b")
    return fig


def segment_spend_area_fig(df: pd.DataFrame) -> go.Figure:
    daily = daily_campaign_series(df)
    if daily.empty:
        return empty_fig("Spend by Segment")
    by_seg = daily.groupby(["date", "segment"], as_index=False)["spend"].sum()
    by_seg["segment_label"] = by_seg["segment"].map(
        {"tutors": "Tutors", "parents": "Parents"}
    ).fillna(by_seg["segment"])
    fig = px.area(
        by_seg,
        x="date",
        y="spend",
        color="segment_label",
        color_discrete_map={"Tutors": SEGMENT_COLORS["tutors"], "Parents": SEGMENT_COLORS["parents"]},
        labels={"spend": "Spend (₹)", "date": "Date"},
    )
    apply_chart_layout(fig, title="Tutors vs Parents Spend", height=340)
    fig.update_yaxes(tickformat=",.0f")
    fig.update_xaxes(tickformat="%d %b")
    return fig


def cpl_trend_fig(df: pd.DataFrame) -> go.Figure:
    daily = daily_campaign_series(df)
    if daily.empty:
        return empty_fig("CPL Trend")
    daily = daily.copy()
    daily["label"] = daily.apply(lambda r: _segment_label(r["object_name"], r["segment"]), axis=1)
    avg_cpl = float(daily["cpl"].mean())
    fig = px.line(
        daily,
        x="date",
        y="cpl",
        color="label",
        color_discrete_map={"Tutors": SEGMENT_COLORS["tutors"], "Parents": SEGMENT_COLORS["parents"]},
        labels={"cpl": "CPL (₹)", "date": "Date"},
    )
    fig.add_hline(
        y=avg_cpl,
        line_dash="dash",
        line_color="#6b7280",
        annotation_text=f"Avg ₹{avg_cpl:,.0f}",
        annotation_position="top right",
    )
    apply_chart_layout(fig, title="CPL by Campaign", height=380)
    fig.update_yaxes(tickformat=",.0f")
    fig.update_xaxes(tickformat="%d %b")
    return fig


def spend_share_fig(df: pd.DataFrame) -> go.Figure:
    daily = daily_campaign_series(df)
    if daily.empty:
        return empty_fig("Spend Share")
    share = daily.groupby("segment", as_index=False)["spend"].sum()
    share["label"] = share["segment"].map({"tutors": "Tutors", "parents": "Parents"}).fillna(share["segment"])
    total = share["spend"].sum()
    fig = px.pie(
        share,
        names="label",
        values="spend",
        hole=0.5,
        color="label",
        color_discrete_map={"Tutors": SEGMENT_COLORS["tutors"], "Parents": SEGMENT_COLORS["parents"]},
    )
    apply_chart_layout(fig, title="Spend Share", height=380)
    fig.update_traces(textinfo="percent+label", hovertemplate="₹%{value:,.0f}<extra>%{label}</extra>")
    fig.add_annotation(text=f"₹{total:,.0f}", x=0.5, y=0.5, showarrow=False, font={"size": 16, "color": "#e5e7eb"})
    return fig


def budget_gauge_fig(df: pd.DataFrame) -> go.Figure:
    camp = campaign_df(df)
    if camp.empty:
        return empty_fig("Budget Utilization")
    latest = camp.sort_values("date").groupby("object_name", as_index=False).tail(1)
    fig = go.Figure()
    for _, row in latest.iterrows():
        util = row.get("budget_utilization") or 0
        label = _segment_label(row["object_name"], row.get("segment", "other"))
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=min(float(util) * 100, 150),
                title={"text": label},
                gauge={
                    "axis": {"range": [0, 150]},
                    "bar": {"color": SEGMENT_COLORS.get(row.get("segment", "other"), "#3b82f6")},
                    "threshold": {"line": {"color": "#ef4444", "width": 2}, "value": 100},
                },
                number={"suffix": "%"},
            )
        )
    apply_chart_layout(fig, title="Budget Utilization", height=300)
    return fig


def period_compare_fig(df: pd.DataFrame, days: int) -> go.Figure:
    daily = daily_campaign_series(df)
    if daily.empty:
        return empty_fig("Period Comparison")
    end = daily["date"].max()
    cur_start = end - pd.Timedelta(days=days - 1)
    prior_end = cur_start - pd.Timedelta(days=1)
    prior_start = prior_end - pd.Timedelta(days=days - 1)
    daily = daily.copy()
    daily["label"] = daily.apply(lambda r: _segment_label(r["object_name"], r["segment"]), axis=1)
    cur = daily[(daily["date"] >= cur_start) & (daily["date"] <= end)].groupby("label")["spend"].sum()
    prv = daily[(daily["date"] >= prior_start) & (daily["date"] <= prior_end)].groupby("label")["spend"].sum()
    names = sorted(set(cur.index) | set(prv.index))
    fig = go.Figure(
        data=[
            go.Bar(
                name="Current",
                x=names,
                y=[cur.get(n, 0) for n in names],
                marker_color="#3b82f6",
                hovertemplate="₹%{y:,.0f}<extra>Current</extra>",
            ),
            go.Bar(
                name="Prior",
                x=names,
                y=[prv.get(n, 0) for n in names],
                marker_color="#6b7280",
                hovertemplate="₹%{y:,.0f}<extra>Prior</extra>",
            ),
        ]
    )
    apply_chart_layout(fig, title="Spend: Current vs Prior Period", height=380)
    fig.update_layout(barmode="group")
    fig.update_yaxes(tickformat=",.0f")
    return fig


def funnel_fig(df: pd.DataFrame) -> go.Figure:
    m = funnel_metrics(df)
    if not m:
        return empty_fig("Conversion Funnel")
    fig = go.Figure(
        go.Funnel(
            y=["Impressions", "Clicks", "Leads"],
            x=[m["impressions"], m["clicks"], m["leads"]],
            textinfo="value+percent initial",
            marker={"color": ["#6366f1", "#8b5cf6", "#22c55e"]},
        )
    )
    apply_chart_layout(fig, title="Impressions → Clicks → Leads", height=400)
    return fig


def ctr_cpc_fig(df: pd.DataFrame) -> go.Figure:
    daily = daily_campaign_series(df)
    if daily.empty:
        return empty_fig("CTR & CPC")
    totals = daily.groupby("date", as_index=False).agg({"ctr": "mean", "cpc": "mean", "clicks": "sum", "spend": "sum"})
    totals["ctr_ma"] = totals["ctr"].rolling(7, min_periods=1).mean()
    totals["cpc_ma"] = totals["cpc"].rolling(7, min_periods=1).mean()
    fig = make_subplots(rows=2, cols=1, subplot_titles=("CTR — 7-day avg (%)", "CPC — 7-day avg (₹)"), vertical_spacing=0.12)
    fig.add_trace(
        go.Scatter(x=totals["date"], y=totals["ctr_ma"], name="CTR", line={"color": "#60a5fa", "width": 2}),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=totals["date"], y=totals["cpc_ma"], name="CPC", line={"color": "#fbbf24", "width": 2}),
        row=2,
        col=1,
    )
    apply_chart_layout(fig, title="CTR & CPC Trends", height=440)
    fig.update_layout(showlegend=False)
    fig.update_xaxes(tickformat="%d %b")
    return fig


def weekday_heatmap_fig(df: pd.DataFrame) -> go.Figure:
    daily = daily_campaign_series(df)
    if daily.empty:
        return empty_fig("Leads by Weekday")
    daily = daily.copy()
    daily["weekday"] = daily["date"].dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = daily.groupby(["weekday", "segment"])["leads"].sum().unstack(fill_value=0).reindex(order)
    pivot.columns = [c.replace("tutors", "Tutors").replace("parents", "Parents") for c in pivot.columns]
    fig = px.imshow(
        pivot.T,
        labels=dict(x="Day", y="Segment", color="Leads"),
        color_continuous_scale=["#1f2937", "#3b82f6", "#fbbf24"],
        aspect="auto",
    )
    apply_chart_layout(fig, title="Leads Heatmap by Weekday", height=320)
    return fig


def leads_bar_fig(lead_df: pd.DataFrame) -> go.Figure:
    if lead_df.empty:
        return empty_fig("Lead Volume")
    frame = lead_df.copy()
    frame["segment_label"] = frame["segment"].map({"tutors": "Tutors", "parents": "Parents"}).fillna(frame["segment"])
    fig = px.bar(
        frame,
        x="date",
        y="leads",
        color="segment_label",
        barmode="group",
        color_discrete_map={"Tutors": SEGMENT_COLORS["tutors"], "Parents": SEGMENT_COLORS["parents"]},
        labels={"leads": "Leads", "date": "Date"},
    )
    apply_chart_layout(fig, title="Daily Leads by Segment", height=380)
    return fig


def cumulative_leads_fig(lead_df: pd.DataFrame) -> go.Figure:
    if lead_df.empty:
        return empty_fig("Cumulative Leads")
    frame = lead_df.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date")
    frame["segment_label"] = frame["segment"].map({"tutors": "Tutors", "parents": "Parents"}).fillna(frame["segment"])
    frame["cumulative"] = frame.groupby("segment")["leads"].cumsum()
    fig = px.line(
        frame,
        x="date",
        y="cumulative",
        color="segment_label",
        color_discrete_map={"Tutors": SEGMENT_COLORS["tutors"], "Parents": SEGMENT_COLORS["parents"]},
        labels={"cumulative": "Leads", "date": "Date"},
    )
    apply_chart_layout(fig, title="Cumulative Leads", height=340)
    return fig


def top_ads_fig(ad_table: pd.DataFrame) -> go.Figure:
    if ad_table.empty:
        return empty_fig("Top Ads")
    top = ad_table.head(5).copy()
    top["label"] = top["object_name"].str.slice(0, 28)
    fig = px.bar(
        top,
        x="label",
        y="leads",
        color="segment",
        color_discrete_map=SEGMENT_COLORS,
        labels={"leads": "Leads", "label": "Ad"},
    )
    apply_chart_layout(fig, title="Top 5 Ads by Leads", height=340)
    return fig
