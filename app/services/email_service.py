# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import current_app, render_template
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from app.extensions import mail


def send_email(subject, recipients, text_body, html_body=None):
    """Send an email via Flask-Mail."""
    msg = Message(subject, recipients=recipients)
    msg.body = text_body
    if html_body:
        msg.html = html_body
    mail.send(msg)


def generate_token(email, salt='email-confirm'):
    """Create a time-limited token encoding the given email address."""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=salt)


def verify_token(token, salt='email-confirm', max_age=3600):
    """Validate a token and return the encoded email, or None if invalid/expired."""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt=salt, max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None
    return email
