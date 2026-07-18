from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html


def kpi_card(label: str, value: str, delta: float | None, spark_graph) -> dbc.Col:
    delta_color = "success" if delta and delta > 0 else "danger" if delta and delta < 0 else "secondary"
    delta_text = f"{delta:+.1f}%" if delta is not None else "—"
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                [
                    html.Div(value, className="kpi-value"),
                    html.Div(label, className="kpi-label"),
                    dbc.Badge(delta_text, color=delta_color, className="kpi-delta"),
                    dcc.Graph(figure=spark_graph, config={"displayModeBar": False}, className="kpi-spark"),
                ]
            ),
            className="kpi-card",
        ),
        md=3,
        sm=6,
        xs=12,
    )


def sync_progress_bar(progress: int, message: str, visible: bool) -> html.Div:
    if not visible:
        return html.Div(id="sync-progress-wrap", style={"display": "none"})
    return html.Div(
        [
            dbc.Progress(
                value=progress,
                striped=True,
                animated=True,
                className="sync-progress mb-2",
                style={"height": "22px"},
            ),
            html.Div(message, className="sync-progress-message"),
        ],
        id="sync-progress-wrap",
        className="sync-progress-wrap",
    )
