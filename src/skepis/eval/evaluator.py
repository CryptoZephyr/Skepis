"""Adapters for developer-supplied evaluation commands."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Protocol, Sequence

from skepis.policy import EvaluationPolicy


class EvaluatorError(RuntimeError):
    """A configured evaluator could not return a valid evaluation result."""


@dataclass(frozen=True)
class EvaluationRequest:
    """The policy-approved task set handed to an evaluator."""

    benchmark_id: str
    evaluation_subject: str
    policy: EvaluationPolicy
    task_ids: tuple[str, ...]
    project_root: Path
    run_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_version": 1,
            "run_id": self.run_id,
            "benchmark_id": self.benchmark_id,
            "evaluation_subject": self.evaluation_subject,
            "policy": self.policy.value,
            "task_ids": list(self.task_ids),
        }


@dataclass(frozen=True)
class EvaluationResult:
    """Structured output returned by an evaluator adapter."""

    evaluated_tasks: tuple[str, ...]
    metrics: dict[str, Any] = field(default_factory=dict)
    score: Any = None
    details: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        task_ids: list[str] = []
        if not isinstance(self.evaluated_tasks, (list, tuple)):
            raise EvaluatorError("evaluator evaluated_tasks must be an array")
        for raw_task_id in self.evaluated_tasks:
            if not isinstance(raw_task_id, str) or not raw_task_id.strip():
                raise EvaluatorError("evaluator evaluated_tasks must contain non-empty strings")
            task_id = raw_task_id.strip()
            if task_id in task_ids:
                raise EvaluatorError(f"evaluator returned duplicate task id: {task_id}")
            task_ids.append(task_id)
        if not isinstance(self.metrics, Mapping):
            raise EvaluatorError("evaluator metrics must be a JSON object")
        if not isinstance(self.details, Mapping):
            raise EvaluatorError("evaluator details must be a JSON object")
        if not isinstance(self.extra, Mapping):
            raise EvaluatorError("evaluator extra data must be a JSON object")
        object.__setattr__(self, "evaluated_tasks", tuple(task_ids))
        object.__setattr__(self, "metrics", dict(self.metrics))
        object.__setattr__(self, "details", dict(self.details))
        object.__setattr__(self, "extra", dict(self.extra))

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EvaluationResult":
        if not isinstance(payload, Mapping):
            raise EvaluatorError("evaluator output must be a JSON object")
        raw_tasks = payload.get("evaluated_tasks")
        if not isinstance(raw_tasks, list):
            raise EvaluatorError("evaluator output must include an evaluated_tasks array")

        raw_metrics = payload.get("metrics", {})
        if not isinstance(raw_metrics, Mapping):
            raise EvaluatorError("evaluator metrics must be a JSON object")
        raw_details = payload.get("details", {})
        if not isinstance(raw_details, Mapping):
            raise EvaluatorError("evaluator details must be a JSON object")

        return cls(
            evaluated_tasks=raw_tasks,
            metrics=dict(raw_metrics),
            score=payload.get("score"),
            details=dict(raw_details),
            extra=dict(payload),
        )

    def as_dict(self) -> dict[str, Any]:
        result = dict(self.extra)
        result["evaluated_tasks"] = list(self.evaluated_tasks)
        result["metrics"] = dict(self.metrics)
        if "score" in result or self.score is not None:
            result["score"] = self.score
        if "details" in result or self.details:
            result["details"] = dict(self.details)
        return result


class Evaluator(Protocol):
    """Narrow evaluator seam used after policy selection."""

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult | Mapping[str, Any]:
        """Execute the selected task IDs and return structured results."""


class CommandEvaluator:
    """Run a developer command using the selected task IDs as its input."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        project_root: str | Path,
        working_directory: str | Path | None = None,
        timeout_seconds: float = 300.0,
    ) -> None:
        if isinstance(command, str) or not command:
            raise ValueError("evaluator command must be a non-empty sequence")
        normalized: list[str] = []
        for index, value in enumerate(command):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"evaluator command argument {index} must be a non-empty string")
            if any(char in value for char in "\r\n\x00"):
                raise ValueError(f"evaluator command argument {index} contains control characters")
            normalized.append(value)
        self.command = tuple(normalized)
        self.project_root = Path(project_root).expanduser().resolve(strict=False)
        self.working_directory = (
            Path(working_directory).expanduser().resolve(strict=False)
            if working_directory is not None
            else self.project_root
        )
        if not _is_within_or_equal(self.working_directory, self.project_root):
            raise ValueError("evaluator working directory must be inside the project root")
        if not self.working_directory.is_dir():
            raise ValueError(f"evaluator working directory does not exist: {self.working_directory}")
        if isinstance(timeout_seconds, bool):
            raise ValueError("evaluator timeout_seconds must be positive")
        try:
            normalized_timeout = float(timeout_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError("evaluator timeout_seconds must be positive") from exc
        if not math.isfinite(normalized_timeout) or normalized_timeout <= 0:
            raise ValueError("evaluator timeout_seconds must be positive")
        self.timeout_seconds = normalized_timeout

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        if request.project_root.resolve(strict=False) != self.project_root:
            raise EvaluatorError("evaluator request project root does not match its configured root")

        request_directory = self.project_root / ".skepis" / "evaluation-requests"
        request_directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="run-", dir=request_directory) as temporary:
            request_file = Path(temporary) / "request.json"
            request_file.write_text(
                json.dumps(request.as_dict(), sort_keys=True),
                encoding="utf-8",
            )
            command = self._render_command(request, request_file)
            environment = dict(os.environ)
            environment.update(
                {
                    "SKEPIS_EVALUATION_REQUEST": str(request_file),
                    "SKEPIS_TASK_IDS": json.dumps(list(request.task_ids), separators=(",", ":")),
                    "SKEPIS_BENCHMARK_ID": request.benchmark_id,
                    "SKEPIS_EVALUATION_SUBJECT": request.evaluation_subject,
                    "SKEPIS_POLICY": request.policy.value,
                    "SKEPIS_RUN_ID": request.run_id,
                    "SKEPIS_PROJECT_ROOT": str(self.project_root),
                }
            )
            try:
                process = subprocess.run(
                    command,
                    cwd=self.working_directory,
                    env=environment,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise EvaluatorError(f"evaluator command could not start: {exc}") from exc
            except OSError as exc:
                raise EvaluatorError(f"evaluator command could not start: {exc}") from exc
            except subprocess.TimeoutExpired as exc:
                raise EvaluatorError(
                    f"evaluator command timed out after {self.timeout_seconds:g} seconds"
                ) from exc

            if process.returncode != 0:
                detail = (process.stderr or process.stdout).strip()
                if len(detail) > 4000:
                    detail = detail[-4000:]
                suffix = f": {detail}" if detail else ""
                raise EvaluatorError(
                    f"evaluator command exited with code {process.returncode}{suffix}"
                )

            output = process.stdout.strip()
            if not output:
                raise EvaluatorError("evaluator command returned no JSON result on stdout")
            try:
                payload = json.loads(output)
            except json.JSONDecodeError as exc:
                raise EvaluatorError("evaluator command must return one JSON object on stdout") from exc
            if not isinstance(payload, Mapping):
                raise EvaluatorError("evaluator command must return a JSON object")
            result = EvaluationResult.from_payload(payload)
            self._validate_result(result, request)
            return result

    def _render_command(self, request: EvaluationRequest, request_file: Path) -> list[str]:
        replacements = {
            "{request_file}": str(request_file),
            "{tasks_file}": str(request_file),
            "{benchmark_id}": request.benchmark_id,
            "{evaluation_subject}": request.evaluation_subject,
            "{policy}": request.policy.value,
            "{run_id}": request.run_id,
        }
        rendered: list[str] = []
        for argument in self.command:
            value = argument
            for token, replacement in replacements.items():
                value = value.replace(token, replacement)
            rendered.append(value)
        return rendered

    @staticmethod
    def _validate_result(result: EvaluationResult, request: EvaluationRequest) -> None:
        selected = set(request.task_ids)
        unauthorized = sorted(set(result.evaluated_tasks) - selected)
        if unauthorized:
            raise EvaluatorError(
                "evaluator returned tasks outside policy-selected task set: "
                + ", ".join(unauthorized)
            )


EvaluatorCallable = Evaluator | Callable[[EvaluationRequest], EvaluationResult | Mapping[str, Any]]


def invoke_evaluator(evaluator: EvaluatorCallable, request: EvaluationRequest) -> EvaluationResult:
    """Invoke a protocol adapter or a callable and normalize its result."""

    method = getattr(evaluator, "evaluate", None)
    if callable(method):
        raw_result = method(request)
    elif callable(evaluator):
        raw_result = evaluator(request)
    else:
        raise EvaluatorError("evaluator must provide evaluate(request)")
    if isinstance(raw_result, EvaluationResult):
        CommandEvaluator._validate_result(raw_result, request)
        return raw_result
    if isinstance(raw_result, Mapping):
        result = EvaluationResult.from_payload(raw_result)
        CommandEvaluator._validate_result(result, request)
        return result
    raise EvaluatorError("evaluator must return EvaluationResult or a JSON object")


def _is_within_or_equal(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
