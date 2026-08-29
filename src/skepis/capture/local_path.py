"""Capture objective access signals for registered protected local paths.

This module deliberately consumes an access signal from an authoritative local
observer. It does not infer exposure from model output, file names in prose, or
similarity. The Codex activity surface is kept outside this adapter until a
reliable objective signal is available.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatchcase
from hashlib import sha256
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from skepis.scope import normalize_scope_identifier


class CaptureOutcome(str, Enum):
    RECORDED = "RECORDED"
    DUPLICATE = "DUPLICATE"
    UNPROTECTED_PATH = "UNPROTECTED_PATH"
    IGNORED_NON_OBJECTIVE = "IGNORED_NON_OBJECTIVE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INCOMPLETE_MONITORING = "INCOMPLETE_MONITORING"


@dataclass(frozen=True)
class ProtectedResource:
    """A protected path pattern owned by exactly one benchmark task."""

    tenant_id: str
    benchmark_id: str
    task_id: str
    pattern: str

    @property
    def task_key(self) -> str:
        return f"{self.benchmark_id}/{self.task_id}"


@dataclass(frozen=True)
class AccessSignal:
    """An objective access observation supplied by a local adapter."""

    path: str | Path
    observed_at: str
    session_id: str
    source_adapter: str = "protected_local_path"
    observation_id: str | None = None
    objective: bool = True
    reason: str = "protected_answer_accessed"
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureResult:
    outcome: CaptureOutcome
    path: str
    task_key: str | None = None
    event_id: str | None = None
    reason: str | None = None
    matches: tuple[str, ...] = ()
    monitoring_complete: bool = True


def _root_text(root: Path | None) -> str | None:
    if root is None:
        return None
    return root.expanduser().resolve(strict=False).as_posix().rstrip("/")


def _clean_relative(value: str, *, allow_glob: bool) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.strip("/")
    if not normalized:
        raise ValueError("path cannot be empty")

    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path must not contain empty, current, or parent segments")
    if not allow_glob and any(char in normalized for char in "*?[]"):
        raise ValueError("observed paths cannot contain glob characters")
    return "/".join(parts)


def normalize_path(value: str | Path, *, root: Path | None = None, allow_glob: bool = False) -> str:
    """Return a stable project-relative POSIX locator.

    Registered patterns and observations are compared after slash
    normalization. A configured root makes absolute observations comparable to
    relative registration patterns without resolving or reading file contents.
    """

    raw = str(value).strip().replace("\\", "/")
    if not raw:
        raise ValueError("path cannot be empty")

    root_value = _root_text(root)
    if root_value is not None:
        root_fold = root_value.casefold()
        raw_fold = raw.casefold()
        if raw_fold == root_fold:
            raw = ""
        elif raw_fold.startswith(root_fold + "/"):
            raw = raw[len(root_value) + 1 :]
        elif raw.startswith("/") or (len(raw) >= 3 and raw[1:3] ==":/"):
            raise ValueError("absolute path is outside the configured project root")

    if not raw:
        raise ValueError("path cannot be the project root")
    return _clean_relative(raw, allow_glob=allow_glob)


class LocalPathDetector:
    """Resolve an observed local path to one and only one task."""

    def __init__(self, root: Path, resources: Iterable[ProtectedResource]):
        self.root = root.expanduser().resolve(strict=False)
        normalized: list[ProtectedResource] = []
        for resource in resources:
            tenant_id = normalize_scope_identifier(resource.tenant_id, label="resource tenant_id")
            benchmark_id = normalize_scope_identifier(resource.benchmark_id, label="resource benchmark_id")
            task_id = normalize_scope_identifier(resource.task_id, label="resource task_id")
            normalized.append(
                ProtectedResource(
                    tenant_id,
                    benchmark_id,
                    task_id,
                    normalize_path(resource.pattern, root=self.root, allow_glob=True),
                )
            )
        self.resources = tuple(normalized)

    def resolve(self, path: str | Path) -> tuple[str, tuple[str, ...], str]:
        normalized = normalize_path(path, root=self.root)
        matches = tuple(
            sorted(
                {
                    resource.task_key
                    for resource in self.resources
                    if fnmatchcase(normalized, resource.pattern)
                }
            )
        )
        if len(matches) == 1:
            return matches[0], matches, normalized
        if len(matches) == 0:
            return CaptureOutcome.UNPROTECTED_PATH.value, matches, normalized
        return CaptureOutcome.NEEDS_REVIEW.value, matches, normalized


class LocalPathCapture:
    """Write objective local-path exposure into Sibyl WARM and COLD state."""

    category = "benchmark_exposure"

    def __init__(
        self,
        *,
        memory: Any,
        detector: LocalPathDetector,
        tenant_id: str,
        evaluation_subject: str,
        benchmark_id: str,
    ):
        self.memory = memory
        self.detector = detector
        self.tenant_id = normalize_scope_identifier(tenant_id, label="tenant_id")
        self.evaluation_subject = normalize_scope_identifier(
            evaluation_subject,
            label="evaluation_subject",
        )
        self.benchmark_id = normalize_scope_identifier(benchmark_id, label="benchmark_id")
        for resource in detector.resources:
            if resource.tenant_id != self.tenant_id or resource.benchmark_id != self.benchmark_id:
                raise ValueError("capture resources must share the capture scope")
        self.lock_path = self.detector.root / ".skepis" / "capture.lock"

    @property
    def entity_name(self) -> str:
        return f"{self.tenant_id}/{self.evaluation_subject}/{self.benchmark_id}"

    def observe(self, signal: AccessSignal) -> CaptureResult:
        try:
            _, matches, normalized_path = self.detector.resolve(signal.path)
        except ValueError as exc:
            return self._gap_result(
                signal,
                path=str(signal.path),
                reason=f"invalid_protected_path:{type(exc).__name__}",
            )

        if not signal.objective:
            return CaptureResult(
                CaptureOutcome.IGNORED_NON_OBJECTIVE,
                normalized_path,
                reason="non_objective_signal",
            )
        if len(matches) == 0:
            return CaptureResult(
                CaptureOutcome.UNPROTECTED_PATH,
                normalized_path,
                reason="path_not_registered_as_protected",
            )
        if len(matches) > 1:
            return self._gap_result(
                signal,
                path=normalized_path,
                reason="ambiguous_task_mapping",
                matches=matches,
            )

        task_key = matches[0]
        observation_id = signal.observation_id or self._observation_id(signal, normalized_path)
        try:
            with self._capture_lock():
                existing = self._load_body()
                tasks = dict(existing.get("tasks", {}))
                task_id = task_key.rsplit("/", 1)[1]
                current = dict(tasks.get(task_id, {}))
                observed_ids = list(current.get("observed_event_ids", []))
                duplicate = observation_id in observed_ids

                if not duplicate:
                    state = current.get("eligibility", "UNSEEN")
                    if state == "UNSEEN":
                        state = "EXPOSED"
                    current.update(
                        {
                            "eligibility": state,
                            "reason": current.get("reason", signal.reason),
                            "first_observed_at": min(
                                signal.observed_at,
                                current.get("first_observed_at", signal.observed_at),
                            ),
                            "last_observed_at": max(
                                signal.observed_at,
                                current.get("last_observed_at", signal.observed_at),
                            ),
                        }
                    )
                    observed_ids.append(observation_id)
                    current["observed_event_ids"] = observed_ids
                    tasks[task_id] = current
                    existing.update(
                        {
                            "tenant_id": self.tenant_id,
                            "evaluation_subject": self.evaluation_subject,
                            "benchmark": self.benchmark_id,
                            "tasks": tasks,
                        }
                    )
                    self.memory.set_entity(self.category, self.entity_name, existing, status="EXPOSED")

                event_extra = {
                    "event_type": "benchmark_material_observed",
                    "duplicate": duplicate,
                    "observation_id": observation_id,
                    "tenant_id": self.tenant_id,
                    "evaluation_subject": self.evaluation_subject,
                    "benchmark": self.benchmark_id,
                    "task": task_key,
                    "resource": normalized_path,
                    "session_id": signal.session_id,
                    "source_adapter": signal.source_adapter,
                    "reason": signal.reason,
                }
                if signal.evidence:
                    event_extra["evidence"] = dict(signal.evidence)
                event_id = self.memory.write_event(extra=event_extra, ts=signal.observed_at)
        except Exception as exc:
            return self._gap_result(
                signal,
                path=normalized_path,
                reason=f"memory_operation_failed:{type(exc).__name__}",
                task_key=task_key,
            )

        return CaptureResult(
            CaptureOutcome.DUPLICATE if duplicate else CaptureOutcome.RECORDED,
            normalized_path,
            task_key=task_key,
            event_id=event_id,
            reason="duplicate_observation" if duplicate else signal.reason,
        )

    def mark_observation_gap(
        self,
        *,
        reason: str,
        session_id: str,
        observed_at: str,
        source_adapter: str,
        path: str | Path = "observation-gap",
    ) -> CaptureResult:
        signal = AccessSignal(
            path=path,
            observed_at=observed_at,
            session_id=session_id,
            source_adapter=source_adapter,
        )
        return self._gap_result(signal, path=str(path), reason=reason)

    def _load_body(self) -> dict[str, Any]:
        try:
            entity = self.memory.get_entity(self.category, self.entity_name)
        except Exception as exc:
            if type(exc).__name__ not in {"NotFoundError", "KeyError"}:
                raise
            return {
                "tenant_id": self.tenant_id,
                "evaluation_subject": self.evaluation_subject,
                "benchmark": self.benchmark_id,
                "tasks": {},
            }
        if isinstance(entity, Mapping) and isinstance(entity.get("body"), Mapping):
            return dict(entity["body"])
        if isinstance(entity, Mapping):
            return dict(entity)
        raise TypeError("Sibyl entity body must be a mapping")

    def _gap_result(
        self,
        signal: AccessSignal,
        *,
        path: str,
        reason: str,
        matches: tuple[str, ...] = (),
        task_key: str | None = None,
    ) -> CaptureResult:
        event_id: str | None = None
        with self._capture_lock():
            self._persist_observation_gap(
                path=path,
                reason=reason,
                session_id=signal.session_id,
                observed_at=signal.observed_at,
                source_adapter=signal.source_adapter,
            )
            try:
                event_id = self.memory.write_event(
                    extra={
                        "event_type": "observation_gap_detected",
                        "monitoring_status": "INCOMPLETE_MONITORING",
                        "tenant_id": self.tenant_id,
                        "evaluation_subject": self.evaluation_subject,
                        "benchmark": self.benchmark_id,
                        "resource": path,
                        "matches": list(matches),
                        "session_id": signal.session_id,
                        "source_adapter": signal.source_adapter,
                        "reason": reason,
                    },
                    ts=signal.observed_at,
                )
            except Exception:
                pass
        return CaptureResult(
            CaptureOutcome.NEEDS_REVIEW if reason == "ambiguous_task_mapping" else CaptureOutcome.INCOMPLETE_MONITORING,
            path,
            task_key=task_key,
            event_id=event_id,
            reason=reason,
            matches=matches,
            monitoring_complete=False,
        )

    def _persist_observation_gap(
        self,
        *,
        path: str,
        reason: str,
        session_id: str,
        observed_at: str,
        source_adapter: str,
    ) -> None:
        """Persist monitoring uncertainty without creating hard exposure."""

        try:
            existing = self._load_body()
        except Exception as exc:
            if type(exc).__name__ not in {"NotFoundError", "KeyError"}:
                return
            existing = {
                "tenant_id": self.tenant_id,
                "evaluation_subject": self.evaluation_subject,
                "benchmark": self.benchmark_id,
                "tasks": {},
            }

        if not isinstance(existing.get("tasks"), Mapping):
            existing["tasks"] = {}
        gaps = existing.get("observation_gaps", [])
        if not isinstance(gaps, list):
            gaps = []
        gap = {
            "resource": path,
            "reason": reason,
            "session_id": session_id,
            "observed_at": observed_at,
            "source_adapter": source_adapter,
        }
        if gap not in gaps:
            gaps.append(gap)
        existing.update(
            {
                "tenant_id": self.tenant_id,
                "evaluation_subject": self.evaluation_subject,
                "benchmark": self.benchmark_id,
                "monitoring_status": "INCOMPLETE_MONITORING",
                "observation_gaps": gaps,
            }
        )
        try:
            self.memory.set_entity(
                self.category,
                self.entity_name,
                existing,
                status="INCOMPLETE_MONITORING",
            )
        except Exception:
            pass

    @contextmanager
    def _capture_lock(self):
        """Serialize local read-modify-write capture operations across processes."""

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _observation_id(signal: AccessSignal, normalized_path: str) -> str:
        raw = "|".join(
            [signal.source_adapter, signal.session_id, normalized_path, signal.observed_at]
        )
        return sha256(raw.encode("utf-8")).hexdigest()
