"""Run the deterministic Checkpoint 12 judge proof from fresh project state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SOURCE = REPO_ROOT / "examples" / "checkout-benchmark" / "fixture.json"
EVALUATOR_SOURCE = REPO_ROOT / "examples" / "checkout-benchmark" / "evaluator.py"
TENANT_ID = "00000000-0000-0000-0000-000000000001"
BENCHMARK_ID = "checkout-benchmark"
EVALUATION_SUBJECT = "checkout-agent"
TASK_IDS = ("checkout-16", "checkout-17", "checkout-18")
PROTECTED_PATH = "evals/checkout-17/solution.patch"
OBSERVED_AT = "2026-08-29T20:00:00Z"


class DemoError(RuntimeError):
    """The repeatable Checkpoint 12 demonstration could not complete."""


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    source_root = str(REPO_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = source_root if not existing else source_root + os.pathsep + existing
    return environment


def _run_cli(
    project: Path,
    arguments: Iterable[str],
    *,
    expected_code: int = 0,
) -> tuple[dict[str, Any], int, int]:
    process = subprocess.Popen(
        [sys.executable, "-m", "skepis", *arguments],
        cwd=project,
        env=_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    process_pid = process.pid
    stdout, stderr = process.communicate()
    if process.returncode != expected_code:
        raise DemoError(
            "command failed\n"
            f"command: skepis {' '.join(arguments)}\n"
            f"expected exit code: {expected_code}\n"
            f"actual exit code: {process.returncode}\n"
            f"stdout: {stdout}\n"
            f"stderr: {stderr}"
        )
    try:
        return json.loads(stdout), process.returncode, process_pid
    except json.JSONDecodeError as exc:
        raise DemoError(
            "command did not return JSON\n"
            f"command: skepis {' '.join(arguments)}\n"
            f"stdout: {stdout}\n"
            f"stderr: {stderr}"
        ) from exc


def _run_setup_command(project: Path, config_path: Path) -> None:
    init = subprocess.run(
        [
            sys.executable,
            "-m",
            "skepis",
            "init",
            "--root",
            str(project),
            "--config",
            str(config_path),
            "--tenant-id",
            TENANT_ID,
            "--memory-db",
            ".skepis/memory.db",
            "--policy",
            "exclude",
        ],
        cwd=REPO_ROOT,
        env=_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if init.returncode != 0:
        raise DemoError(f"skepis init failed: {init.stderr}")

    register = subprocess.run(
        [
            sys.executable,
            "-m",
            "skepis",
            "benchmark",
            "register",
            "--config",
            str(config_path),
            "--id",
            BENCHMARK_ID,
            "--evaluation-subject",
            EVALUATION_SUBJECT,
            "--task",
            TASK_IDS[0],
            "--task",
            TASK_IDS[1],
            "--task",
            TASK_IDS[2],
            "--protected",
            f"checkout-17={PROTECTED_PATH}",
            "--evaluator-command",
            f"{sys.executable} evaluator.py",
        ],
        cwd=REPO_ROOT,
        env=_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if register.returncode != 0:
        raise DemoError(f"benchmark registration failed: {register.stderr}")


def _seed_clean_state(database_path: Path) -> None:
    """Create the canonical baseline through the public Sibyl entity API."""

    seed_code = """
import json
import sys
from pathlib import Path

from sibyl_memory_client import MemoryClient

database_path = Path(sys.argv[1])
memory = MemoryClient.local(str(database_path))
body = {
    "tenant_id": sys.argv[2],
    "evaluation_subject": sys.argv[3],
    "benchmark": sys.argv[4],
    "tasks": {
        task_id: {"eligibility": "UNSEEN"}
        for task_id in json.loads(sys.argv[5])
    },
}
memory.set_entity(
    "benchmark_exposure",
    f"{sys.argv[2]}/{sys.argv[3]}/{sys.argv[4]}",
    body,
    status="UNSEEN",
)
"""
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            seed_code,
            str(database_path),
            TENANT_ID,
            EVALUATION_SUBJECT,
            BENCHMARK_ID,
            json.dumps(TASK_IDS),
        ],
        cwd=REPO_ROOT,
        env=_environment(),
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise DemoError(f"Sibyl baseline write failed: {process.stderr}")


def _delete_memory(database_path: Path) -> list[str]:
    deleted: list[str] = []
    candidates = [database_path, *sorted(database_path.parent.glob(database_path.name + "-*"))]
    for candidate in candidates:
        if candidate.is_file():
            candidate.unlink()
            deleted.append(candidate.name)
    return deleted


def _record(step: str, repeat: int, **fields: Any) -> None:
    print(json.dumps({"step": step, "repeat": repeat, **fields}, sort_keys=True))


def _run_once(repeat: int) -> None:
    with tempfile.TemporaryDirectory(prefix="skepis-checkpoint12-") as temporary:
        project = Path(temporary) / "project"
        project.mkdir()
        config_path = project / "skepis.toml"
        fixture_path = project / "fixture.json"
        fixture_path.write_text(FIXTURE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        evaluator_path = project / "evaluator.py"
        evaluator_path.write_text(EVALUATOR_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        protected_path = project / PROTECTED_PATH
        protected_path.parent.mkdir(parents=True)
        protected_path.write_text("opaque protected checkout-17 material", encoding="utf-8")

        _run_setup_command(project, config_path)
        database_path = project / ".skepis" / "memory.db"
        _seed_clean_state(database_path)

        clean_start, clean_code, clean_pid = _run_cli(
            project,
            ["exposure", "status", "--config", str(config_path), "--json"],
        )
        if clean_start["clean_tasks"] != list(TASK_IDS) or clean_start["exposed_tasks"] or clean_start["unknown_tasks"]:
            raise DemoError(f"clean baseline is not clean: {clean_start}")
        _record(
            "CLEAN_START",
            repeat,
            benchmark=clean_start["benchmark"],
            clean_tasks=clean_start["clean_tasks"],
            exposed_tasks=clean_start["exposed_tasks"],
            unknown_tasks=clean_start["unknown_tasks"],
            status=clean_start["status"],
            process_pid=clean_pid,
            process_boundary="fresh skepis status subprocess",
            sibyl_write_path="MemoryClient.local(memory.db).set_entity(benchmark_exposure, scoped benchmark entity)",
        )

        session_a, session_a_code, session_a_pid = _run_cli(
            project,
            [
                "exposure",
                "read",
                "--config",
                str(config_path),
                "--path",
                PROTECTED_PATH,
                "--session-id",
                "session-a",
                "--observed-at",
                OBSERVED_AT,
                "--json",
            ],
        )
        receipt = session_a["receipt"]
        if receipt["task_key"] != f"{BENCHMARK_ID}/checkout-17" or receipt["capture_outcome"] != "RECORDED":
            raise DemoError(f"Session A did not record checkout-17: {session_a}")
        _record(
            "SESSION_A_READ",
            repeat,
            benchmark=BENCHMARK_ID,
            task=receipt["task_key"],
            capture_outcome=receipt["capture_outcome"],
            bytes_read=receipt["bytes_read"],
            content_sha256=receipt["content_sha256"],
            event_id=receipt["event_id"],
            session_id=receipt["session_id"],
            process_pid=session_a_pid,
            process_boundary="fresh skepis protected-read subprocess",
            exact_sibyl_write_path="LocalPathCapture.observe -> MemoryClient.set_entity + MemoryClient.write_event",
        )

        fresh_status, fresh_status_code, fresh_status_pid = _run_cli(
            project,
            ["exposure", "status", "--config", str(config_path), "--json"],
        )
        if fresh_status["exposed_tasks"] != ["checkout-17"] or fresh_status["unknown_tasks"]:
            raise DemoError(f"fresh Session B did not recall checkout-17 as exposed: {fresh_status}")
        _record(
            "FRESH_SESSION_B_STATUS",
            repeat,
            benchmark=fresh_status["benchmark"],
            clean_tasks=fresh_status["clean_tasks"],
            exposed_tasks=fresh_status["exposed_tasks"],
            unknown_tasks=fresh_status["unknown_tasks"],
            status=fresh_status["status"],
            process_pid=fresh_status_pid,
            process_boundary="fresh skepis status subprocess after Session A exited",
            exact_sibyl_read_path="EvaluationGate.classify -> EvaluationGate._load_tasks -> MemoryClient.get_entity",
        )

        evaluation, evaluation_code, evaluation_pid = _run_cli(
            project,
            ["eval", "run", "--config", str(config_path), "--policy", "exclude", "--json"],
        )
        expected_selected = ["checkout-16", "checkout-18"]
        if (
            evaluation["status"] != "EXCLUDED"
            or evaluation["selected_tasks"] != expected_selected
            or evaluation["excluded_tasks"] != ["checkout-17"]
            or evaluation["evaluated_tasks"] != expected_selected
            or evaluation["score"] != 1.0
            or not evaluation["clean_claim_permitted"]
        ):
            raise DemoError(f"policy evaluation proof failed: {evaluation}")
        _record(
            "POLICY_EVALUATION",
            repeat,
            benchmark=evaluation["benchmark"],
            policy=evaluation["policy"],
            selected_tasks=evaluation["selected_tasks"],
            excluded_tasks=evaluation["excluded_tasks"],
            evaluated_tasks=evaluation["evaluated_tasks"],
            scores=evaluation["evaluation_result"]["scores"],
            score=evaluation["score"],
            status=evaluation["status"],
            clean_claim_permitted=evaluation["clean_claim_permitted"],
            process_pid=evaluation_pid,
            process_boundary="fresh skepis evaluation subprocess",
            exact_policy_decision_path="EvaluationGate.evaluate -> _apply_policy",
            exact_evaluation_filter_path="CommandEvaluator -> evaluator.py -> request.task_ids",
        )

        deleted_paths = _delete_memory(database_path)
        memory_exists_after_delete = database_path.exists()
        if memory_exists_after_delete:
            raise DemoError(f"memory deletion proof did not remove {database_path}")
        deletion, deletion_code, deletion_pid = _run_cli(
            project,
            ["eval", "run", "--config", str(config_path), "--policy", "strict", "--json"],
            expected_code=2,
        )
        expected_unknown = list(TASK_IDS)
        if (
            deletion["status"] != "BLOCKED"
            or deletion["unknown_tasks"] != expected_unknown
            or deletion["selected_tasks"]
            or deletion["evaluated_tasks"]
            or deletion["clean_claim_permitted"]
        ):
            raise DemoError(f"deletion fail-closed proof failed: {deletion}")
        _record(
            "DELETION_PROOF",
            repeat,
            benchmark=deletion["benchmark"],
            deleted_paths=deleted_paths,
            memory_exists_after_delete=memory_exists_after_delete,
            policy=deletion["policy"],
            status=deletion["status"],
            unknown_tasks=deletion["unknown_tasks"],
            selected_tasks=deletion["selected_tasks"],
            evaluated_tasks=deletion["evaluated_tasks"],
            clean_claim_permitted=deletion["clean_claim_permitted"],
            reason=deletion["reason"],
            process_pid=deletion_pid,
            process_boundary="fresh skepis strict-evaluation subprocess after exact memory deletion",
        )
        _record(
            "REPEAT_PASS",
            repeat,
            benchmark=BENCHMARK_ID,
            repeatable=True,
            no_repair_required=True,
            exit_codes={
                "clean_start": clean_code,
                "session_a_read": session_a_code,
                "fresh_session_b_status": fresh_status_code,
                "policy_evaluation": evaluation_code,
                "deletion_strict_evaluation": deletion_code,
            },
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        help="run the full proof this many times from fresh temporary projects",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.repeat < 1:
        print("checkpoint12 demo error: --repeat must be at least 1", file=sys.stderr)
        return 2
    if not FIXTURE_SOURCE.is_file():
        print(f"checkpoint12 demo error: missing fixture {FIXTURE_SOURCE}", file=sys.stderr)
        return 2
    try:
        for repeat in range(1, args.repeat + 1):
            _run_once(repeat)
    except (DemoError, OSError, ValueError) as exc:
        print(f"checkpoint12 demo error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
