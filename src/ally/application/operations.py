"""UI-neutral operational services used by AllyApplication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ally.attention import AttentionDeliveryStore
from ally.events import EventStore
from ally.research import ResearchService
from ally.service import (
    DesktopProactiveCoordinator,
    ServiceCycleRunStore,
    ServiceHealthReport,
)
from ally.service.macos_launchd import MacOSLaunchdService
from ally.tasks import TaskRunner, TaskStore
from ally.tools import ToolSpec

ServiceHealthProvider = Callable[[], ServiceHealthReport]


@dataclass(frozen=True)
class ApplicationOperations:
    """Optional operational dependencies for tasks, attention, and service state."""

    tasks: TaskStore
    task_runner: TaskRunner
    events: EventStore
    attention_deliveries: AttentionDeliveryStore
    service_runs: ServiceCycleRunStore
    service_health: ServiceHealthProvider
    planning_tools: tuple[ToolSpec, ...] = ()
    desktop_proactive: DesktopProactiveCoordinator | None = None
    legacy_managed_service: MacOSLaunchdService | None = None
    research: ResearchService | None = None
