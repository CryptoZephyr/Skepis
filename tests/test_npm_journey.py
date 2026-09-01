import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


RUN_NPM_E2E = os.environ.get("SKEPIS_RUN_NPM_E2E") == "1"
NODE_AVAILABLE = shutil.which("node") is not None
NPM_AVAILABLE = shutil.which("npm.cmd" if os.name == "nt" else "npm") is not None


@unittest.skipUnless(
    RUN_NPM_E2E and NODE_AVAILABLE and NPM_AVAILABLE,
    "set SKEPIS_RUN_NPM_E2E=1 on a Node/npm machine to run the clean npm journey",
)
class NpmJourneyTests(unittest.TestCase):
    def test_clean_npx_journey_reaches_eval_and_fail_closed_state(self):
        repo_root = Path(__file__).parents[1]
        npm = "npm.cmd" if os.name == "nt" else "npm"
        npx_executable = "npx.cmd" if os.name == "nt" else "npx"

        with tempfile.TemporaryDirectory(prefix="skepis-npm-journey-") as tmp:
            sandbox = Path(tmp)
            package_dir = sandbox / "package"
            package_dir.mkdir()
            subprocess.run(
                [npm, "pack", "--pack-destination", str(package_dir)],
                cwd=repo_root,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            package_version = json.loads(
                (repo_root / "package.json").read_text(encoding="utf-8")
            )["version"]
            tarball = package_dir / f"skepis-{package_version}.tgz"
            npm_project = sandbox / "npm-project"
            npm_project.mkdir()
            subprocess.run(
                [npm, "init", "-y", "--prefix", str(npm_project)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    npm,
                    "install",
                    "--prefix",
                    str(npm_project),
                    "--no-audit",
                    "--no-fund",
                    str(tarball),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            project = sandbox / "project"
            project.mkdir()
            evaluator = project / "evaluate.py"
            evaluator.write_text(
                textwrap.dedent(
                    """
                    import json
                    import os

                    request = json.loads(open(os.environ["SKEPIS_EVALUATION_REQUEST"], encoding="utf-8").read())
                    scores = {task_id: True for task_id in request["task_ids"]}
                    print(json.dumps({
                        "evaluated_tasks": request["task_ids"],
                        "scores": scores,
                        "metrics": {
                            "passed": len(scores),
                            "total": len(scores),
                            "candidate_output": "RAW-EVALUATOR-CONTENT",
                        },
                        "score": 1.0,
                        "details": {"secret": "RAW-EVALUATOR-DETAIL"},
                    }))
                    """
                ),
                encoding="utf-8",
            )
            protected = project / "private" / "answers" / "refund.yaml"
            protected.parent.mkdir(parents=True)
            protected.write_text("RAW-PROTECTED-CONTENT", encoding="utf-8")

            fake_client_dir = sandbox / "client-bin"
            fake_client_dir.mkdir()
            fake_client = fake_client_dir / ("claude.cmd" if os.name == "nt" else "claude")
            if os.name == "nt":
                fake_client.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
            else:
                fake_client.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                fake_client.chmod(0o755)

            environment = dict(os.environ)
            environment["PATH"] = str(fake_client_dir) + os.pathsep + environment.get("PATH", "")
            environment["SKEPIS_NPM_CACHE"] = str(sandbox / "python-cache")

            def npx(*arguments: str, cwd: Path = repo_root) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        npx_executable,
                        "--prefix",
                        str(npm_project),
                        "--no-install",
                        "skepis",
                        *arguments,
                    ],
                    cwd=cwd,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )

            initialized = npx(
                "init",
                "--root",
                str(project),
                "--tenant-id",
                "tenant-npm-journey",
                "--benchmark-id",
                "payments-regression",
                "--evaluation-subject",
                "payments-agent",
                "--task",
                "refund-idempotency",
                "--task",
                "oauth-refresh-expiry",
                "--task",
                "ledger-replay-window",
                "--protected",
                "refund-idempotency=private/answers/refund.yaml",
                "--evaluator-command",
                "python evaluate.py",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            self.assertIn("Skepis ready.", initialized.stdout)

            connected = npx("connect", "--root", str(project), "--json")
            self.assertEqual(connected.returncode, 0, connected.stderr)
            connection = json.loads(connected.stdout)
            self.assertEqual(connection["status"], "CONNECTED")
            self.assertEqual(connection["detected"], ["Claude Code"])
            self.assertTrue(connection["connection_verified"])
            self.assertEqual(
                len(connection["configured"][0]["tools"]),
                5,
            )

            client_config = json.loads(
                (project / ".mcp.json").read_text(encoding="utf-8")
            )
            server_spec = client_config["mcpServers"]["skepis"]
            mcp_client_code = r'''
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    spec = json.loads(sys.argv[1])
    project = Path(sys.argv[2])
    environment = dict(os.environ)
    environment.update({str(key): str(value) for key, value in spec.get("env", {}).items()})
    parameters = StdioServerParameters(
        command=spec["command"],
        args=[str(value) for value in spec["args"]],
        env=environment,
        cwd=project,
    )
    with open(os.devnull, "w", encoding="utf-8") as errlog:
        async with stdio_client(parameters, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                before_read = await session.call_tool("skepis_preflight", {})
                read = await session.call_tool(
                    "skepis_read_protected",
                    {
                        "path": "private/answers/refund.yaml",
                        "session_id": "npm-journey-session",
                    },
                )
                def body(response):
                    payload = response.structuredContent
                    return payload.get("result", payload)
                print(json.dumps({
                    "tools": [tool.name for tool in listed.tools],
                    "before_read": body(before_read),
                    "read_error": read.isError,
                    "read": body(read),
                }))


asyncio.run(main())
'''
            runtime_python = Path(server_spec["command"])
            mcp_environment = dict(environment)
            mcp_read = subprocess.run(
                [runtime_python, "-c", mcp_client_code, json.dumps(server_spec), str(project)],
                cwd=project,
                env=mcp_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(mcp_read.returncode, 0, mcp_read.stderr)
            read_result = json.loads(mcp_read.stdout)
            self.assertEqual(len(read_result["tools"]), 5)
            self.assertEqual(
                read_result["before_read"]["unknown_tasks"],
                ["ledger-replay-window", "oauth-refresh-expiry", "refund-idempotency"],
            )
            self.assertFalse(read_result["read_error"])
            self.assertEqual(read_result["read"]["content"], "RAW-PROTECTED-CONTENT")
            self.assertIn(
                "will not count as clean evaluation evidence",
                read_result["read"]["consequence"],
            )
            self.assertEqual(
                read_result["read"]["receipt"]["task_key"],
                "payments-regression/refund-idempotency",
            )

            evaluated = npx("eval", "--config", "skepis.toml", cwd=project)
            self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
            self.assertIn("Skepis Evaluation", evaluated.stdout)
            self.assertIn("Clean claim: permitted", evaluated.stdout)
            self.assertIn("1 exposed tasks excluded", evaluated.stdout)
            self.assertNotIn("RAW-EVALUATOR", evaluated.stdout)

            report = npx("report", "--config", "skepis.toml", "--json", cwd=project)
            self.assertEqual(report.returncode, 0, report.stderr)
            report_body = json.loads(report.stdout)
            self.assertEqual(
                report_body["task_eligibility"]["excluded"],
                ["refund-idempotency"],
            )
            self.assertEqual(report_body["evaluation"]["evaluated_count"], 2)
            self.assertTrue(report_body["clean_claim"]["permitted"])
            self.assertEqual(
                report_body["monitoring"]["generic_agent_access"],
                "INCOMPLETE_MONITORING",
            )
            self.assertNotIn("RAW-PROTECTED-CONTENT", report.stdout)
            self.assertNotIn("RAW-EVALUATOR", report.stdout)

            inspected = npx("inspect", "--config", "skepis.toml", cwd=project)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertIn("refund-idempotency", inspected.stdout)
            self.assertIn("EXPOSED", inspected.stdout)
            self.assertNotIn("RAW-PROTECTED-CONTENT", inspected.stdout)

            memory_db = project / ".skepis" / "memory.db"
            for candidate in (memory_db, Path(f"{memory_db}-wal"), Path(f"{memory_db}-shm")):
                candidate.unlink(missing_ok=True)
            strict = npx(
                "eval",
                "--config",
                "skepis.toml",
                "--policy",
                "strict",
                "--json",
                cwd=project,
            )
            self.assertEqual(strict.returncode, 2, strict.stderr)
            strict_body = json.loads(strict.stdout)
            self.assertEqual(strict_body["status"], "BLOCKED")
            self.assertEqual(
                strict_body["unknown_tasks"],
                ["ledger-replay-window", "oauth-refresh-expiry", "refund-idempotency"],
            )
            self.assertFalse(strict_body["clean_claim_permitted"])


if __name__ == "__main__":
    unittest.main()
