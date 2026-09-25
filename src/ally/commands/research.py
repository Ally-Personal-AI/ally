"""Human-facing commands for privacy-gated public web research."""

from __future__ import annotations

import json

from pydantic import ValidationError

from ally.application import ApplicationUnavailableError
from ally.composition import build_default_application
from ally.research import ResearchServiceError, WebSearchRequest


def _request(*, query: str, count: int) -> WebSearchRequest | None:
    try:
        return WebSearchRequest(query=query, count=count)
    except ValidationError:
        print("Research request is invalid or exceeds the bounded query limits.")
        return None


def run_research_inspect(
    *,
    query: str,
    count: int,
    json_output: bool,
) -> int:
    """Inspect exact outbound field classifications without network access."""

    request = _request(query=query, count=count)
    if request is None:
        return 2

    try:
        inspection = build_default_application().inspect_web_research(request)
    except ApplicationUnavailableError:
        print("Web research is unavailable.")
        return 2

    if json_output:
        print(json.dumps(inspection.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(f"Service: {inspection.service}")
        print(f"Operation: {inspection.operation}")
        print(f"Decision: {inspection.decision}")
        for field in inspection.fields:
            print(f"Field: {field.name} ({field.classification})")
        if inspection.decision == "require_approval":
            print("Approval is required before the exact query is disclosed externally.")
    return 2 if inspection.decision == "deny" else 0


def run_research_search(
    *,
    query: str,
    count: int,
    approved: bool,
    json_output: bool,
) -> int:
    """Execute one exact approved search through controlled egress."""

    request = _request(query=query, count=count)
    if request is None:
        return 2

    try:
        result = build_default_application().search_web(
            request,
            approved=approved,
        )
    except (ApplicationUnavailableError, ResearchServiceError):
        print("Web research failed safely before a usable result was produced.")
        return 2

    if json_output:
        print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    elif result.status == "approval_required":
        print("Approval required before the exact search query is disclosed externally.")
    elif result.status == "denied":
        print("Web research was denied by the external-egress policy.")
    elif result.status == "failed":
        safe_error = result.error_class or "ExternalResearchError"
        print(f"Web research failed safely: {safe_error}")
    else:
        if not result.results:
            print("No web results.")
        for index, item in enumerate(result.results, start=1):
            print(f"{index}. {item.title}")
            print(f"   {item.url}")
            if item.description:
                print(f"   {item.description}")
        if result.more_results_available:
            print("More results are available.")

    if result.status == "succeeded":
        return 0
    if result.status == "approval_required":
        return 1
    return 2
