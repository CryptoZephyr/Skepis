import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

from skepis.cli import main
from skepis.config import ConfigError, initialize_config, load_config, register_benchmark


TENANT_ID = "00000000-0000-0000-0000-000000000001"


def write_fixture(root: Path) -> Path:
    source = Path(__file__).parents[1] / "examples" / "checkout-benchmark" / "fixture.json"
    fixture = root / "fixture.json"
    shutil.copyfile(source, fixture)
    evaluator_source = Path(__file__).parents[1] / "examples" / "checkout-benchmark" / "evaluator.py"
    shutil.copyfile(evaluator_source, root / "evaluator.py")
    return fixture


def make_initialized_project(root: Path) -> Path:
    config_path = root / "skepis.toml"
    initialize_config(
        config_path,
        project_root=root,
        tenant_id=TENANT_ID,
        memory_db=".skepis/memory.db",
    )
    return config_path


def register_checkout(config_path: Path, fixture: Path) -> None:
    register_benchmark(
        config_path,
        benchmark_id="checkout-benchmark",
        evaluation_subject="checkout-agent",
        fixture=fixture,
        task_ids=["checkout-16", "checkout-17", "checkout-18"],
        protected_paths={
            "checkout-17": [
                "evals/checkout-17/hidden/**",
                "evals/checkout-17/solution.patch",
            ]
        },
        evaluator_command=(sys.executable, "evaluator.py"),
    )


def run_command(args, *, cwd=None):
    executable = shutil.which("skepis")
    if executable is None:
        executable = sys.executable
        args = ["-m", "skepis", *args]
    return subprocess.run(
        [executable, *args],
        cwd=cwd,
        env=dict(os.environ),
        text=True,
        capture_output=True,
        check=False,
    )


class ConfigValidationTests(unittest.TestCase):
    def test_missing_config_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "config not found"):
                load_config(Path(tmp) / "skepis.toml")

    def test_malformed_config_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skepis.toml"
            path.write_text("[benchmark\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "malformed config"):
                load_config(path)

    def test_missing_benchmark_id_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            fixture = write_fixture(root)
            config_path.write_text(
                config_path.read_text(encoding="utf-8")
                + "\n[benchmark]\nevaluation_subject = \"checkout-agent\"\n"
                + "fixture = \"fixture.json\"\ntask_ids = [\"checkout-16\"]\n",
                encoding="utf-8",
            )
            self.assertTrue(fixture.is_file())
            with self.assertRaisesRegex(ConfigError, "missing benchmark id"):
                load_config(config_path, require_benchmark=True)

    def test_missing_evaluation_subject_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            write_fixture(root)
            config_path.write_text(
                config_path.read_text(encoding="utf-8")
                + "\n[benchmark]\nid = \"checkout-benchmark\"\n"
                + "fixture = \"fixture.json\"\ntask_ids = [\"checkout-16\"]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "missing evaluation subject"):
                load_config(config_path, require_benchmark=True)

    def test_duplicate_task_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            fixture = write_fixture(root)
            with self.assertRaisesRegex(ConfigError, "duplicate task id"):
                register_benchmark(
                    config_path,
                    benchmark_id="checkout-benchmark",
                    evaluation_subject="checkout-agent",
                    fixture=fixture,
                    task_ids=["checkout-16", "checkout-16"],
                    protected_paths={},
                )

    def test_unknown_protected_task_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            fixture = write_fixture(root)
            with self.assertRaisesRegex(ConfigError, "unknown task"):
                register_benchmark(
                    config_path,
                    benchmark_id="checkout-benchmark",
                    evaluation_subject="checkout-agent",
                    fixture=fixture,
                    task_ids=["checkout-16"],
                    protected_paths={"checkout-17": ["evals/checkout-17/**"]},
                )

    def test_ambiguous_protected_registration_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            fixture = write_fixture(root)
            with self.assertRaisesRegex(ConfigError, "ambiguous protected-resource registration"):
                register_benchmark(
                    config_path,
                    benchmark_id="checkout-benchmark",
                    evaluation_subject="checkout-agent",
                    fixture=fixture,
                    task_ids=["checkout-16", "checkout-17"],
                    protected_paths={
                        "checkout-16": ["evals/**"],
                        "checkout-17": ["evals/checkout-17/**"],
                    },
                )

    def test_missing_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            with self.assertRaisesRegex(ConfigError, "missing fixture"):
                register_benchmark(
                    config_path,
                    benchmark_id="checkout-benchmark",
                    evaluation_subject="checkout-agent",
                    fixture=root / "missing.json",
                    task_ids=["checkout-16"],
                    protected_paths={},
                )

    def test_fixture_outside_project_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "project"
            config_path = make_initialized_project(root)
            outside_fixture = base / "fixture.json"
            outside_fixture.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, "fixture must be inside the project root"):
                register_benchmark(
                    config_path,
                    benchmark_id="checkout-benchmark",
                    evaluation_subject="checkout-agent",
                    fixture=outside_fixture,
                    task_ids=["checkout-17"],
                    protected_paths={},
                )

    def test_scope_delimiter_is_rejected_at_configuration_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "path separators"):
                initialize_config(
                    Path(tmp) / "skepis.toml",
                    project_root=tmp,
                    tenant_id="tenant/a",
                )

    def test_memory_db_outside_project_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaisesRegex(ConfigError, "memory_db must be inside the project root"):
                initialize_config(
                    base / "project" / "skepis.toml",
                    project_root=base / "project",
                    tenant_id=TENANT_ID,
                    memory_db=base / "outside.db",
                )

    def test_unsupported_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace(
                    'default_policy = "exclude"',
                    'default_policy = "review"',
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigError, "unsupported policy"):
                load_config(config_path)

    def test_config_has_no_schema_version_and_keeps_subject_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            fixture = write_fixture(root)
            register_checkout(config_path, fixture)
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("schema_version", raw)
            self.assertEqual(raw["benchmark"]["id"], "checkout-benchmark")
            self.assertEqual(raw["benchmark"]["evaluation_subject"], "checkout-agent")
            self.assertNotEqual(raw["benchmark"]["id"], raw["benchmark"]["evaluation_subject"])


class CliProofTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("sibyl_memory_client"),
        "fresh-process CLI proof requires the configured Sibyl runtime",
    )
    def test_clean_project_cli_proof_and_read_only_status(self):
        source_root = Path(__file__).parents[1] / "src"
        child_env = dict(os.environ)
        child_env["PYTHONPATH"] = str(source_root)
        with tempfile.TemporaryDirectory(prefix="skepis-cli-proof-") as tmp:
            root = Path(tmp)
            fixture = write_fixture(root)
            init = run_command(["init", "--root", str(root), "--tenant-id", TENANT_ID])
            self.assertEqual(init.returncode, 0, init.stderr)
            config_path = root / "skepis.toml"
            self.assertTrue(config_path.is_file())

            register = run_command([
                "benchmark",
                "register",
                "--config",
                str(config_path),
                "--id",
                "checkout-benchmark",
                "--evaluation-subject",
                "checkout-agent",
                "--fixture",
                str(fixture),
                "--task",
                "checkout-16",
                "--task",
                "checkout-17",
                "--task",
                "checkout-18",
                "--protected",
                "checkout-17=evals/checkout-17/hidden/**",
                "--protected",
                "checkout-17=evals/checkout-17/solution.patch",
                "--evaluator-command",
                f"{sys.executable} evaluator.py",
            ])
            self.assertEqual(register.returncode, 0, register.stderr)
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(config["benchmark"]["id"], "checkout-benchmark")
            self.assertEqual(config["benchmark"]["evaluation_subject"], "checkout-agent")

            db = root / ".skepis" / "memory.db"
            protected = root / "evals/checkout-17/solution.patch"
            protected.parent.mkdir(parents=True)
            protected.write_text("opaque fixture", encoding="utf-8")
            writer = r'''
import json
import sys
import tomllib
from pathlib import Path
from sibyl_memory_client import MemoryClient
from skepis.capture import AccessSignal, LocalPathCapture, LocalPathDetector, ProtectedResource

config_path, db_path, protected_path = map(Path, sys.argv[1:4])
config = tomllib.loads(config_path.read_text(encoding="utf-8"))
benchmark = config["benchmark"]
resources = [
    ProtectedResource(
        config["tenant_id"],
        benchmark["id"],
        task_id,
        pattern,
    )
    for task_id, patterns in benchmark["protected_paths"].items()
    for pattern in patterns
]
memory = MemoryClient.local(str(db_path))
capture = LocalPathCapture(
    memory=memory,
    detector=LocalPathDetector(Path(config_path).parent, resources),
    tenant_id=config["tenant_id"],
    evaluation_subject=benchmark["evaluation_subject"],
    benchmark_id=benchmark["id"],
)
protected_path.read_text(encoding="utf-8")
result = capture.observe(
    AccessSignal(
        protected_path,
        "2026-08-29T21:00:00Z",
        "session-a",
        observation_id="checkout-17-exposure",
    )
)
print(json.dumps({"outcome": result.outcome.value, "task": result.task_key}))
'''
            writer = subprocess.run(
                [sys.executable, "-c", writer, str(config_path), str(db), str(protected)],
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(writer.returncode, 0, writer.stderr)
            self.assertEqual(json.loads(writer.stdout), {
                "outcome": "RECORDED",
                "task": "checkout-benchmark/checkout-17",
            })

            read_events = r'''
import json
import sys
from pathlib import Path
from sibyl_memory_client import MemoryClient

memory = MemoryClient.local(str(Path(sys.argv[1])))
events = memory.read_events(limit=1000)
types = []
for event in events:
    extra = event.get("extra", {}) if isinstance(event, dict) else {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            extra = {}
    event_type = extra.get("event_type") if isinstance(extra, dict) else None
    if event_type is not None:
        types.append(event_type)
print(json.dumps(types))
'''
            before = subprocess.run(
                [sys.executable, "-c", read_events, str(db)],
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(before.returncode, 0, before.stderr)
            before_types = json.loads(before.stdout)
            self.assertIn("benchmark_material_observed", before_types)
            self.assertNotIn("evaluation_gate_decision", before_types)

            status = run_command(["exposure", "status", "--config", str(config_path)])
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("CLEAN: checkout-16 checkout-18", status.stdout)
            self.assertIn("EXPOSED: checkout-17", status.stdout)
            self.assertIn("UNKNOWN: none", status.stdout)
            self.assertIn("STATUS: INSPECTED", status.stdout)
            self.assertIn("JOURNALED: false", status.stdout)

            status_json = run_command([
                "exposure",
                "status",
                "--config",
                str(config_path),
                "--json",
            ])
            self.assertEqual(status_json.returncode, 0, status_json.stderr)
            status_result = json.loads(status_json.stdout)
            self.assertEqual(status_result["clean_tasks"], ["checkout-16", "checkout-18"])
            self.assertEqual(status_result["exposed_tasks"], ["checkout-17"])
            self.assertEqual(status_result["unknown_tasks"], [])
            self.assertFalse(status_result["journaled"])

            after_status = subprocess.run(
                [sys.executable, "-c", read_events, str(db)],
                env=child_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(after_status.returncode, 0, after_status.stderr)
            after_types = json.loads(after_status.stdout)
            self.assertEqual(after_types, before_types)
            self.assertNotIn("evaluation_gate_decision", after_types)
            self.assertNotIn("evaluation_started", after_types)
            self.assertNotIn("evaluation_completed", after_types)

            evaluation = run_command([
                "eval",
                "run",
                "--config",
                str(config_path),
                "--policy",
                "exclude",
                "--json",
            ])
            self.assertEqual(evaluation.returncode, 0, evaluation.stderr)
            evaluation_result = json.loads(evaluation.stdout)
            self.assertEqual(evaluation_result["status"], "EXCLUDED")
            self.assertEqual(evaluation_result["selected_tasks"], ["checkout-16", "checkout-18"])
            self.assertEqual(evaluation_result["evaluated_tasks"], ["checkout-16", "checkout-18"])
            self.assertNotIn("checkout-17", evaluation_result["evaluated_tasks"])

            missing_config = root / "missing.toml"
            missing_config.write_text(
                config_path.read_text(encoding="utf-8").replace(
                    'memory_db = ".skepis/memory.db"',
                    'memory_db = ".skepis/memory-missing.db"',
                ),
                encoding="utf-8",
            )
            strict = run_command([
                "eval",
                "run",
                "--config",
                str(missing_config),
                "--policy",
                "strict",
                "--json",
            ])
            self.assertEqual(strict.returncode, 2, strict.stderr)
            strict_result = json.loads(strict.stdout)
            self.assertEqual(strict_result["status"], "BLOCKED")
            self.assertEqual(strict_result["unknown_tasks"], ["checkout-16", "checkout-17", "checkout-18"])
            self.assertEqual(strict_result["selected_tasks"], [])
            self.assertEqual(strict_result["evaluated_tasks"], [])
            self.assertFalse(strict_result["clean_claim_permitted"])

    def test_configuration_error_stops_before_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = make_initialized_project(root)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["eval", "run", "--config", str(config_path)])
            self.assertEqual(exit_code, 2)
            self.assertIn("missing benchmark id", stderr.getvalue())
            self.assertFalse((root / ".skepis" / "memory.db").exists())


if __name__ == "__main__":
    unittest.main()
