"""Support for the PostgreSQL tests of the cost sync worker.

* ``PgCluster``: a throwaway PostgreSQL server. It listens on a unix socket in a private directory and
  on no TCP port, so it can never collide with another server on the machine. It is found through
  ``COST_SYNC_TEST_PG_BIN``, ``PATH`` or ``/usr/lib/postgresql/*/bin``. If it is not found, the tests that
  need it skip with a stated reason.
* ``ContractCloud``: a real HTTP server (loopback) that answers ``GET /api/v1/costs/entries`` with the
  REAL contract of cloud DataForge (``app/api/multi_provider_crud.py::list_cost_entries``):

      WHERE created_at >= :since AND created_at <= :until      (both bounds inclusive)
      total = COUNT(*) of that filter                          (a separate query, not the page)
      ORDER BY created_at DESC  OFFSET :offset LIMIT :limit    (NOT a unique order)

  Rows with equal ``created_at`` come back in an order the contract does not fix. ``ties`` chooses
  one legal order: ``by_request`` (a new order on every request), ``by_page`` (a function of the page
  only, the same on every pass) or ``id_desc`` (the proposed server tiebreak ``created_at DESC, id DESC``).
* ``LocalSink``: a real HTTP server (loopback) for DataForge-Local ``POST /api/v1/costs/record``. Like the
  real one it has no source id: every call makes a new row with a new uuid.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import shutil
import subprocess
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import psycopg

from runtime_promotion.connection import PsycopgConnectionAdapter

MIGRATION = Path(__file__).resolve().parents[1] / "db" / "migrations" / "004_cost_ledger_sync_seen.sql"


# --- PostgreSQL ---------------------------------------------------------------------------------


def find_pg_bin() -> Path | None:
    candidates: list[Path] = []
    if os.environ.get("COST_SYNC_TEST_PG_BIN"):
        candidates.append(Path(os.environ["COST_SYNC_TEST_PG_BIN"]))
    found = shutil.which("initdb")
    if found:
        candidates.append(Path(found).parent)
    candidates += [Path(p).parent for p in sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"), reverse=True)]
    for directory in candidates:
        if (directory / "initdb").exists() and (directory / "pg_ctl").exists():
            return directory
    return None


class PgCluster:
    PORT = 54399  # names the socket file only; there is no TCP listener

    def __init__(self, bin_dir: Path) -> None:
        self.bin = bin_dir
        self.root = Path(tempfile.mkdtemp(prefix="fls-costsync-pg-"))
        self.data = self.root / "data"
        self.socket_dir = self.root / "sock"
        self.socket_dir.mkdir()
        self._counter = 0

    def start(self) -> None:
        subprocess.run(
            [str(self.bin / "initdb"), "-D", str(self.data), "-U", "postgres", "--auth=trust", "-E", "UTF8"],
            check=True, capture_output=True,
        )
        options = f"-p {self.PORT} -k {self.socket_dir} -c listen_addresses='' -c fsync=off -c max_connections=60"
        subprocess.run(
            [str(self.bin / "pg_ctl"), "-D", str(self.data), "-o", options, "-l", str(self.root / "pg.log"), "-w", "start"],
            check=True, capture_output=True,
        )

    def stop(self) -> None:
        subprocess.run([str(self.bin / "pg_ctl"), "-D", str(self.data), "-m", "immediate", "-w", "stop"], capture_output=True)
        shutil.rmtree(self.root, ignore_errors=True)

    def dsn(self, database: str) -> str:
        return f"host={self.socket_dir} port={self.PORT} user=postgres dbname={database}"

    def new_database(self) -> "PgDatabase":
        """A fresh database with the real migration 004 applied."""
        self._counter += 1
        name = f"cost_sync_t{self._counter}_{uuid.uuid4().hex[:6]}"
        with psycopg.connect(self.dsn("postgres"), autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{name}"')
        db = PgDatabase(self, name)
        with psycopg.connect(db.dsn) as conn:
            conn.execute(MIGRATION.read_text())
        return db


class PgDatabase:
    def __init__(self, cluster: PgCluster, name: str) -> None:
        self.cluster, self.name, self.dsn = cluster, name, cluster.dsn(name)
        self._open: list[psycopg.Connection[Any]] = []

    def connect(self) -> PsycopgConnectionAdapter:
        """A new connection, the way a new worker process opens one (same adapter as the runner)."""
        raw = psycopg.connect(self.dsn)
        self._open.append(raw)
        return PsycopgConnectionAdapter(raw)

    @staticmethod
    def close(adapter: PsycopgConnectionAdapter) -> None:
        """The process dies or exits: uncommitted work is lost and session locks are released."""
        adapter._connection.close()

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
        """Read through an independent connection: it sees only what was COMMITTED."""
        with psycopg.connect(self.dsn) as conn:
            return list(conn.execute(sql, params or {}).fetchall())

    def drop(self) -> None:
        for raw in self._open:
            try:
                raw.close()
            except Exception:  # noqa: BLE001
                pass
        with psycopg.connect(self.cluster.dsn("postgres"), autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{self.name}" WITH (FORCE)')


# --- fake sources ---------------------------------------------------------------------------------


def entry(cid: str, created: datetime, **kw: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": cid, "user_id": "u1", "provider": "anthropic", "model_id": cid, "task_type": "codefix",
        "input_tokens": 100, "output_tokens": 50, "input_cost_usd": "0.001000", "output_cost_usd": "0.002000",
        "total_cost_usd": "0.003000", "is_batch": False, "is_cached": False, "created_at": created,
    }
    row.update(kw)
    return row


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "+00:00"


class _Quiet(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass


class _Server:
    def __init__(self, handler: type[BaseHTTPRequestHandler]) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class ContractCloud(_Server):
    def __init__(self, rows: list[dict[str, Any]] | None = None, ties: str = "by_request") -> None:
        self.rows: list[dict[str, Any]] = list(rows or [])
        self.ties = ties
        self.requests: list[dict[str, str]] = []
        self.truncate: dict[int, int] = {}  # offset -> number of items to return (a short page)
        self.on_request: Callable[[int], None] | None = None
        self._lock = threading.Lock()
        cloud = self

        class Handler(_Quiet):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                body = cloud._serve(query)
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        super().__init__(Handler)

    def add(self, *rows: dict[str, Any]) -> None:
        with self._lock:
            self.rows.extend(rows)

    def _order(self, rows: list[dict[str, Any]], request_no: int, offset: int, limit: int) -> list[dict[str, Any]]:
        by_time: dict[datetime, list[dict[str, Any]]] = {}
        for row in rows:
            by_time.setdefault(row["created_at"], []).append(row)
        ordered: list[dict[str, Any]] = []
        for created in sorted(by_time, reverse=True):  # ORDER BY created_at DESC
            tied = sorted(by_time[created], key=lambda r: r["id"])
            if self.ties == "id_desc":
                tied.reverse()
            elif self.ties == "by_page":  # the same wrong order for every pass: a function of the page only
                tied.sort(key=lambda r: hashlib.md5(f"{offset}:{limit}:{r['id']}".encode()).hexdigest())
            elif self.ties == "by_request":  # a new legal order on every request
                random.Random(request_no).shuffle(tied)
            else:
                raise ValueError(self.ties)
            ordered += tied
        return ordered

    def _serve(self, query: dict[str, str]) -> dict[str, Any]:
        with self._lock:
            request_no = len(self.requests)
            self.requests.append(query)
        if self.on_request:
            self.on_request(request_no)
        with self._lock:
            since = datetime.fromisoformat(query["since"]) if "since" in query else None
            until = datetime.fromisoformat(query["until"]) if "until" in query else None
            limit, offset = int(query.get("limit", 50)), int(query.get("offset", 0))
            rows = [
                r for r in self.rows
                if (since is None or r["created_at"] >= since) and (until is None or r["created_at"] <= until)
            ]
            total = len(rows)
            page = self._order(rows, request_no, offset, limit)[offset: offset + limit]
            if offset in self.truncate:
                page = page[: self.truncate[offset]]
            return {"items": [{**r, "created_at": _iso(r["created_at"])} for r in page], "total": total}


class LocalSink(_Server):
    """DataForge-Local ``POST /api/v1/costs/record``: no source id, so no way to recognise a replay."""

    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []
        self.fail_for: set[str] = set()  # model_id values that answer 503
        self.before_post: Callable[[dict[str, Any]], None] | None = None
        self._lock = threading.Lock()
        sink = self

        class Handler(_Quiet):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                status = 201
                if body["model_id"] in sink.fail_for:
                    status = 503
                else:
                    with sink._lock:
                        sink.posts.append(body)
                    if sink.before_post:
                        sink.before_post(body)
                data = json.dumps({"id": str(uuid.uuid4())}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        super().__init__(Handler)

    def ids(self) -> list[str]:
        """The model_id of each stored row (the tests use the cloud id as the model_id)."""
        with self._lock:
            return [p["model_id"] for p in self.posts]
