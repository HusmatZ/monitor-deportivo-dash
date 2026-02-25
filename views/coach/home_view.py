# views/coach/home_view.py
from dash import html, dcc, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import db  # usamos el módulo db

def _fmt_id(session: dict) -> str:
    if not session:
        return "--------"
    if session.get("id_str"):
        return session["id_str"]
    try:
        return f"{int(session.get('id')):08d}"
    except Exception:
        return "--------"

def _card_style():
    return {
        "border": "1px solid rgba(209,217,227,.6)",
        "background": "rgba(255,255,255,.72)",
        "backdropFilter": "saturate(120%) blur(4px)",
        "borderRadius": "16px",
        "boxShadow": "0 6px 18px rgba(15,23,42,.08)"
    }

def _athlete_card(a: dict):
    name = a.get("name") or "—"
    email = a.get("email") or "—"
    country = a.get("country") or "—"
    aid = a.get("id")
    aid_str = f"{int(aid):08d}" if isinstance(aid, int) else "--------"
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(f"Atleta: {name}", className="fw-semibold"),
                html.Div(email, className="muted"),
                html.Div(f"País: {country}", className="mt-1"),
                html.Div(f"ID: {aid_str}", className="mt-1"),
            ]
        ),
        className="mb-2",
        style={"border":"1px solid var(--c-border)", "background":"var(--c-card)", "borderRadius":"12px"}
    )

def layout():
    return html.Div(
        id="coach-home-root",
        className="surface",
        children=[
            # Estado interno para refrescar la lista de atletas
            dcc.Store(id="coach-refresh", data=0),

            # Tarjeta principal
            dbc.Card(
                dbc.CardBody(
                    dbc.Row(
                        [
                            # IZQUIERDA: ID (grande)
                            dbc.Col(
                                [
                                    html.Div("ID de cuenta", className="muted mb-1"),
                                    html.Div(
                                        id="coach-id-big",
                                        style={
                                            "fontSize": "2.25rem",
                                            "fontWeight": 800,
                                            "letterSpacing": "0.06em",
                                            "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                                            "color": "var(--c-text)"
                                        }
                                    ),
                                ],
                                md=6
                            ),
                            # DERECHA: Buscador para enlazar atletas por ID
                            dbc.Col(
                                [
                                    html.Div("Enlazar con un atleta", className="muted mb-1"),
                                    dbc.InputGroup(
                                        [
                                            dbc.Input(
                                                id="coach-link-id",
                                                placeholder="ID del atleta (8 dígitos)",
                                                maxLength=8,
                                                type="text",
                                                debounce=True
                                            ),
                                            dbc.Button("Enlazar", id="coach-link-btn", color="primary",
                                                       style={"backgroundColor":"var(--c-accent)","border":"none"})
                                        ],
                                        className="mb-2"
                                    ),
                                    dbc.Alert(id="coach-link-feedback", is_open=False, color="info", className="mb-0")
                                ],
                                md=6
                            ),
                        ],
                        align="center"
                    )
                ),
                style=_card_style()
            ),

            # LISTA de atletas enlazados (debajo del ID)
            html.Div(id="coach-athletes-list", className="mt-3"),
        ]
    )

def register_callbacks(app):

    # Pinta el ID del coach (cuando view es home o coach-home)
    @app.callback(
        Output("coach-id-big", "children"),
        [Input("session-user", "data"), Input("router", "data")]
    )
    def render_coach_id(session, router):
        if not router or router.get("view") not in ("home", "coach-home"):
            raise PreventUpdate
        if not session or (session.get("role") or "").lower() != "entrenador":
            return ""
        return _fmt_id(session)

    # Renderiza la lista de atletas enlazados (debajo del ID)
    @app.callback(
        Output("coach-athletes-list", "children"),
        [Input("session-user", "data"), Input("router", "data"), Input("coach-refresh", "data")],
        prevent_initial_call=False
    )
    def render_coach_athletes(session, router, refresh_count):
        if not session or (session.get("role") or "").lower() != "entrenador":
            return html.Div()
        if router and router.get("view") not in ("home", "coach-home"):
            raise PreventUpdate

        coach_id = int(session.get("id"))
        athletes = db.get_athletes_for_coach_by_id(coach_id)
        if not athletes:
            return html.Div("Aún no has enlazado atletas.", className="muted")

        cards = [_athlete_card(a) for a in athletes]
        return html.Div(cards)

    # Enlazar coach -> athlete por ID
    @app.callback(
        [
            Output("coach-link-feedback", "children"),
            Output("coach-link-feedback", "is_open"),
            Output("coach-link-feedback", "color"),
            Output("coach-link-id", "value"),
            Output("coach-refresh", "data"),
        ],
        Input("coach-link-btn", "n_clicks"),
        [State("coach-link-id", "value"), State("session-user", "data"), State("coach-refresh", "data")],
        prevent_initial_call=True
    )
    def link_with_athlete(n, target_id, session, refresh_count):
        if not session or (session.get("role") or "").lower() != "entrenador":
            raise PreventUpdate

        other = (target_id or "").strip()
        if not other.isdigit() or len(other) != 8:
            return "El ID debe tener 8 dígitos.", True, "danger", None, refresh_count

        try:
            coach_id = int(session.get("id"))
            athlete_id = int(other)
            db.link_coach_athlete(coach_id=coach_id, athlete_id=athlete_id)
            # Refresca la lista de atletas
            return f"✅ Enlace realizado con el atleta {other}.", True, "success", "", (refresh_count or 0) + 1
        except Exception:
            return "❌ No fue posible enlazar. Verifica el ID e inténtalo de nuevo.", True, "danger", None, refresh_count
