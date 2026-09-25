from __future__ import annotations

import json

import pytest

from ally.commands.research import (
    run_research_inspect,
    run_research_search,
)
from ally.egress import EgressFieldManifest, EgressInspection
from ally.research import WebResearchExecution, WebSearchResult


class FakeResearchApplication:
    def inspect_web_research(self, request: object) -> EgressInspection:
        del request
        from uuid import uuid4

        return EgressInspection(
            request_id=uuid4(),
            service="synthetic.search",
            operation="web.search",
            decision="require_approval",
            fields=(
                EgressFieldManifest(name="count", classification="public"),
                EgressFieldManifest(
                    name="query",
                    classification="explicit_outbound",
                ),
            ),
        )

    def search_web(
        self,
        request: object,
        *,
        approved: bool = False,
    ) -> WebResearchExecution:
        del request
        from uuid import uuid4

        if not approved:
            return WebResearchExecution(
                request_id=uuid4(),
                service="synthetic.search",
                operation="web.search",
                decision="require_approval",
                status="approval_required",
            )
        return WebResearchExecution(
            request_id=uuid4(),
            service="synthetic.search",
            operation="web.search",
            decision="allow",
            status="succeeded",
            results=(
                WebSearchResult(
                    title="Synthetic",
                    url="https://example.test/result",
                    description="Public snippet",
                ),
            ),
        )


def test_research_inspect_cli_is_payload_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "ally.commands.research.build_default_application",
        lambda: FakeResearchApplication(),
    )

    assert (
        run_research_inspect(
            query="synthetic public query",
            count=5,
            json_output=True,
        )
        == 0
    )

    rendered = capsys.readouterr().out
    payload = json.loads(rendered)
    assert payload["decision"] == "require_approval"
    assert "synthetic public query" not in rendered


def test_research_search_cli_does_not_run_without_approval(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "ally.commands.research.build_default_application",
        lambda: FakeResearchApplication(),
    )

    assert (
        run_research_search(
            query="synthetic public query",
            count=5,
            approved=False,
            json_output=False,
        )
        == 1
    )
    assert "Approval required" in capsys.readouterr().out


def test_research_search_cli_renders_approved_results(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "ally.commands.research.build_default_application",
        lambda: FakeResearchApplication(),
    )

    assert (
        run_research_search(
            query="synthetic public query",
            count=5,
            approved=True,
            json_output=False,
        )
        == 0
    )
    rendered = capsys.readouterr().out
    assert "Synthetic" in rendered
    assert "https://example.test/result" in rendered
