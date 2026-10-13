"""
ml/pipeline.py — Traffic sign recognition pipeline.

Single-stage YOLO inference using best.pt.
The model detects AND classifies traffic signs in one forward pass —
no separate CNN stage required.

Falls back to a realistic stub when the weight file is not found, so
the UI and API work even during development.
"""
import base64
import logging
import random
import time
from pathlib import Path

import cv2
import numpy as np

from config import Config

logger = logging.getLogger(__name__)

# ── Module-level state (loaded once at startup) ──────────────────────────────
_yolo_model = None
_sign_labels: list[dict] = []   # rows from sign_meaning_dictionary table
_yolo_class_names: dict[int, str] = {}  # Model-native class names; mapped to the supported 11-class vocabulary.

WEIGHTS_READY = False


# ── Class name → DB sign mapping ─────────────────────────────────────────────
# Maps YOLO class names (from best.pt) to sign_meaning_dictionary categories
# and meanings so detections show rich descriptions in the UI.
_CLASS_DEFINITIONS = [
    ("cross_road", {"aliases": {"cross road", "cross_road"}, "meaning": "Cross-road intersection ahead; watch for cross traffic."}),
    ("gap_in_median", {"aliases": {"gap in median", "gap_in_median"}, "meaning": "Opening in the road median ahead."}),
    ("hump", {"aliases": {"hump"}, "meaning": "Road hump or speed breaker ahead; reduce speed."}),
    ("left_hand_curve", {"aliases": {"lefthand curve", "left hand curve", "left_hand_curve"}, "meaning": "Left-hand curve ahead; reduce speed."}),
    ("men_at_work", {"aliases": {"men at work", "men_at_work"}, "meaning": "Road works ahead; proceed with caution."}),
    ("narrow_bridge", {"aliases": {"narrow bridge", "narrow_bridge"}, "meaning": "Narrow bridge ahead; watch for oncoming traffic."}),
    ("pedestrian", {"aliases": {"pedestrain", "pedestrian", "pedestrians"}, "meaning": "Pedestrian crossing ahead; give way to pedestrians."}),
    ("right_hand_curve", {"aliases": {"righthandcurve", "right hand curve", "right_hand_curve"}, "meaning": "Right-hand curve ahead; reduce speed."}),
    ("school_ahead", {"aliases": {"school ahead", "school_ahead"}, "meaning": "School zone ahead; watch for children."}),
    ("side_road_left", {"aliases": {"sideroadleft", "side road left", "side_road_left"}, "meaning": "Side road joining from the left."}),
    ("side_road_right", {"aliases": {"sideroadright", "side road right", "side_road_right"}, "meaning": "Side road joining from the right."}),
]
_CLASS_META = {name: {**meta, "category": "cautionary"} for name, meta in _CLASS_DEFINITIONS}
_NAME_TO_CANONICAL = {alias: name for name, meta in _CLASS_DEFINITIONS for alias in meta["aliases"]}



def load_models():
    """Called once at application startup. Loads YOLO model if weight file exists."""
    global _yolo_model, _sign_labels, _yolo_class_names, WEIGHTS_READY

    # Load sign dictionary from DB for rich descriptions
    try:
        from db.signs import get_all_signs
        _sign_labels = get_all_signs(limit=500)
        logger.info(f"Loaded {len(_sign_labels)} sign labels from DB")
    except Exception as e:
        logger.warning(f"Could not load sign labels from DB: {e}")
        _sign_labels = []

    yolo_path = Path(Config.YOLO_WEIGHTS)

    if yolo_path.exists():
        try:
            from ultralytics import YOLO
            _yolo_model = YOLO(str(yolo_path))
            _yolo_class_names = _yolo_model.names  # {int: str}
            available = {_NAME_TO_CANONICAL.get(str(n).strip().lower()) for n in _yolo_class_names.values()}
            available.discard(None)
            missing = set(_CLASS_META) - available
            if missing:
                raise ValueError(f"Model is incompatible with the required 11 classes; missing: {sorted(missing)}")
            WEIGHTS_READY = True
            logger.info(
                f"YOLO model loaded from {yolo_path} — "
                f"{len(_yolo_class_names)} classes: {list(_yolo_class_names.values())}"
            )
            logger.info("ML pipeline ready — REAL inference mode ✓")
        except Exception as e:
            logger.error(f"YOLO model load failed: {e}")
            WEIGHTS_READY = False
    else:
        logger.warning(
            f"Weight file not found at '{yolo_path}'. Running in STUB mode. "
            "Place best.pt in Backend/ml/weights/ to enable real inference."
        )
        WEIGHTS_READY = False


def process_frame(frame_b64: str) -> dict:
    """
    Process a single base64-encoded JPEG/PNG frame through the YOLO model.

    Returns:
        {
          "detections": [
              {
                "class_id":    int,
                "sign_name":   str,
                "sign_meaning": str,
                "category":    str,
                "confidence":  float,       # 0.0 – 1.0
                "bbox":        [x, y, w, h] # normalised 0–1
              }, ...
          ],
          "fps":             float,
          "annotated_frame": str,   # base64 JPEG with bounding boxes
          "mode":            "real" | "stub"
        }
    """
    t_start = time.perf_counter()

    # ── Decode incoming frame ────────────────────────────────────────────────
    try:
        img_bytes = base64.b64decode(frame_b64)
        arr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("cv2.imdecode returned None — not a valid image")
    except Exception as e:
        return {"error": f"Frame decode failed: {e}", "detections": [], "fps": 0, "mode": "error"}

    # ── Run inference ────────────────────────────────────────────────────────
    if WEIGHTS_READY:
        detections = _yolo_inference(frame)
        mode = "real"
    else:
        detections = _stub_inference(frame)
        mode = "stub"

    # ── Draw overlays and encode back to base64 ──────────────────────────────
    annotated = _draw_overlays(frame.copy(), detections)
    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
    annotated_b64 = base64.b64encode(buf).decode()

    elapsed = time.perf_counter() - t_start
    fps = round(1.0 / elapsed, 1) if elapsed > 0 else 0.0

    return {
        "detections":      detections,
        "fps":             fps,
        "latency_ms":      round(elapsed * 1000, 1),
        "annotated_frame": annotated_b64,
        "mode":            mode,
    }


# ── Real YOLO inference ───────────────────────────────────────────────────────

def _yolo_inference(frame: np.ndarray) -> list[dict]:
    """Run best.pt YOLO detection. YOLO outputs class_id + confidence directly."""
    h, w = frame.shape[:2]
    results = _yolo_model.predict(frame, verbose=False, conf=Config.CONF_THRESHOLD, imgsz=Config.YOLO_IMGSZ, device=(Config.YOLO_DEVICE or None), stream=False)
    detections = []

    for box in results[0].boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        confidence = round(float(box.conf[0]), 3)
        class_id   = int(box.cls[0])
        model_name = str(_yolo_class_names.get(class_id, f"Class {class_id}")).strip().lower()
        canonical = _NAME_TO_CANONICAL.get(model_name)
        if canonical is None:
            continue  # Exclude all classes outside the required 11-class vocabulary.
        canonical_id = next(i for i, (name, _) in enumerate(_CLASS_DEFINITIONS) if name == canonical)
        meta = _CLASS_META[canonical]
        category = meta["category"]
        meaning = meta["meaning"]

        detections.append({
            "class_id":    canonical_id,
            "sign_name":   canonical,
            "sign_meaning": meaning,
            "sign_description": meaning,
            "logo_url": f"/images/traffic-signs/{canonical}.png",
            "category":    category,
            "confidence":  confidence,
            "bbox": [
                round(x1 / w, 4),
                round(y1 / h, 4),
                round((x2 - x1) / w, 4),
                round((y2 - y1) / h, 4),
            ],
        })

    return detections


# ── Stub inference (no model) ─────────────────────────────────────────────────

def _stub_inference(frame: np.ndarray) -> list[dict]:
    """Return 0–2 plausible random detections from known YOLO classes for UI dev."""
    class_pool = [(name, meta) for name, meta in _CLASS_META.items()]
    if not class_pool:
        return []

    n = random.choices([0, 1, 2], weights=[0.3, 0.5, 0.2])[0]
    detections = []
    for i in range(n):
        name, meta = random.choice(class_pool)
        canonical_id = next(idx for idx, (class_name, _) in enumerate(_CLASS_DEFINITIONS) if class_name == name)
        detections.append({
            "class_id":    canonical_id,
            "sign_name":   name,
            "sign_meaning": meta.get("meaning", name),
            "sign_description": meta.get("meaning", name),
            "logo_url": f"/images/traffic-signs/{name}.png",
            "category":    meta.get("category", "cautionary"),
            "confidence":  round(random.uniform(0.50, 0.97), 3),
            "bbox": [
                round(random.uniform(0.05, 0.50), 3),
                round(random.uniform(0.05, 0.50), 3),
                round(random.uniform(0.15, 0.30), 3),
                round(random.uniform(0.15, 0.30), 3),
            ],
        })
    return detections


# ── Bounding box drawing ──────────────────────────────────────────────────────

def _draw_overlays(frame: np.ndarray, detections: list[dict]) -> np.ndarray:
    h, w = frame.shape[:2]
    for d in detections:
        bx, by, bw, bh = d["bbox"]
        x1 = int(bx * w);       y1 = int(by * h)
        x2 = int((bx + bw) * w); y2 = int((by + bh) * h)

        # Colour by category
        cat = d.get("category", "cautionary")
        if cat == "mandatory":
            color = (80, 80, 230)    # red-ish
        elif cat == "informatory":
            color = (230, 180, 30)   # blue
        else:
            color = (30, 220, 180)   # cyan (cautionary default)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = f"{d['sign_name']}  {d['confidence'] * 100:.0f}%"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), color, -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 1, cv2.LINE_AA)
    return frame
