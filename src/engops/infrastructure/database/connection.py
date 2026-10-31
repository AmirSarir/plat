"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def open_connection(db_file: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Commit on success, roll back on any error. Repositories never commit themselves."""
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def backup_database(conn: sqlite3.Connection, dest: Path) -> None:
    """Consistent copy of the live database using SQLite's online backup API."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
    finally:
        target.close()