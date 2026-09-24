from pathlib import Path

from pydantic import JsonValue

from ally.egress import (
    DefaultEgressPolicy,
    EgressAuditRecord,
    EgressExecutor,
    EgressFieldSpec,
    EgressOperationSpec,
    EgressRequest,
)
from ally.storage.sqlite import SQLiteDatabase, SQLiteEgressAuditStore


class InMemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[EgressAuditRecord] = []

    def append(self, record: EgressAuditRecord) -> None:
        self.records.append(record)

    def list(self, *, limit: int = 100) -> tuple[EgressAuditRecord, ...]:
        return tuple(reversed(self.records[-limit:]))


class RecordingAdapter:
    def __init__(
        self,
        *,
        service: str = "example.service",
        operations: tuple[EgressOperationSpec, ...],
        fail: bool = False,
    ) -> None:
        self._service = service
        self._operations = operations
        self._fail = fail
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []

    @property
    def service(self) -> str:
        return self._service

    @property
    def operations(self) -> tuple[EgressOperationSpec, ...]:
        return self._operations

    def send(
        self,
        operation: str,
        payload: dict[str, JsonValue],
    ) -> JsonValue:
        self.calls.append((operation, payload))
        if self._fail:
            raise RuntimeError("sensitive remote failure details must not persist")
        return {"ok": True}


def operation(
    *fields: EgressFieldSpec,
    name: str = "send",
) -> EgressOperationSpec:
    return EgressOperationSpec(operation=name, fields=fields)


def executor() -> tuple[EgressExecutor, InMemoryAuditStore]:
    audit = InMemoryAuditStore()
    return EgressExecutor(DefaultEgressPolicy(), audit), audit


def test_public_fields_can_cross_without_approval() -> None:
    adapter = RecordingAdapter(
        operations=(
            operation(
                EgressFieldSpec(
                    name="query",
                    classification="public",
                )
            ),
        )
    )
    runtime, audit = executor()
    request = EgressRequest(
        service=adapter.service,
        operation="send",
        fields={"query": "public market data"},
    )

    result = runtime.execute(request, adapter)

    assert result.status == "succeeded"
    assert result.decision == "allow"
    assert adapter.calls == [("send", {"query": "public market data"})]
    assert audit.records[0].status == "succeeded"


def test_explicit_outbound_requires_approval_before_adapter_call() -> None:
    adapter = RecordingAdapter(
        operations=(
            operation(
                EgressFieldSpec(
                    name="recipient",
                    classification="explicit_outbound",
                ),
                EgressFieldSpec(
                    name="body",
                    classification="explicit_outbound",
                ),
            ),
        )
    )
    runtime, audit = executor()
    request = EgressRequest(
        service=adapter.service,
        operation="send",
        fields={
            "recipient": "person@example.test",
            "body": "Synthetic outbound message",
        },
    )

    blocked = runtime.execute(request, adapter)
    allowed = runtime.execute(request, adapter, approved=True)

    assert blocked.status == "approval_required"
    assert blocked.decision == "require_approval"
    assert allowed.status == "succeeded"
    assert len(adapter.calls) == 1
    assert [record.status for record in audit.records] == [
        "approval_required",
        "succeeded",
    ]


def test_private_internal_and_secret_fields_are_denied_even_when_approved() -> None:
    for classification in ("private_internal", "secret"):
        adapter = RecordingAdapter(
            operations=(
                operation(
                    EgressFieldSpec(
                        name="value",
                        classification=classification,
                    )
                ),
            )
        )
        runtime, audit = executor()
        request = EgressRequest(
            service=adapter.service,
            operation="send",
            fields={"value": "must-stay-inside"},
        )

        result = runtime.execute(request, adapter, approved=True)

        assert result.status == "denied"
        assert result.decision == "deny"
        assert adapter.calls == []
        assert audit.records[0].fields[0].classification == classification


def test_adapter_owns_field_classification_not_request() -> None:
    adapter = RecordingAdapter(
        operations=(
            operation(
                EgressFieldSpec(
                    name="profile",
                    classification="private_internal",
                )
            ),
        )
    )
    runtime, _ = executor()

    request = EgressRequest(
        service=adapter.service,
        operation="send",
        fields={"profile": "caller cannot relabel this as public"},
    )
    inspection = runtime.inspect(request, adapter, approved=True)

    assert inspection.decision == "deny"
    assert inspection.fields[0].classification == "private_internal"


def test_undeclared_missing_or_mismatched_requests_fail_before_adapter_call() -> None:
    adapter = RecordingAdapter(
        operations=(
            operation(
                EgressFieldSpec(name="body", classification="explicit_outbound")
            ),
        )
    )
    runtime, audit = executor()

    undeclared = runtime.execute(
        EgressRequest(
            service=adapter.service,
            operation="send",
            fields={"body": "ok", "hidden_context": "must not leave"},
        ),
        adapter,
        approved=True,
    )
    missing = runtime.execute(
        EgressRequest(
            service=adapter.service,
            operation="send",
            fields={},
        ),
        adapter,
        approved=True,
    )
    mismatch = runtime.execute(
        EgressRequest(
            service="other.service",
            operation="send",
            fields={"body": "ok"},
        ),
        adapter,
        approved=True,
    )

    assert [undeclared.status, missing.status, mismatch.status] == [
        "denied",
        "denied",
        "denied",
    ]
    assert adapter.calls == []
    assert [record.error_class for record in audit.records] == [
        "UndeclaredField",
        "MissingRequiredField",
        "ServiceMismatch",
    ]


def test_inspection_is_payload_free() -> None:
    marker = "SENSITIVE-INSPECTION-MARKER"
    adapter = RecordingAdapter(
        operations=(
            operation(
                EgressFieldSpec(
                    name="body",
                    classification="explicit_outbound",
                )
            ),
        )
    )
    runtime, _ = executor()
    request = EgressRequest(
        service=adapter.service,
        operation="send",
        fields={"body": marker},
    )

    inspection = runtime.inspect(request, adapter)

    assert marker not in inspection.model_dump_json()
    assert inspection.fields[0].name == "body"
    assert inspection.fields[0].classification == "explicit_outbound"


def test_adapter_exception_is_reduced_to_class_name_in_audit() -> None:
    adapter = RecordingAdapter(
        operations=(
            operation(EgressFieldSpec(name="query", classification="public")),
        ),
        fail=True,
    )
    runtime, audit = executor()
    request = EgressRequest(
        service=adapter.service,
        operation="send",
        fields={"query": "synthetic"},
    )

    result = runtime.execute(request, adapter)

    assert result.status == "failed"
    assert result.error_class == "RuntimeError"
    assert audit.records[0].error_class == "RuntimeError"
    assert "sensitive remote failure" not in audit.records[0].model_dump_json()


def test_sqlite_audit_never_persists_outbound_values(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    marker = "SENSITIVE-EGRESS-VALUE-9F9BCE"
    store = SQLiteEgressAuditStore(SQLiteDatabase(path))
    adapter = RecordingAdapter(
        operations=(
            operation(
                EgressFieldSpec(
                    name="body",
                    classification="explicit_outbound",
                )
            ),
        )
    )
    runtime = EgressExecutor(DefaultEgressPolicy(), store)
    request = EgressRequest(
        service=adapter.service,
        operation="send",
        fields={"body": marker},
    )

    result = runtime.execute(request, adapter, approved=True)
    records = store.list()

    assert result.status == "succeeded"
    assert len(records) == 1
    assert records[0].fields[0].name == "body"
    assert marker not in records[0].model_dump_json()
    assert marker.encode() not in path.read_bytes()
