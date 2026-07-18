from __future__ import annotations

from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash

from app.config import Settings, get_settings
from app.dashboard.callbacks.chart_callbacks import register_chart_callbacks
from app.dashboard.callbacks.data_callbacks import register_data_callbacks
from app.dashboard.callbacks.sync_callbacks import register_sync_callbacks
from app.dashboard.components.layout import build_layout


def create_dash_app(settings: Settings | None = None) -> Dash:
    settings = settings or get_settings()
    assets_path = Path(__file__).parent / "assets"

    dash_app = Dash(
        __name__,
        requests_pathname_prefix="/cmo/",
        routes_pathname_prefix="/",
        suppress_callback_exceptions=True,
        title="Gharkaguru CMO Dashboard",
        external_stylesheets=[dbc.themes.DARKLY],
        assets_folder=str(assets_path),
    )

    dash_app.layout = build_layout()

    register_data_callbacks(dash_app, settings)
    register_sync_callbacks(dash_app, settings)
    register_chart_callbacks(dash_app, settings)

    return dash_app
