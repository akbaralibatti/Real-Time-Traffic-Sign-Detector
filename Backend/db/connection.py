"""
db/connection.py — Database Connection Layer
Supports MySQL with automatic SQLite fallback if MySQL is unavailable.
"""
import os
import re
import json
import logging
import sqlite3
from pathlib import Path
from config import Config

logger = logging.getLogger(__name__)

_mysql_pool = None
_use_sqlite = False
_sqlite_path = Path(__file__).resolve().parent.parent / "traffic_sign.db"


def _init_sqlite_db():
    """Initializes tables and seeds default data in SQLite if not present."""
    conn = sqlite3.connect(str(_sqlite_path))
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 1,
        totp_secret TEXT,
        is_2fa_enabled INTEGER NOT NULL DEFAULT 0,
        failed_login_attempts INTEGER NOT NULL DEFAULT 0,
        account_locked_until TIMESTAMP,
        email_verified INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS backup_codes (
        code_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        code_hash TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        used_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sessions (
        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        ip_address TEXT,
        user_agent TEXT,
        revoked INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS activity_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        admin_id INTEGER,
        event_type TEXT NOT NULL,
        event_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        details TEXT,
        ip_address TEXT
    );

    CREATE TABLE IF NOT EXISTS sign_meaning_dictionary (
        class_id INTEGER PRIMARY KEY,
        sign_name TEXT NOT NULL,
        category TEXT NOT NULL,
        sign_meaning TEXT,
        sign_description TEXT,
        description TEXT,
        icon_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS recognition_sessions (
        rec_session_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        user_id INTEGER NOT NULL,
        session_type TEXT NOT NULL DEFAULT 'live',
        source_type TEXT NOT NULL DEFAULT 'live',
        source_filename TEXT,
        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        end_time TIMESTAMP,
        frames_processed INTEGER DEFAULT 0,
        avg_fps REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS detection_results (
        detection_id INTEGER PRIMARY KEY AUTOINCREMENT,
        rec_session_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        sign_class_id INTEGER,
        confidence_score REAL NOT NULL,
        confidence REAL,
        bbox_x REAL,
        bbox_y REAL,
        bbox_w REAL,
        bbox_h REAL,
        bbox_width REAL,
        bbox_height REAL,
        detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()

    # Additive migrations preserve accounts, sessions and audit records.
    sign_columns = {row[1] for row in cursor.execute("PRAGMA table_info(sign_meaning_dictionary)").fetchall()}
    if "sign_description" not in sign_columns:
        cursor.execute("ALTER TABLE sign_meaning_dictionary ADD COLUMN sign_description TEXT")
        if "description" in sign_columns:
            cursor.execute("UPDATE sign_meaning_dictionary SET sign_description=description WHERE sign_description IS NULL")
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
    if "is_active" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    # Never create a hard-coded administrator. Provision one only from environment.
    admin_username = os.environ.get("ADMIN_USERNAME", "").strip()
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if admin_username and admin_email and admin_password:
        if len(admin_password) < 12:
            raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters")
        import bcrypt
        existing = cursor.execute("SELECT user_id FROM users WHERE username=? OR email=?",
                                  (admin_username, admin_email)).fetchone()
        if not existing:
            hashed = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
            cursor.execute("INSERT INTO users (username,email,password_hash,role,email_verified,is_active) VALUES (?,?,?,'admin',1,1)",
                           (admin_username, admin_email, hashed))
            conn.commit()
            logger.info("Provisioned administrator from environment; 2FA enrollment is required")

    # Seed the exact supported classes only when the dictionary is empty.
    signs = [
        (0, "cross_road", "cautionary", "Cross-road intersection ahead; watch for cross traffic."),
        (1, "gap_in_median", "cautionary", "Opening in the road median ahead."),
        (2, "hump", "cautionary", "Road hump or speed breaker ahead; reduce speed."),
        (3, "left_hand_curve", "cautionary", "Left-hand curve ahead; reduce speed."),
        (4, "men_at_work", "cautionary", "Road works ahead; proceed with caution."),
        (5, "narrow_bridge", "cautionary", "Narrow bridge ahead; watch for oncoming traffic."),
        (6, "pedestrian", "cautionary", "Pedestrian crossing ahead; give way to pedestrians."),
        (7, "right_hand_curve", "cautionary", "Right-hand curve ahead; reduce speed."),
        (8, "school_ahead", "cautionary", "School zone ahead; watch for children."),
        (9, "side_road_left", "cautionary", "Side road joining from the left."),
        (10, "side_road_right", "cautionary", "Side road joining from the right."),
    ]
    existing_signs = cursor.execute("SELECT COUNT(*) FROM sign_meaning_dictionary").fetchone()[0]
    if existing_signs == 0:
        cursor.executemany("INSERT INTO sign_meaning_dictionary (class_id, sign_name, category, sign_meaning, sign_description, description) VALUES (?,?,?,?,?,?)",
                           [(i, n, c, m, m, m) for i,n,c,m in signs])
        conn.commit()

    conn.close()



def _try_get_mysql_pool():
    global _mysql_pool, _use_sqlite
    if _use_sqlite:
        return None
    if _mysql_pool is not None:
        return _mysql_pool

    try:
        import mysql.connector
        from mysql.connector import pooling
        _mysql_pool = pooling.MySQLConnectionPool(
            pool_name="trafficdb",
            pool_size=5,
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            charset="utf8mb4",
            autocommit=False,
        )
        logger.info(f"Connected to MySQL on {Config.DB_HOST}:{Config.DB_PORT}")
        return _mysql_pool
    except Exception as e:
        logger.warning(f"Could not connect to MySQL ({e}). Falling back to SQLite.")
        _use_sqlite = True
        _init_sqlite_db()
        return None


def execute_query(sql: str, params=None, *, fetch="none", commit=False):
    """
    Executes SQL query using MySQL pool if available, falling back to SQLite.
    Automatically adapts placeholders (%s <-> ?) and date functions.
    """
    pool = _try_get_mysql_pool()

    if pool is not None:
        # Use MySQL
        conn = pool.get_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params or ())
            if commit:
                conn.commit()
                return cursor.lastrowid
            if fetch == "one":
                return cursor.fetchone()
            if fetch == "all":
                return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
    else:
        # Use SQLite
        conn = sqlite3.connect(str(_sqlite_path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # Adapt MySQL syntax to SQLite
            adapted_sql = sql
            adapted_sql = adapted_sql.replace("NOW()", "CURRENT_TIMESTAMP")
            adapted_sql = adapted_sql.replace("CURDATE()", "date('now')")
            adapted_sql = re.sub(r'%s', '?', adapted_sql)

            # Handle datetime string vs param conversion
            adapted_params = []
            if params:
                for p in params:
                    if isinstance(p, (dict, list)):
                        adapted_params.append(json.dumps(p))
                    elif hasattr(p, 'isoformat'):
                        adapted_params.append(p.isoformat())
                    else:
                        adapted_params.append(p)

            cursor.execute(adapted_sql, adapted_params)

            if commit:
                conn.commit()
                return cursor.lastrowid
            if fetch == "one":
                row = cursor.fetchone()
                return dict(row) if row else None
            if fetch == "all":
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        finally:
            cursor.close()
            conn.close()


def execute_many(sql: str, seq_of_params, commit=True):
    """Executes executemany across MySQL or SQLite."""
    pool = _try_get_mysql_pool()
    if pool is not None:
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(sql, seq_of_params)
            if commit:
                conn.commit()
        finally:
            cursor.close()
            conn.close()
    else:
        conn = sqlite3.connect(str(_sqlite_path), timeout=10)
        try:
            cursor = conn.cursor()
            adapted_sql = sql.replace("NOW()", "CURRENT_TIMESTAMP").replace("CURDATE()", "date('now')")
            adapted_sql = re.sub(r'%s', '?', adapted_sql)
            cursor.executemany(adapted_sql, seq_of_params)
            if commit:
                conn.commit()
        finally:
            cursor.close()
            conn.close()


def get_connection():
    """Return a raw connection object from the pool or SQLite."""
    pool = _try_get_mysql_pool()
    if pool is not None:
        return pool.get_connection()
    else:
        conn = sqlite3.connect(str(_sqlite_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

