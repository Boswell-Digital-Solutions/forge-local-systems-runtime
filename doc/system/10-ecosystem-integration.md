## 10. Ecosystem Integration

This baseline section should be expanded with concrete downstream and upstream dependencies as they are documented.

### 10.1 Current Status

| Surface | Status |
| --- | --- |
| Shared service integrations | Expand as concrete integrations are cataloged |
| Cross-repo boundaries | Keep explicit as this repo's authority boundary is clarified |
| Cost Ledger Sync (cloud → DataForge-Local) | Implemented — see 10.2 |

### 10.2 Cost Ledger Sync (cloud → DataForge-Local)

`cost_sync/worker.py` (`CostLedgerSyncWorker`) mirrors cloud DataForge's per-inference `cost_ledger`
into DataForge-Local so Forge_Command can read per-model inference cost locally (local-first).
**Cloud DataForge remains the single source of truth for cost.** The worker only READS cloud and
WRITES to DataForge-Local through their public APIs. It never writes to either service's database
directly, so each system's DB-authority boundary holds.

| Direction | Endpoint (base URL env) | Credential |
| --- | --- | --- |
| Read (source of truth) | cloud `GET /api/v1/costs/entries` (`DATAFORGE_URL`) | `FORGE_COST_SYNC_CLOUD_API_KEY`: DataForge scope `costs:read` on the service `forge_local_runtime`. HTTPS or loopback only. Redirects are never followed. |
| Write (mirror) | DataForge-Local `POST /api/v1/costs/record` (`DATAFORGE_LOCAL_URL`) | none today (DataForge-Local does not authenticate this route). An optional `FORGE_COST_SYNC_LOCAL_API_KEY` goes to the local URL only. |

The two keys are never used for each other's destination. No cloud write scope is needed or granted.

**What one pass guarantees.** The pass reads the cloud ledger in time windows (default 24 hours), oldest
window first, and mirrors each window oldest row first. It stops at the first row it cannot mirror, so the
checkpoint (`max(created_at)` in `cost_sync.seen`) is always a contiguous prefix: every older row is
mirrored, and a failed row is retried by the next pass. Rows newer than a commit-lag horizon (default
120 seconds) wait for the next pass. The dedup record is committed after every row.

**The cloud paging contract.** The worker depends on this contract of `GET /api/v1/costs/entries`
(`list_cost_entries` in cloud DataForge). Both `since` and `until` are inclusive. `total` is a separate
count. The rows are in `created_at DESC` order, with `offset` and `limit`. Before the DataForge change
`security/cost-ledger-ordering` (not deployed) that order is **not unique**. Rows with an equal
`created_at` can come back in a different order on each request. Then one row repeats on one page and
another row is missing from every page. The worker cannot fix this by sorting the pages. It detects the
repeat, calls the window incomplete (`listing_incomplete`) and writes nothing from that window. If the
wrong order is the same on every pass, the sync stays blocked on that window. The block is visible (exit
code 1). The fix is `ORDER BY created_at DESC, id DESC` on the server.

**One pass at a time.** A pass takes a PostgreSQL session advisory lock on the runtime database. A second
pass that starts while the first runs writes nothing. It reports `another_pass_running` and exits 1.
Without the lock, two workers both write the same unseen row to the destination. The lock ends with the
connection, so a crash does not leave it set. It does not work through a transaction-mode pooler.

**Overlap re-scan.** A pass starts `FORGE_COST_SYNC_OVERLAP_HOURS` (default 6) before the checkpoint. A row
that becomes visible late, with a `created_at` before the checkpoint, is then mirrored. A row that becomes
visible later than the overlap is **not** found, and the pass still reports complete. That gap is open
(`docs/KNOWN_ISSUES.md`, `FLS-COST-SYNC-ORDER-COVERAGE-20261013`).

**A pass is complete only if** every window was listed in full (the row count equals the cloud's
`total`, no id repeats, and the page walk ended before the safety bound) and every row was mirrored or
already seen. Otherwise `complete` is false and `stopped_reason` is one of `cloud_read_refused`,
`cloud_read_unavailable`, `cloud_read_error`, `listing_incomplete`, `window_limit`,
`cloud_entry_malformed`, `another_pass_running`, `local_write_rejected` or `local_write_unavailable`. A refused cloud read adds a
fixed `refusal_kind` (`no_credential_sent`, `credential_rejected`, `service_or_scope_not_eligible`,
`route_has_no_authorization_contract`, `redirect_not_followed`). A refused or unreadable cloud read
changes nothing locally and moves no checkpoint. A rejected row (a 4xx from the destination) blocks the
sync visibly. It is not skipped.

**What it does NOT guarantee: exactly-once.** The destination gives every call a new id and has no
source id. If the process dies after the local write and before the dedup record, the next pass writes
that row again. The window is one row. Closing it needs a destination contract (an optional
`source_entry_id` with a unique index on DataForge-Local's `cost_ledger`). That is a proposal and not
part of the implementation (`docs/KNOWN_ISSUES.md`, `FLS-COST-SYNC-NOT-EXACTLY-ONCE-20261013`).

**Freshness is coverage.** Fresh data means the replica covers the source up to a known time. It does not
mean the worker ran, or that it copied a row. `scripts/run_cost_sync_worker.py` prints a JSON summary:
`source`, `watermark` (the newest mirrored row), `covered_through` (the time the last COMPLETE pass scanned
through, which is `now - lag` at that pass), `coverage_age_seconds`, `last_successful_sync` (when that pass
ended), `age_seconds`, `complete`, `stopped_reason` and `failure`. A pass that mirrored rows and then stopped
moves `watermark`. It does not move `covered_through` or `last_successful_sync`. Its exit code is 0 only for
a complete pass. `CostLedgerSyncWorker.status(connection)` reads the same state without calling the cloud.

The two values are kept as sentinel rows in `cost_sync.seen`: `__sync_heartbeat__` (`synced_at` is the end of
the last complete pass) and `__sync_covered_through__` (`synced_at` holds the covered-through time). Both
have `created_at` = epoch, so they never move the checkpoint. The worker refuses a cloud row that has one
of these ids (`cloud_entry_malformed`), because it would read as already mirrored. Sentinel rows are not
ledger rows. The write to DataForge-Local carries the ledger fields only. The stored coverage is one
time. It has no start of the range and no list of confirmed windows. That needs a table of its own, which is
a proposal (`FLS-COST-SYNC-ORDER-COVERAGE-20261013`).
 A reader of
DataForge-Local's ledger **cannot see this state**: the ledger routes carry no freshness field. See
`dataforge-Local` `DLO-COST-REPLICA-NO-FRESHNESS-20261013`.

Dedup / run: `cost_sync.seen` (migration `004_cost_ledger_sync_seen.sql`) holds each cloud entry id
once it is mirrored. Run one pass with `scripts/run_cost_sync_worker.py` on a schedule: the same
one-pass-per-invocation model as the runtime-promotion worker.

Tests: `tests/test_cost_sync_postgres.py` runs the worker on a throwaway PostgreSQL with the real migration 004. It
starts the server itself on a unix socket and no TCP port. It finds `initdb` through `COST_SYNC_TEST_PG_BIN`, the
`PATH` or `/usr/lib/postgresql/*/bin`, and it skips with a stated reason if there is none. The cloud and
DataForge-Local are loopback HTTP fakes (`tests/cost_sync_support.py`) that follow the paging contract above.
The older tests in `tests/test_cost_sync_*.py` use a fake connection and need no server.

### Runtime promotion receipt credential (2026-10-13; local branch, not deployed)

The runtime promotion worker (`runtime_promotion/worker.py`) posts each receipt to
`POST /api/v1/runtime-promotion/receipts/local-failure-pattern`. DataForge needs a service key for the service
`forge_local_runtime` with the scope `runtime-promotion:receipts:write`. The worker reads that key from its own variable
`FORGE_RUNTIME_PROMOTION_RECEIPT_API_KEY`. It reads no other variable for this purpose: not
`FORGE_COST_SYNC_CLOUD_API_KEY` (scope `costs:read`), not `FORGE_COST_SYNC_LOCAL_API_KEY`, not a shared DataForge key,
and not an administrative token. One identity holds two credentials, and neither credential has the other's permission.
`FORGE_RUNTIME_PROMOTION_RECEIPT_URL` may override the destination. The default is the loopback URL in the module.
The key goes only over HTTPS or to a loopback host, and a redirect is never followed. With no key set, no credential is sent,
DataForge answers 401, and the artifact is released for retry as before. A refusal is reported with fixed codes (status,
credential state, reason code). The message never holds the key or the response body.

Environment variables: `DATAFORGE_URL` (cloud base; default the cloud Render URL),
`DATAFORGE_LOCAL_URL` (default `http://127.0.0.1:8005`), `FORGE_COST_SYNC_CLOUD_API_KEY`,
`FORGE_COST_SYNC_LOCAL_API_KEY`, `FORGE_COST_SYNC_LOOKBACK_DAYS` (first run, default 30),
`FORGE_COST_SYNC_PAGE_LIMIT` (1..200, default 200), `FORGE_COST_SYNC_WINDOW_HOURS` (1..168, default 24),
`FORGE_COST_SYNC_LAG_SECONDS` (0..3600, default 120), `FORGE_COST_SYNC_OVERLAP_HOURS` (0..168, default 6).

