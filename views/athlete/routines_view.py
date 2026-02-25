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

from __future__ import annotations

from dash import html, dcc, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from imu_realtime_sim import SIM

from db import (
    resolve_user_id,
    get_daily_summary,
    get_recommended_routine_today,
    get_routine_week_summary,
)

# -------------------------
# Estilos UI (alineado con tu MVP)
# -------------------------

PANEL_STYLE = {
    "border": "1px solid #e2e8f0",
    "background": "#ffffff",
    "borderRadius": "14px",
    "boxShadow": "0 4px 14px rgba(15,23,42,.06)",
}

TITLE_STYLE = {
    "fontWeight": 600,
    "color": "#334155",
    "marginBottom": "8px",
}

MUTED_STYLE = {"color": "#64748b"}

CHIP_BASE = {
    "display": "inline-block",
    "padding": "4px 10px",
    "borderRadius": "999px",
    "fontWeight": 800,
    "fontSize": "12px",
    "border": "1px solid rgba(15,23,42,.15)",
}

def _zone_chip(zone: str) -> html.Span:
    z = (zone or "green").lower()
    if z == "red":
        return html.Span("ROJO", style={**CHIP_BASE, "background": "rgba(239,68,68,.16)", "color": "#b91c1c"})
    if z == "yellow":
        return html.Span("AMARILLO", style={**CHIP_BASE, "background": "rgba(245,158,11,.18)", "color": "#92400e"})
    return html.Span("VERDE", style={**CHIP_BASE, "background": "rgba(34,197,94,.14)", "color": "#166534"})


def _empty_fig(title: str):
    return {
        "data": [],
        "layout": {
            "title": {"text": title},
            "paper_bgcolor": "#ffffff",
            "plot_bgcolor": "#ffffff",
            "font": {"color": "#0f172a"},
            "margin": {"l": 40, "r": 20, "t": 45, "b": 40},
            "xaxis": {"gridcolor": "rgba(15,23,42,0.08)"},
            "yaxis": {"gridcolor": "rgba(15,23,42,0.08)"},
            "legend": {"orientation": "h"},
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
            "title": {"text": title},
            "paper_bgcolor": "#ffffff",
            "plot_bgcolor": "#ffffff",
            "font": {"color": "#0f172a"},
            "margin": {"l": 40, "r": 20, "t": 45, "b": 40},
            "xaxis": {"gridcolor": "rgba(15,23,42,0.08)"},
            "yaxis": {"gridcolor": "rgba(15,23,42,0.08)"},
            "legend": {"orientation": "h"},
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
    return html.Div(
        className="surface",
        children=[
            # Stores + interval RUN
            dcc.Store(id="r-plan-store"),
            dcc.Store(id="r-run-store"),
            dcc.Interval(id="r-run-interval", interval=200, disabled=True),

            # Encabezado
            html.Div(
                [
                    html.H2("Rutinas", className="mb-1"),
                    html.Div(
                        "Rutina recomendada hoy + ejecución en vivo (RUN).",
                        className="muted",
                    ),
                ],
                className="mb-4",
            ),

            # Bloque superior: recomendación + RUN
            dbc.Row(
                [
                    # Rutina recomendada hoy
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div("Rutina recomendada hoy", style=TITLE_STYLE),
                                    html.Div(id="r-recommend-meta", className="mb-2"),
                                    html.Div(id="r-recommend-list"),
                                    html.Hr(),
                                    dbc.Button("Empezar (RUN)", id="r-start-run-btn", color="primary", className="me-2"),
                                    dbc.Button("Parar", id="r-stop-run-btn", color="secondary", outline=True),
                                    html.Div(id="r-run-feedback", className="mt-2", style=MUTED_STYLE),
                                    html.Div(
                                        "Nota: en PASO 3 se guardará la sesión (routine_sessions + sets + sensor_session kind='routine').",
                                        className="muted mt-2",
                                    ),
                                ]
                            ),
                            style={**PANEL_STYLE, "marginBottom": "16px"},
                        ),
                        xs=12,
                        md=5,
                        className="mb-3",
                    ),

                    # Panel RUN
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div("Ejecución (RUN)", style=TITLE_STYLE),
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Div("Ejercicio", className="muted"),
                                                    html.Div(id="r-ex-name", className="fw-semibold"),
                                                ],
                                                style={"flex": 2},
                                            ),
                                            html.Div(
                                                [
                                                    html.Div("Reps", className="muted"),
                                                    html.Div(id="r-ex-reps", className="fw-semibold"),
                                                ],
                                                style={"flex": 1},
                                            ),
                                            html.Div(
                                                [
                                                    html.Div("Score", className="muted"),
                                                    html.Div(id="r-ex-score", className="fw-semibold"),
                                                ],
                                                style={"flex": 1},
                                            ),
                                        ],
                                        style={"display": "flex", "gap": "12px", "alignItems": "center"},
                                        className="mb-2",
                                    ),
                                    html.Div(
                                        [
                                            html.Div(["Torácico: ", html.Span(id="r-thor-chip")]),
                                            html.Div(["Lumbar: ", html.Span(id="r-lum-chip")]),
                                            html.Div(["Comp: ", html.Span(id="r-comp-val")]),
                                        ],
                                        style={"display": "flex", "gap": "14px", "flexWrap": "wrap"},
                                        className="mb-2",
                                    ),
                                    dcc.Graph(id="r-run-graph", figure=_empty_fig("IMU (RUN)")),
                                ]
                            ),
                            style={**PANEL_STYLE, "marginBottom": "16px"},
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
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div("Resumen de la semana", style=TITLE_STYLE),
                                    html.Div(id="r-week-summary"),
                                    html.Hr(),
                                    html.Ul(
                                        [
                                            html.Li("Número de días planificados."),
                                            html.Li("Sesiones de fuerza, accesorios y movilidad."),
                                            html.Li("Distribución aproximada por grupos musculares."),
                                        ],
                                        className="mb-2",
                                    ),
                                    html.Div(
                                        "Cuando el plan esté configurado, aquí aparecerá un resumen de tu carga semanal.",
                                        className="muted",
                                    ),
                                ]
                            ),
                            style=PANEL_STYLE,
                        ),
                        xs=12,
                        md=4,
                        className="mb-4 mb-md-0",
                    ),

                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div("Calendario semanal", style=TITLE_STYLE),
                                    html.Div(
                                        "Este espacio está preparado para mostrar un calendario interactivo con tus sesiones por día. "
                                        "Se integrará con el plan de hoy y con la monitorización para tener todo alineado.",
                                        className="mb-2",
                                    ),
                                    html.Div(
                                        "Puedes reutilizar aquí tu vista de semana combinada de atleta cuando esté lista.",
                                        className="muted",
                                    ),
                                ]
                            ),
                            style=PANEL_STYLE,
                        ),
                        xs=12,
                        md=5,
                        className="mb-4 mb-md-0",
                    ),

                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div("Notas del entrenador", style=TITLE_STYLE),
                                    html.P(
                                        "Aquí se podrán mostrar indicaciones específicas por bloque de trabajo:",
                                        className="mb-2",
                                    ),
                                    html.Ul(
                                        [
                                            html.Li("Puntos clave de técnica a revisar."),
                                            html.Li("Rangos de RPE objetivo para la semana."),
                                            html.Li("Advertencias si vienes de lesión o sobrecarga."),
                                        ],
                                        className="mb-2 muted",
                                    ),
                                    html.Div(
                                        "En versiones futuras esta sección se conectará con mensajes del entrenador y con tus notas diarias.",
                                        className="muted",
                                    ),
                                ]
                            ),
                            style=PANEL_STYLE,
                        ),
                        xs=12,
                        md=3,
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
            meta = html.Div("Inicia sesión para ver tu rutina recomendada.", className="muted")
            return {}, meta, html.Div("—", className="muted"), html.Div("—", className="muted")

        plan = get_recommended_routine_today(user_id=user_id)
        daily = get_daily_summary(user_id=user_id) or {}
        week = get_routine_week_summary(user_id=user_id)

        meta = html.Div(
            [
                html.Div(plan.get("title", "Rutina recomendada"), className="fw-semibold"),
                html.Div(
                    f"Rojo T: {int(float(daily.get('thor_red_s') or 0))}s · "
                    f"Rojo L: {int(float(daily.get('lum_red_s') or 0))}s · "
                    f"Comp: {round(float(daily.get('comp_avg') or 0.0), 1)} · "
                    f"Focus: {plan.get('focus', 'general')}",
                    className="muted",
                ),
            ]
        )

        exs = plan.get("exercises") or []
        if not exs:
            ex_list = html.Div("— (sin ejercicios)", className="muted")
        else:
            ex_list = html.Ul(
                [html.Li(f"{e.get('name')} — {e.get('sets', 1)}x{e.get('reps', '')}") for e in exs],
                className="mb-0",
            )

        week_ui = html.Div(
            [
                html.Div(
                    f"Semana {week.get('start_day')} → {week.get('end_day')}",
                    className="fw-semibold",
                ),
                html.Div(
                    f"Días con rutina: {week.get('planned_days', 0)} · "
                    f"Sesiones: {week.get('sessions_count', 0)} · "
                    f"Score medio: {round(float(week.get('avg_score') or 0.0), 1)}",
                    className="muted",
                ),
            ]
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
            f"{round(float(comp_last), 1)}",
            rs,
        )