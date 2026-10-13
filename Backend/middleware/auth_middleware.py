"""auth_middleware.py — Session-based authentication decorators."""
from functools import wraps
from flask import request, jsonify, g
from db.sessions_db import get_session_by_token
from db.users import get_user_by_id


def _extract_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def require_auth(f):
    """Decorator: validates Bearer token, attaches g.user, g.session_token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"error": "Authentication required"}), 401

        session = get_session_by_token(token)
        if not session:
            return jsonify({"error": "Invalid or expired session"}), 401

        user = get_user_by_id(session["user_id"])
        if not user:
            return jsonify({"error": "User not found"}), 401

        if not user.get("is_active", 1):
            return jsonify({"error": "Account is disabled"}), 403
        if not user.get("is_2fa_enabled"):
            return jsonify({"error": "Two-factor authentication setup is required"}), 403

        g.user          = user
        g.session_token = token
        g.session       = session
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Decorator: must be used AFTER @require_auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(g, "user") or g.user.get("role") != "admin":
            return jsonify({"error": "Admin privileges required"}), 403
        return f(*args, **kwargs)
    return decorated
