"""Traffic-sign dictionary API, restricted to authenticated users."""
from flask import Blueprint, request, jsonify
from db.signs import get_all_signs, get_sign_by_id, search_signs, get_signs_by_category, count_signs
from middleware.auth_middleware import require_auth

signs_bp = Blueprint("signs", __name__, url_prefix="/api/signs")


def _present_sign(sign: dict) -> dict:
    """Normalize SQLite/MySQL dictionary columns and attach the matching public logo path."""
    if not sign:
        return sign
    item = dict(sign)
    name = item.get("sign_name", "")
    meaning = item.get("sign_meaning") or item.get("sign_description") or item.get("description") or ""
    item["sign_meaning"] = meaning
    item["sign_description"] = item.get("sign_description") or item.get("description") or meaning
    item["logo_url"] = f"/images/traffic-signs/{name}.png"
    return item


@signs_bp.route("", methods=["GET"])
@require_auth
def list_signs():
    """Return the supported traffic-sign dictionary with consistent fields."""
    limit = min(max(int(request.args.get("limit", 100)), 1), 100)
    offset = max(int(request.args.get("offset", 0)), 0)
    category = request.args.get("category")
    signs = get_signs_by_category(category) if category else get_all_signs(limit, offset)
    return jsonify({"signs": [_present_sign(sign) for sign in signs], "total": count_signs()}), 200


@signs_bp.route("/search", methods=["GET"])
@require_auth
def search():
    """Search sign names and meanings without exposing arbitrary database data."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "q parameter required"}), 400
    return jsonify({"signs": [_present_sign(sign) for sign in search_signs(query)]}), 200


@signs_bp.route("/<int:class_id>", methods=["GET"])
@require_auth
def get_sign(class_id: int):
    """Return one canonical sign by its stable class ID."""
    sign = get_sign_by_id(class_id)
    if not sign:
        return jsonify({"error": "Sign not found"}), 404
    return jsonify(_present_sign(sign)), 200
