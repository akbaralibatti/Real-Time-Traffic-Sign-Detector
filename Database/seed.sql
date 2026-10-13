-- ============================================================================
-- seed.sql  — Seed data for Real-Time Traffic Sign Recognition System
-- Run AFTER schema.sql
-- ============================================================================

USE traffic_sign_db;

-- ============================================================================
-- Sign Meaning Dictionary — Indian Traffic Signs
-- Categories: mandatory | cautionary | informatory
-- ============================================================================

INSERT INTO sign_meaning_dictionary (class_id, sign_name, sign_description, category) VALUES
(0, 'cross_road', 'Cross-road intersection ahead; watch for cross traffic.', 'cautionary'),
(1, 'gap_in_median', 'Opening in the road median ahead.', 'cautionary'),
(2, 'hump', 'Road hump or speed breaker ahead; reduce speed.', 'cautionary'),
(3, 'left_hand_curve', 'Left-hand curve ahead; reduce speed.', 'cautionary'),
(4, 'men_at_work', 'Road works ahead; proceed with caution.', 'cautionary'),
(5, 'narrow_bridge', 'Narrow bridge ahead; watch for oncoming traffic.', 'cautionary'),
(6, 'pedestrian', 'Pedestrian crossing ahead; give way to pedestrians.', 'cautionary'),
(7, 'right_hand_curve', 'Right-hand curve ahead; reduce speed.', 'cautionary'),
(8, 'school_ahead', 'School zone ahead; watch for children.', 'cautionary'),
(9, 'side_road_left', 'Side road joining from the left.', 'cautionary'),
(10, 'side_road_right', 'Side road joining from the right.', 'cautionary');

-- ============================================================================
-- Default admin user placeholder
-- NOTE: Replace <bcrypt-hash-here> with a real bcrypt hash generated at
--       application startup (never store plaintext passwords).
-- ============================================================================
-- INSERT INTO users (username, email, password_hash, role, email_verified)
-- VALUES ('admin', 'admin@nitk.edu.in', '<bcrypt-hash-here>', 'admin', 1);
