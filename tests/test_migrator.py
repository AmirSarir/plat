import sqlite3

import pytest

from engops.infrastructure.database.migrator import (
    Migration,
    MigrationError,
    applied_versions,
    current_version,
    load_packaged_migrations,
    migrate,
)

M1 = Migration(1, "create_a", "CREATE TABLE a (id INTEGER PRIMARY KEY);")
M2 = Migration(2, "create_b", "CREATE TABLE b (id INTEGER PRIMARY KEY);")


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_packaged_migrations_are_sequential_from_one():
    versions = [m.version for m in load_packaged_migrations()]
    assert versions == list(range(1, len(versions) + 1))


def test_fresh_database_gets_all_packaged_migrations(tmp_path):
    conn = _conn(tmp_path)
    migrations = load_packaged_migrations()
    applied = migrate(conn, migrations)
    assert applied == [m.version for m in migrations]
    assert current_version(conn) == migrations[-1].version
    assert "app_meta" in _tables(conn)


def test_migrate_is_idempotent(tmp_path):
    conn = _conn(tmp_path)
    migrate(conn, [M1, M2])
    assert migrate(conn, [M1, M2]) == []


def test_failed_migration_rolls_back_completely(tmp_path):
    conn = _conn(tmp_path)
    migrate(conn, [M1])
    bad = Migration(2, "broken", "CREATE TABLE b (id INTEGER); THIS IS NOT SQL;")
    with pytest.raises(MigrationError):
        migrate(conn, [M1, bad])
    assert "b" not in _tables(conn)
    assert applied_versions(conn) == {1}


def test_backup_created_before_upgrading_existing_database(tmp_path):
    db_file = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"

    conn = sqlite3.connect(db_file)
    migrate(conn, [M1], db_file=db_file, backup_dir=backup_dir)
    assert not backup_dir.exists()  # fresh database: nothing to back up
    conn.close()

    conn = sqlite3.connect(db_file)
    migrate(conn, [M1, M2], db_file=db_file, backup_dir=backup_dir)
    assert len(list(backup_dir.glob("pre-migration-v0001-*.sqlite3"))) == 1
    conn.close()


def test_database_newer_than_app_is_refused(tmp_path):
    conn = _conn(tmp_path)
    migrate(conn, [M1, M2])
    with pytest.raises(MigrationError):
        migrate(conn, [M1])