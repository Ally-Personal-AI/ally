"""Human-facing commands for the opt-in macOS managed service."""

from __future__ import annotations

import json

from ally.service.macos_launchd import MacOSLaunchdService, ManagedServiceError


def run_managed_service(*, action: str, json_output: bool) -> int:
    service = MacOSLaunchdService()
    try:
        if action == "inspect":
            print(service.definition_bytes().decode("utf-8"), end="")
            return 0
        if action == "status":
            status = service.status()
        elif action == "install":
            status = service.install()
        elif action == "start":
            status = service.start()
        elif action == "stop":
            status = service.stop()
        elif action == "uninstall":
            status = service.uninstall()
        else:
            print("Managed service error: unknown action")
            return 2
    except (ManagedServiceError, OSError) as exc:
        print(f"Managed service error: {exc}")
        return 2

    if json_output:
        print(json.dumps(status.as_dict(), indent=2, sort_keys=True))
    else:
        print(f"Supported: {status.supported}")
        print(f"Configured: {status.configured}")
        print(f"Definition matches: {status.definition_matches}")
        print(f"Loaded: {status.loaded}")
        print(f"Running: {status.running}")
        print(f"Definition: {status.plist_path}")
    return 0
