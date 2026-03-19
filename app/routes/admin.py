# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

import stripe
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort, session, current_app
from flask_login import current_user, login_user
from app.decorators import admin_required
from app.extensions import db
from app.models.user import User
from app.models.job import Job, JobRun, Alert
from datetime import datetime, timezone, timedelta
from sqlalchemy import func

bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/')
@admin_required
def dashboard():
    total_users = User.query.count()
    total_jobs = Job.query.count()
    active_jobs = Job.query.filter_by(is_active=True).count()
    failed_jobs = Job.query.filter_by(last_status='failed').count()
    late_jobs = Job.query.filter_by(last_status='late').count()

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    alerts_today = Alert.query.filter(Alert.created_at >= today_start).count()

    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()

    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_jobs=total_jobs,
                           active_jobs=active_jobs,
                           failed_jobs=failed_jobs,
                           late_jobs=late_jobs,
                           alerts_today=alerts_today,
                           recent_users=recent_users)


@bp.route('/users')
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('q', '').strip()
    plan_filter = request.args.get('plan', '').strip()

    query = User.query

    if search:
        like_term = f'%{search}%'
        query = query.filter(
            db.or_(
                User.email.ilike(like_term),
                User.username.ilike(like_term),
                User.display_name.ilike(like_term)
            )
        )

    if plan_filter in ('free', 'pro', 'team'):
        query = query.filter_by(plan=plan_filter)

    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get job counts per user in one query
    job_counts = dict(
        db.session.query(Job.user_id, func.count(Job.id))
        .group_by(Job.user_id)
        .all()
    )

    return render_template('admin/users.html',
                           users=pagination.items,
                           pagination=pagination,
                           pagination_endpoint='admin.users',
                           pagination_kwargs={'q': search, 'plan': plan_filter},
                           search=search,
                           plan_filter=plan_filter,
                           job_counts=job_counts)


@bp.route('/users/<int:id>')
@admin_required
def user_detail(id):
    user = User.query.get_or_404(id)

    page = request.args.get('page', 1, type=int)
    per_page = 20

    jobs_pagination = (Job.query.filter_by(user_id=user.id)
                       .order_by(Job.created_at.desc())
                       .paginate(page=page, per_page=per_page, error_out=False))

    job_ids = [j.id for j in jobs_pagination.items]
    recent_alerts = []
    if job_ids:
        recent_alerts = (Alert.query
                         .filter(Alert.job_id.in_(job_ids))
                         .order_by(Alert.created_at.desc())
                         .limit(20)
                         .all())

    # Plan dates
    plan_started = user.plan_started_at or user.created_at

    plan_ends = None
    if user.stripe_subscription_id and user.plan != 'free':
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        try:
            sub = stripe.Subscription.retrieve(user.stripe_subscription_id)
            plan_ends = datetime.fromtimestamp(sub['current_period_end'], tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            pass

    return render_template('admin/user_detail.html',
                           user=user,
                           jobs=jobs_pagination.items,
                           pagination=jobs_pagination,
                           pagination_endpoint='admin.user_detail',
                           pagination_kwargs={'id': user.id},
                           recent_alerts=recent_alerts,
                           plan_started=plan_started,
                           plan_ends=plan_ends)


@bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def user_edit(id):
    user = User.query.get_or_404(id)

    if request.method == 'POST':
        new_email = request.form.get('email', user.email).strip().lower()
        new_plan = request.form.get('plan', user.plan)

        # Validate email uniqueness
        if new_email != user.email:
            existing = User.query.filter_by(email=new_email).first()
            if existing:
                flash('That email is already in use by another account.', 'danger')
                return redirect(url_for('admin.user_edit', id=user.id))

        # Validate plan value
        if new_plan not in ('free', 'pro', 'team'):
            flash('Invalid plan selected.', 'danger')
            return redirect(url_for('admin.user_edit', id=user.id))

        user.email = new_email
        user.username = request.form.get('username', '').strip() or None
        user.display_name = request.form.get('display_name', '').strip() or None
        user.timezone = request.form.get('timezone', 'UTC').strip()
        user.plan = new_plan
        user.email_verified = 'email_verified' in request.form
        user.is_admin = 'is_admin' in request.form

        db.session.commit()
        flash(f'User {user.email} updated.', 'success')
        return redirect(url_for('admin.user_detail', id=user.id))

    return render_template('admin/user_edit.html', user=user)


@bp.route('/users/<int:id>/delete', methods=['POST'])
@admin_required
def user_delete(id):
    user = User.query.get_or_404(id)

    if user.id == current_user.id:
        flash('You cannot delete your own account from the admin panel.', 'danger')
        return redirect(url_for('admin.user_detail', id=user.id))

    email = user.email
    # Delete user's jobs (cascade handles runs/alerts)
    Job.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'User {email} and all associated data deleted.', 'info')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:id>/impersonate', methods=['POST'])
@admin_required
def impersonate(id):
    user = User.query.get_or_404(id)

    if user.id == current_user.id:
        flash('You are already logged in as yourself.', 'info')
        return redirect(url_for('admin.user_detail', id=user.id))

    session['admin_impersonating'] = current_user.id
    login_user(user)
    flash(f'Now viewing as {user.email}. Click "Return to Admin" when done.', 'info')
    return redirect(url_for('dashboard.index'))


@bp.route('/return', methods=['POST'])
def return_from_impersonation():
    admin_id = session.pop('admin_impersonating', None)
    if not admin_id:
        abort(403)

    admin_user = db.session.get(User, admin_id)
    if not admin_user or not admin_user.is_admin:
        abort(403)

    login_user(admin_user)
    flash('Returned to admin account.', 'info')
    return redirect(url_for('admin.dashboard'))
