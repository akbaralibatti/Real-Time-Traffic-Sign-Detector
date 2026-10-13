from db.connection import execute_query


def get_all_signs(limit: int = 200, offset: int = 0) -> list:
    return execute_query(
        "SELECT * FROM sign_meaning_dictionary ORDER BY class_id LIMIT %s OFFSET %s",
        (limit, offset), fetch="all"
    )


def get_sign_by_id(class_id: int) -> dict | None:
    return execute_query(
        "SELECT * FROM sign_meaning_dictionary WHERE class_id = %s",
        (class_id,), fetch="one"
    )


def search_signs(query: str, limit: int = 50) -> list:
    like = f"%{query}%"
    return execute_query(
        """SELECT * FROM sign_meaning_dictionary
           WHERE sign_name LIKE %s OR sign_description LIKE %s OR category LIKE %s
           ORDER BY sign_name LIMIT %s""",
        (like, like, like, limit), fetch="all"
    )


def get_signs_by_category(category: str) -> list:
    return execute_query(
        "SELECT * FROM sign_meaning_dictionary WHERE category = %s ORDER BY sign_name",
        (category,), fetch="all"
    )


def count_signs() -> int:
    row = execute_query("SELECT COUNT(*) AS cnt FROM sign_meaning_dictionary", fetch="one")
    return row["cnt"] if row else 0
