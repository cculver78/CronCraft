# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

"""
REST API v1 — Token-authenticated CRUD for Jobs.

Pro and Team only.  Free-tier users are blocked at the auth decorator level.
All endpoints return a consistent JSON envelope: {"ok": bool, "data"|"error": ...}
"""

from flask import Blueprint, request, jsonify, g, url_for
from sqlalchemy import or_

from app.extensions import db, csrf, limiter
from app.api_auth import require_api_token
from app.models.job import Job, JobRun
from app.models.team import Team, TeamMember
from app.services.scheduler import calculate_next_expected
from app.plan_limits import get_job_limit, is_feature_allowed, get_history_days
from app.validators import validate_webhook_url
from croniter import croniter
from datetime import datetime, timezone, timedelta
import secrets

bp = Blueprint('api_v1', __name__, url_prefix='/api/v1')

# API uses token auth, not cookies — exempt from CSRF
csrf.exempt(bp)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_to_dict(job):
    """Serialize a Job to a JSON-safe dict."""
    return {
        'id': job.id,
        'name': job.name,
        'schedule': job.schedule,
        'timezone': job.timezone,
        'grace_period': job.grace_period,
        'notes': job.notes,
        'is_active': job.is_active,
        'last_status': job.last_status,
        'last_ping_at': job.last_ping_at.isoformat() if job.last_ping_at else None,
        'expected_at': job.expected_at.isoformat() if job.expected_at else None,
        'ping_url': url_for('ping.receive_ping', token=job.ping_token, _external=True),
        'notify_email': job.notify_email,
        'notify_webhook': job.notify_webhook,
        'webhook_url': job.webhook_url,
        'notify_slack': job.notify_slack,
        'slack_webhook': job.slack_webhook,
        'depends_on': job.depends_on,
        'team_id': job.team_id,
        'created_at': job.created_at.isoformat() if job.created_at else None,
    }


def _get_user_team_ids(user):
    """Return list of team IDs the user owns or is a member of."""
    owned = Team.query.filter_by(owner_id=user.id).with_entities(Team.id).all()
    member = TeamMember.query.filter_by(user_id=user.id).with_entities(TeamMember.team_id).all()
    return list({t[0] for t in owned + member})


def _has_job_access(job, user):
    """Check whether the user owns or has team access to the job."""
    if job.user_id == user.id:
        return True
    if job.team_id:
        team = db.session.get(Team, job.team_id)
        if team and team.owner_id == user.id:
            return True
        if TeamMember.query.filter_by(team_id=job.team_id, user_id=user.id).first():
            return True
    return False


def _error(message, status=400):
    return jsonify({'ok': False, 'error': message}), status


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@bp.route('/jobs', methods=['GET'])
@limiter.limit("60 per minute")
@require_api_token
def list_jobs():
    """List all jobs the authenticated user has access to (paginated)."""
    user = g.api_user
    team_ids = _get_user_team_ids(user)

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 25, type=int), 100)
    if per_page < 1:
        per_page = 25

    query = Job.query.filter(
        or_(Job.user_id == user.id, Job.team_id.in_(team_ids)) if team_ids
        else Job.user_id == user.id
    ).order_by(Job.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    jobs = [_job_to_dict(j) for j in pagination.items]
    return jsonify({
        'ok': True,
        'data': jobs,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
        }
    })


@bp.route('/jobs', methods=['POST'])
@limiter.limit("60 per minute")
@require_api_token
def create_job():
    """Create a new job from a JSON body."""
    user = g.api_user
    data = request.get_json(silent=True)
    if not data:
        return _error('Request body must be valid JSON.')

    name = (data.get('name') or '').strip()
    schedule = (data.get('schedule') or '').strip()
    grace_period = data.get('grace_period', 15)
    notes = (data.get('notes') or '').strip()[:255]
    team_id = data.get('team_id')
    job_timezone = (data.get('timezone') or user.timezone or 'UTC').strip()

    notify_email = data.get('notify_email', True)
    notify_webhook = data.get('notify_webhook', False)
    webhook_url = (data.get('webhook_url') or '').strip()
    notify_slack = data.get('notify_slack', False)
    slack_webhook = (data.get('slack_webhook') or '').strip()
    depends_on = data.get('depends_on')

    # --- Plan-level feature enforcement ---
    if not is_feature_allowed(user.plan, 'allow_webhook'):
        notify_webhook = False
        webhook_url = ''
    if not is_feature_allowed(user.plan, 'allow_slack'):
        notify_slack = False
        slack_webhook = ''
    if not is_feature_allowed(user.plan, 'allow_dependencies'):
        depends_on = None

    # --- Job limit check (personal jobs only) ---
    if not team_id:
        job_limit = get_job_limit(user.plan)
        current_count = Job.query.filter_by(user_id=user.id, team_id=None).count()
        if job_limit is not None and current_count >= job_limit:
            return _error(f'You have reached the {user.plan.title()} plan limit of {job_limit} personal jobs.', 403)

    # --- Validation ---
    if not name or len(name) > 255:
        return _error('name is required and must be under 255 characters.')

    if not schedule or not croniter.is_valid(schedule):
        return _error('schedule must be a valid cron expression.')

    try:
        grace_period = int(grace_period)
    except (TypeError, ValueError):
        return _error('grace_period must be an integer.')
    if grace_period < 1 or grace_period > 1440:
        return _error('grace_period must be between 1 and 1440 minutes.')

    if team_id:
        team_ids = _get_user_team_ids(user)
        if team_id not in team_ids:
            return _error('Invalid team_id — you do not have access to that team.', 403)

    if depends_on:
        dep_job = db.session.get(Job, depends_on)
        if not dep_job or not _has_job_access(dep_job, user):
            return _error('Invalid depends_on — job not found or no access.')

    if notify_webhook and not webhook_url:
        return _error('webhook_url is required when notify_webhook is true.')
    if notify_webhook and webhook_url:
        url_err = validate_webhook_url(webhook_url)
        if url_err:
            return _error(url_err)

    if notify_slack and not slack_webhook:
        return _error('slack_webhook is required when notify_slack is true.')
    if notify_slack and slack_webhook:
        url_err = validate_webhook_url(slack_webhook)
        if url_err:
            return _error(url_err)

    # --- Create ---
    token = secrets.token_urlsafe(16)
    job = Job(
        user_id=user.id,
        team_id=team_id or None,
        name=name,
        schedule=schedule,
        grace_period=grace_period,
        timezone=job_timezone,
        notes=notes or None,
        notify_email=notify_email,
        notify_webhook=notify_webhook,
        webhook_url=webhook_url if notify_webhook else None,
        notify_slack=notify_slack,
        slack_webhook=slack_webhook if notify_slack else None,
        depends_on=depends_on or None,
        ping_token=token,
        expected_at=calculate_next_expected(schedule, job_timezone),
    )
    db.session.add(job)
    db.session.commit()

    return jsonify({'ok': True, 'data': _job_to_dict(job)}), 201


@bp.route('/jobs/<int:id>', methods=['GET'])
@limiter.limit("60 per minute")
@require_api_token
def get_job(id):
    """Get a single job with recent run history."""
    user = g.api_user
    job = db.session.get(Job, id)
    if not job or not _has_job_access(job, user):
        return _error('Job not found.', 404)

    history_days = get_history_days(user.plan)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=history_days)
    runs = (JobRun.query
            .filter(JobRun.job_id == job.id, JobRun.created_at >= cutoff)
            .order_by(JobRun.created_at.desc())
            .limit(100)
            .all())

    job_data = _job_to_dict(job)
    job_data['runs'] = [{
        'id': r.id,
        'status': r.status,
        'pinged_at': r.pinged_at.isoformat() if r.pinged_at else None,
        'expected_at': r.expected_at.isoformat() if r.expected_at else None,
        'duration_ms': r.duration_ms,
        'ip_address': r.ip_address,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    } for r in runs]

    return jsonify({'ok': True, 'data': job_data})


@bp.route('/jobs/<int:id>/history', methods=['GET'])
@limiter.limit("60 per minute")
@require_api_token
def job_history(id):
    """Paginated run history for a single job."""
    user = g.api_user
    job = db.session.get(Job, id)
    if not job or not _has_job_access(job, user):
        return _error('Job not found.', 404)

    history_days = get_history_days(user.plan)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=history_days)

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 25, type=int), 100)
    if per_page < 1:
        per_page = 25

    pagination = (JobRun.query
                  .filter(JobRun.job_id == job.id, JobRun.created_at >= cutoff)
                  .order_by(JobRun.created_at.desc())
                  .paginate(page=page, per_page=per_page, error_out=False))

    runs = [{
        'id': r.id,
        'status': r.status,
        'pinged_at': r.pinged_at.isoformat() if r.pinged_at else None,
        'expected_at': r.expected_at.isoformat() if r.expected_at else None,
        'duration_ms': r.duration_ms,
        'ip_address': r.ip_address,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    } for r in pagination.items]

    return jsonify({
        'ok': True,
        'data': runs,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
        }
    })

@bp.route('/jobs/<int:id>', methods=['PUT'])
@limiter.limit("60 per minute")
@require_api_token
def update_job(id):
    """Update a job. Supports partial updates — only supplied fields are changed."""
    user = g.api_user
    job = db.session.get(Job, id)
    if not job or not _has_job_access(job, user):
        return _error('Job not found.', 404)

    data = request.get_json(silent=True)
    if not data:
        return _error('Request body must be valid JSON.')

    # Name
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name or len(name) > 255:
            return _error('name is required and must be under 255 characters.')
        job.name = name

    # Schedule
    schedule_changed = False
    if 'schedule' in data:
        schedule = (data['schedule'] or '').strip()
        if not schedule or not croniter.is_valid(schedule):
            return _error('schedule must be a valid cron expression.')
        job.schedule = schedule
        schedule_changed = True

    # Grace period
    if 'grace_period' in data:
        try:
            gp = int(data['grace_period'])
        except (TypeError, ValueError):
            return _error('grace_period must be an integer.')
        if gp < 1 or gp > 1440:
            return _error('grace_period must be between 1 and 1440 minutes.')
        job.grace_period = gp

    # Timezone
    if 'timezone' in data:
        job.timezone = (data['timezone'] or 'UTC').strip()
        schedule_changed = True

    # Notes
    if 'notes' in data:
        job.notes = (data['notes'] or '').strip()[:255] or None

    # Team
    if 'team_id' in data:
        tid = data['team_id']
        if tid:
            team_ids = _get_user_team_ids(user)
            if tid not in team_ids:
                return _error('Invalid team_id — you do not have access to that team.', 403)
        job.team_id = tid or None

    # Notification channels (plan-gated)
    if 'notify_email' in data:
        job.notify_email = bool(data['notify_email'])

    if 'notify_webhook' in data or 'webhook_url' in data:
        nw = data.get('notify_webhook', job.notify_webhook)
        wu = (data.get('webhook_url') or '').strip() or job.webhook_url
        if not is_feature_allowed(user.plan, 'allow_webhook'):
            nw = False
            wu = None
        else:
            if nw and not wu:
                return _error('webhook_url is required when notify_webhook is true.')
            if nw and wu:
                url_err = validate_webhook_url(wu)
                if url_err:
                    return _error(url_err)
        job.notify_webhook = nw
        job.webhook_url = wu if nw else None

    if 'notify_slack' in data or 'slack_webhook' in data:
        ns = data.get('notify_slack', job.notify_slack)
        sw = (data.get('slack_webhook') or '').strip() or job.slack_webhook
        if not is_feature_allowed(user.plan, 'allow_slack'):
            ns = False
            sw = None
        else:
            if ns and not sw:
                return _error('slack_webhook is required when notify_slack is true.')
            if ns and sw:
                url_err = validate_webhook_url(sw)
                if url_err:
                    return _error(url_err)
        job.notify_slack = ns
        job.slack_webhook = sw if ns else None

    # Dependency
    if 'depends_on' in data:
        dep = data['depends_on']
        if not is_feature_allowed(user.plan, 'allow_dependencies'):
            dep = None
        elif dep:
            dep_job = db.session.get(Job, dep)
            if not dep_job or not _has_job_access(dep_job, user):
                return _error('Invalid depends_on — job not found or no access.')
        job.depends_on = dep or None

    # Recalculate expected_at if schedule or timezone changed
    if schedule_changed:
        job.expected_at = calculate_next_expected(job.schedule, job.timezone)

    db.session.commit()
    return jsonify({'ok': True, 'data': _job_to_dict(job)})


@bp.route('/jobs/<int:id>', methods=['DELETE'])
@limiter.limit("60 per minute")
@require_api_token
def delete_job(id):
    """Delete a job."""
    user = g.api_user
    job = db.session.get(Job, id)
    if not job or not _has_job_access(job, user):
        return _error('Job not found.', 404)

    db.session.delete(job)
    db.session.commit()
    return jsonify({'ok': True, 'data': {'id': id, 'deleted': True}})


@bp.route('/jobs/<int:id>/pause', methods=['POST'])
@limiter.limit("60 per minute")
@require_api_token
def pause_job(id):
    """Pause a job."""
    user = g.api_user
    job = db.session.get(Job, id)
    if not job or not _has_job_access(job, user):
        return _error('Job not found.', 404)

    if not job.is_active:
        return _error('Job is already paused.', 409)

    job.is_active = False
    db.session.commit()
    return jsonify({'ok': True, 'data': _job_to_dict(job)})


@bp.route('/jobs/<int:id>/resume', methods=['POST'])
@limiter.limit("60 per minute")
@require_api_token
def resume_job(id):
    """Resume a paused job. Checks plan job limit before resuming."""
    user = g.api_user
    job = db.session.get(Job, id)
    if not job or not _has_job_access(job, user):
        return _error('Job not found.', 404)

    if job.is_active:
        return _error('Job is already active.', 409)

    # Enforce job limit when resuming personal jobs
    if not job.team_id:
        job_limit = get_job_limit(user.plan)
        if job_limit is not None:
            active_count = Job.query.filter_by(user_id=user.id, team_id=None, is_active=True).count()
            if active_count >= job_limit:
                return _error(
                    f'Cannot resume — you have reached the {user.plan.title()} plan limit of '
                    f'{job_limit} active jobs.', 403
                )

    job.is_active = True
    job.expected_at = calculate_next_expected(job.schedule, job.timezone)
    job.last_status = 'ok'
    db.session.commit()
    return jsonify({'ok': True, 'data': _job_to_dict(job)})
