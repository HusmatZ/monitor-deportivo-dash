# views/athlete/progress_view.py
#
# ✅ PASO 14 — Progreso consume daily_summary (semana L–D y mes)
# - Lee daily_summary para el usuario (semana natural L–D y mes actual)
# - Grafica: thor_red_s, lum_red_s, comp_avg, risk_index_max
#
# Notas:
# - No toca IDs de otras vistas.
# - Usa session-user (Store global) para resolver user_id.

from dash import html, dcc, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from datetime import datetime, date, timedelta

from db import resolve_user_id, get_daily_summaries_range

BLACK_TEXT = {"color": "#e2e8f0"}
BLACK_MUTED = {"color": "rgba(226,232,240,.75)"}


def _panel(title, children):
    return html.Div(
        style={
            "width": "100%",
            "background": "#0b1220",
            "borderRadius": "12px",
            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.04)",
            "padding": "12px",
        },
        children=[
            html.Div(title, style={**BLACK_TEXT, "fontWeight": 800, "fontSize": "13px", "marginBottom": "10px"}),
            children,
        ],
    )


def _empty_fig(title: str):
    return {
        "data": [],
        "layout": {
            "title": {"text": title},
            "paper_bgcolor": "#0b1220",
            "plot_bgcolor": "#0b1220",
            "font": {"color": "#e2e8f0"},
            "margin": {"l": 40, "r": 20, "t": 45, "b": 40},
            "xaxis": {"gridcolor": "rgba(226,232,240,.08)"},
            "yaxis": {"gridcolor": "rgba(226,232,240,.08)"},
        },
    }


def _fig_from_daily(rows, title):
    # rows: list[dict], esperados keys:
    # day, thor_red_s, lum_red_s, comp_avg, risk_index_max
    if not rows:
        return _empty_fig(title)

    xs = [r.get("day") for r in rows]
    thor = [float(r.get("thor_red_s") or 0.0) for r in rows]
    lum = [float(r.get("lum_red_s") or 0.0) for r in rows]
    comp = [float(r.get("comp_avg") or 0.0) for r in rows]
    risk = [float(r.get("risk_index_max") or 0.0) for r in rows]

    return {
        "data": [
            {"x": xs, "y": thor, "type": "line", "name": "Rojo Torácico (s)"},
            {"x": xs, "y": lum, "type": "line", "name": "Rojo Lumbar (s)"},
            {"x": xs, "y": comp, "type": "line", "name": "Comp Avg"},
            {"x": xs, "y": risk, "type": "line", "name": "Risk Max"},
        ],
        "layout": {
            "title": {"text": title},
            "paper_bgcolor": "#0b1220",
            "plot_bgcolor": "#0b1220",
            "font": {"color": "#e2e8f0"},
            "margin": {"l": 40, "r": 20, "t": 45, "b": 40},
            "legend": {"orientation": "h", "y": -0.2},
            "xaxis": {"gridcolor": "rgba(226,232,240,.08)"},
            "yaxis": {"gridcolor": "rgba(226,232,240,.08)"},
        },
    }


def _month_end(d: date) -> date:
    # siguiente mes - 1 día
    if d.month == 12:
        nxt = date(d.year + 1, 1, 1)
    else:
        nxt = date(d.year, d.month + 1, 1)
    return nxt - timedelta(days=1)


def layout():
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())  # Lunes
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    month_end = _month_end(today)

    return html.Div(
        className="surface",
        children=[
            html.Div(
                className="mb-4",
                children=[
                    html.H2("Progreso", className="mb-1"),
                    html.Div(
                        "Resumen objetivo (sensor) por semana y mes. Se alimenta desde daily_summary.",
                        className="muted",
                    ),
                ],
            ),

            # Rangos visibles (texto)
            html.Div(
                style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "12px"},
                children=[
                    dbc.Badge(f"Semana: {week_start.isoformat()} → {week_end.isoformat()}", color="secondary", pill=True),
                    dbc.Badge(f"Mes: {month_start.isoformat()} → {month_end.isoformat()}", color="secondary", pill=True),
                ],
            ),

            dbc.Row(
                [
                    dbc.Col(
                        _panel(
                            "Semana (L–D)",
                            dcc.Graph(id="progress-week-graph", figure=_empty_fig("Semana (L–D)"), style={"height": "320px"}),
                        ),
                        xs=12,
                        lg=6,
                        className="mb-3",
                    ),
                    dbc.Col(
                        _panel(
                            "Mes actual",
                            dcc.Graph(id="progress-month-graph", figure=_empty_fig("Mes actual"), style={"height": "320px"}),
                        ),
                        xs=12,
                        lg=6,
                        className="mb-3",
                    ),
                ],
                className="g-3",
            ),

            _panel(
                "Tabla rápida (últimos 10 días)",
                html.Div(
                    id="progress-table",
                    style={
                        "borderRadius": "12px",
                        "background": "rgba(0,0,0,.12)",
                        "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                        "padding": "10px",
                        "overflowX": "auto",
                        "color": "rgba(226,232,240,.85)",
                        "fontSize": "12px",
                    },
                    children="—",
                ),
            ),
        ],
    )


def register_callbacks(app):

    @app.callback(
        [
            Output("progress-week-graph", "figure"),
            Output("progress-month-graph", "figure"),
            Output("progress-table", "children"),
        ],
        Input("session-user", "data"),
        prevent_initial_call=False,
    )
    def load_progress(session_user):
        user_id = resolve_user_id(session_user)
        if not user_id:
            # Sin usuario -> no explota, solo muestra vacío
            return _empty_fig("Semana (L–D)"), _empty_fig("Mes actual"), "Inicia sesión para ver tu progreso."

        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        month_start = today.replace(day=1)
        month_end = _month_end(today)

        week_rows = get_daily_summaries_range(user_id, week_start.isoformat(), week_end.isoformat()) or []
        month_rows = get_daily_summaries_range(user_id, month_start.isoformat(), month_end.isoformat()) or []

        fig_week = _fig_from_daily(week_rows, "Semana (L–D)")
        fig_month = _fig_from_daily(month_rows, "Mes actual")

        # Tabla últimos 10 días
        last10_start = today - timedelta(days=9)
        last10_rows = get_daily_summaries_range(user_id, last10_start.isoformat(), today.isoformat()) or []
        last10_rows = list(reversed(last10_rows))  # más reciente arriba

        if not last10_rows:
            table = "— (sin datos todavía)"
        else:
            table = html.Table(
                style={"width": "100%", "borderCollapse": "collapse"},
                children=[
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("Día", style={"textAlign": "left", "padding": "6px", "color": "#e2e8f0"}),
                                html.Th("Rojo T (s)", style={"textAlign": "left", "padding": "6px", "color": "#e2e8f0"}),
                                html.Th("Rojo L (s)", style={"textAlign": "left", "padding": "6px", "color": "#e2e8f0"}),
                                html.Th("Comp Avg", style={"textAlign": "left", "padding": "6px", "color": "#e2e8f0"}),
                                html.Th("Risk Max", style={"textAlign": "left", "padding": "6px", "color": "#e2e8f0"}),
                            ]
                        )
                    ),
                    html.Tbody(
                        [
                            html.Tr(
                                [
                                    html.Td(r.get("day", ""), style={"padding": "6px", "borderTop": "1px solid rgba(255,255,255,.08)"}),
                                    html.Td(f"{float(r.get('thor_red_s') or 0):.1f}", style={"padding": "6px", "borderTop": "1px solid rgba(255,255,255,.08)"}),
                                    html.Td(f"{float(r.get('lum_red_s') or 0):.1f}", style={"padding": "6px", "borderTop": "1px solid rgba(255,255,255,.08)"}),
                                    html.Td(f"{float(r.get('comp_avg') or 0):.1f}", style={"padding": "6px", "borderTop": "1px solid rgba(255,255,255,.08)"}),
                                    html.Td(f"{float(r.get('risk_index_max') or 0):.1f}", style={"padding": "6px", "borderTop": "1px solid rgba(255,255,255,.08)"}),
                                ]
                            )
                            for r in last10_rows[:10]
                        ]
                    ),
                ],
            )

        return fig_week, fig_month, table

