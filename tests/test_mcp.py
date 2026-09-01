import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from skepis.config import initialize_config, register_benchmark
from skepis.capture import ProtectedReadError
from skepis.mcp import inspect, preflight, read_protected, report, run


TASK_IDS = [
    "refund-idempotency",
    "oauth-refresh-expiry",
    "inventory-race-condition",
    "ledger-replay-window",
    "merchant-timezone-cutoff",
]


class FakeMemory:
    def __init__(self, body=None, *, read_error=None):
        self.body = body
        self.events = []
        self.read_error = read_error

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
        if self.read_error is not None:
            raise self.read_error
        return self.events[-limit:]


def write_config(
    root: Path,
    *,
    name: str = "skepis.toml",
    tenant_id: str = "tenant-a",
    benchmark_id: str = "payments-regression",
    evaluation_subject: str = "payments-agent",
    task_ids: list[str] | None = None,
    protected_paths: dict[str, list[str]] | None = None,
    evaluator_command: tuple[str, ...] | None = None,
) -> Path:
    config_path = root / name
    task_ids = list(TASK_IDS if task_ids is None else task_ids)
    protected_paths = (
        {
            "refund-idempotency": ["answers/refund/idempotency.yaml"],
            "oauth-refresh-expiry": ["answers/oauth/refresh-expiry.json"],
        }
        if protected_paths is None
        else protected_paths
    )
    initialize_config(
        config_path,
        project_root=root,
        tenant_id=tenant_id,
        memory_db=".skepis/memory.db",
    )
    register_benchmark(
        config_path,
        benchmark_id=benchmark_id,
        evaluation_subject=evaluation_subject,
        task_ids=task_ids,
        protected_paths=protected_paths,
        evaluator_command=evaluator_command,
    )
    return config_path


def scoped_body(*, tenant_id: str = "tenant-a") -> dict:
    return {
        "tenant_id": tenant_id,
        "evaluation_subject": "payments-agent",
        "benchmark": "payments-regression",
        "tasks": {
            "oauth-refresh-expiry": {"eligibility": "EXPOSED"},
        },
    }


class McpPreflightTests(unittest.TestCase):
    def test_preflight_wraps_read_only_classifier_for_arbitrary_config(self):
        task_ids = list(reversed(TASK_IDS))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            memory = FakeMemory(scoped_body())

            result = preflight(config_path, task_ids, memory=memory)

        self.assertEqual(result["benchmark"], "payments-regression")
        self.assertEqual(result["evaluation_subject"], "payments-agent")
        self.assertEqual(result["requested_tasks"], sorted(task_ids))
        self.assertEqual(result["clean_tasks"], [
            "inventory-race-condition",
            "ledger-replay-window",
            "merchant-timezone-cutoff",
            "refund-idempotency",
        ])
        self.assertEqual(result["exposed_tasks"], ["oauth-refresh-expiry"])
        self.assertEqual(result["unknown_tasks"], [])
        self.assertEqual(result["policy"], "exclude")
        self.assertFalse(result["policy_applied"])
        self.assertTrue(result["read_only"])
        self.assertEqual(memory.events, [])
        self.assertEqual(
            result["monitoring_coverage"]["generic_agent_access"],
            "INCOMPLETE_MONITORING",
        )

    def test_inspect_projects_scoped_provenance_without_raw_event_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            memory = FakeMemory(scoped_body())
            events = [
                {
                    "id": "event-safe-1",
                    "ts": "2026-09-01T10:00:00Z",
                    "extra": {
                        "event_type": "benchmark_material_observed",
                        "tenant_id": "tenant-a",
                        "evaluation_subject": "payments-agent",
                        "benchmark": "payments-regression",
                        "task": "payments-regression/oauth-refresh-expiry",
                        "resource": "answers/oauth/refresh-expiry.json",
                        "session_id": "session-a",
                        "source_adapter": "protected_read",
                        "reason": "controlled_protected_read",
                        "duplicate": False,
                        "observation_id": "observation-safe-1",
                        "evidence": {
                            "operation": "read",
                            "status": "success",
                            "bytes_read": 42,
                            "content_sha256": "A" * 64,
                            "content": "RAW-PROTECTED-CONTENT",
                            "hidden_answer": "RAW-HIDDEN-ANSWER",
                        },
                        "answer": "RAW-EXTRA-ANSWER",
                    },
                },
                {
                    "id": "event-other-tenant",
                    "ts": "2026-09-01T10:01:00Z",
                    "extra": {
                        "event_type": "benchmark_material_observed",
                        "tenant_id": "tenant-b",
                        "evaluation_subject": "payments-agent",
                        "benchmark": "payments-regression",
                        "task": "payments-regression/oauth-refresh-expiry",
                        "resource": "answers/other-tenant.json",
                        "evidence": {"content": "RAW-OTHER-TENANT"},
                    },
                },
                {
                    "id": "event-other-task",
                    "ts": "2026-09-01T10:02:00Z",
                    "extra": {
                        "event_type": "benchmark_material_observed",
                        "tenant_id": "tenant-a",
                        "evaluation_subject": "payments-agent",
                        "benchmark": "payments-regression",
                        "task": "payments-regression/unrequested-task",
                        "resource": "answers/unrequested.json",
                        "evidence": {"content": "RAW-UNREQUESTED"},
                    },
                },
            ]
            memory.events.extend(events)

            result = inspect(config_path, list(reversed(TASK_IDS)), memory=memory)

        self.assertEqual(result["status"], "INSPECTED")
        self.assertEqual(
            result["eligibility"]["exposed_tasks"],
            ["oauth-refresh-expiry"],
        )
        self.assertEqual(result["eligibility"]["unknown_tasks"], [])
        self.assertEqual(result["provenance"]["status"], "AVAILABLE")
        self.assertEqual(len(result["provenance"]["events"]), 1)
        event = result["provenance"]["events"][0]
        self.assertEqual(event["task"], "payments-regression/oauth-refresh-expiry")
        self.assertEqual(event["read_evidence"], {
            "operation": "read",
            "status": "success",
            "bytes_read": 42,
            "content_sha256": "a" * 64,
        })
        encoded = json.dumps(result, sort_keys=True)
        for secret in (
            "RAW-PROTECTED-CONTENT",
            "RAW-HIDDEN-ANSWER",
            "RAW-EXTRA-ANSWER",
            "RAW-OTHER-TENANT",
            "RAW-UNREQUESTED",
        ):
            self.assertNotIn(secret, encoded)
        self.assertEqual(memory.events, events)

    def test_inspect_preserves_incomplete_monitoring_as_unknown_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            body = scoped_body()
            body["monitoring_status"] = "INCOMPLETE_MONITORING"
            memory = FakeMemory(body)
            memory.events.append(
                {
                    "id": "gap-1",
                    "ts": "2026-09-01T10:00:00Z",
                    "extra": {
                        "event_type": "observation_gap_detected",
                        "monitoring_status": "INCOMPLETE_MONITORING",
                        "tenant_id": "tenant-a",
                        "evaluation_subject": "payments-agent",
                        "benchmark": "payments-regression",
                        "resource": "answers/*.json",
                        "matches": ["payments-regression/oauth-refresh-expiry"],
                        "session_id": "session-gap",
                        "source_adapter": "protected_read",
                        "reason": "ambiguous_task_mapping",
                    },
                }
            )

            result = inspect(
                config_path,
                ["oauth-refresh-expiry", "refund-idempotency"],
                memory=memory,
            )

        self.assertEqual(
            result["eligibility"]["unknown_tasks"],
            ["refund-idempotency"],
        )
        self.assertEqual(result["eligibility"]["clean_tasks"], [])
        self.assertEqual(
            result["eligibility"]["exposed_tasks"],
            ["oauth-refresh-expiry"],
        )
        self.assertEqual(result["eligibility"]["reason"], "incomplete_monitoring")
        self.assertEqual(
            result["monitoring_coverage"]["status"],
            "INCOMPLETE_MONITORING",
        )
        self.assertEqual(result["provenance"]["status"], "INCOMPLETE_MONITORING")
        self.assertEqual(len(result["provenance"]["observation_gaps"]), 1)
        self.assertEqual(memory.events[0]["extra"]["event_type"], "observation_gap_detected")

    def test_inspect_preserves_unknown_when_monitoring_history_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            memory = FakeMemory(
                scoped_body(),
                read_error=RuntimeError("private failure details"),
            )

            result = inspect(
                config_path,
                ["refund-idempotency"],
                memory=memory,
            )

        self.assertEqual(result["eligibility"]["unknown_tasks"], ["refund-idempotency"])
        self.assertEqual(result["eligibility"]["clean_tasks"], [])
        self.assertEqual(result["eligibility"]["reason"], "monitoring_read_failed:RuntimeError")
        self.assertEqual(result["provenance"]["status"], "INCOMPLETE_MONITORING")
        self.assertEqual(
            result["provenance"]["reason"],
            "monitoring_read_failed:RuntimeError",
        )
        self.assertNotIn("private failure details", json.dumps(result))
        self.assertEqual(memory.events, [])

    def test_preflight_isolates_scope_and_fails_closed_without_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            tasks = ["oauth-refresh-expiry", "refund-idempotency"]

            isolated = preflight(
                config_path,
                tasks,
                memory=FakeMemory(scoped_body(tenant_id="tenant-b")),
            )
            missing = preflight(
                config_path,
                tasks,
                memory=FakeMemory(),
            )

        self.assertEqual(isolated["unknown_tasks"], sorted(tasks))
        self.assertEqual(isolated["exposed_tasks"], [])
        self.assertFalse(isolated["state_available"])
        self.assertEqual(isolated["reason"], "scope_mismatch:tenant_id")
        self.assertEqual(missing["unknown_tasks"], sorted(tasks))
        self.assertFalse(missing["state_available"])
        self.assertEqual(missing["reason"], "warm_state_not_found")
        self.assertEqual(missing["monitoring_coverage"]["sibyl_state"], "UNAVAILABLE")

    @unittest.skipUnless(
        importlib.util.find_spec("mcp") and importlib.util.find_spec("sibyl_memory_client"),
        "MCP protocol proof requires the MCP SDK and configured Sibyl runtime",
    )
    def test_stdio_protocol_exposes_two_read_only_tools_and_preserves_scope(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from sibyl_memory_client import MemoryClient

        async def exercise(project: Path, config_path: Path, other_config: Path):
            source_root = Path(__file__).parents[1] / "src"
            child_env = dict(os.environ)
            child_env["PYTHONPATH"] = str(source_root)
            params = StdioServerParameters(
                command=os.fspath(Path(sys.executable)),
                args=["-m", "skepis.mcp"],
                env=child_env,
                cwd=project,
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    exposed = await session.call_tool(
                        "skepis_preflight",
                        {
                            "config_path": os.fspath(config_path),
                            "task_ids": [
                                "inventory-race-condition",
                                "oauth-refresh-expiry",
                                "ledger-replay-window",
                                "merchant-timezone-cutoff",
                                "refund-idempotency",
                            ],
                        },
                    )
                    inspected = await session.call_tool(
                        "skepis_inspect",
                        {
                            "config_path": os.fspath(config_path),
                            "task_ids": [
                                "oauth-refresh-expiry",
                                "refund-idempotency",
                            ],
                        },
                    )
                    isolated = await session.call_tool(
                        "skepis_preflight",
                        {
                            "config_path": os.fspath(other_config),
                            "task_ids": ["oauth-refresh-expiry", "refund-idempotency"],
                        },
                    )
                    return listed, exposed, inspected, isolated

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            other_config = write_config(root, name="other.toml", tenant_id="tenant-b")
            db = root / ".skepis" / "memory.db"
            memory = MemoryClient.local(str(db))
            memory.set_entity(
                "benchmark_exposure",
                "tenant-a/payments-agent/payments-regression",
                scoped_body(),
                status="EXPOSED",
            )

            listed, exposed, inspected, isolated = asyncio.run(
                exercise(root, config_path, other_config)
            )
            self.assertEqual(memory.read_events(limit=1000), [])

        self.assertEqual(
            [tool.name for tool in listed.tools],
            [
                "skepis_preflight",
                "skepis_inspect",
                "skepis_run",
                "skepis_report",
                "skepis_read_protected",
            ],
        )
        annotations = {tool.name: tool.annotations for tool in listed.tools}
        for name in ("skepis_preflight", "skepis_inspect", "skepis_report"):
            self.assertTrue(annotations[name].readOnlyHint)
            self.assertFalse(annotations[name].destructiveHint)
            self.assertTrue(annotations[name].idempotentHint)
        for name in ("skepis_run", "skepis_read_protected"):
            self.assertFalse(annotations[name].readOnlyHint)
            self.assertFalse(annotations[name].destructiveHint)
            self.assertFalse(annotations[name].idempotentHint)
        self.assertEqual(exposed.isError, False)
        self.assertEqual(inspected.isError, False)
        self.assertEqual(isolated.isError, False)

        exposed_payload = exposed.structuredContent
        inspected_payload = inspected.structuredContent
        isolated_payload = isolated.structuredContent
        self.assertIsInstance(exposed_payload, dict)
        self.assertIsInstance(inspected_payload, dict)
        self.assertIsInstance(isolated_payload, dict)
        exposed_result = exposed_payload.get("result", exposed_payload)
        inspected_result = inspected_payload.get("result", inspected_payload)
        isolated_result = isolated_payload.get("result", isolated_payload)
        self.assertEqual(exposed_result["exposed_tasks"], ["oauth-refresh-expiry"])
        self.assertEqual(
            exposed_result["clean_tasks"],
            [
                "inventory-race-condition",
                "ledger-replay-window",
                "merchant-timezone-cutoff",
                "refund-idempotency",
            ],
        )
        self.assertEqual(inspected_result["status"], "INSPECTED")
        self.assertEqual(
            inspected_result["eligibility"]["exposed_tasks"],
            ["oauth-refresh-expiry"],
        )
        self.assertEqual(
            inspected_result["eligibility"]["clean_tasks"],
            ["refund-idempotency"],
        )
        self.assertEqual(inspected_result["provenance"]["status"], "AVAILABLE")
        self.assertFalse(inspected_result["policy"]["applied"])
        self.assertTrue(inspected_result["read_only"])
        self.assertEqual(isolated_result["unknown_tasks"], [
            "oauth-refresh-expiry",
            "refund-idempotency",
        ])
        self.assertEqual(isolated_result["exposed_tasks"], [])
        self.assertFalse(isolated_result["state_available"])

    @unittest.skipUnless(
        importlib.util.find_spec("mcp") and importlib.util.find_spec("sibyl_memory_client"),
        "MCP protocol proof requires the MCP SDK and configured Sibyl runtime",
    )
    def test_stdio_protocol_missing_store_returns_unknown(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def exercise(project: Path, config_path: Path):
            source_root = Path(__file__).parents[1] / "src"
            child_env = dict(os.environ)
            child_env["PYTHONPATH"] = str(source_root)
            params = StdioServerParameters(
                command=os.fspath(Path(sys.executable)),
                args=["-m", "skepis.mcp"],
                env=child_env,
                cwd=project,
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    preflight_result = await session.call_tool(
                        "skepis_preflight",
                        {
                            "config_path": os.fspath(config_path),
                            "task_ids": ["oauth-refresh-expiry", "refund-idempotency"],
                        },
                    )
                    inspect_result = await session.call_tool(
                        "skepis_inspect",
                        {
                            "config_path": os.fspath(config_path),
                            "task_ids": ["oauth-refresh-expiry", "refund-idempotency"],
                        },
                    )
                    return preflight_result, inspect_result

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            result, inspected = asyncio.run(exercise(root, config_path))

        self.assertFalse(result.isError)
        payload = result.structuredContent
        self.assertIsInstance(payload, dict)
        body = payload.get("result", payload)
        self.assertEqual(body["unknown_tasks"], [
            "oauth-refresh-expiry",
            "refund-idempotency",
        ])
        self.assertFalse(body["state_available"])
        self.assertEqual(body["reason"], "warm_state_not_found")
        self.assertEqual(body["monitoring_coverage"]["status"], "UNAVAILABLE")
        self.assertFalse(inspected.isError)
        inspected_payload = inspected.structuredContent
        self.assertIsInstance(inspected_payload, dict)
        inspected_body = inspected_payload.get("result", inspected_payload)
        self.assertEqual(inspected_body["status"], "INSPECTED")
        self.assertEqual(
            inspected_body["eligibility"]["unknown_tasks"],
            ["oauth-refresh-expiry", "refund-idempotency"],
        )
        self.assertEqual(inspected_body["provenance"]["status"], "UNAVAILABLE")

    @unittest.skipUnless(
        importlib.util.find_spec("mcp") and importlib.util.find_spec("sibyl_memory_client"),
        "MCP protocol proof requires the MCP SDK and configured Sibyl runtime",
    )
    def test_stdio_inspect_redacts_provenance_and_preserves_incomplete_monitoring(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from sibyl_memory_client import MemoryClient

        async def exercise(project: Path, config_path: Path):
            source_root = Path(__file__).parents[1] / "src"
            child_env = dict(os.environ)
            child_env["PYTHONPATH"] = str(source_root)
            params = StdioServerParameters(
                command=os.fspath(Path(sys.executable)),
                args=["-m", "skepis.mcp"],
                env=child_env,
                cwd=project,
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    result = await session.call_tool(
                        "skepis_inspect",
                        {
                            "config_path": os.fspath(config_path),
                            "task_ids": list(TASK_IDS),
                        },
                    )
                    return listed, result

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            db = root / ".skepis" / "memory.db"
            memory = MemoryClient.local(str(db))
            incomplete_body = scoped_body()
            incomplete_body["monitoring_status"] = "INCOMPLETE_MONITORING"
            memory.set_entity(
                "benchmark_exposure",
                "tenant-a/payments-agent/payments-regression",
                incomplete_body,
                status="INCOMPLETE_MONITORING",
            )
            memory.write_event(
                extra={
                    "event_type": "benchmark_material_observed",
                    "tenant_id": "tenant-a",
                    "evaluation_subject": "payments-agent",
                    "benchmark": "payments-regression",
                    "task": "payments-regression/oauth-refresh-expiry",
                    "resource": "answers/oauth/refresh-expiry.json",
                    "session_id": "session-a",
                    "source_adapter": "protected_read",
                    "reason": "controlled_protected_read",
                    "evidence": {
                        "operation": "read",
                        "status": "success",
                        "bytes_read": 99,
                        "content_sha256": "B" * 64,
                        "content": "RAW-MCP-PROTECTED-CONTENT",
                        "hidden_answer": "RAW-MCP-HIDDEN-ANSWER",
                    },
                },
                ts="2026-09-01T10:00:00Z",
            )
            memory.write_event(
                extra={
                    "event_type": "observation_gap_detected",
                    "monitoring_status": "INCOMPLETE_MONITORING",
                    "tenant_id": "tenant-a",
                    "evaluation_subject": "payments-agent",
                    "benchmark": "payments-regression",
                    "resource": "answers/*.json",
                    "matches": ["payments-regression/oauth-refresh-expiry"],
                    "session_id": "session-gap",
                    "source_adapter": "protected_read",
                    "reason": "ambiguous_task_mapping",
                    "hidden_answer": "RAW-MCP-GAP-ANSWER",
                },
                ts="2026-09-01T10:01:00Z",
            )
            before = memory.read_events(limit=1000)
            listed, result = asyncio.run(exercise(root, config_path))
            after = memory.read_events(limit=1000)

        self.assertEqual(
            [tool.name for tool in listed.tools],
            [
                "skepis_preflight",
                "skepis_inspect",
                "skepis_run",
                "skepis_report",
                "skepis_read_protected",
            ],
        )
        self.assertFalse(result.isError)
        payload = result.structuredContent
        self.assertIsInstance(payload, dict)
        body = payload.get("result", payload)
        self.assertEqual(body["status"], "INSPECTED")
        self.assertEqual(body["eligibility"]["clean_tasks"], [])
        self.assertEqual(
            body["eligibility"]["exposed_tasks"],
            ["oauth-refresh-expiry"],
        )
        self.assertEqual(
            body["eligibility"]["unknown_tasks"],
            sorted(set(TASK_IDS) - {"oauth-refresh-expiry"}),
        )
        self.assertEqual(
            body["monitoring_coverage"]["status"],
            "INCOMPLETE_MONITORING",
        )
        self.assertEqual(body["provenance"]["status"], "INCOMPLETE_MONITORING")
        self.assertEqual(len(body["provenance"]["events"]), 1)
        self.assertEqual(len(body["provenance"]["observation_gaps"]), 1)
        self.assertEqual(
            body["provenance"]["events"][0]["read_evidence"],
            {
                "operation": "read",
                "status": "success",
                "bytes_read": 99,
                "content_sha256": "b" * 64,
            },
        )
        encoded = json.dumps(body, sort_keys=True)
        for secret in (
            "RAW-MCP-PROTECTED-CONTENT",
            "RAW-MCP-HIDDEN-ANSWER",
            "RAW-MCP-GAP-ANSWER",
        ):
            self.assertNotIn(secret, encoded)
        self.assertEqual(before, after)


class McpWorkflowTests(unittest.TestCase):
    def test_run_reuses_gate_and_returns_a_safe_report_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            memory = FakeMemory(scoped_body())
            received = []

            def evaluator(request):
                received.append(request.task_ids)
                return {
                    "evaluated_tasks": list(request.task_ids),
                    "metrics": {
                        "received_count": len(request.task_ids),
                        "hidden_answer": "must not cross MCP",
                    },
                    "score": 0.75,
                    "details": {"secret": "must not cross MCP"},
                }

            result = run(
                config_path,
                policy="exclude",
                memory=memory,
                evaluator=evaluator,
                run_id="mcp-run-safe-1",
            )
            loaded = report(
                config_path,
                "mcp-run-safe-1",
                memory=memory,
            )

        expected_selected = [
            "inventory-race-condition",
            "ledger-replay-window",
            "merchant-timezone-cutoff",
            "refund-idempotency",
        ]
        self.assertEqual(received, [tuple(expected_selected)])
        self.assertEqual(result["status"], "EXCLUDED")
        self.assertEqual(result["selected_tasks"], expected_selected)
        self.assertEqual(result["excluded_tasks"], ["oauth-refresh-expiry"])
        self.assertEqual(result["evaluated_tasks"], expected_selected)
        self.assertEqual(result["score"], 0.75)
        self.assertTrue(result["clean_claim_permitted"])
        self.assertFalse(result["read_only"])
        self.assertNotIn("evaluation_result", result)
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("must not cross MCP", encoded)
        self.assertEqual(loaded, result["report"])
        self.assertEqual(loaded["evaluation"]["evaluated_count"], 4)
        self.assertTrue(loaded["clean_claim"]["permitted"])

    def test_run_preserves_exclude_flag_and_strict_fail_closed_results(self):
        task_ids = ["clean-refund", "exposed-refund", "uncertain-refund"]
        body = {
            "tenant_id": "tenant-a",
            "evaluation_subject": "payments-agent",
            "benchmark": "payments-regression",
            "tasks": {
                "clean-refund": {"eligibility": "UNSEEN"},
                "exposed-refund": {"eligibility": "EXPOSED"},
                "uncertain-refund": {"eligibility": "REVIEW_REQUIRED"},
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_config(Path(tmp), task_ids=task_ids, protected_paths={})
            for policy, expected_status, expected_selected, expected_flagged, expected_exit in (
                ("exclude", "BLOCKED", ["clean-refund"], [], 2),
                ("flag", "FLAGGED", task_ids, ["exposed-refund", "uncertain-refund"], 0),
                ("strict", "BLOCKED", [], [], 2),
            ):
                with self.subTest(policy=policy):
                    memory = FakeMemory(body)
                    result = run(
                        config_path,
                        task_ids,
                        policy,
                        memory=memory,
                        evaluator=lambda request: {
                            "evaluated_tasks": list(request.task_ids),
                            "metrics": {"received_count": len(request.task_ids)},
                        },
                    )

                    self.assertEqual(result["status"], expected_status)
                    self.assertEqual(result["selected_tasks"], sorted(expected_selected))
                    self.assertEqual(result["flagged_tasks"], sorted(expected_flagged))
                    self.assertEqual(result["exit_code"], expected_exit)
                    self.assertFalse(result["clean_claim_permitted"])
                    self.assertFalse(result["report"]["clean_claim"]["permitted"])
                    if policy == "strict":
                        self.assertEqual(result["evaluated_tasks"], [])
                        self.assertFalse(result["evaluation_complete"])

    def test_run_surfaces_evaluator_failure_without_raw_error_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_config(Path(tmp))

            def evaluator(_request):
                raise RuntimeError("private evaluator output")

            result = run(
                config_path,
                ["refund-idempotency"],
                "strict",
                memory=FakeMemory(
                    {
                        **scoped_body(),
                        "tasks": {
                            "refund-idempotency": {"eligibility": "UNSEEN"},
                        },
                    }
                ),
                evaluator=evaluator,
            )

        self.assertEqual(result["status"], "EVALUATOR_FAILED")
        self.assertEqual(result["exit_code"], 1)
        self.assertFalse(result["clean_claim_permitted"])
        self.assertFalse(result["evaluation_complete"])
        self.assertNotIn("evaluation_error", result)
        self.assertNotIn("private evaluator output", json.dumps(result))

    def test_run_rejects_unauthorized_evaluator_tasks_without_bypassing_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_config(Path(tmp))
            result = run(
                config_path,
                ["refund-idempotency"],
                "strict",
                memory=FakeMemory(
                    {
                        **scoped_body(),
                        "tasks": {
                            "refund-idempotency": {"eligibility": "UNSEEN"},
                        },
                    }
                ),
                evaluator=lambda _request: {
                    "evaluated_tasks": ["outside-policy"],
                },
            )

        self.assertEqual(result["status"], "EVALUATOR_FAILED")
        self.assertEqual(result["selected_tasks"], ["refund-idempotency"])
        self.assertEqual(result["evaluated_tasks"], [])
        self.assertFalse(result["clean_claim_permitted"])
        self.assertNotIn("evaluation_result", result)

    def test_run_requires_a_configured_evaluator_when_no_test_seam_is_supplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_config(Path(tmp))
            with self.assertRaisesRegex(ValueError, "missing evaluator command"):
                run(config_path, memory=FakeMemory(scoped_body()))

    def test_read_protected_uses_the_existing_boundary_and_returns_a_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            protected = root / "answers/oauth/refresh-expiry.json"
            protected.parent.mkdir(parents=True)
            protected.write_text("opaque protected material", encoding="utf-8")
            memory = FakeMemory()

            result = read_protected(
                config_path,
                str(protected),
                "mcp-session-a",
                "2026-09-01T10:00:00Z",
                memory=memory,
            )

        self.assertEqual(result["content"], "opaque protected material")
        self.assertEqual(result["receipt"]["task_key"], "payments-regression/oauth-refresh-expiry")
        self.assertEqual(result["receipt"]["capture_outcome"], "RECORDED")
        self.assertEqual(result["receipt"]["status"], "success")
        self.assertEqual(result["monitoring_coverage"]["protected_reads"], "COMPLETE")
        self.assertEqual(result["monitoring_coverage"]["generic_agent_access"], "INCOMPLETE_MONITORING")
        self.assertFalse(result["read_only"])
        self.assertEqual(memory.body["tasks"]["oauth-refresh-expiry"]["eligibility"], "EXPOSED")
        self.assertEqual(memory.events[0]["extra"]["event_type"], "benchmark_material_observed")

    def test_read_protected_rejects_unregistered_and_failed_reads_without_hard_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            public = root / "public.txt"
            public.write_text("public", encoding="utf-8")
            memory = FakeMemory()

            with self.assertRaisesRegex(ProtectedReadError, "not registered as protected"):
                read_protected(
                    config_path,
                    public,
                    "mcp-session-public",
                    memory=memory,
                )
            self.assertIsNone(memory.body)
            self.assertEqual(memory.events, [])

            with self.assertRaisesRegex(ProtectedReadError, "protected read failed"):
                read_protected(
                    config_path,
                    "answers/oauth/refresh-expiry.json",
                    "mcp-session-missing",
                    "2026-09-01T10:01:00Z",
                    memory=memory,
                )

        self.assertIsNotNone(memory.body)
        self.assertEqual(memory.body["tasks"], {})
        self.assertEqual(memory.body["monitoring_status"], "INCOMPLETE_MONITORING")
        self.assertEqual(memory.events[0]["extra"]["event_type"], "observation_gap_detected")

    @unittest.skipUnless(
        importlib.util.find_spec("mcp") and importlib.util.find_spec("sibyl_memory_client"),
        "MCP workflow proof requires the MCP SDK and configured Sibyl runtime",
    )
    def test_stdio_client_proves_fresh_process_read_run_report_and_policy_modes(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from sibyl_memory_client import MemoryClient

        task_ids = [
            "refund-idempotency",
            "oauth-refresh-expiry",
            "inventory-race-condition",
            "ledger-replay-window",
        ]
        async def open_session(project: Path):
            source_root = Path(__file__).parents[1] / "src"
            child_env = dict(os.environ)
            child_env["PYTHONPATH"] = str(source_root)
            params = StdioServerParameters(
                command=os.fspath(Path(sys.executable)),
                args=["-m", "skepis.mcp"],
                env=child_env,
                cwd=project,
            )
            return stdio_client(params)

        async def first_process(project: Path, config_path: Path):
            async with await open_session(project) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    missing_state = await session.call_tool(
                        "skepis_run",
                        {
                            "config_path": os.fspath(config_path),
                            "policy": "strict",
                        },
                    )
                    missing_body = missing_state.structuredContent
                    missing_body = missing_body.get("result", missing_body)
                    missing_report = await session.call_tool(
                        "skepis_report",
                        {
                            "config_path": os.fspath(config_path),
                            "run_id": missing_body["run_id"],
                        },
                    )
                    read = await session.call_tool(
                        "skepis_read_protected",
                        {
                            "config_path": os.fspath(config_path),
                            "path": "private_material/oauth/refresh.json",
                            "session_id": "mcp-session-a",
                            "observed_at": "2026-09-01T10:00:00Z",
                        },
                    )
                    return listed, missing_state, missing_report, read

        async def second_process(project: Path, config_path: Path):
            async with await open_session(project) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    preflight_result = await session.call_tool(
                        "skepis_preflight",
                        {
                            "config_path": os.fspath(config_path),
                            "task_ids": list(reversed(task_ids)),
                        },
                    )
                    inspected = await session.call_tool(
                        "skepis_inspect",
                        {
                            "config_path": os.fspath(config_path),
                            "task_ids": task_ids,
                        },
                    )
                    inspection_readback = MemoryClient.local(
                        str(project / ".skepis/memory.db")
                    ).read_events(limit=1000)
                    excluded = await session.call_tool(
                        "skepis_run",
                        {
                            "config_path": os.fspath(config_path),
                            "policy": "exclude",
                        },
                    )
                    excluded_body = excluded.structuredContent
                    excluded_body = excluded_body.get("result", excluded_body)
                    retrieved = await session.call_tool(
                        "skepis_report",
                        {
                            "config_path": os.fspath(config_path),
                            "run_id": excluded_body["run_id"],
                        },
                    )
                    flagged = await session.call_tool(
                        "skepis_run",
                        {
                            "config_path": os.fspath(config_path),
                            "policy": "flag",
                        },
                    )
                    strict = await session.call_tool(
                        "skepis_run",
                        {
                            "config_path": os.fspath(config_path),
                            "policy": "strict",
                        },
                    )
                    return (
                        preflight_result,
                        inspected,
                        excluded,
                        retrieved,
                        flagged,
                        strict,
                        inspection_readback,
                    )

        with tempfile.TemporaryDirectory(prefix="skepis-mcp-workflow-") as tmp:
            root = Path(tmp)
            evaluator = root / "evaluator.py"
            evaluator.write_text(
                """
import json
import os

request = json.loads(open(os.environ["SKEPIS_EVALUATION_REQUEST"], encoding="utf-8").read())
print(json.dumps({
    "evaluated_tasks": request["task_ids"],
    "metrics": {
        "received_count": len(request["task_ids"]),
        "hidden_answer": "raw evaluator secret",
    },
    "score": 0.5,
    "details": {"secret": "raw evaluator detail"},
}))
""",
                encoding="utf-8",
            )
            config_path = root / "skepis.toml"
            initialize_config(config_path, project_root=root, tenant_id="tenant-mcp")
            register_benchmark(
                config_path,
                benchmark_id="arbitrary-workflow",
                evaluation_subject="agent-under-test",
                task_ids=task_ids,
                protected_paths={
                    "oauth-refresh-expiry": ["private_material/oauth/refresh.json"],
                    "refund-idempotency": [
                        "private_material/refund/input.yaml",
                        "private_material/refund/notes/*.txt",
                    ],
                },
                evaluator_command=(sys.executable, "evaluator.py"),
            )
            protected = root / "private_material/oauth/refresh.json"
            protected.parent.mkdir(parents=True)
            protected.write_text("MCP protected secret", encoding="utf-8")

            listed, missing_state, missing_report, read = asyncio.run(
                first_process(root, config_path)
            )
            before_readback = MemoryClient.local(str(root / ".skepis/memory.db")).read_events(limit=1000)
            results = asyncio.run(second_process(root, config_path))
            after_readback = MemoryClient.local(str(root / ".skepis/memory.db")).read_events(limit=1000)

        names = [tool.name for tool in listed.tools]
        self.assertEqual(
            names,
            [
                "skepis_preflight",
                "skepis_inspect",
                "skepis_run",
                "skepis_report",
                "skepis_read_protected",
            ],
        )
        annotations = {tool.name: tool.annotations for tool in listed.tools}
        for name in ("skepis_preflight", "skepis_inspect", "skepis_report"):
            self.assertTrue(annotations[name].readOnlyHint)
            self.assertTrue(annotations[name].idempotentHint)
            self.assertFalse(annotations[name].destructiveHint)
        for name in ("skepis_run", "skepis_read_protected"):
            self.assertFalse(annotations[name].readOnlyHint)
            self.assertFalse(annotations[name].idempotentHint)
            self.assertFalse(annotations[name].destructiveHint)

        self.assertFalse(missing_state.isError)
        missing_body = missing_state.structuredContent
        missing_body = missing_body.get("result", missing_body)
        self.assertEqual(missing_body["status"], "BLOCKED")
        self.assertEqual(missing_body["unknown_tasks"], sorted(task_ids))
        self.assertFalse(missing_body["clean_claim_permitted"])
        self.assertEqual(missing_body["exit_code"], 2)

        self.assertFalse(missing_report.isError)
        missing_report_body = missing_report.structuredContent
        missing_report_body = missing_report_body.get("result", missing_report_body)
        self.assertEqual(missing_report_body["evaluation"]["status"], "BLOCKED")
        self.assertFalse(missing_report_body["clean_claim"]["permitted"])
        self.assertFalse(missing_report_body["provenance"]["evaluation_complete"])
        self.assertEqual(missing_report_body["monitoring"]["sibyl_state"], "UNAVAILABLE")

        self.assertFalse(read.isError)
        read_body = read.structuredContent
        read_body = read_body.get("result", read_body)
        self.assertEqual(read_body["content"], "MCP protected secret")
        self.assertEqual(read_body["receipt"]["task_key"], "arbitrary-workflow/oauth-refresh-expiry")
        self.assertEqual(read_body["receipt"]["capture_outcome"], "RECORDED")

        (
            preflight_result,
            inspected,
            excluded,
            retrieved,
            flagged,
            strict,
            inspection_readback,
        ) = results
        for response in (preflight_result, inspected, excluded, retrieved, flagged, strict):
            self.assertFalse(response.isError)
        preflight_body = preflight_result.structuredContent
        preflight_body = preflight_body.get("result", preflight_body)
        self.assertEqual(preflight_body["exposed_tasks"], ["oauth-refresh-expiry"])
        self.assertEqual(
            preflight_body["clean_tasks"],
            ["inventory-race-condition", "ledger-replay-window", "refund-idempotency"],
        )
        inspect_body = inspected.structuredContent
        inspect_body = inspect_body.get("result", inspect_body)
        self.assertEqual(inspect_body["provenance"]["status"], "AVAILABLE")
        self.assertEqual(len(inspect_body["provenance"]["events"]), 1)
        self.assertNotIn("MCP protected secret", json.dumps(inspect_body))
        self.assertEqual(before_readback, inspection_readback)

        excluded_body = excluded.structuredContent
        excluded_body = excluded_body.get("result", excluded_body)
        self.assertEqual(excluded_body["status"], "EXCLUDED")
        self.assertEqual(
            excluded_body["selected_tasks"],
            ["inventory-race-condition", "ledger-replay-window", "refund-idempotency"],
        )
        self.assertEqual(excluded_body["evaluated_tasks"], excluded_body["selected_tasks"])
        self.assertTrue(excluded_body["clean_claim_permitted"])
        self.assertNotIn("evaluation_result", excluded_body)
        self.assertNotIn("raw evaluator secret", json.dumps(excluded_body))

        retrieved_body = retrieved.structuredContent
        retrieved_body = retrieved_body.get("result", retrieved_body)
        self.assertEqual(retrieved_body, excluded_body["report"])
        self.assertTrue(retrieved_body["clean_claim"]["permitted"])
        self.assertEqual(retrieved_body["evaluation"]["evaluated_count"], 3)
        self.assertNotIn("raw evaluator detail", json.dumps(retrieved_body))
        self.assertEqual(
            retrieved_body["monitoring"]["generic_agent_access"],
            "INCOMPLETE_MONITORING",
        )

        flagged_body = flagged.structuredContent
        flagged_body = flagged_body.get("result", flagged_body)
        self.assertEqual(flagged_body["status"], "FLAGGED")
        self.assertEqual(flagged_body["selected_tasks"], sorted(task_ids))
        self.assertEqual(flagged_body["flagged_tasks"], ["oauth-refresh-expiry"])
        self.assertFalse(flagged_body["clean_claim_permitted"])
        self.assertEqual(flagged_body["exit_code"], 0)

        strict_body = strict.structuredContent
        strict_body = strict_body.get("result", strict_body)
        self.assertEqual(strict_body["status"], "BLOCKED")
        self.assertEqual(strict_body["selected_tasks"], [])
        self.assertEqual(strict_body["evaluated_tasks"], [])
        self.assertFalse(strict_body["clean_claim_permitted"])
        self.assertEqual(strict_body["exit_code"], 2)

        event_types = []
        for event in after_readback:
            extra = event.get("extra", {}) if isinstance(event, dict) else {}
            if isinstance(extra, str):
                extra = json.loads(extra)
            if isinstance(extra, dict) and extra.get("event_type"):
                event_types.append(extra["event_type"])
        self.assertIn("benchmark_material_observed", event_types)
        self.assertIn("evaluation_started", event_types)
        self.assertIn("evaluation_gate_decision", event_types)
        self.assertIn("evaluation_completed", event_types)

    @unittest.skipUnless(
        importlib.util.find_spec("mcp") and importlib.util.find_spec("sibyl_memory_client"),
        "MCP failure-mode proof requires the MCP SDK and configured Sibyl runtime",
    )
    def test_stdio_client_surfaces_evaluator_failure_and_incomplete_monitoring(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from sibyl_memory_client import MemoryClient

        async def exercise(project: Path, config_path: Path):
            source_root = Path(__file__).parents[1] / "src"
            child_env = dict(os.environ)
            child_env["PYTHONPATH"] = str(source_root)
            params = StdioServerParameters(
                command=os.fspath(Path(sys.executable)),
                args=["-m", "skepis.mcp"],
                env=child_env,
                cwd=project,
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    failed = await session.call_tool(
                        "skepis_run",
                        {
                            "config_path": os.fspath(config_path),
                            "policy": "strict",
                        },
                    )
                    failed_body = failed.structuredContent
                    failed_body = failed_body.get("result", failed_body)
                    retrieved = await session.call_tool(
                        "skepis_report",
                        {
                            "config_path": os.fspath(config_path),
                            "run_id": failed_body["run_id"],
                        },
                    )

                    memory = MemoryClient.local(str(project / ".skepis/memory.db"))
                    memory.set_entity(
                        "benchmark_exposure",
                        "tenant-failure/agent-under-test/failure-benchmark",
                        {
                            "tenant_id": "tenant-failure",
                            "evaluation_subject": "agent-under-test",
                            "benchmark": "failure-benchmark",
                            "monitoring_status": "INCOMPLETE_MONITORING",
                            "tasks": {"clean-task": {"eligibility": "UNSEEN"}},
                        },
                        status="INCOMPLETE_MONITORING",
                    )
                    incomplete = await session.call_tool(
                        "skepis_run",
                        {
                            "config_path": os.fspath(config_path),
                            "policy": "strict",
                        },
                    )
                    return failed, failed_body, retrieved, incomplete

        with tempfile.TemporaryDirectory(prefix="skepis-mcp-failure-") as tmp:
            root = Path(tmp)
            evaluator = root / "failing_evaluator.py"
            evaluator.write_text(
                "import sys\nprint('private evaluator failure', file=sys.stderr)\nsys.exit(7)\n",
                encoding="utf-8",
            )
            config_path = write_config(
                root,
                tenant_id="tenant-failure",
                benchmark_id="failure-benchmark",
                evaluation_subject="agent-under-test",
                task_ids=["clean-task"],
                protected_paths={},
                evaluator_command=(sys.executable, "failing_evaluator.py"),
            )
            memory = MemoryClient.local(str(root / ".skepis/memory.db"))
            memory.set_entity(
                "benchmark_exposure",
                "tenant-failure/agent-under-test/failure-benchmark",
                {
                    "tenant_id": "tenant-failure",
                    "evaluation_subject": "agent-under-test",
                    "benchmark": "failure-benchmark",
                    "tasks": {"clean-task": {"eligibility": "UNSEEN"}},
                },
                status="UNSEEN",
            )
            failed, failed_body, retrieved, incomplete = asyncio.run(
                exercise(root, config_path)
            )

        self.assertFalse(failed.isError)
        self.assertEqual(failed_body["status"], "EVALUATOR_FAILED")
        self.assertEqual(failed_body["exit_code"], 1)
        self.assertEqual(failed_body["selected_tasks"], ["clean-task"])
        self.assertFalse(failed_body["clean_claim_permitted"])
        self.assertNotIn("evaluation_error", failed_body)
        self.assertNotIn("private evaluator failure", json.dumps(failed_body))

        self.assertFalse(retrieved.isError)
        retrieved_body = retrieved.structuredContent
        retrieved_body = retrieved_body.get("result", retrieved_body)
        self.assertEqual(retrieved_body["evaluation"]["status"], "EVALUATOR_FAILED")
        self.assertFalse(retrieved_body["clean_claim"]["permitted"])
        self.assertNotIn("private evaluator failure", json.dumps(retrieved_body))

        self.assertFalse(incomplete.isError)
        incomplete_body = incomplete.structuredContent
        incomplete_body = incomplete_body.get("result", incomplete_body)
        self.assertEqual(incomplete_body["status"], "BLOCKED")
        self.assertEqual(incomplete_body["unknown_tasks"], ["clean-task"])
        self.assertEqual(incomplete_body["monitoring_coverage"]["status"], "INCOMPLETE_MONITORING")
        self.assertFalse(incomplete_body["clean_claim_permitted"])
        self.assertEqual(incomplete_body["evaluated_tasks"], [])


if __name__ == "__main__":
    unittest.main()
