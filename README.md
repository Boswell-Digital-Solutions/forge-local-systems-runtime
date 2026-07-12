# bds · forge-local-systems-runtime

> **System identity — bds family (Boswell Digital Solutions business system, local-systems tier).**
> The governance-first constitutional repository for the shared local service substrate of the Forge **ecosystem backend**; part of `ecosystem/local-systems`.
> **Purpose:** defines runtime doctrine, cross-service boundaries, ownership lines, and anti-drift enforcement for the four governed local services (DF Local Foundation, NeuronForge Local, Cortex, FA Local) — not an implementation or executable itself.
> **Not the Forge counterpart:** the public-app support boundary is `apps/public-app-local-support/forge-local-runtime-master-reference` (Forge family).

## What this repository is

Forge Local Runtime is the governance-first constitutional repository for the shared local service substrate of the Forge ecosystem.

It governs four service-only internal runtime systems:

- DF Local Foundation
- NeuronForge Local
- Cortex
- FA Local

This repository defines:

- runtime doctrine
- cross-service boundaries
- ownership and non-ownership lines
- readiness and degraded-state language
- denial posture
- handoff rules
- privacy-preserving observability constraints
- anti-drift enforcement surfaces
- shared schemas and validation posture

## What this repository is not

This repository is not:

- a destination application product
- a Tauri application
- a local orchestrator executable
- a shared business backend
- a stealth monolith for local implementation
- a cloud-stack clone on a laptop
- a place where semantic or workflow authority quietly accumulates

## Why this repository exists

The Forge local runtime is a real architecture layer with its own:

- doctrine
- trust boundaries
- failure posture
- degraded-state rules
- service-only visibility rules
- local-versus-cloud boundaries
- handoff rules
- anti-drift requirements

Separating this repository makes that layer governable and testable without forcing all service implementation into one repo.

## The four governed local services

### DF Local Foundation
Local data/control substrate.
Owns bounded persistence, migrations, backup/restore/export doctrine, registration, readiness, and integrity support.

### NeuronForge Local
Local inference and candidate-production substrate.
Owns bounded local inference routing, task-contract execution, model/profile routing, and candidate output under contract.

### Cortex
Local file intelligence and retrieval-preparation substrate.
Owns local intake, syntax-level extraction, retrieval-preparation support, packaging handoff support, and truthful operational status for those surfaces.

### FA Local
Governed local execution substrate.
Owns trusted execution request intake, requester trust resolution, policy-gated execution, capability admission checks, bounded execution-plan validation, and truthful execution-state reporting.

## Core repository rule

This repository is a governance-and-contracts authority repo.

It primarily owns:

- constitutional documentation
- shared doctrine
- boundary matrices
- runtime-level control language
- shared schema posture
- anti-drift tests

It does not exist to absorb implementation from the four service repos by convenience.

## Local baseline doctrine

The local baseline must remain meaningful without cloud.

At minimum, the local runtime must provide:

- a local data/control substrate
- a local inference and candidate-production substrate
- a local file intelligence and retrieval-preparation substrate
- a governed local execution substrate
- truthful readiness, denial, degraded, and observability posture across those services

## Cloud augmentation line

Cloud capability is additive power, not baseline dependency.

Cloud services may expand local capability, but they must not redefine the constitutional minimum local baseline.

## Initial repository build order

1. repo skeleton
2. top-level constitutional docs
3. decision records
4. service role docs
5. boundary matrix
6. shared schemas
7. doctrine/control docs
8. validation and anti-drift scaffold

## Status

Draft constitutional authority repository.
Implementation must not outrun doctrine, boundaries, decisions, and shared schema surfaces.