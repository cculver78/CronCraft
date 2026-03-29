# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Blueprint, render_template

bp = Blueprint("marketing", __name__)


def _page(template: str, *, page_title: str, meta_description: str, canonical_path: str, **extra):
    return render_template(
        template,
        page_title=page_title,
        meta_description=meta_description,
        canonical_path=canonical_path,
        **extra,
    )


# --- Tier 1 keyword pages ---


@bp.route("/cron-job-monitoring")
def cron_job_monitoring():
    return _page(
        "marketing/cron_job_monitoring.html",
        page_title="Cron Job Monitoring — Dead Man's Switch Alerts | CronCraft",
        meta_description="Cron job monitoring with heartbeat pings, grace periods, and Slack or email alerts. Self-host or use croncraft.app.",
        canonical_path="/cron-job-monitoring",
    )


@bp.route("/scheduled-task-monitoring")
def scheduled_task_monitoring():
    return _page(
        "marketing/scheduled_task_monitoring.html",
        page_title="Scheduled Task Monitoring | CronCraft",
        meta_description="Monitor scheduled tasks from cron, systemd timers, or Windows Task Scheduler with a single success ping.",
        canonical_path="/scheduled-task-monitoring",
    )


@bp.route("/heartbeat-monitoring")
def heartbeat_monitoring():
    return _page(
        "marketing/heartbeat_monitoring.html",
        page_title="Heartbeat Monitoring Service for Cron & Jobs | CronCraft",
        meta_description="Heartbeat monitoring: jobs ping when they finish. Miss a window and get alerted before users notice.",
        canonical_path="/heartbeat-monitoring",
    )


@bp.route("/dead-mans-switch-monitoring")
def dead_mans_switch_monitoring():
    return _page(
        "marketing/dead_mans_switch_monitoring.html",
        page_title="Dead Man's Switch Monitoring | CronCraft",
        meta_description="Dead man's switch monitoring for scripts and cron. No ping by the deadline means an alert — with configurable grace periods.",
        canonical_path="/dead-mans-switch-monitoring",
    )


@bp.route("/background-job-monitoring")
def background_job_monitoring():
    return _page(
        "marketing/background_job_monitoring.html",
        page_title="Background Job Monitoring | CronCraft",
        meta_description="Monitor background jobs and workers with HTTP pings. Works with any language or queue — no agent required.",
        canonical_path="/background-job-monitoring",
    )


# --- Tier 2 ---


@bp.route("/free-cron-monitoring")
def free_cron_monitoring():
    return _page(
        "marketing/free_cron_monitoring.html",
        page_title="Free Cron Job Monitoring (10 Jobs) | CronCraft",
        meta_description="Free cron monitoring: 10 jobs, email alerts, 7-day history. No credit card. Upgrade when you need Slack or dependency chains.",
        canonical_path="/free-cron-monitoring",
    )


@bp.route("/open-source-cron-monitoring")
def open_source_cron_monitoring():
    return _page(
        "marketing/open_source_cron_monitoring.html",
        page_title="Open Source Cron Monitoring (AGPL) | CronCraft",
        meta_description="CronCraft is open source under AGPL. Self-host with Docker Compose or use the hosted service at croncraft.app.",
        canonical_path="/open-source-cron-monitoring",
    )


@bp.route("/self-hosted-cron-monitoring")
def self_hosted_cron_monitoring():
    return _page(
        "marketing/self_hosted_cron_monitoring.html",
        page_title="Self-Hosted Cron Job Monitor (Docker) | CronCraft",
        meta_description="Run CronCraft on your own hardware with Docker Compose. Full feature set for self-hosters — no per-monitor billing.",
        canonical_path="/self-hosted-cron-monitoring",
    )


# --- Compare ---


@bp.route("/compare/cronhub-alternative")
def cronhub_alternative():
    return _page(
        "marketing/cronhub_alternative.html",
        page_title="Cronhub Alternative — Migrate Before June 30, 2026 | CronCraft",
        meta_description="Cronhub is shutting down June 30, 2026. CronCraft is a drop-in ping URL replacement with free tier and self-hosted option.",
        canonical_path="/compare/cronhub-alternative",
    )


@bp.route("/compare/cronhub-migration")
def cronhub_migration():
    return _page(
        "marketing/cronhub_migration.html",
        page_title="Cronhub Migration Guide — Swap Ping URLs in Minutes | CronCraft",
        meta_description="Step-by-step Cronhub to CronCraft migration: new jobs, replace curl ping URLs, verify dashboard, cancel Cronhub.",
        canonical_path="/compare/cronhub-migration",
    )


@bp.route("/compare/healthchecks-alternative")
def healthchecks_alternative():
    return _page(
        "marketing/healthchecks_alternative.html",
        page_title="Healthchecks.io Alternative | CronCraft",
        meta_description="Considering a Healthchecks.io alternative? CronCraft adds dependency chains, simple $19/$49 pricing, and Docker self-hosting.",
        canonical_path="/compare/healthchecks-alternative",
    )


@bp.route("/compare/cronitor-alternative")
def cronitor_alternative():
    return _page(
        "marketing/cronitor_alternative.html",
        page_title="Cronitor Alternative — Simpler Cron Monitoring | CronCraft",
        meta_description="Cronitor alternative with flat pricing and no per-monitor math. CronCraft focuses on cron heartbeats, chains, and alerts.",
        canonical_path="/compare/cronitor-alternative",
    )


@bp.route("/compare/dead-mans-snitch-alternative")
def dead_mans_snitch_alternative():
    return _page(
        "marketing/dead_mans_snitch_alternative.html",
        page_title="Dead Man's Snitch Alternative | CronCraft",
        meta_description="Dead Man's Snitch alternative with 10 free jobs, dependency chains on Pro, and optional self-hosting via Docker.",
        canonical_path="/compare/dead-mans-snitch-alternative",
    )


@bp.route("/compare/croncraft-vs-healthchecks")
def croncraft_vs_healthchecks():
    return _page(
        "marketing/croncraft_vs_healthchecks.html",
        page_title="CronCraft vs Healthchecks.io — Honest Comparison | CronCraft",
        meta_description="Side-by-side: free tier, self-hosting, integrations, and where each tool wins. CronCraft vs Healthchecks.io for developers.",
        canonical_path="/compare/croncraft-vs-healthchecks",
    )


@bp.route("/compare/croncraft-vs-cronitor")
def croncraft_vs_cronitor():
    return _page(
        "marketing/croncraft_vs_cronitor.html",
        page_title="CronCraft vs Cronitor — Comparison | CronCraft",
        meta_description="CronCraft vs Cronitor: scope, pricing model, and who each product fits. Honest trade-offs for cron monitoring.",
        canonical_path="/compare/croncraft-vs-cronitor",
    )


@bp.route("/compare/croncraft-vs-dead-mans-snitch")
def croncraft_vs_dead_mans_snitch():
    return _page(
        "marketing/croncraft_vs_dead_mans_snitch.html",
        page_title="CronCraft vs Dead Man's Snitch | CronCraft",
        meta_description="Compare CronCraft and Dead Man's Snitch on free tier limits, pricing, self-hosting, and dependency-aware monitoring.",
        canonical_path="/compare/croncraft-vs-dead-mans-snitch",
    )


# --- Use cases ---


@bp.route("/use-cases/database-backups")
def use_case_database_backups():
    return _page(
        "marketing/use_case_database_backups.html",
        page_title="Monitor Database Backup Cron Jobs | CronCraft",
        meta_description="Ping CronCraft after pg_dump or mysqldump succeeds. If the backup cron fails silently, you get emailed before data loss bites.",
        canonical_path="/use-cases/database-backups",
    )


@bp.route("/use-cases/heroku-scheduler")
def use_case_heroku_scheduler():
    return _page(
        "marketing/use_case_heroku_scheduler.html",
        page_title="Monitor Heroku Scheduler with CronCraft | CronCraft",
        meta_description="Add a one-line curl ping after your Heroku Scheduler task. Heartbeat monitoring without adding another Heroku add-on.",
        canonical_path="/use-cases/heroku-scheduler",
    )


@bp.route("/use-cases/kubernetes")
def use_case_kubernetes():
    return _page(
        "marketing/use_case_kubernetes.html",
        page_title="Kubernetes CronJob Monitoring | CronCraft",
        meta_description="Call CronCraft from a Kubernetes CronJob when the job completes. Example manifest snippet and curl ping pattern.",
        canonical_path="/use-cases/kubernetes",
    )


@bp.route("/use-cases/python")
def use_case_python():
    return _page(
        "marketing/use_case_python.html",
        page_title="Monitor Python Scheduled Tasks & Cron | CronCraft",
        meta_description="Ping CronCraft from Python with urllib or requests after your scheduled job finishes. Copy-paste examples.",
        canonical_path="/use-cases/python",
    )


@bp.route("/use-cases/bash")
def use_case_bash():
    return _page(
        "marketing/use_case_bash.html",
        page_title="Monitor Bash Cron Scripts | CronCraft",
        meta_description="The classic pattern: run your bash job, then curl your CronCraft ping URL on success. Examples for crontab.",
        canonical_path="/use-cases/bash",
    )


@bp.route("/use-cases/windows-scheduled-tasks")
def use_case_windows_scheduled_tasks():
    return _page(
        "marketing/use_case_windows_scheduled_tasks.html",
        page_title="Monitor Windows Scheduled Tasks | CronCraft",
        meta_description="Ping CronCraft from PowerShell or curl.exe after a scheduled task completes. Heartbeat monitoring for Windows Server.",
        canonical_path="/use-cases/windows-scheduled-tasks",
    )


# --- Integrations ---


@bp.route("/integrations/slack")
def integration_slack():
    return _page(
        "marketing/integration_slack.html",
        page_title="Cron Job Slack Alerts | CronCraft",
        meta_description="Slack notifications when a job goes late or fails. Available on Pro and Team — webhook-based, minutes to configure.",
        canonical_path="/integrations/slack",
    )


# --- Blog ---


@bp.route("/blog/how-to-monitor-cron-jobs")
def blog_how_to_monitor_cron_jobs():
    return _page(
        "marketing/blog_how_to_monitor_cron_jobs.html",
        page_title="How to Monitor Cron Jobs — Complete Guide | CronCraft",
        meta_description="Email logs, log aggregation, or heartbeat pings: how to monitor cron jobs reliably and why silent failures are the default without tooling.",
        canonical_path="/blog/how-to-monitor-cron-jobs",
    )


@bp.route("/blog/prevent-silent-cron-failures")
def blog_prevent_silent_cron_failures():
    return _page(
        "marketing/blog_prevent_silent_cron_failures.html",
        page_title="Prevent Silent Cron Job Failures | CronCraft Blog",
        meta_description="Why cron fails quietly and how dead man's switch monitoring catches missed runs before anyone notices.",
        canonical_path="/blog/prevent-silent-cron-failures",
    )


@bp.route("/blog/cron-job-not-running")
def blog_cron_job_not_running():
    return _page(
        "marketing/blog_cron_job_not_running.html",
        page_title="Cron Job Not Running? Troubleshooting Guide | CronCraft",
        meta_description="Check PATH, user, locks, and schedules — plus how heartbeat monitoring tells you when the job stopped firing entirely.",
        canonical_path="/blog/cron-job-not-running",
    )


@bp.route("/blog/dead-mans-switch-pattern")
def blog_dead_mans_switch_pattern():
    return _page(
        "marketing/blog_dead_mans_switch_pattern.html",
        page_title="Dead Man's Switch Pattern Explained | CronCraft Blog",
        meta_description="What a dead man's switch is, when to use it for batch jobs, and how heartbeat URLs implement it in practice.",
        canonical_path="/blog/dead-mans-switch-pattern",
    )


@bp.route("/blog/cron-job-best-practices")
def blog_cron_job_best_practices():
    return _page(
        "marketing/blog_cron_job_best_practices.html",
        page_title="Cron Job Reliability Best Practices | CronCraft Blog",
        meta_description="Idempotency, logging, timeouts, and monitoring: practical cron job best practices for production systems.",
        canonical_path="/blog/cron-job-best-practices",
    )


@bp.route("/blog/cron-job-dependencies")
def blog_cron_job_dependencies():
    return _page(
        "marketing/blog_cron_job_dependencies.html",
        page_title="Cron Job Dependency Management | CronCraft Blog",
        meta_description="Model job A then job B without silent handoffs. How dependency chains work and when they beat ad-hoc scripting.",
        canonical_path="/blog/cron-job-dependencies",
    )
