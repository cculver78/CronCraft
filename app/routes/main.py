# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Blueprint, render_template, redirect, url_for, jsonify, send_from_directory, current_app
from flask_login import current_user
from app.extensions import csrf
import os

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    from app.plan_limits import is_self_hosted
    if is_self_hosted():
        return redirect(url_for('auth.login'))

    return render_template('index.html')

@bp.route('/health')
@csrf.exempt
def health():
    return jsonify({'status': 'ok'}), 200

@bp.route('/sitemap.xml')
def sitemap():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'sitemap.xml', mimetype='application/xml')

@bp.route('/robots.txt')
def robots():
    return send_from_directory(os.path.join(current_app.root_path, 'static'), 'robots.txt', mimetype='text/plain')
