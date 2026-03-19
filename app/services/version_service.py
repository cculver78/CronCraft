# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

import os
import requests
from flask import current_app

GITHUB_RAW_URL = 'https://raw.githubusercontent.com/cculver78/croncraft/main/VERSION'
VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'VERSION')


def get_local_version():
    """Read the local VERSION file and return the version string."""
    try:
        with open(VERSION_FILE, 'r') as f:
            return f.read().strip()
    except Exception:
        return None


def get_remote_version():
    """Fetch the latest VERSION from GitHub. Returns None on any failure."""
    try:
        resp = requests.get(GITHUB_RAW_URL, timeout=3)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        current_app.logger.debug('Version check: failed to reach GitHub')
    return None


def is_update_available():
    """Compare local and remote versions.

    Returns (update_available, local_version, remote_version).
    On any failure, returns (False, local_version, None).
    """
    local = get_local_version()
    remote = get_remote_version()
    if local and remote and remote > local:
        return True, local, remote
    return False, local, remote
