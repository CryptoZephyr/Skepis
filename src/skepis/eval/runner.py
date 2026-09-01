"""Run a configured evaluator behind the Skepis policy gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from skepis.policy import DecisionStatus, EvaluationGate, EvaluationPolicy

from .evaluator import (
    EvaluationRequest,
    EvaluationResult,
    EvaluatorCallable,
    invoke_evaluator,
)
from .fixture import run_fixture


DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_event(memory: Any, extra: Mapping[str, Any]) -> bool:
    try:
        memory.write_event(extra=dict(extra), ts=_timestamp())
    except Exception:
        return False
    return True


def run_evaluation(
    *,
    evaluator: EvaluatorCallable,
    memory: Any,
    task_ids: Iterable[str],
    policy: EvaluationPolicy | str,
    tenant_id: str = DEFAULT_TENANT_ID,
    evaluation_subject: str,
    benchmark_id: str,
    project_root: str | Path = ".",
    run_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Apply policy, run the selected tasks, and return a structured result."""

    requested_input = tuple(task_ids)
    resolved_run_id = run_id or uuid4().hex
    gate = EvaluationGate(
        memory=memory,
        tenant_id=tenant_id,
        evaluation_subject=evaluation_subject,
        benchmark_id=benchmark_id,
    )
    resolved_tenant = gate.tenant_id
    resolved_subject = gate.evaluation_subject
    resolved_benchmark = gate.benchmark_id
    resolved_policy = (
        policy.value if isinstance(policy, EvaluationPolicy) else str(policy)
    )
    started_journaled = _write_event(
        memory,
        {
            "event_type": "evaluation_started",
            "run_id": resolved_run_id,
            "tenant_id": resolved_tenant,
            "evaluation_subject": resolved_subject,
            "benchmark": resolved_benchmark,
            "policy": resolved_policy,
            "requested_tasks": [str(task_id) for task_id in requested_input],
        },
    )
    decision = gate.evaluate(requested_input, policy)
    evaluator_result: EvaluationResult | None = None
    evaluator_error: str | None = None
    evaluator_error_type: str | None = None
    evaluation_failed_journaled = False
    evaluation_complete = not decision.selected_tasks and decision.status != DecisionStatus.BLOCKED
    evaluated_tasks: list[str] = []

    if decision.selected_tasks:
        request = EvaluationRequest(
            benchmark_id=resolved_benchmark,
            evaluation_subject=resolved_subject,
            policy=decision.policy,
            task_ids=decision.selected_tasks,
            project_root=Path(project_root).expanduser().resolve(strict=False),
            run_id=resolved_run_id,
        )
        try:
            evaluator_result = invoke_evaluator(evaluator, request)
        except Exception as exc:
            evaluator_error = str(exc) or type(exc).__name__
            evaluator_error_type = type(exc).__name__
            evaluation_failed_journaled = _write_event(
                memory,
                {
                    "event_type": "evaluation_failed",
                    "run_id": resolved_run_id,
                    "tenant_id": resolved_tenant,
                    "evaluation_subject": resolved_subject,
                    "benchmark": resolved_benchmark,
                    "policy": decision.policy.value,
                    "selected_tasks": list(decision.selected_tasks),
                    "error": evaluator_error,
                },
            )
        else:
            evaluated_tasks = list(evaluator_result.evaluated_tasks)
            evaluation_complete = set(evaluated_tasks) == set(decision.selected_tasks)

    if evaluator_error is not None:
        status = "EVALUATOR_FAILED"
        reason = f"evaluator_failed:{evaluator_error_type}"
        clean_claim_permitted = False
        completed_journaled = False
    else:
        status = decision.status.value
        reason = decision.reason
        clean_claim_permitted = decision.clean_claim_permitted and evaluation_complete
        if decision.selected_tasks and not evaluation_complete:
            reason = "evaluator_did_not_evaluate_all_selected_tasks"
        completed_journaled = _write_event(
            memory,
            {
                "event_type": "evaluation_completed",
                "run_id": resolved_run_id,
                "tenant_id": resolved_tenant,
                "evaluation_subject": resolved_subject,
                "benchmark": resolved_benchmark,
                "policy": decision.policy.value,
                "status": decision.status.value,
                "evaluated_tasks": evaluated_tasks,
                "evaluation_result": (
                    evaluator_result.as_dict() if evaluator_result is not None else None
                ),
                "evaluation_complete": evaluation_complete,
                "clean_claim_permitted": clean_claim_permitted,
            },
        )

    result = {
        "run_id": resolved_run_id,
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
        "status": status,
        "memory_available": decision.memory_available,
        "state_available": decision.state_available,
        "clean_claim_permitted": clean_claim_permitted,
        "reason": reason,
        "evaluated_tasks": evaluated_tasks,
        "evaluation_result": evaluator_result.as_dict() if evaluator_result is not None else None,
        "metrics": dict(evaluator_result.metrics) if evaluator_result is not None else {},
        "score": evaluator_result.score if evaluator_result is not None else None,
        "evaluation_complete": evaluation_complete and evaluator_error is None,
        "evaluation_error": evaluator_error,
        "evaluation_started_journaled": started_journaled,
        "gate_decision_journaled": decision.journaled,
        "evaluation_completed_journaled": completed_journaled,
        "evaluation_failed_journaled": evaluation_failed_journaled,
        "journaled": started_journaled and decision.journaled and completed_journaled,
    }
    if evaluator_error is not None:
        exit_code = 1
    elif decision.status == DecisionStatus.BLOCKED:
        exit_code = 2
    elif not result["evaluation_complete"]:
        exit_code = 1
    else:
        exit_code = 0
    return result, exit_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the configured evaluator through the Skepis policy gate"
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--policy", choices=[policy.value for policy in EvaluationPolicy])
    parser.add_argument("--task", dest="task_ids", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    from skepis.cli import main as cli_main

    cli_args = ["eval", "run", "--config", str(args.config), "--json"]
    if args.policy is not None:
        cli_args.extend(["--policy", args.policy])
    for task_id in args.task_ids:
        cli_args.extend(["--task", task_id])
    return cli_main(cli_args)


if __name__ == "__main__":
    raise SystemExit(main())
