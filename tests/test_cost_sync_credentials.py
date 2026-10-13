"""Cost sync credentials, refusals and status.

The cloud read needs a DataForge service key (scope costs:read on the service forge_local_runtime). These
tests prove, with the transport faked or with real local HTTP servers: a refused cloud read changes
nothing locally and moves no checkpoint; the cloud key and the local key never cross; a redirect is
never followed; a crash loses at most the row in flight; freshness is exposed without reading the cloud.
No real credential. No external network.
"""
from __future__ import annotations

import io
import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib import error

import pytest

import cost_sync.worker as w
from cost_sync.worker import CostLedgerSyncWorker
from test_cost_sync_recovery import NOW, FakeCloud, FakeDb, FakeLocal, SimulatedCrash, _entry, mirrored, old, run

CLOUD_KEY = "synthetic-cloud-read-key-not-real"
LOCAL_KEY = "synthetic-local-ingest-key-not-real"


class _Resp:
    def __init__(self, body):
        self._b = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def getcode(self):
        return 200

    def read(self, *a):
        return self._b


def _http_error(status, body=None):
    return error.HTTPError("https://cloud.example/x", status, "msg", {}, io.BytesIO(json.dumps(body or {}).encode()))


@pytest.fixture
def wire(monkeypatch):
    """Fake the transport (urlopen) and record every request that would leave the process."""
    sent: list = []
    script: list = []

    def fake_urlopen(req, timeout):
        sent.append(req)
        item = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(w, "_urlopen", fake_urlopen)
    monkeypatch.setattr(w, "_utcnow", lambda: NOW)
    monkeypatch.setenv("DATAFORGE_URL", "https://cloud.example")
    monkeypatch.setenv("DATAFORGE_LOCAL_URL", "http://127.0.0.1:8005")
    for name in ("FORGE_COST_SYNC_CLOUD_API_KEY", "FORGE_COST_SYNC_LOCAL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return sent, script


def _db_with_checkpoint():
    db = FakeDb()
    db.seen["prior"] = {"created_at": old(30), "synced_at": NOW - timedelta(hours=20)}
    return db


# --- a refused cloud read changes nothing ------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "error_obj", "refusal_kind", "reason"),
    [
        (None, _http_error(401, {"detail": "API key required"}), "no_credential_sent", "unrecognized"),
        (CLOUD_KEY, _http_error(401, {"detail": "API key required"}), "credential_rejected", "unrecognized"),  # expired or revoked
        (CLOUD_KEY, _http_error(403, {"detail": {"code": "service_key_service_forbidden"}}), "service_or_scope_not_eligible", "service_key_service_forbidden"),
        (CLOUD_KEY, _http_error(403, {"detail": {"code": "service_key_scope_required"}}), "service_or_scope_not_eligible", "service_key_scope_required"),
        (CLOUD_KEY, _http_error(403, {"detail": {"code": "route_quarantined"}}), "route_has_no_authorization_contract", "route_quarantined"),
    ],
)
def test_a_refused_cloud_read_is_named_and_changes_nothing_locally(wire, monkeypatch, key, error_obj, refusal_kind, reason):
    sent, script = wire
    if key:
        monkeypatch.setenv("FORGE_COST_SYNC_CLOUD_API_KEY", key)
    script.append(error_obj)
    local = FakeLocal()
    monkeypatch.setattr(w, "_http_post_json", local.post)
    db = _db_with_checkpoint()
    before_seen, before_mark = dict(db.seen), w.CostLedgerSyncWorker()._watermark(db)

    result = run(db)

    assert result.complete is False and result.stopped_reason == "cloud_read_refused"
    assert result.failure["refusal_kind"] == refusal_kind and result.failure["reason"] == reason
    assert local.rows == [], "a refused cloud read must not write to the local ledger"
    assert db.seen == before_seen, "no dedup record may change"
    assert w.CostLedgerSyncWorker()._watermark(db) == before_mark, "the checkpoint must not advance"
    assert exit_code(result) != 0
    assert CLOUD_KEY not in json.dumps(result.failure) and CLOUD_KEY not in repr(result)


def exit_code(result):
    return w.exit_code_for(result)


@pytest.mark.parametrize("failure", [_http_error(503), error.URLError("down")])
def test_an_unavailable_cloud_changes_nothing_locally(wire, monkeypatch, failure):
    sent, script = wire
    script.append(failure)
    local = FakeLocal()
    monkeypatch.setattr(w, "_http_post_json", local.post)
    db = _db_with_checkpoint()
    before = dict(db.seen)
    result = run(db)
    assert result.complete is False and result.stopped_reason == "cloud_read_unavailable"
    assert local.rows == [] and db.seen == before


# --- the two keys never cross ------------------------------------------------------------------------


def test_the_cloud_key_goes_to_the_cloud_and_the_local_key_goes_to_the_local_url_only(wire, monkeypatch):
    sent, script = wire
    monkeypatch.setenv("FORGE_COST_SYNC_CLOUD_API_KEY", CLOUD_KEY)
    monkeypatch.setenv("FORGE_COST_SYNC_LOCAL_API_KEY", LOCAL_KEY)
    cloud_rows = [_entry("c1", old(5))]
    script.append(_Resp({"items": cloud_rows, "total": 1}))

    def post_through_transport(url, body):
        # Use the real _http_post_json so its header logic runs; the transport is faked.
        script.append(_Resp({}))
        return real_post(url, body)

    real_post = w._http_post_json
    monkeypatch.setattr(w, "_http_post_json", post_through_transport)
    db = FakeDb()
    result = run(db)
    assert result.complete is True
    get_req = next(r for r in sent if r.get_method() == "GET")
    post_req = next(r for r in sent if r.get_method() == "POST")
    assert get_req.get_header("Authorization") == f"Bearer {CLOUD_KEY}"
    assert post_req.get_header("Authorization") == f"Bearer {LOCAL_KEY}"
    assert get_req.full_url.startswith("https://cloud.example/")
    assert post_req.full_url.startswith("http://127.0.0.1:8005/")


def test_with_only_a_cloud_key_the_local_write_carries_no_authorization(wire, monkeypatch):
    sent, script = wire
    monkeypatch.setenv("FORGE_COST_SYNC_CLOUD_API_KEY", CLOUD_KEY)
    script.append(_Resp({"items": [_entry("c1", old(5))], "total": 1}))
    real_post = w._http_post_json

    def post(url, body):
        script.append(_Resp({}))
        return real_post(url, body)

    monkeypatch.setattr(w, "_http_post_json", post)
    run(FakeDb())
    post_req = next(r for r in sent if r.get_method() == "POST")
    assert post_req.get_header("Authorization") is None, "the cloud read key must never be sent to the local URL"


def test_the_cloud_key_is_withheld_from_cleartext_http_to_a_non_loopback_host(wire, monkeypatch):
    sent, script = wire
    monkeypatch.setenv("DATAFORGE_URL", "http://cloud.example")
    monkeypatch.setenv("FORGE_COST_SYNC_CLOUD_API_KEY", CLOUD_KEY)
    script.append(_http_error(401, {"detail": "API key required"}))
    result = run(FakeDb())
    assert sent[0].get_header("Authorization") is None
    assert result.failure["refusal_kind"] == "no_credential_sent", "withheld means 'no credential sent', not 'rejected'"


# --- a redirect is never followed (real opener, two real servers) -------------------------------------


def _serve(handler_cls):
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_a_redirect_does_not_carry_the_cloud_key_to_a_second_origin(monkeypatch):
    seen_by_target: list = []

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            seen_by_target.append(self.headers.get("Authorization"))
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    target = _serve(Target)

    class Redirector(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/stolen")
            self.end_headers()

        def log_message(self, *a):
            pass

    origin = _serve(Redirector)
    monkeypatch.setenv("DATAFORGE_URL", f"http://127.0.0.1:{origin.server_port}")  # loopback http: key allowed
    monkeypatch.setenv("FORGE_COST_SYNC_CLOUD_API_KEY", CLOUD_KEY)
    try:
        with pytest.raises(w.CloudReadError) as raised:
            w._http_get_json(f"http://127.0.0.1:{origin.server_port}/api/v1/costs/entries?limit=1")
    finally:
        origin.shutdown(); target.shutdown()
    assert raised.value.kind == "refused" and raised.value.refusal_kind == "redirect_not_followed"
    assert seen_by_target == [], "the redirect target must receive no request, and so no credential"


# --- a crash loses at most the row in flight ----------------------------------------------------------


def test_a_crash_mid_run_does_not_re_post_rows_that_were_already_recorded(wire, monkeypatch):
    cloud, local, db = FakeCloud([_entry(f"c{i}", old(6 - i)) for i in range(1, 5)]), FakeLocal(), FakeDb()
    monkeypatch.setattr(w, "_http_get_json", cloud.get)
    real_post = local.post

    def post(url, body):
        if body["model_id"] == "c3":
            raise SimulatedCrash()
        real_post(url, body)

    monkeypatch.setattr(w, "_http_post_json", post)
    with pytest.raises(SimulatedCrash):
        run(db)
    db.crash()  # the process died: uncommitted writes are gone
    assert sorted(r["model_id"] for r in local.rows) == ["c1", "c2"] and mirrored(db) == {"c1", "c2"}

    monkeypatch.setattr(w, "_http_post_json", real_post)
    run(db)
    assert sorted(r["model_id"] for r in local.rows) == ["c1", "c2", "c3", "c4"], "each row exactly once"


# --- freshness and failure state without reading the cloud ---------------------------------------------


def test_status_says_freshness_is_unknown_before_any_complete_pass(wire):
    status = CostLedgerSyncWorker().status(FakeDb())
    assert status["freshness_known"] is False and status["last_successful_sync"] is None
    assert status["source"] == "cloud_dataforge"


def test_a_complete_pass_records_a_heartbeat_even_when_there_was_nothing_to_mirror(env_complete):
    result, db = env_complete
    assert result.complete and result.synced == 0
    status = CostLedgerSyncWorker().status(db)
    assert status["freshness_known"] is True and status["age_seconds"] is not None and status["age_seconds"] < 5


def test_an_incomplete_pass_does_not_refresh_the_heartbeat(wire, monkeypatch):
    sent, script = wire
    script.append(_http_error(503))
    db = FakeDb()
    db.seen[w._HEARTBEAT_ID] = {"created_at": datetime(1970, 1, 1, tzinfo=UTC), "synced_at": NOW - timedelta(hours=9)}
    result = run(db)
    assert result.complete is False
    assert result.last_successful_sync is not None and result.age_seconds > 8 * 3600, "the age keeps growing; a failed pass is not fresh"


def test_the_heartbeat_is_never_a_checkpoint(wire, monkeypatch):
    db = FakeDb()
    db.seen[w._HEARTBEAT_ID] = {"created_at": datetime(1970, 1, 1, tzinfo=UTC), "synced_at": NOW}
    assert CostLedgerSyncWorker()._watermark(db) is None


@pytest.fixture
def env_complete(monkeypatch):
    cloud = FakeCloud([])
    monkeypatch.setattr(w, "_http_get_json", cloud.get)
    monkeypatch.setattr(w, "_utcnow", lambda: NOW)
    db = FakeDb()
    # synced_at uses the real clock in the fake, so make "now" real for the age check
    monkeypatch.setattr(w, "_utcnow", lambda: datetime.now(UTC))
    return CostLedgerSyncWorker().sync_once(db), db
