"""Cost sync recovery: partial failure, crash windows, incomplete listings.

No live database and no network. `cost_sync.seen` is emulated by a fake connection routed on SQL
substrings. The cloud ledger is a fake that honours `since`, `until`, `limit`, `offset` and `total` the
way DataForge's route does (inclusive bounds, newest first). The local ledger is a fake that stores
what it is sent.

Cases A, B and C are the three recovery cases of the 2026-10-13 ruling:

A. An earlier row fails its local write and a later row succeeds. A later run must recover the earlier row.
B. The local write succeeds and the worker dies before it records its deduplication state.
   The destination has no deduplication contract, so this duplicates. It is a RETAINED BLOCKER, not a fix.
C. A listing is incomplete or a safety limit is reached. Partial progress must not read as complete.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

import cost_sync.worker as w
from cost_sync.worker import CostLedgerSyncWorker

NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)


class SimulatedCrash(BaseException):
    """The process dies. It is a BaseException so no `except Exception` in the worker can absorb it."""


# --- fakes -----------------------------------------------------------------------------------


class _Cursor:
    def __init__(self, store, pending=None):
        self._store, self._pending, self._last = store, pending if pending is not None else set(), []

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        p = params or {}
        if "max(created_at)" in sql:
            values = [r["created_at"] for r in self._store.values() if r["created_at"]]
            self._last = [(max(values) if values else None,)]
        elif "max(synced_at)" in sql:
            values = [r["synced_at"] for r in self._store.values() if r.get("synced_at")]
            self._last = [(max(values) if values else None,)]
        elif "ANY(%(ids)s)" in sql:
            wanted = set(p.get("ids", []))
            self._last = [(cid,) for cid in self._store if cid in wanted]
        elif "pg_try_advisory_lock" in sql:
            self._last = [(True,)]
        elif "ON CONFLICT (cloud_id) DO UPDATE" in sql:
            self._store[p["cloud_id"]] = {"created_at": p["created_at"], "synced_at": p.get("covered_through") or datetime.now(UTC)}
            self._pending.add(p["cloud_id"])
            self._last = []
        elif sql.startswith("SELECT synced_at"):
            row = self._store.get(p.get("cloud_id"))
            self._last = [(row.get("synced_at"),)] if row and row.get("synced_at") else []
        elif sql.startswith("INSERT INTO cost_sync.seen"):
            if p["cloud_id"] not in self._store:
                self._store[p["cloud_id"]] = {"created_at": p["created_at"], "synced_at": datetime.now(UTC)}
                self._pending.add(p["cloud_id"])
            self._last = []
        else:
            self._last = []

    def fetchall(self):
        return list(self._last)


class FakeDb:
    """`cost_sync.seen` with transaction semantics: a write is durable only after commit()."""

    def __init__(self):
        self.seen: dict[str, dict[str, Any]] = {}
        self._pending: set[str] = set()
        self.commits = 0

    def cursor(self):
        return _Cursor(self.seen, self._pending)

    def commit(self):
        self.commits += 1
        self._pending.clear()

    def rollback(self):
        self.crash()

    def crash(self):
        """The process dies: every uncommitted write is lost."""
        for key in self._pending:
            self.seen.pop(key, None)
        self._pending.clear()


class FakeCloud:
    """The cloud cost ledger: filters by since/until (inclusive), newest first, pages by offset."""

    def __init__(self, entries):
        self.entries = list(entries)
        self.requests: list[dict[str, Any]] = []
        self.fail_with: BaseException | None = None
        self.total_override: int | None = None

    def get(self, url: str):
        if self.fail_with is not None:
            raise self.fail_with
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        self.requests.append(q)
        since = datetime.fromisoformat(q["since"].replace("Z", "+00:00")) if "since" in q else None
        until = datetime.fromisoformat(q["until"].replace("Z", "+00:00")) if "until" in q else None
        rows = [
            e for e in self.entries
            if (since is None or _dt(e) >= since) and (until is None or _dt(e) <= until)
        ]
        rows.sort(key=_dt, reverse=True)
        limit, offset = int(q.get("limit", 50)), int(q.get("offset", 0))
        total = self.total_override if self.total_override is not None else len(rows)
        return {"items": rows[offset: offset + limit], "total": total}


class FakeLocal:
    """DataForge Local's ledger. It has NO deduplication: every POST makes a new row (new uuid)."""

    def __init__(self):
        self.rows: list[dict[str, Any]] = []
        self.fail_models: dict[str, int] = {}  # model_id -> how many more POSTs fail
        self.reject_models: set[str] = set()  # model_id -> permanent 422

    def post(self, url: str, body: dict[str, Any]):
        mid = body["model_id"]
        if mid in self.reject_models:
            raise w.LocalWriteError("rejected", 422)
        if self.fail_models.get(mid, 0) > 0:
            self.fail_models[mid] -= 1
            raise w.LocalWriteError("unavailable", None)
        self.rows.append(dict(body))


def _dt(e):
    return datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))


def _entry(cid: str, created: datetime, **kw):
    e = {
        "id": cid, "user_id": "u1", "provider": "anthropic", "model_id": cid, "task_type": "codefix",
        "input_tokens": 100, "output_tokens": 50, "input_cost_usd": "0.001000", "output_cost_usd": "0.002000",
        "total_cost_usd": "0.003000", "is_batch": False, "is_cached": False,
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00",
    }
    e.update(kw)
    return e


@pytest.fixture
def env(monkeypatch):
    cloud, local = FakeCloud([]), FakeLocal()
    monkeypatch.setattr(w, "_http_get_json", cloud.get)
    monkeypatch.setattr(w, "_http_post_json", local.post)
    monkeypatch.setattr(w, "_utcnow", lambda: NOW)
    return cloud, local, FakeDb()


def run(db):
    return CostLedgerSyncWorker().sync_once(db)


def mirrored(db):
    """The ids recorded as mirrored. The sentinel rows (heartbeat, coverage) are not entries."""
    return set(db.seen) - w._RESERVED_IDS


def old(hours):
    return NOW - timedelta(hours=hours)


# --- case A: an earlier row fails and a later row succeeds ------------------------------------------


def test_A_an_earlier_row_that_fails_is_recovered_by_a_later_run(env):
    cloud, local, db = env
    cloud.entries = [_entry("c1", old(5)), _entry("c2", old(4)), _entry("c3", old(3))]
    local.fail_models = {"c1": 1}  # c1 fails once, then the destination is healthy again

    first = run(db)
    assert first.complete is False and first.failed == 1
    assert "c2" not in db.seen and "c3" not in db.seen, "no row may be marked seen after a failed earlier row"

    second = run(db)
    assert second.complete is True
    assert sorted(r["model_id"] for r in local.rows) == ["c1", "c2", "c3"], "every row exactly once"
    assert mirrored(db) == {"c1", "c2", "c3"}


def test_A_the_watermark_never_passes_a_row_that_is_not_mirrored(env):
    cloud, local, db = env
    cloud.entries = [_entry("c1", old(5)), _entry("c2", old(4))]
    local.fail_models = {"c1": 1}
    run(db)
    assert w.CostLedgerSyncWorker()._watermark(db) is None, "nothing mirrored, so no checkpoint"


def test_A_a_permanently_rejected_row_blocks_visibly_and_is_not_skipped(env):
    cloud, local, db = env
    cloud.entries = [_entry("c1", old(5)), _entry("poison", old(4)), _entry("c3", old(3))]
    local.reject_models = {"poison"}
    result = run(db)
    assert result.complete is False and result.stopped_reason == "local_write_rejected"
    assert mirrored(db) == {"c1"}, "the row before the poison row is mirrored; the poison row and later rows are not"
    again = run(db)
    assert again.complete is False and again.stopped_reason == "local_write_rejected", "it keeps blocking, loudly"


# --- case B: crash between the local write and the dedup record (RETAINED BLOCKER) --------------------


def test_B_a_crash_after_the_local_write_duplicates_the_row_until_the_destination_deduplicates(env, monkeypatch):
    """Characterization of a retained blocker. DataForge Local's POST /api/v1/costs/record assigns a new
    uuid to every call and has no source id, so the worker cannot make a replay idempotent. This test
    documents the duplicate. It is not a statement that the behavior is acceptable."""
    cloud, local, db = env
    cloud.entries = [_entry("c1", old(5))]
    real_mark = CostLedgerSyncWorker._mark_seen
    monkeypatch.setattr(CostLedgerSyncWorker, "_mark_seen", lambda *a, **k: (_ for _ in ()).throw(SimulatedCrash()))
    with pytest.raises(SimulatedCrash):
        run(db)
    assert len(local.rows) == 1 and mirrored(db) == set(), "posted, but the worker died before it recorded that"

    monkeypatch.setattr(CostLedgerSyncWorker, "_mark_seen", real_mark)
    run(db)
    assert len(local.rows) == 2, "the replay duplicates the entry: the destination has no dedup contract"


# --- case C: incomplete listings and safety limits ---------------------------------------------------


def test_C_reaching_the_safety_limit_is_incomplete_and_advances_nothing(env, monkeypatch):
    cloud, local, db = env
    monkeypatch.setattr(w, "_MAX_OFFSET", 3)
    monkeypatch.setenv("FORGE_COST_SYNC_PAGE_LIMIT", "2")
    cloud.entries = [_entry(f"c{i}", old(10) + timedelta(minutes=i)) for i in range(6)]  # one window, six rows
    result = run(db)
    assert result.complete is False and result.stopped_reason == "listing_incomplete"
    assert local.rows == [] and mirrored(db) == set(), "a partial listing misses the OLDEST rows; mirroring the rest would skip them forever"


def test_C_a_total_that_does_not_match_the_rows_received_is_incomplete(env):
    cloud, local, db = env
    cloud.entries = [_entry("c1", old(5)), _entry("c2", old(4))]
    cloud.total_override = 5
    result = run(db)
    assert result.complete is False and result.stopped_reason == "listing_incomplete"
    assert local.rows == [] and mirrored(db) == set()


def test_C_rows_newer_than_the_lag_horizon_wait_for_the_next_run(env):
    cloud, local, db = env
    cloud.entries = [_entry("old", old(5)), _entry("fresh", NOW - timedelta(seconds=30))]
    result = run(db)
    assert result.complete is True
    assert [r["model_id"] for r in local.rows] == ["old"], "a row inside the commit-lag window is not read yet"


def test_C_a_long_idle_span_is_walked_in_windows_and_loses_nothing(env, monkeypatch):
    cloud, local, db = env
    monkeypatch.setenv("FORGE_COST_SYNC_WINDOW_HOURS", "24")
    cloud.entries = [_entry("a", NOW - timedelta(days=9, hours=3)), _entry("b", NOW - timedelta(days=4)), _entry("c", old(2))]
    result = run(db)
    assert result.complete is True and sorted(r["model_id"] for r in local.rows) == ["a", "b", "c"]
    assert all(
        datetime.fromisoformat(r["until"].replace("Z", "+00:00")) - datetime.fromisoformat(r["since"].replace("Z", "+00:00"))
        <= timedelta(hours=24) for r in cloud.requests
    ), "every cloud read is bounded to one window"


def test_C_progress_is_not_represented_as_complete_synchronization(env):
    cloud, local, db = env
    cloud.entries = [_entry("c1", old(5)), _entry("c2", old(4))]
    local.fail_models = {"c2": 1}
    result = run(db)
    assert result.synced == 1 and result.failed == 1
    assert result.complete is False, "one of two rows was mirrored; that is not a complete sync"
    assert w.exit_code_for(result) != 0


def test_a_complete_empty_run_is_complete(env):
    _, _, db = env
    result = run(db)
    assert result.complete is True and w.exit_code_for(result) == 0
