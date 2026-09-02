"""Project-scoped MCP connection helpers for supported coding-agent clients."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib
from typing import Any, Mapping, Protocol


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


class ConnectionError(ValueError):
    """A project-scoped MCP connection could not be configured or verified."""


class ProjectAdapter(Protocol):
    """The deliberately small contract for a built-in project agent adapter."""

    definition: ClientDefinition

    def detect(self, project_root: Path) -> bool:
        """Return whether this host is present in the project or on PATH."""

    def configure_mcp(
        self,
        project_root: Path,
        server_spec: Mapping[str, Any],
    ) -> Path:
        """Merge the Skepis server into the host's project-local configuration."""

    def configure_instructions(self, project_root: Path) -> Path:
        """Install the host's minimal project-scoped behavioral instruction."""

    def verify(
        self,
        project_root: Path,
        server_spec: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Verify the existing Skepis server and its complete tool surface."""


@dataclass(frozen=True)
class _AdapterBase:
    definition: ClientDefinition

    def detect(self, project_root: Path) -> bool:
        config_path = project_root / self.definition.config_relative_path
        return config_path.is_file() or any(
            shutil.which(command) is not None
            for command in self.definition.detect_commands
        )

    def configure_instructions(self, project_root: Path) -> Path:
        path = project_root / self.definition.instruction_relative_path
        _write_agent_instruction(path, self.definition.client_id)
        return path

    def verify(
        self,
        project_root: Path,
        server_spec: Mapping[str, Any],
    ) -> dict[str, Any]:
        return _verify_server(server_spec, project_root)


@dataclass(frozen=True)
class _JsonAdapter(_AdapterBase):
    def configure_mcp(
        self,
        project_root: Path,
        server_spec: Mapping[str, Any],
    ) -> Path:
        path = project_root / self.definition.config_relative_path
        _write_json_client_config(path, server_spec)
        return path


@dataclass(frozen=True)
class _CodexAdapter(_AdapterBase):
    def configure_mcp(
        self,
        project_root: Path,
        server_spec: Mapping[str, Any],
    ) -> Path:
        path = project_root / self.definition.config_relative_path
        _write_codex_client_config(path, server_spec)
        return path


CLIENT_ADAPTERS: tuple[ProjectAdapter, ...] = (
    _JsonAdapter(
        ClientDefinition(
            client_id="claude",
            label="Claude Code",
            config_relative_path=Path(".mcp.json"),
            instruction_relative_path=Path("CLAUDE.md"),
            detect_commands=("claude",),
        )
    ),
    _JsonAdapter(
        ClientDefinition(
            client_id="cursor",
            label="Cursor",
            config_relative_path=Path(".cursor") / "mcp.json",
            instruction_relative_path=Path(".cursor") / "rules" / "skepis.mdc",
            detect_commands=("cursor-agent", "cursor"),
        )
    ),
    _CodexAdapter(
        ClientDefinition(
            client_id="codex",
            label="Codex",
            config_relative_path=Path(".codex") / "config.toml",
            instruction_relative_path=Path("AGENTS.md"),
            detect_commands=("codex",),
        )
    ),
    _JsonAdapter(
        ClientDefinition(
            client_id="antigravity",
            label="Antigravity",
            config_relative_path=Path(".agents") / "mcp_config.json",
            instruction_relative_path=Path(".agents") / "rules" / "skepis.md",
            detect_commands=("agy", "antigravity"),
        )
    ),
    _JsonAdapter(
        ClientDefinition(
            client_id="gemini",
            label="Gemini CLI",
            config_relative_path=Path(".gemini") / "settings.json",
            instruction_relative_path=Path("GEMINI.md"),
            detect_commands=("gemini",),
        )
    ),
)

CLIENT_DEFINITIONS = tuple(adapter.definition for adapter in CLIENT_ADAPTERS)
SUPPORTED_CLIENT_IDS = tuple(definition.client_id for definition in CLIENT_DEFINITIONS)
_CLIENT_ALIASES = {
    "antigravity-cli": "antigravity",
    "gemini-cli": "gemini",
}


def detect_clients(
    project_root: str | Path,
    requested_client: str | None = None,
) -> tuple[ClientDefinition, ...]:
    """Find supported clients from project files or installed client commands."""

    root = Path(project_root).expanduser().resolve(strict=False)
    if requested_client is not None and requested_client != "auto":
        requested_client = _CLIENT_ALIASES.get(requested_client, requested_client)
        for definition in CLIENT_DEFINITIONS:
            if definition.client_id == requested_client:
                return (definition,)
        raise ConnectionError(
            f"unsupported MCP client {requested_client!r}; choose "
            + ", ".join((*SUPPORTED_CLIENT_IDS, "auto"))
        )

    return tuple(
        adapter.definition
        for adapter in CLIENT_ADAPTERS
        if adapter.detect(root)
    )


def _detect_adapters(
    project_root: Path,
    requested_client: str | None,
) -> tuple[ProjectAdapter, ...]:
    definitions = detect_clients(project_root, requested_client)
    selected = {definition.client_id for definition in definitions}
    return tuple(
        adapter
        for adapter in CLIENT_ADAPTERS
        if adapter.definition.client_id in selected
    )


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
    adapters = _detect_adapters(root, requested_client)
    manual = _manual_configuration(canonical_config)
    if not adapters:
        return {
            "status": "NO_CLIENT",
            "detected": [],
            "configured": [],
            "connection_verified": False,
            "manual_configuration": manual,
            "reason": "no_supported_mcp_client_detected",
        }

    configured: list[dict[str, Any]] = []
    server_spec = _server_spec(canonical_config)
    for adapter in adapters:
        definition = adapter.definition
        try:
            client_config = adapter.configure_mcp(root, server_spec)
            instruction_path = adapter.configure_instructions(root)
            verification = (
                adapter.verify(root, server_spec)
                if verify
                else {"verified": False, "reason": "verification_skipped", "tools": []}
            )
        except (ConnectionError, OSError, ValueError) as exc:
            return {
                "status": "FAILED",
                "detected": [item.definition.label for item in adapters],
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
        "detected": [item.definition.label for item in adapters],
        "configured": configured,
        "connection_verified": verified,
        "manual_configuration": manual,
        "reason": None if verified else "mcp_server_verification_failed",
    }


def _write_json_client_config(
    path: Path,
    server_spec: Mapping[str, Any],
) -> None:
    data: dict[str, Any]
    if path.exists():
        if not path.is_file():
            raise ConnectionError(f"client MCP config is not a file: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConnectionError(f"client MCP config could not be read: {path}") from exc
        except json.JSONDecodeError as exc:
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
    servers[MCP_SERVER_NAME] = _merge_server_entry(
        servers.get(MCP_SERVER_NAME),
        server_spec,
        path,
    )
    data["mcpServers"] = servers

    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        path,
        json.dumps(data, indent=2, sort_keys=True) + "\n",
    )


def _write_codex_client_config(
    path: Path,
    server_spec: Mapping[str, Any],
) -> None:
    data: dict[str, Any]
    if path.exists():
        if not path.is_file():
            raise ConnectionError(f"Codex config is not a file: {path}")
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConnectionError(f"Codex config could not be read: {path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConnectionError(f"Codex config is not valid TOML: {path}") from exc
        if not isinstance(raw, dict):
            raise ConnectionError(f"Codex config must be a TOML table: {path}")
        data = dict(raw)
    else:
        data = {}

    raw_servers = data.get("mcp_servers", {})
    if not isinstance(raw_servers, Mapping):
        raise ConnectionError(f"Codex config has an invalid mcp_servers value: {path}")
    servers = dict(raw_servers)
    servers[MCP_SERVER_NAME] = _merge_server_entry(
        servers.get(MCP_SERVER_NAME),
        server_spec,
        path,
    )
    data["mcp_servers"] = servers

    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, _render_toml(data))


def _merge_server_entry(
    existing: Any,
    server_spec: Mapping[str, Any],
    path: Path,
) -> dict[str, Any]:
    if existing is not None and not isinstance(existing, Mapping):
        raise ConnectionError(
            f"client MCP config has an invalid {MCP_SERVER_NAME!r} server entry: {path}"
        )
    merged = dict(existing or {})
    existing_env = merged.get("env")
    if existing_env is not None and not isinstance(existing_env, Mapping):
        raise ConnectionError(
            f"client MCP config has an invalid {MCP_SERVER_NAME!r} environment: {path}"
        )
    incoming_env = server_spec.get("env", {})
    if not isinstance(incoming_env, Mapping):
        raise ConnectionError("Skepis server environment must be a mapping")
    merged_env = dict(existing_env or {})
    merged_env.update({str(key): str(value) for key, value in incoming_env.items()})
    for key, value in server_spec.items():
        if key != "env":
            merged[key] = value
    merged["env"] = merged_env
    return merged


def _write_agent_instruction(path: Path, client_id: str) -> None:
    if client_id == "cursor":
        content = (
            "---\n"
            "description: Use Skepis for protected benchmark resources and evaluation\n"
            "alwaysApply: true\n"
            "---\n\n"
            f"{AGENT_INSTRUCTION}\n"
        )
    elif client_id == "antigravity":
        content = f"# Skepis\n\n{AGENT_INSTRUCTION}\n"
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
    if path.exists():
        raise ConnectionError(f"agent instruction path is not a file: {path}")
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


_TOML_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _render_toml(data: Mapping[str, Any]) -> str:
    lines: list[str] = []
    _render_toml_table(lines, (), data)
    return "\n".join(lines).rstrip() + "\n"


def _render_toml_table(
    lines: list[str],
    table_path: tuple[str, ...],
    table: Mapping[str, Any],
) -> None:
    children: list[tuple[str, Mapping[str, Any]]] = []
    for key, value in table.items():
        if isinstance(value, Mapping):
            children.append((str(key), value))
        else:
            lines.append(f"{_toml_key(str(key))} = {_toml_value(value)}")

    for key, child in children:
        if lines:
            lines.append("")
        path = (*table_path, key)
        lines.append("[" + ".".join(_toml_key(part) for part in path) + "]")
        _render_toml_table(lines, path, child)


def _toml_key(value: str) -> str:
    return value if _TOML_BARE_KEY.fullmatch(value) else json.dumps(value, ensure_ascii=False)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "+inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Mapping):
        entries = [
            f"{_toml_key(str(key))} = {_toml_value(item)}"
            for key, item in value.items()
        ]
        return "{" + ", ".join(entries) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise ConnectionError(f"unsupported TOML value type: {type(value).__name__}")


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
