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
) -> int:
    if not isinstance(user_id, int):
        raise ValueError("user_id inválido")
    kind = (kind or "").strip()
    if kind not in {"monitor", "routine", "baseline"}:
        raise ValueError("kind inválido (monitor|routine|baseline)")

    sa = (started_at or datetime.now()).isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO sensor_sessions(user_id, kind, mode, sport, started_at)
            VALUES (?,?,?,?,?)
            """,
            (user_id, kind, mode, sport, sa),
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


def upsert_user_posture_settings(*, user_id: int, thresholds: Dict) -> None:
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")
    if thresholds is None:
        thresholds = {}
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds debe ser dict")

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
            (uid, _json_dumps_safe(thresholds)),
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

    thresholds = _json_loads_safe(row["thresholds_json"])
    if not isinstance(thresholds, dict):
        thresholds = {}
    return {"user_id": uid, "thresholds": thresholds, "updated_at": row["updated_at"]}


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
    uid = resolve_user_id(user_id)
    if uid is None:
        raise ValueError("user_id inválido")

    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM baseline_tests
            WHERE user_id=?
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (uid,),
        ).fetchone()

    if not row:
        return None

    out = dict(row)
    out["baseline"] = _json_loads_safe(out.get("baseline_json"))
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

    return {
        "title": title,
        "focus": focus,
        "inputs": {
            "pain": {"neck": pain_neck, "thor": pain_thor, "lum": pain_lum},
            "daily": {"thor_red_s": thor_red, "lum_red_s": lum_red, "comp_avg": comp},
        },
        "exercises": exercises,
    }