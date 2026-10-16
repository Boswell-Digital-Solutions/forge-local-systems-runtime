"""The runtime promotion worker sends its own DEDICATED receipt credential and nothing else.

The receipt write needs a DataForge service key (scope ``runtime-promotion:receipts:write`` on the service
``forge_local_runtime``). These tests drive the real ``_post_to_dataforge`` against real loopback HTTP servers
and prove: the key is sent when set; nothing is sent when it is not; the cost-sync read key is never used as a
fallback; the key goes only over HTTPS or to a loopback host; a redirect is never followed; a refusal is named
with fixed codes and never repeats the key or the response body; the retry behavior is unchanged.

Synthetic keys only. No external network. These tests do NOT prove that a running DataForge accepts the key.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import runtime_promotion.worker as rw
from runtime_promotion.worker import PromotionDeliveryWorker

from test_runtime_promotion_worker import FakeWorkerConnection, build_claimed_artifact

RECEIPT_KEY = "synthetic-receipt-write-key-not-real"
COST_KEY = "synthetic-cost-sync-read-key-not-real"
LOCAL_KEY = "synthetic-cost-sync-local-key-not-real"


class _Server:
    """A loopback HTTP server that records every request and answers a fixed status and body."""

    def __init__(self, status=201, body=None, location=None):
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silence
                pass

            def do_GET(self):
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": b"", "method": "GET"})
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                outer.requests.append(
                    {"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": self.rfile.read(length)}
                )
                self.send_response(status)
                if location:
                    self.send_header("Location", location)
                payload = json.dumps(body if body is not None else {}).encode()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/api/v1/runtime-promotion/receipts/local-failure-pattern"
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._t.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (rw.RECEIPT_KEY_ENV, rw.RECEIPT_URL_ENV, "FORGE_COST_SYNC_CLOUD_API_KEY", "FORGE_COST_SYNC_LOCAL_API_KEY",
                 "DATAFORGE_API_KEY", "ROTATION_ADMIN_TOKEN", "EMERGENCY_OPS_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def server(request):
    marker = request.node.get_closest_marker("serve")
    kwargs = marker.kwargs if marker else {}
    s = _Server(**kwargs)
    yield s
    s.close()


def _post(url, monkeypatch):
    monkeypatch.setenv(rw.RECEIPT_URL_ENV, url)
    PromotionDeliveryWorker()._post_to_dataforge(build_claimed_artifact())


def test_the_receipt_key_is_sent_as_a_bearer_when_it_is_set(server, monkeypatch):
    monkeypatch.setenv(rw.RECEIPT_KEY_ENV, RECEIPT_KEY)
    _post(server.url, monkeypatch)
    assert len(server.requests) == 1
    assert server.requests[0]["headers"]["authorization"] == f"Bearer {RECEIPT_KEY}"
    assert json.loads(server.requests[0]["body"])["envelope_type"] == "local_failure_pattern"


def test_no_credential_is_sent_when_the_receipt_key_is_not_set(server, monkeypatch):
    _post(server.url, monkeypatch)
    assert "authorization" not in server.requests[0]["headers"]


def test_other_keys_are_never_used_as_a_fallback(server, monkeypatch):
    """The cost-sync keys, a shared DataForge key and admin tokens are all set; none may be sent."""
    for name, value in (("FORGE_COST_SYNC_CLOUD_API_KEY", COST_KEY), ("FORGE_COST_SYNC_LOCAL_API_KEY", LOCAL_KEY),
                        ("DATAFORGE_API_KEY", "synthetic-shared-key-not-real"), ("ROTATION_ADMIN_TOKEN", "synthetic-admin-not-real"),
                        ("EMERGENCY_OPS_KEY", "synthetic-emergency-not-real")):
        monkeypatch.setenv(name, value)
    _post(server.url, monkeypatch)
    assert "authorization" not in server.requests[0]["headers"]
    assert b"synthetic" not in server.requests[0]["body"]


def test_the_receipt_key_is_not_what_the_cost_sync_worker_sends(monkeypatch):
    """The two credentials have separate retrieval paths: setting the receipt key does not give the cost sync a key."""
    import cost_sync.worker as cw

    monkeypatch.setenv(rw.RECEIPT_KEY_ENV, RECEIPT_KEY)
    headers, state = cw._cloud_headers("https://cloud.example/api/v1/costs/entries")
    assert "Authorization" not in headers and state == "not_configured"
    monkeypatch.delenv(rw.RECEIPT_KEY_ENV)
    monkeypatch.setenv("FORGE_COST_SYNC_CLOUD_API_KEY", COST_KEY)
    headers, state = rw.receipt_headers("https://cloud.example/receipts")
    assert "Authorization" not in headers and state == "not_configured"


@pytest.mark.parametrize("url", ["http://dataforge.example/receipts", "http://10.0.0.5:8001/receipts", "ftp://127.0.0.1/x"])
def test_the_key_is_withheld_over_cleartext_to_a_non_loopback_host(monkeypatch, url):
    monkeypatch.setenv(rw.RECEIPT_KEY_ENV, RECEIPT_KEY)
    headers, state = rw.receipt_headers(url)
    assert "Authorization" not in headers and state == "withheld_cleartext"


@pytest.mark.parametrize("url", ["https://dataforge.example/r", "http://127.0.0.1:8001/r", "http://localhost:8001/r", "http://[::1]:8001/r"])
def test_the_key_is_allowed_over_https_or_to_loopback(monkeypatch, url):
    monkeypatch.setenv(rw.RECEIPT_KEY_ENV, RECEIPT_KEY)
    headers, state = rw.receipt_headers(url)
    assert headers["Authorization"] == f"Bearer {RECEIPT_KEY}" and state == "attached"


def test_the_default_destination_is_kept_when_no_override_is_set():
    assert rw.receipt_url() == rw.DATAFORGE_RECEIPT_URL


@pytest.mark.serve(status=401, body={"detail": {"code": "service_key_scope_required", "secret": "do-not-copy"}})
@pytest.mark.parametrize("keyed", [False, True])
def test_a_401_is_named_with_fixed_codes_and_never_repeats_the_key_or_the_body(server, monkeypatch, keyed):
    if keyed:
        monkeypatch.setenv(rw.RECEIPT_KEY_ENV, RECEIPT_KEY)
    with pytest.raises(RuntimeError) as exc:
        _post(server.url, monkeypatch)
    text = str(exc.value)
    assert "HTTP 401" in text and "reason: service_key_scope_required" in text
    assert f"credential: {'attached' if keyed else 'not_configured'}" in text
    assert RECEIPT_KEY not in text and "do-not-copy" not in text


@pytest.mark.serve(status=403, body={"detail": {"code": "service_key_service_forbidden"}})
def test_a_403_is_named_the_same_way(server, monkeypatch):
    monkeypatch.setenv(rw.RECEIPT_KEY_ENV, RECEIPT_KEY)
    with pytest.raises(RuntimeError, match=r"HTTP 403; credential: attached; reason: service_key_service_forbidden"):
        _post(server.url, monkeypatch)


def test_a_redirect_is_never_followed_so_the_key_cannot_reach_another_origin(monkeypatch):
    other = _Server(status=201)
    first = _Server(status=302, location=other.url)  # 302 on a POST is the status urllib would follow
    try:
        monkeypatch.setenv(rw.RECEIPT_KEY_ENV, RECEIPT_KEY)
        with pytest.raises(RuntimeError, match="redirect"):
            _post(first.url, monkeypatch)
        assert len(first.requests) == 1 and other.requests == [], "the second origin must receive nothing"
    finally:
        first.close()
        other.close()


@pytest.mark.serve(status=401, body={"detail": {"code": "service_key_scope_required"}})
def test_a_refusal_keeps_the_existing_retry_behavior_and_reason_class(server, monkeypatch):
    monkeypatch.setenv(rw.RECEIPT_URL_ENV, server.url)
    connection = FakeWorkerConnection()
    result = PromotionDeliveryWorker().deliver_claimed_artifact(connection, build_claimed_artifact())
    assert result.action == "retry_scheduled" and result.reason_class == "dataforge_delivery_failed"
    assert "release_claim_for_retry" in connection.cursor().calls[0][0]


@pytest.mark.serve(status=201, body={"ingest_status": "accepted"})
def test_a_201_delivers_with_a_key_and_marks_the_artifact_delivered(server, monkeypatch):
    monkeypatch.setenv(rw.RECEIPT_KEY_ENV, RECEIPT_KEY)
    monkeypatch.setenv(rw.RECEIPT_URL_ENV, server.url)
    connection = FakeWorkerConnection()
    result = PromotionDeliveryWorker().deliver_claimed_artifact(connection, build_claimed_artifact())
    assert result.action == "delivered"
    assert server.requests[0]["headers"]["authorization"] == f"Bearer {RECEIPT_KEY}"
