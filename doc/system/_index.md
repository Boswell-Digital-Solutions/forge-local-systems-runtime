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
