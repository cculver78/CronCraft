# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from app.models.job import Job, JobRun
from app.models.team import Team, TeamMember
from sqlalchemy import or_
from app.extensions import db
from app.services.scheduler import calculate_next_expected
from app.plan_limits import get_job_limit, get_history_days, is_feature_allowed
from app.validators import validate_webhook_url
from croniter import croniter
from datetime import datetime, timezone, timedelta
import secrets

bp = Blueprint('jobs', __name__, url_prefix='/dashboard/jobs')

def has_job_access(job, user, require_admin=False):
    if job.user_id == user.id:
        return True
    if job.team_id:
        team = db.session.get(Team, job.team_id)
        if team and team.owner_id == user.id:
            return True
        member = TeamMember.query.filter_by(team_id=job.team_id, user_id=user.id).first()
        if member:
            if require_admin:
                return member.role == 'admin'
            return True
    return False

def get_user_teams(user):
    owned = Team.query.filter_by(owner_id=user.id).all()
    member = Team.query.join(TeamMember).filter(TeamMember.user_id == user.id, Team.owner_id != user.id).all()
    return owned + member



@bp.route('/<int:id>')
@login_required
def detail(id):
    job = Job.query.get_or_404(id)
    if not has_job_access(job, current_user):
        abort(403)

    history_days = get_history_days(current_user.plan)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=history_days)

    page = request.args.get('page', 1, type=int)
    per_page = 25

    pagination = (JobRun.query
            .filter(JobRun.job_id == job.id, JobRun.created_at >= cutoff)
            .order_by(JobRun.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False))

    return render_template('jobs/detail.html', job=job, runs=pagination.items,
                           pagination=pagination,
                           pagination_endpoint='jobs.detail',
                           pagination_kwargs={'id': job.id},
                           history_days=history_days)


@bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    # Enforce plan-level job limit (only applies to personal jobs currently)
    # Team creation requires pro/team, and they have unlimited jobs, so we only restrict personal jobs for free
    job_limit = get_job_limit(current_user.plan)
    current_count = Job.query.filter_by(user_id=current_user.id, team_id=None).count()
    if job_limit is not None and current_count >= job_limit:
        flash(f'You have reached the {current_user.plan.title()} plan limit of {job_limit} personal jobs. '
              'Please upgrade your plan to add more.', 'danger')
        return redirect(url_for('dashboard.index'))

    user_teams = get_user_teams(current_user)
    team_ids = [t.id for t in user_teams]
    available_jobs = Job.query.filter(
        db.or_(Job.user_id == current_user.id, Job.team_id.in_(team_ids))
    ).order_by(Job.name).all()
    
    team_id_param = request.args.get('team_id', type=int)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        schedule = request.form.get('schedule', '').strip()
        grace_period = request.form.get('grace_period', type=int)
        notes = request.form.get('notes', '').strip()[:255]
        team_id = request.form.get('team_id', type=int)
        job_timezone = request.form.get('timezone', current_user.timezone).strip()
        
        notify_email = request.form.get('notify_email') == 'on'
        notify_webhook = request.form.get('notify_webhook') == 'on'
        webhook_url = request.form.get('webhook_url', '').strip()
        notify_slack = request.form.get('notify_slack') == 'on'
        slack_webhook = request.form.get('slack_webhook', '').strip()
        notify_duration_anomaly = request.form.get('notify_duration_anomaly') == 'on'
        depends_on = request.form.get('depends_on', type=int)

        # Enforce plan-level feature restrictions
        if not is_feature_allowed(current_user.plan, 'allow_webhook'):
            notify_webhook = False
            webhook_url = ''
        if not is_feature_allowed(current_user.plan, 'allow_slack'):
            notify_slack = False
            slack_webhook = ''
        if not is_feature_allowed(current_user.plan, 'allow_dependencies'):
            depends_on = None

        # Validate team_id
        if team_id:
            if not any(t.id == team_id for t in user_teams):
                flash('Invalid team selected.', 'danger')
                return redirect(url_for('jobs.create'))
        
        # Input validation
        if depends_on:
            if not any(j.id == depends_on for j in available_jobs):
                flash('Invalid dependency selected.', 'danger')
                return redirect(url_for('jobs.create'))
                
        if not name or len(name) > 255:
            flash('Job name is required and must be under 255 characters.', 'danger')
            return redirect(url_for('jobs.create'))
        
        if not schedule or not croniter.is_valid(schedule):
            flash('A valid cron expression is required.', 'danger')
            return redirect(url_for('jobs.create'))

        if grace_period is None or grace_period < 1 or grace_period > 1440:
            flash('Grace period must be between 1 and 1440 minutes.', 'danger')
            return redirect(url_for('jobs.create'))
            
        if notify_webhook and not webhook_url:
            flash('Webhook URL is required when webhook notifications are enabled.', 'danger')
            return redirect(url_for('jobs.create'))

        if notify_webhook and webhook_url:
            url_error = validate_webhook_url(webhook_url)
            if url_error:
                flash(url_error, 'danger')
                return redirect(url_for('jobs.create'))
            
        if notify_slack and not slack_webhook:
            flash('Slack Webhook URL is required when Slack notifications are enabled.', 'danger')
            return redirect(url_for('jobs.create'))

        if notify_slack and slack_webhook:
            url_error = validate_webhook_url(slack_webhook)
            if url_error:
                flash(url_error, 'danger')
                return redirect(url_for('jobs.create'))
        
        token = secrets.token_urlsafe(16)
        
        job = Job(
            user_id=current_user.id,
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
            notify_duration_anomaly=notify_duration_anomaly,
            depends_on=depends_on or None,
            ping_token=token,
            expected_at=calculate_next_expected(schedule, job_timezone)
        )
        db.session.add(job)
        db.session.commit()
        
        flash('Job created successfully!', 'info')
        return redirect(url_for('dashboard.index'))
        
    plan_limits = {
        'allow_webhook': is_feature_allowed(current_user.plan, 'allow_webhook'),
        'allow_slack': is_feature_allowed(current_user.plan, 'allow_slack'),
        'allow_dependencies': is_feature_allowed(current_user.plan, 'allow_dependencies'),
        'allow_anomaly_detection': is_feature_allowed(current_user.plan, 'allow_anomaly_detection'),
    }
    return render_template('jobs/create.html', user_teams=user_teams, available_jobs=available_jobs, default_team_id=team_id_param, plan_limits=plan_limits)

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    job = Job.query.get_or_404(id)
    if not has_job_access(job, current_user):
        abort(403)
        
    user_teams = get_user_teams(current_user)
    team_ids = [t.id for t in user_teams]
    available_jobs = Job.query.filter(
        db.or_(Job.user_id == current_user.id, Job.team_id.in_(team_ids)),
        Job.id != job.id
    ).order_by(Job.name).all()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        schedule = request.form.get('schedule', '').strip()
        grace_period = request.form.get('grace_period', type=int)
        notes = request.form.get('notes', '').strip()[:255]
        team_id = request.form.get('team_id', type=int)
        job_timezone = request.form.get('timezone', job.timezone).strip()
        
        notify_email = request.form.get('notify_email') == 'on'
        notify_webhook = request.form.get('notify_webhook') == 'on'
        webhook_url = request.form.get('webhook_url', '').strip()
        notify_slack = request.form.get('notify_slack') == 'on'
        slack_webhook = request.form.get('slack_webhook', '').strip()
        notify_duration_anomaly = request.form.get('notify_duration_anomaly') == 'on'
        depends_on = request.form.get('depends_on', type=int)

        # Enforce plan-level feature restrictions
        if not is_feature_allowed(current_user.plan, 'allow_webhook'):
            notify_webhook = False
            webhook_url = ''
        if not is_feature_allowed(current_user.plan, 'allow_slack'):
            notify_slack = False
            slack_webhook = ''
        if not is_feature_allowed(current_user.plan, 'allow_dependencies'):
            depends_on = None

        if team_id:
            if not any(t.id == team_id for t in user_teams):
                flash('Invalid team selected.', 'danger')
                return redirect(url_for('jobs.edit', id=id))

        if depends_on:
            if not any(j.id == depends_on for j in available_jobs):
                flash('Invalid dependency selected.', 'danger')
                return redirect(url_for('jobs.edit', id=id))
                
        if not name or len(name) > 255:
            flash('Job name is required and must be under 255 characters.', 'danger')
            return redirect(url_for('jobs.edit', id=id))

        if not schedule or not croniter.is_valid(schedule):
            flash('A valid cron expression is required.', 'danger')
            return redirect(url_for('jobs.edit', id=id))

        if grace_period is None or grace_period < 1 or grace_period > 1440:
            flash('Grace period must be between 1 and 1440 minutes.', 'danger')
            return redirect(url_for('jobs.edit', id=id))
            
        if notify_webhook and not webhook_url:
            flash('Webhook URL is required when webhook notifications are enabled.', 'danger')
            return redirect(url_for('jobs.edit', id=id))

        if notify_webhook and webhook_url:
            url_error = validate_webhook_url(webhook_url)
            if url_error:
                flash(url_error, 'danger')
                return redirect(url_for('jobs.edit', id=id))

        if notify_slack and not slack_webhook:
            flash('Slack Webhook URL is required when Slack notifications are enabled.', 'danger')
            return redirect(url_for('jobs.edit', id=id))

        if notify_slack and slack_webhook:
            url_error = validate_webhook_url(slack_webhook)
            if url_error:
                flash(url_error, 'danger')
                return redirect(url_for('jobs.edit', id=id))

        job.name = name
        job.schedule = schedule
        job.grace_period = grace_period
        job.timezone = job_timezone
        job.notes = notes or None
        job.team_id = team_id or None
        job.notify_email = notify_email
        job.notify_webhook = notify_webhook
        job.webhook_url = webhook_url if notify_webhook else None
        job.notify_slack = notify_slack
        job.slack_webhook = slack_webhook if notify_slack else None
        job.notify_duration_anomaly = notify_duration_anomaly
        job.depends_on = depends_on or None
        job.expected_at = calculate_next_expected(schedule, job_timezone)
        db.session.commit()
        flash('Job updated successfully', 'success')
        return redirect(url_for('dashboard.index'))
        
    plan_limits = {
        'allow_webhook': is_feature_allowed(current_user.plan, 'allow_webhook'),
        'allow_slack': is_feature_allowed(current_user.plan, 'allow_slack'),
        'allow_dependencies': is_feature_allowed(current_user.plan, 'allow_dependencies'),
        'allow_anomaly_detection': is_feature_allowed(current_user.plan, 'allow_anomaly_detection'),
    }
    return render_template('jobs/edit.html', job=job, user_teams=user_teams, available_jobs=available_jobs, plan_limits=plan_limits)

@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    job = Job.query.get_or_404(id)
    if not has_job_access(job, current_user, require_admin=True):
        abort(403)

    db.session.delete(job)
    db.session.commit()
    flash('Job deleted', 'info')
    return redirect(url_for('dashboard.index'))

@bp.route('/<int:id>/toggle-pause', methods=['POST'])
@login_required
def toggle_pause(id):
    job = Job.query.get_or_404(id)
    if not has_job_access(job, current_user):
        abort(403)

    # When un-pausing, check that the user hasn't hit their job limit
    if not job.is_active:
        job_limit = get_job_limit(current_user.plan)
        if job_limit is not None and not job.team_id:
            active_count = Job.query.filter_by(user_id=current_user.id, team_id=None, is_active=True).count()
            if active_count >= job_limit:
                flash(f'Cannot resume — you have reached the {current_user.plan.title()} plan limit of {job_limit} active jobs. '
                      'Please upgrade your plan or pause another job first.', 'danger')
                return redirect(url_for('dashboard.index'))

    job.is_active = not job.is_active

    # When un-pausing, recalculate expected_at so the job has a fresh deadline
    if job.is_active:
        job.expected_at = calculate_next_expected(job.schedule, job.timezone)
        job.last_status = 'ok'

    db.session.commit()
    flash(f'Job {"resumed" if job.is_active else "paused"}', 'info')
    return redirect(url_for('dashboard.index'))
