        # forge-local-systems-runtime - Compiled System Reference

        **Designation:** FLS
        **Document role:** Canonical compiled technical reference for the Forge local systems runtime
        **Source:** `doc/system/`
        **Build command:** `bash doc/system/BUILD.sh`
        **Document version:** 2.0 (2026-06-22) - canonical compliance migration
        **Protocol:** BDS Documentation Protocol v2.0; BDS Repo Documentation System Canonical Compliance Standard

        > **Generated artifact warning:** `doc/FLSSYSTEM.md` is assembled output. Edit
        > the source modules under `doc/system/` and rebuild. Hand edits to the
        > compiled artifact are overwritten by the next build.

        Assembly contract:

        - Command: `bash doc/system/BUILD.sh`
        - Validation: `bash doc/system/validate_snapshots.sh` runs during assembly
        - Primary output: `doc/FLSSYSTEM.md`

        This `doc/system/` tree is the canonical source of truth for forge-local-systems-runtime. It uses
        explicit **truth classes**: canonical facts define repo role, authority
        boundaries, contract behavior, runtime behavior, and verification doctrine;
        snapshot facts are dated, audit-derived counts and current implementation
        inventory that may drift between audits.

        | Part | File | Contents |
        | --- | --- | --- |
        | §1 | `00-overview.md` | Overview |
| §2 | `01-architecture.md` | Architecture |
| §3 | `01-overview-philosophy.md` | 1. Overview & Philosophy |
| §4 | `02-architecture.md` | 2. Architecture |
| §5 | `04-project-structure.md` | 4. Project Structure |
| §6 | `08-api-layer.md` | 8. API Layer |
| §7 | `10-ecosystem-integration.md` | 10. Ecosystem Integration |
| §8 | `07-frontend.md` | 7. Frontend |
| §9 | `09-backend.md` | 9. Backend |
| §10 | `11-database-schema.md` | 11. Database Schema |
| §11 | `12-ai-integration.md` | 12. AI Integration |
| §12 | `13-error-handling.md` | 13. Error Handling Contract |
| §13 | `03-tech-stack.md` | 3. Tech Stack |
| §14 | `06-design-system.md` | 6. Design System |
| §15 | `10-scope.md` | Scope |
| §16 | `30-governance.md` | Governance |
| §17 | `40-change-control.md` | Change Control |
| §18 | `05-configuration.md` | 5. Configuration & Environment |
| §19 | `14-testing-infrastructure.md` | 14. Testing Infrastructure |
| §20 | `15-handover-migration-notes.md` | 15. Handover / Migration Notes |
| §21 | `20-structure.md` | Structure |
| §22 | `90-appendices.md` | Appendices |

        ## Quick Assembly

        ```bash
        bash doc/system/BUILD.sh
        ```

---

# Overview

> **System identity — bds family (Boswell Digital Solutions business system, local-systems tier).** forge-local-systems-runtime is the governance-first constitutional repository for the shared local service substrate of the Forge ecosystem backend, in `ecosystem/local-systems`. It is **not** the Forge counterpart `apps/public-app-local-support/forge-local-runtime-master-reference`.

**Document version:** 1.0 (bootstrap scaffold)

System identity, role, and boundary with the rest of the Forge ecosystem.

> This chapter is a registry-generated bootstrap scaffold for a
> `documentation` class documentation system. Replace this placeholder with
> real authored content. Registry will not invent repo truth that is not
> already present in the repo.

---

# Architecture

**Document version:** 1.0 (bootstrap scaffold)

High-level architecture, authority posture, and surface ownership.

> This chapter is a registry-generated bootstrap scaffold for a
> `documentation` class documentation system. Replace this placeholder with
> real authored content. Registry will not invent repo truth that is not
> already present in the repo.

---

## 1. Overview & Philosophy

Forge Local Runtime is currently documented through a baseline protocol-adoption pass.
This section records only repository surfaces directly observable from the working tree.

### 1.1 Current Posture

| Topic | Current truth |
| --- | --- |
| Repo | `forge-local-runtime` |
| Protocol status | Baseline adoption in progress |
| Canonical technical reference | `doc/system/` plus generated root `SYSTEM.md` |
| Current scope | Expand this section as product and service boundaries are cataloged |

---

## 2. Architecture

This baseline architecture section records the major repo surfaces present today.

### 2.1 Observed Top-Level Areas

```text
forge-local-runtime/
├── .mypy_cache/
├── .vscode/
├── DECISIONS/
├── db/
├── doc/
├── docs/
├── runtime_promotion/
├── schemas/
├── scripts/
├── tests/
```

---

## 3. Tech Stack

This baseline stack inventory is inferred from repository markers and directory layout.

### 3.1 Detected Surfaces

| Layer | Marker | Current interpretation |
| --- | --- | --- |
| Persistence / Schemas | `alembic/`, `migrations/`, `db/`, `sql/`, `models/`, or `schemas/` present | Database, migration, or schema layer detected |

---

## 4. Project Structure

### 4.1 Directory Layout

```text
forge-local-runtime/
├── .mypy_cache/
├── .vscode/
├── DECISIONS/
├── db/
├── doc/
├── docs/
├── runtime_promotion/
├── schemas/
├── scripts/
├── tests/
```

### 4.2 Documentation Rule

- `doc/system/` is the canonical modular source for the root `SYSTEM.md`
- `scripts/context-bundle.sh` is the selective context assembly surface
- `CLAUDE.md` is the repo-local AI instruction file

---

## 5. Configuration & Environment

This baseline section has not yet enumerated every environment variable or configuration file.

### 5.1 Current Status

| Surface | Status |
| --- | --- |
| Environment variable inventory | Not yet expanded in this baseline |
| Config ownership mapping | Not yet expanded in this baseline |
| Protocol requirement | Every env var must be documented here as this repo matures |

---

## 6. Design System

This section is a placeholder unless a UI surface is present in the current repo.

### 6.1 Current Status

| Surface | Status |
| --- | --- |
| Design tokens | Expand when UI tokens are inventoried |
| Component patterns | Expand when UI components are cataloged |
| Brand posture | Keep this section grounded in implemented UI reality only |

---

## 7. Frontend

No obvious frontend surface was detected from the current top-level directory layout.

### 7.1 Current Status

| Surface | Status |
| --- | --- |
| UI routing and component inventory | Expand from current source files as the repo is cataloged |
| Desktop shell / browser surface | Record here only if implemented in the repo |

---

## 8. API Layer

No obvious dedicated API directory was detected from the current top-level directory layout.

### 8.1 Current Status

| Surface | Status |
| --- | --- |
| Endpoint inventory | Expand with real routes and shapes if this repo exposes APIs |
| Middleware and auth | Expand when the transport contract is cataloged |

---

## 9. Backend

This baseline section records the backend or core runtime surfaces detectable from the repo layout.

### 9.1 Observed Runtime Areas

| Surface | Current interpretation |
| --- | --- |
| Core runtime | Expand from `app/`, `service/`, `cortex_runtime/`, `crates/`, or `src-tauri/` as applicable |
| Delivery posture | Keep this section aligned with implemented code, not roadmap intent |

---

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

Environment variables: `DATAFORGE_URL` (cloud base; default the cloud Render URL),
`DATAFORGE_LOCAL_URL` (default `http://127.0.0.1:8005`), `FORGE_COST_SYNC_CLOUD_API_KEY`,
`FORGE_COST_SYNC_LOCAL_API_KEY`, `FORGE_COST_SYNC_LOOKBACK_DAYS` (first run, default 30),
`FORGE_COST_SYNC_PAGE_LIMIT` (1..200, default 200), `FORGE_COST_SYNC_WINDOW_HOURS` (1..168, default 24),
`FORGE_COST_SYNC_LAG_SECONDS` (0..3600, default 120), `FORGE_COST_SYNC_OVERLAP_HOURS` (0..168, default 6).


---

# Scope

**Document version:** 1.0 (bootstrap scaffold)

Scope and authority boundary of this documentation system.

> This chapter is a registry-generated bootstrap scaffold for a
> `documentation` class documentation system. Replace this placeholder with
> real authored content. Registry will not invent repo truth that is not
> already present in the repo.

---

## 11. Database Schema

Database, schema, or migration surfaces are present in the repository tree.

### 11.1 Current Status

| Surface | Status |
| --- | --- |
| Table inventory | Expand with real table, column, and constraint definitions |
| Migration contract | Expand if this repo owns migrations or persistent schemas |

---

## 12. AI Integration

No obvious AI-specific directory was detected from the current top-level layout.

### 12.1 Current Status

| Surface | Status |
| --- | --- |
| Prompt or model routing docs | Expand as concrete AI surfaces are cataloged |
| Transparency and fallback posture | Record here when the current runtime contract is documented |

---

## 13. Error Handling Contract

Current error-handling documentation is a baseline only.

### 13.1 Baseline Law

- fail closed on missing documentation truth, malformed inputs, and unsupported runtime states
- document real error envelopes here as soon as they are cataloged from code or tests

---

## 14. Testing Infrastructure

This baseline section records only that testing surfaces exist in the repository tree.

### 14.1 Current Status

| Surface | Status |
| --- | --- |
| `tests/` directory | Present |
| QA expansion | Expand with concrete commands, suites, and pre-flight checks as they are cataloged |

---

## 15. Handover / Migration Notes

This repository entered a baseline documentation-protocol migration on 2026-04-03.

### 15.1 Current Migration Note

- modular `doc/system/` was established or normalized to support root `SYSTEM.md`
- further authored expansion is still required for exact APIs, schemas, and runtime contracts

---

# Structure

**Document version:** 1.0 (bootstrap scaffold)

Module/chapter layout and cross-reference rules.

> This chapter is a registry-generated bootstrap scaffold for a
> `documentation` class documentation system. Replace this placeholder with
> real authored content. Registry will not invent repo truth that is not
> already present in the repo.

---

# Governance

**Document version:** 1.0 (bootstrap scaffold)

Ownership, review, and change-authority boundaries.

> This chapter is a registry-generated bootstrap scaffold for a
> `documentation` class documentation system. Replace this placeholder with
> real authored content. Registry will not invent repo truth that is not
> already present in the repo.

---

# Change Control

**Document version:** 1.0 (bootstrap scaffold)

Change-control workflow, proposal lifecycle, and audit.

> This chapter is a registry-generated bootstrap scaffold for a
> `documentation` class documentation system. Replace this placeholder with
> real authored content. Registry will not invent repo truth that is not
> already present in the repo.

---

# Appendices

**Document version:** 1.0 (carry-forward)

Appendices, glossary, and cross-references.

## Unmapped legacy chapters

The following legacy chapters were carried forward but could not be
deterministically mapped to a class-aware slot. Review and place them by
hand:

- `Forge Local Systems Runtime — Complete System Reference`
