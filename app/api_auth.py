# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

"""
API token authentication decorator.

Reads ``Authorization: Bearer <token>`` from the request, hashes it with
SHA-256, and looks up the user by ``api_token_hash``.  Also enforces the
``allow_api`` plan gate so free-tier tokens (if any somehow exist) are
rejected.
"""

import hashlib
from functools import wraps

from flask import request, jsonify, g
from app.models.user import User
from app.plan_limits import is_feature_allowed


def require_api_token(f):
    """Decorator that authenticates via Bearer token and enforces plan gating."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'ok': False, 'error': 'Missing or malformed Authorization header. Use: Bearer <token>'}), 401

        raw_token = auth_header[7:]  # strip "Bearer "
        if not raw_token:
            return jsonify({'ok': False, 'error': 'Empty token.'}), 401

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        user = User.query.filter_by(api_token_hash=token_hash).first()

        if not user:
            return jsonify({'ok': False, 'error': 'Invalid API token.'}), 401

        if not is_feature_allowed(user.plan, 'allow_api'):
            return jsonify({'ok': False, 'error': 'API access requires a Pro or Team plan.'}), 403

        g.api_user = user
        return f(*args, **kwargs)
    return decorated
