import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from skepis.config import initialize_config, register_benchmark
from skepis.mcp import inspect, preflight


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

    def read_events(self, *, limit=50, since=None, until=None):
        if self.read_error is not None:
            raise self.read_error
        return self.events[-limit:]


def write_config(root: Path, *, name: str = "skepis.toml", tenant_id: str = "tenant-a") -> Path:
    config_path = root / name
    initialize_config(
        config_path,
        project_root=root,
        tenant_id=tenant_id,
        memory_db=".skepis/memory.db",
    )
    register_benchmark(
        config_path,
        benchmark_id="payments-regression",
        evaluation_subject="payments-agent",
        task_ids=TASK_IDS,
        protected_paths={
            "refund-idempotency": ["answers/refund/idempotency.yaml"],
            "oauth-refresh-expiry": ["answers/oauth/refresh-expiry.json"],
        },
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
            ["skepis_preflight", "skepis_inspect"],
        )
        for tool in listed.tools:
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)
            self.assertTrue(tool.annotations.idempotentHint)
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
            ["skepis_preflight", "skepis_inspect"],
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


if __name__ == "__main__":
    unittest.main()
