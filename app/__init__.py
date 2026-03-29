# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import config
from app.extensions import db, migrate, login_manager, csrf, limiter, mail

def create_app(config_name='default'):
    app = Flask(__name__)
    
    # Trust reverse proxy headers so url_for(_external=True) generates https:// URLs
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)

    # Detect self-hosted mode (SELF_HOSTED=true = all features unlocked, no billing UI)
    from app.plan_limits import init_self_hosted, is_self_hosted
    init_self_hosted(app.config.get('SELF_HOSTED', False))

    # Make is_self_hosted and app_version available in all templates
    from app.services.version_service import get_local_version
    @app.context_processor
    def inject_globals():
        return dict(
            is_self_hosted=is_self_hosted(),
            app_version=get_local_version() or 'unknown',
        )

    # Import models so Alembic can detect them
    from app.models import user, team, job


    # Register blueprints
    from app.routes.stripe_routes import bp as stripe_routes_bp
    app.register_blueprint(stripe_routes_bp)

    from app.routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.routes.marketing import bp as marketing_bp
    app.register_blueprint(marketing_bp)

    from app.routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.routes.dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)
    
    from app.routes.jobs import bp as jobs_bp
    app.register_blueprint(jobs_bp)
    
    from app.routes.ping import bp as ping_bp
    app.register_blueprint(ping_bp)

    from app.routes.settings import bp as settings_bp
    app.register_blueprint(settings_bp)

    from app.routes.teams import bp as teams_bp
    app.register_blueprint(teams_bp)

    from app.routes.subscription import bp as subscription_bp
    app.register_blueprint(subscription_bp)

    from app.routes.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    from app.routes.api_v1 import bp as api_v1_bp
    app.register_blueprint(api_v1_bp)

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        from flask import render_template
        return render_template('errors/500.html'), 500

    return app
