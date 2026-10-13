"""Tests for the cloud->local cost-ledger sync worker.

No live DB or HTTP: `cost_sync.seen` is emulated by a fake connection routed on
SQL substrings, and the cloud read / local write are monkeypatched. Verifies the
worker mirrors unseen cloud entries, skips already-seen ones (idempotency), and
does not mark an entry seen when its local write fails.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import cost_sync.worker as worker_mod
from cost_sync.worker import CostLedgerSyncWorker


class _FakeCursor:
    def __init__(self, store: dict[str, dict[str, Any]]) -> None:
        self._store = store
        self._last: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        p = params or {}
        if "max(created_at)" in sql:
            values = [row["created_at"] for row in self._store.values() if row["created_at"]]
            self._last = [(max(values) if values else None,)]
        elif sql.startswith("SELECT synced_at"):
            row = self._store.get(p.get("cloud_id"))
            self._last = [(row.get("synced_at"),)] if row and row.get("synced_at") else []
        elif "ON CONFLICT (cloud_id) DO UPDATE" in sql:
            self._store[p["cloud_id"]] = {"created_at": p["created_at"], "synced_at": datetime.now(UTC)}
            self._last = []
        elif "ANY(%(ids)s)" in sql:
            wanted = set(p.get("ids", []))
            self._last = [(cid,) for cid in self._store if cid in wanted]
        elif sql.startswith("INSERT INTO cost_sync.seen"):
            self._store.setdefault(p["cloud_id"], {"created_at": p["created_at"]})
            self._last = []
        else:
            self._last = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._last)


class _FakeConnection:
    def __init__(self) -> None:
        self.seen: dict[str, dict[str, Any]] = {}

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.seen)

    def commit(self) -> None:  # pragma: no cover - not exercised here
        pass

    def rollback(self) -> None:  # pragma: no cover
        pass


NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)
_RECENT = (NOW - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry(cloud_id: str, *, provider: str = "anthropic", created: str = _RECENT) -> dict[str, Any]:
    return {
        "id": cloud_id,
        "user_id": "u1",
        "provider": provider,
        "model_id": "m1",
        "task_type": "codefix",
        "input_tokens": 100,
        "output_tokens": 50,
        "input_cost_usd": "0.001000",
        "output_cost_usd": "0.002000",
        "total_cost_usd": "0.003000",
        "is_batch": False,
        "is_cached": False,
        "created_at": created,
    }


def _patch_cloud(monkeypatch, entries: list[dict[str, Any]]) -> None:
    """A cloud that honours since/until like the real route (inclusive, newest first)."""
    monkeypatch.setattr(worker_mod, "_utcnow", lambda: NOW)

    def get(url: str) -> dict[str, Any]:
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        since = datetime.fromisoformat(q["since"].replace("Z", "+00:00"))
        until = datetime.fromisoformat(q["until"].replace("Z", "+00:00"))
        rows = [
            e for e in entries
            if since <= datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) <= until
        ]
        return {"items": rows, "total": len(rows)}

    monkeypatch.setattr(worker_mod, "_http_get_json", get)


def test_mirrors_unseen_then_skips_on_rerun(monkeypatch):
    posted: list[dict[str, Any]] = []
    monkeypatch.setattr(worker_mod, "_http_post_json", lambda url, body: posted.append(body))
    _patch_cloud(monkeypatch, [_entry("c1"), _entry("c2", provider="openai")])
    conn = _FakeConnection()

    first = CostLedgerSyncWorker().sync_once(conn)
    assert (first.fetched, first.synced, first.skipped, first.failed) == (2, 2, 0, 0)
    assert len(posted) == 2
    assert {b["provider"] for b in posted} == {"anthropic", "openai"}

    # Re-run over the same window: both ids are already seen → skipped, no new writes.
    posted.clear()
    second = CostLedgerSyncWorker().sync_once(conn)
    assert (second.fetched, second.synced, second.skipped, second.failed) == (2, 0, 2, 0)
    assert posted == []


def test_failed_local_write_is_not_marked_seen(monkeypatch):
    def boom(url, body):
        raise worker_mod.LocalWriteError("unavailable")

    monkeypatch.setattr(worker_mod, "_http_post_json", boom)
    _patch_cloud(monkeypatch, [_entry("c1")])
    conn = _FakeConnection()

    result = CostLedgerSyncWorker().sync_once(conn)
    assert (result.synced, result.failed) == (0, 1)
    assert result.complete is False and result.stopped_reason == "local_write_unavailable"
    assert set(conn.seen) <= {worker_mod._HEARTBEAT_ID}  # not marked seen → a later run retries it


def test_empty_cloud_is_noop(monkeypatch):
    monkeypatch.setattr(worker_mod, "_http_post_json", lambda url, body: None)
    _patch_cloud(monkeypatch, [])
    result = CostLedgerSyncWorker().sync_once(_FakeConnection())
    assert (result.fetched, result.synced, result.skipped, result.failed) == (0, 0, 0, 0)
