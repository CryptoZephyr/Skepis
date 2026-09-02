import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import unittest
from unittest.mock import patch

from skepis.cli import main
from skepis.integration import (
    AGENT_INSTRUCTION,
    EXPECTED_MCP_TOOLS,
    ConnectionError,
    connect_project,
)


HAS_SIBYL = importlib.util.find_spec("sibyl_memory_client") is not None
SOURCE_ROOT = Path(__file__).parents[1] / "src"


def _run_main(arguments: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = main(arguments)
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _child_environment() -> dict[str, str]:
    environment = dict(os.environ)
    current = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(SOURCE_ROOT) + (
        os.pathsep + current if current else ""
    )
    return environment


def _make_project(root: Path) -> Path:
    evaluator = root / "evaluator.py"
    evaluator.write_text(
        textwrap.dedent(
            """
            import json
            import os

            request = json.loads(
                open(os.environ["SKEPIS_EVALUATION_REQUEST"], encoding="utf-8").read()
            )
            print(json.dumps({
                "evaluated_tasks": request["task_ids"],
                "metrics": {
                    "passed": len(request["task_ids"]),
                    "total": len(request["task_ids"]),
                    "private_metric": "RAW-EVALUATOR-METRIC",
                },
                "score": 1.0,
                "details": {"secret": "RAW-EVALUATOR-DETAIL"},
            }))
            """
        ),
        encoding="utf-8",
    )
    protected = root / "private-material" / "answers" / "refund.bin"
    protected.parent.mkdir(parents=True)
    protected.write_text("RAW-PROTECTED-CONTENT", encoding="utf-8")

    config_path = root / "skepis.toml"
    init_code, _, init_error = _run_main(
        [
            "init",
            "--root",
            str(root),
            "--tenant-id",
            "tenant-agent-integrations",
            "--benchmark-id",
            "payments-regression",
            "--evaluation-subject",
            "payments-agent",
            "--task",
            "refund-idempotency",
            "--task",
            "oauth-refresh-expiry",
            "--task",
            "ledger-replay-window",
            "--protected",
            "refund-idempotency=private-material/answers/refund.bin",
            "--evaluator-command",
            json.dumps([sys.executable, "evaluator.py"]),
        ]
    )
    if init_code != 0:
        raise AssertionError(init_error)
    return config_path


CLIENT_CASES = {
    "codex": {
        "label": "Codex",
        "detect_command": "codex",
        "config_parts": (".codex", "config.toml"),
        "instruction_parts": ("AGENTS.md",),
    },
    "antigravity": {
        "label": "Antigravity",
        "detect_command": "agy",
        "config_parts": (".agents", "mcp_config.json"),
        "instruction_parts": (".agents", "rules", "skepis.md"),
    },
    "gemini": {
        "label": "Gemini CLI",
        "detect_command": "gemini",
        "config_parts": (".gemini", "settings.json"),
        "instruction_parts": ("GEMINI.md",),
    },
}


def _client_path(root: Path, parts: tuple[str, ...]) -> Path:
    path = root
    for part in parts:
        path /= part
    return path


def _write_existing_client_config(root: Path, client_id: str) -> None:
    case = CLIENT_CASES[client_id]
    path = _client_path(root, case["config_parts"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if client_id == "codex":
        path.write_text(
            "approval_policy = \"never\"\n"
            "\n"
            "[mcp_servers.existing]\n"
            "command = \"keep-existing\"\n"
            "args = [\"--keep\"]\n"
            "\n"
            "[mcp_servers.skepis]\n"
            "enabled = true\n"
            "\n"
            "[mcp_servers.skepis.env]\n"
            "CUSTOM_SETTING = \"keep-me\"\n",
            encoding="utf-8",
        )
        return
    path.write_text(
        json.dumps(
            {
                "hostSetting": {"keep": True},
                "mcpServers": {
                    "existing": {"command": "keep-existing", "args": ["--keep"]},
                    "skepis": {"enabled": True, "env": {"CUSTOM_SETTING": "keep-me"}},
                },
            }
        ),
        encoding="utf-8",
    )


def _read_server_spec(root: Path, client_id: str) -> dict[str, object]:
    case = CLIENT_CASES[client_id]
    path = _client_path(root, case["config_parts"])
    if client_id == "codex":
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        return dict(raw["mcp_servers"]["skepis"])
    raw = json.loads(path.read_text(encoding="utf-8"))
    return dict(raw["mcpServers"]["skepis"])


def _event_type(event: object) -> str | None:
    if not isinstance(event, dict):
        return None
    extra = event.get("extra")
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            return None
    return extra.get("event_type") if isinstance(extra, dict) else None


def _run_mcp_read(root: Path, server_spec: dict[str, object]) -> dict[str, object]:
    client_code = r'''
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    spec = json.loads(sys.argv[1])
    project = Path(sys.argv[2])
    environment = dict(os.environ)
    environment.update({str(key): str(value) for key, value in spec.get("env", {}).items()})
    parameters = StdioServerParameters(
        command=spec["command"],
        args=[str(value) for value in spec["args"]],
        env=environment,
        cwd=project,
    )

    def body(response):
        payload = response.structuredContent
        return payload.get("result", payload) if isinstance(payload, dict) else payload

    with open(os.devnull, "w", encoding="utf-8") as errlog:
        async with stdio_client(parameters, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                before = await session.call_tool("skepis_preflight", {})
                read = await session.call_tool(
                    "skepis_read_protected",
                    {
                        "path": "private-material/answers/refund.bin",
                        "session_id": "agent-integration-session",
                    },
                )
                print(json.dumps({
                    "tools": [tool.name for tool in listed.tools],
                    "before": body(before),
                    "read_error": read.isError,
                    "read": body(read),
                }))


asyncio.run(main())
'''
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            client_code,
            json.dumps(server_spec),
            str(root),
        ],
        cwd=root,
        env=_child_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class AgentIntegrationJourneyTests(unittest.TestCase):
    @unittest.skipUnless(
        HAS_SIBYL and importlib.util.find_spec("mcp"),
        "the complete adapter journey requires the configured Sibyl and MCP runtimes",
    )
    def test_three_adapters_complete_the_real_product_journey(self):
        for client_id, case in CLIENT_CASES.items():
            with self.subTest(client=client_id), tempfile.TemporaryDirectory(
                prefix=f"skepis-{client_id}-journey-"
            ) as tmp:
                root = Path(tmp)
                config_path = _make_project(root)
                _write_existing_client_config(root, client_id)

                def fake_which(command: str) -> str | None:
                    return command if command == case["detect_command"] else None

                runtime = {
                    "SKEPIS_RUNTIME_PYTHON": sys.executable,
                    "SKEPIS_RUNTIME_SOURCE_ROOT": str(SOURCE_ROOT),
                }
                with patch.dict(os.environ, runtime, clear=False), patch(
                    "skepis.integration.shutil.which",
                    side_effect=fake_which,
                ):
                    connect_code, connect_output, connect_error = _run_main(
                        ["connect", "--root", str(root), "--json"]
                    )

                self.assertEqual(connect_code, 0, connect_error)
                connection = json.loads(connect_output)
                self.assertEqual(connection["status"], "CONNECTED")
                self.assertEqual(connection["detected"], [case["label"]])
                self.assertTrue(connection["connection_verified"])
                self.assertEqual(
                    connection["configured"][0]["tools"],
                    list(EXPECTED_MCP_TOOLS),
                )

                server_spec = _read_server_spec(root, client_id)
                self.assertEqual(server_spec["command"], sys.executable)
                self.assertEqual(
                    server_spec["args"][-2:],
                    ["--config", str(config_path.resolve())],
                )
                instruction = _client_path(root, case["instruction_parts"]).read_text(
                    encoding="utf-8"
                )
                self.assertIn(AGENT_INSTRUCTION, instruction)

                from sibyl_memory_client import MemoryClient

                memory = MemoryClient.local(str(root / ".skepis" / "memory.db"))
                self.assertEqual(
                    {
                        _event_type(event)
                        for event in memory.read_events(limit=1000)
                        if _event_type(event)
                    },
                    set(),
                )

                with patch.dict(os.environ, runtime, clear=False), patch(
                    "skepis.integration.shutil.which",
                    side_effect=fake_which,
                ):
                    repeated_code, repeated_output, repeated_error = _run_main(
                        ["connect", "--root", str(root), "--json"]
                    )
                self.assertEqual(repeated_code, 0, repeated_error)
                repeated = json.loads(repeated_output)
                self.assertEqual(repeated["status"], "CONNECTED")
                self.assertEqual(
                    _client_path(root, case["instruction_parts"])
                    .read_text(encoding="utf-8")
                    .count(AGENT_INSTRUCTION),
                    1,
                )

                if client_id == "codex":
                    raw_config = tomllib.loads(
                        _client_path(root, case["config_parts"]).read_text(encoding="utf-8")
                    )
                    self.assertEqual(raw_config["approval_policy"], "never")
                    self.assertEqual(
                        raw_config["mcp_servers"]["existing"],
                        {"command": "keep-existing", "args": ["--keep"]},
                    )
                    self.assertTrue(raw_config["mcp_servers"]["skepis"]["enabled"])
                    self.assertEqual(
                        raw_config["mcp_servers"]["skepis"]["env"]["CUSTOM_SETTING"],
                        "keep-me",
                    )
                else:
                    raw_config = json.loads(
                        _client_path(root, case["config_parts"]).read_text(encoding="utf-8")
                    )
                    self.assertEqual(raw_config["hostSetting"], {"keep": True})
                    self.assertEqual(
                        raw_config["mcpServers"]["existing"],
                        {"command": "keep-existing", "args": ["--keep"]},
                    )
                    self.assertTrue(raw_config["mcpServers"]["skepis"]["enabled"])
                    self.assertEqual(
                        raw_config["mcpServers"]["skepis"]["env"]["CUSTOM_SETTING"],
                        "keep-me",
                    )

                read_result = _run_mcp_read(root, server_spec)
                self.assertEqual(read_result["tools"], list(EXPECTED_MCP_TOOLS))
                self.assertFalse(read_result["read_error"])
                self.assertEqual(read_result["read"]["content"], "RAW-PROTECTED-CONTENT")
                self.assertEqual(
                    read_result["read"]["receipt"]["task_key"],
                    "payments-regression/refund-idempotency",
                )

                child_env = _child_environment()

                status = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "skepis",
                        "exposure",
                        "status",
                        "--config",
                        str(config_path),
                        "--json",
                    ],
                    cwd=root,
                    env=child_env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(status.returncode, 0, status.stderr)
                status_body = json.loads(status.stdout)
                self.assertEqual(status_body["exposed_tasks"], ["refund-idempotency"])
                self.assertEqual(
                    status_body["clean_tasks"],
                    ["ledger-replay-window", "oauth-refresh-expiry"],
                )

                evaluation = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "skepis",
                        "eval",
                        "--config",
                        str(config_path),
                        "--policy",
                        "exclude",
                        "--json",
                    ],
                    cwd=root,
                    env=child_env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(evaluation.returncode, 0, evaluation.stderr)
                evaluation_body = json.loads(evaluation.stdout)
                self.assertEqual(
                    evaluation_body["selected_tasks"],
                    ["ledger-replay-window", "oauth-refresh-expiry"],
                )
                self.assertEqual(evaluation_body["excluded_tasks"], ["refund-idempotency"])
                self.assertTrue(evaluation_body["clean_claim_permitted"])

                inspect = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "skepis",
                        "inspect",
                        "--config",
                        str(config_path),
                        "--json",
                    ],
                    cwd=root,
                    env=child_env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(inspect.returncode, 0, inspect.stderr)
                inspect_body = json.loads(inspect.stdout)
                self.assertEqual(
                    inspect_body["eligibility"]["exposed_tasks"],
                    ["refund-idempotency"],
                )
                self.assertNotIn("RAW-PROTECTED-CONTENT", inspect.stdout)

                report = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "skepis",
                        "report",
                        "--config",
                        str(config_path),
                        "--json",
                    ],
                    cwd=root,
                    env=child_env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(report.returncode, 0, report.stderr)
                report_body = json.loads(report.stdout)
                self.assertEqual(report_body["evaluation"]["evaluated_count"], 2)
                self.assertTrue(report_body["clean_claim"]["permitted"])
                self.assertNotIn("RAW-PROTECTED-CONTENT", report.stdout)
                self.assertNotIn("RAW-EVALUATOR-DETAIL", report.stdout)

    def test_missing_project_configs_are_created_for_each_adapter(self):
        for client_id in CLIENT_CASES:
            with self.subTest(client=client_id), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                config_path = root / "skepis.toml"
                case = CLIENT_CASES[client_id]
                with patch.dict(
                    os.environ,
                    {
                        "SKEPIS_RUNTIME_PYTHON": sys.executable,
                        "SKEPIS_RUNTIME_SOURCE_ROOT": str(SOURCE_ROOT),
                    },
                    clear=False,
                ):
                    result = connect_project(
                        root,
                        config_path,
                        requested_client=client_id,
                        verify=False,
                    )
                self.assertEqual(result["status"], "FAILED")
                self.assertTrue(_client_path(root, case["config_parts"]).is_file())
                self.assertTrue(_client_path(root, case["instruction_parts"]).is_file())

    def test_malformed_project_configs_fail_without_overwrite(self):
        malformed = {
            "codex": (".codex", "config.toml"),
            "antigravity": (".agents", "mcp_config.json"),
            "gemini": (".gemini", "settings.json"),
        }
        for client_id, parts in malformed.items():
            with self.subTest(client=client_id), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                config_path = root / "skepis.toml"
                path = _client_path(root, parts)
                path.parent.mkdir(parents=True)
                original = "mcp_servers = [\n" if client_id == "codex" else "{invalid"
                path.write_text(original, encoding="utf-8")
                result = connect_project(
                    root,
                    config_path,
                    requested_client=client_id,
                    verify=False,
                )
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_connection_recovers_after_server_start_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "skepis.toml"
            invalid_runtime = root / "missing-python"
            with patch.dict(
                os.environ,
                {
                    "SKEPIS_RUNTIME_PYTHON": str(invalid_runtime),
                    "SKEPIS_RUNTIME_SOURCE_ROOT": str(SOURCE_ROOT),
                },
                clear=False,
            ):
                failed = connect_project(root, config_path, requested_client="codex")
            self.assertEqual(failed["status"], "FAILED")
            self.assertFalse(failed["connection_verified"])

            with patch.dict(
                os.environ,
                {
                    "SKEPIS_RUNTIME_PYTHON": sys.executable,
                    "SKEPIS_RUNTIME_SOURCE_ROOT": str(SOURCE_ROOT),
                },
                clear=False,
            ):
                recovered = connect_project(root, config_path, requested_client="codex")
            self.assertEqual(recovered["status"], "CONNECTED")
            self.assertTrue(recovered["connection_verified"])
            self.assertEqual(recovered["configured"][0]["tools"], list(EXPECTED_MCP_TOOLS))

    def test_auto_detection_without_supported_host_keeps_manual_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "skepis.toml"
            with patch("skepis.integration.shutil.which", return_value=None):
                result = connect_project(root, config_path, verify=False)
        self.assertEqual(result["status"], "NO_CLIENT")
        self.assertFalse(result["connection_verified"])
        self.assertIn("mcpServers", result["manual_configuration"])

    def test_unsupported_client_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConnectionError, "unsupported MCP client"):
                connect_project(Path(tmp), Path(tmp) / "skepis.toml", requested_client="unknown")


if __name__ == "__main__":
    unittest.main()
