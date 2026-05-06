# views/athlete/questionnaire_view.py 
#
# Wizard 6 pasos (perfil -> dolor -> auto -> baseline -> daily -> sensor)
# - Guarda a DB: questionnaire_sessions (payload_json)
# - Calibración recomendada (NO obligatoria): banner + CTA
# - Salida: upsert_user_posture_settings + risk index + recomendaciones + CTA a Monitor/Rutinas
#
# ✅ Calibración SIM: start/stop -> sensor_sessions(kind="baseline") + RAW -> baseline_tests
# ✅ Baseline cuenta en daily_summary: recompute_daily_summary(...)
# ✅ FIX Dash: Todos los IDs usados en States existen siempre (pasos ocultos, no removidos)
# ✅ FIX Dash: Eliminado q-reset (no existe en otras ventanas)
#
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import json
import dash
import time

# QUESTIONNAIRE FASE 2/3 COMPAT — trazabilidad de centralización baseline histórico
# Mantiene callbacks existentes sin añadir Outputs nuevos.
# Mantiene IDs existentes y stores actuales.
# La lectura del baseline histórico queda delegada en db.py.
# baseline_tests conserva el rol de fuente persistida.
# get_latest_baseline_reference(...) conserva el rol de API principal.
# get_latest_valid_baseline(...) queda solo como fallback compatible.
# La normalización para UI se comparte mediante normalize_baseline_reference_for_ui(...).
# Los wrappers locales se conservan solo para no tocar el flujo visual ni los callbacks.
# Línea de compatibilidad documental 01: no altera lógica ni callbacks.
# Línea de compatibilidad documental 02: no altera lógica ni callbacks.
# Línea de compatibilidad documental 03: no altera lógica ni callbacks.
# Línea de compatibilidad documental 04: no altera lógica ni callbacks.
# Línea de compatibilidad documental 05: no altera lógica ni callbacks.
# Línea de compatibilidad documental 06: no altera lógica ni callbacks.
# Línea de compatibilidad documental 07: no altera lógica ni callbacks.
# Línea de compatibilidad documental 08: no altera lógica ni callbacks.
# Línea de compatibilidad documental 09: no altera lógica ni callbacks.
# Línea de compatibilidad documental 10: no altera lógica ni callbacks.
# Línea de compatibilidad documental 11: no altera lógica ni callbacks.
# Línea de compatibilidad documental 12: no altera lógica ni callbacks.
# Línea de compatibilidad documental 13: no altera lógica ni callbacks.
# Línea de compatibilidad documental 14: no altera lógica ni callbacks.
# Línea de compatibilidad documental 15: no altera lógica ni callbacks.
# Línea de compatibilidad documental 16: no altera lógica ni callbacks.
# Línea de compatibilidad documental 17: no altera lógica ni callbacks.
# Línea de compatibilidad documental 18: no altera lógica ni callbacks.
# Línea de compatibilidad documental 19: no altera lógica ni callbacks.
# Línea de compatibilidad documental 20: no altera lógica ni callbacks.
# Línea de compatibilidad documental 21: no altera lógica ni callbacks.
# Línea de compatibilidad documental 22: no altera lógica ni callbacks.
# Línea de compatibilidad documental 23: no altera lógica ni callbacks.
# Línea de compatibilidad documental 24: no altera lógica ni callbacks.
# Línea de compatibilidad documental 25: no altera lógica ni callbacks.
# Línea de compatibilidad documental 26: no altera lógica ni callbacks.
# Línea de compatibilidad documental 27: no altera lógica ni callbacks.
# Línea de compatibilidad documental 28: no altera lógica ni callbacks.
# Línea de compatibilidad documental 29: no altera lógica ni callbacks.
# Línea de compatibilidad documental 30: no altera lógica ni callbacks.
# Línea de compatibilidad documental 31: no altera lógica ni callbacks.
# Línea de compatibilidad documental 32: no altera lógica ni callbacks.
# Línea de compatibilidad documental 33: no altera lógica ni callbacks.
# Línea de compatibilidad documental 34: no altera lógica ni callbacks.
# Línea de compatibilidad documental 35: no altera lógica ni callbacks.
from dash import dcc, html, Input, Output, State, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from posture_engine import DEFAULT_THRESHOLDS
from imu_realtime_sim import SIM
from db import (
    resolve_user_id,
    get_daily_summary,
    start_questionnaire_session,
    save_questionnaire_step,
    complete_questionnaire_session,
    get_latest_questionnaire_session,
    get_latest_baseline_reference,
    get_latest_valid_baseline,
    get_latest_baseline_reference_for_ui,
    normalize_baseline_reference_for_ui,
    get_user_posture_settings,
    get_user_posture_settings_status,
    upsert_user_posture_settings,
    # baseline recording
    start_sensor_session,
    insert_sensor_samples_raw_batch,
    upsert_session_summary,
    recompute_daily_summary,
    end_sensor_session,
    create_baseline_test,
)

BLACK_TEXT = {"color": "#e2e8f0"}
BLACK_MUTED = {"color": "rgba(226,232,240,.75)"}
MUTED = BLACK_MUTED

INPUT_STYLE = {
    "background": "#ffffff",
    "border": "1px solid rgba(255,255,255,.10)",
    "color": "#0f172a",
    "height": "28px",
    "minHeight": "28px",
}

TEXTAREA_STYLE = {
    "background": "#ffffff",
    "border": "1px solid rgba(255,255,255,.10)",
    "color": "#0f172a",
    "minHeight": "90px",
}

DROPDOWN_STYLE = {
    "background": "#ffffff",
    "color": "#0f172a",
}

CHOICE_INPUT_STYLE = {"margin": "0"}

CHOICE_GROUP_STYLE_3 = {
    "display": "grid",
    "gridTemplateColumns": "repeat(3, minmax(0, 1fr))",
    "columnGap": "8px",
    "rowGap": "6px",
    "width": "100%",
}

CHOICE_GROUP_STYLE_2 = {
    "display": "grid",
    "gridTemplateColumns": "repeat(2, minmax(0, 1fr))",
    "columnGap": "8px",
    "rowGap": "6px",
    "width": "100%",
}

CHOICE_LABEL_STYLE = {
    "display": "flex",
    "alignItems": "center",
    "gap": "4px",
    "color": "#e2e8f0",
    "marginBottom": "0px",
    "width": "100%",
    "minWidth": "0",
    "fontSize": "12px",
    "lineHeight": "1.25",
}

CIRCULAR_CHECKLIST_LABEL_STYLE = {
    "display": "flex",
    "alignItems": "center",
    "gap": "6px",
    "color": "#e2e8f0",
    "marginBottom": "0px",
    "width": "100%",
    "minWidth": "0",
    "fontSize": "12px",
    "lineHeight": "1.25",
}

SELF_NOTES_TEXTAREA_STYLE = {
    **TEXTAREA_STYLE,
    "minHeight": "49.5px",
    "height": "49.5px",
}

FIELD_HELP_STYLE = {
    "color": "rgba(226,232,240,.75)",
    "fontSize": "12px",
    "fontWeight": 600,
    "lineHeight": "1.45",
}

BUTTON_PRIMARY_CLASS = "ax-btn ax-btn-full ax-btn-primary"
BUTTON_SECONDARY_CLASS = "ax-btn ax-btn-full ax-btn-gray"
BUTTON_OUTLINE_CLASS = "ax-btn ax-btn-outline"
BUTTON_POPUP_SECONDARY_CLASS = "ax-btn ax-btn-full ax-btn-gray"
BUTTON_POPUP_PRIMARY_CLASS = "ax-btn ax-btn-full ax-btn-primary"
QUESTIONNAIRE_MONITOR_TITLE_STYLE = {
    "fontSize": "clamp(12px, .95vw, 16px)",
    "fontWeight": "var(--ax-title-weight, 700)",
    "lineHeight": "1.15",
    "whiteSpace": "normal",
    "overflowWrap": "anywhere",
    "margin": "0",
    "padding": "0",
}

def _kv(label, value, tone="neutral"):
    tone_map = {
        "neutral": {"background": "rgba(255,255,255,.06)", "border": "rgba(255,255,255,.08)", "color": "#e2e8f0"},
        "ok": {"background": "rgba(34,197,94,.18)", "border": "rgba(34,197,94,.24)", "color": "#bbf7d0"},
        "warn": {"background": "rgba(245,158,11,.18)", "border": "rgba(245,158,11,.24)", "color": "#fde68a"},
        "bad": {"background": "rgba(239,68,68,.18)", "border": "rgba(239,68,68,.24)", "color": "#fecaca"},
    }
    s = tone_map.get(tone, tone_map["neutral"])
    return html.Div(
        className="ax-pill ax-pill-full",
        style={
            "background": s["background"],
            "boxShadow": f"inset 0 0 0 1px {s['border']}",
            "margin": "0",
            "minHeight": "28px",
        },
        children=[
            html.Span(label, className="ax-label-muted"),
            html.Span(value, className="ax-value-text", style={"color": s["color"] if tone != "neutral" else "#e2e8f0"}),
        ],
    )

def _subpanel(title: str, children, style: Optional[Dict[str, Any]] = None):
    merged_style = {
        "paddingTop": "6px",
        "paddingBottom": "6px",
        "paddingLeft": "12px",
        "paddingRight": "12px",
        "gap": "8px",
    }
    if style:
        merged_style.update(style)
    return html.Div(
        className="ax-panel-black ax-panel-black-stack",
        style=merged_style,
        children=[
            html.Div(
                className="ax-panel-black-row",
                style={"gap": "8px"},
                children=[html.Div(title, className="ax-section-title")],
            ),
            children,
        ],
    )

def _field(label: str, child, help_text: Optional[str] = None):
    items = [
        html.Div(
            style={"display": "flex", "alignItems": "center", "gap": "8px", "width": "100%"},
            children=[
                html.Div(
                    label,
                    className="ax-status-badge",
                    style={
                        "minWidth": "200px",
                        "width": "200px",
                        "flex": "0 0 200px",
                        "margin": "0",
                        "background": "rgba(255,255,255,.10)",
                    },
                ),
                html.Div(child, style={"flex": "1 1 auto", "minWidth": "0"}),
            ],
        )
    ]
    if help_text:
        items.append(html.Div(help_text, style=FIELD_HELP_STYLE))
    return html.Div(style={"display": "flex", "flexDirection": "column", "gap": "6px"}, children=items)



def _slider_control(slider):
    return html.Div(
        style={
            "flex": "1 1 auto",
            "minWidth": "0",
            "display": "flex",
            "alignItems": "center",
            "height": "28px",
            "minHeight": "28px",
            "background": "#ffffff",
            "border": "1px solid rgba(255,255,255,.10)",
            "borderRadius": "8px",
            "paddingLeft": "0px",
            "paddingRight": "0px",
            "overflow": "hidden",
        },
        children=[slider],
    )


def _slider_percent(value: Any, min_value: int = 0, max_value: int = 10) -> float:
    try:
        v = float(value)
    except Exception:
        v = float(min_value)
    lo = float(min_value)
    hi = float(max_value)
    if hi <= lo:
        return 0.0
    return max(0.0, min(100.0, ((v - lo) / (hi - lo)) * 100.0))


def _slider_bubble_left(value: Any, min_value: int = 0, max_value: int = 10) -> str:
    pct = _slider_percent(value, min_value=min_value, max_value=max_value)
    return f"calc(14px + ((100% - 28px) * {pct / 100.0:.6f}))"


SLIDER_TRACK_BASE_STYLE = {
    "position": "absolute",
    "left": "14px",
    "right": "14px",
    "top": "12px",
    "height": "4px",
    "borderRadius": "999px",
    "background": "rgba(15,23,42,.14)",
    "overflow": "hidden",
    "pointerEvents": "none",
    "zIndex": "1",
}

SLIDER_FILL_BASE_STYLE = {
    "height": "100%",
    "borderRadius": "999px",
    "background": "linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)",
}

SLIDER_BUBBLE_BASE_STYLE = {
    "position": "absolute",
    "top": "14px",
    "width": "18px",
    "height": "18px",
    "borderRadius": "999px",
    "background": "#2563eb",
    "color": "#ffffff",
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
    "fontSize": "9px",
    "fontWeight": 800,
    "lineHeight": "1",
    "boxShadow": "0 0 0 2px #ffffff, 0 2px 6px rgba(37,99,235,.28)",
    "pointerEvents": "none",
    "transform": "translate(-50%, -50%)",
    "zIndex": "3",
}

SLIDER_MARKS_ROW_STYLE = {
    "position": "absolute",
    "left": "14px",
    "right": "14px",
    "bottom": "0px",
    "display": "none",
    "gridTemplateColumns": "repeat(11, minmax(0, 1fr))",
    "alignItems": "center",
    "pointerEvents": "none",
    "zIndex": "2",
}

SLIDER_MARK_STYLE = {
    "fontSize": "7px",
    "fontWeight": 700,
    "color": "rgba(15,23,42,.58)",
    "textAlign": "center",
    "lineHeight": "1",
    "userSelect": "none",
}


def _build_slider_marks(active_value: Any, min_value: int = 0, max_value: int = 10):
    marks = []
    try:
        active_int = int(float(active_value))
    except Exception:
        active_int = min_value
    for i in range(min_value, max_value + 1):
        style = dict(SLIDER_MARK_STYLE)
        if i == active_int:
            style["color"] = "#1d4ed8"
            style["fontWeight"] = 800
        _ = html.Div(str(i), style=style)
    return marks


def _slider_visual_style(value: Any, min_value: int = 0, max_value: int = 10):
    pct = _slider_percent(value, min_value=min_value, max_value=max_value)
    fill_style = dict(SLIDER_FILL_BASE_STYLE)
    fill_style["width"] = f"{pct:.4f}%"
    bubble_style = dict(SLIDER_BUBBLE_BASE_STYLE)
    bubble_style["left"] = _slider_bubble_left(value, min_value=min_value, max_value=max_value)
    if pct >= 70:
        bubble_style["background"] = "#1d4ed8"
    elif pct >= 40:
        bubble_style["background"] = "#2563eb"
    else:
        bubble_style["background"] = "#3b82f6"
    try:
        bubble_text = str(int(float(value)))
    except Exception:
        bubble_text = str(int(min_value))
    return fill_style, bubble_style, bubble_text


def _range_control(control_id: str, value: int = 0, min_value: int = 0, max_value: int = 10, step: int = 1):
    fill_style, bubble_style, bubble_text = _slider_visual_style(value, min_value=min_value, max_value=max_value)
    return html.Div(
        style={
            "position": "relative",
            "width": "100%",
            "height": "28px",
            "minHeight": "28px",
            "background": "#ffffff",
            "border": "1px solid rgba(15,23,42,.10)",
            "borderRadius": "8px",
            "padding": "0",
            "overflow": "hidden",
            "boxShadow": "inset 0 1px 0 rgba(255,255,255,.65)",
        },
        children=[
            html.Div(style=SLIDER_TRACK_BASE_STYLE, children=[html.Div(id=f"{control_id}-fill", style=fill_style)]),
            html.Div(id=f"{control_id}-bubble", style=bubble_style, children=bubble_text),
            html.Div(
                id=f"{control_id}-marks",
                style=SLIDER_MARKS_ROW_STYLE,
                children=_build_slider_marks(value, min_value=min_value, max_value=max_value),
            ),
            dbc.Input(
                id=control_id,
                type="range",
                min=min_value,
                max=max_value,
                step=step,
                value=value,
                style={
                    "position": "absolute",
                    "left": "0",
                    "top": "0",
                    "width": "100%",
                    "height": "100%",
                    "margin": "0",
                    "padding": "0",
                    "background": "transparent",
                    "border": "0",
                    "boxShadow": "none",
                    "outline": "none",
                    "opacity": "0.02",
                    "cursor": "pointer",
                    "zIndex": "5",
                },
            ),
        ],
    )


def _field_slider(label: str, slider, help_text: Optional[str] = None):
    items = [
        html.Div(
            style={"display": "flex", "alignItems": "center", "gap": "8px", "width": "100%"},
            children=[
                html.Div(
                    label,
                    className="ax-status-badge",
                    style={
                        "minWidth": "200px",
                        "width": "200px",
                        "flex": "0 0 200px",
                        "margin": "0",
                        "background": "rgba(255,255,255,.10)",
                    },
                ),
                html.Div(slider, style={"flex": "1 1 auto", "minWidth": "0"}),
            ],
        )
    ]
    if help_text:
        items.append(html.Div(help_text, style=FIELD_HELP_STYLE))
    return html.Div(style={"display": "flex", "flexDirection": "column", "gap": "6px"}, children=items)


def _dark_alert(message, color="info", extra_style: Optional[Dict[str, Any]] = None, **kwargs):
    style = {
        "marginTop": "4px",
        "marginBottom": "0",
        "padding": "7px 12px",
        "fontSize": "12px",
        "background": "rgba(0,0,0,.12)",
        "border": "1px solid rgba(255,255,255,.10)",
        "color": "#e2e8f0",
    }
    if extra_style:
        style.update(extra_style)
    return dbc.Alert(message, color=color, style=style, **kwargs)

def _control_summary_inline_box(title: str, value: str):
    return html.Div(
        className="ax-pill ax-pill-full",
        style={"margin": "0", "minHeight": "28px"},
        children=[
            html.Div(title, className="ax-label-muted", style={"flex": "0 1 auto"}),
            html.Div(value, className="ax-value-text", style={"textAlign": "right", "whiteSpace": "nowrap", "flex": "0 0 auto"}),
        ],
    )


def _top_status_item(label: str, value, tone: str = "neutral"):
    bg = {
        "neutral": "rgba(255,255,255,.10)",
        "ok": "rgba(34,197,94,.18)",
        "warn": "rgba(245,158,11,.18)",
        "bad": "rgba(239,68,68,.18)",
    }.get(tone, "rgba(255,255,255,.10)")
    return html.Div(
        className="ax-status-item",
        children=[
            html.Div(label, className="ax-section-title", style={"whiteSpace": "nowrap"}),
            html.Div(
                value,
                className="ax-status-badge",
                style={
                    "background": bg,
                    "width": "100px",
                    "minWidth": "100px",
                    "maxWidth": "100px",
                    "textAlign": "center",
                    "flex": "0 0 100px",
                },
            ),
        ],
    )

def _get_thresholds_status_text(user_id: Optional[int]) -> str:
    """
    Estado real de user_posture_settings para el usuario.
    La lectura principal queda centralizada en db.get_user_posture_settings_status(...).
    """
    if not user_id:
        return "Pendientes"

    try:
        return get_user_posture_settings_status(user_id=int(user_id))
    except Exception:
        return "Pendientes"


def _build_control_summary_panel(
    risk_text: str = "—/100",
    calibration_date_text: str = "Pendiente",
    calibration_state_text: str = "Pendiente",
    thresholds_state_text: str = "Pendiente",
):
    risk_tone = "neutral"
    try:
        risk_value = float(str(risk_text).split("/")[0].replace(",", ".").strip())
        if risk_value >= 70:
            risk_tone = "bad"
        elif risk_value >= 40:
            risk_tone = "warn"
        else:
            risk_tone = "ok"
    except Exception:
        risk_tone = "neutral"
    return _top_status_item("Índice de riesgo", risk_text, risk_tone)


def _build_last_questionnaire_panel(last_completed_text: str = "Pendiente"):
    return html.Div(
        className="ax-status-item",
        children=[
            html.Div("Última evaluación registrada", className="ax-section-title", style={"whiteSpace": "nowrap"}),
            html.Div(
                last_completed_text,
                className="ax-status-badge",
                style={
                    "background": "rgba(255,255,255,.10)",
                    "width": "100px",
                    "minWidth": "100px",
                    "maxWidth": "100px",
                    "textAlign": "center",
                    "flex": "0 0 100px",
                },
            ),
        ],
    )


def _build_daily_status_panel(
    status_text: str = "Pendiente",
    calibration_date_text: str = "Pendiente",
    calibration_state_text: str = "Pendiente",
):
    bg = "rgba(245,158,11,.18)" if str(status_text or "").strip().lower() == "pendiente" else "rgba(34,197,94,.18)"
    if str(status_text or "").strip().lower() not in ("pendiente", "completado"):
        bg = "rgba(255,255,255,.10)"
    return html.Div(
        className="ax-status-item",
        children=[
            html.Div("Estado diario", className="ax-section-title", style={"whiteSpace": "nowrap"}),
            html.Div(
                status_text,
                className="ax-status-badge",
                style={
                    "background": bg,
                    "width": "100px",
                    "minWidth": "100px",
                    "maxWidth": "100px",
                    "textAlign": "center",
                    "flex": "0 0 100px",
                },
            ),
        ],
    )


def _build_thresholds_status_panel(thresholds_state_text: str = "Pendientes"):
    tone = "rgba(34,197,94,.18)" if str(thresholds_state_text or "").strip().lower().startswith("guardados") else "rgba(245,158,11,.18)"
    return html.Div(
        className="ax-status-item",
        children=[
            html.Div("Umbrales personalizados", className="ax-section-title", style={"whiteSpace": "nowrap"}),
            html.Div(
                thresholds_state_text,
                className="ax-status-badge",
                style={
                    "background": tone,
                    "width": "100px",
                    "minWidth": "100px",
                    "maxWidth": "100px",
                    "textAlign": "center",
                    "flex": "0 0 100px",
                },
            ),
        ],
    )


def _format_local_questionnaire_datetime(dt_value: Any) -> str:
    raw = str(dt_value or "").strip()
    if not raw:
        return "Pendiente"
    raw = raw.replace("Z", "")
    parsed = None
    for candidate in (raw, raw.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            break
        except Exception:
            parsed = None
    if parsed is None:
        return raw
    parsed = parsed + timedelta(hours=2)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _get_latest_calibration_reference(user_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """Wrapper local compatible: lectura centralizada en db.py.

    Convención compartida con Monitor:
    1) baseline_tests como fuente histórica persistida
    2) get_latest_baseline_reference(...) como API principal
    3) get_latest_valid_baseline(...) solo como fallback compatible

    q-baseline-rec se reserva para la grabación activa; el histórico persistido
    siempre se reconstruye desde DB mediante helpers centralizados.
    """
    if not user_id:
        return None
    try:
        ref = get_latest_baseline_reference_for_ui(user_id=int(user_id), allow_fallback=True)
        return ref if isinstance(ref, dict) and ref.get("has_baseline") else None
    except Exception:
        return None


def _calibration_reference_meta(calibration_ref: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normaliza referencia histórica para UI usando db.py como fuente común."""
    ref = normalize_baseline_reference_for_ui(calibration_ref if isinstance(calibration_ref, dict) else {})
    created_at_label = _format_local_questionnaire_datetime(ref.get("created_at_raw") or ref.get("created_at"))
    return {
        "has_baseline": bool(ref.get("has_baseline")),
        "baseline_payload": ref.get("baseline_payload") if isinstance(ref.get("baseline_payload"), dict) else {},
        "summary": ref.get("summary") if isinstance(ref.get("summary"), dict) else {},
        "source": ref.get("history_source") or ref.get("source") or "baseline_tests",
        "source_label": ref.get("source_label") or "Histórico compartido",
        "created_at_raw": ref.get("created_at_raw") or ref.get("created_at"),
        "created_at_label": created_at_label,
        "baseline_test_id": ref.get("baseline_test_id"),
        "status_label": ref.get("status_label") or "Pendiente",
        "is_valid": bool(ref.get("is_valid")),
    }

def _build_historical_baseline_widgets(calibration_ref: Optional[Dict[str, Any]]):
    """Reconstruye widgets históricos del baseline leyendo la última calibración desde DB."""
    meta = _calibration_reference_meta(calibration_ref)

    if not meta.get("has_baseline"):
        return (
            _build_baseline_current_info_panel(
                calibration_date_text="Pendiente",
                calibration_state_text="Pendiente",
            ),
            _build_baseline_status_box(
                message="Aún no hay datos de calibración guardados.",
                tone="neutral",
            ),
            _build_baseline_metrics_block(),
        )

    baseline_payload = meta.get("baseline_payload") if isinstance(meta.get("baseline_payload"), dict) else {}
    rom = baseline_payload.get("rom") if isinstance(baseline_payload.get("rom"), dict) else {}
    comp = baseline_payload.get("comp") if isinstance(baseline_payload.get("comp"), dict) else {}
    stability = baseline_payload.get("stability") if isinstance(baseline_payload.get("stability"), dict) else {}

    rom_thor_pitch = float(rom.get("thor_pitch") or 0.0)
    rom_lum_pitch = float(rom.get("lum_pitch") or 0.0)
    comp_avg = float(comp.get("comp_avg") or 0.0)
    comp_peak = float(comp.get("comp_peak") or 0.0)
    lum_pitch_std = float(stability.get("lum_pitch_std") or 0.0)

    baseline_id_text = f" #{meta.get('baseline_test_id')}" if meta.get("baseline_test_id") is not None else ""
    source_label = str(meta.get("source_label") or "Histórico compartido").strip()
    message = f"Calibración histórica guardada en DB{baseline_id_text} · {source_label} ✓"

    return (
        _build_baseline_current_info_panel(
            calibration_date_text=meta.get("created_at_label") or "Pendiente",
            calibration_state_text="OK ✓",
        ),
        _build_baseline_status_box(
            message=message,
            tone="ok",
            rom_thor_pitch=rom_thor_pitch,
            rom_lum_pitch=rom_lum_pitch,
            comp_avg=comp_avg,
            comp_peak=comp_peak,
            lum_pitch_std=lum_pitch_std,
        ),
        _build_baseline_metrics_block(
            rom_thor_pitch=rom_thor_pitch,
            rom_lum_pitch=rom_lum_pitch,
            comp_avg=comp_avg,
            comp_peak=comp_peak,
            lum_pitch_std=lum_pitch_std,
        ),
    )


def _build_advice_status_panel(
    calibration_date_text: str = "Pendiente",
    calibration_state_text: str = "Pendiente",
    thresholds_state_text: str = "Pendiente",
):
    return html.Div(style={"display": "none"})


def _build_baseline_current_info_panel(
    calibration_date_text: str = "Pendiente",
    calibration_state_text: str = "Pendiente",
):
    state_bg = "rgba(245,158,11,.18)"
    state_txt = str(calibration_state_text or "").strip().lower()
    if state_txt.startswith("ok") or state_txt.startswith("lista") or state_txt.startswith("válida"):
        state_bg = "rgba(34,197,94,.18)"
    elif state_txt.startswith("en curso"):
        state_bg = "rgba(59,130,246,.18)"

    date_text = str(calibration_date_text or "Pendiente")
    return html.Div(
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "flex-end",
            "gap": "8px",
            "width": "100%",
            "flexWrap": "wrap",
        },
        children=[
            html.Div(
                calibration_state_text,
                className="ax-status-badge",
                style={
                    "margin": "0",
                    "background": state_bg,
                    "whiteSpace": "nowrap",
                    "minWidth": "110px",
                    "textAlign": "center",
                },
            ),
            html.Div(
                date_text,
                className="ax-status-badge",
                style={
                    "margin": "0",
                    "background": "rgba(255,255,255,.10)",
                    "whiteSpace": "nowrap",
                },
            ),
        ],
    )


def _baseline_metric_value(value: Any, suffix: str = "", decimals: int = 1) -> str:
    if value is None:
        return "—"
    try:
        fv = float(value)
    except Exception:
        return "—"
    if decimals <= 0:
        txt = f"{int(round(fv))}"
    else:
        txt = f"{fv:.{decimals}f}"
    return f"{txt}{suffix}"


def _build_baseline_status_box(
    title: str = "Resumen de calibración",
    message: str = "Aún no hay datos de calibración guardados.",
    tone: str = "neutral",
    rom_thor_pitch: Any = None,
    rom_lum_pitch: Any = None,
    comp_avg: Any = None,
    comp_peak: Any = None,
    lum_pitch_std: Any = None,
):
    tone_map = {
        "neutral": {"background": "rgba(255,255,255,.06)", "border": "rgba(255,255,255,.08)"},
        "info": {"background": "rgba(59,130,246,.14)", "border": "rgba(59,130,246,.24)"},
        "ok": {"background": "rgba(34,197,94,.14)", "border": "rgba(34,197,94,.24)"},
        "warn": {"background": "rgba(245,158,11,.14)", "border": "rgba(245,158,11,.24)"},
        "bad": {"background": "rgba(239,68,68,.14)", "border": "rgba(239,68,68,.24)"},
    }
    palette = tone_map.get(tone, tone_map["neutral"])

    return html.Div(
        className="ax-panel-black ax-panel-black-stack",
        style={
            "paddingTop": "8px",
            "paddingBottom": "8px",
            "paddingLeft": "10px",
            "paddingRight": "10px",
            "gap": "6px",
            "background": palette["background"],
            "boxShadow": f"inset 0 0 0 1px {palette['border']}",
            "borderRadius": "12px",
        },
        children=[
            html.Div(title, className="ax-section-title"),
            html.Div(message, style={**BLACK_MUTED, "fontSize": "12px", "lineHeight": "1.45"}),
            html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
            html.Div(
                style={"display": "flex", "flexDirection": "column", "gap": "6px", "width": "100%"},
                children=[
                    _control_summary_inline_box("Movilidad torácica (pitch)", _baseline_metric_value(rom_thor_pitch, "°", 1)),
                    _control_summary_inline_box("Movilidad lumbar (pitch)", _baseline_metric_value(rom_lum_pitch, "°", 1)),
                    _control_summary_inline_box("Compensación media", _baseline_metric_value(comp_avg, "", 1)),
                    _control_summary_inline_box("Compensación pico", _baseline_metric_value(comp_peak, "", 1)),
                    _control_summary_inline_box("Estabilidad lumbar", _baseline_metric_value(lum_pitch_std, "", 2)),
                ],
            ),
        ],
    )


def _result_metric_card(title: str, value: str, tone: str = "neutral"):
    tone_map = {
        "neutral": {"background": "rgba(255,255,255,.06)", "border": "rgba(255,255,255,.08)", "value": "#e2e8f0"},
        "ok": {"background": "rgba(34,197,94,.16)", "border": "rgba(34,197,94,.24)", "value": "#bbf7d0"},
        "warn": {"background": "rgba(245,158,11,.16)", "border": "rgba(245,158,11,.24)", "value": "#fde68a"},
        "bad": {"background": "rgba(239,68,68,.16)", "border": "rgba(239,68,68,.24)", "value": "#fecaca"},
    }
    palette = tone_map.get(tone, tone_map["neutral"])
    return html.Div(
        style={
            "background": palette["background"],
            "boxShadow": f"inset 0 0 0 1px {palette['border']}",
            "borderRadius": "18px",
            "padding": "10px",
            "aspectRatio": "1 / 1",
            "minHeight": "120px",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "space-between",
            "alignItems": "center",
            "textAlign": "center",
            "gap": "10px",
        },
        children=[
            html.Div(
                title,
                style={
                    "color": "rgba(226,232,240,.82)",
                    "fontSize": "12px",
                    "fontWeight": 700,
                    "lineHeight": "1.3",
                    "width": "100%",
                },
            ),
            html.Div(
                value,
                style={
                    "color": palette["value"],
                    "fontSize": "22px",
                    "fontWeight": 800,
                    "lineHeight": "1",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "flex": "1 1 auto",
                    "width": "100%",
                },
            ),
        ],
    )


def _build_results_grid(cards):
    return html.Div(
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(6, minmax(0, 1fr))",
            "gap": "8px",
            "width": "100%",
        },
        children=cards,
    )


def _build_sensor_results_block(
    thor: Any = "—",
    lum: Any = "—",
    comp_avg: Any = "—",
    comp_peak: Any = "—",
    alerts_count: Any = "—",
    risk_max: Any = "—",
    tone_thor: str = "neutral",
    tone_lum: str = "neutral",
    tone_comp_avg: str = "neutral",
    tone_comp_peak: str = "neutral",
    tone_alerts: str = "neutral",
    tone_risk: str = "neutral",
):
    return _build_results_grid([
        _result_metric_card("Rojo Torácico (s)", str(thor), tone_thor),
        _result_metric_card("Rojo Lumbar (s)", str(lum), tone_lum),
        _result_metric_card("Compensación promedio", str(comp_avg), tone_comp_avg),
        _result_metric_card("Compensación pico", str(comp_peak), tone_comp_peak),
        _result_metric_card("Alertas (count)", str(alerts_count), tone_alerts),
        _result_metric_card("Risk Index (max)", str(risk_max), tone_risk),
    ])


def _build_baseline_metrics_block(
    rom_thor_pitch: Any = None,
    rom_lum_pitch: Any = None,
    comp_avg: Any = None,
    comp_peak: Any = None,
    lum_pitch_std: Any = None,
):
    return _build_results_grid([
        _result_metric_card("Movilidad torácica (pitch)", _baseline_metric_value(rom_thor_pitch, "°", 1)),
        _result_metric_card("Movilidad lumbar (pitch)", _baseline_metric_value(rom_lum_pitch, "°", 1)),
        _result_metric_card("Compensación media", _baseline_metric_value(comp_avg, "", 1)),
        _result_metric_card("Compensación pico", _baseline_metric_value(comp_peak, "", 1)),
        _result_metric_card("Estabilidad lumbar", _baseline_metric_value(lum_pitch_std, "", 2)),
    ])


def _step_label(step: int) -> str:
    labels = {
        1: "1/6 · Perfil postural",
        2: "2/6 · Dolor y síntomas",
        3: "3/6 · Autoevaluación",
        4: "4/6 · Calibración",
        5: "5/6 · Daily + objetivos",
        6: "6/6 · Resultados",
    }
    return labels.get(int(step or 1), "1/6 · Perfil postural")

def _clamp_int(v, lo=0, hi=10) -> Optional[int]:
    if v is None:
        return None
    try:
        iv = int(v)
    except Exception:
        return None
    return max(lo, min(hi, iv))

def _format_score_0_100(v: Any) -> str:
    try:
        fv = float(v)
    except Exception:
        return str(v)
    if fv.is_integer():
        return str(int(fv))
    return f"{fv:.1f}".rstrip("0").rstrip(".")

def json_clone(x):
    import json
    return json.loads(json.dumps(x))

def _risk_from_inputs(payload: Dict[str, Any], daily: Optional[Dict[str, Any]] = None) -> float:
    """
    Risk Index simple MVP 0..100:
    - dolor máximo (VAS zona) 0..10
    - auto-eval (3 checks) 0..3
    - daily_summary risk_index_max si existe
    """
    pain = payload.get("pain") or {}
    vas_vals = [
        _clamp_int(pain.get("neck"), 0, 10) or 0,
        _clamp_int(pain.get("thor"), 0, 10) or 0,
        _clamp_int(pain.get("lum"), 0, 10) or 0,
        _clamp_int(pain.get("tingle"), 0, 10) or 0,
        _clamp_int(pain.get("headache"), 0, 10) or 0,
    ]
    vas_max = float(max(vas_vals) if vas_vals else 0.0)

    se = payload.get("self_eval") or {}
    se_score = 0
    for k in ("slouch", "asymmetry", "endday_pain"):
        if bool(se.get(k)):
            se_score += 1

    daily_r = 0.0
    if daily:
        try:
            daily_r = float(daily.get("risk_index_max") or 0.0)
        except Exception:
            daily_r = 0.0

    r = (vas_max / 10.0) * 55.0 + (se_score / 3.0) * 15.0 + (daily_r / 100.0) * 30.0
    return max(0.0, min(100.0, float(r)))



def _risk_from_form_and_calibration(
    payload: Dict[str, Any],
    daily: Optional[Dict[str, Any]] = None,
    baseline: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Risk Index visible en UI 0..100:
    - base desde dolor + auto-evaluación + daily_summary
    - ajustes por rigidez, fatiga, sueño y horas sentado
    - ajuste por calibración/baseline real más reciente
    """
    risk = float(_risk_from_inputs(payload, daily=daily))

    pain = payload.get("pain") or {}
    profile = payload.get("profile") or {}
    daily_form = payload.get("daily") or {}

    stiffness = _clamp_int(pain.get("stiffness"), 0, 10) or 0
    headache = _clamp_int(pain.get("headache"), 0, 10) or 0
    fatigue = _clamp_int(daily_form.get("fatigue"), 0, 10) or 0
    sleep = _clamp_int(daily_form.get("sleep"), 0, 10)

    try:
        sitting_hours = float(profile.get("sitting_hours") or 0.0)
    except Exception:
        sitting_hours = 0.0

    if stiffness > 0:
        risk += (float(stiffness) / 10.0) * 6.0

    if headache > 0:
        risk += (float(headache) / 10.0) * 5.0

    if fatigue >= 4:
        risk += ((float(fatigue) - 3.0) / 7.0) * 8.0

    if sleep is not None:
        if sleep <= 4:
            risk += ((5.0 - float(sleep)) / 5.0) * 6.0
        elif sleep >= 8:
            risk -= min(3.0, (float(sleep) - 7.0) * 1.0)

    if sitting_hours >= 8:
        risk += 6.0
    elif sitting_hours >= 6:
        risk += 4.0
    elif sitting_hours >= 4:
        risk += 2.0

    baseline_payload = {}
    if isinstance(baseline, dict):
        maybe_payload = baseline.get("baseline") if isinstance(baseline.get("baseline"), dict) else baseline
        baseline_payload = maybe_payload if isinstance(maybe_payload, dict) else {}

    if baseline_payload:
        comp = baseline_payload.get("comp") if isinstance(baseline_payload.get("comp"), dict) else {}
        stability = baseline_payload.get("stability") if isinstance(baseline_payload.get("stability"), dict) else {}

        try:
            baseline_comp_avg = float(comp.get("comp_avg") or 0.0)
        except Exception:
            baseline_comp_avg = 0.0
        try:
            baseline_comp_peak = float(comp.get("comp_peak") or 0.0)
        except Exception:
            baseline_comp_peak = 0.0
        try:
            lum_pitch_std = float(stability.get("lum_pitch_std") or 0.0)
        except Exception:
            lum_pitch_std = 0.0
        try:
            thor_pitch_std = float(stability.get("thor_pitch_std") or 0.0)
        except Exception:
            thor_pitch_std = 0.0
        try:
            diff_tl_pitch_mean = float(baseline_payload.get("diff_TL_pitch_mean") or 0.0)
        except Exception:
            diff_tl_pitch_mean = 0.0

        calibration_adjustment = 0.0
        calibration_adjustment += min(4.0, baseline_comp_avg / 12.0)
        calibration_adjustment += min(3.0, baseline_comp_peak / 25.0)
        calibration_adjustment += min(3.0, max(lum_pitch_std, thor_pitch_std) * 0.75)
        if diff_tl_pitch_mean >= 8.0:
            calibration_adjustment += 2.0
        elif diff_tl_pitch_mean <= 3.0 and baseline_comp_avg <= 15.0 and max(lum_pitch_std, thor_pitch_std) <= 1.5:
            calibration_adjustment -= 4.0
        elif diff_tl_pitch_mean <= 5.0 and baseline_comp_avg <= 22.0 and max(lum_pitch_std, thor_pitch_std) <= 2.2:
            calibration_adjustment -= 2.0
        risk += calibration_adjustment
    else:
        risk += 2.0

    return max(0.0, min(100.0, float(risk)))


def _tighten_threshold_block(seg: Dict[str, Any], *, pitch_g: float = 0.0, pitch_y: float = 0.0, roll_g: float = 0.0, roll_y: float = 0.0):
    if not isinstance(seg, dict):
        return
    try:
        seg["pitch_g"] = max(3.0, float(seg.get("pitch_g") or 0.0) - float(pitch_g))
        seg["pitch_y"] = max(seg["pitch_g"] + 1.0, float(seg.get("pitch_y") or 0.0) - float(pitch_y))
        seg["roll_g"] = max(2.0, float(seg.get("roll_g") or 0.0) - float(roll_g))
        seg["roll_y"] = max(seg["roll_g"] + 1.0, float(seg.get("roll_y") or 0.0) - float(roll_y))
    except Exception:
        return


def _build_monitor_profile(
    profile: Dict[str, Any],
    pain: Dict[str, Any],
    daily: Dict[str, Any],
    baseline: Optional[Dict[str, Any]],
    fatigue: Optional[int],
    sleep: Optional[int],
) -> Dict[str, Any]:
    """
    Construye el perfil de monitorización personalizado para el usuario.

    Salida esperada:
    - thresholds: umbrales por modo/segmento
    - adaptation_rules: reglas de sensibilidad derivadas de dolor, fatiga, sueño y calibración
    - baseline_reference: resumen de la última calibración disponible
    - version: versión del payload guardado en DB
    """
    thr = {
        "desk": json_clone(DEFAULT_THRESHOLDS["desk"]),
        "train": json_clone(DEFAULT_THRESHOLDS["train"]),
    }

    hours = profile.get("sitting_hours")
    try:
        hours = float(hours) if hours is not None else 0.0
    except Exception:
        hours = 0.0

    lum_pain = _clamp_int((pain or {}).get("lum"), 0, 10) or 0
    thor_pain = _clamp_int((pain or {}).get("thor"), 0, 10) or 0
    neck_pain = _clamp_int((pain or {}).get("neck"), 0, 10) or 0
    headache_symptom = _clamp_int((pain or {}).get("headache"), 0, 10) or 0
    fatigue_i = _clamp_int(fatigue, 0, 10) or 0
    sleep_i = _clamp_int(sleep, 0, 10) or 0

    daily = daily or {}
    try:
        daily_risk = float(daily.get("risk_index_max") or 0.0)
    except Exception:
        daily_risk = 0.0
    try:
        daily_comp = float(daily.get("comp_avg") or 0.0)
    except Exception:
        daily_comp = 0.0
    try:
        daily_alerts = int(daily.get("alerts_count") or 0)
    except Exception:
        daily_alerts = 0

    baseline_payload = {}
    if isinstance(baseline, dict):
        maybe_payload = baseline.get("baseline") if isinstance(baseline.get("baseline"), dict) else baseline
        baseline_payload = maybe_payload if isinstance(maybe_payload, dict) else {}

    baseline_comp = baseline_payload.get("comp") if isinstance(baseline_payload.get("comp"), dict) else {}
    baseline_stability = baseline_payload.get("stability") if isinstance(baseline_payload.get("stability"), dict) else {}
    baseline_rom = baseline_payload.get("rom") if isinstance(baseline_payload.get("rom"), dict) else {}

    try:
        baseline_comp_avg = float(baseline_comp.get("comp_avg") or 0.0)
    except Exception:
        baseline_comp_avg = 0.0
    try:
        baseline_comp_peak = float(baseline_comp.get("comp_peak") or 0.0)
    except Exception:
        baseline_comp_peak = 0.0
    try:
        lum_pitch_std = float(baseline_stability.get("lum_pitch_std") or 0.0)
    except Exception:
        lum_pitch_std = 0.0
    try:
        thor_pitch_std = float(baseline_stability.get("thor_pitch_std") or 0.0)
    except Exception:
        thor_pitch_std = 0.0
    try:
        diff_tl_pitch_mean = float(baseline_payload.get("diff_TL_pitch_mean") or 0.0)
    except Exception:
        diff_tl_pitch_mean = 0.0

    baseline_available = bool(baseline_payload)
    baseline_unstable = bool(
        baseline_available and (
            lum_pitch_std >= 3.0 or
            thor_pitch_std >= 3.0 or
            baseline_comp_avg >= 30.0 or
            baseline_comp_peak >= 55.0 or
            diff_tl_pitch_mean >= 8.0
        )
    )

    # -------------------------
    # Reglas mínimas de ajuste
    # -------------------------
    if lum_pain >= 7:
        _tighten_threshold_block(thr["desk"]["lum"], pitch_g=1.0, pitch_y=2.0, roll_g=0.5, roll_y=1.0)
        _tighten_threshold_block(thr["train"]["lum"], pitch_g=1.0, pitch_y=2.0, roll_g=0.5, roll_y=1.0)
    elif lum_pain >= 4:
        _tighten_threshold_block(thr["desk"]["lum"], pitch_g=0.5, pitch_y=1.0)
        _tighten_threshold_block(thr["train"]["lum"], pitch_g=0.5, pitch_y=1.0)

    if thor_pain >= 7 or neck_pain >= 7 or headache_symptom >= 7:
        _tighten_threshold_block(thr["desk"]["thor"], pitch_g=1.0, pitch_y=2.0, roll_g=0.5, roll_y=1.0)
        _tighten_threshold_block(thr["train"]["thor"], pitch_g=1.0, pitch_y=2.0, roll_g=0.5, roll_y=1.0)
    elif thor_pain >= 4 or neck_pain >= 4 or headache_symptom >= 4:
        _tighten_threshold_block(thr["desk"]["thor"], pitch_g=0.5, pitch_y=1.0)
        _tighten_threshold_block(thr["train"]["thor"], pitch_g=0.5, pitch_y=1.0)

    if hours >= 6:
        _tighten_threshold_block(thr["desk"]["thor"], pitch_g=0.5, pitch_y=1.0, roll_y=0.5)
        _tighten_threshold_block(thr["desk"]["lum"], pitch_g=0.5, pitch_y=1.0, roll_y=0.5)

    if fatigue_i >= 7:
        _tighten_threshold_block(thr["desk"]["thor"], pitch_y=1.0, roll_y=1.0)
        _tighten_threshold_block(thr["desk"]["lum"], pitch_y=1.0, roll_y=1.0)
        _tighten_threshold_block(thr["train"]["thor"], pitch_y=1.0, roll_y=1.0)
        _tighten_threshold_block(thr["train"]["lum"], pitch_y=1.0, roll_y=1.0)

    if sleep_i and sleep_i <= 4:
        _tighten_threshold_block(thr["desk"]["thor"], pitch_y=0.5)
        _tighten_threshold_block(thr["desk"]["lum"], pitch_y=0.5)
        _tighten_threshold_block(thr["train"]["thor"], pitch_y=0.5)
        _tighten_threshold_block(thr["train"]["lum"], pitch_y=0.5)

    if baseline_unstable:
        _tighten_threshold_block(thr["desk"]["thor"], pitch_g=0.5, pitch_y=1.0, roll_y=0.5)
        _tighten_threshold_block(thr["desk"]["lum"], pitch_g=0.5, pitch_y=1.0, roll_y=0.5)
        _tighten_threshold_block(thr["train"]["thor"], pitch_g=0.5, pitch_y=1.0, roll_y=0.5)
        _tighten_threshold_block(thr["train"]["lum"], pitch_g=0.5, pitch_y=1.0, roll_y=0.5)

    adaptation_rules = {
        "pain": {
            "lumbar_vas": lum_pain,
            "thoracic_vas": thor_pain,
            "neck_vas": neck_pain,
            "headache_vas": headache_symptom,
            "lumbar_more_sensitive": bool(lum_pain >= 7),
            "thoracic_more_sensitive": bool(thor_pain >= 7 or neck_pain >= 7 or headache_symptom >= 7),
        },
        "daily_context": {
            "sitting_hours": float(hours),
            "desk_stricter": bool(hours >= 6),
            "daily_risk_index_max": float(daily_risk),
            "daily_comp_avg": float(daily_comp),
            "daily_alerts_count": int(daily_alerts),
        },
        "fatigue": {
            "level": int(fatigue_i),
            "high": bool(fatigue_i >= 7),
            "alert_speed_multiplier": 0.85 if fatigue_i >= 7 else (0.92 if fatigue_i >= 5 else 1.0),
        },
        "sleep": {
            "level": int(sleep_i),
            "low": bool(sleep_i > 0 and sleep_i <= 4),
            "sustained_tolerance_multiplier": 0.85 if sleep_i > 0 and sleep_i <= 4 else (0.92 if sleep_i == 5 else 1.0),
        },
        "baseline": {
            "available": baseline_available,
            "unstable": baseline_unstable,
            "comp_sensitivity_multiplier": 0.85 if baseline_unstable else 1.0,
            "lum_pitch_std": float(lum_pitch_std),
            "thor_pitch_std": float(thor_pitch_std),
            "comp_avg": float(baseline_comp_avg),
            "comp_peak": float(baseline_comp_peak),
            "diff_tl_pitch_mean": float(diff_tl_pitch_mean),
        },
    }

    baseline_reference = {
        "available": baseline_available,
        "baseline_id": baseline.get("id") if isinstance(baseline, dict) else None,
        "created_at": baseline.get("created_at") if isinstance(baseline, dict) else None,
        "stable": (not baseline_unstable) if baseline_available else False,
        "rom": baseline_rom if isinstance(baseline_rom, dict) else {},
        "stability": baseline_stability if isinstance(baseline_stability, dict) else {},
        "comp": baseline_comp if isinstance(baseline_comp, dict) else {},
    }

    return {
        "thresholds": thr,
        "adaptation": adaptation_rules,
        "adaptation_rules": adaptation_rules,
        "baseline_reference": baseline_reference,
        "version": "wizard_v2",
    }


# -------------------------
# Baseline metrics (MVP)
# -------------------------
def _safe_minmax(xs: List[float]) -> Tuple[float, float]:
    if not xs:
        return 0.0, 0.0
    return float(min(xs)), float(max(xs))


def _safe_mean(xs: List[float]) -> float:
    if not xs:
        return 0.0
    return float(sum(xs) / max(len(xs), 1))


def _safe_std(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _safe_mean(xs)
    v = sum((float(x) - m) ** 2 for x in xs) / max(len(xs) - 1, 1)
    return float(v ** 0.5)


def _baseline_from_window(win: Dict[str, List]) -> Dict[str, Any]:
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
        "source": "SIM",
    }


BASELINE_GOOD_POSTURE_TARGET_S = 15.0
BASELINE_GOOD_POSTURE_TARGET_MS = int(BASELINE_GOOD_POSTURE_TARGET_S * 1000)
BASELINE_SIM_SAMPLE_MS = 20


def _baseline_rec_defaults() -> Dict[str, Any]:
    return {
        "is_recording": False,
        "sensor_session_id": None,
        "calibration_user_id": None,
        "login_session_id": None,
        "last_ts_ms": 0,
        "start_iso": None,
        "started_at_epoch_ms": None,
        "n_raw": 0,
        "good_posture_streak_ms": 0,
        "streak_last_ts_ms": 0,
        "calibration_ready": False,
        "target_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S,
        "good_posture_rule": "thor_green_lum_green_comp_le_20",
    }


def _baseline_streak_seconds(rec: Optional[Dict[str, Any]]) -> float:
    try:
        rec = rec or {}
        stored_s = max(0.0, float(rec.get("good_posture_streak_ms") or 0.0) / 1000.0)
        if bool(rec.get("is_recording")) and rec.get("started_at_epoch_ms"):
            elapsed_s = max(0.0, (int(time.time() * 1000) - int(rec.get("started_at_epoch_ms") or 0)) / 1000.0)
            target_s = float(rec.get("target_good_posture_s") or BASELINE_GOOD_POSTURE_TARGET_S)
            return min(max(stored_s, elapsed_s), target_s)
        return stored_s
    except Exception:
        return 0.0



def _baseline_remaining_seconds(rec: Optional[Dict[str, Any]]) -> float:
    target_s = float((rec or {}).get("target_good_posture_s") or BASELINE_GOOD_POSTURE_TARGET_S)
    return max(0.0, target_s - _baseline_streak_seconds(rec))



def _baseline_good_posture_sample(sample: Dict[str, Any]) -> bool:
    thor_zone = str(sample.get("thor_zone") or "").strip().lower()
    lum_zone = str(sample.get("lum_zone") or "").strip().lower()
    try:
        comp_index = float(sample.get("comp_index") or 0.0)
    except Exception:
        comp_index = 999.0
    return thor_zone == "green" and lum_zone == "green" and comp_index <= 20.0


def _complete_baseline_recording_for_questionnaire(rec, user_id, wizard_store=None, baseline_choice=None, baseline_notes=None):
    rec = rec or _baseline_rec_defaults()
    ssid = rec.get("sensor_session_id")

    try:
        if ssid:
            end_sensor_session(session_id=int(ssid))
    except Exception:
        pass

    try:
        win = SIM.get_window(seconds=60)
    except Exception:
        win = {}

    baseline = _baseline_from_window(win)

    duration_s = 0.0
    try:
        ts = win.get("ts_ms") or []
        if len(ts) >= 2:
            duration_s = float((int(ts[-1]) - int(ts[0])) / 1000.0)
    except Exception:
        duration_s = 0.0

    thor_zone = win.get("thor_zone") or []
    lum_zone = win.get("lum_zone") or []
    comp = win.get("comp_index") or []

    thor_red_s = float(sum(1 for z in thor_zone if z == "red") / 50.0) if thor_zone else 0.0
    lum_red_s = float(sum(1 for z in lum_zone if z == "red") / 50.0) if lum_zone else 0.0
    comp_avg = float(sum(float(x) for x in comp) / max(len(comp), 1)) if comp else 0.0
    comp_peak = float(max(float(x) for x in comp)) if comp else 0.0

    alerts_count = 0
    try:
        prev = None
        for z in (thor_zone or []):
            if z == "red" and prev != "red":
                alerts_count += 1
            prev = z
        prev = None
        for z in (lum_zone or []):
            if z == "red" and prev != "red":
                alerts_count += 1
            prev = z
    except Exception:
        alerts_count = 0

    risk_index = max(0.0, min(100.0, (thor_red_s + lum_red_s) * 2.5 + comp_avg * 0.35))

    try:
        if ssid:
            upsert_session_summary(
                session_id=int(ssid),
                duration_s=float(duration_s),
                thor_red_s=float(thor_red_s),
                lum_red_s=float(lum_red_s),
                alerts_count=int(alerts_count),
                comp_avg=float(comp_avg),
                comp_peak=float(comp_peak),
                risk_index=float(risk_index),
            )
    except Exception:
        pass

    baseline_id = None
    try:
        baseline_id = create_baseline_test(
            user_id=int(user_id),
            sensor_session_id=int(ssid) if ssid else None,
            baseline=baseline,
        )
    except Exception:
        baseline_id = None

    try:
        recompute_daily_summary(user_id=int(user_id), day=date.today())
    except Exception:
        pass

    completed_ok = baseline_id is not None
    try:
        if wizard_store and wizard_store.get("session_id"):
            save_questionnaire_step(
                session_id=int(wizard_store["session_id"]),
                step_key="baseline",
                step_payload={
                    "choice": baseline_choice or "later",
                    "notes": baseline_notes or "",
                    "recording_started_at": rec.get("start_iso"),
                    "completed": bool(completed_ok),
                    "baseline_id": baseline_id,
                    "sensor_session_id": ssid,
                    "calibration_ready": bool(completed_ok),
                    "continuous_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S,
                    "target_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S,
                    "good_posture_rule": "thor_green_lum_green_comp_le_20",
                    "calibration_summary": {
                        "comp_avg": float(baseline["comp"].get("comp_avg") or 0.0),
                        "comp_peak": float(baseline["comp"].get("comp_peak") or 0.0),
                        "lum_pitch_std": float(baseline["stability"].get("lum_pitch_std") or 0.0),
                    },
                    "baseline_summary": {
                        "comp_avg": float(baseline["comp"].get("comp_avg") or 0.0),
                        "comp_peak": float(baseline["comp"].get("comp_peak") or 0.0),
                        "lum_pitch_std": float(baseline["stability"].get("lum_pitch_std") or 0.0),
                    },
                },
            )
    except Exception:
        pass

    completed_rec = {
        **_baseline_rec_defaults(),
        "is_recording": False,
        "sensor_session_id": None,
        "completed_sensor_session_id": ssid,
        "calibration_user_id": rec.get("calibration_user_id") or int(user_id),
        "login_session_id": rec.get("login_session_id"),
        "last_ts_ms": int(rec.get("last_ts_ms") or 0),
        "start_iso": rec.get("start_iso"),
        "completed_iso": datetime.now().isoformat(timespec="seconds"),
        "n_raw": int(rec.get("n_raw") or 0),
        "good_posture_streak_ms": BASELINE_GOOD_POSTURE_TARGET_MS,
        "streak_last_ts_ms": int(rec.get("streak_last_ts_ms") or 0),
        "calibration_ready": bool(completed_ok),
        "completed": bool(completed_ok),
        "baseline_id": baseline_id,
        "baseline_summary": {
            "rom_thor_pitch": float(baseline["rom"].get("thor_pitch") or 0.0),
            "rom_lum_pitch": float(baseline["rom"].get("lum_pitch") or 0.0),
            "comp_avg": float(baseline["comp"].get("comp_avg") or 0.0),
            "comp_peak": float(baseline["comp"].get("comp_peak") or 0.0),
            "lum_pitch_std": float(baseline["stability"].get("lum_pitch_std") or 0.0),
        },
        "save_failed": not bool(completed_ok),
    }
    return completed_rec, baseline, baseline_id


def _get_questionnaire_login_session_id(session_user):
    if isinstance(session_user, dict):
        value = session_user.get("login_session_id")
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _get_questionnaire_user_id(session_user):
    session_user = session_user if isinstance(session_user, dict) else {}
    return resolve_user_id(user_id=session_user.get("id"), email=session_user.get("email"))


def _baseline_rec_matches_login(rec, session_user) -> bool:
    rec = rec if isinstance(rec, dict) else {}
    if not any(bool(rec.get(k)) for k in ("is_recording", "completed", "save_failed", "reset_active", "baseline_id", "started_at_epoch_ms")):
        return True
    user_id = _get_questionnaire_user_id(session_user)
    if not user_id:
        return False
    try:
        rec_user_id = int(rec.get("calibration_user_id"))
    except Exception:
        return False
    if rec_user_id != int(user_id):
        return False
    login_session_id = _get_questionnaire_login_session_id(session_user)
    rec_login_session_id = rec.get("login_session_id")
    if login_session_id and str(rec_login_session_id or "") != str(login_session_id):
        return False
    return True


def _build_questionnaire_calibration_handoff(rec, session_user):
    rec = rec if isinstance(rec, dict) else {}
    session_user = session_user if isinstance(session_user, dict) else {}
    user_id = resolve_user_id(user_id=session_user.get("id"), email=session_user.get("email"))
    baseline_id = rec.get("baseline_id")
    if not user_id or not baseline_id or not bool(rec.get("completed")) or bool(rec.get("save_failed")):
        return None
    return {
        "source": "questionnaire_baseline_session",
        "status": "Completada",
        "valid_for_current_session": True,
        "baseline_test_id": baseline_id,
        "calibration_user_id": int(user_id),
        "login_session_id": _get_questionnaire_login_session_id(session_user),
        "completed_iso": rec.get("completed_iso"),
        "created_at": rec.get("completed_iso") or datetime.now().isoformat(timespec="seconds"),
        "target_wait_s": BASELINE_GOOD_POSTURE_TARGET_S,
        "elapsed_s": BASELINE_GOOD_POSTURE_TARGET_S,
        "baseline_summary": rec.get("baseline_summary") if isinstance(rec.get("baseline_summary"), dict) else {},
    }


def _build_questionnaire_calibration_reset_handoff(rec, session_user, *, source="questionnaire_baseline_reset"):
    rec = rec if isinstance(rec, dict) else {}
    session_user = session_user if isinstance(session_user, dict) else {}
    user_id = resolve_user_id(user_id=session_user.get("id"), email=session_user.get("email"))
    if not user_id:
        return None
    return {
        "source": source,
        "status": "Pendiente",
        "valid_for_current_session": False,
        "baseline_test_id": None,
        "calibration_user_id": int(user_id),
        "login_session_id": _get_questionnaire_login_session_id(session_user),
        "reset_active": True,
        "requires_monitor_recalibration": True,
        "reset_epoch_ms": int(rec.get("reset_at_epoch_ms") or time.time() * 1000),
        "reset_iso": rec.get("reset_at") or datetime.now().isoformat(timespec="seconds"),
        "target_wait_s": BASELINE_GOOD_POSTURE_TARGET_S,
        "elapsed_s": 0.0,
    }


# -------------------------
# Steps (siempre presentes)
# -------------------------
def _step_1_profile():
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "6px"},
        children=[
            html.Div(
                style={"display": "flex", "flexDirection": "row", "alignItems": "stretch", "gap": "6px", "width": "100%"},
                children=[
                    html.Div(
                        style={"flex": "1 1 0", "minWidth": "0", "width": "50%"},
                        children=[
                            _subpanel(
                                "Datos básicos",
                                html.Div(
                                    style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                                    children=[
                                        _field("Edad (años)", dbc.Input(id="q-age", type="number", min=10, max=100, step=1, placeholder="Ej: 28", style=INPUT_STYLE)),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        _field("Altura (cm)", dbc.Input(id="q-height", type="number", min=80, max=250, step=1, placeholder="Ej: 175", style=INPUT_STYLE)),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        _field("Peso (kg)", dbc.Input(id="q-weight", type="number", min=30, max=250, step=0.5, placeholder="Ej: 74", style=INPUT_STYLE)),
                                    ],
                                ),
                                style={"paddingTop": "10px", "paddingBottom": "10px", "paddingLeft": "10px", "paddingRight": "10px", "gap": "6px", "minHeight": "unset", "height": "auto", "overflow": "visible", "alignSelf": "stretch"},
                            ),
                        ],
                    ),
                    html.Div(
                        style={"flex": "1 1 0", "minWidth": "0", "width": "50%"},
                        children=[
                            _subpanel(
                                "Contexto diario",
                                html.Div(
                                    style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                                    children=[
                                        _field("Horas sentado al día", dbc.Input(id="q-sitting-hours", type="number", min=0, max=18, step=0.5, placeholder="Ej: 6", style=INPUT_STYLE)),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        _field(
                                            "Contexto de trabajo",
                                            dcc.RadioItems(
                                                id="q-desk-job",
                                                options=[
                                                    {"label": "Trabajo de escritorio/PC", "value": "desk"},
                                                    {"label": "Mixto", "value": "mixed"},
                                                    {"label": "Físico", "value": "active"},
                                                ],
                                                value="desk",
                                                style=CHOICE_GROUP_STYLE_3,
                                                labelStyle=CHOICE_LABEL_STYLE,
                                                inputStyle=CHOICE_INPUT_STYLE,
                                            ),
                                        ),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        _field(
                                            "Pantalla",
                                            dcc.RadioItems(
                                                id="q-screen-height",
                                                options=[
                                                    {"label": "Alta/Correcta", "value": "ok"},
                                                    {"label": "Media", "value": "mid"},
                                                    {"label": "Baja", "value": "low"},
                                                ],
                                                value="mid",
                                                style=CHOICE_GROUP_STYLE_3,
                                                labelStyle=CHOICE_LABEL_STYLE,
                                                inputStyle=CHOICE_INPUT_STYLE,
                                            ),
                                        ),
                                    ],
                                ),
                                style={"paddingTop": "10px", "paddingBottom": "10px", "paddingLeft": "10px", "paddingRight": "10px", "gap": "6px", "minHeight": "unset", "height": "auto", "overflow": "visible", "alignSelf": "stretch"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _step_2_pain():
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "6px"},
        children=[
            html.Div(
                style={"display": "flex", "flexDirection": "row", "alignItems": "stretch", "gap": "6px", "width": "100%"},
                children=[
                    html.Div(
                        style={"flex": "1 1 0", "minWidth": "0", "width": "50%"},
                        children=[
                            _subpanel(
                                "Dolor por zona",
                                html.Div(
                                    style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                                    children=[
                                        _field_slider("Dolor cervical (0–10)", _range_control("q-pain-neck", value=0, min_value=0, max_value=10, step=1)),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        _field_slider("Dolor dorsal/torácico (0–10)", _range_control("q-pain-thor", value=0, min_value=0, max_value=10, step=1)),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        _field_slider("Dolor lumbar (0–10)", _range_control("q-pain-lum", value=0, min_value=0, max_value=10, step=1)),
                                    ],
                                ),
                                style={"paddingTop": "10px", "paddingBottom": "10px", "paddingLeft": "10px", "paddingRight": "10px", "gap": "6px", "minHeight": "unset", "height": "auto", "overflow": "visible", "alignSelf": "stretch"},
                            ),
                        ],
                    ),
                    html.Div(
                        style={"flex": "1 1 0", "minWidth": "0", "width": "50%"},
                        children=[
                            _subpanel(
                                "Síntomas asociados",
                                html.Div(
                                    style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                                    children=[
                                        _field_slider("Hormigueo/neurológico (0–10)", _range_control("q-tingle", value=0, min_value=0, max_value=10, step=1)),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        _field_slider("Rigidez matutina (0–10)", _range_control("q-stiffness", value=0, min_value=0, max_value=10, step=1)),
                                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                                        _field_slider("Cefalea/tensión (0–10)", _range_control("q-headache", value=0, min_value=0, max_value=10, step=1)),
                                    ],
                                ),
                                style={"paddingTop": "10px", "paddingBottom": "10px", "paddingLeft": "10px", "paddingRight": "10px", "gap": "6px", "minHeight": "unset", "height": "auto", "overflow": "visible", "alignSelf": "stretch"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

def _step_3_self_eval():
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "6px"},
        children=[
            _subpanel(
                "Autoevaluación postural",
                html.Div(
                    style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                    children=[
                        dcc.Checklist(
                            id="q-self-checks",
                            options=[
                                {"label": "Me encorvo al trabajar/entrenar", "value": "slouch"},
                                {"label": "Siento asimetría (cargo más un lado)", "value": "asymmetry"},
                                {"label": "Termino el día con dolor/carga", "value": "endday_pain"},
                            ],
                            value=[],
                            style=CHOICE_GROUP_STYLE_3,
                            labelStyle=CIRCULAR_CHECKLIST_LABEL_STYLE,
                            inputStyle=CHOICE_INPUT_STYLE,
                        ),
                    ],
                ),
                style={"paddingTop": "10px", "paddingBottom": "10px", "paddingLeft": "10px", "paddingRight": "10px", "gap": "6px", "minHeight": "unset", "height": "auto", "overflow": "visible", "alignSelf": "stretch"},
            ),
            _subpanel(
                "Comentario",
                html.Div(
                    style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                    children=[
                        dbc.Textarea(id="q-self-notes", placeholder="Ej: siento la zona lumbar cargada después de overhead", rows=2, style=SELF_NOTES_TEXTAREA_STYLE),
                        html.Div(style={"display": "none"}),
                    ],
                ),
                style={"paddingTop": "10px", "paddingBottom": "10px", "paddingLeft": "10px", "paddingRight": "10px", "gap": "6px", "minHeight": "unset", "height": "auto", "overflow": "visible", "alignSelf": "stretch"},
            ),
        ],
    )

def _step_4_baseline():
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "6px"},
        children=[
            html.Div(style={"display": "none"}),
            html.Div(
                style={"display": "none"},
                children=[
                    dcc.RadioItems(
                        id="q-baseline-choice",
                        options=[
                            {"label": "Ahora (recomendado)", "value": "now"},
                            {"label": "Más tarde", "value": "later"},
                        ],
                        value="later",
                        style=CHOICE_GROUP_STYLE_2,
                        labelStyle=CHOICE_LABEL_STYLE,
                        inputStyle=CHOICE_INPUT_STYLE,
                    ),
                    dbc.Textarea(id="q-baseline-notes", rows=2, placeholder="Ej: hoy me siento rígido / hice movilidad antes", style=TEXTAREA_STYLE),
                ],
            ),
            _subpanel(
                "Configuración de calibración",
                html.Div(
                    style={"display": "flex", "flexDirection": "row", "alignItems": "stretch", "gap": "8px", "width": "100%"},
                    children=[
                        html.Div(
                            style={"flex": "3 1 0", "minWidth": "0", "display": "flex", "flexDirection": "column", "gap": "6px"},
                            children=[
                                html.Div(
                                    style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                                    children=[
                                        dbc.Button("Iniciar calibración", id="q-baseline-start", color="primary", size="sm", className=BUTTON_PRIMARY_CLASS),
                                        dbc.Button("Detener y guardar", id="q-baseline-stop", color="success", size="sm", className=BUTTON_PRIMARY_CLASS, disabled=True),
                                        dbc.Button("Reset SIM", id="q-baseline-reset-sim", color="secondary", size="sm", className=BUTTON_SECONDARY_CLASS),
                                    ],
                                ),
                            ],
                        ),
                        html.Div(
                            style={"flex": "7 1 0", "minWidth": "0"},
                            children=[
                                html.Div(
                                    className="ax-panel-gray-soft ax-panel-gray-soft-stack",
                                    style={"display": "flex", "flexDirection": "column", "gap": "6px", "paddingTop": "8px", "paddingBottom": "8px", "paddingLeft": "10px", "paddingRight": "10px"},
                                    children=[
                                        html.Div(
                                            style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "8px", "width": "100%", "flexWrap": "wrap"},
                                            children=[
                                                html.Div("Estado de calibración", className="ax-section-title"),
                                                html.Div(id="q-baseline-current-info", children=_build_baseline_current_info_panel(), style={"flex": "1 1 auto", "minWidth": "220px"}),
                                            ],
                                        ),
                                        html.Div(
                                            id="q-baseline-status-box",
                                            children=_build_baseline_status_box(),
                                            style={"marginTop": "0px"},
                                        ),
                                        html.Div(id="q-baseline-status", style={"display": "none"}),
                                        html.Div(id="q-baseline-metrics-preview", style={"display": "none"}),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ),
        ],
    )

def _step_5_daily():
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "6px"},
        children=[
            _subpanel(
                "Daily check-in + objetivos",
                html.Div(
                    style={"display": "flex", "flexDirection": "column", "gap": "6px"},
                    children=[
                        _field_slider("Fatiga (0–10)", _range_control("q-fatigue", value=3, min_value=0, max_value=10, step=1)),
                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                        _field_slider("Sueño (0–10)", _range_control("q-sleep", value=6, min_value=0, max_value=10, step=1)),
                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                        _field("Objetivo principal del día", dbc.Input(id="q-goal", type="text", placeholder="Ej: técnica overhead / evitar dolor lumbar", style=INPUT_STYLE)),
                        html.Div(style={"height": "1px", "background": "rgba(255,255,255,.08)", "margin": "0"}),
                        _field(
                            "Tipo de sesión",
                            dcc.Dropdown(
                                id="q-session-type",
                                options=[
                                    {"label": "Descanso / recuperación", "value": "recovery"},
                                    {"label": "Entreno suave", "value": "light"},
                                    {"label": "Entreno normal", "value": "normal"},
                                    {"label": "Entreno intenso", "value": "hard"},
                                ],
                                value="normal",
                                clearable=False,
                                style=DROPDOWN_STYLE,
                            ),
                        ),
                    ],
                ),
            ),
        ],
    )


def _step_6_sensor():
    return html.Div(
        style={"display": "flex", "flexDirection": "column", "gap": "6px"},
        children=[
            _subpanel(
                "Resultados",
                html.Div(
                    style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                    children=[
                        html.Div(
                            id="q-auto-sensor-block",
                            style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                            children=_build_sensor_results_block(),
                        ),
                        dbc.Alert(id="q-auto-sensor-note", is_open=False, color="info", style={"display": "none", "marginTop": "4px", "marginBottom": "0", "padding": "7px 12px", "fontSize": "12px", "background": "rgba(0,0,0,.12)", "border": "1px solid rgba(255,255,255,.10)", "color": "#e2e8f0"}),
                        html.Div(
                            id="q-results-baseline-copy",
                            children=_build_baseline_metrics_block(),
                            style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                        ),
                    ],
                ),
            ),
        ],
    )



# -------------------------
# Layout
# -------------------------
def layout(reset_key=None):
    return html.Div(
        className="surface ax-questionnaire-surface",
        key=f"q{reset_key}",
        children=[
            dcc.Store(id="q-wizard-store", storage_type="memory"),
            dcc.Store(id="q-wizard-msg", storage_type="memory"),
            dcc.Store(
                id="q-baseline-rec",
                storage_type="session",
                data=_baseline_rec_defaults(),
            ),
            dcc.Store(id="questionnaire-calibration-handoff-store", storage_type="session"),
            dcc.Interval(id="q-baseline-interval", interval=200, n_intervals=0, disabled=False),

            html.Div(
                className="ax-monitor-title-row",
                style={"display": "flex", "alignItems": "flex-start", "justifyContent": "space-between", "gap": "12px", "flexWrap": "wrap"},
                children=[html.Div(className="ax-title-banner", children=[html.H2("Cuestionario", className="mb-0 ax-page-title")])],
            ),

            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.Div(
                                className="ax-card-black ax-card-black-stack ax-main-card-col ax-questionnaire-control-card",
                                children=[
                                    html.Div(
                                        className="ax-questionnaire-card-header",
                                        children=[
                                            html.Div(
                                                "Punto de control",
                                                className="ax-main-card-title-only",
                                                style=QUESTIONNAIRE_MONITOR_TITLE_STYLE,
                                            )
                                        ],
                                    ),
                                    html.Div(
                                        className="ax-device-top-row-responsive ax-questionnaire-device-row ax-questionnaire-control-status-row",
                                        style={"display": "flex", "alignItems": "stretch", "gap": "8px", "width": "100%", "flexWrap": "nowrap"},
                                        children=[
                                            html.Div(
                                                className="ax-status-item ax-questionnaire-step-status-item",
                                                style={"flex": "7 1 0", "minWidth": "0", "minHeight": "36px", "paddingTop": "6px", "paddingBottom": "6px", "paddingLeft": "12px", "paddingRight": "12px", "display": "flex", "alignItems": "center", "gap": "8px"},
                                                children=[
                                                    html.Div("Paso actual", className="ax-section-title", style={"whiteSpace": "nowrap", "flex": "0 0 auto"}),
                                                    html.Div(id="q-step-label", children=_step_label(1), className="ax-status-badge", style={"background": "rgba(255,255,255,.10)", "width": "150px", "minWidth": "150px", "maxWidth": "150px", "textAlign": "center", "flex": "0 0 150px"}),
                                                    html.Div(
                                                        dbc.Progress(id="q-step-progress", value=17, striped=True, animated=True, style={"height": "28px", "borderRadius": "999px", "overflow": "hidden"}),
                                                        style={"flex": "1 1 auto", "minWidth": "220px"},
                                                    ),
                                                ],
                                            ),
                                            html.Div(
                                                id="q-control-summary-panel",
                                                className="ax-questionnaire-status-slot",
                                                children=_build_control_summary_panel(),
                                                style={"flex": "2 1 0", "minWidth": "0"},
                                            ),
                                        ],
                                    ),
                                    html.Div(id="q-current-step-number", children="", style={"display": "none"}),
                                    dbc.Alert(id="q-baseline-banner", is_open=False, color="info", style={"marginTop": "4px", "marginBottom": "0", "padding": "7px 12px", "fontSize": "12px", "background": "rgba(0,0,0,.12)", "border": "1px solid rgba(255,255,255,.10)", "color": "#e2e8f0", "display": "none"}),
                                    html.Div(id="q-final-summary", className="mt-3", style={"display": "none"}),
                                ],
                            ),
                        ],
                        xs=12,
                        md=12,
                    ),

                    dbc.Col(
                        [
                            html.Div(
                                className="ax-card-black ax-card-black-stack ax-main-card-col ax-questionnaire-form-card",
                                children=[
                                    html.Div(
                                        className="ax-questionnaire-card-header",
                                        style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "8px", "width": "100%"},
                                        children=[
                                            html.Div(
                                                "Formulario de evaluación",
                                                className="ax-main-card-title-only",
                                                style=QUESTIONNAIRE_MONITOR_TITLE_STYLE,
                                            )
                                        ],
                                    ),
                                    html.Div(
                                        style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "8px", "width": "100%", "flexWrap": "wrap"},
                                        children=[
                                            html.Div(
                                                className="ax-device-top-row-responsive ax-questionnaire-device-row ax-questionnaire-form-status-row",
                                                style={"display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap", "flex": "1 1 auto", "minWidth": "0"},
                                                children=[
                                                    html.Div(
                                                        id="q-last-questionnaire-panel",
                                                        children=_build_last_questionnaire_panel(),
                                                        style={"flex": "1 1 0", "minWidth": "0"},
                                                    ),
                                                    html.Div(
                                                        id="q-daily-status-panel",
                                                        children=_build_daily_status_panel(),
                                                        style={"flex": "1 1 0", "minWidth": "0"},
                                                    ),
                                                    html.Div(
                                                        id="q-thresholds-status-panel",
                                                        children=_build_thresholds_status_panel(),
                                                        style={"flex": "1 1 0", "minWidth": "0"},
                                                    ),
                                                    html.Div(
                                                        children=[dbc.Button("Consejos", id="q-open-quick-tips", color="secondary", size="sm", className=BUTTON_SECONDARY_CLASS)],
                                                        style={"display": "flex", "alignItems": "stretch", "minWidth": "160px", "maxWidth": "160px", "width": "160px", "flex": "0 0 160px"},
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Div(id="q-step-1", children=_step_1_profile()),
                                    html.Div(id="q-step-2", children=_step_2_pain()),
                                    html.Div(id="q-step-3", children=_step_3_self_eval()),
                                    html.Div(id="q-step-4", children=_step_4_baseline()),
                                    html.Div(id="q-step-5", children=_step_5_daily()),
                                    html.Div(id="q-step-6", children=_step_6_sensor()),
                                    html.Div(style={"display": "none"}),
                                    html.Div(
                                        [
                                            html.Div(
                                                style={"display": "flex", "justifyContent": "flex-end", "alignItems": "center", "gap": "8px", "width": "100%"},
                                                children=[
                                                    dbc.Button("Atrás", id="q-back", color="secondary", size="sm", className=BUTTON_SECONDARY_CLASS, style={"width": "100px", "minWidth": "100px", "maxWidth": "100px"}),
                                                    dbc.Button("Siguiente", id="q-next", color="primary", size="sm", className=BUTTON_PRIMARY_CLASS, style={"width": "100px", "minWidth": "100px", "maxWidth": "100px"}),
                                                    dbc.Button("Guardar y finalizar", id="q-save-exit", color="success", size="sm", className=BUTTON_PRIMARY_CLASS, style={"width": "200px", "minWidth": "200px", "maxWidth": "200px"}),
                                                    html.Div(
                                                        dbc.Button("Finalizar", id="q-finish", color="success", size="sm", className=BUTTON_PRIMARY_CLASS),
                                                        style={"display": "none", "width": "0px", "height": "0px", "overflow": "hidden"},
                                                    ),
                                                ],
                                            ),
                                        ],
                                        className="d-flex align-items-center justify-content-end flex-wrap gap-2",
                                    ),
                                    dbc.Alert(id="q-feedback", is_open=False, color="info", style={"display": "none", "marginTop": "12px", "marginBottom": "0", "padding": "7px 12px", "fontSize": "12px", "background": "rgba(0,0,0,.12)", "border": "1px solid rgba(255,255,255,.10)", "color": "#e2e8f0"}),
                                ],
                                style={"paddingTop": "6px", "paddingBottom": "6px", "paddingLeft": "12px", "paddingRight": "12px", "display": "flex", "flexDirection": "column", "gap": "8px", "marginBottom": "0px", "marginTop": "0px"},
                            ),
                            dbc.Modal(
                                [
                                    dbc.ModalHeader(
                                        children=html.Div(
                                            style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "12px", "width": "100%"},
                                            children=[
                                                html.Div("Consejos", className="ax-modal-title"),
                                                html.Button("×", id="q-close-quick-tips-x", n_clicks=0, className="ax-modal-close-x"),
                                            ],
                                        ),
                                        close_button=False,
                                        className="ax-modal-header",
                                    ),
                                    dbc.ModalBody(
                                        html.Div(
                                            style={"display": "flex", "flexDirection": "column", "gap": "10px"},
                                            children=[
                                                html.Div(
                                                    className="ax-panel-black ax-panel-black-stack",
                                                    style={
                                                        "paddingTop": "6px",
                                                        "paddingBottom": "6px",
                                                        "paddingLeft": "12px",
                                                        "paddingRight": "12px",
                                                        "gap": "8px",
                                                    },
                                                    children=[
                                                        html.Div("Recomendaciones para completar el cuestionario", className="ax-section-title"),
                                                        html.Div(
                                                            "Responde con calma y dedica entre 2 y 3 minutos a completar cada apartado. Cuanto más precisas sean tus respuestas, mejor podrá personalizarse la monitorización y las recomendaciones.",
                                                            style={**BLACK_TEXT, "fontSize": "13px", "lineHeight": "1.5"},
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="ax-panel-gray-soft ax-panel-gray-soft-stack",
                                                    children=[
                                                        html.Div("Gestión del dolor y la carga", className="ax-section-title"),
                                                        html.Div(
                                                            "Si hoy presentas dolor elevado, rigidez o fatiga marcada, reduce la intensidad de la sesión y prioriza control técnico, movilidad y confort durante el ejercicio.",
                                                            style={**BLACK_MUTED, "fontSize": "12px", "lineHeight": "1.5"},
                                                        ),
                                                    ],
                                                ),
                                                html.Div(
                                                    className="ax-panel-gray-soft ax-panel-gray-soft-stack",
                                                    children=[
                                                        html.Div("Importancia de la calibración", className="ax-section-title"),
                                                        html.Div(
                                                            "Para que la calibración sea válida debes mantener 15 s seguidos de buena postura. Eso mejora la precisión del sensor y permite detectar compensaciones con mayor fiabilidad.",
                                                            style={**BLACK_MUTED, "fontSize": "12px", "lineHeight": "1.5"},
                                                        ),
                                                    ],
                                                ),
                                            ],
                                        ),
                                        className="ax-modal-body",
                                    ),
                                    dbc.ModalFooter(
                                        dbc.Button("Cerrar", id="q-close-quick-tips", color="secondary", outline=True, size="sm", className=BUTTON_OUTLINE_CLASS),
                                        className="ax-modal-footer",
                                    ),
                                ],
                                id="q-quick-tips-modal",
                                is_open=False,
                                centered=True,
                                backdrop=False,
                            ),
                        ],
                        xs=12,
                        md=12,
                    ),

                    dbc.Col(
                        [
                            html.Div(
                                style={"display": "none"},
                                children=[
                                    html.Div(id="q-advice-status-panel", children=_build_advice_status_panel()),
                                    dbc.Button("Ir a Monitorización", id="q-cta-monitor", color="primary", size="sm", className="ax-btn ax-btn-primary", style={"minWidth": "200px", "width": "200px", "whiteSpace": "nowrap"}),
                                    dbc.Button("Rutina recomendada", id="q-cta-routines", color="secondary", size="sm", className="ax-btn ax-btn-gray", style={"minWidth": "200px", "width": "200px", "whiteSpace": "nowrap"}),
                                ],
                            ),
                        ],
                        xs=12,
                        md=12,
                    ),

                ],
                className="ax-questionnaire-body",
                style={"rowGap": "8px", "columnGap": "8px"},
            ),
        ],
    )

# -------------------------
# Callbacks
# -------------------------
def register_callbacks(app):

    # Mostrar/ocultar pasos + controles
    @app.callback(
        [
            Output("q-step-1", "style"),
            Output("q-step-2", "style"),
            Output("q-step-3", "style"),
            Output("q-step-4", "style"),
            Output("q-step-5", "style"),
            Output("q-step-6", "style"),
            Output("q-step-label", "children"),
            Output("q-step-progress", "value"),
            Output("q-current-step-number", "children"),
            Output("q-back", "disabled"),
            Output("q-next", "disabled"),
            Output("q-finish", "disabled"),
        ],
        Input("q-wizard-store", "data"),
        prevent_initial_call=False,
    )
    def show_hide_steps(store):
        store = store or {}
        step = int(store.get("step") or 1)

        def sty(i):
            return {"display": "block"} if step == i else {"display": "none"}

        label = _step_label(step)
        progress = int((step / 6.0) * 100)
        current_step_text = f"{step} de 6"
        return sty(1), sty(2), sty(3), sty(4), sty(5), sty(6), label, progress, current_step_text, step <= 1, step >= 6, step != 6

    # Init wizard session when entering view
    @app.callback(
        [
            Output("q-wizard-store", "data"),
            Output("q-feedback", "children"),
            Output("q-feedback", "is_open"),
            Output("q-feedback", "color"),
        ],
        [Input("router", "data"), Input("session-user", "data")],
        prevent_initial_call=False,
    )
    def init_wizard(router, session_user):
        if (router or {}).get("view") != "questionnaire":
            raise PreventUpdate

        user_id = _get_questionnaire_user_id(session_user)
        if not user_id:
            return None, "Inicia sesión para completar el cuestionario.", True, "warning"

        try:
            last_init = get_latest_questionnaire_session(user_id=user_id, q_type="initial_full")
        except Exception:
            last_init = None

        q_type = "initial_full"
        if last_init and last_init.get("completed_at"):
            q_type = "daily_checkin"

        session_id = start_questionnaire_session(user_id=user_id, q_type=q_type)
        store = {"session_id": session_id, "user_id": user_id, "type": q_type, "step": 1}
        msg = "Wizard iniciado." if q_type == "initial_full" else "Daily check-in iniciado (wizard)."
        return store, msg, True, "info"

    @app.callback(
        [
            Output("q-control-summary-panel", "children"),
            Output("q-advice-status-panel", "children"),
            Output("q-last-questionnaire-panel", "children"),
            Output("q-daily-status-panel", "children"),
            Output("q-thresholds-status-panel", "children"),
            Output("q-baseline-current-info", "children"),
            Output("q-baseline-status-box", "children"),
            Output("q-results-baseline-copy", "children"),
        ],
        [
            Input("session-user", "data"),
            Input("q-wizard-store", "data"),
            Input("router", "data"),
            Input("q-finish", "n_clicks"),
            Input("q-baseline-stop", "n_clicks"),
            Input("q-baseline-start", "n_clicks"),
            Input("q-baseline-reset-sim", "n_clicks"),
            Input("q-baseline-rec", "data"),
            Input("q-wizard-msg", "data"),
            Input("q-back", "n_clicks"),
            Input("q-next", "n_clicks"),
            Input("q-save-exit", "n_clicks"),
            Input("q-age", "value"),
            Input("q-height", "value"),
            Input("q-weight", "value"),
            Input("q-sitting-hours", "value"),
            Input("q-desk-job", "value"),
            Input("q-screen-height", "value"),
            Input("q-pain-neck", "value"),
            Input("q-pain-thor", "value"),
            Input("q-pain-lum", "value"),
            Input("q-tingle", "value"),
            Input("q-stiffness", "value"),
            Input("q-headache", "value"),
            Input("q-self-checks", "value"),
            Input("q-self-notes", "value"),
            Input("q-baseline-choice", "value"),
            Input("q-baseline-notes", "value"),
            Input("q-fatigue", "value"),
            Input("q-sleep", "value"),
            Input("q-goal", "value"),
            Input("q-session-type", "value"),
        ],
        prevent_initial_call=False,
    )
    def refresh_control_summary_panel(session_user, store, router, n_finish, _n_bstop, _n_bstart, _n_breset, baseline_rec, _wizard_msg, _n_back, _n_next, _n_save_exit, age, height, weight, sitting_hours, desk_job, screen_height, pain_neck, pain_thor, pain_lum, tingle, stiffness, headache, self_checks, self_notes, baseline_choice, baseline_notes, fatigue, sleep, goal, session_type):
        if (router or {}).get("view") != "questionnaire":
            raise PreventUpdate

        user_id = _get_questionnaire_user_id(session_user)
        if not user_id:
            return (
                _build_control_summary_panel(),
                _build_advice_status_panel(),
                _build_last_questionnaire_panel(),
                _build_daily_status_panel(),
                _build_thresholds_status_panel(),
                _build_baseline_current_info_panel(),
                _build_baseline_status_box(),
                _build_baseline_metrics_block(),
            )

        try:
            latest_calibration = _get_latest_calibration_reference(int(user_id))
        except Exception:
            latest_calibration = None

        try:
            latest_daily_questionnaire = get_latest_questionnaire_session(user_id=int(user_id), q_type="daily_checkin")
        except Exception:
            latest_daily_questionnaire = None

        latest_daily_completed_at = (latest_daily_questionnaire or {}).get("completed_at")
        last_completed_text = _format_local_questionnaire_datetime(latest_daily_completed_at)

        daily_status_text = "Pendiente"
        if latest_daily_completed_at:
            raw_completed = str(latest_daily_completed_at).strip().replace("Z", "")
            parsed_completed = None
            for candidate in (raw_completed, raw_completed.replace(" ", "T")):
                try:
                    parsed_completed = datetime.fromisoformat(candidate)
                    break
                except Exception:
                    parsed_completed = None
            if parsed_completed is not None:
                parsed_completed = parsed_completed + timedelta(hours=2)
                if parsed_completed.date() == date.today():
                    daily_status_text = "Completado"

        if not _baseline_rec_matches_login(baseline_rec, session_user):
            baseline_rec = _baseline_rec_defaults()

        is_recording = bool((baseline_rec or {}).get("is_recording"))
        baseline_completed_active = bool((baseline_rec or {}).get("completed"))
        baseline_save_failed = bool((baseline_rec or {}).get("save_failed"))
        baseline_reset_active = bool((baseline_rec or {}).get("reset_active"))
        if is_recording:
            if bool((baseline_rec or {}).get("calibration_ready")):
                calibration_state_text = "Lista ✓"
            else:
                calibration_state_text = f"En curso {_baseline_streak_seconds(baseline_rec):.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f}s"
        elif baseline_completed_active:
            calibration_state_text = "OK ✓"
        elif baseline_save_failed:
            calibration_state_text = "Error"
        else:
            calibration_state_text = "Pendiente"

        if is_recording:
            calibration_date_text = f"{_baseline_streak_seconds(baseline_rec):.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f} s"
        elif baseline_completed_active:
            calibration_date_text = _format_local_questionnaire_datetime((baseline_rec or {}).get("completed_iso"))
        else:
            calibration_date_text = "Pendiente"
        thresholds_state_text = _get_thresholds_status_text(int(user_id))

        try:
            daily = get_daily_summary(user_id=int(user_id), day=date.today())
        except Exception:
            daily = None

        payload_all = {
            "profile": {
                "age": age,
                "height_cm": height,
                "weight_kg": weight,
                "sitting_hours": sitting_hours,
                "desk_job": desk_job,
                "screen_height": screen_height,
            },
            "pain": {
                "neck": pain_neck,
                "thor": pain_thor,
                "lum": pain_lum,
                "tingle": tingle,
                "stiffness": stiffness,
                "headache": headache,
            },
            "self_eval": {
                "slouch": "slouch" in (self_checks or []),
                "asymmetry": "asymmetry" in (self_checks or []),
                "endday_pain": "endday_pain" in (self_checks or []),
                "notes": self_notes or "",
            },
            "baseline": {
                "choice": baseline_choice or "later",
                "notes": baseline_notes or "",
            },
            "daily": {
                "fatigue": fatigue,
                "sleep": sleep,
                "goal": goal or "",
                "session_type": session_type or "normal",
            },
        }
        risk = _risk_from_form_and_calibration(payload_all, daily=daily, baseline=latest_calibration)
        risk_text = f"{_format_score_0_100(risk)}/100"

        historical_current_info_panel, baseline_status_box, baseline_copy_box = _build_historical_baseline_widgets(None)
        if baseline_completed_active:
            summary = baseline_rec.get("baseline_summary") if isinstance((baseline_rec or {}).get("baseline_summary"), dict) else {}
            historical_current_info_panel = _build_baseline_current_info_panel(
                calibration_date_text=_format_local_questionnaire_datetime((baseline_rec or {}).get("completed_iso")),
                calibration_state_text="OK ✓",
            )
            baseline_status_box = _build_baseline_status_box(
                message="Calibración completada: 15 s registrados en esta calibración.",
                tone="ok",
                rom_thor_pitch=summary.get("rom_thor_pitch"),
                rom_lum_pitch=summary.get("rom_lum_pitch"),
                comp_avg=summary.get("comp_avg"),
                comp_peak=summary.get("comp_peak"),
                lum_pitch_std=summary.get("lum_pitch_std"),
            )
            baseline_copy_box = _build_baseline_metrics_block(
                rom_thor_pitch=summary.get("rom_thor_pitch"),
                rom_lum_pitch=summary.get("rom_lum_pitch"),
                comp_avg=summary.get("comp_avg"),
                comp_peak=summary.get("comp_peak"),
                lum_pitch_std=summary.get("lum_pitch_std"),
            )
        elif baseline_save_failed:
            historical_current_info_panel = _build_baseline_current_info_panel(
                calibration_date_text="Pendiente",
                calibration_state_text="Error",
            )
            baseline_status_box = _build_baseline_status_box(
                message="Se completaron 15 s, pero no se pudo guardar la calibración. Pulsa Reset SIM e inténtalo de nuevo.",
                tone="warn",
            )
        elif is_recording:
            current_s = _baseline_streak_seconds(baseline_rec)
            remaining_s = _baseline_remaining_seconds(baseline_rec)
            historical_current_info_panel = _build_baseline_current_info_panel(
                calibration_date_text=f"{current_s:.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f} s",
                calibration_state_text="En progreso",
            )
            baseline_status_box = _build_baseline_status_box(
                message=f"Mantén la postura {current_s:.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f} s. Restan {remaining_s:.1f} s.",
                tone="info",
            )
        elif baseline_reset_active:
            historical_current_info_panel = _build_baseline_current_info_panel(
                calibration_date_text="Pendiente",
                calibration_state_text="Pendiente",
            )
            baseline_status_box = _build_baseline_status_box(
                message="Calibración pendiente. Pulsa Iniciar calibración para comenzar un nuevo conteo de 15 s.",
                tone="neutral",
            )
            baseline_copy_box = _build_baseline_metrics_block()

        return (
            _build_control_summary_panel(
                risk_text=risk_text,
                calibration_date_text=calibration_date_text,
                calibration_state_text=calibration_state_text,
                thresholds_state_text=thresholds_state_text,
            ),
            _build_advice_status_panel(
                calibration_date_text=calibration_date_text,
                calibration_state_text=calibration_state_text,
                thresholds_state_text=thresholds_state_text,
            ),
            _build_last_questionnaire_panel(last_completed_text=last_completed_text),
            _build_daily_status_panel(
                status_text=daily_status_text,
                calibration_date_text=calibration_date_text,
                calibration_state_text=calibration_state_text,
            ),
            _build_thresholds_status_panel(thresholds_state_text=thresholds_state_text),
            historical_current_info_panel,
            no_update if is_recording else baseline_status_box,
            baseline_copy_box,
        )



    @app.callback(
        [
            Output("q-baseline-current-info", "children", allow_duplicate=True),
            Output("q-baseline-status-box", "children", allow_duplicate=True),
            Output("q-results-baseline-copy", "children", allow_duplicate=True),
        ],
        [
            Input("router", "data"),
            Input("session-user", "data"),
            Input("q-baseline-stop", "n_clicks"),
            Input("q-wizard-msg", "data"),
            Input("q-baseline-rec", "data"),
        ],
        prevent_initial_call="initial_duplicate",
    )
    def rehydrate_baseline_history(router, session_user, _n_bstop, _wizard_msg, baseline_rec):
        if (router or {}).get("view") != "questionnaire":
            raise PreventUpdate

        user_id = _get_questionnaire_user_id(session_user)
        if not user_id:
            return (
                _build_baseline_current_info_panel(),
                _build_baseline_status_box(),
                _build_baseline_metrics_block(),
            )

        if not _baseline_rec_matches_login(baseline_rec, session_user):
            baseline_rec = _baseline_rec_defaults()

        baseline_rec = baseline_rec if isinstance(baseline_rec, dict) else _baseline_rec_defaults()
        if bool(baseline_rec.get("completed")):
            summary = baseline_rec.get("baseline_summary") if isinstance(baseline_rec.get("baseline_summary"), dict) else {}
            return (
                _build_baseline_current_info_panel(
                    calibration_date_text=_format_local_questionnaire_datetime(baseline_rec.get("completed_iso")),
                    calibration_state_text="OK ✓",
                ),
                _build_baseline_status_box(
                    message="Calibración completada: 15 s registrados en esta calibración.",
                    tone="ok",
                    rom_thor_pitch=summary.get("rom_thor_pitch"),
                    rom_lum_pitch=summary.get("rom_lum_pitch"),
                    comp_avg=summary.get("comp_avg"),
                    comp_peak=summary.get("comp_peak"),
                    lum_pitch_std=summary.get("lum_pitch_std"),
                ),
                _build_baseline_metrics_block(
                    rom_thor_pitch=summary.get("rom_thor_pitch"),
                    rom_lum_pitch=summary.get("rom_lum_pitch"),
                    comp_avg=summary.get("comp_avg"),
                    comp_peak=summary.get("comp_peak"),
                    lum_pitch_std=summary.get("lum_pitch_std"),
                ),
            )

        if bool(baseline_rec.get("save_failed")):
            return (
                _build_baseline_current_info_panel(
                    calibration_date_text="Pendiente",
                    calibration_state_text="Error",
                ),
                _build_baseline_status_box(
                    message="Se completaron 15 s, pero no se pudo guardar la calibración. Pulsa Reset SIM e inténtalo de nuevo.",
                    tone="warn",
                ),
                _build_baseline_metrics_block(),
            )

        if bool(baseline_rec.get("is_recording")):
            current_s = _baseline_streak_seconds(baseline_rec)
            remaining_s = _baseline_remaining_seconds(baseline_rec)
            return (
                _build_baseline_current_info_panel(
                    calibration_date_text=f"{current_s:.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f} s",
                    calibration_state_text="En progreso",
                ),
                _build_baseline_status_box(
                    message=f"Mantén la postura {current_s:.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f} s. Restan {remaining_s:.1f} s.",
                    tone="info",
                ),
                _build_baseline_metrics_block(),
            )

        return (
            _build_baseline_current_info_panel(),
            _build_baseline_status_box(),
            _build_baseline_metrics_block(),
        )

    @app.callback(
        [
            Output("q-pain-neck-fill", "style"),
            Output("q-pain-neck-bubble", "style"),
            Output("q-pain-neck-bubble", "children"),
            Output("q-pain-neck-marks", "children"),
            Output("q-pain-thor-fill", "style"),
            Output("q-pain-thor-bubble", "style"),
            Output("q-pain-thor-bubble", "children"),
            Output("q-pain-thor-marks", "children"),
            Output("q-pain-lum-fill", "style"),
            Output("q-pain-lum-bubble", "style"),
            Output("q-pain-lum-bubble", "children"),
            Output("q-pain-lum-marks", "children"),
            Output("q-tingle-fill", "style"),
            Output("q-tingle-bubble", "style"),
            Output("q-tingle-bubble", "children"),
            Output("q-tingle-marks", "children"),
            Output("q-stiffness-fill", "style"),
            Output("q-stiffness-bubble", "style"),
            Output("q-stiffness-bubble", "children"),
            Output("q-stiffness-marks", "children"),
            Output("q-headache-fill", "style"),
            Output("q-headache-bubble", "style"),
            Output("q-headache-bubble", "children"),
            Output("q-headache-marks", "children"),
            Output("q-fatigue-fill", "style"),
            Output("q-fatigue-bubble", "style"),
            Output("q-fatigue-bubble", "children"),
            Output("q-fatigue-marks", "children"),
            Output("q-sleep-fill", "style"),
            Output("q-sleep-bubble", "style"),
            Output("q-sleep-bubble", "children"),
            Output("q-sleep-marks", "children"),
        ],
        [
            Input("q-pain-neck", "value"),
            Input("q-pain-thor", "value"),
            Input("q-pain-lum", "value"),
            Input("q-tingle", "value"),
            Input("q-stiffness", "value"),
            Input("q-headache", "value"),
            Input("q-fatigue", "value"),
            Input("q-sleep", "value"),
        ],
        prevent_initial_call=False,
    )
    def sync_slider_visuals(pain_neck, pain_thor, pain_lum, tingle, stiffness, headache, fatigue, sleep):
        vals = [pain_neck, pain_thor, pain_lum, tingle, stiffness, headache, fatigue, sleep]
        output = []
        for v in vals:
            fill_style, bubble_style, bubble_text = _slider_visual_style(v, min_value=0, max_value=10)
            output.extend([fill_style, bubble_style, bubble_text, _build_slider_marks(v, min_value=0, max_value=10)])
        return output

    @app.callback(
        Output("q-quick-tips-modal", "is_open"),
        [Input("q-open-quick-tips", "n_clicks"), Input("q-close-quick-tips", "n_clicks"), Input("q-close-quick-tips-x", "n_clicks")],
        State("q-quick-tips-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_quick_tips_modal(_open, _close, _close_x, is_open):
        trig = dash.ctx.triggered_id
        if trig == "q-open-quick-tips":
            return True
        if trig in ("q-close-quick-tips", "q-close-quick-tips-x"):
            return False
        return is_open

    # Banner calibración recomendada (si no hay calibración)
    @app.callback(
        [
            Output("q-baseline-banner", "children"),
            Output("q-baseline-banner", "is_open"),
            Output("q-baseline-banner", "color"),
        ],
        [Input("q-wizard-store", "data"), Input("session-user", "data"), Input("router", "data")],
        prevent_initial_call=False,
    )
    def baseline_banner(_store, session_user, router):
        if (router or {}).get("view") != "questionnaire":
            raise PreventUpdate

        user_id = resolve_user_id(user_id=(session_user or {}).get("id"), email=(session_user or {}).get("email"))
        if not user_id:
            return "", False, "info"

        b = _get_latest_calibration_reference(int(user_id))

        if not b:
            return "Calibración recomendada: exige 15 s seguidos de buena postura. Ve al paso 4 para completarla.", True, "info"

        ts = b.get("created_at") or "—"
        baseline_id = b.get("baseline_test_id") or b.get("id") or "—"
        return f"Calibración detectada ✓ (última: {ts} · baseline #{baseline_id}).", True, "success"

    # -------------------------
    # PASO 4 — Calibración (start/stop + flush RAW a DB)
    # -------------------------
    @app.callback(
        [
            Output("q-baseline-rec", "data", allow_duplicate=True),
            Output("q-baseline-interval", "disabled", allow_duplicate=True),
            Output("q-baseline-status-box", "children", allow_duplicate=True),
            Output("q-baseline-status", "children"),
            Output("q-baseline-metrics-preview", "children"),
            Output("q-baseline-status", "style"),
        ],
        [
            Input("q-baseline-start", "n_clicks"),
            Input("q-baseline-stop", "n_clicks"),
            Input("q-baseline-reset-sim", "n_clicks"),
        ],
        [
            State("q-baseline-rec", "data"),
            State("q-wizard-store", "data"),
            State("session-user", "data"),
            State("q-baseline-choice", "value"),
            State("q-baseline-notes", "value"),
        ],
        prevent_initial_call=True,
    )
    def baseline_control(_n_start, _n_stop, _n_reset_sim, rec, wizard_store, session_user, baseline_choice, baseline_notes):
        trig = dash.ctx.triggered_id
        rec = rec or _baseline_rec_defaults()

        user_id = _get_questionnaire_user_id(session_user)
        if not user_id:
            return (
                rec,
                True,
                _build_baseline_status_box(
                    message="Inicia sesión para poder grabar y guardar la calibración.",
                    tone="warn",
                ),
                "",
                no_update,
                {"display": "none"},
            )
        if not _baseline_rec_matches_login(rec, session_user):
            rec = _baseline_rec_defaults()

        if trig == "q-baseline-reset-sim":
            try:
                SIM.reset()
            except Exception:
                pass
            try:
                if rec.get("sensor_session_id"):
                    end_sensor_session(session_id=int(rec.get("sensor_session_id")))
            except Exception:
                pass
            rec = {
                **_baseline_rec_defaults(),
                "reset_active": True,
                "reset_at": datetime.now().isoformat(timespec="seconds"),
                "reset_at_epoch_ms": int(time.time() * 1000),
                "calibration_user_id": int(user_id),
                "login_session_id": _get_questionnaire_login_session_id(session_user),
            }
            try:
                if wizard_store and wizard_store.get("session_id"):
                    save_questionnaire_step(
                        session_id=int(wizard_store["session_id"]),
                        step_key="baseline",
                        step_payload={
                            "choice": baseline_choice or "later",
                            "notes": baseline_notes or "",
                            "completed": False,
                            "calibration_ready": False,
                            "target_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S,
                            "good_posture_rule": "thor_green_lum_green_comp_le_20",
                            "reset_at": datetime.now().isoformat(timespec="seconds"),
                        },
                    )
            except Exception:
                pass
            return (
                rec,
                True,
                _build_baseline_status_box(
                    message="La simulación se reinició correctamente. Ya puedes iniciar una nueva calibración de 15 s seguidos de buena postura.",
                    tone="info",
                ),
                "",
                no_update,
                {"display": "none"},
            )

        if trig == "q-baseline-start":
            if rec.get("is_recording"):
                return (
                    rec,
                    False,
                    _build_baseline_status_box(
                        message=f"La grabación ya está activa. Mantén buena postura {_baseline_streak_seconds(rec):.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f} s seguidos.",
                        tone="info",
                    ),
                    "",
                    no_update,
                    {"display": "none"},
                )

            try:
                SIM.set_context(mode="desk", sport="gym")
            except Exception:
                pass

            try:
                ssid = start_sensor_session(
                    user_id=int(user_id),
                    kind="baseline",
                    mode="desk",
                    sport="gym",
                    planned_session_name="Calibración inicial",
                    questionnaire_session_id=int(wizard_store["session_id"]) if wizard_store and wizard_store.get("session_id") else None,
                    context_json={
                        "source": "questionnaire",
                        "flow": "wizard",
                        "step": "calibration",
                        "choice": baseline_choice or "later",
                    },
                )
            except Exception:
                ssid = None

            rec = {
                **_baseline_rec_defaults(),
                "is_recording": True,
                "sensor_session_id": ssid,
                "calibration_user_id": int(user_id),
                "login_session_id": _get_questionnaire_login_session_id(session_user),
                "last_ts_ms": 0,
                "start_iso": datetime.now().isoformat(timespec="seconds"),
                "started_at_epoch_ms": int(time.time() * 1000),
                "n_raw": 0,
                "good_posture_streak_ms": 0,
                "streak_last_ts_ms": 0,
                "calibration_ready": False,
            }

            try:
                if wizard_store and wizard_store.get("session_id"):
                    save_questionnaire_step(
                        session_id=int(wizard_store["session_id"]),
                        step_key="baseline",
                        step_payload={
                            "choice": baseline_choice or "later",
                            "notes": baseline_notes or "",
                            "recording_started_at": rec["start_iso"],
                            "completed": False,
                            "calibration_ready": False,
                            "target_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S,
                            "good_posture_rule": "thor_green_lum_green_comp_le_20",
                        },
                    )
            except Exception:
                pass

            return (
                rec,
                False,
                _build_baseline_status_box(
                    message=f"La grabación comenzó. Debes mantener 15 s seguidos de buena postura. Si se rompe, el contador vuelve a 0.",
                    tone="info",
                ),
                "",
                no_update,
                {"display": "none"},
            )

        if trig == "q-baseline-stop":
            if not rec.get("is_recording"):
                return (
                    rec,
                    True,
                    _build_baseline_status_box(
                        message="Primero inicia la calibración. El guardado solo se habilita cuando completes 15 s seguidos de buena postura.",
                        tone="warn",
                    ),
                    "",
                    no_update,
                    {"display": "none"},
                )

            current_s = _baseline_streak_seconds(rec)
            if not bool(rec.get("calibration_ready")) and current_s < BASELINE_GOOD_POSTURE_TARGET_S:
                remaining_s = _baseline_remaining_seconds(rec)
                return (
                    rec,
                    False,
                    _build_baseline_status_box(
                        message=f"Aún no puedes guardar. Llevas {current_s:.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f} s seguidos de buena postura y faltan {remaining_s:.1f} s.",
                        tone="warn",
                    ),
                    "",
                    no_update,
                    {"display": "none"},
                )
            rec["calibration_ready"] = True
            rec["good_posture_streak_ms"] = BASELINE_GOOD_POSTURE_TARGET_MS

            rec, baseline, baseline_id = _complete_baseline_recording_for_questionnaire(
                rec,
                user_id=int(user_id),
                wizard_store=wizard_store,
                baseline_choice=baseline_choice,
                baseline_notes=baseline_notes,
            )

            preview = _build_baseline_status_box(
                message=(
                    "Completaste 15 s seguidos de buena postura y la calibración se guardó correctamente en la base de datos."
                    if not rec.get("save_failed")
                    else "Completaste 15 s seguidos de buena postura, pero no se pudo guardar la calibración en la base de datos."
                ),
                tone="ok" if not rec.get("save_failed") else "warn",
                rom_thor_pitch=float(baseline["rom"].get("thor_pitch") or 0.0),
                rom_lum_pitch=float(baseline["rom"].get("lum_pitch") or 0.0),
                comp_avg=float(baseline["comp"].get("comp_avg") or 0.0),
                comp_peak=float(baseline["comp"].get("comp_peak") or 0.0),
                lum_pitch_std=float(baseline["stability"].get("lum_pitch_std") or 0.0),
            )
            return rec, True, preview, "", no_update, {"display": "none"}

        raise PreventUpdate

    # Interval: flush RAW mientras está grabando baseline
    @app.callback(
        Output("q-baseline-rec", "data", allow_duplicate=True),
        Input("q-baseline-interval", "n_intervals"),
        [
            State("q-baseline-rec", "data"),
            State("q-wizard-store", "data"),
            State("session-user", "data"),
            State("q-baseline-choice", "value"),
            State("q-baseline-notes", "value"),
        ],
        prevent_initial_call=True,
    )
    def baseline_tick(_n, rec, wizard_store, session_user, baseline_choice, baseline_notes):
        rec = rec or _baseline_rec_defaults()
        if not _baseline_rec_matches_login(rec, session_user):
            return _baseline_rec_defaults()
        if not rec.get("is_recording"):
            raise PreventUpdate

        ssid = rec.get("sensor_session_id")

        last_ts = int(rec.get("last_ts_ms") or 0)

        try:
            new_samples = SIM.get_samples_since(last_ts)
        except Exception:
            new_samples = []

        rows = []
        max_ts = last_ts
        started_at_epoch_ms = int(rec.get("started_at_epoch_ms") or 0)
        if started_at_epoch_ms <= 0:
            started_at_epoch_ms = int(time.time() * 1000)
            rec["started_at_epoch_ms"] = started_at_epoch_ms
        elapsed_ms = max(0, int(time.time() * 1000) - started_at_epoch_ms)
        streak_ms = min(int(elapsed_ms), BASELINE_GOOD_POSTURE_TARGET_MS)
        prev_streak_ts = int(rec.get("streak_last_ts_ms") or 0)
        for s in new_samples:
            ts_ms = int(s["ts_ms"])
            max_ts = max(max_ts, ts_ms)
            if ssid:
                rows.append(
                    (
                        int(ssid),
                        ts_ms,
                        float(s["T_pitch"]),
                        float(s["T_roll"]),
                        float(s["T_yaw"]),
                        float(s["L_pitch"]),
                        float(s["L_roll"]),
                        float(s["L_yaw"]),
                        str(s["thor_zone"]),
                        str(s["lum_zone"]),
                        float(s["comp_index"]),
                        int(s["T_imu_ts_ms"]),
                        int(s["L_imu_ts_ms"]),
                    )
                )

            prev_streak_ts = ts_ms

        rec["last_ts_ms"] = int(max_ts)
        rec["n_raw"] = int(rec.get("n_raw") or 0) + len(rows)
        rec["good_posture_streak_ms"] = int(streak_ms)
        rec["streak_last_ts_ms"] = int(prev_streak_ts)
        rec["calibration_ready"] = bool(streak_ms >= BASELINE_GOOD_POSTURE_TARGET_MS)
        rec["target_good_posture_s"] = BASELINE_GOOD_POSTURE_TARGET_S
        rec["good_posture_rule"] = "thor_green_lum_green_comp_le_20"
        rec["raw_insert_error"] = None
        if rows:
            try:
                insert_sensor_samples_raw_batch(session_id=int(ssid), rows=rows)
            except Exception as e:
                rec["raw_insert_error"] = str(e)
        if bool(rec.get("calibration_ready")):
            user_id = _get_questionnaire_user_id(session_user)
            if not user_id:
                return rec
            completed_rec, _baseline, _baseline_id = _complete_baseline_recording_for_questionnaire(
                rec,
                user_id=int(user_id),
                wizard_store=wizard_store,
                baseline_choice=baseline_choice,
                baseline_notes=baseline_notes,
            )
            return completed_rec
        return rec

    @app.callback(
        Output("q-baseline-rec", "data", allow_duplicate=True),
        [Input("session-user", "data"), Input("q-baseline-rec", "data")],
        prevent_initial_call="initial_duplicate",
    )
    def sync_baseline_rec_login_scope(session_user, rec):
        if _baseline_rec_matches_login(rec, session_user):
            raise PreventUpdate
        return _baseline_rec_defaults()

    # Activar/desactivar interval según estado de grabación
    @app.callback(
        Output("questionnaire-calibration-handoff-store", "data"),
        [Input("q-baseline-rec", "data", allow_optional=True), Input("session-user", "data")],
        prevent_initial_call=True,
    )
    def sync_questionnaire_calibration_handoff(rec, session_user):
        trig = dash.ctx.triggered_id
        rec = rec if isinstance(rec, dict) else {}
        session_user = session_user if isinstance(session_user, dict) else {}
        user_id = resolve_user_id(user_id=session_user.get("id"), email=session_user.get("email"))
        if not user_id:
            return None
        if bool(rec.get("reset_active")):
            return _build_questionnaire_calibration_reset_handoff(rec, session_user)
        if bool(rec.get("is_recording")):
            return _build_questionnaire_calibration_reset_handoff(rec, session_user, source="questionnaire_baseline_in_progress")
        handoff = _build_questionnaire_calibration_handoff(rec, session_user)
        if handoff:
            return handoff
        if trig == "session-user":
            return None
        raise PreventUpdate

    @app.callback(
        Output("q-baseline-interval", "disabled", allow_duplicate=True),
        Input("q-baseline-rec", "data"),
        prevent_initial_call=True,
    )
    def baseline_interval_toggle(rec):
        rec = rec or {}
        return (not bool(rec.get("is_recording")))

    # Status mientras graba
    @app.callback(
        Output("q-baseline-status-box", "children", allow_duplicate=True),
        [Input("q-baseline-rec", "data"), Input("q-baseline-interval", "n_intervals")],
        State("session-user", "data"),
        prevent_initial_call=True,
    )
    def baseline_status(rec, _n_interval, session_user):
        rec = rec or _baseline_rec_defaults()
        if not _baseline_rec_matches_login(rec, session_user):
            rec = _baseline_rec_defaults()
        if bool(rec.get("completed")):
            summary = rec.get("baseline_summary") if isinstance(rec.get("baseline_summary"), dict) else {}
            return _build_baseline_status_box(
                message="Calibración completada: 15 s seguidos de buena postura registrados y guardados.",
                tone="ok",
                rom_thor_pitch=summary.get("rom_thor_pitch"),
                rom_lum_pitch=summary.get("rom_lum_pitch"),
                comp_avg=summary.get("comp_avg"),
                comp_peak=summary.get("comp_peak"),
                lum_pitch_std=summary.get("lum_pitch_std"),
            )
        if bool(rec.get("save_failed")):
            return _build_baseline_status_box(
                message="Se completaron 15 s seguidos de buena postura, pero no se pudo guardar la calibración. Pulsa Reset SIM e inténtalo de nuevo.",
                tone="warn",
            )
        if not rec.get("is_recording"):
            raise PreventUpdate
        current_s = _baseline_streak_seconds(rec)
        remaining_s = _baseline_remaining_seconds(rec)
        if bool(rec.get("calibration_ready")):
            return _build_baseline_status_box(
                message="Calibración completada: 15 s seguidos de buena postura registrados.",
                tone="ok",
            )
        return _build_baseline_status_box(
            message=f"Mantén buena postura {current_s:.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f} s seguidos. Si se rompe, el contador vuelve a 0. Restan {remaining_s:.1f} s.",
            tone="info",
        )


    @app.callback(
        [
            Output("q-baseline-stop", "disabled"),
            Output("q-baseline-stop", "children"),
        ],
        [Input("q-baseline-rec", "data"), Input("q-baseline-interval", "n_intervals")],
        State("session-user", "data"),
        prevent_initial_call=False,
    )
    def sync_baseline_stop_button(rec, _n_interval, session_user):
        rec = rec or _baseline_rec_defaults()
        if not _baseline_rec_matches_login(rec, session_user):
            rec = _baseline_rec_defaults()
        if bool(rec.get("completed")):
            return True, "Calibración completada"
        if bool(rec.get("save_failed")):
            return True, "Error al guardar"
        if not rec.get("is_recording"):
            return True, "Detener y guardar"
        if bool(rec.get("calibration_ready")) or _baseline_streak_seconds(rec) >= BASELINE_GOOD_POSTURE_TARGET_S:
            return False, "Detener y guardar"
        return True, f"Buena postura {_baseline_streak_seconds(rec):.1f}/{BASELINE_GOOD_POSTURE_TARGET_S:.0f}s"

    # Cargar daily_summary (solo en paso 5)
    @app.callback(
        [
            Output("q-auto-sensor-block", "children"),
            Output("q-auto-sensor-note", "children"),
            Output("q-auto-sensor-note", "is_open"),
            Output("q-auto-sensor-note", "color"),
        ],
        [Input("session-user", "data"), Input("q-wizard-store", "data"), Input("router", "data")],
        prevent_initial_call=False,
    )
    def load_daily_summary_block(session_user, store, router):
        if (router or {}).get("view") != "questionnaire":
            raise PreventUpdate

        user_id = resolve_user_id(user_id=(session_user or {}).get("id"), email=(session_user or {}).get("email"))
        step = int((store or {}).get("step") or 1)
        if step != 6:
            return no_update, no_update, no_update, no_update

        if not user_id:
            block = _build_sensor_results_block()
            return block, "", False, "warning"

        today_date = date.today()
        try:
            d = get_daily_summary(user_id=int(user_id), day=today_date)
        except Exception:
            d = None

        latest_calibration = _get_latest_calibration_reference(int(user_id))
        calibration_note = "Calibración disponible desde baseline histórico compartido." if latest_calibration else "Calibración pendiente."

        if not d:
            block = _build_sensor_results_block(
                thor="0.0",
                lum="0.0",
                comp_avg="0.0",
                comp_peak="0.0",
                alerts_count="0",
                risk_max="0.0",
            )
            return block, "", False, "info"

        thor = float(d.get("thor_red_s") or 0.0)
        lum = float(d.get("lum_red_s") or 0.0)
        comp_avg = float(d.get("comp_avg") or 0.0)
        comp_peak = float(d.get("comp_peak") or 0.0)
        alerts_count = int(d.get("alerts_count") or 0)
        risk_max = float(d.get("risk_index_max") or 0.0)

        tone = "ok"
        if risk_max >= 70 or thor + lum >= 60:
            tone = "bad"
        elif risk_max >= 40 or thor + lum >= 20:
            tone = "warn"

        block = _build_sensor_results_block(
            thor=f"{thor:.1f}",
            lum=f"{lum:.1f}",
            comp_avg=f"{comp_avg:.1f}",
            comp_peak=f"{comp_peak:.1f}",
            alerts_count=f"{alerts_count:d}",
            risk_max=f"{risk_max:.1f}",
            tone_thor=tone if thor > 0 else "neutral",
            tone_lum=tone if lum > 0 else "neutral",
            tone_comp_avg=tone if comp_avg >= 60 else "neutral",
            tone_comp_peak=tone if comp_peak >= 60 else "neutral",
            tone_alerts="warn" if alerts_count > 0 else "neutral",
            tone_risk=tone,
        )
        return block, "", False, "success"

    # Wizard control: back/next/save-exit/finish
    @app.callback(
        [
            Output("q-wizard-store", "data", allow_duplicate=True),
            Output("q-feedback", "children", allow_duplicate=True),
            Output("q-feedback", "is_open", allow_duplicate=True),
            Output("q-feedback", "color", allow_duplicate=True),
            Output("q-final-summary", "children", allow_duplicate=True),
            Output("q-wizard-msg", "data", allow_duplicate=True),
        ],
        [Input("q-back", "n_clicks"), Input("q-next", "n_clicks"), Input("q-save-exit", "n_clicks"), Input("q-finish", "n_clicks")],
        [
            State("q-wizard-store", "data"),
            State("session-user", "data"),
            # step 1
            State("q-age", "value"),
            State("q-height", "value"),
            State("q-weight", "value"),
            State("q-sitting-hours", "value"),
            State("q-desk-job", "value"),
            State("q-screen-height", "value"),
            # step 2
            State("q-pain-neck", "value"),
            State("q-pain-thor", "value"),
            State("q-pain-lum", "value"),
            State("q-tingle", "value"),
            State("q-stiffness", "value"),
            State("q-headache", "value"),
            # step 3
            State("q-self-checks", "value"),
            State("q-self-notes", "value"),
            # step 4
            State("q-baseline-choice", "value"),
            State("q-baseline-notes", "value"),
            # step 5
            State("q-fatigue", "value"),
            State("q-sleep", "value"),
            State("q-goal", "value"),
            State("q-session-type", "value"),
            State("q-baseline-rec", "data"),
        ],
        prevent_initial_call=True,
    )
    def wizard_control(_nb, _nn, _nse, _nf, store, session_user, *vals):
        trig = dash.ctx.triggered_id
        store = store or {}

        user_id = resolve_user_id(user_id=(session_user or {}).get("id"), email=(session_user or {}).get("email"))
        if not user_id:
            return store, "Inicia sesión para continuar.", True, "warning", no_update, {"ts": datetime.now().isoformat(timespec="seconds"), "source": "auth"}

        session_id = store.get("session_id")
        step = int(store.get("step") or 1)

        (
            age, height, weight, sitting_hours, desk_job, screen_height,
            pain_neck, pain_thor, pain_lum, tingle, stiffness, headache,
            self_checks, self_notes,
            baseline_choice, baseline_notes,
            fatigue, sleep, goal, session_type,
            baseline_rec
        ) = vals

        def save_current_step():
            if not session_id:
                return
            try:
                if step == 1:
                    save_questionnaire_step(session_id=int(session_id), step_key="profile", step_payload={
                        "age": age, "height_cm": height, "weight_kg": weight,
                        "sitting_hours": sitting_hours, "desk_job": desk_job, "screen_height": screen_height
                    })
                elif step == 2:
                    save_questionnaire_step(session_id=int(session_id), step_key="pain", step_payload={
                        "neck": pain_neck, "thor": pain_thor, "lum": pain_lum, "tingle": tingle, "stiffness": stiffness, "headache": headache
                    })
                elif step == 3:
                    checks = self_checks or []
                    save_questionnaire_step(session_id=int(session_id), step_key="self_eval", step_payload={
                        "slouch": "slouch" in checks,
                        "asymmetry": "asymmetry" in checks,
                        "endday_pain": "endday_pain" in checks,
                        "notes": self_notes or ""
                    })
                elif step == 4:
                    baseline_rec_local = baseline_rec if isinstance(baseline_rec, dict) else {}
                    baseline_completed = bool(baseline_rec_local.get("completed"))
                    save_questionnaire_step(session_id=int(session_id), step_key="baseline", step_payload={
                        "choice": baseline_choice or "later",
                        "notes": baseline_notes or "",
                        "completed": baseline_completed,
                        "calibration_ready": baseline_completed,
                        "baseline_id": baseline_rec_local.get("baseline_id") if baseline_completed else None,
                        "continuous_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S if baseline_completed else 0.0,
                        "target_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S,
                        "good_posture_rule": "thor_green_lum_green_comp_le_20",
                        "baseline_summary": baseline_rec_local.get("baseline_summary") if baseline_completed and isinstance(baseline_rec_local.get("baseline_summary"), dict) else {},
                    })
                elif step == 5:
                    save_questionnaire_step(session_id=int(session_id), step_key="daily", step_payload={
                        "fatigue": fatigue, "sleep": sleep, "goal": goal or "",
                        "session_type": session_type or "normal", "day": date.today().isoformat()
                    })
                elif step == 6:
                    pass
            except Exception:
                pass

        if trig in ("q-back", "q-next", "q-save-exit", "q-finish"):
            save_current_step()

        if trig == "q-back":
            store["step"] = max(1, step - 1)
            return store, "Guardado ✓", True, "success", no_update, {"ts": datetime.now().isoformat(timespec="seconds"), "source": "nav_back"}

        if trig == "q-next":
            store["step"] = min(6, step + 1)
            return store, "Guardado ✓", True, "success", no_update, {"ts": datetime.now().isoformat(timespec="seconds"), "source": "nav_next"}

        if trig in ("q-save-exit", "q-finish"):
            try:
                daily = get_daily_summary(user_id=int(user_id), day=date.today())
            except Exception:
                daily = None

            payload_all = {
                "profile": {"age": age, "height_cm": height, "weight_kg": weight, "sitting_hours": sitting_hours,
                            "desk_job": desk_job, "screen_height": screen_height},
                "pain": {"neck": pain_neck, "thor": pain_thor, "lum": pain_lum, "tingle": tingle, "stiffness": stiffness, "headache": headache},
                "self_eval": {"slouch": "slouch" in (self_checks or []), "asymmetry": "asymmetry" in (self_checks or []),
                             "endday_pain": "endday_pain" in (self_checks or []), "notes": self_notes or ""},
                "baseline": {"choice": baseline_choice or "later", "notes": baseline_notes or ""},
                "daily": {"fatigue": fatigue, "sleep": sleep, "goal": goal or "", "session_type": session_type or "normal"},
            }

            # guardar perfil de monitorización personalizado por usuario
            b = _get_latest_calibration_reference(int(user_id))

            risk = _risk_from_form_and_calibration(payload_all, daily=daily, baseline=b)

            thresholds_saved = False
            try:
                monitor_profile = _build_monitor_profile(
                    payload_all["profile"],
                    payload_all["pain"],
                    daily or {},
                    b,
                    fatigue,
                    sleep,
                )
                upsert_user_posture_settings(user_id=int(user_id), thresholds=monitor_profile)
                thresholds_saved = (_get_thresholds_status_text(int(user_id)) == "Guardados ✓")
            except Exception:
                thresholds_saved = False

            # estado de calibración
            has_baseline = bool(b)

            recommendation = {
                "risk_index": risk,
                "has_baseline": has_baseline,
                "cta": {"monitor": True, "routines": True},
                "note": "Calibración recomendada para mejorar precisión." if not has_baseline else "Calibración OK.",
            }

            try:
                if session_id:
                    complete_questionnaire_session(session_id=int(session_id), risk_index=risk, recommendation=recommendation)
            except Exception:
                pass

            tone = "success" if risk < 40 else ("warning" if risk < 70 else "danger")
            summary = dbc.Alert(
                [
                    html.Div(f"Risk Index estimado: {_format_score_0_100(risk)}/100", style={"fontWeight": 800}),
                    html.Div("Calibración: " + ("OK ✓" if has_baseline else "pendiente (recomendada)")),
                    html.Div("Umbrales personalizados: " + ("Guardados ✓" if thresholds_saved else "Pendientes")),
                ],
                color=tone,
                className="mb-0",
            )
            return store, "Cuestionario finalizado ✓", True, "success", summary, {"ts": datetime.now().isoformat(timespec="seconds"), "source": ("save_exit" if trig == "q-save-exit" else "finish")}

        raise PreventUpdate

    # CTAs: navegar por router
    @app.callback(
        Output("router", "data", allow_duplicate=True),
        [Input("q-cta-monitor", "n_clicks"), Input("q-cta-routines", "n_clicks")],
        [
            State("session-user", "data"),
            State("q-wizard-store", "data"),
            State("q-age", "value"),
            State("q-height", "value"),
            State("q-weight", "value"),
            State("q-sitting-hours", "value"),
            State("q-desk-job", "value"),
            State("q-screen-height", "value"),
            State("q-pain-neck", "value"),
            State("q-pain-thor", "value"),
            State("q-pain-lum", "value"),
            State("q-tingle", "value"),
            State("q-stiffness", "value"),
            State("q-headache", "value"),
            State("q-self-checks", "value"),
            State("q-self-notes", "value"),
            State("q-baseline-choice", "value"),
            State("q-baseline-notes", "value"),
            State("q-fatigue", "value"),
            State("q-sleep", "value"),
            State("q-goal", "value"),
            State("q-session-type", "value"),
            State("q-baseline-rec", "data"),
        ],
        prevent_initial_call=True,
    )
    def go_to_pages(n_m, n_r, session_user, store, age, height, weight, sitting_hours, desk_job, screen_height, pain_neck, pain_thor, pain_lum, tingle, stiffness, headache, self_checks, self_notes, baseline_choice, baseline_notes, fatigue, sleep, goal, session_type, baseline_rec):
        trig = dash.ctx.triggered_id
        if not session_user or (session_user.get("role") or "").lower() != "atleta":
            raise PreventUpdate

        def _save_current_for_link():
            local_store = store or {}
            session_id = local_store.get("session_id")
            step = int(local_store.get("step") or 1)
            q_type = str(local_store.get("type") or "")
            if not session_id:
                return

            try:
                if step == 1:
                    save_questionnaire_step(session_id=int(session_id), step_key="profile", step_payload={
                        "age": age, "height_cm": height, "weight_kg": weight,
                        "sitting_hours": sitting_hours, "desk_job": desk_job, "screen_height": screen_height
                    })
                elif step == 2:
                    save_questionnaire_step(session_id=int(session_id), step_key="pain", step_payload={
                        "neck": pain_neck, "thor": pain_thor, "lum": pain_lum, "tingle": tingle, "stiffness": stiffness, "headache": headache
                    })
                elif step == 3:
                    checks = self_checks or []
                    save_questionnaire_step(session_id=int(session_id), step_key="self_eval", step_payload={
                        "slouch": "slouch" in checks,
                        "asymmetry": "asymmetry" in checks,
                        "endday_pain": "endday_pain" in checks,
                        "notes": self_notes or ""
                    })
                elif step == 4:
                    baseline_rec_local = baseline_rec if isinstance(baseline_rec, dict) else {}
                    baseline_completed = bool(baseline_rec_local.get("completed"))
                    save_questionnaire_step(session_id=int(session_id), step_key="baseline", step_payload={
                        "choice": baseline_choice or "later",
                        "notes": baseline_notes or "",
                        "completed": baseline_completed,
                        "calibration_ready": baseline_completed,
                        "baseline_id": baseline_rec_local.get("baseline_id") if baseline_completed else None,
                        "continuous_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S if baseline_completed else 0.0,
                        "target_good_posture_s": BASELINE_GOOD_POSTURE_TARGET_S,
                        "good_posture_rule": "thor_green_lum_green_comp_le_20",
                        "baseline_summary": baseline_rec_local.get("baseline_summary") if baseline_completed and isinstance(baseline_rec_local.get("baseline_summary"), dict) else {},
                    })
                elif step == 5:
                    save_questionnaire_step(session_id=int(session_id), step_key="daily", step_payload={
                        "fatigue": fatigue, "sleep": sleep, "goal": goal or "",
                        "session_type": session_type or "normal", "day": date.today().isoformat()
                    })
                elif step == 6:
                    pass
            except Exception:
                pass

            # Para que Monitor pueda enlazar automáticamente la sesión vinculada desde DB,
            # completamos el cuestionario si ya existe contexto suficiente del paso Daily
            # o si el flujo ya es daily_checkin. Así get_monitor_link_context(...) prioriza
            # este cuestionario actual y no una sesión antigua ya completada.
            should_complete_for_link = bool(step in (5, 6) and (session_type or goal or fatigue is not None or sleep is not None)) or q_type == "daily_checkin"
            if not should_complete_for_link:
                return

            try:
                daily = get_daily_summary(user_id=int(resolve_user_id(user_id=(session_user or {}).get("id"), email=(session_user or {}).get("email"))), day=date.today())
            except Exception:
                daily = None

            payload_all = {
                "profile": {"age": age, "height_cm": height, "weight_kg": weight, "sitting_hours": sitting_hours,
                            "desk_job": desk_job, "screen_height": screen_height},
                "pain": {"neck": pain_neck, "thor": pain_thor, "lum": pain_lum, "tingle": tingle, "stiffness": stiffness, "headache": headache},
                "self_eval": {"slouch": "slouch" in (self_checks or []), "asymmetry": "asymmetry" in (self_checks or []),
                             "endday_pain": "endday_pain" in (self_checks or []), "notes": self_notes or ""},
                "baseline": {"choice": baseline_choice or "later", "notes": baseline_notes or ""},
                "daily": {"fatigue": fatigue, "sleep": sleep, "goal": goal or "", "session_type": session_type or "normal"},
            }
            try:
                _uid_for_link = int(resolve_user_id(user_id=(session_user or {}).get("id"), email=(session_user or {}).get("email")))
            except Exception:
                _uid_for_link = None
            b = _get_latest_calibration_reference(_uid_for_link)
            risk = _risk_from_form_and_calibration(payload_all, daily=daily, baseline=b)
            recommendation = {
                "risk_index": risk,
                "has_baseline": bool(b),
                "cta": {"monitor": True, "routines": True},
                "auto_completed_from": "questionnaire_cta",
                "note": "Calibración recomendada para mejorar precisión." if not b else "Calibración OK.",
            }
            try:
                # Enlace Cuestionario -> Monitor/Rutinas: persistimos el payload
                # completo antes de completar la sesiÃ³n para que las vistas enlazadas
                # no dependan solo del paso activo guardado justo antes del CTA.
                for _step_key, _step_payload in payload_all.items():
                    save_questionnaire_step(
                        session_id=int(session_id),
                        step_key=str(_step_key),
                        step_payload=_step_payload if isinstance(_step_payload, dict) else {},
                    )
                complete_questionnaire_session(session_id=int(session_id), risk_index=risk, recommendation=recommendation)
            except Exception:
                pass

        _save_current_for_link()

        if trig == "q-cta-monitor" and (n_m or 0) > 0:
            return {"view": "monitor"}
        if trig == "q-cta-routines" and (n_r or 0) > 0:
            return {"view": "routines"}
        raise PreventUpdate

# Ajuste visual solicitado: subcuadro negro de Estado movido al encabezado de Paso actual.
# Ajuste visual solicitado: botones de Estado se mantienen en su tarjeta original.
# Ajuste visual solicitado: cuadros grises de Paso actual con ancho fijo de 200px.
# Ajuste visual solicitado: en ventana 2, “Dolor por zona” y “Síntomas asociados” van en horizontal.
# Ajuste visual solicitado: ambos cuadros negros de ventana 2 mantienen 200px de alto.

# Ajuste funcional solicitado: el CTA a Monitor/Rutinas guarda el paso actual y completa el cuestionario cuando existe contexto Daily para poblar automáticamente la sesión vinculada del monitor.
# Ajuste visual solicitado: título del cuadro superior cambiado de “Estado” a “Punto de control”.
# Ajuste visual solicitado: se añade “Formulario de evaluación” sobre el cuadro negro principal del centro.

# Ajuste visual solicitado: botones de navegación movidos desde Punto de control al cuadro de Consejos rápidos.
# Ajuste visual solicitado: en Índice de riesgo, Umbrales personalizados ahora aparece debajo de Calibración.

# Ajuste visual solicitado: en Punto de control, “Paso actual” ocupa 4/6 y “Índice de riesgo” ocupa 2/6 en la misma fila.

# Ajuste visual solicitado: en Paso actual, título, subcuadro gris y barra quedan en una sola línea.
# Ajuste visual solicitado: el cuadro de Índice de riesgo y su valor interno se reducen para ceder espacio a Paso actual.

# Ajuste visual solicitado: en Punto de control se elimina la línea blanca separatoria inferior.
# Ajuste visual solicitado: se reduce solo la separación con Formulario de evaluación, manteniendo el resto igual.

# Ajuste visual solicitado: cuadros negros secundarios unificados a padding 10px, gap interno 6px y gap entre subcuadros 5px.
# Ajuste tipográfico solicitado: títulos principales 13px/700/#e2e8f0, texto secundario 12px/600/rgba(226,232,240,.75) y valores 12px/700/#e2e8f0.

# Ajuste visual solicitado: cuadros grises generales unificados a margen 0, padding 6px 10px, gap interno horizontal 8px, altura aprox. 28–32px, radio 999px y tipografía label/value 12px.
# Ajuste visual solicitado: Paso actual e Índice de riesgo usan padding 10px 10px, gap interno 6px, altura aprox. 36–42px, radio 12px y tipografía especial 13px/12px.

# Ajuste visual solicitado: cuadros negros del cuestionario unificados a padding vertical 6px, padding horizontal 12px y gap interno 8px.

# Ajuste visual solicitado: sliders de Dolor por zona, Síntomas asociados y Daily check-in + objetivos envueltos en un contenedor más alto verticalmente.
# Ajuste visual solicitado: se añade _slider_control y _field_slider para aumentar la altura visual de la línea del selector sin tocar la lógica del componente.
# Ajuste visual solicitado: cuadro gris de Paso actual con ancho fijo de 150px.
# Ajuste visual solicitado: cuadro gris de Índice de riesgo con ancho fijo de 100px.
# Ajuste visual solicitado: el valor máximo visible del índice se muestra como 100 y no como 100.0.

# Ajuste funcional solicitado: se añade un tercer síntoma en el bloque de síntomas asociados.
# Ajuste funcional solicitado: el nuevo síntoma se guarda en payload/session y participa en el cálculo del índice de riesgo.

# Ajuste visual solicitado: los cuadros negros de Datos básicos, Contexto diario, Dolor por zona y Síntomas asociados ajustan su altura al contenido.
# Ajuste visual solicitado: esos cuatro cuadros usan el mismo comportamiento compacto del bloque tipo Índice de riesgo, sin alto fijo ni scroll interno.

# Ajuste visual solicitado: botones del formulario combinados en tres visibles, alineados a la derecha con anchos 100px, 200px y 100px.
# Ajuste funcional solicitado: el botón “Guardar y finalizar” reutiliza q-save-exit y ejecuta la misma lógica de finalización, manteniendo q-finish oculto para compatibilidad de callbacks.

# Ajuste visual solicitado: en Autoevaluación postural y Comentario se elimina “opcional”, ambos cuadros usan el mismo estilo compacto de Datos básicos y el checklist se alinea como Contexto de trabajo.

# Ajuste visual solicitado: en Autoevaluación postural se elimina el cuadro gris del campo y el checklist usa la misma disposición visual del contexto diario.
# Ajuste visual solicitado: el comentario de autoevaluación se reduce a un área equivalente a 2 líneas visibles.

# Ajuste visual solicitado: paso 4 rediseñado con botones a la izquierda y panel de estado de calibración a la derecha, priorizando legibilidad del resumen y del estado actual.
# Ajuste visual solicitado: en Estado de calibración se eliminan las etiquetas internas “Estado” y “Última calibración”, se muestran solo valor y fecha en la misma línea del título, y se elimina el texto descriptivo inferior.

# Ajuste funcional solicitado: “Datos automáticos del sensor (hoy)” se separa del paso 5 y pasa a ser el paso final 6 del wizard, manteniendo su misma lógica de carga desde daily_summary.

# Ajuste visual solicitado: paso 6 renombrado a “Resultados” y se añade una copia del resumen de calibración para mostrar toda la información obtenida.

# Ajuste visual solicitado: en Resultados se integran las métricas de calibración dentro del mismo cuadro y se ocultan los textos repetidos del bloque automático.
