"""routes/detection.py — Video/camera detection session endpoints."""
import os
from pathlib import Path
import cv2

from flask import Blueprint, request, jsonify, g
from config import Config
from db.detection import (create_recognition_session, end_recognition_session,
                          get_user_sessions, get_session_by_id,
                          get_session_detections, save_detection)
from db.activity_logs import log_event
from middleware.auth_middleware import require_auth
from ml.pipeline import process_frame

detection_bp = Blueprint("detection", __name__, url_prefix="/api/detection")

ALLOWED = Config.ALLOWED_EXTENSIONS


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


# ── Sessions ─────────────────────────────────────────────────────────────────────

@detection_bp.route("/sessions", methods=["GET"])
@require_auth
def list_sessions():
    sessions = get_user_sessions(g.user["user_id"])
    return jsonify({"sessions": sessions}), 200


@detection_bp.route("/start-session", methods=["POST"])
@require_auth
def start_session():
    data        = request.get_json() or {}
    source_type = data.get("source_type") or data.get("session_type", "live")
    if source_type not in ("live", "upload"):
        return jsonify({"error": "source_type must be 'live' or 'upload'"}), 400

    rec_id = create_recognition_session(
        g.user["user_id"], source_type,
        source_filename=data.get("source_filename")
    )
    log_event("detection_session_started", user_id=g.user["user_id"], details={"session_id": rec_id, "source_type": source_type})
    return jsonify({"rec_session_id": rec_id, "session_id": rec_id}), 201



@detection_bp.route("/end-session/<int:rec_session_id>", methods=["POST"])
@require_auth
def end_session(rec_session_id: int):
    session = get_session_by_id(rec_session_id)
    if not session or session["user_id"] != g.user["user_id"]:
        return jsonify({"error": "Session not found"}), 404
    data    = request.get_json() or {}
    avg_fps = data.get("avg_fps")
    end_recognition_session(rec_session_id, avg_fps=avg_fps)
    log_event("detection_session_ended", user_id=g.user["user_id"], details={"session_id": rec_session_id, "avg_fps": avg_fps})
    return jsonify({"message": "Session ended"}), 200


@detection_bp.route("/results/<int:rec_session_id>", methods=["GET"])
@require_auth
def get_results(rec_session_id: int):
    session = get_session_by_id(rec_session_id)
    if not session or session["user_id"] != g.user["user_id"]:
        return jsonify({"error": "Session not found"}), 404
    detections = get_session_detections(rec_session_id)
    return jsonify({"session": session, "detections": detections}), 200


# ── Live frame processing ─────────────────────────────────────────────────────────

@detection_bp.route("/frame", methods=["POST"])
@require_auth
def process_live_frame():
    """Accept a base64 JPEG frame, run the pipeline, optionally persist detections."""
    data           = request.get_json() or {}
    frame_b64      = data.get("frame")
    rec_session_id = data.get("rec_session_id") or data.get("session_id")


    if not frame_b64:
        return jsonify({"error": "frame (base64) required"}), 400

    result = process_frame(frame_b64)

    if "error" in result:
        return jsonify(result), 400

    # Persist detections if a session ID was provided
    if rec_session_id:
        session = get_session_by_id(rec_session_id)
        if session and session["user_id"] == g.user["user_id"]:
            for d in result.get("detections", []):
                bx, by, bw, bh = d["bbox"]
                save_detection(rec_session_id, d["class_id"],
                               d["confidence"], bx, by, bw, bh)

    return jsonify(result), 200


# ── Video upload processing ───────────────────────────────────────────────────────

@detection_bp.route("/upload", methods=["POST"])
@require_auth
def upload_video():
    """Upload a video file; run pipeline on sampled frames; return summary."""
    if "video" not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files["video"]
    if not file.filename or not allowed_file(file.filename):
        return jsonify({"error":
            f"Unsupported file type. Allowed: {', '.join(ALLOWED)}"}), 415

    # Save file
    upload_dir = Path(Config.UPLOAD_FOLDER)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{g.user['user_id']}_{file.filename}"
    filepath  = upload_dir / safe_name
    file.save(str(filepath))

    # Create recognition session
    rec_id = create_recognition_session(
        g.user["user_id"], "upload", source_filename=file.filename
    )
    log_event("detection_session_started", user_id=g.user["user_id"], details={"session_id": rec_id, "source_type": "upload"})

    # Process video — sample 1 frame per second
    cap = cv2.VideoCapture(str(filepath))
    all_detections = []
    fps_sum, frame_count = 0.0, 0

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 25
    interval  = max(1, int(video_fps))
    idx       = 0
    success   = True

    while success:
        success, frame = cap.read()
        if not success:
            break
        if idx % interval != 0:
            idx += 1
            continue

        import base64
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64    = base64.b64encode(buf).decode()
        result = process_frame(b64)

        fps_sum    += result.get("fps", 0)
        frame_count += 1

        for d in result.get("detections", []):
            bx, by, bw, bh = d["bbox"]
            save_detection(rec_id, d["class_id"],
                           d["confidence"], bx, by, bw, bh)
            all_detections.append(d)
        idx += 1

    cap.release()

    avg_fps = round(fps_sum / frame_count, 1) if frame_count else 0
    end_recognition_session(rec_id, avg_fps=avg_fps)
    log_event("detection_session_ended", user_id=g.user["user_id"], details={"session_id": rec_id, "avg_fps": avg_fps, "frames_processed": frame_count})

    return jsonify({
        "rec_session_id": rec_id,
        "frames_processed": frame_count,
        "avg_fps": avg_fps,
        "detections_found": len(all_detections),
        "detections": all_detections[:50]   # first 50 for preview
    }), 200


# Make cv2 available inside the function (already imported at top of file in real usage)
try:
    import cv2
except ImportError:
    pass
