import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TENANT_ID = "00000000-0000-0000-0000-000000000001"


class EndToEndProofTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("sibyl_memory_client"),
        "fresh-process proof requires the configured Sibyl runtime",
    )
    def test_exposure_changes_fresh_session_task_selection(self):
        fixture_path = Path(__file__).parents[1] / "examples" / "checkout-benchmark" / "fixture.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        source_root = fixture_path.parents[2] / "src"
        child_env = dict(os.environ)
        child_env["PYTHONPATH"] = str(source_root)

        with tempfile.TemporaryDirectory(prefix="skepis-e2e-proof-") as tmp:
            base = Path(tmp)
            db = base / "memory.db"
            project = base / "project"
            protected = project / "evals/checkout-17/solution.patch"
            protected.parent.mkdir(parents=True)
            protected.write_text("opaque fixture", encoding="utf-8")

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
        "2026-08-29T19:00:00Z",
        "session-a",
        observation_id="checkout-17-exposure",
    )
)
print(json.dumps({"outcome": result.outcome.value, "task": result.task_key}))
'''
            writer_process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    writer,
                    str(db),
                    str(project),
                    str(protected),
                    str(fixture_path),
                ],
                env=child_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            writer_stdout, writer_stderr = writer_process.communicate()
            self.assertEqual(writer_process.returncode, 0, writer_stderr)
            writer_result = json.loads(writer_stdout)
            self.assertEqual(writer_result, {
                "outcome": "RECORDED",
                "task": "checkout-benchmark/checkout-17",
            })

            reader = r'''
import json
import sys
from pathlib import Path
from sibyl_memory_client import MemoryClient
from skepis.policy import EvaluationGate

db = Path(sys.argv[1])
fixture = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
memory = MemoryClient.local(str(db))
gate = EvaluationGate(
    memory=memory,
    tenant_id="00000000-0000-0000-0000-000000000001",
    evaluation_subject=fixture["evaluation_subject"],
    benchmark_id=fixture["benchmark"],
)
decision = gate.evaluate(fixture["task_ids"], fixture["policy"])
print(json.dumps({
    "requested": list(decision.requested_tasks),
    "clean": list(decision.clean_tasks),
    "exposed": list(decision.exposed_tasks),
    "unknown": list(decision.unknown_tasks),
    "selected": list(decision.selected_tasks),
    "excluded": list(decision.excluded_tasks),
    "status": decision.status.value,
    "clean_claim_permitted": decision.clean_claim_permitted,
    "journaled": decision.journaled,
}))
'''
            reader_process = subprocess.Popen(
                [sys.executable, "-c", reader, str(db), str(fixture_path)],
                env=child_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            reader_stdout, reader_stderr = reader_process.communicate()
            self.assertEqual(reader_process.returncode, 0, reader_stderr)
            reader_result = json.loads(reader_stdout)

            self.assertEqual(reader_result, {
                "requested": ["checkout-16", "checkout-17", "checkout-18"],
                "clean": ["checkout-16", "checkout-18"],
                "exposed": ["checkout-17"],
                "unknown": [],
                "selected": ["checkout-16", "checkout-18"],
                "excluded": ["checkout-17"],
                "status": "EXCLUDED",
                "clean_claim_permitted": True,
                "journaled": True,
            })
            self.assertEqual(writer_process.poll(), 0)
            self.assertEqual(reader_process.poll(), 0)


if __name__ == "__main__":
    unittest.main()
