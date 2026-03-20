# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user
from app.models.user import User
from app.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from app.services.email_service import send_email, generate_token, verify_token
from app.validators import validate_password
import requests

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        # Bot protection: honeypot + reCAPTCHA
        if _is_honeypot_filled(request):
            flash('Please check your login details and try again.', 'danger')
            return redirect(url_for('auth.login'))
        if not _verify_recaptcha(request.form.get('g-recaptcha-response', '')):
            flash('Bot verification failed. Please try again.', 'danger')
            return redirect(url_for('auth.login'))

        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter_by(email=email).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Please check your login details and try again.', 'danger')
            return redirect(url_for('auth.login'))
        
        if not user.email_verified:
            flash('Please verify your email before logging in. Check your inbox for a verification link.', 'danger')
            return render_template('auth/verify_sent.html', email=email)
            
        login_user(user, remember=remember)
        if user.grace_period_end:
            flash('⚠ Your payment is past due. Please update your payment method to avoid being downgraded to the Free plan.', 'danger')
        elif user.display_name:
            flash(f'Welcome back, {user.display_name}!', 'info')

        # Version update check for admin users
        if user.is_admin and user.version_check_enabled:
            from app.services.version_service import is_update_available
            try:
                update_avail, local_ver, remote_ver = is_update_available()
                if update_avail:
                    flash(f'A new version of CronCraft is available: {remote_ver} (you are running {local_ver})', 'info')
            except Exception:
                pass  # never block login for a version check failure
            
        from flask import session
        pending_plan = session.pop('pending_plan', None)
        if pending_plan in ['pro', 'team']:
            return redirect(url_for('stripe_routes.forward_checkout', plan=pending_plan))
            
        return redirect(url_for('dashboard.index'))
        
    return render_template('auth/login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        # Bot protection: honeypot + reCAPTCHA
        if _is_honeypot_filled(request):
            flash('Email address already exists.', 'danger')
            return redirect(url_for('auth.register'))
        if not _verify_recaptcha(request.form.get('g-recaptcha-response', '')):
            flash('Bot verification failed. Please try again.', 'danger')
            return redirect(url_for('auth.register'))

        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        # Server-side password validation
        pw_error = validate_password(password)
        if pw_error:
            flash(pw_error, 'danger')
            return redirect(url_for('auth.register'))

        user = User.query.filter_by(email=email).first()
        
        if user:
            flash('Email address already exists.', 'danger')
            return redirect(url_for('auth.register'))

        # First user to register becomes admin automatically
        is_first_user = User.query.count() == 0

        new_user = User(email=email, password_hash=generate_password_hash(password, method='scrypt'))
        if is_first_user:
            new_user.is_admin = True
        db.session.add(new_user)

        # Self-hosted: auto-verify and skip email
        from app.plan_limits import is_self_hosted
        if is_self_hosted():
            new_user.email_verified = True
            db.session.commit()
            flash('Account created! You can now log in.', 'success')
            return redirect(url_for('auth.login'))

        db.session.commit()
        
        # Send verification email
        _send_verification_email(new_user)
        
        flash('Account created! Please check your email to verify your account.', 'success')
        return render_template('auth/verify_sent.html', email=email)
        
    plan = request.args.get('plan')
    if plan in ['pro', 'team']:
        from flask import session
        session['pending_plan'] = plan
        
    return render_template('auth/register.html')

@bp.route('/verify/<token>')
def verify_email(token):
    email = verify_token(token, salt='email-verify')
    if email is None:
        flash('The verification link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Account not found.', 'danger')
        return redirect(url_for('auth.login'))
    
    if user.email_verified:
        flash('Email already verified. You can sign in.', 'info')
        return redirect(url_for('auth.login'))
        
    user.email_verified = True
    db.session.commit()
    
    flash('Email verified! You can now sign in.', 'success')
    return redirect(url_for('auth.login'))

@bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email', '').strip().lower()
    user = User.query.filter_by(email=email).first()
    
    if user and not user.email_verified:
        _send_verification_email(user)
    
    # Always show success to avoid email enumeration
    flash('If that email is registered, a new verification link has been sent.', 'info')
    return render_template('auth/verify_sent.html', email=email)

@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if user:
            token = generate_token(user.email, salt='password-reset')
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            send_email(
                subject='[CronCraft] Reset Your Password',
                recipients=[user.email],
                text_body=f'Click the following link to reset your password: {reset_url}\n\nThis link expires in 1 hour.',
                html_body=render_template('email/reset_password.html', reset_url=reset_url)
            )
        
        # Always show success to avoid email enumeration
        flash('If that email is registered, a password reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    email = verify_token(token, salt='password-reset', max_age=3600)
    if email is None:
        flash('The reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        pw_error = validate_password(password)
        if pw_error:
            flash(pw_error, 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Account not found.', 'danger')
            return redirect(url_for('auth.login'))
        
        user.password_hash = generate_password_hash(password, method='scrypt')
        db.session.commit()
        
        flash('Password reset successfully. You can now sign in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)

@bp.route('/logout', methods=['POST'])
def logout():
    logout_user()
    return redirect(url_for('main.index'))


def _verify_recaptcha(token):
    """Verify a reCAPTCHA v2 response token with Google. Skipped in self-hosted mode."""
    from app.plan_limits import is_self_hosted
    if is_self_hosted():
        return True

    secret = current_app.config.get('RECAPTCHA_SECRET_KEY', '')
    if not secret:
        return True  # skip when no key is configured
    try:
        resp = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={'secret': secret, 'response': token},
            timeout=5
        )
        return resp.json().get('success', False)
    except Exception:
        current_app.logger.exception('reCAPTCHA verification request failed')
        return False


def _is_honeypot_filled(req):
    """Return True if the hidden honeypot field was filled in (bot detected)."""
    return bool(req.form.get('website', ''))


def _send_verification_email(user):
    """Helper to send an account verification email."""
    token = generate_token(user.email, salt='email-verify')
    verify_url = url_for('auth.verify_email', token=token, _external=True)
    
    send_email(
        subject='[CronCraft] Verify Your Email',
        recipients=[user.email],
        text_body=f'Click the following link to verify your email: {verify_url}',
        html_body=render_template('email/verify.html', verify_url=verify_url)
    )
