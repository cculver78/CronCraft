# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

import stripe
from flask import Blueprint, redirect, request, render_template, current_app, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.models.user import User

bp = Blueprint('stripe_routes', __name__, url_prefix='/subscription')


@bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    plan = request.form.get('plan')

    # Mapping of plan name to Stripe Price ID from config.
    price_map = {
        'pro': current_app.config['STRIPE_PRO_PRICE_ID'],
        'team': current_app.config['STRIPE_TEAM_PRICE_ID']
    }

    if plan not in price_map:
        flash("Invalid plan selected.", "danger")
        return redirect(url_for('subscription.index'))

    try:
        checkout_session_kwargs = {
            'line_items': [
                {
                    # Provide the exact Price ID (for example, pr_1234) of the product you want to sell
                    'price': price_map[plan],
                    'quantity': 1,
                },
            ],
            'mode': 'subscription',
            'success_url': url_for('subscription.index', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': url_for('subscription.index', _external=True),
            'client_reference_id': str(current_user.id)
        }
        
        if current_user.stripe_customer_id:
            checkout_session_kwargs['customer'] = current_user.stripe_customer_id
        else:
            checkout_session_kwargs['customer_email'] = current_user.email
            
        checkout_session = stripe.checkout.Session.create(**checkout_session_kwargs)

    except Exception as e:
        current_app.logger.error(f'Stripe checkout error: {e}')
        flash('Something went wrong creating your checkout session. Please try again.', 'danger')
        return redirect(url_for('subscription.index'))

    return redirect(checkout_session.url, code=303)


@bp.route('/forward_checkout/<plan>', methods=['GET'])
@login_required
def forward_checkout(plan):
    if plan not in ['pro', 'team']:
        return redirect(url_for('subscription.index'))
    return render_template('subscription/forward_checkout.html', plan=plan)


@bp.route('/portal', methods=['POST'])
@login_required
def portal():
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

    if not current_user.stripe_customer_id:
        flash("No active subscription found.", "danger")
        return redirect(url_for('subscription.index'))

    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=url_for('subscription.index', _external=True)
        )
    except Exception as e:
        current_app.logger.error(f'Stripe portal error: {e}')
        flash('Something went wrong opening the billing portal. Please try again.', 'danger')
        return redirect(url_for('subscription.index'))

    return redirect(session.url, code=303)


@bp.route('/webhook', methods=['POST'])
@csrf.exempt
def webhook():
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    endpoint_secret = current_app.config['STRIPE_WEBHOOK_SECRET']
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return "Invalid signature", 400

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session(session)

    elif event['type'] in ['customer.subscription.updated', 'customer.subscription.deleted']:
        subscription = event['data']['object']
        handle_subscription_change(subscription)

    return jsonify(success=True)


def handle_checkout_session(session):
    client_reference_id = session.get('client_reference_id')
    if not client_reference_id:
        return

    user = db.session.get(User, client_reference_id)
    if not user:
        return

    user.stripe_customer_id = session.get('customer')
    user.stripe_subscription_id = session.get('subscription')
    # Will update the actual plan in the subscription.updated hook, or we can fetch the sub real quick.
    db.session.commit()


def handle_subscription_change(subscription):
    customer_id = subscription.get('customer')
    user = User.query.filter_by(stripe_customer_id=customer_id).first()

    if not user:
        return

    status = subscription.get('status')
    if status in ['active', 'trialing']:
        # Update user plan based on Product. This requires expanding or fetching the price.
        # For simplicity, we can fetch the Stripe Subscription
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        sub = stripe.Subscription.retrieve(subscription['id'])
        
        price_id = sub['items']['data'][0]['price']['id']
        
        if price_id == current_app.config.get('STRIPE_PRO_PRICE_ID'):
            user.plan = 'pro'
        elif price_id == current_app.config.get('STRIPE_TEAM_PRICE_ID'):
            user.plan = 'team'
        else:
            if user.plan == 'free':
                user.plan = 'pro' 
        user.stripe_subscription_id = subscription['id']
        # Clear any existing grace period since subscription is active again
        user.grace_period_end = None
    elif status == 'past_due':
        # Give user a 7-day grace period before downgrading
        from datetime import datetime, timezone, timedelta
        if not user.grace_period_end:
            user.grace_period_end = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
            current_app.logger.info(f"User {user.id} subscription past_due — grace period until {user.grace_period_end}")
    elif status in ['canceled', 'unpaid']:
        user.plan = 'free'
        user.stripe_subscription_id = None
        user.grace_period_end = None

    db.session.commit()
