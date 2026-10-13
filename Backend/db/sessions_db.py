import secrets
import hashlib
from datetime import datetime, timedelta
from db.connection import execute_query
from config import Config


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_session(user_id: int, ip_address: str = None, user_agent: str = None) -> str:
    """Create a new server-side session. Returns the raw (unhashed) token."""
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.utcnow() + timedelta(hours=Config.SESSION_EXPIRE_HOURS)
    execute_query(
        """INSERT INTO sessions (user_id, token_hash, expires_at, ip_address, user_agent)
           VALUES (%s, %s, %s, %s, %s)""",
        (user_id, token_hash, expires_at, ip_address, user_agent),
        commit=True
    )
    return raw_token


def get_session_by_token(raw_token: str) -> dict | None:
    token_hash = _hash_token(raw_token)
    return execute_query(
        """SELECT * FROM sessions
           WHERE token_hash = %s AND revoked = 0 AND expires_at > NOW()""",
        (token_hash,), fetch="one"
    )


def revoke_session(raw_token: str):
    token_hash = _hash_token(raw_token)
    execute_query(
        "UPDATE sessions SET revoked = 1 WHERE token_hash = %s",
        (token_hash,), commit=True
    )


def revoke_session_by_id(session_id: int):
    execute_query(
        "UPDATE sessions SET revoked = 1 WHERE session_id = %s",
        (session_id,), commit=True
    )


def revoke_all_user_sessions(user_id: int):
    execute_query(
        "UPDATE sessions SET revoked = 1 WHERE user_id = %s",
        (user_id,), commit=True
    )


def list_user_sessions(user_id: int) -> list:
    return execute_query(
        """SELECT session_id, issued_at, expires_at, ip_address, user_agent, revoked
           FROM sessions WHERE user_id = %s ORDER BY issued_at DESC""",
        (user_id,), fetch="all"
    )


def count_active_sessions_today() -> int:
    row = execute_query(
        """SELECT COUNT(*) AS cnt FROM sessions
           WHERE DATE(issued_at) = CURDATE() AND revoked = 0""",
        fetch="one"
    )
    return row["cnt"] if row else 0
