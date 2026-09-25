"""UI-neutral privacy gate for public web research."""

from __future__ import annotations

from pydantic import ValidationError

from ally.egress import EgressAdapter, EgressExecutor, EgressInspection, EgressRequest
from ally.research.models import WebResearchExecution, WebSearchPayload, WebSearchRequest

WEB_SEARCH_OPERATION = "web.search"


class ResearchServiceError(ValueError):
    """Raised when a research adapter violates Ally's normalized output contract."""


class ResearchService:
    """Inspect and execute exact-query research through controlled egress."""

    def __init__(
        self,
        *,
        executor: EgressExecutor,
        adapter: EgressAdapter,
    ) -> None:
        self._executor = executor
        self._adapter = adapter

    def _egress_request(self, request: WebSearchRequest) -> EgressRequest:
        return EgressRequest(
            service=self._adapter.service,
            operation=WEB_SEARCH_OPERATION,
            fields={
                "query": request.query,
                "count": request.count,
            },
        )

    def inspect_search(self, request: WebSearchRequest) -> EgressInspection:
        """Describe disclosure metadata without contacting the adapter."""

        return self._executor.inspect(
            self._egress_request(request),
            self._adapter,
        )

    def search(
        self,
        request: WebSearchRequest,
        *,
        approved: bool = False,
    ) -> WebResearchExecution:
        """Search only after controlled-egress policy authorizes the exact fields."""

        execution = self._executor.execute(
            self._egress_request(request),
            self._adapter,
            approved=approved,
        )
        if execution.status != "succeeded":
            return WebResearchExecution(
                request_id=execution.request_id,
                service=execution.service,
                operation=execution.operation,
                decision=execution.decision,
                status=execution.status,
                error_class=execution.error_class,
            )

        try:
            payload = WebSearchPayload.model_validate(execution.output)
        except ValidationError as exc:
            raise ResearchServiceError(
                "research adapter returned invalid normalized output"
            ) from exc

        return WebResearchExecution(
            request_id=execution.request_id,
            service=execution.service,
            operation=execution.operation,
            decision=execution.decision,
            status=execution.status,
            results=payload.results,
            more_results_available=payload.more_results_available,
        )
