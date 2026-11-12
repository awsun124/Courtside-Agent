import asyncio
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
import logging
from zoneinfo import ZoneInfo

from .database import connect

from .storage import read_briefings

EASTERN = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


def daily_times(now):
    local = now.astimezone(EASTERN)
    today = datetime.combine(local.date(), time(6), EASTERN)
    next_update = today if local < today else datetime.combine(local.date() + timedelta(days=1), time(6), EASTERN)
    return today.astimezone(timezone.utc), next_update.astimezone(timezone.utc)


def schedule_status(now):
    _, next_update = daily_times(now)
    return dict(enabled=True, timezone="America/New_York", hour=6,
                next_update_at=next_update.isoformat())


def collect_daily(service):
    now = service.clock()
    due, _ = daily_times(now)
    if now < due:
        return False
    slot = due.isoformat()
    with closing(connect(service.database)) as connection, connection:
        claimed = connection.execute(
            "INSERT INTO daily_collections (scheduled_at, status) VALUES (?, 'running') ON CONFLICT DO NOTHING", (slot,)).rowcount
    if not claimed:
        return False
    try:
        previous = read_briefings(service.database, "live", limit=1)
        if not previous or datetime.fromisoformat(previous[0]["as_of"].replace("Z", "+00:00")) < due:
            service.refresh("live", 7, 3)
        status = "complete"
    except Exception:
        status = "failed"
        logger.warning("Daily collection failed. Keeping the previous briefing until the next scheduled edition.")
    with closing(connect(service.database)) as connection, connection:
        connection.execute("UPDATE daily_collections SET status=? WHERE scheduled_at=?", (status, slot))
    return True


async def run_schedule(service):
    while True:
        try:
            await asyncio.to_thread(collect_daily, service)
        except Exception:
            logger.warning("Daily schedule could not access storage. Will check again in one minute.")
        try:
            from .stats import collect_stats_daily
            await asyncio.to_thread(collect_stats_daily, service.database, service.clock())
        except Exception:
            logger.warning("Statistics collection could not finish. Saved data remains available.")
        await asyncio.sleep(60)
