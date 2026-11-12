from contextlib import closing
import logging
import sqlite3

from courtside.database import connect, database_setting
from courtside.schedule import collect_daily, daily_times
from courtside.service import NewsService
from courtside.stats import collect_stats_daily, read_stats, season_for


def main():
    service = NewsService(database_setting())
    collect_daily(service)
    collect_stats_daily(service.database, service.clock())
    due, _ = daily_times(service.clock())
    with closing(connect(service.database)) as connection:
        row = connection.execute('SELECT status FROM daily_collections WHERE scheduled_at=?', (due.isoformat(),)).fetchone()
    if row and row[0] != 'complete':
        raise RuntimeError('Daily news collection did not complete. Previous data is preserved.')
    snapshot = read_stats(service.database, season_for(service.clock()), service.clock())
    if any((snapshot.get(kind) or {}).get('error') for kind in ('players', 'teams')):
        raise RuntimeError('Statistics collection was incomplete. Saved results remain available.')
    logging.info('Daily collection finished or was already collected.')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except (sqlite3.Error, RuntimeError):
        logging.error('Daily collection failed. Check source access and database configuration.')
        raise SystemExit(1) from None
