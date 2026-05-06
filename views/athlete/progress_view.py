# views/athlete/progress_view.py
#
# ✅ PASO 14 — Progreso consume daily_summary (semana L–D y mes)
# - Lee daily_summary para el usuario (semana natural L–D y mes actual)
# - Grafica: thor_red_s, lum_red_s, comp_avg, risk_index_max
#
# Notas:
# - No toca IDs de otras vistas.
# - Usa session-user (Store global) para resolver user_id.
# - Ajuste visual: adopta la línea de diseño de monitorización.
# - Mantiene la misma lógica funcional y los mismos callbacks.

from dash import html, dcc, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from datetime import datetime, date, timedelta

from db import resolve_user_id, get_daily_summaries_range

BLACK_TEXT = {"color": "#e2e8f0"}
BLACK_MUTED = {"color": "rgba(226,232,240,.75)"}

GRAPH_TOOLBAR_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
}

PROGRESS_PANEL_TITLE_STYLE = {
    **BLACK_TEXT,
    "fontWeight": 700,
    "fontSize": "clamp(12px, .95vw, 16px)",
    "lineHeight": "1.15",
    "marginBottom": "8px",
    "padding": "0",
}


def _panel(title, children, extra_class=""):
    return html.Div(
        className=f"ax-card-black ax-card-black-stack ax-main-card-col ax-progress-main-black-card {extra_class}".strip(),
        style={
            "width": "100%",
            "background": "#0b1220",
            "borderRadius": "12px",
            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.04)",
            "padding": "6px 12px 6px 12px",
            "display": "flex",
            "flexDirection": "column",
            "gap": "8px",
        },
        children=[
            html.Div(title, className="ax-main-card-title-only ax-progress-main-card-title", style=PROGRESS_PANEL_TITLE_STYLE),
            children,
        ],
    )



def _inner_card(children, gap="8px", padding="10px"):
    return html.Div(
        className="ax-panel-black ax-panel-black-stack",
        style={
            "width": "100%",
            "background": "rgba(2,6,23,.78)",
            "borderRadius": "12px",
            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.06)",
            "padding": padding,
            "display": "flex",
            "flexDirection": "column",
            "gap": gap,
        },
        children=children,
    )



def _range_pill(label: str, value: str):
    return html.Div(
        className="ax-pill ax-pill-full",
        style={
            "width": "100%",
            "minWidth": "0",
            "background": "rgba(2,6,23,.78)",
            "borderRadius": "12px",
            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.06)",
            "padding": "10px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            "gap": "8px",
        },
        children=[
            html.Div(label, className="ax-label-muted", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "whiteSpace": "nowrap"}),
            html.Div(
                value,
                className="ax-value-text",
                style={
                    **BLACK_TEXT,
                    "fontSize": "12px",
                    "fontWeight": 700,
                    "whiteSpace": "nowrap",
                },
            ),
        ],
    )



def _empty_fig(title: str):
    return {
        "data": [],
        "layout": {
            "title": {"text": ""},
            "paper_bgcolor": "#0b1220",
            "plot_bgcolor": "#0b1220",
            "font": {"color": "#e2e8f0"},
            "margin": {"l": 28, "r": 44, "t": 0, "b": 34},
            "showlegend": True,
            "modebar": {"orientation": "v"},
            "legend": {
                "orientation": "h",
                "yanchor": "top",
                "y": -0.08,
                "xanchor": "left",
                "x": 0,
                "bgcolor": "rgba(0,0,0,0)",
                "bordercolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "font": {"color": "#e2e8f0", "size": 11},
            },
            "xaxis": {"gridcolor": "rgba(226,232,240,.08)"},
            "yaxis": {"gridcolor": "rgba(226,232,240,.08)"},
            "annotations": [
                {
                    "text": title,
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0,
                    "y": 1.08,
                    "showarrow": False,
                    "font": {"color": "#e2e8f0", "size": 13},
                    "xanchor": "left",
                    "align": "left",
                }
            ],
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

    legend_separator_shape = {
        "type": "line",
        "xref": "paper",
        "yref": "paper",
        "x0": 0,
        "x1": 1,
        "y0": -0.045,
        "y1": -0.045,
        "line": {"color": "rgba(255,255,255,.14)", "width": 1},
    }

    return {
        "data": [
            {"x": xs, "y": thor, "type": "line", "name": "Rojo Torácico (s)"},
            {"x": xs, "y": lum, "type": "line", "name": "Rojo Lumbar (s)"},
            {"x": xs, "y": comp, "type": "line", "name": "Comp Avg"},
            {"x": xs, "y": risk, "type": "line", "name": "Risk Max"},
        ],
        "layout": {
            "title": {"text": ""},
            "paper_bgcolor": "#0b1220",
            "plot_bgcolor": "#0b1220",
            "font": {"color": "#e2e8f0"},
            "margin": {"l": 28, "r": 44, "t": 0, "b": 34},
            "showlegend": True,
            "modebar": {"orientation": "v"},
            "legend": {
                "orientation": "h",
                "yanchor": "top",
                "y": -0.08,
                "xanchor": "left",
                "x": 0,
                "bgcolor": "rgba(0,0,0,0)",
                "bordercolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "font": {"color": "#e2e8f0", "size": 11},
            },
            "xaxis": {"gridcolor": "rgba(226,232,240,.08)"},
            "yaxis": {"gridcolor": "rgba(226,232,240,.08)"},
            "shapes": [legend_separator_shape],
            "annotations": [
                {
                    "text": title,
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0,
                    "y": 1.08,
                    "showarrow": False,
                    "font": {"color": "#e2e8f0", "size": 13},
                    "xanchor": "left",
                    "align": "left",
                }
            ],
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

    progress_layout_visual_compat = {
        "monitor_title_card": True,
        "monitor_dark_panels": True,
        "monitor_inner_cards": True,
        "monitor_spacing_system": True,
    }

    return html.Div(
        className="surface ax-progress-surface",
        children=[
            html.Div(
                className="ax-monitor-title-row",
                style={"display": "flex", "alignItems": "flex-start", "justifyContent": "space-between", "gap": "12px", "flexWrap": "wrap"},
                children=[
                    html.Div(
                        className="ax-title-banner",
                        children=[
                            html.H2(
                                "Progreso",
                                className="mb-0 ax-page-title",
                            )
                        ],
                    ),
                    html.Div(
                        style={"display": "none"},
                        children=[
                            html.Div(
                                f"Compatibilidad visual progreso-monitor: {progress_layout_visual_compat}",
                                style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600},
                            ),
                        ],
                    ),
                ],
            ),

            html.Div(
                className="ax-progress-body",
                style={
                    "width": "100%",
                    "maxWidth": "100%",
                    "display": "flex",
                    "flexDirection": "column",
                    "gap": "8px",
                    "alignItems": "stretch",
                    "overflowX": "hidden",
                },
                children=[
                    _panel(
                        "Resumen",
                        html.Div(
                            style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                            children=[
                                _inner_card(
                                    [
                                        html.Div(
                                            "Resumen objetivo (sensor) por semana y mes. Se alimenta desde daily_summary.",
                                            style={**BLACK_MUTED, "fontSize": "12px"},
                                        ),
                                    ],
                                    gap="6px",
                                ),
                                html.Div(
                                    style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
                                    children=[
                                        html.Div(
                                            style={"flex": "1 1 320px", "minWidth": "280px"},
                                            children=_range_pill("Semana", f"{week_start.isoformat()} → {week_end.isoformat()}"),
                                        ),
                                        html.Div(
                                            style={"flex": "1 1 320px", "minWidth": "280px"},
                                            children=_range_pill("Mes", f"{month_start.isoformat()} → {month_end.isoformat()}"),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        extra_class="ax-progress-summary-card",
                    ),

                    html.Div(
                        style={"display": "flex", "gap": "12px", "alignItems": "flex-start", "flexWrap": "wrap"},
                        children=[
                            html.Div(
                                style={"flex": "1 1 460px", "minWidth": "320px"},
                                children=_panel(
                                    "Semana (L–D)",
                                    _inner_card(
                                        [
                                            dcc.Graph(
                                                id="progress-week-graph",
                                                figure=_empty_fig("Semana (L–D)"),
                                                style={"height": "320px", "width": "100%", "margin": "0", "padding": "0", "display": "block"},
                                                config=GRAPH_TOOLBAR_CONFIG,
                                            ),
                                        ],
                                        gap="0px",
                                        padding="8px",
                                    ),
                                ),
                            ),
                            html.Div(
                                style={"flex": "1 1 460px", "minWidth": "320px"},
                                children=_panel(
                                    "Mes actual",
                                    _inner_card(
                                        [
                                            dcc.Graph(
                                                id="progress-month-graph",
                                                figure=_empty_fig("Mes actual"),
                                                style={"height": "320px", "width": "100%", "margin": "0", "padding": "0", "display": "block"},
                                                config=GRAPH_TOOLBAR_CONFIG,
                                            ),
                                        ],
                                        gap="0px",
                                        padding="8px",
                                    ),
                                ),
                            ),
                        ],
                    ),

                    _panel(
                        "Tabla rápida (últimos 10 días)",
                        _inner_card(
                            [
                                html.Div(
                                    id="progress-table",
                                    className="axisfit-table-wrap",
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
                            ],
                            gap="8px",
                        ),
                        extra_class="ax-progress-quick-table-card",
                    ),
                ],
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
