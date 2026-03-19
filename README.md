# CronCraft(tm)

**Cron job monitoring that actually tells you when things break.**

CronCraft is a production cron job monitor with a visual web UI. Your jobs ping CronCraft when they complete. If the ping doesn't arrive on schedule, you get alerted immediately -- not three weeks later when someone notices the backup never ran.

No agent to install. No dependencies. Works with any cron job on any server with a single `curl` line.

---

## The Problem

Cron jobs are silent killers. They fail with no noise, no alert, and no log you can easily find. Every developer who runs a server has lost time to a job that stopped running quietly.

---

## Quick Start (Self-Hosted)

```bash
# 1. Clone and configure
git clone https://github.com/cculver78/croncraft.git
cd croncraft
cp .env.example .env
# Edit .env: set SECRET_KEY and SELF_HOSTED=true

# 2. Start (SQLite, zero config)
docker compose up -d
```

That's it. The database is created automatically on first boot. Visit `http://localhost:5010` and register -- the first account gets admin privileges automatically.

**With MySQL instead:**
```bash
# Set DATABASE_URL=mysql+pymysql://croncraft:pass@mysql/croncraft in .env
docker compose --profile mysql up -d
```

---

## Integrating a Job

At the end of your cron script, add one line:

```bash
# Success ping
curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN_HERE > /dev/null

# Or report success/failure based on exit code
0 2 * * * /usr/local/bin/backup.sh && curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN > /dev/null || curl -fsS --retry 3 https://croncraft.app/ping/YOUR_TOKEN/fail > /dev/null
```

Windows Task Scheduler and PowerShell are also supported -- see the docs.

---

## Features

### Monitoring
- **Dead Man's Switch** -- jobs ping in; silence triggers an alert
- **Explicit fail endpoint** -- `/ping/<token>/fail` for scripts that know they failed
- **Auto-escalation** -- 3 consecutive missed windows promotes a job from LATE to FAILED
- **Per-job timezones** -- monitor servers across time zones correctly
- **Grace periods** -- configurable buffer before a missed ping fires an alert

### Alerting
- Email (all tiers)
- Slack Incoming Webhooks (Pro+)
- Generic HTTP Webhooks (Pro+)
- Dependency chain failures propagate immediately to downstream jobs (Pro+)

### Anomaly Detection (Pro/Team)
- Flags jobs running significantly faster or slower than their rolling average (2.5 standard deviations over last 30 runs)
- Works automatically from response latency -- or pass `?duration_ms=` for precise execution-time tracking
- Alerts fire even on technically successful jobs
- 24-hour cooldown per job to prevent spam

### Teams & Collaboration
- Create teams and share job ownership across members
- Role-based access: owners, admins, and members
- Team jobs don't count against personal plan limits

### REST API (Pro/Team)
Bearer token authentication. Full CRUD on jobs plus pause/resume and paginated run history.

```bash
curl -H "Authorization: Bearer $TOKEN" https://croncraft.app/api/v1/jobs
```

See `DEV_DOCUMENT.md` for the full API reference.

### History & Retention
| Tier | Retention |
|------|-----------|
| Free | 7 days |
| Pro | 90 days |
| Team | 365 days |

### Admin Panel
- System-wide stats, user management, plan overrides
- Impersonate any user for troubleshooting
- First registered account is auto-promoted to admin

---

## Plan Tiers

| Feature | Free | Pro ($19/mo) | Team ($49/mo) |
|---------|------|--------------|---------------|
| Monitored Jobs | 10 | Unlimited | Unlimited |
| Run History | 7 days | 90 days | 365 days |
| Email Alerts | Yes | Yes | Yes |
| Slack / Webhook Alerts | No | Yes | Yes |
| Dependency Chains | No | Yes | Yes |
| Anomaly Detection | No | Yes | Yes |
| REST API | No | Yes | Yes |
| Teams | No | No | Yes |

Self-hosted instances get Team-tier features automatically with no billing required.

---

## Architecture

- **Web app**: Python / Flask / SQLAlchemy / Jinja2
- **Background worker**: APScheduler (standalone process)
- **Database**: MySQL/MariaDB (production) or SQLite (fallback / self-hosted)
- **Migrations**: Flask-Migrate / Alembic
- **Payments**: Stripe (hosted version only)
- **Deployment**: Docker + docker-compose, or Nginx + Gunicorn + systemd

---

## Self-Hosted Mode

Set `SELF_HOSTED=true` in `.env` to:

- Unlock all Team-tier features with no billing
- Skip the marketing landing page (redirects straight to login)
- Hide all subscription/billing UI
- Auto-verify new accounts (no SMTP required to get started)
- Bypass reCAPTCHA (no Google keys needed)

---

## Updating

```bash
docker compose pull && docker compose up -d
```

Migrations run automatically on startup.

---

## License

AGPLv3. See [LICENSE](LICENSE).

If you self-host and modify CronCraft, the AGPL requires you to make those modifications available. The hosted service at `croncraft.app` is where the paid tiers live.

---

*Built by [Edge Case Software](https://edgecasesoftware.dev)*
