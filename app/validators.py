# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

import ipaddress
import re
from urllib.parse import urlparse


def validate_password(password):
    """Validate password complexity. Returns an error message string, or None if valid."""
    if len(password) < 8 or len(password) > 50:
        return 'Password must be between 8 and 50 characters.'
    if not re.search(r'[A-Z]', password):
        return 'Password must contain at least one uppercase letter.'
    if not re.search(r'[a-z]', password):
        return 'Password must contain at least one lowercase letter.'
    if not re.search(r'[0-9]', password):
        return 'Password must contain at least one number.'
    if not re.search(r'[^A-Za-z0-9]', password):
        return 'Password must contain at least one special character.'
    return None


def validate_webhook_url(url):
    """Validate that a webhook URL is safe to POST to. Returns an error message string, or None if valid."""
    try:
        parsed = urlparse(url)
    except Exception:
        return 'Invalid URL format.'

    if parsed.scheme not in ('http', 'https'):
        return 'Webhook URL must use http:// or https://.'

    hostname = parsed.hostname
    if not hostname:
        return 'Webhook URL must include a hostname.'

    # Block obviously dangerous targets
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return 'Webhook URL must not target a private or internal address.'
    except ValueError:
        # hostname is not an IP literal — check for localhost aliases
        if hostname.lower() in ('localhost', 'localhost.localdomain'):
            return 'Webhook URL must not target localhost.'

    return None
