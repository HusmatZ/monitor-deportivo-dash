from dash import dcc, html
import sqlite3

# Layout de cuestionario
questionnaire_layout = html.Div([
    html.Label("Nivel de fatiga (1-10):"),
    dcc.Slider(1, 10, 1, value=5, id="fatiga"),

    html.Label("Horas de sueño:"),
    dcc.Input(id="suenio", type="number", min=0, max=12, step=1, value=8),

    html.Label("Esfuerzo percibido (RPE, 1-10):"),
    dcc.Slider(1, 10, 1, value=5, id="rpe"),

    html.Br(),
    html.Button("Enviar", id="submit-questionnaire", n_clicks=0)
])

def save_questionnaire(fatiga, suenio, rpe):
    conn = sqlite3.connect("data/users.db")
    c = conn.cursor()
    c.execute("INSERT INTO questionnaires (user_id, fatiga, suenio, rpe) VALUES (?, ?, ?, ?)",
              (1, fatiga, suenio, rpe))  # por ahora asignamos user_id = 1 fijo
    conn.commit()
    conn.close()