"""Portable reports derived from a policy-gated evaluation result."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Any, Mapping


class ReportError(ValueError):
    """A report source or format could not be validated."""


REPORT_VERSION = 1
_SENSITIVE_METRIC_TOKENS = (
    "answer",
    "candidate",
    "content",
    "expected",
    "hidden",
    "output",
    "prompt",
    "secret",
    "solution",
)


def build_report(
    evaluation: Mapping[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a report without recalculating policy or copying evaluator details."""

    if not isinstance(evaluation, Mapping):
        raise ReportError("evaluation result must be a JSON object")

    benchmark = _required_text(evaluation, "benchmark")
    evaluation_subject = _required_text(evaluation, "evaluation_subject")
    run_id = _required_text(evaluation, "run_id")
    policy = _required_text(evaluation, "policy").upper()
    status = _required_text(evaluation, "status")

    requested = _task_list(evaluation, "requested_tasks")
    clean = _task_list(evaluation, "clean_tasks")
    exposed = _task_list(evaluation, "exposed_tasks")
    unknown = _task_list(evaluation, "unknown_tasks")
    selected = _task_list(evaluation, "selected_tasks")
    excluded = _task_list(evaluation, "excluded_tasks")
    flagged = _task_list(evaluation, "flagged_tasks")
    evaluated = _task_list(evaluation, "evaluated_tasks")

    raw_evaluation = evaluation.get("evaluation_result")
    nested_metrics = (
        raw_evaluation.get("metrics", {})
        if isinstance(raw_evaluation, Mapping)
        else {}
    )
    metrics = evaluation.get("metrics", nested_metrics)
    if not isinstance(metrics, Mapping):
        raise ReportError("evaluation metrics must be a JSON object")
    score = evaluation.get(
        "score",
        raw_evaluation.get("score") if isinstance(raw_evaluation, Mapping) else None,
    )
    public_score = _public_scalar(score)

    evaluation_complete = evaluation.get("evaluation_complete") is True
    journaled = evaluation.get("journaled") is True
    raw_claim = evaluation.get("clean_claim_permitted") is True
    claim_permitted = raw_claim and evaluation_complete and journaled
    reason = _optional_text(evaluation.get("reason"))
    if reason is None:
        if not evaluation_complete:
            reason = "evaluation_incomplete"
        elif not journaled:
            reason = "run_not_fully_journaled"
        elif not raw_claim:
            reason = "clean_claim_not_permitted"
        else:
            reason = "clean_claim_permitted"

    completed_at = _optional_text(evaluation.get("completed_at"))
    report_time = generated_at or completed_at or _timestamp()
    monitoring = derive_monitoring_coverage(evaluation)

    return {
        "report_version": REPORT_VERSION,
        "generated_at": report_time,
        "evaluation": {
            "run_id": run_id,
            "benchmark": benchmark,
            "evaluation_subject": evaluation_subject,
            "status": status,
            "evaluated_tasks": evaluated,
            "evaluated_count": len(evaluated),
            "score": public_score,
            "metrics": _public_metrics(metrics),
        },
        "task_eligibility": {
            "requested": requested,
            "eligible": clean,
            "exposed": exposed,
            "unknown": unknown,
            "selected": selected,
            "excluded": excluded,
            "flagged": flagged,
            "counts": {
                "requested": len(requested),
                "eligible": len(clean),
                "exposed": len(exposed),
                "unknown": len(unknown),
                "selected": len(selected),
                "excluded": len(excluded),
                "flagged": len(flagged),
            },
        },
        "policy": {"mode": policy},
        "clean_claim": {
            "permitted": claim_permitted,
            "reason": reason,
        },
        "monitoring": monitoring,
        "provenance": {
            "memory_available": evaluation.get("memory_available") is True,
            "state_available": evaluation.get("state_available") is True,
            "evaluation_complete": evaluation_complete,
            "evaluation_started_journaled": evaluation.get(
                "evaluation_started_journaled"
            ) is True,
            "gate_decision_journaled": evaluation.get("gate_decision_journaled") is True,
            "evaluation_completed_journaled": evaluation.get(
                "evaluation_completed_journaled"
            ) is True,
            "journaled": journaled,
        },
    }


def derive_monitoring_coverage(source: Mapping[str, Any]) -> dict[str, str]:
    """Describe the proven capture boundary without claiming generic coverage."""

    memory_available = source.get("memory_available") is True
    state_available = source.get("state_available") is True
    reason = _optional_text(source.get("reason")) or ""
    monitoring_status = _optional_text(source.get("monitoring_status"))
    incomplete = (
        monitoring_status == "INCOMPLETE_MONITORING"
        or reason == "incomplete_monitoring"
        or reason.startswith("monitoring_")
    )

    if not memory_available or not state_available:
        protected_reads = "UNAVAILABLE"
        sibyl_state = "UNAVAILABLE"
        overall = "UNAVAILABLE"
    elif incomplete:
        protected_reads = "INCOMPLETE_MONITORING"
        sibyl_state = "AVAILABLE"
        overall = "INCOMPLETE_MONITORING"
    else:
        protected_reads = "COMPLETE"
        sibyl_state = "AVAILABLE"
        overall = "INCOMPLETE_MONITORING"

    return {
        "status": overall,
        "protected_reads": protected_reads,
        "generic_agent_access": "INCOMPLETE_MONITORING",
        "sibyl_state": sibyl_state,
    }


def load_latest_evaluation(
    memory: Any,
    *,
    tenant_id: str,
    evaluation_subject: str,
    benchmark_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Load the newest scoped terminal evaluation event from Sibyl COLD events."""

    reader = getattr(memory, "read_events", None)
    if not callable(reader):
        raise ReportError("Sibyl event history is unavailable")
    try:
        events = reader(limit=1000)
    except Exception as exc:
        raise ReportError(f"could not read evaluation history: {type(exc).__name__}") from exc
    if not isinstance(events, list):
        raise ReportError("Sibyl event history returned an invalid result")

    scoped_runs: list[tuple[str, Mapping[str, Any], Mapping[str, Any], Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            raise ReportError("Sibyl event history contains an invalid event")
        raw_extra = event.get("extra", event)
        extra = _event_extra(raw_extra)
        event_type = extra.get("event_type")
        if event_type not in {
            "evaluation_started",
            "evaluation_completed",
            "evaluation_failed",
        }:
            continue
        if extra.get("tenant_id") != tenant_id:
            continue
        if extra.get("evaluation_subject") != evaluation_subject:
            continue
        if extra.get("benchmark") != benchmark_id:
            continue
        if run_id is not None and extra.get("run_id") != run_id:
            continue
        scoped_runs.append((str(event_type), event, extra, event.get("ts")))

    if scoped_runs:
        _, (event_type, event, extra, timestamp) = max(
            enumerate(scoped_runs),
            key=lambda item: (
                _event_timestamp(item[1][3]) is not None,
                _event_timestamp(item[1][3]) or datetime.min.replace(tzinfo=timezone.utc),
                item[1][0] != "evaluation_started",
                item[0],
            ),
        )
        if event_type == "evaluation_started":
            selected_run = extra.get("run_id")
            raise ReportError(
                f"evaluation {selected_run or run_id or 'latest'} has no completed result"
            )
        result = dict(extra)
        if timestamp is not None and "completed_at" not in result:
            result["completed_at"] = timestamp
        return result

    scope = f"{tenant_id}/{evaluation_subject}/{benchmark_id}"
    suffix = f" and run {run_id}" if run_id is not None else ""
    raise ReportError(f"no completed evaluation found for {scope}{suffix}")


def render_report(report: Mapping[str, Any], output_format: str = "text") -> str:
    """Render a portable report as terminal text, JSON, or Markdown."""

    if not isinstance(report, Mapping):
        raise ReportError("report must be a JSON object")
    normalized_format = str(output_format).strip().lower()
    if normalized_format == "json":
        return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if normalized_format == "markdown":
        return _render_markdown(report)
    if normalized_format == "text":
        return _render_text(report)
    raise ReportError("report format must be text, json, or markdown")


def _render_text(report: Mapping[str, Any]) -> str:
    evaluation = report["evaluation"]
    eligibility = report["task_eligibility"]
    counts = eligibility["counts"]
    policy = report["policy"]
    claim = report["clean_claim"]
    monitoring = report["monitoring"]
    score = evaluation["score"]
    lines = [
        "Skepis Clean Evaluation Report",
        "",
        "Evaluation",
        f"Agent: {evaluation['evaluation_subject']}",
        f"Benchmark: {evaluation['benchmark']}",
        f"Run ID: {evaluation['run_id']}",
        f"Date: {report['generated_at']}",
        "",
        "Task eligibility",
        f"Requested: {counts['requested']}",
        f"Eligible: {counts['eligible']}",
        f"Exposed: {counts['exposed']}",
        f"Unknown: {counts['unknown']}",
        f"Selected: {counts['selected']}",
        f"Evaluated: {evaluation['evaluated_count']}",
        "",
        "Clean result",
        f"Clean score: {_display_value(score)}",
        "",
        "Policy",
        f"Mode: {policy['mode']}",
        f"Clean claim permitted: {'YES' if claim['permitted'] else 'NO'}",
        f"Reason: {claim['reason']}",
        "",
        "Monitoring coverage",
        f"Protected reads: {monitoring['protected_reads']}",
        f"Generic agent access: {monitoring['generic_agent_access']}",
        f"Sibyl state: {monitoring['sibyl_state']}",
        "",
    ]
    return "\n".join(lines)


def _render_markdown(report: Mapping[str, Any]) -> str:
    evaluation = report["evaluation"]
    eligibility = report["task_eligibility"]
    counts = eligibility["counts"]
    policy = report["policy"]
    claim = report["clean_claim"]
    monitoring = report["monitoring"]
    lines = [
        "# Skepis Clean Evaluation Report",
        "",
        "## Evaluation",
        f"- Agent: {evaluation['evaluation_subject']}",
        f"- Benchmark: {evaluation['benchmark']}",
        f"- Run ID: {evaluation['run_id']}",
        f"- Date: {report['generated_at']}",
        "",
        "## Task eligibility",
        f"- Requested: {counts['requested']}",
        f"- Eligible: {counts['eligible']}",
        f"- Exposed: {counts['exposed']}",
        f"- Unknown: {counts['unknown']}",
        f"- Selected: {counts['selected']}",
        f"- Evaluated: {evaluation['evaluated_count']}",
        "",
        "## Clean result",
        f"- Clean score: {_display_value(evaluation['score'])}",
        "",
        "## Policy",
        f"- Mode: {policy['mode']}",
        f"- Clean claim permitted: {'YES' if claim['permitted'] else 'NO'}",
        f"- Reason: {claim['reason']}",
        "",
        "## Monitoring coverage",
        f"- Protected reads: {monitoring['protected_reads']}",
        f"- Generic agent access: {monitoring['generic_agent_access']}",
        f"- Sibyl state: {monitoring['sibyl_state']}",
        "",
    ]
    return "\n".join(lines)


def _required_text(source: Mapping[str, Any], key: str) -> str:
    value = _optional_text(source.get(key))
    if value is None:
        raise ReportError(f"evaluation result is missing {key}")
    return value


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or any(char in normalized for char in "\r\n\x00"):
        return None
    return normalized


def _task_list(source: Mapping[str, Any], key: str) -> list[str]:
    raw_tasks = source.get(key, [])
    if not isinstance(raw_tasks, (list, tuple)):
        raise ReportError(f"evaluation result {key} must be an array")
    tasks: list[str] = []
    for raw_task in raw_tasks:
        task = _optional_text(raw_task)
        if task is None:
            raise ReportError(f"evaluation result {key} must contain non-empty strings")
        if task in tasks:
            raise ReportError(f"evaluation result {key} contains duplicate task {task}")
        tasks.append(task)
    return tasks


def _public_scalar(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    return None


def _public_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for raw_key, value in metrics.items():
        if not isinstance(raw_key, str):
            continue
        key = raw_key.strip()
        if not key or _is_sensitive_key(key):
            continue
        safe_value = _public_scalar(value)
        if safe_value is not None:
            public[key] = safe_value
    return public


def _is_sensitive_key(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in _SENSITIVE_METRIC_TOKENS)


def _event_extra(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ReportError("Sibyl event contains invalid JSON extra data") from exc
        if isinstance(parsed, Mapping):
            return parsed
    raise ReportError("Sibyl event contains invalid extra data")


def _event_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _display_value(value: Any) -> str:
    return "not available" if value is None else str(value)


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
