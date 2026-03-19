# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

import stripe
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, current_app, redirect, url_for
from flask_login import login_required, current_user
from app.models.job import Job
from app.extensions import db
from app.plan_limits import get_plan_limits

bp = Blueprint('subscription', __name__, url_prefix='/subscription')


@bp.route('/')
@login_required
def index():
    session_id = request.args.get('session_id')
    if session_id:
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            if checkout_session.payment_status == 'paid':
                current_user.stripe_customer_id = checkout_session.customer
                current_user.stripe_subscription_id = checkout_session.subscription
                
                if checkout_session.subscription:
                    sub = stripe.Subscription.retrieve(checkout_session.subscription)
                    price_id = sub['items']['data'][0]['price']['id']
                    
                    if price_id == current_app.config.get('STRIPE_PRO_PRICE_ID'):
                        current_user.plan = 'pro'
                    elif price_id == current_app.config.get('STRIPE_TEAM_PRICE_ID'):
                        current_user.plan = 'team'
                    else:
                        current_user.plan = 'pro'
                        
                if current_user.plan != 'free' and not current_user.plan_started_at:
                     current_user.plan_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
                     
                db.session.commit()
                return redirect(url_for('subscription.index'))
                
        except Exception as e:
            current_app.logger.error(f"Error retrieving stripe session synchronously: {e}")

    limits = get_plan_limits(current_user.plan)
    job_count = Job.query.filter_by(user_id=current_user.id, team_id=None).count()

    # Use plan_started_at if set, otherwise fall back to created_at
    plan_started = current_user.plan_started_at or current_user.created_at

    # Fetch subscription period end from Stripe
    plan_ends = None
    if current_user.stripe_subscription_id and current_user.plan != 'free':
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        try:
            sub = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
            plan_ends = datetime.fromtimestamp(sub['current_period_end'], tz=timezone.utc).replace(tzinfo=None)
        except Exception as e:
            current_app.logger.error(f"Error fetching subscription period end: {e}")

    return render_template('subscription/index.html',
                           limits=limits,
                           job_count=job_count,
                           plan_started=plan_started,
                           plan_ends=plan_ends)
