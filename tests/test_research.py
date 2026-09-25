from __future__ import annotations

import pytest
from pydantic import JsonValue, ValidationError

from ally.egress import (
    DefaultEgressPolicy,
    EgressAuditRecord,
    EgressExecutor,
    EgressFieldSpec,
    EgressOperationSpec,
)
from ally.research import (
    WEB_SEARCH_OPERATION,
    ResearchService,
    WebSearchRequest,
)


class InMemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[EgressAuditRecord] = []

    def append(self, record: EgressAuditRecord) -> None:
        self.records.append(record)

    def list(self, *, limit: int = 100) -> tuple[EgressAuditRecord, ...]:
        return tuple(reversed(self.records[-limit:]))


class RecordingSearchAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []

    @property
    def service(self) -> str:
        return "synthetic.search"

    @property
    def operations(self) -> tuple[EgressOperationSpec, ...]:
        return (
            EgressOperationSpec(
                operation=WEB_SEARCH_OPERATION,
                fields=(
                    EgressFieldSpec(
                        name="query",
                        classification="explicit_outbound",
                    ),
                    EgressFieldSpec(
                        name="count",
                        classification="public",
                    ),
                ),
            ),
        )

    def send(
        self,
        operation: str,
        payload: dict[str, JsonValue],
    ) -> JsonValue:
        self.calls.append((operation, payload))
        return {
            "results": [
                {
                    "title": "Synthetic result",
                    "url": "https://example.test/result",
                    "description": "Public synthetic snippet.",
                }
            ],
            "more_results_available": False,
        }


def _service() -> tuple[ResearchService, RecordingSearchAdapter, InMemoryAuditStore]:
    adapter = RecordingSearchAdapter()
    audit = InMemoryAuditStore()
    return (
        ResearchService(
            executor=EgressExecutor(DefaultEgressPolicy(), audit),
            adapter=adapter,
        ),
        adapter,
        audit,
    )


def test_research_inspection_requires_approval_without_calling_adapter() -> None:
    service, adapter, audit = _service()

    inspection = service.inspect_search(
        WebSearchRequest(query="synthetic public topic", count=3)
    )

    assert inspection.decision == "require_approval"
    assert [(field.name, field.classification) for field in inspection.fields] == [
        ("count", "public"),
        ("query", "explicit_outbound"),
    ]
    assert adapter.calls == []
    assert audit.records == []
    assert "synthetic public topic" not in inspection.model_dump_json()


def test_research_search_stops_before_network_until_approved() -> None:
    service, adapter, audit = _service()
    request = WebSearchRequest(query="synthetic public topic", count=3)

    blocked = service.search(request)

    assert blocked.status == "approval_required"
    assert blocked.decision == "require_approval"
    assert blocked.results == ()
    assert adapter.calls == []
    assert len(audit.records) == 1
    assert audit.records[0].status == "approval_required"
    assert "synthetic public topic" not in audit.records[0].model_dump_json()


def test_approved_research_sends_only_declared_exact_fields() -> None:
    service, adapter, audit = _service()
    request = WebSearchRequest(query="synthetic public topic", count=3)

    result = service.search(request, approved=True)

    assert result.status == "succeeded"
    assert result.results[0].title == "Synthetic result"
    assert result.results[0].url == "https://example.test/result"
    assert adapter.calls == [
        (
            WEB_SEARCH_OPERATION,
            {"query": "synthetic public topic", "count": 3},
        )
    ]
    assert len(audit.records) == 1
    assert audit.records[0].status == "succeeded"
    assert "synthetic public topic" not in audit.records[0].model_dump_json()
    assert "synthetic public topic" not in result.model_dump_json()


def test_research_query_limits_fail_before_egress() -> None:
    with pytest.raises(ValidationError):
        WebSearchRequest(query="word " * 76)

    with pytest.raises(ValidationError):
        WebSearchRequest(query="line one\nline two")
