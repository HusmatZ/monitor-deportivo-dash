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
import csv
import io
import json

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
    get_latest_baseline_reference,
    get_latest_baseline_reference_for_ui,
    get_latest_baseline_history_legacy_fields,
    normalize_baseline_reference_for_ui,
    empty_baseline_history_reference,
    get_monitor_link_context,
    create_baseline_test,
    list_baseline_tests_for_user,
    get_user_by_id,
    get_daily_summary,
    get_latest_questionnaire_session,
    list_recent_sensor_sessions_for_user,
    list_daily_summaries_for_user,
    list_routine_sessions_for_user,
    list_exercise_sets_for_user,
    list_sensor_raw_samples_for_user,
    list_sensor_agg_samples_for_user,
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

RESPONSIVE_SECTION_TITLE_STYLE = {
    "fontSize": "clamp(12px, 1vw, 16px)",
    "lineHeight": "1.2",
    "whiteSpace": "normal",
    "overflowWrap": "anywhere",
}



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
    session_ok = bool(calib.get("valid_for_current_session"))
    baseline_ok = bool(calib.get("baseline_test_id"))
    return bool(status_ok and session_ok and baseline_ok)


def _is_calibration_valid_for_auth_session(calib, session_user=None, auth_session=None) -> bool:
    calib = _normalize_calibration_store(calib)
    active = _get_active_calibration(calib)
    auth_session = auth_session if isinstance(auth_session, dict) else {}
    if auth_session.get("logged_out"):
        return False

    user_id = _get_user_id(session_user)
    session_scope_id = auth_session.get("session_scope_id")
    if user_id is None or not session_scope_id:
        return False

    try:
        calibration_user_id = int(active.get("calibration_user_id"))
    except Exception:
        return False

    login_session_id = _get_login_session_id(session_user)
    calibration_login_session_id = active.get("login_session_id")
    if login_session_id and calibration_login_session_id and str(calibration_login_session_id) != str(login_session_id):
        return False

    return bool(
        _normalize_calibration_status(active.get("status")) == "Completada"
        and bool(active.get("valid_for_current_session"))
        and bool(active.get("baseline_test_id"))
        and calibration_user_id == int(user_id)
        and str(active.get("session_scope_id") or "") == str(session_scope_id)
    )


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
        "goal": link_ctx.get("goal") or "",
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
    goal_value = existing_session.get("goal")
    if goal_value is None:
        goal_value = link_ctx_norm.get("goal")

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
        "goal": goal_value or "",
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
            "goal": goal_value or "",
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


def _score_tone(score: float):
    try:
        score = max(0.0, min(100.0, float(score or 0.0)))
    except Exception:
        score = 0.0
    if score >= 80:
        return "ok"
    if score >= 50:
        return "warn"
    return "bad"


def _posture_score_gauge(score: float, pending: bool = False):
    try:
        score_val = max(0.0, min(100.0, float(score or 0.0)))
        score_text = f"{score_val:.0f}"
    except Exception:
        score_val = 0.0
        score_text = "—"
    tone = "empty" if pending else _score_tone(score_val)
    tone_color = {
        "empty": "#64748b",
        "ok": "#22c55e",
        "warn": "#f59e0b",
        "bad": "#ef4444",
    }.get(tone, "#3b82f6")
    return html.Div(
        className=f"ax-posture-score-gauge ax-posture-score-gauge--{tone}",
        style={"--score": f"{score_val:.1f}", "--score-color": tone_color},
        children=[
            html.Span(score_text, className="ax-posture-score-gauge-value"),
        ],
    )


def _empty_status_light():
    def dot():
        return html.Div(
            className="ax-status-light-dot ax-status-light-dot--empty",
            style={
                "width": "7px",
                "height": "7px",
                "borderRadius": "999px",
                "background": "rgba(148,163,184,.45)",
                "opacity": 0.35,
                "boxShadow": "0 0 0 1px rgba(255,255,255,.08)",
            },
        )

    return html.Div(
        className="ax-status-light ax-status-light--empty",
        style={"display": "flex", "gap": "4px", "alignItems": "center"},
        children=[dot(), dot(), dot()],
    )


def _empty_inclination_status():
    return html.Div(
        className="ax-inclination-status ax-inclination-status--empty",
        style={"display": "flex", "gap": "4px", "alignItems": "center"},
        children=[
            html.Span("●", className="ax-inclination-status-dot"),
            html.Span("Pendiente", className="ax-inclination-status-label"),
            _empty_status_light(),
        ],
    )


def _traffic_light_dynamic(score: float):
    g = 1.0 if score >= 80 else 0.25
    y = 1.0 if 50 <= score < 80 else 0.25
    r = 1.0 if score < 50 else 0.25
    tone = _score_tone(score)
    label = {"ok": "Estable", "warn": "Atención", "bad": "Riesgo"}.get(tone, "Estable")

    def dot(color, alpha):
        return html.Div(
            className="ax-status-light-dot",
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
        className=f"ax-inclination-status ax-inclination-status--{tone}",
        style={"display": "flex", "gap": "4px", "alignItems": "center"},
        children=[
            html.Span("●", className="ax-inclination-status-dot"),
            html.Span(label, className="ax-inclination-status-label"),
            html.Div(
                className="ax-status-light",
                children=[
                    dot("rgba(34,197,94,.95)", g),
                    dot("rgba(245,158,11,.95)", y),
                    dot("rgba(239,68,68,.95)", r),
                ],
            ),
        ],
    )


def _traffic_light_zone(zone: str):
    """Semáforo por zona: green/yellow/red."""
    zone = (zone or "").lower()
    if zone in ("", "empty", "pending", "none", "off"):
        return _empty_status_light()
    g = 1.0 if zone == "green" else 0.25
    y = 1.0 if zone == "yellow" else 0.25
    r = 1.0 if zone == "red" else 0.25

    def dot(color, alpha):
        return html.Div(
            className="ax-status-light-dot",
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
        className="ax-status-light ax-status-light--zone",
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
        return "Riesgo"
    if zone == "yellow":
        return "Atención"
    return "Estable"


def _zone_status_badge(zone: str):
    zone = (zone or "").strip().lower()
    if zone in ("", "empty", "pending", "none", "off"):
        return html.Span("Pendiente", className="ax-zone-status-badge ax-zone-status-badge--empty")
    tone = "bad" if zone == "red" else ("warn" if zone == "yellow" else "ok")
    return html.Span(_zone_action_label(zone), className=f"ax-zone-status-badge ax-zone-status-badge--{tone}")


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


def _comp_output_block(score: float, pending: bool = False):
    level, tone = _comp_level_meta(score)
    if pending:
        level, tone = "Pendiente", "empty"
    tone_color = {
        "empty": "rgba(148,163,184,.55)",
        "ok": "rgba(34,197,94,.95)",
        "warn": "rgba(245,158,11,.95)",
        "bad": "rgba(239,68,68,.95)",
    }.get(tone, "#e2e8f0")
    return html.Div(
        className="ax-comp-output-block",
        style={"display": "flex", "flexDirection": "column", "gap": "4px"},
        children=[
            html.Div(
                className="ax-comp-output-row",
                style={"display": "flex", "alignItems": "center", "gap": "5px", "width": "100%"},
                children=[
                    html.Div(
                        "Compensación",
                        className="ax-comp-output-label",
                        style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600},
                    ),
                    html.Div(
                        className="ax-comp-output-meter",
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
                            html.Div(className="ax-comp-output-fill", style=_comp_meter_fill_style(score))
                        ],
                    ),
                    html.Span(
                        f"{int(round(float(score or 0.0))):d}/100",
                        className="ax-comp-output-score",
                        style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700},
                    ),
                    html.Div(
                        level,
                        className="ax-comp-output-level",
                        style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700, "color": tone_color},
                    ),
                ],
            ),
        ],
    )


def _segment_state_card(title: str, light_id: str, status_id: str, cue_id: str, angle_id: str, angle_label: str, time_id: str = None, time_label: str = "Tiempo en rojo", extra_children=None):
    extra_children = extra_children or []
    return html.Div(
        className="ax-segment-status-card",
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
                            html.Div(id=status_id, children=_zone_status_badge("empty"), style={**BLACK_TEXT, "fontSize": "10px", "fontWeight": 800, "whiteSpace": "nowrap", "textAlign": "right"}),
                            html.Div(
                                id=light_id,
                                children=_traffic_light_zone("empty"),
                                style={"width": "24px", "minWidth": "24px", "display": "flex", "justifyContent": "flex-end"},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(id=cue_id, children="Estable", style={**BLACK_MUTED, "fontSize": "10px", "fontWeight": 700, "display": "none"}),
            html.Div(
                className="ax-segment-metric-row",
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "5px"},
                children=[
                    html.Span(angle_label, style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                    html.Span(id=angle_id, children="0.0°", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700}),
                ],
            ),
            html.Div(
                className="ax-segment-metric-row",
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


def _get_login_session_id(session_user):
    if isinstance(session_user, dict):
        value = session_user.get("login_session_id")
        if value is not None and str(value).strip():
            return str(value).strip()
    return None



def _safe_minmax(xs):
    xs = [float(x) for x in (xs or [])]
    if not xs:
        return 0.0, 0.0
    return float(min(xs)), float(max(xs))


def _safe_mean(xs):
    xs = [float(x) for x in (xs or [])]
    if not xs:
        return 0.0
    return float(sum(xs) / max(len(xs), 1))


def _safe_std(xs):
    xs = [float(x) for x in (xs or [])]
    if len(xs) < 2:
        return 0.0
    m = _safe_mean(xs)
    v = sum((float(x) - m) ** 2 for x in xs) / max(len(xs) - 1, 1)
    return float(v ** 0.5)


def _build_monitor_simulated_baseline_from_window(win):
    win = win if isinstance(win, dict) else {}
    T_pitch = [float(x) for x in (win.get("T_pitch") or [])]
    T_roll = [float(x) for x in (win.get("T_roll") or [])]
    L_pitch = [float(x) for x in (win.get("L_pitch") or [])]
    L_roll = [float(x) for x in (win.get("L_roll") or [])]
    comp = [float(x) for x in (win.get("comp_index") or [])]

    tmin, tmax = _safe_minmax(T_pitch)
    rmin, rmax = _safe_minmax(T_roll)
    lpmin, lpmax = _safe_minmax(L_pitch)
    lrmin, lrmax = _safe_minmax(L_roll)

    diff_tl = [abs(lp - tp) for lp, tp in zip(L_pitch, T_pitch)] if (L_pitch and T_pitch) else []

    return {
        "rom": {
            "thor_pitch": float(tmax - tmin),
            "thor_roll": float(rmax - rmin),
            "lum_pitch": float(lpmax - lpmin),
            "lum_roll": float(lrmax - lrmin),
        },
        "stability": {
            "thor_pitch_std": _safe_std(T_pitch),
            "thor_roll_std": _safe_std(T_roll),
            "lum_pitch_std": _safe_std(L_pitch),
            "lum_roll_std": _safe_std(L_roll),
        },
        "diff_TL_pitch_mean": _safe_mean(diff_tl),
        "comp": {"comp_avg": _safe_mean(comp), "comp_peak": float(max(comp) if comp else 0.0)},
        "n_samples": int(len(win.get("ts_ms") or [])),
        "created_day": date.today().isoformat(),
        "source": "monitor_simulated_wait_15s",
    }


def _build_monitor_baseline_summary_for_store(baseline_payload):
    """Resumen mínimo del baseline recién guardado para calibration-store.

    Reutiliza luego normalize_baseline_reference_for_ui(...) mediante
    _legacy_history_fields_from_reference(...), evitando crear otro helper de DB
    solo para el caso temporal del baseline recién creado.
    """
    payload = baseline_payload if isinstance(baseline_payload, dict) else {}
    rom = payload.get("rom") if isinstance(payload.get("rom"), dict) else {}
    comp = payload.get("comp") if isinstance(payload.get("comp"), dict) else {}
    stability = payload.get("stability") if isinstance(payload.get("stability"), dict) else {}

    def _f(value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    return {
        "rom_thor_pitch": _f(rom.get("thor_pitch")),
        "rom_lum_pitch": _f(rom.get("lum_pitch")),
        "comp_avg": _f(comp.get("comp_avg")),
        "comp_peak": _f(comp.get("comp_peak")),
        "lum_pitch_std": _f(stability.get("lum_pitch_std")),
        "thor_pitch_std": _f(stability.get("thor_pitch_std")),
        "diff_tl_pitch_mean": _f(payload.get("diff_TL_pitch_mean")),
        "n_samples": int(_f(payload.get("n_samples"), 0.0)),
    }


def _get_shared_baseline_reference_for_user(session_user):
    """Lee baseline histórico usando helpers centralizados de db.py."""
    user_id = _get_user_id(session_user)
    if user_id is None:
        return None
    try:
        ref = get_latest_baseline_reference_for_ui(user_id=int(user_id), allow_fallback=True)
        return ref if isinstance(ref, dict) and ref.get("has_baseline") else None
    except Exception:
        return None


def _latest_baseline_history_from_db(session_user):
    """Devuelve latest_* para calibration-store usando normalización centralizada."""
    user_id = _get_user_id(session_user)
    if user_id is None:
        ref = empty_baseline_history_reference()
        return {
            "latest_baseline_test_id": ref.get("latest_baseline_test_id"),
            "latest_baseline_ts": ref.get("latest_baseline_ts"),
            "latest_baseline_payload": {},
            "latest_baseline_summary": {},
            "latest_baseline_source": ref.get("latest_baseline_source"),
        }
    try:
        return get_latest_baseline_history_legacy_fields(user_id=int(user_id), allow_fallback=True)
    except Exception:
        ref = empty_baseline_history_reference()
        return {
            "latest_baseline_test_id": ref.get("latest_baseline_test_id"),
            "latest_baseline_ts": ref.get("latest_baseline_ts"),
            "latest_baseline_payload": {},
            "latest_baseline_summary": {},
            "latest_baseline_source": ref.get("latest_baseline_source"),
        }


# =============================
# Calibration store v2 — separación clara de conceptos
# =============================
# FASE 5:
# - active_session_calibration: estado operativo de la sesión actual.
# - historical_baseline_reference: referencia histórica compartida persistida en DB.
# - campos legacy en raíz: solo alias compatibles para callbacks existentes.
# No se añade ningún Output ni callback nuevo.

_CALIBRATION_STORE_SCHEMA_VERSION = "monitor_calibration_store_v2"


def _empty_historical_baseline_reference():
    ref = empty_baseline_history_reference()
    return {
        "latest_baseline_test_id": ref.get("latest_baseline_test_id"),
        "latest_baseline_ts": ref.get("latest_baseline_ts"),
        "latest_baseline_payload": ref.get("latest_baseline_payload") if isinstance(ref.get("latest_baseline_payload"), dict) else {},
        "latest_baseline_summary": ref.get("latest_baseline_summary") if isinstance(ref.get("latest_baseline_summary"), dict) else {},
        "latest_baseline_source": ref.get("latest_baseline_source"),
    }


def _normalize_historical_baseline_reference(history=None):
    """Adapta histórico al formato latest_* sin duplicar parsing."""
    ref = normalize_baseline_reference_for_ui(history if isinstance(history, dict) else {})
    return {
        "latest_baseline_test_id": ref.get("latest_baseline_test_id"),
        "latest_baseline_ts": ref.get("latest_baseline_ts"),
        "latest_baseline_payload": ref.get("latest_baseline_payload") if isinstance(ref.get("latest_baseline_payload"), dict) else {},
        "latest_baseline_summary": ref.get("latest_baseline_summary") if isinstance(ref.get("latest_baseline_summary"), dict) else {},
        "latest_baseline_source": ref.get("latest_baseline_source"),
    }


def _legacy_history_fields_from_reference(history=None):
    history = _normalize_historical_baseline_reference(history)
    return {
        "latest_baseline_test_id": history.get("latest_baseline_test_id"),
        "latest_baseline_ts": history.get("latest_baseline_ts"),
        "latest_baseline_payload": history.get("latest_baseline_payload") or {},
        "latest_baseline_summary": history.get("latest_baseline_summary") or {},
        "latest_baseline_source": history.get("latest_baseline_source"),
    }


def _legacy_history_source_from_store(calib=None):
    """Extrae solo campos latest_* para que el histórico no reactive estado operativo."""
    calib = calib if isinstance(calib, dict) else {}
    return {
        "latest_baseline_test_id": calib.get("latest_baseline_test_id"),
        "latest_baseline_ts": calib.get("latest_baseline_ts"),
        "latest_baseline_payload": calib.get("latest_baseline_payload") if isinstance(calib.get("latest_baseline_payload"), dict) else {},
        "latest_baseline_summary": calib.get("latest_baseline_summary") if isinstance(calib.get("latest_baseline_summary"), dict) else {},
        "latest_baseline_source": calib.get("latest_baseline_source"),
    }


def _normalize_active_session_calibration(active=None):
    active = active if isinstance(active, dict) else {}
    return {
        "status": _normalize_calibration_status(active.get("status", "Pendiente")),
        "source": active.get("source") or "baseline_required",
        "ts": active.get("ts") or datetime.now().isoformat(timespec="seconds"),
        "started_at_epoch_ms": active.get("started_at_epoch_ms"),
        "completed_at_epoch_ms": active.get("completed_at_epoch_ms"),
        "baseline_test_id": active.get("baseline_test_id"),
        "baseline_payload": active.get("baseline_payload") if isinstance(active.get("baseline_payload"), dict) else {},
        "valid_for_current_session": bool(active.get("valid_for_current_session", False)),
        "session_scope_id": active.get("session_scope_id"),
        "calibration_user_id": active.get("calibration_user_id"),
        "login_session_id": active.get("login_session_id"),
        "simulated": bool(active.get("simulated", True)),
        "target_wait_s": float(active.get("target_wait_s") or 15.0),
        "elapsed_s": float(active.get("elapsed_s") or 0.0),
        "remaining_s": float(active.get("remaining_s") or 0.0),
        "auto_started": bool(active.get("auto_started", False)),
    }


def _legacy_active_fields_from_session(active=None):
    active = _normalize_active_session_calibration(active)
    return {
        "status": active.get("status"),
        "source": active.get("source"),
        "ts": active.get("ts"),
        "started_at_epoch_ms": active.get("started_at_epoch_ms"),
        "completed_at_epoch_ms": active.get("completed_at_epoch_ms"),
        "baseline_test_id": active.get("baseline_test_id"),
        "baseline_payload": active.get("baseline_payload") or {},
        "valid_for_current_session": active.get("valid_for_current_session"),
        "session_scope_id": active.get("session_scope_id"),
        "calibration_user_id": active.get("calibration_user_id"),
        "login_session_id": active.get("login_session_id"),
        "simulated": active.get("simulated"),
        "target_wait_s": active.get("target_wait_s"),
        "elapsed_s": active.get("elapsed_s"),
        "remaining_s": active.get("remaining_s"),
        "auto_started": active.get("auto_started"),
    }


def _build_calibration_store(active_session_calibration=None, historical_baseline_reference=None, *, preserve_extra=None):
    active = _normalize_active_session_calibration(active_session_calibration)
    history = _normalize_historical_baseline_reference(historical_baseline_reference)
    out = {}
    if isinstance(preserve_extra, dict):
        out.update(preserve_extra)
    out.update(_legacy_active_fields_from_session(active))
    out.update(_legacy_history_fields_from_reference(history))
    out["schema_version"] = _CALIBRATION_STORE_SCHEMA_VERSION
    out["active_session_calibration"] = active
    out["historical_baseline_reference"] = history
    return out


def _normalize_calibration_store(calib):
    """Normaliza calibration-store sin romper compatibilidad legacy."""
    calib = calib if isinstance(calib, dict) else {}
    active_src = calib.get("active_session_calibration") if isinstance(calib.get("active_session_calibration"), dict) else calib
    history_src = calib.get("historical_baseline_reference") if isinstance(calib.get("historical_baseline_reference"), dict) else _legacy_history_source_from_store(calib)
    return _build_calibration_store(active_src, history_src, preserve_extra=calib)


def _get_active_calibration(calib):
    calib = _normalize_calibration_store(calib)
    active = calib.get("active_session_calibration")
    return active if isinstance(active, dict) else {}


def _get_historical_baseline_reference(calib):
    calib = _normalize_calibration_store(calib)
    history = calib.get("historical_baseline_reference")
    return history if isinstance(history, dict) else _empty_historical_baseline_reference()


def _build_pending_calibration_state(reason: str, session_user=None, auth_session=None):
    auth_session = auth_session if isinstance(auth_session, dict) else {}
    history = _latest_baseline_history_from_db(session_user)
    active = {
        "status": "Pendiente",
        "source": reason,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "baseline_test_id": None,
        "baseline_payload": {},
        "valid_for_current_session": False,
        "session_scope_id": auth_session.get("session_scope_id"),
        "calibration_user_id": _get_user_id(session_user),
        "login_session_id": _get_login_session_id(session_user),
        "simulated": True,
        "target_wait_s": 15.0,
        "elapsed_s": 0.0,
        "remaining_s": 15.0,
        "auto_started": False,
    }
    return _build_calibration_store(active, history)


def _invalidate_active_calibration_for_session(reason: str, session_user=None, auth_session=None):
    """Invalida solo la calibración activa de la sesión actual.

    Regla maestra Paso 1:
    - cada login deja la calibración activa en Pendiente;
    - cada apagado de simulación deja la calibración activa en Pendiente;
    - el baseline histórico persistido en DB se conserva solo como referencia visual.

    Este helper centraliza la escritura de calibration-store para no duplicar
    lógica entre ramas del callback ni mezclar histórico con estado operativo.
    """
    return _build_pending_calibration_state(reason, session_user=session_user, auth_session=auth_session)




def _build_in_progress_calibration_state(session_user=None, auth_session=None, *, auto_started: bool = False):
    auth_session = auth_session if isinstance(auth_session, dict) else {}
    history = _latest_baseline_history_from_db(session_user)
    active = {
        "status": "En progreso",
        "source": "monitor_simulated_wait_15s",
        "ts": datetime.now().isoformat(timespec="seconds"),
        "started_at_epoch_ms": int(time.time() * 1000),
        "baseline_test_id": None,
        "baseline_payload": {},
        "valid_for_current_session": False,
        "session_scope_id": auth_session.get("session_scope_id"),
        "calibration_user_id": _get_user_id(session_user),
        "login_session_id": _get_login_session_id(session_user),
        "simulated": True,
        "target_wait_s": 15.0,
        "elapsed_s": 0.0,
        "remaining_s": 15.0,
        "auto_started": bool(auto_started),
    }
    return _build_calibration_store(active, history)


def _build_calibration_state_from_questionnaire_handoff(questionnaire_handoff, session_user=None, auth_session=None):
    questionnaire_handoff = questionnaire_handoff if isinstance(questionnaire_handoff, dict) else {}
    auth_session = auth_session if isinstance(auth_session, dict) else {}
    user_id = _get_user_id(session_user)
    session_scope_id = auth_session.get("session_scope_id")
    baseline_id = questionnaire_handoff.get("baseline_test_id") or questionnaire_handoff.get("baseline_id")
    if (
        user_id is None
        or not session_scope_id
        or auth_session.get("logged_out")
        or not baseline_id
        or _normalize_calibration_status(questionnaire_handoff.get("status")) != "Completada"
        or not bool(questionnaire_handoff.get("valid_for_current_session"))
    ):
        return None
    try:
        handoff_user_id = int(questionnaire_handoff.get("calibration_user_id"))
    except Exception:
        return None
    if handoff_user_id != int(user_id):
        return None

    login_session_id = _get_login_session_id(session_user)
    handoff_login_session_id = questionnaire_handoff.get("login_session_id")
    if login_session_id and str(handoff_login_session_id or "") != str(login_session_id):
        return None

    history = _latest_baseline_history_from_db(session_user)
    baseline_payload = {}
    if str(history.get("latest_baseline_test_id") or "") == str(baseline_id):
        baseline_payload = history.get("latest_baseline_payload") if isinstance(history.get("latest_baseline_payload"), dict) else {}
    completed_at_iso = questionnaire_handoff.get("completed_iso") or history.get("latest_baseline_ts") or datetime.now().isoformat(timespec="seconds")
    active = {
        "status": "Completada",
        "source": "questionnaire_baseline_session",
        "ts": completed_at_iso,
        "started_at_epoch_ms": None,
        "completed_at_epoch_ms": int(time.time() * 1000),
        "baseline_test_id": baseline_id,
        "baseline_payload": baseline_payload,
        "valid_for_current_session": True,
        "session_scope_id": session_scope_id,
        "calibration_user_id": int(user_id),
        "login_session_id": login_session_id,
        "simulated": True,
        "target_wait_s": float(questionnaire_handoff.get("target_wait_s") or 15.0),
        "elapsed_s": float(questionnaire_handoff.get("elapsed_s") or 15.0),
        "remaining_s": 0.0,
        "auto_started": False,
    }
    return _build_calibration_store(active, history, preserve_extra={})


def _questionnaire_handoff_requires_monitor_recalibration(questionnaire_handoff, session_user=None) -> bool:
    questionnaire_handoff = questionnaire_handoff if isinstance(questionnaire_handoff, dict) else {}
    source = str(questionnaire_handoff.get("source") or "").strip()
    requires_reset = bool(questionnaire_handoff.get("requires_monitor_recalibration")) or bool(questionnaire_handoff.get("reset_active"))
    if source not in ("questionnaire_baseline_reset", "questionnaire_baseline_in_progress") and not requires_reset:
        return False

    user_id = _get_user_id(session_user)
    if user_id is None:
        return False
    try:
        handoff_user_id = int(questionnaire_handoff.get("calibration_user_id"))
    except Exception:
        return False
    if handoff_user_id != int(user_id):
        return False

    login_session_id = _get_login_session_id(session_user)
    handoff_login_session_id = questionnaire_handoff.get("login_session_id")
    if login_session_id and handoff_login_session_id and str(handoff_login_session_id) != str(login_session_id):
        return False
    return True


def _questionnaire_reset_should_invalidate_monitor_calibration(questionnaire_handoff, calib, session_user=None) -> bool:
    if not _questionnaire_handoff_requires_monitor_recalibration(questionnaire_handoff, session_user=session_user):
        return False

    active = _get_active_calibration(calib)
    if not active or not active.get("baseline_test_id"):
        return True
    if active.get("source") == "questionnaire_baseline_session":
        return True

    try:
        reset_epoch_ms = int((questionnaire_handoff or {}).get("reset_epoch_ms") or 0)
    except Exception:
        reset_epoch_ms = 0
    try:
        completed_at_epoch_ms = int(active.get("completed_at_epoch_ms") or 0)
    except Exception:
        completed_at_epoch_ms = 0

    if reset_epoch_ms and completed_at_epoch_ms:
        return completed_at_epoch_ms <= reset_epoch_ms
    if reset_epoch_ms and not completed_at_epoch_ms:
        return True
    return False


def _calibration_popup_status_from_state(calib):
    calib = _normalize_calibration_store(calib)
    active = _get_active_calibration(calib)
    history = _get_historical_baseline_reference(calib)
    status_txt = _normalize_calibration_status(active.get("status"))
    if status_txt == "Completada":
        return "Estado actual: Completada · lista para esta sesión"
    if status_txt == "En progreso":
        elapsed_s = float(active.get("elapsed_s") or calib.get("elapsed_s") or 0.0)
        target_wait_s = float(active.get("target_wait_s") or calib.get("target_wait_s") or 15.0)
        return f"Estado actual: En progreso · {elapsed_s:.1f}/{target_wait_s:.1f} s"
    latest_ts = str(history.get("latest_baseline_ts") or calib.get("latest_baseline_ts") or "").strip()
    if latest_ts:
        return f"Estado actual: Pendiente · última calibración registrada: {latest_ts}"
    return "Estado actual: Pendiente"


def _load_calibration_state_from_db(session_user):
    """Devuelve el histórico guardado, pero no lo activa para la sesión actual."""
    calib = _build_pending_calibration_state("baseline_required", session_user=session_user, auth_session={})
    history = _latest_baseline_history_from_db(session_user)
    if history.get("latest_baseline_test_id") is not None:
        active = _get_active_calibration(calib)
        active["source"] = "baseline_history_available"
        calib = _build_calibration_store(active, history, preserve_extra=calib)
    return calib


def _format_calibration_history_date(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return raw


def _fmt_calibration_number(value, suffix: str = "", digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except Exception:
        return "—"


def _load_calibration_history_rows(session_user, limit: int = 50):
    user_id = _get_user_id(session_user)
    if user_id is None:
        return []
    try:
        rows = list_baseline_tests_for_user(user_id=int(user_id), limit=limit)
    except Exception:
        rows = []
    return rows if isinstance(rows, list) else []


def _calibration_history_empty_block():
    return html.Div(
        className=SECONDARY_GRAY_PANEL_CLASS,
        style={"alignItems": "center", "textAlign": "center", "gap": "6px"},
        children=[
            html.Div("Sin calibraciones registradas", className=SECTION_TITLE_CLASS),
            html.Div(
                "Cuando completes una calibración, aparecerá aquí con fecha, estado, muestras y métricas principales.",
                style={**BLACK_MUTED, "fontSize": "12px", "lineHeight": "1.45"},
            ),
        ],
    )


def _build_calibration_history_table(session_user):
    rows = _load_calibration_history_rows(session_user, limit=50)
    if not rows:
        return _calibration_history_empty_block()

    header_style = {
        **BLACK_MUTED,
        "fontSize": "11px",
        "fontWeight": 800,
        "textTransform": "uppercase",
        "letterSpacing": ".03em",
        "padding": "8px 10px",
        "borderBottom": "1px solid rgba(255,255,255,.10)",
        "whiteSpace": "nowrap",
    }
    cell_style = {
        **BLACK_TEXT,
        "fontSize": "12px",
        "fontWeight": 600,
        "padding": "8px 10px",
        "borderBottom": "1px solid rgba(255,255,255,.07)",
        "verticalAlign": "middle",
        "whiteSpace": "nowrap",
    }

    body_rows = []
    for item in rows:
        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        status = item.get("status") or ("Completada" if item.get("is_valid") else "Pendiente")
        status_tone = "ok" if status == "Completada" else "warn"
        source = str(item.get("source") or item.get("history_source") or "baseline_tests")
        body_rows.append(
            html.Tr(
                children=[
                    html.Td(_format_calibration_history_date(item.get("created_at")), style=cell_style),
                    html.Td(_status_value_badge(status, status_tone), style={**cell_style, "padding": "6px 10px"}),
                    html.Td(f"#{item.get('baseline_test_id') or item.get('id') or '—'}", style=cell_style),
                    html.Td(_fmt_calibration_number(summary.get("n_samples"), "", 0), style=cell_style),
                    html.Td(_fmt_calibration_number(summary.get("rom_thor_pitch"), "°"), style=cell_style),
                    html.Td(_fmt_calibration_number(summary.get("rom_lum_pitch"), "°"), style=cell_style),
                    html.Td(_fmt_calibration_number(summary.get("comp_avg"), "/100"), style=cell_style),
                    html.Td(_fmt_calibration_number(summary.get("comp_peak"), "/100"), style=cell_style),
                    html.Td(_fmt_calibration_number(summary.get("lum_pitch_std"), "°"), style=cell_style),
                    html.Td(source, style={**cell_style, "color": "rgba(226,232,240,.75)"}),
                ]
            )
        )

    latest = rows[0]
    latest_summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
    return html.Div(
        className=SECONDARY_BLACK_PANEL_CLASS,
        style={"gap": "10px"},
        children=[
            html.Div(
                className=SECONDARY_GRAY_PANEL_CLASS,
                style={"display": "grid", "gridTemplateColumns": "repeat(4, minmax(0, 1fr))", "gap": "8px"},
                children=[
                    _pill("Total", str(len(rows)), "neutral", full=True),
                    _pill("Última", _format_calibration_history_date(latest.get("created_at")), "neutral", full=True),
                    _pill("Estado", latest.get("status") or "—", "ok" if latest.get("is_valid") else "warn", full=True),
                    _pill("Comp. media", _fmt_calibration_number(latest_summary.get("comp_avg"), "/100"), "neutral", full=True),
                ],
            ),
            html.Div(
                style={
                    "width": "100%",
                    "overflowX": "auto",
                    "borderRadius": "12px",
                    "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                    "background": "rgba(255,255,255,.04)",
                },
                children=[
                    html.Table(
                        style={"width": "100%", "borderCollapse": "collapse", "minWidth": "920px"},
                        children=[
                            html.Thead(
                                html.Tr(
                                    children=[
                                        html.Th("Fecha", style=header_style),
                                        html.Th("Estado", style=header_style),
                                        html.Th("ID", style=header_style),
                                        html.Th("Muestras", style=header_style),
                                        html.Th("ROM torácica", style=header_style),
                                        html.Th("ROM lumbar", style=header_style),
                                        html.Th("Comp. media", style=header_style),
                                        html.Th("Comp. pico", style=header_style),
                                        html.Th("Estabilidad lum.", style=header_style),
                                        html.Th("Origen", style=header_style),
                                    ]
                                )
                            ),
                            html.Tbody(body_rows),
                        ],
                    )
                ],
            ),
            html.Div(
                "Nota: este historial es una referencia persistida; la calibración operativa de cada sesión sigue validándose por sesión.",
                style={**BLACK_MUTED, "fontSize": "12px", "lineHeight": "1.45"},
            ),
        ],
    )




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
# Exportación PDF / CSV de informe Axisfit
# =============================
def _fmt_report_value(value, default="—"):
    if value is None:
        return default
    if isinstance(value, float):
        return f"{value:.1f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    txt = str(value).strip()
    return txt if txt else default


def _fmt_report_date(value, default="—"):
    raw = str(value or "").strip()
    if not raw:
        return default
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return raw


def _fmt_duration_seconds(value):
    try:
        total = int(float(value or 0))
    except Exception:
        total = 0
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if hours:
        return f"{hours}h {minutes:02d}min"
    if minutes:
        return f"{minutes}min {seconds:02d}s"
    return f"{seconds}s"


def _risk_label(value):
    try:
        v = float(value or 0.0)
    except Exception:
        return "Sin datos"
    if v >= 70:
        return "Riesgo elevado"
    if v >= 40:
        return "Atención"
    return "Óptimo"


def _comp_label(value):
    try:
        v = float(value or 0.0)
    except Exception:
        return "Sin datos"
    if v >= 66:
        return "Alta"
    if v >= 33:
        return "Media"
    return "Baja"


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


def _first_existing_dict(*values):
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _extract_payload(questionnaire_row):
    questionnaire_row = _safe_dict(questionnaire_row)
    payload = questionnaire_row.get("payload")
    if isinstance(payload, dict):
        return payload
    raw = questionnaire_row.get("payload_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                return decoded
        except Exception:
            return {}
    return {}


def _extract_recommendation(questionnaire_row):
    questionnaire_row = _safe_dict(questionnaire_row)
    rec = questionnaire_row.get("recommendation")
    if isinstance(rec, dict):
        return rec
    raw = questionnaire_row.get("recommendation_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                return decoded
        except Exception:
            return {}
    return {}


def _latest_session_summary(report_data):
    sessions = report_data.get("sensor_sessions") or []
    for s in sessions:
        if s.get("duration_s") is not None or s.get("risk_index") is not None:
            return s
    return sessions[0] if sessions else {}


def _build_report_data(session_user, active_session=None, calib=None, recorder=None, history_store=None):
    user_id = _get_user_id(session_user)
    user = _safe_dict(session_user)
    if user_id is not None:
        try:
            db_user = get_user_by_id(int(user_id))
            if isinstance(db_user, dict) and db_user:
                user = db_user
        except Exception:
            pass

    questionnaire = {}
    daily_today = {}
    baseline = {}
    posture_settings = {}
    sensor_sessions = []
    daily_summaries = []
    routine_sessions = []
    exercise_sets = []
    raw_samples = []
    agg_samples = []

    if user_id is not None:
        try:
            questionnaire = get_latest_questionnaire_session(user_id=int(user_id)) or {}
        except Exception:
            questionnaire = {}
        try:
            daily_today = get_daily_summary(user_id=int(user_id), day=date.today()) or {}
        except Exception:
            daily_today = {}
        try:
            baseline = get_latest_baseline_reference(user_id=int(user_id)) or get_latest_valid_baseline(user_id=int(user_id)) or {}
        except Exception:
            baseline = {}
        try:
            posture_settings = get_user_posture_settings(user_id=int(user_id)) or {}
        except Exception:
            posture_settings = {}
        try:
            sensor_sessions = list_recent_sensor_sessions_for_user(user_id=int(user_id), limit=20)
        except Exception:
            sensor_sessions = []
        try:
            daily_summaries = list_daily_summaries_for_user(user_id=int(user_id), limit=14)
        except Exception:
            daily_summaries = []
        try:
            routine_sessions = list_routine_sessions_for_user(user_id=int(user_id), limit=20)
        except Exception:
            routine_sessions = []
        try:
            exercise_sets = list_exercise_sets_for_user(user_id=int(user_id), limit=50)
        except Exception:
            exercise_sets = []
        try:
            raw_samples = list_sensor_raw_samples_for_user(user_id=int(user_id), limit=500)
        except Exception:
            raw_samples = []
        try:
            agg_samples = list_sensor_agg_samples_for_user(user_id=int(user_id), limit=500)
        except Exception:
            agg_samples = []

    payload = _extract_payload(questionnaire)
    recommendation = _extract_recommendation(questionnaire)
    baseline_payload = {}
    if isinstance(baseline, dict):
        baseline_payload = baseline.get("baseline") if isinstance(baseline.get("baseline"), dict) else baseline.get("baseline_payload")
        if not isinstance(baseline_payload, dict):
            baseline_payload = {}
    if not baseline_payload and isinstance(calib, dict):
        baseline_payload = calib.get("baseline_payload") if isinstance(calib.get("baseline_payload"), dict) else {}

    history_items = []
    if isinstance(history_store, dict):
        history_items = history_store.get("items") or []
    elif isinstance(history_store, list):
        history_items = history_store

    return {
        "user_id": user_id,
        "user": user,
        "questionnaire": questionnaire or {},
        "payload": payload or {},
        "recommendation": recommendation or {},
        "daily_today": daily_today or {},
        "baseline": baseline or {},
        "baseline_payload": baseline_payload or {},
        "posture_settings": posture_settings or {},
        "sensor_sessions": sensor_sessions or [],
        "daily_summaries": daily_summaries or [],
        "routine_sessions": routine_sessions or [],
        "exercise_sets": exercise_sets or [],
        "raw_samples": raw_samples or [],
        "agg_samples": agg_samples or [],
        "active_session": _safe_dict(active_session),
        "calibration_state": _safe_dict(calib),
        "recorder": _safe_dict(recorder),
        "history_items": history_items if isinstance(history_items, list) else [],
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }


def _report_table_rows(title, rows):
    out = []
    out.append(("__title__", title, ""))
    out.extend(rows or [])
    return out



def _pdf_escape_text(value):
    txt = str(value if value is not None else "-")
    txt = txt.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return txt


def _wrap_pdf_line(text, width=88):
    txt = str(text if text is not None else "-").replace("\r", " ").replace("\n", " ")
    words = txt.split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or ["-"]


def _build_valid_fallback_pdf_bytes(title, lines):
    """Genera un PDF minimo valido sin dependencias externas.

    Motivo:
    - Si reportlab no esta instalado, no se debe devolver texto plano con extension .pdf.
    - Este fallback conserva la descarga como PDF cargable en cualquier visor.
    """
    page_width = 595
    page_height = 842
    margin_x = 42
    y_start = 800
    line_h = 13
    safe_lines = []
    safe_lines.append(str(title or "Informe PDF Axisfit"))
    safe_lines.append("Generado en modo compatible sin reportlab.")
    safe_lines.append("")
    for line in lines or []:
        safe_lines.extend(_wrap_pdf_line(line, width=92))
    if len(safe_lines) < 4:
        safe_lines.extend([
            "No se encontraron datos suficientes para completar el informe.",
            "El archivo sigue siendo un PDF valido para evitar errores al abrirlo.",
        ])

    pages = []
    current = []
    max_lines = 58
    for line in safe_lines:
        current.append(line)
        if len(current) >= max_lines:
            pages.append(current)
            current = []
    if current:
        pages.append(current)

    objects = []
    page_ids = []
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(None)
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_index, page_lines in enumerate(pages, start=1):
        page_obj_id = len(objects) + 1
        content_obj_id = page_obj_id + 1
        page_ids.append(page_obj_id)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>")
        stream_lines = ["BT", "/F1 10 Tf", f"{margin_x} {y_start} Td"]
        for i, line in enumerate(page_lines):
            if i == 0 and page_index == 1:
                stream_lines.append("/F1 14 Tf")
            escaped = _pdf_escape_text(line)
            stream_lines.append(f"({escaped}) Tj")
            stream_lines.append(f"0 -{line_h} Td")
            if i == 0 and page_index == 1:
                stream_lines.append("/F1 10 Tf")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n" + stream.decode("latin-1") + "\nendstream")

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>"

    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj_id, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{obj_id} 0 obj\n".encode("latin-1"))
        output.write(str(obj).encode("latin-1", errors="replace"))
        output.write(b"\nendobj\n")
    xref_pos = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1"))
    return output.getvalue()


def _build_axisfit_pdf_fallback_lines(report_data, reason=""):
    report_data = report_data if isinstance(report_data, dict) else {}
    user = report_data.get("user") if isinstance(report_data.get("user"), dict) else {}
    latest_session = _latest_session_summary(report_data)
    sessions = report_data.get("sensor_sessions") or []
    baseline = report_data.get("baseline") if isinstance(report_data.get("baseline"), dict) else {}
    exported_at = _fmt_report_date(report_data.get("exported_at"))
    lines = [
        "Informe de Postura y Monitorizacion",
        f"Fecha de exportacion: {exported_at}",
        f"Usuario: {_fmt_report_value(user.get('name') or user.get('nombre') or user.get('email'))}",
        f"Email: {_fmt_report_value(user.get('email'))}",
        f"Sesiones registradas: {len(sessions)}",
        f"Ultima calibracion: {_fmt_report_date(baseline.get('created_at') or baseline.get('latest_baseline_ts'))}",
        f"Riesgo ultima sesion: {_fmt_report_value(latest_session.get('risk_index'))}/100",
        f"Duracion ultima sesion: {_fmt_duration_seconds(latest_session.get('duration_s'))}",
        f"Alertas ultima sesion: {_fmt_report_value(latest_session.get('alerts_count'))}",
        "",
        "Aviso tecnico:",
        "Este PDF fue generado con el motor compatible interno porque reportlab no esta disponible o fallo al construir el informe enriquecido.",
        "Para activar el diseno completo con tablas avanzadas instala reportlab en el mismo entorno de Python de la app: pip install reportlab",
    ]
    if reason:
        lines.append(f"Detalle tecnico: {reason}")
    return lines


def _build_axisfit_pdf_bytes(report_data, *, report_kind="full"):
    try:
        reportlab_lib = __import__("reportlab.lib", fromlist=["colors"])
        colors = reportlab_lib.colors
        enums_mod = __import__("reportlab.lib.enums", fromlist=["TA_CENTER"])
        TA_CENTER = enums_mod.TA_CENTER
        pagesizes_mod = __import__("reportlab.lib.pagesizes", fromlist=["A4"])
        A4 = pagesizes_mod.A4
        styles_mod = __import__("reportlab.lib.styles", fromlist=["getSampleStyleSheet", "ParagraphStyle"])
        getSampleStyleSheet = styles_mod.getSampleStyleSheet
        ParagraphStyle = styles_mod.ParagraphStyle
        units_mod = __import__("reportlab.lib.units", fromlist=["mm"])
        mm = units_mod.mm
        platypus_mod = __import__("reportlab.platypus", fromlist=["SimpleDocTemplate", "Paragraph", "Spacer", "Table", "TableStyle", "PageBreak"])
        SimpleDocTemplate = platypus_mod.SimpleDocTemplate
        Paragraph = platypus_mod.Paragraph
        Spacer = platypus_mod.Spacer
        Table = platypus_mod.Table
        TableStyle = platypus_mod.TableStyle
        PageBreak = platypus_mod.PageBreak
    except Exception as exc:
        fallback_lines = _build_axisfit_pdf_fallback_lines(report_data, reason=str(exc))
        return _build_valid_fallback_pdf_bytes("Informe PDF Axisfit", fallback_lines)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="Informe PDF Axisfit",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="AxisTitle", parent=styles["Title"], fontSize=20, leading=24, textColor=colors.HexColor("#0b1220"), alignment=TA_CENTER, spaceAfter=8))
    styles.add(ParagraphStyle(name="AxisSubtitle", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#1d4ed8"), spaceBefore=8, spaceAfter=6))
    styles.add(ParagraphStyle(name="AxisBody", parent=styles["BodyText"], fontSize=8.8, leading=11, textColor=colors.HexColor("#0f172a")))
    styles.add(ParagraphStyle(name="AxisSmall", parent=styles["BodyText"], fontSize=7.8, leading=9.5, textColor=colors.HexColor("#334155")))

    story = []
    user = report_data.get("user") or {}
    payload = report_data.get("payload") or {}
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    pain = payload.get("pain") if isinstance(payload.get("pain"), dict) else {}
    self_eval = payload.get("self_eval") if isinstance(payload.get("self_eval"), dict) else {}
    daily_payload = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    questionnaire = report_data.get("questionnaire") or {}
    baseline = report_data.get("baseline") or {}
    baseline_payload = report_data.get("baseline_payload") or {}
    daily_today = report_data.get("daily_today") or {}
    settings = report_data.get("posture_settings") or {}
    latest_session = _latest_session_summary(report_data)
    sessions = report_data.get("sensor_sessions") or []
    daily_summaries = report_data.get("daily_summaries") or []
    routines = report_data.get("routine_sessions") or []
    exercise_sets = report_data.get("exercise_sets") or []

    risk_now = latest_session.get("risk_index")
    if risk_now is None:
        risk_now = daily_today.get("risk_index_max") or questionnaire.get("risk_index") or 0
    comp_avg = latest_session.get("comp_avg")
    if comp_avg is None:
        comp_avg = daily_today.get("comp_avg") or 0
    total_duration = sum(float(s.get("duration_s") or 0.0) for s in sessions if s.get("duration_s") is not None)
    total_bad = sum(float(s.get("thor_red_s") or 0.0) + float(s.get("lum_red_s") or 0.0) for s in sessions)
    latest_baseline_date = baseline.get("created_at") or baseline.get("latest_baseline_ts") or report_data.get("calibration_state", {}).get("latest_baseline_ts")

    def P(txt, style="AxisBody"):
        safe = str(txt if txt is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(safe, styles[style])

    def table(title, headers, rows, col_widths=None):
        story.append(P(title, "AxisSubtitle"))
        data = [[P(h, "AxisSmall") for h in headers]]
        for row in rows:
            data.append([P(c, "AxisSmall") for c in row])
        if not rows:
            data.append([P("Sin datos registrados", "AxisSmall")] + [P("—", "AxisSmall") for _ in headers[1:]])
        t = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b1220")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 5))

    # Página 1
    story.append(P("AXISFIT", "AxisTitle"))
    story.append(P("Informe de Postura y Monitorización", "AxisTitle"))
    story.append(P(f"Reporte de postura, calibración y evolución del usuario · Exportado: {_fmt_report_date(report_data.get('exported_at'))}", "AxisBody"))
    story.append(Spacer(1, 6))
    table(
        "Página 1 — Portada + resumen ejecutivo",
        ["Indicador", "Valor", "Interpretación"],
        [
            ["Riesgo postural actual", f"{_fmt_report_value(risk_now)}/100", _risk_label(risk_now)],
            ["Sesiones registradas", str(len(sessions)), "Últimas sesiones disponibles"],
            ["Tiempo total monitorizado", _fmt_duration_seconds(total_duration), "Acumulado"],
            ["Tiempo en mala postura", _fmt_duration_seconds(total_bad), "Torácica + lumbar"],
            ["Compensación media", f"{_fmt_report_value(comp_avg)}/100", _comp_label(comp_avg)],
            ["Última calibración", _fmt_report_date(latest_baseline_date), "Válida / Histórica"],
        ],
        [58 * mm, 45 * mm, 78 * mm],
    )
    story.append(P("Resumen para usuario", "AxisSubtitle"))
    story.append(P("Durante el periodo analizado, tu postura se interpreta a partir de cuestionario, calibración, sesiones de monitorización y resumen diario. Revisa especialmente las zonas con más tiempo en mala postura, la compensación media y las alertas repetidas.", "AxisBody"))
    story.append(P("Semáforo visual: Verde = postura estable · Amarillo = revisar técnica · Rojo = requiere atención.", "AxisSmall"))

    if report_kind == "quick":
        story.append(PageBreak())
        table(
            "Resumen rápido — Última calibración y últimas sesiones",
            ["Fecha", "Modalidad", "Deporte", "Sesión", "Duración", "Riesgo", "Alertas"],
            [
                [
                    _fmt_report_date(s.get("started_at")),
                    _fmt_report_value(s.get("mode")),
                    _fmt_report_value(s.get("sport")),
                    _fmt_report_value(s.get("planned_session_name")),
                    _fmt_duration_seconds(s.get("duration_s")),
                    f"{_fmt_report_value(s.get('risk_index'))}/100",
                    _fmt_report_value(s.get("alerts_count")),
                ]
                for s in sessions[:6]
            ],
        )
        story.append(P("Este resumen rápido contiene portada, estado general, última calibración y últimas sesiones. Para el detalle completo usa Exportar informe PDF.", "AxisBody"))
        try:
            doc.build(story)
            pdf_bytes = buffer.getvalue()
            if not pdf_bytes.startswith(b"%PDF"):
                fallback_lines = _build_axisfit_pdf_fallback_lines(report_data, reason="La salida generada no empieza con %PDF")
                return _build_valid_fallback_pdf_bytes("Informe PDF Axisfit", fallback_lines)
            return pdf_bytes
        except Exception as exc:
            fallback_lines = _build_axisfit_pdf_fallback_lines(report_data, reason=str(exc))
            return _build_valid_fallback_pdf_bytes("Informe PDF Axisfit", fallback_lines)

    story.append(PageBreak())

    table(
        "Página 2 — Perfil del usuario",
        ["Campo", "Valor"],
        [
            ["Nombre", _fmt_report_value(user.get("name") or user.get("nombre"))],
            ["Email", _fmt_report_value(user.get("email"))],
            ["País", _fmt_report_value(user.get("country"))],
            ["Rol", _fmt_report_value(user.get("role") or "Atleta")],
            ["Uso principal", _fmt_report_value(user.get("ath_uso") or profile.get("goal"))],
            ["Nivel", _fmt_report_value(user.get("ath_nivel") or profile.get("level"))],
            ["Frecuencia semanal", _fmt_report_value(user.get("ath_freq") or profile.get("frequency"))],
            ["Box / centro", _fmt_report_value(user.get("ath_box"))],
            ["Altura", _fmt_report_value(user.get("ath_altura"))],
            ["Peso", _fmt_report_value(user.get("ath_peso"))],
            ["Molestias reportadas", _fmt_report_value(user.get("ath_molestias"))],
            ["Dolor VAS", f"{_fmt_report_value(user.get('ath_vas'))}/10"],
        ],
        [62 * mm, 118 * mm],
    )
    story.append(P("Estos datos provienen del perfil inicial del usuario y ayudan a personalizar los umbrales posturales y las recomendaciones.", "AxisSmall"))

    table(
        "Página 3 — Cuestionario y estado inicial",
        ["Campo", "Valor"],
        [
            ["Tipo de cuestionario", _fmt_report_value(questionnaire.get("type"))],
            ["Fecha de inicio", _fmt_report_date(questionnaire.get("started_at"))],
            ["Fecha de finalización", _fmt_report_date(questionnaire.get("completed_at"))],
            ["Índice de riesgo", f"{_fmt_report_value(questionnaire.get('risk_index'))}/100"],
            ["Estado", "Completado" if questionnaire.get("completed_at") else "Pendiente"],
            ["Objetivo principal", _fmt_report_value(profile.get("goal") or daily_payload.get("goal"))],
            ["Nivel de actividad", _fmt_report_value(profile.get("level"))],
            ["Frecuencia de entrenamiento", _fmt_report_value(profile.get("frequency"))],
            ["Cervical", f"{_fmt_report_value(pain.get('neck') or pain.get('cervical'))}/10"],
            ["Torácica", f"{_fmt_report_value(pain.get('thor') or pain.get('thoracic'))}/10"],
            ["Lumbar", f"{_fmt_report_value(pain.get('lum') or pain.get('lumbar') or pain.get('low_back'))}/10"],
            ["Fatiga", f"{_fmt_report_value(daily_payload.get('fatigue'))}/10"],
            ["Sueño", f"{_fmt_report_value(daily_payload.get('sleep'))}/10"],
            ["RPE", f"{_fmt_report_value(daily_payload.get('rpe'))}/10"],
        ],
        [62 * mm, 118 * mm],
    )
    story.append(P("Recomendación principal: Mantener monitorización activa durante sesiones de entrenamiento y repetir calibración antes de cada sesión importante.", "AxisBody"))
    story.append(P("Acciones sugeridas: revisar técnica en ejercicios con carga; priorizar movilidad lumbar si el tiempo rojo lumbar supera al torácico; repetir cuestionario diario si hay dolor o fatiga alta.", "AxisSmall"))
    story.append(PageBreak())

    rom = baseline_payload.get("rom") if isinstance(baseline_payload.get("rom"), dict) else {}
    comp = baseline_payload.get("comp") if isinstance(baseline_payload.get("comp"), dict) else {}
    stability = baseline_payload.get("stability") if isinstance(baseline_payload.get("stability"), dict) else {}
    table(
        "Página 4 — Calibración / baseline",
        ["Campo", "Valor"],
        [
            ["Última calibración", _fmt_report_date(latest_baseline_date)],
            ["ID baseline", _fmt_report_value(baseline.get("id") or baseline.get("baseline_test_id") or report_data.get("calibration_state", {}).get("baseline_test_id"))],
            ["Sesión sensor asociada", _fmt_report_value(baseline.get("sensor_session_id"))],
            ["Estado", "Válida / Histórica" if baseline_payload else "Pendiente"],
            ["Fuente", _fmt_report_value(baseline.get("history_source") or baseline.get("source") or report_data.get("calibration_state", {}).get("source"))],
            ["Muestras usadas", _fmt_report_value(baseline_payload.get("n_samples"))],
            ["ROM torácico pitch", f"{_fmt_report_value(rom.get('thor_pitch'))}°"],
            ["ROM lumbar pitch", f"{_fmt_report_value(rom.get('lum_pitch'))}°"],
            ["Compensación media", f"{_fmt_report_value(comp.get('comp_avg'))}/100"],
            ["Compensación pico", f"{_fmt_report_value(comp.get('comp_peak'))}/100"],
            ["Estabilidad lumbar", _fmt_report_value(stability.get("lum_pitch_std"))],
            ["Estabilidad torácica", _fmt_report_value(stability.get("thor_pitch_std"))],
            ["Diferencia T/L media", _fmt_report_value(baseline_payload.get("diff_TL_pitch_mean"))],
        ],
        [62 * mm, 118 * mm],
    )
    story.append(P("La calibración sirve como referencia personal para comparar sesiones. Una calibración previa puede verse como historial, pero la sesión actual debe tener una calibración válida para medir con precisión.", "AxisSmall"))

    table(
        "Página 5 — Monitorización de sesiones",
        ["Fecha", "Modalidad", "Deporte", "Sesión", "Duración", "Riesgo", "Alertas"],
        [
            [
                _fmt_report_date(s.get("started_at")),
                _fmt_report_value(s.get("mode")),
                _fmt_report_value(s.get("sport")),
                _fmt_report_value(s.get("planned_session_name")),
                _fmt_duration_seconds(s.get("duration_s")),
                f"{_fmt_report_value(s.get('risk_index'))}/100",
                _fmt_report_value(s.get("alerts_count")),
            ]
            for s in sessions[:12]
        ],
    )
    table(
        "Resumen de la sesión seleccionada",
        ["Métrica", "Valor"],
        [
            ["Duración", _fmt_duration_seconds(latest_session.get("duration_s"))],
            ["Tiempo rojo torácico", _fmt_duration_seconds(latest_session.get("thor_red_s"))],
            ["Tiempo rojo lumbar", _fmt_duration_seconds(latest_session.get("lum_red_s"))],
            ["Alertas", _fmt_report_value(latest_session.get("alerts_count"))],
            ["Compensación media", _fmt_report_value(latest_session.get("comp_avg"))],
            ["Compensación pico", _fmt_report_value(latest_session.get("comp_peak"))],
            ["Risk Index", f"{_fmt_report_value(latest_session.get('risk_index'))}/100"],
        ],
        [62 * mm, 118 * mm],
    )
    story.append(PageBreak())

    story.append(P("Página 6 — Gráficas del monitor", "AxisSubtitle"))
    story.append(P("El PDF reserva esta sección para gráficas de inclinación, compensación y alertas. En esta versión exportable se priorizan tablas procesadas y resúmenes; las muestras RAW quedan disponibles en Exportar datos técnicos CSV.", "AxisBody"))
    story.append(P("Gráfica recomendada de inclinación: eje X tiempo de sesión, eje Y grados, líneas de torácica pitch, lumbar pitch y umbrales amarillo/rojo.", "AxisSmall"))
    story.append(P("Gráfica recomendada de compensación: eje X tiempo, eje Y compensación 0-100, zonas verde/amarillo/rojo.", "AxisSmall"))
    story.append(P("Gráfica recomendada de alertas: barras por sesión o por día, separando alertas torácicas, lumbares y de compensación.", "AxisSmall"))

    table(
        "Página 7 — Evolución diaria / semanal",
        ["Día", "Sesiones", "Duración", "Rojo torácico", "Rojo lumbar", "Comp. media", "Riesgo máx."],
        [
            [
                _fmt_report_value(d.get("day")),
                _fmt_report_value(d.get("sessions_count")),
                _fmt_duration_seconds(d.get("duration_s")),
                _fmt_duration_seconds(d.get("thor_red_s")),
                _fmt_duration_seconds(d.get("lum_red_s")),
                _fmt_report_value(d.get("comp_avg")),
                _fmt_report_value(d.get("risk_index_max")),
            ]
            for d in daily_summaries[:14]
        ],
    )

    thresholds = settings.get("thresholds") if isinstance(settings.get("thresholds"), dict) else {}
    active_mode = thresholds.get("train") if isinstance(thresholds.get("train"), dict) else thresholds
    thor = active_mode.get("thor") if isinstance(active_mode.get("thor"), dict) else {}
    lum = active_mode.get("lum") if isinstance(active_mode.get("lum"), dict) else {}
    table(
        "Página 8 — Umbrales y personalización",
        ["Segmento", "Pitch verde", "Pitch amarillo", "Roll verde", "Roll amarillo"],
        [
            ["Torácica", _fmt_report_value(thor.get("pitch_g")), _fmt_report_value(thor.get("pitch_y")), _fmt_report_value(thor.get("roll_g")), _fmt_report_value(thor.get("roll_y"))],
            ["Lumbar", _fmt_report_value(lum.get("pitch_g")), _fmt_report_value(lum.get("pitch_y")), _fmt_report_value(lum.get("roll_g")), _fmt_report_value(lum.get("roll_y"))],
        ],
    )
    table(
        "Adaptación personalizada",
        ["Campo", "Valor"],
        [
            ["Versión", _fmt_report_value(settings.get("version"))],
            ["Última actualización", _fmt_report_date(settings.get("updated_at"))],
            ["Fuente", "Cuestionario / baseline"],
            ["Reglas adaptadas", _fmt_report_value(json.dumps(settings.get("adaptation") or {}, ensure_ascii=False)[:300])],
        ],
        [62 * mm, 118 * mm],
    )
    story.append(PageBreak())

    table(
        "Página 9 — Rutinas y entrenamiento",
        ["Fecha", "Rutina", "Score medio", "Notas"],
        [
            [
                _fmt_report_value(r.get("day")),
                _fmt_report_value((r.get("plan") or {}).get("title") if isinstance(r.get("plan"), dict) else r.get("notes")),
                _fmt_report_value(r.get("score_avg")),
                _fmt_report_value(r.get("notes")),
            ]
            for r in routines[:10]
        ],
    )
    table(
        "Detalle por ejercicio",
        ["Ejercicio", "Set", "Reps objetivo", "Reps válidas", "Score", "Rojo T", "Rojo L", "Comp. media"],
        [
            [
                _fmt_report_value(e.get("exercise_name")),
                _fmt_report_value(e.get("set_index")),
                _fmt_report_value(e.get("reps_target")),
                _fmt_report_value(e.get("reps_valid")),
                _fmt_report_value(e.get("score_avg")),
                _fmt_duration_seconds(e.get("thor_red_s")),
                _fmt_duration_seconds(e.get("lum_red_s")),
                _fmt_report_value(e.get("comp_avg")),
            ]
            for e in exercise_sets[:16]
        ],
    )

    table(
        "Página 10 — Conclusiones y plan de acción",
        ["Prioridad", "Acción", "Motivo"],
        [
            ["Alta", "Repetir calibración antes de entrenar", "Mejora precisión"],
            ["Alta", "Revisar ejercicios con mayor rojo lumbar", "Mayor riesgo acumulado"],
            ["Media", "Añadir movilidad lumbar", "Reduce compensación"],
            ["Media", "Revisar fatiga/sueño en cuestionario diario", "Influye en postura"],
            ["Baja", "Exportar reporte semanal", "Seguimiento con entrenador"],
        ],
        [30 * mm, 80 * mm, 70 * mm],
    )
    story.append(P("Checklist: realizar calibración antes de la próxima sesión; revisar sesiones con riesgo mayor a 60/100; comparar tiempo rojo torácico vs lumbar; completar cuestionario diario si hay dolor o fatiga; compartir PDF con entrenador si hay tendencia negativa.", "AxisBody"))

    try:
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        if not pdf_bytes.startswith(b"%PDF"):
            fallback_lines = _build_axisfit_pdf_fallback_lines(report_data, reason="La salida generada no empieza con %PDF")
            return _build_valid_fallback_pdf_bytes("Informe PDF Axisfit", fallback_lines)
        return pdf_bytes
    except Exception as exc:
        fallback_lines = _build_axisfit_pdf_fallback_lines(report_data, reason=str(exc))
        return _build_valid_fallback_pdf_bytes("Informe PDF Axisfit", fallback_lines)


def _build_technical_csv_bytes(report_data):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["section", "source", "key", "value_1", "value_2", "value_3", "value_4", "value_5"])

    user = report_data.get("user") or {}
    for k in ["id", "name", "email", "country", "role", "ath_uso", "ath_nivel", "ath_freq", "ath_vas", "ath_altura", "ath_peso"]:
        writer.writerow(["user", "users", k, _fmt_report_value(user.get(k)), "", "", "", ""])

    q = report_data.get("questionnaire") or {}
    writer.writerow(["questionnaire", "questionnaire_sessions", "id", _fmt_report_value(q.get("id")), _fmt_report_value(q.get("type")), _fmt_report_date(q.get("started_at")), _fmt_report_date(q.get("completed_at")), _fmt_report_value(q.get("risk_index"))])

    baseline_payload = report_data.get("baseline_payload") or {}
    writer.writerow(["baseline", "baseline_tests", "payload_json", json.dumps(baseline_payload, ensure_ascii=False), "", "", "", ""])

    for s in report_data.get("sensor_sessions") or []:
        writer.writerow([
            "sensor_session",
            "sensor_sessions/session_summary",
            _fmt_report_value(s.get("id")),
            _fmt_report_date(s.get("started_at")),
            _fmt_report_date(s.get("ended_at")),
            _fmt_report_value(s.get("planned_session_name")),
            _fmt_report_value(s.get("duration_s")),
            _fmt_report_value(s.get("risk_index")),
        ])

    for d in report_data.get("daily_summaries") or []:
        writer.writerow([
            "daily_summary",
            "daily_summary",
            _fmt_report_value(d.get("day")),
            _fmt_report_value(d.get("sessions_count")),
            _fmt_report_value(d.get("duration_s")),
            _fmt_report_value(d.get("thor_red_s")),
            _fmt_report_value(d.get("lum_red_s")),
            _fmt_report_value(d.get("risk_index_max")),
        ])

    for r in report_data.get("raw_samples") or []:
        writer.writerow([
            "raw_sample",
            "sensor_samples_raw",
            _fmt_report_value(r.get("session_id")),
            _fmt_report_value(r.get("ts_ms")),
            _fmt_report_value(r.get("T_pitch")),
            _fmt_report_value(r.get("L_pitch")),
            _fmt_report_value(r.get("thor_zone")),
            _fmt_report_value(r.get("comp_index")),
        ])

    for a in report_data.get("agg_samples") or []:
        writer.writerow([
            "agg_sample",
            "sensor_samples_agg",
            _fmt_report_value(a.get("session_id")),
            _fmt_report_value(a.get("ts_s")),
            _fmt_report_value(a.get("T_pitch")),
            _fmt_report_value(a.get("L_pitch")),
            _fmt_report_value(a.get("thor_zone")),
            _fmt_report_value(a.get("comp_index")),
        ])

    for item in report_data.get("history_items") or []:
        writer.writerow([
            "live_history",
            "session-history-store",
            _fmt_report_value(item.get("ts")),
            _fmt_report_value(item.get("session")),
            _fmt_report_value(item.get("mode")),
            _fmt_report_value(item.get("score")),
            _fmt_report_value(item.get("bad_time")),
            _fmt_report_value(item.get("quality")),
        ])

    return output.getvalue().encode("utf-8-sig")




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
        "width": "20%",
        "minWidth": "20%",
        "maxWidth": "20%",
        "flex": "0 0 20%",
        "display": "flex",
        "flexDirection": "column",
        "gap": "8px",
        "minHeight": "0",
    }

    right_col_style = {
        "width": "100%",
        "minWidth": "0",
        "maxWidth": "100%",
        "flex": "1 1 0",
        "display": "flex",
        "flexDirection": "column",
        "gap": "8px",
        "minHeight": "0",
    }

    right_container_style = {
        "display": "grid",
        "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
        "gap": f"{RIGHT_INNER_GAP_PX}px",
        "alignItems": "stretch",
        "width": "100%",
        "minHeight": "0",
        "flex": "1 1 0",
    }

    right_area_style = {
        "width": "80%",
        "minWidth": "80%",
        "maxWidth": "80%",
        "flex": "0 0 80%",
        "display": "flex",
        "flexDirection": "column",
        "gap": "8px",
        "minHeight": "0",
    }

    # Compatibilidad visual solicitada:
    # - Estado del dispositivo vuelve a su altura objetivo del 20% del área derecha.
    # - El contenedor inferior de Postura en vivo + Gráficas vuelve a aprovechar el 80% restante.

    return html.Div(
        className="surface ax-monitor-surface",
        children=[
            dcc.Store(id="session-history-store", storage_type="local"),
            dcc.Store(id="active-session-store", storage_type="local"),
            dcc.Store(id="monitor-auth-session-store", storage_type="session"),
            dcc.Store(id="questionnaire-calibration-handoff-store", storage_type="session"),
            dcc.Store(id="calibration-store", storage_type="session"),
            dcc.Store(id="sim-state-store", data={"on": False, "reset_seq": 0}, storage_type="session"),
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
            dcc.Interval(id="recal-interval", interval=200, n_intervals=0, disabled=True),
            # PASO 2 — blindaje de entrada a Monitor:
            # Este intervalo de un solo disparo fuerza el estado operativo inicial
            # aunque Dash conserve stores de memoria al cambiar entre vistas.
            dcc.Interval(id="monitor-entry-reset-interval", interval=100, n_intervals=0, max_intervals=1, disabled=False),

            # Título + menú derecha
            html.Div(
                className="ax-monitor-title-row",
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
                className="ax-monitor-body",
                style={
                    "width": "100%",
                    "maxWidth": "100%",
                    "display": "flex",
                    "gap": "8px",
                    "alignItems": "stretch",
                    "flexWrap": "nowrap",
                    "overflowX": "hidden",
                    "flex": "1 1 0",
                    "minHeight": "0",
                },
                children=[
                    # ===== COLUMNA 1 (IZQUIERDA) =====
                    html.Div(
                        className="ax-monitor-left-col",
                        style=left_col_style,
                        children=[
                            # Estado
                            html.Div(
                                className=f"{MAIN_BLACK_CARD_CLASS} {MAIN_CARD_COL_CLASS} ax-control-session-card",
                                children=[
                                    html.Div(
                                        className=MAIN_CARD_HEADER_TIGHT_CLASS,
                                        children=[
                                            html.Div("Control de sesión", className=SECTION_TITLE_CLASS, style=RESPONSIVE_SECTION_TITLE_STYLE),
                                        ],
                                    ),
                                    html.Div(
                                        className=f"{PANEL_GROUP_TIGHT_CLASS} ax-control-session-panels",
                                        children=[
                                            html.Div(
                                                className=f"{SECONDARY_BLACK_PANEL_CLASS} ax-control-session-panel",
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
                                                    dbc.Button(
                                                        "Historial",
                                                        id="open-calibration-history-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=SECONDARY_BUTTON_CLASS,
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                className=f"{SECONDARY_BLACK_PANEL_CLASS} ax-control-session-panel",
                                                children=[
                                                    html.Div(
                                                        style={
                                                            "display": "flex",
                                                            "alignItems": "center",
                                                            "justifyContent": "space-between",
                                                            "gap": "10px",
                                                        },
                                                        children=[
                                                            html.Div("Ajuste de sesión", className=SECTION_TITLE_CLASS),
                                                            html.Div(
                                                                id="config-link-status-pill",
                                                                children=_status_value_badge("Sin vincular", "neutral"),
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(id="mode-summary-pill", children=_pill("Modalidad", _mode_label("train"), "neutral", full=True)),
                                                    html.Div(id="sport-summary-pill", children=_pill("Deporte", _sport_label("gym"), "neutral", full=True), style={"display": "none"}),
                                                    html.Div(id="session-summary-pill", children=_pill("Sesión del día", _default_session_for_mode("train"), "neutral", full=True), style={"display": "none"}),
                                                    dbc.Button(
                                                        "Editar sesión",
                                                        id="link-session-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=SECONDARY_BUTTON_CLASS,
                                                    ),
                                                    dbc.Button(
                                                        "Actividad y gráfica",
                                                        id="config-history-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=SECONDARY_BUTTON_CLASS,
                                                    ),
                                                    html.Div(id="active-session-label", style={"display": "none"}, children="Sesión activa: —"),
                                                    html.Div(id="active-session-badge", style={"display": "none"}, children=_pill("Sesión", "—", "neutral", full=True)),
                                                ],
                                            ),
                                            html.Div(
                                                className=f"{SECONDARY_BLACK_PANEL_CLASS} ax-control-session-panel",
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
                        className="ax-monitor-right-area",
                        style=right_area_style,
                        children=[
                            html.Div(
                                className=f"{MAIN_BLACK_CARD_CLASS} {MAIN_CARD_COL_CLASS} ax-device-card",
                                children=[
                                    html.Div(
                                        id="device-user-top",
                                        children=html.Div("Estado del dispositivo", className=SECTION_TITLE_CLASS, style={**RESPONSIVE_SECTION_TITLE_STYLE, "textAlign": "left"}),
                                        style={
                                            "width": "100%",
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
                                        className="ax-device-top-row ax-device-top-row-responsive",
                                        children=[
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
                                                className="ax-device-controls-wrap",
                                                style={"flex": "1 1 0", "minWidth": "0", "display": "flex", "alignItems": "stretch", "gap": "8px"},
                                                children=[
                                                    dbc.DropdownMenu(
                                                        id="sim-control-menu",
                                                        label="Apagado",
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
                                                        "OFF",
                                                        id="sim-status-badge",
                                                        color="secondary",
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
                                className="ax-monitor-right-content",
                                style=right_container_style,
                                children=[
                                    # ===== COLUMNA 2 =====
                                    html.Div(
                                        className="ax-monitor-half-col",
                                        style=right_col_style,
                                        children=[
                                            # Postura en vivo
                                            html.Div(
                                                className=f"{MAIN_BLACK_CARD_CLASS} {MAIN_CARD_COL_CLASS} ax-monitor-fill-card",
                                                children=[
                                                    html.Div("Postura en vivo", className=MAIN_CARD_TITLE_ONLY_CLASS, style=RESPONSIVE_SECTION_TITLE_STYLE),
                                                    html.Div(
                                                        className="ax-posture-live-inner-shell",
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
                                                                className="ax-posture-live-left-pane",
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
                                                                className=f"{SECONDARY_GRAY_PANEL_CLASS} ax-posture-live-right-pane",
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
                                                                    html.Div(
                                                                        className="ax-general-status-card",
                                                                        children=[
                                                                            html.Div(
                                                                                className="ax-status-section-head",
                                                                                children=[
                                                                                    html.Div("Estado general", className=SECTION_TITLE_CLASS),
                                                                                    html.Div("Resumen en tiempo real", className="ax-status-section-subtitle"),
                                                                                ],
                                                                            ),
                                                                            html.Div(
                                                                                className="ax-general-status-summary",
                                                                                children=[
                                                                                    html.Div(
                                                                                        className="ax-general-gauge-cell",
                                                                                        children=[
                                                                                            html.Div(id="posture-score", children=_posture_score_gauge(0, pending=True)),
                                                                                            html.Div("Score postural", className="ax-general-score-label"),
                                                                                        ],
                                                                                    ),
                                                                                    html.Div(
                                                                                        className="ax-general-meta-cell",
                                                                                        children=[
                                                                                            html.Div("Inclinación", className="ax-general-meta-label"),
                                                                                            html.Div(id="traffic-light", children=_empty_inclination_status()),
                                                                                        ],
                                                                                    ),
                                                                                ],
                                                                            ),
                                                                        ],
                                                                    ),
                                                                    html.Div(
                                                                        className="ax-detailed-status-card",
                                                                        children=[
                                                                            html.Div(
                                                                                className="ax-status-section-head",
                                                                                children=[
                                                                                    html.Div("Estado detallado", className=SECTION_TITLE_CLASS),
                                                                                ],
                                                                            ),
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
                                                                                            html.Div(className="ax-lumbar-comp-divider"),
                                                                                            html.Div(id="comp-output", children=_comp_output_block(0.0, pending=True)),
                                                                                        ],
                                                                                    ),
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
                                        className="ax-monitor-half-col",
                                        style=right_col_style,
                                        children=[
                                            # Gráficas
                                            html.Div(
                                                className=f"{MAIN_BLACK_CARD_CLASS} {MAIN_CARD_COL_CLASS} ax-monitor-fill-card",
                                                children=[
                                                    html.Div("Gráficas", className=MAIN_CARD_TITLE_ONLY_CLASS, style=RESPONSIVE_SECTION_TITLE_STYLE),
                                                    html.Div(
                                                        className=SECONDARY_GRAY_PANEL_CLASS,
                                                        style={"background": "rgba(0,0,0,.12)", "padding": "8px", "gap": "8px"},
                                                        children=[
                                                            dbc.RadioItems(
                                                                id="graphs-tabs",
                                                                options=[
                                                                    {"label": "Inclinación", "value": "imu"},
                                                                    {"label": "Estabilidad", "value": "sway"},
                                                                ],
                                                                value="imu",
                                                                className="ax-graphs-tabs ax-graphs-segmented",
                                                                inputClassName="ax-graphs-tab-input",
                                                                labelClassName="ax-btn ax-btn-gray ax-graphs-tab-button",
                                                                labelCheckedClassName="ax-btn ax-btn-gray ax-graphs-tab-button ax-graphs-tab-button-selected",
                                                                style={"display": "flex", "justifyContent": "stretch", "alignItems": "stretch", "gap": "8px", "width": "100%", "minWidth": "0", "padding": "0", "margin": "0", "flexWrap": "wrap", "lineHeight": "1.2"},
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
                                                                            dcc.Graph(id="imu-graph", style={"height": "100%", "width": "100%", "margin": "0", "padding": "0", "display": "block"}, figure=empty_imu_fig, config=IMU_GRAPH_CONFIG),
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
                                                                            dcc.Graph(id="sway-graph", style={"height": "100%", "width": "100%", "margin": "0", "padding": "0", "display": "block"}, figure=empty_sway_fig, config=SWAY_GRAPH_CONFIG),
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
                                                                className=f"{SECONDARY_GRAY_PANEL_CLASS} ax-alerts-gray-box",
                                                                style={"background": "rgba(255,255,255,.10)", "padding": "7px", "gap": "5px", "borderRadius": "8px"},
                                                                children=[
                                                                    html.Div(
                                                                        className="ax-alerts-gray-box-header",
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
                                        dbc.ModalTitle("Editar sesión", className=MODAL_TITLE_CLASS),
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
                                    html.Div("Ajusta modalidad, deporte y sesión vinculada.", className="mb-2", style={**BLACK_MUTED, "fontSize": "12px"}),
                                    html.Div(id="session-modal-preview", style={"display": "none"}),
                                    html.Div(
                                        style={"display": "flex", "flexDirection": "column", "gap": "12px"},
                                        children=[
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
                                                ],
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
                                                ],
                                            ),
                                            html.Div(
                                                className=SECONDARY_BLACK_PANEL_CLASS,
                                                children=[
                                                    html.Div("Sesión", className=MUTED_LABEL_CLASS, style={"marginBottom": "4px"}),
                                                    dbc.Select(
                                                        id="planned-session",
                                                        options=_session_options_for_mode("train"),
                                                        value=_default_session_for_mode("train"),
                                                        size="sm",
                                                        style={"width": "100%"},
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
                                    dbc.Button("Guardar", id="save-link-session-btn", color="primary", className=PRIMARY_BUTTON_CLASS),
                                    dbc.Button("Desvincular", id="unlink-session-btn", color="secondary", outline=True, className=OUTLINE_BUTTON_CLASS),
                                    dbc.Button("Cerrar", id="close-link-session-btn", color="secondary", outline=True, className=OUTLINE_BUTTON_CLASS),
                                ],
                                className=MODAL_FOOTER_CLASS,
                            ),
                        ],
                    ),
                    # Modal gráfica / histórico de sesiones
                    dbc.Modal(
                        id="config-history-modal",
                        backdrop=False,
                        is_open=False,
                        centered=True,
                        size="lg",
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
                                        dbc.ModalTitle("Actividad y gráfica", className=MODAL_TITLE_CLASS),
                                        html.Button(
                                            "×",
                                            id="close-config-history-x-btn",
                                            n_clicks=0,
                                            className=MODAL_CLOSE_X_CLASS,
                                        ),
                                    ],
                                ),
                                close_button=False,
                                className=MODAL_HEADER_CLASS,
                            ),
                            dbc.ModalBody(
                                html.Div(
                                    className=SECONDARY_BLACK_PANEL_CLASS,
                                    children=[
                                        dcc.Graph(id="history-graph", style={"height": "260px", "width": "100%"}, figure=empty_history_fig, config=GRAPH_TOOLBAR_CONFIG),
                                        html.Div(
                                            className=SECONDARY_GRAY_PANEL_CLASS,
                                            style={"maxHeight": "130px", "overflowY": "auto"},
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
                                className=MODAL_BODY_CLASS,
                            ),
                            dbc.ModalFooter(
                                [dbc.Button("Cerrar", id="close-config-history-btn", color="secondary", outline=True, className=OUTLINE_BUTTON_CLASS)],
                                className=MODAL_FOOTER_END_CLASS,
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
                                                        "Exportar informe PDF",
                                                        id="export-full-report-pdf-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=MODAL_GRAY_BUTTON_CLASS,
                                                        title="Genera todo el informe completo.",
                                                    ),
                                                    dbc.Button(
                                                        "Exportar resumen rápido",
                                                        id="export-quick-summary-pdf-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=MODAL_GRAY_BUTTON_CLASS,
                                                        title="Solo portada, resumen, última calibración y últimas sesiones.",
                                                    ),
                                                    dbc.Button(
                                                        "Exportar datos técnicos CSV",
                                                        id="export-technical-csv-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=MODAL_GRAY_BUTTON_CLASS,
                                                        title="RAW de sensores y agregados para análisis avanzado.",
                                                    ),
                                                    dbc.Button(
                                                        "Compartir con entrenador",
                                                        id="share-coach-report-btn",
                                                        color="secondary",
                                                        size="sm",
                                                        className=MODAL_GRAY_BUTTON_CLASS,
                                                        title="Futuro: enviar PDF o adjuntar al perfil.",
                                                    ),
                                                    html.Div(
                                                        "Exportar informe PDF: genera todo el informe completo. Exportar resumen rápido: solo portada, resumen, última calibración y últimas sesiones. Exportar datos técnicos CSV: RAW de sensores y agregados. Compartir con entrenador: futuro envío o adjunto al perfil.",
                                                        style={**BLACK_MUTED, "fontSize": "11px", "lineHeight": "1.35", "marginTop": "0px"},
                                                    ),
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
                                                    html.Li("Mantén buena postura durante 15 segundos seguidos."),
                                                    html.Li("Si se rompe la postura, el contador debe volver a 0 antes de guardar."),
                                                    html.Li("Si intentas encender la simulación sin calibración válida, se abrirá este modal en estado pendiente."),
                                                    html.Li("Pulsa “Iniciar calibración” para comenzar manualmente la espera de 15 segundos."),
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
                    # Modal Historial de calibraciones
                    dbc.Modal(
                        id="calibration-history-modal",
                        backdrop=False,
                        is_open=False,
                        centered=True,
                        size="xl",
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
                                        dbc.ModalTitle("Historial de calibraciones", className=MODAL_TITLE_CLASS),
                                        html.Button(
                                            "×",
                                            id="close-calibration-history-x-btn",
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
                                    html.Div(
                                        "Consulta todas las calibraciones guardadas del usuario actual y sus métricas principales.",
                                        className="mb-2",
                                        style={**BLACK_MUTED, "fontSize": "12px"},
                                    ),
                                    html.Div(
                                        id="calibration-history-content",
                                        children=_calibration_history_empty_block(),
                                    ),
                                ],
                                className=MODAL_BODY_CLASS,
                            ),
                            dbc.ModalFooter(
                                [
                                    dbc.Button("Cerrar", id="close-calibration-history-btn", color="secondary", outline=True, className=OUTLINE_BUTTON_CLASS),
                                ],
                                className=MODAL_FOOTER_END_CLASS,
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),

# =============================
# Callbacks
# =============================
def register_callbacks(app):
    @app.callback(
        Output("monitor-auth-session-store", "data"),
        Input("session-user", "data"),
        State("monitor-auth-session-store", "data"),
        prevent_initial_call=False,
    )
    def sync_monitor_auth_session(session_user, auth_session):
        user_id = _get_user_id(session_user)
        if user_id is None:
            return {"logged_out": True, "session_scope_id": None, "user_id": None}
        login_session_id = _get_login_session_id(session_user)
        auth_session = auth_session if isinstance(auth_session, dict) else {}
        try:
            auth_user_id = int(auth_session.get("user_id") or 0)
        except Exception:
            auth_user_id = None
        auth_login_session_id = auth_session.get("login_session_id")
        if (
            not auth_session.get("logged_out")
            and auth_session.get("session_scope_id")
            and auth_user_id == int(user_id)
            and (
                (login_session_id and str(auth_login_session_id or "") == str(login_session_id))
                or (not login_session_id)
            )
        ):
            auth_session["login_session_id"] = login_session_id or auth_login_session_id
            return auth_session
        return {
            "user_id": int(user_id),
            "session_scope_id": str(login_session_id or uuid.uuid4()),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "logged_out": False,
            "login_session_id": login_session_id,
        }

    @app.callback(
        [
            Output("calibration-history-modal", "is_open"),
            Output("calibration-history-content", "children"),
        ],
        [
            Input("open-calibration-history-btn", "n_clicks"),
            Input("close-calibration-history-btn", "n_clicks"),
            Input("close-calibration-history-x-btn", "n_clicks"),
            Input("session-user", "data"),
        ],
        [
            State("calibration-history-modal", "is_open"),
        ],
        prevent_initial_call=False,
    )
    def toggle_calibration_history_modal(open_n, close_n, close_x_n, session_user, is_open):
        trigger = ctx.triggered_id
        content = _build_calibration_history_table(session_user)
        if trigger == "open-calibration-history-btn":
            return True, content
        if trigger in ("close-calibration-history-btn", "close-calibration-history-x-btn"):
            return False, content
        return bool(is_open) if is_open else False, content

    @app.callback(
        [Output("sim-state-store", "data"), Output("imu-interval", "disabled"), Output("sim-status-badge", "children"), Output("sim-status-badge", "color"), Output("sim-control-menu", "label")],
        [
            Input("sim-on-item", "n_clicks"),
            Input("sim-off-item", "n_clicks"),
            Input("sim-reset-item", "n_clicks"),
            Input("calibration-store", "data"),
            Input("session-user", "data"),
            Input("monitor-auth-session-store", "data"),
            Input("monitor-entry-reset-interval", "n_intervals"),
        ],
        State("sim-state-store", "data"),
        prevent_initial_call=False,
    )
    def sim_control(_on, _off, _reset, calib, session_user, auth_session, _entry_reset_n, sim_state):
        sim_state = dict(sim_state or {"on": False, "reset_seq": 0})
        trig = ctx.triggered_id
        calib = _normalize_calibration_store(calib)
        active_calib = _get_active_calibration(calib)
        calibrated = _is_calibration_valid_for_auth_session(calib, session_user=session_user, auth_session=auth_session)
        calib_status = _normalize_calibration_status(active_calib.get("status", "Pendiente"))
        auto_started = bool(active_calib.get("auto_started"))

        # PASO 1 — regla maestra de invalidación:
        # sim_control mantiene únicamente el estado visual/operativo de simulación.
        # La escritura canónica de calibration-store en apagado/login queda centralizada
        # en recalibrate(...) mediante _invalidate_active_calibration_for_session(...),
        # evitando crear un segundo callback que escriba el mismo Output.
        # PASO 2 — estado inicial estricto de Monitor:
        # al montar la vista o cambiar usuario, la simulación vuelve siempre a OFF,
        # el intervalo IMU queda desactivado y el menú vuelve a Apagado.
        if trig == "calibration-store" and active_calib.get("source") == "questionnaire_baseline_session" and calibrated:
            sim_state["on"] = False
            return sim_state, True, "OFF", "secondary", "Apagado"

        if trig in (None, "session-user", "monitor-auth-session-store", "monitor-entry-reset-interval"):
            if calibrated and bool(sim_state.get("on", False)):
                return sim_state, False, "ON", "success", "Encendido"
            if calibrated:
                sim_state["on"] = False
                return sim_state, True, "OFF", "secondary", "Apagado"
            sim_state["on"] = False
            if calib_status == "En progreso":
                return sim_state, True, "CAL", "primary", "Calibrando"
            return sim_state, True, "PEND", "warning", "Pendiente"

        if trig == "sim-off-item":
            sim_state["on"] = False
            return sim_state, True, "OFF", "secondary", "Apagado"

        if trig == "sim-reset-item":
            sim_state["reset_seq"] = int(sim_state.get("reset_seq", 0)) + 1
            if calibrated and bool(sim_state.get("on", False)):
                return sim_state, False, "ON", "success", "Encendido"
            if calib_status == "En progreso":
                sim_state["on"] = False
                return sim_state, True, "CAL", "primary", "Calibrando"
            if bool(sim_state.get("on", False)) and not calibrated:
                sim_state["on"] = False
                return sim_state, True, "PEND", "warning", "Pendiente"
            return sim_state, True, "OFF", "secondary", "Apagado"

        if trig == "sim-on-item":
            if calibrated:
                sim_state["on"] = True
                return sim_state, False, "ON", "success", "Encendido"
            sim_state["on"] = False
            if calib_status == "En progreso":
                return sim_state, True, "CAL", "primary", "Calibrando"
            return sim_state, True, "PEND", "warning", "Pendiente"

        if calibrated and auto_started and not bool(sim_state.get("on", False)):
            sim_state["on"] = False
            return sim_state, True, "OFF", "secondary", "Apagado"

        if not bool(sim_state.get("on", False)):
            if calib_status == "En progreso":
                return sim_state, True, "CAL", "primary", "Calibrando"
            return sim_state, True, "OFF", "secondary", "Apagado"

        if calibrated:
            return sim_state, False, "ON", "success", "Encendido"

        if calib_status == "En progreso":
            sim_state["on"] = False
            return sim_state, True, "CAL", "primary", "Calibrando"

        sim_state["on"] = False
        return sim_state, True, "PEND", "warning", "Pendiente"


    @app.callback(
        [Output("device-user-top", "children"), Output("device-state-top", "children")],
        [Input("session-user", "data"), Input("sim-state-store", "data")],
        prevent_initial_call=False,
    )
    def update_device_top_bar(session_user, sim_state):
        _ = _get_user_display_name(session_user)
        sim_on = bool((sim_state or {}).get("on", False))
        state_value = "Operativo" if sim_on else "Pausado"
        state_tone = "ok" if sim_on else "warn"
        return (
            html.Div("Estado del dispositivo", className=SECTION_TITLE_CLASS, style={**RESPONSIVE_SECTION_TITLE_STYLE, "textAlign": "left"}),
            _hidden_device_state_placeholder(state_value, state_tone),
        )

    @app.callback(
        Output("config-history-modal", "is_open"),
        [
            Input("config-history-btn", "n_clicks"),
            Input("close-config-history-btn", "n_clicks"),
            Input("close-config-history-x-btn", "n_clicks"),
        ],
        State("config-history-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_config_history_modal(open_n, close_n, close_x_n, is_open):
        trigger = ctx.triggered_id
        if trigger == "config-history-btn":
            return True
        if trigger in ("close-config-history-btn", "close-config-history-x-btn"):
            return False
        return bool(is_open)

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
            Output("config-link-status-pill", "children"),
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
        is_linked = bool(active_session.get("name") or active_session.get("planned_session_name") or active_session.get("questionnaire_session_id") or active_session.get("routine_session_id"))
        return (
            _pill("Modalidad", _mode_label(display_mode), "neutral", full=True),
            _pill("Deporte", _sport_label(display_sport), "neutral", full=True),
            _pill("Sesión del día", display_session or "—", "neutral", full=True),
            _status_value_badge("Vinculado" if is_linked else "Sin vincular", "ok" if is_linked else "neutral"),
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
        [
            Input("calibration-store", "data"),
            Input("monitor-auth-session-store", "data"),
        ],
        State("session-user", "data"),
        prevent_initial_call=False,
    )
    def sync_graph_calibration_visibility(calib, auth_session, session_user):
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

        if _is_calibration_valid_for_auth_session(calib, session_user=session_user, auth_session=auth_session):
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
        [
            Input("export-history-btn", "n_clicks"),
            Input("export-window-btn", "n_clicks"),
            Input("export-full-report-pdf-btn", "n_clicks"),
            Input("export-quick-summary-pdf-btn", "n_clicks"),
            Input("export-technical-csv-btn", "n_clicks"),
            Input("share-coach-report-btn", "n_clicks"),
        ],
        [
            State("session-history-store", "data"),
            State("session-user", "data"),
            State("active-session-store", "data"),
            State("calibration-store", "data"),
            State("recorder-store", "data"),
        ],
        prevent_initial_call=True,
    )
    def export_monitor_download(_hist_n, _win_n, _full_pdf_n, _quick_pdf_n, _tech_csv_n, _share_n, history_store, session_user, active_session, calib, recorder):
        trig = ctx.triggered_id

        # ---- INFORME PDF COMPLETO ----
        if trig == "export-full-report-pdf-btn":
            report_data = _build_report_data(session_user, active_session=active_session, calib=calib, recorder=recorder, history_store=history_store)
            pdf_bytes = _build_axisfit_pdf_bytes(report_data, report_kind="full")
            filename = make_filename("axisfit_informe_postural_completo", ext="pdf")
            return dcc.send_bytes(pdf_bytes, filename)

        # ---- RESUMEN RÁPIDO PDF ----
        if trig == "export-quick-summary-pdf-btn":
            report_data = _build_report_data(session_user, active_session=active_session, calib=calib, recorder=recorder, history_store=history_store)
            pdf_bytes = _build_axisfit_pdf_bytes(report_data, report_kind="quick")
            filename = make_filename("axisfit_resumen_postural_rapido", ext="pdf")
            return dcc.send_bytes(pdf_bytes, filename)

        # ---- DATOS TÉCNICOS CSV ----
        if trig == "export-technical-csv-btn":
            report_data = _build_report_data(session_user, active_session=active_session, calib=calib, recorder=recorder, history_store=history_store)
            csv_bytes = _build_technical_csv_bytes(report_data)
            filename = make_filename("axisfit_datos_tecnicos", ext="csv")
            return dcc.send_bytes(csv_bytes, filename)

        # ---- COMPARTIR CON ENTRENADOR (MVP descargable) ----
        if trig == "share-coach-report-btn":
            report_data = _build_report_data(session_user, active_session=active_session, calib=calib, recorder=recorder, history_store=history_store)
            pdf_bytes = _build_axisfit_pdf_bytes(report_data, report_kind="quick")
            filename = make_filename("axisfit_informe_para_entrenador", ext="pdf")
            return dcc.send_bytes(pdf_bytes, filename)

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
        Output("recal-interval", "disabled"),
        Input("calibration-store", "data"),
        prevent_initial_call=False,
    )
    def recalibration_interval_toggle(calib):
        status = _normalize_calibration_status((calib or {}).get("status", "Pendiente"))
        return status != "En progreso"

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
        [
            Input("open-recal-btn", "n_clicks"),
            Input("close-recal-btn", "n_clicks"),
            Input("close-recal-x-btn", "n_clicks"),
            Input("start-recal-btn", "n_clicks"),
            Input("session-user", "data"),
            Input("monitor-auth-session-store", "data"),
            Input("questionnaire-calibration-handoff-store", "data"),
            Input("sim-on-item", "n_clicks"),
            Input("sim-off-item", "n_clicks"),
        ],
        [State("recal-modal", "is_open"), State("calibration-store", "data")],
        prevent_initial_call=False,
    )
    def recalibrate(open_n, close_n, close_x_n, start_n, session_user, auth_session, questionnaire_handoff, sim_on_n, sim_off_n, is_open, calib):
        trigger = ctx.triggered_id
        calib = _normalize_calibration_store(calib)
        auth_session = auth_session if isinstance(auth_session, dict) else {}
        if trigger in ("session-user", "monitor-auth-session-store", "questionnaire-calibration-handoff-store") or trigger is None:
            # PASO 1 — cada inicio/hidratación de sesión invalida la calibración activa.
            # El baseline de DB se conserva en historical_baseline_reference, pero nunca
            # reactiva valid_for_current_session ni deja el badge como Completada.
            if _get_user_id(session_user) is None or auth_session.get("logged_out"):
                calib = _invalidate_active_calibration_for_session("logged_out", session_user=session_user, auth_session=auth_session)
            elif _questionnaire_reset_should_invalidate_monitor_calibration(questionnaire_handoff, calib, session_user=session_user):
                calib = _invalidate_active_calibration_for_session("questionnaire_reset_requires_recalibration", session_user=session_user, auth_session=auth_session)
            elif _is_calibration_valid_for_auth_session(calib, session_user=session_user, auth_session=auth_session):
                status = _normalize_calibration_status(_get_active_calibration(calib).get("status", "Completada"))
                return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)
            elif _build_calibration_state_from_questionnaire_handoff(questionnaire_handoff, session_user=session_user, auth_session=auth_session):
                calib = _build_calibration_state_from_questionnaire_handoff(questionnaire_handoff, session_user=session_user, auth_session=auth_session)
                status = _normalize_calibration_status(_get_active_calibration(calib).get("status", "Completada"))
                return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)
            elif (
                _is_calibration_completed(_get_active_calibration(calib))
                and str(_get_active_calibration(calib).get("calibration_user_id") or "") == str(_get_user_id(session_user))
                and _get_login_session_id(session_user)
                and str(_get_active_calibration(calib).get("login_session_id") or "") == str(_get_login_session_id(session_user))
                and auth_session.get("session_scope_id")
            ):
                active = _get_active_calibration(calib)
                active["session_scope_id"] = auth_session.get("session_scope_id")
                active["login_session_id"] = _get_login_session_id(session_user)
                calib = _build_calibration_store(active, _get_historical_baseline_reference(calib), preserve_extra=calib)
                status = _normalize_calibration_status(active.get("status", "Completada"))
                return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)
            else:
                calib = _invalidate_active_calibration_for_session("new_login_requires_recalibration", session_user=session_user, auth_session=auth_session)
            status = _normalize_calibration_status(_get_active_calibration(calib).get("status", "Pendiente"))
            return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)

        status = _normalize_calibration_status(_get_active_calibration(calib).get("status", "Pendiente"))

        if trigger == "sim-off-item":
            # PASO 1 — apagar simulación invalida la calibración activa inmediatamente.
            # La referencia histórica queda visible, pero la sesión vuelve a Pendiente.
            calib = _invalidate_active_calibration_for_session("sim_off_requires_recalibration", session_user=session_user, auth_session=auth_session)
            status = _normalize_calibration_status(_get_active_calibration(calib).get("status", "Pendiente"))
            return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)

        if trigger == "open-recal-btn":
            if not calib:
                calib = _build_pending_calibration_state("manual_recalibration", session_user=session_user, auth_session=auth_session)
            status = _normalize_calibration_status(_get_active_calibration(calib).get("status", "Pendiente"))
            return True, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)

        if trigger in ("close-recal-btn", "close-recal-x-btn"):
            return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)

        if trigger == "start-recal-btn":
            calib = _build_in_progress_calibration_state(session_user=session_user, auth_session=auth_session, auto_started=False)
            status = _normalize_calibration_status(calib.get("status", "En progreso"))
            return True, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), "Calibrando 0.0/15.0 s"

        if trigger == "sim-on-item":
            if _is_calibration_valid_for_auth_session(calib, session_user=session_user, auth_session=auth_session):
                return False, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)
            calib = _build_pending_calibration_state("sim_on_requires_manual_calibration", session_user=session_user, auth_session=auth_session)
            status = _normalize_calibration_status(calib.get("status", "Pendiente"))
            return True, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)

        return is_open, calib, _calibration_pill(status), _calibration_action_label(status), _calibration_popup_status_from_state(calib), _calibration_pill(status), _calibration_action_label(status)

    @app.callback(
        [
            Output("calibration-store", "data", allow_duplicate=True),
            Output("calibration-pill", "children", allow_duplicate=True),
            Output("open-recal-btn", "children", allow_duplicate=True),
            Output("recal-status-text", "children", allow_duplicate=True),
            Output("recal-status-pill", "children", allow_duplicate=True),
            Output("start-recal-btn", "children", allow_duplicate=True),
            Output("recal-modal", "is_open", allow_duplicate=True),
        ],
        Input("recal-interval", "n_intervals"),
        State("calibration-store", "data"),
        State("session-user", "data"),
        State("monitor-auth-session-store", "data"),
        prevent_initial_call=True,
    )
    def recalibration_tick(_n, calib, session_user, auth_session):
        calib = _normalize_calibration_store(calib)
        status = _normalize_calibration_status(_get_active_calibration(calib).get("status", "Pendiente"))
        if status != "En progreso":
            raise PreventUpdate

        started_at_ms = int(calib.get("started_at_epoch_ms") or 0)
        target_wait_s = float(calib.get("target_wait_s") or 15.0)
        if started_at_ms <= 0:
            started_at_ms = int(time.time() * 1000)
            calib["started_at_epoch_ms"] = started_at_ms

        elapsed_s = max(0.0, (int(time.time() * 1000) - started_at_ms) / 1000.0)
        if elapsed_s >= target_wait_s:
            user_id = _get_user_id(session_user)
            try:
                win = IMU_SIM.get_window(seconds=max(20.0, target_wait_s + 5.0))
            except Exception:
                win = {}
            baseline_payload = _build_monitor_simulated_baseline_from_window(win)
            baseline_id = None
            if user_id is not None:
                try:
                    baseline_id = create_baseline_test(
                        user_id=int(user_id),
                        sensor_session_id=None,
                        baseline=baseline_payload,
                    )
                except Exception:
                    baseline_id = None

            if baseline_id is None:
                failed = _build_pending_calibration_state("monitor_baseline_save_failed", session_user=session_user, auth_session=auth_session)
                failed["ts"] = datetime.now().isoformat(timespec="seconds")
                pending_status = _normalize_calibration_status(failed.get("status", "Pendiente"))
                return failed, _calibration_pill(pending_status), _calibration_action_label(pending_status), "Estado actual: Pendiente · no se pudo guardar la calibración en DB", _calibration_pill(pending_status), _calibration_action_label(pending_status), True

            completed_at_iso = datetime.now().isoformat(timespec="seconds")
            completed_history = _legacy_history_fields_from_reference({
                "id": baseline_id,
                "baseline_test_id": baseline_id,
                "created_at": completed_at_iso,
                "baseline": baseline_payload,
                "baseline_payload": baseline_payload,
                "summary": _build_monitor_baseline_summary_for_store(baseline_payload),
                "source": "baseline_tests",
                "history_source": "baseline_tests",
                "is_valid": True,
                "status": "Completada",
            })
            completed_active = {
                "status": "Completada",
                "source": "baseline_db_monitor_session",
                "ts": completed_at_iso,
                "started_at_epoch_ms": started_at_ms,
                "completed_at_epoch_ms": int(time.time() * 1000),
                "baseline_test_id": baseline_id,
                "baseline_payload": baseline_payload,
                "valid_for_current_session": True,
                "session_scope_id": (auth_session or {}).get("session_scope_id"),
                "calibration_user_id": user_id,
                "login_session_id": _get_login_session_id(session_user),
                "simulated": True,
                "target_wait_s": target_wait_s,
                "elapsed_s": round(target_wait_s, 1),
                "remaining_s": 0.0,
                "auto_started": bool(calib.get("auto_started")),
            }
            completed = _build_calibration_store(completed_active, completed_history, preserve_extra={})
            done_status = _normalize_calibration_status(completed.get("status", "Completada"))
            return completed, _calibration_pill(done_status), _calibration_action_label(done_status), _calibration_popup_status_from_state(completed), _calibration_pill(done_status), _calibration_action_label(done_status), False

        calib["elapsed_s"] = round(elapsed_s, 1)
        calib["remaining_s"] = round(max(0.0, target_wait_s - elapsed_s), 1)
        in_progress_status = _normalize_calibration_status(calib.get("status", "En progreso"))
        progress_label = f"Calibrando {elapsed_s:.1f}/{target_wait_s:.1f} s"
        return calib, _calibration_pill(in_progress_status), _calibration_action_label(in_progress_status), _calibration_popup_status_from_state(calib), _calibration_pill(in_progress_status), progress_label, True

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
            State("monitor-auth-session-store", "data"),
        ],
        prevent_initial_call=True,
    )
    def recorder_control(start_n, stop_n, recorder, active_session, mode_ui, sport_ui, calib, session_user, auth_session):
        recorder = recorder or {
            "on": False,
            "session_id": None,
            "main_session_id": None,
            "status_label": "sin_iniciar",
            "started_at_epoch_ms": None,
            "elapsed_label": "00:00",
        }
        trig = ctx.triggered_id

        calibrated = _is_calibration_valid_for_auth_session(calib, session_user=session_user, auth_session=auth_session)
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
                "goal": runtime_active_session.get("goal") or "",
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
            State("monitor-auth-session-store", "data"),
        ],
        prevent_initial_call=False,
    )
    def update_realtime(_n_intervals, sim_state, mode_ui, alerts_on, active_session, history_store, calib, recorder, sport_ui, session_user, auth_session):
        sim_state = sim_state or {"on": False, "reset_seq": 0}
        if not bool(sim_state.get("on", False)):
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

        calibrated = _is_calibration_valid_for_auth_session(calib, session_user=session_user, auth_session=auth_session)
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
                _posture_score_gauge(0, pending=True),
                _empty_inclination_status(),
                "",
                general_note_hidden_style,
                [html.Li("— (sin datos aún)")],
                history_store,
                empty_hist,
                [html.Li("— (sin historial)")],
                {"fontSize": "34px", "color": "rgba(226,232,240,.90)", "transform": "rotate(-10deg)"},
                {"display": "none"},
                _traffic_light_zone("empty"),
                _traffic_light_zone("empty"),
                _zone_status_badge("empty"),
                _zone_status_badge("empty"),
                "",
                "",
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
                _posture_score_gauge(0, pending=True),
                _empty_inclination_status(),
                "",
                general_note_hidden_style,
                [html.Li("— (sin datos aún)")],
                history_store,
                empty_hist,
                [html.Li("— (sin historial)")],
                {"fontSize": "34px", "color": "rgba(226,232,240,.90)", "transform": "rotate(-10deg)"},
                {"display": "none"},
                _traffic_light_zone("empty"),
                _traffic_light_zone("empty"),
                _zone_status_badge("empty"),
                _zone_status_badge("empty"),
                "",
                "",
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

        thor_status_text = _zone_status_badge(thor_zone_last)
        lum_status_text = _zone_status_badge(lum_zone_last)
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
            _posture_score_gauge(score_now),
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
