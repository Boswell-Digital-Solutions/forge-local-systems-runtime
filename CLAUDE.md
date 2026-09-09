# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Forge Local Runtime is a **governance-first constitutional repository** — it defines runtime doctrine,
cross-service boundaries, ownership lines, and anti-drift enforcement for the shared local service
substrate of the Forge ecosystem backend (business/bds side). It governs four service-only local
systems (DF Local Foundation, NeuronForge Local, Cortex, FA Local). **This repo implements nothing —
it governs.**

> **Not `forge-local-runtime`.** A near-identically named, separate doctrine repo
> (`apps/public-app-local-support/forge-local-runtime-master-reference`) governs the public-app side.
> Applying one side's doctrine to the other side's services is the failure mode to avoid.

## Common Commands

- `make validate` — runs `validate-schemas` + `check-boundaries`; this is the only gate (there is no
  CI workflow)
- `python scripts/validate_schemas.py` — validates the schema/contract corpus
- `python scripts/check_boundaries.py` — checks that declared ownership boundaries hold
- `./scripts/context-bundle.sh --list` — list available context bundles
- `bash doc/system/BUILD.sh` — build the canonical reference (see `SYSTEM.md`)

## Architecture

Doctrine is expressed as JSON schemas in [`schemas/`](schemas/): `runtime-contract`, `service-status`,
`readiness-summary`, `handoff-envelope`, `degraded-state`, `denial-state`, and
`forensic-event-envelope`. The repo governs four service domains without implementing any of them:

- **DF Local Foundation** — local data/control substrate (persistence, migrations, backup/restore)
- **NeuronForge Local** — local inference and candidate-production substrate
- **Cortex** — local file intelligence and retrieval-preparation substrate
- **FA Local** — governed local execution substrate (policy-gated, capability-admission checked)

Degraded and denied are declared states, never silent fallbacks — a service cannot quietly pretend to
be healthy.

## Notes

- This repo must never become a Tauri app, Svelte frontend, runtime daemon, service executable, or a
  convenience sink for service implementation code — see `BUILD.md` for the required change bundles
  when a change adds a capability, a new denial/degraded state, or expands a schema.
- A schema change is not complete until: the schema is updated, at least one valid and one invalid
  fixture cover it, and `make validate` (or `python scripts/validate_schemas.py` /
  `python scripts/check_boundaries.py`) passes.
- See `ARCHITECTURE.md`, `BOUNDARIES.md`, and `BUILD.md` for the full doctrine; `DECISIONS/` holds ADRs.
