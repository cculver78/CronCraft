# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Charles Culver / Edge Case Software, LLC

import os
from app import create_app
from app.services.scheduler import check_missed_pings, purge_old_runs, check_grace_period_expirations
from apscheduler.schedulers.blocking import BlockingScheduler

app = create_app(os.getenv('FLASK_ENV', 'default'))

def run_worker():
    scheduler = BlockingScheduler()
    # Check for missed pings every minute
    scheduler.add_job(
        lambda: run_in_context(check_missed_pings), 
        'interval', 
        minutes=1
    )
    # Purge expired run history once a day at 03:00 UTC
    scheduler.add_job(
        lambda: run_in_context(purge_old_runs),
        'cron',
        hour=3,
        minute=0
    )
    # Check for expired grace periods once a day at 03:15 UTC
    scheduler.add_job(
        lambda: run_in_context(check_grace_period_expirations),
        'cron',
        hour=3,
        minute=15
    )
    print("Worker started. Checking for missed pings every 1 minute...")
    scheduler.start()

def run_in_context(func):
    with app.app_context():
        func()

if __name__ == '__main__':
    run_worker()
