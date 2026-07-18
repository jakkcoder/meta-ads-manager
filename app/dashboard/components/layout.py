from __future__ import annotations

from pathlib import Path

import dash_bootstrap_components as dbc
from dash import dcc, html

NAV_ITEMS = [
    ("executive", "Executive"),
    ("campaigns", "Campaigns"),
    ("funnel", "Funnel"),
    ("leads", "Leads"),
    ("ads", "Ad Performance"),
    ("ops", "Data Ops"),
]


def build_layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="insights-store"),
            dcc.Store(id="leads-store"),
            dcc.Store(id="manifest-store"),
            dcc.Store(id="sync-job-store"),
            dcc.Store(id="data-refresh-token", data=0),
            dcc.Interval(id="sync-poll", interval=1000, disabled=True),
            dcc.Interval(id="refresh-interval", interval=5 * 60 * 1000, n_intervals=0),
            dbc.Container(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H4("Gharkaguru CMO", className="brand-title"),
                                    html.P("Meta Ads Analytics", className="brand-sub"),
                                ],
                                className="sidebar-brand",
                            ),
                            dbc.Nav(
                                [
                                    dbc.NavLink(label, id=f"nav-{key}", href="#", active=(key == "executive"))
                                    for key, label in NAV_ITEMS
                                ],
                                vertical=True,
                                pills=True,
                                className="sidebar-nav",
                            ),
                        ],
                        className="sidebar",
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            dbc.RadioItems(
                                                id="date-preset",
                                                options=[
                                                    {"label": "7d", "value": 7},
                                                    {"label": "30d", "value": 30},
                                                    {"label": "90d", "value": 90},
                                                ],
                                                value=30,
                                                inline=True,
                                                className="date-pills",
                                            ),
                                            dcc.DatePickerRange(
                                                id="date-range",
                                                display_format="DD MMM YYYY",
                                                className="date-picker",
                                            ),
                                            dcc.Dropdown(
                                                id="campaign-filter",
                                                options=[
                                                    {"label": "All", "value": "all"},
                                                    {"label": "Tutors", "value": "tutors"},
                                                    {"label": "Parents", "value": "parents"},
                                                ],
                                                value="all",
                                                clearable=False,
                                                style={"width": "140px"},
                                            ),
                                        ],
                                        className="toolbar-left",
                                    ),
                                    html.Div(
                                        [
                                            html.Span(id="last-updated", className="last-updated"),
                                            dbc.Badge("Ready", id="sync-pill", color="success", className="sync-pill"),
                                            dbc.Button("Pull All → GCS", id="btn-pull-all", color="success", size="sm"),
                                            dbc.Button("Pull Insights", id="btn-insights", color="primary", size="sm", outline=True),
                                            dbc.Button("Pull Leads", id="btn-leads", color="secondary", size="sm", outline=True),
                                        ],
                                        className="toolbar-right",
                                    ),
                                ],
                                className="topbar",
                            ),
                            html.Div(id="sync-progress-container"),
                            html.Div(
                                [
                                    dbc.Progress(
                                        id="data-loading-bar",
                                        value=100,
                                        striped=True,
                                        animated=True,
                                        className="data-loading-bar mb-1",
                                        style={"display": "none", "height": "6px"},
                                    ),
                                    html.Div(
                                        "Loading analytics from GCS…",
                                        id="data-loading-msg",
                                        className="data-loading-msg",
                                        style={"display": "none"},
                                    ),
                                ],
                                id="data-loading-panel",
                                className="data-loading-panel",
                            ),
                            dbc.Alert(id="sync-toast", is_open=False, duration=5000, color="success"),
                            dcc.Loading(
                                id="kpi-loading",
                                type="default",
                                color="#3b82f6",
                                children=dbc.Row(id="kpi-row", className="kpi-row g-3"),
                            ),
                            dcc.Loading(
                                id="charts-loading",
                                type="circle",
                                color="#3b82f6",
                                children=html.Div(id="tab-content", className="tab-content"),
                            ),
                        ],
                        className="main-panel",
                    ),
                ],
                fluid=True,
                className="dashboard-shell",
            ),
            dcc.Store(id="active-tab", data="executive"),
        ],
        className="cmo-root",
    )
