# Known Issues

Repository-level findings. Each entry has a date, what is wrong, the cause, and an open or closed scope.

## The cost sync worker lost rows in two cases and reported success (Closed in the local branch 2026-10-13, not pushed) — FLS-COST-SYNC-LOST-ROWS-20261013

- **Location**: `cost_sync/worker.py`, `scripts/run_cost_sync_worker.py`.
- **Case A, reproduced on `c123d0e`:** when an earlier row failed its local write and a later row succeeded, the checkpoint (`max(created_at)` in `cost_sync.seen`) moved past the earlier row. The next pass asked the cloud only for rows from the checkpoint onward, so the earlier row was **never retried**. Evidence: run 1 mirrored `c2` and failed `c1`; run 2 fetched 1 row and did not recover `c1`.
- **Case C, reproduced on `c123d0e`:** when a window held more rows than the safety bound (`_MAX_OFFSET`), the page walk stopped, the worker mirrored the newest rows it had, and the checkpoint moved past the OLDEST rows it never saw. Evidence: 8 cloud rows, 6 mirrored, `SyncResult` showed `synced=6` with no sign of incompleteness, and the 2 oldest rows were missing forever.
- **Also found:** the runner committed once after the whole pass and rolled back on any exception, so a crash mid-pass discarded the dedup records of every row already posted and the next pass posted them all again.
- **Fix (branch):** time windows, oldest first, with a stop at the first row that cannot be mirrored; a pass is `complete` only if every listing matched the cloud's `total`; the dedup record is committed after every row; the runner exits non-zero for an incomplete pass. 29 tests, 12 of 12 mutations caught. The evidence scripts and their SHA-256 are in the operator's evidence folder named in the HANDOFF section of 2026-10-13.
- **Not fixed:** a rejected row (a 4xx from the destination) blocks the sync. It is reported and not skipped. A permanent block needs an operator decision.
- **Past loss:** rows that these two cases lost in the past are not recovered by the fix, because the checkpoint is already past them. Whether any were lost is **not known**. A reconciliation against the cloud ledger would show it. Not done.

## The cost sync cannot be exactly-once with today's destination (Open 2026-10-13, retained blocker) — FLS-COST-SYNC-NOT-EXACTLY-ONCE-20261013

- **What is wrong:** DataForge Local's `POST /api/v1/costs/record` gives every call a new id and has no source id. If the worker dies after the local write and before the dedup record, the next pass writes that row again. The ledger then overstates spend by that row. Skipping already-seen ids does not prevent this, because the id is recorded only after the write succeeds.
- **What was done:** the window is one row (the dedup record is committed after every row). `tests/test_cost_sync_recovery.py::test_B_...` documents the duplicate. It is a characterization of a blocker and not a statement that the behavior is acceptable.
- **Exact proposal, NOT authorized, NOT built (a destination contract):** DataForge Local `POST /api/v1/costs/record` accepts an optional `source_entry_id` (UUID); a migration adds a nullable column and a partial unique index on it (`WHERE source_entry_id IS NOT NULL`); the route answers 201 for a new id, 200 with `duplicate: true` for the same id and payload, and 409 for the same id with a different payload; the worker sends the cloud row id. The change is additive and backward compatible. Other writers send null.
- **Rollout effect:** the sync may duplicate a row after a crash. Keep the cost-sync part of the rollout blocked until the contract exists, or until the operator accepts in writing that a crash can add one duplicate row.

## The cost sync code lives where this repository's constitution says implementation must not (Open 2026-10-13) — FLS-COST-SYNC-OUTSIDE-AUTHORITY-20261013

- **What is wrong:** `CLAUDE.md` and `BUILD.md` say this repository "implements nothing — it governs" and must not become "a service executable" or "a convenience sink for service implementation code". The repository holds `cost_sync/` and `runtime_promotion/` (implementation) and `scripts/run_cost_sync_worker.py` (a runner). `BUILD.md` also says "implementation must not outrun authority artifacts". The cost sync worker is named in no authority artifact: not in `docs/services/df-local-foundation-role.md`, not in `docs/architecture/boundary-matrix.md`. It appears only in `doc/system/10-ecosystem-integration.md`.
- **Not changed:** the operator named this runtime as the owner of the cost sync component, so the worker stays here. This pass changed the worker's behavior (credentials, windows, stop rule), which `BUILD.md` says needs its authority artifacts in the same change set. They were **not** updated.
- **Decision for the operator:** (a) amend the constitution to admit `cost_sync/` and `runtime_promotion/` as narrowly justified repo-local tooling, with the required bundle (the role file, the boundary matrix, an ADR in `DECISIONS/`); or (b) move the worker to an implementation repository. Until then `make validate` passes, and it checks neither question.
- **Related doc drift:** `CLAUDE.md` still says "this repo implements nothing". That sentence is untrue today.

## The cost sync worker reads the cloud ledger with no credential, and DataForge will refuse it (Open 2026-10-13) — FLS-COST-SYNC-NO-CREDENTIAL-20261013

- **Location**: `cost_sync/worker.py` (`CostLedgerSyncWorker._fetch_cloud_entries`, `_http_get_json`), run by `scripts/run_cost_sync_worker.py`. Documented in `doc/system/10-ecosystem-integration.md` §10.2.
- **What is wrong**: the worker calls cloud DataForge `GET /api/v1/costs/entries` with a plain `urllib` request and no `Authorization` header. DataForge's route authorization hardening (branch `security/route-authorization-default-deny`, not deployed) classifies that route `legacy_unauthenticated`, which is refused with 403. After the deploy the worker raises `cloud cost read HTTP 403` and mirrors nothing.
- **Effect downstream**: the worker fills DataForge Local's `cost_ledger`. When the worker stops, that table stops growing. DataForge Local keeps answering `200` from its old rows, so a reader sees old cost as current. Forge_Command reads that replica first only when `DATAFORGE_LOCAL_URL` is set where the app starts. The replica has no freshness field (see `dataforge-Local` `DLO-COST-REPLICA-NO-FRESHNESS-20261013`).
- **The worker itself is not silent**: `run_cost_sync_worker.py` rolls back and re-raises, so the process exits non-zero. Whether a cron job or systemd timer runs it on the operator's machine, and whether anyone sees a failed run, is **not verified**.
- **Cause**: the worker predates the hardening. The DataForge branch `security/cost-ledger-scopes` gives `costs:read` to the service `forge_command` only. This worker is a different service, so it has no eligible identity.
- **Status (local branch `feat/cost-sync-recovery`, NOT pushed, NOT merged, NOT deployed):** the worker now sends a cloud read key (`FORGE_COST_SYNC_CLOUD_API_KEY`), and refusals are named with fixed codes. The identity is `forge_local_runtime`, the canonical identity the DataForge registry already holds for this runtime. DataForge's local branch `security/cost-ledger-scopes` lets that identity hold `costs:read` and nothing else. **No key is issued.** Issuing one is an operator step.
- **Still needed before this works in production:** a `costs:read` key for the service `forge_local_runtime` (operator step), the DataForge branch accepted, pushed and deployed (operator steps), and the constitutional documents of this repo (see `FLS-COST-SYNC-OUTSIDE-AUTHORITY-20261013`).
- **Related**: Forge_Command `FC-COSTS-WRITER-UNLISTED-20261013`, inventory row 14.

## A default local database password is tracked in `.env` (Open 2026-10-13) — FLS-TRACKED-ENV-20261013

- **Location**: `.env` at the repository root. Line 1 sets `FORGE_LOCAL_RUNTIME_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/forge_local_runtime`.
- **What is wrong**: the file is tracked. The value is the default PostgreSQL development password on `localhost`, not a production secret. It still teaches the habit of committing `.env`, and a real value could be added to this file later.
- **Not verified**: whether other lines exist beyond line 1 in other branches, and whether the file is intentional.
- **Not changed**: nothing was removed or rewritten. Decision for the operator: keep as a documented sample (rename to `.env.example`), or untrack it.
