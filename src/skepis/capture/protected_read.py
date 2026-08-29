"""Read registered protected resources through an auditable boundary.

The boundary opens and reads the requested file itself. It creates the
existing objective :class:`AccessSignal` only after the read succeeds, and it
returns a receipt containing the successful read evidence. Direct reads made
through other tools remain outside this adapter's coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from .local_path import (
    AccessSignal,
    CaptureOutcome,
    CaptureResult,
    LocalPathCapture,
)


SOURCE_ADAPTER = "protected_read"


class ProtectedReadError(RuntimeError):
    """A protected read could not produce a defensible capture receipt."""

    def __init__(
        self,
        message: str,
        *,
        capture_result: CaptureResult | None = None,
    ) -> None:
        super().__init__(message)
        self.capture_result = capture_result


@dataclass(frozen=True)
class ProtectedReadReceipt:
    """Evidence that one controlled protected-resource read completed."""

    operation: str
    status: str
    requested_path: str
    normalized_path: str
    task_key: str
    bytes_read: int
    content_sha256: str
    observed_at: str
    session_id: str
    source_adapter: str
    observation_id: str
    capture_outcome: CaptureOutcome
    event_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status,
            "requested_path": self.requested_path,
            "normalized_path": self.normalized_path,
            "task_key": self.task_key,
            "bytes_read": self.bytes_read,
            "content_sha256": self.content_sha256,
            "observed_at": self.observed_at,
            "session_id": self.session_id,
            "source_adapter": self.source_adapter,
            "observation_id": self.observation_id,
            "capture_outcome": self.capture_outcome.value,
            "event_id": self.event_id,
        }


@dataclass(frozen=True)
class ProtectedReadResult:
    """The protected content and the receipt created for the read."""

    content: bytes
    receipt: ProtectedReadReceipt
    capture: CaptureResult


class ProtectedReadBoundary:
    """Allow only registered, in-root files to be read and captured."""

    def __init__(self, *, capture: LocalPathCapture, root: str | Path):
        self.capture = capture
        self.root = Path(root).expanduser().resolve(strict=False)
        detector_root = capture.detector.root.resolve(strict=False)
        if self.root != detector_root:
            raise ValueError("protected read root must match the capture detector root")

    def read(
        self,
        path: str | Path,
        *,
        session_id: str,
        observed_at: str | None = None,
    ) -> ProtectedReadResult:
        requested_path = str(path)
        session = str(session_id).strip()
        if not session:
            raise ProtectedReadError("session_id cannot be empty")
        timestamp = str(observed_at or _timestamp()).strip()
        if not timestamp:
            raise ProtectedReadError("observed_at cannot be empty")

        try:
            _, matches, normalized_path = self.capture.detector.resolve(path)
        except ValueError as exc:
            raise ProtectedReadError(f"invalid protected path: {exc}") from exc

        if len(matches) == 0:
            raise ProtectedReadError(
                f"path is not registered as protected: {requested_path}"
            )
        if len(matches) > 1:
            gap = self.capture.mark_observation_gap(
                reason="ambiguous_protected_resource_mapping",
                session_id=session,
                observed_at=timestamp,
                source_adapter=SOURCE_ADAPTER,
                path=normalized_path,
            )
            raise ProtectedReadError(
                f"protected path maps to multiple tasks: {', '.join(matches)}",
                capture_result=gap,
            )

        actual_path = (self.root / Path(normalized_path)).resolve(strict=False)
        if not _is_within(actual_path, self.root):
            raise ProtectedReadError("protected path resolves outside the project root")

        try:
            content = actual_path.read_bytes()
        except OSError as exc:
            gap = self.capture.mark_observation_gap(
                reason=f"protected_read_failed:{type(exc).__name__}",
                session_id=session,
                observed_at=timestamp,
                source_adapter=SOURCE_ADAPTER,
                path=normalized_path,
            )
            raise ProtectedReadError(
                f"protected read failed for {requested_path}: {exc}",
                capture_result=gap,
            ) from exc

        content_hash = sha256(content).hexdigest()
        observation_id = _observation_id(
            session,
            normalized_path,
            timestamp,
            content_hash,
        )
        signal = AccessSignal(
            path=normalized_path,
            observed_at=timestamp,
            session_id=session,
            source_adapter=SOURCE_ADAPTER,
            observation_id=observation_id,
            reason="controlled_protected_read",
            evidence={
                "operation": "read",
                "status": "success",
                "bytes_read": len(content),
                "content_sha256": content_hash,
            },
        )
        captured = self.capture.observe(signal)
        if captured.outcome not in {CaptureOutcome.RECORDED, CaptureOutcome.DUPLICATE}:
            raise ProtectedReadError(
                f"protected read completed but capture returned {captured.outcome.value}",
                capture_result=captured,
            )
        if captured.event_id is None:
            raise ProtectedReadError(
                "protected read completed without a persisted capture event",
                capture_result=captured,
            )

        receipt = ProtectedReadReceipt(
            operation="read",
            status="success",
            requested_path=requested_path,
            normalized_path=normalized_path,
            task_key=matches[0],
            bytes_read=len(content),
            content_sha256=content_hash,
            observed_at=timestamp,
            session_id=session,
            source_adapter=SOURCE_ADAPTER,
            observation_id=observation_id,
            capture_outcome=captured.outcome,
            event_id=str(captured.event_id),
        )
        return ProtectedReadResult(content=content, receipt=receipt, capture=captured)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _observation_id(
    session_id: str,
    normalized_path: str,
    observed_at: str,
    content_hash: str,
) -> str:
    raw = "|".join((SOURCE_ADAPTER, session_id, normalized_path, observed_at, content_hash))
    return sha256(raw.encode("utf-8")).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root
