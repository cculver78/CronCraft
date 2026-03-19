# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from datetime import datetime, timezone
from flask import render_template, current_app
import requests
from app.extensions import db
from app.models.job import Alert
from app.services.email_service import send_email


def send_alert(job, alert_type, anomaly_data=None):
    """
    Dispatch alerts for a job event.
    alert_type: 'missed' | 'recovered' | 'dependency_failed' | 'anomaly'
    anomaly_data: optional dict with keys: metric, current, mean, stdev, z_score
    """
    subject, message = build_message(job, alert_type, anomaly_data)

    if job.notify_email and getattr(job, 'user', None):
        html_body = render_template(
            'email/alert.html',
            job=job,
            alert_type=alert_type,
            message=message,
            anomaly_data=anomaly_data
        )
        send_email(
            subject=subject,
            recipients=[job.user.email],
            text_body=message,
            html_body=html_body
        )

        alert = Alert(
            job_id=job.id,
            alert_type=alert_type,
            sent_via='email',
            sent_at=datetime.now(timezone.utc).replace(tzinfo=None)
        )
        db.session.add(alert)
        db.session.commit()

    if job.notify_webhook and job.webhook_url:
        # Only send webhook if user's plan allows it
        from app.plan_limits import is_feature_allowed
        user_plan = job.user.plan if getattr(job, 'user', None) else 'free'
        if not is_feature_allowed(user_plan, 'allow_webhook'):
            pass  # Skip webhook — user's plan no longer supports it
        else:
            payload = {
                'job_id': job.id,
                'job_name': job.name,
                'alert_type': alert_type,
                'status': job.last_status,
                'expected_at': job.expected_at.isoformat() if job.expected_at else None,
                'message': message,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            if anomaly_data:
                payload['anomaly'] = anomaly_data
            
            try:
                # Short timeout so we don't block the scheduler thread for long
                response = requests.post(job.webhook_url, json=payload, timeout=5)
                response.raise_for_status()
                
                alert = Alert(
                    job_id=job.id,
                    alert_type=alert_type,
                    sent_via='webhook',
                    sent_at=datetime.now(timezone.utc).replace(tzinfo=None)
                )
                db.session.add(alert)
                db.session.commit()
            except requests.exceptions.RequestException as e:
                current_app.logger.warning(f'Webhook delivery failed for job {job.id} ({job.name}): {e}')

    if job.notify_slack and job.slack_webhook:
        # Only send Slack if user's plan allows it
        from app.plan_limits import is_feature_allowed
        user_plan = job.user.plan if getattr(job, 'user', None) else 'free'
        if not is_feature_allowed(user_plan, 'allow_slack'):
            pass  # Skip Slack — user's plan no longer supports it
        else:
            slack_payload = {
                "text": f"{subject}\n{message}\n*Status:* {job.last_status}\n*Expected At:* {job.expected_at.isoformat() if job.expected_at else 'N/A'}"
            }
            
            try:
                response = requests.post(job.slack_webhook, json=slack_payload, timeout=5)
                response.raise_for_status()
                
                alert = Alert(
                    job_id=job.id,
                    alert_type=alert_type,
                    sent_via='slack',
                    sent_at=datetime.now(timezone.utc).replace(tzinfo=None)
                )
                db.session.add(alert)
                db.session.commit()
            except requests.exceptions.RequestException as e:
                current_app.logger.warning(f'Slack delivery failed for job {job.id} ({job.name}): {e}')

def build_message(job, alert_type, anomaly_data=None):
    if alert_type == 'missed':
        subject = f'[CronCraft] {job.name} — Missed Ping'
        body = f'{job.name} missed its expected ping at {job.expected_at}.'
    elif alert_type == 'failed':
        subject = f'[CronCraft] {job.name} — FAILED'
        body = f'{job.name} has reported a failure status.'
    elif alert_type == 'recovered':
        subject = f'[CronCraft] {job.name} — Recovered'
        body = f'{job.name} has recovered and just checked in.'
    elif alert_type == 'anomaly' and anomaly_data:
        subject = f'[CronCraft] {job.name} — Duration Anomaly'
        current_fmt = _format_duration(anomaly_data['current'])
        mean_fmt = _format_duration(anomaly_data['mean'])
        body = (
            f'{job.name} completed in {current_fmt}, '
            f'which is {abs(anomaly_data["z_score"])}σ from the average of {mean_fmt}. '
            f'This is unusual based on the last 30 runs.'
        )
    else:
        subject = f'[CronCraft] Alert for {job.name}'
        body = f'Alert for {job.name}'
    return subject, body


def _format_duration(ms):
    """Format milliseconds into a human-readable string."""
    if ms < 1000:
        return f'{int(ms)}ms'
    seconds = ms / 1000
    if seconds < 60:
        return f'{seconds:.1f}s'
    minutes = seconds / 60
    if minutes < 60:
        return f'{minutes:.1f}min'
    hours = minutes / 60
    return f'{hours:.1f}h'
