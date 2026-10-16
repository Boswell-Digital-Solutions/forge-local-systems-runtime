from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from typing import Any, Protocol, cast, runtime_checkable
from urllib import error, parse, request

from runtime_promotion.persistence import DbConnection


DATAFORGE_RECEIPT_URL = (
    "http://127.0.0.1:8001/api/v1/runtime-promotion/receipts/local-failure-pattern"
)

# The receipt write needs a DataForge service key: scope ``runtime-promotion:receipts:write`` on the service
# ``forge_local_runtime``. This is a DEDICATED credential. It is not the cost-sync read key
# (``FORGE_COST_SYNC_CLOUD_API_KEY``, scope ``costs:read``), and no code here falls back to that key, to any
# other key, or to an administrative credential. An unset variable means no credential is sent, and DataForge
# answers 401. That is the hardened denial, and it stays the failure mode.
RECEIPT_KEY_ENV = "FORGE_RUNTIME_PROMOTION_RECEIPT_API_KEY"
# Optional destination override. The default above is kept.
RECEIPT_URL_ENV = "FORGE_RUNTIME_PROMOTION_RECEIPT_URL"
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class _NoRedirect(request.HTTPRedirectHandler):
    """Never follow a redirect: the key must not travel to an origin that was not chosen."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_OPENER = request.build_opener(_NoRedirect)


def _urlopen(req: request.Request, timeout: float):
    return _OPENER.open(req, timeout=timeout)


def receipt_url() -> str:
    return (os.environ.get(RECEIPT_URL_ENV) or "").strip() or DATAFORGE_RECEIPT_URL


def receipt_headers(url: str) -> tuple[dict[str, str], str]:
    """Headers for the receipt write and the credential state.

    State is ``attached``, ``not_configured`` or ``withheld_cleartext`` (the key goes only over HTTPS or to a
    loopback host). The only key read is ``FORGE_RUNTIME_PROMOTION_RECEIPT_API_KEY``.
    """
    headers = {"Content-Type": "application/json"}
    key = os.environ.get(RECEIPT_KEY_ENV, "").strip()
    if not key:
        return headers, "not_configured"
    parsed = parse.urlparse(url)
    if not (parsed.scheme == "https" or (parsed.scheme == "http" and (parsed.hostname or "") in _LOOPBACK)):
        return headers, "withheld_cleartext"
    headers["Authorization"] = f"Bearer {key}"
    return headers, "attached"


def _refusal_code(exc: error.HTTPError) -> str:
    """A fixed reason code from a refusal body. Never the body itself."""
    try:
        body = json.loads(exc.read(4096).decode("utf-8"))
    except Exception:
        return "unreadable"
    detail = body.get("detail") if isinstance(body, dict) else None
    code = detail.get("code") if isinstance(detail, dict) else (body.get("code") if isinstance(body, dict) else None)
    if isinstance(code, str) and 0 < len(code) <= 64 and all(c.isalnum() or c in "_-" for c in code):
        return code
    return "unrecognized"


@runtime_checkable
class WorkerCursor(Protocol):
    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None: ...
    def fetchall(self) -> list[tuple[Any, ...]]: ...


@dataclass(frozen=True, slots=True)
class ClaimedArtifact:
    artifact_id: str
    envelope_type: str
    envelope_version: str
    service: str
    fleet_member_id: str
    dedupe_key: str
    payload_json: dict[str, Any]
    status: str
    delivery_attempt_count: int
    first_observed_at: datetime
    last_attempted_at: datetime | None
    next_attempt_at: datetime | None
    expires_at: datetime | None
    acknowledged_at: datetime | None
    rejection_reason_class: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    artifact_id: str
    action: str
    reason_class: str | None = None


class PromotionDeliveryWorker:
    CLAIM_SQL = """
    SELECT *
    FROM runtime_promotion.claim_ready_artifacts(%(limit)s)
    """

    MARK_DELIVERED_SQL = """
    SELECT runtime_promotion.mark_delivered(
        %(artifact_id)s,
        %(acknowledged_at)s
    )
    """

    RELEASE_FOR_RETRY_SQL = """
    SELECT runtime_promotion.release_claim_for_retry(
        %(artifact_id)s,
        %(next_attempt_at)s,
        %(reason_class)s
    )
    """

    def claim_ready_artifacts(
        self,
        connection: DbConnection,
        limit: int = 10,
    ) -> list[ClaimedArtifact]:
        cursor = connection.cursor()
        worker_cursor = cursor
        assert isinstance(worker_cursor, WorkerCursor)

        worker_cursor.execute(self.CLAIM_SQL, {"limit": limit})
        rows = worker_cursor.fetchall()

        claimed: list[ClaimedArtifact] = []
        for row in rows:
            claimed.append(
                ClaimedArtifact(
                    artifact_id=row[0],
                    envelope_type=row[1],
                    envelope_version=row[2],
                    service=row[3],
                    fleet_member_id=row[4],
                    dedupe_key=row[5],
                    payload_json=row[6],
                    status=row[7],
                    delivery_attempt_count=row[8],
                    first_observed_at=row[9],
                    last_attempted_at=row[10],
                    next_attempt_at=row[11],
                    expires_at=row[12],
                    acknowledged_at=row[13],
                    rejection_reason_class=row[14],
                    created_at=row[15],
                    updated_at=row[16],
                )
            )

        return claimed

    def deliver_claimed_artifact(
        self,
        connection: DbConnection,
        artifact: ClaimedArtifact,
    ) -> DeliveryResult:
        simulate_failure = bool(artifact.payload_json.get("simulate_delivery_failure", False))

        cursor = connection.cursor()
        worker_cursor = cursor
        assert isinstance(worker_cursor, WorkerCursor)

        if simulate_failure:
            next_attempt_at = datetime.now(UTC) + timedelta(minutes=15)
            worker_cursor.execute(
                self.RELEASE_FOR_RETRY_SQL,
                {
                    "artifact_id": artifact.artifact_id,
                    "next_attempt_at": next_attempt_at,
                    "reason_class": "simulated_delivery_failure",
                },
            )
            return DeliveryResult(
                artifact_id=artifact.artifact_id,
                action="retry_scheduled",
                reason_class="simulated_delivery_failure",
            )

        try:
            self._post_to_dataforge(artifact)
        except Exception as exc:
            print(f"DATAFORGE DELIVERY ERROR for {artifact.artifact_id}: {exc}")
            next_attempt_at = datetime.now(UTC) + timedelta(minutes=15)
            worker_cursor.execute(
                self.RELEASE_FOR_RETRY_SQL,
                {
                    "artifact_id": artifact.artifact_id,
                    "next_attempt_at": next_attempt_at,
                    "reason_class": "dataforge_delivery_failed",
                },
            )
            return DeliveryResult(
                artifact_id=artifact.artifact_id,
                action="retry_scheduled",
                reason_class="dataforge_delivery_failed",
            )

        worker_cursor.execute(
            self.MARK_DELIVERED_SQL,
            {
                "artifact_id": artifact.artifact_id,
                "acknowledged_at": datetime.now(UTC),
            },
        )
        return DeliveryResult(
            artifact_id=artifact.artifact_id,
            action="delivered",
        )

    def _normalize_supporting_examples(self, payload_json: dict[str, Any]) -> list[str]:
        raw_examples_obj = payload_json.get("supporting_examples", [])
        raw_examples = cast(list[Any], raw_examples_obj if isinstance(raw_examples_obj, list) else [])

        normalized: list[str] = []
        for item in raw_examples:
            if isinstance(item, str):
                value = item.strip()
                if value:
                    normalized.append(value)
                continue

            if isinstance(item, dict):
                item_dict = cast(dict[str, Any], item)
                summary = str(item_dict.get("summary", "")).strip()
                reason_class = str(item_dict.get("reason_class", "")).strip()

                if summary and reason_class:
                    normalized.append(f"{reason_class}: {summary}")
                elif summary:
                    normalized.append(summary)
                elif reason_class:
                    normalized.append(reason_class)

        return normalized

    def _build_dataforge_payload(self, artifact: ClaimedArtifact) -> dict[str, Any]:
        payload_json = artifact.payload_json

        pattern_id_value = payload_json.get("pattern_id")
        pattern_id = str(pattern_id_value).strip() if pattern_id_value is not None else ""
        if not pattern_id:
            pattern_id = f"pattern-{artifact.artifact_id}"

        return {
            "pattern_id": pattern_id,
            "failure_pattern_type": str(payload_json.get("failure_pattern_type", "")),
            "frequency_window": str(payload_json.get("frequency_window", "")),
            "occurrence_count": int(payload_json.get("occurrence_count", 0)),
            "severity": str(payload_json.get("severity", "")),
            "affected_contract_or_capability": str(
                payload_json.get("affected_contract_or_capability", "")
            ),
            "supporting_examples": self._normalize_supporting_examples(payload_json),
        }

    def _post_to_dataforge(self, artifact: ClaimedArtifact) -> None:
        observed_at = artifact.first_observed_at
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)

        envelope: dict[str, Any] = {
            "envelope_type": artifact.envelope_type,
            "envelope_version": artifact.envelope_version,
            "fleet_member_id": artifact.fleet_member_id,
            "runtime_bundle_id": "runtime-promotion",
            "runtime_bundle_version": "v1",
            "service": artifact.service,
            "dedupe_key": artifact.dedupe_key,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "payload": self._build_dataforge_payload(artifact),
        }

        body = json.dumps(envelope).encode("utf-8")
        url = receipt_url()
        headers, credential_state = receipt_headers(url)
        http_request = request.Request(url, data=body, headers=headers, method="POST")

        try:
            with _urlopen(http_request, 10) as response:
                status_code = response.getcode()
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                # A refusal is named with fixed codes only: the status, whether a credential was sent, and the
                # reason code. The response body and the key are never copied into the message.
                raise RuntimeError(
                    f"DataForge refused the receipt (HTTP {exc.code}; credential: {credential_state}; "
                    f"reason: {_refusal_code(exc)})"
                ) from None
            if 300 <= exc.code < 400:
                raise RuntimeError(f"DataForge answered a redirect (HTTP {exc.code}); it is not followed") from None
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DataForge HTTP {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"DataForge unreachable: {exc.reason}") from exc

        if status_code not in (200, 201):
            raise RuntimeError(f"Unexpected DataForge status: {status_code} body={response_body}")