from db.connection import execute_query


# ── Recognition sessions ────────────────────────────────────────────────────────

def create_recognition_session(user_id: int, source_type: str, source_filename: str = None) -> int:
    return execute_query(
        """INSERT INTO recognition_sessions (user_id, source_type, source_filename)
           VALUES (%s, %s, %s)""",
        (user_id, source_type, source_filename), commit=True
    )


def end_recognition_session(rec_session_id: int, avg_fps: float = None):
    execute_query(
        "UPDATE recognition_sessions SET end_time = NOW(), avg_fps = %s WHERE rec_session_id = %s",
        (avg_fps, rec_session_id), commit=True
    )


def get_user_sessions(user_id: int, limit: int = 50) -> list:
    return execute_query(
        """SELECT rs.*, COUNT(dr.detection_id) AS detection_count
           FROM recognition_sessions rs
           LEFT JOIN detection_results dr ON rs.rec_session_id = dr.rec_session_id
           WHERE rs.user_id = %s
           GROUP BY rs.rec_session_id
           ORDER BY rs.start_time DESC LIMIT %s""",
        (user_id, limit), fetch="all"
    )


def get_session_by_id(rec_session_id: int) -> dict | None:
    return execute_query(
        "SELECT * FROM recognition_sessions WHERE rec_session_id = %s",
        (rec_session_id,), fetch="one"
    )


def count_sessions_today() -> int:
    row = execute_query(
        "SELECT COUNT(*) AS cnt FROM recognition_sessions WHERE DATE(start_time) = CURDATE()",
        fetch="one"
    )
    return row["cnt"] if row else 0


# ── Detection results ───────────────────────────────────────────────────────────

def save_detection(rec_session_id: int, class_id: int, confidence_score: float,
                   bbox_x: float, bbox_y: float, bbox_w: float, bbox_h: float) -> int:
    return execute_query(
        """INSERT INTO detection_results
               (rec_session_id, class_id, confidence_score, bbox_x, bbox_y, bbox_w, bbox_h)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (rec_session_id, class_id, confidence_score, bbox_x, bbox_y, bbox_w, bbox_h),
        commit=True
    )


def get_session_detections(rec_session_id: int) -> list:
    return execute_query(
        """SELECT dr.*, smd.sign_name, smd.sign_description, smd.category
           FROM detection_results dr
           JOIN sign_meaning_dictionary smd ON dr.class_id = smd.class_id
           WHERE dr.rec_session_id = %s
           ORDER BY dr.frame_timestamp ASC""",
        (rec_session_id,), fetch="all"
    )


def get_top_detected_signs(limit: int = 5) -> list:
    return execute_query(
        """SELECT smd.sign_name, COUNT(*) AS count
           FROM detection_results dr
           JOIN sign_meaning_dictionary smd ON dr.class_id = smd.class_id
           GROUP BY dr.class_id
           ORDER BY count DESC LIMIT %s""",
        (limit,), fetch="all"
    )


def count_total_detections() -> int:
    row = execute_query("SELECT COUNT(*) AS cnt FROM detection_results", fetch="one")
    return row["cnt"] if row else 0
