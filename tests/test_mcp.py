import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

from skepis.config import initialize_config, register_benchmark
from skepis.mcp import create_server, preflight


TASK_IDS = [
    "refund-idempotency",
    "oauth-refresh-expiry",
    "inventory-race-condition",
    "ledger-replay-window",
    "merchant-timezone-cutoff",
]


class FakeMemory:
    def __init__(self, body=None):
        self.body = body
        self.events = []

    def get_entity(self, _category, _name):
        if self.body is None:
            error = type("NotFoundError", (Exception,), {})
            raise error("missing")
        return {"body": self.body}

    def read_events(self, *, limit=50, since=None, until=None):
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
    def test_stdio_protocol_exposes_one_tool_and_preserves_scope_and_fail_closed_state(self):
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
                    isolated = await session.call_tool(
                        "skepis_preflight",
                        {
                            "config_path": os.fspath(other_config),
                            "task_ids": ["oauth-refresh-expiry", "refund-idempotency"],
                        },
                    )
                    return listed, exposed, isolated

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

            listed, exposed, isolated = asyncio.run(
                exercise(root, config_path, other_config)
            )
            self.assertEqual(memory.read_events(limit=1000), [])

        self.assertEqual([tool.name for tool in listed.tools], ["skepis_preflight"])
        tool = listed.tools[0]
        self.assertTrue(tool.annotations.readOnlyHint)
        self.assertTrue(tool.annotations.idempotentHint)
        self.assertEqual(exposed.isError, False)
        self.assertEqual(isolated.isError, False)

        exposed_payload = exposed.structuredContent
        isolated_payload = isolated.structuredContent
        self.assertIsInstance(exposed_payload, dict)
        self.assertIsInstance(isolated_payload, dict)
        exposed_result = exposed_payload.get("result", exposed_payload)
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
                    return await session.call_tool(
                        "skepis_preflight",
                        {
                            "config_path": os.fspath(config_path),
                            "task_ids": ["oauth-refresh-expiry", "refund-idempotency"],
                        },
                    )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_config(root)
            result = asyncio.run(exercise(root, config_path))

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


if __name__ == "__main__":
    unittest.main()
