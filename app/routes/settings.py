# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.user import User
from app.validators import validate_password

bp = Blueprint('settings', __name__, url_prefix='/settings')

@bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        display_name = request.form.get('display_name', '').strip()
        timezone = request.form.get('timezone', 'UTC').strip()
        
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')

        date_format = request.form.get('date_format', 'YYYY-MM-DD').strip()
        time_format = request.form.get('time_format', '24h').strip()

        # --- Validate everything before making any changes ---
        has_error = False
        new_password_hash = None

        # Email validation
        if email != current_user.email:
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('That email is already in use.', 'danger')
                has_error = True

        # Username validation
        if username and username != current_user.username:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('That username is already in use.', 'danger')
                has_error = True

        # Password validation
        if current_password or new_password:
            if not current_password:
                flash('You must provide your current password to set a new password.', 'danger')
                has_error = True
            elif not check_password_hash(current_user.password_hash, current_password):
                flash('Incorrect current password.', 'danger')
                has_error = True
            else:
                pw_error = validate_password(new_password)
                if pw_error:
                    flash(pw_error, 'danger')
                    has_error = True
                else:
                    new_password_hash = generate_password_hash(new_password, method='scrypt')

        if has_error:
            return render_template('settings/index.html')

        # --- All validation passed — apply changes ---
        current_user.email = email
        current_user.username = username if username else None
        current_user.display_name = display_name if display_name else None
        current_user.timezone = timezone

        if date_format in ('YYYY-MM-DD', 'MM/DD/YYYY', 'DD/MM/YYYY'):
            current_user.date_format = date_format
        if time_format in ('24h', '12h'):
            current_user.time_format = time_format

        # Admin-only: version check preference
        if current_user.is_admin:
            current_user.version_check_enabled = bool(request.form.get('version_check_enabled'))

        if new_password_hash:
            current_user.password_hash = new_password_hash
            flash('Password updated successfully.', 'success')

        db.session.commit()
        flash('Settings updated successfully.', 'success')
        return redirect(url_for('settings.index'))
            
    return render_template('settings/index.html')


@bp.route('/api-token/generate', methods=['POST'])
@login_required
def generate_api_token():
    """Generate a new API token (overwrites any existing token)."""
    import hashlib
    import secrets as _secrets
    from app.plan_limits import is_feature_allowed

    if not is_feature_allowed(current_user.plan, 'allow_api'):
        flash('API access requires a Pro or Team plan.', 'danger')
        return redirect(url_for('settings.index'))

    raw_token = _secrets.token_urlsafe(32)
    current_user.api_token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    db.session.commit()

    flash(f'Your new API token (copy it now — it will not be shown again): {raw_token}', 'success')
    return redirect(url_for('settings.index'))


@bp.route('/api-token/revoke', methods=['POST'])
@login_required
def revoke_api_token():
    """Revoke the current API token."""
    current_user.api_token_hash = None
    db.session.commit()
    flash('API token revoked.', 'info')
    return redirect(url_for('settings.index'))
