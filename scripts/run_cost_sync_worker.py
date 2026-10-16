"""One-pass runner for the cloud->local cost-ledger sync.

Invoked on a schedule (cron/systemd timer) like the runtime-promotion worker:
each run mirrors any new cloud cost entries into DataForge-Local and commits the
runtime-owned dedup state. Prints a JSON summary with the source, the checkpoint, the last
completed pass and its age, and a fixed failure code.

The exit code is 0 only for a COMPLETE pass. A refused cloud read, an unreachable destination, a rejected
row or an incomplete listing exits 1, so the scheduler shows it as a failure. Partial progress is never
reported as success.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict

from cost_sync.worker import CostLedgerSyncWorker, exit_code_for
from runtime_promotion.connection import create_connection


def main() -> int:
    connection = create_connection()
    worker = CostLedgerSyncWorker()
    try:
        result = worker.sync_once(connection)
        connection.commit()
        print(json.dumps(asdict(result), indent=2, default=str))
        return exit_code_for(result)
    except Exception:
        connection.rollback()
        raise


if __name__ == "__main__":
    sys.exit(main())
