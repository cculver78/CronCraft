# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from app.extensions import db
from datetime import datetime, timezone

class Team(db.Model):
    __tablename__ = 'teams'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    owner_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    members = db.relationship('TeamMember', backref='team', lazy=True)
    jobs = db.relationship('Job', backref='team', lazy=True)

class TeamMember(db.Model):
    __tablename__ = 'team_members'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    team_id = db.Column(db.BigInteger, db.ForeignKey('teams.id'), nullable=False)
    user_id = db.Column(db.BigInteger, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.Enum('admin', 'member'), default='member')
