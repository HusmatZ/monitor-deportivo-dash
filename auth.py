# auth.py
import re
import dash
from dash import html, dcc, no_update
from dash import Input, Output, State
from dash.dependencies import ALL
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import db

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PWD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")  # ≥8, 1 mayús, 1 minús, 1 número

def _navbar_content(session):
    if session and isinstance(session, dict) and session.get("name"):
        user_name = session["name"]
        return html.Div(
            [
                html.Div(f"Hola, {user_name}", className="me-3 fw-semibold"),
                dbc.DropdownMenu(
                    children=[
                        dbc.DropdownMenuItem("Ajustes", id={"type": "user-menu", "action": "settings"}),
                        dbc.DropdownMenuItem(divider=True),
                        dbc.DropdownMenuItem("Salir", id={"type": "user-menu", "action": "logout"}),
                    ],
                    label="",
                    caret=False,
                    align_end=True,
                    toggle_style={
                        "width": "40px",
                        "height": "40px",
                        "borderRadius": "50%",
                        "backgroundColor": "#e9ecef",
                        "border": "1px solid #ced4da"
                    },
                    toggle_class_name="d-flex align-items-center justify-content-center"
                )
            ],
            className="d-flex align-items-center"
        )
    return html.Div(
        [
            dbc.Button("Iniciar sesión", id="nav-login-btn", color="dark",
                       outline=True, size="md", className="fw-semibold mb-2",
                       style={"width": "200px"}),
            dbc.Button("Registrarse", id="nav-register-btn", color="dark",
                       outline=True, size="md", className="fw-semibold",
                       style={"width": "200px"}),
        ],
        className="d-flex flex-column"
    )

def register_auth_callbacks(app):
    # Navbar auth dinámico
    @app.callback(
        Output("navbar-auth", "children"),
        Input("session-user", "data")
    )
    def render_navbar_auth(session):
        return _navbar_content(session)

    # Modal acceso si no hay sesión
    @app.callback(
        Output("access-modal", "is_open"),
        [
            Input("metrics-btn", "n_clicks"),
            Input("questionnaire-btn", "n_clicks"),
            Input("rutinas-btn", "n_clicks"),
            Input("progresos-btn", "n_clicks"),
            Input("access-close", "n_clicks"),
        ],
        State("session-user", "data"),
        prevent_initial_call=True
    )
    def toggle_access_modal(n_metrics, n_q, n_rut, n_prog, n_close, session):
        if n_close:
            return False
        if any([n_metrics, n_q, n_rut, n_prog]) and not (session and session.get("name")):
            return True
        raise PreventUpdate

    # Abrir/cerrar login
    @app.callback(
        Output("login-modal", "is_open", allow_duplicate=True),
        [
            Input("nav-login-btn", "n_clicks"),
            Input("access-login", "n_clicks"),
            Input("login-close", "n_clicks"),
        ],
        prevent_initial_call=True
    )
    def toggle_login_modal(n_nav_login, n_access_login, n_close):
        if n_close:
            return False
        if n_nav_login or n_access_login:
            return True
        raise PreventUpdate

    # Abrir/cerrar registro
    @app.callback(
        Output("reg-modal", "is_open", allow_duplicate=True),
        [
            Input("nav-register-btn", "n_clicks"),
            Input("access-register", "n_clicks"),
            Input("reg-close", "n_clicks"),
            Input("ath-back", "n_clicks"),
            Input("coach-back", "n_clicks"),
        ],
        prevent_initial_call=True
    )
    def toggle_reg_modal(n_nav_reg, n_access_reg, n_close, n_ath_back, n_coach_back):
        trig = dash.ctx.triggered_id
        if trig in ("reg-close",):
            return False
        if trig in ("ath-back", "coach-back"):
            return True
        if n_nav_reg or n_access_reg:
            return True
        raise PreventUpdate

    # Usuarios: abrir/cerrar
    @app.callback(
        Output("users-modal", "is_open"),
        [Input("open-users", "n_clicks"), Input("users-close", "n_clicks")],
        prevent_initial_call=True
    )
    def toggle_users_modal(n_open, n_close):
        if n_close:
            return False
        if n_open:
            return True
        raise PreventUpdate

    # Listado de usuarios
    @app.callback(
        Output("users-list-modal", "children"),
        [Input("open-users", "n_clicks"), Input("ath-submit", "n_clicks"), Input("coach-submit", "n_clicks")],
        prevent_initial_call=True
    )
    def refresh_users_list(*_):
        users = db.get_users()
        if not users:
            return html.Div("Aún no hay usuarios.", className="muted")
        items = []
        for u in users:
            linea = f"{u.get('name') or '—'}  |  {u.get('email') or '—'}  |  {u.get('role') or '—'}  |  {u.get('country') or '—'}"
            items.append(html.Li(linea))
        return html.Ul(items, className="mb-0")

    # -------- LOGIN / LOGOUT --------
    @app.callback(
        [
            Output("login-feedback", "children"),
            Output("login-feedback", "is_open"),
            Output("session-user", "data", allow_duplicate=True),
            Output("login-modal", "is_open", allow_duplicate=True),
            Output("router", "data", allow_duplicate=True),
            Output("login-email", "value"),
            Output("login-password", "value"),
        ],
        [
            Input("login-submit", "n_clicks"),
            Input({"type": "user-menu", "action": ALL}, "n_clicks"),
        ],
        [
            State("login-email", "value"),
            State("login-password", "value"),
        ],
        prevent_initial_call=True
    )
    def login_logout(n_login, user_menu_clicks, email, pwd):
        trig = dash.ctx.triggered_id

        # Logout desde menú usuario
        if isinstance(trig, dict) and trig.get("type") == "user-menu":
            if trig.get("action") == "logout":
                return no_update, False, None, no_update, {"view": "home"}, no_update, no_update
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update

        # Login
        if trig == "login-submit":
            email_norm = (email or "").strip().lower()
            pwd_val = (pwd or "")

            if not email_norm or not pwd_val:
                return "Por favor, introduce correo y contraseña.", True, no_update, no_update, no_update, "", ""

            user = db.verify_login_email(email_norm, pwd_val)  # ahora usa LOWER(email)=?
            if user:
                try:
                    user["id_str"] = f"{int(user['id']):08d}"
                except Exception:
                    user["id_str"] = "--------"
                session_payload = {
                    "id": user["id"],
                    "id_str": user["id_str"],
                    "name": user["name"],
                    "email": user["email"],
                    "role": user["role"],
                    "country": user.get("country"),
                }
                return (f"✅ Bienvenido, {user['name']}.", True,
                        session_payload,
                        False, {"view": "home"}, "", "")
            else:
                return "❌ Credenciales incorrectas.", True, no_update, no_update, no_update, "", ""

        return no_update, no_update, no_update, no_update, no_update, no_update, no_update

    # Mostrar/ocultar VAS (Atleta)
    @app.callback(
        [Output("ath-vas-col", "style"),
         Output("ath-vas-label", "style")],
        Input("ath-molestias", "value")
    )
    def toggle_vas(mols):
        mols = mols or []
        show = any(m != "Ninguna" for m in mols)
        style = {"display": "block"} if show else {"display": "none"}
        return style, style

    # Continuar registro -> abrir perfil
    @app.callback(
        [
            Output("reg-feedback", "children"),
            Output("reg-feedback", "is_open"),
            Output("reg-feedback", "color"),
            Output("reg-base", "data"),
            Output("reg-modal", "is_open", allow_duplicate=True),
            Output("athlete-modal", "is_open", allow_duplicate=True),
            Output("coach-modal", "is_open", allow_duplicate=True),
            # limpiar base
            Output("reg-email", "value"),
            Output("reg-name", "value"),
            Output("reg-country", "value"),
            Output("reg-password", "value"),
            Output("reg-password2", "value"),
            Output("reg-accepts", "value"),
            Output("reg-role", "value"),
        ],
        Input("reg-continue", "n_clicks"),
        [
            State("reg-email", "value"),
            State("reg-password", "value"),
            State("reg-password2", "value"),
            State("reg-name", "value"),
            State("reg-country", "value"),
            State("reg-accepts", "value"),
            State("reg-role", "value"),
        ],
        prevent_initial_call=True
    )
    def continue_to_profile(n, email, pwd1, pwd2, name, country, accepts, role):
        errors = []
        if not email or not EMAIL_RE.match(email): errors.append("Email inválido.")
        if not pwd1 or not PWD_RE.match(pwd1): errors.append("La contraseña no cumple los requisitos.")
        if pwd1 != pwd2: errors.append("Las contraseñas no coinciden.")
        if not name or not (2 <= len(name.strip()) <= 50): errors.append("Nombre: longitud 2–50 caracteres.")
        if not country: errors.append("Selecciona un país (lista ISO).")
        accepts = accepts or []
        if "terms" not in accepts: errors.append("Debes aceptar Términos y Privacidad.")
        if "disclaimer" not in accepts: errors.append("Debes declarar que no es dispositivo médico.")
        if (role or "") not in ["atleta", "entrenador"]: errors.append("Selecciona un rol inicial (Atleta / Entrenador).")

        if errors:
            return html.Ul([html.Li(e) for e in errors]), True, "danger", no_update, True, False, False, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        base = {
            "email": (email or "").strip().lower(),
            "password": pwd1,
            "name": name.strip(),
            "country": country,
            "terms": "terms" in accepts,
            "disclaimer": "disclaimer" in accepts,
            "role": role
        }
        return "", False, "danger", base, False, role == "atleta", role == "entrenador", "", "", None, "", "", [], None

    # Botón atrás perfiles
    @app.callback(
        Output("athlete-modal", "is_open", allow_duplicate=True),
        Input("ath-back", "n_clicks"),
        prevent_initial_call=True
    )
    def athlete_back(n):
        if n:
            return False
        raise PreventUpdate

    @app.callback(
        Output("coach-modal", "is_open", allow_duplicate=True),
        Input("coach-back", "n_clicks"),
        prevent_initial_call=True
    )
    def coach_back(n):
        if n:
            return False
        raise PreventUpdate

    # Crear cuenta ATLETA
    @app.callback(
        [
            Output("ath-feedback", "children"),
            Output("ath-feedback", "is_open"),
            Output("ath-feedback", "color"),
            Output("athlete-modal", "is_open", allow_duplicate=True),
            Output("q-reset", "data", allow_duplicate=True),
            Output("ath-uso", "value"),
            Output("ath-nivel", "value"),
            Output("ath-freq", "value"),
            Output("ath-molestias", "value"),
            Output("ath-dolor", "value"),
            Output("ath-box", "value"),
            Output("ath-altura", "value"),
            Output("ath-peso", "value"),
            Output("reg-base", "data", allow_duplicate=True),
            Output("session-user", "data", allow_duplicate=True),
            Output("router", "data", allow_duplicate=True),
        ],
        Input("ath-submit", "n_clicks"),
        [
            State("reg-base", "data"),
            State("ath-uso", "value"),
            State("ath-nivel", "value"),
            State("ath-freq", "value"),
            State("ath-molestias", "value"),
            State("ath-dolor", "value"),
            State("ath-box", "value"),
            State("ath-altura", "value"),
            State("ath-peso", "value"),
            State("q-reset", "data"),
        ],
        prevent_initial_call=True
    )
    def athlete_submit(n, base, uso, nivel, freq, mols, vas, box, altura, peso, qreset):
        if not base:
            return "❌ Falta la información base del registro.", True, "danger", no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        errors = []
        if not uso: errors.append("Atleta: 'Rol de uso' es obligatorio.")
        if not nivel: errors.append("Atleta: 'Nivel de experiencia' es obligatorio.")
        if not freq: errors.append("Atleta: 'Frecuencia semanal' es obligatoria.")
        mols = mols or []
        if any(m != "Ninguna" for m in mols) and vas is None:
            errors.append("Atleta: indica intensidad de dolor (VAS).")
        if box and not (2 <= len(box.strip()) <= 50):
            errors.append("Atleta: Box/Gimnasio debe tener 2–50 caracteres.")
        if altura is not None:
            try:
                if not (80 <= float(altura) <= 250): errors.append("Atleta: Altura fuera de rango (80–250 cm).")
            except: errors.append("Atleta: Altura inválida.")
        if peso is not None:
            try:
                if not (30 <= float(peso) <= 250): errors.append("Atleta: Peso fuera de rango (30–250 kg).")
            except: errors.append("Atleta: Peso inválida.")
        if errors:
            return html.Ul([html.Li(e) for e in errors]), True, "danger", no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        try:
            new_id = db.create_user(
                name=base["name"],
                email=base["email"],
                password=base["password"],
                country=base["country"],
                role="atleta",
                terms_accepted=base["terms"],
                disclaimer_accepted=base["disclaimer"],
                ath_uso=uso, ath_nivel=nivel, ath_freq=freq,
                ath_molestias=mols, ath_vas=(int(vas) if vas is not None else None),
                ath_box=(box.strip() if box else None),
                ath_altura=(float(altura) if altura is not None else None),
                ath_peso=(float(peso) if peso is not None else None),
            )
            id_str = f"{int(new_id):08d}"
            session_payload = {
                "id": new_id, "id_str": id_str,
                "name": base["name"], "email": base["email"],
                "role": "atleta", "country": base["country"]
            }
            return (
                "✅ Cuenta creada correctamente.", True, "success", False, (qreset or 0) + 1,
                None, None, None, [], 0, "", None, None,
                None,
                session_payload, {"view": "home"}
            )
        except ValueError as e:
            return f"❌ {str(e)}", True, "danger", no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        except Exception:
            return "❌ Error interno al registrar. Revisa la consola.", True, "danger", no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

    # Crear cuenta ENTRENADOR
    @app.callback(
        [
            Output("coach-feedback", "children"),
            Output("coach-feedback", "is_open"),
            Output("coach-feedback", "color"),
            Output("coach-modal", "is_open", allow_duplicate=True),
            Output("q-reset", "data", allow_duplicate=True),
            Output("coach-especialidad", "value"),
            Output("coach-anios", "value"),
            Output("coach-centro", "value"),
            Output("coach-ubicacion", "value"),
            Output("coach-modalidad", "value"),
            Output("coach-disponibilidad", "value"),
            Output("coach-cred", "value"),
            Output("reg-base", "data", allow_duplicate=True),
            Output("session-user", "data", allow_duplicate=True),
            Output("router", "data", allow_duplicate=True),
        ],
        Input("coach-submit", "n_clicks"),
        [
            State("reg-base", "data"),
            State("coach-especialidad", "value"),
            State("coach-anios", "value"),
            State("coach-centro", "value"),
            State("coach-ubicacion", "value"),
            State("coach-modalidad", "value"),
            State("coach-disponibilidad", "value"),
            State("coach-cred", "value"),
            State("q-reset", "data"),
        ],
        prevent_initial_call=True
    )
    def coach_submit(n, base, esp, anios, centro, ubicacion, modalidad, disponibilidad, cred, qreset):
        if not base:
            return "❌ Falta la información base del registro.", True, "danger", no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        errors = []
        if not (esp and len(esp) > 0):
            errors.append("Entrenador: 'Especialidad' es obligatoria.")
        if not anios:
            errors.append("Entrenador: 'Años de experiencia' es obligatorio.")
        if not (modalidad and len(modalidad) > 0):
            errors.append("Entrenador: 'Modalidad de servicio' es obligatoria.")
        if not disponibilidad:
            errors.append("Entrenador: 'Disponibilidad semanal' es obligatoria.")
        if centro and not (2 <= len(centro.strip()) <= 50):
            errors.append("Entrenador: Centro de trabajo debe tener 2–50 caracteres.")
        if errors:
            return html.Ul([html.Li(e) for e in errors]), True, "danger", no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        try:
            new_id = db.create_user(
                name=base["name"],
                email=base["email"],
                password=base["password"],
                country=base["country"],
                role="entrenador",
                terms_accepted=base["terms"],
                disclaimer_accepted=base["disclaimer"],
                co_especialidad=esp, co_anios=anios,
                co_centro=(centro.strip() if centro else None),
                co_ubicacion=(ubicacion.strip() if ubicacion else None),
                co_modalidad=modalidad,
                co_disponibilidad=disponibilidad,
                co_cred=bool(cred)
            )
            id_str = f"{int(new_id):08d}"
            session_payload = {
                "id": new_id, "id_str": id_str,
                "name": base["name"], "email": base["email"],
                "role": "entrenador", "country": base["country"]
            }
            return (
                "✅ Cuenta creada correctamente.", True, "success", False, (qreset or 0) + 1,
                [], None, "", "", [], None, False,
                None,
                session_payload, {"view": "home"}
            )
        except ValueError as e:
            return f"❌ {str(e)}", True, "danger", no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
        except Exception:
            return "❌ Error interno al registrar. Revisa la consola.", True, "danger", no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update
