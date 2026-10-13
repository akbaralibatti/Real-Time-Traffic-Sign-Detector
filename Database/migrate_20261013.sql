-- Run after taking a full database backup. Adds account status used by ban/unban.
ALTER TABLE activity_logs MODIFY event_type ENUM(
 'register','login_success','login_failure','otp_success','otp_failure','logout',
 'password_change','account_locked','account_unlocked','admin_action',
 'detection_session_started','detection_session_ended','password_reset_failure','profile_update'
) NOT NULL;
ALTER TABLE users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1;
-- The sign dictionary must contain exactly the 11 classes from seed.sql.
-- Back up first; preserve users, sessions, recognition_sessions and activity_logs.
-- For existing MySQL detection_results, archive the DB backup before removing obsolete class rows.
SET FOREIGN_KEY_CHECKS=0;
START TRANSACTION;
-- Map by the legacy dictionary's sign name, not assumed numeric IDs.
CREATE TEMPORARY TABLE traffic_sign_class_map AS
SELECT class_id AS old_id,
 CASE LOWER(sign_name)
  WHEN 'cross road' THEN 0 WHEN 'cross_road' THEN 0
  WHEN 'gap in median' THEN 1 WHEN 'gap_in_median' THEN 1
  WHEN 'hump' THEN 2
  WHEN 'lefthand curve' THEN 3 WHEN 'left hand curve' THEN 3 WHEN 'left_hand_curve' THEN 3
  WHEN 'men at work' THEN 4 WHEN 'men_at_work' THEN 4
  WHEN 'narrow bridge' THEN 5 WHEN 'narrow_bridge' THEN 5
  WHEN 'pedestrain' THEN 6 WHEN 'pedestrian' THEN 6
  WHEN 'righthandcurve' THEN 7 WHEN 'right hand curve' THEN 7 WHEN 'right_hand_curve' THEN 7
  WHEN 'school ahead' THEN 8 WHEN 'school_ahead' THEN 8
  WHEN 'sideroadleft' THEN 9 WHEN 'side road left' THEN 9 WHEN 'side_road_left' THEN 9
  WHEN 'sideroadright' THEN 10 WHEN 'side road right' THEN 10 WHEN 'side_road_right' THEN 10
  ELSE NULL END AS new_id
FROM sign_meaning_dictionary;
DELETE FROM detection_results WHERE class_id NOT IN (SELECT old_id FROM traffic_sign_class_map WHERE new_id IS NOT NULL);
UPDATE detection_results dr JOIN traffic_sign_class_map m ON dr.class_id=m.old_id SET dr.class_id=m.new_id;
DROP TEMPORARY TABLE traffic_sign_class_map;
DELETE FROM sign_meaning_dictionary;
INSERT INTO sign_meaning_dictionary (class_id, sign_name, sign_description, category) VALUES
(0,'cross_road','Cross-road intersection ahead; watch for cross traffic.','cautionary'),
(1,'gap_in_median','Opening in the road median ahead.','cautionary'),
(2,'hump','Road hump or speed breaker ahead; reduce speed.','cautionary'),
(3,'left_hand_curve','Left-hand curve ahead; reduce speed.','cautionary'),
(4,'men_at_work','Road works ahead; proceed with caution.','cautionary'),
(5,'narrow_bridge','Narrow bridge ahead; watch for oncoming traffic.','cautionary'),
(6,'pedestrian','Pedestrian crossing ahead; give way to pedestrians.','cautionary'),
(7,'right_hand_curve','Right-hand curve ahead; reduce speed.','cautionary'),
(8,'school_ahead','School zone ahead; watch for children.','cautionary'),
(9,'side_road_left','Side road joining from the left.','cautionary'),
(10,'side_road_right','Side road joining from the right.','cautionary');
COMMIT;
SET FOREIGN_KEY_CHECKS=1;
