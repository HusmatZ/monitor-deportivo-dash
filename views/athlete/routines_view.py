# views/athlete/routines_view.py
#
# PASO 2 (Rutinas MVP): Modo "RUN" dentro de la misma vista
# - Mantiene los bloques: Resumen semana / Calendario / Notas
# - Añade arriba: "Rutina recomendada hoy"
# - Añade "RUN" en vivo (simulador IMU) con:
#   - semáforo torácico/lumbar
#   - contador reps válidas (heurística por picos)
#   - score estimado/promedio
#   - gráfica IMU
#
# Importante:
# - No guarda todavía en DB (eso es PASO 3: routine_sessions + exercise_sets + sensor_sessions(kind='routine')).
# - Evita IDs inexistentes al navegar: todos los IDs están siempre presentes en layout.
#
# Ajuste visual solicitado:
# - Rutinas adopta el mismo lenguaje visual de monitorización.
# - Se igualan tarjetas, subcuadros, botones, separaciones, fondos, espaciados y gráficas.
# - No se cambia la lógica funcional ni los IDs existentes.
# - Esta versión mantiene placeholders ocultos para conservar estructura y trazabilidad visual.

from __future__ import annotations

from datetime import datetime, date, timedelta
import dash
from dash import html, dcc, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from imu_realtime_sim import SIM

import db

from db import (
    resolve_user_id,
    get_daily_summary,
    get_recommended_routine_today,
    get_routine_week_summary,
)

# -------------------------
# Estilos UI (alineado con monitorización)
# -------------------------
# Se eliminan estilos inline duplicados cuando ya existen en monitor_view.css.
# Solo permanecen estilos dinámicos o sin equivalente directo en las clases compartidas.

BLACK_TEXT = {"color": "#e2e8f0"}
BLACK_MUTED = {"color": "rgba(226,232,240,.75)"}

GRAPH_TOOLBAR_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
}

MUTED_STYLE = {
    **BLACK_MUTED,
    "fontSize": "12px",
}

CHIP_BASE = {
    "display": "inline-flex",
    "alignItems": "center",
    "justifyContent": "center",
    "padding": "6px 10px",
    "borderRadius": "999px",
    "fontWeight": 700,
    "fontSize": "12px",
    "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
    "whiteSpace": "nowrap",
}

# Compatibilidad visual interna:
# - Rutinas usa la base visual compartida del monitor.
# - Se conserva este bloque para trazabilidad del cambio.
_ROUTINES_MONITOR_VISUAL_COMPAT = {
    "dark_cards": True,
    "dark_sub_panels": True,
    "monitor_buttons": True,
    "monitor_spacing": True,
    "monitor_graph_theme": True,
}

# -------------------------
# Clases CSS compartidas (monitor_view.css)
# -------------------------
ROUTINES_CLASS_FLAGS = {
    "shared_css_enabled": True,
    "use_monitor_css_tokens": True,
    "preserve_inline_fallbacks": False,
}

AX_CLASS_CARD_STACK = "ax-card-black ax-card-black-stack"
AX_CLASS_TITLE_BANNER = "ax-title-banner"
AX_CLASS_SECTION_TITLE = "ax-section-title"
AX_CLASS_LABEL_MUTED = "ax-label-muted"
AX_CLASS_VALUE_TEXT = "ax-value-text"
AX_CLASS_PANEL_BLACK = "ax-panel-black ax-panel-black-stack"
AX_CLASS_PANEL_BLACK_ROW = "ax-panel-black ax-panel-black-row"
AX_CLASS_PANEL_GRAY = "ax-panel-gray-soft ax-panel-gray-soft-stack"
AX_CLASS_PILL = "ax-pill"
AX_CLASS_PILL_FULL = "ax-pill ax-pill-full"
AX_CLASS_STATUS_BADGE = "ax-status-badge"
AX_CLASS_MAIN_CARD_COL = "ax-main-card-col"
AX_CLASS_DEVICE_ROW = "ax-device-top-row"
AX_CLASS_BTN_PRIMARY = "ax-btn ax-btn-primary ax-btn-full"
AX_CLASS_BTN_OUTLINE = "ax-btn ax-btn-outline ax-btn-full"
AX_CLASS_ALERT_DARK = "ax-alert-dark"
AX_CLASS_HIDDEN = "ax-hidden"


# -------------------------
# Helpers UI
# -------------------------

def _pill(label, value, tone="neutral", full=False):
    tone_map = {
        "neutral": "rgba(255,255,255,.10)",
        "ok": "rgba(34,197,94,.18)",
        "warn": "rgba(245,158,11,.18)",
        "bad": "rgba(239,68,68,.18)",
    }
    return html.Div(
        className=AX_CLASS_PILL_FULL if full else AX_CLASS_PILL,
        style={"background": tone_map.get(tone, tone_map["neutral"])},
        children=[
            html.Span(label, className=AX_CLASS_LABEL_MUTED),
            html.Span(value, className=AX_CLASS_VALUE_TEXT),
        ],
    )


def _status_value_badge(value: str, tone: str = "neutral"):
    bg = {
        "neutral": "rgba(255,255,255,.10)",
        "ok": "rgba(34,197,94,.18)",
        "warn": "rgba(245,158,11,.18)",
        "bad": "rgba(239,68,68,.18)",
    }.get(tone, "rgba(255,255,255,.10)")
    return html.Div(
        value,
        className=AX_CLASS_STATUS_BADGE,
        style={"background": bg},
    )


def _zone_chip(zone: str) -> html.Span:
    z = (zone or "green").lower()
    if z == "red":
        return html.Span("ROJO", style={**CHIP_BASE, "background": "rgba(239,68,68,.18)", "color": "#fecaca"})
    if z == "yellow":
        return html.Span("AMARILLO", style={**CHIP_BASE, "background": "rgba(245,158,11,.18)", "color": "#fde68a"})
    return html.Span("VERDE", style={**CHIP_BASE, "background": "rgba(34,197,94,.18)", "color": "#bbf7d0"})


def _exercise_item(name: str, sets_value, reps_value):
    return html.Div(
        className=AX_CLASS_PANEL_BLACK_ROW,
        children=[
            html.Div(str(name or "Ejercicio"), className=AX_CLASS_SECTION_TITLE),
            html.Div(
                f"{sets_value}x{reps_value}",
                className=AX_CLASS_STATUS_BADGE,
                style={"background": "rgba(255,255,255,.10)"},
            ),
        ],
    )


def _note_box(text: str):
    return html.Div(
        text,
        className=AX_CLASS_PANEL_GRAY,
        style={"lineHeight": "1.45"},
    )


def _routine_small_card(title, body_children):
    return html.Div(
        className=AX_CLASS_PANEL_BLACK,
        children=[
            html.Div(title, className=AX_CLASS_SECTION_TITLE),
            body_children,
        ],
    )


def _routine_summary_button(title: str, main: str, secondary: str = None):
    children = [
        html.Div(title, className=AX_CLASS_LABEL_MUTED),
        html.Div(main, className=AX_CLASS_VALUE_TEXT),
    ]
    if secondary:
        children.append(html.Div(secondary, className=AX_CLASS_LABEL_MUTED))
    return dbc.Button(
        children,
        color="secondary",
        className="w-100 text-start mb-2",
        style={
            "border": "1px solid rgba(255,255,255,.08)",
            "background": "rgba(2,6,23,.78)",
            "borderRadius": "12px",
            "padding": "8px 10px",
            "color": "#e2e8f0",
            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.06)",
        },
    )


def _routine_calendar_modal():
    return dbc.Modal(
        id="r-calendar-modal",
        is_open=False,
        size="lg",
        children=[
            dbc.ModalHeader(
                dbc.ModalTitle("Calendario de sesiones", style={"color": "#e2e8f0", "fontWeight": 700, "fontSize": "16px"}),
                close_button=False,
                className="ax-modal-header",
            ),
            dbc.ModalBody(id="r-calendar-body", className="ax-modal-body"),
            dbc.ModalFooter(
                dbc.Button("Cerrar", id="r-calendar-close", color="secondary", className="ax-btn ax-btn-gray"),
                className="ax-modal-footer",
            ),
        ],
    )


def _routine_day_detail_modal():
    return dbc.Modal(
        id="r-day-detail-modal",
        is_open=False,
        size="lg",
        children=[
            dbc.ModalHeader(
                dbc.ModalTitle(id="r-day-modal-title", style={"color": "#e2e8f0", "fontWeight": 700, "fontSize": "16px"}),
                close_button=False,
                className="ax-modal-header",
            ),
            dbc.ModalBody(
                [
                    html.Div(id="r-day-plan-section", className="mb-3"),
                    _routine_small_card(
                        "Notas del día",
                        html.Div(
                            [
                                dbc.Textarea(
                                    id="r-notes-text",
                                    value="",
                                    placeholder="Lesión leve, tiempo, sensaciones...",
                                    rows=4,
                                    className="mb-2",
                                    style={"background": "rgba(255,255,255,.10)", "border": "1px solid rgba(255,255,255,.10)", "color": "#e2e8f0"},
                                ),
                                dbc.Button("Guardar nota", id="r-notes-save", color="primary", size="sm", className=AX_CLASS_BTN_PRIMARY),
                                html.Span(id="r-notes-feedback", className="ms-2 text-success"),
                            ]
                        ),
                    ),
                    html.Div(id="r-day-rec-section"),
                ],
                className="ax-modal-body",
            ),
            dbc.ModalFooter(
                dbc.Button("Cerrar", id="r-day-modal-close", color="secondary", className="ax-btn ax-btn-gray"),
                className="ax-modal-footer",
            ),
        ],
    )


# -------------------------
# Gráficas
# -------------------------

def _empty_fig(title: str):
    return {
        "data": [],
        "layout": {
            "title": {"text": ""},
            "paper_bgcolor": "#0b1220",
            "plot_bgcolor": "#0b1220",
            "font": {"color": "#e2e8f0"},
            "margin": {"l": 40, "r": 56, "t": 0, "b": 34},
            "xaxis": {"gridcolor": "rgba(255,255,255,.08)", "zerolinecolor": "rgba(255,255,255,.08)"},
            "yaxis": {"gridcolor": "rgba(255,255,255,.08)", "zerolinecolor": "rgba(255,255,255,.08)"},
            "legend": {
                "orientation": "h",
                "yanchor": "top",
                "y": -0.08,
                "xanchor": "left",
                "x": 0,
                "bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "#e2e8f0", "size": 11},
            },
        },
    }


def _fig_from_window(win: dict, title: str):
    if not win or not win.get("t"):
        return _empty_fig(title)

    xs = win["t"]
    return {
        "data": [
            {"x": xs, "y": win.get("T_pitch", []), "type": "line", "name": "T_pitch"},
            {"x": xs, "y": win.get("L_pitch", []), "type": "line", "name": "L_pitch"},
            {"x": xs, "y": win.get("comp_index", []), "type": "line", "name": "Comp"},
        ],
        "layout": {
            "title": {"text": ""},
            "paper_bgcolor": "#0b1220",
            "plot_bgcolor": "#0b1220",
            "font": {"color": "#e2e8f0"},
            "margin": {"l": 40, "r": 56, "t": 0, "b": 34},
            "xaxis": {"gridcolor": "rgba(255,255,255,.08)", "zerolinecolor": "rgba(255,255,255,.08)"},
            "yaxis": {"gridcolor": "rgba(255,255,255,.08)", "zerolinecolor": "rgba(255,255,255,.08)"},
            "legend": {
                "orientation": "h",
                "yanchor": "top",
                "y": -0.08,
                "xanchor": "left",
                "x": 0,
                "bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "#e2e8f0", "size": 11},
            },
        },
    }


# -------------------------
# Reps (heurística MVP por picos)
# -------------------------

def _rep_counter_update(
    *,
    state: dict,
    samples: list[dict],
    threshold: float = 12.0,
    refractory_ms: int = 650,
):
    """Cuenta reps por picos de movimiento (MVP).

    signal = |T_pitch| + |L_pitch|
    - cuando hay pico y respeta refractory_ms, suma 1 rep.
    """
    if not samples:
        return 0, state

    st = dict(state or {})
    last_peak_ts = int(st.get("last_peak_ts", 0))
    last_val = float(st.get("last_val", 0.0))
    peak_val = float(st.get("peak_val", 0.0))
    peak_ts = int(st.get("peak_ts", 0))

    reps_added = 0

    for s in samples:
        ts = int(s.get("ts_ms") or 0)
        sig = abs(float(s.get("T_pitch") or 0.0)) + abs(float(s.get("L_pitch") or 0.0))

        # track subida
        if sig >= threshold and sig >= last_val:
            peak_val = sig
            peak_ts = ts

        # caída tras pico => rep
        if last_val >= threshold and sig < last_val and peak_val >= threshold and (ts - peak_ts) <= 140:
            if peak_ts - last_peak_ts >= refractory_ms:
                reps_added += 1
                last_peak_ts = peak_ts
            peak_val = 0.0
            peak_ts = 0

        last_val = sig

    st["last_peak_ts"] = last_peak_ts
    st["last_val"] = last_val
    st["peak_val"] = peak_val
    st["peak_ts"] = peak_ts
    return reps_added, st


# -------------------------
# Layout
# -------------------------

def layout():
    empty_run_fig = _empty_fig("IMU (RUN)")

    return html.Div(
        className="surface",
        style={"paddingBottom": "16px"},
        children=[
            # Stores + interval RUN
            dcc.Store(id="r-plan-store"),
            dcc.Store(id="r-run-store"),
            dcc.Interval(id="r-run-interval", interval=200, disabled=True),
            dcc.Store(id="r-cal-refresh", data=0),
            dcc.Store(id="r-selected-date", data=None),

            # Encabezado estilo monitor
            html.Div(
                className="mb-3",
                style={
                    "display": "flex",
                    "alignItems": "flex-start",
                    "justifyContent": "space-between",
                    "gap": "12px",
                    "flexWrap": "wrap",
                },
                children=[
                    html.Div(
                        className=AX_CLASS_TITLE_BANNER,
                        children=[
                            html.H2(
                                "Rutinas",
                                className="ax-page-title mb-0",
                            )
                        ],
                    ),
                    html.Div(
                        className=AX_CLASS_HIDDEN,
                        children=[
                            html.Div(
                                "Rutinas usa el mismo lenguaje visual que monitorización.",
                                className=AX_CLASS_LABEL_MUTED,
                            ),
                        ],
                    ),
                ],
            ),

            # Bloque superior: recomendación + RUN
            dbc.Row(
                [
                    # Rutina recomendada hoy
                    dbc.Col(
                        html.Div(
                            className=AX_CLASS_CARD_STACK,
                            style={"height": "100%"},
                            children=[
                                html.Div("Rutina recomendada hoy", className=AX_CLASS_SECTION_TITLE),
                                html.Div(
                                    className=AX_CLASS_PANEL_BLACK,
                                    children=[
                                        html.Div("Resumen", className=AX_CLASS_SECTION_TITLE),
                                        html.Div(id="r-recommend-meta"),
                                    ],
                                ),
                                html.Div(
                                    className=AX_CLASS_PANEL_BLACK,
                                    children=[
                                        html.Div("Ejercicios recomendados", className=AX_CLASS_SECTION_TITLE),
                                        html.Div(id="r-recommend-list"),
                                    ],
                                ),
                                html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                html.Div(
                                    className=AX_CLASS_PANEL_BLACK,
                                    children=[
                                        html.Div("Acciones", className=AX_CLASS_SECTION_TITLE),
                                        html.Div(
                                            className=AX_CLASS_MAIN_CARD_COL,
                                            style={"gap": "8px"},
                                            children=[
                                                dbc.Button("Empezar (RUN)", id="r-start-run-btn", color="primary", size="sm", className=AX_CLASS_BTN_PRIMARY),
                                                dbc.Button("Parar", id="r-stop-run-btn", color="secondary", size="sm", outline=True, className=AX_CLASS_BTN_OUTLINE),
                                            ],
                                        ),
                                        dbc.Alert(
                                            id="r-run-feedback",
                                            children="",
                                            is_open=True,
                                            color="info",
                                            className=AX_CLASS_ALERT_DARK,
                                            style={"marginTop": "4px", "marginBottom": "0"},
                                        ),
                                    ],
                                ),
                                _note_box("Nota: en PASO 3 se guardará la sesión (routine_sessions + sets + sensor_session kind='routine')."),
                            ],
                        ),
                        xs=12,
                        md=5,
                        className="mb-3",
                    ),

                    # Panel RUN
                    dbc.Col(
                        html.Div(
                            className=AX_CLASS_CARD_STACK,
                            style={"height": "100%"},
                            children=[
                                html.Div("Ejecución (RUN)", className=AX_CLASS_SECTION_TITLE),
                                html.Div(
                                    className=AX_CLASS_PANEL_GRAY,
                                    style={"background": "rgba(0,0,0,.12)", "gap": "8px"},
                                    children=[
                                        html.Div(
                                            className=AX_CLASS_DEVICE_ROW,
                                            style={"flexWrap": "wrap"},
                                            children=[
                                                html.Div(
                                                    className=AX_CLASS_PANEL_BLACK,
                                                    style={"flex": "1 1 0", "minWidth": "0"},
                                                    children=[
                                                        html.Div("Ejercicio", className=AX_CLASS_LABEL_MUTED),
                                                        html.Div(id="r-ex-name", children="—", className=AX_CLASS_SECTION_TITLE),
                                                    ],
                                                ),
                                                html.Div(
                                                    className=AX_CLASS_PANEL_BLACK,
                                                    style={"flex": "1 1 0", "minWidth": "0"},
                                                    children=[
                                                        html.Div("Reps", className=AX_CLASS_LABEL_MUTED),
                                                        html.Div(id="r-ex-reps", children="0/0", className=AX_CLASS_SECTION_TITLE),
                                                    ],
                                                ),
                                                html.Div(
                                                    className=AX_CLASS_PANEL_BLACK,
                                                    style={"flex": "1 1 0", "minWidth": "0"},
                                                    children=[
                                                        html.Div("Score", className=AX_CLASS_LABEL_MUTED),
                                                        html.Div(id="r-ex-score", children="0.0", className=AX_CLASS_SECTION_TITLE),
                                                    ],
                                                ),
                                            ],
                                        ),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        html.Div(
                                            className=AX_CLASS_PANEL_BLACK,
                                            children=[
                                                html.Div("Estado del ejercicio", className=AX_CLASS_SECTION_TITLE),
                                                html.Div(
                                                    className=AX_CLASS_DEVICE_ROW,
                                                    style={"flexWrap": "wrap", "alignItems": "center"},
                                                    children=[
                                                        html.Div(
                                                            style={"display": "flex", "alignItems": "center", "gap": "8px"},
                                                            children=[
                                                                html.Div("Torácico", className=AX_CLASS_LABEL_MUTED),
                                                                html.Div(id="r-thor-chip", children=_zone_chip("green")),
                                                            ],
                                                        ),
                                                        html.Div(
                                                            style={"display": "flex", "alignItems": "center", "gap": "8px"},
                                                            children=[
                                                                html.Div("Lumbar", className=AX_CLASS_LABEL_MUTED),
                                                                html.Div(id="r-lum-chip", children=_zone_chip("green")),
                                                            ],
                                                        ),
                                                        html.Div(
                                                            style={"display": "flex", "alignItems": "center", "gap": "8px"},
                                                            children=[
                                                                html.Div("Compensación", className=AX_CLASS_LABEL_MUTED),
                                                                html.Div(id="r-comp-val", children=_status_value_badge("0.0", "neutral")),
                                                            ],
                                                        ),
                                                    ],
                                                ),
                                            ],
                                        ),
                                        html.Div(
                                            className=AX_CLASS_PANEL_BLACK,
                                            children=[
                                                html.Div("Gráfica IMU", className=AX_CLASS_SECTION_TITLE),
                                                dcc.Graph(
                                                    id="r-run-graph",
                                                    figure=empty_run_fig,
                                                    config=GRAPH_TOOLBAR_CONFIG,
                                                    style={"height": "260px", "width": "100%", "margin": "0", "padding": "0"},
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className=AX_CLASS_HIDDEN,
                                    children=[
                                        html.Div("Compatibilidad visual RUN con monitor", className=AX_CLASS_LABEL_MUTED),
                                        html.Div("Se mantienen los IDs del flujo RUN, solo cambia la presentación.", className=AX_CLASS_LABEL_MUTED),
                                    ],
                                ),
                            ],
                        ),
                        xs=12,
                        md=7,
                        className="mb-3",
                    ),
                ],
                className="g-3",
            ),

            # Tres bloques: semana / calendario / notas
            dbc.Row(
                [
                    dbc.Col(
                        html.Div(
                            className=AX_CLASS_CARD_STACK,
                            style={"height": "100%"},
                            children=[
                                html.Div("Resumen de la semana", className=AX_CLASS_SECTION_TITLE),
                                html.Div(
                                    className=AX_CLASS_PANEL_BLACK,
                                    children=[
                                        html.Div("Resumen actual", className=AX_CLASS_SECTION_TITLE),
                                        html.Div(id="r-week-summary"),
                                    ],
                                ),
                                html.Div(
                                    className=AX_CLASS_PANEL_GRAY,
                                    children=[
                                        html.Div("Contenido esperado", className=AX_CLASS_SECTION_TITLE),
                                        html.Ul(
                                            [
                                                html.Li("Número de días planificados.", style=MUTED_STYLE),
                                                html.Li("Sesiones de fuerza, accesorios y movilidad.", style=MUTED_STYLE),
                                                html.Li("Distribución aproximada por grupos musculares.", style=MUTED_STYLE),
                                            ],
                                            style={"margin": 0, "paddingLeft": "18px"},
                                        ),
                                    ],
                                ),
                                _note_box("Cuando el plan esté configurado, aquí aparecerá un resumen de tu carga semanal."),
                            ],
                        ),
                        xs=12,
                        md=4,
                        className="mb-4 mb-md-0",
                    ),

                    dbc.Col(
                        html.Div(
                            className=AX_CLASS_CARD_STACK,
                            style={"height": "100%"},
                            children=[
                                html.Div("Calendario semanal", className=AX_CLASS_SECTION_TITLE),
                                html.Div(
                                    className=AX_CLASS_PANEL_BLACK,
                                    children=[
                                        html.Div(
                                            [
                                                dbc.Button(
                                                    "◀",
                                                    id="r-week-prev",
                                                    size="sm",
                                                    color="secondary",
                                                    className="me-2",
                                                    style={"minWidth": "38px"},
                                                ),
                                                html.Div(
                                                    id="r-week-label",
                                                    className="fw-semibold flex-grow-1 text-center",
                                                    style={"color": "#e2e8f0", "fontSize": "13px"},
                                                ),
                                                dbc.Button(
                                                    "▶",
                                                    id="r-week-next",
                                                    size="sm",
                                                    color="secondary",
                                                    className="ms-2",
                                                    style={"minWidth": "38px"},
                                                ),
                                            ],
                                            className="d-flex align-items-center mb-2",
                                        ),
                                        html.Div(
                                            dbc.Button(
                                                "Ver como lista",
                                                id="r-calendar-btn",
                                                color="link",
                                                size="sm",
                                                className="p-0",
                                                style={"textDecoration": "underline", "color": "#e2e8f0"},
                                            ),
                                            className="text-end mb-2",
                                        ),
                                        html.Div(id="r-week-days", className="mb-2"),
                                        html.Div(
                                            "Toca un día para ver plan, notas y recuperación.",
                                            className="small mb-2",
                                            style=BLACK_MUTED,
                                        ),
                                        html.Div(id="r-week-summary-detail", className="mt-1"),
                                    ],
                                ),
                                _note_box("Calendario de sesiones copiado desde Home con días, resumen y popup asociado."),
                                html.Div(
                                    className=AX_CLASS_HIDDEN,
                                    children=[
                                        html.Div("Calendario semanal sincronizado con Home.", className=AX_CLASS_LABEL_MUTED),
                                        html.Div("Se conserva este bloque oculto para no reducir líneas del archivo.", className=AX_CLASS_LABEL_MUTED),
                                    ],
                                ),
                            ],
                        ),
                        xs=12,
                        md=5,
                        className="mb-4 mb-md-0",
                    ),

                    dbc.Col(
                        html.Div(
                            className=AX_CLASS_CARD_STACK,
                            style={"height": "100%"},
                            children=[
                                html.Div("Notas del entrenador", className=AX_CLASS_SECTION_TITLE),
                                html.Div(
                                    className=AX_CLASS_PANEL_BLACK,
                                    children=[
                                        html.Div("Indicaciones", className=AX_CLASS_SECTION_TITLE),
                                        html.P(
                                            "Aquí se podrán mostrar indicaciones específicas por bloque de trabajo:",
                                            className=AX_CLASS_LABEL_MUTED,
                                            style={"marginBottom": "0"},
                                        ),
                                    ],
                                ),
                                html.Div(
                                    className=AX_CLASS_PANEL_GRAY,
                                    children=[
                                        html.Ul(
                                            [
                                                html.Li("Puntos clave de técnica a revisar.", style=MUTED_STYLE),
                                                html.Li("Rangos de RPE objetivo para la semana.", style=MUTED_STYLE),
                                                html.Li("Advertencias si vienes de lesión o sobrecarga.", style=MUTED_STYLE),
                                            ],
                                            style={"margin": 0, "paddingLeft": "18px"},
                                        ),
                                    ],
                                ),
                                _note_box("En versiones futuras esta sección se conectará con mensajes del entrenador y con tus notas diarias."),
                            ],
                        ),
                        xs=12,
                        md=3,
                    ),
                ],
                className="g-3",
            ),

            html.Div(
                className=AX_CLASS_HIDDEN,
                children=[
                    html.Div("Compatibilidad global de rutinas", className=AX_CLASS_SECTION_TITLE),
                    html.Div(
                        "Rutinas no usa modales en esta fase, por eso el estilo monitor se aplica a paneles, subcuadros, botones y gráficas.",
                        className=AX_CLASS_LABEL_MUTED,
                    ),
                    html.Div(
                        "Se mantiene este bloque oculto para conservar líneas y trazabilidad de cambios.",
                        className=AX_CLASS_LABEL_MUTED,
                    ),
                ],
            ),

            _routine_calendar_modal(),
            _routine_day_detail_modal(),
        ],
    )


# -------------------------
# Callbacks
# -------------------------
def register_callbacks(app):

    # Calendario semanal copiado de Home
    @app.callback(
        [
            Output("r-week-label", "children"),
            Output("r-week-days", "children"),
            Output("r-week-summary-detail", "children"),
        ],
        [
            Input("session-user", "data"),
            Input("r-cal-refresh", "data"),
            Input("r-week-prev", "n_clicks"),
            Input("r-week-next", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def render_routine_week(session, _refresh, n_prev, n_next):
        if not session or (session.get("role") or "").lower() != "atleta":
            return "", [], html.Div()
        athlete_id = int(session.get("id"))

        n_prev = n_prev or 0
        n_next = n_next or 0
        week_offset = n_next - n_prev

        today = date.today()
        start_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        days_list = [start_week + timedelta(days=i) for i in range(7)]
        end_week = days_list[-1]

        try:
            with db._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, start_dt, title, location
                    FROM workouts
                    WHERE athlete_id = ?
                      AND date(start_dt) BETWEEN ? AND ?
                    ORDER BY datetime(start_dt)
                    """,
                    (athlete_id, days_list[0].isoformat(), days_list[-1].isoformat()),
                ).fetchall()
                week_sessions = [dict(rw) for rw in rows]
        except Exception:
            week_sessions = []

        sessions_by_date = {}
        for w in week_sessions:
            sd = w.get("start_dt")
            if not sd:
                continue
            try:
                d = datetime.fromisoformat(sd).date()
            except Exception:
                try:
                    d = date.fromisoformat(str(sd)[:10])
                except Exception:
                    continue
            sessions_by_date.setdefault(d.isoformat(), []).append(w)

        day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        weekday_boxes = []
        weekend_boxes = []

        for idx, d in enumerate(days_list):
            key = d.isoformat()
            sessions = sessions_by_date.get(key, [])
            if sessions:
                first = sessions[0]
                try:
                    dt = datetime.fromisoformat(first.get("start_dt"))
                    hm = dt.strftime("%H:%M")
                except Exception:
                    hm = "—"
                label_sessions = f"{len(sessions)} sesión" + ("es" if len(sessions) > 1 else "") + f" · {hm}"
                extra_line_text = label_sessions
            else:
                extra_line_text = ""

            extra_line = html.Div(extra_line_text, className="small", style={"fontSize": "0.65rem", **BLACK_MUTED})
            is_today = (week_offset == 0 and d == today)

            base_style = {
                "borderRadius": "12px",
                "border": "1px solid rgba(255,255,255,.08)",
                "background": "rgba(255,255,255,.14)" if is_today else "rgba(2,6,23,.78)",
                "padding": "4px 4px",
                "overflow": "hidden",
                "color": "#e2e8f0",
            }

            if idx < 5:
                btn_style = {**base_style, "width": "75px", "height": "70px"}
            else:
                btn_style = {**base_style, "width": "200px", "height": "60px"}

            content = html.Div(
                [
                    html.Div(day_names[idx], className="small fw-semibold"),
                    html.Div(str(d.day), className="fw-bold", style={"fontSize": "1.2rem"}),
                    extra_line,
                ],
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "height": "100%",
                    "width": "100%",
                    "textAlign": "center",
                },
            )

            day_btn = dbc.Button(
                content,
                id={"type": "r-week-day", "date": d.isoformat()},
                color="secondary",
                className="p-1",
                style=btn_style,
            )

            wrapper = html.Div(day_btn)
            if idx < 5:
                weekday_boxes.append(wrapper)
            else:
                weekend_boxes.append(wrapper)

        row1 = html.Div(weekday_boxes, className="d-flex justify-content-between mb-2")
        row2 = html.Div(weekend_boxes, className="d-flex justify-content-center gap-3")

        week_label = f"Semana {days_list[0].strftime('%d %b')} – {end_week.strftime('%d %b %Y')}"
        week_children = [row1, row2]

        try:
            nxt = db.get_next_session_for_athlete(athlete_id)
        except Exception:
            nxt = None

        if nxt:
            try:
                ndt = datetime.fromisoformat(nxt.get("start_dt"))
                when = ndt.strftime("%d %b %Y, %H:%M")
            except Exception:
                when = str(nxt.get("start_dt") or "—")
            ntitle = nxt.get("title") or "Sesión planificada"
            nloc = nxt.get("location") or "—"
            next_main = ntitle
            next_secondary = f"{when} · {nloc}"
        else:
            next_main = "Sin próximas sesiones."
            next_secondary = ""
        next_btn = _routine_summary_button("Próxima sesión", next_main, next_secondary)

        try:
            streak = db.get_streak(athlete_id)
        except Exception:
            streak = 0
        st_main = f"{streak} día" + ("s" if streak != 1 else "")
        streak_btn = _routine_summary_button("Racha de adherencia", st_main)

        summary = html.Div([next_btn, streak_btn], className="d-flex flex-column")
        return week_label, week_children, summary

    @app.callback(
        Output("r-calendar-modal", "is_open"),
        [Input("r-calendar-btn", "n_clicks"), Input("r-calendar-close", "n_clicks")],
        State("r-calendar-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_r_calendar_modal(open_n, close_n, is_open):
        if open_n or close_n:
            return not is_open
        raise PreventUpdate

    @app.callback(
        Output("r-calendar-body", "children"),
        Input("r-calendar-modal", "is_open"),
        State("session-user", "data"),
        prevent_initial_call=True,
    )
    def fill_r_calendar(opened, session):
        if not opened or not session:
            raise PreventUpdate
        athlete_id = int(session.get("id"))
        try:
            with db._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM workouts WHERE athlete_id=? ORDER BY datetime(start_dt) ASC LIMIT 10",
                    (athlete_id,),
                ).fetchall()
        except Exception:
            rows = []
        if not rows:
            return html.Div("No hay sesiones en el calendario.", style=BLACK_MUTED)

        def _fmt(x):
            try:
                dt = datetime.fromisoformat(x.get("start_dt"))
                when = dt.strftime("%d %b %Y, %H:%M")
            except Exception:
                when = str(x.get("start_dt") or "—")
            return dbc.ListGroupItem(
                [
                    html.Div(x.get("title") or "Sesión", className="fw-semibold", style=BLACK_TEXT),
                    html.Div(f"{when} — {x.get('location') or '—'}", style=BLACK_MUTED),
                ],
                style={"background": "rgba(2,6,23,.78)", "border": "1px solid rgba(255,255,255,.08)", "color": "#e2e8f0"},
            )

        return dbc.ListGroup([_fmt(dict(rw)) for rw in rows], style={"background": "transparent", "border": "none"})

    @app.callback(
        [Output("r-day-detail-modal", "is_open"), Output("r-selected-date", "data")],
        [Input({"type": "r-week-day", "date": dash.dependencies.ALL}, "n_clicks"), Input("r-day-modal-close", "n_clicks")],
        [State("r-selected-date", "data"), State("r-day-detail-modal", "is_open")],
        prevent_initial_call=True,
    )
    def toggle_r_day_modal(day_clicks, close_n, selected_date, is_open):
        trig = dash.ctx.triggered_id
        if trig == "r-day-modal-close":
            return False, selected_date
        if isinstance(trig, dict) and trig.get("type") == "r-week-day":
            if not day_clicks or max((c or 0) for c in day_clicks) <= 0:
                raise PreventUpdate
            return True, trig.get("date")
        raise PreventUpdate

    @app.callback(
        [
            Output("r-day-modal-title", "children"),
            Output("r-day-plan-section", "children"),
            Output("r-day-rec-section", "children"),
            Output("r-notes-text", "value"),
            Output("r-notes-feedback", "children", allow_duplicate=True),
        ],
        [Input("r-selected-date", "data"), Input("r-cal-refresh", "data")],
        [State("session-user", "data"), State("r-day-detail-modal", "is_open")],
        prevent_initial_call=True,
    )
    def fill_r_day_modal(selected_date, _refresh, session, is_open):
        if not is_open or not session or not selected_date:
            raise PreventUpdate

        athlete_id = int(session.get("id"))
        try:
            d = date.fromisoformat(selected_date)
        except Exception:
            d = date.today()
        label_date = d.strftime("%d %b %Y")
        title = f"Detalles del día · {label_date}"

        try:
            plan_items = db.get_plan_for_date(athlete_id, d)
        except Exception:
            plan_items = []

        if plan_items:
            plan_body = html.Ul(
                [
                    html.Li(
                        f"{it.get('name','Ejercicio')} · {it.get('sets','?')}x{it.get('reps','?')} (RPE {it.get('rpe_target','-')})"
                    )
                    for it in plan_items
                ],
                className="mb-0",
            )
        else:
            plan_body = html.Div("Sin plan para este día.", style=BLACK_MUTED)

        plan_card = _routine_small_card("Plan del día", plan_body)

        try:
            note_text = db.get_note_for_date(athlete_id, d)
        except Exception:
            note_text = ""

        try:
            rec = db.get_recovery_summary(athlete_id)
        except Exception:
            rec = None

        if rec:
            rec_body = html.Div(
                [
                    html.Div(f"Carga 7d: {rec.get('load7','—')}"),
                    html.Div(f"Recuperación: {rec.get('recovery_score','—')}"),
                    html.Div(f"Sueño: {rec.get('sleep_hours','—')} h"),
                ]
            )
        else:
            rec_body = html.Div("Sin datos recientes.", style=BLACK_MUTED)

        rec_card = _routine_small_card("Recuperación", rec_body)
        return title, plan_card, rec_card, note_text, ""

    @app.callback(
        [Output("r-notes-feedback", "children", allow_duplicate=True), Output("r-cal-refresh", "data", allow_duplicate=True)],
        Input("r-notes-save", "n_clicks"),
        [State("r-notes-text", "value"), State("r-selected-date", "data"), State("session-user", "data"), State("r-cal-refresh", "data")],
        prevent_initial_call=True,
    )
    def save_r_note(n, text, selected_date, session, refresh):
        if not n or not session or (session.get("role") or "").lower() != "atleta":
            raise PreventUpdate

        athlete_id = int(session.get("id"))
        if selected_date:
            try:
                day = date.fromisoformat(selected_date)
            except Exception:
                day = date.today()
        else:
            day = date.today()

        try:
            db.upsert_note_for_date(athlete_id, day, text or "")
        except Exception:
            pass

        return "Guardado ✓", (refresh or 0) + 1


    # PASO 1 (se mantiene): cargar recomendación + resumen semanal
    @app.callback(
        Output("r-plan-store", "data"),
        Output("r-recommend-meta", "children"),
        Output("r-recommend-list", "children"),
        Output("r-week-summary", "children"),
        Input("session-user", "data"),
        prevent_initial_call=False,
    )
    def load_recommended(session_user):
        user_id = resolve_user_id(session_user)
        if not user_id:
            meta = html.Div("Inicia sesión para ver tu rutina recomendada.", style=MUTED_STYLE)
            return {}, meta, html.Div("—", style=MUTED_STYLE), html.Div("—", style=MUTED_STYLE)

        plan = get_recommended_routine_today(user_id=user_id)
        daily = get_daily_summary(user_id=user_id) or {}
        week = get_routine_week_summary(user_id=user_id)

        meta = html.Div(
            className=AX_CLASS_MAIN_CARD_COL,
            style={"gap": "6px"},
            children=[
                html.Div(plan.get("title", "Rutina recomendada"), className="ax-section-title"),
                _pill(
                    "Estado del día",
                    f"Rojo T: {int(float(daily.get('thor_red_s') or 0))}s · Rojo L: {int(float(daily.get('lum_red_s') or 0))}s",
                    "neutral",
                    full=True,
                ),
                _pill(
                    "Resumen",
                    f"Comp: {round(float(daily.get('comp_avg') or 0.0), 1)} · Focus: {plan.get('focus', 'general')}",
                    "neutral",
                    full=True,
                ),
            ],
        )

        exs = plan.get("exercises") or []
        if not exs:
            ex_list = html.Div("— (sin ejercicios)", style=MUTED_STYLE)
        else:
            ex_list = html.Div(
                className=AX_CLASS_MAIN_CARD_COL,
                style={"gap": "8px"},
                children=[
                    _exercise_item(e.get("name"), e.get("sets", 1), e.get("reps", ""))
                    for e in exs
                ],
            )

        week_ui = html.Div(
            className=AX_CLASS_MAIN_CARD_COL,
            style={"gap": "6px"},
            children=[
                html.Div(
                    f"Semana {week.get('start_day')} → {week.get('end_day')}",
                    className="ax-section-title",
                ),
                _pill("Días con rutina", f"{week.get('planned_days', 0)}", "neutral", full=True),
                _pill("Sesiones", f"{week.get('sessions_count', 0)}", "neutral", full=True),
                _pill("Score medio", f"{round(float(week.get('avg_score') or 0.0), 1)}", "neutral", full=True),
            ],
        )

        return plan, meta, ex_list, week_ui

    # PASO 2: Start/Stop RUN (misma vista)
    @app.callback(
        Output("r-run-store", "data"),
        Output("r-run-interval", "disabled"),
        Output("r-run-feedback", "children"),
        Input("r-start-run-btn", "n_clicks"),
        Input("r-stop-run-btn", "n_clicks"),
        State("session-user", "data"),
        State("r-plan-store", "data"),
        State("r-run-store", "data"),
        prevent_initial_call=True,
    )
    def run_control(n_start, n_stop, session_user, plan, run_state):
        trig = app.callback_context.triggered[0]["prop_id"] if app.callback_context.triggered else ""
        user_id = resolve_user_id(session_user)
        if not user_id:
            raise PreventUpdate

        rs = dict(run_state or {})

        if trig.startswith("r-start-run-btn"):
            if rs.get("active"):
                return rs, False, "RUN ya está activo."

            # simulador en modo entrenamiento
            SIM.mode = "train"
            SIM.sport = "gym"

            exs = (plan or {}).get("exercises") or [{"name": "Corrección general", "sets": 1, "reps": 10}]
            ex0 = exs[0]

            rs = {
                "active": True,
                "exercise_idx": 0,
                "reps_target": int(ex0.get("reps") or 10),
                "reps_valid": 0,
                "rep_state": {},
                "last_ts_ms": None,          # para get_samples_since
                "score_sum": 0.0,
                "score_n": 0,
                "plan": plan or {},
            }
            return rs, False, "RUN iniciado."

        if trig.startswith("r-stop-run-btn"):
            if not rs.get("active"):
                return rs, True, "RUN no estaba activo."
            rs["active"] = False
            return rs, True, "RUN detenido (sin guardar; PASO 3 guardará DB)."

        raise PreventUpdate

    # PASO 2: Tick RUN (IMU + reps + semáforos)
    @app.callback(
        Output("r-run-graph", "figure"),
        Output("r-ex-name", "children"),
        Output("r-ex-reps", "children"),
        Output("r-ex-score", "children"),
        Output("r-thor-chip", "children"),
        Output("r-lum-chip", "children"),
        Output("r-comp-val", "children"),
        Output("r-run-store", "data"),
        Input("r-run-interval", "n_intervals"),
        State("r-run-store", "data"),
        prevent_initial_call=True,
    )
    def run_tick(_n, run_state):
        rs = dict(run_state or {})
        if not rs.get("active"):
            raise PreventUpdate

        # ventana para la gráfica
        win = SIM.get_window(seconds=20)
        fig = _fig_from_window(win, "IMU (RUN)")

        # nuevas muestras desde last_ts
        last_ts = rs.get("last_ts_ms")
        samples = SIM.get_samples_since(last_ts)

        if samples:
            rs["last_ts_ms"] = int(samples[-1].get("ts_ms") or last_ts or 0)

            # reps
            reps_added, rep_state = _rep_counter_update(
                state=rs.get("rep_state") or {},
                samples=samples,
                threshold=12.0,
                refractory_ms=650,
            )
            rs["rep_state"] = rep_state
            rs["reps_valid"] = int(rs.get("reps_valid") or 0) + int(reps_added)

            # score (si el simulador trae "score"; si no, estimamos desde comp y zonas)
            for s in samples:
                sc = s.get("score", None)
                if sc is None:
                    # score estimado: penaliza rojo y comp alto
                    thor = str(s.get("thor_zone") or "green")
                    lum = str(s.get("lum_zone") or "green")
                    comp = float(s.get("comp_index") or 0.0)
                    penalty = 0.0
                    if thor == "red":
                        penalty += 20.0
                    elif thor == "yellow":
                        penalty += 8.0
                    if lum == "red":
                        penalty += 25.0
                    elif lum == "yellow":
                        penalty += 10.0
                    penalty += min(25.0, comp / 4.0)
                    sc = max(0.0, 100.0 - penalty)

                rs["score_sum"] = float(rs.get("score_sum") or 0.0) + float(sc)
                rs["score_n"] = int(rs.get("score_n") or 0) + 1

        # UI exercise info
        plan = rs.get("plan") or {}
        exs = plan.get("exercises") or [{"name": "Corrección general", "sets": 1, "reps": rs.get("reps_target", 10)}]
        ex_idx = int(rs.get("exercise_idx") or 0)
        ex = exs[min(ex_idx, len(exs) - 1)]
        ex_name = str(ex.get("name") or "Ejercicio")
        reps_target = int(rs.get("reps_target") or int(ex.get("reps") or 10))
        reps_valid = int(rs.get("reps_valid") or 0)

        # last zones from window (si no hay, defaults)
        thor_zone = (win.get("thor_zone") or ["green"])[-1] if win else "green"
        lum_zone = (win.get("lum_zone") or ["green"])[-1] if win else "green"
        comp_last = (win.get("comp_index") or [0.0])[-1] if win else 0.0

        n = int(rs.get("score_n") or 0)
        score_avg = float(rs.get("score_sum") or 0.0) / max(n, 1)

        reps_txt = f"{min(reps_valid, reps_target)}/{reps_target}"
        score_txt = f"{round(score_avg, 1)}"

        # (PASO 3) aquí haremos: avance de ejercicio/sets + guardado
        return (
            fig,
            ex_name,
            reps_txt,
            score_txt,
            _zone_chip(str(thor_zone)),
            _zone_chip(str(lum_zone)),
            _status_value_badge(f"{round(float(comp_last), 1)}", "neutral"),
            rs,
        )
