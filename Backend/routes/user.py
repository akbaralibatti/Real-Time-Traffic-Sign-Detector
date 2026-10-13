"""routes/user.py — User self-service endpoints."""
import bcrypt
from flask import Blueprint, request, jsonify, g

from db.users import get_user_by_id, update_profile, update_password, get_user_by_email, get_user_by_username
from db.sessions_db import list_user_sessions, revoke_session_by_id, revoke_all_user_sessions
from db.activity_logs import log_event
from middleware.auth_middleware import require_auth

user_bp = Blueprint("user", __name__, url_prefix="/api/user")


def _safe_user(u): return {k: v for k, v in u.items()
                            if k not in ("password_hash", "totp_secret")}


@user_bp.route("/profile", methods=["GET"])
@require_auth
def get_profile():
    safe = _safe_user(g.user)
    return jsonify({"user": safe, **safe}), 200


@user_bp.route("/profile", methods=["PATCH"])
@require_auth
def update_profile_route():
    data     = request.get_json() or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email")    or "").strip().lower()

    if not username or not email:
        return jsonify({"error": "username and email required"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username too short"}), 400

    # Check uniqueness (allow same as own)
    existing = get_user_by_username(username)
    if existing and existing["user_id"] != g.user["user_id"]:
        return jsonify({"error": "Username taken"}), 409
    existing = get_user_by_email(email)
    if existing and existing["user_id"] != g.user["user_id"]:
        return jsonify({"error": "Email in use"}), 409

    update_profile(g.user["user_id"], username, email)
    log_event("profile_update", user_id=g.user["user_id"], details={"username_changed": username != g.user.get("username"), "email_changed": email != g.user.get("email")})
    updated = get_user_by_id(g.user["user_id"])
    return jsonify({"message": "Profile updated", "user": _safe_user(updated)}), 200


@user_bp.route("/change-password", methods=["POST"])
@require_auth
def change_password():
    data         = request.get_json() or {}
    current_pass = data.get("current_password", "")
    new_pass     = data.get("new_password", "")

    if not current_pass or not new_pass:
        return jsonify({"error": "current_password and new_password required"}), 400
    if len(new_pass) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400

    if not bcrypt.checkpw(current_pass.encode(), g.user["password_hash"].encode()):
        return jsonify({"error": "Current password is incorrect"}), 401

    new_hash = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
    update_password(g.user["user_id"], new_hash)

    # Revoke all other sessions
    revoke_all_user_sessions(g.user["user_id"])
    log_event("password_change", user_id=g.user["user_id"])

    return jsonify({"message": "Password changed. Please log in again."}), 200


@user_bp.route("/sessions", methods=["GET"])
@require_auth
def get_sessions():
    sessions = list_user_sessions(g.user["user_id"])
    return jsonify(sessions), 200


@user_bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@require_auth
def revoke_session_route(session_id: int):
    revoke_session_by_id(session_id)
    return jsonify({"message": "Session revoked"}), 200
