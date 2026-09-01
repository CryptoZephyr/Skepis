import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from skepis.cli import main
from skepis.config import initialize_config, register_benchmark
from skepis.integration import AGENT_INSTRUCTION, connect_project


class FakeMemory:
    def __init__(self, body):
        self.body = body
        self.events = []

    def get_entity(self, _category, _name):
        if self.body is None:
            error = type("NotFoundError", (Exception,), {})
            raise error("missing")
        return {"body": self.body}

    def set_entity(self, _category, _name, body, *, status=None):
        self.body = body
        return {"body": body, "status": status}

    def write_event(self, *, extra=None, ts=None, **_):
        event_id = f"event-{len(self.events) + 1}"
        self.events.append({"id": event_id, "extra": extra, "ts": ts})
        return event_id

    def read_events(self, *, limit=50, since=None, until=None):
        return self.events[-limit:]


def make_config(root: Path, *, task_ids: list[str], evaluator: bool = True) -> Path:
    config_path = root / "skepis.toml"
    initialize_config(
        config_path,
        project_root=root,
        tenant_id="tenant-ux",
        memory_db=".skepis/memory.db",
    )
    evaluator_path = None
    if evaluator:
        evaluator_path = root / "evaluate.py"
        evaluator_path.write_text(
            textwrap.dedent(
                """
                import json
                import os

                request = json.loads(open(os.environ["SKEPIS_EVALUATION_REQUEST"], encoding="utf-8").read())
                print(json.dumps({
                    "evaluated_tasks": request["task_ids"],
                    "metrics": {"passed": len(request["task_ids"]), "total": len(request["task_ids"])},
                    "score": 1.0,
                }))
                """
            ),
            encoding="utf-8",
        )
    register_benchmark(
        config_path,
        benchmark_id="payments-regression",
        evaluation_subject="payments-agent",
        task_ids=task_ids,
        protected_paths={"refund-idempotency": ["private/answers/refund.yaml"]}
        if "refund-idempotency" in task_ids
        else {},
        evaluator_command=(sys.executable, str(evaluator_path)) if evaluator_path else None,
    )
    return config_path


class CliJourneyTests(unittest.TestCase):
    def test_init_discovers_dynamic_task_metadata_from_a_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "metadata.json"
            fixture.write_text(
                json.dumps(
                    {
                        "benchmark": "payments-regression",
                        "evaluation_subject": "payments-agent",
                        "task_ids": ["refund-idempotency", "ledger-replay-window"],
                        "protected_paths": {
                            "refund-idempotency": ["private/refund.yaml"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with patch("skepis.cli._open_memory", return_value=object()):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "init",
                            "--root",
                            str(root),
                            "--tenant-id",
                            "tenant-ux",
                            "--fixture",
                            str(fixture),
                            "--evaluator-command",
                            f"{sys.executable} evaluate.py",
                        ]
                    )
            self.assertEqual(exit_code, 0)
            self.assertIn("Tasks: 2", stdout.getvalue())
            self.assertIn("Protected resources: 1 patterns", stdout.getvalue())

    def test_init_flags_complete_the_guided_setup_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = io.StringIO()
            with patch("skepis.cli._open_memory", return_value=object()):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "init",
                            "--root",
                            str(root),
                            "--tenant-id",
                            "tenant-ux",
                            "--benchmark-id",
                            "payments-regression",
                            "--evaluation-subject",
                            "payments-agent",
                            "--task",
                            "refund-idempotency",
                            "--task",
                            "oauth-refresh-expiry",
                            "--protected",
                            "refund-idempotency=private/answers/refund.yaml",
                            "--evaluator-command",
                            f"{sys.executable} evaluate.py",
                        ]
                    )
            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("Skepis ready.", output)
            self.assertIn("Benchmark: payments-regression", output)
            self.assertIn("Agent: payments-agent", output)
            self.assertIn("Tasks: 2", output)
            self.assertIn("Protected resources: 1 patterns", output)
            self.assertIn("Policy: EXCLUDE", output)
            self.assertIn("Memory: available", output)
            self.assertIn("Next: skepis connect", output)

    def test_eval_is_the_single_human_evaluation_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_config(
                root,
                task_ids=["refund-idempotency", "oauth-refresh-expiry"],
            )
            memory = FakeMemory(
                {
                    "tenant_id": "tenant-ux",
                    "evaluation_subject": "payments-agent",
                    "benchmark": "payments-regression",
                    "tasks": {"refund-idempotency": {"eligibility": "EXPOSED"}},
                }
            )
            stdout = io.StringIO()
            with patch("skepis.cli._open_memory", return_value=memory):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["eval", "--config", str(config_path)])
            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("Skepis Evaluation", output)
            self.assertIn("payments-agent x payments-regression", output)
            self.assertIn("2 requested", output)
            self.assertIn("1 clean", output)
            self.assertIn("1 previously exposed", output)
            self.assertIn("Evaluating 1 clean tasks", output)
            self.assertIn("Clean claim: permitted", output)
            self.assertIn("Monitoring:", output)
            self.assertNotIn("evaluation_result", output)

    def test_inspect_is_optional_and_explains_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_config(
                root,
                task_ids=["refund-idempotency", "oauth-refresh-expiry"],
            )
            memory = FakeMemory(
                {
                    "tenant_id": "tenant-ux",
                    "evaluation_subject": "payments-agent",
                    "benchmark": "payments-regression",
                    "tasks": {
                        "refund-idempotency": {"eligibility": "EXPOSED"},
                    },
                }
            )
            memory.events.append(
                {
                    "id": "event-1",
                    "ts": "2026-09-01T10:00:00Z",
                    "extra": {
                        "event_type": "benchmark_material_observed",
                        "tenant_id": "tenant-ux",
                        "evaluation_subject": "payments-agent",
                        "benchmark": "payments-regression",
                        "task": "payments-regression/refund-idempotency",
                        "reason": "controlled_protected_read",
                        "resource": "private/answers/refund.yaml",
                    },
                }
            )
            before = list(memory.events)
            stdout = io.StringIO()
            import skepis.mcp as mcp

            with patch("skepis.cli._open_memory", return_value=memory), patch(
                "skepis.mcp._open_memory", return_value=memory
            ):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["inspect", "--config", str(config_path)])
            self.assertEqual(exit_code, 0)
            output = stdout.getvalue()
            self.assertIn("Why didn't these tasks count?", output)
            self.assertIn("refund-idempotency", output)
            self.assertIn("EXPOSED", output)
            self.assertIn("Protected material was accessed", output)
            self.assertIn("oauth-refresh-expiry", output)
            self.assertIn("CLEAN", output)
            self.assertEqual(memory.events, before)

    def test_eval_surfaces_unknown_state_and_points_to_inspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_config(
                root,
                task_ids=["refund-idempotency", "oauth-refresh-expiry"],
            )
            memory = FakeMemory(
                {
                    "tenant_id": "tenant-ux",
                    "evaluation_subject": "payments-agent",
                    "benchmark": "payments-regression",
                    "monitoring_status": "INCOMPLETE_MONITORING",
                    "tasks": {"refund-idempotency": {"eligibility": "EXPOSED"}},
                }
            )
            stdout = io.StringIO()
            with patch("skepis.cli._open_memory", return_value=memory):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["eval", "--config", str(config_path)])
            self.assertEqual(exit_code, 2)
            output = stdout.getvalue()
            self.assertIn("Clean evaluation could not be established.", output)
            self.assertIn("1 unknown", output)
            self.assertIn("Monitoring history is incomplete", output)
            self.assertIn("Run `skepis inspect` for details.", output)


@unittest.skipUnless(
    importlib.util.find_spec("mcp"),
    "MCP SDK is required for the project connection verification proof",
)
class ConnectionJourneyTests(unittest.TestCase):
    def test_connect_configures_claude_project_scope_and_verifies_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_config(root, task_ids=["refund-idempotency"], evaluator=False)
            client_config = root / ".mcp.json"
            client_config.write_text(
                json.dumps({"mcpServers": {"existing": {"command": "keep-me"}}}),
                encoding="utf-8",
            )
            environment = {
                "SKEPIS_RUNTIME_PYTHON": sys.executable,
                "SKEPIS_RUNTIME_SOURCE_ROOT": str(Path(__file__).parents[1] / "src"),
            }
            with patch.dict(os.environ, environment, clear=False):
                result = connect_project(
                    root,
                    config_path,
                    requested_client="claude",
                )
                repeated = connect_project(
                    root,
                    config_path,
                    requested_client="claude",
                )

            self.assertEqual(result["status"], "CONNECTED")
            self.assertTrue(result["connection_verified"])
            self.assertEqual(
                result["configured"][0]["tools"],
                [
                    "skepis_preflight",
                    "skepis_inspect",
                    "skepis_run",
                    "skepis_report",
                    "skepis_read_protected",
                ],
            )
            self.assertEqual(repeated["status"], "CONNECTED")
            saved = json.loads(client_config.read_text(encoding="utf-8"))
            self.assertEqual(saved["mcpServers"]["existing"], {"command": "keep-me"})
            self.assertEqual(
                saved["mcpServers"]["skepis"]["args"][-2:],
                ["--config", str(config_path.resolve())],
            )
            instruction = (root / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertIn(AGENT_INSTRUCTION, instruction)
            self.assertEqual(instruction.count(AGENT_INSTRUCTION), 1)

    def test_connect_returns_manual_fallback_without_a_detected_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_config(root, task_ids=["refund-idempotency"], evaluator=False)
            with patch("skepis.integration.shutil.which", return_value=None):
                result = connect_project(root, config_path, verify=False)

        self.assertEqual(result["status"], "NO_CLIENT")
        self.assertFalse(result["connection_verified"])
        self.assertEqual(
            result["manual_configuration"]["mcpServers"]["skepis"]["args"][-2:],
            ["--config", str(config_path.resolve())],
        )

    def test_connect_configures_cursor_project_scope_and_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_config(root, task_ids=["refund-idempotency"], evaluator=False)
            environment = {
                "SKEPIS_RUNTIME_PYTHON": sys.executable,
                "SKEPIS_RUNTIME_SOURCE_ROOT": str(Path(__file__).parents[1] / "src"),
            }
            with patch.dict(os.environ, environment, clear=False):
                result = connect_project(
                    root,
                    config_path,
                    requested_client="cursor",
                )

            self.assertEqual(result["status"], "CONNECTED")
            saved = json.loads(
                (root / ".cursor" / "mcp.json").read_text(encoding="utf-8")
            )
            self.assertIn("skepis", saved["mcpServers"])
            rule = (root / ".cursor" / "rules" / "skepis.mdc").read_text(
                encoding="utf-8"
            )
            self.assertIn("alwaysApply: true", rule)
            self.assertIn(AGENT_INSTRUCTION, rule)


if __name__ == "__main__":
    unittest.main()
