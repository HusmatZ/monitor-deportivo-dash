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
# - Captura RAW “tipo 2-IMUs” SIN duplicar usando ventana del simulador (wrapper equivalente a get_samples_since)
# - Flush en lote a axisfit.db (batch) para 50 Hz (aprox, sin lag)
# - Cálculo en vivo: tiempo rojo T/L + comp (sum/avg/peak) + alerts con streak
# - STOP: session_summary + daily_summary + Risk Index v2
# - PASO 9/10: 2 semáforos (Torácica/Lumbar) + Comp + Rojo T/L (sin tocar IDs viejos hasta el PASO 11)
# - PASO 11: elimina definitivamente bpm-output (demo) y lo reemplaza por “Compensación”
# - PASO 12: renombra ecg-graph -> imu-graph
# - PASO 13: selector Deporte = Gym/CrossFit (acepta values viejos: general/strength/etc.)
#
# ⚠️ Nota importante:
# Tu imu_realtime_sim.py actual NO trae get_samples_since() ni campos T_/L_/zones/comp.
# Para no bloquear el MVP, aquí se implementa un wrapper que:
# - toma la ventana (t/pitch/roll/yaw/score/bad) y genera timestamps absolutos por sesión
# - “duplica” datos a 2 IMUs (T y L) con ligeras variaciones
# - calcula thor_zone/lum_zone/comp_index de forma simple
# Cuando tu simulador ya exponga get_samples_since(last_ts_ms) real, puedes reemplazar el wrapper.

from dash import html, dcc, Input, Output, State, ctx
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
)

# ✅ Export helpers (PASO 2/3)
from export_utils import make_filename, rows_to_csv_bytes

BLACK_TEXT = {"color": "#e2e8f0"}
BLACK_MUTED = {"color": "rgba(226,232,240,.75)"}

LEFT_W = "250px"
RIGHT_BOX_W = "459px"  # ✅ Cada cuadro (columna derecha) debe medir 459px
RIGHT_INNER_GAP_PX = 12

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
    style = {
        "display": "flex",
        "gap": "8px",
        "alignItems": "center",
        "padding": "6px 10px",
        "borderRadius": "999px",
        "background": tone_map.get(tone, tone_map["neutral"]),
        "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
        "whiteSpace": "nowrap",
    }
    if full:
        style.update({"width": "100%", "justifyContent": "space-between", "whiteSpace": "normal"})

    return html.Div(
        style=style,
        children=[
            html.Span(label, style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
            html.Span(value, style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 700}),
        ],
    )


def _traffic_light_dynamic(score: float):
    g = 1.0 if score >= 80 else 0.25
    y = 1.0 if 50 <= score < 80 else 0.25
    r = 1.0 if score < 50 else 0.25

    def dot(color, alpha):
        return html.Div(
            style={
                "width": "10px",
                "height": "10px",
                "borderRadius": "999px",
                "background": color,
                "opacity": alpha,
                "boxShadow": "0 0 0 1px rgba(255,255,255,.10)",
            }
        )

    return html.Div(
        style={"display": "flex", "gap": "6px", "alignItems": "center"},
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
                "width": "10px",
                "height": "10px",
                "borderRadius": "999px",
                "background": color,
                "opacity": alpha,
                "boxShadow": "0 0 0 1px rgba(255,255,255,.10)",
            }
        )

    return html.Div(
        style={"display": "flex", "gap": "6px", "alignItems": "center"},
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
            "title": {"text": title},
            "paper_bgcolor": "#0b1220",
            "plot_bgcolor": "#0b1220",
            "font": {"color": "#e2e8f0"},
            "margin": {"l": 40, "r": 20, "t": 40, "b": 35},
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


# =============================
# PASO 5 — Thresholds por usuario (desde cuestionario)
# =============================
def _load_user_thresholds_for_mode(*, user_id: int, mode: str) -> dict:
    """Devuelve thresholds activos (thor/lum) para el modo actual.

    - Si el usuario tiene user_posture_settings.thresholds_json, lo usa.
    - Si no, usa DEFAULT_THRESHOLDS (genéricos).
    """
    mode = (mode or "desk").strip().lower()
    if mode not in ("desk", "train"):
        mode = "desk"

    fallback = DEFAULT_THRESHOLDS.get(mode, DEFAULT_THRESHOLDS["desk"])
    thr_thor = dict((fallback.get("thor") or {}))
    thr_lum = dict((fallback.get("lum") or {}))

    try:
        s = get_user_posture_settings(user_id=int(user_id))
        if s and isinstance(s.get("thresholds"), dict):
            root = s["thresholds"]
            # soporta: {"thresholds": {desk/train...}, "version": ...}  o directamente {desk/train...}
            t = root.get("thresholds") if isinstance(root.get("thresholds"), dict) else root
            mode_block = (t or {}).get(mode) or {}
            if isinstance(mode_block.get("thor"), dict):
                thr_thor.update(mode_block["thor"])
            if isinstance(mode_block.get("lum"), dict):
                thr_lum.update(mode_block["lum"])
    except Exception:
        pass

    return {"thor": thr_thor, "lum": thr_lum}

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


# =============================
# Layout
# =============================
def layout():
    card_style = {
        "width": "100%",
        "background": "#0b1220",
        "borderRadius": "12px",
        "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.04)",
        "padding": "12px",
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
        "gap": "12px",
    }

    right_col_style = {
        "width": RIGHT_BOX_W,
        "minWidth": RIGHT_BOX_W,
        "flex": f"0 0 {RIGHT_BOX_W}",
        "display": "flex",
        "flexDirection": "column",
        "gap": "12px",
    }

    right_container_style = {
        "display": "flex",
        "gap": f"{RIGHT_INNER_GAP_PX}px",
        "alignItems": "flex-start",
        "flexWrap": "wrap",
    }

    return html.Div(
        className="surface",
        children=[
            dcc.Store(id="session-history-store", storage_type="local"),
            dcc.Store(id="active-session-store", storage_type="local"),
            dcc.Store(id="calibration-store", storage_type="local"),
            dcc.Store(id="sim-state-store", data={"on": True, "reset_seq": 0}, storage_type="memory"),
            # ✅ recorder-store SOLO se escribe en recorder_control
            dcc.Store(id="recorder-store", data={"on": False, "session_id": None, "main_session_id": None}, storage_type="memory"),
            dcc.Download(id="download-monitor"),

            dcc.Interval(id="imu-interval", interval=200, n_intervals=0, disabled=False),

            # Título + menú derecha
            html.Div(
                className="mb-4",
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "12px"},
                children=[
                    html.H2("Monitorizacion de Postura", className="mb-0"),
                    html.Div(
                        style={"display": "flex", "alignItems": "center", "gap": "10px"},
                        children=[
                            dbc.Badge("ON", id="sim-status-badge", color="success", pill=True),
                            dbc.DropdownMenu(
                                id="sim-control-menu",
                                label="Reiniciar inclinación",
                                color="primary",
                                size="sm",
                                toggle_style={"backgroundColor": "var(--c-accent-2)", "border": "none"},
                                children=[
                                    dbc.DropdownMenuItem("Encender simulación", id="sim-on-item", n_clicks=0),
                                    dbc.DropdownMenuItem("Apagar simulación", id="sim-off-item", n_clicks=0),
                                    dbc.DropdownMenuItem(divider=True),
                                    dbc.DropdownMenuItem("Reiniciar inclinación", id="sim-reset-item", n_clicks=0),
                                ],
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
                    "gap": "12px",
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
                                style=card_style,
                                children=[
                                    html.Div(
                                        style={
                                            "display": "flex",
                                            "alignItems": "center",
                                            "justifyContent": "space-between",
                                            "gap": "10px",
                                            "marginBottom": "8px",
                                        },
                                        children=[
                                            html.Div("Estado", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px"}),
                                            html.Div(id="fw-pill", children=_pill("Firmware", "v1.0.3", "neutral")),
                                        ],
                                    ),
                                    html.Div(
                                        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                                        children=[
                                            _pill("Batería", "82%", "ok", full=True),
                                            _pill("Conexión", "BLE Conectado", "ok", full=True),
                                            html.Div(id="calibration-pill", style={"width": "100%"}, children=_pill("Calibración", "No", "warn", full=True)),
                                            html.Div(id="active-session-badge", style={"width": "100%"}, children=_pill("Sesión", "—", "neutral", full=True)),
                                            html.Div(id="recording-pill", style={"width": "100%"}, children=_pill("Registro", "OFF", "neutral", full=True)),
                                        ],
                                    ),
                                ],
                            ),

                            # Controles rápidos
                            html.Div(
                                style=card_style,
                                children=[
                                    html.Div("Controles rápidos", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                    html.Div(
                                        style={"display": "flex", "flexDirection": "column", "gap": "8px"},
                                        children=[
                                            html.Div(
                                                children=[
                                                    html.Div("Presets por modo", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600, "marginBottom": "4px"}),
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
                                            dbc.Switch(id="alerts-switch", label="Alertas", value=True, style={**BLACK_TEXT, "fontSize": "12px"}),

                                            html.Div(
                                                children=[
                                                    html.Div("Sesión del día", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600, "marginBottom": "4px"}),
                                                    dbc.Select(
                                                        id="planned-session",
                                                        options=[
                                                            {"label": "Fuerza · Torso", "value": "Fuerza · Torso"},
                                                            {"label": "Rehab · Espalda", "value": "Rehab · Espalda"},
                                                            {"label": "Oficina · Postura", "value": "Oficina · Postura"},
                                                        ],
                                                        value="Oficina · Postura",
                                                        size="sm",
                                                        style={"width": "100%"},
                                                    ),
                                                ]
                                            ),

                                            # ✅ PASO 13: Deporte Gym/CrossFit (acepta values viejos)
                                            html.Div(
                                                children=[
                                                    html.Div("Deporte", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600, "marginBottom": "4px"}),
                                                    dbc.Select(
                                                        id="sport-select",
                                                        options=[
                                                            {"label": "Gym", "value": "gym"},
                                                            {"label": "CrossFit", "value": "crossfit"},
                                                        ],
                                                        value="gym",
                                                        size="sm",
                                                        style={"width": "100%"},
                                                    ),
                                                ]
                                            ),

                                            # ✅ Botones con el mismo diseño/colores original (primary/secondary)
                                            dbc.ButtonGroup(
                                                [
                                                    dbc.Button("Iniciar registro (50 Hz)", id="start-record-btn", color="primary", size="sm", style={"flex": "1 1 auto"}),
                                                    dbc.Button("Detener", id="stop-record-btn", color="secondary", size="sm", outline=True, style={"flex": "0 0 auto"}),
                                                ],
                                                style={"width": "100%"},
                                            ),

                                            dbc.Alert(
                                                id="recorder-alert",
                                                children="",
                                                is_open=False,
                                                color="info",
                                                style={
                                                    "marginTop": "8px",
                                                    "padding": "8px 10px",
                                                    "fontSize": "12px",
                                                    "background": "rgba(0,0,0,.12)",
                                                    "border": "1px solid rgba(255,255,255,.10)",
                                                    "color": "#e2e8f0",
                                                },
                                            ),

                                            dbc.Button(
                                                "Vincular sesión",
                                                id="link-session-btn",
                                                color="secondary",
                                                size="sm",
                                                style={"width": "100%", "background": "rgba(255,255,255,.10)", "border": "1px solid rgba(255,255,255,.10)", "color": "#e2e8f0"},
                                            ),
                                            # ✅ PASO 2: Exportar histórico (CSV)
                                            dbc.Button(
                                                "Exportar histórico (CSV)",
                                                id="export-history-btn",
                                                color="secondary",
                                                size="sm",
                                                style={"width": "100%", "background": "rgba(255,255,255,.10)", "border": "1px solid rgba(255,255,255,.10)", "color": "#e2e8f0"},
                                            ),
                                            # ✅ PASO 3: Exportar ventana 20s (CSV)
                                            dbc.Button(
                                                "Exportar ventana 20s (CSV)",
                                                id="export-window-btn",
                                                color="secondary",
                                                size="sm",
                                                style={"width": "100%", "background": "rgba(255,255,255,.10)", "border": "1px solid rgba(255,255,255,.10)", "color": "#e2e8f0"},
                                            ),
                                            dbc.Button(
                                                "Recalibración guiada",
                                                id="open-recal-btn",
                                                color="secondary",
                                                size="sm",
                                                style={"width": "100%", "background": "rgba(255,255,255,.10)", "border": "1px solid rgba(255,255,255,.10)", "color": "#e2e8f0"},
                                            ),
                                            html.Div(id="active-session-label", style={**BLACK_MUTED, "fontSize": "12px", "marginTop": "4px"}, children="Sesión activa: —"),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),

                    # ===== COLUMNA DERECHA =====
                    html.Div(
                        style=right_container_style,
                        children=[
                            # ===== COLUMNA 2 =====
                            html.Div(
                                style=right_col_style,
                                children=[
                                    # Espalda visual
                                    html.Div(
                                        style=card_style,
                                        children=[
                                            html.Div("Espalda (visual)", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                            html.Div(
                                                style={
                                                    "height": "200px",
                                                    "borderRadius": "12px",
                                                    "background": "rgba(0,0,0,.15)",
                                                    "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                                                    "display": "flex",
                                                    "alignItems": "center",
                                                    "justifyContent": "space-between",
                                                    "gap": "12px",
                                                    "padding": "10px",
                                                },
                                                children=[
                                                    html.Div(
                                                        style={
                                                            "flex": "1 1 auto",
                                                            "height": "100%",
                                                            "display": "flex",
                                                            "alignItems": "center",
                                                            "justifyContent": "flex-start",
                                                            "paddingLeft": "18px",
                                                        },
                                                        children=[html.Div("↗", id="back-arrow", style={"fontSize": "34px", "color": "rgba(226,232,240,.90)", "transform": "rotate(-10deg)"})],
                                                    ),
                                                    # Cuadro de datos
                                                    html.Div(
                                                        style={
                                                            "width": "220px",
                                                            "minWidth": "220px",
                                                            "display": "flex",
                                                            "flexDirection": "column",
                                                            "gap": "6px",
                                                            "padding": "8px 10px",
                                                            "borderRadius": "12px",
                                                            "background": "rgba(255,255,255,.10)",
                                                            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                                                        },
                                                        children=[
                                                            html.Div(
                                                                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "10px"},
                                                                children=[
                                                                    html.Span("Estado de inclinación", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                    html.Div(id="traffic-light", children=_traffic_light_dynamic(86)),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "10px"},
                                                                children=[
                                                                    html.Span("Postura", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                    html.Span(id="posture-score", children="86", style={**BLACK_TEXT, "fontSize": "13px", "fontWeight": 800}),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                style={"display": "flex", "gap": "10px", "alignItems": "center", "justifyContent": "space-between"},
                                                                children=[
                                                                    html.Span("Tiempo mala post.", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                    html.Span(id="bad-time-metric", children="—", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 800}),
                                                                ],
                                                            ),

                                                            # ✅ PASO 9: nuevas filas (sin romper IDs viejos)
                                                            html.Div(
                                                                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "10px"},
                                                                children=[
                                                                    html.Span("Torácica", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                    html.Div(id="thor-traffic-light", children=_traffic_light_zone("green")),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between", "gap": "10px"},
                                                                children=[
                                                                    html.Span("Lumbar", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                    html.Div(id="lum-traffic-light", children=_traffic_light_zone("green")),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                style={"display": "flex", "gap": "10px", "alignItems": "center", "justifyContent": "space-between"},
                                                                children=[
                                                                    html.Span("Compensación", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                    html.Span(id="comp-output", children="—", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 800}),
                                                                ],
                                                            ),
                                                            html.Div(
                                                                style={"display": "flex", "gap": "10px", "alignItems": "center", "justifyContent": "space-between"},
                                                                children=[
                                                                    html.Span("Rojo T / Rojo L", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 600}),
                                                                    html.Span(
                                                                        children=[
                                                                            html.Span(id="thor-red-output", children="—", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 800}),
                                                                            html.Span(" / ", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 700}),
                                                                            html.Span(id="lum-red-output", children="—", style={**BLACK_TEXT, "fontSize": "12px", "fontWeight": 800}),
                                                                        ]
                                                                    ),
                                                                ],
                                                            ),
                                                        ],
                                                    ),
                                                    html.Div(id="state-dot", style={"display": "none"}),
                                                ],
                                            ),
                                        ],
                                    ),

                                    # Alertas activas
                                    html.Div(
                                        style=card_style,
                                        children=[
                                            html.Div("Alertas activas", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                            html.Ul(
                                                id="alerts-list",
                                                style={"margin": 0, "paddingLeft": "18px", "color": "rgba(226,232,240,.85)", "fontSize": "12px"},
                                                children=[html.Li("— (sin datos aún)")],
                                            ),
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
                                        style=card_style,
                                        children=[
                                            html.Div("Gráficas", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                            html.Div(
                                                style={"display": "flex", "flexDirection": "column", "gap": "12px"},
                                                children=[
                                                    html.Div(
                                                        style={
                                                            "borderRadius": "12px",
                                                            "background": "rgba(0,0,0,.12)",
                                                            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                                                            "padding": "8px",
                                                            "display": "flex",
                                                            "flexDirection": "column",
                                                            "gap": "6px",
                                                        },
                                                        children=[
                                                            _metric_header("Pitch / Roll / Yaw", "pry-metric", value_default="— / — / —"),
                                                            # ✅ PASO 12: ecg-graph -> imu-graph
                                                            dcc.Graph(id="imu-graph", style={"height": "210px", "width": "100%"}, figure=empty_imu_fig),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        style={
                                                            "borderRadius": "12px",
                                                            "background": "rgba(0,0,0,.12)",
                                                            "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                                                            "padding": "8px",
                                                            "display": "flex",
                                                            "flexDirection": "column",
                                                            "gap": "6px",
                                                        },
                                                        children=[
                                                            _metric_header("Sway", "sway-metric", value_default="—"),
                                                            dcc.Graph(id="sway-graph", style={"height": "210px", "width": "100%"}, figure=empty_sway_fig),
                                                        ],
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),

                                    # Histórico
                                    html.Div(
                                        style=card_style,
                                        children=[
                                            html.Div("Histórico de sesiones", style={**BLACK_TEXT, "fontWeight": 700, "fontSize": "13px", "marginBottom": "8px"}),
                                            dcc.Graph(id="history-graph", style={"height": "210px", "width": "100%"}, figure=empty_history_fig),
                                            html.Div(
                                                style={
                                                    "marginTop": "10px",
                                                    "borderRadius": "12px",
                                                    "background": "rgba(0,0,0,.12)",
                                                    "boxShadow": "inset 0 0 0 1px rgba(255,255,255,.08)",
                                                    "padding": "10px",
                                                    "maxHeight": "170px",
                                                    "overflowY": "auto",
                                                },
                                                children=[
                                                    html.Div("Últimas sesiones", style={**BLACK_MUTED, "fontSize": "12px", "fontWeight": 700, "marginBottom": "6px"}),
                                                    html.Ul(
                                                        id="history-list",
                                                        style={"margin": 0, "paddingLeft": "18px", "color": "rgba(226,232,240,.85)", "fontSize": "12px"},
                                                        children=[html.Li("— (sin historial)")],
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),

                    # Modal Recalibración
                    dbc.Modal(
                        id="recal-modal",
                        is_open=False,
                        centered=True,
                        children=[
                            dbc.ModalHeader(dbc.ModalTitle("Recalibración guiada")),
                            dbc.ModalBody(
                                [
                                    html.Div("Sigue estos pasos para recalibrar el dispositivo:", className="mb-2"),
                                    html.Ol(
                                        [
                                            html.Li("Coloca el dispositivo correctamente y mantén postura neutra."),
                                            html.Li("Permanece inmóvil durante 5–10 segundos."),
                                            html.Li("Pulsa “Iniciar recalibración”."),
                                            html.Li("Confirma que el estado queda en verde (semáforo)."),
                                        ]
                                    ),
                                    dbc.ButtonGroup(
                                        [
                                            dbc.Button("Iniciar recalibración", id="start-recal-btn", color="primary"),
                                            dbc.Button("Cerrar", id="close-recal-btn", color="secondary", outline=True),
                                        ],
                                        className="mt-2",
                                    ),
                                ]
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
        [Output("sim-state-store", "data"), Output("imu-interval", "disabled"), Output("sim-status-badge", "children"), Output("sim-status-badge", "color")],
        [Input("sim-on-item", "n_clicks"), Input("sim-off-item", "n_clicks"), Input("sim-reset-item", "n_clicks")],
        State("sim-state-store", "data"),
        prevent_initial_call=True,
    )
    def sim_control(_on, _off, _reset, sim_state):
        sim_state = sim_state or {"on": True, "reset_seq": 0}
        trig = ctx.triggered_id

        if trig == "sim-on-item":
            sim_state["on"] = True
            return sim_state, False, "ON", "success"

        if trig == "sim-off-item":
            sim_state["on"] = False
            return sim_state, True, "OFF", "secondary"

        if trig == "sim-reset-item":
            sim_state["on"] = True
            sim_state["reset_seq"] = int(sim_state.get("reset_seq", 0)) + 1
            return sim_state, False, "ON", "success"

        raise PreventUpdate

    @app.callback(
        [Output("active-session-store", "data"), Output("active-session-label", "children"), Output("active-session-badge", "children")],
        Input("link-session-btn", "n_clicks"),
        State("planned-session", "value"),
        prevent_initial_call=True,
    )
    def link_session(n, planned):
        if not n:
            raise PreventUpdate
        session_name = planned or "—"
        data = {"name": session_name, "linked_at": datetime.now().isoformat(timespec="seconds")}
        label = f"Sesión activa: {session_name}"
        badge = _pill("Sesión", session_name, "neutral", full=True)
        return data, label, badge

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
        [Output("recal-modal", "is_open"), Output("calibration-store", "data"), Output("calibration-pill", "children")],
        [Input("open-recal-btn", "n_clicks"), Input("close-recal-btn", "n_clicks"), Input("start-recal-btn", "n_clicks")],
        [State("recal-modal", "is_open"), State("calibration-store", "data")],
        prevent_initial_call=True,
    )
    def recalibrate(open_n, close_n, start_n, is_open, calib):
        trigger = ctx.triggered_id
        calib = calib or {"status": "No"}

        if trigger == "open-recal-btn":
            return True, calib, _pill("Calibración", calib.get("status", "No"), "warn" if calib.get("status") != "OK" else "ok", full=True)
        if trigger == "close-recal-btn":
            return False, calib, _pill("Calibración", calib.get("status", "No"), "warn" if calib.get("status") != "OK" else "ok", full=True)
        if trigger == "start-recal-btn":
            new_calib = {"status": "OK", "ts": datetime.now().isoformat(timespec="seconds")}
            return False, new_calib, _pill("Calibración", "OK", "ok", full=True)

        return is_open, calib, _pill("Calibración", calib.get("status", "No"), "warn" if calib.get("status") != "OK" else "ok", full=True)

    # -----------------------------
    # recorder_control (PASO 0/1/2/3/8)
    # ✅ ÚNICO callback que escribe recorder-store
    # -----------------------------
    @app.callback(
        [
            Output("recorder-store", "data"),
            Output("recording-pill", "children"),
            Output("recorder-alert", "children"),
            Output("recorder-alert", "is_open"),
            Output("recorder-alert", "color"),
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
        recorder = recorder or {"on": False, "session_id": None, "main_session_id": None}
        trig = ctx.triggered_id

        calibrated = (calib or {}).get("status") == "OK"
        user_id = _get_user_id(session_user)
        session_name = (active_session or {}).get("name") or "—"

        mapped_mode = _map_mode_ui_to_db(mode_ui or "train")
        mapped_sport = _map_sport_ui_to_db(sport_ui or "gym")

        if trig == "start-record-btn":
            if recorder.get("on"):
                return recorder, _pill("Registro", "ON", "ok", full=True), "Ya estás grabando.", True, "info"

            legacy_uuid = str(uuid.uuid4())

            main_session_id = None
            main_db_err = None

            if user_id is None:
                main_db_err = "user_id inválido (session-user no trae id numérico)."
            else:
                try:
                    main_session_id = start_sensor_session(
                        user_id=user_id,
                        kind="monitor",
                        mode=mapped_mode,
                        sport=mapped_sport,
                    )
                except Exception as e:
                    main_db_err = str(e)

            recorder = {"on": True, "session_id": legacy_uuid, "main_session_id": main_session_id}

            if main_session_id is not None:
                _RAW_BUFFER_MAIN[main_session_id] = []
                _STATS_MAIN[main_session_id] = {
                    "user_id": user_id,
                    "mode": mapped_mode,
                    "sport": mapped_sport,
                    "thr_active": _load_user_thresholds_for_mode(user_id=int(user_id), mode=mapped_mode),
                    "session_name": session_name,
                    "calibrated": bool(calibrated),
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

            alert = f"Grabación iniciada (session_id={legacy_uuid[:8]}...)."
            pill_tone = "ok"
            color = "success"
            if main_db_err:
                alert = alert + f" | axisfit.db: {main_db_err}"
                pill_tone = "warn"
                color = "warning"

            return recorder, _pill("Registro", "ON", pill_tone, full=True), alert, True, color

        if trig == "stop-record-btn":
            if not recorder.get("on"):
                return recorder, _pill("Registro", "OFF", "neutral", full=True), "No hay grabación activa.", True, "warning"

            main_session_id = recorder.get("main_session_id")
            user_id = _get_user_id(session_user)

            if main_session_id is None:
                recorder = {"on": False, "session_id": None, "main_session_id": None}
                return recorder, _pill("Registro", "OFF", "neutral", full=True), "Grabación detenida (sin sesión en axisfit.db).", True, "warning"

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
            duration_s = 0.0
            if first_ts is not None and last_ts is not None and int(last_ts) >= int(first_ts):
                duration_s = (int(last_ts) - int(first_ts)) / 1000.0

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
                    vas=float(0.0),
                )
            except Exception as e:
                summary_err = str(e)

            try:
                end_sensor_session(session_id=int(main_session_id))
            except Exception as e:
                close_err = str(e)

            try:
                if user_id is not None:
                    recompute_daily_summary(user_id=int(user_id), day=date.today().isoformat())
            except Exception as e:
                daily_err = str(e)

            _RAW_BUFFER_MAIN.pop(main_session_id, None)
            _STATS_MAIN.pop(main_session_id, None)

            recorder = {"on": False, "session_id": None, "main_session_id": None}

            msg = f"Grabación detenida. Risk v2={risk:.1f} · dur={duration_s:.1f}s · rojoT={thor_red_s:.1f}s · rojoL={lum_red_s:.1f}s · comp_avg={comp_avg:.1f} · alerts={alerts_count}"
            color = "success"
            if flush_err or summary_err or close_err or daily_err:
                color = "warning"
                if flush_err:
                    msg += f" | flush: {flush_err}"
                if summary_err:
                    msg += f" | summary: {summary_err}"
                if close_err:
                    msg += f" | end: {close_err}"
                if daily_err:
                    msg += f" | daily: {daily_err}"

            return recorder, _pill("Registro", "OFF", "neutral", full=True), msg, True, color

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
            Output("alerts-list", "children"),
            Output("session-history-store", "data"),
            Output("history-graph", "figure"),
            Output("history-list", "children"),
            Output("back-arrow", "style"),
            Output("state-dot", "style"),
            Output("thor-traffic-light", "children"),
            Output("lum-traffic-light", "children"),
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

        recorder = recorder or {"on": False, "session_id": None, "main_session_id": None}
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
                [html.Li("— (sin datos aún)")],
                history_store,
                empty_hist,
                [html.Li("— (sin historial)")],
                {"fontSize": "34px", "color": "rgba(226,232,240,.90)", "transform": "rotate(-10deg)"},
                {"display": "none"},
                _traffic_light_zone("green"),
                _traffic_light_zone("green"),
                "—",
                "—",
                "—",
            )

        total_time = max(float(t[-1]) - float(t[0]), 1e-6)
        calibrated = (calib or {}).get("status") == "OK"

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
        comp_out = f"{comp_last:.1f}"

        live_alerts_v2 = []
        if recorder.get("on") and main_session_id is not None and main_session_id in _STATS_MAIN:
            stats = _STATS_MAIN[main_session_id]
            buf = _RAW_BUFFER_MAIN.get(main_session_id, [])

            new_rows = _get_samples_since_from_window(win, stats)

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
            comp_out = f"{comp_last:.1f}"
            thor_red_s_out = f"{float(stats.get('thor_red_s', 0.0)):.1f}s"
            lum_red_s_out = f"{float(stats.get('lum_red_s', 0.0)):.1f}s"
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

                thor_red_s_out = f"{thor_red:.1f}s"
                lum_red_s_out = f"{lum_red:.1f}s"
            except Exception:
                thor_red_s_out = "—"
                lum_red_s_out = "—"

        alerts = []
        if not alerts_on:
            alerts = ["Alertas desactivadas."]
        else:
            if quality == "BAD":
                alerts.append("Señal/Movimientos muy inestables: revisa ajuste del dispositivo.")
            elif quality == "WARN":
                alerts.append("Movimientos irregulares: revisa colocación o postura.")
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
            if not calibrated:
                alerts.append("Calibración pendiente: usa “Recalibración guiada”.")
            if not alerts:
                alerts.append("Sin alertas: estado estable.")

        alerts_children = [html.Li(a) for a in alerts]

        shapes = []
        for a, b in bad_segments[:40]:
            shapes.append(
                {"type": "rect", "xref": "x", "yref": "paper", "x0": a, "x1": b, "y0": 0, "y1": 1, "fillcolor": "rgba(239,68,68,.12)", "line": {"width": 0}}
            )

        fig_imu = {
            "data": [
                {"x": t, "y": pitch, "type": "line", "name": "Pitch"},
                {"x": t, "y": roll, "type": "line", "name": "Roll"},
            ],
            "layout": {"title": {"text": "Gráfica IMU (Pitch / Roll)"}, "paper_bgcolor": "#0b1220", "plot_bgcolor": "#0b1220", "font": {"color": "#e2e8f0"}, "margin": {"l": 40, "r": 20, "t": 40, "b": 35}},
        }

        event_y = [(max(sway) if sway else 1.0) for _ in events_t]
        fig_sway = {
            "data": [
                {"x": t, "y": sway, "type": "line", "name": "Sway"},
                {"x": events_t, "y": event_y, "type": "scatter", "mode": "markers", "name": "Eventos", "text": events_label},
            ],
            "layout": {"title": {"text": "Gráfica Sway / Eventos"}, "paper_bgcolor": "#0b1220", "plot_bgcolor": "#0b1220", "font": {"color": "#e2e8f0"}, "margin": {"l": 40, "r": 20, "t": 40, "b": 35}, "shapes": shapes},
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
            "data": [{"x": xs, "y": ys, "type": "line", "name": "Postura"}],
            "layout": {"title": {"text": "Histórico de sesiones (Postura)"}, "paper_bgcolor": "#0b1220", "plot_bgcolor": "#0b1220", "font": {"color": "#e2e8f0"}, "margin": {"l": 40, "r": 20, "t": 45, "b": 40}},
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
            alerts_children,
            history_store,
            fig_hist,
            history_list,
            arrow_style,
            dot_style,
            _traffic_light_zone(thor_zone_last),
            _traffic_light_zone(lum_zone_last),
            comp_out,
            thor_red_s_out,
            lum_red_s_out,
        )