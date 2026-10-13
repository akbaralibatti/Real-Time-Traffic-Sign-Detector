import json
from db.connection import execute_query


def log_event(event_type: str, user_id: int = None, admin_id: int = None, details: dict = None):
    """
    Insert an activity log record.
    At least one of user_id or admin_id must be provided (DB constraint).
    """
    execute_query(
        """INSERT INTO activity_logs (user_id, admin_id, event_type, details)
           VALUES (%s, %s, %s, %s)""",
        (user_id, admin_id, event_type, json.dumps(details) if details else None),
        commit=True
    )


def get_logs(limit: int = 100, offset: int = 0,
             event_type: str = None, user_id: int = None,
             date_from: str = None, date_to: str = None) -> list:
    conditions = []
    params = []
    if event_type:
        conditions.append("al.event_type = %s"); params.append(event_type)
    if user_id:
        conditions.append("al.user_id = %s"); params.append(user_id)
    if date_from:
        conditions.append("al.event_timestamp >= %s"); params.append(date_from)
    if date_to:
        conditions.append("al.event_timestamp <= %s"); params.append(date_to)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params += [limit, offset]

    return execute_query(
        f"""SELECT al.log_id, al.event_type, al.event_timestamp, al.details,
                   u.username AS user_name, a.username AS admin_name
            FROM activity_logs al
            LEFT JOIN users u ON al.user_id  = u.user_id
            LEFT JOIN users a ON al.admin_id = a.user_id
            {where}
            ORDER BY al.event_timestamp DESC
            LIMIT %s OFFSET %s""",
        params, fetch="all"
    )


def count_logs(**kwargs) -> int:
    conditions, params = [], []
    if kwargs.get("event_type"):
        conditions.append("event_type = %s"); params.append(kwargs["event_type"])
    if kwargs.get("user_id"):
        conditions.append("user_id = %s"); params.append(kwargs["user_id"])
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    row = execute_query(f"SELECT COUNT(*) AS cnt FROM activity_logs {where}", params, fetch="one")
    return row["cnt"] if row else 0


def get_recent_auth_events(limit: int = 20) -> list:
    return execute_query(
        """SELECT al.event_type, al.event_timestamp, u.username
           FROM activity_logs al
           LEFT JOIN users u ON al.user_id = u.user_id
           WHERE al.event_type IN ('login_success','login_failure','register','logout')
           ORDER BY al.event_timestamp DESC LIMIT %s""",
        (limit,), fetch="all"
    )
