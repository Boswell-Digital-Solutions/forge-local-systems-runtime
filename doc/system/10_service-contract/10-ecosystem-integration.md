## 10. Ecosystem Integration

This baseline section should be expanded with concrete downstream and upstream dependencies as they are documented.

### 10.1 Current Status

| Surface | Status |
| --- | --- |
| Shared service integrations | Expand as concrete integrations are cataloged |
| Cross-repo boundaries | Keep explicit as this repo's authority boundary is clarified |
| Cost Ledger Sync (cloud → DataForge-Local) | Implemented — see 10.2 |

### 10.2 Cost Ledger Sync (cloud → DataForge-Local)

`cost_sync/worker.py` (`CostLedgerSyncWorker`) mirrors cloud DataForge's
per-inference `cost_ledger` into DataForge-Local so Forge_Command can read
per-model inference cost locally (local-first). **Cloud DataForge remains the
single source of truth for cost.** The worker only READS cloud and WRITES to
DataForge-Local through their public APIs — it never writes to either service's
database directly, so each system's DB-authority boundary holds.

| Direction | Endpoint (base URL env) | Purpose |
| --- | --- | --- |
| Read (source of truth) | cloud `GET /api/v1/costs/entries` (`DATAFORGE_URL`) | Fetch cost entries newer than the watermark, paginated. |
| Write (mirror) | DataForge-Local `POST /api/v1/costs/record` (`DATAFORGE_LOCAL_URL`) | Insert each unseen entry into the local mirror. |

Dedup / idempotency is runtime-owned: each cloud entry id is recorded in
`cost_sync.seen` (migration `004_cost_ledger_sync_seen.sql`) only after its local
write succeeds; already-seen ids are skipped, so re-runs and overlapping `since`
windows never double-count. Run one pass with `scripts/run_cost_sync_worker.py`
on a schedule — the same one-pass-per-invocation model as the runtime-promotion
worker.

Environment variables: `DATAFORGE_URL` (cloud base; default the cloud Render
URL), `DATAFORGE_LOCAL_URL` (default `http://127.0.0.1:8005`),
`FORGE_COST_SYNC_LOOKBACK_DAYS` (first-run / empty-state window, default 30),
`FORGE_COST_SYNC_PAGE_LIMIT` (cloud page size, 1..200, default 200).
