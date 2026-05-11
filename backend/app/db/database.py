from contextlib import contextmanager
from typing import Iterator

import psycopg

from app.core.config import settings


@contextmanager
def get_db_connection() -> Iterator[psycopg.Connection]:
    connection = psycopg.connect(settings.db_dsn)
    try:
        yield connection
    finally:
        connection.close()
