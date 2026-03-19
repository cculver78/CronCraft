# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

"""
Anomaly detection for job run durations.

Computes rolling stats (mean + stddev) over the last 30 runs and flags
anything beyond 2.5 standard deviations.  Works with two metrics:

1. User-sent duration_ms (preferred, most accurate)
2. Response latency = pinged_at - expected_at (automatic fallback)

Requires >= 5 data points before checks activate.
Max one anomaly alert per job per 24 hours.
"""

import statistics
from datetime import datetime, timezone, timedelta
from sqlalchemy import desc
from app.models.job import JobRun, Alert

ANOMALY_THRESHOLD = 2.5   # standard deviations
MIN_SAMPLE_SIZE = 5
LOOKBACK_RUNS = 30
COOLDOWN_HOURS = 24


def check_duration_anomaly(job, current_duration_ms=None, current_latency_ms=None):
    """
    Check if the current run's timing is anomalous compared to the last 30 runs.

    Returns a dict with anomaly stats if anomalous, or None if normal / not
    enough data / on cooldown.
    """
    # Decide which metric to use: prefer duration_ms if available
    metric, metric_label, current_value = _pick_metric(
        job.id, current_duration_ms, current_latency_ms
    )
    if current_value is None:
        return None

    # Gather historical values for the chosen metric
    history = _get_history(job.id, metric)
    if len(history) < MIN_SAMPLE_SIZE:
        return None

    mean = statistics.mean(history)
    stdev = statistics.stdev(history)

    if stdev == 0:
        return None  # all values identical, no meaningful deviation

    z_score = (current_value - mean) / stdev

    if abs(z_score) < ANOMALY_THRESHOLD:
        return None  # within normal range

    # Check cooldown: no duplicate anomaly alert within 24 hours
    if _on_cooldown(job.id):
        return None

    return {
        'metric': metric_label,
        'current': current_value,
        'mean': round(mean, 1),
        'stdev': round(stdev, 1),
        'z_score': round(z_score, 2),
    }


def _pick_metric(job_id, current_duration_ms, current_latency_ms):
    """
    Choose between duration_ms and latency.  Use duration_ms if the current
    run has it AND there are enough historical runs with it.  Otherwise
    fall back to response latency.
    """
    if current_duration_ms is not None:
        count = JobRun.query.filter(
            JobRun.job_id == job_id,
            JobRun.duration_ms.isnot(None)
        ).count()
        if count >= MIN_SAMPLE_SIZE:
            return 'duration_ms', 'duration', current_duration_ms

    # Fall back to latency
    if current_latency_ms is not None:
        return 'latency', 'response latency', current_latency_ms

    return None, None, None


def _get_history(job_id, metric):
    """Return the last LOOKBACK_RUNS values for the chosen metric."""
    if metric == 'duration_ms':
        rows = (
            JobRun.query
            .filter(JobRun.job_id == job_id, JobRun.duration_ms.isnot(None))
            .order_by(desc(JobRun.created_at))
            .limit(LOOKBACK_RUNS)
            .all()
        )
        return [r.duration_ms for r in rows]
    else:
        # latency = pinged_at - expected_at
        rows = (
            JobRun.query
            .filter(
                JobRun.job_id == job_id,
                JobRun.pinged_at.isnot(None),
                JobRun.expected_at.isnot(None)
            )
            .order_by(desc(JobRun.created_at))
            .limit(LOOKBACK_RUNS)
            .all()
        )
        values = []
        for r in rows:
            delta_ms = (r.pinged_at - r.expected_at).total_seconds() * 1000
            if delta_ms >= 0:
                values.append(delta_ms)
        return values


def _on_cooldown(job_id):
    """Return True if an anomaly alert was sent for this job in the last 24h."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=COOLDOWN_HOURS)
    recent = Alert.query.filter(
        Alert.job_id == job_id,
        Alert.alert_type == 'anomaly',
        Alert.sent_at > cutoff
    ).first()
    return recent is not None
