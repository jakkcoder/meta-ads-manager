from __future__ import annotations

import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, callback, dcc, html, no_update

from app.config import Settings
from app.dashboard.analytics import (
    ad_performance_table,
    compute_kpis,
    filter_segment,
    funnel_metrics,
    leads_daily_df,
    recent_leads_table,
)
from app.dashboard.components import charts
from app.dashboard.components.charts import GRAPH_CONFIG
from app.dashboard.components.kpi_cards import kpi_card
from app.dashboard.components.tables import ad_performance_datatable, recent_leads_datatable


def register_chart_callbacks(dash_app, settings: Settings) -> None:
    @callback(
        Output("active-tab", "data"),
        *[Output(nid, "active") for nid in [
            "nav-executive", "nav-campaigns", "nav-funnel", "nav-leads", "nav-ads", "nav-ops"
        ]],
        Input("nav-executive", "n_clicks"),
        Input("nav-campaigns", "n_clicks"),
        Input("nav-funnel", "n_clicks"),
        Input("nav-leads", "n_clicks"),
        Input("nav-ads", "n_clicks"),
        Input("nav-ops", "n_clicks"),
        prevent_initial_call=True,
    )
    def switch_tab(*_clicks):
        from dash import ctx

        tab_map = {
            "nav-executive": "executive",
            "nav-campaigns": "campaigns",
            "nav-funnel": "funnel",
            "nav-leads": "leads",
            "nav-ads": "ads",
            "nav-ops": "ops",
        }
        tab = tab_map.get(ctx.triggered_id, "executive")
        active = [tab == t for t in tab_map.values()]
        return [tab, *active]

    @callback(
        Output("kpi-row", "children"),
        Output("tab-content", "children"),
        Input("insights-store", "data"),
        Input("leads-store", "data"),
        Input("manifest-store", "data"),
        Input("active-tab", "data"),
        Input("date-range", "start_date"),
        Input("date-range", "end_date"),
        Input("campaign-filter", "value"),
        running=[
            (Output("charts-loading", "className"), "tab-content loading-active", "tab-content"),
        ],
    )
    def render_dashboard(insights_data, leads_data, manifest, tab, start_date, end_date, campaign_filter):
        tab = tab or "executive"
        df = pd.DataFrame((insights_data or {}).get("rows", []))
        if not df.empty and "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        if start_date and end_date:
            days = (pd.Timestamp(end_date).date() - pd.Timestamp(start_date).date()).days + 1
        else:
            days = 30

        filtered = filter_segment(df, campaign_filter or "all")
        kpis = compute_kpis(filtered if not filtered.empty else df, days=days)
        kpi_row = (
            [kpi_card(k["label"], k["value"], k["delta"], k["spark"]) for k in kpis]
            if kpis
            else [dbc.Col(html.P("No data — click Pull Insights or Export All", className="text-muted"), width=12)]
        )

        tutors = (leads_data or {}).get("tutors", [])
        parents = (leads_data or {}).get("parents", [])

        if tab == "executive":
            content = html.Div(
                [
                    dcc.Graph(figure=charts.spend_vs_leads_fig(filtered), config=GRAPH_CONFIG),
                    html.Div(
                        [
                            html.Div(dcc.Graph(figure=charts.rolling_cpl_fig(filtered), config=GRAPH_CONFIG), className="chart-card"),
                            html.Div(dcc.Graph(figure=charts.segment_spend_area_fig(filtered), config=GRAPH_CONFIG), className="chart-card"),
                        ],
                        className="chart-grid",
                    ),
                ]
            )
        elif tab == "campaigns":
            content = html.Div(
                [
                    html.Div(
                        [
                            html.Div(dcc.Graph(figure=charts.cpl_trend_fig(filtered), config=GRAPH_CONFIG), className="chart-card"),
                            html.Div(dcc.Graph(figure=charts.spend_share_fig(filtered), config=GRAPH_CONFIG), className="chart-card"),
                        ],
                        className="chart-grid",
                    ),
                    dcc.Graph(figure=charts.budget_gauge_fig(filtered), config=GRAPH_CONFIG),
                    dcc.Graph(figure=charts.period_compare_fig(filtered, days or 30), config=GRAPH_CONFIG),
                ]
            )
        elif tab == "funnel":
            m = funnel_metrics(filtered)
            stats = html.Div(
                [
                    html.Div([html.Div(f"{m.get('ctr', 0):.2f}%", className="funnel-stat-value"), html.Div("CTR", className="funnel-stat-label")], className="funnel-stat"),
                    html.Div([html.Div(f"{m.get('click_to_lead', 0):.2f}%", className="funnel-stat-value"), html.Div("Click→Lead", className="funnel-stat-label")], className="funnel-stat"),
                    html.Div([html.Div(f"{m.get('impression_to_lead', 0):.3f}%", className="funnel-stat-value"), html.Div("Imp→Lead", className="funnel-stat-label")], className="funnel-stat"),
                ],
                className="funnel-stats",
            ) if m else html.Div()
            content = html.Div(
                [
                    stats,
                    dcc.Graph(figure=charts.funnel_fig(filtered), config=GRAPH_CONFIG),
                    html.Div(
                        [
                            html.Div(dcc.Graph(figure=charts.ctr_cpc_fig(filtered), config=GRAPH_CONFIG), className="chart-card"),
                            html.Div(dcc.Graph(figure=charts.weekday_heatmap_fig(filtered), config=GRAPH_CONFIG), className="chart-card"),
                        ],
                        className="chart-grid",
                    ),
                ]
            )
        elif tab == "leads":
            lead_df = leads_daily_df(tutors, parents)
            content = html.Div(
                [
                    dcc.Graph(figure=charts.leads_bar_fig(lead_df), config=GRAPH_CONFIG),
                    dcc.Graph(figure=charts.cumulative_leads_fig(lead_df), config=GRAPH_CONFIG),
                    html.H5("Recent Leads", className="mt-3"),
                    recent_leads_datatable(recent_leads_table(tutors, parents)),
                ]
            )
        elif tab == "ads":
            ad_table = ad_performance_table(filtered if not filtered.empty else df)
            content = html.Div(
                [
                    dcc.Graph(figure=charts.top_ads_fig(ad_table), config=GRAPH_CONFIG),
                    html.H5("Ad Performance", className="mt-3"),
                    ad_performance_datatable(ad_table),
                ]
            )
        elif tab == "ops":
            jobs = (manifest or {}).get("jobs", {})
            history = jobs.get("history", [])
            content = html.Div(
                [
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H5("Manual Sync"),
                                html.P(
                                    "Use Pull All → GCS in the top bar for incremental Meta sync: ads, leads, and insights "
                                    f"with {settings.insights_overlap_days}-day insights overlap. "
                                    "Partitions are merged into GCS — nothing is deleted.",
                                    className="text-muted small mb-3",
                                ),
                                html.H5("Last Sync"),
                                html.H5("Current Job"),
                                html.Pre(str(jobs.get("current") or "None"), style={"fontSize": "0.8rem"}),
                                html.H5("Job History"),
                                html.Pre(str(history), style={"fontSize": "0.8rem"}),
                                html.Hr(),
                                html.A("tutors.json", href=settings.gcs_tutors_url or "#", target="_blank", className="me-3"),
                                html.A("parents.json", href=settings.gcs_parents_url or "#", target="_blank"),
                            ]
                        ),
                        className="chart-card",
                    )
                ]
            )
        else:
            content = html.Div()

        return dbc.Row(kpi_row, className="g-3"), content
