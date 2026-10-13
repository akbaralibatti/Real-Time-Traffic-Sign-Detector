# TrafficVision — modified code package

## Setup (Windows PowerShell)
1. `cd codes/Backend`
2. `py -m venv .venv; .\.venv\Scripts\Activate.ps1`
3. `python -m pip install --upgrade pip`
4. `pip install -r requirements.txt`
5. Copy `.env.example` to `.env`; set a unique `SECRET_KEY`, a generated `TOTP_ENCRYPTION_KEY`, `ADMIN_USERNAME`, `ADMIN_EMAIL`, and strong `ADMIN_PASSWORD`. Generate keys with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Never commit `.env`.
6. Run `python app.py` (backend: `http://127.0.0.1:5000`). The admin is provisioned only when all ADMIN_* values are supplied; TOTP setup is mandatory before access.
7. In a second terminal, `cd codes/Frontend` and run `py -m http.server 5500`; open `http://127.0.0.1:5500`.

## Model and 11-class compatibility
The included `Backend/ml/weights/best.pt` is checked on load against the 11 required class names (including common spelling aliases). Incompatible weights fail closed instead of silently mapping incorrect classes. Use `YOLO_WEIGHTS`, `YOLO_IMGSZ`, `YOLO_DEVICE` and `CONF_THRESHOLD` in `.env` to configure inference. Camera processing uses downscaled JPEGs and a single-flight loop; the UI displays measured backend FPS and per-frame latency.

## Existing database migration
The bundled ZIP deliberately omits the old live database. For an existing SQLite install, stop the backend and run `python migrate_sign_classes.py` from `codes/Backend`; it makes a timestamped database backup before updating class records. For an **existing legacy MySQL database**, take a full backup, then review/run `codes/Database/migrate_20261013.sql`. For a **fresh MySQL install**, run `schema.sql` followed by `seed.sql` and do not run the migration script. User accounts, sessions and audit logs are preserved; obsolete-class detections are removed because their labels no longer exist.

## Logos
Add optional PNG files under `codes/Frontend/images/traffic-signs/` with the exact filenames listed in that folder's README. Password-strength validation has not been changed. Password reset requires the enrolled TOTP code and revokes all existing sessions.
