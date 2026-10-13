"""
config.py — Application configuration
All sensitive values come from environment variables (.env in dev, system env in prod).
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ── Flask ──────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    if not SECRET_KEY and os.environ.get("FLASK_DEBUG", "0") != "1":
        raise RuntimeError("SECRET_KEY must be set outside development mode")
    DEBUG      = os.environ.get("FLASK_DEBUG", "0") == "1"

    # ── MySQL ──────────────────────────────────────────────────────────────
    DB_HOST     = os.environ.get("DB_HOST",     "localhost")
    DB_PORT     = int(os.environ.get("DB_PORT", "3306"))
    DB_USER     = os.environ.get("DB_USER",     "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME     = os.environ.get("DB_NAME",     "traffic_sign_db")

    # ── Sessions ───────────────────────────────────────────────────────────
    SESSION_EXPIRE_HOURS = int(os.environ.get("SESSION_EXPIRE_HOURS", "24"))

    # ── Auth ───────────────────────────────────────────────────────────────
    MAX_LOGIN_ATTEMPTS  = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_MINUTES     = int(os.environ.get("LOCKOUT_MINUTES",    "15"))
    TOTP_ISSUER         = os.environ.get("TOTP_ISSUER", "TrafficSign-IT303")
    TOTP_ENCRYPTION_KEY = os.environ.get("TOTP_ENCRYPTION_KEY", "")

    # ── Uploads ────────────────────────────────────────────────────────────
    UPLOAD_FOLDER       = os.environ.get("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH  = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
    ALLOWED_EXTENSIONS  = {"mp4", "avi", "mov", "mkv", "webm"}

    # ── ML ─────────────────────────────────────────────────────────────────
    YOLO_WEIGHTS     = os.environ.get("YOLO_WEIGHTS", "ml/weights/best.pt")
    CONF_THRESHOLD   = float(os.environ.get("CONF_THRESHOLD", "0.35"))   # min detection confidence
    YOLO_IMGSZ = int(os.environ.get("YOLO_IMGSZ", "640"))
    YOLO_DEVICE = os.environ.get("YOLO_DEVICE", "")

    # ── CORS ───────────────────────────────────────────────────────────────
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "https://real-time-traffic-recognition-syste.vercel.app").split(",")
