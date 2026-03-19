# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from datetime import datetime, timezone, timedelta
from croniter import croniter
from app.models.job import Job, JobRun
from app.models.user import User
from app.plan_limits import get_history_days
from app.extensions import db
import pytz

def calculate_next_expected(schedule_expr, tz='UTC'):
    now_utc = datetime.now(timezone.utc)
    local_tz = pytz.timezone(tz)
    now_local = now_utc.astimezone(local_tz).replace(tzinfo=None)
    if croniter.is_valid(schedule_expr):
        iterator = croniter(schedule_expr, now_local)
        next_local = iterator.get_next(datetime)
        # If the next occurrence is less than 60 seconds away, skip it.
        # This handles clock drift where a cron job pings slightly early
        # (e.g. 11:59:54 for a noon schedule) — without this, the imminent
        # window would be set as expected_at and immediately marked late.
        if (next_local - now_local).total_seconds() < 60:
            next_local = iterator.get_next(datetime)
        # Convert back to naive UTC for storage
        next_aware = local_tz.localize(next_local)
        return next_aware.astimezone(pytz.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)

def check_missed_pings():
    # Note: query needs app context when run by APScheduler
    # It will be provided by the worker process.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    overdue_jobs = Job.query.filter(
        Job.is_active == True,
        Job.expected_at < now,
        Job.last_status.in_(['ok', 'never_run', 'late'])
    ).all()

    for job in overdue_jobs:
        grace_cutoff = job.expected_at + timedelta(minutes=job.grace_period)

        if now > grace_cutoff:
            was_already_late = job.last_status == 'late'
            
            # Increment miss counter
            if was_already_late:
                job.miss_count += 1
            else:
                job.last_status = 'late'
                job.miss_count = 1
                
            # Escalate to failed if miss count >= 3
            if job.miss_count >= 3:
                job.last_status = 'failed'
                new_status = 'failed'
            else:
                new_status = 'late'

            run = JobRun(
                job_id=job.id,
                status=new_status,
                expected_at=job.expected_at
            )
            db.session.add(run)

            # Advance expected_at so the field stays current
            job.expected_at = calculate_next_expected(job.schedule, job.timezone)

            # Send appropriate alert
            from app.services.alerting import send_alert
            if new_status == 'failed':
                send_alert(job, alert_type='failed')
                _cascade_dependency_failures(job, now)
            elif not was_already_late:
                send_alert(job, alert_type='missed')

    db.session.commit()

def _cascade_dependency_failures(parent_job, now_time):
    """
    Recursively find all jobs that depend on `parent_job` and force 
    them into a 'failed' state, dispatching a dependency alert.
    Only cascades if the parent job's owner has dependency feature enabled.
    """
    from app.plan_limits import is_feature_allowed
    user_plan = parent_job.user.plan if getattr(parent_job, 'user', None) else 'free'
    if not is_feature_allowed(user_plan, 'allow_dependencies'):
        return  # Free-tier users' jobs don't cascade failures

    children = Job.query.filter_by(depends_on=parent_job.id, is_active=True).all()
    from app.services.alerting import send_alert
    
    for child in children:
        # Only cascade if the child isn't already failed
        if child.last_status != 'failed':
            child.last_status = 'failed'
            child.miss_count = 0
            
            run = JobRun(
                job_id=child.id,
                status='failed',
                expected_at=child.expected_at
            )
            db.session.add(run)
            
            child.expected_at = calculate_next_expected(child.schedule, child.timezone)
            send_alert(child, alert_type='dependency_failed')
            
            # Recurse downward
            _cascade_dependency_failures(child, now_time)

def purge_old_runs():
    """Delete JobRun records older than each user's plan retention window."""
    users = User.query.all()

    for user in users:
        history_days = get_history_days(user.plan)
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=history_days)

        job_ids = [j.id for j in Job.query.filter_by(user_id=user.id).all()]
        if not job_ids:
            continue

        JobRun.query.filter(
            JobRun.job_id.in_(job_ids),
            JobRun.created_at < cutoff
        ).delete(synchronize_session=False)

    db.session.commit()


def check_grace_period_expirations():
    """Downgrade users whose grace period has expired and pause excess jobs."""
    from app.plan_limits import get_job_limit
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    expired_users = User.query.filter(
        User.grace_period_end.isnot(None),
        User.grace_period_end < now,
        User.plan != 'free'
    ).all()

    for user in expired_users:
        user.plan = 'free'
        user.stripe_subscription_id = None
        user.grace_period_end = None

        # Pause excess jobs beyond the free limit
        max_jobs = get_job_limit('free')  # 10
        if max_jobs is not None:
            active_jobs = Job.query.filter_by(
                user_id=user.id, team_id=None, is_active=True
            ).order_by(Job.created_at.desc()).all()

            if len(active_jobs) > max_jobs:
                for job in active_jobs[max_jobs:]:
                    job.is_active = False

    db.session.commit()

