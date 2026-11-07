"""Daily ETL scheduler (FR-11). Run in its own container: python -m app.etl.scheduler"""
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.db.client import get_db
from .run import run_range


def daily_window(now):
    """Yesterday + the day before, which catches late events (D-15)."""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=2), today


def daily_job():
    start, end = daily_window(datetime.now(timezone.utc))
    print(run_range(get_db(), start, end))


if __name__ == "__main__":
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(daily_job, "cron", hour=1, minute=0)
    sched.start()