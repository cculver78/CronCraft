# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from app.extensions import db
from datetime import datetime, timezone

class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False)
    team_id = db.Column(db.BigInteger, db.ForeignKey('teams.id'), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    notes = db.Column(db.String(255), nullable=True)
    ping_token = db.Column(db.String(64), unique=True, nullable=False)
    schedule = db.Column(db.String(100), nullable=False)
    grace_period = db.Column(db.Integer, default=15)
    timezone = db.Column(db.String(64), default='UTC')
    is_active = db.Column(db.Boolean, default=True)
    notify_email = db.Column(db.Boolean, default=True)
    notify_slack = db.Column(db.Boolean, default=False)
    slack_webhook = db.Column(db.String(500))
    notify_webhook = db.Column(db.Boolean, default=False)
    webhook_url = db.Column(db.String(500))
    depends_on = db.Column(db.BigInteger, db.ForeignKey('jobs.id'), nullable=True)
    last_ping_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.Enum('ok', 'late', 'failed', 'never_run'), default='never_run')
    miss_count = db.Column(db.Integer, default=0)
    expected_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    runs = db.relationship('JobRun', backref='job', lazy=True, cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='job', lazy=True, cascade='all, delete-orphan')

class JobRun(db.Model):
    __tablename__ = 'job_runs'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_id = db.Column(db.BigInteger, db.ForeignKey('jobs.id'), nullable=False)
    status = db.Column(db.Enum('ok', 'late', 'failed'))
    pinged_at = db.Column(db.DateTime, nullable=True)
    expected_at = db.Column(db.DateTime, nullable=True)
    duration_ms = db.Column(db.BigInteger)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_id = db.Column(db.BigInteger, db.ForeignKey('jobs.id'), nullable=False)
    alert_type = db.Column(db.Enum('missed', 'recovered', 'failed', 'dependency_failed', 'anomaly'))
    sent_via = db.Column(db.Enum('email', 'slack', 'webhook'))
    sent_at = db.Column(db.DateTime, nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
