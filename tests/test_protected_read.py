import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from skepis.capture import (
    CaptureOutcome,
    LocalPathCapture,
    LocalPathDetector,
    ProtectedReadBoundary,
    ProtectedReadError,
    ProtectedResource,
)
from skepis.config import initialize_config, register_benchmark
from skepis.eval.runner import run_fixture


class FakeMemory:
    def __init__(self):
        self.entities = {}
        self.events = []

    def get_entity(self, category, name):
        key = (category, name)
        if key not in self.entities:
            error = type("NotFoundError", (Exception,), {})
            raise error(name)
        return {"body": self.entities[key]}

    def set_entity(self, category, name, body, *, status=None):
        self.entities[(category, name)] = body
        return {"body": body, "status": status}

    def write_event(self, *, extra=None, ts=None, **_):
        event_id = f"event-{len(self.events) + 1}"
        self.events.append({"id": event_id, "extra": extra, "ts": ts})
        return event_id

    def read_events(self, *, limit=50, since=None, until=None):
        return self.events[-limit:]


def make_boundary(memory, root, *resources):
    capture = LocalPathCapture(
        memory=memory,
        detector=LocalPathDetector(root, resources),
        tenant_id="tenant-a",
        evaluation_subject="checkout-agent",
        benchmark_id="checkout-benchmark",
    )
    return ProtectedReadBoundary(capture=capture, root=root)


class ProtectedReadBoundaryTests(unittest.TestCase):
    def test_boundary_root_must_match_detector_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            capture = LocalPathCapture(
                memory=memory,
                detector=LocalPathDetector(
                    root,
                    [
                        ProtectedResource(
                            "tenant-a",
                            "checkout-benchmark",
                            "checkout-17",
                            "evals/checkout-17/solution.patch",
                        )
                    ],
                ),
                tenant_id="tenant-a",
                evaluation_subject="checkout-agent",
                benchmark_id="checkout-benchmark",
            )

            with self.assertRaisesRegex(ValueError, "match the capture detector root"):
                ProtectedReadBoundary(capture=capture, root=root / "other")

    def test_successful_read_returns_receipt_and_persists_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protected = root / "evals/checkout-17/solution.patch"
            protected.parent.mkdir(parents=True)
            content = b"opaque fixture\n"
            protected.write_bytes(content)
            memory = FakeMemory()
            boundary = make_boundary(
                memory,
                root,
                ProtectedResource(
                    "tenant-a",
                    "checkout-benchmark",
                    "checkout-17",
                    "evals/checkout-17/solution.patch",
                ),
            )

            result = boundary.read(
                protected,
                session_id="codex-session-a",
                observed_at="2026-08-29T22:00:00Z",
            )

            self.assertEqual(result.content, content)
            self.assertEqual(result.capture.outcome, CaptureOutcome.RECORDED)
            self.assertEqual(result.receipt.operation, "read")
            self.assertEqual(result.receipt.status, "success")
            self.assertEqual(result.receipt.normalized_path, "evals/checkout-17/solution.patch")
            self.assertEqual(result.receipt.task_key, "checkout-benchmark/checkout-17")
            self.assertEqual(result.receipt.bytes_read, len(content))
            self.assertEqual(result.receipt.content_sha256, hashlib.sha256(content).hexdigest())
            self.assertEqual(result.receipt.source_adapter, "protected_read")
            self.assertEqual(result.receipt.event_id, "event-1")
            event = memory.events[0]["extra"]
            self.assertEqual(event["event_type"], "benchmark_material_observed")
            self.assertEqual(event["evidence"]["operation"], "read")
            self.assertEqual(event["evidence"]["status"], "success")
            self.assertEqual(event["evidence"]["content_sha256"], result.receipt.content_sha256)
            body = memory.entities[("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark")]
            self.assertEqual(body["tasks"]["checkout-17"]["eligibility"], "EXPOSED")

    def test_unprotected_existing_path_is_rejected_without_read_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public = root / "public.txt"
            public.write_text("public", encoding="utf-8")
            memory = FakeMemory()
            boundary = make_boundary(
                memory,
                root,
                ProtectedResource(
                    "tenant-a",
                    "checkout-benchmark",
                    "checkout-17",
                    "evals/checkout-17/solution.patch",
                ),
            )

            with self.assertRaisesRegex(ProtectedReadError, "not registered as protected"):
                boundary.read(public, session_id="codex-session-a")

            self.assertEqual(memory.events, [])
            self.assertEqual(memory.entities, {})

    def test_failed_protected_read_records_gap_without_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            boundary = make_boundary(
                memory,
                root,
                ProtectedResource(
                    "tenant-a",
                    "checkout-benchmark",
                    "checkout-17",
                    "evals/checkout-17/solution.patch",
                ),
            )

            with self.assertRaisesRegex(ProtectedReadError, "protected read failed"):
                boundary.read(
                    "evals/checkout-17/solution.patch",
                    session_id="codex-session-a",
                    observed_at="2026-08-29T22:01:00Z",
                )

            body = memory.entities[("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark")]
            self.assertEqual(body["monitoring_status"], "INCOMPLETE_MONITORING")
            self.assertEqual(body["tasks"], {})
            self.assertEqual(memory.events[0]["extra"]["event_type"], "observation_gap_detected")
            self.assertEqual(
                memory.events[0]["extra"]["monitoring_status"],
                "INCOMPLETE_MONITORING",
            )

    def test_ambiguous_mapping_records_gap_without_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protected = root / "evals/checkout-17/solution.patch"
            protected.parent.mkdir(parents=True)
            protected.write_text("opaque", encoding="utf-8")
            memory = FakeMemory()
            boundary = make_boundary(
                memory,
                root,
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-17", "evals/**/solution.patch"
                ),
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-18", "evals/checkout-17/**"
                ),
            )

            with self.assertRaisesRegex(ProtectedReadError, "multiple tasks"):
                boundary.read(
                    protected,
                    session_id="codex-session-a",
                    observed_at="2026-08-29T22:02:00Z",
                )

            body = memory.entities[("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark")]
            self.assertEqual(body["monitoring_status"], "INCOMPLETE_MONITORING")
            self.assertEqual(body["tasks"], {})
            self.assertEqual(memory.events[0]["extra"]["event_type"], "observation_gap_detected")

    def test_runner_rejects_fixture_tasks_outside_registered_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture.json"
            fixture.write_text(
                json.dumps(
                    {
                        "benchmark": "checkout-benchmark",
                        "evaluation_subject": "checkout-agent",
                        "task_ids": ["checkout-17", "unregistered-99"],
                        "cases": {
                            "checkout-17": {"expected": "x", "candidate_output": "x"},
                            "unregistered-99": {"expected": "x", "candidate_output": "x"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            memory = FakeMemory()

            with self.assertRaisesRegex(ValueError, "not registered in the project"):
                run_fixture(
                    fixture,
                    memory=memory,
                    policy="exclude",
                    tenant_id="tenant-a",
                    evaluation_subject="checkout-agent",
                    benchmark_id="checkout-benchmark",
                    allowed_task_ids=["checkout-17"],
                )

            self.assertEqual(memory.events, [])

    def test_runner_requires_registered_task_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixture.json"
            fixture.write_text(
                json.dumps(
                    {
                        "benchmark": "checkout-benchmark",
                        "evaluation_subject": "checkout-agent",
                        "task_ids": ["checkout-17"],
                        "cases": {
                            "checkout-17": {"expected": "x", "candidate_output": "x"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            memory = FakeMemory()

            with self.assertRaisesRegex(ValueError, "registered task allowlist is required"):
                run_fixture(
                    fixture,
                    memory=memory,
                    policy="exclude",
                    tenant_id="tenant-a",
                    evaluation_subject="checkout-agent",
                    benchmark_id="checkout-benchmark",
                    allowed_task_ids=None,
                )

            self.assertEqual(memory.events, [])

    @unittest.skipUnless(
        importlib.util.find_spec("sibyl_memory_client"),
        "fresh-process CLI proof requires the configured Sibyl runtime",
    )
    def test_cli_read_persists_exposure_for_a_fresh_status_process(self):
        source_root = Path(__file__).parents[1] / "src"
        child_env = dict(os.environ)
        existing_pythonpath = child_env.get("PYTHONPATH")
        child_env["PYTHONPATH"] = str(source_root) + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
        with tempfile.TemporaryDirectory(prefix="skepis-protected-read-") as tmp:
            root = Path(tmp)
            fixture = root / "fixture.json"
            fixture.write_text(
                json.dumps(
                    {
                        "benchmark": "checkout-benchmark",
                        "evaluation_subject": "checkout-agent",
                        "task_ids": ["checkout-17"],
                        "cases": {
                            "checkout-17": {
                                "expected": "opaque",
                                "candidate_output": "opaque",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            config_path = root / "skepis.toml"
            initialize_config(
                config_path,
                project_root=root,
                tenant_id="tenant-a",
                memory_db=".skepis/memory.db",
            )
            register_benchmark(
                config_path,
                benchmark_id="checkout-benchmark",
                evaluation_subject="checkout-agent",
                fixture=fixture,
                task_ids=["checkout-17"],
                protected_paths={
                    "checkout-17": ["evals/checkout-17/solution.patch"]
                },
                evaluator_command=(
                    sys.executable,
                    str(Path(__file__).parents[1] / "examples" / "checkout-benchmark" / "evaluator.py"),
                ),
            )
            protected = root / "evals/checkout-17/solution.patch"
            protected.parent.mkdir(parents=True)
            protected.write_text("opaque", encoding="utf-8")

            read = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "skepis",
                    "exposure",
                    "read",
                    "--config",
                    str(config_path),
                    "--path",
                    str(protected),
                    "--session-id",
                    "codex-session-a",
                    "--observed-at",
                    "2026-08-29T22:03:00Z",
                    "--json",
                ],
                cwd=root,
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(read.returncode, 0, read.stderr)
            read_result = json.loads(read.stdout)
            self.assertEqual(read_result["content"], "opaque")
            self.assertEqual(read_result["receipt"]["status"], "success")
            self.assertEqual(read_result["receipt"]["task_key"], "checkout-benchmark/checkout-17")

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
            status_result = json.loads(status.stdout)
            self.assertEqual(status_result["exposed_tasks"], ["checkout-17"])
            self.assertEqual(status_result["clean_tasks"], [])
            self.assertEqual(status_result["unknown_tasks"], [])

            evaluation = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "skepis",
                    "eval",
                    "run",
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
            evaluation_result = json.loads(evaluation.stdout)
            self.assertEqual(evaluation_result["status"], "EXCLUDED")
            self.assertEqual(evaluation_result["selected_tasks"], [])
            self.assertEqual(evaluation_result["evaluated_tasks"], [])
            self.assertNotIn("checkout-17", evaluation_result["evaluated_tasks"])

            override = root / "override.json"
            override.write_text(
                json.dumps(
                    {
                        "benchmark": "checkout-benchmark",
                        "evaluation_subject": "checkout-agent",
                        "task_ids": ["checkout-17", "unregistered-99"],
                        "cases": {
                            "checkout-17": {"expected": "opaque", "candidate_output": "opaque"},
                            "unregistered-99": {"expected": "opaque", "candidate_output": "opaque"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            rejected = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "skepis",
                    "eval",
                    "run",
                    "--config",
                    str(config_path),
                    "--fixture",
                    str(override),
                    "--json",
                ],
                cwd=root,
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("unrecognized arguments: --fixture", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
