from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dash_table, html

from app.dashboard.analytics import cpl_style


def ad_performance_datatable(df) -> dash_table.DataTable:
    if df is None or df.empty:
        return html.P("No ad-level data. Pull insights to populate.", className="text-muted")
    display = df.copy()
    display["spend"] = display["spend"].map(lambda v: f"₹{v:,.0f}")
    display["cpl"] = display["cpl"].map(lambda v: f"₹{v:,.2f}" if v and v == v else "—")
    display["ctr"] = display["ctr"].map(lambda v: f"{v:.2f}%")
    display["cpc"] = display["cpc"].map(lambda v: f"₹{v:.2f}")
    return dash_table.DataTable(
        id="ad-performance-table",
        columns=[
            {"name": "Ad", "id": "object_name"},
            {"name": "Segment", "id": "segment"},
            {"name": "Spend", "id": "spend"},
            {"name": "Leads", "id": "leads"},
            {"name": "CPL", "id": "cpl"},
            {"name": "CTR", "id": "ctr"},
            {"name": "CPC", "id": "cpc"},
        ],
        data=display.to_dict("records"),
        sort_action="native",
        filter_action="native",
        page_size=10,
        style_table={"overflowX": "auto"},
        style_header={"backgroundColor": "#1f2937", "color": "#e5e7eb", "fontWeight": "600"},
        style_cell={"backgroundColor": "#111827", "color": "#e5e7eb", "padding": "10px"},
        style_data_conditional=[
            {
                "if": {"filter_query": "{cpl} contains ₹", "column_id": "cpl"},
                "color": "#22c55e",
            },
        ],
    )


def recent_leads_datatable(df) -> dash_table.DataTable:
    if df is None or df.empty:
        return html.P("No leads in GCS yet.", className="text-muted")
    return dash_table.DataTable(
        id="recent-leads-table",
        columns=[
            {"name": "When", "id": "created_time"},
            {"name": "Segment", "id": "segment"},
            {"name": "Form", "id": "form_name"},
            {"name": "Name", "id": "name"},
            {"name": "Phone", "id": "phone"},
            {"name": "Platform", "id": "platform"},
        ],
        data=df.to_dict("records"),
        sort_action="native",
        filter_action="native",
        page_size=10,
        style_table={"overflowX": "auto"},
        style_header={"backgroundColor": "#1f2937", "color": "#e5e7eb"},
        style_cell={"backgroundColor": "#111827", "color": "#e5e7eb", "padding": "10px"},
    )
