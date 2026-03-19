# CronCraft™ Developer Documentation

This document outlines the architecture, features, and core workflows of the CronCraft application.

## Core Architecture

CronCraft is a Flask web application designed for cron job monitoring and alerting. It uses a MySQL database in production (via SQLAlchemy), with an automatic SQLite fallback when `DATABASE_URL` is not set (useful for local development and self-hosted setups). Schema changes are managed through Flask-Migrate/Alembic versioned migrations. A standalone background worker scheduler (APScheduler) handles missed-ping detection.

- **Web Application**: Handles the UI, API endpoints, user authentication, and job CRUD operations.
- **Worker Process**: Runs continuously in the background to evaluate job schedules and dispatch alerts for missed pings.
- **Database**: MySQL (production) or SQLite (fallback) storing Users, Teams, Jobs, JobRuns, and Alerts.

## Core Features & Workflows

### 1. Job Monitoring & Pinging
The core feature of CronCraft is monitoring whether external scheduled tasks run on time.

- **Ping Endpoints**:
  - `/ping/<token>`: The standard endpoint hit by an external script upon successful execution. It records a successful `JobRun`, sets the job's `last_status` to `'ok'`, resets the `miss_count` to 0, and calculates the next `expected_at` time based on the cron schedule.
  - `/ping/<token>/fail`: An explicit failure endpoint. If hit, it immediately records a failed `JobRun`, sets the job's `last_status` to `'failed'`, resets `miss_count` to 0, calculates the next `expected_at`, and dispatches a failure email alert.
  
  **Usage Example (Bash Script):**
  This pattern allows cron jobs to report success or explicit failure based on the exit code of their execution payload:
  ```bash
  #!/bin/bash
  
  # Run the actual backup or task script
  /usr/local/bin/my-backup-job.sh
  
  # Check the exit code of the script
  if [ $? -ne 0 ]; then
      # If the script failed (non-zero exit code), hit the fail endpoint
      curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN_HERE/fail > /dev/null
  else
      # If the script succeeded, hit the normal ping endpoint
      curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN_HERE > /dev/null
  fi
  ```
  **Usage Example (Direct edit in crontab):**
  This pattern allows cron jobs to report success or explicit failure based on the exit code of their execution payload using && and ||:
  ```bash
  0 */4 * * * /var/www/webservice/run_entra_sync.sh && curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN_HERE > /dev/null || curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN_HERE/fail > /dev/null
  ```
  **Usage Example (Windows Batch File):**
  This pattern works in Windows Task Scheduler batch scripts. `curl.exe` is built into Windows 10+ and the `> nul` redirect suppresses output:
  ```batch
  @echo off
  REM Run the actual task
  "C:\Program Files\Python314\python.exe" C:\scripts\my_task.py

  REM Report to CronCraft based on exit code
  if %errorlevel% neq 0 (
      curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN_HERE/fail > nul
  ) else (
      curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN_HERE > nul
  )
  ```
- **Background Worker**: `check_missed_pings()` runs every minute. It checks for active jobs where `expected_at < now`. 
  - If a job is past its `grace_cutoff` (expected time + grace period), it increments `miss_count`.
  - If `miss_count >= 3`, it auto-escalates the job to `'failed'` and sends an alert.
  - Otherwise, it marks the job as `'late'` and sends a missed alert.
  - The worker always advances `expected_at` to the next cron window after processing a miss to keep the schedule moving forward.
- **Dependency Chains** *(Pro+ only)*: Jobs can be configured to depend on a parent job.
  - If a parent job fails (either through auto-escalation or an explicit `/fail` ping), the failed status is recursively cascaded to all of its dependent child jobs immediately.
  - Child jobs that are forcibly failed will dispatch a `dependency_failed` alert to their designated channels.
  - **Plan enforcement**: Dependency cascading only runs if the parent job's owner has `allow_dependencies` enabled for their plan. Free-tier users' jobs do not cascade failures.
- **Status Mapping**:
  - `ok`: Job is pinging on schedule.
  - `late`: Job missed its expected window (up to 2 consecutive misses).
  - `failed`: Job either explicitly hit the `/fail` endpoint, or missed 3 consecutive windows.
  - `never_run`: Job was created but hasn't received its first ping yet (displays as "WAITING" in UI).
  - `is_active=False`: Job is manually paused by the user. Un-pausing recalculates `expected_at`.
  - **Unpause Guard**: When unpausing a personal (non-team) job, the system checks whether the user has already reached their plan's active job limit. If so, the unpause is blocked with a flash message. This prevents circumventing the free-tier limit after a downgrade.

### 2. User Authentication & Accounts
- **Registration**: Protected by reCAPTCHA v2 (invisible) and a honeypot field. Currently restricted via `.env` whitelist (`ALLOWED_REGISTRATION_EMAILS`). Requires email verification.
- **Password Reset**: Standard forgot-password token flow via email.
- **Profile Settings**: Users can manage their email, username, display name, timezone, password, and preferred date/time formatting.
- **Password Complexity**: All password entry points (registration, reset, settings) enforce the same rules via a shared `validate_password()` helper in `validators.py`: 8–50 characters, at least one uppercase, one lowercase, one digit, and one special character.
- **Subscriptions & Billing**: Users are assigned to plan tiers (`free`, `pro`, `team`). 
  - `free` tier is limited to 10 jobs, email-only alerts, and no dependency chains.
  - `pro` and `team` tiers unlock Webhook alerts, Slack alerts, and Dependency Chains.
  - Feature access is controlled via `plan_limits.py` flags (`allow_webhook`, `allow_slack`, `allow_dependencies`) and enforced both in the UI and server-side. Free-tier users see a 🔒 upgrade hint on create/edit forms for restricted features.
  - **Stripe Integration** (`stripe_routes.py`):
    - **Checkout**: `POST /subscription/checkout` creates a Stripe Checkout Session for upgrading to Pro or Team. Uses existing `stripe_customer_id` if the user has one, otherwise passes `customer_email`.
    - **Customer Portal**: `POST /subscription/portal` redirects the user to Stripe's billing portal for managing their subscription (update payment, cancel, etc.).
    - **Webhook**: `POST /subscription/webhook` receives Stripe events. Handles `checkout.session.completed` (stores customer/subscription IDs), `customer.subscription.updated` (maps Price IDs to plan tiers), and `customer.subscription.deleted` (downgrades to free). This is the only Stripe route exempt from CSRF protection; checkout and portal forms require CSRF tokens.
    - **Error Handling**: Stripe API errors are logged to the systemd journal and users see a generic error message (no internal details are exposed).
    - **Sync on Redirect**: After Stripe Checkout, the redirect back to `/subscription?session_id=...` synchronously retrieves the Checkout Session and updates the user's plan immediately, without waiting for the async webhook.
  - **Paid Plan Signup Flow**: Landing page "Start with Pro/Team" links pass plan intent via the registration URL. After email verification and first login, the `pending_plan` session variable auto-forwards the user to Stripe Checkout.
  - **Grace Period**: When a subscription enters `past_due` status (failed payment), the user keeps their current plan for **7 days** rather than being immediately downgraded. A `grace_period_end` timestamp is set on the user record. A daily worker task (`check_grace_period_expirations`, 03:15 UTC) handles expiration:
    - Downgrades the user to `free` and clears `stripe_subscription_id`.
    - **Pauses excess jobs** beyond the free-tier limit (10), keeping the 10 most recently created jobs active.
  - **Grace Period Notifications**:
    - On login, users with an active grace period see a red flash warning about their past-due payment.
    - The `/subscription` page displays a prominent amber "Payment Past Due" banner showing the exact downgrade date.
  - **Subscription Page** (`/subscription`): Shows current plan, plan start date, member-since date, and plan end date (next billing cycle, fetched from Stripe's `current_period_end`). Includes "Manage Subscription" and upgrade buttons.
  - **Admin-Managed Plans**: If an admin manually upgrades a user's plan in the admin panel (without Stripe), the plan has no billing cycle and will never expire automatically. The subscription page and admin detail show "Admin Managed" instead of a plan end date. Only an admin can change the plan back.

### 3. Admin Panel
Located at `/admin` and restricted to users with `is_admin=True`.
- **First User Auto-Admin**: The first account registered on a fresh database is automatically granted admin privileges. No manual SQL or CLI commands needed — ideal for self-hosted Docker deployments.
- **Dashboard**: System-wide statistics on users, jobs, and recent alerts.
- **User Management**: View, edit (plan, admin status, verification status, email), and delete users (cascade deletes all associated data).
- **User Detail View**: Shows profile, plan status (with Plan Started, Plan Ends dates from Stripe), grace period status (with amber "PAST DUE" badge if applicable), all jobs with statuses, and recent alerts.
- **Impersonation**: Admins can log in as any user to troubleshoot issues, with a "Return to Admin" banner to quickly switch back.

### 4. Alerting System
- **Delivery Channels**:
  - **Email**: Uses Flask-Mail via standard SMTP to send HTML and plaintext emails. Available on all tiers.
  - **Generic Webhooks** *(Pro+ only)*: Dispatches a JSON payload via an HTTP POST request to a custom, user-provided webhook URL.
  - **Slack** *(Pro+ only)*: Dispatches a formatted Slack JSON payload to a user-provided Slack Incoming Webhook URL.
  - **URL Validation (SSRF Protection)**: Webhook and Slack URLs are validated on job create/edit via `validate_webhook_url()` in `validators.py`. Private/loopback IPs, non-HTTP schemes, and localhost are rejected to prevent Server-Side Request Forgery.
- **Plan Enforcement**: Before dispatching webhook or Slack alerts, `alerting.py` checks the job owner's current plan via `is_feature_allowed()`. If the user has been downgraded to free, existing jobs with leftover webhook/Slack configurations will silently skip those channels while email alerts continue.
- **Delivery Logging**: Webhook and Slack delivery failures are logged to the systemd journal via `current_app.logger.warning()` for diagnostics.
- **Alert Types**:
  - `missed`: Sent when a job misses its window and enters the `'late'` state.
  - `failed`: Sent when a job hits the explicit fail endpoint or auto-escalates after 3 consecutive misses.
  - `recovered`: Sent when a late or failed job successfully pings the normal endpoint.
  - `dependency_failed`: Sent when a parent job's failure is cascaded to a dependent child job.
- **Alert History**: All sent alerts are logged in the `alerts` table for auditing and UI display.

### 5. Run History & Retention
- **Execution Tracking**: Every ping, fail, and missed window generates a `JobRun` record storing the status, timestamp, IP address, and (optionally) duration.
  - *Note on IP Addresses*: If the application is hosted locally or behind a consumer router, pings from devices on the same local network may be logged with the router's gateway IP (e.g., `192.168.2.1`) due to **Hairpin NAT** (NAT Loopback). This is expected networking behavior and does not indicate a proxy configuration issue; external public traffic will still log the correct real IP.
- **Data Cleanup**: A daily worker task (`purge_old_runs()`) at 03:00 UTC deletes `JobRun` records extending beyond the user's plan retention window (Free: 7 days, Pro: 90 days, Team: 365 days).
- **Grace Period Expirations**: A daily worker task (`check_grace_period_expirations()`) at 03:15 UTC downgrades users whose 7-day grace period has expired and pauses their excess jobs.

### 6. Teams & Collaboration
- **Multi-User Teams**: Pro and Team tier users can create and manage their own teams.
- **Role-Based Access Control**:
  - **Owners/Admins**: Can add/remove members, change roles, and delete team-owned jobs.
  - **Members**: Can view and edit jobs assigned to the team.
- **Job Ownership**: Jobs can be assigned as personal (bound only to the User) or assigned to a Team. Team-owned jobs appear on the dashboards of all team members with collaborative edit access.
- **Subscription Caps**: Plan job limits are enforced only against personal jobs. Team-owned jobs fall under the team owner's practically unlimited billing quota.

### 7. Deployment & Infrastructure
- **Server Stack**: Nginx (reverse proxy) -> Gunicorn -> Flask application.
- **Automated Deployment**: A `deploy.sh` script automates pulling from Git, syncing python dependencies via `requirements.txt`, running `flask db upgrade` to apply any pending migrations, reloading systemd daemons, restarting the UI and Worker services, and running health checks (stops and retries on 000 status codes).
- **Database Migrations**: Schema changes use Flask-Migrate (Alembic). Generate a migration with `flask db migrate -m "description"`, review the generated file in `migrations/versions/`, then apply with `flask db upgrade`. The `deploy.sh` script runs `flask db upgrade` automatically on every deploy. Migrations use batch mode (`render_as_batch=True`) so they work transparently on both SQLite and MySQL.
- **Timezones**: All internal datetimes are stored as naive UTC (`datetime.now(timezone.utc).replace(tzinfo=None)`) to prevent comparison crashes across the application and worker processes. The UI explicitly converts these to the user's local timezone via JavaScript or native template rendering.
  - **Per-Job Timezone**: Each job has a configurable timezone (dropdown on create/edit forms). New jobs default to the user's profile timezone. This allows a single user to monitor servers across different time zones.
  - **Schedule Calculation**: `calculate_next_expected()` converts UTC "now" to the job's local timezone, feeds it to croniter (so cron expressions are evaluated in local time), then converts the result back to naive UTC for storage. This ensures DST transitions are handled correctly. A 60-second early tolerance is applied: if the next scheduled occurrence is less than 60 seconds away, it is skipped in favor of the following one. This prevents false late alerts caused by minor clock drift (e.g. a cron job pinging at 11:59:54 for a noon schedule).

### 8. Self-Hosted Mode
- **Activation**: Set `SELF_HOSTED=true` in `.env`. This is the single flag that controls all self-hosted behaviors.
- **Database Auto-Setup**: On first deploy, `flask db upgrade` (run by `deploy.sh`) creates all tables from versioned migration files. Self-hosters using the SQLite fallback (no `DATABASE_URL` set) need zero manual SQL — just run the deploy script or `flask db upgrade`. For MySQL users, the same migration-based setup applies.
- **Plan Unlocking**: All `get_plan_limits()`, `get_job_limit()`, `get_history_days()`, and `is_feature_allowed()` calls return Team-tier values. Every feature is unlocked: unlimited jobs, webhooks, Slack, dependency chains, and 365-day run history.
- **Marketing Page Skipped**: The `/` landing page redirects unauthenticated users to `/login` instead of showing the marketing site. Authenticated users still redirect to `/dashboard` as normal.
- **Billing UI Hidden**: The Subscription nav link is hidden (via `is_self_hosted` Jinja context variable). Upgrade hints on job forms are suppressed by the plan limits returning `True` for all feature flags.
- **reCAPTCHA Bypassed**: `_verify_recaptcha()` returns `True` immediately, so self-hosters don't need Google reCAPTCHA keys.
- **Email Auto-Verification**: New accounts are auto-verified on registration, skipping the verification email. Self-hosters don't need SMTP configured to log in.
- **Team Creation**: The Pro/Team plan requirement for creating teams is bypassed.
- **Design Rationale**: Self-hosters run on their own infrastructure, so tiered pricing and marketing content offer no value. The hosted service at `croncraft.app` is where billing applies. This aligns with the AGPLv3 license model.

### 9. Docker Deployment
CronCraft ships with Docker support for self-hosted deployments. Two profiles are available: **SQLite** (default, zero config) and **MySQL** (production-grade).

- **Architecture**: Two containers — `web` (Gunicorn) and `worker` (APScheduler) — share the same image. The entrypoint script runs `flask db upgrade` on every startup, so tables are created automatically on first boot.
- **Quick Start (SQLite)**:
  ```bash
  # 1. Create a minimal .env file
  cp .env.example .env
  # Edit .env: set SECRET_KEY, keep SELF_HOSTED=true, remove DATABASE_URL

  # 2. Start
  docker compose up -d
  ```
  The SQLite database is persisted in a Docker volume (`croncraft-data`) at `/app/data/app.db`. Data survives container rebuilds.

- **With MySQL**:
  ```bash
  # 1. Create .env with DATABASE_URL pointing to the compose MySQL service
  #    DATABASE_URL=mysql+pymysql://croncraft:croncraft_pass@mysql/croncraft

  # 2. Start with the mysql profile
  docker compose --profile mysql up -d
  ```
  MySQL data is persisted in a separate volume (`mysql-data`). Customize credentials via `MYSQL_PASSWORD` and `MYSQL_ROOT_PASSWORD` env vars.

- **Environment Variables**:
  | Variable | Default | Description |
  |----------|---------|-------------|
  | `SECRET_KEY` | *(required)* | Flask secret key |
  | `SELF_HOSTED` | `true` | Unlocks all features |
  | `DATABASE_URL` | *(none → SQLite)* | MySQL connection string |
  | `DATA_DIR` | `/app/data` | Directory for SQLite database file |
  | `GUNICORN_WORKERS` | `2` | Number of web worker processes |
  | `CRONCRAFT_PORT` | `5010` | Host port mapping for the web service |
  | `MYSQL_PASSWORD` | `croncraft_pass` | MySQL user password (mysql profile) |
  | `MYSQL_ROOT_PASSWORD` | `croncraft_root` | MySQL root password (mysql profile) |

- **Health Check**: The web container exposes a health check at `/health` (checked every 30s). The worker container restarts automatically on crash via `restart: unless-stopped`.
- **Updating**: Pull the latest image and restart — migrations run automatically:
  ```bash
  docker compose pull && docker compose up -d
  ```

### 10. App Versioning
- **Version File**: A plain-text `VERSION` file in the repo root contains the current version string. Format: `YYYYMMDD.NN` (e.g. `20260319.00`). The date portion is the release date; `.NN` is a revision counter for same-day releases (`.00`, `.01`, etc.).
- **Footer Display**: The version is shown in the bottom-right corner of every page footer (e.g. `v20260319.00`). Available to all users via the `app_version` Jinja context variable injected in `__init__.py`.
- **Admin Update Check**: On login, admin users trigger a remote version check against `https://raw.githubusercontent.com/cculver78/croncraft/main/VERSION`. If the remote version is newer than the local `VERSION` file, a flash notification is displayed: *"A new version of CronCraft is available: {remote} (you are running {local})"*.
  - The check uses a 3-second HTTP timeout and silently catches all failures — it never blocks or crashes the login flow.
  - Comparison uses lexicographic string ordering, which works correctly for the `YYYYMMDD.NN` format.
- **Opt-Out Toggle**: Admins can disable the update check via Settings → Admin Preferences → "Check for new versions on login" checkbox. Stored as `version_check_enabled` (Boolean, default `True`) on the User model.
- **Version Service** (`services/version_service.py`): Provides `get_local_version()`, `get_remote_version()`, and `is_update_available()` helpers.
- **Bumping the Version**: Update the `VERSION` file in the repo root (e.g. `20260320.00`) and push to `main`. Self-hosted instances will see the notification on the next admin login.

### 11. REST API (v1)
- **Plan Gating**: Pro and Team only. Free-tier users receive `403 Forbidden`. Self-hosted mode grants full access automatically.
- **Authentication**: Bearer token via the `Authorization` header. Tokens are generated from the Settings page and stored as SHA-256 hashes — the raw token is shown once on creation and cannot be retrieved again.
  - Header format: `Authorization: Bearer <token>`
  - Invalid or missing tokens return `401 Unauthorized`.
- **Base URL**: `/api/v1`
- **CSRF**: Exempt (token auth replaces cookie-based CSRF). Rate-limited at 60 requests/minute.
- **Response Envelope**: All endpoints return `{"ok": true, "data": ...}` on success or `{"ok": false, "error": "message"}` on failure. List endpoints additionally include a `pagination` metadata block.
- **Endpoints**:

  | Method | Path | Description |
  |--------|------|-------------|
  | `GET` | `/api/v1/jobs` | List all jobs (paginated, `?page=` `?per_page=`) |
  | `POST` | `/api/v1/jobs` | Create a job (JSON body) |
  | `GET` | `/api/v1/jobs/<id>` | Get a job with recent run history |
  | `GET` | `/api/v1/jobs/<id>/history` | Paginated run history (`?page=` `?per_page=`) |
  | `PUT` | `/api/v1/jobs/<id>` | Update a job (partial updates) |
  | `DELETE` | `/api/v1/jobs/<id>` | Delete a job |
  | `POST` | `/api/v1/jobs/<id>/pause` | Pause a job |
  | `POST` | `/api/v1/jobs/<id>/resume` | Resume a paused job |

- **Create/Update Fields**: `name`, `schedule` (cron expression), `grace_period` (1–1440 min), `timezone`, `notes`, `team_id`, `notify_email`, `notify_webhook`, `webhook_url`, `notify_slack`, `slack_webhook`, `depends_on`. Plan-gated features (webhook, Slack, dependencies) are silently stripped for ineligible plans.
- **Validation**: Same rules as the web UI — cron expression validation, SSRF protection on webhook URLs, job limit enforcement on personal jobs.
- **Token Management** (Settings page):
  - **Generate**: Creates a `secrets.token_urlsafe(32)` token, stores SHA-256 hash on the user.
  - **Regenerate**: Replaces the existing token (old token stops working immediately).
  - **Revoke**: Clears the token hash, disabling API access.
  - Free-tier users see a 🔒 upgrade hint instead of the token controls.

### 12. Anomaly Detection *(Pro/Team Only)*
Detects unusual job behavior by computing rolling statistics over the last 30 runs and flagging anything beyond **2.5 standard deviations**. Alerts fire even if the job technically succeeded — a backup that normally takes 4 minutes but suddenly takes 40 will trigger an anomaly alert.

- **Plan Gating**: Controlled by the `allow_anomaly_detection` flag in `plan_limits.py`. Free-tier users get nothing. Self-hosted mode has full access.
- **Dual-Metric Detection**:
  - **Response Latency (automatic)**: Computed as `pinged_at − expected_at` on every successful ping. Works out of the box with **zero user changes** — CronCraft already stores both timestamps on every `JobRun`.
  - **Execution Duration (optional, preferred)**: Users send their script's actual execution time via the `duration_ms` or `duration` query parameter on the ping endpoint. When ≥ 5 runs have duration data, CronCraft switches to this more precise metric automatically.
- **Metric Priority**: If the current ping includes `duration_ms` AND at least 5 historical runs have it, duration is used. Otherwise, response latency is the fallback.
- **Minimum Sample**: Anomaly checks require **≥ 5** data points. Fewer runs produce unreliable standard deviations.
- **Alert Cooldown**: Maximum one anomaly alert per job per **24 hours** to prevent spam on persistently slow jobs.
- **No Per-Job Toggle**: Anomaly detection activates automatically for Pro/Team users. No configuration needed.
- **Alert Channels**: Anomaly alerts dispatch via all configured channels (email, webhook, Slack), following the same plan-gated rules as other alert types. Webhook payloads include an `anomaly` object with `metric`, `current`, `mean`, `stdev`, and `z_score`.
- **Stats Computation**: Stats are aggregated from the existing `job_runs` table (no separate stats table). Python's `statistics.mean()` and `statistics.stdev()` are used for cross-database compatibility (SQLite lacks `STDDEV()`).

  **Sending Duration with a Ping:**

  The ping endpoint accepts an optional execution duration via query parameters:
  - `duration_ms` — integer, milliseconds (e.g. `?duration_ms=240000` for 4 minutes)
  - `duration` — float, seconds (e.g. `?duration=240` for 4 minutes, converted to ms internally)

  If both are provided, `duration_ms` takes precedence.

  **Usage Example (Bash Script):**
  Wrap your job and compute the elapsed time in milliseconds:
  ```bash
  #!/bin/bash

  START_MS=$(($(date +%s%N) / 1000000))

  # Run the actual task
  /usr/local/bin/my-backup-job.sh
  EXIT_CODE=$?

  END_MS=$(($(date +%s%N) / 1000000))
  DURATION_MS=$((END_MS - START_MS))

  if [ $EXIT_CODE -ne 0 ]; then
      curl -fsS --retry 3 "https://croncraft.app/ping/YOUR_TOKEN_HERE/fail?duration_ms=$DURATION_MS" > /dev/null
  else
      curl -fsS --retry 3 "https://croncraft.app/ping/YOUR_TOKEN_HERE?duration_ms=$DURATION_MS" > /dev/null
  fi
  ```

  **Usage Example (Direct edit in crontab):**
  For simple inline crontab entries, use `SECONDS` (Bash built-in) to measure elapsed time in seconds:
  ```bash
  0 2 * * * SECONDS=0; /usr/local/bin/my-backup-job.sh && curl -fsS --retry 3 "https://croncraft.app/ping/YOUR_TOKEN_HERE?duration=$SECONDS" > /dev/null || curl -fsS --retry 3 "https://croncraft.app/ping/YOUR_TOKEN_HERE/fail?duration=$SECONDS" > /dev/null
  ```

  **Usage Example (Windows Batch File):**
  Capture start/end times and compute duration in seconds:
  ```batch
  @echo off
  REM Capture start time (seconds since midnight)
  for /f "tokens=1-3 delims=:." %%a in ("%TIME%") do (
      set /a START=%%a*3600 + %%b*60 + %%c
  )

  REM Run the actual task
  "C:\Program Files\Python314\python.exe" C:\scripts\my_task.py
  set EXIT_CODE=%errorlevel%

  REM Capture end time and compute duration
  for /f "tokens=1-3 delims=:." %%a in ("%TIME%") do (
      set /a END=%%a*3600 + %%b*60 + %%c
  )
  set /a DURATION=%END%-%START%

  REM Report to CronCraft with duration
  if %EXIT_CODE% neq 0 (
      curl -fsS --retry 3 "https://croncraft.app/ping/YOUR_TOKEN_HERE/fail?duration=%DURATION%" > nul
  ) else (
      curl -fsS --retry 3 "https://croncraft.app/ping/YOUR_TOKEN_HERE?duration=%DURATION%" > nul
  )
  ```

  **Usage Example (PowerShell):**
  Use `Measure-Command` for precise timing:
  ```powershell
  $result = Measure-Command {
      & "C:\scripts\my_task.ps1"
  }
  $durationMs = [int]$result.TotalMilliseconds
  $exitCode = $LASTEXITCODE

  if ($exitCode -ne 0) {
      curl -fsS --retry 3 "https://croncraft.app/ping/YOUR_TOKEN_HERE/fail?duration_ms=$durationMs" | Out-Null
  } else {
      curl -fsS --retry 3 "https://croncraft.app/ping/YOUR_TOKEN_HERE?duration_ms=$durationMs" | Out-Null
  }
  ```


  **API Examples:**

  All examples assume `TOKEN` holds your API token:
  ```bash
  TOKEN="your_api_token_here"
  BASE="https://croncraft.app/api/v1"
  ```

  ---

  #### `GET /api/v1/jobs` — List All Jobs

  Returns every job you own plus team jobs you have access to. Paginated — defaults to 25 per page, max 100.

  ```bash
  # Page 1 (default)
  curl -s -H "Authorization: Bearer $TOKEN" "$BASE/jobs" | python3 -m json.tool

  # Custom page and page size
  curl -s -H "Authorization: Bearer $TOKEN" "$BASE/jobs?page=2&per_page=10" | python3 -m json.tool
  ```

  **Response (200):**
  ```json
  {
    "ok": true,
    "data": [
      {
        "id": 12,
        "name": "Nightly Backup",
        "schedule": "0 2 * * *",
        "timezone": "America/New_York",
        "grace_period": 30,
        "notes": "Runs on db-server-01",
        "is_active": true,
        "last_status": "ok",
        "last_ping_at": "2026-03-19T06:00:02",
        "expected_at": "2026-03-20T06:00:00",
        "ping_url": "https://croncraft.app/ping/aBcDeFgHiJkLmNoP",
        "notify_email": true,
        "notify_webhook": false,
        "webhook_url": null,
        "notify_slack": true,
        "slack_webhook": "https://hooks.slack.com/services/T00/B00/xxxx",
        "depends_on": null,
        "team_id": null,
        "created_at": "2026-03-10T14:22:31"
      }
    ],
    "pagination": {
      "page": 1,
      "per_page": 25,
      "total": 147,
      "pages": 6
    }
  }
  ```

  ---

  #### `GET /api/v1/jobs/<id>/history` — Paginated Run History

  Returns the full run history for a job, paginated. Filtered by the plan's retention window (Free 7 days, Pro 90 days, Team 365 days). Defaults to 25 per page, max 100.

  ```bash
  # Page 1 (default)
  curl -s -H "Authorization: Bearer $TOKEN" "$BASE/jobs/12/history" | python3 -m json.tool

  # Custom page and page size
  curl -s -H "Authorization: Bearer $TOKEN" "$BASE/jobs/12/history?page=3&per_page=50" | python3 -m json.tool
  ```

  **Response (200):**
  ```json
  {
    "ok": true,
    "data": [
      {
        "id": 501,
        "status": "ok",
        "pinged_at": "2026-03-19T06:00:02",
        "expected_at": "2026-03-19T06:00:00",
        "duration_ms": null,
        "ip_address": "203.0.113.42",
        "created_at": "2026-03-19T06:00:02"
      }
    ],
    "pagination": {
      "page": 1,
      "per_page": 25,
      "total": 312,
      "pages": 13
    }
  }
  ```

  ---

  #### `POST /api/v1/jobs` — Create a Job

  Creates a new monitored job. Only `name` and `schedule` are required.

  **All accepted fields:**

  | Field | Type | Required | Default | Notes |
  |-------|------|----------|---------|-------|
  | `name` | string | ✅ | — | Max 255 characters |
  | `schedule` | string | ✅ | — | Valid cron expression (e.g. `*/5 * * * *`) |
  | `grace_period` | integer | — | `15` | Minutes (1–1440) before a miss is flagged |
  | `timezone` | string | — | User's profile TZ | IANA timezone (e.g. `America/Chicago`) |
  | `notes` | string | — | `null` | Max 255 characters |
  | `team_id` | integer | — | `null` | Assign to a team you're a member of |
  | `notify_email` | boolean | — | `true` | Send email alerts |
  | `notify_webhook` | boolean | — | `false` | Send webhook alerts *(Pro+ only)* |
  | `webhook_url` | string | — | `null` | Required if `notify_webhook` is true |
  | `notify_slack` | boolean | — | `false` | Send Slack alerts *(Pro+ only)* |
  | `slack_webhook` | string | — | `null` | Slack Incoming Webhook URL *(Pro+ only)* |
  | `depends_on` | integer | — | `null` | Parent job ID for dependency chain *(Pro+ only)* |

  **Minimal example:**
  ```bash
  curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "DB Backup",
      "schedule": "0 2 * * *"
    }' \
    "$BASE/jobs" | python3 -m json.tool
  ```

  **Full example with all options:**
  ```bash
  curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Nightly ETL Pipeline",
      "schedule": "30 3 * * *",
      "grace_period": 45,
      "timezone": "America/New_York",
      "notes": "Extracts from prod DB, loads to warehouse",
      "notify_email": true,
      "notify_webhook": true,
      "webhook_url": "https://hooks.example.com/croncraft",
      "notify_slack": true,
      "slack_webhook": "https://hooks.slack.com/services/T00/B00/xxxx",
      "depends_on": 12
    }' \
    "$BASE/jobs" | python3 -m json.tool
  ```

  **Response (201 Created):**
  ```json
  {
    "ok": true,
    "data": {
      "id": 18,
      "name": "Nightly ETL Pipeline",
      "schedule": "30 3 * * *",
      "timezone": "America/New_York",
      "grace_period": 45,
      "notes": "Extracts from prod DB, loads to warehouse",
      "is_active": true,
      "last_status": "never_run",
      "last_ping_at": null,
      "expected_at": "2026-03-20T07:30:00",
      "ping_url": "https://croncraft.app/ping/xYzAbCdEfGhIjKlM",
      "notify_email": true,
      "notify_webhook": true,
      "webhook_url": "https://hooks.example.com/croncraft",
      "notify_slack": true,
      "slack_webhook": "https://hooks.slack.com/services/T00/B00/xxxx",
      "depends_on": 12,
      "team_id": null,
      "created_at": "2026-03-19T21:35:00"
    }
  }
  ```

  **Error — invalid cron expression (400):**
  ```json
  {
    "ok": false,
    "error": "schedule must be a valid cron expression."
  }
  ```

  **Error — job limit reached (403):**
  ```json
  {
    "ok": false,
    "error": "You have reached the Free plan limit of 10 personal jobs."
  }
  ```

  ---

  #### `GET /api/v1/jobs/<id>` — Get a Single Job

  Returns the job details plus recent run history (up to **100 runs** within the plan's retention window: Free 7 days, Pro 90 days, Team 365 days).

  ```bash
  curl -s -H "Authorization: Bearer $TOKEN" "$BASE/jobs/12" | python3 -m json.tool
  ```

  **Response (200):**
  ```json
  {
    "ok": true,
    "data": {
      "id": 12,
      "name": "Nightly Backup",
      "schedule": "0 2 * * *",
      "timezone": "America/New_York",
      "grace_period": 30,
      "notes": "Runs on db-server-01",
      "is_active": true,
      "last_status": "ok",
      "last_ping_at": "2026-03-19T06:00:02",
      "expected_at": "2026-03-20T06:00:00",
      "ping_url": "https://croncraft.app/ping/aBcDeFgHiJkLmNoP",
      "notify_email": true,
      "notify_webhook": false,
      "webhook_url": null,
      "notify_slack": false,
      "slack_webhook": null,
      "depends_on": null,
      "team_id": null,
      "created_at": "2026-03-10T14:22:31",
      "runs": [
        {
          "id": 501,
          "status": "ok",
          "pinged_at": "2026-03-19T06:00:02",
          "expected_at": "2026-03-19T06:00:00",
          "duration_ms": null,
          "ip_address": "203.0.113.42",
          "created_at": "2026-03-19T06:00:02"
        },
        {
          "id": 488,
          "status": "ok",
          "pinged_at": "2026-03-18T06:00:01",
          "expected_at": "2026-03-18T06:00:00",
          "duration_ms": null,
          "ip_address": "203.0.113.42",
          "created_at": "2026-03-18T06:00:01"
        }
      ]
    }
  }
  ```

  **Error — job not found or no access (404):**
  ```json
  {
    "ok": false,
    "error": "Job not found."
  }
  ```

  ---

  #### `PUT /api/v1/jobs/<id>` — Update a Job

  Supports partial updates — only include the fields you want to change. Omitted fields are left untouched.

  **Change name and grace period only:**
  ```bash
  curl -s -X PUT \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Nightly Backup v2",
      "grace_period": 60
    }' \
    "$BASE/jobs/12" | python3 -m json.tool
  ```

  **Change schedule and timezone (recalculates next expected window):**
  ```bash
  curl -s -X PUT \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "schedule": "0 3 * * *",
      "timezone": "UTC"
    }' \
    "$BASE/jobs/12" | python3 -m json.tool
  ```

  **Enable Slack alerts (Pro+ only):**
  ```bash
  curl -s -X PUT \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "notify_slack": true,
      "slack_webhook": "https://hooks.slack.com/services/T00/B00/xxxx"
    }' \
    "$BASE/jobs/12" | python3 -m json.tool
  ```

  **Move job to a team:**
  ```bash
  curl -s -X PUT \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"team_id": 3}' \
    "$BASE/jobs/12" | python3 -m json.tool
  ```

  **Response (200):** Returns the full updated job object (same shape as GET).
  ```json
  {
    "ok": true,
    "data": {
      "id": 12,
      "name": "Nightly Backup v2",
      "schedule": "0 3 * * *",
      "timezone": "UTC",
      "grace_period": 60,
      "notes": "Runs on db-server-01",
      "is_active": true,
      "last_status": "ok",
      "last_ping_at": "2026-03-19T06:00:02",
      "expected_at": "2026-03-20T03:00:00",
      "ping_url": "https://croncraft.app/ping/aBcDeFgHiJkLmNoP",
      "notify_email": true,
      "notify_webhook": false,
      "webhook_url": null,
      "notify_slack": false,
      "slack_webhook": null,
      "depends_on": null,
      "team_id": null,
      "created_at": "2026-03-10T14:22:31"
    }
  }
  ```

  ---

  #### `DELETE /api/v1/jobs/<id>` — Delete a Job

  Permanently deletes the job and all associated run history and alerts. This cannot be undone.

  ```bash
  curl -s -X DELETE \
    -H "Authorization: Bearer $TOKEN" \
    "$BASE/jobs/18" | python3 -m json.tool
  ```

  **Response (200):**
  ```json
  {
    "ok": true,
    "data": {
      "id": 18,
      "deleted": true
    }
  }
  ```

  ---

  #### `POST /api/v1/jobs/<id>/pause` — Pause a Job

  Pauses monitoring. The worker will stop checking this job until it is resumed. Does not delete any data.

  ```bash
  curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    "$BASE/jobs/12/pause" | python3 -m json.tool
  ```

  **Response (200):** Returns the job with `is_active: false`.
  ```json
  {
    "ok": true,
    "data": {
      "id": 12,
      "name": "Nightly Backup",
      "is_active": false,
      "last_status": "ok",
      "schedule": "0 2 * * *",
      "timezone": "America/New_York",
      "grace_period": 30,
      "notes": "Runs on db-server-01",
      "last_ping_at": "2026-03-19T06:00:02",
      "expected_at": "2026-03-20T06:00:00",
      "ping_url": "https://croncraft.app/ping/aBcDeFgHiJkLmNoP",
      "notify_email": true,
      "notify_webhook": false,
      "webhook_url": null,
      "notify_slack": false,
      "slack_webhook": null,
      "depends_on": null,
      "team_id": null,
      "created_at": "2026-03-10T14:22:31"
    }
  }
  ```

  **Error — already paused (409):**
  ```json
  {
    "ok": false,
    "error": "Job is already paused."
  }
  ```

  ---

  #### `POST /api/v1/jobs/<id>/resume` — Resume a Paused Job

  Resumes a paused job. Recalculates the next expected window and resets status to `ok`. Subject to the plan's active job limit for personal jobs.

  ```bash
  curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    "$BASE/jobs/12/resume" | python3 -m json.tool
  ```

  **Response (200):** Returns the job with `is_active: true` and a fresh `expected_at`.
  ```json
  {
    "ok": true,
    "data": {
      "id": 12,
      "name": "Nightly Backup",
      "is_active": true,
      "last_status": "ok",
      "expected_at": "2026-03-20T03:00:00",
      "schedule": "0 2 * * *",
      "timezone": "America/New_York",
      "grace_period": 30,
      "notes": "Runs on db-server-01",
      "last_ping_at": "2026-03-19T06:00:02",
      "ping_url": "https://croncraft.app/ping/aBcDeFgHiJkLmNoP",
      "notify_email": true,
      "notify_webhook": false,
      "webhook_url": null,
      "notify_slack": false,
      "slack_webhook": null,
      "depends_on": null,
      "team_id": null,
      "created_at": "2026-03-10T14:22:31"
    }
  }
  ```

  **Error — already active (409):**
  ```json
  {
    "ok": false,
    "error": "Job is already active."
  }
  ```

  **Error — job limit reached (403):**
  ```json
  {
    "ok": false,
    "error": "Cannot resume — you have reached the Pro plan limit of ... active jobs."
  }
  ```

  ---

  #### Authentication Errors

  **Missing or malformed header (401):**
  ```bash
  curl -s https://croncraft.app/api/v1/jobs
  ```
  ```json
  {
    "ok": false,
    "error": "Missing or malformed Authorization header. Use: Bearer <token>"
  }
  ```

  **Invalid token (401):**
  ```bash
  curl -s -H "Authorization: Bearer wrong_token" https://croncraft.app/api/v1/jobs
  ```
  ```json
  {
    "ok": false,
    "error": "Invalid API token."
  }
  ```

  **Free-tier user (403):**
  ```bash
  curl -s -H "Authorization: Bearer free_user_token" https://croncraft.app/api/v1/jobs
  ```
  ```json
  {
    "ok": false,
    "error": "API access requires a Pro or Team plan."
  }
  ```

