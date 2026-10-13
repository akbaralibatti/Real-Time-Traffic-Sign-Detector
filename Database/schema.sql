-- ============================================================================
-- Real-Time Traffic Sign Recognition System — Database Schema
-- Dialect: MySQL 8.0+
-- ============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================================
-- 1. USERS
-- Core identity + credential table (D1 in the SRS data dictionary).
-- ============================================================================
CREATE TABLE users (
    user_id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username                VARCHAR(50)  NOT NULL UNIQUE,
    email                   VARCHAR(255) NOT NULL UNIQUE,
    password_hash           VARCHAR(255) NOT NULL,          -- bcrypt hash, never plaintext
    role                    ENUM('user', 'admin') NOT NULL DEFAULT 'user',
    is_active               TINYINT(1) NOT NULL DEFAULT 1,

    -- 2FA (TOTP via external authenticator app)
    totp_secret             VARCHAR(255) NULL,              -- encrypted at rest by application layer
    is_2fa_enabled          TINYINT(1)   NOT NULL DEFAULT 0,

    -- Brute-force protection
    failed_login_attempts   SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    account_locked_until    DATETIME NULL,

    -- Bookkeeping
    email_verified          TINYINT(1)  NOT NULL DEFAULT 0,
    created_at              DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login_at           DATETIME NULL,

    CONSTRAINT chk_users_username_len CHECK (CHAR_LENGTH(username) >= 3),
    INDEX idx_users_email (email),
    INDEX idx_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- 2. BACKUP_CODES
-- One-time recovery codes issued when a user enables 2FA.
-- ============================================================================
CREATE TABLE backup_codes (
    code_id      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id      INT UNSIGNED NOT NULL,
    code_hash    VARCHAR(255) NOT NULL,      -- bcrypt/argon2 hash of the recovery code
    used         TINYINT(1)   NOT NULL DEFAULT 0,
    used_at      DATETIME NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_backup_codes_user
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    INDEX idx_backup_codes_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- 3. SESSIONS
-- Server-side session store (chosen over stateless JWT so sessions can be
-- revoked immediately — e.g. by an admin, or on password change).
-- ============================================================================
CREATE TABLE sessions (
    session_id    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id       INT UNSIGNED NOT NULL,
    token_hash    VARCHAR(255) NOT NULL UNIQUE,   -- hash of the session token, never the raw token
    issued_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at    DATETIME     NOT NULL,
    ip_address    VARCHAR(45)  NULL,               -- supports IPv4 and IPv6
    user_agent    VARCHAR(255) NULL,
    revoked       TINYINT(1)   NOT NULL DEFAULT 0,

    CONSTRAINT fk_sessions_user
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    INDEX idx_sessions_user_id (user_id),
    INDEX idx_sessions_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- 4. ACTIVITY_LOGS
-- Audit trail for authentication and admin events (D3 in the SRS).
-- user_id and admin_id both reference users; either may be NULL depending
-- on whether the event was user-initiated, admin-initiated, or system-level.
-- ============================================================================
CREATE TABLE activity_logs (
    log_id      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     INT UNSIGNED NULL,
    admin_id    INT UNSIGNED NULL,
    event_type  ENUM(
                    'register', 'login_success', 'login_failure',
                    'otp_success', 'otp_failure', 'logout',
                    'password_change', 'account_locked',
                    'account_unlocked', 'admin_action', 'detection_session_started',
                    'detection_session_ended', 'password_reset_failure', 'profile_update'
                ) NOT NULL,
    event_timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details     JSON NULL,          -- flexible field for event-specific metadata

    CONSTRAINT fk_activity_logs_user
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT fk_activity_logs_admin
        FOREIGN KEY (admin_id) REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT chk_activity_logs_actor CHECK (user_id IS NOT NULL OR admin_id IS NOT NULL),
    INDEX idx_activity_logs_user_id (user_id),
    INDEX idx_activity_logs_admin_id (admin_id),
    INDEX idx_activity_logs_ts (event_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- 5. SIGN_MEANING_DICTIONARY
-- Static reference table mapping a class id to its human-readable name and
-- meaning (D6 in the SRS). Seeded once from the classification dataset's
-- class list; not user-editable at runtime.
-- ============================================================================
CREATE TABLE sign_meaning_dictionary (
    class_id          INT UNSIGNED PRIMARY KEY,
    sign_name         VARCHAR(100) NOT NULL,
    sign_description  TEXT         NOT NULL,
    category          VARCHAR(50)  NULL,          -- e.g. 'mandatory', 'cautionary', 'informatory'

    INDEX idx_sign_meaning_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- 6. RECOGNITION_SESSIONS
-- One row per live-camera run or uploaded-video run (F.11 "session logs").
-- ============================================================================
CREATE TABLE recognition_sessions (
    rec_session_id    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id           INT UNSIGNED NOT NULL,
    source_type       ENUM('live', 'upload') NOT NULL,
    source_filename   VARCHAR(255) NULL,        -- NULL for live camera sessions
    start_time        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time          DATETIME NULL,
    avg_fps           FLOAT NULL,

    CONSTRAINT fk_rec_sessions_user
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
    CONSTRAINT chk_rec_sessions_times CHECK (end_time IS NULL OR end_time >= start_time),
    INDEX idx_rec_sessions_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================================
-- 7. DETECTION_RESULTS
-- Per-frame detection + classification history within a recognition session.
-- This is the "sign detection history" a user/admin can review later.
-- ============================================================================
CREATE TABLE detection_results (
    detection_id      BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rec_session_id    INT UNSIGNED NOT NULL,
    frame_timestamp   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    class_id          INT UNSIGNED NOT NULL,
    confidence_score  FLOAT NOT NULL,
    bbox_x            FLOAT NOT NULL,
    bbox_y            FLOAT NOT NULL,
    bbox_w            FLOAT NOT NULL,
    bbox_h            FLOAT NOT NULL,

    CONSTRAINT fk_detection_results_session
        FOREIGN KEY (rec_session_id) REFERENCES recognition_sessions (rec_session_id) ON DELETE CASCADE,
    CONSTRAINT fk_detection_results_class
        FOREIGN KEY (class_id) REFERENCES sign_meaning_dictionary (class_id),
    CONSTRAINT chk_detection_confidence CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    INDEX idx_detection_results_session (rec_session_id),
    INDEX idx_detection_results_class_id (class_id),
    INDEX idx_detection_results_ts (frame_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================================
-- Seed data: default admin account placeholder
-- NOTE: password_hash below is a placeholder — generate a real bcrypt hash
-- in the application layer before inserting, never hardcode a real hash here.
-- ============================================================================
-- INSERT INTO users (username, email, password_hash, role, email_verified)
-- VALUES ('admin', 'admin@example.com', '<bcrypt-hash-here>', 'admin', 1);