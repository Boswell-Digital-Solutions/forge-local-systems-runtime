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

**A pass is complete only if** every window was listed in full (the row count equals the cloud's
`total`, no id repeats, and the page walk ended before the safety bound) and every row was mirrored or
already seen. Otherwise `complete` is false and `stopped_reason` is one of `cloud_read_refused`,
`cloud_read_unavailable`, `cloud_read_error`, `listing_incomplete`, `window_limit`,
`cloud_entry_malformed`, `local_write_rejected` or `local_write_unavailable`. A refused cloud read adds a
fixed `refusal_kind` (`no_credential_sent`, `credential_rejected`, `service_or_scope_not_eligible`,
`route_has_no_authorization_contract`, `redirect_not_followed`). A refused or unreadable cloud read
changes nothing locally and moves no checkpoint. A rejected row (a 4xx from the destination) blocks the
sync visibly. It is not skipped.

**What it does NOT guarantee: exactly-once.** The destination gives every call a new id and has no
source id. If the process dies after the local write and before the dedup record, the next pass writes
that row again. The window is one row. Closing it needs a destination contract (an optional
`source_entry_id` with a unique index on DataForge-Local's `cost_ledger`). That is a proposal and not
part of the implementation (`docs/KNOWN_ISSUES.md`, `FLS-COST-SYNC-NOT-EXACTLY-ONCE-20261013`).

**Freshness and failure state.** `scripts/run_cost_sync_worker.py` prints a JSON summary: `source`,
`watermark`, `last_successful_sync` (the last COMPLETE pass, kept as a heartbeat row with id
`__sync_heartbeat__` in `cost_sync.seen`, created_at = epoch so it never moves the checkpoint),
`age_seconds`, `complete`, `stopped_reason` and `failure`. Its exit code is 0 only for a complete pass.
`CostLedgerSyncWorker.status(connection)` reads the same freshness without calling the cloud. A reader of
DataForge-Local's ledger **cannot see this state**: the ledger routes carry no freshness field. See
`dataforge-Local` `DLO-COST-REPLICA-NO-FRESHNESS-20261013`.

Dedup / run: `cost_sync.seen` (migration `004_cost_ledger_sync_seen.sql`) holds each cloud entry id
once it is mirrored. Run one pass with `scripts/run_cost_sync_worker.py` on a schedule: the same
one-pass-per-invocation model as the runtime-promotion worker.

Environment variables: `DATAFORGE_URL` (cloud base; default the cloud Render URL),
`DATAFORGE_LOCAL_URL` (default `http://127.0.0.1:8005`), `FORGE_COST_SYNC_CLOUD_API_KEY`,
`FORGE_COST_SYNC_LOCAL_API_KEY`, `FORGE_COST_SYNC_LOOKBACK_DAYS` (first run, default 30),
`FORGE_COST_SYNC_PAGE_LIMIT` (1..200, default 200), `FORGE_COST_SYNC_WINDOW_HOURS` (1..168, default 24),
`FORGE_COST_SYNC_LAG_SECONDS` (0..3600, default 120).

