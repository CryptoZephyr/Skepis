import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class Checkpoint12DemoTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("sibyl_memory_client"),
        "Checkpoint 12 demo requires the configured Sibyl runtime",
    )
    def test_demo_repeats_the_full_judge_proof_from_fresh_projects(self):
        repo_root = Path(__file__).parents[1]
        child_env = dict(os.environ)
        child_env["PYTHONPATH"] = str(repo_root / "src")

        process = subprocess.run(
            [
                sys.executable,
                str(repo_root / "demo" / "checkpoint12_demo.py"),
                "--repeat",
                "2",
            ],
            cwd=repo_root,
            env=child_env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(process.returncode, 0, process.stderr)
        records = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(
            [record["step"] for record in records],
            [
                "CLEAN_START",
                "SESSION_A_READ",
                "FRESH_SESSION_B_STATUS",
                "POLICY_EVALUATION",
                "DELETION_PROOF",
                "REPEAT_PASS",
                "CLEAN_START",
                "SESSION_A_READ",
                "FRESH_SESSION_B_STATUS",
                "POLICY_EVALUATION",
                "DELETION_PROOF",
                "REPEAT_PASS",
            ],
        )
        for record in records:
            self.assertEqual(record["benchmark"], "checkout-benchmark")
        self.assertEqual(records[0]["clean_tasks"], ["checkout-16", "checkout-17", "checkout-18"])
        self.assertEqual(records[2]["exposed_tasks"], ["checkout-17"])
        self.assertEqual(records[3]["selected_tasks"], ["checkout-16", "checkout-18"])
        self.assertEqual(records[3]["excluded_tasks"], ["checkout-17"])
        self.assertEqual(records[3]["score"], 1.0)
        self.assertTrue(records[3]["clean_claim_permitted"])
        self.assertEqual(records[4]["status"], "BLOCKED")
        self.assertEqual(records[4]["unknown_tasks"], ["checkout-16", "checkout-17", "checkout-18"])
        self.assertFalse(records[4]["clean_claim_permitted"])
        self.assertTrue(all(record["repeat"] in {1, 2} for record in records))


if __name__ == "__main__":
    unittest.main()
