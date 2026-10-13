"""
app.py — Flask application factory & entry-point.
Run with:  python app.py
"""
import os
import logging
from flask import Flask, jsonify
from flask_cors import CORS

from config import Config


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── Logging ──────────────────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.DEBUG if Config.DEBUG else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    # Allow the local frontend to access API endpoints.
    CORS(
        app,
        resources={r"/api/*": {
            "origins": [
                "http://127.0.0.1:5500",
                "http://localhost:5500",
            ]
        }},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    # ── Upload folder ─────────────────────────────────────────────────────────
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs("ml/weights", exist_ok=True)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from routes.auth      import auth_bp
    from routes.user      import user_bp
    from routes.admin     import admin_bp
    from routes.detection import detection_bp
    from routes.signs     import signs_bp

    for bp in (auth_bp, user_bp, admin_bp, detection_bp, signs_bp):
        app.register_blueprint(bp)

    # Provision initial admin only from environment; no source-controlled default password.
    try:
        from db.users import provision_admin_from_env
        if provision_admin_from_env():
            app.logger.info("Initial administrator provisioned; TOTP enrollment is mandatory")
    except Exception as exc:
        app.logger.warning("Admin provisioning skipped: %s", exc)

    # ── Global error handlers ─────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "File too large (max 100 MB)"}), 413

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception(e)
        return jsonify({"error": "Internal server error"}), 500

    # ── Health check ──────────────────────────────────────────────────────────
    @app.route("/api/health")
    def health():
        import ml.pipeline as pipeline
        return jsonify({
            "status": "ok",
            "ml_mode": "real" if pipeline.WEIGHTS_READY else "stub"
        }), 200

    return app


app = create_app()


if __name__ == "__main__":
    # Pre-load ML models before first request
    with app.app_context():
        try:
            from ml.pipeline import load_models
            load_models()
        except Exception as e:
            app.logger.warning(f"ML model load skipped: {e}")

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=Config.DEBUG
    )
