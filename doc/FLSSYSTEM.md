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
        | §1 | `00_overview/00-overview.md` | Overview |
| §2 | `00_overview/01-architecture.md` | Architecture |
| §3 | `00_overview/01-overview-philosophy.md` | 1. Overview & Philosophy |
| §4 | `00_overview/02-architecture.md` | 2. Architecture |
| §5 | `00_overview/04-project-structure.md` | 4. Project Structure |
| §6 | `10_service-contract/08-api-layer.md` | 8. API Layer |
| §7 | `10_service-contract/10-ecosystem-integration.md` | 10. Ecosystem Integration |
| §8 | `20_runtime/07-frontend.md` | 7. Frontend |
| §9 | `20_runtime/09-backend.md` | 9. Backend |
| §10 | `20_runtime/11-database-schema.md` | 11. Database Schema |
| §11 | `20_runtime/12-ai-integration.md` | 12. AI Integration |
| §12 | `20_runtime/13-error-handling.md` | 13. Error Handling Contract |
| §13 | `30_dependencies/03-tech-stack.md` | 3. Tech Stack |
| §14 | `30_dependencies/06-design-system.md` | 6. Design System |
| §15 | `40_governance/10-scope.md` | Scope |
| §16 | `40_governance/30-governance.md` | Governance |
| §17 | `40_governance/40-change-control.md` | Change Control |
| §18 | `50_operations/05-configuration.md` | 5. Configuration & Environment |
| §19 | `50_operations/14-testing-infrastructure.md` | 14. Testing Infrastructure |
| §20 | `50_operations/15-handover-migration-notes.md` | 15. Handover / Migration Notes |
| §21 | `99_appendices/20-structure.md` | Structure |
| §22 | `99_appendices/90-appendices.md` | Appendices |

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

## 8. API Layer

No obvious dedicated API directory was detected from the current top-level directory layout.

### 8.1 Current Status

| Surface | Status |
| --- | --- |
| Endpoint inventory | Expand with real routes and shapes if this repo exposes APIs |
| Middleware and auth | Expand when the transport contract is cataloged |

---

## 10. Ecosystem Integration

This baseline section should be expanded with concrete downstream and upstream dependencies as they are documented.

### 10.1 Current Status

| Surface | Status |
| --- | --- |
| Shared service integrations | Expand as concrete integrations are cataloged |
| Cross-repo boundaries | Keep explicit as this repo's authority boundary is clarified |

---

## 7. Frontend

No obvious frontend surface was detected from the current top-level directory layout.

### 7.1 Current Status

| Surface | Status |
| --- | --- |
| UI routing and component inventory | Expand from current source files as the repo is cataloged |
| Desktop shell / browser surface | Record here only if implemented in the repo |

---

## 9. Backend

This baseline section records the backend or core runtime surfaces detectable from the repo layout.

### 9.1 Observed Runtime Areas

| Surface | Current interpretation |
| --- | --- |
| Core runtime | Expand from `app/`, `service/`, `cortex_runtime/`, `crates/`, or `src-tauri/` as applicable |
| Delivery posture | Keep this section aligned with implemented code, not roadmap intent |

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

## 3. Tech Stack

This baseline stack inventory is inferred from repository markers and directory layout.

### 3.1 Detected Surfaces

| Layer | Marker | Current interpretation |
| --- | --- | --- |
| Persistence / Schemas | `alembic/`, `migrations/`, `db/`, `sql/`, `models/`, or `schemas/` present | Database, migration, or schema layer detected |

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

# Scope

**Document version:** 1.0 (bootstrap scaffold)

Scope and authority boundary of this documentation system.

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

## 5. Configuration & Environment

This baseline section has not yet enumerated every environment variable or configuration file.

### 5.1 Current Status

| Surface | Status |
| --- | --- |
| Environment variable inventory | Not yet expanded in this baseline |
| Config ownership mapping | Not yet expanded in this baseline |
| Protocol requirement | Every env var must be documented here as this repo matures |

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

# Appendices

**Document version:** 1.0 (carry-forward)

Appendices, glossary, and cross-references.

## Unmapped legacy chapters

The following legacy chapters were carried forward but could not be
deterministically mapped to a class-aware slot. Review and place them by
hand:

- `Forge Local Systems Runtime — Complete System Reference`
