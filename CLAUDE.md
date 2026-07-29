# Forge Local Runtime — Claude Code Context

Governance-first constitution: doctrine, boundaries, and ownership for the **business-side** local
services. **This repo implements nothing** — it governs.

> **Not `forge-local-runtime`.** Near-identical names, and both are doctrine repos that implement
> nothing. This one governs the business-side local services;
> `apps/public-app-local-support/forge-local-runtime-master-reference` governs the public-app local
> services. Applying one side's doctrine to the other side's services is the failure mode.

Canonical reference: `doc/system/` → root `SYSTEM.md` (`bash doc/system/BUILD.sh`).

---

## Boundaries

The doctrine is expressed as schemas, not prose — [`schemas/`](schemas/) defines
`runtime-contract`, `service-status`, `readiness-summary`, `handoff-envelope`,
`degraded-state`, `denial-state`, and `forensic-event-envelope`. A local service that reports
readiness, degradation, or denial does it in these shapes.

- **Degraded and denied are declared states, never silent fallbacks.** `degraded-state` and
  `denial-state` exist so a service cannot quietly pretend to be healthy.
- Ownership boundaries here are binding on the services they govern; do not add implementation to
  this repo to "make it work".

---

## Verification

```bash
make validate      # validate-schemas + check-boundaries
```

`scripts/validate_schemas.py` checks the contract corpus; `scripts/check_boundaries.py` checks that
the declared ownership boundaries hold. There is no CI workflow — `make validate` is the gate.

```bash
./scripts/context-bundle.sh --list
```
