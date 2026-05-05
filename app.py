# app.py
import dash
from dash import dcc, html, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from db import init_db

# --- vistas de INICIO separadas ---
from views.athlete.home_view import layout as athlete_home_layout, register_callbacks as register_athlete_home_callbacks
from views.coach.home_view import layout as coach_home_layout, register_callbacks as register_coach_home_callbacks

# --- vistas del ATLETA (pestañas) ---
from views.athlete.monitor_view import layout as monitor_layout, register_callbacks as register_monitor_callbacks
from views.athlete.questionnaire_view import layout as questionnaire_layout_view, register_callbacks as register_questionnaire_callbacks
from views.athlete.routines_view import layout as routines_layout
from views.athlete.progress_view import layout as progress_layout

# --- auth (modales + callbacks de login/registro) ---
from auth import register_auth_callbacks

# Inicializar app Dash con estilos de Bootstrap
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True
)
server = app.server

# --- INYECTAR CSS ---
app.index_string = """
<!DOCTYPE html>
<html>
  <head>
    {%metas%}
    <title>AXISFIT</title>
    {%favicon%}
    {%css%}
    <style>
      :root{
        --c-navbar:#eef2f6;
        --c-bg:#eef2f6;
        --c-surface:#c2ccd9;
        --c-card:#ffffff;
        --c-border:#d1d9e3;
        --c-text:#0f172a;
        --c-muted:#475569;
        --c-accent:#3a6ea5;
        --c-accent-2:#5b8bd6;

        /* gris oscuro del texto de los botones */
        --btn-dark-gray:#334155;
      }

      html{ overflow-y:scroll; }
      body{ background:var(--c-bg); color:var(--c-text); }
      body.modal-open{ padding-right:0 !important; }
      .modal{ overflow-y:auto !important; }

      .navbar-custom{
        background: var(--c-navbar) !important;
        border-bottom: 1px solid var(--c-border);
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        overflow: visible !important;
      }

      .navbar-custom .container-fluid{
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        flex-wrap: nowrap !important;
        overflow: visible !important;
      }

      .navbar-inner{
        display:flex !important;
        align-items:center !important;
        flex-wrap:nowrap !important;
        position:relative !important;
        gap: 8px;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        overflow: visible !important;
      }

      /* ==========================================================
         BOTONES NAV CENTRAL (Métrica/Cuestionario/Rutinas/Progreso)
         - mismo tipo de letra que Registro/Login (normal)
         - color de letra gris oscuro antes del hover
         - hover: el color pasa a gris oscuro (fondo gris oscuro),
                 igual al color de sus letras antes del hover
         ========================================================== */
      .btn-nav{
        background: var(--c-navbar) !important;     /* color navbar */
        color: var(--btn-dark-gray) !important;     /* gris oscuro */
        border: 1px solid transparent !important;   /* sin borde negro */
        width:160px;
        box-shadow:none !important;

        /* MISMO "TIPO" (estilo) DE LETRA QUE REGISTRO/LOGIN */
        font-weight:400 !important;                 /* normal */
        font-family: inherit !important;

        transition: all .15s ease !important;
      }
      .btn-nav:hover{
        background: var(--btn-dark-gray) !important; /* gris oscuro */
        color:#fff !important;                       /* contraste */
        border-color: var(--btn-dark-gray) !important;
        transform: none !important;
      }
      .btn-nav:active{
        background:#1f2937 !important; /* un poco más oscuro */
        color:#fff !important;
        border-color:#1f2937 !important;
        transform: none !important;
      }

      .modal-content{ background:var(--c-card); border:1px solid var(--c-border); }
      .surface{ background:var(--c-surface); border-radius:12px; padding:24px; min-height:75vh; }
      .soft-hr{ border-top:1px solid var(--c-border); }
      h2,h3{ color:var(--c-text); }
      .muted{ color:var(--c-muted); }
      .req::after { content:" *"; color:#b91c1c; }
      .help{ font-size:.875rem; color:var(--c-muted); }

      /* ==========================
         NAVBAR AUTH BUTTONS (fila)
         + alineación perfecta
         ========================== */
      #navbar-auth{
        display:flex !important;
        flex-direction:row !important;
        flex-wrap:nowrap !important;
        align-items:center !important;
        gap: 8px !important;
        white-space: nowrap !important;
      }
      #navbar-auth > *{
        display:flex !important;
        flex-direction:row !important;
        flex-wrap:nowrap !important;
        align-items:center !important;
        gap: 8px !important;
        white-space: nowrap !important;
      }
      #navbar-auth .btn-group,
      #navbar-auth .btn-group-vertical,
      #navbar-auth .vstack,
      #navbar-auth .d-grid{
        display:flex !important;
        flex-direction:row !important;
        flex-wrap:nowrap !important;
        align-items:center !important;
        gap: 8px !important;
      }
      #navbar-auth .row{
        flex-wrap: nowrap !important;
        --bs-gutter-x: .5rem;
        --bs-gutter-y: 0;
        margin: 0 !important;
      }
      #navbar-auth .col,
      #navbar-auth [class*="col-"]{
        flex: 0 0 auto !important;
        width: auto !important;
        max-width: none !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
      }
      #navbar-auth .btn{
        display:inline-flex !important;
        align-items:center !important;
        justify-content:center !important;
        align-self:center !important;
        min-height: 38px !important;
        padding-top: .375rem !important;
        padding-bottom: .375rem !important;
        line-height: 1.2 !important;
        flex: 0 0 auto !important;
        width: auto !important;
        white-space: nowrap !important;
        margin: 0 !important;
        transition: all .15s ease !important;
        font-weight:400 !important; /* normal */
      }

      /* ==========================================================
         ORDEN:
         - Registro a la IZQUIERDA
         - Iniciar sesión a la DERECHA
         ========================================================== */
      #navbar-auth [id*="register"]{ order: 0 !important; }
      #navbar-auth [id*="login"]{ order: 1 !important; }

      /* ==========================================================
         BOTÓN "INICIAR SESIÓN" (NEGRO + BLANCO)
         ========================================================== */
      #navbar-auth [id*="login"]{
        background:#000 !important;
        color:#fff !important;
        border:1px solid #000 !important;
        font-weight:400 !important;
      }
      #navbar-auth [id*="login"]:hover{
        background:#2b2b2b !important;
        border-color:#2b2b2b !important;
        color:#fff !important;
      }
      #navbar-auth [id*="login"]:active{
        background:#111 !important;
        border-color:#111 !important;
      }

      /* ==========================================================
         BOTÓN "REGISTRARSE"
         - sin borde negro
         - mismo color del navbar
         - hover: negro
         ========================================================== */
      #navbar-auth [id*="register"]{
        background: var(--c-navbar) !important;
        color: var(--c-text) !important;
        border: 1px solid transparent !important;
        box-shadow: none !important;
        font-weight:400 !important;
      }
      #navbar-auth [id*="register"]:hover{
        background:#000 !important;
        color:#fff !important;
        border-color:#000 !important;
      }
      #navbar-auth [id*="register"]:active{
        background:#111 !important;
        border-color:#111 !important;
        color:#fff !important;
      }

      /* ==========================================================
         MODAL DE ACCESO (consistente)
         ========================================================== */
      #access-login{
        background:#000 !important;
        color:#fff !important;
        border:1px solid #000 !important;
        font-weight:400 !important;
        transition: all .15s ease !important;
      }
      #access-login:hover{
        background:#2b2b2b !important;
        border-color:#2b2b2b !important;
        color:#fff !important;
      }
      #access-login:active{
        background:#111 !important;
        border-color:#111 !important;
      }

      #access-register{
        background: var(--c-navbar) !important;
        color: var(--c-text) !important;
        border: 1px solid transparent !important;
        box-shadow: none !important;
        font-weight:400 !important;
        transition: all .15s ease !important;
      }
      #access-register:hover{
        background:#000 !important;
        color:#fff !important;
        border-color:#000 !important;
      }
      #access-register:active{
        background:#111 !important;
        border-color:#111 !important;
        color:#fff !important;
      }
    </style>
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
  </body>
</html>
"""

# Inicializar la base de datos
init_db()

# -------- Layout general (navbar + modales + contenedor de página) --------
app.layout = html.Div([
    dcc.Store(id="session-user", storage_type="session"),
    dcc.Store(id="router", storage_type="session", data={"view": "home"}),  # home decidirá ath-home / coach-home
    dcc.Store(id="reg-base", storage_type="memory"),
    dcc.Store(id="q-reset", storage_type="memory", data=0),

    # ----- NAVBAR -----
    dbc.Navbar(
        dbc.Container(
            [
                dbc.Button(
                    html.Img(
                        src="/assets/AXISFIT.png",
                        style={
                            "height": "80px",
                            "width": "auto",
                            "maxWidth": "200px",
                            "borderRadius": "12px",
                            "objectFit": "contain",
                            "display": "block"
                        }
                    ),
                    id="logo-btn",
                    color="link",
                    className="p-0",
                    style={
                        "lineHeight": 0,
                        "border": "none",
                        "background": "transparent",
                        "cursor": "pointer",
                        "display": "flex",
                        "alignItems": "center",
                        "overflow": "visible",
                        "padding": "0",
                        "margin": "0"
                    }
                ),

                html.Div(
                    [
                        dbc.Button("Monitorización", id="metrics-btn", size="md",
                                   className="btn-nav"),
                        dbc.Button("Cuestionario", id="questionnaire-btn", size="md",
                                   className="ms-2 btn-nav"),
                        dbc.Button("Rutinas", id="rutinas-btn", size="md",
                                   className="ms-2 btn-nav"),
                        dbc.Button("Progresos", id="progresos-btn", size="md",
                                   className="ms-2 btn-nav"),
                    ],
                    id="navbar-center",
                    className="d-none d-md-flex align-items-center",
                    style={"position": "absolute", "left": "50%", "transform": "translateX(-50%)"}
                ),

                html.Div(
                    id="navbar-auth",
                    className="d-flex flex-row flex-nowrap align-items-center ms-auto",
                    style={"gap": "8px"}
                ),
            ],
            fluid=True,
            className="navbar-inner"
        ),
        fixed="top",
        className="shadow-sm py-0 navbar-light navbar-custom",
    ),

    # ---- MODALES (UI) -> callbacks en auth.py ----
    # (Login)
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Iniciar sesión")),
            dbc.ModalBody(
                [
                    dbc.Input(id="login-email", placeholder="Correo electrónico", type="email", className="mb-2"),
                    dbc.Input(id="login-password", placeholder="Contraseña", type="password", className="mb-3"),
                    dbc.Alert(id="login-feedback", color="info", is_open=False)
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Cerrar", id="login-close", className="me-2", outline=True),
                    dbc.Button("Entrar", id="login-submit", color="primary",
                               style={"backgroundColor":"var(--c-accent)","border":"none"})
                ]
            ),
        ],
        id="login-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="md", fade=False
    ),

    # (Registro base)
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Crear cuenta")),
            dbc.ModalBody(
                [
                    dbc.Alert(id="reg-feedback", color="danger", is_open=False, className="mb-3"),
                    dbc.Form(
                        [
                            dbc.Label("Email", className="req"),
                            dbc.Input(id="reg-email", type="email", placeholder="tu@correo.com", className="mb-3"),
                            dbc.Label("Nombre", className="req"),
                            dbc.Input(id="reg-name", type="text", placeholder="Tu nombre completo", className="mb-3"),
                            dbc.Label("País", className="req"),
                            dcc.Dropdown(
                                id="reg-country",
                                options=[
                                    {"label": "España (ES)", "value": "ES"},
                                    {"label": "Venezuela (VE)", "value": "VE"},
                                    {"label": "México (MX)", "value": "MX"},
                                    {"label": "Argentina (AR)", "value": "AR"},
                                    {"label": "Colombia (CO)", "value": "CO"},
                                    {"label": "Chile (CL)", "value": "CL"},
                                    {"label": "Perú (PE)", "value": "PE"},
                                    {"label": "Brasil (BR)", "value": "BR"},
                                    {"label": "Estados Unidos (US)", "value": "US"},
                                    {"label": "Canadá (CA)", "value": "CA"},
                                    {"label": "Portugal (PT)", "value": "PT"},
                                    {"label": "Francia (FR)", "value": "FR"},
                                    {"label": "Italia (IT)", "value": "IT"},
                                    {"label": "Alemania (DE)", "value": "DE"},
                                    {"label": "Reino Unido (GB)", "value": "GB"},
                                ],
                                placeholder="Selecciona tu país", className="mb-3"
                            ),

                            dbc.Label("Contraseña", className="req"),
                            dbc.Input(id="reg-password", type="password",
                                      placeholder="Mín. 8, 1 mayús, 1 minús, 1 número", className="mb-2"),
                            dbc.Label("Confirmar contraseña", className="req"),
                            dbc.Input(id="reg-password2", type="password",
                                      placeholder="Repite la contraseña", className="mb-2"),
                            html.Div(
                                "La contraseña debe tener ≥8 caracteres, incluir al menos 1 mayúscula, 1 minúscula y 1 número.",
                                className="help mb-3"
                            ),

                            dbc.Label("Aceptaciones", className="req"),
                            dbc.Checklist(
                                id="reg-accepts",
                                options=[
                                    {"label": "Acepto Términos y Privacidad", "value": "terms"},
                                    {"label": "Declaro que no es dispositivo médico", "value": "disclaimer"}
                                ],
                                value=[], switch=True, className="mb-3"
                            ),

                            dbc.Label("Rol al inicio", className="req"),
                            dcc.RadioItems(
                                id="reg-role",
                                options=[
                                    {"label": "Soy Atleta", "value": "atleta"},
                                    {"label": "Soy Entrenador", "value": "entrenador"},
                                ],
                                value=None, labelStyle={"display":"block"}, className="mb-2"
                            ),
                        ]
                    )
                ]
            ),
            dbc.ModalFooter(
                [
                    html.Div(
                        dbc.Button("Usuarios registrados", id="open-users",
                                   color="secondary", outline=True, style={"width": "200px"}),
                        className="me-auto"
                    ),
                    dbc.Button("Cerrar", id="reg-close", outline=True, className="me-2"),
                    dbc.Button("Continuar", id="reg-continue", n_clicks=0, color="primary",
                               style={"backgroundColor":"var(--c-accent)","border":"none"}),
                ]
            ),
        ],
        id="reg-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="lg", fade=False
    ),

    # (Perfil ATLETA)
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Perfil de Atleta")),
            dbc.ModalBody(
                [
                    dbc.Alert(id="ath-feedback", color="danger", is_open=False, className="mb-3"),
                    dbc.Form(
                        [
                            dbc.Label("Rol de uso", className="req"),
                            dcc.Dropdown(
                                id="ath-uso",
                                options=[{"label":"Gym","value":"Gym"}, {"label":"CrossFit","value":"CrossFit"}],
                                placeholder="Selecciona uso principal",
                                className="mb-3"
                            ),

                            dbc.Label("Nivel de experiencia", className="req"),
                            dcc.Dropdown(
                                id="ath-nivel",
                                options=[{"label":x, "value":x} for x in ["Novato","Intermedio","Avanzado"]],
                                placeholder="Selecciona nivel",
                                className="mb-3"
                            ),

                            dbc.Label("Frecuencia semanal", className="req"),
                            dcc.Dropdown(
                                id="ath-freq",
                                options=[{"label":x, "value":x} for x in ["1–2","3–4","5+"]],
                                placeholder="Sesiones/semana",
                                className="mb-3"
                            ),

                            dbc.Label("Molestias actuales"),
                            dcc.Dropdown(
                                id="ath-molestias",
                                options=[{"label":x,"value":x} for x in ["Cervical","Hombro","Dorsal","Lumbar","Ninguna"]],
                                placeholder="Selecciona (opcional)",
                                multi=True,
                                className="mb-3"
                            ),

                            html.Div(
                                [
                                    dbc.Label("Intensidad de dolor (VAS)", id="ath-vas-label", style={"display":"none"}),
                                    dcc.Slider(0,10,1, value=0, id="ath-dolor",
                                               tooltip={"always_visible":False}, marks=None),
                                ],
                                id="ath-vas-col",
                                style={"display":"none"},
                                className="mb-3"
                            ),

                            dbc.Label("Box/Gimnasio"),
                            dbc.Input(id="ath-box", type="text",
                                      placeholder="Nombre del Box/Gimnasio (2–50 car.)", className="mb-3"),

                            dbc.Row([
                                dbc.Col([
                                    dbc.Label("Altura (cm)"),
                                    dbc.Input(id="ath-altura", type="number",
                                              min=80, max=250, step=1, placeholder="Opcional")
                                ], md=6),
                                dbc.Col([
                                    dbc.Label("Peso (kg)"),
                                    dbc.Input(id="ath-peso", type="number",
                                              min=30, max=250, step=0.1, placeholder="Opcional")
                                ], md=6),
                            ], className="mb-2"),
                            html.Div(
                                "Nota: la intensidad (VAS) aparece si declaras molestias distintas de “Ninguna”.",
                                className="help"
                            ),
                        ]
                    )
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Atrás", id="ath-back", outline=True, className="me-2"),
                    dbc.Button("Crear cuenta", id="ath-submit", n_clicks=0, color="primary",
                               style={"backgroundColor":"var(--c-accent)","border":"none"}),
                ]
            ),
        ],
        id="athlete-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="lg", fade=False
    ),

    # (Perfil ENTRENADOR)
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Perfil de Entrenador")),
            dbc.ModalBody(
                [
                    dbc.Alert(id="coach-feedback", color="danger", is_open=False, className="mb-3"),
                    dbc.Form(
                        [
                            dbc.Label("Especialidad", className="req"),
                            dcc.Dropdown(
                                id="coach-especialidad",
                                options=[{"label":"Gym/Strength","value":"Gym/Strength"},{"label":"CrossFit","value":"CrossFit"}],
                                multi=True,
                                placeholder="Selecciona especialidades",
                                className="mb-3"
                            ),

                            dbc.Label("Años de experiencia", className="req"),
                            dcc.Dropdown(
                                id="coach-anios",
                                options=[{"label":x,"value":x} for x in ["0–1","2–4","5–9","10+"]],
                                placeholder="Selecciona rango",
                                className="mb-3"
                            ),

                            dbc.Label("Centro de trabajo"),
                            dbc.Input(id="coach-centro", type="text",
                                      placeholder="Nombre del Box/Gimnasio (2–50 car.)", className="mb-3"),

                            dbc.Label("Ubicación"),
                            dbc.Input(id="coach-ubicacion", type="text",
                                      placeholder="Ciudad / Provincia", className="mb-3"),

                            dbc.Label("Modalidad de servicio", className="req"),
                            dcc.Dropdown(
                                id="coach-modalidad",
                                options=[{"label":x,"value":x} for x in ["Presencial","Online","Híbrido"]],
                                multi=True,
                                placeholder="Selecciona modalidades",
                                className="mb-3"
                            ),

                            dbc.Label("Disponibilidad semanal", className="req"),
                            dcc.Dropdown(
                                id="coach-disponibilidad",
                                options=[{"label":x,"value":x} for x in ["Mañanas","Tardes","Mixto"]],
                                placeholder="Selecciona franja",
                                className="mb-2"
                            ),

                            dbc.Checkbox(id="coach-cred", value=False,
                                         label="Acepto verificación de credenciales (opcional)"),
                        ]
                    )
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Atrás", id="coach-back", outline=True, className="me-2"),
                    dbc.Button("Crear cuenta", id="coach-submit", n_clicks=0, color="primary",
                               style={"backgroundColor":"var(--c-accent)","border":"none"}),
                ]
            ),
        ],
        id="coach-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="lg", fade=False
    ),

    # (Usuarios)
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Usuarios registrados")),
            dbc.ModalBody(html.Div(id="users-list-modal")),
            dbc.ModalFooter(dbc.Button("Cerrar", id="users-close", outline=True)),
        ],
        id="users-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="md", fade=False
    ),

    # (Acceso)
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Inicia sesión o regístrate")),
            dbc.ModalBody(
                [
                    html.P("inicia sesión o crea tu cuenta para acceder a más información.",
                           className="text-center muted"),
                    html.Div(
                        [
                            dbc.Button("Registrarse", id="access-register",
                                       style={"width": "200px"}, className="me-2"),
                            dbc.Button("Iniciar sesión", id="access-login",
                                       style={"width": "200px"}),
                        ],
                        className="d-flex justify-content-center align-items-center"
                    ),
                ]
            ),
            dbc.ModalFooter(dbc.Button("Cerrar", id="access-close", outline=True)),
        ],
        id="access-modal",
        is_open=False,
        centered=True, backdrop=True, keyboard=True, size="md", fade=False
    ),

    html.Div(style={"height": "90px"}),

    # ---- Contenedor de la página actual ----
    dbc.Container([html.Div(id="main-content", children=html.Div(className="surface"))], fluid=True),
])

# =======================
#  Router (cambia pestaña)
# =======================
@app.callback(
    Output("router", "data"),
    [
        Input("logo-btn", "n_clicks"),
        Input("metrics-btn", "n_clicks"),
        Input("questionnaire-btn", "n_clicks"),
        Input("rutinas-btn", "n_clicks"),
        Input("progresos-btn", "n_clicks"),
    ],
    State("session-user", "data"),
    prevent_initial_call=True
)
def update_router(n_logo, n_metrics, n_q, n_rut, n_prog, session):
    trig = dash.ctx.triggered_id

    # Logo: ir SIEMPRE a 'home' (ahí se decide por rol)
    if trig == "logo-btn":
        return {"view": "home"}

    # Si no hay sesión, nada (modal de acceso lo maneja auth.py)
    if not (session and isinstance(session, dict) and session.get("name")):
        raise PreventUpdate

    role = (session.get("role") or "").lower()

    # Solo atleta puede ir a estas vistas
    if trig == "metrics-btn" and (n_metrics or 0) > 0 and role == "atleta":
        return {"view": "monitor"}
    if trig == "questionnaire-btn" and (n_q or 0) > 0 and role == "atleta":
        return {"view": "questionnaire"}
    if trig == "rutinas-btn" and (n_rut or 0) > 0 and role == "atleta":
        return {"view": "routines"}
    if trig == "progresos-btn" and (n_prog or 0) > 0 and role == "atleta":
        return {"view": "progress"}

    raise PreventUpdate


@app.callback(
    Output("main-content", "children"),
    [Input("router", "data"), Input("q-reset", "data"), Input("session-user", "data")]
)
def render_main_content(router, qreset, session):
    view = (router or {}).get("view", "home")

    # Inicio: misma ventana al entrar y al pulsar el logo
    if view == "home":
        if session and (session.get("role") or "").lower() == "atleta":
            return athlete_home_layout()
        if session and (session.get("role") or "").lower() == "entrenador":
            return coach_home_layout()
        return html.Div(className="surface")  # sin sesión: vacío

    # Vistas de atleta
    if view == "monitor":
        return monitor_layout()
    if view == "questionnaire":
        return questionnaire_layout_view(reset_key=qreset)
    if view == "routines":
        return routines_layout()
    if view == "progress":
        return progress_layout()

    return html.Div(className="surface")


# =======================
#  Registrar callbacks de módulos
# =======================
register_auth_callbacks(app)              # login/registro/modales/limpieza
register_monitor_callbacks(app)           # ECG (atleta)
register_questionnaire_callbacks(app)     # Cuestionario (atleta)
register_coach_home_callbacks(app)        # Inicio entrenador (solo perfil)
register_athlete_home_callbacks(app)      # Inicio atleta (perfil)

if __name__ == "__main__":
    app.run(debug=True)
