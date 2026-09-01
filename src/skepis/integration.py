"""Project-scoped MCP connection helpers for supported coding-agent clients."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping


MCP_SERVER_NAME = "skepis"
EXPECTED_MCP_TOOLS = (
    "skepis_preflight",
    "skepis_inspect",
    "skepis_run",
    "skepis_report",
    "skepis_read_protected",
)
AGENT_INSTRUCTION = (
    "When accessing benchmark resources registered as protected by Skepis, use "
    "the Skepis protected-read MCP tool rather than reading them directly. Use "
    "Skepis for evaluation runs involving the configured benchmark."
)


@dataclass(frozen=True)
class ClientDefinition:
    """A client surface that Skepis can configure without global state."""

    client_id: str
    label: str
    config_relative_path: Path
    instruction_relative_path: Path
    detect_commands: tuple[str, ...]


CLIENT_DEFINITIONS = (
    ClientDefinition(
        client_id="claude",
        label="Claude Code",
        config_relative_path=Path(".mcp.json"),
        instruction_relative_path=Path("CLAUDE.md"),
        detect_commands=("claude",),
    ),
    ClientDefinition(
        client_id="cursor",
        label="Cursor",
        config_relative_path=Path(".cursor") / "mcp.json",
        instruction_relative_path=Path(".cursor") / "rules" / "skepis.mdc",
        detect_commands=("cursor-agent", "cursor"),
    ),
)


class ConnectionError(ValueError):
    """A project-scoped MCP connection could not be configured or verified."""


def detect_clients(
    project_root: str | Path,
    requested_client: str | None = None,
) -> tuple[ClientDefinition, ...]:
    """Find supported clients from project files or installed client commands."""

    root = Path(project_root).expanduser().resolve(strict=False)
    if requested_client is not None and requested_client != "auto":
        for definition in CLIENT_DEFINITIONS:
            if definition.client_id == requested_client:
                return (definition,)
        raise ConnectionError(
            f"unsupported MCP client {requested_client!r}; choose claude, cursor, or auto"
        )

    detected: list[ClientDefinition] = []
    for definition in CLIENT_DEFINITIONS:
        config_path = root / definition.config_relative_path
        command_found = any(
            shutil.which(command) is not None
            for command in definition.detect_commands
        )
        if config_path.is_file() or command_found:
            detected.append(definition)
    return tuple(detected)


def connect_project(
    project_root: str | Path,
    config_path: str | Path,
    *,
    requested_client: str | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    """Configure and verify the existing Skepis MCP server for a project."""

    root = Path(project_root).expanduser().resolve(strict=False)
    canonical_config = Path(config_path).expanduser().resolve(strict=False)
    definitions = detect_clients(root, requested_client)
    manual = _manual_configuration(canonical_config)
    if not definitions:
        return {
            "status": "NO_CLIENT",
            "detected": [],
            "configured": [],
            "connection_verified": False,
            "manual_configuration": manual,
            "reason": "no_supported_mcp_client_detected",
        }

    configured: list[dict[str, Any]] = []
    for definition in definitions:
        try:
            client_config = root / definition.config_relative_path
            _write_client_config(client_config, canonical_config)
            instruction_path = root / definition.instruction_relative_path
            _write_agent_instruction(instruction_path, definition.client_id)
            server_spec = _server_spec(canonical_config)
            verification = (
                _verify_server(server_spec, root)
                if verify
                else {"verified": False, "reason": "verification_skipped", "tools": []}
            )
        except (ConnectionError, OSError, ValueError) as exc:
            return {
                "status": "FAILED",
                "detected": [item.label for item in definitions],
                "configured": configured,
                "connection_verified": False,
                "manual_configuration": manual,
                "reason": _safe_error_reason(exc),
            }
        configured.append(
            {
                "client": definition.client_id,
                "label": definition.label,
                "config_path": str(client_config),
                "instruction_path": str(instruction_path),
                "verified": verification["verified"],
                "tools": verification["tools"],
                "verification_reason": verification.get("reason"),
            }
        )

    verified = all(item["verified"] for item in configured)
    return {
        "status": "CONNECTED" if verified else "FAILED",
        "detected": [item.label for item in definitions],
        "configured": configured,
        "connection_verified": verified,
        "manual_configuration": manual,
        "reason": None if verified else "mcp_server_verification_failed",
    }


def _write_client_config(path: Path, canonical_config: Path) -> None:
    data: dict[str, Any]
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConnectionError(f"client MCP config is not valid JSON: {path}") from exc
        if not isinstance(raw, dict):
            raise ConnectionError(f"client MCP config must be a JSON object: {path}")
        data = dict(raw)
    else:
        data = {}

    raw_servers = data.get("mcpServers", {})
    if not isinstance(raw_servers, Mapping):
        raise ConnectionError(f"client MCP config has an invalid mcpServers value: {path}")
    servers = dict(raw_servers)
    servers[MCP_SERVER_NAME] = _server_spec(canonical_config)
    data["mcpServers"] = servers

    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        path,
        json.dumps(data, indent=2, sort_keys=True) + "\n",
    )


def _write_agent_instruction(path: Path, client_id: str) -> None:
    if client_id == "cursor":
        content = (
            "---\n"
            "description: Use Skepis for protected benchmark resources and evaluation\n"
            "alwaysApply: true\n"
            "---\n\n"
            f"{AGENT_INSTRUCTION}\n"
        )
    else:
        heading = "## Skepis\n"
        content = f"{heading}\n{AGENT_INSTRUCTION}\n"

    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if AGENT_INSTRUCTION in existing:
            return
        separator = "\n" if existing.endswith("\n") else "\n\n"
        _atomic_write_text(path, existing + separator + content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, content)


def _atomic_write_text(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _server_spec(canonical_config: Path) -> dict[str, Any]:
    runtime_python = os.environ.get("SKEPIS_RUNTIME_PYTHON")
    command = runtime_python or shutil.which("skepis-mcp") or sys.executable
    if runtime_python or command == sys.executable:
        args = ["-m", "skepis.mcp", "--config", str(canonical_config)]
    else:
        args = ["--config", str(canonical_config)]

    environment: dict[str, str] = {"SKEPIS_CONFIG": str(canonical_config)}
    source_root = os.environ.get("SKEPIS_RUNTIME_SOURCE_ROOT")
    if not source_root:
        candidate_root = Path(__file__).resolve().parents[1]
        if (candidate_root / "skepis").is_dir():
            source_root = str(candidate_root)
    if source_root:
        environment["PYTHONPATH"] = source_root
    return {"command": command, "args": args, "env": environment}


def _manual_configuration(canonical_config: Path) -> dict[str, Any]:
    return {"mcpServers": {MCP_SERVER_NAME: _server_spec(canonical_config)}}


def _verify_server(server_spec: Mapping[str, Any], project_root: Path) -> dict[str, Any]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        return {
            "verified": False,
            "reason": "mcp_sdk_unavailable",
            "tools": [],
        }

    command = server_spec.get("command")
    args = server_spec.get("args")
    extra_environment = server_spec.get("env", {})
    if not isinstance(command, str) or not isinstance(args, list):
        return {"verified": False, "reason": "invalid_server_command", "tools": []}
    if not isinstance(extra_environment, Mapping):
        return {"verified": False, "reason": "invalid_server_environment", "tools": []}

    environment = dict(os.environ)
    environment.update(
        {
            str(key): str(value)
            for key, value in extra_environment.items()
        }
    )

    async def exercise() -> list[str]:
        parameters = StdioServerParameters(
            command=command,
            args=[str(value) for value in args],
            env=environment,
            cwd=project_root,
        )
        with open(os.devnull, "w", encoding="utf-8") as errlog:
            async with stdio_client(parameters, errlog=errlog) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    return [str(tool.name) for tool in listed.tools]

    try:
        tools = asyncio.run(exercise())
    except Exception as exc:
        return {
            "verified": False,
            "reason": f"server_start_failed:{type(exc).__name__}",
            "tools": [],
        }
    missing = [name for name in EXPECTED_MCP_TOOLS if name not in tools]
    if missing:
        return {
            "verified": False,
            "reason": "missing_tools:" + ",".join(missing),
            "tools": tools,
        }
    return {"verified": True, "reason": None, "tools": tools}


def _safe_error_reason(error: Exception) -> str:
    if isinstance(error, ConnectionError):
        return str(error)
    return type(error).__name__
