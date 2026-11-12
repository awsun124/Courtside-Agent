from argparse import ArgumentParser
import os
from pathlib import Path
import sqlite3

from courtside.database import is_postgres, migrate_database


def main():
    parser = ArgumentParser()
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    database = os.environ.get('DATABASE_URL_UNPOOLED')
    if not database and args.env_file:
        for line in args.env_file.read_text().splitlines():
            name, separator, value = line.partition('=')
            if separator and name.strip() == 'DATABASE_URL_UNPOOLED':
                database = value.strip().strip("\"'")
    if not is_postgres(database):
        raise SystemExit('Set DATABASE_URL_UNPOOLED before running migrations.')
    try:
        migrate_database(database)
    except (sqlite3.Error, ValueError):
        raise SystemExit('Schema setup failed. Check the direct database URL and permissions.') from None
    print('Database schema is ready.')


if __name__ == '__main__':
    main()
