"""Fixtures shared by the PostgreSQL tests of the cost sync worker."""
from __future__ import annotations

import pytest

from cost_sync_support import PgCluster, find_pg_bin


@pytest.fixture(scope="session")
def pg_cluster():
    """One throwaway PostgreSQL server for the session, on a private unix socket. Skips if there is none."""
    bin_dir = find_pg_bin()
    if bin_dir is None:
        pytest.skip("PostgreSQL server binaries (initdb, pg_ctl) not found; set COST_SYNC_TEST_PG_BIN")
    cluster = PgCluster(bin_dir)
    try:
        cluster.start()
        yield cluster
    finally:
        cluster.stop()


@pytest.fixture
def pg(pg_cluster):
    """A fresh database with the real migration 004 (cost_sync.seen). Dropped after the test."""
    database = pg_cluster.new_database()
    try:
        yield database
    finally:
        database.drop()


def pytest_configure(config):
    config.addinivalue_line("markers", "serve(status, body, location): loopback server answer for test_runtime_promotion_credentials")
