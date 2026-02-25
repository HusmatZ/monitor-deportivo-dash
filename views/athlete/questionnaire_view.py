# views/athlete/questionnaire_view.py
#
# Wizard 5 pasos (perfil -> dolor -> auto -> baseline -> daily)
# - Guarda a DB: questionnaire_sessions (payload_json)
# - Baseline recomendado (NO obligatorio): banner + CTA
# - Salida: upsert_user_posture_settings + risk index + recomendaciones + CTA a Monitor/Rutinas
#
# ✅ Baseline SIM: start/stop -> sensor_sessions(kind="baseline") + RAW -> baseline_tests
# ✅ Baseline cuenta en daily_summary: recompute_daily_summary(...)
# ✅ FIX Dash: Todos los IDs usados en States existen siempre (pasos ocultos, no removidos)
# ✅ FIX Dash: Eliminado q-reset (no existe en otras ventanas)
#
from datetime import date, datetime
from typing import Dict, Any, Optional, List, Tuple

import dash
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
    get_latest_baseline,
    upsert_user_posture_settings,
    # baseline recording
    start_sensor_session,
    insert_sensor_samples_raw_batch,
    upsert_session_summary,
    recompute_daily_summary,
    end_sensor_session,
    create_baseline_test,
)

PANEL_STYLE = {
    "border": "1px solid #e2e8f0",
    "background": "#ffffff",
    "borderRadius": "14px",
    "boxShadow": "0 4px 14px rgba(15,23,42,.06)",
}
TITLE_STYLE = {"fontWeight": 700, "color": "#0f172a", "marginBottom": "8px"}
MUTED = {"color": "#64748b"}


# -------------------------
# UI helpers
# -------------------------
def _kv(label, value, tone="neutral"):
    tone_map = {
        "neutral": {"background": "#f1f5f9", "border": "#e2e8f0", "color": "#334155"},
        "ok": {"background": "#ecfdf5", "border": "#bbf7d0", "color": "#065f46"},
        "warn": {"background": "#fffbeb", "border": "#fde68a", "color": "#92400e"},
        "bad": {"background": "#fef2f2", "border": "#fecaca", "color": "#991b1b"},
    }
    s = tone_map.get(tone, tone_map["neutral"])
    return html.Div(
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "gap": "10px",
            "padding": "8px 10px",
            "borderRadius": "12px",
            "background": s["background"],
            "border": f"1px solid {s['border']}",
            "color": s["color"],
            "fontSize": "12px",
            "fontWeight": 700,
        },
        children=[html.Span(label), html.Span(value)],
    )


def _step_label(step: int) -> str:
    labels = {
        1: "1/5 · Perfil postural",
        2: "2/5 · Dolor y síntomas",
        3: "3/5 · Autoevaluación",
        4: "4/5 · Baseline (recomendado)",
        5: "5/5 · Daily + objetivos",
    }
    return labels.get(int(step or 1), "1/5 · Perfil postural")


def _clamp_int(v, lo=0, hi=10) -> Optional[int]:
    if v is None:
        return None
    try:
        iv = int(v)
    except Exception:
        return None
    return max(lo, min(hi, iv))


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


def _build_thresholds(profile: Dict[str, Any], pain: Dict[str, Any]) -> Dict[str, Any]:
    """
    Genera thresholds por usuario (genéricos pero ajustables).
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

    if lum_pain >= 7:
        thr["desk"]["lum"]["pitch_y"] = max(12.0, thr["desk"]["lum"]["pitch_y"] - 2.0)
        thr["desk"]["lum"]["pitch_g"] = max(7.0, thr["desk"]["lum"]["pitch_g"] - 1.0)

    if thor_pain >= 7 or neck_pain >= 7 or hours >= 6:
        thr["desk"]["thor"]["pitch_y"] = max(10.0, thr["desk"]["thor"]["pitch_y"] - 2.0)
        thr["desk"]["thor"]["pitch_g"] = max(5.0, thr["desk"]["thor"]["pitch_g"] - 1.0)

    return {"thresholds": thr, "version": "wizard_v1"}


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


# -------------------------
# Steps (siempre presentes)
# -------------------------
def _step_1_profile():
    return dbc.Form(
        [
            dbc.Label("Edad (años)"),
            dbc.Input(id="q-age", type="number", min=10, max=100, step=1, placeholder="Ej: 28", className="mb-2"),
            dbc.Label("Altura (cm)"),
            dbc.Input(id="q-height", type="number", min=80, max=250, step=1, placeholder="Ej: 175", className="mb-2"),
            dbc.Label("Peso (kg)"),
            dbc.Input(id="q-weight", type="number", min=30, max=250, step=0.5, placeholder="Ej: 74", className="mb-2"),
            dbc.Label("Horas sentado al día"),
            dbc.Input(id="q-sitting-hours", type="number", min=0, max=18, step=0.5, placeholder="Ej: 6", className="mb-2"),
            dbc.Label("Contexto de trabajo"),
            dcc.RadioItems(
                id="q-desk-job",
                options=[
                    {"label": "Trabajo de escritorio/PC", "value": "desk"},
                    {"label": "Mixto", "value": "mixed"},
                    {"label": "Físico", "value": "active"},
                ],
                value="desk",
                labelStyle={"display": "block"},
                className="mb-2",
            ),
            dbc.Label("Pantalla"),
            dcc.RadioItems(
                id="q-screen-height",
                options=[
                    {"label": "Alta/Correcta", "value": "ok"},
                    {"label": "Media", "value": "mid"},
                    {"label": "Baja", "value": "low"},
                ],
                value="mid",
                labelStyle={"display": "block"},
                className="mb-0",
            ),
        ]
    )


def _step_2_pain():
    return dbc.Form(
        [
            dbc.Label("Dolor cervical (0–10)"),
            dcc.Slider(id="q-pain-neck", min=0, max=10, step=1, value=0, marks=None, tooltip={"placement": "bottom"}),
            html.Div(className="mb-2"),
            dbc.Label("Dolor dorsal/torácico (0–10)"),
            dcc.Slider(id="q-pain-thor", min=0, max=10, step=1, value=0, marks=None, tooltip={"placement": "bottom"}),
            html.Div(className="mb-2"),
            dbc.Label("Dolor lumbar (0–10)"),
            dcc.Slider(id="q-pain-lum", min=0, max=10, step=1, value=0, marks=None, tooltip={"placement": "bottom"}),
            html.Div(className="mb-2"),
            dbc.Label("Hormigueo/neurológico (0–10)"),
            dcc.Slider(id="q-tingle", min=0, max=10, step=1, value=0, marks=None, tooltip={"placement": "bottom"}),
            html.Div(className="mb-2"),
            dbc.Label("Rigidez matutina (0–10)"),
            dcc.Slider(id="q-stiffness", min=0, max=10, step=1, value=0, marks=None, tooltip={"placement": "bottom"}),
        ]
    )


def _step_3_self_eval():
    return dbc.Form(
        [
            dbc.Checklist(
                id="q-self-checks",
                options=[
                    {"label": "Me encorvo al trabajar/entrenar", "value": "slouch"},
                    {"label": "Siento asimetría (cargo más un lado)", "value": "asymmetry"},
                    {"label": "Termino el día con dolor/carga", "value": "endday_pain"},
                ],
                value=[],
                switch=True,
                className="mb-2",
            ),
            dbc.Label("Comentario (opcional)"),
            dbc.Textarea(id="q-self-notes", placeholder="Ej: siento la zona lumbar cargada después de overhead", rows=3),
        ]
    )


def _step_4_baseline():
    return html.Div(
        [
            dbc.Alert(
                "Baseline recomendado: mejora calibración y detección de compensaciones. "
                "Puedes hacerlo ahora o después; no bloquea Monitorización.",
                color="info",
                className="mb-2",
            ),
            dbc.Label("¿Quieres realizar baseline ahora?"),
            dcc.RadioItems(
                id="q-baseline-choice",
                options=[
                    {"label": "Ahora (recomendado)", "value": "now"},
                    {"label": "Más tarde", "value": "later"},
                ],
                value="later",
                labelStyle={"display": "block"},
                className="mb-2",
            ),
            dbc.Label("Nota baseline (opcional)"),
            dbc.Textarea(id="q-baseline-notes", rows=2, placeholder="Ej: hoy me siento rígido / hice movilidad antes"),
            html.Hr(),
            html.Div(
                [
                    dbc.Button(
                        "Iniciar baseline",
                        id="q-baseline-start",
                        color="primary",
                        style={"backgroundColor": "var(--c-accent)", "border": "none"},
                        className="me-2",
                    ),
                    dbc.Button("Detener y guardar", id="q-baseline-stop", color="success", className="me-2"),
                    dbc.Button("Reset SIM", id="q-baseline-reset-sim", outline=True),
                ],
                className="d-flex flex-wrap gap-2",
            ),
            dbc.Alert(id="q-baseline-status", is_open=False, color="info", style={"marginTop": "10px", "fontSize": "12px"}),
            html.Div(id="q-baseline-metrics-preview", style={"marginTop": "10px"}),
        ]
    )


def _step_5_daily():
    return html.Div(
        [
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div("Datos automáticos del sensor (hoy)", style=TITLE_STYLE),
                        html.Div(
                            "Se rellena desde daily_summary. Si hoy no has grabado, aparecerá en 0.",
                            style={**MUTED, "fontSize": "12px", "marginBottom": "10px"},
                        ),
                        html.Div(
                            id="q-auto-sensor-block",
                            style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                            children=[
                                _kv("Rojo Torácico (s)", "—"),
                                _kv("Rojo Lumbar (s)", "—"),
                                _kv("Compensación promedio", "—"),
                                _kv("Compensación pico", "—"),
                                _kv("Alertas (count)", "—"),
                                _kv("Risk Index (max)", "—"),
                            ],
                        ),
                        dbc.Alert(id="q-auto-sensor-note", is_open=False, color="info", style={"marginTop": "10px", "fontSize": "12px"}),
                    ]
                ),
                style={**PANEL_STYLE, "marginBottom": "10px"},
            ),
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Div("Daily check-in + objetivos", style=TITLE_STYLE),
                        dbc.Label("Fatiga (0–10)"),
                        dcc.Slider(id="q-fatigue", min=0, max=10, step=1, value=3, marks=None, tooltip={"placement": "bottom"}),
                        html.Div(className="mb-2"),
                        dbc.Label("Sueño (0–10)"),
                        dcc.Slider(id="q-sleep", min=0, max=10, step=1, value=6, marks=None, tooltip={"placement": "bottom"}),
                        html.Div(className="mb-2"),
                        dbc.Label("Objetivo principal del día"),
                        dbc.Input(id="q-goal", type="text", placeholder="Ej: técnica overhead / evitar dolor lumbar", className="mb-2"),
                        dbc.Label("Tipo de sesión"),
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
                        ),
                    ]
                ),
                style=PANEL_STYLE,
            ),
        ]
    )


# -------------------------
# Layout
# -------------------------
def layout(reset_key=None):
    return html.Div(
        className="surface",
        key=f"q{reset_key}",
        children=[
            # stores
            dcc.Store(id="q-wizard-store", storage_type="memory"),
            dcc.Store(id="q-wizard-msg", storage_type="memory"),
            dcc.Store(
                id="q-baseline-rec",
                storage_type="memory",
                data={"is_recording": False, "sensor_session_id": None, "last_ts_ms": 0, "start_iso": None, "n_raw": 0},
            ),
            dcc.Interval(id="q-baseline-interval", interval=200, n_intervals=0, disabled=True),

            html.Div([html.H2("Cuestionario — Wizard (5 pasos)", className="mb-1")], className="mb-3"),

            dbc.Row(
                [
                    # Sidebar
                    dbc.Col(
                        [
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.Div("Estado del wizard", style=TITLE_STYLE),
                                        html.Div(id="q-step-label", className="mb-2", style={"fontWeight": 700}),
                                        dbc.Progress(id="q-step-progress", value=20, striped=True, animated=True),
                                        html.Hr(),
                                        dbc.Alert(id="q-baseline-banner", is_open=False, color="info", style={"fontSize": "12px"}),
                                        html.Div(
                                            [
                                                dbc.Button(
                                                    "Ir a Monitorización",
                                                    id="q-cta-monitor",
                                                    color="primary",
                                                    style={"backgroundColor": "var(--c-accent)", "border": "none"},
                                                    className="me-2",
                                                ),
                                                dbc.Button("Rutina recomendada", id="q-cta-routines", outline=True),
                                            ],
                                            className="d-flex flex-wrap gap-2 mt-2",
                                        ),
                                        html.Div(id="q-final-summary", className="mt-3"),
                                    ]
                                ),
                                style={**PANEL_STYLE, "marginBottom": "16px"},
                            ),
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.Div("Consejos rápidos", style=TITLE_STYLE),
                                        html.Ul(
                                            [
                                                html.Li("Responde con calma: 2–3 min."),
                                                html.Li("Si tienes dolor alto, reduce intensidad ese día."),
                                                html.Li("El Baseline mejora la precisión del sensor (recomendado)."),
                                            ],
                                            className="mb-0",
                                        ),
                                    ]
                                ),
                                style=PANEL_STYLE,
                            ),
                        ],
                        xs=12,
                        md=4,
                        className="mb-4 mb-md-0",
                    ),

                    # Main
                    dbc.Col(
                        [
                            dbc.Card(
                                dbc.CardBody(
                                    [
                                        html.Div("Paso actual", style=TITLE_STYLE),

                                        # ✅ pasos siempre presentes (evita errores de Inputs/States inexistentes)
                                        html.Div(id="q-step-1", children=_step_1_profile()),
                                        html.Div(id="q-step-2", children=_step_2_pain()),
                                        html.Div(id="q-step-3", children=_step_3_self_eval()),
                                        html.Div(id="q-step-4", children=_step_4_baseline()),
                                        html.Div(id="q-step-5", children=_step_5_daily()),

                                        html.Hr(),
                                        html.Div(
                                            [
                                                dbc.Button("Atrás", id="q-back", outline=True, className="me-2"),
                                                dbc.Button("Guardar y salir", id="q-save-exit", outline=True, className="me-auto"),
                                                dbc.Button(
                                                    "Siguiente",
                                                    id="q-next",
                                                    color="primary",
                                                    style={"backgroundColor": "var(--c-accent)", "border": "none"},
                                                    className="me-2",
                                                ),
                                                dbc.Button("Finalizar", id="q-finish", color="success"),
                                            ],
                                            className="d-flex align-items-center flex-wrap gap-2",
                                        ),
                                        dbc.Alert(id="q-feedback", is_open=False, color="info", style={"marginTop": "12px", "fontSize": "12px"}),
                                    ]
                                ),
                                style=PANEL_STYLE,
                            ),
                        ],
                        xs=12,
                        md=8,
                    ),
                ],
                className="g-3",
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
            Output("q-step-label", "children"),
            Output("q-step-progress", "value"),
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
        progress = int((step / 5.0) * 100)
        return sty(1), sty(2), sty(3), sty(4), sty(5), label, progress, step <= 1, step >= 5, step != 5

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

        user_id = resolve_user_id(user_id=(session_user or {}).get("id"), email=(session_user or {}).get("email"))
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

    # Banner baseline recomendado (si no hay baseline)
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

        try:
            b = get_latest_baseline(user_id=user_id)
        except Exception:
            b = None

        if not b:
            return "Baseline recomendado: mejora precisión. Ve al paso 4 para completarlo (3 min).", True, "info"

        ts = b.get("created_at") or "—"
        return f"Baseline detectado ✓ (último: {ts}).", True, "success"

    # -------------------------
    # PASO 4 — Baseline control (start/stop + flush RAW a DB)
    # -------------------------
    @app.callback(
        [
            Output("q-baseline-rec", "data"),
            Output("q-baseline-interval", "disabled"),
            Output("q-baseline-status", "children"),
            Output("q-baseline-status", "is_open"),
            Output("q-baseline-status", "color"),
            Output("q-baseline-metrics-preview", "children"),
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
        rec = rec or {"is_recording": False, "sensor_session_id": None, "last_ts_ms": 0, "start_iso": None, "n_raw": 0}

        user_id = resolve_user_id(user_id=(session_user or {}).get("id"), email=(session_user or {}).get("email"))
        if not user_id:
            return rec, True, "Inicia sesión para grabar baseline.", True, "warning", no_update

        if trig == "q-baseline-reset-sim":
            try:
                SIM.reset()
            except Exception:
                pass
            rec = {"is_recording": False, "sensor_session_id": None, "last_ts_ms": 0, "start_iso": None, "n_raw": 0}
            return rec, True, "SIM reseteado. Listo para grabar baseline.", True, "info", no_update

        if trig == "q-baseline-start":
            if rec.get("is_recording"):
                return rec, False, "Ya estás grabando baseline…", True, "info", no_update

            try:
                SIM.set_context(mode="desk", sport="gym")
            except Exception:
                pass

            # TODO BLE real: reemplazar SIM por stream BLE y mantener pipeline
            ssid = start_sensor_session(user_id=int(user_id), kind="baseline", mode="desk", sport="gym")

            rec = {
                "is_recording": True,
                "sensor_session_id": ssid,
                "last_ts_ms": 0,
                "start_iso": datetime.now().isoformat(timespec="seconds"),
                "n_raw": 0,
            }

            # marcar paso baseline iniciado
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
                        },
                    )
            except Exception:
                pass

            return rec, False, "Grabación baseline iniciada ✓ (SIM)", True, "success", no_update

        if trig == "q-baseline-stop":
            if not rec.get("is_recording"):
                return rec, True, "No hay grabación activa.", True, "warning", no_update

            ssid = rec.get("sensor_session_id")

            # cerrar sesión
            try:
                if ssid:
                    end_sensor_session(session_id=int(ssid))
            except Exception:
                pass

            # calcular baseline desde última ventana
            try:
                win = SIM.get_window(seconds=60)
            except Exception:
                win = {}

            baseline = _baseline_from_window(win)

            # session_summary para baseline
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

            # baseline_tests
            baseline_id = None
            try:
                baseline_id = create_baseline_test(
                    user_id=int(user_id),
                    sensor_session_id=int(ssid) if ssid else None,
                    baseline=baseline,
                )
            except Exception:
                baseline_id = None

            # ✅ baseline cuenta como sesión del día
            try:
                recompute_daily_summary(user_id=int(user_id), day=date.today())
            except Exception:
                pass

            # marcar baseline completado
            try:
                if wizard_store and wizard_store.get("session_id"):
                    save_questionnaire_step(
                        session_id=int(wizard_store["session_id"]),
                        step_key="baseline",
                        step_payload={
                            "choice": baseline_choice or "later",
                            "notes": baseline_notes or "",
                            "recording_started_at": rec.get("start_iso"),
                            "completed": True,
                            "baseline_id": baseline_id,
                            "sensor_session_id": ssid,
                        },
                    )
            except Exception:
                pass

            rec = {"is_recording": False, "sensor_session_id": None, "last_ts_ms": 0, "start_iso": None, "n_raw": rec.get("n_raw", 0)}

            preview = dbc.Alert(
                [
                    html.Div("Baseline guardado ✓", style={"fontWeight": 800}),
                    html.Div(f"ROM Thor pitch: {baseline['rom']['thor_pitch']:.1f}° | Lum pitch: {baseline['rom']['lum_pitch']:.1f}°"),
                    html.Div(f"Comp avg: {baseline['comp']['comp_avg']:.1f} | Comp peak: {baseline['comp']['comp_peak']:.1f}"),
                    html.Div(f"Stability (lum pitch std): {baseline['stability']['lum_pitch_std']:.2f}"),
                ],
                color="success",
                className="mb-0",
            )
            return rec, True, "Grabación detenida y baseline guardado en DB ✓", True, "success", preview

        raise PreventUpdate

    # Interval: flush RAW mientras está grabando baseline
    @app.callback(
        Output("q-baseline-rec", "data", allow_duplicate=True),
        Input("q-baseline-interval", "n_intervals"),
        State("q-baseline-rec", "data"),
        prevent_initial_call=True,
    )
    def baseline_tick(_n, rec):
        rec = rec or {}
        if not rec.get("is_recording"):
            raise PreventUpdate

        ssid = rec.get("sensor_session_id")
        if not ssid:
            raise PreventUpdate

        last_ts = int(rec.get("last_ts_ms") or 0)

        try:
            new_samples = SIM.get_samples_since(last_ts)
        except Exception:
            new_samples = []

        if not new_samples:
            raise PreventUpdate

        rows = []
        max_ts = last_ts
        for s in new_samples:
            ts_ms = int(s["ts_ms"])
            max_ts = max(max_ts, ts_ms)
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

        insert_sensor_samples_raw_batch(session_id=int(ssid), rows=rows)

        rec["last_ts_ms"] = int(max_ts)
        rec["n_raw"] = int(rec.get("n_raw") or 0) + len(rows)
        return rec

    # Activar/desactivar interval según estado de grabación
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
        [
            Output("q-baseline-status", "children", allow_duplicate=True),
            Output("q-baseline-status", "is_open", allow_duplicate=True),
            Output("q-baseline-status", "color", allow_duplicate=True),
        ],
        Input("q-baseline-rec", "data"),
        prevent_initial_call=True,
    )
    def baseline_status(rec):
        rec = rec or {}
        if not rec.get("is_recording"):
            raise PreventUpdate
        return f"Grabando… muestras RAW guardadas: {int(rec.get('n_raw') or 0)}", True, "info"

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
        if step != 5:
            return no_update, no_update, no_update, no_update

        if not user_id:
            block = [
                _kv("Rojo Torácico (s)", "—"),
                _kv("Rojo Lumbar (s)", "—"),
                _kv("Compensación promedio", "—"),
                _kv("Compensación pico", "—"),
                _kv("Alertas (count)", "—"),
                _kv("Risk Index (max)", "—"),
            ]
            return block, "Inicia sesión para ver los datos automáticos del sensor.", True, "warning"

        today_date = date.today()
        try:
            d = get_daily_summary(user_id=int(user_id), day=today_date)
        except Exception:
            d = None

        if not d:
            block = [
                _kv("Rojo Torácico (s)", "0.0"),
                _kv("Rojo Lumbar (s)", "0.0"),
                _kv("Compensación promedio", "0.0"),
                _kv("Compensación pico", "0.0"),
                _kv("Alertas (count)", "0"),
                _kv("Risk Index (max)", "0.0"),
            ]
            return block, "Hoy no hay datos (daily_summary vacío).", True, "info"

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

        block = [
            _kv("Rojo Torácico (s)", f"{thor:.1f}", tone if thor > 0 else "neutral"),
            _kv("Rojo Lumbar (s)", f"{lum:.1f}", tone if lum > 0 else "neutral"),
            _kv("Compensación promedio", f"{comp_avg:.1f}", tone if comp_avg >= 60 else "neutral"),
            _kv("Compensación pico", f"{comp_peak:.1f}", tone if comp_peak >= 60 else "neutral"),
            _kv("Alertas (count)", f"{alerts_count:d}", "warn" if alerts_count > 0 else "neutral"),
            _kv("Risk Index (max)", f"{risk_max:.1f}", tone),
        ]
        return block, f"Datos automáticos cargados para {today_date.isoformat()}.", True, "success"

    # Wizard control: back/next/save-exit/finish
    @app.callback(
        [
            Output("q-wizard-store", "data", allow_duplicate=True),
            Output("q-feedback", "children", allow_duplicate=True),
            Output("q-feedback", "is_open", allow_duplicate=True),
            Output("q-feedback", "color", allow_duplicate=True),
            Output("q-final-summary", "children", allow_duplicate=True),
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
        ],
        prevent_initial_call=True,
    )
    def wizard_control(_nb, _nn, _nse, _nf, store, session_user, *vals):
        trig = dash.ctx.triggered_id
        store = store or {}

        user_id = resolve_user_id(user_id=(session_user or {}).get("id"), email=(session_user or {}).get("email"))
        if not user_id:
            return store, "Inicia sesión para continuar.", True, "warning", no_update

        session_id = store.get("session_id")
        step = int(store.get("step") or 1)

        (
            age, height, weight, sitting_hours, desk_job, screen_height,
            pain_neck, pain_thor, pain_lum, tingle, stiffness,
            self_checks, self_notes,
            baseline_choice, baseline_notes,
            fatigue, sleep, goal, session_type
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
                        "neck": pain_neck, "thor": pain_thor, "lum": pain_lum, "tingle": tingle, "stiffness": stiffness
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
                    save_questionnaire_step(session_id=int(session_id), step_key="baseline", step_payload={
                        "choice": baseline_choice or "later",
                        "notes": baseline_notes or ""
                    })
                elif step == 5:
                    save_questionnaire_step(session_id=int(session_id), step_key="daily", step_payload={
                        "fatigue": fatigue, "sleep": sleep, "goal": goal or "",
                        "session_type": session_type or "normal", "day": date.today().isoformat()
                    })
            except Exception:
                pass

        if trig in ("q-back", "q-next", "q-save-exit", "q-finish"):
            save_current_step()

        if trig == "q-back":
            store["step"] = max(1, step - 1)
            return store, "Guardado ✓", True, "success", no_update

        if trig == "q-next":
            store["step"] = min(5, step + 1)
            return store, "Guardado ✓", True, "success", no_update

        if trig == "q-save-exit":
            return store, "Guardado ✓ (puedes salir).", True, "info", no_update

        if trig == "q-finish":
            try:
                daily = get_daily_summary(user_id=int(user_id), day=date.today())
            except Exception:
                daily = None

            payload_all = {
                "profile": {"age": age, "height_cm": height, "weight_kg": weight, "sitting_hours": sitting_hours,
                            "desk_job": desk_job, "screen_height": screen_height},
                "pain": {"neck": pain_neck, "thor": pain_thor, "lum": pain_lum, "tingle": tingle, "stiffness": stiffness},
                "self_eval": {"slouch": "slouch" in (self_checks or []), "asymmetry": "asymmetry" in (self_checks or []),
                             "endday_pain": "endday_pain" in (self_checks or []), "notes": self_notes or ""},
                "baseline": {"choice": baseline_choice or "later", "notes": baseline_notes or ""},
                "daily": {"fatigue": fatigue, "sleep": sleep, "goal": goal or "", "session_type": session_type or "normal"},
            }

            risk = _risk_from_inputs(payload_all, daily=daily)

            # guardar thresholds por usuario
            try:
                thresholds_payload = _build_thresholds(payload_all["profile"], payload_all["pain"])
                upsert_user_posture_settings(user_id=int(user_id), thresholds=thresholds_payload)
            except Exception:
                pass

            # baseline status
            try:
                b = get_latest_baseline(user_id=int(user_id))
            except Exception:
                b = None
            has_baseline = bool(b)

            recommendation = {
                "risk_index": risk,
                "has_baseline": has_baseline,
                "cta": {"monitor": True, "routines": True},
                "note": "Baseline recomendado para mejorar precisión." if not has_baseline else "Baseline OK.",
            }

            try:
                if session_id:
                    complete_questionnaire_session(session_id=int(session_id), risk_index=risk, recommendation=recommendation)
            except Exception:
                pass

            tone = "success" if risk < 40 else ("warning" if risk < 70 else "danger")
            summary = dbc.Alert(
                [
                    html.Div(f"Risk Index estimado: {risk:.1f}/100", style={"fontWeight": 800}),
                    html.Div("Baseline: " + ("OK ✓" if has_baseline else "pendiente (recomendado)")),
                    html.Div("Umbrales personalizados guardados ✓"),
                ],
                color=tone,
                className="mb-0",
            )
            return store, "Cuestionario finalizado ✓", True, "success", summary

        raise PreventUpdate

    # CTAs: navegar por router
    @app.callback(
        Output("router", "data", allow_duplicate=True),
        [Input("q-cta-monitor", "n_clicks"), Input("q-cta-routines", "n_clicks")],
        State("session-user", "data"),
        prevent_initial_call=True,
    )
    def go_to_pages(n_m, n_r, session_user):
        trig = dash.ctx.triggered_id
        if not session_user or (session_user.get("role") or "").lower() != "atleta":
            raise PreventUpdate
        if trig == "q-cta-monitor" and (n_m or 0) > 0:
            return {"view": "monitor"}
        if trig == "q-cta-routines" and (n_r or 0) > 0:
            return {"view": "routines"}
        raise PreventUpdate