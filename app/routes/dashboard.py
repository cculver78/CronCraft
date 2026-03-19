# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models.job import Job
from app.models.team import Team, TeamMember
from app.extensions import db
from app.routes.jobs import get_user_teams
from app.plan_limits import get_job_limit

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@bp.route('/')
@login_required
def index():
    user_teams = get_user_teams(current_user)
    team_ids = [t.id for t in user_teams]

    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Job.query.filter(
        db.or_(Job.user_id == current_user.id, Job.team_id.in_(team_ids))
    ).order_by(Job.name)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    job_limit = get_job_limit(current_user.plan)
    personal_jobs_count = Job.query.filter_by(user_id=current_user.id, team_id=None).count()
    
    # Free plan users can't create teams, limit applies strictly
    at_limit = job_limit is not None and personal_jobs_count >= job_limit and not current_user.plan in ('pro', 'team')

    return render_template('dashboard/index.html', jobs=pagination.items,
                           pagination=pagination,
                           pagination_endpoint='dashboard.index',
                           pagination_kwargs={},
                           job_count=pagination.total, job_limit=job_limit, 
                           personal_jobs_count=personal_jobs_count, at_limit=at_limit)
