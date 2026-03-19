# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Blueprint, request, jsonify
from app.models.job import Job, JobRun
from app.services.scheduler import calculate_next_expected, _cascade_dependency_failures
from app.extensions import db, limiter, csrf
from datetime import datetime, timezone

bp = Blueprint('ping', __name__)

# Exempt ping from CSRF (it's an API endpoint hit by external scripts)
csrf.exempt(bp)


def _parse_duration(args):
    """Extract duration_ms from query params.  Accepts `duration_ms` (int,
    milliseconds) or `duration` (float, seconds → converted to ms)."""
    raw = args.get('duration_ms')
    if raw is not None:
        try:
            return max(0, int(raw))
        except (ValueError, TypeError):
            pass

    raw = args.get('duration')
    if raw is not None:
        try:
            return max(0, int(float(raw) * 1000))
        except (ValueError, TypeError):
            pass

    return None


@bp.route('/ping/<token>', methods=['GET', 'POST'])
@limiter.limit("30 per minute")
def receive_ping(token):
    job = Job.query.filter_by(ping_token=token, is_active=True).first()

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    was_late = job.last_status == 'late'
    duration_ms = _parse_duration(request.args)

    # Record the run
    run = JobRun(
        job_id=job.id,
        status='ok',
        pinged_at=now,
        expected_at=job.expected_at,
        duration_ms=duration_ms,
        ip_address=request.remote_addr
    )
    db.session.add(run)

    # Update job state
    job.last_ping_at = now
    job.last_status = 'ok'
    job.miss_count = 0
    job.expected_at = calculate_next_expected(job.schedule, job.timezone)

    # If it was late and just recovered, send recovery alert
    if was_late:
        from app.services.alerting import send_alert
        send_alert(job, alert_type='recovered')

    db.session.commit()

    # Anomaly detection (Pro/Team only, after commit so the run is saved)
    _check_anomaly(job, duration_ms, now, run.expected_at)

    return jsonify({'status': 'ok', 'next_expected': job.expected_at.isoformat()})

@bp.route('/ping/<token>/fail', methods=['GET', 'POST'])
@limiter.limit("30 per minute")
def receive_ping_fail(token):
    job = Job.query.filter_by(ping_token=token, is_active=True).first()

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    duration_ms = _parse_duration(request.args)

    # Record the run as failed
    run = JobRun(
        job_id=job.id,
        status='failed',
        pinged_at=now,
        expected_at=job.expected_at,
        duration_ms=duration_ms,
        ip_address=request.remote_addr
    )
    db.session.add(run)

    # Update job state
    job.last_ping_at = now
    job.last_status = 'failed'
    job.miss_count = 0
    job.expected_at = calculate_next_expected(job.schedule, job.timezone)

    # Dispatch failure alert
    from app.services.alerting import send_alert
    send_alert(job, alert_type='failed')
    
    # Cascade failure downward
    _cascade_dependency_failures(job, now)

    db.session.commit()

    return jsonify({'status': 'failed', 'next_expected': job.expected_at.isoformat()})


def _check_anomaly(job, duration_ms, pinged_at, expected_at):
    """Run anomaly detection if the user's plan supports it."""
    from app.plan_limits import is_feature_allowed
    user_plan = job.user.plan if getattr(job, 'user', None) else 'free'
    if not is_feature_allowed(user_plan, 'allow_anomaly_detection'):
        return

    # Compute response latency (ms) as fallback metric
    latency_ms = None
    if pinged_at and expected_at:
        latency_ms = max(0, (pinged_at - expected_at).total_seconds() * 1000)

    from app.services.anomaly import check_duration_anomaly
    result = check_duration_anomaly(job, duration_ms, latency_ms)
    if result:
        from app.services.alerting import send_alert
        send_alert(job, alert_type='anomaly', anomaly_data=result)
