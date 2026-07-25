-- 004_cost_ledger_sync_seen.sql
-- Runtime-owned dedup ledger for the cloud->local cost sync (cost_sync/worker.py).
-- Records each cloud DataForge cost_ledger entry id already mirrored into
-- DataForge-Local, so re-runs and overlapping `since` windows never double-write.
-- This state lives in THIS runtime's database only; the worker never writes to the
-- DataForge or DataForge-Local databases directly (both are reached via their APIs).

CREATE SCHEMA IF NOT EXISTS cost_sync;

CREATE TABLE IF NOT EXISTS cost_sync.seen (
    cloud_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_cost_sync_seen_created_at
    ON cost_sync.seen (created_at);
