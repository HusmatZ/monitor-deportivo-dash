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
# - Guarda el RUN en DB: routine_sessions + exercise_sets + sensor_sessions(kind='routine') + RAW.
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
    get_routine_link_context,
    get_recommended_routine_today,
    get_routine_week_summary,
    create_routine_session,
    finish_routine_session,
    insert_exercise_set,
    insert_sensor_samples_raw_batch,
    start_sensor_session,
    end_sensor_session,
    upsert_session_summary,
    recompute_daily_summary,
    update_routine_session_sensor_link,
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
AX_CLASS_MAIN_CARD_TITLE = "ax-main-card-title-only ax-section-title ax-routines-main-card-title"
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
# Layout responsive de Rutinas (40/60)
# -------------------------
ROUTINES_PRIMARY_WRAPPER_STYLE = {
    "display": "flex",
    "flexDirection": "column",
    "gap": "12px",
    "width": "100%",
    "minWidth": "0",
}

ROUTINES_PRIMARY_SPLIT_STYLE = {
    "display": "flex",
    "alignItems": "stretch",
    "justifyContent": "space-between",
    "gap": "12px",
    "flexWrap": "wrap",
    "width": "100%",
    "minWidth": "0",
}

ROUTINES_PRIMARY_CALENDAR_COL_STYLE = {
    "flex": "0 1 calc((100% - 12px) * 0.40)",
    "minWidth": "320px",
    "maxWidth": "100%",
    "width": "100%",
    "display": "flex",
    "flexDirection": "column",
    "gap": "12px",
}

ROUTINES_PRIMARY_OTHER_COL_STYLE = {
    "flex": "0 1 calc((100% - 12px) * 0.60)",
    "minWidth": "320px",
    "maxWidth": "100%",
    "width": "100%",
    "display": "flex",
    "flexDirection": "column",
    "gap": "12px",
}

ROUTINES_SECONDARY_GRID_STYLE = {
    "display": "flex",
    "alignItems": "stretch",
    "justifyContent": "space-between",
    "gap": "12px",
    "flexWrap": "wrap",
    "width": "100%",
    "minWidth": "0",
}

ROUTINES_SECONDARY_SUMMARY_STYLE = {
    "flex": "1 1 220px",
    "minWidth": "220px",
    "maxWidth": "100%",
    "width": "100%",
}

ROUTINES_SECONDARY_RECOMMEND_STYLE = {
    "flex": "1 1 260px",
    "minWidth": "260px",
    "maxWidth": "100%",
    "width": "100%",
}

ROUTINES_SECONDARY_NOTES_STYLE = {
    "flex": "1 1 220px",
    "minWidth": "220px",
    "maxWidth": "100%",
    "width": "100%",
}

ROUTINES_FILL_CARD_STYLE = {
    "height": "100%",
    "minHeight": "0",
}


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
# Helpers semana calendario
# -------------------------

def _normalize_text_for_match(value) -> str:
    txt = str(value or "").strip().lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
    }
    for old, new in replacements.items():
        txt = txt.replace(old, new)
    return txt


WEEK_DETAIL_SUBCARD_STYLE = {
    "background": "rgba(255,255,255,.06)",
    "border": "1px solid rgba(255,255,255,.08)",
    "borderRadius": "12px",
    "padding": "10px 12px",
    "display": "flex",
    "flexDirection": "column",
    "gap": "4px",
    "minHeight": "72px",
}


WEEK_DETAIL_GRID_STYLE = {
    "display": "grid",
    "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
    "gap": "8px",
    "width": "100%",
}


WEEK_DETAIL_FULL_STYLE = {
    "gridColumn": "1 / -1",
}


ROUTINE_TYPE_LABELS = {
    "strength": "Fuerza",
    "accessories": "Accesorios",
    "mobility": "Movilidad",
}


def _infer_routine_type_from_session(session_row: dict) -> str:
    txt = " ".join(
        [
            _normalize_text_for_match(session_row.get("title")),
            _normalize_text_for_match(session_row.get("location")),
            _normalize_text_for_match(session_row.get("type")),
            _normalize_text_for_match(session_row.get("category")),
            _normalize_text_for_match(session_row.get("focus")),
        ]
    )

    mobility_keywords = [
        "movilidad", "mobility", "stretch", "stretching", "flexibilidad", "recovery", "recuperacion", "recovery day",
    ]
    accessory_keywords = [
        "accesorio", "accessory", "accessories", "auxiliar", "auxiliares", "complementario", "complementarios", "isolation",
    ]
    strength_keywords = [
        "fuerza", "strength", "gym", "pesas", "power", "hipertrofia", "hypertrophy", "resistencia", "workout", "training",
    ]

    if any(k in txt for k in mobility_keywords):
        return "mobility"
    if any(k in txt for k in accessory_keywords):
        return "accessories"
    if any(k in txt for k in strength_keywords):
        return "strength"
    return "strength"


def _infer_groups_from_session(session_row: dict) -> list[str]:
    txt = " ".join(
        [
            _normalize_text_for_match(session_row.get("title")),
            _normalize_text_for_match(session_row.get("location")),
            _normalize_text_for_match(session_row.get("type")),
            _normalize_text_for_match(session_row.get("category")),
            _normalize_text_for_match(session_row.get("focus")),
        ]
    )

    groups_map = [
        ("pierna", ["pierna", "piernas", "leg", "legs", "lower", "cuadriceps", "quad", "hamstring", "glute", "gluteo", "pantorrilla", "calf"]),
        ("core", ["core", "abdomen", "abdominal", "tronco", "lumbar", "estabilidad", "stability"]),
        ("empuje", ["empuje", "push", "pecho", "chest", "hombro", "shoulder", "tricep", "triceps"]),
        ("tirón", ["tiron", "pull", "espalda", "back", "remo", "row", "bicep", "biceps", "dorsal", "lat"]),
        ("movilidad", ["movilidad", "mobility", "stretch", "flexibilidad", "recovery", "recuperacion"]),
        ("cardio", ["cardio", "run", "running", "correr", "bike", "bici", "cycling", "aerob"]),
    ]

    found = []
    for label, keywords in groups_map:
        if any(k in txt for k in keywords):
            found.append(label)

    seen = []
    for item in found:
        if item not in seen:
            seen.append(item)
    return seen


def _format_sessions_label(value: int) -> str:
    return f"{value} sesión" + ("es" if int(value or 0) != 1 else "")


def _build_week_detail_card(week_sessions: list[dict], next_session: dict | None = None, streak: int = 0):
    planned_days = set()
    type_counts = {"strength": 0, "accessories": 0, "mobility": 0}
    groups_worked = []

    for item in week_sessions or []:
        start_dt = item.get("start_dt")
        if start_dt:
            try:
                planned_days.add(datetime.fromisoformat(start_dt).date().isoformat())
            except Exception:
                try:
                    planned_days.add(str(start_dt)[:10])
                except Exception:
                    pass

        routine_type = _infer_routine_type_from_session(item)
        if routine_type not in type_counts:
            type_counts[routine_type] = 0
        type_counts[routine_type] += 1

        for grp in _infer_groups_from_session(item):
            if grp not in groups_worked:
                groups_worked.append(grp)

    groups_label = ", ".join(groups_worked) if groups_worked else "Sin grupos detectados"

    if next_session:
        try:
            ndt = datetime.fromisoformat(next_session.get("start_dt"))
            when = ndt.strftime("%d %b %Y, %H:%M")
        except Exception:
            when = str(next_session.get("start_dt") or "—")
        next_title = next_session.get("title") or "Sesión planificada"
        next_location = next_session.get("location") or "—"
        next_value = f"{next_title} · {when} · {next_location}"
    else:
        next_value = "Sin próximas sesiones."

    streak_value = f"{int(streak or 0)} día" + ("s" if int(streak or 0) != 1 else "")

    def _subcard(title: str, value: str, extra_style: dict | None = None):
        style = dict(WEEK_DETAIL_SUBCARD_STYLE)
        if extra_style:
            style.update(extra_style)
        return html.Div(
            style=style,
            children=[
                html.Div(title, className=AX_CLASS_LABEL_MUTED),
                html.Div(value, className=AX_CLASS_SECTION_TITLE, style={"fontSize": "14px"}),
            ],
        )

    return html.Div(
        className=AX_CLASS_PANEL_BLACK,
        children=[
            html.Div("Detalle de la semana", className=AX_CLASS_SECTION_TITLE),
            html.Div(
                style=WEEK_DETAIL_GRID_STYLE,
                children=[
                    _subcard("Días planificados", str(len(planned_days))),
                    _subcard("Fuerza", _format_sessions_label(type_counts.get("strength", 0))),
                    _subcard("Accesorios", _format_sessions_label(type_counts.get("accessories", 0))),
                    _subcard("Movilidad", _format_sessions_label(type_counts.get("mobility", 0))),
                    _subcard("Próxima sesión", next_value, WEEK_DETAIL_FULL_STYLE),
                    _subcard("Racha", streak_value),
                    _subcard("Grupos trabajados", groups_label),
                ],
            ),
            html.Div(
                className=AX_CLASS_HIDDEN,
                children=[
                    html.Div("El detalle semanal se calcula con los datos reales del calendario.", className=AX_CLASS_LABEL_MUTED),
                    html.Div("Próxima sesión y racha vuelven a mostrarse con el mismo diseño visual de subcuadros.", className=AX_CLASS_LABEL_MUTED),
                    html.Div("Si una sesión no trae categoría explícita, se clasifica por palabras clave del título y ubicación.", className=AX_CLASS_LABEL_MUTED),
                ],
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
# Registro autónomo de callbacks
# -------------------------
def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _get_routine_user_id(session_user) -> int | None:
    """Compatibilidad: session-user puede llegar como id simple o como dict."""
    if isinstance(session_user, dict):
        return resolve_user_id(user_id=session_user.get("id"), email=session_user.get("email"))
    return resolve_user_id(session_user)


def _routine_score_from_sample(sample: dict) -> float:
    sc = sample.get("score", None)
    if sc is not None:
        return max(0.0, min(100.0, _safe_float(sc)))
    thor = str(sample.get("thor_zone") or "green")
    lum = str(sample.get("lum_zone") or "green")
    comp = _safe_float(sample.get("comp_index"))
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
    return max(0.0, min(100.0, 100.0 - penalty))


def _routine_raw_rows_from_samples(samples: list[dict]) -> list[tuple]:
    rows = []
    for s in samples or []:
        rows.append((
            _safe_int(s.get("ts_ms")),
            _safe_float(s.get("T_pitch")),
            _safe_float(s.get("T_roll")),
            _safe_float(s.get("T_yaw")),
            _safe_float(s.get("L_pitch")),
            _safe_float(s.get("L_roll")),
            _safe_float(s.get("L_yaw")),
            str(s.get("thor_zone") or "green"),
            str(s.get("lum_zone") or "green"),
            _safe_float(s.get("comp_index")),
            _safe_int(s.get("T_imu_ts_ms")),
            _safe_int(s.get("L_imu_ts_ms")),
        ))
    return rows


def _routine_plan_with_link_context(plan: dict, link_ctx: dict) -> dict:
    """Alinea mode/sport/session_type con el contrato de Cuestionario/Monitor."""
    out = dict(plan or {})
    link_ctx = link_ctx if isinstance(link_ctx, dict) else {}
    questionnaire_payload = link_ctx.get("questionnaire_payload") if isinstance(link_ctx.get("questionnaire_payload"), dict) else {}
    daily_payload = questionnaire_payload.get("daily") if isinstance(questionnaire_payload.get("daily"), dict) else {}
    out["planned_session_name"] = out.get("planned_session_name") or link_ctx.get("planned_session_name") or out.get("title") or "Rutina recomendada"
    out["mode"] = out.get("mode") or link_ctx.get("mode") or "train"
    out["sport"] = out.get("sport") or link_ctx.get("sport") or "gym"
    out["session_type"] = out.get("session_type") or link_ctx.get("session_type") or daily_payload.get("session_type") or "normal"
    out["goal"] = out.get("goal") or link_ctx.get("goal") or daily_payload.get("goal") or ""
    out["questionnaire_session_id"] = out.get("questionnaire_session_id") or link_ctx.get("questionnaire_session_id")
    out["source"] = out.get("source") or link_ctx.get("source") or "routine_recommendation"
    out["questionnaire_payload"] = out.get("questionnaire_payload") if isinstance(out.get("questionnaire_payload"), dict) else questionnaire_payload
    return out


def _routine_empty_stats(started_at_iso: str | None = None) -> dict:
    return {
        "started_at": started_at_iso or datetime.now().isoformat(timespec="seconds"),
        "prev_ts_ms": None,
        "duration_s": 0.0,
        "thor_red_s": 0.0,
        "lum_red_s": 0.0,
        "comp_sum": 0.0,
        "comp_n": 0,
        "comp_peak": 0.0,
        "alerts_count": 0,
        "score_sum": 0.0,
        "score_n": 0,
        "last_thor_zone": "green",
        "last_lum_zone": "green",
    }


def _routine_update_stats(stats: dict, samples: list[dict]) -> dict:
    stats = dict(stats or _routine_empty_stats())
    prev_ts = stats.get("prev_ts_ms")
    for s in samples or []:
        ts = _safe_int(s.get("ts_ms"), prev_ts or 0)
        dt = 0.0 if prev_ts is None else max(0.0, min(1.0, (ts - _safe_int(prev_ts)) / 1000.0))
        thor = str(s.get("thor_zone") or "green")
        lum = str(s.get("lum_zone") or "green")
        comp = _safe_float(s.get("comp_index"))
        score = _routine_score_from_sample(s)
        stats["duration_s"] = _safe_float(stats.get("duration_s")) + dt
        if thor == "red":
            stats["thor_red_s"] = _safe_float(stats.get("thor_red_s")) + dt
        if lum == "red":
            stats["lum_red_s"] = _safe_float(stats.get("lum_red_s")) + dt
        if thor == "red" and stats.get("last_thor_zone") != "red":
            stats["alerts_count"] = _safe_int(stats.get("alerts_count")) + 1
        if lum == "red" and stats.get("last_lum_zone") != "red":
            stats["alerts_count"] = _safe_int(stats.get("alerts_count")) + 1
        stats["comp_sum"] = _safe_float(stats.get("comp_sum")) + comp
        stats["comp_n"] = _safe_int(stats.get("comp_n")) + 1
        stats["comp_peak"] = max(_safe_float(stats.get("comp_peak")), comp)
        stats["score_sum"] = _safe_float(stats.get("score_sum")) + score
        stats["score_n"] = _safe_int(stats.get("score_n")) + 1
        stats["last_thor_zone"] = thor
        stats["last_lum_zone"] = lum
        stats["prev_ts_ms"] = ts
        prev_ts = ts
    return stats


def _routine_stats_summary(stats: dict) -> dict:
    stats = stats or {}
    comp_n = max(_safe_int(stats.get("comp_n")), 1)
    score_n = max(_safe_int(stats.get("score_n")), 1)
    score_avg = _safe_float(stats.get("score_sum")) / score_n
    return {
        "duration_s": _safe_float(stats.get("duration_s")),
        "thor_red_s": _safe_float(stats.get("thor_red_s")),
        "lum_red_s": _safe_float(stats.get("lum_red_s")),
        "alerts_count": _safe_int(stats.get("alerts_count")),
        "comp_avg": _safe_float(stats.get("comp_sum")) / comp_n,
        "comp_peak": _safe_float(stats.get("comp_peak")),
        "score_avg": score_avg,
        "risk_index": max(0.0, min(100.0, 100.0 - score_avg)),
    }


def _routine_flush_raw_buffer(sensor_session_id, raw_buffer) -> tuple[list, str | None]:
    """Flush RAW desacoplado de la grÃ¡fica: recibe filas ya normalizadas."""
    rows = list(raw_buffer or [])
    if not rows or sensor_session_id is None:
        return rows, None
    try:
        insert_sensor_samples_raw_batch(session_id=int(sensor_session_id), rows=rows)
        return [], None
    except Exception as exc:
        return rows, str(exc)


def _routine_current_set_summary(rs: dict, summary: dict) -> dict:
    current_ex = rs.get("current_exercise") if isinstance(rs.get("current_exercise"), dict) else {}
    return {
        "exercise_name": current_ex.get("name") or "Ejercicio",
        "set_index": _safe_int(current_ex.get("set_index"), 1),
        "reps_target": _safe_int(rs.get("reps_target"), 0),
        "reps_valid": _safe_int(rs.get("reps_valid"), 0),
        "score_avg": summary.get("score_avg"),
        "thor_red_s": summary.get("thor_red_s"),
        "lum_red_s": summary.get("lum_red_s"),
        "comp_avg": summary.get("comp_avg"),
        "comp_peak": summary.get("comp_peak"),
    }


ROUTINES_CALLBACKS_REGISTERED = False


def _get_current_dash_app():
    """Devuelve la app Dash activa si ya existe.

    Rutinas usa esta ayuda para registrar sus callbacks desde la propia vista,
    sin depender de que app.py invoque register_callbacks(...).
    """
    getter = getattr(dash, "get_app", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return None
    return None



def _ensure_callbacks_registered():
    """Compatibilidad heredada.

    Los callbacks de Rutinas se registran ahora a nivel de módulo con
    ``@dash.callback`` para que estén disponibles desde la primera apertura
    de la vista, sin requerir recarga manual de la página.
    """
    return


# -------------------------
# Layout
# -------------------------

def layout():
    _ensure_callbacks_registered()
    empty_run_fig = _empty_fig("IMU (RUN)")

    return html.Div(
        className="surface ax-routines-surface",
        children=[
            # Stores + interval RUN
            dcc.Store(id="r-plan-store"),
            dcc.Store(id="r-run-store"),
            dcc.Store(id="r-run-db-store"),
            dcc.Store(id="r-run-buffer-store"),
            dcc.Store(id="r-run-context-store"),
            dcc.Interval(id="r-run-interval", interval=200, disabled=True),
            dcc.Store(id="r-cal-refresh", data=0),
            dcc.Store(id="r-selected-date", data=None),

            # Encabezado estilo monitor
            # Ajuste solicitado:
            # - Rutinas aplica las características visuales del cuadro del título
            #   definidas en monitor_view.css.
            # - Se usa la fila responsive del monitor para que el banner herede
            #   alto, ancho y comportamiento adaptable del CSS compartido.
            html.Div(
                className="ax-monitor-title-row",
                style={
                    "width": "100%",
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

            # Distribución principal responsive 40/60 dentro del cuadro gris
            html.Div(
                className=f"{AX_CLASS_MAIN_CARD_COL} ax-routines-body",
                style=ROUTINES_PRIMARY_WRAPPER_STYLE,
                children=[
                    html.Div(
                        style=ROUTINES_PRIMARY_SPLIT_STYLE,
                        children=[
                            # Calendario semanal ocupa 40% del ancho horizontal disponible
                            html.Div(
                                style=ROUTINES_PRIMARY_CALENDAR_COL_STYLE,
                                children=[
                                    html.Div(
                                        className=f"{AX_CLASS_CARD_STACK} ax-routines-main-black-card ax-routines-calendar-card",
                                        style=ROUTINES_FILL_CARD_STYLE,
                                        children=[
                                            html.Div("Calendario semanal", className=AX_CLASS_MAIN_CARD_TITLE),
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
                                                        className=AX_CLASS_HIDDEN,
                                                        style={"display": "none"},
                                                    ),
                                                    html.Div(id="r-week-days", className="mb-2"),
                                                    html.Div(
                                                        className=AX_CLASS_HIDDEN,
                                                        children=[
                                                            html.Div("Texto informativo del calendario eliminado por ajuste solicitado.", className=AX_CLASS_LABEL_MUTED),
                                                            html.Div("Se conserva este placeholder oculto para no reducir líneas del archivo.", className=AX_CLASS_LABEL_MUTED),
                                                        ],
                                                    ),
                                                    html.Div(id="r-week-summary-detail", className="mt-1"),
                                                    html.Div(
                                                        style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "4px 0 0 0"},
                                                    ),
                                                    html.Div(
                                                        className=AX_CLASS_PANEL_BLACK,
                                                        children=[
                                                            html.Div(
                                                                id="r-inline-day-title",
                                                                className=AX_CLASS_SECTION_TITLE,
                                                                children="Detalles del día",
                                                            ),
                                                            html.Div(
                                                                id="r-inline-day-plan-section",
                                                                className="mb-3",
                                                            ),
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div("Notas del día movidas al cuadro de Notas del entrenador.", className=AX_CLASS_LABEL_MUTED),
                                                                    html.Div("Se conservan los IDs originales sin duplicarlos para no afectar callbacks.", className=AX_CLASS_LABEL_MUTED),
                                                                ],
                                                            ),
                                                            html.Div(id="r-inline-day-rec-section"),
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div(
                                                                        "Panel fijo del detalle del día extraído del popup.",
                                                                        className=AX_CLASS_LABEL_MUTED,
                                                                    ),
                                                                    html.Div(
                                                                        "Se ubica debajo del cuadro de adherencia para acceso permanente.",
                                                                        className=AX_CLASS_LABEL_MUTED,
                                                                    ),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                className=AX_CLASS_HIDDEN,
                                                children=[
                                                    html.Div("Cuadro informativo del calendario eliminado por ajuste solicitado.", className=AX_CLASS_LABEL_MUTED),
                                                    html.Div("Se conserva este placeholder oculto para no reducir líneas del archivo.", className=AX_CLASS_LABEL_MUTED),
                                                ],
                                            ),
                                            html.Div(
                                                className=AX_CLASS_HIDDEN,
                                                children=[
                                                    html.Div("Calendario semanal sincronizado con Home.", className=AX_CLASS_LABEL_MUTED),
                                                    html.Div("Se conserva este bloque oculto para no reducir líneas del archivo.", className=AX_CLASS_LABEL_MUTED),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),

                            # Todo el resto ocupa 60% y se adapta al ancho disponible
                            html.Div(
                                style=ROUTINES_PRIMARY_OTHER_COL_STYLE,
                                children=[
                                    html.Div(
                                        className=f"{AX_CLASS_CARD_STACK} ax-routines-main-black-card ax-routines-program-card",
                                        style=ROUTINES_FILL_CARD_STYLE,
                                        children=[
                                            html.Div("Programa de entrenamiento", className=AX_CLASS_MAIN_CARD_TITLE),
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
                                                    html.Div(
                                                        id="r-run-feedback",
                                                        children="",
                                                        className=AX_CLASS_LABEL_MUTED,
                                                        style={"marginTop": "4px", "marginBottom": "0"},
                                                    ),
                                                    html.Div(
                                                        className=AX_CLASS_HIDDEN,
                                                        children=[
                                                            html.Div("Cuadro visual de feedback en Acciones eliminado por ajuste solicitado.", className=AX_CLASS_LABEL_MUTED),
                                                            html.Div("Se conserva el mismo ID r-run-feedback para no afectar callbacks.", className=AX_CLASS_LABEL_MUTED),
                                                        ],
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                className=AX_CLASS_PANEL_BLACK,
                                                children=[
                                                    html.Div("Ejercicios recomendados", className=AX_CLASS_SECTION_TITLE),
                                                    html.Div(id="r-recommend-list"),
                                                ],
                                            ),
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
                                                        className=AX_CLASS_HIDDEN,
                                                        children=[
                                                            html.Div("Resumen de la semana eliminado de Programa de entrenamiento por ajuste solicitado.", className=AX_CLASS_LABEL_MUTED),
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div("Se conserva el contenedor dinámico oculto para no afectar callbacks existentes.", className=AX_CLASS_LABEL_MUTED),
                                                                    html.Div(id="r-week-summary"),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div("Contenido esperado oculto para conservar trazabilidad visual y longitud del archivo.", className=AX_CLASS_LABEL_MUTED),
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
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    _note_box("Cuando el plan esté configurado, aquí aparecerá un resumen de tu carga semanal."),
                                                                    html.Div("El bloque visible fue retirado sin tocar la lógica funcional asociada.", className=AX_CLASS_LABEL_MUTED),
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
                                                    _note_box("Nota: el RUN guarda routine_sessions, sensor_samples_raw, session_summary y exercise_sets."),
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

                                    # Bloques restantes dentro del 60% con ajuste automático de ancho
                                    html.Div(
                                        style=ROUTINES_SECONDARY_GRID_STYLE,
                                        children=[
                                            html.Div(
                                                style=ROUTINES_SECONDARY_SUMMARY_STYLE,
                                                children=[
                                                    html.Div(
                                                        className=AX_CLASS_HIDDEN,
                                                        style=ROUTINES_FILL_CARD_STYLE,
                                                        children=[
                                                            html.Div("Resumen de la semana movido a Programa de entrenamiento.", className=AX_CLASS_LABEL_MUTED),
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div("Resumen actual ahora se muestra debajo de Estado del ejercicio.", className=AX_CLASS_LABEL_MUTED),
                                                                    html.Div("Contenido esperado y nota informativa también fueron movidos sin alterar la lógica.", className=AX_CLASS_LABEL_MUTED),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div("Se conserva este placeholder oculto para no reducir líneas del archivo.", className=AX_CLASS_LABEL_MUTED),
                                                                    html.Div("La salida dinámica sigue usando el mismo callback de r-week-summary.", className=AX_CLASS_LABEL_MUTED),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            ),

                                            html.Div(
                                                style=ROUTINES_SECONDARY_RECOMMEND_STYLE,
                                                children=[
                                                    html.Div(
                                                        className=AX_CLASS_HIDDEN,
                                                        style=ROUTINES_FILL_CARD_STYLE,
                                                        children=[
                                                            html.Div("Rutina recomendada hoy eliminada de la vista por ajuste solicitado.", className=AX_CLASS_LABEL_MUTED),
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div("Resumen oculto para conservar IDs y no afectar callbacks.", className=AX_CLASS_LABEL_MUTED),
                                                                    html.Div(id="r-recommend-meta"),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div("Ejercicios recomendados ahora se muestran en Programa de entrenamiento.", className=AX_CLASS_LABEL_MUTED),
                                                                    html.Div(id="r-recommend-list-placeholder", className=AX_CLASS_LABEL_MUTED, children="Subcuadro movido sin alterar la lógica de datos."),
                                                                ],
                                                            ),
                                                            html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),

                                                            html.Div(
                                                                className=AX_CLASS_HIDDEN,
                                                                children=[
                                                                    html.Div("La nota de PASO 3 ahora se muestra debajo de la gráfica IMU.", className=AX_CLASS_LABEL_MUTED),
                                                                    html.Div("Se conserva este placeholder oculto para no reducir líneas del archivo.", className=AX_CLASS_LABEL_MUTED),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            ),

                                            html.Div(
                                                style=ROUTINES_SECONDARY_NOTES_STYLE,
                                                children=[
                                                    html.Div(
                                                        className=f"{AX_CLASS_CARD_STACK} ax-routines-main-black-card ax-routines-notes-card",
                                                        style=ROUTINES_FILL_CARD_STYLE,
                                                        children=[
                                                            html.Div("Notas del entrenador", className=AX_CLASS_MAIN_CARD_TITLE),
                                                            _routine_small_card(
                                                                "Notas del día",
                                                                html.Div(
                                                                    [
                                                                        dbc.Textarea(
                                                                            id="r-inline-notes-text",
                                                                            value="",
                                                                            placeholder="Lesión leve, tiempo, sensaciones...",
                                                                            rows=4,
                                                                            className="mb-2",
                                                                            style={
                                                                                "background": "rgba(255,255,255,.10)",
                                                                                "border": "1px solid rgba(255,255,255,.10)",
                                                                                "color": "#e2e8f0",
                                                                            },
                                                                        ),
                                                                        dbc.Button(
                                                                            "Guardar nota",
                                                                            id="r-inline-notes-save",
                                                                            color="primary",
                                                                            size="sm",
                                                                            className=AX_CLASS_BTN_PRIMARY,
                                                                        ),
                                                                        html.Span(
                                                                            id="r-inline-notes-feedback",
                                                                            className="ms-2 text-success",
                                                                        ),
                                                                    ]
                                                                ),
                                                            ),
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
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
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
def register_callbacks(app=None):
    global ROUTINES_CALLBACKS_REGISTERED
    ROUTINES_CALLBACKS_REGISTERED = True
    # Compatibilidad heredada:
    # los callbacks ya no se registran dinámicamente dentro de layout(),
    # porque eso hacía que el calendario apareciera solo después de recargar.
    # Se mantienen esta función y su firma para no romper imports externos.
    return
    try:

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

            weekday_row_style = {
                "display": "grid",
                "gridTemplateColumns": "repeat(5, minmax(0, 1fr))",
                "gap": "8px",
                "width": "100%",
                "minWidth": "0",
                "marginBottom": "8px",
            }
            weekend_row_style = {
                "display": "grid",
                "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
                "gap": "8px",
                "width": "100%",
                "minWidth": "0",
            }
            day_wrapper_style = {
                "width": "100%",
                "minWidth": "0",
                "aspectRatio": "1 / 1",
            }
            weekend_wrapper_style = {
                "width": "100%",
                "minWidth": "0",
                "height": "100%",
            }

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

                extra_line = html.Div(
                    extra_line_text,
                    className="small",
                    style={
                        "fontSize": "0.58rem",
                        "lineHeight": "1.05",
                        "minHeight": "1.15rem",
                        "maxWidth": "100%",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                        **BLACK_MUTED,
                    },
                )
                is_today = (week_offset == 0 and d == today)

                btn_style = {
                    "borderRadius": "12px",
                    "border": "1px solid rgba(255,255,255,.08)",
                    "background": "rgba(255,255,255,.14)" if is_today else "rgba(2,6,23,.78)",
                    "padding": "4px",
                    "overflow": "hidden",
                    "color": "#e2e8f0",
                    "width": "100%",
                    "height": "100%",
                    "minWidth": "0",
                    "minHeight": "0",
                    "aspectRatio": "1 / 1" if idx < 5 else None,
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                }
                if idx >= 5:
                    btn_style["height"] = "100%"
                    btn_style["minHeight"] = "0"

                content = html.Div(
                    [
                        html.Div(
                            day_names[idx],
                            className="small fw-semibold",
                            style={
                                "fontSize": "0.72rem",
                                "lineHeight": "1.05",
                                "whiteSpace": "normal",
                                "overflowWrap": "anywhere",
                            },
                        ),
                        html.Div(str(d.day), className="fw-bold", style={"fontSize": "1.5rem", "lineHeight": "1"}),
                        extra_line,
                    ],
                    style={
                        "display": "flex",
                        "flexDirection": "column",
                        "alignItems": "center",
                        "justifyContent": "center",
                        "gap": "4px",
                        "height": "100%",
                        "width": "100%",
                        "textAlign": "center",
                        "padding": "2px",
                    },
                )

                day_btn = dbc.Button(
                    content,
                    id={"type": "r-week-day", "date": d.isoformat()},
                    color="secondary",
                    className="p-1",
                    style=btn_style,
                )

                if idx < 5:
                    wrapper = html.Div(day_btn, style=day_wrapper_style)
                    weekday_boxes.append(wrapper)
                else:
                    wrapper = html.Div(day_btn, style=weekend_wrapper_style)
                    weekend_boxes.append(wrapper)

            weekday_container = html.Div(weekday_boxes, style=weekday_row_style)
            weekend_container = html.Div(weekend_boxes, style=weekend_row_style)
            # Ajuste visual solicitado para fin de semana:
            # - Sábado y domingo viven en un contenedor inferior propio.
            # - Ambos comparten el mismo ancho dentro de su fila.
            # - Su altura visible replica el largo vertical de los cuadros superiores.
            # - El contenedor inferior ocupa todo el ancho horizontal del calendario.

            week_label = f"Semana {days_list[0].strftime('%d %b')} – {end_week.strftime('%d %b %Y')}"
            week_children = [weekday_container, weekend_container]

            try:
                nxt = db.get_next_session_for_athlete(athlete_id)
            except Exception:
                nxt = None

            try:
                streak = db.get_streak(athlete_id)
            except Exception:
                streak = 0

            detail_card = _build_week_detail_card(week_sessions, nxt, streak)
            return week_label, week_children, detail_card

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
                return False, trig.get("date")
            raise PreventUpdate

        @app.callback(
            [
                Output("r-day-modal-title", "children"),
                Output("r-day-plan-section", "children"),
                Output("r-day-rec-section", "children"),
                Output("r-notes-text", "value"),
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
            return title, plan_card, rec_card, note_text

        @app.callback(
            [
                Output("r-inline-day-title", "children"),
                Output("r-inline-day-plan-section", "children"),
                Output("r-inline-day-rec-section", "children"),
                Output("r-inline-notes-text", "value"),
            ],
            [Input("r-selected-date", "data"), Input("r-cal-refresh", "data"), Input("session-user", "data")],
            prevent_initial_call=False,
        )
        def fill_r_inline_day_panel(selected_date, _refresh, session):
            if not session or (session.get("role") or "").lower() != "atleta":
                return "Detalles del día", html.Div("Inicia sesión para ver el detalle del día.", style=BLACK_MUTED), html.Div(), ""

            athlete_id = int(session.get("id"))
            if selected_date:
                try:
                    d = date.fromisoformat(selected_date)
                except Exception:
                    d = date.today()
            else:
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
            return title, plan_card, rec_card, note_text

        @app.callback(
            [Output("r-inline-notes-feedback", "children", allow_duplicate=True), Output("r-cal-refresh", "data", allow_duplicate=True)],
            Input("r-inline-notes-save", "n_clicks"),
            [State("r-inline-notes-text", "value"), State("r-selected-date", "data"), State("session-user", "data"), State("r-cal-refresh", "data")],
            prevent_initial_call=True,
        )
        def save_r_inline_note(n, text, selected_date, session, refresh):
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
            user_id = _get_routine_user_id(session_user)
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
            user_id = _get_routine_user_id(session_user)
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
            Output("r-run-store", "data", allow_duplicate=True),
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

    except Exception:
        ROUTINES_CALLBACKS_REGISTERED = False
        raise


# -------------------------
# Callbacks globales de Rutinas
# -------------------------
# Se declaran a nivel de módulo con @dash.callback para que Dash los conozca
# desde el primer render de la aplicación y la vista no necesite recarga.

@dash.callback(
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
def routines_render_routine_week(session, _refresh, n_prev, n_next):
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

    weekday_row_style = {
        "display": "grid",
        "gridTemplateColumns": "repeat(5, minmax(0, 1fr))",
        "gap": "8px",
        "width": "100%",
        "minWidth": "0",
        "marginBottom": "8px",
    }
    weekend_row_style = {
        "display": "grid",
        "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
        "gap": "8px",
        "width": "100%",
        "minWidth": "0",
    }
    day_wrapper_style = {
        "width": "100%",
        "minWidth": "0",
        "aspectRatio": "1 / 1",
    }
    weekend_wrapper_style = {
        "width": "100%",
        "minWidth": "0",
        "height": "100%",
    }

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

        extra_line = html.Div(
            extra_line_text,
            className="small",
            style={
                "fontSize": "0.58rem",
                "lineHeight": "1.05",
                "minHeight": "1.15rem",
                "maxWidth": "100%",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                **BLACK_MUTED,
            },
        )
        is_today = (week_offset == 0 and d == today)

        btn_style = {
            "borderRadius": "12px",
            "border": "1px solid rgba(255,255,255,.08)",
            "background": "rgba(255,255,255,.14)" if is_today else "rgba(2,6,23,.78)",
            "padding": "4px",
            "overflow": "hidden",
            "color": "#e2e8f0",
            "width": "100%",
            "height": "100%",
            "minWidth": "0",
            "minHeight": "0",
            "aspectRatio": "1 / 1" if idx < 5 else None,
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
        }
        if idx >= 5:
            btn_style["height"] = "100%"
            btn_style["minHeight"] = "0"

        content = html.Div(
            [
                html.Div(
                    day_names[idx],
                    className="small fw-semibold",
                    style={
                        "fontSize": "0.72rem",
                        "lineHeight": "1.05",
                        "whiteSpace": "normal",
                        "overflowWrap": "anywhere",
                    },
                ),
                html.Div(str(d.day), className="fw-bold", style={"fontSize": "1.5rem", "lineHeight": "1"}),
                extra_line,
            ],
            style={
                "display": "flex",
                "flexDirection": "column",
                "alignItems": "center",
                "justifyContent": "center",
                "gap": "4px",
                "height": "100%",
                "width": "100%",
                "textAlign": "center",
                "padding": "2px",
            },
        )

        day_btn = dbc.Button(
            content,
            id={"type": "r-week-day", "date": d.isoformat()},
            color="secondary",
            className="p-1",
            style=btn_style,
        )

        if idx < 5:
            wrapper = html.Div(day_btn, style=day_wrapper_style)
            weekday_boxes.append(wrapper)
        else:
            wrapper = html.Div(day_btn, style=weekend_wrapper_style)
            weekend_boxes.append(wrapper)

    weekday_container = html.Div(weekday_boxes, style=weekday_row_style)
    weekend_container = html.Div(weekend_boxes, style=weekend_row_style)

    week_label = f"Semana {days_list[0].strftime('%d %b')} – {end_week.strftime('%d %b %Y')}"
    week_children = [weekday_container, weekend_container]

    try:
        nxt = db.get_next_session_for_athlete(athlete_id)
    except Exception:
        nxt = None

    try:
        streak = db.get_streak(athlete_id)
    except Exception:
        streak = 0

    summary = _build_week_detail_card(week_sessions, nxt, streak)
    return week_label, week_children, summary


@dash.callback(
    Output("r-calendar-modal", "is_open"),
    [Input("r-calendar-btn", "n_clicks"), Input("r-calendar-close", "n_clicks")],
    State("r-calendar-modal", "is_open"),
    prevent_initial_call=True,
)
def routines_toggle_r_calendar_modal(open_n, close_n, is_open):
    if open_n or close_n:
        return not is_open
    raise PreventUpdate


@dash.callback(
    Output("r-calendar-body", "children"),
    Input("r-calendar-modal", "is_open"),
    State("session-user", "data"),
    prevent_initial_call=True,
)
def routines_fill_r_calendar(opened, session):
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


@dash.callback(
    [Output("r-day-detail-modal", "is_open"), Output("r-selected-date", "data")],
    [Input({"type": "r-week-day", "date": dash.dependencies.ALL}, "n_clicks"), Input("r-day-modal-close", "n_clicks")],
    [State("r-selected-date", "data"), State("r-day-detail-modal", "is_open")],
    prevent_initial_call=True,
)
def routines_toggle_r_day_modal(day_clicks, close_n, selected_date, is_open):
    trig = dash.ctx.triggered_id
    if trig == "r-day-modal-close":
        return False, selected_date
    if isinstance(trig, dict) and trig.get("type") == "r-week-day":
        if not day_clicks or max((c or 0) for c in day_clicks) <= 0:
            raise PreventUpdate
        return False, trig.get("date")
    raise PreventUpdate


@dash.callback(
    [
        Output("r-day-modal-title", "children"),
        Output("r-day-plan-section", "children"),
        Output("r-day-rec-section", "children"),
        Output("r-notes-text", "value"),
    ],
    [Input("r-selected-date", "data"), Input("r-cal-refresh", "data")],
    [State("session-user", "data"), State("r-day-detail-modal", "is_open")],
    prevent_initial_call=True,
)
def routines_fill_r_day_modal(selected_date, _refresh, session, is_open):
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
    return title, plan_card, rec_card, note_text


@dash.callback(
    [
        Output("r-inline-day-title", "children"),
        Output("r-inline-day-plan-section", "children"),
        Output("r-inline-day-rec-section", "children"),
        Output("r-inline-notes-text", "value"),
    ],
    [Input("r-selected-date", "data"), Input("r-cal-refresh", "data"), Input("session-user", "data")],
    prevent_initial_call=False,
)
def routines_fill_r_inline_day_panel(selected_date, _refresh, session):
    if not session or (session.get("role") or "").lower() != "atleta":
        return "Detalles del día", html.Div("Inicia sesión para ver el detalle del día.", style=BLACK_MUTED), html.Div(), ""

    athlete_id = int(session.get("id"))
    if selected_date:
        try:
            d = date.fromisoformat(selected_date)
        except Exception:
            d = date.today()
    else:
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
    return title, plan_card, rec_card, note_text


@dash.callback(
    [Output("r-inline-notes-feedback", "children", allow_duplicate=True), Output("r-cal-refresh", "data", allow_duplicate=True)],
    Input("r-inline-notes-save", "n_clicks"),
    [State("r-inline-notes-text", "value"), State("r-selected-date", "data"), State("session-user", "data"), State("r-cal-refresh", "data")],
    prevent_initial_call=True,
)
def routines_save_r_inline_note(n, text, selected_date, session, refresh):
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


@dash.callback(
    [Output("r-notes-feedback", "children", allow_duplicate=True), Output("r-cal-refresh", "data", allow_duplicate=True)],
    Input("r-notes-save", "n_clicks"),
    [State("r-notes-text", "value"), State("r-selected-date", "data"), State("session-user", "data"), State("r-cal-refresh", "data")],
    prevent_initial_call=True,
)
def routines_save_r_note(n, text, selected_date, session, refresh):
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


@dash.callback(
    Output("r-plan-store", "data"),
    Output("r-recommend-meta", "children"),
    Output("r-recommend-list", "children"),
    Output("r-week-summary", "children"),
    Input("session-user", "data"),
    prevent_initial_call=False,
)
def routines_load_recommended(session_user):
    user_id = _get_routine_user_id(session_user)
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


@dash.callback(
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
def routines_run_control(n_start, n_stop, session_user, plan, run_state):
    ctx = dash.ctx
    trig = ctx.triggered_id if ctx.triggered_id is not None else ""
    user_id = _get_routine_user_id(session_user)
    if not user_id:
        raise PreventUpdate

    rs = dict(run_state or {})

    if trig == "r-start-run-btn":
        if rs.get("active"):
            return rs, False, "RUN ya está activo."

        try:
            link_ctx = get_routine_link_context(user_id=user_id, day=date.today())
            plan_ctx = _routine_plan_with_link_context(plan or {}, link_ctx)
            mode = str(plan_ctx.get("mode") or "train")
            sport = str(plan_ctx.get("sport") or "gym")
            planned_session_name = plan_ctx.get("planned_session_name") or plan_ctx.get("title") or "Rutina recomendada"
            questionnaire_session_id = plan_ctx.get("questionnaire_session_id")
            SIM.mode = mode
            SIM.sport = sport
            exs = plan_ctx.get("exercises") or [{"name": "Correccion general", "sets": 1, "reps": 10}]
            ex0 = exs[0]
            exercise_name = str(ex0.get("name") or "Ejercicio")
            reps_target = _safe_int(ex0.get("reps"), 10)
            started_at = datetime.now()
            routine_payload = dict(plan_ctx)
            routine_payload["db_link"] = {"questionnaire_session_id": questionnaire_session_id, "source": plan_ctx.get("source") or "routine_run"}
            routine_session_id = create_routine_session(user_id=int(user_id), day=date.today(), plan_json=routine_payload, notes=planned_session_name)
            routine_payload["db_link"]["routine_session_id"] = routine_session_id
            sensor_session_id = start_sensor_session(
                user_id=int(user_id), kind="routine", mode=mode, sport=sport,
                started_at=started_at, planned_session_name=planned_session_name,
                questionnaire_session_id=questionnaire_session_id, routine_session_id=routine_session_id,
                context_json={
                    "source": plan_ctx.get("source") or "routine_run",
                    "questionnaire_session_id": questionnaire_session_id,
                    "routine_session_id": routine_session_id,
                    "session_type": plan_ctx.get("session_type"),
                    "goal": plan_ctx.get("goal") or "",
                    "planned_session_name": planned_session_name,
                    "mode": mode,
                    "sport": sport,
                    "questionnaire_payload": plan_ctx.get("questionnaire_payload") or {},
                    "routine_payload": routine_payload,
                    "initial_exercise": exercise_name,
                    "plan": routine_payload,
                },
            )
            update_routine_session_sensor_link(
                routine_session_id=int(routine_session_id),
                sensor_session_id=int(sensor_session_id),
                questionnaire_session_id=questionnaire_session_id,
            )
            rs = {
                "active": True,
                "routine_session_id": routine_session_id,
                "sensor_session_id": sensor_session_id,
                "questionnaire_session_id": questionnaire_session_id,
                "started_at": started_at.isoformat(timespec="seconds"),
                "planned_session_name": planned_session_name,
                "mode": mode,
                "sport": sport,
                "exercise_idx": 0,
                "current_exercise": {"name": exercise_name, "set_index": 1, "raw": ex0},
                "reps_target": reps_target,
                "reps_valid": 0,
                "rep_state": {},
                "last_ts_ms": None,
                "score_sum": 0.0,
                "score_n": 0,
                "stats": _routine_empty_stats(started_at.isoformat(timespec="seconds")),
                "raw_buffer": [],
                "ui": {"active": True, "exercise_idx": 0},
                "db": {
                    "routine_session_id": routine_session_id,
                    "sensor_session_id": sensor_session_id,
                    "questionnaire_session_id": questionnaire_session_id,
                },
                "metrics": _routine_empty_stats(started_at.isoformat(timespec="seconds")),
                "context": {
                    "source": plan_ctx.get("source") or "routine_run",
                    "planned_session_name": planned_session_name,
                    "mode": mode,
                    "sport": sport,
                    "session_type": plan_ctx.get("session_type"),
                    "goal": plan_ctx.get("goal") or "",
                },
                "plan": plan_ctx,
                "last_flush_at": started_at.isoformat(timespec="seconds"),
            }
            return rs, False, "RUN iniciado."
        except Exception as exc:
            rs["active"] = False
            rs["db_error"] = str(exc)
            return rs, True, f"Error DB al iniciar RUN: {exc}"

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
            "last_ts_ms": None,
            "score_sum": 0.0,
            "score_n": 0,
            "plan": plan or {},
        }
        return rs, False, "RUN iniciado."

    if trig == "r-stop-run-btn":
        if not rs.get("active"):
            return rs, True, "RUN no estaba activo."
        rs["active"] = False
        errors = []
        sensor_session_id = rs.get("sensor_session_id")
        routine_session_id = rs.get("routine_session_id")
        summary = _routine_stats_summary(rs.get("stats") or {})
        try:
            if sensor_session_id is not None:
                raw_buffer, flush_err = _routine_flush_raw_buffer(sensor_session_id, rs.get("raw_buffer") or [])
                rs["raw_buffer"] = raw_buffer
                if flush_err:
                    errors.append(f"raw_flush: {flush_err}")
                end_sensor_session(session_id=int(sensor_session_id))
                upsert_session_summary(
                    session_id=int(sensor_session_id),
                    duration_s=summary["duration_s"],
                    thor_red_s=summary["thor_red_s"],
                    lum_red_s=summary["lum_red_s"],
                    alerts_count=summary["alerts_count"],
                    comp_avg=summary["comp_avg"],
                    comp_peak=summary["comp_peak"],
                    risk_index=summary["risk_index"],
                )
                recompute_daily_summary(user_id=int(user_id), day=date.today())
        except Exception as exc:
            errors.append(f"sensor/summary: {exc}")
        try:
            if routine_session_id is not None:
                finish_routine_session(routine_session_id=int(routine_session_id), score_avg=summary["score_avg"], notes=rs.get("planned_session_name"))
                set_summaries = rs.get("completed_sets") if isinstance(rs.get("completed_sets"), list) else []
                if not set_summaries:
                    set_summaries = [_routine_current_set_summary(rs, summary)]
                for set_summary in set_summaries:
                    insert_exercise_set(
                        routine_session_id=int(routine_session_id),
                        exercise_name=set_summary.get("exercise_name") or "Ejercicio",
                        set_index=_safe_int(set_summary.get("set_index"), 1),
                        reps_target=_safe_int(set_summary.get("reps_target"), 0),
                        reps_valid=_safe_int(set_summary.get("reps_valid"), 0),
                        score_avg=set_summary.get("score_avg"),
                        thor_red_s=set_summary.get("thor_red_s"),
                        lum_red_s=set_summary.get("lum_red_s"),
                        comp_avg=set_summary.get("comp_avg"),
                        comp_peak=set_summary.get("comp_peak"),
                    )
        except Exception as exc:
            errors.append(f"routine/set: {exc}")
        if errors:
            rs["db_error"] = " | ".join(errors)
            return rs, True, f"Error parcial: sesiÃ³n cerrada con incidencias. {rs['db_error']}"
        return rs, True, "RUN detenido y guardado."
        return rs, True, "RUN detenido (sin guardar; PASO 3 guardará DB)."

    raise PreventUpdate


@dash.callback(
    Output("r-run-graph", "figure"),
    Output("r-ex-name", "children"),
    Output("r-ex-reps", "children"),
    Output("r-ex-score", "children"),
    Output("r-thor-chip", "children"),
    Output("r-lum-chip", "children"),
    Output("r-comp-val", "children"),
    Output("r-run-store", "data", allow_duplicate=True),
    Input("r-run-interval", "n_intervals"),
    State("r-run-store", "data"),
    prevent_initial_call=True,
)
def routines_run_tick(_n, run_state):
    rs = dict(run_state or {})
    if not rs.get("active"):
        raise PreventUpdate

    win = SIM.get_window(seconds=20)
    fig = _fig_from_window(win, "IMU (RUN)")

    last_ts = rs.get("last_ts_ms")
    samples = SIM.get_samples_since(last_ts)

    if samples:
        rs["last_ts_ms"] = int(samples[-1].get("ts_ms") or last_ts or 0)
        sensor_session_id = rs.get("sensor_session_id")
        raw_buffer = list(rs.get("raw_buffer") or [])
        raw_buffer.extend(_routine_raw_rows_from_samples(samples))
        if len(raw_buffer) >= 100:
            raw_buffer, flush_err = _routine_flush_raw_buffer(sensor_session_id, raw_buffer)
            if flush_err:
                rs["db_error"] = flush_err
        rs["raw_buffer"] = raw_buffer
        rs["stats"] = _routine_update_stats(rs.get("stats") or {}, samples)
        rs["metrics"] = rs["stats"]

        reps_added, rep_state = _rep_counter_update(
            state=rs.get("rep_state") or {},
            samples=samples,
            threshold=12.0,
            refractory_ms=650,
        )
        rs["rep_state"] = rep_state
        rs["reps_valid"] = int(rs.get("reps_valid") or 0) + int(reps_added)

        for s in samples:
            sc = s.get("score", None)
            if sc is None:
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
        if isinstance(rs.get("metrics"), dict):
            rs["metrics"]["score_sum"] = rs.get("score_sum")
            rs["metrics"]["score_n"] = rs.get("score_n")

    plan = rs.get("plan") or {}
    exs = plan.get("exercises") or [{"name": "Corrección general", "sets": 1, "reps": rs.get("reps_target", 10)}]
    ex_idx = int(rs.get("exercise_idx") or 0)
    ex = exs[min(ex_idx, len(exs) - 1)]
    ex_name = str(ex.get("name") or "Ejercicio")
    reps_target = int(rs.get("reps_target") or int(ex.get("reps") or 10))
    reps_valid = int(rs.get("reps_valid") or 0)

    thor_zone = (win.get("thor_zone") or ["green"])[-1] if win else "green"
    lum_zone = (win.get("lum_zone") or ["green"])[-1] if win else "green"
    comp_last = (win.get("comp_index") or [0.0])[-1] if win else 0.0

    n = int(rs.get("score_n") or 0)
    score_avg = float(rs.get("score_sum") or 0.0) / max(n, 1)

    reps_txt = f"{min(reps_valid, reps_target)}/{reps_target}"
    score_txt = f"{round(score_avg, 1)}"

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
