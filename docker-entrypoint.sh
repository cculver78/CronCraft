#!/bin/sh
set -e

# Ensure data directory exists for SQLite storage
mkdir -p "${DATA_DIR:-/app/data}"

# Run database migrations on startup (creates tables on first boot)
echo "Applying database migrations..."
flask db upgrade

case "$1" in
    web)
        echo "Starting CronCraft web server on port 5010..."
        exec gunicorn \
            --workers "${GUNICORN_WORKERS:-2}" \
            --bind "0.0.0.0:5010" \
            --access-logfile - \
            --error-logfile - \
            "app:create_app('production')"
        ;;
    worker)
        echo "Starting CronCraft background worker..."
        exec python -m app.worker
        ;;
    *)
        # Allow running arbitrary commands (e.g. flask shell)
        exec "$@"
        ;;
esac
