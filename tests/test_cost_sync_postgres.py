"""Cost sync on real PostgreSQL, against a source that has the REAL cloud ordering and paging contract.

* `cost_sync.seen` is the real table from migration 004 on a throwaway PostgreSQL (no mock cursor).
* The cloud and DataForge-Local are real HTTP servers on loopback (`tests/cost_sync_support.py`). The
  worker uses its real transport. The cloud answers like `list_cost_entries` of cloud DataForge:
  inclusive `since` and `until`, `total` counted apart, `ORDER BY created_at DESC` with `OFFSET`/`LIMIT`
  and NO order among rows with equal `created_at`. The local sink has no source id, like the real route.
* A "restart" is a new connection. A "crash" closes the connection with no commit.

Each test says what it proves. The last section lists what is NOT proven.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

import cost_sync.worker as w
from cost_sync.worker import CostLedgerSyncWorker
from cost_sync_support import ContractCloud, LocalSink, entry

# The sentinel rows use the real clock (NOW() in PostgreSQL), so "now" is the real time at import.
NOW = datetime.now(UTC).replace(microsecond=0)


class SimulatedCrash(BaseException):
    """The process dies. A BaseException, so no `except Exception` in the worker can absorb it."""


def ago(**kw):
    return NOW - timedelta(**kw)


@pytest.fixture
def world(monkeypatch, pg):
    cloud, sink = ContractCloud(), LocalSink()
    monkeypatch.setenv("DATAFORGE_URL", cloud.url)
    monkeypatch.setenv("DATAFORGE_LOCAL_URL", sink.url)
    for name in ("FORGE_COST_SYNC_CLOUD_API_KEY", "FORGE_COST_SYNC_LOCAL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FORGE_COST_SYNC_LOOKBACK_DAYS", "1")
    monkeypatch.setattr(w, "_utcnow", lambda: NOW)
    yield cloud, sink, pg
    cloud.close()
    sink.close()


def run_pass(pg, worker=None):
    """One pass the way the runner does it: a new connection, sync_once, commit, exit."""
    connection = pg.connect()
    try:
        result = (worker or CostLedgerSyncWorker()).sync_once(connection)
        connection.commit()
        return result
    finally:
        pg.close(connection)


def marked(pg):
    """Committed ledger markers. The sentinel rows are not ledger rows."""
    reserved = sorted(w._RESERVED_IDS)
    rows = pg.query("SELECT cloud_id FROM cost_sync.seen WHERE cloud_id <> ALL(%(r)s)", {"r": reserved})
    return {r[0] for r in rows}


def no_duplicates(sink):
    ids = sink.ids()
    return len(ids) == len(set(ids))


# --- 1. equal timestamps across pages ---------------------------------------------------------------


def _tied_rows(n_tied=7, n_distinct=3):
    tied_at = ago(hours=5)
    rows = [entry(f"t{i:02d}", tied_at) for i in range(n_tied)]
    rows += [entry(f"d{i:02d}", ago(hours=4, minutes=i)) for i in range(n_distinct)]
    return rows


def test_equal_timestamps_are_repeated_and_omitted_across_pages_and_sorting_the_pages_does_not_help(world, monkeypatch):
    """PROVES: with the real contract (no order among equal created_at), a page walk can return a row twice
    and never return another. Sorting the pages we already hold cannot bring back the omitted row."""
    cloud, sink, pg = world
    cloud.rows, cloud.ties = _tied_rows(), "by_page"
    monkeypatch.setenv("FORGE_COST_SYNC_PAGE_LIMIT", "3")
    all_ids = {r["id"] for r in cloud.rows}

    collected, listed_in_full = CostLedgerSyncWorker()._fetch_window(ago(days=1), NOW)
    got = [str(item["id"]) for item in collected]

    assert len(got) == len(all_ids), "every page was full and the count matches `total`"
    assert len(set(got)) < len(got), "a row is repeated"
    assert all_ids - set(got), "and a row is missing from every page"
    assert set(sorted(got)) == set(got) and all_ids - set(sorted(got)), "sorting what was returned restores nothing"
    assert listed_in_full is False, "the worker's own check sees the repeat"


def test_a_broken_listing_is_never_called_complete_writes_nothing_and_stays_blocked(world, monkeypatch):
    """PROVES (safety): a window whose listing repeats and omits rows is not mirrored, and the pass is not
    complete. PROVES (liveness FAULT): when the wrong order is the same on every pass, the sync is blocked
    on that window for good. The block is loud (exit code 1). It is the reason for the server tiebreak."""
    cloud, sink, pg = world
    cloud.rows, cloud.ties = _tied_rows(), "by_page"
    monkeypatch.setenv("FORGE_COST_SYNC_PAGE_LIMIT", "3")
    for _ in range(3):
        result = run_pass(pg)
        assert result.complete is False and result.stopped_reason == "listing_incomplete"
        assert w.exit_code_for(result) == 1
    assert sink.ids() == [] and marked(pg) == set(), "a partial window is never written"
    assert result.covered_through is None, "and no coverage is claimed"


def test_with_the_server_tiebreak_the_same_data_is_listed_in_full_and_mirrored_once(world, monkeypatch):
    """PROVES: with `ORDER BY created_at DESC, id DESC` (the proposed fix) the same rows and page size give a
    complete pass and one write per row. Source: DataForge branch security/cost-ledger-ordering."""
    cloud, sink, pg = world
    cloud.rows, cloud.ties = _tied_rows(), "id_desc"
    monkeypatch.setenv("FORGE_COST_SYNC_PAGE_LIMIT", "3")
    result = run_pass(pg)
    assert result.complete is True and result.synced == 10
    assert sorted(sink.ids()) == sorted(r["id"] for r in cloud.rows) and no_duplicates(sink)
    assert marked(pg) == {r["id"] for r in cloud.rows}


def test_with_an_order_that_changes_on_every_request_a_pass_is_either_exact_or_writes_nothing(world, monkeypatch):
    """PROVES (property over 25 passes): under a different legal tie order on every request, a pass is
    never a partial copy of a window. It is complete with every row once, or it is incomplete with no write."""
    cloud, sink, pg = world
    cloud.rows, cloud.ties = _tied_rows(n_tied=4, n_distinct=2), "by_request"
    monkeypatch.setenv("FORGE_COST_SYNC_PAGE_LIMIT", "3")
    outcomes = set()
    for _ in range(25):
        before = len(sink.ids())
        result = run_pass(pg)
        outcomes.add(result.complete)
        if not result.complete:
            assert result.stopped_reason == "listing_incomplete" and len(sink.ids()) == before
        else:
            break
    assert result.complete is True, "a changing order gives a clean listing now and then (the request seeds are fixed)"
    assert sorted(sink.ids()) == sorted(r["id"] for r in cloud.rows) and no_duplicates(sink)
    assert False in outcomes, "and it did fail first: the fault is real under this source"


# --- 2. window boundaries ------------------------------------------------------------------------------


def test_a_row_on_a_window_boundary_is_listed_by_both_windows_and_written_once(world, monkeypatch):
    """PROVES: both bounds are inclusive, so a row exactly on a boundary appears in two windows; the dedup
    record keeps it to one write. The horizon row is included; the first row after it waits for the next pass."""
    cloud, sink, pg = world
    monkeypatch.setenv("FORGE_COST_SYNC_WINDOW_HOURS", "1")
    start = NOW - timedelta(days=1)  # first window [start, start+1h]
    horizon = NOW - timedelta(seconds=120)
    cloud.rows = [
        entry("first", start),
        entry("boundary", start + timedelta(hours=1)),
        entry("after", start + timedelta(hours=1, microseconds=1)),
        entry("at_horizon", horizon),
        entry("past_horizon", horizon + timedelta(microseconds=1)),
    ]
    result = run_pass(pg)
    assert result.complete is True
    assert sorted(sink.ids()) == ["after", "at_horizon", "boundary", "first"]
    assert no_duplicates(sink) and result.skipped >= 1, "the boundary row was seen again and skipped"
    assert "past_horizon" not in marked(pg), "it waits for the next pass"
    monkeypatch.setattr(w, "_utcnow", lambda: NOW + timedelta(seconds=10))
    run_pass(pg)
    assert sorted(sink.ids()) == ["after", "at_horizon", "boundary", "first", "past_horizon"] and no_duplicates(sink)


def test_the_next_pass_starts_one_overlap_before_the_checkpoint(world, monkeypatch):
    """PROVES: the first cloud read of a later pass has since = checkpoint - overlap (default 6 hours)."""
    cloud, sink, pg = world
    cloud.rows = [entry("a", ago(hours=3))]
    run_pass(pg)
    cloud.requests.clear()
    run_pass(pg)
    since = datetime.fromisoformat(cloud.requests[0]["since"])
    assert since == ago(hours=3) - timedelta(hours=6)


# --- 3. partial pages --------------------------------------------------------------------------------


@pytest.mark.parametrize("rows,limit", [(6, 3), (5, 3), (2, 3), (0, 3)])
def test_a_last_page_that_is_full_partial_or_empty_still_ends_the_listing(world, monkeypatch, rows, limit):
    """PROVES: a final page that is exactly full (6 rows, 3 per page), short, or absent ends cleanly."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry(f"r{i}", ago(hours=5, minutes=i)) for i in range(rows)]
    monkeypatch.setenv("FORGE_COST_SYNC_PAGE_LIMIT", str(limit))
    result = run_pass(pg)
    assert result.complete is True and result.synced == rows and no_duplicates(sink)


def test_a_short_page_in_the_middle_is_not_read_as_the_end(world, monkeypatch):
    """PROVES: a page shorter than the limit with rows still behind it gives an incomplete listing (the count
    does not match `total`), and nothing is written."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry(f"r{i}", ago(hours=5, minutes=i)) for i in range(8)]
    cloud.truncate = {3: 2}  # the page at offset 3 returns 2 of its 3 rows
    monkeypatch.setenv("FORGE_COST_SYNC_PAGE_LIMIT", "3")
    result = run_pass(pg)
    assert result.complete is False and result.stopped_reason == "listing_incomplete"
    assert sink.ids() == [] and marked(pg) == set()


def test_a_row_inserted_between_two_page_requests_is_caught_and_the_next_pass_is_complete(world, monkeypatch):
    """PROVES: a write that lands while we page shifts the offsets (a repeat or a count mismatch). The pass is
    incomplete and writes nothing from that window. The next pass lists all rows."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry(f"r{i}", ago(hours=5, minutes=i)) for i in range(8)]
    monkeypatch.setenv("FORGE_COST_SYNC_PAGE_LIMIT", "3")
    inserted = []

    def insert_once(request_no):
        if request_no == 1 and not inserted:
            inserted.append(entry("late", ago(hours=5, minutes=3, seconds=30)))
            cloud.rows.append(inserted[0])

    cloud.on_request = insert_once
    first = run_pass(pg)
    assert first.complete is False and first.stopped_reason == "listing_incomplete" and sink.ids() == []
    second = run_pass(pg)
    assert second.complete is True and len(sink.ids()) == 9 and no_duplicates(sink)


# --- 4. late visible rows in windows already scanned ----------------------------------------------------


def test_a_late_visible_row_inside_the_overlap_is_found_by_the_next_pass(world):
    """PROVES: a row that becomes visible after the checkpoint passed it, but within the overlap, is mirrored."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry("a", ago(hours=5)), entry("b", ago(hours=3))]
    assert run_pass(pg).complete
    cloud.add(entry("late_in_overlap", ago(hours=4)))  # created_at older than the checkpoint (3 h ago)
    result = run_pass(pg)
    assert result.complete is True and "late_in_overlap" in sink.ids() and no_duplicates(sink)


def test_a_late_visible_row_older_than_the_overlap_is_NOT_found_and_the_pass_still_says_complete(world):
    """DOCUMENTS A GAP (not closed). PROVES that the overlap is a bound and not a guarantee: a row that
    becomes visible with a created_at more than 6 hours before the checkpoint is never listed again, and
    the pass reports complete. Closing it needs a count reconciliation over the whole range (a proposal in
    docs/KNOWN_ISSUES.md). The cloud sets created_at with now() at transaction start, so the row needs a
    transaction that commits more than 6 hours late."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry("a", ago(hours=20)), entry("b", ago(hours=3))]
    assert run_pass(pg).complete
    cloud.add(entry("late_beyond_overlap", ago(hours=12)))
    result = run_pass(pg)
    assert result.complete is True, "the worker cannot see the gap"
    assert "late_beyond_overlap" not in sink.ids(), "and the row is lost to the replica"


def test_with_no_overlap_even_a_recent_late_row_is_lost(world, monkeypatch):
    """PROVES why the overlap exists: with FORGE_COST_SYNC_OVERLAP_HOURS=0 (the behavior before this change)
    a late row just behind the checkpoint is never mirrored."""
    cloud, sink, pg = world
    monkeypatch.setenv("FORGE_COST_SYNC_OVERLAP_HOURS", "0")
    cloud.ties = "id_desc"
    cloud.rows = [entry("a", ago(hours=5)), entry("b", ago(hours=3))]
    assert run_pass(pg).complete
    cloud.add(entry("late", ago(hours=4)))
    assert run_pass(pg).complete is True
    assert "late" not in sink.ids()


# --- 5. two concurrent workers -----------------------------------------------------------------------


def _hold_first_post(sink):
    entered, release = threading.Event(), threading.Event()
    state = {"first": True}

    def hook(body):
        if state["first"]:
            state["first"] = False
            entered.set()
            assert release.wait(20)

    sink.before_post = hook
    return entered, release


def test_two_workers_without_the_pass_lock_write_rows_twice(world, monkeypatch):
    """DOCUMENTS THE HAZARD the lock closes. PROVES: both workers see a row as unseen and both write it. The
    marker table stays right (one row per id, ON CONFLICT DO NOTHING); the damage is at the destination."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry(f"r{i}", ago(hours=5, minutes=i)) for i in range(4)]
    monkeypatch.setattr(CostLedgerSyncWorker, "_acquire_pass_lock", lambda self, c: True)
    monkeypatch.setattr(CostLedgerSyncWorker, "_release_pass_lock", lambda self, c: None)
    entered, release = _hold_first_post(sink)
    results = {}
    thread = threading.Thread(target=lambda: results.update(a=run_pass(pg)))
    thread.start()
    assert entered.wait(20)
    results["b"] = run_pass(pg)
    release.set()
    thread.join(30)
    assert results["a"].complete and results["b"].complete
    assert len(sink.ids()) > 4 and not no_duplicates(sink), "the destination holds a row more than once"
    assert marked(pg) == {r["id"] for r in cloud.rows}


def test_a_second_worker_does_nothing_while_the_first_pass_runs(world):
    """PROVES: a session advisory lock makes a pass single-flight. The second pass writes nothing, reports
    `another_pass_running` and exits 1. The destination holds each row once. The lock is free again after."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry(f"r{i}", ago(hours=5, minutes=i)) for i in range(4)]
    entered, release = _hold_first_post(sink)
    results = {}
    thread = threading.Thread(target=lambda: results.update(a=run_pass(pg)))
    thread.start()
    assert entered.wait(20)
    second = run_pass(pg)
    assert second.complete is False and second.stopped_reason == "another_pass_running"
    assert second.synced == 0 and w.exit_code_for(second) == 1
    release.set()
    thread.join(30)
    assert results["a"].complete is True
    assert sorted(sink.ids()) == sorted(r["id"] for r in cloud.rows) and no_duplicates(sink)
    assert run_pass(pg).complete is True, "the lock was released at the end of the first pass"


def test_the_pass_lock_is_released_when_the_process_dies(world, monkeypatch):
    """PROVES: a crash mid-pass (the connection closes) frees the lock; the next pass runs."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry("r0", ago(hours=5))]
    monkeypatch.setattr(CostLedgerSyncWorker, "_post_local", lambda self, e: (_ for _ in ()).throw(SimulatedCrash()))
    connection = pg.connect()
    with pytest.raises(SimulatedCrash):
        CostLedgerSyncWorker().sync_once(connection)
    pg.close(connection)
    monkeypatch.undo()
    assert run_pass(pg).stopped_reason != "another_pass_running"


# --- 6. restart after partial progress ---------------------------------------------------------------------


def test_after_a_failed_row_the_committed_markers_survive_a_restart_and_the_rest_is_written_once(world):
    """PROVES: rows before the failure are durable in PostgreSQL (committed per row). After the connection is
    gone, a new process finishes the rest. The destination holds each row once."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry(f"c{i}", ago(hours=6 - i)) for i in range(1, 6)]
    sink.fail_for = {"c3"}
    first = run_pass(pg)
    assert first.complete is False and first.stopped_reason == "local_write_unavailable"
    assert marked(pg) == {"c1", "c2"}, "visible to an independent connection: committed"
    assert first.covered_through is None
    sink.fail_for = set()
    second = run_pass(pg)
    assert second.complete is True
    assert sink.ids() == ["c1", "c2", "c3", "c4", "c5"]
    assert marked(pg) == {"c1", "c2", "c3", "c4", "c5"}


def test_a_crash_after_some_rows_loses_only_the_row_in_flight(world, monkeypatch):
    """PROVES: a crash (no commit, connection closed) after two rows keeps the two committed markers."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry(f"c{i}", ago(hours=6 - i)) for i in range(1, 5)]
    real = CostLedgerSyncWorker._post_local

    def post(self, e):
        if e["model_id"] == "c3":
            raise SimulatedCrash()
        real(self, e)

    monkeypatch.setattr(CostLedgerSyncWorker, "_post_local", post)
    connection = pg.connect()
    with pytest.raises(SimulatedCrash):
        CostLedgerSyncWorker().sync_once(connection)
    pg.close(connection)
    assert marked(pg) == {"c1", "c2"}
    monkeypatch.setattr(CostLedgerSyncWorker, "_post_local", real)
    assert run_pass(pg).complete
    assert sink.ids() == ["c1", "c2", "c3", "c4"]


# --- 7. sentinel rows ---------------------------------------------------------------------------------------


def test_sentinel_rows_are_not_ledger_rows_and_never_move_the_checkpoint(world):
    """PROVES: after a complete pass `cost_sync.seen` holds the ledger markers plus two sentinel rows with
    created_at = epoch. A count of ledger rows excludes them; the checkpoint is the newest ledger row, not a sentinel."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry(f"r{i}", ago(hours=5, minutes=i)) for i in range(3)]
    result = run_pass(pg)
    total = pg.query("SELECT count(*) FROM cost_sync.seen")[0][0]
    sentinels = pg.query("SELECT cloud_id, created_at FROM cost_sync.seen WHERE cloud_id = ANY(%(r)s)", {"r": sorted(w._RESERVED_IDS)})
    assert total == 3 + 2 and {r[0] for r in sentinels} == set(w._RESERVED_IDS)
    assert all(r[1] == datetime(1970, 1, 1, tzinfo=UTC) for r in sentinels)
    assert len(marked(pg)) == 3 == result.synced
    assert datetime.fromisoformat(result.watermark) == max(r["created_at"] for r in cloud.rows)


def test_an_empty_ledger_leaves_only_sentinels_and_no_checkpoint(world):
    cloud, sink, pg = world
    result = run_pass(pg)
    assert result.complete and result.watermark is None and marked(pg) == set()
    assert pg.query("SELECT count(*) FROM cost_sync.seen")[0][0] == 2


def test_a_cloud_row_with_a_sentinel_id_is_refused_not_skipped(world):
    """PROVES: once the sentinel rows exist, a cloud row whose id equals one would be read as 'already
    mirrored' and silently skipped. The worker refuses it (`cloud_entry_malformed`) and writes nothing for it."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    assert run_pass(pg).complete  # creates the sentinel rows
    connection = pg.connect()
    assert CostLedgerSyncWorker()._seen_ids(connection, [w._HEARTBEAT_ID]) == {w._HEARTBEAT_ID}, "the collision mechanism"
    pg.close(connection)
    for reserved in sorted(w._RESERVED_IDS):
        cloud.rows = [entry(reserved, ago(hours=5)), entry("ok", ago(hours=4))]
        result = run_pass(pg)
        assert result.complete is False and result.stopped_reason == "cloud_entry_malformed"
        assert sink.ids() == [] and w.exit_code_for(result) == 1


def test_the_marker_table_enforces_one_row_per_cloud_id(world):
    """PROVES: the real PRIMARY KEY on cloud_id; a second marker for one id is refused by PostgreSQL."""
    import psycopg

    cloud, sink, pg = world
    connection = pg.connect()
    worker = CostLedgerSyncWorker()
    worker._mark_seen(connection, "x", NOW)
    worker._mark_seen(connection, "x", NOW)  # ON CONFLICT DO NOTHING: no error, no second row
    connection.commit()
    assert pg.query("SELECT count(*) FROM cost_sync.seen WHERE cloud_id = 'x'")[0][0] == 1
    with pytest.raises(psycopg.errors.UniqueViolation):
        connection._connection.execute("INSERT INTO cost_sync.seen (cloud_id, created_at) VALUES ('x', now())")
    connection._connection.rollback()
    pg.close(connection)


def test_only_ledger_facts_cross_to_the_destination(world):
    """PROVES: the write to DataForge-Local carries the billable ledger fields only. Sync metadata (marker
    id, heartbeat, coverage) stays in `cost_sync.seen` in this runtime's database."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry("r0", ago(hours=5))]
    run_pass(pg)
    assert set(sink.posts[0]) == {
        "user_id", "provider", "model_id", "task_type", "input_tokens", "output_tokens",
        "input_cost_usd", "output_cost_usd", "total_cost_usd", "is_batch", "is_cached",
    }


# --- 8. case B: crash between the destination write and the marker commit (BLOCKED) --------------------------


def test_B_a_crash_between_the_destination_write_and_the_marker_commit_duplicates_that_one_row(world, monkeypatch):
    """CHARACTERIZATION OF A RETAINED BLOCKER, on real PostgreSQL and a real HTTP destination. PROVES: the row
    in flight is written twice after a restart, because the destination has no source id. Per-row marker
    commits shrink the window to one row; they do NOT close it. This is not a statement that it is acceptable."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry("c1", ago(hours=5)), entry("c2", ago(hours=4)), entry("c3", ago(hours=3))]
    real_mark = CostLedgerSyncWorker._mark_seen

    def mark(self, connection, cloud_id, created_at):
        if cloud_id == "c2":
            raise SimulatedCrash()  # after the destination answered 201 for c2, before its marker
        real_mark(self, connection, cloud_id, created_at)

    monkeypatch.setattr(CostLedgerSyncWorker, "_mark_seen", mark)
    connection = pg.connect()
    with pytest.raises(SimulatedCrash):
        CostLedgerSyncWorker().sync_once(connection)
    pg.close(connection)
    assert sink.ids() == ["c1", "c2"] and marked(pg) == {"c1"}, "c2 is stored at the destination and not marked"

    monkeypatch.setattr(CostLedgerSyncWorker, "_mark_seen", real_mark)
    assert run_pass(pg).complete
    ids = sink.ids()
    assert sorted(ids) == ["c1", "c2", "c2", "c3"], "c2 is duplicated; c1 (marker committed) is not"
    assert not no_duplicates(sink)


# --- 9. freshness is coverage -----------------------------------------------------------------------------------


def test_a_complete_pass_records_what_it_scanned_through(world):
    """PROVES: coverage = the horizon the last complete pass scanned (now minus the commit lag), read back
    by status() with no call to the cloud."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry("a", ago(hours=5))]
    result = run_pass(pg)
    horizon = NOW - timedelta(seconds=120)
    assert datetime.fromisoformat(result.covered_through) == horizon
    cloud.close()  # the cloud is gone: status must still answer
    connection = pg.connect()
    status = CostLedgerSyncWorker().status(connection)
    pg.close(connection)
    assert datetime.fromisoformat(status["covered_through"]) == horizon
    assert status["coverage_age_seconds"] == pytest.approx(120, abs=1) and status["freshness_known"] is True


def test_copying_rows_without_a_complete_pass_does_not_advance_coverage(world, monkeypatch):
    """PROVES: coverage and last_successful_sync are not 'when a row was last copied'. A pass that mirrored
    rows and then stopped moves the checkpoint but not coverage."""
    cloud, sink, pg = world
    cloud.ties = "id_desc"
    cloud.rows = [entry("a", ago(hours=5))]
    first = run_pass(pg)
    monkeypatch.setattr(w, "_utcnow", lambda: NOW + timedelta(hours=1))
    cloud.add(entry("b", ago(minutes=50)), entry("c", ago(minutes=40)))
    sink.fail_for = {"c"}
    second = run_pass(pg)
    assert second.complete is False and second.synced == 1, "b was copied, c failed"
    assert second.covered_through == first.covered_through
    assert second.last_successful_sync == first.last_successful_sync
    assert datetime.fromisoformat(second.watermark) > datetime.fromisoformat(first.watermark), "progress is not coverage"
    assert second.coverage_age_seconds > first.coverage_age_seconds + 3000
