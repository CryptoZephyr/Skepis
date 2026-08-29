"""Run one deterministic benchmark command through :class:`EvaluationGate`.

The runner is intentionally small. It proves the integration boundary with a
local fixture and exact output comparison. It does not claim to be a model
runner or an Inspect AI adapter.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from skepis.policy import DecisionStatus, EvaluationGate, EvaluationPolicy


DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_event(memory: Any, extra: Mapping[str, Any]) -> bool:
    try:
        memory.write_event(extra=dict(extra), ts=_timestamp())
    except Exception:
        return False
    return True


def _load_fixture(fixture_path: str | Path) -> dict[str, Any]:
    path = Path(fixture_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("fixture root must be an object")

    task_ids = raw.get("task_ids")
    cases = raw.get("cases")
    if not isinstance(task_ids, list) or not task_ids:
        raise ValueError("fixture task_ids must be a non-empty list")
    if not isinstance(cases, dict):
        raise ValueError("fixture cases must be an object")
    for task_id in task_ids:
        if str(task_id) not in cases:
            raise ValueError(f"fixture case missing for task {task_id}")
        case = cases[str(task_id)]
        if not isinstance(case, Mapping) or "expected" not in case or "candidate_output" not in case:
            raise ValueError(f"fixture case must include expected and candidate_output for task {task_id}")
    return raw


def _score_case(case: Mapping[str, Any]) -> bool:
    return case["candidate_output"] == case["expected"]


def run_fixture(
    fixture_path: str | Path,
    *,
    memory: Any,
    policy: EvaluationPolicy | str | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    evaluation_subject: str | None = None,
    benchmark_id: str | None = None,
    allowed_task_ids: Iterable[str],
) -> tuple[dict[str, Any], int]:
    """Run registered fixture cases and return the JSON result and exit code."""

    fixture = _load_fixture(fixture_path)
    if benchmark_id is not None and fixture.get("benchmark") != benchmark_id:
        raise ValueError(
            f"fixture benchmark {fixture.get('benchmark')!r} does not match configured benchmark {benchmark_id!r}"
        )
    if evaluation_subject is not None and fixture.get("evaluation_subject") != evaluation_subject:
        raise ValueError(
            "fixture evaluation subject "
            f"{fixture.get('evaluation_subject')!r} does not match configured subject {evaluation_subject!r}"
        )
    resolved_subject = evaluation_subject or str(fixture["evaluation_subject"])
    resolved_benchmark = benchmark_id or str(fixture["benchmark"])
    resolved_policy = policy if policy is not None else str(fixture.get("policy", "exclude"))
    requested_tasks = [str(task_id) for task_id in fixture["task_ids"]]
    if allowed_task_ids is None:
        raise ValueError("registered task allowlist is required")
    allowed = {str(task_id) for task_id in allowed_task_ids}
    unexpected = sorted(set(requested_tasks) - allowed)
    if unexpected:
        raise ValueError(
            "fixture contains task ids not registered in the project: "
            + ", ".join(unexpected)
        )
    gate = EvaluationGate(
        memory=memory,
        tenant_id=tenant_id,
        evaluation_subject=resolved_subject,
        benchmark_id=resolved_benchmark,
    )

    started_journaled = _write_event(
        memory,
        {
            "event_type": "evaluation_started",
            "tenant_id": tenant_id,
            "evaluation_subject": resolved_subject,
            "benchmark": resolved_benchmark,
            "policy": str(resolved_policy),
            "requested_tasks": sorted(set(requested_tasks)),
        },
    )
    decision = gate.evaluate(requested_tasks, resolved_policy)

    cases = fixture["cases"]
    scores: dict[str, bool] = {}
    for task_id in decision.selected_tasks:
        scores[task_id] = _score_case(cases[task_id])

    evaluated_tasks = list(decision.selected_tasks)
    score = (sum(scores.values()) / len(scores)) if scores else None
    completed_journaled = _write_event(
        memory,
        {
            "event_type": "evaluation_completed",
            "tenant_id": tenant_id,
            "evaluation_subject": resolved_subject,
            "benchmark": resolved_benchmark,
            "policy": decision.policy.value,
            "status": decision.status.value,
            "evaluated_tasks": evaluated_tasks,
            "scores": scores,
            "score": score,
            "clean_claim_permitted": decision.clean_claim_permitted,
        },
    )

    result = {
        "benchmark": resolved_benchmark,
        "evaluation_subject": resolved_subject,
        "policy": decision.policy.value,
        "requested_tasks": list(decision.requested_tasks),
        "clean_tasks": list(decision.clean_tasks),
        "exposed_tasks": list(decision.exposed_tasks),
        "unknown_tasks": list(decision.unknown_tasks),
        "selected_tasks": list(decision.selected_tasks),
        "excluded_tasks": list(decision.excluded_tasks),
        "flagged_tasks": list(decision.flagged_tasks),
        "status": decision.status.value,
        "memory_available": decision.memory_available,
        "state_available": decision.state_available,
        "clean_claim_permitted": decision.clean_claim_permitted,
        "reason": decision.reason,
        "evaluated_tasks": evaluated_tasks,
        "scores": scores,
        "score": score,
        "evaluation_started_journaled": started_journaled,
        "gate_decision_journaled": decision.journaled,
        "evaluation_completed_journaled": completed_journaled,
        "journaled": started_journaled and decision.journaled and completed_journaled,
    }
    exit_code = 2 if decision.status == DecisionStatus.BLOCKED else 0
    return result, exit_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the registered project fixture through the Skepis evaluation gate"
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--policy", choices=[policy.value for policy in EvaluationPolicy])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    from skepis.cli import main as cli_main

    cli_args = ["eval", "run", "--config", str(args.config), "--json"]
    if args.policy is not None:
        cli_args.extend(["--policy", args.policy])
    return cli_main(cli_args)


if __name__ == "__main__":
    raise SystemExit(main())
