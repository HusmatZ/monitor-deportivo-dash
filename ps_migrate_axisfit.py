# ps_migrate_axisfit.py
# Migración sin tocar el código de la app:
# - Copia usuarios/perfiles/enlaces desde user.db / users.db / users.deb a axisfit.db
# - Asigna una contraseña temporal a los migrados para que puedan iniciar sesión
#   con el sistema actual (texto plano).

import sqlite3, json
from pathlib import Path

BASE = Path(__file__).parent
DST_DB = BASE / "axisfit.db"
SRC_CANDIDATES = [BASE / "user.db", BASE / "users.db", BASE / "users.deb"]

TEMP_PASSWORD = "AxisTemp123"  # <- cámbiala si quieres

def open_db(p):
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    return con

def t_exists(con, name):
    return con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()[0] > 0

def ensure_axis_schema(dst):
    cur = dst.cursor()
    # No cambia la app: solo asegura que las tablas existen
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT,
        email             TEXT UNIQUE,
        password          TEXT,
        country           TEXT,
        role              TEXT,
        created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
        -- ATLETA
        ath_uso           TEXT,
        ath_nivel         TEXT,
        ath_freq          TEXT,
        ath_molestias     TEXT,
        ath_vas           INTEGER,
        ath_box           TEXT,
        ath_altura        REAL,
        ath_peso          REAL,
        -- ENTRENADOR
        co_especialidad   TEXT,
        co_anios          TEXT,
        co_centro         TEXT,
        co_ubicacion      TEXT,
        co_modalidad      TEXT,
        co_disponibilidad TEXT,
        co_cred           INTEGER
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS coach_athlete_links (
        coach_id    INTEGER NOT NULL,
        athlete_id  INTEGER NOT NULL,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (coach_id, athlete_id)
    )
    """)
    dst.commit()

def jdump(x):
    try: return json.dumps(x if x is not None else [])
    except Exception: return "[]"

def jload_list(s):
    if s is None: return []
    s = str(s).strip()
    if not s: return []
    try: return json.loads(s)
    except Exception: return [p.strip() for p in s.split(",") if p.strip()]

def migrate_users(src_path: Path, dst) -> int:
    if not src_path.exists(): return 0
    s = open_db(src_path)
    try:
        if not t_exists(s, "users"): return 0
        rows = s.execute("SELECT * FROM users").fetchall()
    finally:
        s.close()

    cur = dst.cursor()
    inserted = 0
    for r in rows:
        email = (r.get("email") or "").strip().lower()
        if not email: continue
        name = r.get("name")
        country = r.get("country")
        role = r.get("role")
        created_at = r.get("created_at")

        # No machacamos usuarios ya existentes en axisfit.db
        cur.execute("""
            INSERT OR IGNORE INTO users (name, email, password, country, role, created_at,
                                         ath_uso, ath_nivel, ath_freq, ath_molestias, ath_vas, ath_box, ath_altura, ath_peso,
                                         co_especialidad, co_anios, co_centro, co_ubicacion, co_modalidad, co_disponibilidad, co_cred)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, '[]', NULL, NULL, NULL, NULL, '[]', NULL, NULL, NULL, '[]', NULL, 0)
        """, (name, email, TEMP_PASSWORD, country, role, created_at))
        if cur.rowcount == 1:
            inserted += 1
    dst.commit()
    return inserted

def migrate_athlete_profile(src_path: Path, dst) -> int:
    if not src_path.exists(): return 0
    s = open_db(src_path)
    try:
        table = "athlete_profile" if t_exists(s, "athlete_profile") else ("athlete_profiles" if t_exists(s, "athlete_profiles") else None)
        if not table: return 0
        rows = s.execute(f"SELECT * FROM {table}").fetchall()
        umap = {}
        for u in s.execute("SELECT id, email FROM users").fetchall():
            umap[int(u["id"])] = (u["email"] or "").strip().lower()
    finally:
        s.close()

    cur = dst.cursor()
    updated = 0
    for r in rows:
        email = umap.get(int(r.get("user_id"))) if r.get("user_id") in umap else None
        if not email: continue
        uso   = r.get("uso")
        nivel = r.get("nivel")
        freq  = r.get("freq")
        mols  = jload_list(r.get("molestias_json") if "molestias_json" in r.keys() else r.get("molestias"))
        vas   = r.get("vas")
        box   = r.get("box")
        altura = r.get("altura", None) if "altura" in r.keys() else r.get("altura_cm", None)
        peso   = r.get("peso", None) if "peso" in r.keys() else r.get("peso_kg", None)

        cur.execute("""
            UPDATE users SET ath_uso=?, ath_nivel=?, ath_freq=?, ath_molestias=?, ath_vas=?, ath_box=?, ath_altura=?, ath_peso=?
            WHERE LOWER(TRIM(email)) = ?
        """, (uso, nivel, freq, jdump(mols), vas, box, altura, peso, email))
        if cur.rowcount == 1:
            updated += 1
    dst.commit()
    return updated

def migrate_coach_profile(src_path: Path, dst) -> int:
    if not src_path.exists(): return 0
    s = open_db(src_path)
    try:
        table = "coach_profile" if t_exists(s, "coach_profile") else ("coach_profiles" if t_exists(s, "coach_profiles") else None)
        if not table: return 0
        rows = s.execute(f"SELECT * FROM {table}").fetchall()
        umap = {}
        for u in s.execute("SELECT id, email FROM users").fetchall():
            umap[int(u["id"])] = (u["email"] or "").strip().lower()
    finally:
        s.close()

    cur = dst.cursor()
    updated = 0
    for r in rows:
        email = umap.get(int(r.get("user_id"))) if r.get("user_id") in umap else None
        if not email: continue
        esp = jload_list(r.get("especialidad_json") if "especialidad_json" in r.keys() else r.get("especialidad"))
        anios = r.get("anios")
        centro = r.get("centro")
        ubic   = r.get("ubicacion")
        mod = jload_list(r.get("modalidad_json") if "modalidad_json" in r.keys() else r.get("modalidad"))
        disp = r.get("disponibilidad")
        cred = r.get("cred", None) if "cred" in r.keys() else r.get("acepta_verificacion", 0)

        cur.execute("""
            UPDATE users SET
                co_especialidad=?, co_anios=?, co_centro=?, co_ubicacion=?, co_modalidad=?, co_disponibilidad=?, co_cred=?
            WHERE LOWER(TRIM(email)) = ?
        """, (jdump(esp), anios, centro, ubic, jdump(mod), disp, int(bool(cred or 0)), email))
        if cur.rowcount == 1:
            updated += 1
    dst.commit()
    return updated

def migrate_links(src_path: Path, dst) -> int:
    if not src_path.exists(): return 0
    s = open_db(src_path)
    try:
        if not t_exists(s, "coach_athletes"): return 0
        rows = s.execute("SELECT coach_email, athlete_email FROM coach_athletes").fetchall()
    finally:
        s.close()

    cur = dst.cursor()
    created = 0
    for r in rows:
        coach_email = (r["coach_email"] or "").strip().lower()
        athlete_email = (r["athlete_email"] or "").strip().lower()
        if not coach_email or not athlete_email: continue
        rc = cur.execute("SELECT id FROM users WHERE LOWER(TRIM(email))=?", (coach_email,)).fetchone()
        ra = cur.execute("SELECT id FROM users WHERE LOWER(TRIM(email))=?", (athlete_email,)).fetchone()
        if not rc or not ra: continue
        cur.execute("INSERT OR IGNORE INTO coach_athlete_links (coach_id, athlete_id) VALUES (?,?)", (int(rc[0]), int(ra[0])))
        if cur.rowcount == 1: created += 1
    dst.commit()
    return created

if __name__ == "__main__":
    DST_DB.touch(exist_ok=True)
    dst = open_db(DST_DB)
    ensure_axis_schema(dst)

    total_u = total_ath = total_co = total_l = 0
    print("== Migración → axisfit.db (sin cambiar código) ==")
    for src in SRC_CANDIDATES:
        if not src.exists(): continue
        print(f"\nLeyendo: {src.name}")
        u = migrate_users(src, dst)
        a = migrate_athlete_profile(src, dst)
        c = migrate_coach_profile(src, dst)
        l = migrate_links(src, dst)
        print(f"  Usuarios insertados: {u}")
        print(f"  Perfiles atleta actualizados: {a}")
        print(f"  Perfiles entrenador actualizados: {c}")
        print(f"  Enlaces creados: {l}")
        total_u += u; total_ath += a; total_co += c; total_l += l

    # Normalización mínima
    cur = dst.cursor()
    cur.execute("UPDATE users SET email = LOWER(TRIM(email)) WHERE email IS NOT NULL")
    cur.execute("UPDATE users SET password = TRIM(password) WHERE password IS NOT NULL")
    dst.commit()

    n_users = dst.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_links = dst.execute("SELECT COUNT(*) FROM coach_athlete_links").fetchone()[0]
    print("\n== Resumen ==")
    print(f"Usuarios totales en axisfit.db: {n_users}")
    print(f"Enlaces totales coach<->athlete: {n_links}")
    print(f"Contraseña temporal asignada a migrados: {TEMP_PASSWORD}")
    dst.close()
