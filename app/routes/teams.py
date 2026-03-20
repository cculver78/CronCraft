# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.team import Team, TeamMember
from app.models.user import User

bp = Blueprint('teams', __name__, url_prefix='/dashboard/teams')


def _is_team_admin(team, user_id):
    """Return True if the user owns the team or has an 'admin' membership role."""
    if team.owner_id == user_id:
        return True
    member = TeamMember.query.filter_by(team_id=team.id, user_id=user_id).first()
    return member is not None and member.role == 'admin'

@bp.route('/')
@login_required
def index():
    # Teams the user owns
    owned_teams = Team.query.filter_by(owner_id=current_user.id).all()
    
    # Teams the user is a member of
    member_teams = Team.query.join(TeamMember).filter(
        TeamMember.user_id == current_user.id,
        Team.owner_id != current_user.id # exclude owned teams to prevent duplicates if they are also a member
    ).all()
    
    return render_template('teams/index.html', owned_teams=owned_teams, member_teams=member_teams)

@bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    from app.plan_limits import is_self_hosted
    if not is_self_hosted() and current_user.plan not in ('pro', 'team'):
         flash('Team creation requires a Pro or Team plan.', 'danger')
         return redirect(url_for('subscription.index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name or len(name) > 255:
            flash('Team name is required and must be under 255 characters.', 'danger')
            return redirect(url_for('teams.create'))
            
        team = Team(name=name, owner_id=current_user.id)
        db.session.add(team)
        db.session.commit()
        
        # Add the owner as an admin member of the team
        owner_member = TeamMember(team_id=team.id, user_id=current_user.id, role='admin')
        db.session.add(owner_member)
        db.session.commit()
        
        flash('Team created successfully.', 'success')
        return redirect(url_for('teams.detail', id=team.id))
        
    return render_template('teams/create.html')

@bp.route('/<int:id>')
@login_required
def detail(id):
    team = Team.query.get_or_404(id)

    # Any team member (or owner) can view
    member_record = TeamMember.query.filter_by(team_id=team.id, user_id=current_user.id).first()
    if team.owner_id != current_user.id and not member_record:
        abort(403)

    is_admin = _is_team_admin(team, current_user.id)
    members = TeamMember.query.filter_by(team_id=team.id).all()

    return render_template('teams/detail.html', team=team, members=members, is_admin=is_admin, current_user_id=current_user.id)

@bp.route('/<int:id>/members/add', methods=['POST'])
@login_required
def add_member(id):
    team = Team.query.get_or_404(id)
    if not _is_team_admin(team, current_user.id):
        abort(403)
        
    identifier = request.form.get('identifier', '').strip()
    role = request.form.get('role', 'member').strip()
    
    if role not in ('admin', 'member'):
        role = 'member'
        
    if not identifier:
        flash('Email or username is required.', 'danger')
        return redirect(url_for('teams.detail', id=team.id))
        
    # Find user by email or username
    user_to_add = User.query.filter((User.email == identifier) | (User.username == identifier)).first()
    
    if not user_to_add:
        flash('User not found.', 'danger')
        return redirect(url_for('teams.detail', id=team.id))
        
    # Check if already a member
    existing_member = TeamMember.query.filter_by(team_id=team.id, user_id=user_to_add.id).first()
    if existing_member:
        flash('User is already a member of this team.', 'warning')
        return redirect(url_for('teams.detail', id=team.id))
        
    new_member = TeamMember(team_id=team.id, user_id=user_to_add.id, role=role)
    db.session.add(new_member)
    db.session.commit()
    
    flash(f'{user_to_add.email} added to the team.', 'success')
    return redirect(url_for('teams.detail', id=team.id))

@bp.route('/<int:team_id>/members/<int:member_id>/role', methods=['POST'])
@login_required
def change_role(team_id, member_id):
    team = Team.query.get_or_404(team_id)
    if not _is_team_admin(team, current_user.id):
        abort(403)
        
    target_member = TeamMember.query.filter_by(id=member_id, team_id=team.id).first_or_404()
    
    # Prevent changing the owner's role
    if target_member.user_id == team.owner_id:
        flash("Cannot change the owner's role.", 'danger')
        return redirect(url_for('teams.detail', id=team.id))
        
    new_role = request.form.get('role')
    if new_role in ('admin', 'member'):
        target_member.role = new_role
        db.session.commit()
        flash('Role updated.', 'success')
    else:
        flash('Invalid role.', 'danger')
        
    return redirect(url_for('teams.detail', id=team.id))

@bp.route('/<int:team_id>/members/<int:member_id>/remove', methods=['POST'])
@login_required
def remove_member(team_id, member_id):
    team = Team.query.get_or_404(team_id)
    target_member = TeamMember.query.filter_by(id=member_id, team_id=team.id).first_or_404()

    # Allow team admins/owners, or the member removing themselves
    is_admin = _is_team_admin(team, current_user.id)
    is_self = target_member.user_id == current_user.id
    if not is_admin and not is_self:
        abort(403)
        
    # Prevent removing the owner
    if target_member.user_id == team.owner_id:
        flash("Cannot remove the team owner.", 'danger')
        return redirect(url_for('teams.detail', id=team.id))
        
    db.session.delete(target_member)
    db.session.commit()
    
    flash('Member removed.', 'success')
    
    if is_self:
        return redirect(url_for('teams.index'))
    return redirect(url_for('teams.detail', id=team.id))

@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    team = Team.query.get_or_404(id)
    
    # Only owner can delete team
    if team.owner_id != current_user.id:
        abort(403)
        
    # Delete team members first
    TeamMember.query.filter_by(team_id=team.id).delete()
    
    db.session.delete(team)
    db.session.commit()
    
    flash('Team deleted.', 'success')
    return redirect(url_for('teams.index'))
