"""Cloud->local cost-ledger sync worker.

Mirrors cloud DataForge's ``cost_ledger`` into DataForge-Local so Forge_Command
can read per-model inference cost locally (local-first). Cloud DataForge stays
the single source of truth for cost; this worker only READS cloud
(``GET /api/v1/costs/entries``) and WRITES to DataForge-Local through its public
``POST /api/v1/costs/record`` API. All sync/dedup state lives in THIS runtime's
own database (``cost_sync.seen``) — the worker never writes to the DataForge or
DataForge-Local databases directly, so each system's DB-authority boundary holds.

Idempotent: a cloud entry's id is recorded in ``cost_sync.seen`` only after its
local write succeeds, and already-seen ids are skipped, so re-runs and overlapping
``since`` windows never double-count.

Environment:
* ``DATAFORGE_URL``                 cloud DataForge base (default cloud Render URL)
* ``DATAFORGE_LOCAL_URL``           DataForge-Local base (default http://127.0.0.1:8005)
* ``FORGE_COST_SYNC_LOOKBACK_DAYS`` first-run / empty-state window (default 30)
* ``FORGE_COST_SYNC_PAGE_LIMIT``    cloud page size, 1..200 (default 200)
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import error, parse, request

from runtime_promotion.persistence import DbConnection

_CLOUD_DEFAULT = "https://dataforge-pzmo.onrender.com"
_LOCAL_DEFAULT = "http://127.0.0.1:8005"
_MAX_OFFSET = 10_000  # safety bound on pagination


def _cloud_base_url() -> str:
    return os.environ.get("DATAFORGE_URL", _CLOUD_DEFAULT).strip().rstrip("/") or _CLOUD_DEFAULT


def _local_base_url() -> str:
    return os.environ.get("DATAFORGE_LOCAL_URL", _LOCAL_DEFAULT).strip().rstrip("/") or _LOCAL_DEFAULT


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.environ.get(name, str(default)).strip())))
    except (ValueError, AttributeError):
        return default


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@dataclass(frozen=True, slots=True)
class SyncResult:
    fetched: int
    synced: int
    skipped: int
    failed: int
    watermark: str | None


class CostLedgerSyncWorker:
    """Pull cloud cost entries and mirror the unseen ones into DataForge-Local."""

    WATERMARK_SQL = "SELECT max(created_at) FROM cost_sync.seen"
    SEEN_SQL = "SELECT cloud_id FROM cost_sync.seen WHERE cloud_id = ANY(%(ids)s)"
    MARK_SEEN_SQL = (
        "INSERT INTO cost_sync.seen (cloud_id, created_at) "
        "VALUES (%(cloud_id)s, %(created_at)s) "
        "ON CONFLICT (cloud_id) DO NOTHING"
    )

    def sync_once(self, connection: DbConnection) -> SyncResult:
        watermark = self._watermark(connection)
        since = watermark or (
            datetime.now(UTC)
            - timedelta(days=_int_env("FORGE_COST_SYNC_LOOKBACK_DAYS", 30, 1, 3650))
        )
        entries = self._fetch_cloud_entries(since)
        if not entries:
            return SyncResult(0, 0, 0, 0, watermark.isoformat() if watermark else None)

        seen = self._seen_ids(connection, [str(e["id"]) for e in entries])
        synced = skipped = failed = 0
        high_water = watermark
        for entry in entries:
            cloud_id = str(entry["id"])
            if cloud_id in seen:
                skipped += 1
                continue
            try:
                self._post_local(entry)
            except Exception as exc:  # keep going; a later run retries this id
                print(f"COST SYNC local write failed for {cloud_id}: {exc}")
                failed += 1
                continue
            created = _parse_dt(entry.get("created_at"))
            self._mark_seen(connection, cloud_id, created)
            seen.add(cloud_id)
            synced += 1
            if created and (high_water is None or created > high_water):
                high_water = created

        return SyncResult(
            fetched=len(entries),
            synced=synced,
            skipped=skipped,
            failed=failed,
            watermark=high_water.isoformat() if high_water else None,
        )

    # -- runtime-owned dedup state ---------------------------------------
    def _watermark(self, connection: DbConnection) -> datetime | None:
        cursor = connection.cursor()
        cursor.execute(self.WATERMARK_SQL, {})
        rows = cursor.fetchall()
        return rows[0][0] if rows and rows[0][0] is not None else None

    def _seen_ids(self, connection: DbConnection, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        cursor = connection.cursor()
        cursor.execute(self.SEEN_SQL, {"ids": ids})
        return {str(row[0]) for row in cursor.fetchall()}

    def _mark_seen(
        self, connection: DbConnection, cloud_id: str, created_at: datetime | None
    ) -> None:
        cursor = connection.cursor()
        cursor.execute(self.MARK_SEEN_SQL, {"cloud_id": cloud_id, "created_at": created_at})

    # -- cloud read (source of truth) ------------------------------------
    def _fetch_cloud_entries(self, since: datetime) -> list[dict[str, Any]]:
        limit = _int_env("FORGE_COST_SYNC_PAGE_LIMIT", 200, 1, 200)
        since_q = since.isoformat()
        collected: list[dict[str, Any]] = []
        offset = 0
        while True:
            query = parse.urlencode({"since": since_q, "limit": limit, "offset": offset})
            payload = _http_get_json(f"{_cloud_base_url()}/api/v1/costs/entries?{query}")
            items = payload.get("items", []) if isinstance(payload, dict) else []
            collected.extend(items)
            if len(items) < limit or offset >= _MAX_OFFSET:
                break
            offset += limit
        return collected

    # -- local write (through DataForge-Local's public API) --------------
    def _post_local(self, entry: dict[str, Any]) -> None:
        body = {
            "user_id": entry.get("user_id"),
            "provider": entry["provider"],
            "model_id": entry["model_id"],
            "task_type": entry["task_type"],
            "input_tokens": int(entry["input_tokens"]),
            "output_tokens": int(entry["output_tokens"]),
            "input_cost_usd": str(entry["input_cost_usd"]),
            "output_cost_usd": str(entry["output_cost_usd"]),
            "total_cost_usd": str(entry["total_cost_usd"]),
            "is_batch": bool(entry.get("is_batch", False)),
            "is_cached": bool(entry.get("is_cached", False)),
        }
        _http_post_json(f"{_local_base_url()}/api/v1/costs/record", body)


def _http_get_json(url: str) -> Any:
    req = request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=15) as response:
            code = response.getcode()
            if code != 200:
                raise RuntimeError(f"cloud cost read HTTP {code}")
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError(f"cloud cost read HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"cloud DataForge unreachable: {exc.reason}") from exc


def _http_post_json(url: str, body: dict[str, Any]) -> None:
    data = json.dumps(body).encode("utf-8")
    req = request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            code = response.getcode()
            if code not in (200, 201):
                raise RuntimeError(f"local cost write HTTP {code}")
    except error.HTTPError as exc:
        raise RuntimeError(f"local cost write HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"DataForge-Local unreachable: {exc.reason}") from exc
