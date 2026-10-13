"""Safely migrate the SQLite sign dictionary to the 11 supported classes.

Run from Backend: python migrate_sign_classes.py
The database is copied to a timestamped backup before any destructive operation.
Only obsolete detection rows and obsolete dictionary classes are removed; users,
sessions, recognition sessions, and audit logs are retained.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).resolve().parent / "traffic_sign.db"
BACKUP = DB.with_name(f"traffic_sign.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db")
# Old best.pt class ID -> canonical ID in the new 11-class dictionary.
OLD_TO_NEW = {2: 0, 3: 1, 4: 2, 5: 3, 7: 4, 8: 5, 9: 6, 10: 7, 11: 8, 12: 9, 13: 10}
SIGNS = [
 (0,'cross_road','Cross-road intersection ahead; watch for cross traffic.'),
 (1,'gap_in_median','Opening in the road median ahead.'),
 (2,'hump','Road hump or speed breaker ahead; reduce speed.'),
 (3,'left_hand_curve','Left-hand curve ahead; reduce speed.'),
 (4,'men_at_work','Road works ahead; proceed with caution.'),
 (5,'narrow_bridge','Narrow bridge ahead; watch for oncoming traffic.'),
 (6,'pedestrian','Pedestrian crossing ahead; give way to pedestrians.'),
 (7,'right_hand_curve','Right-hand curve ahead; reduce speed.'),
 (8,'school_ahead','School zone ahead; watch for children.'),
 (9,'side_road_left','Side road joining from the left.'),
 (10,'side_road_right','Side road joining from the right.'),
]

def main():
    if not DB.exists():
        print('No existing database found; the application will create a clean database on first run.')
        return
    shutil.copy2(DB, BACKUP)
    conn = sqlite3.connect(DB)
    try:
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('BEGIN IMMEDIATE')
        cols = {row[1] for row in conn.execute('PRAGMA table_info(detection_results)')}
        class_col = 'class_id' if 'class_id' in cols else ('sign_class_id' if 'sign_class_id' in cols else None)
        if class_col:
            rows = conn.execute(f'SELECT detection_id, {class_col} FROM detection_results').fetchall()
            for detection_id, old_id in rows:
                if old_id in OLD_TO_NEW:
                    conn.execute(f'UPDATE detection_results SET {class_col}=? WHERE detection_id=?', (OLD_TO_NEW[old_id], detection_id))
                else:
                    conn.execute('DELETE FROM detection_results WHERE detection_id=?', (detection_id,))
        conn.execute('DELETE FROM sign_meaning_dictionary')
        # Adapt to the project's SQLite column names.
        dictionary_cols = {row[1] for row in conn.execute('PRAGMA table_info(sign_meaning_dictionary)')}
        for class_id, name, meaning in SIGNS:
            if 'sign_meaning' in dictionary_cols:
                conn.execute('INSERT INTO sign_meaning_dictionary (class_id, sign_name, category, sign_meaning, description) VALUES (?,?,?,?,?)', (class_id,name,'cautionary',meaning,meaning))
            else:
                conn.execute('INSERT INTO sign_meaning_dictionary (class_id, sign_name, sign_description, category) VALUES (?,?,?,?)', (class_id,name,meaning,'cautionary'))
        conn.commit()
        count = conn.execute('SELECT COUNT(*) FROM sign_meaning_dictionary').fetchone()[0]
        assert count == 11, f'Expected 11 classes, got {count}'
        print(f'Migration complete: {count} classes. Backup: {BACKUP}')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    main()
