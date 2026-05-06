import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime, date, timedelta

DB_PATH = Path(__file__).parent / "axisfit.db"

# -------------------------
# Helpers de conexión
# -------------------------
def _connect():
    """Abre conexión a SQLite con pragmas recomendados para ingestión de muestras (RAW)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Pragmas por conexión (WAL + rendimiento). Si algo falla, seguimos con defaults.
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA busy_timeout=3000;")
    except Exception:
        pass

    return conn


def init_db():
    # Windows puede denegar `touch(exist_ok=True)` si SQLite ya tiene el
    # archivo abierto o bloqueado por el servidor Dash. No necesitamos tocar
    # mtime en cada arranque: sqlite3 crea el archivo al conectar si no existe.
    if not DB_PATH.exists():
        DB_PATH.touch(exist_ok=True)
    with _connect() as conn:
        _ensure_schema(conn)


def _ensure_schema(conn: sqlite3.Connection):
    cur = conn.cursor()

    # Tabla principal de usuarios
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT,
            email             TEXT UNIQUE,
            password          TEXT,
            country           TEXT,
            role              TEXT, -- 'atleta' | 'entrenador'
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,

            -- Campos ATLETA
            ath_uso           TEXT,
            ath_nivel         TEXT,
            ath_freq          TEXT,
            ath_molestias     TEXT,   -- JSON list
            ath_vas           INTEGER,
            ath_box           TEXT,
            ath_altura        REAL,
            ath_peso          REAL,

            -- Campos ENTRENADOR
            co_especialidad   TEXT,   -- JSON list
            co_anios          TEXT,
            co_centro         TEXT,
            co_ubicacion      TEXT,
            co_modalidad      TEXT,
            co_disponibilidad TEXT,
            co_cred           INTEGER -- 0/1
        )
        """
    )

    # Enlaces entrenador <-> atleta
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS coach_athlete_links (
            coach_id    INTEGER NOT NULL,
            athlete_id  INTEGER NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (coach_id, athlete_id),
            FOREIGN KEY (coach_id)   REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (athlete_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ---- NUEVAS TABLAS PARA INICIO DEL ATLETA ----
    # Workouts (sesiones) y sus ítems
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS workouts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL,
            start_dt    DATETIME,           -- fecha/hora próxima sesión
            location    TEXT,               -- box / ubicación
            title       TEXT,
            status      TEXT,               -- planned / done / skipped
            FOREIGN KEY (athlete_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS workout_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_id  INTEGER NOT NULL,
            name        TEXT,
            sets        INTEGER,
            reps        TEXT,               -- '10' o '8-10' o '3-5 reps'
            rpe_target  TEXT,
            FOREIGN KEY (workout_id) REFERENCES workouts(id) ON DELETE CASCADE
        )
        """
    )

    # Notas del día
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS athlete_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL,
            note_date   DATE NOT NULL,
            note        TEXT,
            UNIQUE (athlete_id, note_date),
            FOREIGN KEY (athlete_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # Mensajes coach -> atleta
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            coach_id    INTEGER NOT NULL,
            athlete_id  INTEGER NOT NULL,
            text        TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (coach_id)   REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (athlete_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # Check-ins diarios (para streak)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_checkins (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER NOT NULL,
            check_date  DATE NOT NULL,
            status      INTEGER DEFAULT 1,  -- 1=hecho
            note        TEXT,
            UNIQUE(athlete_id, check_date),
            FOREIGN KEY (athlete_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # Resumen de recuperación (opcional)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS recovery (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id      INTEGER NOT NULL,
            rec_date        DATE NOT NULL,
            load7           REAL,
            recovery_score  INTEGER,
            sleep_hours     REAL,
            UNIQUE(athlete_id, rec_date),
            FOREIGN KEY (athlete_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # -------------------------
    # Cuestionario diario (MVP legacy)
    # -------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_daily (
            athlete_id  INTEGER NOT NULL,
            q_date      TEXT NOT NULL,      -- YYYY-MM-DD
            fatiga      INTEGER,
            suenio      INTEGER,
            rpe         INTEGER,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME,
            PRIMARY KEY (athlete_id, q_date),
            FOREIGN KEY (athlete_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # -------------------------
    # Cuestionarios (Wizard v1) + Baseline + Settings por usuario
    # -------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS questionnaire_sessions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            type                TEXT NOT NULL,  -- initial_full | daily_checkin
            started_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at        DATETIME,
            payload_json        TEXT,           -- wizard completo (JSON)
            risk_index          REAL,
            recommendation_json TEXT,           -- recomendaciones/CTA (JSON)
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baseline_tests (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL,
            sensor_session_id INTEGER,          -- FK opcional a sensor_sessions(kind='baseline')
            baseline_json     TEXT,             -- baseline agregado (JSON)
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (sensor_session_id) REFERENCES sensor_sessions(id) ON DELETE SET NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_posture_settings (
            user_id         INTEGER PRIMARY KEY,
            thresholds_json TEXT,               -- JSON con umbrales/sensibilidad por segmento
            updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # -------------------------
    # Sensores (RAW 50 Hz) + Summary
    # -------------------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            kind       TEXT NOT NULL,     -- monitor | routine | baseline
            mode       TEXT,              -- desk | train
            sport      TEXT,              -- gym | crossfit
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at   DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_samples_raw (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id   INTEGER NOT NULL,
            ts_ms        INTEGER NOT NULL,  -- host time (ms) unificado
            T_pitch      REAL,
            T_roll       REAL,
            T_yaw        REAL,
            L_pitch      REAL,
            L_roll       REAL,
            L_yaw        REAL,
            thor_zone    TEXT,              -- green | yellow | red
            lum_zone     TEXT,              -- green | yellow | red
            comp_index   REAL,              -- 0..100
            T_imu_ts_ms  INTEGER,           -- timestamp del IMU torácico (su propio reloj)
            L_imu_ts_ms  INTEGER,           -- timestamp del IMU lumbar (su propio reloj)
            FOREIGN KEY (session_id) REFERENCES sensor_sessions(id) ON DELETE CASCADE
        )
        """
    )

    # Agregado 1 Hz para consultas rápidas (progreso / UI)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_samples_agg (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            ts_s       INTEGER NOT NULL, -- host time (s)
            T_pitch    REAL,
            L_pitch    REAL,
            thor_zone  TEXT,
            lum_zone   TEXT,
            comp_index REAL,
            FOREIGN KEY (session_id) REFERENCES sensor_sessions(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS session_summary (
            session_id    INTEGER PRIMARY KEY,
            duration_s    REAL,
            thor_red_s    REAL,
            lum_red_s     REAL,
            alerts_count  INTEGER,
            comp_avg      REAL,
            comp_peak     REAL,
            risk_index    REAL,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sensor_sessions(id) ON DELETE CASCADE
        )
        """
    )

    # ✅ FIX: daily_summary debe tener alerts_count porque questionnaire_view lo lee.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_summary (
            user_id        INTEGER NOT NULL,
            day            TEXT NOT NULL, -- YYYY-MM-DD
            sessions_count INTEGER,
            duration_s     REAL,
            thor_red_s     REAL,
            lum_red_s      REAL,
            alerts_count   INTEGER,
            comp_avg       REAL,
            comp_peak      REAL,
            risk_index_avg REAL,
            risk_index_max REAL,
            updated_at     DATETIME,
            PRIMARY KEY (user_id, day),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ============================================================
    # ✅ PASO 1 (Rutinas) — Tablas MVP (aún sin modo RUN)
    # ============================================================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS routine_sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL,
            day               TEXT NOT NULL,             -- YYYY-MM-DD
            plan_json         TEXT,                      -- rutina recomendada (JSON)
            started_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at          DATETIME,
            score_avg         REAL,
            notes             TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exercise_sets (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            routine_session_id  INTEGER NOT NULL,
            exercise_name       TEXT NOT NULL,
            set_index           INTEGER NOT NULL,
            reps_target         INTEGER,
            reps_valid          INTEGER,
            score_avg           REAL,
            thor_red_s          REAL,
            lum_red_s           REAL,
            comp_avg            REAL,
            comp_peak           REAL,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (routine_session_id) REFERENCES routine_sessions(id) ON DELETE CASCADE
        )
        """
    )

    # Índices (velocidad)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_sessions_user_start ON sensor_sessions(user_id, started_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_samples_raw_session_ts ON sensor_samples_raw(session_id, ts_ms)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_samples_agg_session_ts ON sensor_samples_agg(session_id, ts_s)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_q_sessions_user_completed ON questionnaire_sessions(user_id, completed_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_baseline_user_created ON baseline_tests(user_id, created_at)")

    # ✅ Rutinas índices
    cur.execute("CREATE INDEX IF NOT EXISTS idx_routine_sessions_user_day ON routine_sessions(user_id, day)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_exercise_sets_routine ON exercise_sets(routine_session_id, created_at)")

    # Backward compatible: añade columnas nuevas si faltan (por si el DB ya existía)
    def _ensure_columns(table: str, cols):
        try:
            existing = {r["name"] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, ddl in cols:
                if name not in existing:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        except Exception:
            pass

    _ensure_columns("questionnaire_daily", [("updated_at", "DATETIME")])
    _ensure_columns("sensor_samples_raw", [("T_imu_ts_ms", "INTEGER"), ("L_imu_ts_ms", "INTEGER")])
    _ensure_columns("daily_summary", [("alerts_count", "INTEGER")])  # ✅ FIX
    _ensure_columns(
        "sensor_sessions",
        [
            ("planned_session_name", "TEXT"),
            ("questionnaire_session_id", "INTEGER"),
            ("routine_session_id", "INTEGER"),
            ("baseline_test_id", "INTEGER"),
            ("context_json", "TEXT"),
        ],
    )

    existing_cols = {r["name"] for r in cur.execute("PRAGMA table_info(users)").fetchall()}

    def _add_col(name, ddl):
        if name not in existing_cols:
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
            except Exception:
                pass

    _add_col("terms_accepted",   "INTEGER")
    _add_col("disclaimer_accepted","INTEGER")
    _add_col("ath_uso",           "TEXT")
    _add_col("ath_nivel",         "TEXT")
    _add_col("ath_freq",          "TEXT")
    _add_col("ath_molestias",     "TEXT")
    _add_col("ath_vas",           "INTEGER")
    _add_col("ath_box",           "TEXT")
    _add_col("ath_altura",        "REAL")
    _add_col("ath_peso",          "REAL")
    _add_col("co_especialidad",   "TEXT")
    _add_col("co_anios",          "TEXT")
    _add_col("co_centro",         "TEXT")
    _add_col("co_ubicacion",      "TEXT")
    _add_col("co_modalidad",      "TEXT")
    _add_col("co_disponibilidad", "TEXT")
    _add_col("co_cred",           "INTEGER")

    conn.commit()


# -------------------------
# Utilidades internas
# -------------------------
def _row_to_dict(row: sqlite3.Row) -> Dict:
    if row is None:
        return {}
    d = dict(row)
    if "co_cred" in d and d["co_cred"] is not None:
        d["co_cred"] = bool(d["co_cred"])
    for k in ("ath_molestias", "co_especialidad", "co_modalidad"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


def _json_dumps_safe(obj) -> str:
    try:
        return json.dumps(obj if obj is not None else {}, ensure_ascii=False)
    except Exception:
        return json.dumps({}, ensure_ascii=False)


def _json_loads_safe(s: Optional[str]):
    if not s:
        return None
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return None


def _get_user(conn: sqlite3.Connection, user_id: int) -> Optional[Dict]:
    r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_dict(r) if r else None


def _get_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[Dict]:
    email_norm = (email or "").strip().lower()
    r = conn.execute(
        "SELECT * FROM users WHERE LOWER(email) = ?",
        (email_norm,),
    ).fetchone()
    return _row_to_dict(r) if r else None


# -------------------------
# Usuarios
# -------------------------
def get_user_by_id(user_id: int) -> Optional[Dict]:
    with _connect() as conn:
        r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _row_to_dict(r) if r else None


def user_is_coach(user_id: int) -> bool:
    with _connect() as conn:
        r = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        return bool(r and (r["role"] or "").lower() == "entrenador")


def get_users() -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, email, role, country, created_at FROM users ORDER BY id DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def verify_login_email(email: str, password: str) -> Optional[Dict]:
    """
    Verifica el login por email (case-insensitive) y password en texto plano.
    """
    email_norm = (email or "").strip().lower()
    with _connect() as conn:
        r = conn.execute(
            "SELECT id, name, email, role, country FROM users "
            "WHERE LOWER(email)=? AND password=?",
            (email_norm, password),
        ).fetchone()
        return _row_to_dict(r) if r else None


# -------------------------
# Usuarios - creación (Sprint 0)
# -------------------------
def create_user(
    *,
    name: str,
    email: str,
    password: str,
    country: str,
    role: str,
    terms_accepted: bool = False,
    disclaimer_accepted: bool = False,
    # Campos atleta
    ath_uso: Optional[str] = None,
    ath_nivel: Optional[str] = None,
    ath_freq: Optional[str] = None,
    ath_molestias=None,
    ath_vas: Optional[int] = None,
    ath_box: Optional[str] = None,
    ath_altura: Optional[float] = None,
    ath_peso: Optional[float] = None,
    # Campos entrenador
    co_especialidad=None,
    co_anios: Optional[str] = None,
    co_centro: Optional[str] = None,
    co_ubicacion: Optional[str] = None,
    co_modalidad=None,
    co_disponibilidad: Optional[str] = None,
    co_cred: bool = False,
) -> int:
    """Crea un usuario (atleta o entrenador) y devuelve su id.

    - Normaliza email a minúsculas.
    - Guarda listas como JSON.
    - Si el email ya existe lanza ValueError.
    """

    role_norm = (role or "").strip().lower()
    if role_norm not in {"atleta", "entrenador"}:
        raise ValueError("Rol inválido. Usa 'atleta' o 'entrenador'.")

    email_norm = (email or "").strip().lower()
    if not email_norm:
        raise ValueError("Email inválido.")

    def _dump_list(x) -> str:
        if x is None:
            return json.dumps([])
        if isinstance(x, str):
            parts = [p.strip() for p in x.split(",") if p.strip()]
            return json.dumps(parts)
        if isinstance(x, (list, tuple)):
            return json.dumps(list(x))
        return json.dumps([x])

    with _connect() as conn:
        if _get_user_by_email(conn, email_norm):
            raise ValueError("Email ya registrado.")

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (
                name, email, password, country, role,
                terms_accepted, disclaimer_accepted,
                ath_uso, ath_nivel, ath_freq, ath_molestias, ath_vas, ath_box, ath_altura, ath_peso,
                co_especialidad, co_anios, co_centro, co_ubicacion, co_modalidad, co_disponibilidad, co_cred
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                (name or "").strip() or None,
                email_norm,
                password,
                (country or "").strip() or None,
                role_norm,
                int(bool(terms_accepted)),
                int(bool(disclaimer_accepted)),
                ath_uso,
                ath_nivel,
                ath_freq,
                _dump_list(ath_molestias),
                ath_vas,
                (ath_box.strip() if isinstance(ath_box, str) and ath_box.strip() else None),
                ath_altura,
                ath_peso,
                _dump_list(co_especialidad),
                co_anios,
                (co_centro.strip() if isinstance(co_centro, str) and co_centro.strip() else None),
                (co_ubicacion.strip() if isinstance(co_ubicacion, str) and co_ubicacion.strip() else None),
                _dump_list(co_modalidad),
                co_disponibilidad,
                int(bool(co_cred)),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


# -------------------------
# Cuestionario diario legacy (NO USAR en wizard)
# -------------------------
def upsert_questionnaire_daily(
    *,
    athlete_id: int,
    fatiga: int,
    suenio: int,
    rpe: int,
    q_date: Optional[date] = None,
) -> None:
    """Legacy Sprint 0 (NO USAR en wizard)."""
    if not isinstance(athlete_id, int):
        raise ValueError("athlete_id inválido")

    d = (q_date or date.today()).isoformat()

    def _to_int(v, lo=0, hi=10) -> Optional[int]:
        if v is None:
            return None
        try:
            iv = int(v)
        except Exception:
            return None
        return max(lo, min(hi, iv))

    fat = _to_int(fatiga)
    sue = _to_int(suenio)
    rp = _to_int(rpe)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO questionnaire_daily(athlete_id, q_date, fatiga, suenio, rpe, updated_at)
            VALUES (?,?,?,?,?, CURRENT_TIMESTAMP)
            ON CONFLICT(athlete_id, q_date)
            DO UPDATE SET
                fatiga=excluded.fatiga,
                suenio=excluded.suenio,
                rpe=excluded.rpe,
                updated_at=CURRENT_TIMESTAMP
            """,
            (athlete_id, d, fat, sue, rp),
        )
        conn.commit()


# -------------------------
# Enlaces Coach <-> Athlete
# -------------------------
def link_coach_athlete(*, coach_id: int, athlete_id: int) -> None:
    if not isinstance(coach_id, int) or not isinstance(athlete_id, int):
        raise ValueError("IDs inválidos.")
    with _connect() as conn:
        coach = _get_user(conn, coach_id)
        athlete = _get_user(conn, athlete_id)
        if not coach:
            raise ValueError("Entrenador no encontrado.")
        if not athlete:
            raise ValueError("Atleta no encontrado.")
        if (coach.get("role") or "").lower() != "entrenador":
            raise ValueError("El usuario no es entrenador.")

        existing = conn.execute(
            "SELECT 1 FROM coach_athlete_links WHERE coach_id=? AND athlete_id=?",
            (coach_id, athlete_id),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO coach_athlete_links(coach_athlete_links.coach_id, coach_athlete_links.athlete_id) VALUES(?, ?)",
                (coach_id, athlete_id),
            )
            conn.commit()


def unlink_coach_athlete(*, coach_id: int, athlete_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM coach_athlete_links WHERE coach_id=? AND athlete_id=?",
            (coach_id, athlete_id),
        )
        conn.commit()


def get_coaches_for_athlete_by_id(athlete_id: int) -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.name, u.email, u.role,
                   u.co_especialidad, u.co_anios, u.co_centro,
                   u.co_ubicacion, u.co_modalidad, u.co_disponibilidad, u.co_cred
            FROM coach_athlete_links l
            JOIN users u ON u.id = l.coach_id
            WHERE l.athlete_id = ?
            ORDER BY u.name
            """,
            (athlete_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


# -------------------------
# Próxima sesión
# -------------------------
def get_next_session_for_athlete(athlete_id: int) -> Optional[Dict]:
    with _connect() as conn:
        r = conn.execute(
            """
            SELECT * FROM workouts
            WHERE athlete_id=? AND (start_dt IS NOT NULL)
            ORDER BY datetime(start_dt) ASC
            """,
            (athlete_id,),
        ).fetchall()
        now = datetime.now()
        candidates = [dict(x) for x in r]
        future = [
            x
            for x in candidates
            if x.get("start_dt") and datetime.fromisoformat(x["start_dt"]) >= now
        ]
        chosen = future[0] if future else (candidates[0] if candidates else None)
        return chosen


# -------------------------
# Plan del día (por fecha)
# -------------------------
def get_plan_for_date(athlete_id: int, day) -> List[Dict]:
    if isinstance(day, date):
        day_str = day.isoformat()
    else:
        day_str = str(day)
    with _connect() as conn:
        w = conn.execute(
            "SELECT id FROM workouts WHERE athlete_id=? AND date(start_dt)=?",
            (athlete_id, day_str),
        ).fetchone()
        if not w:
            return []
        wid = w["id"]
        items = conn.execute(
            "SELECT name, sets, reps, rpe_target FROM workout_items WHERE workout_id=? ORDER BY id",
            (wid,),
        ).fetchall()
        return [dict(x) for x in items]


def get_plan_for_today(athlete_id: int) -> List[Dict]:
    return get_plan_for_date(athlete_id, date.today())


# -------------------------
# Notas del día
# -------------------------
def get_note_for_date(athlete_id: int, day) -> str:
    if isinstance(day, date):
        day_str = day.isoformat()
    else:
        day_str = str(day)
    with _connect() as conn:
        r = conn.execute(
            "SELECT note FROM athlete_notes WHERE athlete_id=? AND note_date=?",
            (athlete_id, day_str),
        ).fetchone()
        return r["note"] if r and r["note"] else ""


def get_note_for_today(athlete_id: int) -> str:
    return get_note_for_date(athlete_id, date.today())


def upsert_note_for_date(athlete_id: int, day, note: str) -> None:
    if isinstance(day, date):
        day_str = day.isoformat()
    else:
        day_str = str(day)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO athlete_notes(athlete_id, note_date, note)
            VALUES (?, ?, ?)
            ON CONFLICT(athlete_id, note_date)
            DO UPDATE SET note=excluded.note
            """,
            (athlete_id, day_str, note or ""),
        )
        conn.commit()


def upsert_note_for_today(athlete_id: int, note: str) -> None:
    upsert_note_for_date(athlete_id, date.today(), note)


# -------------------------
# Recuperación & Streak
# -------------------------
def get_recovery_summary(athlete_id: int) -> Optional[Dict]:
    with _connect() as conn:
        r = conn.execute(
            "SELECT * FROM recovery WHERE athlete_id=? ORDER BY date(rec_date) DESC LIMIT 1",
            (athlete_id,),
        ).fetchone()
        return dict(r) if r else None


def get_streak(athlete_id: int) -> int:
    with _connect() as conn:
        d = date.today()
        streak = 0
        while True:
            r = conn.execute(
                "SELECT status FROM daily_checkins WHERE athlete_id=? AND check_date=?",
                (athlete_id, d.isoformat()),
            ).fetchone()
            if not r or not r["status"]:
                break
            streak += 1
            d = d - timedelta(days=1)
        return streak


# -------------------------
# Mensajes del coach
# -------------------------
def get_latest_messages_for_athlete(athlete_id: int, limit: int = 3) -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.text, m.created_at, u.name as coach_name
            FROM messages m
            JOIN users u ON u.id = m.coach_id
            WHERE m.athlete_id=?
            ORDER BY datetime(m.created_at) DESC
            LIMIT ?
            """,
            (athlete_id, int(limit)),
        ).fetchall()
        return [dict(x) for x in rows]


def get_messages_history_for_athlete(athlete_id: int, limit: int = 50) -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.text, m.created_at, u.name as coach_name
            FROM messages m
            JOIN users u ON u.id = m.coach_id
            WHERE m.athlete_id=?
            ORDER BY datetime(m.created_at) DESC
            LIMIT ?
            """,
            (athlete_id, int(limit)),
        ).fetchall()
        return [dict(x) for x in rows]


def get_messages_between(athlete_id: int, coach_id: int, limit: int = 50) -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.text, m.created_at, u.name as coach_name
            FROM messages m
            JOIN users u ON u.id = m.coach_id
            WHERE m.athlete_id=? AND m.coach_id=?
            ORDER BY datetime(m.created_at) DESC
            LIMIT ?
            """,
            (athlete_id, coach_id, int(limit)),
        ).fetchall()
        return [dict(x) for x in rows]


# -------------------------
# Perfil - completitud
# -------------------------
def get_profile_completion(athlete_id: int) -> Tuple[int, List[str]]:
    with _connect() as conn:
        r = conn.execute(
            "SELECT ath_altura, ath_peso, ath_box, ath_nivel FROM users WHERE id=?",
            (athlete_id,),
        ).fetchone()
        if not r:
            return 0, ["perfil"]
        have = {
            "ath_altura": bool(r["ath_altura"]),
            "ath_peso": bool(r["ath_peso"]),
            "ath_box": bool(r["ath_box"]),
            "ath_nivel": bool(r["ath_nivel"]),
        }
        total = len(have)
        pct = round(100 * sum(1 for v in have.values() if v) / max(1, total))
        missing = [k for k, v in have.items() if not v]
        return pct, missing


# -------------------------
# Seed demo (opcional)
# -------------------------
def seed_demo_if_empty(athlete_id: int):
    with _connect() as conn:
        has_any = conn.execute(
            "SELECT 1 FROM workouts WHERE athlete_id=? LIMIT 1",
            (athlete_id,),
        ).fetchone()
        if has_any:
            return

        start = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        conn.execute(
            """
            INSERT INTO workouts(athlete_id, start_dt, location, title, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (athlete_id, start.isoformat(timespec="minutes"), "Box Central", "Full Body A", "planned"),
        )
        wid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        items = [
            ("Back Squat", 5, "5", "7"),
            ("Bench Press", 5, "5", "7"),
            ("Row", 4, "10", "7-8"),
        ]
        for name, sets, reps, rpe in items:
            conn.execute(
                "INSERT INTO workout_items(workout_id,name,sets,reps,rpe_target) VALUES(?,?,?,?,?)",
                (wid, name, sets, reps, rpe),
            )
        conn.commit()


# -------------------------
# Sensores: sesiones + RAW + summary
# -------------------------
def start_sensor_session(
    *,
    user_id: int,
    kind: str,
    mode: Optional[str] = None,
    sport: Optional[str] = None,
    started_at: Optional[datetime] = None,
    planned_session_name: Optional[str] = None,
    questionnaire_session_id: Optional[int] = None,
    routine_session_id: Optional[int] = None,
    baseline_test_id: Optional[int] = None,
    context_json: Optional[Dict] = None,
) -> int:
    if not isinstance(user_id, int):
        raise ValueError("user_id inválido")
    kind = (kind or "").strip()
    if kind not in {"monitor", "routine", "baseline"}:
        raise ValueError("kind inválido (monitor|routine|baseline)")

    sa = (started_at or datetime.now()).isoformat(timespec="seconds")

    qsid = None
    rsid = None
    bsid = None
    try:
        if questionnaire_session_id is not None:
            qsid = int(questionnaire_session_id)
    except Exception:
        qsid = None
    try:
        if routine_session_id is not None:
            rsid = int(routine_session_id)
    except Exception:
        rsid = None
    try:
        if baseline_test_id is not None:
            bsid = int(baseline_test_id)
    except Exception:
        bsid = None

    ctx_json = _json_dumps_safe(context_json if isinstance(context_json, dict) else {})

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO sensor_sessions(
                user_id, kind, mode, sport,
                planned_session_name, questionnaire_session_id, routine_session_id, baseline_test_id, context_json,
                started_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                kind,
                mode,
                sport,
                (planned_session_name or None),
                qsid,
                rsid,
                bsid,
                ctx_json,
                sa,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def end_sensor_session(*, session_id: int, ended_at: Optional[datetime] = None) -> None:
    if not isinstance(session_id, int):
        raise ValueError("session_id inválido")
    ea = (ended_at or datetime.now()).isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "UPDATE sensor_sessions SET ended_at=? WHERE id=?",
            (ea, session_id),
        )
        conn.commit()


def insert_sensor_samples_raw_batch(*, session_id: int, rows: List[Tuple]) -> None:
    if not rows:
        return
    if not isinstance(session_id, int):
        raise ValueError("session_id inválido")

    sql = """
        INSERT INTO sensor_samples_raw(
            session_id, ts_ms,
            T_pitch, T_roll, T_yaw,
            L_pitch, L_roll, L_yaw,
            thor_zone, lum_zone,
            comp_index,
            T_imu_ts_ms, L_imu_ts_ms
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with _connect() as conn:
        conn.executemany(sql, rows)
        conn.commit()


def insert_sensor_samples_agg_batch(*, session_id: int, rows: List[Tuple]) -> None:
    if not rows:
        return
    if not isinstance(session_id, int):
        raise ValueError("session_id inválido")

    sql = """
        INSERT INTO sensor_samples_agg(
            session_id, ts_s,
            T_pitch, L_pitch,
            thor_zone, lum_zone,
            comp_index
        )
        VALUES (?,?,?,?,?,?,?)
    """
    with _connect() as conn:
        conn.executemany(sql, rows)
        conn.commit()


def upsert_session_summary(
    *,
    session_id: int,
    duration_s: float,
    thor_red_s: float,
    lum_red_s: float,
    alerts_count: int,
    comp_avg: float,
    comp_peak: float,
    risk_index: float,
) -> None:
    if not isinstance(session_id, int):
        raise ValueError("session_id inválido")

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO session_summary(
                session_id, duration_s, thor_red_s, lum_red_s,
                alerts_count, comp_avg, comp_peak, risk_index
            )
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(session_id)
            DO UPDATE SET
                duration_s=excluded.duration_s,
                thor_red_s=excluded.thor_red_s,
                lum_red_s=excluded.lum_red_s,
                alerts_count=excluded.alerts_count,
                comp_avg=excluded.comp_avg,
                comp_peak=excluded.comp_peak,
                risk_index=excluded.risk_index
            """,
            (
                session_id,
                float(duration_s),
                float(thor_red_s),
                float(lum_red_s),
                int(alerts_count),
                float(comp_avg),
                float(comp_peak),
                float(risk_index),
            ),
        )
        conn.commit()


def recompute_daily_summary(*, user_id: int, day: Optional[date] = None) -> Dict:
    if not isinstance(user_id, int):
        raise ValueError("user_id inválido")
    d = (day or date.today()).isoformat()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(ss.session_id)                AS sessions_count,
                COALESCE(SUM(ss.duration_s), 0.0)   AS duration_s,
                COALESCE(SUM(ss.thor_red_s), 0.0)   AS thor_red_s,
                COALESCE(SUM(ss.lum_red_s), 0.0)    AS lum_red_s,
                COALESCE(SUM(ss.alerts_count), 0)   AS alerts_count,
                COALESCE(AVG(ss.comp_avg), 0.0)     AS comp_avg,
                COALESCE(MAX(ss.comp_peak), 0.0)    AS comp_peak,
                COALESCE(AVG(ss.risk_index), 0.0)   AS risk_index_avg,
                COALESCE(MAX(ss.risk_index), 0.0)   AS risk_index_max
            FROM sensor_sessions s
            JOIN session_summary ss ON ss.session_id = s.id
            WHERE s.user_id = ?
              AND DATE(s.started_at) = ?
              AND s.ended_at IS NOT NULL
            """,
            (user_id, d),
        ).fetchone()

        payload = {
            "user_id": user_id,
            "day": d,
            "sessions_count": int(row["sessions_count"] or 0),
            "duration_s": float(row["duration_s"] or 0.0),
            "thor_red_s": float(row["thor_red_s"] or 0.0),
            "lum_red_s": float(row["lum_red_s"] or 0.0),
            "alerts_count": int(row["alerts_count"] or 0),
            "comp_avg": float(row["comp_avg"] or 0.0),
            "comp_peak": float(row["comp_peak"] or 0.0),
            "risk_index_avg": float(row["risk_index_avg"] or 0.0),
            "risk_index_max": float(row["risk_index_max"] or 0.0),
        }

        conn.execute(
            """
            INSERT INTO daily_summary(
                user_id, day,
                sessions_count, duration_s, thor_red_s, lum_red_s,
                alerts_count,
                comp_avg, comp_peak, risk_index_avg, risk_index_max,
                updated_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, day)
            DO UPDATE SET
                sessions_count=excluded.sessions_count,
                duration_s=excluded.duration_s,
                thor_red_s=excluded.thor_red_s,
                lum_red_s=excluded.lum_red_s,
                alerts_count=excluded.alerts_count,
                comp_avg=excluded.comp_avg,
                comp_peak=excluded.comp_peak,
                risk_index_avg=excluded.risk_index_avg,
                risk_index_max=excluded.risk_index_max,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                user_id,
                d,
                payload["sessions_count"],
                payload["duration_s"],
                payload["thor_red_s"],
                payload["lum_red_s"],
                payload["alerts_count"],
                payload["comp_avg"],
                payload["comp_peak"],
                payload["risk_index_avg"],
                payload["risk_index_max"],
            ),
        )
        conn.commit()
        return payload


def get_daily_summary(*, user_id: int, day: Optional[date] = None) -> Optional[Dict]:
    if not isinstance(user_id, int):
        raise ValueError("user_id inválido")
    d = (day or date.today()).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM daily_summary WHERE user_id=? AND day=?",
            (user_id, d),
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------
# Daily summary range helpers (Week L–D, Month)
# ---------------------------------------------------------------------
def list_users(role: Optional[str] = None) -> List[Dict]:
    q = "SELECT id, name, email, country, role, created_at FROM users"
    params: List = []
    if role:
        q += " WHERE role=?"
        params.append(role)
    q += " ORDER BY created_at DESC"
    with _connect() as con:
        cur = con.execute(q, params)
        rows = cur.fetchall()
    return [
        {
            "id": int(r["id"]),
            "name": r["name"],
            "email": r["email"],
            "country": r["country"],
            "role": r["role"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def resolve_user_id(user_id=None, email: Optional[str] = None) -> Optional[int]:
    if user_id is not None:
        try:
            return int(user_id)
        except Exception:
            pass

    if email:
        with _connect() as con:
            cur = con.execute("SELECT id FROM users WHERE email=? LIMIT 1", (email,))
            row = cur.fetchone()
        if row:
            return int(row["id"])

    return None


def get_daily_summaries_range(user_id: int, start_day: str, end_day: str) -> List[Dict]:
    user_id = resolve_user_id(user_id)
    if user_id is None:
        raise ValueError("user_id inválido")

    with _connect() as con:
        cur = con.execute(
            """
            SELECT day, thor_red_s, lum_red_s, comp_avg, comp_peak, alerts_count,
                   risk_index_max, sessions_count, updated_at
            FROM daily_summary
            WHERE user_id=? AND day>=? AND day<=?
            ORDER BY day ASC
            """,
            (user_id, start_day, end_day),
        )
        rows = cur.fetchall()

    out: List[Dict] = []
    for r in rows:
        out.append(
            {
                "day": r["day"],
                "thor_red_s": float(r["thor_red_s"] or 0.0),
                "lum_red_s": float(r["lum_red_s"] or 0.0),
                "comp_avg": float(r["comp_avg"] or 0.0),
                "comp_peak": float(r["comp_peak"] or 0.0),
                "alerts_count": int(r["alerts_count"] or 0),
                "risk_index_max": float(r["risk_index_max"] or 0.0),
                "sessions_count": int(r["sessions_count"] or 0),
                "updated_at": r["updated_at"],
            }
        )
    return out


def _parse_day_iso(day: Optional[str]) -> date:
    return date.today() if not day else date.fromisoformat(day)


def get_week_range_monday_sunday(day: Optional[str] = None) -> Tuple[str, str]:
    d = _parse_day_iso(day)
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def get_month_range(day: Optional[str] = None) -> Tuple[str, str]:
    d = _parse_day_iso(day)
    first = d.replace(day=1)
    if d.month == 12:
        next_first = date(d.year + 1, 1, 1)
    else:
        next_first = date(d.year, d.month + 1, 1)
    last = next_first - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def get_daily_summaries_week(user_id: int, day: Optional[str] = None) -> List[Dict]:
    start_day, end_day = get_week_range_monday_sunday(day)
    return get_daily_summaries_range(user_id, start_day, end_day)


def get_daily_summaries_month(user_id: int, day: Optional[str] = None) -> List[Dict]:
    start_day, end_day = get_month_range(day)
    return get_daily_summaries_range(user_id, start_day, end_day)


# ============================================================
# PASO 2 — API Wizard: questionnaire_sessions + baseline + settings
# ============================================================

def start_questionnaire_session(*, user_id: int, q_type: str) -> int:
    """
    Crea una sesión de cuestionario y devuelve session_id.
    q_type: 'initial_full' | 'daily_checkin'
    """
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    q_type = (q_type or "").strip()
    if q_type not in {"initial_full", "daily_checkin"}:
        raise ValueError("q_type inválido (initial_full|daily_checkin)")

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO questionnaire_sessions(user_id, type, payload_json)
            VALUES (?,?,?)
            """,
            (uid, q_type, _json_dumps_safe({})),
        )
        conn.commit()
        return int(cur.lastrowid)


def _get_questionnaire_payload(conn: sqlite3.Connection, session_id: int) -> Dict:
    row = conn.execute(
        "SELECT payload_json FROM questionnaire_sessions WHERE id=?",
        (int(session_id),),
    ).fetchone()
    payload = _json_loads_safe(row["payload_json"]) if row else None
    return payload if isinstance(payload, dict) else {}


def save_questionnaire_step(*, session_id: int, step_key: str, step_payload: Dict) -> None:
    """
    Guarda un paso dentro de payload_json (merge por key).
    - step_key: 'profile' | 'pain' | 'self_eval' | 'baseline' | 'daily'
    - step_payload: dict
    """
    if not isinstance(session_id, int):
        raise ValueError("session_id inválido")

    step_key = (step_key or "").strip()
    if not step_key:
        raise ValueError("step_key inválido")

    if step_payload is None:
        step_payload = {}
    if not isinstance(step_payload, dict):
        raise ValueError("step_payload debe ser dict")

    with _connect() as conn:
        payload = _get_questionnaire_payload(conn, session_id)
        payload[step_key] = step_payload
        conn.execute(
            """
            UPDATE questionnaire_sessions
            SET payload_json=?
            WHERE id=?
            """,
            (_json_dumps_safe(payload), int(session_id)),
        )
        conn.commit()


def complete_questionnaire_session(
    *,
    session_id: int,
    risk_index: float,
    recommendation: Dict,
) -> Dict:
    """
    Marca la sesión como completada + guarda risk_index y recommendation_json.
    Devuelve la sesión completa como dict.
    """
    if not isinstance(session_id, int):
        raise ValueError("session_id inválido")

    try:
        ri = float(risk_index)
    except Exception:
        ri = 0.0

    if recommendation is None:
        recommendation = {}
    if not isinstance(recommendation, dict):
        raise ValueError("recommendation debe ser dict")

    with _connect() as conn:
        conn.execute(
            """
            UPDATE questionnaire_sessions
            SET completed_at=CURRENT_TIMESTAMP,
                risk_index=?,
                recommendation_json=?
            WHERE id=?
            """,
            (ri, _json_dumps_safe(recommendation), int(session_id)),
        )
        conn.commit()

        row = conn.execute("SELECT * FROM questionnaire_sessions WHERE id=?", (int(session_id),)).fetchone()
        out = dict(row) if row else {}
        out["payload"] = _json_loads_safe(out.get("payload_json"))
        out["recommendation"] = _json_loads_safe(out.get("recommendation_json"))
        return out


def get_latest_questionnaire_session(*, user_id: int, q_type: Optional[str] = None) -> Optional[Dict]:
    """
    Devuelve la última sesión (completada si existe, si no, la última iniciada).
    q_type opcional: initial_full|daily_checkin
    """
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    where = "WHERE user_id=?"
    params = [uid]
    if q_type:
        q_type = (q_type or "").strip()
        where += " AND type=?"
        params.append(q_type)

    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT *
            FROM questionnaire_sessions
            {where}
            ORDER BY
                CASE WHEN completed_at IS NULL THEN 1 ELSE 0 END ASC,
                datetime(COALESCE(completed_at, started_at)) DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()

        if not row:
            return None

        out = dict(row)
        out["payload"] = _json_loads_safe(out.get("payload_json"))
        out["recommendation"] = _json_loads_safe(out.get("recommendation_json"))
        return out


def list_questionnaire_sessions(*, user_id: int, limit: int = 20) -> List[Dict]:
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    lim = max(1, min(int(limit or 20), 200))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM questionnaire_sessions
            WHERE user_id=?
            ORDER BY datetime(started_at) DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()

    out: List[Dict] = []
    for r in rows:
        d = dict(r)
        d["payload"] = _json_loads_safe(d.get("payload_json"))
        d["recommendation"] = _json_loads_safe(d.get("recommendation_json"))
        out.append(d)
    return out



def _baseline_summary_from_payload(baseline_payload: Optional[Dict]) -> Dict:
    payload = baseline_payload if isinstance(baseline_payload, dict) else {}
    rom = payload.get("rom") if isinstance(payload.get("rom"), dict) else {}
    stability = payload.get("stability") if isinstance(payload.get("stability"), dict) else {}
    comp = payload.get("comp") if isinstance(payload.get("comp"), dict) else {}

    def _f(v, default=0.0):
        try:
            return float(v)
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


def _normalize_numeric_dict(raw: Optional[Dict]) -> Dict:
    src = raw if isinstance(raw, dict) else {}
    out: Dict = {}
    for k, v in src.items():
        if isinstance(v, bool):
            out[k] = v
            continue
        try:
            if v is None or (isinstance(v, str) and not v.strip()):
                out[k] = v
            elif isinstance(v, (int, float)):
                out[k] = float(v)
            else:
                out[k] = float(v)
        except Exception:
            out[k] = v
    return out


def _normalize_thresholds_root(raw_thresholds: Optional[Dict]) -> Dict:
    src = raw_thresholds if isinstance(raw_thresholds, dict) else {}

    def _mode_block(mode_key: str) -> Dict:
        mode_src = src.get(mode_key) if isinstance(src.get(mode_key), dict) else {}
        thor_src = mode_src.get("thor") if isinstance(mode_src.get("thor"), dict) else {}
        lum_src = mode_src.get("lum") if isinstance(mode_src.get("lum"), dict) else {}
        return {
            "thor": _normalize_numeric_dict(thor_src),
            "lum": _normalize_numeric_dict(lum_src),
        }

    if any(k in src for k in ("desk", "train")):
        return {
            "desk": _mode_block("desk"),
            "train": _mode_block("train"),
        }

    thor_src = src.get("thor") if isinstance(src.get("thor"), dict) else {}
    lum_src = src.get("lum") if isinstance(src.get("lum"), dict) else {}
    if thor_src or lum_src:
        shared = {
            "thor": _normalize_numeric_dict(thor_src),
            "lum": _normalize_numeric_dict(lum_src),
        }
        return {
            "desk": json.loads(json.dumps(shared, ensure_ascii=False)),
            "train": json.loads(json.dumps(shared, ensure_ascii=False)),
        }

    return {
        "desk": {"thor": {}, "lum": {}},
        "train": {"thor": {}, "lum": {}},
    }


def _normalize_posture_settings_payload(payload: Optional[Dict]) -> Dict:
    """Normaliza user_posture_settings a una forma estable compartida.

    Regla de fuente de verdad:
    - thresholds vive en user_posture_settings.thresholds_json
    - la forma persistida debe ser siempre consistente para Monitor y Cuestionario
    - si entra una estructura legacy, se adapta sin romper compatibilidad
    """
    src = payload if isinstance(payload, dict) else {}

    thresholds_src = src.get("thresholds") if isinstance(src.get("thresholds"), dict) else None
    if thresholds_src is None:
        thresholds_src = src

    adaptation_src = src.get("adaptation") if isinstance(src.get("adaptation"), dict) else {}
    if not adaptation_src and isinstance(src.get("adaptation_rules"), dict):
        adaptation_src = src.get("adaptation_rules")

    baseline_reference = src.get("baseline_reference") if isinstance(src.get("baseline_reference"), dict) else {}

    normalized = {
        "thresholds": _normalize_thresholds_root(thresholds_src),
        "adaptation": _normalize_numeric_dict(adaptation_src),
        "baseline_reference": baseline_reference,
        "version": str(src.get("version") or "wizard_v2"),
    }

    # Alias compatible para consumidores antiguos.
    normalized["adaptation_rules"] = json.loads(json.dumps(normalized["adaptation"], ensure_ascii=False))

    for extra_key in ("source", "updated_from", "notes"):
        if extra_key in src and extra_key not in normalized:
            normalized[extra_key] = src.get(extra_key)

    return normalized


def get_latest_baseline_reference(*, user_id: int) -> Optional[Dict]:
    """Fuente de verdad compartida del baseline histórico.

    Devuelve la última fila de baseline_tests ya normalizada para Monitor y Cuestionario:
    - baseline histórico siempre sale de baseline_tests
    - baseline parseado en `baseline`
    - resumen agregado en `summary`
    - alias `baseline_test_id` para no duplicar lógica de lectura en vistas
    """
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM baseline_tests
            WHERE user_id=?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (uid,),
        ).fetchone()

    if not row:
        return None

    out = dict(row)
    baseline_payload = _json_loads_safe(out.get("baseline_json"))
    if not isinstance(baseline_payload, dict):
        baseline_payload = {}

    out["baseline"] = baseline_payload
    out["baseline_test_id"] = out.get("id")
    out["summary"] = _baseline_summary_from_payload(baseline_payload)
    out["source"] = "baseline_tests"
    out["history_source"] = "baseline_tests"
    out["is_history_reference"] = True
    return out


def get_routine_link_context(*, user_id: int, day: Optional[date] = None) -> Dict:
    """
    Devuelve a Rutinas el mismo contexto semÃ¡ntico que Monitor.
    La rutina del dÃ­a tiene prioridad; el cuestionario reciente queda como
    fallback y como enlace clÃ­nico para crear la nueva ejecuciÃ³n RUN.
    """
    return get_monitor_link_context(user_id=user_id, day=day)



# ============================================================
# FASE 5 — Baseline histórico compartido + normalización UI
# ============================================================
# Convención consolidada:
# - baseline_tests = fuente histórica persistida
# - get_latest_baseline_reference(...) = API principal
# - get_latest_valid_baseline(...) = solo fallback compatible
# Estos helpers evitan parsing repetido en Monitor y Cuestionario.

BASELINE_HISTORY_SOURCE = "baseline_tests"


def _safe_baseline_payload_from_reference(ref: Optional[Dict]) -> Dict:
    src = ref if isinstance(ref, dict) else {}
    for key in ("baseline", "baseline_payload", "latest_baseline_payload"):
        value = src.get(key)
        if isinstance(value, dict):
            return value
    raw_json = src.get("baseline_json")
    decoded = _json_loads_safe(raw_json)
    return decoded if isinstance(decoded, dict) else {}


def _safe_baseline_summary_from_reference(ref: Optional[Dict], baseline_payload: Optional[Dict] = None) -> Dict:
    src = ref if isinstance(ref, dict) else {}
    for key in ("summary", "latest_baseline_summary"):
        value = src.get(key)
        if isinstance(value, dict):
            return value
    return _baseline_summary_from_payload(baseline_payload if isinstance(baseline_payload, dict) else {})


def _baseline_reference_id(ref: Optional[Dict]):
    src = ref if isinstance(ref, dict) else {}
    return src.get("baseline_test_id") or src.get("latest_baseline_test_id") or src.get("id")


def _baseline_reference_created_at(ref: Optional[Dict]):
    src = ref if isinstance(ref, dict) else {}
    return src.get("created_at") or src.get("created_at_iso") or src.get("latest_baseline_ts")


def _baseline_reference_source(ref: Optional[Dict]) -> str:
    src = ref if isinstance(ref, dict) else {}
    return str(src.get("history_source") or src.get("source") or src.get("latest_baseline_source") or BASELINE_HISTORY_SOURCE).strip() or BASELINE_HISTORY_SOURCE


def _baseline_source_label(source: Optional[str]) -> str:
    source_txt = str(source or "").strip() or BASELINE_HISTORY_SOURCE
    if source_txt == BASELINE_HISTORY_SOURCE:
        return "Histórico compartido"
    if source_txt in {"baseline_db", "db", "database"}:
        return "Histórico DB"
    return source_txt


def _baseline_status_label(ref: Optional[Dict], baseline_payload: Optional[Dict] = None) -> str:
    src = ref if isinstance(ref, dict) else {}
    if not src:
        return "Pendiente"
    if src.get("status"):
        return str(src.get("status"))
    if src.get("is_valid") is False:
        return "Pendiente"
    payload = baseline_payload if isinstance(baseline_payload, dict) else _safe_baseline_payload_from_reference(src)
    return "Completada" if bool(payload) else "Pendiente"


def normalize_baseline_reference_for_ui(ref: Optional[Dict]) -> Dict:
    """Normaliza cualquier referencia de baseline a una forma lista para UI.

    Salida común para Monitor y Cuestionario:
    - baseline_test_id
    - created_at / created_at_raw
    - baseline / baseline_payload
    - summary
    - source / history_source / source_label
    - has_baseline / is_valid / status_label
    - campos latest_* compatibles con calibration-store legacy
    """
    src = ref if isinstance(ref, dict) else {}
    baseline_payload = _safe_baseline_payload_from_reference(src)
    summary = _safe_baseline_summary_from_reference(src, baseline_payload)
    baseline_test_id = _baseline_reference_id(src)
    created_at = _baseline_reference_created_at(src)
    source = _baseline_reference_source(src)
    has_baseline = bool(src) and bool(baseline_payload)
    is_valid = bool(src.get("is_valid", has_baseline)) if src else False
    status_label = _baseline_status_label(src, baseline_payload)

    normalized = dict(src)
    normalized.update({
        "has_baseline": has_baseline,
        "baseline": baseline_payload,
        "baseline_payload": baseline_payload,
        "payload": baseline_payload,
        "summary": summary,
        "baseline_test_id": baseline_test_id,
        "created_at": created_at,
        "created_at_raw": created_at,
        "source": source,
        "history_source": BASELINE_HISTORY_SOURCE,
        "source_label": _baseline_source_label(source),
        "is_history_reference": True,
        "is_valid": is_valid,
        "status": status_label,
        "status_label": status_label,
        "latest_baseline_test_id": baseline_test_id,
        "latest_baseline_ts": created_at,
        "latest_baseline_payload": baseline_payload,
        "latest_baseline_summary": summary,
        "latest_baseline_source": source,
    })
    return normalized


def empty_baseline_history_reference() -> Dict:
    """Referencia vacía estable para stores/UI cuando todavía no hay baseline."""
    return normalize_baseline_reference_for_ui({
        "baseline_test_id": None,
        "created_at": None,
        "baseline": {},
        "summary": {},
        "source": BASELINE_HISTORY_SOURCE,
        "history_source": BASELINE_HISTORY_SOURCE,
        "is_valid": False,
        "status": "Pendiente",
    })


def get_latest_baseline_reference_for_ui(*, user_id: int, allow_fallback: bool = True) -> Dict:
    """Lee y normaliza la referencia histórica para UI desde la API principal."""
    ref = None
    try:
        ref = get_latest_baseline_reference(user_id=user_id)
    except Exception:
        ref = None

    if not ref and allow_fallback:
        try:
            ref = get_latest_valid_baseline(user_id=user_id)
        except Exception:
            ref = None

    if not ref:
        return empty_baseline_history_reference()
    return normalize_baseline_reference_for_ui(ref)


def get_latest_baseline_history_legacy_fields(*, user_id: int, allow_fallback: bool = True) -> Dict:
    """Devuelve los campos latest_* que usa el calibration-store legacy de Monitor."""
    ref = get_latest_baseline_reference_for_ui(user_id=user_id, allow_fallback=allow_fallback)
    return {
        "latest_baseline_test_id": ref.get("latest_baseline_test_id"),
        "latest_baseline_ts": ref.get("latest_baseline_ts"),
        "latest_baseline_payload": ref.get("latest_baseline_payload") if isinstance(ref.get("latest_baseline_payload"), dict) else {},
        "latest_baseline_summary": ref.get("latest_baseline_summary") if isinstance(ref.get("latest_baseline_summary"), dict) else {},
        "latest_baseline_source": ref.get("latest_baseline_source"),
    }



def get_baseline_reference_by_id_for_ui(*, user_id: int, baseline_test_id: int) -> Dict:
    """Lee un baseline_tests concreto y lo devuelve con la misma normalización UI."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    try:
        bid = int(baseline_test_id)
    except Exception:
        return empty_baseline_history_reference()

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM baseline_tests
            WHERE user_id=? AND id=?
            LIMIT 1
            """,
            (uid, bid),
        ).fetchone()

    if not row:
        return empty_baseline_history_reference()

    out = dict(row)
    baseline_payload = _json_loads_safe(out.get("baseline_json"))
    if not isinstance(baseline_payload, dict):
        baseline_payload = {}

    out["baseline"] = baseline_payload
    out["baseline_payload"] = baseline_payload
    out["baseline_test_id"] = out.get("id")
    out["summary"] = _baseline_summary_from_payload(baseline_payload)
    out["source"] = BASELINE_HISTORY_SOURCE
    out["history_source"] = BASELINE_HISTORY_SOURCE
    out["is_history_reference"] = True
    return normalize_baseline_reference_for_ui(out)


def get_baseline_history_legacy_fields_by_id(*, user_id: int, baseline_test_id: int) -> Dict:
    """Devuelve latest_* para un baseline histórico concreto, sin activar sesión."""
    ref = get_baseline_reference_by_id_for_ui(user_id=user_id, baseline_test_id=baseline_test_id)
    return {
        "latest_baseline_test_id": ref.get("latest_baseline_test_id"),
        "latest_baseline_ts": ref.get("latest_baseline_ts"),
        "latest_baseline_payload": ref.get("latest_baseline_payload") if isinstance(ref.get("latest_baseline_payload"), dict) else {},
        "latest_baseline_summary": ref.get("latest_baseline_summary") if isinstance(ref.get("latest_baseline_summary"), dict) else {},
        "latest_baseline_source": ref.get("latest_baseline_source"),
    }


def list_baseline_tests_for_user(*, user_id: int, limit: int = 50) -> List[Dict]:
    """Lista baseline_tests normalizados para historial de calibraciones."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    lim = max(1, min(int(limit or 50), 500))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                b.*,
                s.kind AS sensor_kind,
                s.started_at AS sensor_started_at,
                s.ended_at AS sensor_ended_at,
                s.mode AS sensor_mode,
                s.sport AS sensor_sport
            FROM baseline_tests b
            LEFT JOIN sensor_sessions s ON s.id = b.sensor_session_id
            WHERE b.user_id=?
            ORDER BY datetime(b.created_at) DESC, b.id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()

    out: List[Dict] = []
    for r in rows:
        item = dict(r)
        baseline_payload = _json_loads_safe(item.get("baseline_json"))
        if not isinstance(baseline_payload, dict):
            baseline_payload = {}
        item["baseline"] = baseline_payload
        item["baseline_payload"] = baseline_payload
        item["baseline_test_id"] = item.get("id")
        item["summary"] = _baseline_summary_from_payload(baseline_payload)
        item["source"] = BASELINE_HISTORY_SOURCE
        item["history_source"] = BASELINE_HISTORY_SOURCE
        item["is_history_reference"] = True

        normalized = normalize_baseline_reference_for_ui(item)
        normalized.update({
            "id": item.get("id"),
            "sensor_session_id": item.get("sensor_session_id"),
            "sensor_kind": item.get("sensor_kind"),
            "sensor_started_at": item.get("sensor_started_at"),
            "sensor_ended_at": item.get("sensor_ended_at"),
            "sensor_mode": item.get("sensor_mode"),
            "sensor_sport": item.get("sensor_sport"),
        })
        out.append(normalized)

    return out


def upsert_user_posture_settings(*, user_id: int, thresholds: Dict) -> None:
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    if thresholds is None:
        thresholds = {}
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds debe ser dict")

    normalized = _normalize_posture_settings_payload(thresholds)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_posture_settings(user_id, thresholds_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id)
            DO UPDATE SET
                thresholds_json=excluded.thresholds_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (uid, _json_dumps_safe(normalized)),
        )
        conn.commit()


def get_user_posture_settings(*, user_id: int) -> Optional[Dict]:
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    with _connect() as conn:
        row = conn.execute(
            "SELECT thresholds_json, updated_at FROM user_posture_settings WHERE user_id=?",
            (uid,),
        ).fetchone()

    if not row:
        return None

    settings = _json_loads_safe(row["thresholds_json"])
    if not isinstance(settings, dict):
        settings = {}

    normalized = _normalize_posture_settings_payload(settings)
    return {
        "user_id": uid,
        "settings": normalized,
        "thresholds": normalized.get("thresholds") or {},
        "adaptation": normalized.get("adaptation") or {},
        "version": normalized.get("version") or "wizard_v2",
        "updated_at": row["updated_at"],
    }



def get_user_posture_settings_status(*, user_id: int) -> str:
    """Estado compacto de user_posture_settings para UI."""
    try:
        settings_payload = get_user_posture_settings(user_id=int(user_id))
    except Exception:
        settings_payload = None

    if not isinstance(settings_payload, dict):
        return "Pendientes"

    thresholds = settings_payload.get("thresholds")
    settings_root = settings_payload.get("settings")
    if isinstance(thresholds, dict) and bool(thresholds):
        return "Guardados ✓"
    if isinstance(settings_root, dict):
        if isinstance(settings_root.get("thresholds"), dict) and bool(settings_root.get("thresholds")):
            return "Guardados ✓"
        if bool(settings_root):
            return "Guardados ✓"
    return "Pendientes"


def create_baseline_test(*, user_id: int, sensor_session_id: Optional[int], baseline: Dict) -> int:
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    if baseline is None:
        baseline = {}
    if not isinstance(baseline, dict):
        raise ValueError("baseline debe ser dict")

    ssid = None
    if sensor_session_id is not None:
        try:
            ssid = int(sensor_session_id)
        except Exception:
            ssid = None

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO baseline_tests(user_id, sensor_session_id, baseline_json)
            VALUES (?,?,?)
            """,
            (uid, ssid, _json_dumps_safe(baseline)),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_latest_baseline(*, user_id: int) -> Optional[Dict]:
    """Compatibilidad: devuelve el baseline histórico usando la fuente de verdad compartida.

    Mantiene el nombre legacy para no romper vistas antiguas, pero ahora reutiliza
    la misma normalización que Monitor y Cuestionario deben compartir.
    """
    ref = get_latest_baseline_reference(user_id=user_id)
    if not ref:
        return None

    out = dict(ref)
    if not isinstance(out.get("baseline"), dict):
        out["baseline"] = {}
    if "summary" not in out or not isinstance(out.get("summary"), dict):
        out["summary"] = _baseline_summary_from_payload(out.get("baseline"))
    if "baseline_test_id" not in out:
        out["baseline_test_id"] = out.get("id")
    return out

def get_latest_valid_baseline(*, user_id: int) -> Optional[Dict]:
    """
    Devuelve la última calibración/baseline válida para monitorización.

    Criterios mínimos de validez MVP:
    - existe baseline_tests
    - si tiene sensor_session_id, la sensor_session existe y está cerrada
    - payload baseline_json se parsea y se adjunta como `baseline`
    """
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                b.*, 
                s.kind AS sensor_kind,
                s.started_at AS sensor_started_at,
                s.ended_at AS sensor_ended_at,
                s.mode AS sensor_mode,
                s.sport AS sensor_sport
            FROM baseline_tests b
            LEFT JOIN sensor_sessions s ON s.id = b.sensor_session_id
            WHERE b.user_id = ?
            ORDER BY datetime(b.created_at) DESC, b.id DESC
            """,
            (uid,),
        ).fetchall()

    for r in row:
        out = dict(r)
        baseline_payload = _json_loads_safe(out.get("baseline_json"))
        if not isinstance(baseline_payload, dict):
            baseline_payload = {}

        sensor_session_id = out.get("sensor_session_id")
        sensor_ok = True
        if sensor_session_id is not None:
            sensor_ok = bool((out.get("sensor_kind") or "") == "baseline" and out.get("sensor_ended_at"))

        n_samples = 0
        try:
            n_samples = int(baseline_payload.get("n_samples") or 0)
        except Exception:
            n_samples = 0

        payload_ok = bool(baseline_payload) and (n_samples > 0 or bool(baseline_payload.get("rom")) or bool(baseline_payload.get("stability")))
        if sensor_ok and payload_ok:
            out["baseline"] = baseline_payload
            out["baseline_test_id"] = out.get("id")
            out["summary"] = _baseline_summary_from_payload(baseline_payload)
            out["is_valid"] = True
            out["source"] = "baseline_db"
            out["history_source"] = "baseline_tests"
            return out

    return None


def _infer_monitor_mode_from_questionnaire_payload(payload: Optional[Dict]) -> str:
    payload = payload if isinstance(payload, dict) else {}
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}

    desk_job = str(profile.get("desk_job") or "").strip().lower()
    session_type = str(daily.get("session_type") or "").strip().lower()
    goal_txt = str(daily.get("goal") or "").strip().lower()

    if desk_job == "desk":
        return "office"
    if session_type in {"recovery", "light"} and ("rehab" in goal_txt or "movilidad" in goal_txt or "dolor" in goal_txt):
        return "rehab"
    return "train"


def _infer_planned_session_name_from_questionnaire_payload(payload: Optional[Dict]) -> str:
    payload = payload if isinstance(payload, dict) else {}
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    goal = str(daily.get("goal") or "").strip()
    session_type = str(daily.get("session_type") or "normal").strip().lower() or "normal"

    label_map = {
        "recovery": "Descanso / recuperación",
        "light": "Entreno suave",
        "normal": "Entreno normal",
        "hard": "Entreno intenso",
    }
    base = label_map.get(session_type, "Entreno normal")
    if goal:
        return f"{base} · {goal}"
    return base


def _normalize_link_day(day_value: Optional[date]) -> tuple[date, str]:
    if day_value is None:
        d_obj = date.today()
    elif isinstance(day_value, datetime):
        d_obj = day_value.date()
    elif isinstance(day_value, date):
        d_obj = day_value
    else:
        d_obj = date.fromisoformat(str(day_value)[:10])
    return d_obj, d_obj.isoformat()


def _normalize_routine_plan_for_context(plan_payload: Optional[Dict], fallback_day: str) -> Dict:
    plan_payload = plan_payload if isinstance(plan_payload, dict) else {}
    mode = str(plan_payload.get("mode") or plan_payload.get("monitor_mode") or "train").strip() or "train"
    sport = str(plan_payload.get("sport") or "gym").strip() or "gym"
    session_type = str(plan_payload.get("session_type") or "").strip() or None
    goal = str(plan_payload.get("goal") or "").strip() or None
    title = (
        plan_payload.get("planned_session_name")
        or plan_payload.get("title")
        or plan_payload.get("name")
        or plan_payload.get("session_name")
        or f"Rutina del {fallback_day}"
    )
    return {
        "plan": plan_payload,
        "planned_session_name": str(title),
        "mode": mode,
        "sport": sport,
        "session_type": session_type,
        "goal": goal,
    }


def _extract_questionnaire_daily_payload(payload: Optional[Dict]) -> Dict:
    payload = payload if isinstance(payload, dict) else {}
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    return daily


def _extract_goal_from_questionnaire_payload(payload: Optional[Dict]) -> Optional[str]:
    daily = _extract_questionnaire_daily_payload(payload)
    profile = payload.get("profile") if isinstance(payload, dict) and isinstance(payload.get("profile"), dict) else {}
    goal = str(daily.get("goal") or profile.get("goal") or "").strip()
    return goal or None


def _infer_sport_from_questionnaire_payload(payload: Optional[Dict]) -> str:
    payload = payload if isinstance(payload, dict) else {}
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    daily = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    raw = str(daily.get("sport") or profile.get("sport") or profile.get("activity") or "").strip().lower()
    if raw in {"run", "running", "correr", "runner"}:
        return "running"
    if raw in {"bike", "cycling", "bici", "ciclismo"}:
        return "cycling"
    if raw in {"office", "desk", "trabajo"}:
        return "office"
    return "gym"


def create_routine_session(
    user_id: int,
    day: date,
    plan_json: Dict,
    notes: Optional[str] = None,
) -> int:
    """Crea una rutina ejecutable y guarda el plan/contexto usado por RUN."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id invÃ¡lido")
    _d_obj, d_iso = _normalize_link_day(day)
    payload = plan_json if isinstance(plan_json, dict) else {}

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO routine_sessions(user_id, day, plan_json, notes)
            VALUES (?,?,?,?)
            """,
            (int(uid), d_iso, _json_dumps_safe(payload), notes),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_routine_session(
    routine_session_id: int,
    score_avg: float,
    notes: Optional[str] = None,
    ended_at: Optional[datetime] = None,
) -> None:
    """Cierra una routine_session con score medio y notas opcionales."""
    if not isinstance(routine_session_id, int):
        raise ValueError("routine_session_id invÃ¡lido")
    ea = (ended_at or datetime.now()).isoformat(timespec="seconds")
    try:
        score = float(score_avg)
    except Exception:
        score = 0.0

    with _connect() as conn:
        if notes is None:
            conn.execute(
                "UPDATE routine_sessions SET ended_at=?, score_avg=? WHERE id=?",
                (ea, score, int(routine_session_id)),
            )
        else:
            conn.execute(
                "UPDATE routine_sessions SET ended_at=?, score_avg=?, notes=? WHERE id=?",
                (ea, score, notes, int(routine_session_id)),
            )
        conn.commit()


def insert_exercise_set(
    routine_session_id: int,
    exercise_name: str,
    set_index: int,
    reps_target: Optional[int],
    reps_valid: Optional[int],
    score_avg: Optional[float],
    thor_red_s: Optional[float],
    lum_red_s: Optional[float],
    comp_avg: Optional[float],
    comp_peak: Optional[float],
) -> int:
    """Inserta el resumen de un set/ejercicio enlazado a una rutina."""
    if not isinstance(routine_session_id, int):
        raise ValueError("routine_session_id invÃ¡lido")

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO exercise_sets(
                routine_session_id, exercise_name, set_index,
                reps_target, reps_valid, score_avg,
                thor_red_s, lum_red_s, comp_avg, comp_peak
            )
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                int(routine_session_id),
                str(exercise_name or "Ejercicio"),
                int(set_index or 1),
                None if reps_target is None else int(reps_target),
                None if reps_valid is None else int(reps_valid),
                None if score_avg is None else float(score_avg),
                None if thor_red_s is None else float(thor_red_s),
                None if lum_red_s is None else float(lum_red_s),
                None if comp_avg is None else float(comp_avg),
                None if comp_peak is None else float(comp_peak),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_routine_session_sensor_link(
    routine_session_id: int,
    sensor_session_id: int,
    questionnaire_session_id: Optional[int] = None,
) -> None:
    """
    Enlaza la rutina con su sensor_session dentro de plan_json.
    sensor_sessions.routine_session_id mantiene la relaciÃ³n principal y este
    bloque deja el contexto visible tambiÃ©n desde Rutinas.
    """
    if not isinstance(routine_session_id, int):
        raise ValueError("routine_session_id invÃ¡lido")
    if not isinstance(sensor_session_id, int):
        raise ValueError("sensor_session_id invÃ¡lido")

    with _connect() as conn:
        row = conn.execute("SELECT plan_json FROM routine_sessions WHERE id=?", (int(routine_session_id),)).fetchone()
        plan_payload = _json_loads_safe(row["plan_json"]) if row else {}
        if not isinstance(plan_payload, dict):
            plan_payload = {}
        db_link = plan_payload.get("db_link") if isinstance(plan_payload.get("db_link"), dict) else {}
        db_link["routine_session_id"] = int(routine_session_id)
        db_link["sensor_session_id"] = int(sensor_session_id)
        if questionnaire_session_id is not None:
            try:
                db_link["questionnaire_session_id"] = int(questionnaire_session_id)
            except Exception:
                pass
        plan_payload["db_link"] = db_link
        conn.execute(
            "UPDATE routine_sessions SET plan_json=? WHERE id=?",
            (_json_dumps_safe(plan_payload), int(routine_session_id)),
        )
        conn.commit()


def get_monitor_link_context(*, user_id: int, day: Optional[date] = None) -> Dict:
    """
    Devuelve el contexto enlazable más reciente para Monitor.

    Prioridad:
    1) rutina del día si existe
    2) último cuestionario con payload útil

    Esto deja resuelto en DB el puente para que Monitor no tenga que inventar
    `questionnaire_session_id`, `routine_session_id` o `planned_session_name`.
    """
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    _d_obj, d = _normalize_link_day(day)
    out = {
        "user_id": uid,
        "day": d,
        "questionnaire_session_id": None,
        "routine_session_id": None,
        "planned_session_name": None,
        "mode": "train",
        "sport": "gym",
        "session_type": None,
        "goal": None,
        "source": None,
        "questionnaire_payload": {},
        "routine_payload": {},
    }

    with _connect() as conn:
        routine_row = conn.execute(
            """
            SELECT *
            FROM routine_sessions
            WHERE user_id=? AND day=?
            ORDER BY datetime(COALESCE(ended_at, started_at)) DESC, id DESC
            LIMIT 1
            """,
            (uid, d),
        ).fetchone()

        if routine_row:
            rr = dict(routine_row)
            plan_payload = _json_loads_safe(rr.get("plan_json"))
            if not isinstance(plan_payload, dict):
                plan_payload = {}
            routine_ctx = _normalize_routine_plan_for_context(plan_payload, d)
            out.update({
                "routine_session_id": int(rr.get("id")),
                "planned_session_name": rr.get("notes") or routine_ctx.get("planned_session_name") or f"Rutina del {d}",
                "mode": routine_ctx.get("mode") or "train",
                "sport": routine_ctx.get("sport") or "gym",
                "session_type": routine_ctx.get("session_type"),
                "goal": routine_ctx.get("goal"),
                "source": "routine_session",
                "routine_payload": routine_ctx.get("plan") or {},
            })

        q_row = conn.execute(
            """
            SELECT *
            FROM questionnaire_sessions
            WHERE user_id=?
            ORDER BY
                CASE WHEN completed_at IS NULL THEN 1 ELSE 0 END ASC,
                datetime(COALESCE(completed_at, started_at)) DESC,
                id DESC
            LIMIT 1
            """,
            (uid,),
        ).fetchone()

    if q_row:
        qq = dict(q_row)
        payload = _json_loads_safe(qq.get("payload_json"))
        if not isinstance(payload, dict):
            payload = {}
        daily_payload = _extract_questionnaire_daily_payload(payload)
        goal = _extract_goal_from_questionnaire_payload(payload)
        out["questionnaire_payload"] = payload
        out["questionnaire_session_id"] = int(qq.get("id")) if qq.get("id") is not None else None
        out["session_type"] = out.get("session_type") or daily_payload.get("session_type")
        out["goal"] = out.get("goal") or goal
        if out.get("source") is None:
            out["planned_session_name"] = _infer_planned_session_name_from_questionnaire_payload(payload)
            out["mode"] = _infer_monitor_mode_from_questionnaire_payload(payload)
            out["sport"] = _infer_sport_from_questionnaire_payload(payload)
            out["source"] = "questionnaire_session"

    if not out.get("planned_session_name"):
        out["planned_session_name"] = "Entreno normal"
    if not out.get("mode"):
        out["mode"] = "train"
    if not out.get("sport"):
        out["sport"] = "gym"
    if out.get("goal") is None:
        out["goal"] = ""

    return out



# ============================================================
# ✅ PASO 1 (Rutinas) — API recomendación (dolor + daily_summary)
# ============================================================

def get_routine_week_summary(*, user_id: int, day: Optional[date] = None) -> Dict:
    """Resumen simple para UI: nº días con rutina registrada en la semana actual."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    d = day or date.today()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, day, score_avg
            FROM routine_sessions
            WHERE user_id=? AND day BETWEEN ? AND ?
            ORDER BY day ASC
            """,
            (uid, monday.isoformat(), sunday.isoformat()),
        ).fetchall()

    days = sorted({r["day"] for r in rows})
    avg_score = 0.0
    if rows:
        avg_score = sum(float(r["score_avg"] or 0.0) for r in rows) / max(len(rows), 1)

    return {
        "start_day": monday.isoformat(),
        "end_day": sunday.isoformat(),
        "planned_days": len(days),
        "sessions_count": len(rows),
        "avg_score": float(avg_score),
    }


def _safe_get(d: Dict, path: List[str], default=0.0):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def get_recommended_routine_today(*, user_id: int, day: Optional[date] = None) -> Dict:
    """
    Heurística MVP (PASO 1):
    - Lee daily_summary del día: thor_red_s / lum_red_s / comp_avg
    - Lee último questionnaire_sessions.payload_json para dolor por zona
    - Devuelve un plan simple con 3 ejercicios
    """
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    d = day or date.today()
    daily = get_daily_summary(user_id=uid, day=d) or {}
    q = get_latest_questionnaire_session(user_id=uid) or {}
    payload = q.get("payload") if isinstance(q, dict) else {}
    payload = payload if isinstance(payload, dict) else {}

    pain_lum = float(_safe_get(payload, ["pain", "low_back"], _safe_get(payload, ["pain", "lumbar"], 0.0)))
    pain_thor = float(_safe_get(payload, ["pain", "thoracic"], _safe_get(payload, ["pain", "dorsal"], 0.0)))
    pain_neck = float(_safe_get(payload, ["pain", "neck"], _safe_get(payload, ["pain", "cervical"], 0.0)))

    thor_red = float(daily.get("thor_red_s") or 0.0)
    lum_red = float(daily.get("lum_red_s") or 0.0)
    comp = float(daily.get("comp_avg") or 0.0)

    focus = "general"
    if pain_lum >= 6 or lum_red > thor_red * 1.2:
        focus = "lumbar"
    elif pain_thor >= 6 or thor_red > lum_red * 1.2:
        focus = "thoracic"
    elif pain_neck >= 6:
        focus = "neck"
    elif comp >= 35:
        focus = "anti_compensation"

    if focus == "lumbar":
        exercises = [
            {"name": "Hip Hinge Drill", "sets": 2, "reps": 10},
            {"name": "Dead Bug", "sets": 2, "reps": 12},
            {"name": "Glute Bridge", "sets": 2, "reps": 12},
        ]
        title = "Rutina recomendada (Protección lumbar)"
    elif focus == "thoracic":
        exercises = [
            {"name": "Thoracic Extension", "sets": 2, "reps": 10},
            {"name": "Wall Slides", "sets": 2, "reps": 12},
            {"name": "Band Pull Apart", "sets": 2, "reps": 15},
        ]
        title = "Rutina recomendada (Movilidad torácica)"
    elif focus == "neck":
        exercises = [
            {"name": "Chin Tucks", "sets": 2, "reps": 12},
            {"name": "Scapular Retraction", "sets": 2, "reps": 12},
            {"name": "Breathing Reset", "sets": 2, "reps": 6},
        ]
        title = "Rutina recomendada (Cervical/escápulas)"
    elif focus == "anti_compensation":
        exercises = [
            {"name": "Anti-Extension Plank", "sets": 2, "reps": 30},
            {"name": "Pallof Press", "sets": 2, "reps": 10},
            {"name": "Side Plank", "sets": 2, "reps": 20},
        ]
        title = "Rutina recomendada (Control/compensación)"
    else:
        exercises = [
            {"name": "Posture Reset", "sets": 2, "reps": 8},
            {"name": "Cat-Camel", "sets": 2, "reps": 10},
            {"name": "Hip Opener", "sets": 2, "reps": 10},
        ]
        title = "Rutina recomendada (Corrección general)"

    link_ctx = get_monitor_link_context(user_id=uid, day=d)
    questionnaire_payload = link_ctx.get("questionnaire_payload") if isinstance(link_ctx, dict) else {}
    if not isinstance(questionnaire_payload, dict):
        questionnaire_payload = {}
    daily_payload = questionnaire_payload.get("daily") if isinstance(questionnaire_payload.get("daily"), dict) else {}
    session_type = link_ctx.get("session_type") or daily_payload.get("session_type") or "normal"
    mode = link_ctx.get("mode") or _infer_monitor_mode_from_questionnaire_payload(questionnaire_payload)
    sport = link_ctx.get("sport") or "gym"
    planned_session_name = link_ctx.get("planned_session_name") or title

    return {
        "title": title,
        "planned_session_name": planned_session_name,
        "mode": mode,
        "sport": sport,
        "session_type": session_type,
        "goal": link_ctx.get("goal") or daily_payload.get("goal") or "",
        "questionnaire_session_id": link_ctx.get("questionnaire_session_id"),
        "routine_session_id": link_ctx.get("routine_session_id"),
        "source": link_ctx.get("source") or "routine_recommendation",
        "focus": focus,
        "inputs": {
            "pain": {"neck": pain_neck, "thor": pain_thor, "lum": pain_lum},
            "daily": {"thor_red_s": thor_red, "lum_red_s": lum_red, "comp_avg": comp},
        },
        "questionnaire_payload": questionnaire_payload,
        "exercises": exercises,
    }





# compat-padding-step-1
# compat-padding-step-1

# ============================================================
# Exportación de informe Axisfit — helpers de lectura para PDF/CSV
# ============================================================
def list_recent_sensor_sessions_for_user(*, user_id: int, limit: int = 20) -> List[Dict]:
    """Devuelve sesiones de sensor recientes con resumen agregado si existe.

    Uso principal:
    - Informe PDF del monitor
    - Resumen rápido
    - CSV técnico
    """
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    lim = max(1, min(int(limit or 20), 200))

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.user_id,
                s.kind,
                s.mode,
                s.sport,
                s.planned_session_name,
                s.questionnaire_session_id,
                s.routine_session_id,
                s.baseline_test_id,
                s.context_json,
                s.started_at,
                s.ended_at,
                ss.duration_s,
                ss.thor_red_s,
                ss.lum_red_s,
                ss.alerts_count,
                ss.comp_avg,
                ss.comp_peak,
                ss.risk_index,
                ss.created_at AS summary_created_at
            FROM sensor_sessions s
            LEFT JOIN session_summary ss ON ss.session_id = s.id
            WHERE s.user_id=?
            ORDER BY datetime(COALESCE(s.ended_at, s.started_at)) DESC, s.id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()

    out: List[Dict] = []
    for r in rows:
        d = dict(r)
        d["context"] = _json_loads_safe(d.get("context_json")) if d.get("context_json") else {}
        out.append(d)
    return out


def list_daily_summaries_for_user(*, user_id: int, limit: int = 14) -> List[Dict]:
    """Devuelve los últimos daily_summary del usuario para evolución diaria/semanal."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    lim = max(1, min(int(limit or 14), 120))

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM daily_summary
            WHERE user_id=?
            ORDER BY day DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()
    return [dict(r) for r in rows]


def list_routine_sessions_for_user(*, user_id: int, limit: int = 20) -> List[Dict]:
    """Devuelve rutinas recientes con plan_json normalizado."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    lim = max(1, min(int(limit or 20), 200))

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM routine_sessions
            WHERE user_id=?
            ORDER BY datetime(COALESCE(ended_at, started_at)) DESC, day DESC, id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()

    out: List[Dict] = []
    for r in rows:
        d = dict(r)
        d["plan"] = _json_loads_safe(d.get("plan_json")) if d.get("plan_json") else {}
        out.append(d)
    return out


def list_exercise_sets_for_user(*, user_id: int, limit: int = 50) -> List[Dict]:
    """Devuelve sets recientes enlazados a routine_sessions del usuario."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    lim = max(1, min(int(limit or 50), 500))

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                es.*,
                rs.day,
                rs.score_avg AS routine_score_avg,
                rs.notes AS routine_notes
            FROM exercise_sets es
            JOIN routine_sessions rs ON rs.id = es.routine_session_id
            WHERE rs.user_id=?
            ORDER BY datetime(es.created_at) DESC, es.id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()
    return [dict(r) for r in rows]


def list_sensor_raw_samples_for_user(*, user_id: int, limit: int = 500) -> List[Dict]:
    """Devuelve muestras RAW recientes de todas las sesiones del usuario."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    lim = max(1, min(int(limit or 500), 5000))

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                r.*,
                s.kind,
                s.mode,
                s.sport,
                s.planned_session_name,
                s.started_at,
                s.ended_at
            FROM sensor_samples_raw r
            JOIN sensor_sessions s ON s.id = r.session_id
            WHERE s.user_id=?
            ORDER BY datetime(s.started_at) DESC, r.ts_ms DESC, r.id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()
    return [dict(r) for r in rows]


def list_sensor_agg_samples_for_user(*, user_id: int, limit: int = 500) -> List[Dict]:
    """Devuelve muestras agregadas recientes de todas las sesiones del usuario."""
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    lim = max(1, min(int(limit or 500), 5000))

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                a.*,
                s.kind,
                s.mode,
                s.sport,
                s.planned_session_name,
                s.started_at,
                s.ended_at
            FROM sensor_samples_agg a
            JOIN sensor_sessions s ON s.id = a.session_id
            WHERE s.user_id=?
            ORDER BY datetime(s.started_at) DESC, a.ts_s DESC, a.id DESC
            LIMIT ?
            """,
            (uid, lim),
        ).fetchall()
    return [dict(r) for r in rows]

