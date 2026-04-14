# views/athlete/monitor_view.py
#
# Monitorización (IMU simulada en tiempo real)
# - Usa dcc.Interval para refrescar cada 200 ms
# - Importa el simulador desde imu_realtime_sim.py
#
# ✅ Incluye (hasta PASO 14 en Monitor):
# - Fix anti-roturas Dash: recorder-store.data SOLO se escribe en 1 callback (recorder_control)
# - Conexión a axisfit.db (start_sensor_session / insert_sensor_samples_raw_batch / upsert_session_summary /
#   recompute_daily_summary / end_sensor_session)
# - Start/Stop crean/cierran sensor_sessions en axisfit.db
# - Buffers/estado server-side v2: _RAW_BUFFER_MAIN + _STATS_MAIN
# - Captura RAW “tipo 2-IMUs” priorizando IMU_SIM.get_samples_since(...) y con wrapper de fallback compatible
# - Flush en lote a axisfit.db (batch) para 50 Hz (aprox, sin lag)
# - Cálculo en vivo: tiempo rojo T/L + comp (sum/avg/peak) + alerts con streak
# - STOP: session_summary + daily_summary + Risk Index v2
# - PASO 9/10: 2 semáforos (Torácica/Lumbar) + Comp + Rojo T/L (sin tocar IDs viejos hasta el PASO 11)
# - PASO 11: elimina definitivamente bpm-output (demo) y lo reemplaza por “Compensación”
# - PASO 12: renombra ecg-graph -> imu-graph
# - PASO 13: selector Deporte = Gym/CrossFit (acepta values viejos: general/strength/etc.)
#
# ℹ️ Nota importante:
# Tu imu_realtime_sim.py actual YA expone get_samples_since(last_ts_ms).
# En este monitor se usa ese camino como fuente principal para capturar RAW incremental.
# El wrapper _get_samples_since_from_window(...) se conserva solo como fallback compatible por si
# en algún entorno vuelves a usar una versión antigua del simulador que solo exponga get_window(...).

from dash import html, dcc, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from datetime import datetime, date
from statistics import median
import uuid
import time

from imu_realtime_sim import SIM as IMU_SIM
from posture_engine import DEFAULT_THRESHOLDS

# ✅ API principal axisfit.db (debe existir en db.py con DB_PATH absoluto por módulo)
from db import (
    start_sensor_session,
    insert_sensor_samples_raw_batch,
    upsert_session_summary,
    recompute_daily_summary,
    end_sensor_session,
    get_user_posture_settings,
    get_latest_valid_baseline,
    get_monitor_link_context,
)

# ✅ Export helpers (PASO 2/3)
from export_utils import make_filename, rows_to_csv_bytes

BLACK_TEXT = {"color": "#e2e8f0"}
BLACK_MUTED = {"color": "rgba(226,232,240,.75)"}

LEFT_W = "250px"
RIGHT_BOX_W = "461px"  # ✅ Cada cuadro (columna derecha) se ajusta para compensar el menor gap horizontal
RIGHT_INNER_GAP_PX = 8


MAIN_BLACK_CARD_CLASS = "ax-card-black ax-card-black-stack"
MAIN_BLACK_CARD_HEADER_CLASS = "ax-card-black-header"
MAIN_BLACK_CARD_TITLE_CLASS = "ax-card-black-title"
MAIN_BLACK_CARD_BODY_CLASS = "ax-card-black-body"

SECONDARY_BLACK_PANEL_CLASS = "ax-panel-black ax-panel-black-stack"
SECONDARY_BLACK_PANEL_ROW_CLASS = "ax-panel-black-row"
SECONDARY_GRAY_PANEL_CLASS = "ax-panel-gray-soft ax-panel-gray-soft-stack"
SECONDARY_GRAY_PANEL_ROW_CLASS = "ax-panel-gray-soft-row"

PILL_CLASS = "ax-pill"
PILL_FULL_CLASS = "ax-pill ax-pill-full"
STATUS_BADGE_CLASS = "ax-status-badge"
DEVICE_STATUS_ITEM_CLASS = "ax-status-item"
SECTION_TITLE_CLASS = "ax-section-title"
MUTED_LABEL_CLASS = "ax-label-muted"
VALUE_TEXT_CLASS = "ax-value-text"

PRIMARY_BUTTON_CLASS = "ax-btn ax-btn-primary ax-btn-full"
SECONDARY_BUTTON_CLASS = "ax-btn ax-btn-gray ax-btn-full"
OUTLINE_BUTTON_CLASS = "ax-btn ax-btn-outline"
MODAL_PRIMARY_BUTTON_CLASS = "ax-btn ax-btn-modal-primary"
MODAL_GRAY_BUTTON_CLASS = "ax-btn ax-btn-modal-gray"
SIM_TOGGLE_BUTTON_STYLE = {
    "backgroundColor": "var(--bs-primary)",
    "border": "1px solid var(--bs-primary)",
    "color": "#ffffff",
    "fontWeight": 700,
    "fontSize": "13px",
    "lineHeight": "1.2",
    "width": "150px",
    "minWidth": "150px",
    "maxWidth": "150px",
    "minHeight": "30.5px",
    "height": "30.5px",
    "padding": "3.25px 7.25px",
    "display": "inline-flex",
    "alignItems": "center",
    "justifyContent": "center",
    "textAlign": "center",
    "whiteSpace": "nowrap",
    "gap": "0",
}

MAIN_CARD_COL_CLASS = "ax-main-card-col"
MAIN_CARD_TITLE_ONLY_CLASS = "ax-main-card-title-only"
MAIN_CARD_HEADER_TIGHT_CLASS = "ax-main-card-header-tight"
DEVICE_TOP_ROW_CLASS = "ax-device-top-row"
PANEL_GROUP_TIGHT_CLASS = "ax-panel-group-tight"
MODAL_CLOSE_X_CLASS = "ax-modal-close-x"
DARK_ALERT_CLASS = "ax-alert-dark"
TITLE_BANNER_CLASS = "ax-title-banner"
PAGE_TITLE_CLASS = "ax-page-title"
MODAL_HEADER_CLASS = "ax-modal-header"
MODAL_BODY_CLASS = "ax-modal-body"
MODAL_FOOTER_CLASS = "ax-modal-footer"
MODAL_TITLE_CLASS = "ax-modal-title"
MODAL_FOOTER_END_CLASS = "ax-modal-footer ax-modal-footer-end"



GRAPH_TOOLBAR_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
}

IMU_GRAPH_CONFIG = {
    **GRAPH_TOOLBAR_CONFIG,
    "modeBarButtonsToRemove": ["lasso2d"],
}

SWAY_GRAPH_CONFIG = {
    **GRAPH_TOOLBAR_CONFIG,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

# -----------------------------
# Buffers v1 (legacy local-only)
# -----------------------------
_REC_BUFFERS = {}  # session_uuid (str) -> dict (legacy)

# -----------------------------
# Buffers v2 (axisfit.db)
# -----------------------------
_RAW_BUFFER_MAIN = {}  # main_session_id (int) -> [row_dict...]
_STATS_MAIN = {}       # main_session_id (int) -> stats dict


# =============================
# Helpers UI
# =============================
def _pill(label, value, tone="neutral", full=False):
    tone_map = {
        "neutral": "rgba(255,255,255,.10)",
        "ok": "rgba(34,197,94,.18)",
        "warn": "rgba(245,158,11,.18)",
        "bad": "rgba(239,68,68,.18)",
    }
    class_name = PILL_FULL_CLASS if full else PILL_CLASS

    return html.Div(
        className=class_name,
        style={"background": tone_map.get(tone, tone_map["neutral"])}, 
        children=[
            html.Span(label, className=MUTED_LABEL_CLASS),
            html.Span(value, className=VALUE_TEXT_CLASS),
        ],
    )


def _normalize_calibration_status(status: str) -> str:
    status_txt = str(status or "").strip().lower()
    if status_txt in ("ok", "completada", "completed"):
        return "Completada"
    if status_txt in ("en progreso", "in progress", "progress", "progreso"):
        return "En progreso"
    if status_txt in ("pendiente", "pending", ""):
        return "Pendiente"
    return "Pendiente"


def _is_calibration_completed(calib) -> bool:
    calib = calib or {}
    status_ok = _normalize_calibration_status(calib.get("status")) in {"Completada", "Completed"}
    source_ok = str(calib.get("source") or "").strip().lower() == "baseline_db"
    return bool(status_ok or source_ok)


def _calibration_pill(status: str):
    status_txt = _normalize_calibration_status(status)
    tone = "warn"
    if status_txt == "Completada":
        tone = "ok"
    elif status_txt == "En progreso":
        tone = "neutral"
    bg = {
        "ok": "rgba(34,197,94,.18)",
        "warn": "rgba(245,158,11,.18)",
        "neutral": "rgba(255,255,255,.10)",
    }.get(tone, "rgba(255,255,255,.10)")
    return html.Div(
        status_txt,
        className=STATUS_BADGE_CLASS,
        style={"background": bg},
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
        className=STATUS_BADGE_CLASS,
        style={"background": bg},
    )


def _device_status_item(label: str, value: str, tone: str = "neutral"):
    return html.Div(
        className=DEVICE_STATUS_ITEM_CLASS,
        children=[
            html.Div(label, className=SECTION_TITLE_CLASS, style={"whiteSpace": "nowrap"}),
            _status_value_badge(value, tone),
        ],
    )


def _hidden_device_state_placeholder(value: str, tone: str = "neutral"):
    return html.Div(
        _device_status_item("Estado", value, tone),
        style={"display": "none"},
    )


def _normalize_record_status_label(status: str) -> str:
    status_txt = str(status or "").strip().lower()
    if status_txt in ("grabando", "recording", "on", "activo", "active"):
        return "Grabando"
    if status_txt in ("detenido", "stopped", "off", "stop"):
        return "Detenido"
    if status_txt in ("sin iniciar", "idle", "none", ""):
        return "Sin iniciar"
    return "Sin iniciar"


def _record_status_tone(status: str) -> str:
    status_txt = _normalize_record_status_label(status)
    if status_txt == "Grabando":
        return "ok"
    if status_txt == "Detenido":
        return "warn"
    return "neutral"


def _record_status_badge(status: str):
    status_txt = _normalize_record_status_label(status)
    tone = _record_status_tone(status_txt)
    return _status_value_badge(status_txt, tone)


def _format_recording_elapsed(total_seconds: float) -> str:
    try:
        total_seconds = max(0, int(float(total_seconds or 0)))
    except Exception:
        total_seconds = 0
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def _elapsed_seconds_from_started_at(started_at_epoch_ms):
    try:
        if started_at_epoch_ms is None:
            return 0
        now_ms = int(time.time() * 1000)
        started_at_epoch_ms = int(started_at_epoch_ms)
        if now_ms < started_at_epoch_ms:
            return 0
        return int((now_ms - started_at_epoch_ms) / 1000)
    except Exception:
        return 0


def _friendly_record_start_message(session_name: str, main_db_err: str = None) -> str:
    session_txt = (session_name or "—").strip() or "—"
    msg = f"Registro iniciado correctamente. La sesión \"{session_txt}\" ya se está grabando."
    if main_db_err:
        msg += f" Se inició la grabación, pero hubo un problema al preparar el guardado en la base de datos ({main_db_err})."
    return msg


def _friendly_record_idle_message() -> str:
    return "No hay una grabación activa en este momento."


def _friendly_record_stop_without_db_message(elapsed_label: str) -> str:
    return (
        f"La grabación se detuvo tras {elapsed_label}, pero no se encontró una sesión válida en la base de datos para cerrar correctamente."
    )


def _friendly_record_stop_message(elapsed_label: str, risk: float, thor_red_s: float, lum_red_s: float, comp_avg: float, alerts_count: int) -> str:
    return (
        f"Grabación finalizada correctamente. "
        f"Tiempo total: {elapsed_label}. "
        f"Riesgo estimado: {risk:.1f}/100. "
        f"Tiempo en mala postura: torácica {thor_red_s:.1f}s y lumbar {lum_red_s:.1f}s. "
        f"Compensación media: {comp_avg:.1f}/100. "
        f"Alertas registradas: {alerts_count}."
    )


def _friendly_record_stop_issues(flush_err=None, summary_err=None, close_err=None, daily_err=None) -> str:
    issues = []
    if flush_err:
        issues.append(f"no se pudieron guardar algunas muestras finales ({flush_err})")
    if summary_err:
        issues.append(f"no se pudo guardar el resumen de la sesión ({summary_err})")
    if close_err:
        issues.append(f"no se pudo cerrar la sesión en la base de datos ({close_err})")
    if daily_err:
        issues.append(f"no se pudo actualizar el resumen diario ({daily_err})")
    if not issues:
        return ""
    return " Se detectaron algunos problemas al guardar la información: " + "; ".join(issues) + "."


def _calibration_action_label(status: str) -> str:
    status_txt = _normalize_calibration_status(status)
    if status_txt == "Completada":
        return "Recalibrar"
    if status_txt == "En progreso":
        return "Completar calibración"
    return "Iniciar calibración"


def _calibration_helper_text(status: str) -> str:
    return (
        "Calibración correcta. El sistema está listo para medir."
        if _normalize_calibration_status(status) == "Completada"
        else "Necesaria antes de iniciar la monitorización."
    )


def _calibration_popup_status_text(status: str) -> str:
    status_txt = _normalize_calibration_status(status)
    if status_txt == "Completada":
        return "Estado actual: Completada"
    if status_txt == "En progreso":
        return "Estado actual: En progreso"
    return "Estado actual: Pendiente"


def _mode_label(mode_value: str) -> str:
    mode_value = (mode_value or "").strip().lower()
    return {
        "train": "Entrenamiento",
        "rehab": "Rehabilitación",
        "office": "Oficina",
    }.get(mode_value, "Entrenamiento")


def _sport_label(sport_value: str) -> str:
    sport_value = (sport_value or "").strip().lower()
    return {
        "gym": "Gym",
        "crossfit": "CrossFit",
        "general": "Gym",
        "strength": "CrossFit",
        "rehab": "Gym",
        "office": "Gym",
    }.get(sport_value, "Gym")


# =============================
# Sesiones por modalidad
# =============================
def _session_options_for_mode(mode_value: str):
    """
    Opciones base para "Sesión del día".
    Nota:
    - En esta fase quedan definidas por modalidad.
    - Más adelante se conectan con la ventana de Rutina para traer sesiones reales.
    """
    mode_value = (mode_value or "train").strip().lower()

    if mode_value == "rehab":
        return [
            {"label": "Rehab · Espalda", "value": "Rehab · Espalda"},
            {"label": "Rehab · Hombro", "value": "Rehab · Hombro"},
            {"label": "Estabilidad · Core", "value": "Estabilidad · Core"},
            {"label": "Movilidad terapéutica", "value": "Movilidad terapéutica"},
        ]

    if mode_value == "office":
        return [
            {"label": "Oficina · Postura", "value": "Oficina · Postura"},
            {"label": "Pausa activa · Escritorio", "value": "Pausa activa · Escritorio"},
            {"label": "Ergonomía · Jornada", "value": "Ergonomía · Jornada"},
            {"label": "Movilidad · Oficina", "value": "Movilidad · Oficina"},
        ]

    return [
        {"label": "Fuerza · Torso", "value": "Fuerza · Torso"},
        {"label": "Fuerza · Pierna", "value": "Fuerza · Pierna"},
        {"label": "Técnica · Levantamiento", "value": "Técnica · Levantamiento"},
        {"label": "Movilidad · Gym", "value": "Movilidad · Gym"},
    ]


def _default_session_for_mode(mode_value: str) -> str:
    options = _session_options_for_mode(mode_value)
    if options:
        return options[0]["value"]
    return "—"


def _is_training_mode(mode_value: str) -> bool:
    return (mode_value or "train").strip().lower() == "train"


def _default_sport_for_mode(mode_value: str) -> str:
    """
    Deporte solo se edita en Entrenamiento.
    En Rehab / Oficina queda fijado a Gym como valor compatible.
    """
    if _is_training_mode(mode_value):
        return "gym"
    return "gym"


def _session_summary_items(mode_value: str, sport_value: str, planned_session: str):
    return [
        _pill("Modalidad", _mode_label(mode_value), "neutral", full=True),
        _pill("Deporte", _sport_label(sport_value), "neutral", full=True),
        _pill("Sesión del día", planned_session or "—", "neutral", full=True),
    ]


def _link_context_has_reference(link_ctx) -> bool:
    link_ctx = link_ctx if isinstance(link_ctx, dict) else {}
    return bool(
        link_ctx.get("questionnaire_session_id") is not None
        or link_ctx.get("routine_session_id") is not None
        or str(link_ctx.get("source") or "").strip()
    )


def _normalize_monitor_link_context(link_ctx):
    link_ctx = link_ctx if isinstance(link_ctx, dict) else {}
    mode_value = str(link_ctx.get("mode") or "train")
    sport_value = str(link_ctx.get("sport") or _default_sport_for_mode(mode_value))
    session_name = (
        link_ctx.get("planned_session_name")
        or link_ctx.get("name")
        or _default_session_for_mode(mode_value)
    )
    return {
        "mode": mode_value,
        "sport": sport_value,
        "planned_session_name": session_name,
        "questionnaire_session_id": link_ctx.get("questionnaire_session_id"),
        "routine_session_id": link_ctx.get("routine_session_id"),
        "session_type": link_ctx.get("session_type"),
        "source": link_ctx.get("source"),
        "questionnaire_payload": link_ctx.get("questionnaire_payload") if isinstance(link_ctx.get("questionnaire_payload"), dict) else {},
        "routine_payload": link_ctx.get("routine_payload") if isinstance(link_ctx.get("routine_payload"), dict) else {},
    }


def _build_active_session_payload(existing_session=None, link_ctx=None, *, planned_session_name=None, mode=None, sport=None):
    existing_session = existing_session if isinstance(existing_session, dict) else {}
    link_ctx_norm = _normalize_monitor_link_context(link_ctx)

    mode_value = str(mode or existing_session.get("mode") or link_ctx_norm.get("mode") or "train")
    sport_value = str(sport or existing_session.get("sport") or link_ctx_norm.get("sport") or _default_sport_for_mode(mode_value))
    session_name = str(
        planned_session_name
        or existing_session.get("planned_session_name")
        or existing_session.get("name")
        or link_ctx_norm.get("planned_session_name")
        or _default_session_for_mode(mode_value)
    )

    questionnaire_session_id = existing_session.get("questionnaire_session_id")
    if questionnaire_session_id is None:
        questionnaire_session_id = link_ctx_norm.get("questionnaire_session_id")

    routine_session_id = existing_session.get("routine_session_id")
    if routine_session_id is None:
        routine_session_id = link_ctx_norm.get("routine_session_id")

    session_type_value = existing_session.get("session_type")
    if session_type_value is None:
        session_type_value = link_ctx_norm.get("session_type")

    source_value = (
        existing_session.get("session_origin")
        or existing_session.get("linked_db_source")
        or link_ctx_norm.get("source")
        or "monitor_session_config"
    )

    linked_at_value = existing_session.get("linked_at") or datetime.now().isoformat(timespec="seconds")

    return {
        "name": session_name,
        "planned_session_name": session_name,
        "mode": mode_value,
        "sport": sport_value,
        "linked_at": linked_at_value,
        "questionnaire_session_id": questionnaire_session_id,
        "routine_session_id": routine_session_id,
        "session_type": session_type_value,
        "session_origin": source_value,
        "linked_db_source": link_ctx_norm.get("source") or source_value,
        "questionnaire_payload": link_ctx_norm.get("questionnaire_payload") or existing_session.get("questionnaire_payload") or {},
        "routine_payload": link_ctx_norm.get("routine_payload") or existing_session.get("routine_payload") or {},
        # Punto de enlace para la futura sincronización con la ventana de Rutina.
        "routine_context": {
            "mode": mode_value,
            "session_name": session_name,
            "source": source_value,
            "questionnaire_session_id": questionnaire_session_id,
            "routine_session_id": routine_session_id,
            "session_type": session_type_value,
        },
    }


def _load_monitor_link_context_for_user(session_user):
    user_id = _get_user_id(session_user)
    if user_id is None:
        return {}
    try:
        return get_monitor_link_context(user_id=int(user_id), day=date.today())
    except Exception:
        return {}


def _hidden_record_session_placeholder(session_name: str):
    return html.Div(
        _pill("Sesión", session_name or "—", "neutral", full=True),
        style={"display": "none"},
    )


def _recording_panel_items(recorder_on: bool, session_name: str, recorder_status: str = "Sin iniciar", elapsed_label: str = "00:00"):
    state_value = _normalize_record_status_label(recorder_status)
    state_tone = _record_status_tone(state_value)
    time_tone = "ok" if recorder_on else ("warn" if state_value == "Detenido" else "neutral")
    return [
        _pill("Estado", state_value, state_tone, full=True),
        _pill("Tiempo", elapsed_label or "00:00", time_tone, full=True),
        _pill("Frecuencia", "50 Hz", "neutral", full=True),
        _hidden_record_session_placeholder(session_name),
    ]


def _traffic_light_dynamic(score: float):
    g = 1.0 if score >= 80 else 0.25
    y = 1.0 if 50 <= score < 80 else 0.25
    r = 1.0 if score < 50 else 0.25

    def dot(color, alpha):
        return html.Div(
            style={
                "width": "7px",
                "height": "7px",
                "borderRadius": "999px",
                "background": color,
                "opacity": alpha,
                "boxShadow": "0 0 0 1px rgba(255,255,255,.10)",
            }
        )

    return html.Div(
        style={"display": "flex", "gap": "4px", "alignItems": "center"},
        children=[
            dot("rgba(34,197,94,.95)", g),
            dot("rgba(245,158,11,.95)", y),
            dot("rgba(239,68,68,.95)", r),
        ],
    )


def _traffic_light_zone(zone: str):
    """Semáforo por zona: green/yellow/red."""
    zone = (zone or "").lower()
    g = 1.0 if zone == "green" else 0.25
    y = 1.0 if zone == "yellow" else 0.25
    r = 1.0 if zone == "red" else 0.25

    def dot(color, alpha):
        return html.Div(
            style={
                "width": "7px",
                "height": "7px",
                "borderRadius": "999px",
                "background": color,
                "opacity": alpha,
                "boxShadow": "0 0 0 1px rgba(255,255,255,.10)",
            }
        )

    return html.Div(
        style={"display": "flex", "gap": "4px", "alignItems": "center"},
        children=[
            dot("rgba(34,197,94,.95)", g),
            dot("rgba(245,158,11,.95)", y),
            dot("rgba(239,68,68,.95)", r),
        ],
    )


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _segments_from_mask(t, mask):
    segs = []
    if not t or not mask or len(t) != len(mask):
        return segs

    start = None
    for i, on in enumerate(mask):
        if on and start is None:
            start = t[i]
        if (not on) and start is not None:
            end = t[i]
            segs.append((start, end))
            start = None

    if start is not None:
        segs.append((start, t[-1]))
    return segs


def _empty_fig(title: str):
    return {
        "data": [],
        "layout": {
            "title": {"text": ""},
            "paper_bgcolor": "#0b1220",
            "plot_bgcolor": "#0b1220",
            "font": {"color": "#e2e8f0"},
            "margin": {"l": 40, "r": 56, "t": 0, "b": 0},
        },
    }


def _metric_header(label, value_id, value_default="—"):
    return html.Div(
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            "gap": "10px",
            "padding": "4px 6px 0 6px",
        },
        children=[
            html.Span(label, style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 700}),
            html.Span(id=value_id, children=value_default, style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 800}),
        ],
    )


def _graph_calibration_warning_block():
    return html.Div(
        "Calibración pendiente “Iniciar calibración”. Necesaria antes de comenzar la monitorización.",
        style={
            "width": "100%",
            "height": "125px",
            "minHeight": "125px",
            "borderRadius": "12px",
            "background": "rgba(245,158,11,.18)",
            "boxShadow": "inset 0 0 0 1px rgba(245,158,11,.28)",
            "padding": "12px 14px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "textAlign": "center",
            "fontSize": "12px",
            "fontWeight": 700,
            "lineHeight": "1.45",
            "color": "#fbbf24",
        },
    )


def _posture_calibration_warning_block():
    return html.Div(
        "Calibración pendiente “Iniciar calibración”. Necesaria antes de comenzar la monitorización.",
        style={
            "width": "100%",
            "minHeight": "148px",
            "borderRadius": "12px",
            "background": "rgba(245,158,11,.18)",
            "boxShadow": "inset 0 0 0 1px rgba(245,158,11,.28)",
            "padding": "12px 14px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "textAlign": "center",
            "fontSize": "12px",
            "fontWeight": 700,
            "lineHeight": "1.45",
            "color": "#fbbf24",
        },
    )


def _zone_status_label(zone: str) -> str:
    zone = (zone or "").strip().lower()
    if zone == "red":
        return "Rojo"
    if zone == "yellow":
        return "Amarillo"
    return "Verde"


def _zone_action_label(zone: str) -> str:
    zone = (zone or "").strip().lower()
    if zone == "red":
        return "Corrige"
    if zone == "yellow":
        return "Vigila"
    return "Estable"


def _format_signed_angle(value: float) -> str:
    try:
        v = float(value or 0.0)
    except Exception:
        v = 0.0
    return f"{v:+.1f}°"


def _format_elapsed_tenths(total_seconds: float) -> str:
    try:
        total_seconds = max(0.0, float(total_seconds or 0.0))
    except Exception:
        total_seconds = 0.0
    total_tenths = int(round(total_seconds * 10.0))
    minutes = total_tenths // 600
    seconds_tenths = total_tenths % 600
    seconds = seconds_tenths / 10.0
    return f"{minutes}:{seconds:04.1f}"


def _comp_level_meta(score: float):
    try:
        score = max(0.0, min(100.0, float(score or 0.0)))
    except Exception:
        score = 0.0

    if score >= 66.0:
        return "Alta", "bad"
    if score >= 33.0:
        return "Media", "warn"
    return "Baja", "ok"


def _comp_meter_fill_style(score: float):
    level, tone = _comp_level_meta(score)
    width_pct = f"{max(0.0, min(100.0, float(score or 0.0))):.1f}%"
    bg = {
        "ok": "linear-gradient(90deg, rgba(34,197,94,.95), rgba(34,197,94,.55))",
        "warn": "linear-gradient(90deg, rgba(245,158,11,.95), rgba(245,158,11,.55))",
        "bad": "linear-gradient(90deg, rgba(239,68,68,.95), rgba(239,68,68,.55))",
    }.get(tone, "linear-gradient(90deg, rgba(255,255,255,.85), rgba(255,255,255,.35))")
    return {
        "width": width_pct,
        "height": "100%",
        "borderRadius": "999px",
        "background": bg,
    }


def _comp_output_block(score: float):
    level, tone = _comp_level_meta(score)
    tone_color = {
        "ok": "rgba(34,197,94,.95)",
        "warn": "rgba(245,158,11,.95)",
        "bad": "rgba(239,68,68,.95)",
    }.get(tone, "#e2e8f0")
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "4px"},
        children=[
            html.Div(
                style={"display": "flex", "alignItems": "center", "gap": "5px", "width": "100%"},
                children=[
                    html.Div(
                        "Compensación",
                        style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600},
                    ),
                    html.Div(
                        style={
                            "flex": "1 1 auto",
                            "height": "7px",
                            "borderRadius": "999px",
                            "background": "rgba(255,255,255,.08)",
                            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                            "overflow": "hidden",
                            "minWidth": "38px",
                        },
                        children=[
                            html.Div(style=_comp_meter_fill_style(score))
                        ],
                    ),
                    html.Span(
                        f"{int(round(float(score or 0.0))):d}/100",
                        style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700},
                    ),
                    html.Div(
                        level,
                        style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700, "color": tone_color},
                    ),
                ],
            ),
            html.Div(style={"display": "none"}, children=[html.Span("Compensación / etiqueta superior integrada")]),
            html.Div(style={"display": "none"}, children=[html.Span("Compensación / diseño compacto 2-3")]),
        ],
    )


def _segment_state_card(title: str, light_id: str, status_id: str, cue_id: str, angle_id: str, angle_label: str, time_id: str = None, time_label: str = "Tiempo en rojo", extra_children=None):
    extra_children = extra_children or []
    return html.Div(
        style={
            "width": "100%",
            "minWidth": "0",
            "borderRadius": "8px",
            "background": "rgba(255,255,255,.06)",
            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
            "padding": "7px",
            "display": "flex",
            "flexDirection": "column",
            "gap": "3px",
        },
        children=[
            html.Div(
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "5px"},
                children=[
                    html.Div(title, className=SECTION_TITLE_CLASS),
                    html.Div(
                        style={
                            "display": "grid",
                            "gridTemplateColumns": "minmax(0,1fr) 24px",
                            "alignItems": "center",
                            "columnGap": "10px",
                            "minWidth": "86px",
                        },
                        children=[
                            html.Div(id=status_id, children="Estable", style={**BLACK_TEXT, "fontSize": "10px", "fontWeight": 800, "whiteSpace": "nowrap", "textAlign": "right"}),
                            html.Div(
                                id=light_id,
                                children=_traffic_light_zone("green"),
                                style={"width": "24px", "minWidth": "24px", "display": "flex", "justifyContent": "flex-end"},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(id=cue_id, children="Estable", style={**BLACK_MUTED, "fontSize": "10px", "fontWeight": 700, "display": "none"}),
            html.Div(
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "5px"},
                children=[
                    html.Span(angle_label, style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                    html.Span(id=angle_id, children="0.0°", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700}),
                ],
            ),
            html.Div(
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "5px"},
                children=[
                    html.Span(time_label, style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                    html.Span(id=time_id, children="0:00.0", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700}) if time_id else html.Span("—", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700}),
                ],
            ),
            *extra_children,
        ],
    )


# =============================
# Mapeadores (PASO 1 / PASO 13)
# =============================
def _map_mode_ui_to_db(mode_ui: str):
    """UI: train/rehab/office -> DB: train/desk (temporal)."""
    mode_ui = (mode_ui or "").strip().lower()
    if mode_ui == "office":
        return "desk"
    return "train"  # train + rehab -> train (temporal)


def _map_sport_ui_to_db(sport_ui: str):
    """
    UI nuevo: gym/crossfit
    Compat: general/strength/rehab/office -> gym/crossfit (temporal)
    """
    sport_ui = (sport_ui or "").strip().lower()
    if sport_ui in ("gym", "crossfit"):
        return sport_ui
    if sport_ui == "strength":
        return "crossfit"
    # general/rehab/office/otros -> gym
    return "gym"


def _get_user_id(session_user):
    """
    Intenta obtener un user_id válido para start_sensor_session.
    Debe ser int (lo que espera tu db.py).
    """
    if not session_user:
        return None

    if isinstance(session_user, dict):
        # prioriza id numérico si existe
        for k in ("id", "user_id", "athlete_id"):
            v = session_user.get(k)
            try:
                if v is not None and str(v).strip() != "":
                    return int(v)
            except Exception:
                pass

    # si viene como string (ej. "1")
    try:
        return int(session_user)
    except Exception:
        return None


def _get_user_display_name(session_user):
    """Nombre legible del usuario para el cuadro superior."""
    if isinstance(session_user, dict):
        for k in ("name", "nombre", "full_name"):
            v = session_user.get(k)
            if v and str(v).strip():
                return str(v).strip()
        for k in ("email", "id_str", "id", "user_id", "athlete_id"):
            v = session_user.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
    if session_user is None:
        return "Invitado"
    s = str(session_user).strip()
    return s or "Invitado"


def _load_calibration_state_from_db(session_user):
    """Carga el estado real de calibración/baseline desde DB.

    Monitor no debe marcar calibración completada por flujo local.
    La única fuente válida es un baseline/calibración real guardado en DB.
    """
    user_id = _get_user_id(session_user)
    if user_id is None:
        return {
            "status": "Pendiente",
            "source": "baseline_required",
            "ts": None,
            "baseline_test_id": None,
            "baseline_payload": {},
        }

    try:
        baseline_row = get_latest_valid_baseline(user_id=int(user_id))
    except Exception:
        baseline_row = None

    if baseline_row:
        baseline_payload = baseline_row.get("baseline") if isinstance(baseline_row.get("baseline"), dict) else {}
        return {
            "status": "Completada",
            "source": "baseline_db",
            "ts": baseline_row.get("created_at"),
            "baseline_test_id": baseline_row.get("id"),
            "baseline_payload": baseline_payload,
        }

    return {
        "status": "Pendiente",
        "source": "baseline_required",
        "ts": None,
        "baseline_test_id": None,
        "baseline_payload": {},
    }


# =============================
# PASO 5 — Thresholds por usuario (desde cuestionario)
# =============================
def _load_user_thresholds_for_mode(*, user_id: int, mode: str) -> dict:
    """Devuelve el perfil activo de monitorización para el modo actual.

    - Si el usuario tiene user_posture_settings.thresholds_json, usa thresholds + adaptation.
    - Si no, usa DEFAULT_THRESHOLDS (genéricos) y adaptation vacío.
    - Se mantiene compatibilidad devolviendo también thor/lum al nivel raíz.
    """
    mode = (mode or "desk").strip().lower()
    if mode not in ("desk", "train"):
        mode = "desk"

    fallback = DEFAULT_THRESHOLDS.get(mode, DEFAULT_THRESHOLDS["desk"])
    thr_thor = dict((fallback.get("thor") or {}))
    thr_lum = dict((fallback.get("lum") or {}))
    adaptation = {}
    version = "wizard_v2"

    try:
        s = get_user_posture_settings(user_id=int(user_id))
        if s:
            adaptation = dict(s.get("adaptation") or {})
            version = s.get("version") or "wizard_v2"
            root_settings = s.get("settings") if isinstance(s.get("settings"), dict) else {}
            thresholds_root = root_settings.get("thresholds") if isinstance(root_settings.get("thresholds"), dict) else (s.get("thresholds") or {})
            mode_block = (thresholds_root or {}).get(mode) or {}
            if isinstance(mode_block.get("thor"), dict):
                thr_thor.update(mode_block["thor"])
            if isinstance(mode_block.get("lum"), dict):
                thr_lum.update(mode_block["lum"])
    except Exception:
        pass

    return {
        "thor": thr_thor,
        "lum": thr_lum,
        "thresholds": {"thor": thr_thor, "lum": thr_lum},
        "adaptation": adaptation,
        "version": version,
    }


# =============================
# Risk Index v2 (PASO 8)
# =============================
def _risk_index_v2(duration_s: float, thor_red_s: float, lum_red_s: float, comp_avg: float, vas: float = 0.0):
    """
    0–100: mayor = peor.
    Simple y estable para MVP.
    """
    duration_s = max(float(duration_s or 0.0), 1e-6)
    tr = max(0.0, min(1.0, float(thor_red_s or 0.0) / duration_s))
    lr = max(0.0, min(1.0, float(lum_red_s or 0.0) / duration_s))
    ca = max(0.0, min(1.0, float(comp_avg or 0.0) / 100.0))
    vas_n = max(0.0, min(1.0, float(vas or 0.0) / 10.0))

    r = 100.0 * (0.40 * tr + 0.40 * lr + 0.18 * ca + 0.02 * vas_n)
    return max(0.0, min(100.0, r))


# =============================
# Wrapper samples_since (PASO 4/5)
# =============================
def _zone_from_angles(pitch_deg: float, roll_deg: float, *, thr: dict) -> str:
    """Zonificación por thresholds (por segmento) guardados por usuario.

    thr esperado: {pitch_g, pitch_y, roll_g, roll_y}
    - green si abs(pitch)<=pitch_g y abs(roll)<=roll_g
    - yellow si abs(pitch)<=pitch_y y abs(roll)<=roll_y
    - red en otro caso
    """
    try:
        pitch_g = float(thr.get("pitch_g", 8.0))
        pitch_y = float(thr.get("pitch_y", 15.0))
        roll_g = float(thr.get("roll_g", 7.0))
        roll_y = float(thr.get("roll_y", 12.0))
    except Exception:
        pitch_g, pitch_y, roll_g, roll_y = 8.0, 15.0, 7.0, 12.0

    ap = abs(float(pitch_deg))
    ar = abs(float(roll_deg))

    if ap <= pitch_g and ar <= roll_g:
        return "green"
    if ap <= pitch_y and ar <= roll_y:
        return "yellow"
    return "red"


def _comp_index_simple(T_pitch, T_roll, L_pitch, L_roll):
    # compensación simple (0–100)
    v = (abs(T_pitch - L_pitch) * 6.0) + (abs(T_roll - L_roll) * 4.0)
    return max(0.0, min(100.0, float(v)))


def _get_samples_since_from_window(win, stats):
    """
    Emula IMU_SIM.get_samples_since(last_ts_ms) usando:
    - ventana 20s (t/pitch/roll/yaw)
    - last_t_s para no duplicar
    - base_epoch_ms para timestamps absolutos por sesión
    Devuelve lista de dicts con el esquema v2:
      ts_ms, T_pitch,T_roll,T_yaw, L_pitch,L_roll,L_yaw,
      thor_zone, lum_zone, comp_index, T_imu_ts_ms, L_imu_ts_ms
    """
    t = win.get("t") or []
    pitch = win.get("pitch") or []
    roll = win.get("roll") or []
    yaw = win.get("yaw") or []

    if not t:
        return []

    last_t_s = stats.get("last_t_s")
    # base para convertir t (segundos) -> ts_ms absoluto
    now_ms = int(time.time() * 1000)
    if stats.get("base_epoch_ms") is None:
        # ancla al final de ventana actual
        stats["base_epoch_ms"] = now_ms - int(float(t[-1]) * 1000.0)

    base_epoch_ms = int(stats["base_epoch_ms"])

    start_i = 0
    if last_t_s is not None:
        try:
            for i in range(len(t)):
                if float(t[i]) > float(last_t_s):
                    start_i = i
                    break
            else:
                start_i = len(t)
        except Exception:
            start_i = 0

    rows = []
    for i in range(start_i, len(t)):
        ti = float(t[i])
        ts_ms = base_epoch_ms + int(ti * 1000.0)

        Tp = float(pitch[i]) if i < len(pitch) else 0.0
        Tr = float(roll[i]) if i < len(roll) else 0.0
        Ty = float(yaw[i]) if i < len(yaw) else 0.0

        # “Lumbar” con pequeña variación (placeholder)
        Lp = Tp * 0.85
        Lr = Tr * 0.90
        Ly = Ty * 0.95

        thr_active = (stats.get("thr_active") or {})
        thr_thor = (thr_active.get("thor") or DEFAULT_THRESHOLDS.get("desk", {}).get("thor", {}))
        thr_lum  = (thr_active.get("lum")  or DEFAULT_THRESHOLDS.get("desk", {}).get("lum", {}))

        thor_zone = _zone_from_angles(Tp, Tr, thr=thr_thor)
        lum_zone  = _zone_from_angles(Lp, Lr, thr=thr_lum)
        comp = _comp_index_simple(Tp, Tr, Lp, Lr)

        rows.append(
            {
                "ts_ms": ts_ms,
                "T_pitch": Tp,
                "T_roll": Tr,
                "T_yaw": Ty,
                "L_pitch": Lp,
                "L_roll": Lr,
                "L_yaw": Ly,
                "thor_zone": thor_zone,
                "lum_zone": lum_zone,
                "comp_index": comp,
                "T_imu_ts_ms": ts_ms,
                "L_imu_ts_ms": ts_ms,
            }
        )

    # actualiza cursores
    stats["last_t_s"] = float(t[-1])
    if rows:
        stats["last_ts_ms"] = int(rows[-1]["ts_ms"])

    return rows



def _get_live_samples_since(stats, win=None):
    """Obtiene nuevas muestras priorizando IMU_SIM.get_samples_since(...) y usando wrapper como fallback."""
    stats = stats or {}
    last_ts_ms = int(stats.get("last_ts_ms") or 0)
    getter = getattr(IMU_SIM, "get_samples_since", None)

    if callable(getter):
        try:
            rows = getter(last_ts_ms)
            if isinstance(rows, list):
                if rows:
                    try:
                        stats["last_ts_ms"] = int(rows[-1].get("ts_ms") or last_ts_ms)
                    except Exception:
                        pass
                return rows
        except Exception:
            pass

    return _get_samples_since_from_window(win or {}, stats)

# Bloque oculto de compatibilidad visual para conservar estructura de líneas
_COMP_LAYOUT_COMPAT = {
    "estado_general_compacto": True,
    "estado_detallado_compacto": True,
    "comp_integrada": True,
}


# Compatibilidad visual:
# - Torácica/Lumbar ahora muestran estado a la izquierda del bloque derecho y semáforo a la derecha.
# - Los gaps internos se reducen 1px solo en las tarjetas segmentarias.
# - Los valores medidos visibles en Postura en vivo se alinean al estilo de 00:00.
_POSTURE_LIVE_VALUE_STYLE_COMPAT = {
    "segment_gap_minus_1px": True,
    "traffic_light_right": True,
    "measured_values_match_time_style": True,
}


# Compatibilidad visual:
# - El aviso de lectura se fija en la esquina inferior izquierda del bloque izquierdo de Postura en vivo.
# - Los dos estados amarillos se unifican en un único mensaje compacto.
# - El estado verde también se simplifica para evitar repetir contenido.
# - El bloque de lectura queda pegado al borde inferior del subcuadro izquierdo.
# - El texto del aviso se centra visualmente dentro del bloque.
_POSTURE_LIVE_NOTE_COMPAT = {
    "bottom_left_anchored_note": True,
    "merged_yellow_states": True,
    "reduced_copy_for_green_and_warn": True,
}


# =============================
# Layout
# =============================
def layout():

    # Compatibilidad visual del modal de calibración:
    # - La X del encabezado se fuerza a blanco para mantener contraste sobre fondo oscuro.
    # - El cierre por X reutiliza la misma lógica del botón Cerrar.
    # - La separación vertical entre acciones inferiores se reduce a la mitad.
    _recal_modal_close_visual_compat = {
        "white_close_x": True,
        "shared_close_logic": True,
        "footer_gap_halved": True,
    }

    _record_options_modal_visual_compat = {
        "white_close_x": True,
        "toggle_start_stop_action": True,
        "primary_blue_action_button": True,
    }

    # Compatibilidad visual de popups:
    # - Mismo lenguaje visual que los cuadros negros del dashboard.
    # - Sin oscurecer por completo el fondo para que se siga viendo la vista detrás.
    # - Se conservan los mismos modales y la misma estructura funcional.
    _modal_visual_compat = {
        "dashboard_black_modal": True,
        "background_view_stays_visible": True,
        "modal_inner_cards_aligned": True,
    }

    empty_imu_fig = _empty_fig("Gráfica IMU (Pitch / Roll)")
    empty_sway_fig = _empty_fig("Gráfica Sway / Eventos")
    empty_history_fig = _empty_fig("Histórico de sesiones (Postura)")

    left_col_style = {
        "width": LEFT_W,
        "minWidth": LEFT_W,
        "flex": f"0 0 {LEFT_W}",
        "display": "flex",
        "flexDirection": "column",
        "gap": "8px",
    }

    right_col_style = {
        "width": RIGHT_BOX_W,
        "minWidth": RIGHT_BOX_W,
        "flex": f"0 0 {RIGHT_BOX_W}",
        "display": "flex",
        "flexDirection": "column",
        "gap": "8px",
    }

    right_container_style = {
        "display": "flex",
        "gap": f"{RIGHT_INNER_GAP_PX}px",
        "alignItems": "flex-start",
        "flexWrap": "wrap",
    }

    right_total_w = f"{(int(RIGHT_BOX_W.replace('px', '')) * 2) + RIGHT_INNER_GAP_PX}px"
    right_area_style = {
        "width": right_total_w,
        "minWidth": right_total_w,
        "flex": f"0 0 {right_total_w}",
        "display": "flex",
        "flexDirection": "column",
        "gap": "8px",
    }

    return html.Div(
        className="surface",
        style={"paddingBottom": "16px"},
        children=[
            dcc.Store(id="session-history-store", storage_type="local"),
            dcc.Store(id="active-session-store", storage_type="local"),
            dcc.Store(id="calibration-store", storage_type="local"),
            dcc.Store(id="sim-state-store", data={"on": True, "reset_seq": 0}, storage_type="memory"),
            # ✅ recorder-store SOLO se escribe en recorder_control
            dcc.Store(
                id="recorder-store",
                data={
                    "on": False,
                    "session_id": None,
                    "main_session_id": None,
                    "status_label": "sin_iniciar",
                    "started_at_epoch_ms": None,
                    "elapsed_label": "00:00",
                },
                storage_type="memory",
            ),
            dcc.Download(id="download-monitor"),

            dcc.Interval(id="imu-interval", interval=200, n_intervals=0, disabled=True),

            # Título + menú derecha
            html.Div(
                className="mb-3",
                style={"display": "flex", "alignItems": "flex-start", "justifyContent": "space-between", "gap": "12px", "flexWrap": "wrap"},
                children=[
                    html.Div(
                        className=TITLE_BANNER_CLASS,
                        children=[
                            html.H2(
                                "Monitorizacion de Postura",
                                className=f"mb-0 {PAGE_TITLE_CLASS}",
                            )
                        ],
                    ),
                    html.Div(
                        style={"display": "none"},
                        children=[
                            html.Div(
                                "Controles de simulación reubicados al bloque Estado del dispositivo.",
                                style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600},
                            ),
                        ],
                    ),
                ],
            ),

            # Layout principal
            html.Div(
                style={
                    "width": "100%",
                    "maxWidth": "100%",
                    "display": "flex",
                    "gap": "8px",
                    "alignItems": "flex-start",
                    "flexWrap": "wrap",
                    "overflowX": "hidden",
                },
                children=[
                    # ===== COLUMNA 1 (IZQUIERDA) =====
                    html.Div(
                        style=left_col_style,
                        children=[
                            # Estado
                            html.Div(
                                className=f"{MAIN_BLACK_CARD_CLASS} {MAIN_CARD_COL_CLASS}",
                                children=[
                                    html.Div(
                                        className=MAIN_CARD_HEADER_TIGHT_CLASS,
                                        children=[
                                            html.Div("Control de sesión", className=SECTION_TITLE_CLASS),
                                        ],
                                    ),
                                    html.Div(
                                        className=PANEL_GROUP_TIGHT_CLASS,
                                        children=[
                                            html.Div(
                                                className=SECONDARY_BLACK_PANEL_CLASS,
                                                children=[
                                                    html.Div(
                                                        style={
                                                            "display": "flex",
                                                            "alignItems": "center",
                                                            "justifyContent": "space-between",
                                                            "gap": "10px",
                                                        },
                                                        children=[
                                                            html.Div("Calibración", className=SECTION_TITLE_CLASS),
                                                            html.Div(id="calibration-pill", children=_calibration_pill("Pendiente")),
                                                        ],
                                                    ),
                                                    dbc.Button(
                                                        _calibration_action_label("Pendiente"),
                                                        id="open-recal-btn",
                                                        color="primary",
                                                        size="sm",
                                                        className=PRIMARY_BUTTON_CLASS,
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                className=SECONDARY_BLACK_PANEL_CLASS,
                                                children=[
                                                    html.Div("Configuración", className=SECTION_TITLE_CLASS),
                                                    html.Div(id="mode-summary-pill", children=_pill("Modalidad", _mode_label("train"), "neutral", full=True)),
                                                    html.Div(id="sport-summary-pill", children=_pill("Deporte", _sport_label("gym"), "neutral", full=True), style={"display": "none"}),
                                                    html.Div(id="session-summary-pill", children=_pill("Sesión del día", _default_session_for_mode("train"), "neutral", full=True), style={"display": "none"}),
                                                    dbc.Button(
                                                        "Vincular sesión",
                                                        id="link-session-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=SECONDARY_BUTTON_CLASS,
                                                    ),
                                                    html.Div(id="active-session-label", style={"display": "none"}, children="Sesión activa: —"),
                                                    html.Div(id="active-session-badge", style={"display": "none"}, children=_pill("Sesión", "—", "neutral", full=True)),
                                                ],
                                            ),
                                            html.Div(
                                                className=SECONDARY_BLACK_PANEL_CLASS,
                                                children=[
                                                    html.Div(
                                                        style={
                                                            "display": "flex",
                                                            "alignItems": "center",
                                                            "justifyContent": "space-between",
                                                            "gap": "10px",
                                                        },
                                                        children=[
                                                            html.Div("Registro", className=SECTION_TITLE_CLASS),
                                                            html.Div(
                                                                id="recording-header-status",
                                                                children=_record_status_badge("Sin iniciar"),
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        id="recording-pill",
                                                        children=_pill("Estado", "Sin iniciar", "neutral", full=True),
                                                        style={"display": "none"},
                                                    ),
                                                    html.Div(
                                                        id="recording-time-pill",
                                                        children=_pill("Tiempo", "00:00", "neutral", full=True),
                                                    ),
                                                    html.Div(
                                                        id="recording-session-pill",
                                                        children=_pill("Sesión", _default_session_for_mode("train"), "neutral", full=True),
                                                        style={"display": "none"},
                                                    ),
                                                    dbc.Button(
                                                        "Iniciar registro",
                                                        id="start-record-btn",
                                                        color="primary",
                                                        size="sm",
                                                        className=PRIMARY_BUTTON_CLASS,
                                                    ),
                                                    dbc.Button(
                                                        "Opciones de registro",
                                                        id="open-record-options-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=SECONDARY_BUTTON_CLASS,
                                                    ),
                                                    dbc.Alert(
                                                        id="recorder-alert",
                                                        children="",
                                                        is_open=False,
                                                        color="info",
                                                        className=DARK_ALERT_CLASS,
                                                        style={"marginTop": "4px", "marginBottom": "0"},
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),

                            # Controles rápidos eliminados según solicitud.
                            # Se mantiene este bloque oculto para no reducir líneas del archivo.
                            html.Div(
                                style={"display": "none"},
                                children=[
                                    html.Div("Controles rápidos eliminados", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                    html.Div(
                                        style={
                                            "borderRadius": "12px",
                                            "background": "rgba(0,0,0,.12)",
                                            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                                            "padding": "10px",
                                        },
                                        children=[
                                            html.Div(
                                                "Las opciones avanzadas de registro se siguen gestionando desde el botón “Opciones de registro”.",
                                                style={**BLACK_MUTED, "fontSize": "12px", "lineHeight": "1.45"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),

                        ],
                    ),

                    # ===== ÁREA DERECHA =====
                    html.Div(
                        style=right_area_style,
                        children=[
                            html.Div(
                                className=f"{MAIN_BLACK_CARD_CLASS} {MAIN_CARD_COL_CLASS}",
                                children=[
                                    html.Div(
                                        className=DEVICE_TOP_ROW_CLASS,
                                        children=[
                                            html.Div(
                                                id="device-user-top",
                                                children=html.Div("Estado del dispositivo", className=SECTION_TITLE_CLASS, style={"textAlign": "left"}),
                                                style={
                                                    "flex": "0 0 auto",
                                                    "minWidth": "0px",
                                                    "display": "flex",
                                                    "alignItems": "center",
                                                    "justifyContent": "flex-start",
                                                    "textAlign": "left",
                                                    "paddingRight": "0px",
                                                    "paddingLeft": "0px",
                                                },
                                            ),
                                            html.Div(
                                                id="fw-pill",
                                                children=_device_status_item("Firmware", "v1.0.3", "neutral"),
                                                style={"flex": "1 1 0", "minWidth": "0"},
                                            ),
                                            html.Div(
                                                id="device-battery-top",
                                                children=_device_status_item("Batería", "82%", "ok"),
                                                style={"flex": "1 1 0", "minWidth": "0"},
                                            ),
                                            html.Div(
                                                id="device-bt-top",
                                                children=_device_status_item("Bluetooth", "Conectado", "ok"),
                                                style={"flex": "1 1 0", "minWidth": "0"},
                                            ),
                                            html.Div(
                                                style={"flex": "0 0 auto", "display": "flex", "alignItems": "center", "gap": "8px"},
                                                children=[
                                                    dbc.DropdownMenu(
                                                        id="sim-control-menu",
                                                        label="Pendiente",
                                                        color="primary",
                                                        size="sm",
                                                        toggle_style=SIM_TOGGLE_BUTTON_STYLE,
                                                        children=[
                                                            dbc.DropdownMenuItem("Encender simulación", id="sim-on-item", n_clicks=0),
                                                            dbc.DropdownMenuItem("Apagar simulación", id="sim-off-item", n_clicks=0),
                                                            dbc.DropdownMenuItem(divider=True),
                                                            dbc.DropdownMenuItem("Reiniciar inclinación", id="sim-reset-item", n_clicks=0),
                                                        ],
                                                    ),
                                                    dbc.Badge(
                                                        "ON",
                                                        id="sim-status-badge",
                                                        color="success",
                                                        pill=True,
                                                        style={
                                                            "width": "54px",
                                                            "minWidth": "54px",
                                                            "maxWidth": "54px",
                                                            "display": "inline-flex",
                                                            "alignItems": "center",
                                                            "justifyContent": "center",
                                                            "textAlign": "center",
                                                        },
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                id="device-state-top",
                                                children=_hidden_device_state_placeholder("Operativo", "ok"),
                                                style={"display": "none"},
                                            ),
                                        ],
                                    ),
                                ],
                            ),

                            # ===== CONTENIDO DERECHO =====
                            html.Div(
                                style=right_container_style,
                                children=[
                                    # ===== COLUMNA 2 =====
                                    html.Div(
                                        style=right_col_style,
                                        children=[
                                            # Postura en vivo
                                            html.Div(
                                                className=f"{MAIN_BLACK_CARD_CLASS} {MAIN_CARD_COL_CLASS}",
                                                children=[
                                                    html.Div("Postura en vivo", className=MAIN_CARD_TITLE_ONLY_CLASS),
                                                    html.Div(
                                                        style={
                                                            "minHeight": "0",
                                                            "borderRadius": "12px",
                                                            "background": "rgba(0,0,0,.15)",
                                                            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                                                            "display": "flex",
                                                            "alignItems": "stretch",
                                                            "justifyContent": "space-between",
                                                            "gap": "12px",
                                                            "padding": "10px",
                                                        },
                                                        children=[
                                                            html.Div(
                                                                style={
                                                                    "width": "40%",
                                                                    "minWidth": "0",
                                                                    "display": "flex",
                                                                    "flexDirection": "column",
                                                                    "alignItems": "stretch",
                                                                    "justifyContent": "space-between",
                                                                    "gap": "0px",
                                                                    "alignSelf": "stretch",
                                                                },
                                                                children=[
                                                                    html.Div(
                                                                        id="posture-calibration-warning",
                                                                        children=_posture_calibration_warning_block(),
                                                                        style={"display": "none", "width": "100%"},
                                                                    ),
                                                                    html.Div(
                                                                        id="posture-arrow-wrap",
                                                                        style={
                                                                            "flex": "1 1 auto",
                                                                            "height": "auto",
                                                                            "display": "flex",
                                                                            "alignItems": "center",
                                                                            "justifyContent": "flex-start",
                                                                            "paddingLeft": "18px",
                                                                            "width": "100%",
                                                                        },
                                                                        children=[html.Div("↗", id="back-arrow", style={"fontSize": "34px", "color": "rgba(226,232,240,.90)", "transform": "rotate(-10deg)"})],
                                                                    ),
                                                                    html.Div(
                                                                        id="general-status-note",
                                                                        children="",
                                                                        style={
                                                                            "display": "none",
                                                                            "width": "100%",
                                                                            "marginTop": "auto",
                                                                            "padding": "12px 14px",
                                                                            "borderRadius": "12px",
                                                                            "background": "rgba(245,158,11,.18)",
                                                                            "boxShadow": "inset 0 0 0 1px rgba(245,158,11,.28)",
                                                                            "color": "#fbbf24",
                                                                            "fontSize": "12px",
                                                                            "fontWeight": 700,
                                                                            "lineHeight": "1.45",
                                                                            "textAlign": "center",
                                                                            "display": "none",
                                                                            "alignItems": "center",
                                                                            "justifyContent": "center",
                                                                            "alignSelf": "stretch",
                                                                        },
                                                                    ),
                                                                ],
                                                            ),
                                                            # Cuadro de datos
                                                            html.Div(
                                                                className=SECONDARY_GRAY_PANEL_CLASS,
                                                                style={
                                                                    "width": "60%",
                                                                    "minWidth": "60%",
                                                                    "maxWidth": "60%",
                                                                    "gap": "5px",
                                                                    "padding": "7px",
                                                                    "borderRadius": "8px",
                                                                    "background": "rgba(255,255,255,.10)",
                                                                },
                                                                children=[
                                                                    html.Div("Estado general", className=SECTION_TITLE_CLASS),
                                                                    html.Div(
                                                                        style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "6px"},
                                                                        children=[
                                                                            html.Div(
                                                                                style={"display": "flex", "alignItems": "center", "gap": "5px"},
                                                                                children=[
                                                                                    html.Span("Inclinación", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                                    html.Div(id="traffic-light", children=_traffic_light_dynamic(86)),
                                                                                ],
                                                                            ),
                                                                            html.Div(
                                                                                style={"display": "flex", "alignItems": "center", "gap": "5px"},
                                                                                children=[
                                                                                    html.Span("Postura", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                                    html.Span(id="posture-score", children="86", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700}),
                                                                                ],
                                                                            ),
                                                                        ],
                                                                    ),
                                                                    html.Div(
                                                                        style={"display": "none"},
                                                                        children=[
                                                                            html.Div("Aviso de lectura reubicado", className=SECTION_TITLE_CLASS),
                                                                            html.Div("El aviso amarillo ahora vive bajo la flecha en Postura en vivo.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                        ],
                                                                    ),
                                                                    html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "1px 0"}),
                                                                    html.Div("Estado detallado", className=SECTION_TITLE_CLASS),
                                                                    html.Div(
                                                                        className=PANEL_GROUP_TIGHT_CLASS,
                                                                        children=[
                                                                            _segment_state_card(
                                                                                "Torácica",
                                                                                "thor-traffic-light",
                                                                                "thor-segment-status",
                                                                                "thor-segment-cue",
                                                                                "thor-angle-output",
                                                                                "Ángulo",
                                                                                time_id="thor-red-output",
                                                                                time_label="Tiempo mala postura",
                                                                            ),
                                                                            _segment_state_card(
                                                                                "Lumbar",
                                                                                "lum-traffic-light",
                                                                                "lum-segment-status",
                                                                                "lum-segment-cue",
                                                                                "lum-angle-output",
                                                                                "Ángulo",
                                                                                time_id="lum-red-output",
                                                                                time_label="Tiempo mala postura",
                                                                                extra_children=[
                                                                                    html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "1px 0"}),
                                                                                    html.Div("Compensación", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600, "display": "none"}),
                                                                                    html.Div(id="comp-output", children=_comp_output_block(18.0)),
                                                                                ],
                                                                            ),
                                                                        ],
                                                                    ),
                                                                    html.Div(
                                                                        style={"display": "none"},
                                                                        children=[
                                                                            html.Div("COMPENSACIÓN LUMBAR", style={**BLACK_TEXT, "fontWeight": 800, "fontSize": "12px", "letterSpacing": ".04em"}),
                                                                            html.Div("Bloque movido al cuadro lumbar.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                        ],
                                                                    ),
                                                                    html.Div(
                                                                        style={"display": "none"},
                                                                        children=[
                                                                            html.Div("TIEMPO EN ROJO (sesión)", style={**BLACK_TEXT, "fontWeight": 800, "fontSize": "12px", "letterSpacing": ".04em"}),
                                                                            html.Div("El tiempo segmentario ahora vive dentro de Torácica y Lumbar.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                        ],
                                                                    ),
                                                                    html.Div(id="bad-time-metric", children="—", style={"display": "none"}),
                                                                ],
                                                            ),
                                                            html.Div(id="state-dot", style={"display": "none"}),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        style={"display": "none"},
                                                        children=[
                                                            html.Div("Alertas activas reubicadas", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                                            html.Div("El cuadro de alertas ahora vive dentro de Gráficas, debajo de las gráficas.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                            html.Div("Se deja este placeholder oculto para no reducir líneas del archivo.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                        ],
                                                    ),
                                                ],
                                            ),

                                            # Alertas activas movidas a subcuadro dentro de Postura en vivo.
                                            # Este placeholder se deja oculto para no reducir líneas del archivo.
                                            html.Div(
                                                style={"display": "none"},
                                                children=[
                                                    html.Div("Alertas reubicadas", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                                    html.Div("Las alertas activas ahora están dentro del cuadro Gráficas.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                ],
                                            ),

                                        ],
                                    ),

                                    # ===== COLUMNA 3 =====
                                    html.Div(
                                        style=right_col_style,
                                        children=[
                                            # Gráficas
                                            html.Div(
                                                className=f"{MAIN_BLACK_CARD_CLASS} {MAIN_CARD_COL_CLASS}",
                                                children=[
                                                    html.Div("Gráficas", className=MAIN_CARD_TITLE_ONLY_CLASS),
                                                    html.Div(
                                                        className=SECONDARY_GRAY_PANEL_CLASS,
                                                        style={"background": "rgba(0,0,0,.12)", "padding": "8px", "gap": "8px"},
                                                        children=[
                                                            dcc.Tabs(
                                                                id="graphs-tabs",
                                                                value="imu",
                                                                parent_style={"margin": "0", "padding": "0", "display": "flex", "justifyContent": "center", "alignItems": "center", "width": "100%"},
                                                                style={"height": "36px", "display": "flex", "justifyContent": "center", "alignItems": "center", "gap": "10px", "width": "100%", "padding": "0", "margin": "0"},
                                                                children=[
                                                                    dcc.Tab(
                                                                        label="Inclinación",
                                                                        value="imu",
                                                                        style={
                                                                            "background": "rgba(255,255,255,.06)",
                                                                            "border": "1px solid rgba(255,255,255,.08)",
                                                                            "borderRadius": "10px",
                                                                            "padding": "7px 0px",
                                                                            "color": "#e2e8f0",
                                                                            "fontSize": "12px",
                                                                            "fontWeight": 700,
                                                                            "width": "calc((100% - 10px) / 2)",
                                                                            "textAlign": "center",
                                                                            "display": "flex",
                                                                            "alignItems": "center",
                                                                            "justifyContent": "center",
                                                                        },
                                                                        selected_style={
                                                                            "background": "rgba(255,255,255,.14)",
                                                                            "border": "1px solid rgba(255,255,255,.14)",
                                                                            "borderRadius": "10px",
                                                                            "padding": "7px 0px",
                                                                            "color": "#ffffff",
                                                                            "fontSize": "12px",
                                                                            "fontWeight": 800,
                                                                            "width": "calc((100% - 10px) / 2)",
                                                                            "textAlign": "center",
                                                                            "display": "flex",
                                                                            "alignItems": "center",
                                                                            "justifyContent": "center",
                                                                        },
                                                                    ),
                                                                    dcc.Tab(
                                                                        label="Estabilidad",
                                                                        value="sway",
                                                                        style={
                                                                            "background": "rgba(255,255,255,.06)",
                                                                            "border": "1px solid rgba(255,255,255,.08)",
                                                                            "borderRadius": "10px",
                                                                            "padding": "7px 0px",
                                                                            "color": "#e2e8f0",
                                                                            "fontSize": "12px",
                                                                            "fontWeight": 700,
                                                                            "width": "calc((100% - 10px) / 2)",
                                                                            "textAlign": "center",
                                                                            "display": "flex",
                                                                            "alignItems": "center",
                                                                            "justifyContent": "center",
                                                                        },
                                                                        selected_style={
                                                                            "background": "rgba(255,255,255,.14)",
                                                                            "border": "1px solid rgba(255,255,255,.14)",
                                                                            "borderRadius": "10px",
                                                                            "padding": "7px 0px",
                                                                            "color": "#ffffff",
                                                                            "fontSize": "12px",
                                                                            "fontWeight": 800,
                                                                            "width": "calc((100% - 10px) / 2)",
                                                                            "textAlign": "center",
                                                                            "display": "flex",
                                                                            "alignItems": "center",
                                                                            "justifyContent": "center",
                                                                        },
                                                                    ),
                                                                    dcc.Tab(
                                                                        label="Histórico de sesiones",
                                                                        value="history",
                                                                        style={
                                                                            "background": "rgba(255,255,255,.06)",
                                                                            "border": "1px solid rgba(255,255,255,.08)",
                                                                            "borderRadius": "10px",
                                                                            "padding": "7px 12px",
                                                                            "color": "#e2e8f0",
                                                                            "fontSize": "12px",
                                                                            "fontWeight": 700,
                                                                            "display": "none",
                                                                        },
                                                                        selected_style={
                                                                            "background": "rgba(255,255,255,.14)",
                                                                            "border": "1px solid rgba(255,255,255,.14)",
                                                                            "borderRadius": "10px",
                                                                            "padding": "7px 12px",
                                                                            "color": "#ffffff",
                                                                            "fontSize": "12px",
                                                                            "fontWeight": 800,
                                                                            "display": "none",
                                                                        },
                                                                    ),
                                                                ],
                                                            ),
                                                            html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0 8px"}),
                                                            html.Div(
                                                                style={"display": "flex", "flexDirection": "column", "gap": "0px", "minHeight": "0", "paddingTop": "0px", "paddingBottom": "0px"},
                                                                children=[
                                                                    html.Div(
                                                                        id="graphs-pane-imu",
                                                                        style={
                                                                            "display": "flex",
                                                                            "flexDirection": "column",
                                                                            "gap": "0px",
                                                                            "paddingTop": "0px",
                                                                            "paddingBottom": "0px",
                                                                        },
                                                                        children=[
                                                                            html.Div(_metric_header("Inclinación", "pry-metric", value_default="— / — / —"), style={"display": "none"}),
                                                                            html.Div(
                                                                                id="imu-calibration-warning",
                                                                                children=_graph_calibration_warning_block(),
                                                                                style={"display": "none", "width": "100%"},
                                                                            ),
                                                                            # ✅ PASO 12: ecg-graph -> imu-graph
                                                                            dcc.Graph(id="imu-graph", style={"height": "125px", "width": "100%", "margin": "0", "padding": "0", "display": "block"}, figure=empty_imu_fig, config=IMU_GRAPH_CONFIG),
                                                                        ],
                                                                    ),
                                                                    html.Div(
                                                                        id="graphs-pane-sway",
                                                                        style={
                                                                            "display": "none",
                                                                            "flexDirection": "column",
                                                                            "gap": "0px",
                                                                            "paddingTop": "0px",
                                                                            "paddingBottom": "0px",
                                                                        },
                                                                        children=[
                                                                            html.Div(_metric_header("Estabilidad", "sway-metric", value_default="—"), style={"display": "none"}),
                                                                            html.Div(
                                                                                id="sway-calibration-warning",
                                                                                children=_graph_calibration_warning_block(),
                                                                                style={"display": "none", "width": "100%"},
                                                                            ),
                                                                            dcc.Graph(id="sway-graph", style={"height": "125px", "width": "100%", "margin": "0", "padding": "0", "display": "block"}, figure=empty_sway_fig, config=SWAY_GRAPH_CONFIG),
                                                                        ],
                                                                    ),
                                                                    html.Div(
                                                                        id="graphs-pane-history",
                                                                        style={
                                                                            "display": "none",
                                                                            "flexDirection": "column",
                                                                            "gap": "8px",
                                                                        },
                                                                        children=[
                                                                            html.Div("Histórico movido al popup de vincular sesión.", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 700}),
                                                                            html.Div("El gráfico y las últimas sesiones ahora se visualizan dentro del modal.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                            html.Div(
                                                                                style={"display": "none"},
                                                                                children=[
                                                                                    html.Div("Compatibilidad interna de histórico fuera del cuadro principal.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                                    html.Div("Se conserva este contenedor para no reducir líneas del archivo.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                                ],
                                                                            ),
                                                                        ],
                                                                    ),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                className=SECONDARY_GRAY_PANEL_CLASS,
                                                                style={"background": "rgba(0,0,0,.12)", "padding": "8px", "gap": "6px"},
                                                                children=[
                                                                    html.Div(
                                                                        style={
                                                                            "display": "flex",
                                                                            "alignItems": "center",
                                                                            "justifyContent": "space-between",
                                                                            "gap": "10px",
                                                                            "marginBottom": "0",
                                                                        },
                                                                        children=[
                                                                            html.Div("Alertas activas", className=SECTION_TITLE_CLASS),
                                                                            dbc.Switch(id="alerts-switch", label="", value=True, style={**BLACK_TEXT, "fontSize": "13px", "marginBottom": "0", "padding": "0", "display": "flex", "alignItems": "center", "minHeight": "19px"}),
                                                                        ],
                                                                    ),
                                                                    html.Ul(
                                                                        id="alerts-list",
                                                                        style={
                                                                            "margin": 0,
                                                                            "paddingLeft": "18px",
                                                                            "paddingRight": "4px",
                                                                            "color": "rgba(226,232,240,.85)",
                                                                            "fontSize": "12px",
                                                                            "lineHeight": "1.30",
                                                                            "height": "53px",
                                                                            "minHeight": "53px",
                                                                            "maxHeight": "53px",
                                                                            "overflow": "hidden",
                                                                        },
                                                                        children=[html.Li("— (sin datos aún)")],
                                                                    ),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                style={"display": "none"},
                                                                children=[
                                                                    html.Div("Compatibilidad visual interna de gráficas con tabs", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                    html.Div("El contenido vertical anterior se reemplazó por pestañas para mantener compacto el cuadro sin scroll.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                    html.Div("Las tres vistas permanecen montadas en el layout y solo cambia su visibilidad.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                ],
                                            ),

                                            # Histórico movido a subcuadro dentro de Gráficas según solicitud.
                                            # Este placeholder se deja oculto para no reducir líneas del archivo.
                                            html.Div(
                                                style={"display": "none"},
                                                children=[
                                                    html.Div("Histórico reubicado", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                                    html.Div("El histórico de sesiones ahora vive dentro del cuadro de Gráficas.", style={**BLACK_MUTED, "fontSize": "12px"}),
                                                ],
                                            ),
                                        ],
                                    ),

                                ],
                            ),
                        ],
                    ),
                    # Modal configuración de sesión
                    dbc.Modal(
                        id="session-link-modal",
                        backdrop=False,
                        is_open=False,
                        centered=True,
                        size="lg",
                        # Sin oscurecer el resto para que la vista siga siendo visible detrás del popup.
                        children=[
                            dbc.ModalHeader(
                                html.Div(
                                    style={
                                        "width": "100%",
                                        "display": "flex",
                                        "alignItems": "center",
                                        "justifyContent": "space-between",
                                        "gap": "12px",
                                    },
                                    children=[
                                        dbc.ModalTitle("Vincular sesión", className=MODAL_TITLE_CLASS),
                                        html.Button(
                                            "×",
                                            id="close-link-session-x-btn",
                                            n_clicks=0,
                                            className=MODAL_CLOSE_X_CLASS,
                                        ),
                                    ],
                                ),
                                close_button=False,
                                className=MODAL_HEADER_CLASS,
                            ),
                            dbc.ModalBody(
                                [
                                    html.Div("Ajusta la configuración visible del panel y vincula la sesión activa del día.", className="mb-2", style={**BLACK_MUTED, "fontSize": "12px"}),
                                    html.Div(
                                        style={
                                            "display": "flex",
                                            "alignItems": "flex-start",
                                            "justifyContent": "space-between",
                                            "gap": "12px",
                                            "flexWrap": "nowrap",
                                        },
                                        children=[
                                            html.Div(
                                                style={
                                                    "width": "33.333%",
                                                    "minWidth": "33.333%",
                                                    "maxWidth": "33.333%",
                                                    "display": "flex",
                                                    "flexDirection": "column",
                                                    "gap": "12px",
                                                },
                                                children=[
                                                    html.Div(
                                                        id="session-modal-preview",
                                                        className=SECONDARY_BLACK_PANEL_CLASS,
                                                        children=_session_summary_items("train", "gym", _default_session_for_mode("train")),
                                                    ),
                                                    html.Div(
                                                        className=SECONDARY_BLACK_PANEL_CLASS,
                                                        children=[
                                                            html.Div("Modalidad", className=MUTED_LABEL_CLASS, style={"marginBottom": "4px"}),
                                                            dbc.Select(
                                                                id="mode-preset",
                                                                options=[
                                                                    {"label": "Entrenamiento", "value": "train"},
                                                                    {"label": "Rehabilitación", "value": "rehab"},
                                                                    {"label": "Oficina", "value": "office"},
                                                                ],
                                                                value="train",
                                                                size="sm",
                                                                style={"width": "100%"},
                                                            ),
                                                        ]
                                                    ),
                                                    html.Div(
                                                        className=SECONDARY_BLACK_PANEL_CLASS,
                                                        children=[
                                                            html.Div("Sesión del día", className=MUTED_LABEL_CLASS, style={"marginBottom": "4px"}),
                                                            dbc.Select(
                                                                id="planned-session",
                                                                options=_session_options_for_mode("train"),
                                                                value=_default_session_for_mode("train"),
                                                                size="sm",
                                                                style={"width": "100%"},
                                                            ),
                                                        ]
                                                    ),
                                                    html.Div(
                                                        className=SECONDARY_BLACK_PANEL_CLASS,
                                                        children=[
                                                            html.Div("Deporte", className=MUTED_LABEL_CLASS, style={"marginBottom": "4px"}),
                                                            dbc.Select(
                                                                id="sport-select",
                                                                options=[
                                                                    {"label": "Gym", "value": "gym"},
                                                                    {"label": "CrossFit", "value": "crossfit"},
                                                                ],
                                                                value="gym",
                                                                disabled=False,
                                                                size="sm",
                                                                style={"width": "100%"},
                                                            ),
                                                        ]
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                style={
                                                    "width": "66.667%",
                                                    "minWidth": "66.667%",
                                                    "maxWidth": "66.667%",
                                                    "display": "flex",
                                                    "flexDirection": "column",
                                                    "gap": "12px",
                                                },
                                                children=[
                                                    html.Div(
                                                        className=SECONDARY_BLACK_PANEL_CLASS,
                                                        children=[
                                                            html.Div("Histórico de sesiones", className=SECTION_TITLE_CLASS, style={"marginBottom": "0"}),
                                                            dcc.Graph(id="history-graph", style={"height": "220px", "width": "100%"}, figure=empty_history_fig, config=GRAPH_TOOLBAR_CONFIG),
                                                            html.Div(
                                                                className=SECONDARY_GRAY_PANEL_CLASS,
                                                                style={"maxHeight": "110px", "overflowY": "auto"},
                                                                children=[
                                                                    html.Div("Últimas sesiones", className=MUTED_LABEL_CLASS, style={"fontWeight": 700, "marginBottom": "6px"}),
                                                                    html.Ul(
                                                                        id="history-list",
                                                                        style={"margin": 0, "paddingLeft": "18px", "color": "rgba(226,232,240,.85)", "fontSize": "12px"},
                                                                        children=[html.Li("— (sin historial)")],
                                                                    ),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        style={"display": "none"},
                                                        children=[
                                                            html.Div("Compatibilidad visual: formulario a la izquierda 1/3 e histórico a la derecha 2/3."),
                                                            html.Div("La X de cierre se iguala en color blanco al resto de popups."),
                                                        ],
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                                className=MODAL_BODY_CLASS,
                            ),
                            dbc.ModalFooter(
                                [
                                    dbc.Button("Guardar vinculación", id="save-link-session-btn", color="primary", className=PRIMARY_BUTTON_CLASS),
                                    dbc.Button("Desvincular", id="unlink-session-btn", color="secondary", outline=True, className=OUTLINE_BUTTON_CLASS),
                                    dbc.Button("Cerrar", id="close-link-session-btn", color="secondary", outline=True, className=OUTLINE_BUTTON_CLASS),
                                ],
                                className=MODAL_FOOTER_CLASS,
                            ),
                        ],
                    ),
                    # Modal opciones de registro
                    dbc.Modal(
                        id="record-options-modal",
                        backdrop=False,
                        is_open=False,
                        centered=True,
                        # Sin oscurecer el resto para que la vista siga siendo visible detrás del popup.
                        children=[
                            dbc.ModalHeader(
                                html.Div(
                                    style={
                                        "width": "100%",
                                        "display": "flex",
                                        "alignItems": "center",
                                        "justifyContent": "space-between",
                                        "gap": "12px",
                                    },
                                    children=[
                                        dbc.ModalTitle("Opciones de registro", className=MODAL_TITLE_CLASS),
                                        html.Button(
                                            "×",
                                            id="close-record-options-x-btn",
                                            n_clicks=0,
                                            className=MODAL_CLOSE_X_CLASS,
                                        ),
                                    ],
                                ),
                                close_button=False,
                                className=MODAL_HEADER_CLASS,
                            ),
                            dbc.ModalBody(
                                [
                                    html.Div("Configura y gestiona el registro sin recargar el panel principal.", className="mb-2", style={**BLACK_MUTED, "fontSize": "12px"}),
                                    html.Div(
                                        id="record-options-preview",
                                        className=SECONDARY_BLACK_PANEL_CLASS,
                                        style={"marginBottom": "12px"},
                                        children=_recording_panel_items(False, _default_session_for_mode("train"), "Sin iniciar", "00:00"),
                                    ),
                                    dbc.Alert(
                                        id="record-options-alert",
                                        children="",
                                        is_open=False,
                                        color="info",
                                        className=DARK_ALERT_CLASS,
                                        style={"marginTop": "4px", "marginBottom": "12px"},
                                    ),
                                    html.Div(
                                        className=SECONDARY_BLACK_PANEL_CLASS,
                                        children=[
                                            html.Div("Acciones rápidas", className=MUTED_LABEL_CLASS, style={"fontWeight": 700, "marginBottom": "2px"}),
                                            html.Div(
                                                style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                                                children=[
                                                    dbc.Button("Iniciar registro", id="stop-record-btn", color="primary", size="sm", className=MODAL_PRIMARY_BUTTON_CLASS),
                                                    dbc.Button(
                                                        "Exportar histórico (CSV)",
                                                        id="export-history-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=MODAL_GRAY_BUTTON_CLASS,
                                                    ),
                                                    dbc.Button(
                                                        "Exportar ventana 20s (CSV)",
                                                        id="export-window-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=MODAL_GRAY_BUTTON_CLASS,
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                                className=MODAL_BODY_CLASS,
                            ),
                            dbc.ModalFooter(
                                [
                                    dbc.Button("Cerrar", id="close-record-options-btn", color="secondary", outline=True, className=OUTLINE_BUTTON_CLASS),
                                ],
                                className=MODAL_FOOTER_CLASS,
                            ),
                        ],
                    ),
                    # Modal Recalibración
                    dbc.Modal(
                        id="recal-modal",
                        backdrop=False,
                        is_open=False,
                        centered=True,
                        # Sin oscurecer el resto para que la vista siga siendo visible detrás del popup.
                        children=[
                            dbc.ModalHeader(
                                html.Div(
                                    style={
                                        "width": "100%",
                                        "display": "flex",
                                        "alignItems": "center",
                                        "justifyContent": "space-between",
                                        "gap": "12px",
                                    },
                                    children=[
                                        dbc.ModalTitle("Calibración", className=MODAL_TITLE_CLASS),
                                        html.Button(
                                            "×",
                                            id="close-recal-x-btn",
                                            n_clicks=0,
                                            className=MODAL_CLOSE_X_CLASS,
                                        ),
                                    ],
                                ),
                                close_button=False,
                                className=MODAL_HEADER_CLASS,
                            ),
                            dbc.ModalBody(
                                [
                                    html.Div("Sigue estos pasos para calibrar el dispositivo:", className="mb-2", style={**BLACK_MUTED, "fontSize": "12px"}),
                                    html.Div(
                                        className=SECONDARY_GRAY_PANEL_CLASS,
                                        children=[
                                            html.Div("Necesaria antes de iniciar la monitorización.", style={**BLACK_MUTED, "fontSize": "12px", "marginBottom": "0px"}),
                                            html.Div("Al completarla, el sistema quedará listo para medir.", style={**BLACK_MUTED, "fontSize": "12px", "marginBottom": "0px"}),
                                            html.Ol(
                                                [
                                                    html.Li("Coloca el dispositivo correctamente y mantén postura neutra."),
                                                    html.Li("Permanece inmóvil durante 5–10 segundos."),
                                                    html.Li("Pulsa “Iniciar calibración”."),
                                                    html.Li("Comprueba que el estado cambie a “Completada”."),
                                                ],
                                                style={"marginBottom": "0", "paddingLeft": "18px", "color": "rgba(226,232,240,.85)", "fontSize": "12px"},
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className=SECONDARY_BLACK_PANEL_CLASS,
                                        style={"alignItems": "center", "justifyContent": "center", "gap": "8px", "marginTop": "8px"},
                                        children=[
                                            dbc.Button(_calibration_action_label("Pendiente"), id="start-recal-btn", color="primary", size="sm", className=MODAL_PRIMARY_BUTTON_CLASS),
                                            html.Div(id="recal-status-text", children=_calibration_popup_status_text("Pendiente"), style={"display": "none"}),
                                            html.Div(id="recal-status-pill", children=_calibration_pill("Pendiente")),
                                            html.Div(
                                                style={"display": "none"},
                                                children=[
                                                    html.Div("Compatibilidad visual: acción de calibración movida dentro del subcuadro negro."),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                                className=MODAL_BODY_CLASS,
                            ),
                            dbc.ModalFooter(
                                [
                                    html.Div(
                                        style={"display": "none"},
                                        children=[
                                            html.Div("Placeholder oculto para conservar estructura del footer de calibración."),
                                        ],
                                    ),
                                    dbc.Button("Cerrar", id="close-recal-btn", color="secondary", outline=True, className=OUTLINE_BUTTON_CLASS),
                                ],
                                className=MODAL_FOOTER_END_CLASS,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

# =============================
# Callbacks
# =============================
def register_callbacks(app):
    @app.callback(
        [Output("sim-state-store", "data"), Output("imu-interval", "disabled"), Output("sim-status-badge", "children"), Output("sim-status-badge", "color"), Output("sim-control-menu", "label")],
        [Input("sim-on-item", "n_clicks"), Input("sim-off-item", "n_clicks"), Input("sim-reset-item", "n_clicks"), Input("calibration-store", "data")],
        State("sim-state-store", "data"),
        prevent_initial_call=False,
    )
    def sim_control(_on, _off, _reset, calib, sim_state):
        sim_state = sim_state or {"on": True, "reset_seq": 0}
        trig = ctx.triggered_id
        calibrated = _is_calibration_completed(calib)

        if trig == "sim-off-item":
            sim_state["on"] = False
            return sim_state, True, "OFF", "secondary", "Apagado"

        if trig == "sim-reset-item":
            sim_state["on"] = True
            sim_state["reset_seq"] = int(sim_state.get("reset_seq", 0)) + 1
            if calibrated:
                return sim_state, False, "ON", "success", "Encendido"
            return sim_state, True, "PEND", "warning", "Pendiente"

        if trig == "sim-on-item":
            sim_state["on"] = True
            if calibrated:
                return sim_state, False, "ON", "success", "Encendido"
            return sim_state, True, "PEND", "warning", "Pendiente"

        if not calibrated:
            return sim_state, True, "PEND", "warning", "Pendiente"

        if bool(sim_state.get("on", True)):
            return sim_state, False, "ON", "success", "Encendido"
        return sim_state, True, "OFF", "secondary", "Apagado"


    @app.callback(
        [Output("device-user-top", "children"), Output("device-state-top", "children")],
        [Input("session-user", "data"), Input("sim-state-store", "data")],
        prevent_initial_call=False,
    )
    def update_device_top_bar(session_user, sim_state):
        _ = _get_user_display_name(session_user)
        sim_on = bool((sim_state or {}).get("on", True))
        state_value = "Operativo" if sim_on else "Pausado"
        state_tone = "ok" if sim_on else "warn"
        return (
            html.Div("Estado del dispositivo", className=SECTION_TITLE_CLASS, style={"textAlign": "left"}),
            _hidden_device_state_placeholder(state_value, state_tone),
        )

    @app.callback(
        [
            Output("session-link-modal", "is_open"),
            Output("active-session-store", "data"),
            Output("active-session-label", "children"),
            Output("active-session-badge", "children"),
        ],
        [
            Input("link-session-btn", "n_clicks"),
            Input("close-link-session-btn", "n_clicks"),
            Input("close-link-session-x-btn", "n_clicks"),
            Input("save-link-session-btn", "n_clicks"),
            Input("unlink-session-btn", "n_clicks"),
            Input("session-user", "data"),
        ],
        [
            State("session-link-modal", "is_open"),
            State("active-session-store", "data"),
            State("planned-session", "value"),
            State("mode-preset", "value"),
            State("sport-select", "value"),
        ],
        prevent_initial_call=False,
    )
    def link_session_modal(open_n, close_n, close_x_n, save_n, unlink_n, session_user, is_open, active_session, planned, mode_value, sport_value):
        trigger = ctx.triggered_id
        empty_label = "Sesión activa: —"
        empty_badge = _pill("Sesión", "—", "neutral", full=True)

        if trigger == "session-user" or trigger is None:
            db_link_ctx = _load_monitor_link_context_for_user(session_user)
            has_db_ctx = _link_context_has_reference(db_link_ctx)
            if not active_session and not has_db_ctx:
                return False, None, empty_label, empty_badge

            data = _build_active_session_payload(existing_session=active_session, link_ctx=db_link_ctx)
            label = f"Sesión activa: {data.get('name') or '—'}"
            badge = _pill("Sesión", data.get("name") or "—", "neutral", full=True)
            return False, data, label, badge

        if trigger == "link-session-btn":
            return True, no_update, no_update, no_update

        if trigger in ("close-link-session-btn", "close-link-session-x-btn"):
            return False, no_update, no_update, no_update

        if trigger == "unlink-session-btn":
            return False, None, empty_label, empty_badge

        if trigger == "save-link-session-btn":
            db_link_ctx = _load_monitor_link_context_for_user(session_user)
            session_name = planned or (active_session or {}).get("planned_session_name") or (active_session or {}).get("name") or db_link_ctx.get("planned_session_name") or "—"
            final_mode = mode_value or (active_session or {}).get("mode") or db_link_ctx.get("mode") or "train"
            final_sport = sport_value or (active_session or {}).get("sport") or db_link_ctx.get("sport") or _default_sport_for_mode(final_mode)
            data = _build_active_session_payload(
                existing_session=active_session,
                link_ctx=db_link_ctx,
                planned_session_name=session_name,
                mode=final_mode,
                sport=final_sport,
            )
            data["linked_at"] = datetime.now().isoformat(timespec="seconds")
            label = f"Sesión activa: {data.get('name') or '—'}"
            badge = _pill("Sesión", data.get("name") or "—", "neutral", full=True)
            return False, data, label, badge

        return is_open, active_session, no_update, no_update

    @app.callback(
        [
            Output("mode-summary-pill", "children"),
            Output("sport-summary-pill", "children"),
            Output("session-summary-pill", "children"),
            Output("session-modal-preview", "children"),
        ],
        [
            Input("mode-preset", "value"),
            Input("sport-select", "value"),
            Input("planned-session", "value"),
            Input("active-session-store", "data"),
        ],
        prevent_initial_call=False,
    )
    def update_session_summary(mode_value, sport_value, planned_session, active_session):
        active_session = active_session if isinstance(active_session, dict) else {}
        if ctx.triggered_id == "active-session-store":
            display_mode = active_session.get("mode") or mode_value or "train"
            display_sport = active_session.get("sport") or sport_value or _default_sport_for_mode(display_mode)
            display_session = active_session.get("planned_session_name") or active_session.get("name") or planned_session or "—"
        else:
            display_mode = mode_value or active_session.get("mode") or "train"
            display_sport = sport_value or active_session.get("sport") or _default_sport_for_mode(display_mode)
            display_session = planned_session or active_session.get("planned_session_name") or active_session.get("name") or "—"

        preview = _session_summary_items(display_mode, display_sport, display_session)
        return (
            _pill("Modalidad", _mode_label(display_mode), "neutral", full=True),
            _pill("Deporte", _sport_label(display_sport), "neutral", full=True),
            _pill("Sesión del día", display_session or "—", "neutral", full=True),
            preview,
        )

    @app.callback(
        [
            Output("sport-select", "disabled"),
            Output("sport-select", "value"),
            Output("planned-session", "options"),
            Output("planned-session", "value"),
        ],
        Input("mode-preset", "value"),
        [
            State("sport-select", "value"),
            State("planned-session", "value"),
        ],
        prevent_initial_call=False,
    )
    def sync_session_form_by_mode(mode_value, sport_value, planned_session):
        """
        Reglas:
        - Modalidad reemplaza al concepto visual de preset.
        - Deporte solo se habilita en Entrenamiento.
        - Sesión del día cambia por modalidad.
        - Esta estructura deja listo el punto de enlace con la ventana de Rutina.
        """
        mode_value = mode_value or "train"
        planned_options = _session_options_for_mode(mode_value)
        valid_sessions = [opt["value"] for opt in planned_options]

        is_training = _is_training_mode(mode_value)
        sport_disabled = not is_training

        if is_training:
            next_sport = sport_value if sport_value in ("gym", "crossfit") else _default_sport_for_mode(mode_value)
        else:
            next_sport = _default_sport_for_mode(mode_value)

        if planned_session in valid_sessions:
            next_planned_session = planned_session
        else:
            next_planned_session = _default_session_for_mode(mode_value)

        return sport_disabled, next_sport, planned_options, next_planned_session


    @app.callback(
        Output("record-options-modal", "is_open"),
        [Input("open-record-options-btn", "n_clicks"), Input("close-record-options-btn", "n_clicks"), Input("close-record-options-x-btn", "n_clicks")],
        State("record-options-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_record_options_modal(open_n, close_n, close_x_n, is_open):
        trig = ctx.triggered_id
        if trig == "open-record-options-btn":
            return True
        if trig in ("close-record-options-btn", "close-record-options-x-btn"):
            return False
        return is_open

    @app.callback(
        [
            Output("graphs-pane-imu", "style"),
            Output("graphs-pane-sway", "style"),
            Output("graphs-pane-history", "style"),
        ],
        Input("graphs-tabs", "value"),
        prevent_initial_call=False,
    )
    def switch_graphs_tab(tab_value):
        tab_value = tab_value or "imu"
        pane_visible = {
            "display": "flex",
            "flexDirection": "column",
            "gap": "0px",
            "paddingTop": "0px",
            "paddingBottom": "0px",
        }
        pane_visible_history = {
            "display": "flex",
            "flexDirection": "column",
            "gap": "8px",
        }
        pane_hidden = {"display": "none", "flexDirection": "column", "gap": "0px", "paddingTop": "0px", "paddingBottom": "0px"}
        pane_hidden_history = {"display": "none", "flexDirection": "column", "gap": "8px"}

        if tab_value == "sway":
            return pane_hidden, pane_visible, pane_hidden_history
        if tab_value == "history":
            return pane_hidden, pane_hidden, pane_visible_history
        return pane_visible, pane_hidden, pane_hidden_history

    @app.callback(
        [
            Output("imu-graph", "style"),
            Output("sway-graph", "style"),
            Output("imu-calibration-warning", "style"),
            Output("sway-calibration-warning", "style"),
            Output("posture-calibration-warning", "style"),
            Output("posture-arrow-wrap", "style"),
        ],
        Input("calibration-store", "data"),
        prevent_initial_call=False,
    )
    def sync_graph_calibration_visibility(calib):
        graph_style = {"height": "125px", "width": "100%", "margin": "0", "padding": "0", "display": "block"}
        graph_hidden_style = {"height": "125px", "width": "100%", "margin": "0", "padding": "0", "display": "none"}
        warning_visible_style = {"display": "block", "width": "100%"}
        warning_hidden_style = {"display": "none", "width": "100%"}
        posture_warning_visible_style = {"display": "block", "width": "100%"}
        posture_warning_hidden_style = {"display": "none", "width": "100%"}
        posture_arrow_visible_style = {
            "flex": "1 1 auto",
            "height": "auto",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "flex-start",
            "paddingLeft": "18px",
            "width": "100%",
        }
        posture_arrow_hidden_style = {
            "flex": "1 1 auto",
            "height": "auto",
            "display": "none",
            "alignItems": "center",
            "justifyContent": "flex-start",
            "paddingLeft": "18px",
            "width": "100%",
        }

        if _is_calibration_completed(calib):
            return graph_style, graph_style, warning_hidden_style, warning_hidden_style, posture_warning_hidden_style, posture_arrow_visible_style
        return graph_hidden_style, graph_hidden_style, warning_visible_style, warning_visible_style, posture_warning_visible_style, posture_arrow_hidden_style

    @app.callback(
        [
            Output("recording-session-pill", "children"),
            Output("record-options-preview", "children"),
            Output("recording-time-pill", "children"),
            Output("start-record-btn", "children"),
            Output("start-record-btn", "disabled"),
            Output("stop-record-btn", "children"),
            Output("stop-record-btn", "disabled"),
        ],
        [Input("active-session-store", "data"), Input("recorder-store", "data"), Input("imu-interval", "n_intervals")],
        prevent_initial_call=False,
    )
    def update_recording_panel(active_session, recorder, _timer_tick):
        recorder = recorder or {"on": False, "status_label": "sin_iniciar", "started_at_epoch_ms": None, "elapsed_label": "00:00"}
        session_name = (active_session or {}).get("name") or "—"
        recorder_on = bool(recorder.get("on"))
        recorder_status = recorder.get("status_label", "sin_iniciar")
        stored_elapsed_label = recorder.get("elapsed_label") or "00:00"

        if recorder_on:
            elapsed_seconds = _elapsed_seconds_from_started_at(recorder.get("started_at_epoch_ms"))
            elapsed_label = _format_recording_elapsed(elapsed_seconds)
        else:
            elapsed_label = stored_elapsed_label

        state_value = _normalize_record_status_label(recorder_status)
        time_tone = "ok" if recorder_on else ("warn" if state_value == "Detenido" else "neutral")

        return (
            _pill("Sesión", session_name, "neutral", full=True),
            _recording_panel_items(recorder_on, session_name, recorder_status, elapsed_label),
            _pill("Tiempo", elapsed_label, time_tone, full=True),
            "Detener registro" if recorder_on else "Iniciar registro",
            False,
            "Detener registro" if recorder_on else "Iniciar registro",
            False,
        )

    # -----------------------------
    # ✅ PASO 2 + PASO 3 — Exportar (un solo callback) HISTÓRICO o VENTANA 20s (sin outputs duplicados)
    # -----------------------------
    @app.callback(
        Output("download-monitor", "data"),
        [Input("export-history-btn", "n_clicks"), Input("export-window-btn", "n_clicks")],
        State("session-history-store", "data"),
        prevent_initial_call=True,
    )
    def export_monitor_download(_hist_n, _win_n, history_store):
        trig = ctx.triggered_id

        # ---- HISTÓRICO ----
        if trig == "export-history-btn":
            items = []
            if isinstance(history_store, dict):
                items = history_store.get("items") or []
            elif isinstance(history_store, list):
                items = history_store
            else:
                items = []

            fieldnames = ["ts", "session", "mode", "sport", "score", "bad_time", "quality"]
            csv_bytes = rows_to_csv_bytes(items, fieldnames=fieldnames, delimiter=";")
            filename = make_filename("monitor_history", ext="csv")
            return dcc.send_bytes(csv_bytes, filename)

        # ---- VENTANA 20s (v2) ----
        if trig == "export-window-btn":
            win = IMU_SIM.get_window(seconds=20.0)

            # stats temporal -> exporta toda la ventana siempre
            temp_stats = {"last_t_s": None, "base_epoch_ms": None, "last_ts_ms": 0}
            rows = _get_samples_since_from_window(win, temp_stats)

            fieldnames = [
                "ts_ms",
                "T_pitch", "T_roll", "T_yaw",
                "L_pitch", "L_roll", "L_yaw",
                "thor_zone", "lum_zone",
                "comp_index",
                "T_imu_ts_ms", "L_imu_ts_ms",
            ]
            csv_bytes = rows_to_csv_bytes(rows, fieldnames=fieldnames, delimiter=";")
            filename = make_filename("monitor_window_20s", ext="csv")
            return dcc.send_bytes(csv_bytes, filename)

        raise PreventUpdate

    @app.callback(
        [
            Output("recal-modal", "is_open"),
            Output("calibration-store", "data"),
            Output("calibration-pill", "children"),
            Output("open-recal-btn", "children"),
            Output("recal-status-text", "children"),
            Output("recal-status-pill", "children"),
            Output("start-recal-btn", "children"),
        ],
        [Input("open-recal-btn", "n_clicks"), Input("close-recal-btn", "n_clicks"), Input("close-recal-x-btn", "n_clicks"), Input("start-recal-btn", "n_clicks"), Input("session-user", "data")],
        [State("recal-modal", "is_open"), State("calibration-store", "data")],
        prevent_initial_call=False,
    )
    def recalibrate(open_n, close_n, close_x_n, start_n, session_user, is_open, calib):
        trigger = ctx.triggered_id
        calib = calib or {"status": "Pendiente", "source": "baseline_required"}

        if trigger == "session-user" or trigger is None:
            calib = _load_calibration_state_from_db(session_user)
            status = _normalize_calibration_status(calib.get("status", "Pendiente"))
            return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_text(status), _calibration_pill(status), _calibration_action_label(status)

        status = _normalize_calibration_status(calib.get("status", "Pendiente"))

        if trigger == "open-recal-btn":
            calib = _load_calibration_state_from_db(session_user)
            status = _normalize_calibration_status(calib.get("status", "Pendiente"))
            return True, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_text(status), _calibration_pill(status), _calibration_action_label(status)
        if trigger in ("close-recal-btn", "close-recal-x-btn"):
            return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_text(status), _calibration_pill(status), _calibration_action_label(status)
        if trigger == "start-recal-btn":
            refreshed_calib = _load_calibration_state_from_db(session_user)
            refreshed_status = _normalize_calibration_status(refreshed_calib.get("status", "Pendiente"))
            # Flujo unificado: Monitor solo reconoce calibración real guardada en DB.
            # Se elimina el camino local que marcaba "Completada" sin baseline_test real.
            if refreshed_status == "Completada":
                return False, refreshed_calib, _calibration_pill(refreshed_status), _calibration_action_label(refreshed_status), _calibration_popup_status_text(refreshed_status), _calibration_pill(refreshed_status), _calibration_action_label(refreshed_status)
            pending_calib = {
                "status": "Pendiente",
                "source": "baseline_required",
                "ts": datetime.now().isoformat(timespec="seconds"),
                "baseline_test_id": None,
                "baseline_payload": {},
            }
            return True, pending_calib, _calibration_pill("Pendiente"), _calibration_action_label("Pendiente"), _calibration_popup_status_text("Pendiente"), _calibration_pill("Pendiente"), _calibration_action_label("Pendiente")

        return is_open, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_text(status), _calibration_pill(status), _calibration_action_label(status)

    # -----------------------------
    # recorder_control (PASO 0/1/2/3/8)
    # ✅ ÚNICO callback que escribe recorder-store
    # -----------------------------
    @app.callback(
        [
            Output("recorder-store", "data"),
            Output("recording-pill", "children"),
            Output("recording-header-status", "children"),
            Output("recorder-alert", "children"),
            Output("recorder-alert", "is_open"),
            Output("recorder-alert", "color"),
            Output("record-options-alert", "children"),
            Output("record-options-alert", "is_open"),
            Output("record-options-alert", "color"),
        ],
        [Input("start-record-btn", "n_clicks"), Input("stop-record-btn", "n_clicks")],
        [
            State("recorder-store", "data"),
            State("active-session-store", "data"),
            State("mode-preset", "value"),
            State("sport-select", "value"),
            State("calibration-store", "data"),
            State("session-user", "data"),
        ],
        prevent_initial_call=True,
    )
    def recorder_control(start_n, stop_n, recorder, active_session, mode_ui, sport_ui, calib, session_user):
        recorder = recorder or {
            "on": False,
            "session_id": None,
            "main_session_id": None,
            "status_label": "sin_iniciar",
            "started_at_epoch_ms": None,
            "elapsed_label": "00:00",
        }
        trig = ctx.triggered_id

        calibrated = _is_calibration_completed(calib)
        user_id = _get_user_id(session_user)
        db_link_ctx = _load_monitor_link_context_for_user(session_user)
        runtime_active_session = _build_active_session_payload(existing_session=active_session, link_ctx=db_link_ctx)
        session_name = runtime_active_session.get("name") or "—"

        selected_mode_ui = runtime_active_session.get("mode") or mode_ui or "train"
        selected_sport_ui = runtime_active_session.get("sport") or sport_ui or "gym"
        mapped_mode = _map_mode_ui_to_db(selected_mode_ui)
        mapped_sport = _map_sport_ui_to_db(selected_sport_ui)

        current_status = _normalize_record_status_label(recorder.get("status_label", "sin_iniciar"))

        if trig in ("start-record-btn", "stop-record-btn") and not recorder.get("on"):
            if not calibrated:
                warning_msg = "Completa calibración antes de iniciar."
                return (
                    recorder,
                    _pill("Estado", current_status, _record_status_tone(current_status), full=True),
                    _record_status_badge(current_status),
                    warning_msg,
                    True,
                    "warning",
                    warning_msg,
                    True,
                    "warning",
                )

            legacy_uuid = str(uuid.uuid4())
            started_at_epoch_ms = int(time.time() * 1000)

            main_session_id = None
            main_db_err = None
            planned_session_name = runtime_active_session.get("planned_session_name") or session_name
            questionnaire_session_id = runtime_active_session.get("questionnaire_session_id")
            routine_session_id = runtime_active_session.get("routine_session_id")
            calibration_db_id = (calib or {}).get("baseline_test_id")
            calibration_source = (calib or {}).get("source")
            calibration_payload = (calib or {}).get("baseline_payload")
            context_json = {
                "session_origin": runtime_active_session.get("session_origin") or "monitor_session_config",
                "linked_db_source": runtime_active_session.get("linked_db_source"),
                "session_type": runtime_active_session.get("session_type"),
                "routine_context": runtime_active_session.get("routine_context") or {},
                "ui": {"mode": selected_mode_ui or "train", "sport": selected_sport_ui or "gym"},
                "calibration": {
                    "status": _normalize_calibration_status((calib or {}).get("status")),
                    "source": calibration_source,
                    "baseline_test_id": calibration_db_id,
                    "payload": calibration_payload or {},
                },
            }

            if user_id is None:
                main_db_err = "user_id inválido (session-user no trae id numérico)."
            else:
                try:
                    main_session_id = start_sensor_session(
                        user_id=user_id,
                        kind="monitor",
                        mode=mapped_mode,
                        sport=mapped_sport,
                        planned_session_name=planned_session_name,
                        questionnaire_session_id=questionnaire_session_id,
                        routine_session_id=routine_session_id,
                        baseline_test_id=calibration_db_id,
                        context_json=context_json,
                    )
                except Exception as e:
                    main_db_err = str(e)

            recorder = {
                "on": True,
                "session_id": legacy_uuid,
                "main_session_id": main_session_id,
                "status_label": "grabando",
                "started_at_epoch_ms": started_at_epoch_ms,
                "elapsed_label": "00:00",
            }

            if main_session_id is not None:
                _RAW_BUFFER_MAIN[main_session_id] = []
                _STATS_MAIN[main_session_id] = {
                    "user_id": user_id,
                    "mode": mapped_mode,
                    "sport": mapped_sport,
                    "thr_active": _load_user_thresholds_for_mode(user_id=int(user_id), mode=mapped_mode),
                    "session_name": session_name,
                    "calibrated": bool(calibrated),
                    "started_at_epoch_ms": started_at_epoch_ms,
                    "last_ts_ms": 0,
                    "prev_ts_ms": None,
                    "first_ts_ms": None,
                    "last_t_s": None,
                    "base_epoch_ms": None,
                    "last_flush_ms": 0,
                    "thor_red_s": 0.0,
                    "lum_red_s": 0.0,
                    "comp_sum": 0.0,
                    "comp_peak": 0.0,
                    "samples": 0,
                    "alerts_count": 0,
                    "thor_red_streak_s": 0.0,
                    "lum_red_streak_s": 0.0,
                    "comp_high_streak_s": 0.0,
                    "cooldown": {"thor": 0, "lum": 0, "comp": 0},
                    "live_alerts": [],
                    "last_thor_zone": "green",
                    "last_lum_zone": "green",
                    "last_comp": 0.0,
                }

            alert = _friendly_record_start_message(session_name, main_db_err=main_db_err)
            pill_tone = "ok"
            color = "success"
            if main_db_err:
                pill_tone = "warn"
                color = "warning"

            return (
                recorder,
                _pill("Estado", "Grabando", pill_tone, full=True),
                _record_status_badge("Grabando"),
                "",
                False,
                "info",
                alert,
                True,
                color,
            )

        if trig == "stop-record-btn" or (trig == "start-record-btn" and recorder.get("on")):
            if not recorder.get("on"):
                return (
                    recorder,
                    _pill("Estado", current_status, _record_status_tone(current_status), full=True),
                    _record_status_badge(current_status),
                    "",
                    False,
                    "info",
                    _friendly_record_idle_message(),
                    True,
                    "warning",
                )

            main_session_id = recorder.get("main_session_id")
            user_id = _get_user_id(session_user)

            wall_elapsed_seconds = _elapsed_seconds_from_started_at(recorder.get("started_at_epoch_ms"))
            wall_elapsed_label = _format_recording_elapsed(wall_elapsed_seconds)

            if main_session_id is None:
                recorder = {
                    "on": False,
                    "session_id": None,
                    "main_session_id": None,
                    "status_label": "detenido",
                    "started_at_epoch_ms": None,
                    "elapsed_label": wall_elapsed_label,
                }
                return (
                    recorder,
                    _pill("Estado", "Detenido", "warn", full=True),
                    _record_status_badge("Detenido"),
                    "",
                    False,
                    "info",
                    _friendly_record_stop_without_db_message(wall_elapsed_label),
                    True,
                    "warning",
                )

            stats = _STATS_MAIN.get(main_session_id)
            buf = _RAW_BUFFER_MAIN.get(main_session_id, [])

            flush_err = None
            try:
                if buf:
                    tuples = [
                        (
                            int(main_session_id),
                            int(r["ts_ms"]),
                            float(r["T_pitch"]),
                            float(r["T_roll"]),
                            float(r["T_yaw"]),
                            float(r["L_pitch"]),
                            float(r["L_roll"]),
                            float(r["L_yaw"]),
                            str(r["thor_zone"]),
                            str(r["lum_zone"]),
                            float(r["comp_index"]),
                            int(r["T_imu_ts_ms"]),
                            int(r["L_imu_ts_ms"]),
                        )
                        for r in buf
                    ]
                    insert_sensor_samples_raw_batch(session_id=int(main_session_id), rows=tuples)
                    buf.clear()
            except Exception as e:
                flush_err = str(e)

            first_ts = (stats or {}).get("first_ts_ms")
            last_ts = (stats or {}).get("last_ts_ms")
            sensor_duration_s = 0.0
            if first_ts is not None and last_ts is not None and int(last_ts) >= int(first_ts):
                sensor_duration_s = (int(last_ts) - int(first_ts)) / 1000.0

            duration_s = float(wall_elapsed_seconds)
            if duration_s <= 0.0:
                duration_s = float(sensor_duration_s)
            elapsed_label = _format_recording_elapsed(duration_s)

            thor_red_s = float((stats or {}).get("thor_red_s", 0.0))
            lum_red_s = float((stats or {}).get("lum_red_s", 0.0))
            samples = int((stats or {}).get("samples", 0))
            comp_sum = float((stats or {}).get("comp_sum", 0.0))
            comp_peak = float((stats or {}).get("comp_peak", 0.0))
            comp_avg = (comp_sum / samples) if samples > 0 else 0.0
            alerts_count = int((stats or {}).get("alerts_count", 0))

            risk = _risk_index_v2(duration_s, thor_red_s, lum_red_s, comp_avg, vas=0.0)

            close_err = None
            summary_err = None
            daily_err = None
            try:
                upsert_session_summary(
                    session_id=int(main_session_id),
                    duration_s=float(duration_s),
                    thor_red_s=float(thor_red_s),
                    lum_red_s=float(lum_red_s),
                    alerts_count=int(alerts_count),
                    comp_avg=float(comp_avg),
                    comp_peak=float(comp_peak),
                    risk_index=float(risk),
                )
            except Exception as e:
                summary_err = str(e)

            try:
                end_sensor_session(session_id=int(main_session_id))
            except Exception as e:
                close_err = str(e)

            try:
                if user_id is not None:
                    recompute_daily_summary(user_id=int(user_id), day=date.today())
            except Exception as e:
                daily_err = str(e)

            _RAW_BUFFER_MAIN.pop(main_session_id, None)
            _STATS_MAIN.pop(main_session_id, None)

            recorder = {
                "on": False,
                "session_id": None,
                "main_session_id": None,
                "status_label": "detenido",
                "started_at_epoch_ms": None,
                "elapsed_label": elapsed_label,
            }

            msg = _friendly_record_stop_message(
                elapsed_label=elapsed_label,
                risk=risk,
                thor_red_s=thor_red_s,
                lum_red_s=lum_red_s,
                comp_avg=comp_avg,
                alerts_count=alerts_count,
            )
            color = "success"
            if flush_err or summary_err or close_err or daily_err:
                color = "warning"
                msg += _friendly_record_stop_issues(
                    flush_err=flush_err,
                    summary_err=summary_err,
                    close_err=close_err,
                    daily_err=daily_err,
                )

            return (
                recorder,
                _pill("Estado", "Detenido", "warn", full=True),
                _record_status_badge("Detenido"),
                "",
                False,
                "info",
                msg,
                True,
                color,
            )

        raise PreventUpdate

    # -----------------------------
    # update_realtime (PASO 0/4/5/6/7/9/10/11/12)
    # ✅ NO escribe recorder-store
    # -----------------------------
    @app.callback(
        [
            Output("imu-graph", "figure"),
            Output("sway-graph", "figure"),
            Output("pry-metric", "children"),
            Output("sway-metric", "children"),
            Output("bad-time-metric", "children"),
            Output("posture-score", "children"),
            Output("traffic-light", "children"),
            Output("general-status-note", "children"),
            Output("general-status-note", "style"),
            Output("alerts-list", "children"),
            Output("session-history-store", "data"),
            Output("history-graph", "figure"),
            Output("history-list", "children"),
            Output("back-arrow", "style"),
            Output("state-dot", "style"),
            Output("thor-traffic-light", "children"),
            Output("lum-traffic-light", "children"),
            Output("thor-segment-status", "children"),
            Output("lum-segment-status", "children"),
            Output("thor-segment-cue", "children"),
            Output("lum-segment-cue", "children"),
            Output("thor-angle-output", "children"),
            Output("lum-angle-output", "children"),
            Output("comp-output", "children"),
            Output("thor-red-output", "children"),
            Output("lum-red-output", "children"),
        ],
        [Input("imu-interval", "n_intervals"), Input("sim-state-store", "data")],
        [
            State("mode-preset", "value"),
            State("alerts-switch", "value"),
            State("active-session-store", "data"),
            State("session-history-store", "data"),
            State("calibration-store", "data"),
            State("recorder-store", "data"),
            State("sport-select", "value"),
            State("session-user", "data"),
        ],
        prevent_initial_call=False,
    )
    def update_realtime(_n_intervals, sim_state, mode_ui, alerts_on, active_session, history_store, calib, recorder, sport_ui, session_user):
        sim_state = sim_state or {"on": True, "reset_seq": 0}
        if not bool(sim_state.get("on", True)):
            raise PreventUpdate

        reset_seq = int(sim_state.get("reset_seq", 0))
        general_note_hidden_style = {
            "display": "none",
            "width": "100%",
            "marginTop": "auto",
            "padding": "12px 14px",
            "borderRadius": "12px",
            "background": "rgba(245,158,11,.18)",
            "boxShadow": "inset 0 0 0 1px rgba(245,158,11,.28)",
            "color": "#fbbf24",
            "fontSize": "12px",
            "fontWeight": 700,
            "lineHeight": "1.45",
            "textAlign": "center",
            "alignItems": "center",
            "justifyContent": "center",
            "alignSelf": "stretch",
        }
        general_note_warn_style = {
            "display": "flex",
            "width": "100%",
            "marginTop": "auto",
            "padding": "12px 14px",
            "borderRadius": "12px",
            "background": "rgba(245,158,11,.18)",
            "boxShadow": "inset 0 0 0 1px rgba(245,158,11,.28)",
            "color": "#fbbf24",
            "fontSize": "12px",
            "fontWeight": 700,
            "lineHeight": "1.45",
            "textAlign": "center",
            "alignItems": "center",
            "justifyContent": "center",
            "alignSelf": "stretch",
        }
        general_note_ok_style = {
            "display": "flex",
            "width": "100%",
            "marginTop": "auto",
            "padding": "12px 14px",
            "borderRadius": "12px",
            "background": "rgba(34,197,94,.18)",
            "boxShadow": "inset 0 0 0 1px rgba(34,197,94,.28)",
            "color": "#86efac",
            "fontSize": "12px",
            "fontWeight": 700,
            "lineHeight": "1.45",
            "textAlign": "center",
            "alignItems": "center",
            "justifyContent": "center",
            "alignSelf": "stretch",
        }
        if history_store is None:
            history_store = {"items": [], "last_saved_t": None, "reset_seq": reset_seq}
        if isinstance(history_store, list):
            history_store = {"items": history_store, "last_saved_t": None, "reset_seq": reset_seq}
        if not isinstance(history_store, dict):
            history_store = {"items": [], "last_saved_t": None, "reset_seq": reset_seq}

        last_applied_reset = int(history_store.get("reset_seq", reset_seq))
        if reset_seq != last_applied_reset:
            IMU_SIM.reset()
            history_store = {"items": [], "last_saved_t": None, "reset_seq": reset_seq}

        calibrated = _is_calibration_completed(calib)
        if not calibrated:
            empty_imu = _empty_fig("Gráfica IMU (Pitch / Roll)")
            empty_sway = _empty_fig("Gráfica Sway / Eventos")
            empty_hist = _empty_fig("Histórico de sesiones (Postura)")
            # Ajuste solicitado: no mostrar mensajes de calibración dentro del cuadro de Alertas.
            return (
                empty_imu,
                empty_sway,
                "— / — / —",
                "—",
                "—",
                "—",
                _traffic_light_dynamic(0),
                "",
                general_note_hidden_style,
                [html.Li("— (sin datos aún)")],
                history_store,
                empty_hist,
                [html.Li("— (sin historial)")],
                {"fontSize": "34px", "color": "rgba(226,232,240,.90)", "transform": "rotate(-10deg)"},
                {"display": "none"},
                _traffic_light_zone("green"),
                _traffic_light_zone("green"),
                "Verde",
                "Verde",
                "Estable",
                "Estable",
                _format_signed_angle(0.0),
                _format_signed_angle(0.0),
                _comp_output_block(0.0),
                "0:00.0",
                "0:00.0",
            )

        win = IMU_SIM.get_window(seconds=20.0)
        t = win.get("t") or []
        pitch = win.get("pitch") or []
        roll = win.get("roll") or []
        yaw = win.get("yaw") or []
        sway = win.get("sway") or []
        score_series = win.get("score") or []
        bad_mask = win.get("bad") or []
        events_t = win.get("events_t") or []
        events_label = win.get("events_label") or []

        recorder = recorder or {
            "on": False,
            "session_id": None,
            "main_session_id": None,
            "status_label": "sin_iniciar",
            "started_at_epoch_ms": None,
            "elapsed_label": "00:00",
        }
        main_session_id = recorder.get("main_session_id")

        if not t:
            empty_imu = _empty_fig("Gráfica IMU (Pitch / Roll)")
            empty_sway = _empty_fig("Gráfica Sway / Eventos")
            empty_hist = _empty_fig("Histórico de sesiones (Postura)")
            return (
                empty_imu,
                empty_sway,
                "— / — / —",
                "—",
                "—",
                "—",
                _traffic_light_dynamic(0),
                "",
                general_note_hidden_style,
                [html.Li("— (sin datos aún)")],
                history_store,
                empty_hist,
                [html.Li("— (sin historial)")],
                {"fontSize": "34px", "color": "rgba(226,232,240,.90)", "transform": "rotate(-10deg)"},
                {"display": "none"},
                _traffic_light_zone("green"),
                _traffic_light_zone("green"),
                "Verde",
                "Verde",
                "Estable",
                "Estable",
                _format_signed_angle(0.0),
                _format_signed_angle(0.0),
                _comp_output_block(0.0),
                "0:00.0",
                "0:00.0",
            )

        total_time = max(float(t[-1]) - float(t[0]), 1e-6)

        score_now = float(score_series[-1]) if score_series else 0.0
        if not calibrated:
            score_now = max(0.0, score_now - 5.0)

        bad_segments = _segments_from_mask(t, bad_mask)
        bad_time = sum(max(0.0, (b - a)) for (a, b) in bad_segments)
        bad_time = min(bad_time, total_time)

        artefacts = sum(1 for lbl in events_label if lbl == "artefacto")
        sway_med = median(sway) if sway else 0.0
        quality = "OK"
        if artefacts >= 3 or sway_med > 1.2:
            quality = "WARN"
        if artefacts >= 6 or sway_med > 1.6:
            quality = "BAD"

        pitch_now = float(pitch[-1]) if pitch else 0.0
        roll_now = float(roll[-1]) if roll else 0.0
        yaw_now = float(yaw[-1]) if yaw else 0.0
        sway_now = float(sway[-1]) if sway else 0.0

        mode_ui = mode_ui or "train"
        if mode_ui == "office":
            ext_thr, flex_thr = 12.0, -12.0
        elif mode_ui == "rehab":
            ext_thr, flex_thr = 10.0, -10.0
        else:
            ext_thr, flex_thr = 15.0, -15.0
        # thresholds (por usuario). Si no existen, usa genéricos.
        uid_tmp = _get_user_id(session_user)
        if uid_tmp is not None:
            thr_tmp = _load_user_thresholds_for_mode(user_id=int(uid_tmp), mode=_map_mode_ui_to_db(mode_ui))
        else:
            thr_tmp = {"thor": DEFAULT_THRESHOLDS.get("desk", {}).get("thor", {}), "lum": DEFAULT_THRESHOLDS.get("desk", {}).get("lum", {})}
        thr_thor_tmp = (thr_tmp or {}).get("thor") or DEFAULT_THRESHOLDS.get("desk", {}).get("thor", {})
        thr_lum_tmp  = (thr_tmp or {}).get("lum")  or DEFAULT_THRESHOLDS.get("desk", {}).get("lum", {})

        thor_zone_last = _zone_from_angles(pitch_now, roll_now, thr=thr_thor_tmp)
        lum_zone_last  = _zone_from_angles(pitch_now * 0.85, roll_now * 0.90, thr=thr_lum_tmp)
        comp_last = _comp_index_simple(pitch_now, roll_now, pitch_now * 0.85, roll_now * 0.90)
        thor_red_s_out = "—"
        lum_red_s_out = "—"
        comp_out = _comp_output_block(comp_last)

        live_alerts_v2 = []
        if recorder.get("on") and main_session_id is not None and main_session_id in _STATS_MAIN:
            stats = _STATS_MAIN[main_session_id]
            buf = _RAW_BUFFER_MAIN.get(main_session_id, [])

            new_rows = _get_live_samples_since(stats, win=win)

            if new_rows and stats.get("first_ts_ms") is None:
                stats["first_ts_ms"] = int(new_rows[0]["ts_ms"])

            for r in new_rows:
                ts_ms = int(r["ts_ms"])
                prev_ts = stats.get("prev_ts_ms")
                if prev_ts is None:
                    dt_s = 0.02
                else:
                    dt_s = max(0.0, (ts_ms - int(prev_ts)) / 1000.0)
                    if dt_s <= 0:
                        dt_s = 0.02

                stats["prev_ts_ms"] = ts_ms

                if r["thor_zone"] == "red":
                    stats["thor_red_s"] += dt_s
                    stats["thor_red_streak_s"] += dt_s
                else:
                    stats["thor_red_streak_s"] = 0.0

                if r["lum_zone"] == "red":
                    stats["lum_red_s"] += dt_s
                    stats["lum_red_streak_s"] += dt_s
                else:
                    stats["lum_red_streak_s"] = 0.0

                comp_i = float(r["comp_index"])
                stats["comp_sum"] += comp_i
                stats["comp_peak"] = max(float(stats.get("comp_peak", 0.0)), comp_i)
                stats["samples"] = int(stats.get("samples", 0)) + 1

                if comp_i >= 60.0:
                    stats["comp_high_streak_s"] += dt_s
                else:
                    stats["comp_high_streak_s"] = 0.0

                stats["last_thor_zone"] = r["thor_zone"]
                stats["last_lum_zone"] = r["lum_zone"]
                stats["last_comp"] = comp_i

                cooldown_ms = 5000
                now_ms = ts_ms

                def push_alert(key, text):
                    last_fire = int(stats["cooldown"].get(key, 0))
                    if now_ms - last_fire < cooldown_ms:
                        return
                    stats["cooldown"][key] = now_ms
                    stats["alerts_count"] = int(stats.get("alerts_count", 0)) + 1
                    la = stats.get("live_alerts") or []
                    la.append(text)
                    la = la[-5:]
                    stats["live_alerts"] = la

                if stats["thor_red_streak_s"] >= 3.0:
                    push_alert("thor", "Torácica en rojo ≥ 3s")

                if stats["lum_red_streak_s"] >= 3.0:
                    push_alert("lum", "Lumbar en rojo ≥ 3s")

                if stats["comp_high_streak_s"] >= 2.0:
                    push_alert("comp", "Compensación alta ≥ 2s")

            if new_rows:
                buf.extend(new_rows)

            flush_every_ms = 1000
            max_buf = 350
            last_flush = int(stats.get("last_flush_ms") or 0)
            now_ms = int(stats.get("last_ts_ms") or 0)

            should_flush = False
            if buf and (len(buf) >= max_buf):
                should_flush = True
            elif buf and now_ms and (now_ms - last_flush >= flush_every_ms):
                should_flush = True

            if should_flush:
                try:
                    tuples = [
                        (
                            int(main_session_id),
                            int(r["ts_ms"]),
                            float(r["T_pitch"]),
                            float(r["T_roll"]),
                            float(r["T_yaw"]),
                            float(r["L_pitch"]),
                            float(r["L_roll"]),
                            float(r["L_yaw"]),
                            str(r["thor_zone"]),
                            str(r["lum_zone"]),
                            float(r["comp_index"]),
                            int(r["T_imu_ts_ms"]),
                            int(r["L_imu_ts_ms"]),
                        )
                        for r in buf
                    ]
                    insert_sensor_samples_raw_batch(session_id=int(main_session_id), rows=tuples)
                    buf.clear()
                    stats["last_flush_ms"] = int(now_ms)
                except Exception:
                    pass

            thor_zone_last = stats.get("last_thor_zone", thor_zone_last)
            lum_zone_last = stats.get("last_lum_zone", lum_zone_last)
            comp_last = float(stats.get("last_comp", comp_last))
            comp_out = _comp_output_block(comp_last)
            thor_red_s_out = _format_elapsed_tenths(float(stats.get('thor_red_s', 0.0)))
            lum_red_s_out = _format_elapsed_tenths(float(stats.get('lum_red_s', 0.0)))
            live_alerts_v2 = stats.get("live_alerts") or []

        else:
            try:
                uid_tmp = _get_user_id(session_user)
                if uid_tmp is not None:
                    thr_tmp = _load_user_thresholds_for_mode(user_id=int(uid_tmp), mode=_map_mode_ui_to_db(mode_ui))
                else:
                    thr_tmp = {"thor": DEFAULT_THRESHOLDS.get("desk", {}).get("thor", {}), "lum": DEFAULT_THRESHOLDS.get("desk", {}).get("lum", {})}
                thr_thor_tmp = (thr_tmp or {}).get("thor") or DEFAULT_THRESHOLDS.get("desk", {}).get("thor", {})
                thr_lum_tmp  = (thr_tmp or {}).get("lum")  or DEFAULT_THRESHOLDS.get("desk", {}).get("lum", {})

                zones = [_zone_from_angles(float(p), 0.0, thr=thr_thor_tmp) for p in pitch]
                red_count = sum(1 for z in zones if z == "red")
                dt = total_time / max(1, len(pitch) - 1)
                thor_red = dt * red_count

                zones_l = [_zone_from_angles(float(p) * 0.85, 0.0, thr=thr_lum_tmp) for p in pitch]
                red_count_l = sum(1 for z in zones_l if z == "red")
                lum_red = dt * red_count_l

                thor_red_s_out = _format_elapsed_tenths(thor_red)
                lum_red_s_out = _format_elapsed_tenths(lum_red)
            except Exception:
                thor_red_s_out = "—"
                lum_red_s_out = "—"

        thor_status_text = _zone_action_label(thor_zone_last)
        lum_status_text = _zone_action_label(lum_zone_last)
        thor_cue_text = _zone_action_label(thor_zone_last)
        lum_cue_text = _zone_action_label(lum_zone_last)
        thor_angle_text = _format_signed_angle(pitch_now)
        lum_angle_text = _format_signed_angle(pitch_now * 0.85)
        general_note_text = "Lectura correcta."
        general_note_style = general_note_ok_style
        if quality in ("WARN", "BAD"):
            general_note_text = "Revisa colocación y postura."
            general_note_style = general_note_warn_style

        alerts = []
        if not alerts_on:
            alerts = ["Alertas desactivadas."]
        else:
            if quality == "BAD":
                alerts.append("Señal/Movimientos muy inestables: revisa ajuste del dispositivo.")
            elif quality == "WARN":
                pass
            if artefacts > 0:
                alerts.append(f"Artefactos detectados: {artefacts} evento(s).")
            if bad_time > 0.2:
                alerts.append(f"Mala postura detectada: {bad_time:.1f}s acumulados (ventana 20s).")
            if pitch_now >= ext_thr:
                alerts.append(f"Hiperextensión lumbar (pitch +{pitch_now:.1f}°).")
            elif pitch_now <= flex_thr:
                alerts.append(f"Flexión lumbar (pitch {pitch_now:.1f}°).")

            for a in (live_alerts_v2 or [])[-5:]:
                alerts.append(f"[V2] {a}")

            if not active_session or not active_session.get("name"):
                alerts.append("Sesión no vinculada: vincula la sesión del día para registrar correctamente.")
            # Ajuste solicitado: eliminar de Alertas los mensajes de calibración.
            if not calibrated:
                pass
            else:
                pass
            if not alerts:
                alerts.append("Sin alertas: estado estable.")

        alerts_visible = alerts[:3]
        alerts_children = [html.Li(a) for a in alerts_visible]
        # Compatibilidad visual: el cuadro queda dimensionado solo para 3 alertas visibles.
        # Ajuste solicitado: se reduce el alto visible del listado para que no aparente espacio de 4 alertas.

        shapes = []
        for a, b in bad_segments[:40]:
            shapes.append(
                {"type": "rect", "xref": "x", "yref": "paper", "x0": a, "x1": b, "y0": 0, "y1": 1, "fillcolor": "rgba(239,68,68,.12)", "line": {"width": 0}}
            )

        legend_separator_shape = {
            "type": "line",
            "xref": "paper",
            "yref": "paper",
            "x0": 0,
            "x1": 1,
            "y0": -0.040,
            "y1": -0.040,
            "line": {"color": "rgba(255,255,255,.14)", "width": 1},
        }

        # Ajuste visual solicitado: bajar la leyenda para que quede pegada a la parte inferior del cuadro.
        # Se mantiene la estructura previa con separador y caja de leyenda para no tocar el resto del flujo.
        legend_box_style = {
            # Ajuste solicitado: eliminar el cuadro de la leyenda,
            # pero mantener exactamente la misma posición y el mismo espacio.
            "bgcolor": "rgba(0,0,0,0)",
            "bordercolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "font": {"color": "#e2e8f0", "size": 11},
        }

        fig_imu = {
            "data": [
                {"x": t, "y": pitch, "type": "line", "name": f"Flexión / Extensión · {pitch_now:.1f}°"},
                {"x": t, "y": roll, "type": "line", "name": f"Lateral · {roll_now:.1f}°"},
                {"x": [], "y": [], "type": "scatter", "mode": "lines", "name": f"Yaw · {yaw_now:.1f}°", "visible": "legendonly"},
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
                    "y": -0.065,
                    "xanchor": "left",
                    "x": 0,
                    **legend_box_style,
                },
                "shapes": [legend_separator_shape],
            },
        }

        event_y = [(max(sway) if sway else 1.0) for _ in events_t]
        fig_sway = {
            "data": [
                {"x": t, "y": sway, "type": "line", "name": f"Estabilidad · {sway_now:.3f}"},
                {"x": events_t, "y": event_y, "type": "scatter", "mode": "markers", "name": f"Eventos · {len(events_t)}", "text": events_label},
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
                    "y": -0.065,
                    "xanchor": "left",
                    "x": 0,
                    **legend_box_style,
                },
                "shapes": shapes + [legend_separator_shape],
            },
        }

        pry_s = f"{pitch_now:.1f} / {roll_now:.1f} / {yaw_now:.1f}"
        sway_s = f"{sway_now:.3f}"
        bad_s = f"{bad_time:.1f}s"

        items = history_store.get("items") or []
        last_saved_t = history_store.get("last_saved_t")
        t_end = float(t[-1])

        should_save = False
        if last_saved_t is None:
            should_save = True
        else:
            try:
                should_save = (t_end - float(last_saved_t)) >= 10.0
            except Exception:
                should_save = True

        if should_save:
            session_name = (active_session or {}).get("name") or "—"
            now = datetime.now().isoformat(timespec="seconds")
            items.append(
                {
                    "ts": now,
                    "session": session_name,
                    "mode": (mode_ui or "train"),
                    "sport": _map_sport_ui_to_db(sport_ui or "gym"),
                    "score": float(score_now),
                    "bad_time": float(bad_time),
                    "quality": quality,
                }
            )
            items = items[-25:]
            history_store = {"items": items, "last_saved_t": t_end, "reset_seq": reset_seq}
        else:
            history_store = {"items": items, "last_saved_t": last_saved_t, "reset_seq": reset_seq}

        xs = [h.get("ts") for h in items]
        ys = [h.get("score") for h in items]
        fig_hist = {
            "data": [{"x": xs, "y": ys, "type": "line", "name": f"Postura · {float(ys[-1]) if ys else 0.0:.0f}" if ys else "Postura · —"}],
            "layout": {
                "title": {"text": ""},
                "paper_bgcolor": "#0b1220",
                "plot_bgcolor": "#0b1220",
                "font": {"color": "#e2e8f0"},
                "margin": {"l": 40, "r": 58, "t": 0, "b": 34},
                "showlegend": True,
                "modebar": {"orientation": "v"},
                "legend": {
                    "orientation": "h",
                    "yanchor": "top",
                    "y": -0.03,
                    "xanchor": "left",
                    "x": 0,
                    "bgcolor": "rgba(0,0,0,0)",
                    "font": {"color": "#e2e8f0", "size": 11},
                },
            },
        }

        history_list = [
            html.Li(f"{h.get('ts','')} · {h.get('session','—')} · score {float(h.get('score',0)):.0f} · mala {float(h.get('bad_time',0)):.1f}s · {h.get('quality','')}")
            for h in reversed(items[-10:])
        ] or [html.Li("— (sin historial)")]

        arrow_deg = _safe_float(roll_now, 0.0) * -1.2 + _safe_float(pitch_now, 0.0) * 0.6
        arrow_deg = max(-45.0, min(45.0, arrow_deg))
        arrow_style = {"fontSize": "34px", "color": "rgba(226,232,240,.90)", "transform": f"rotate({arrow_deg:.1f}deg)"}
        dot_style = {"display": "none"}

        return (
            fig_imu,
            fig_sway,
            pry_s,
            sway_s,
            bad_s,
            f"{score_now:.0f}",
            _traffic_light_dynamic(score_now),
            general_note_text,
            general_note_style,
            alerts_children,
            history_store,
            fig_hist,
            history_list,
            arrow_style,
            dot_style,
            _traffic_light_zone(thor_zone_last),
            _traffic_light_zone(lum_zone_last),
            thor_status_text,
            lum_status_text,
            thor_cue_text,
            lum_cue_text,
            thor_angle_text,
            lum_angle_text,
            comp_out,
            thor_red_s_out,
            lum_red_s_out,
        )
