"""One-pass runner for the cloud->local cost-ledger sync.

Invoked on a schedule (cron/systemd timer) like the runtime-promotion worker:
each run mirrors any new cloud cost entries into DataForge-Local and commits the
runtime-owned dedup state. Prints a JSON summary.
"""
from __future__ import annotations

import json

from cost_sync.worker import CostLedgerSyncWorker
from runtime_promotion.connection import create_connection


def main() -> None:
    connection = create_connection()
    worker = CostLedgerSyncWorker()
    try:
        result = worker.sync_once(connection)
        connection.commit()
        print(
            json.dumps(
                {
                    "fetched": result.fetched,
                    "synced": result.synced,
                    "skipped": result.skipped,
                    "failed": result.failed,
                    "watermark": result.watermark,
                },
                indent=2,
                default=str,
            )
        )
    except Exception:
        connection.rollback()
        raise


if __name__ == "__main__":
    main()
