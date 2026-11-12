from pathlib import Path
import os
import sqlite3


def is_postgres(database):
    return str(database).startswith(('postgresql://', 'postgres://'))


def database_setting():
    return os.environ.get('DATABASE_URL') or os.environ.get('COURTSIDE_DATABASE') or Path('artifacts/courtside.db')


class PostgresConnection:
    def __init__(self, database):
        import psycopg
        try:
            self.connection = psycopg.connect(str(database), connect_timeout=15, autocommit=True)
        except psycopg.Error:
            raise sqlite3.DatabaseError('PostgreSQL connection failed') from None
        self.row_factory = None

    def execute(self, query, params=()):
        import psycopg
        from psycopg.rows import dict_row
        if query == 'BEGIN IMMEDIATE':
            self.execute("SET LOCAL lock_timeout = '10s'")
            return self.execute('SELECT pg_advisory_xact_lock(428913)')
        query = query.replace('?', '%s')
        try:
            cursor = self.connection.cursor(row_factory=dict_row if self.row_factory else None)
            cursor.execute(query, tuple(int(value) if isinstance(value, bool) else value for value in params))
            return cursor
        except psycopg.Error:
            raise sqlite3.DatabaseError('PostgreSQL query failed') from None

    def __enter__(self):
        self.execute('BEGIN')
        return self

    def __exit__(self, error_type, error, traceback):
        self.connection.execute('ROLLBACK' if error_type else 'COMMIT')

    def close(self):
        self.connection.close()


def connect(database):
    if is_postgres(database):
        return PostgresConnection(database)
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def migrate_database(database):
    if not is_postgres(database):
        from .storage import initialize_database
        initialize_database(database)
        return
    if '-pooler.' in str(database):
        raise ValueError('Use DATABASE_URL_UNPOOLED for schema migration')
    schema = Path(__file__).with_name('schema_postgres.sql').read_text()
    from contextlib import closing
    with closing(connect(database)) as connection, connection:
        for statement in schema.split(';'):
            if statement.strip():
                connection.execute(statement)
