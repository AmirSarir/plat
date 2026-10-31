from types import SimpleNamespace

import pytest

from engops.infrastructure.database.connection import open_connection
from engops.infrastructure.database.migrator import load_packaged_migrations, migrate
from engops.infrastructure.database.repositories import (
    SqliteProcessRepository,
    SqliteProcessVersionRepository,
    SqliteRunRepository,
    SqliteStoredFileRepository,
)


@pytest.fixture
def conn(tmp_path):
    connection = open_connection(tmp_path / "test.db")
    migrate(connection, load_packaged_migrations())
    yield connection
    connection.close()


@pytest.fixture
def repos(conn):
    return SimpleNamespace(
        processes=SqliteProcessRepository(conn),
        versions=SqliteProcessVersionRepository(conn),
        files=SqliteStoredFileRepository(conn),
        runs=SqliteRunRepository(conn),
    )