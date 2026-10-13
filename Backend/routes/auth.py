"""
routes/auth.py — Authentication & 2FA endpoints
"""
import secrets
import io
import base64
from datetime import datetime, timedelta

import bcrypt
import pyotp
import qrcode
from flask import Blueprint, request, jsonify, g

from config import Config
from db.users import (
    create_user, get_user_by_email, get_user_by_username,
    update_last_login, increment_failed_attempts, lock_account, unlock_account,
    set_totp_secret, enable_2fa, disable_2fa,
    save_backup_codes, get_unused_backup_codes, mark_backup_code_used, update_password
)
from db.sessions_db import create_session, revoke_session, revoke_all_user_sessions
from db.activity_logs import log_event
from middleware.auth_middleware import require_auth
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# Signed short-lived challenge tokens permit only OTP/setup endpoints before a full session.
def _challenge_serializer():
    return URLSafeTimedSerializer(Config.SECRET_KEY or "development-only-secret", salt="totp-login-challenge")

def _issue_challenge(user_id):
    return _challenge_serializer().dumps({"user_id": int(user_id), "purpose": "totp"})

def _challenge_user_id(token):
    try:
        payload = _challenge_serializer().loads(token, max_age=300)
        return int(payload["user_id"]) if payload.get("purpose") == "totp" else None
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
        return None

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ── helpers ─────────────────────────────────────────────────────────────────────

def _safe_user(user: dict) -> dict:
    """Return a user dict without sensitive fields."""
    return {k: v for k, v in user.items()
            if k not in ("password_hash", "totp_secret")}


def _check_lock(user: dict):
    if user.get("account_locked_until"):
        locked_until = user["account_locked_until"]
        if isinstance(locked_until, str):
            locked_until = datetime.fromisoformat(locked_until)
        if locked_until > datetime.utcnow():
            return jsonify({
                "error": "Account is locked. Try again later.",
                "locked_until": str(locked_until)
            }), 423
    return None


# ── Register ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email")    or "").strip().lower()
    password = (data.get("password") or "")

    if not username or not email or not password:
        return jsonify({"error": "username, email and password are required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    if get_user_by_username(username):
        return jsonify({"error": "Username already taken"}), 409
    if get_user_by_email(email):
        return jsonify({"error": "Email already registered"}), 409

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = create_user(username, email, pw_hash)
    log_event("register", user_id=user_id, details={"username": username, "email": email})

    return jsonify({"message": "Account created successfully", "user_id": user_id}), 201


# ── Login ─────────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    data      = request.get_json() or {}
    identifier = (data.get("email") or data.get("username") or "").strip()
    password   = (data.get("password") or "")

    if not identifier or not password:
        return jsonify({"error": "Email/username and password required"}), 400

    user = get_user_by_email(identifier) or get_user_by_username(identifier)
    if not user or not user.get("is_active", 1):
        log_event("login_failure", user_id=(user or {}).get("user_id"), details={"reason": "invalid_or_disabled"}) if user else None
        return jsonify({"error": "Invalid credentials"}), 401

    # Check lock
    lock_resp = _check_lock(user)
    if lock_resp:
        return lock_resp

    # Verify password
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        increment_failed_attempts(user["user_id"])
        attempts = (user["failed_login_attempts"] or 0) + 1
        log_event("login_failure", user_id=user["user_id"],
                  details={"attempts": attempts})
        if attempts >= Config.MAX_LOGIN_ATTEMPTS:
            locked_until = datetime.utcnow() + timedelta(minutes=Config.LOCKOUT_MINUTES)
            lock_account(user["user_id"], locked_until)
            log_event("account_locked", user_id=user["user_id"],
                      details={"locked_until": str(locked_until)})
            return jsonify({"error": "Account locked due to too many failed attempts"}), 423
        return jsonify({"error": "Invalid credentials",
                        "attempts_remaining": Config.MAX_LOGIN_ATTEMPTS - attempts}), 401

    # No dashboard session is issued until TOTP has been configured and verified.
    challenge = _issue_challenge(user["user_id"])
    log_event("login_success", user_id=user["user_id"], details={"stage": "password", "requires_otp": bool(user.get("is_2fa_enabled"))})
    return jsonify({
        "requires_otp": bool(user.get("is_2fa_enabled")),
        "requires_setup_2fa": not bool(user.get("is_2fa_enabled")),
        "challenge_token": challenge,
        "message": "OTP verification required" if user.get("is_2fa_enabled") else "Set up two-factor authentication to continue"
    }), 200


# ── Verify OTP ────────────────────────────────────────────────────────────────────

@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data    = request.get_json() or {}
    challenge_token = data.get("challenge_token", "")
    user_id = _challenge_user_id(challenge_token)
    otp = str(data.get("otp") or "").strip()
    if not user_id or not otp:
        return jsonify({"error": "Valid challenge_token and OTP are required"}), 400

    from db.users import get_user_by_id
    user = get_user_by_id(user_id)
    if not user or not user.get("is_active", 1) or not user.get("is_2fa_enabled") or not user.get("totp_secret"):
        return jsonify({"error": "User not found or 2FA not configured"}), 404

    lock_resp = _check_lock(user)
    if lock_resp:
        return lock_resp

    totp = pyotp.TOTP(user["totp_secret"])
    if not totp.verify(otp, valid_window=1):
        increment_failed_attempts(user_id)
        log_event("otp_failure", user_id=user_id)
        return jsonify({"error": "Invalid or expired OTP"}), 401

    update_last_login(user_id)
    token = create_session(
        user_id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:255]
    )
    log_event("otp_success", user_id=user_id)

    return jsonify({
        "message": "OTP verified. Login successful.",
        "token": token,
        "user": _safe_user(user)
    }), 200


# ── Setup 2FA ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/setup-2fa", methods=["POST"])
def setup_2fa():
    data = request.get_json() or {}
    challenge_user_id = _challenge_user_id(data.get("challenge_token", ""))
    if challenge_user_id:
        from db.users import get_user_by_id
        user = get_user_by_id(challenge_user_id)
        if not user or not user.get("is_active", 1):
            return jsonify({"error": "Invalid challenge"}), 401
        if user.get("is_2fa_enabled"):
            return jsonify({"error": "Authenticator is already enrolled; verify its current code at login"}), 403
    else:
        token = request.headers.get("Authorization", "")
        if not token.startswith("Bearer "):
            return jsonify({"error": "Authentication or valid setup challenge required"}), 401
        from db.sessions_db import get_session_by_token
        session = get_session_by_token(token[7:])
        from db.users import get_user_by_id
        user = get_user_by_id(session["user_id"]) if session else None
        if not user:
            return jsonify({"error": "Invalid session"}), 401
    secret = pyotp.random_base32()
    set_totp_secret(user["user_id"], secret)

    totp = pyotp.TOTP(secret)
    uri  = totp.provisioning_uri(name=user["email"], issuer_name=Config.TOTP_ISSUER)

    # Generate QR code as base64 PNG
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return jsonify({
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_b64}",
        "otpauth_uri": uri
    }), 200


# ── Confirm 2FA ────────────────────────────────────────────────────────────────────

@auth_bp.route("/confirm-2fa", methods=["POST"])
def confirm_2fa():
    data = request.get_json() or {}
    otp = str(data.get("otp") or data.get("token") or "").strip()
    challenge_user_id = _challenge_user_id(data.get("challenge_token", ""))
    if challenge_user_id:
        from db.users import get_user_by_id
        user = get_user_by_id(challenge_user_id)
    else:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Valid setup challenge required"}), 401
        from db.sessions_db import get_session_by_token
        session = get_session_by_token(auth[7:])
        from db.users import get_user_by_id
        user = get_user_by_id(session["user_id"]) if session else None
    if not user or not user.get("is_active", 1):
        return jsonify({"error": "Invalid setup challenge"}), 401

    if not user.get("totp_secret"):
        return jsonify({"error": "2FA not set up yet. Call /setup-2fa first."}), 400

    totp = pyotp.TOTP(user["totp_secret"])
    if not totp.verify(otp, valid_window=1):
        return jsonify({"error": "Invalid OTP — could not confirm 2FA"}), 401

    enable_2fa(user["user_id"])

    # Generate backup codes
    raw_codes = [secrets.token_hex(8) for _ in range(8)]
    hashes    = [bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode() for c in raw_codes]
    save_backup_codes(user["user_id"], hashes)
    challenge_login = bool(challenge_user_id)
    response = {"message": "2FA enabled successfully", "backup_codes": raw_codes}
    if challenge_login:
        update_last_login(user["user_id"])
        response["token"] = create_session(user["user_id"], ip_address=request.remote_addr, user_agent=request.headers.get("User-Agent", "")[:255])
        from db.users import get_user_by_id
        response["user"] = _safe_user(get_user_by_id(user["user_id"]))
        log_event("otp_success", user_id=user["user_id"], details={"stage": "setup"})
    return jsonify(response), 200


# ── Disable 2FA ────────────────────────────────────────────────────────────────────

@auth_bp.route("/disable-2fa", methods=["POST"])
@require_auth
def disable_2fa_route():
    data     = request.get_json() or {}
    password = data.get("password", "")
    user     = g.user

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"error": "Password incorrect"}), 401

    return jsonify({"error": "Two-factor authentication is mandatory and cannot be disabled"}), 403


# ── Backup code login ───────────────────────────────────────────────────────────────

@auth_bp.route("/use-backup-code", methods=["POST"])
def use_backup_code():
    data    = request.get_json() or {}
    user_id = _challenge_user_id(data.get("challenge_token", ""))
    code = str(data.get("code") or "").strip()
    if not user_id or not code:
        return jsonify({"error": "Valid challenge_token and backup code are required"}), 400
    from db.users import get_user_by_id
    user_check = get_user_by_id(user_id)
    if not user_check or not user_check.get("is_active", 1) or not user_check.get("is_2fa_enabled"):
        return jsonify({"error": "Invalid challenge"}), 401
    codes = get_unused_backup_codes(user_id)
    matched = next(
        (c for c in codes if bcrypt.checkpw(code.encode(), c["code_hash"].encode())),
        None
    )
    if not matched:
        return jsonify({"error": "Invalid or already-used backup code"}), 401

    mark_backup_code_used(matched["code_id"])
    update_last_login(user_id)
    token = create_session(user_id,
                           ip_address=request.remote_addr,
                           user_agent=request.headers.get("User-Agent", "")[:255])
    log_event("otp_success", user_id=user_id, details={"method": "backup_code"})

    from db.users import get_user_by_id
    user = get_user_by_id(user_id)
    return jsonify({"message": "Backup code accepted", "token": token,
                    "user": _safe_user(user)}), 200


# ── Password reset: email + enrolled TOTP + new password ───────────────────────
@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    """Reset a password only after verifying the account's existing TOTP factor."""
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = str(data.get("otp") or "").strip()
    password = data.get("new_password") or ""
    user = get_user_by_email(email) if email else None
    if not user or not user.get("is_active", 1) or not user.get("is_2fa_enabled") or not user.get("totp_secret"):
        return jsonify({"error": "Account cannot be verified for password reset"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not pyotp.TOTP(user["totp_secret"]).verify(otp, valid_window=1):
        log_event("password_reset_failure", user_id=user["user_id"])
        return jsonify({"error": "Invalid authenticator code"}), 401
    update_password(user["user_id"], bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode())
    revoke_all_user_sessions(user["user_id"])
    log_event("password_change", user_id=user["user_id"], details={"method": "totp_password_reset"})
    return jsonify({"message": "Password reset. Please sign in again."}), 200


# ── Logout ──────────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    revoke_session(g.session_token)
    log_event("logout", user_id=g.user["user_id"])
    return jsonify({"message": "Logged out"}), 200
