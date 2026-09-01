"""Minimal read-only MCP access to the canonical Skepis classifier."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from skepis.cli import _open_memory, _selected_tasks
from skepis.config import (
    DEFAULT_CONFIG_NAME,
    load_config,
    require_benchmark,
    resolve_config_path,
)
from skepis.policy import EvaluationGate
from skepis.report import derive_monitoring_coverage


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


def create_server() -> Any:
    """Create the one-tool FastMCP server."""

    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - depends on installation
        raise RuntimeError(
            "MCP support is unavailable. Install the `mcp` project dependency."
        ) from exc

    server = FastMCP(
        "skepis",
        instructions=(
            "Skepis preflight is read-only. It classifies the configured task set "
            "from scoped Sibyl state and never reads protected resources, journals "
            "a decision, or runs an evaluator."
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
        config_path: str = str(DEFAULT_CONFIG_NAME),
        task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return preflight(config_path, task_ids)

    return server


def main() -> None:
    """Run the read-only Skepis MCP server over stdio."""

    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
