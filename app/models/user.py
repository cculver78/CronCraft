# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from app.extensions import db
from flask_login import UserMixin
from datetime import datetime, timezone

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.Enum('free', 'pro', 'team'), default='free')
    stripe_customer_id = db.Column(db.String(255))
    stripe_subscription_id = db.Column(db.String(255))
    timezone = db.Column(db.String(50), default='UTC')
    username = db.Column(db.String(50), unique=True, nullable=True)
    display_name = db.Column(db.String(100), nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    plan_started_at = db.Column(db.DateTime, nullable=True)
    date_format = db.Column(db.String(20), default='YYYY-MM-DD')
    time_format = db.Column(db.String(10), default='24h')
    grace_period_end = db.Column(db.DateTime, nullable=True)
    api_token_hash = db.Column(db.String(64), unique=True, nullable=True)
    version_check_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    teams_owned = db.relationship('Team', backref='owner', lazy=True)
    jobs = db.relationship('Job', backref='user', lazy=True)

from app.extensions import login_manager

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

