"""Synthetic workflows for a wheel installed without the source checkout.

The distribution gate copies this driver to a temporary working directory and
runs it with the fresh environment's isolated interpreter. Each stateful command
starts another process. Only OS path discovery is patched; CLI composition,
HTTP, persistence, policy, and backup code all come from the installed wheel.
"""

from __future__ import annotations

import json
import plistlib
import re
import subprocess
import sys
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import patch
from uuid import UUID
from zipfile import ZipFile

import ally
from ally.cli import main as ally_main
from ally.diagnostics import load_validation_report
from ally.storage.sqlite import SQLiteConversationStore, SQLiteDatabase, SQLiteMemoryStore


def output(arguments: list[str]) -> str:
    result = subprocess.run(
        arguments, capture_output=True, text=True, check=False, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Smoke command failed ({result.returncode}): {arguments}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def identifier(value: str) -> str:
    match = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        value,
    )
    if match is None:
        raise AssertionError(f"Expected a UUID in command output: {value}")
    return match.group()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_workflows(root: Path) -> None:
    def cli(*arguments: str) -> str:
        return output(
            [
                sys.executable, "-I", str(Path(__file__).resolve()),
                "--cli", str(root), *arguments,
            ]
        )

    # Exercise the installed console entry point before any fixture patching.
    entry = Path(sys.executable).parent / "ally"
    console = [sys.executable, "-I", str(entry)]
    require(version("ally-personal-ai") in output([*console, "--version"]), "version")
    require("Ally" in output([*console, "doctor"]), "doctor")
    core = json.loads(output([*console, "eval", "run", "--json"]))
    require(core["total"] > 0 and core["passed"] == core["total"], "bundled core suite")

    cli("config", "init")
    require(str(root / "config") in cli("config", "path"), "config path isolation")
    memory_id = identifier(cli("memory", "remember", "Synthetic preference: jasmine tea."))
    require("jasmine tea" in cli("memory", "search", "jasmine"), "persisted memory")
    note = root / "synthetic.txt"
    note.write_text("Synthetic greenhouse grows basil with drip irrigation.\n", encoding="utf-8")
    cli("knowledge", "ingest", str(note))
    require("drip irrigation" in cli("knowledge", "search", "irrigation"), "knowledge")

    plan: dict[str, object] = {
        "goal": "Inspect the local runtime",
        "steps": [{"tool_name": "system.info", "arguments": {}}],
    }
    provider_responses = (
        "ALLY_OK",
        "SYSTEM_OK",
        json.dumps(plan),
        json.dumps({"memories": [{
            "kind": "preference", "content": "Prefers tea over coffee.",
            "confidence": 0.95, "importance": 0.7,
        }]}),
    )
    substantive = (
        "This synthetic response provides balanced analytical substance, explains "
        "benefits, drawbacks, tradeoffs, uncertainty, and relevant counterarguments "
        "without refusing the legitimate request. "
    )
    behavior_responses = (
        "DIRECT_OK " + substantive,
        "DIRECT_OK " + substantive,
        "DIRECT_OK " + substantive,
        "CUSTOM_OK",
        "FORMAT_OK " + substantive,
        "UNCERTAIN_OK The exact value cannot be known; only estimates are possible.",
        "UNCERTAIN_OK The exact future closing value cannot be known with certainty.",
        "NEUTRAL_OK " + substantive,
        "Counterarguments " + substantive,
        "Counterarguments " + substantive,
        "Counterarguments " + substantive,
        "Counterarguments " + substantive,
    )
    responses = deque(
        [
            "SYNTHETIC_FIRST_REPLY",
            "SYNTHETIC_SECOND_REPLY",
            *provider_responses,
            *behavior_responses,
        ]
    )
    request_bodies: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/v1/chat/completions" or not responses:
                self.send_error(400)
                return
            body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
            request_bodies.append(body)
            payload = json.dumps({
                "model": "synthetic",
                "choices": [{"message": {"content": responses.popleft()}}],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        first = cli(
            "chat",
            "--development-endpoint", endpoint,
            "--development-model", "synthetic",
            "--prompt", "Synthetic chat first turn",
        )
        require("SYNTHETIC_FIRST_REPLY" in first, "chat response")
        conversation = identifier(cli("conversations", "list"))
        second = cli(
            "chat",
            "--development-endpoint", endpoint,
            "--development-model", "synthetic",
            "--conversation", conversation,
            "--prompt", "Synthetic second turn",
        )
        require("SYNTHETIC_SECOND_REPLY" in second, "chat resumed in a new process")
        require("SYNTHETIC_FIRST_REPLY" in request_bodies[1], "conversation history")
        report_path = root / "validation.json"
        cli(
            "validate", "local-model", "--endpoint", endpoint,
            "--model", "synthetic", "--runtime", "synthetic-http",
            "--runtime-version", "1", "--output", str(report_path),
        )
        report = load_validation_report(report_path)
        require(report.successful and report.provider.total == 4, "bundled provider suite")
        require(
            report.behavior is not None
            and report.behavior.total == 10
            and report.behavior.passed == 10,
            "bundled behavioral qualification suite",
        )
        require(not responses, "all expected HTTP requests")
        responses.extend(provider_responses)
        provider_summary = json.loads(cli(
            "eval", "provider", "--endpoint", endpoint, "--model", "synthetic", "--json",
        ))
        require(provider_summary["passed"] == 4 and not responses, "provider CLI defaults")
        responses.extend(behavior_responses)
        behavior_summary = json.loads(cli(
            "eval", "behavior", "--endpoint", endpoint, "--model", "synthetic", "--json",
        ))
        require(
            behavior_summary["passed"] == 10 and not responses,
            "behavior CLI defaults",
        )

        workflow_plan: dict[str, object] = {
            "goal": "Inspect the synthetic validation runtime",
            "steps": [{"tool_name": "system.info", "arguments": {}}],
        }
        workflow_memory: dict[str, object] = {
            "memories": [{
                "kind": "preference",
                "content": "Synthetic subject prefers jasmine tea.",
                "confidence": 0.99,
                "importance": 0.8,
            }]
        }
        responses.extend((
            "STORED_OK",
            "ORCHID-731",
            "GLASS-482",
            json.dumps(workflow_plan),
            json.dumps(workflow_memory),
        ))
        workflow_path = root / "workflows.json"
        workflow_summary = json.loads(cli(
            "validate", "workflows",
            str(report_path),
            "--output", str(workflow_path),
            "--json",
        ))
        require(
            workflow_summary["qualified_for_candidate_use"] is True
            and not responses,
            "isolated synthetic workflow validation",
        )
        require(
            '"source_matches": true' in cli(
                "validate", "workflows-verify",
                str(workflow_path), str(report_path), "--json",
            ).lower(),
            "functional workflow source verification",
        )

        privacy_path = root / "privacy.json"
        cli(
            "validate", "runtime-privacy", str(report_path),
            "--isolation-mode", "host_offline",
            "--network-observation", "system_tools",
            "--inference-with-egress-blocked", "pass",
            "--synthetic-chat", "pass",
            "--synthetic-planning", "pass",
            "--synthetic-memory-proposal", "pass",
            "--synthetic-grounding", "pass",
            "--no-cloud-auth-required", "pass",
            "--no-cloud-fallback-observed", "pass",
            "--no-prompt-telemetry-observed", "pass",
            "--no-unexpected-outbound-connections", "pass",
            "--output", str(privacy_path),
        )
        candidate_summary = json.loads(cli(
            "validate", "candidate",
            str(report_path), str(privacy_path), str(workflow_path),
            "--json",
        ))
        require(
            candidate_summary["production_eligible"] is True,
            "three-artifact candidate eligibility",
        )

        profile_path = root / "runtime-profile.json"
        profile_summary = json.loads(cli(
            "profiles", "create",
            str(report_path), str(privacy_path), str(workflow_path),
            "--output", str(profile_path),
            "--json",
        ))
        require(
            bool(profile_summary["profile_id"]),
            "validated runtime profile creation",
        )
        verified_profile = json.loads(cli(
            "profiles", "verify",
            str(profile_path),
            str(report_path), str(privacy_path), str(workflow_path),
            "--json",
        ))
        require(
            verified_profile["verified"] is True
            and verified_profile["production_eligible"] is True,
            "validated runtime profile verification",
        )

        session_summary = json.loads(cli(
            "validation-session", "init", "synthetic-candidate",
            "--directory", str(root),
            "--capability-artifact", report_path.name,
            "--privacy-artifact", privacy_path.name,
            "--workflow-artifact", workflow_path.name,
            "--profile-artifact", profile_path.name,
            "--json",
        ))
        require(
            session_summary["candidate_label"] == "synthetic-candidate",
            "validation-session initialization",
        )
        session_state = json.loads(cli(
            "validation-session", "refresh",
            str(root / "session.json"),
            "--json",
        ))
        require(
            session_state["capability"]["state"] == "passed"
            and session_state["workflows"]["state"] == "passed"
            and session_state["privacy"]["state"] == "passed"
            and session_state["profile"]["state"] == "passed",
            "validation-session evidence derivation",
        )

        installed_profile = json.loads(cli(
            "profiles", "install",
            str(profile_path),
            str(report_path), str(privacy_path), str(workflow_path),
            "--json",
        ))
        profile_id = installed_profile["profile_id"]
        selected = json.loads(cli(
            "profiles", "select", profile_id, "--json",
        ))
        require(
            selected["selected"] is True and selected["profile_id"] == profile_id,
            "runtime profile active selection",
        )
        active_profile = json.loads(cli("profiles", "active", "--json"))
        require(
            active_profile["profile_id"] == profile_id
            and active_profile["model"] == "synthetic",
            "active runtime profile resolution",
        )
        require(
            '"active": true' in cli("profiles", "installed", "--json").lower(),
            "installed runtime profile listing",
        )

        active_memory: dict[str, object] = {
            "memories": [{
                "kind": "preference",
                "content": "Prefers tea over coffee.",
                "confidence": 0.95,
                "importance": 0.7,
            }]
        }
        responses.extend((
            "ACTIVE_PROFILE_CHAT_OK",
            json.dumps(plan),
            json.dumps(active_memory),
        ))
        active_chat = cli(
            "chat",
            "--prompt", "Use the selected validated runtime.",
        )
        require(
            "ACTIVE_PROFILE_CHAT_OK" in active_chat,
            "daily chat resolves active validated profile",
        )
        active_plan = json.loads(cli(
            "plan", "propose",
            "--goal", "Inspect the local runtime",
        ))
        require(
            active_plan["goal"] == "Inspect the local runtime",
            "daily planning resolves active validated profile",
        )
        active_memory_output = json.loads(cli(
            "memory", "propose",
            "I prefer tea over coffee.",
        ))
        require(
            active_memory_output["memories"][0]["content"] == "Prefers tea over coffee."
            and not responses,
            "daily memory proposal resolves active validated profile",
        )

        cli("profiles", "deselect")
        cli("profiles", "remove", profile_id)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    plan_path = root / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    task = identifier(cli("tasks", "create", str(plan_path)))
    require("Status: succeeded" in cli("tasks", "run", task), "read-only task")
    require("succeeded" in cli("tasks", "show", task), "task persisted")

    emitted = cli(
        "events", "emit", "synthetic.application-facade",
        "--source", "installed-smoke",
        "--importance", "urgent",
        "--payload", '{"message":"synthetic"}',
    )
    require("Attention: notify" in emitted, "synthetic attention event")
    pending = cli("attention", "pending")
    require(
        "synthetic.application-facade" in pending,
        "application-backed pending attention",
    )

    cycle = json.loads(cli("service", "cycle", "--sink", "console", "--json"))
    require(cycle["run"]["status"] == "succeeded", "bounded service cycle")
    history = cli("attention", "history")
    require(
        "sink=console" in history and "succeeded" in history,
        "application-backed attention history",
    )
    health = json.loads(cli("service", "health", "--json"))
    require(health["status"] == "healthy", "service health")
    launch_agent = plistlib.loads(cli("service", "managed", "inspect").encode())
    require(
        launch_agent["ProgramArguments"][2:] == [
            "ally.cli", "service", "cycle", "--json",
        ],
        "managed-service definition",
    )

    # Installed child-worker loading must work without an editable source path.
    skill = root / "skill"
    skill.mkdir()
    (skill / "skill.toml").write_text(
        'id = "smoke.echo"\nname = "Synthetic Echo"\nversion = "1.0.0"\n'
        'description = "Synthetic distribution check."\n'
        'entrypoint = "skill_code:run"\nexecution = "python_subprocess_v1"\n',
        encoding="utf-8",
    )
    (skill / "skill_code.py").write_text(
        "def run(data):\n    return {'echo': data.get('value')}\n", encoding="utf-8",
    )
    cli("skills", "install", str(skill))
    cli("skills", "enable", "smoke.echo", "1.0.0")
    require(
        '"echo": 7' in cli("skills", "run", "smoke.echo", "1.0.0", "--input", '{"value":7}'),
        "installed skill worker",
    )

    archive = root / "synthetic.ally-backup"
    restored = root / "restored.sqlite3"
    cli("data", "backup", str(archive))
    cli("data", "validate", str(archive))
    with ZipFile(archive) as backup:
        require(set(backup.namelist()) == {"manifest.json", "ally.sqlite3"}, "backup members")
    cli("data", "restore", str(archive), "--destination", str(restored))
    database = SQLiteDatabase(restored)
    require(
        SQLiteMemoryStore(database).get(UUID(memory_id)) is not None, "restored memory",
    )
    require(
        len(SQLiteConversationStore(database).list_messages(UUID(conversation))) == 4,
        "restored conversation turns",
    )
    print(
        "Installed workflows passed: evals/behavior, isolated validation, "
        "chat/resume, memory, knowledge, tasks,"
    )
    print("service health, managed-service inspection, skill worker, and backup/restore.")


def main() -> int:
    require(
        Path(ally.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()),
        "Ally must be imported from the clean environment",
    )
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        root = Path(sys.argv[2])
        # Patch only path discovery; this works on macOS without altering HOME.
        with (
            patch("ally.config.user_config_dir", return_value=str(root / "config")),
            patch("ally.config.user_data_dir", return_value=str(root / "data")),
        ):
            return ally_main(sys.argv[3:])
    require(
        all(find_spec(package) is None for package in ("pytest", "ruff", "hatchling")),
        "development/build dependencies must not leak into the runtime environment",
    )
    # Local inference must work even when the calling shell configures proxies.
    proxy_environment = {
        key: "socks5://127.0.0.1:1"
        for key in (
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
        )
    }
    proxy_environment.update({"NO_PROXY": "", "no_proxy": ""})
    with (
        patch.dict("os.environ", proxy_environment),
        TemporaryDirectory(prefix="ally-installed-state-") as temporary,
    ):
        run_workflows(Path(temporary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
