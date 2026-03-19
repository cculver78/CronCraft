# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

"""
Plan-level limits for CronCraft tiers.

Each plan maps to a dict of resource caps.
A value of None means unlimited.

Self-hosted mode: when STRIPE_SECRET_KEY is not configured, all users
are treated as Team tier with everything unlocked.  Call
init_self_hosted() during app startup to activate.
"""

_self_hosted = False


def init_self_hosted(flag):
    """Set self-hosted mode based on the SELF_HOSTED config flag."""
    global _self_hosted
    _self_hosted = flag


def is_self_hosted():
    """Return True if the app is running in self-hosted (no-Stripe) mode."""
    return _self_hosted


PLAN_LIMITS = {
    'free': {
        'max_jobs': 10,
        'history_days': 7,
        'allow_webhook': False,
        'allow_slack': False,
        'allow_dependencies': False,
        'allow_api': False,
        'allow_anomaly_detection': False,
    },
    'pro': {
        'max_jobs': None,  # unlimited
        'history_days': 90,
        'allow_webhook': True,
        'allow_slack': True,
        'allow_dependencies': True,
        'allow_api': True,
        'allow_anomaly_detection': True,
    },
    'team': {
        'max_jobs': None,  # unlimited
        'history_days': 365,
        'allow_webhook': True,
        'allow_slack': True,
        'allow_dependencies': True,
        'allow_api': True,
        'allow_anomaly_detection': True,
    },
}


def get_plan_limits(plan):
    """Return the limits dict for a given plan name."""
    if _self_hosted:
        return PLAN_LIMITS['team']
    return PLAN_LIMITS.get(plan, PLAN_LIMITS['free'])


def get_job_limit(plan):
    """Return the max_jobs cap for the given plan, or None if unlimited."""
    return get_plan_limits(plan)['max_jobs']


def get_history_days(plan):
    """Return the history_days retention window for the given plan."""
    return get_plan_limits(plan)['history_days']


def is_feature_allowed(plan, feature):
    """Check if a feature (allow_webhook, allow_slack, allow_dependencies) is enabled for the plan."""
    return get_plan_limits(plan).get(feature, False)

