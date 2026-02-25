import dash
from dash import html, dcc, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from datetime import datetime, date, timedelta
import db  # módulo de datos
import json

# -------------------------
# Constantes de UI
# -------------------------
CONTROL_HEIGHT_PX = 40      # Alto estándar para buscador y botón "Agregar otro"
TITLE_MB_PX = 10            # Margen inferior estándar para títulos
BLOCK_MB_PX = 10            # Margen inferior estándar para bloques


# -------------------------
# Helpers de UI
# -------------------------
def _fmt_id(session: dict) -> str:
    if not session:
        return "--------"
    if session.get("id_str"):
        return session["id_str"]
    try:
        return f"{int(session.get('id')):08d}"
    except Exception:
        return "--------"


def _panel_style():
    return {
        "border": "1px solid #e2e8f0",
        "background": "#ffffff",
        "borderRadius": "14px",
        "boxShadow": "0 4px 14px rgba(15,23,42,.06)",
    }


def _title_style():
    return {
        "fontWeight": 600,
        "color": "#334155",
        "marginBottom": f"{TITLE_MB_PX}px",
    }


def _card_style():
    # Estilo base para los paneles principales (sin width para poder fijar por columna)
    s = _panel_style().copy()
    s.update(
        {
            "height": "400px",
            "overflow": "hidden",
        }
    )
    return s


def _id_box_style():
    # Mismo look & feel que los resúmenes (Próxima sesión / Racha)
    return {
        "padding": "6px 10px",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "flex-end",
        "gap": "10px",
        "minHeight": "42px",
        "height": "42px",
        "width": "260px",
        "borderRadius": "10px",
        "border": "1px solid #e2e8f0",
        "background": "#f8fafc",
    }


def _coach_bottom_bar(cid_val: int):
    return html.Div(
        [
            html.Div(
                [
                    dbc.Button(
                        "Más información",
                        id={"type": "coach-info", "cid": cid_val},
                        color="secondary",
                        outline=True,
                        size="sm",
                        className="me-2",
                    ),
                    dbc.Button(
                        "Mensajes",
                        id={"type": "coach-msgs", "cid": cid_val},
                        color="primary",
                        outline=True,
                        size="sm",
                    ),
                ],
                className="d-flex align-items-center",
            ),
            dbc.Button(
                "Eliminar",
                id={"type": "del-coach", "cid": cid_val},
                color="danger",
                outline=True,
                size="sm",
                className="ms-auto",
            ),
        ],
        className="d-flex align-items-center mt-2",
    )


def _coach_card(c: dict):
    name = c.get("name") or "—"
    email = c.get("email") or "—"

    esp_list = c.get("co_especialidad") or []
    if isinstance(esp_list, str):
        try:
            esp_list = json.loads(esp_list)
        except Exception:
            esp_list = [esp_list] if esp_list else []
    especialidad = ", ".join([str(x) for x in esp_list]) if esp_list else "—"

    turnos = c.get("co_disponibilidad") or "—"

    cid = c.get("id")
    cid_val = int(cid) if cid is not None else -1

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(f"Entrenador: {name}", className="fw-semibold"),
                html.Div(email, className="muted"),
                html.Div(f"Especialidad: {especialidad}", className="mt-1"),
                html.Div(f"Turnos: {turnos}", className="mt-1"),
                _coach_bottom_bar(cid_val),
            ],
            style={"padding": "10px 14px"},
        ),
        className="mb-2",
        style=_panel_style(),
    )


def _coach_details_block(c: dict):
    email = c.get("email") or "—"

    esp_list = c.get("co_especialidad") or []
    if isinstance(esp_list, str):
        try:
            esp_list = json.loads(esp_list)
        except Exception:
            esp_list = [esp_list] if esp_list else []
    especialidad = ", ".join([str(x) for x in esp_list]) if esp_list else "—"

    turnos = c.get("co_disponibilidad") or "—"
    cid = c.get("id")
    cid_val = int(cid) if cid is not None else -1

    return html.Div(
        [
            html.Div(email, className="muted"),
            html.Div(f"Especialidad: {especialidad}", className="mt-1"),
            html.Div(f"Turnos: {turnos}", className="mt-1"),
            _coach_bottom_bar(cid_val),
        ],
        style={"paddingTop": "6px", "paddingBottom": "6px"},
    )


def _pill(on: bool):
    label = "Activo" if on else "Desactivado"
    color = "success" if on else "danger"
    return label, color


def _status_card(title: str, name_key: str, is_on: bool, subtitle: str):
    label, color = _pill(is_on)
    pill_btn = dbc.Button(
        label,
        id={"type": "status-toggle", "name": name_key},
        size="sm",
        color=color,
        className="rounded-pill px-2",
    )
    style = _panel_style()
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    title,
                    className="fw-semibold mb-1",
                    style={"fontSize": "0.90rem", **_title_style()},
                ),
                html.Div(
                    subtitle,
                    className="mb-1",
                    style={
                        "fontSize": "1.05rem",
                        "fontWeight": 700,
                        "color": "#0f172a",
                    },
                ),
                pill_btn,
            ],
            className="py-2 px-2",
        ),
        style=style,
    )


def _battery_card(batt_on: bool, batt_pct):
    """Card específica de batería, 100x100px, sin botón, con círculo de estado clicable."""
    try:
        pct = int(batt_pct or 0)
    except Exception:
        pct = 0
    pct = max(0, min(100, pct))

    circle_color = "#22c55e" if bool(batt_on) else "#ef4444"

    circle = html.Div(
        style={
            "width": "14px",
            "height": "14px",
            "borderRadius": "50%",
            "background": circle_color,
        }
    )

    card = dbc.Card(
        dbc.CardBody(
            html.Div(
                [
                    html.Div(
                        "Batería",
                        className="fw-semibold",
                        style={
                            "fontSize": "1.1rem",
                            "textAlign": "center",
                            "marginBottom": "4px",
                        },
                    ),
                    html.Div(
                        [
                            html.Span(
                                f"{pct}%",
                                style={
                                    "fontSize": "1.5rem",
                                    "fontWeight": 800,
                                    "color": "#0f172a",
                                },
                            ),
                            circle,
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "gap": "8px",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "height": "100%",
                    "width": "100%",
                },
            ),
            className="p-2",
        ),
        style={
            **_panel_style(),
            "height": "100%",
            "width": "100%",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
        },
    )

    return html.Div(
        card,
        id="ath-batt-card",
        n_clicks=0,
        style={"height": "100%", "width": "100%"},
    )


def _ble_card(ble_on: bool):
    """Card de Bluetooth 100x100, mismo estilo que batería, con círculo clicable."""
    circle_color = "#22c55e" if bool(ble_on) else "#ef4444"
    status_text = "On" if bool(ble_on) else "Off"

    circle = html.Div(
        style={
            "width": "14px",
            "height": "14px",
            "borderRadius": "50%",
            "background": circle_color,
        }
    )

    card = dbc.Card(
        dbc.CardBody(
            html.Div(
                [
                    html.Div(
                        "Bluetooth",
                        className="fw-semibold",
                        style={
                            "fontSize": "1.1rem",
                            "textAlign": "center",
                            "marginBottom": "4px",
                        },
                    ),
                    html.Div(
                        [
                            html.Span(
                                status_text,
                                style={
                                    "fontSize": "1.5rem",
                                    "fontWeight": 800,
                                    "color": "#0f172a",
                                },
                            ),
                            circle,
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "gap": "8px",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "height": "100%",
                    "width": "100%",
                },
            ),
            className="p-2",
        ),
        style={
            **_panel_style(),
            "height": "100%",
            "width": "100%",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
        },
    )

    return html.Div(
        card,
        id="ath-ble-card",
        n_clicks=0,
        style={"height": "100%", "width": "100%"},
    )


def _firmware_card(subtitle: str):
    """
    Card de firmware con mismas características visuales que batería y Bluetooth:
    - Usa _panel_style()
    - "Firmware" a la izquierda y versión (v1.0.3) a la derecha en la misma línea
    - Wrapper de 50px de alto y 268px de ancho
    """
    inner = dbc.Card(
        dbc.CardBody(
            html.Div(
                [
                    html.Span(
                        "Firmware",
                        className="fw-semibold",
                        style={
                            "fontSize": "1.1rem",
                            "textAlign": "left",
                            "flex": "0 0 auto",
                        },
                    ),
                    html.Span(
                        subtitle,
                        style={
                            "fontSize": "1.3rem",
                            "fontWeight": 700,
                            "color": "#0f172a",
                            "textAlign": "right",
                            "flex": "0 0 auto",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "flexDirection": "row",
                    "alignItems": "center",
                    "justifyContent": "space-between",  # izquierda / derecha
                    "width": "100%",
                },
            ),
            className="py-1 px-3",
        ),
        style={
            **_panel_style(),
            "height": "100%",
            "width": "100%",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
        },
    )

    return html.Div(
        inner,
        style={
            "height": "50px",
            "width": "268px",
        },
    )


def _small_card(title, body_children):
    style = _panel_style()
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(title, className="fw-semibold", style=_title_style()),
                body_children,
            ],
            className="py-3",
        ),
        style=style,
        className="mb-3",
    )


def _summary_button(title: str, main: str, secondary: str = None):
    """Botón-resumen para Próxima sesión y Racha de adherencia."""
    children = [
        html.Div(title, className="small fw-semibold"),
        html.Div(main, className="small"),
    ]
    if secondary:
        children.append(html.Div(secondary, className="small text-muted"))
    return dbc.Button(
        children,
        color="light",
        className="w-100 text-start mb-2",
        style={
            "border": "1px solid #e2e8f0",
            "background": "#f8fafc",
            "borderRadius": "10px",
            "padding": "8px 10px",
        },
    )


# -------------------------
# Layout
# -------------------------
def layout():
    return html.Div(
        id="ath-home-root",
        className="surface",
        children=[
            # Estados generales
            dcc.Store(id="ath-refresh", data=0),
            dcc.Store(id="ath-add-mode", data=None),
            dcc.Store(id="ath-selected-coach", data=None),
            dcc.Store(id="ath-accordion-active", data=None),

            # Estados de dispositivos
            dcc.Store(id="ath-batt-on", data=True),
            dcc.Store(id="ath-batt-pct", data=78),
            dcc.Store(id="ath-ble-on", data=False),
            dcc.Store(id="ath-fw-on", data=True),
            dcc.Store(id="ath-fw-version", data="v1.0.3"),

            # Día seleccionado en el calendario
            dcc.Store(id="ath-selected-date", data=None),

            # Toast de copiar ID
            dbc.Toast(
                id="ath-copy-toast",
                header="ID copiado",
                is_open=False,
                duration=2500,
                icon="success",
                dismissable=True,
                children="ID copiado al portapapeles.",
                style={"position": "fixed", "top": 10, "right": 10, "zIndex": 1080},
            ),

            dcc.Interval(
                id="ath-alert-timer",
                interval=10000,
                n_intervals=0,
                disabled=True,
                max_intervals=1,
            ),

            # ---------- Modal de error al enlazar ----------
            dbc.Modal(
                id="ath-link-error-modal",
                is_open=False,
                centered=True,
                children=[
                    dbc.ModalHeader(
                        dbc.ModalTitle("Error al enlazar"),
                        close_button=False,
                        style={"background": "#dc2626", "color": "#fff"},
                    ),
                    dbc.ModalBody(
                        id="ath-link-error-body",
                        style={"color": "#991b1b", "fontWeight": 600},
                    ),
                    dbc.ModalFooter(
                        dbc.Button("Cerrar", id="ath-link-error-close", color="danger")
                    ),
                ],
            ),

            # ---------- Tres columnas ----------
            dbc.Row(
                [
                    # IZQUIERDA: ID + entrenadores (400px)
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            html.Span(
                                                "ID de cuenta:",
                                                className="me-2",
                                                style={
                                                    **_title_style(),
                                                    "whiteSpace": "nowrap",
                                                    "marginBottom": "0",
                                                },
                                            ),
                                            html.Div(
                                                [
                                                    html.Code(
                                                        id="ath-id-inline",
                                                        style={
                                                            "fontFamily": (
                                                                "ui-monospace, "
                                                                "SFMono-Regular, Menlo, Monaco, "
                                                                "Consolas, 'Liberation Mono', "
                                                                "'Courier New', monospace"
                                                            ),
                                                            "fontWeight": 800,
                                                            "letterSpacing": "0.04em",
                                                            "fontSize": "1.25rem",
                                                            "color": "#0f172a",
                                                            "lineHeight": "1",
                                                        },
                                                        className="me-2",
                                                    ),
                                                    dcc.Clipboard(
                                                        id="ath-copy-id",
                                                        target_id="ath-id-inline",
                                                        title="Copiar ID",
                                                        style={
                                                            "border": "1px solid #e2e8f0",
                                                            "background": "#ffffff",
                                                            "borderRadius": "8px",
                                                            "padding": "6px 12px",
                                                            "cursor": "pointer",
                                                            "lineHeight": "1",
                                                        },
                                                    ),
                                                ],
                                                style=_id_box_style(),
                                            ),
                                        ],
                                        style={
                                            "display": "flex",
                                            "alignItems": "center",
                                            "gap": "12px",
                                            "marginBottom": f"{BLOCK_MB_PX}px",
                                        },
                                    ),
                                    html.Div(id="ath-link-pane"),
                                ]
                            ),
                            style={**_card_style(), "width": "400px"},
                        ),
                        xs=12,
                        md="auto",
                    ),

                    # CENTRO: Calendario semanal
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div(
                                        [
                                            dbc.Button(
                                                "◀",
                                                id="ath-week-prev",
                                                size="sm",
                                                color="light",
                                                className="me-2",
                                            ),
                                            html.Div(
                                                id="ath-week-label",
                                                className="fw-semibold flex-grow-1 text-center",
                                            ),
                                            dbc.Button(
                                                "▶",
                                                id="ath-week-next",
                                                size="sm",
                                                color="light",
                                                className="ms-2",
                                            ),
                                        ],
                                        className="d-flex align-items-center mb-2",
                                    ),
                                    html.Div(
                                        dbc.Button(
                                            "Ver como lista",
                                            id="ath-calendar-btn",
                                            color="link",
                                            size="sm",
                                            className="p-0",
                                            style={"textDecoration": "underline"},
                                        ),
                                        className="text-end mb-2",
                                    ),
                                    html.Div(
                                        id="ath-week-days",
                                        className="mb-2",
                                    ),
                                    html.Div(
                                        "Toca un día para ver plan, notas y recuperación.",
                                        className="text-muted small mb-2",
                                    ),
                                    html.Div(
                                        id="ath-week-summary",
                                        className="mt-1",
                                    ),
                                ]
                            ),
                            style={**_card_style(), "minWidth": "450px", "width": "450px"},
                        ),
                        xs=12,
                        md="auto",
                    ),

                    # DERECHA: cuadro negro + estado
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.Div(
                                        html.Div(
                                            [
                                                html.Div(
                                                    html.Img(
                                                        src="/assets/Siluetamenuatleta.png",
                                                        style={
                                                            "width": "100%",
                                                            "height": "100%",
                                                            "objectFit": "cover",
                                                        },
                                                    ),
                                                    style={
                                                        "flex": "1 1 auto",
                                                        "height": "100%",
                                                        "display": "flex",
                                                        "alignItems": "center",
                                                        "justifyContent": "center",
                                                    },
                                                ),
                                                html.Div(
                                                    id="ath-mini-status-col",
                                                    style={
                                                        "width": "110px",
                                                        "height": "100%",
                                                        "display": "flex",
                                                        "flexDirection": "column",
                                                        "gap": "2px",
                                                    },
                                                ),
                                            ],
                                            style={
                                                "display": "flex",
                                                "width": "100%",
                                                "height": "300px",
                                                "background": "#000000",
                                                "borderRadius": "8px",
                                                "overflow": "hidden",
                                                "padding": "8px",
                                                "boxSizing": "border-box",
                                                "gap": "8px",
                                            },
                                        ),
                                        className="mb-3",
                                    ),
                                    html.Div(id="ath-status-col"),
                                ]
                            ),
                            style={
                                **_card_style(),
                                "height": "auto",
                                "overflow": "visible",
                                "width": "310px",
                                "minWidth": "310px",
                            },
                        ),
                        xs=12,
                        md="auto",
                    ),
                ],
                className="g-3",
                align="start",
            ),

            # Modales coach info / mensajes / calendario / día
            dbc.Modal(
                id="ath-coach-info-modal",
                is_open=False,
                size="lg",
                children=[
                    dbc.ModalHeader(dbc.ModalTitle("Información del entrenador")),
                    dbc.ModalBody(id="ath-coach-info-body"),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Cerrar", id="ath-coach-info-close", color="secondary"
                        )
                    ),
                ],
            ),
            dbc.Modal(
                id="ath-coach-msgs-modal",
                is_open=False,
                size="lg",
                children=[
                    dbc.ModalHeader(
                        dbc.ModalTitle("Mensajes con el entrenador")
                    ),
                    dbc.ModalBody(id="ath-coach-msgs-body"),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Cerrar", id="ath-coach-msgs-close", color="secondary"
                        )
                    ),
                ],
            ),
            dbc.Modal(
                id="ath-calendar-modal",
                is_open=False,
                size="lg",
                children=[
                    dbc.ModalHeader(
                        dbc.ModalTitle("Calendario de sesiones")
                    ),
                    dbc.ModalBody(id="ath-calendar-body"),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Cerrar",
                            id="ath-calendar-close",
                            color="secondary",
                        )
                    ),
                ],
            ),
            dbc.Modal(
                id="ath-day-detail-modal",
                is_open=False,
                size="lg",
                children=[
                    dbc.ModalHeader(
                        dbc.ModalTitle(id="ath-day-modal-title")
                    ),
                    dbc.ModalBody(
                        [
                            html.Div(
                                id="ath-day-plan-section",
                                className="mb-3",
                            ),
                            _small_card(
                                "Notas del día",
                                html.Div(
                                    [
                                        dbc.Textarea(
                                            id="ath-notes-text",
                                            value="",
                                            placeholder="Lesión leve, tiempo, sensaciones...",
                                            rows=4,
                                            className="mb-2",
                                        ),
                                        dbc.Button(
                                            "Guardar nota",
                                            id="ath-notes-save",
                                            color="primary",
                                            size="sm",
                                        ),
                                        html.Span(
                                            id="ath-notes-feedback",
                                            className="ms-2 text-success",
                                        ),
                                    ]
                                ),
                            ),
                            html.Div(id="ath-day-rec-section"),
                        ]
                    ),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Cerrar",
                            id="ath-day-modal-close",
                            color="secondary",
                        )
                    ),
                ],
            ),
        ],
        style={"display": "block"},
    )


# -------------------------
# Callbacks
# -------------------------
def register_callbacks(app):

    # ID atleta
    @app.callback(
        Output("ath-id-inline", "children"),
        [Input("session-user", "data"), Input("router", "data")],
    )
    def render_athlete_id(session, router):
        if not router or router.get("view") not in ("home", "ath-home"):
            raise PreventUpdate
        if not session or (session.get("role") or "").lower() != "atleta":
            return ""
        return _fmt_id(session)

    @app.callback(
        Output("ath-copy-toast", "is_open"),
        Input("ath-copy-id", "n_clicks"),
        prevent_initial_call=True,
    )
    def copied_id(n):
        if n:
            return True
        raise PreventUpdate

    # Columna mini: batería + negro + BLE
    @app.callback(
        Output("ath-mini-status-col", "children"),
        [
            Input("ath-batt-on", "data"),
            Input("ath-batt-pct", "data"),
            Input("ath-ble-on", "data"),
        ],
        prevent_initial_call=False,
    )
    def render_mini_status_col(batt_on, batt_pct, ble_on):
        batt_card = _battery_card(bool(batt_on), batt_pct)
        ble_card = _ble_card(bool(ble_on))

        return [
            html.Div(
                batt_card,
                style={
                    "height": "100px",
                    "width": "100px",
                    "overflow": "hidden",
                    "margin": "0 auto",
                    "marginTop": "5px",
                },
            ),
            html.Div(
                "",
                style={
                    "height": "20px",
                    "width": "100%",
                    "background": "#000000",
                },
            ),
            html.Div(
                ble_card,
                style={
                    "height": "100px",
                    "width": "100px",
                    "overflow": "hidden",
                    "margin": "0 auto",
                    "marginBottom": "5px",
                },
            ),
        ]

    # Toggle batería
    @app.callback(
        Output("ath-batt-on", "data"),
        Input("ath-batt-card", "n_clicks"),
        State("ath-batt-on", "data"),
        prevent_initial_call=True,
    )
    def toggle_battery_circle(n_clicks, batt_on):
        if not n_clicks:
            raise PreventUpdate
        return not bool(batt_on)

    # Toggle Bluetooth
    @app.callback(
        Output("ath-ble-on", "data"),
        Input("ath-ble-card", "n_clicks"),
        State("ath-ble-on", "data"),
        prevent_initial_call=True,
    )
    def toggle_ble_circle(n_clicks, ble_on):
        if not n_clicks:
            raise PreventUpdate
        return not bool(ble_on)

    # Columna derecha: firmware + perfil
    @app.callback(
        Output("ath-status-col", "children"),
        [
            Input("ath-fw-on", "data"),
            Input("ath-fw-version", "data"),
            Input("session-user", "data"),
            Input("ath-refresh", "data"),
        ],
        prevent_initial_call=False,
    )
    def render_status_col(fw_on, fw_version, session, _):
        athlete_id = int(session.get("id")) if session else None

        fw_sub = fw_version if isinstance(fw_version, str) else "—"
        fw_card = _firmware_card(fw_sub)

        try:
            pct, missing = (
                db.get_profile_completion(athlete_id) if athlete_id else (0, [])
            )
        except Exception:
            pct, missing = (0, [])
        prof_body = html.Div(
            [
                dbc.Progress(value=pct, label=f"{pct}%", className="mb-2"),
                html.Div(
                    ("Faltan: " + ", ".join(missing))
                    if missing
                    else "¡Perfil completo!",
                    className="text-muted",
                ),
            ]
        )
        prof_card = _small_card("Completitud de perfil", prof_body)

        return html.Div(
            [fw_card, prof_card],
            className="d-flex flex-column gap-2",
        )

    # Pane izquierda: entrenadores
    @app.callback(
        Output("ath-link-pane", "children"),
        [
            Input("session-user", "data"),
            Input("router", "data"),
            Input("ath-refresh", "data"),
            Input("ath-add-mode", "data"),
            Input("ath-accordion-active", "data"),
        ],
        prevent_initial_call=False,
    )
    def render_ath_link_pane(session, router, refresh_count, add_mode, open_item):
        if not session or (session.get("role") or "").lower() != "atleta":
            return html.Div()
        if router and router.get("view") not in ("home", "ath-home"):
            raise PreventUpdate

        athlete_id = int(session.get("id"))
        try:
            coaches = db.get_coaches_for_athlete_by_id(athlete_id)
        except Exception:
            coaches = []
        count = len(coaches)

        desired_add_mode = add_mode
        if desired_add_mode is None:
            desired_add_mode = True if count == 0 else False

        show_search = (count < 3) and bool(desired_add_mode)
        show_button = (count < 3) and (not bool(desired_add_mode))

        controls = html.Div(
            [
                dbc.InputGroup(
                    [
                        dbc.Input(
                            id="ath-link-id",
                            placeholder="ID del entrenador (8 dígitos)",
                            maxLength=8,
                            type="text",
                            debounce=True,
                            style={
                                "minWidth": "0",
                                "flex": "1 1 auto",
                                "height": f"{CONTROL_HEIGHT_PX}px",
                            },
                        ),
                        dbc.Button(
                            "Enlazar",
                            id="ath-link-btn",
                            color="primary",
                            className="d-inline-flex alignItems-center",
                            style={
                                "backgroundColor": "#334155",
                                "border": "none",
                                "whiteSpace": "nowrap",
                                "height": f"{CONTROL_HEIGHT_PX}px",
                                "lineHeight": f"{CONTROL_HEIGHT_PX - 2}px",
                            },
                        ),
                    ],
                    id="ath-search-group",
                    size="md",
                    className="flex-nowrap w-100",
                    style={
                        "display": "flex" if show_search else "none",
                        "maxWidth": "100%",
                        "height": f"{CONTROL_HEIGHT_PX}px",
                    },
                ),
                dbc.Button(
                    "Agregar otro entrenador",
                    id="ath-add-more",
                    outline=True,
                    color="secondary",
                    style={
                        "display": "inline-flex" if show_button else "none",
                        "alignItems": "center",
                        "height": f"{CONTROL_HEIGHT_PX}px",
                        "lineHeight": f"{CONTROL_HEIGHT_PX - 2}px",
                    },
                ),
            ],
            style={
                "width": "100%",
                "minHeight": f"{CONTROL_HEIGHT_PX}px",
                "display": "flex",
                "alignItems": "center",
            },
        )

        header = html.Div(
            [
                html.Div("Enlazar con tu entrenador", style=_title_style()),
                controls,
            ],
            style={"marginBottom": f"{BLOCK_MB_PX}px"},
        )

        if count == 0:
            list_block = html.Div()
        elif count == 1:
            list_block = html.Div(
                [
                    html.Div("Entrenador(es) asignado(s)", style=_title_style()),
                    _coach_card(coaches[0]),
                ],
                style={"marginBottom": f"{BLOCK_MB_PX}px"},
            )
        else:
            items = []
            id_map = {}
            for c in coaches:
                name = c.get("name") or "—"
                cid = c.get("id")
                item_id = str(cid) if cid is not None else f"c-{name}"
                id_map[item_id] = c

            show_only_one = open_item in id_map if open_item else False

            def make_item(c):
                name = c.get("name") or "—"
                cid = c.get("id")
                item_id = str(cid) if cid is not None else f"c-{name}"
                return dbc.AccordionItem(
                    _coach_details_block(c),
                    title=f"Entrenador: {name}",
                    item_id=item_id,
                )

            if show_only_one:
                items.append(make_item(id_map[open_item]))
            else:
                for c in coaches:
                    items.append(make_item(c))

            accordion = dbc.Accordion(
                items,
                id="ath-coach-accordion",
                always_open=False,
                start_collapsed=not show_only_one,
                active_item=open_item if show_only_one else None,
                className="mb-0",
                style={
                    **_panel_style(),
                    "--bs-accordion-btn-padding-y": "11px",
                    "--bs-accordion-body-padding-y": "6px",
                },
            )
            list_block = html.Div(
                [
                    html.Div("Entrenador(es) asignado(s)", style=_title_style()),
                    accordion,
                ],
                style={"marginBottom": f"{BLOCK_MB_PX}px"},
            )

        persistent_alert = dbc.Alert(
            id="ath-link-feedback", is_open=False, color="danger", className="mb-0"
        )

        return html.Div([header, list_block, persistent_alert])

    @app.callback(
        Output("ath-accordion-active", "data"),
        Input("ath-coach-accordion", "active_item"),
        prevent_initial_call=True,
    )
    def remember_open_item(active_item):
        return active_item

    @app.callback(
        Output("ath-add-mode", "data", allow_duplicate=True),
        Input("ath-add-more", "n_clicks"),
        prevent_initial_call=True,
    )
    def activate_add_mode(n):
        if n:
            return True
        raise PreventUpdate

    @app.callback(
        [
            Output("ath-link-feedback", "children"),
            Output("ath-link-feedback", "is_open"),
            Output("ath-link-feedback", "color"),
            Output("ath-link-id", "value"),
            Output("ath-refresh", "data", allow_duplicate=True),
            Output("ath-add-mode", "data", allow_duplicate=True),
            Output("ath-alert-timer", "disabled", allow_duplicate=True),
            Output("ath-link-error-body", "children"),
            Output("ath-link-error-modal", "is_open"),
        ],
        Input("ath-link-btn", "n_clicks"),
        [
            State("ath-link-id", "value"),
            State("session-user", "data"),
            State("ath-refresh", "data"),
        ],
        prevent_initial_call=True,
    )
    def link_with_coach(n, target_id, session, refresh_count):
        if not session or (session.get("role") or "").lower() != "atleta":
            raise PreventUpdate

        text = (target_id or "").strip()
        if not (text.isdigit() and len(text) == 8):
            raise PreventUpdate

        athlete_id = int(session.get("id"))

        try:
            current = db.get_coaches_for_athlete_by_id(athlete_id) or []
        except Exception:
            current = []
        if len(current) >= 3:
            return (
                dash.no_update,
                False,
                dash.no_update,
                None,
                refresh_count,
                False,
                True,
                "Has alcanzado el máximo de 3 entrenadores. Elimina uno para agregar otro.",
                True,
            )

        coach_id = int(text)

        current_ids = {int(c.get("id")) for c in current if c.get("id") is not None}
        if coach_id in current_ids:
            return (
                dash.no_update,
                False,
                dash.no_update,
                None,
                refresh_count,
                True,
                True,
                f"El ID {text} ya está enlazado contigo.",
                True,
            )

        try:
            is_coach = db.user_is_coach(coach_id)
        except Exception:
            try:
                u = db.get_user_by_id(coach_id)
                is_coach = u and (u.get("role").lower() == "entrenador")
            except Exception:
                is_coach = False

        if not is_coach:
            return (
                dash.no_update,
                False,
                dash.no_update,
                None,
                refresh_count,
                True,
                True,
                f"El ID {text} es incorrecto o no existe como entrenador.",
                True,
            )

        try:
            db.link_coach_athlete(coach_id=coach_id, athlete_id=athlete_id)
        except Exception:
            return (
                dash.no_update,
                False,
                dash.no_update,
                None,
                refresh_count,
                True,
                True,
                "No fue posible enlazar. Verifica el ID e inténtalo de nuevo.",
                True,
            )

        try:
            updated = db.get_coaches_for_athlete_by_id(athlete_id) or []
        except Exception:
            updated = []
        reached_max = len(updated) >= 3

        return (
            dash.no_update,
            False,
            dash.no_update,
            "",
            (refresh_count or 0) + 1,
            False,
            True,
            dash.no_update,
            False if not reached_max else False,
        )

    @app.callback(
        Output("ath-link-error-modal", "is_open", allow_duplicate=True),
        Input("ath-link-error-close", "n_clicks"),
        State("ath-link-error-modal", "is_open"),
        prevent_initial_call=True,
    )
    def close_error_modal(n, is_open):
        if n:
            return False
        raise PreventUpdate

    @app.callback(
        [
            Output("ath-link-feedback", "is_open", allow_duplicate=True),
            Output("ath-alert-timer", "disabled", allow_duplicate=True),
        ],
        Input("ath-alert-timer", "n_intervals"),
        prevent_initial_call=True,
    )
    def close_feedback_after_timer(_):
        return False, True

    @app.callback(
        [
            Output("ath-refresh", "data", allow_duplicate=True),
            Output("ath-add-mode", "data", allow_duplicate=True),
        ],
        Input({"type": "del-coach", "cid": dash.dependencies.ALL}, "n_clicks"),
        [
            State({"type": "del-coach", "cid": dash.dependencies.ALL}, "id"),
            State("session-user", "data"),
            State("ath-refresh", "data"),
        ],
        prevent_initial_call=True,
    )
    def remove_coach(n_clicks_list, del_btn_ids, session, refresh_count):
        trig = dash.ctx.triggered_id
        if not isinstance(trig, dict) or "cid" not in trig:
            raise PreventUpdate

        try:
            idx = next(
                i
                for i, comp_id in enumerate(del_btn_ids)
                if comp_id.get("cid") == trig.get("cid")
            )
        except StopIteration:
            raise PreventUpdate

        if not n_clicks_list or (n_clicks_list[idx] or 0) <= 0:
            raise PreventUpdate

        if not session or (session.get("role") or "").lower() != "atleta":
            raise PreventUpdate

        coach_id = int(trig.get("cid"))
        athlete_id = int(session.get("id"))

        try:
            db.unlink_coach_athlete(coach_id=coach_id, athlete_id=athlete_id)
        except Exception:
            pass

        try:
            remaining = len(db.get_coaches_for_athlete_by_id(athlete_id))
        except Exception:
            remaining = 0

        return ((refresh_count or 0) + 1, True if remaining == 0 else False)

    # Calendario semanal
    @app.callback(
        [
            Output("ath-week-label", "children"),
            Output("ath-week-days", "children"),
            Output("ath-week-summary", "children"),
        ],
        [
            Input("session-user", "data"),
            Input("ath-refresh", "data"),
            Input("ath-week-prev", "n_clicks"),
            Input("ath-week-next", "n_clicks"),
        ],
        prevent_initial_call=False,
    )
    def render_week(session, _refresh, n_prev, n_next):
        if not session or (session.get("role") or "").lower() != "atleta":
            return "", [], html.Div()
        athlete_id = int(session.get("id"))

        n_prev = n_prev or 0
        n_next = n_next or 0
        week_offset = n_next - n_prev

        today = date.today()
        start_week = today - timedelta(days=today.weekday()) + timedelta(
            weeks=week_offset
        )
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
                week_sessions = [dict(r) for r in rows]
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

        day_names = [
            "Lunes",
            "Martes",
            "Miércoles",
            "Jueves",
            "Viernes",
            "Sábado",
            "Domingo",
        ]

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
                label_sessions = (
                    f"{len(sessions)} sesión"
                    + ("es" if len(sessions) > 1 else "")
                    + f" · {hm}"
                )
                extra_line_text = label_sessions
            else:
                extra_line_text = ""

            extra_line = html.Div(
                extra_line_text,
                className="small text-muted",
                style={"fontSize": "0.65rem"},
            )

            is_today = (week_offset == 0 and d == today)

            base_style = {
                "borderRadius": "10px",
                "border": "1px solid #e2e8f0",
                "background": "#f8fafc" if is_today else "#ffffff",
                "padding": "4px 4px",
                "overflow": "hidden",
            }

            if idx < 5:
                btn_style = {
                    **base_style,
                    "width": "75px",
                    "height": "70px",
                }
            else:
                btn_style = {
                    **base_style,
                    "width": "200px",
                    "height": "60px",
                }

            content = html.Div(
                [
                    html.Div(day_names[idx], className="small fw-semibold"),
                    html.Div(
                        str(d.day),
                        className="fw-bold",
                        style={"fontSize": "1.2rem"},
                    ),
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
                id={"type": "ath-week-day", "date": d.isoformat()},
                color="light",
                className="p-1",
                style=btn_style,
            )

            wrapper = html.Div(day_btn)

            if idx < 5:
                weekday_boxes.append(wrapper)
            else:
                weekend_boxes.append(wrapper)

        row1 = html.Div(
            weekday_boxes,
            className="d-flex justify-content-between mb-2",
        )
        row2 = html.Div(
            weekend_boxes,
            className="d-flex justify-content-center gap-3",
        )

        week_label = (
            f"Semana {days_list[0].strftime('%d %b')} – "
            f"{end_week.strftime('%d %b %Y')}"
        )
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
        next_btn = _summary_button("Próxima sesión", next_main, next_secondary)

        try:
            streak = db.get_streak(athlete_id)
        except Exception:
            streak = 0
        st_main = f"{streak} día" + ("s" if streak != 1 else "")
        streak_btn = _summary_button("Racha de adherencia", st_main)

        summary = html.Div(
            [next_btn, streak_btn],
            className="d-flex flex-column",
        )

        return week_label, week_children, summary

    @app.callback(
        Output("ath-calendar-modal", "is_open"),
        [Input("ath-calendar-btn", "n_clicks"), Input("ath-calendar-close", "n_clicks")],
        State("ath-calendar-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_calendar_modal(open_n, close_n, is_open):
        if open_n or close_n:
            return not is_open
        raise PreventUpdate

    @app.callback(
        Output("ath-calendar-body", "children"),
        Input("ath-calendar-modal", "is_open"),
        State("session-user", "data"),
        prevent_initial_call=True,
    )
    def fill_calendar(opened, session):
        if not opened or not session:
            raise PreventUpdate
        athlete_id = int(session.get("id"))
        try:
            with db._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM workouts WHERE athlete_id=? "
                    "ORDER BY datetime(start_dt) ASC LIMIT 10",
                    (athlete_id,),
                ).fetchall()
        except Exception:
            rows = []
        if not rows:
            return html.Div("No hay sesiones en el calendario.", className="text-muted")

        def _fmt(x):
            try:
                dt = datetime.fromisoformat(x.get("start_dt"))
                when = dt.strftime("%d %b %Y, %H:%M")
            except Exception:
                when = str(x.get("start_dt") or "—")
            return dbc.ListGroupItem(
                [
                    html.Div(x.get("title") or "Sesión", className="fw-semibold"),
                    html.Div(
                        f"{when} — {x.get('location') or '—'}",
                        className="text-muted",
                    ),
                ]
            )

        return dbc.ListGroup([_fmt(dict(r)) for r in rows])

    @app.callback(
        [
            Output("ath-day-detail-modal", "is_open"),
            Output("ath-selected-date", "data"),
        ],
        [
            Input({"type": "ath-week-day", "date": dash.dependencies.ALL}, "n_clicks"),
            Input("ath-day-modal-close", "n_clicks"),
        ],
        [
            State("ath-selected-date", "data"),
            State("ath-day-detail-modal", "is_open"),
        ],
        prevent_initial_call=True,
    )
    def toggle_day_modal(day_clicks, close_n, selected_date, is_open):
        trig = dash.ctx.triggered_id

        if trig == "ath-day-modal-close":
            return False, selected_date

        if isinstance(trig, dict) and trig.get("type") == "ath-week-day":
            if not day_clicks or max((c or 0) for c in day_clicks) <= 0:
                raise PreventUpdate
            return True, trig.get("date")

        raise PreventUpdate

    @app.callback(
        [
            Output("ath-day-modal-title", "children"),
            Output("ath-day-plan-section", "children"),
            Output("ath-day-rec-section", "children"),
            Output("ath-notes-text", "value"),
            Output("ath-notes-feedback", "children", allow_duplicate=True),
        ],
        [
            Input("ath-selected-date", "data"),
            Input("ath-refresh", "data"),
        ],
        [
            State("session-user", "data"),
            State("ath-day-detail-modal", "is_open"),
        ],
        prevent_initial_call=True,
    )
    def fill_day_modal(selected_date, _refresh, session, is_open):
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
                        f"{it.get('name','Ejercicio')} · "
                        f"{it.get('sets','?')}x{it.get('reps','?')} "
                        f"(RPE {it.get('rpe_target','-')})"
                    )
                    for it in plan_items
                ],
                className="mb-0",
            )
        else:
            plan_body = html.Div(
                "Sin plan para este día.", className="text-muted"
            )

        plan_card = _small_card("Plan del día", plan_body)

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
            rec_body = html.Div(
                "Sin datos recientes.", className="text-muted"
            )

        rec_card = _small_card("Recuperación", rec_body)

        return title, plan_card, rec_card, note_text, ""

    @app.callback(
        [
            Output("ath-notes-feedback", "children", allow_duplicate=True),
            Output("ath-refresh", "data", allow_duplicate=True),
        ],
        Input("ath-notes-save", "n_clicks"),
        [
            State("ath-notes-text", "value"),
            State("ath-selected-date", "data"),
            State("session-user", "data"),
            State("ath-refresh", "data"),
        ],
        prevent_initial_call=True,
    )
    def save_note(n, text, selected_date, session, refresh):
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
        [
            Output("ath-coach-info-modal", "is_open"),
            Output("ath-selected-coach", "data", allow_duplicate=True),
        ],
        [
            Input({"type": "coach-info", "cid": dash.dependencies.ALL}, "n_clicks"),
            Input("ath-coach-info-close", "n_clicks"),
        ],
        [
            State({"type": "coach-info", "cid": dash.dependencies.ALL}, "id"),
            State("ath-coach-info-modal", "is_open"),
            State("ath-selected-coach", "data"),
        ],
        prevent_initial_call=True,
    )
    def toggle_info_modal(info_clicks, close_n, info_ids, is_open, selected):
        trig = dash.ctx.triggered_id

        if trig == "ath-coach-info-close":
            return False, selected

        if isinstance(trig, dict) and trig.get("type") == "coach-info":
            try:
                idx = next(
                    i
                    for i, comp_id in enumerate(info_ids)
                    if comp_id.get("cid") == trig.get("cid")
                )
            except StopIteration:
                raise PreventUpdate

            if info_clicks and (info_clicks[idx] or 0) > 0:
                return True, int(trig.get("cid"))

        raise PreventUpdate

    @app.callback(
        Output("ath-coach-info-body", "children"),
        Input("ath-coach-info-modal", "is_open"),
        [State("ath-selected-coach", "data")],
        prevent_initial_call=True,
    )
    def fill_info_body(opened, coach_id):
        if not opened or not coach_id:
            raise PreventUpdate

        try:
            coach = db.get_user_by_id(int(coach_id)) or {}
        except Exception:
            coach = {}

        name = coach.get("name", "—")
        email = coach.get("email", "—")

        esp = coach.get("co_especialidad") or []
        if isinstance(esp, str):
            try:
                esp = json.loads(esp)
            except Exception:
                esp = [esp] if esp else []
        esp_txt = ", ".join(esp) if esp else "—"

        mod = coach.get("co_modalidad") or []
        if isinstance(mod, str):
            try:
                mod = json.loads(mod)
            except Exception:
                mod = [mod] if mod else []
        mod_txt = ", ".join(mod) if mod else "—"

        turnos = coach.get("co_disponibilidad") or "—"
        centro = coach.get("co_centro") or "—"
        ubic = coach.get("co_ubicacion") or "—"
        anios = coach.get("co_anios") or "—"
        cred = "Sí" if coach.get("co_cred") else "No"

        return html.Div(
            [
                html.Div(f"Nombre: {name}", className="mb-1"),
                html.Div(f"Email: {email}", className="mb-1"),
                html.Div(f"Especialidad: {esp_txt}", className="mb-1"),
                html.Div(f"Modalidad: {mod_txt}", className="mb-1"),
                html.Div(f"Turnos: {turnos}", className="mb-1"),
                html.Div(f"Centro: {centro}", className="mb-1"),
                html.Div(f"Ubicación: {ubic}", className="mb-1"),
                html.Div(f"Años de experiencia: {anios}", className="mb-1"),
                html.Div(f"Verificado: {cred}", className="mb-1"),
            ]
        )

    @app.callback(
        [
            Output("ath-coach-msgs-modal", "is_open"),
            Output("ath-selected-coach", "data", allow_duplicate=True),
        ],
        [
            Input({"type": "coach-msgs", "cid": dash.dependencies.ALL}, "n_clicks"),
            Input("ath-coach-msgs-close", "n_clicks"),
        ],
        [
            State({"type": "coach-msgs", "cid": dash.dependencies.ALL}, "id"),
            State("ath-coach-msgs-modal", "is_open"),
            State("ath-selected-coach", "data"),
        ],
        prevent_initial_call=True,
    )
    def toggle_msgs_modal(msgs_clicks, close_n, msg_ids, is_open, selected):
        trig = dash.ctx.triggered_id

        if trig == "ath-coach-msgs-close":
            return False, selected

        if isinstance(trig, dict) and trig.get("type") == "coach-msgs":
            try:
                idx = next(
                    i
                    for i, comp_id in enumerate(msg_ids)
                    if comp_id.get("cid") == trig.get("cid")
                )
            except StopIteration:
                raise PreventUpdate

            if msgs_clicks and (msgs_clicks[idx] or 0) > 0:
                return True, int(trig.get("cid"))

        raise PreventUpdate

    @app.callback(
        Output("ath-coach-msgs-body", "children"),
        Input("ath-coach-msgs-modal", "is_open"),
        [State("ath-selected-coach", "data"), State("session-user", "data")],
        prevent_initial_call=True,
    )
    def fill_msgs_body(opened, coach_id, session):
        if not opened or not coach_id or not session:
            raise PreventUpdate
        athlete_id = int(session.get("id"))
        msgs = []
        try:
            msgs = db.get_messages_between(
                athlete_id=athlete_id, coach_id=int(coach_id), limit=50
            ) or []
        except Exception:
            try:
                all_msgs = db.get_messages_history_for_athlete(
                    athlete_id, limit=200
                ) or []
                msgs = [
                    m
                    for m in all_msgs
                    if int(m.get("coach_id", -1)) == int(coach_id)
                ]
            except Exception:
                msgs = []

        if not msgs:
            return html.Div(
                "Sin mensajes con este entrenador.", className="text-muted"
            )

        items = []
        for m in msgs:
            who = m.get("coach_name") or "Coach"
            ts = m.get("created_at") or ""
            text_msg = m.get("text") or ""
            items.append(
                dbc.Alert(
                    f"[{ts}] {who}: {text_msg}",
                    color="light",
                    style=_panel_style(),
                )
            )
        return html.Div(items)
