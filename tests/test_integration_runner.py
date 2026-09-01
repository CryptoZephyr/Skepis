import contextlib
import io
import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skepis.config import initialize_config, register_benchmark
from skepis.eval.runner import _parser


TENANT_ID = "00000000-0000-0000-0000-000000000001"


class EvaluationRunnerIntegrationTests(unittest.TestCase):
    def test_standalone_runner_requires_registered_project_config(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                _parser().parse_args(
                    ["--fixture", "fixture.json", "--config", "skepis.toml"]
                )

        self.assertEqual(raised.exception.code, 2)

    @unittest.skipUnless(
        importlib.util.find_spec("sibyl_memory_client"),
        "evaluation integration proof requires the configured Sibyl runtime",
    )
    def test_real_command_runs_only_policy_selected_tasks(self):
        fixture_path = Path(__file__).parents[1] / "examples" / "checkout-benchmark" / "fixture.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        source_root = fixture_path.parents[2] / "src"
        child_env = dict(os.environ)
        child_env["PYTHONPATH"] = str(source_root)

        with tempfile.TemporaryDirectory(prefix="skepis-integration-proof-") as tmp:
            base = Path(tmp)
            project = base / "project"
            protected = project / "evals/checkout-17/solution.patch"
            protected.parent.mkdir(parents=True)
            protected.write_text("opaque fixture", encoding="utf-8")
            fixture_copy = project / "fixture.json"
            fixture_copy.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")
            evaluator_copy = project / "evaluator.py"
            evaluator_copy.write_text(
                (fixture_path.parent / "evaluator.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            config_path = project / "skepis.toml"
            initialize_config(
                config_path,
                project_root=project,
                tenant_id=TENANT_ID,
                memory_db=".skepis/memory.db",
            )
            register_benchmark(
                config_path,
                benchmark_id=fixture["benchmark"],
                evaluation_subject=fixture["evaluation_subject"],
                fixture=fixture_copy,
                task_ids=fixture["task_ids"],
                protected_paths=fixture["protected_paths"],
                evaluator_command=(sys.executable, "evaluator.py"),
            )
            db = project / ".skepis/memory.db"

            writer = r'''
import json
import sys
from pathlib import Path
from sibyl_memory_client import MemoryClient
from skepis.capture import AccessSignal, LocalPathCapture, LocalPathDetector, ProtectedResource

db, project, protected = map(Path, sys.argv[1:4])
fixture = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
memory = MemoryClient.local(str(db))
resources = [
    ProtectedResource(
        "00000000-0000-0000-0000-000000000001",
        fixture["benchmark"],
        task_id,
        pattern,
    )
    for task_id, patterns in fixture["protected_paths"].items()
    for pattern in patterns
]
capture = LocalPathCapture(
    memory=memory,
    detector=LocalPathDetector(project, resources),
    tenant_id="00000000-0000-0000-0000-000000000001",
    evaluation_subject=fixture["evaluation_subject"],
    benchmark_id=fixture["benchmark"],
)
protected.read_text(encoding="utf-8")
result = capture.observe(
    AccessSignal(
        protected,
        "2026-08-29T20:00:00Z",
        "session-a",
        observation_id="checkout-17-exposure",
    )
)
print(json.dumps({"outcome": result.outcome.value, "task": result.task_key}))
'''
            writer_process = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    writer,
                    str(db),
                    str(project),
                    str(protected),
                    str(fixture_copy),
                ],
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(writer_process.returncode, 0, writer_process.stderr)
            self.assertEqual(json.loads(writer_process.stdout), {
                "outcome": "RECORDED",
                "task": "checkout-benchmark/checkout-17",
            })

            evaluation_process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "skepis.eval.runner",
                    "--config",
                    str(config_path),
                    "--policy",
                    "exclude",
                ],
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(evaluation_process.returncode, 0, evaluation_process.stderr)
            result = json.loads(evaluation_process.stdout)

            self.assertEqual(result["requested_tasks"], ["checkout-16", "checkout-17", "checkout-18"])
            self.assertEqual(result["clean_tasks"], ["checkout-16", "checkout-18"])
            self.assertEqual(result["exposed_tasks"], ["checkout-17"])
            self.assertEqual(result["unknown_tasks"], [])
            self.assertEqual(result["selected_tasks"], ["checkout-16", "checkout-18"])
            self.assertEqual(result["excluded_tasks"], ["checkout-17"])
            self.assertEqual(result["flagged_tasks"], [])
            self.assertEqual(result["status"], "EXCLUDED")
            self.assertTrue(result["clean_claim_permitted"])
            self.assertEqual(result["evaluated_tasks"], ["checkout-16", "checkout-18"])
            self.assertEqual(
                result["evaluation_result"]["scores"],
                {"checkout-16": True, "checkout-18": True},
            )
            self.assertEqual(result["evaluation_result"]["score"], 1.0)
            self.assertTrue(result["evaluation_started_journaled"])
            self.assertTrue(result["gate_decision_journaled"])
            self.assertTrue(result["evaluation_completed_journaled"])
            self.assertTrue(result["journaled"])
            self.assertNotIn("checkout-17", result["evaluated_tasks"])
            self.assertNotIn("checkout-17", result["evaluation_result"]["scores"])

            for database_path in db.parent.glob("memory.db*"):
                database_path.unlink()

            blocked_process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "skepis.eval.runner",
                    "--config",
                    str(config_path),
                    "--policy",
                    "strict",
                ],
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blocked_process.returncode, 2, blocked_process.stderr)
            blocked_result = json.loads(blocked_process.stdout)
            self.assertEqual(blocked_result["status"], "BLOCKED")
            self.assertEqual(blocked_result["selected_tasks"], [])
            self.assertEqual(blocked_result["evaluated_tasks"], [])
            self.assertFalse(blocked_result["clean_claim_permitted"])


if __name__ == "__main__":
    unittest.main()
