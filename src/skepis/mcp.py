"""MCP access to the canonical Skepis evaluation workflow."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Sequence

from skepis.capture import ProtectedReadBoundary
from skepis.cli import _make_capture, _open_memory, _selected_tasks
from skepis.config import (
    DEFAULT_CONFIG_NAME,
    load_config,
    parse_policy,
    require_benchmark,
    resolve_config_path,
)
from skepis.eval import CommandEvaluator, run_evaluation
from skepis.policy import EvaluationGate
from skepis.report import (
    build_report,
    derive_monitoring_coverage,
    load_scoped_exposure_provenance,
    load_latest_evaluation,
)


def preflight(
    config_path: str | Path = DEFAULT_CONFIG_NAME,
    task_ids: Sequence[str] | None = None,
    *,
    memory: Any | None = None,
) -> dict[str, Any]:
    """Classify configured tasks without journaling or running an evaluator.

    The optional memory argument is an internal test seam. The public MCP tool
    always opens the configured local Sibyl store.
    """

    if isinstance(task_ids, (str, bytes)):
        raise ValueError("task_ids must be an array of task identifiers")

    config = load_config(resolve_config_path(config_path), require_benchmark=True)
    benchmark = require_benchmark(config)
    requested = _selected_tasks(list(task_ids or ()), benchmark.task_ids)
    memory_client = memory if memory is not None else _open_memory(config.memory_db)
    classification = EvaluationGate(
        memory=memory_client,
        tenant_id=config.tenant_id,
        evaluation_subject=benchmark.evaluation_subject,
        benchmark_id=benchmark.id,
    ).classify(requested)

    monitoring = derive_monitoring_coverage(
        {
            "memory_available": classification.memory_available,
            "state_available": classification.state_available,
            "reason": classification.reason,
            "monitoring_status": "INCOMPLETE_MONITORING",
        }
    )
    return {
        "benchmark": benchmark.id,
        "evaluation_subject": benchmark.evaluation_subject,
        "requested_tasks": list(classification.requested_tasks),
        "clean_tasks": list(classification.clean_tasks),
        "exposed_tasks": list(classification.exposed_tasks),
        "unknown_tasks": list(classification.unknown_tasks),
        "memory_available": classification.memory_available,
        "state_available": classification.state_available,
        "reason": classification.reason,
        "policy": config.default_policy.value,
        "policy_applied": False,
        "read_only": True,
        "monitoring_coverage": monitoring,
    }


def inspect(
    config_path: str | Path = DEFAULT_CONFIG_NAME,
    task_ids: Sequence[str] | None = None,
    *,
    memory: Any | None = None,
) -> dict[str, Any]:
    """Explain one preflight classification with scoped safe provenance."""

    summary = preflight(config_path, task_ids, memory=memory)
    config = load_config(resolve_config_path(config_path), require_benchmark=True)
    benchmark = require_benchmark(config)
    memory_client = memory if memory is not None else _open_memory(config.memory_db)

    if not summary["memory_available"] or not summary["state_available"]:
        provenance = {
            "status": "UNAVAILABLE",
            "reason": summary["reason"],
            "events": [],
            "observation_gaps": [],
        }
    else:
        provenance = load_scoped_exposure_provenance(
            memory_client,
            tenant_id=config.tenant_id,
            evaluation_subject=benchmark.evaluation_subject,
            benchmark_id=benchmark.id,
            task_ids=summary["requested_tasks"],
        )
        if summary["reason"] is not None:
            provenance["status"] = "INCOMPLETE_MONITORING"
            provenance["reason"] = summary["reason"]

    return {
        "status": "INSPECTED",
        "benchmark": summary["benchmark"],
        "evaluation_subject": summary["evaluation_subject"],
        "eligibility": {
            "requested_tasks": summary["requested_tasks"],
            "clean_tasks": summary["clean_tasks"],
            "exposed_tasks": summary["exposed_tasks"],
            "unknown_tasks": summary["unknown_tasks"],
            "memory_available": summary["memory_available"],
            "state_available": summary["state_available"],
            "reason": summary["reason"],
        },
        "policy": {
            "mode": summary["policy"],
            "applied": False,
        },
        "monitoring_coverage": summary["monitoring_coverage"],
        "provenance": provenance,
        "read_only": True,
    }


def run(
    config_path: str | Path = DEFAULT_CONFIG_NAME,
    task_ids: Sequence[str] | None = None,
    policy: str | None = None,
    *,
    memory: Any | None = None,
    evaluator: Any | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run the configured evaluator after the canonical policy gate.

    ``memory``, ``evaluator``, and ``run_id`` are internal test seams. The
    public MCP tool always uses the configured local Sibyl store, the
    configured evaluator command, and a fresh run identifier.
    """

    if isinstance(task_ids, (str, bytes)):
        raise ValueError("task_ids must be an array of task identifiers")

    config = load_config(resolve_config_path(config_path), require_benchmark=True)
    benchmark = require_benchmark(config)
    requested = _selected_tasks(list(task_ids or ()), benchmark.task_ids)
    resolved_policy = parse_policy(
        config.default_policy if policy is None else policy
    )

    if evaluator is None:
        if benchmark.evaluator is None:
            raise ValueError("missing evaluator command in benchmark config")
        evaluator = CommandEvaluator(
            benchmark.evaluator.command,
            project_root=config.project_root,
            working_directory=benchmark.evaluator.working_directory,
            timeout_seconds=benchmark.evaluator.timeout_seconds,
        )

    memory_client = memory if memory is not None else _open_memory(config.memory_db)
    result, exit_code = run_evaluation(
        evaluator=evaluator,
        memory=memory_client,
        task_ids=requested,
        policy=resolved_policy,
        tenant_id=config.tenant_id,
        evaluation_subject=benchmark.evaluation_subject,
        benchmark_id=benchmark.id,
        project_root=config.project_root,
        run_id=run_id,
    )
    return _safe_run_payload(result, exit_code)


def report(
    config_path: str | Path = DEFAULT_CONFIG_NAME,
    run_id: str | None = None,
    *,
    memory: Any | None = None,
) -> dict[str, Any]:
    """Retrieve the safe portable report for a scoped terminal evaluation."""

    config = load_config(resolve_config_path(config_path), require_benchmark=True)
    benchmark = require_benchmark(config)
    memory_client = memory if memory is not None else _open_memory(config.memory_db)
    source = load_latest_evaluation(
        memory_client,
        tenant_id=config.tenant_id,
        evaluation_subject=benchmark.evaluation_subject,
        benchmark_id=benchmark.id,
        run_id=run_id,
    )
    return build_report(source)


def read_protected(
    config_path: str | Path = DEFAULT_CONFIG_NAME,
    path: str | Path | None = None,
    session_id: str | None = None,
    observed_at: str | None = None,
    encoding: str = "utf-8",
    *,
    memory: Any | None = None,
) -> dict[str, Any]:
    """Read one registered protected resource through the capture boundary."""

    if path is None or not str(path).strip():
        raise ValueError("path is required")
    if session_id is None or not str(session_id).strip():
        raise ValueError("session_id is required")

    config = load_config(resolve_config_path(config_path), require_benchmark=True)
    benchmark = require_benchmark(config)
    memory_client = memory if memory is not None else _open_memory(config.memory_db)
    boundary = ProtectedReadBoundary(
        capture=_make_capture(config, benchmark, memory_client),
        root=config.project_root,
    )
    result = boundary.read(
        path,
        session_id=session_id,
        observed_at=observed_at,
    )
    try:
        content = result.content.decode(encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"protected read was captured but content cannot be decoded as {encoding!r}"
        ) from exc

    task_id = result.receipt.task_key.rsplit("/", 1)[-1]
    classification = EvaluationGate(
        memory=memory_client,
        tenant_id=config.tenant_id,
        evaluation_subject=benchmark.evaluation_subject,
        benchmark_id=benchmark.id,
    ).classify([task_id])
    monitoring = derive_monitoring_coverage(
        {
            "memory_available": classification.memory_available,
            "state_available": classification.state_available,
            "reason": classification.reason,
        }
    )
    consequence = (
        f"Skepis: {task_id} was exposed. "
        "It will not count as clean evaluation evidence."
    )
    return {
        "content": content,
        "content_encoding": encoding,
        "receipt": result.receipt.as_dict(),
        "consequence": consequence,
        "monitoring_coverage": monitoring,
        "read_only": False,
    }


def _safe_run_payload(result: dict[str, Any], exit_code: int) -> dict[str, Any]:
    """Project a runner result without exposing evaluator-owned raw payloads."""

    portable = build_report(result)
    evaluation = portable["evaluation"]
    eligibility = portable["task_eligibility"]
    provenance = portable["provenance"]
    return {
        "run_id": evaluation["run_id"],
        "benchmark": evaluation["benchmark"],
        "evaluation_subject": evaluation["evaluation_subject"],
        "policy": result["policy"],
        "policy_applied": True,
        "requested_tasks": eligibility["requested"],
        "clean_tasks": eligibility["eligible"],
        "exposed_tasks": eligibility["exposed"],
        "unknown_tasks": eligibility["unknown"],
        "selected_tasks": eligibility["selected"],
        "excluded_tasks": eligibility["excluded"],
        "flagged_tasks": eligibility["flagged"],
        "evaluated_tasks": evaluation["evaluated_tasks"],
        "status": evaluation["status"],
        "memory_available": result["memory_available"],
        "state_available": result["state_available"],
        "evaluation_complete": result["evaluation_complete"],
        "clean_claim_permitted": portable["clean_claim"]["permitted"],
        "reason": portable["clean_claim"]["reason"],
        "score": evaluation["score"],
        "metrics": evaluation["metrics"],
        "evaluation_started_journaled": provenance["evaluation_started_journaled"],
        "gate_decision_journaled": provenance["gate_decision_journaled"],
        "evaluation_completed_journaled": provenance["evaluation_completed_journaled"],
        "journaled": provenance["journaled"],
        "monitoring_coverage": portable["monitoring"],
        "exit_code": exit_code,
        "report": portable,
        "read_only": False,
    }


def create_server(default_config_path: str | Path | None = None) -> Any:
    """Create the Skepis FastMCP server."""

    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - depends on installation
        raise RuntimeError(
            "MCP support is unavailable. Install the `mcp` project dependency."
        ) from exc

    server_default_config = str(default_config_path or DEFAULT_CONFIG_NAME)
    server = FastMCP(
        "skepis",
        instructions=(
            "Skepis exposes the existing scoped Sibyl, capture, policy, evaluation, "
            "and report paths. Preflight, inspect, and report are read-only. Run "
            "journals and executes the configured evaluator after the policy gate. "
            "Read protected performs a registered local read through the controlled "
            "capture boundary. Generic agent access remains incomplete monitoring."
        ),
    )

    @server.tool(
        name="skepis_preflight",
        description=(
            "Classify configured benchmark tasks from the existing Sibyl-backed "
            "Skepis gate. This read-only tool returns CLEAN, EXPOSED, and UNKNOWN "
            "partitions. It does not run an evaluator, write state, or claim "
            "complete generic-agent monitoring."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    def skepis_preflight(
        config_path: str | None = None,
        task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return preflight(config_path or server_default_config, task_ids)

    @server.tool(
        name="skepis_inspect",
        description=(
            "Explain a Skepis preflight classification using scoped eligibility, "
            "monitoring coverage, and safe exposure provenance. Raw event payloads "
            "and protected contents are redacted. This read-only tool does not "
            "write state, run policy, read protected resources, or run an evaluator."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    def skepis_inspect(
        config_path: str | None = None,
        task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return inspect(config_path or server_default_config, task_ids)

    @server.tool(
        name="skepis_run",
        description=(
            "Run the configured evaluator through the canonical Sibyl-backed policy "
            "gate. Only policy-selected task IDs are handed to the evaluator. The "
            "response includes a safe portable report projection and never exposes "
            "raw evaluator details. Evaluator failures, unknown state, incomplete "
            "monitoring, and incomplete task coverage cannot produce a clean claim."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
        structured_output=True,
    )
    def skepis_run(
        config_path: str | None = None,
        task_ids: list[str] | None = None,
        policy: str | None = None,
    ) -> dict[str, Any]:
        return run(config_path or server_default_config, task_ids, policy)

    @server.tool(
        name="skepis_report",
        description=(
            "Retrieve the portable report for the latest or requested scoped terminal "
            "evaluation. The report is built from the canonical Sibyl journal and "
            "redacts evaluator details, extra fields, sensitive metrics, and protected "
            "contents. It does not run an evaluator or recalculate policy."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    def skepis_report(
        config_path: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        return report(config_path or server_default_config, run_id)

    @server.tool(
        name="skepis_read_protected",
        description=(
            "Read one registered protected resource through the controlled local "
            "boundary. The boundary verifies the path, reads it, and only then "
            "records objective exposure through the existing capture path. Unregistered "
            "or ambiguous paths are rejected, and the response includes the existing "
            "read receipt and monitoring coverage."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    def skepis_read_protected(
        path: str,
        session_id: str,
        config_path: str | None = None,
        observed_at: str | None = None,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        return read_protected(
            config_path or server_default_config,
            path,
            session_id,
            observed_at,
            encoding,
        )

    return server


def main(argv: list[str] | None = None) -> None:
    """Run the Skepis MCP server over stdio."""

    parser = argparse.ArgumentParser(description="Run the Skepis MCP server over stdio")
    parser.add_argument(
        "--config",
        type=Path,
        help="canonical project config used when a tool omits config_path",
    )
    args = parser.parse_args(argv)
    create_server(args.config).run(transport="stdio")


if __name__ == "__main__":
    main()
