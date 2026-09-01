import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import unittest

from skepis.capture import LocalPathCapture, LocalPathDetector, ProtectedReadBoundary, ProtectedResource
from skepis.cli import main
from skepis.config import initialize_config, register_benchmark
from skepis.eval import CommandEvaluator, run_evaluation


class FakeMemory:
    def __init__(self, body=None):
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


def scoped_body(tasks):
    return {
        "tenant_id": "tenant-a",
        "evaluation_subject": "payments-agent",
        "benchmark": "payments-regression",
        "tasks": tasks,
    }


class GeneralizedEvaluationTests(unittest.TestCase):
    def test_registration_without_fixture_persists_real_evaluator_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "skepis.toml"
            initialize_config(
                config_path,
                project_root=root,
                tenant_id="tenant-a",
            )

            config = register_benchmark(
                config_path,
                benchmark_id="payments-regression",
                evaluation_subject="payments-agent",
                task_ids=["refund-idempotency", "oauth-refresh-expiry"],
                protected_paths={
                    "refund-idempotency": [
                        "answers/refund/idempotency.yaml",
                        "hidden/refund/idempotency.test",
                    ],
                    "oauth-refresh-expiry": ["answers/oauth/refresh-expiry.json"],
                },
                evaluator_command=(sys.executable, "evaluate.py"),
            )

            benchmark = config.benchmark
            self.assertIsNotNone(benchmark)
            self.assertIsNone(benchmark.fixture)
            self.assertIsNotNone(benchmark.evaluator)
            self.assertEqual(benchmark.evaluator.command, (sys.executable, "evaluate.py"))
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("fixture", raw["benchmark"])
            self.assertEqual(
                raw["benchmark"]["evaluator"]["command"],
                [sys.executable, "evaluate.py"],
            )

    def test_registration_allows_an_empty_task_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "skepis.toml"
            initialize_config(config_path, project_root=root, tenant_id="tenant-a")

            config = register_benchmark(
                config_path,
                benchmark_id="empty-regression",
                evaluation_subject="payments-agent",
                task_ids=[],
                protected_paths={},
                evaluator_command=(sys.executable, "evaluate.py"),
            )

            self.assertEqual(config.benchmark.task_ids, ())

    def test_real_command_receives_dynamic_policy_selected_semantic_tasks(self):
        task_ids = [
            "refund-idempotency",
            "oauth-refresh-expiry",
            "inventory-race-condition",
            "ledger-replay-window",
            "merchant-timezone-cutoff",
            "partial-capture-recovery",
            "duplicate-webhook-ordering",
            "currency-rounding-boundary",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evaluator_script = root / "evaluate.py"
            evaluator_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os

                    request = json.loads(open(os.environ["SKEPIS_EVALUATION_REQUEST"], encoding="utf-8").read())
                    print(json.dumps({
                        "evaluated_tasks": request["task_ids"],
                        "metrics": {
                            "received_count": len(request["task_ids"]),
                            "benchmark": request["benchmark_id"],
                        },
                        "score": len(request["task_ids"]),
                    }))
                    """
                ),
                encoding="utf-8",
            )
            exposed = "oauth-refresh-expiry"
            memory = FakeMemory(
                scoped_body({
                    exposed: {"eligibility": "EXPOSED"},
                })
            )
            evaluator = CommandEvaluator(
                (sys.executable, str(evaluator_script)),
                project_root=root,
            )

            result, exit_code = run_evaluation(
                evaluator=evaluator,
                memory=memory,
                task_ids=task_ids,
                policy="exclude",
                tenant_id="tenant-a",
                evaluation_subject="payments-agent",
                benchmark_id="payments-regression",
                project_root=root,
            )

            expected_selected = sorted(set(task_ids) - {exposed})
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["requested_tasks"], sorted(task_ids))
            self.assertEqual(result["selected_tasks"], expected_selected)
            self.assertEqual(result["excluded_tasks"], [exposed])
            self.assertEqual(result["evaluated_tasks"], expected_selected)
            self.assertEqual(result["evaluation_result"]["evaluated_tasks"], expected_selected)
            self.assertEqual(result["evaluation_result"]["metrics"]["received_count"], 7)
            self.assertEqual(result["evaluation_result"]["metrics"]["benchmark"], "payments-regression")
            self.assertEqual(result["score"], 7)
            self.assertTrue(result["evaluation_complete"])
            self.assertTrue(result["clean_claim_permitted"])

    def test_evaluator_seam_preserves_exclude_flag_and_strict_policies(self):
        task_ids = ["clean-refund", "exposed-refund", "uncertain-refund"]

        def evaluate(request):
            return {
                "evaluated_tasks": list(request.task_ids),
                "metrics": {"received_count": len(request.task_ids)},
            }

        for policy, expected_selected, expected_status, expected_exit in (
            ("exclude", ["clean-refund"], "BLOCKED", 2),
            ("flag", task_ids, "FLAGGED", 0),
            ("strict", [], "BLOCKED", 2),
        ):
            with self.subTest(policy=policy):
                memory = FakeMemory(
                    scoped_body(
                        {
                            "clean-refund": {"eligibility": "UNSEEN"},
                            "exposed-refund": {"eligibility": "EXPOSED"},
                            "uncertain-refund": {"eligibility": "REVIEW_REQUIRED"},
                        }
                    )
                )
                result, exit_code = run_evaluation(
                    evaluator=evaluate,
                    memory=memory,
                    task_ids=task_ids,
                    policy=policy,
                    tenant_id="tenant-a",
                    evaluation_subject="payments-agent",
                    benchmark_id="payments-regression",
                )

                self.assertEqual(exit_code, expected_exit)
                self.assertEqual(result["selected_tasks"], sorted(expected_selected))
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["evaluated_tasks"], sorted(expected_selected))
                self.assertFalse(result["clean_claim_permitted"])
                if policy == "strict":
                    self.assertIsNone(result["evaluation_result"])
                    self.assertFalse(result["evaluation_complete"])
                    self.assertEqual(result["reason"], "strict_policy_blocked")

    def test_protected_read_maps_arbitrary_resources_to_semantic_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protected = root / "answers/refund/idempotency.yaml"
            protected.parent.mkdir(parents=True)
            protected.write_text("answer: opaque", encoding="utf-8")
            memory = FakeMemory()
            capture = LocalPathCapture(
                memory=memory,
                detector=LocalPathDetector(
                    root,
                    [
                        ProtectedResource(
                            "tenant-a",
                            "payments-regression",
                            "refund-idempotency",
                            "answers/refund/idempotency.yaml",
                        ),
                        ProtectedResource(
                            "tenant-a",
                            "payments-regression",
                            "refund-idempotency",
                            "hidden/refund/idempotency.test",
                        ),
                    ],
                ),
                tenant_id="tenant-a",
                evaluation_subject="payments-agent",
                benchmark_id="payments-regression",
            )

            result = ProtectedReadBoundary(capture=capture, root=root).read(
                protected,
                session_id="development-session",
                observed_at="2026-09-01T10:00:00Z",
            )

            self.assertEqual(result.receipt.task_key, "payments-regression/refund-idempotency")
            self.assertEqual(result.receipt.normalized_path, "answers/refund/idempotency.yaml")
            self.assertEqual(memory.body["tasks"]["refund-idempotency"]["eligibility"], "EXPOSED")

    def test_evaluator_cannot_return_tasks_outside_policy_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evaluator_script = root / "evaluate.py"
            evaluator_script.write_text(
                "print('{\"evaluated_tasks\": [\"outside-task\"]}')\n",
                encoding="utf-8",
            )
            memory = FakeMemory(
                scoped_body({"refund-idempotency": {"eligibility": "UNSEEN"}})
            )
            evaluator = CommandEvaluator(
                (sys.executable, str(evaluator_script)),
                project_root=root,
            )

            result, exit_code = run_evaluation(
                evaluator=evaluator,
                memory=memory,
                task_ids=["refund-idempotency"],
                policy="strict",
                tenant_id="tenant-a",
                evaluation_subject="payments-agent",
                benchmark_id="payments-regression",
                project_root=root,
            )

            self.assertEqual(exit_code, 1)
            self.assertEqual(result["status"], "EVALUATOR_FAILED")
            self.assertFalse(result["clean_claim_permitted"])
            self.assertEqual(result["evaluated_tasks"], [])
            self.assertIn("outside policy-selected task set", result["evaluation_error"])

    def test_cli_registration_accepts_real_evaluator_without_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "skepis.toml"
            initialize_config(config_path, project_root=root, tenant_id="tenant-a")

            exit_code = main(
                [
                    "benchmark",
                    "register",
                    "--config",
                    str(config_path),
                    "--id",
                    "payments-regression",
                    "--evaluation-subject",
                    "payments-agent",
                    "--task",
                    "refund-idempotency",
                    "--evaluator-command",
                    f"{sys.executable} evaluate.py",
                ]
            )

            self.assertEqual(exit_code, 0)
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("fixture", raw["benchmark"])
            self.assertEqual(raw["benchmark"]["evaluator"]["command"], [sys.executable, "evaluate.py"])

    def test_cli_eval_run_requires_a_configured_evaluator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "skepis.toml"
            initialize_config(config_path, project_root=root, tenant_id="tenant-a")
            register_benchmark(
                config_path,
                benchmark_id="payments-regression",
                evaluation_subject="payments-agent",
                task_ids=["refund-idempotency"],
                protected_paths={},
            )

            exit_code = main(["eval", "run", "--config", str(config_path)])

            self.assertEqual(exit_code, 2)

    @unittest.skipUnless(
        importlib.util.find_spec("sibyl_memory_client"),
        "fresh-process generalized proof requires the configured Sibyl runtime",
    )
    def test_public_workflow_handles_unrelated_dynamic_benchmark_without_fixture(self):
        task_ids = [
            "refund-idempotency",
            "oauth-refresh-expiry",
            "inventory-race-condition",
            "ledger-replay-window",
            "merchant-timezone-cutoff",
            "partial-capture-recovery",
            "duplicate-webhook-ordering",
            "currency-rounding-boundary",
            "regional-tax-rollover",
        ]
        with tempfile.TemporaryDirectory(prefix="skepis-generalized-proof-") as tmp:
            root = Path(tmp)
            source_root = Path(__file__).parents[1] / "src"
            child_env = dict(os.environ)
            existing_pythonpath = child_env.get("PYTHONPATH")
            child_env["PYTHONPATH"] = str(source_root) + (
                os.pathsep + existing_pythonpath if existing_pythonpath else ""
            )
            evaluator = root / "evaluator.py"
            evaluator.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os

                    request = json.loads(open(os.environ["SKEPIS_EVALUATION_REQUEST"], encoding="utf-8").read())
                    tasks = request["task_ids"]
                    print(json.dumps({
                        "evaluated_tasks": tasks,
                        "metrics": {"received_count": len(tasks)},
                        "score": len(tasks),
                    }))
                    """
                ),
                encoding="utf-8",
            )
            protected = root / "private_material/refund/answer.bin"
            protected.parent.mkdir(parents=True)
            protected.write_bytes(b"opaque benchmark answer")

            config_path = root / "skepis.toml"
            initialize_config(
                config_path,
                project_root=root,
                tenant_id="tenant-a",
            )
            register_benchmark(
                config_path,
                benchmark_id="payments-regression",
                evaluation_subject="payments-agent",
                task_ids=task_ids,
                protected_paths={
                    "refund-idempotency": [
                        "private_material/refund/answer.bin",
                        "private_material/refund/notes/*.txt",
                    ],
                },
                evaluator_command=(sys.executable, "evaluator.py"),
            )
            self.assertFalse((root / "fixture.json").exists())

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
                    "private_material/refund/answer.bin",
                    "--session-id",
                    "development-session",
                    "--observed-at",
                    "2026-09-01T10:00:00Z",
                    "--json",
                ],
                cwd=root,
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(read.returncode, 0, read.stderr)
            self.assertEqual(json.loads(read.stdout)["receipt"]["task_key"], "payments-regression/refund-idempotency")

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
            self.assertEqual(status_result["exposed_tasks"], ["refund-idempotency"])
            self.assertEqual(status_result["unknown_tasks"], [])
            self.assertEqual(len(status_result["clean_tasks"]), 8)

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
            selected = sorted(set(task_ids) - {"refund-idempotency"})
            self.assertEqual(evaluation_result["selected_tasks"], selected)
            self.assertEqual(evaluation_result["excluded_tasks"], ["refund-idempotency"])
            self.assertEqual(evaluation_result["evaluated_tasks"], selected)
            self.assertEqual(evaluation_result["evaluation_result"]["evaluated_tasks"], selected)
            self.assertEqual(evaluation_result["metrics"]["received_count"], 8)
            self.assertTrue(evaluation_result["clean_claim_permitted"])


if __name__ == "__main__":
    unittest.main()
