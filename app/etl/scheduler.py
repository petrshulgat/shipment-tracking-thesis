"""Daily ETL scheduler (FR-11). Run in its own container: python -m app.etl.scheduler"""
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.db.client import get_db
from .run import run_range


def daily_job():
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # yesterday + the day before (catches late events)
    print(run_range(get_db(), today - timedelta(days=2), today))


if __name__ == "__main__":
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(daily_job, "cron", hour=1, minute=0)
    sched.start()