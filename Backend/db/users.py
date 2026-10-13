from db.connection import execute_query
from config import Config


def _encrypt_totp_secret(secret: str) -> str:
    """Encrypt newly provisioned TOTP secrets before persisting them."""
    from cryptography.fernet import Fernet
    if not Config.TOTP_ENCRYPTION_KEY:
        raise RuntimeError("TOTP_ENCRYPTION_KEY must be configured before enrolling an authenticator")
    return Fernet(Config.TOTP_ENCRYPTION_KEY.encode()).encrypt(secret.encode()).decode()


def _decrypt_user_totp(user):
    """Decrypt stored TOTP material; tolerate legacy plaintext during migration."""
    if not user or not user.get("totp_secret") or not Config.TOTP_ENCRYPTION_KEY:
        return user
    from cryptography.fernet import Fernet, InvalidToken
    try:
        user["totp_secret"] = Fernet(Config.TOTP_ENCRYPTION_KEY.encode()).decrypt(user["totp_secret"].encode()).decode()
    except (InvalidToken, ValueError):
        pass  # Existing installations may contain legacy plaintext secrets.
    return user



# ── CRUD helpers for the `users` table ─────────────────────────────────────────

def create_user(username: str, email: str, password_hash: str, role: str = "user") -> int:
    sql = """
        INSERT INTO users (username, email, password_hash, role)
        VALUES (%s, %s, %s, %s)
    """
    return execute_query(sql, (username, email, password_hash, role), commit=True)


def get_user_by_id(user_id: int) -> dict | None:
    return _decrypt_user_totp(execute_query(
        "SELECT * FROM users WHERE user_id = %s", (user_id,), fetch="one"
    ))


def get_user_by_email(email: str) -> dict | None:
    return _decrypt_user_totp(execute_query(
        "SELECT * FROM users WHERE email = %s", (email,), fetch="one"
    ))


def get_user_by_username(username: str) -> dict | None:
    return _decrypt_user_totp(execute_query(
        "SELECT * FROM users WHERE username = %s", (username,), fetch="one"
    ))


def update_last_login(user_id: int):
    execute_query(
        "UPDATE users SET last_login_at = NOW(), failed_login_attempts = 0, account_locked_until = NULL WHERE user_id = %s",
        (user_id,), commit=True
    )


def increment_failed_attempts(user_id: int):
    execute_query(
        "UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE user_id = %s",
        (user_id,), commit=True
    )


def lock_account(user_id: int, until_dt):
    execute_query(
        "UPDATE users SET account_locked_until = %s WHERE user_id = %s",
        (until_dt, user_id), commit=True
    )


def unlock_account(user_id: int):
    execute_query(
        "UPDATE users SET account_locked_until = NULL, failed_login_attempts = 0 WHERE user_id = %s",
        (user_id,), commit=True
    )


def set_totp_secret(user_id: int, secret: str):
    encrypted = _encrypt_totp_secret(secret)
    execute_query(
        "UPDATE users SET totp_secret = %s WHERE user_id = %s",
        (encrypted, user_id), commit=True
    )


def enable_2fa(user_id: int):
    execute_query(
        "UPDATE users SET is_2fa_enabled = 1 WHERE user_id = %s",
        (user_id,), commit=True
    )


def disable_2fa(user_id: int):
    execute_query(
        "UPDATE users SET is_2fa_enabled = 0, totp_secret = NULL WHERE user_id = %s",
        (user_id,), commit=True
    )


def update_password(user_id: int, new_hash: str):
    execute_query(
        "UPDATE users SET password_hash = %s WHERE user_id = %s",
        (new_hash, user_id), commit=True
    )


def update_profile(user_id: int, username: str, email: str):
    execute_query(
        "UPDATE users SET username = %s, email = %s WHERE user_id = %s",
        (username, email, user_id), commit=True
    )


def list_users(limit: int = 100, offset: int = 0) -> list:
    return execute_query(
        """SELECT user_id, username, email, role, is_2fa_enabled,
                  failed_login_attempts, account_locked_until, is_active,
                  email_verified, created_at, last_login_at
           FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s""",
        (limit, offset), fetch="all"
    )


def admin_update_user(user_id: int, role: str = None, email_verified: bool = None):
    parts, params = [], []
    if role is not None:
        parts.append("role = %s"); params.append(role)
    if email_verified is not None:
        parts.append("email_verified = %s"); params.append(int(email_verified))
    if not parts:
        return
    params.append(user_id)
    execute_query(f"UPDATE users SET {', '.join(parts)} WHERE user_id = %s", params, commit=True)


def set_user_active(user_id: int, active: bool):
    """Enable or ban a user account without deleting audit history."""
    execute_query("UPDATE users SET is_active = %s WHERE user_id = %s", (int(active), user_id), commit=True)


def delete_user(user_id: int):
    execute_query("DELETE FROM users WHERE user_id = %s", (user_id,), commit=True)


def get_user_count() -> int:
    row = execute_query("SELECT COUNT(*) AS cnt FROM users", fetch="one")
    return row["cnt"] if row else 0


# ── Backup codes ────────────────────────────────────────────────────────────────

def save_backup_codes(user_id: int, code_hashes: list[str]):
    from db.connection import execute_many
    execute_many(
        "INSERT INTO backup_codes (user_id, code_hash) VALUES (%s, %s)",
        [(user_id, h) for h in code_hashes]
    )



def get_unused_backup_codes(user_id: int) -> list:
    return execute_query(
        "SELECT * FROM backup_codes WHERE user_id = %s AND used = 0",
        (user_id,), fetch="all"
    )


def mark_backup_code_used(code_id: int):
    execute_query(
        "UPDATE backup_codes SET used = 1, used_at = NOW() WHERE code_id = %s",
        (code_id,), commit=True
    )


def provision_admin_from_env():
    """Create the initial admin only from environment-provided credentials."""
    import os
    import bcrypt
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not (username and email and password):
        return False
    if len(password) < 12:
        raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters")
    if get_user_by_username(username) or get_user_by_email(email):
        return False  # Never silently promote or overwrite an existing account.
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    create_user(username, email, password_hash, role="admin")
    return True
