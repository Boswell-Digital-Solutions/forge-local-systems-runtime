"""Cloud->local cost-ledger sync worker.

Mirrors cloud DataForge's ``cost_ledger`` into DataForge-Local so Forge_Command can read
per-model inference cost locally (local-first). Cloud DataForge stays the single source of truth for
cost; this worker only READS cloud (``GET /api/v1/costs/entries``) and WRITES to DataForge-Local through
its public ``POST /api/v1/costs/record`` API. All sync/dedup state lives in THIS runtime's own database
(``cost_sync.seen``) — the worker never writes to the DataForge or DataForge-Local databases directly.

What a pass guarantees, and what it does not
--------------------------------------------
* **Contiguous progress.** A pass reads the cloud ledger in time windows, oldest window first, and mirrors
  each window oldest row first. It **stops at the first row it cannot mirror**. So every row older than
  the checkpoint is mirrored, and a row that failed is retried by the next pass. (Before 2026-10-13 a
  failed earlier row was never retried, because a later row moved the checkpoint past it.)
* **Never complete by accident.** A pass reports ``complete=True`` only if every window it needed was
  listed in full (the row count matches ``total``) and every row was mirrored or already seen. A
  safety limit, a count mismatch, a refused cloud read, an unreachable destination or a rejected row all
  give ``complete=False`` with a fixed ``stopped_reason``. Rows newer than a commit-lag horizon wait for
  the next pass; that is normal and is not an incomplete pass.
* **At-least-once, NOT exactly-once.** The destination (``POST /api/v1/costs/record``) gives every call a
  new id and has no source id, so it cannot recognise a replay. If the process dies after the local
  write and before the dedup record, the next pass writes that row again. The window is one row,
  because the dedup record is committed after every row. Closing it needs a destination contract
  (an optional ``source_entry_id`` with a unique index). That is a proposal, not part of this change
  (docs/KNOWN_ISSUES.md, FLS-COST-SYNC-NOT-EXACTLY-ONCE-20261013).

* **One pass at a time.** A pass takes a PostgreSQL session advisory lock on the runtime database. A second
  pass that starts while the first one runs does nothing and reports ``another_pass_running``. Without
  the lock, two workers both see a row as unseen, and both write it to the destination, which duplicates it.
* **Overlap re-scan.** A pass starts ``FORGE_COST_SYNC_OVERLAP_HOURS`` (default 6) before the checkpoint, not
  at the checkpoint. A row that became visible late, with a ``created_at`` older than the checkpoint, is then
  found. Already mirrored rows are skipped. A row that becomes visible later than the overlap is NOT found.
* **Freshness is coverage.** A complete pass records the time it scanned through (``covered_through``). A
  pass that copied rows and then stopped does not move it. ``last_successful_sync`` is when the last
  complete pass ended. Neither is "when a row was last copied".

Credentials (separate on purpose)
---------------------------------
* ``FORGE_COST_SYNC_CLOUD_API_KEY``  the cloud read key: DataForge scope ``costs:read`` on the service
  ``forge_local_runtime``. It is sent to the cloud origin only, never to the local URL, only over HTTPS (or
  loopback HTTP), and the client never follows a redirect.
* ``FORGE_COST_SYNC_LOCAL_API_KEY``  an optional local ingestion key. DataForge-Local does not
  authenticate this route today. If one is set it goes to the local URL only, never to the cloud.
The two keys are never used for each other's destination.

Environment: ``DATAFORGE_URL`` (cloud base), ``DATAFORGE_LOCAL_URL`` (default http://127.0.0.1:8005),
``FORGE_COST_SYNC_LOOKBACK_DAYS`` (first run, default 30), ``FORGE_COST_SYNC_PAGE_LIMIT`` (1..200,
default 200), ``FORGE_COST_SYNC_WINDOW_HOURS`` (1..168, default 24), ``FORGE_COST_SYNC_LAG_SECONDS``
(0..3600, default 120), ``FORGE_COST_SYNC_OVERLAP_HOURS`` (0..168, default 6).
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
_MAX_OFFSET = 10_000  # safety bound on pagination, per window
_MAX_WINDOWS = 400  # safety bound on windows per pass
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
_HEARTBEAT_ID = "__sync_heartbeat__"  # sentinel row in cost_sync.seen; created_at = epoch, so it never moves the checkpoint
#: Sentinel row: synced_at holds the time the last complete pass scanned through. created_at = epoch.
_COVERAGE_ID = "__sync_covered_through__"
#: Sentinel ids. A cloud entry with one of these ids would be read as already mirrored, so it is refused.
_RESERVED_IDS = frozenset({_HEARTBEAT_ID, _COVERAGE_ID})
_PASS_LOCK_KEY = 0x434F535453594E43  # "COSTSYNC": the advisory lock key of one pass
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SOURCE = "cloud_dataforge"


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


# --- errors ------------------------------------------------------------------------------------


class CloudReadError(RuntimeError):
    """The cloud ledger could not be read. ``kind`` and ``refusal_kind`` are fixed codes, never a body."""

    def __init__(self, kind: str, status: int | None = None, refusal_kind: str | None = None, reason: str | None = None):
        super().__init__(f"cloud cost read {kind}" + (f" HTTP {status}" if status else ""))
        self.kind, self.status, self.refusal_kind, self.reason = kind, status, refusal_kind, reason


class LocalWriteError(RuntimeError):
    """The local write failed. ``kind`` is ``rejected`` (a 4xx: retrying will not help) or ``unavailable``."""

    def __init__(self, kind: str, status: int | None = None):
        super().__init__(f"local cost write {kind}" + (f" HTTP {status}" if status else ""))
        self.kind, self.status = kind, status


# --- transport ---------------------------------------------------------------------------------


class _NoRedirect(request.HTTPRedirectHandler):
    """Never follow a redirect: a credential must not reach a second origin."""

    def redirect_request(self, *args: Any, **kwargs: Any):  # noqa: D401 - urllib hook
        return None


_OPENER = request.build_opener(_NoRedirect)


def _urlopen(req: request.Request, timeout: float):
    return _OPENER.open(req, timeout=timeout)


def _origin_ok_for_key(url: str) -> bool:
    parsed = parse.urlparse(url)
    return parsed.scheme == "https" or (parsed.scheme == "http" and (parsed.hostname or "") in _LOOPBACK)


def _cloud_headers(url: str) -> tuple[dict[str, str], str]:
    """Headers for a cloud read and the credential state: ``attached``, ``not_configured`` or ``withheld_cleartext``."""
    headers = {"Accept": "application/json"}
    key = os.environ.get("FORGE_COST_SYNC_CLOUD_API_KEY", "").strip()
    if not key:
        return headers, "not_configured"
    if not _origin_ok_for_key(url):
        return headers, "withheld_cleartext"
    headers["Authorization"] = f"Bearer {key}"
    return headers, "attached"


def _refusal_code(exc: error.HTTPError) -> str:
    """A fixed reason code from a refusal body, or ``unreadable``. Never the body."""
    try:
        body = json.loads(exc.read(4096).decode("utf-8"))
    except Exception:
        return "unreadable"
    detail = body.get("detail") if isinstance(body, dict) else None
    code = detail.get("code") if isinstance(detail, dict) else (body.get("code") if isinstance(body, dict) else None)
    if isinstance(code, str) and 0 < len(code) <= 64 and all(c.isalnum() or c in "_-" for c in code):
        return code
    return "unrecognized"


def _refusal_kind(status: int, credential_state: str, reason: str) -> str:
    if status == 401:
        return "credential_rejected" if credential_state == "attached" else "no_credential_sent"
    if status == 403:
        return "route_has_no_authorization_contract" if reason == "route_quarantined" else "service_or_scope_not_eligible"
    if 300 <= status < 400:
        return "redirect_not_followed"
    return "other"


def _http_get_json(url: str) -> Any:
    headers, credential_state = _cloud_headers(url)
    req = request.Request(url, method="GET", headers=headers)
    try:
        with _urlopen(req, 15) as response:
            code = response.getcode()
            if code != 200:
                raise CloudReadError("error", code)
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        status = exc.code
        if status in (401, 403) or 300 <= status < 400:
            reason = _refusal_code(exc) if status in (401, 403) else "redirect"
            raise CloudReadError("refused", status, _refusal_kind(status, credential_state, reason), reason) from None
        raise CloudReadError("unavailable" if status >= 500 else "error", status) from None
    except error.URLError:
        raise CloudReadError("unavailable") from None
    except (ValueError, UnicodeDecodeError):
        raise CloudReadError("error", reason="unreadable_body") from None


def _http_post_json(url: str, body: dict[str, Any]) -> None:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    local_key = os.environ.get("FORGE_COST_SYNC_LOCAL_API_KEY", "").strip()
    if local_key:
        headers["Authorization"] = f"Bearer {local_key}"  # the LOCAL key, to the local URL only
    req = request.Request(url, data=data, method="POST", headers=headers)
    try:
        with _urlopen(req, 15) as response:
            code = response.getcode()
            if code not in (200, 201):
                raise LocalWriteError("rejected" if 400 <= code < 500 else "unavailable", code)
    except error.HTTPError as exc:
        raise LocalWriteError("rejected" if 400 <= exc.code < 500 else "unavailable", exc.code) from None
    except error.URLError:
        raise LocalWriteError("unavailable") from None


# --- result ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SyncResult:
    fetched: int
    synced: int
    skipped: int
    failed: int
    watermark: str | None
    #: True only if every window needed was listed in full and every row was mirrored or already seen.
    complete: bool = True
    #: A fixed code when ``complete`` is False: ``cloud_read_refused``, ``cloud_read_unavailable``,
    #: ``cloud_read_error``, ``listing_incomplete``, ``window_limit``, ``cloud_entry_malformed``,
    #: ``another_pass_running``, ``local_write_rejected`` or ``local_write_unavailable``.
    stopped_reason: str | None = None
    #: Fixed detail for a refusal: ``{"status": 403, "refusal_kind": "...", "reason": "..."}``.
    failure: dict[str, Any] | None = None
    source: str = _SOURCE
    #: When a pass last completed (heartbeat), or None if none has. Not "when a row was last mirrored".
    last_successful_sync: str | None = None
    age_seconds: float | None = None
    #: The time the last COMPLETE pass scanned through: every row visible then, up to this time, is mirrored.
    covered_through: str | None = None
    #: How old that coverage is. Larger than ``age_seconds`` by about the commit lag.
    coverage_age_seconds: float | None = None


def exit_code_for(result: SyncResult) -> int:
    """0 only for a complete pass. A scheduler (cron, systemd) then shows an incomplete pass as a failure."""
    return 0 if result.complete else 1


class CostLedgerSyncWorker:
    """Pull cloud cost entries and mirror the unseen ones into DataForge-Local."""

    WATERMARK_SQL = "SELECT max(created_at) FROM cost_sync.seen"
    HEARTBEAT_READ_SQL = "SELECT synced_at FROM cost_sync.seen WHERE cloud_id = %(cloud_id)s"
    HEARTBEAT_WRITE_SQL = (
        "INSERT INTO cost_sync.seen (cloud_id, created_at, synced_at) "
        "VALUES (%(cloud_id)s, %(created_at)s, NOW()) "
        "ON CONFLICT (cloud_id) DO UPDATE SET synced_at = NOW()"
    )
    PASS_LOCK_SQL = "SELECT pg_try_advisory_lock(%(key)s)"
    PASS_UNLOCK_SQL = "SELECT pg_advisory_unlock(%(key)s)"
    COVERAGE_WRITE_SQL = (
        "INSERT INTO cost_sync.seen (cloud_id, created_at, synced_at) "
        "VALUES (%(cloud_id)s, %(created_at)s, %(covered_through)s) "
        "ON CONFLICT (cloud_id) DO UPDATE SET synced_at = %(covered_through)s"
    )
    SEEN_SQL = "SELECT cloud_id FROM cost_sync.seen WHERE cloud_id = ANY(%(ids)s)"
    MARK_SEEN_SQL = (
        "INSERT INTO cost_sync.seen (cloud_id, created_at) "
        "VALUES (%(cloud_id)s, %(created_at)s) "
        "ON CONFLICT (cloud_id) DO NOTHING"
    )

    # -- one pass --------------------------------------------------------------------------------
    def sync_once(self, connection: DbConnection) -> SyncResult:
        if not self._acquire_pass_lock(connection):
            return self._result(connection, _utcnow(), stopped="another_pass_running")
        try:
            return self._sync_pass(connection)
        finally:
            self._release_pass_lock(connection)

    def _sync_pass(self, connection: DbConnection) -> SyncResult:
        now = _utcnow()
        lag = timedelta(seconds=_int_env("FORGE_COST_SYNC_LAG_SECONDS", 120, 0, 3600))
        window = timedelta(hours=_int_env("FORGE_COST_SYNC_WINDOW_HOURS", 24, 1, 168))
        horizon = now - lag
        watermark = self._watermark(connection)
        overlap = timedelta(hours=_int_env("FORGE_COST_SYNC_OVERLAP_HOURS", 6, 0, 168))
        cursor = (watermark - overlap) if watermark else (now - timedelta(days=_int_env("FORGE_COST_SYNC_LOOKBACK_DAYS", 30, 1, 3650)))

        fetched = synced = skipped = failed = 0
        stopped: str | None = None
        failure: dict[str, Any] | None = None
        windows = 0

        while cursor <= horizon:
            windows += 1
            if windows > _MAX_WINDOWS:
                stopped = "window_limit"
                break
            win_end = min(cursor + window, horizon)
            try:
                entries, listed_in_full = self._fetch_window(cursor, win_end)
            except CloudReadError as exc:
                stopped = f"cloud_read_{exc.kind}"
                failure = {"status": exc.status, "refusal_kind": exc.refusal_kind, "reason": exc.reason}
                break
            fetched += len(entries)
            if not listed_in_full:
                # A partial listing is missing its OLDEST rows. Mirroring the rest would move the
                # checkpoint past them, so nothing from this window is written.
                stopped = "listing_incomplete"
                break
            keyed: list[tuple[datetime, str, dict[str, Any]]] = []
            for entry in entries:
                created = _parse_dt(entry.get("created_at"))
                if created is None or "id" not in entry or str(entry["id"]) in _RESERVED_IDS:
                    stopped = "cloud_entry_malformed"
                    break
                keyed.append((created, str(entry["id"]), entry))
            if stopped:
                break
            keyed.sort(key=lambda item: (item[0], item[1]))
            seen = self._seen_ids(connection, [cid for _, cid, _ in keyed])
            for created, cloud_id, entry in keyed:
                if cloud_id in seen:
                    skipped += 1
                    continue
                try:
                    self._post_local(entry)
                except Exception as exc:  # stop at the first row that cannot be mirrored
                    kind = exc.kind if isinstance(exc, LocalWriteError) else "unavailable"
                    print(f"COST SYNC local write {kind} for {cloud_id}")
                    failed += 1
                    stopped = f"local_write_{kind}"
                    failure = {"status": getattr(exc, "status", None), "refusal_kind": None, "reason": kind}
                    break
                self._mark_seen(connection, cloud_id, created)
                connection.commit()  # one row at a time: a crash can only affect the row in flight
                seen.add(cloud_id)
                synced += 1
            if stopped:
                break
            if win_end >= horizon:
                break
            cursor = win_end

        complete = stopped is None
        if complete:
            self._write_heartbeat(connection)
            self._write_coverage(connection, horizon)
            connection.commit()
        return self._result(
            connection, now, fetched=fetched, synced=synced, skipped=skipped, failed=failed, stopped=stopped, failure=failure
        )

    def _result(
        self,
        connection: DbConnection,
        now: datetime,
        *,
        fetched: int = 0,
        synced: int = 0,
        skipped: int = 0,
        failed: int = 0,
        stopped: str | None = None,
        failure: dict[str, Any] | None = None,
    ) -> SyncResult:
        last_sync, age = self._last_successful_sync(connection, now)
        covered, covered_age = self._covered_through(connection, now)
        final_watermark = self._watermark(connection)
        return SyncResult(
            fetched=fetched,
            synced=synced,
            skipped=skipped,
            failed=failed,
            watermark=final_watermark.isoformat() if final_watermark else None,
            complete=stopped is None,
            stopped_reason=stopped,
            failure=failure,
            last_successful_sync=last_sync.isoformat() if last_sync else None,
            age_seconds=age,
            covered_through=covered.isoformat() if covered else None,
            coverage_age_seconds=covered_age,
        )

    # -- status ----------------------------------------------------------------------------------
    def status(self, connection: DbConnection) -> dict[str, Any]:
        """Freshness without reading the cloud: the last completed pass, its age, and the checkpoint."""
        now = _utcnow()
        last_sync, age = self._last_successful_sync(connection, now)
        covered, covered_age = self._covered_through(connection, now)
        watermark = self._watermark(connection)
        return {
            "source": _SOURCE,
            "last_successful_sync": last_sync.isoformat() if last_sync else None,
            "age_seconds": age,
            "covered_through": covered.isoformat() if covered else None,
            "coverage_age_seconds": covered_age,
            "watermark": watermark.isoformat() if watermark else None,
            "freshness_known": last_sync is not None,
        }

    # -- runtime-owned dedup state ---------------------------------------------------------------
    def _watermark(self, connection: DbConnection) -> datetime | None:
        cursor = connection.cursor()
        cursor.execute(self.WATERMARK_SQL, {})
        rows = cursor.fetchall()
        value = rows[0][0] if rows and rows[0][0] is not None else None
        # The heartbeat row has created_at = epoch. It is not a checkpoint.
        return None if value is None or _parse_dt(value) == _EPOCH else _parse_dt(value)

    def _seen_ids(self, connection: DbConnection, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        cursor = connection.cursor()
        cursor.execute(self.SEEN_SQL, {"ids": ids})
        return {str(row[0]) for row in cursor.fetchall()}

    def _mark_seen(self, connection: DbConnection, cloud_id: str, created_at: datetime) -> None:
        cursor = connection.cursor()
        cursor.execute(self.MARK_SEEN_SQL, {"cloud_id": cloud_id, "created_at": created_at})

    def _write_heartbeat(self, connection: DbConnection) -> None:
        cursor = connection.cursor()
        cursor.execute(self.HEARTBEAT_WRITE_SQL, {"cloud_id": _HEARTBEAT_ID, "created_at": _EPOCH})

    def _write_coverage(self, connection: DbConnection, covered_through: datetime) -> None:
        cursor = connection.cursor()
        cursor.execute(
            self.COVERAGE_WRITE_SQL, {"cloud_id": _COVERAGE_ID, "created_at": _EPOCH, "covered_through": covered_through}
        )

    def _read_sentinel_time(self, connection: DbConnection, now: datetime, cloud_id: str) -> tuple[datetime | None, float | None]:
        cursor = connection.cursor()
        cursor.execute(self.HEARTBEAT_READ_SQL, {"cloud_id": cloud_id})
        rows = cursor.fetchall()
        value = _parse_dt(rows[0][0]) if rows and rows[0][0] is not None else None
        return value, ((now - value).total_seconds() if value else None)

    def _last_successful_sync(self, connection: DbConnection, now: datetime) -> tuple[datetime | None, float | None]:
        return self._read_sentinel_time(connection, now, _HEARTBEAT_ID)

    def _covered_through(self, connection: DbConnection, now: datetime) -> tuple[datetime | None, float | None]:
        return self._read_sentinel_time(connection, now, _COVERAGE_ID)

    # -- single flight ---------------------------------------------------------------------------
    def _acquire_pass_lock(self, connection: DbConnection) -> bool:
        cursor = connection.cursor()
        cursor.execute(self.PASS_LOCK_SQL, {"key": _PASS_LOCK_KEY})
        rows = cursor.fetchall()
        return bool(rows and rows[0][0] is True)

    def _release_pass_lock(self, connection: DbConnection) -> None:
        try:
            connection.cursor().execute(self.PASS_UNLOCK_SQL, {"key": _PASS_LOCK_KEY})
        except Exception:  # noqa: BLE001 - the lock also ends with the connection
            pass

    # -- cloud read (source of truth) ------------------------------------------------------------
    def _fetch_window(self, start: datetime, end: datetime) -> tuple[list[dict[str, Any]], bool]:
        """Every row with ``start <= created_at <= end``, and whether the listing is complete.

        Complete means: the page walk ended before the safety bound, the row count equals the cloud's
        ``total``, and no id appears twice (a repeat means the paging moved under us).
        """
        limit = _int_env("FORGE_COST_SYNC_PAGE_LIMIT", 200, 1, 200)
        collected: list[dict[str, Any]] = []
        offset = 0
        total: int | None = None
        reached_end = False
        while True:
            query = parse.urlencode(
                {"since": start.isoformat(), "until": end.isoformat(), "limit": limit, "offset": offset}
            )
            payload = _http_get_json(f"{_cloud_base_url()}/api/v1/costs/entries?{query}")
            items = payload.get("items", []) if isinstance(payload, dict) else []
            if total is None and isinstance(payload, dict) and isinstance(payload.get("total"), int):
                total = payload["total"]
            collected.extend(items)
            if len(items) < limit:
                reached_end = True
                break
            if offset >= _MAX_OFFSET:
                break
            offset += limit
        ids = [str(item.get("id")) for item in collected]
        in_full = reached_end and len(set(ids)) == len(ids) and (total is None or total == len(collected))
        return collected, in_full

    # -- local write (through DataForge-Local's public API) --------------------------------------
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
