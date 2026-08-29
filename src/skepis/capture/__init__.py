"""Objective exposure capture adapters."""

from .local_path import (
    AccessSignal,
    CaptureOutcome,
    CaptureResult,
    LocalPathCapture,
    LocalPathDetector,
    ProtectedResource,
)
from .protected_read import (
    ProtectedReadBoundary,
    ProtectedReadError,
    ProtectedReadReceipt,
    ProtectedReadResult,
)

__all__ = [
    "AccessSignal",
    "CaptureOutcome",
    "CaptureResult",
    "LocalPathCapture",
    "LocalPathDetector",
    "ProtectedResource",
    "ProtectedReadBoundary",
    "ProtectedReadError",
    "ProtectedReadReceipt",
    "ProtectedReadResult",
]
