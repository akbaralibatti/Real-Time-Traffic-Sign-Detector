"""routes/admin.py — Admin-only endpoints."""
from flask import Blueprint, request, jsonify, g, Response
import csv
import io

from db.users import (list_users, get_user_by_id, admin_update_user,
                      delete_user, unlock_account, get_user_count, set_user_active)
from db.activity_logs import log_event, get_logs, count_logs, get_recent_auth_events
from db.sessions_db import count_active_sessions_today, revoke_all_user_sessions
from db.detection import (get_top_detected_signs, count_total_detections,
                           count_sessions_today)
from db.signs import count_signs
from middleware.auth_middleware import require_auth, require_admin

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _safe_user(u): return {k: v for k, v in u.items()
                            if k not in ("password_hash", "totp_secret")}


# ── Dashboard summary ────────────────────────────────────────────────────────────

@admin_bp.route("/dashboard", methods=["GET"])
@require_auth
@require_admin
def dashboard():
    return jsonify({
        "total_users":         get_user_count(),
        "sessions_today":      count_sessions_today(),
        "total_detections":    count_total_detections(),
        "total_signs":         count_signs(),
        "active_sessions":     count_active_sessions_today(),
        "top_detected_signs":  get_top_detected_signs(5),
        "recent_auth_events":  get_recent_auth_events(10)
    }), 200


# ── User management ──────────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@require_auth
@require_admin
def get_users():
    limit  = int(request.args.get("limit",  50))
    offset = int(request.args.get("offset", 0))
    users  = list_users(limit, offset)
    return jsonify({"users": [_safe_user(u) for u in users],
                    "total": get_user_count()}), 200


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@require_auth
@require_admin
def get_user(user_id: int):
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(_safe_user(user)), 200


@admin_bp.route("/users/<int:user_id>", methods=["PATCH"])
@require_auth
@require_admin
def update_user(user_id: int):
    data = request.get_json() or {}
    role           = data.get("role")
    email_verified = data.get("email_verified")

    if role and role not in ("user", "admin"):
        return jsonify({"error": "role must be 'user' or 'admin'"}), 400

    target = get_user_by_id(user_id)
    if not target:
        return jsonify({"error": "User not found"}), 404
    if target.get("role") == "admin" and (role == "user" or ("is_active" in data and not bool(data["is_active"]))):
        return jsonify({"error": "Admin accounts cannot be demoted or banned through user moderation"}), 403
    admin_update_user(user_id, role=role, email_verified=email_verified)
    if "is_active" in data:
        set_user_active(user_id, bool(data["is_active"]))
        revoke_all_user_sessions(user_id) if not data["is_active"] else None
    log_event("admin_action", admin_id=g.user["user_id"],
              details={"action": "update_user", "target_user_id": user_id, "changes": {k:v for k,v in data.items() if k not in ("password", "token", "totp_secret")}})
    updated = get_user_by_id(user_id)
    return jsonify({"message": "User updated", "user": _safe_user(updated)}), 200


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_auth
@require_admin
def remove_user(user_id: int):
    if user_id == g.user["user_id"]:
        return jsonify({"error": "Cannot delete your own account"}), 400
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user.get("role") == "admin":
        return jsonify({"error": "Admin accounts cannot be removed through user moderation"}), 403
    delete_user(user_id)
    log_event("admin_action", admin_id=g.user["user_id"],
              details={"action": "delete_user", "target_user_id": user_id})
    return jsonify({"message": "User deleted"}), 200


@admin_bp.route("/users/<int:user_id>/unlock", methods=["POST"])
@require_auth
@require_admin
def unlock_user(user_id: int):
    unlock_account(user_id)
    log_event("account_unlocked", admin_id=g.user["user_id"],
              user_id=user_id, details={"unlocked_by_admin": g.user["user_id"]})
    return jsonify({"message": "Account unlocked"}), 200


@admin_bp.route("/users/<int:user_id>/revoke-sessions", methods=["POST"])
@require_auth
@require_admin
def revoke_user_sessions(user_id: int):
    revoke_all_user_sessions(user_id)
    log_event("admin_action", admin_id=g.user["user_id"],
              details={"action": "revoke_sessions", "target_user_id": user_id})
    return jsonify({"message": "All sessions revoked"}), 200


@admin_bp.route("/users/report.csv", methods=["GET"])
@require_auth
@require_admin
def download_users_report():
    """Export user account metadata, never credential material, as CSV."""
    users = list_users(10000, 0)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["user_id", "username", "email", "role", "is_active", "is_2fa_enabled", "last_login_at", "created_at"])
    writer.writeheader()
    for user in users:
        writer.writerow({key: user.get(key) for key in writer.fieldnames})
    log_event("admin_action", admin_id=g.user["user_id"], details={"action": "export_users_report"})
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=trafficvision-users.csv"})


# ── Activity logs ────────────────────────────────────────────────────────────────

@admin_bp.route("/logs", methods=["GET"])
@require_auth
@require_admin
def get_activity_logs():
    limit      = int(request.args.get("limit",   50))
    offset     = int(request.args.get("offset",   0))
    event_type = request.args.get("event_type")
    user_id    = request.args.get("user_id")
    date_from  = request.args.get("date_from")
    date_to    = request.args.get("date_to")

    logs  = get_logs(limit, offset, event_type,
                     int(user_id) if user_id else None,
                     date_from, date_to)
    total = count_logs(event_type=event_type,
                       user_id=int(user_id) if user_id else None)
    return jsonify({"logs": logs, "total": total}), 200
