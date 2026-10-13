# Known Issues

Repository-level findings. Each entry has a date, what is wrong, the cause, and an open or closed scope.

## The cost sync worker reads the cloud ledger with no credential, and DataForge will refuse it (Open 2026-10-13) — FLS-COST-SYNC-NO-CREDENTIAL-20261013

- **Location**: `cost_sync/worker.py` (`CostLedgerSyncWorker._fetch_cloud_entries`, `_http_get_json`), run by `scripts/run_cost_sync_worker.py`. Documented in `doc/system/10-ecosystem-integration.md` §10.2.
- **What is wrong**: the worker calls cloud DataForge `GET /api/v1/costs/entries` with a plain `urllib` request and no `Authorization` header. DataForge's route authorization hardening (branch `security/route-authorization-default-deny`, not deployed) classifies that route `legacy_unauthenticated`, which is refused with 403. After the deploy the worker raises `cloud cost read HTTP 403` and mirrors nothing.
- **Effect downstream**: the worker fills DataForge Local's `cost_ledger`. When the worker stops, that table stops growing. DataForge Local keeps answering `200` from its old rows, so a reader sees old cost as current. Forge_Command reads that replica first only when `DATAFORGE_LOCAL_URL` is set where the app starts. The replica has no freshness field (see `dataforge-Local` `DLO-COST-REPLICA-NO-FRESHNESS-20261013`).
- **The worker itself is not silent**: `run_cost_sync_worker.py` rolls back and re-raises, so the process exits non-zero. Whether a cron job or systemd timer runs it on the operator's machine, and whether anyone sees a failed run, is **not verified**.
- **Cause**: the worker predates the hardening. The DataForge branch `security/cost-ledger-scopes` gives `costs:read` to the service `forge_command` only. This worker is a different service, so it has no eligible identity.
- **Not changed**: no code. A change needs (1) an operator ruling on the worker's service identity (`forge_local_runtime` is the likely name, because the runtime-promotion worker's receipts carry `source = forge_local_runtime`; no document names it), (2) a DataForge registry change, (3) a key, and (4) code that sends it.
- **Related**: Forge_Command `FC-COSTS-WRITER-UNLISTED-20261013`, inventory row 14.

## A default local database password is tracked in `.env` (Open 2026-10-13) — FLS-TRACKED-ENV-20261013

- **Location**: `.env` at the repository root. Line 1 sets `FORGE_LOCAL_RUNTIME_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/forge_local_runtime`.
- **What is wrong**: the file is tracked. The value is the default PostgreSQL development password on `localhost`, not a production secret. It still teaches the habit of committing `.env`, and a real value could be added to this file later.
- **Not verified**: whether other lines exist beyond line 1 in other branches, and whether the file is intentional.
- **Not changed**: nothing was removed or rewritten. Decision for the operator: keep as a documented sample (rename to `.env.example`), or untrack it.
