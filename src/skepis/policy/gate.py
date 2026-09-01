"""Partition recalled exposure state and apply an evaluation policy.

The gate only reads the canonical WARM entity written by the capture side. It
does not run an evaluator or infer contamination from model output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
from typing import Any, Iterable, Mapping

from skepis.scope import normalize_scope_identifier


class EvaluationPolicy(str, Enum):
    EXCLUDE = "exclude"
    FLAG = "flag"
    STRICT = "strict"


class DecisionStatus(str, Enum):
    ALLOWED = "ALLOWED"
    EXCLUDED = "EXCLUDED"
    FLAGGED = "FLAGGED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class GateDecision:
    policy: EvaluationPolicy
    requested_tasks: tuple[str, ...]
    clean_tasks: tuple[str, ...]
    exposed_tasks: tuple[str, ...]
    unknown_tasks: tuple[str, ...]
    selected_tasks: tuple[str, ...]
    excluded_tasks: tuple[str, ...]
    flagged_tasks: tuple[str, ...]
    status: DecisionStatus
    memory_available: bool
    state_available: bool
    clean_claim_permitted: bool
    journaled: bool
    reason: str


@dataclass(frozen=True)
class ExposureClassification:
    """Read-only task partitions loaded from the scoped WARM entity."""

    requested_tasks: tuple[str, ...]
    clean_tasks: tuple[str, ...]
    exposed_tasks: tuple[str, ...]
    unknown_tasks: tuple[str, ...]
    memory_available: bool
    state_available: bool
    reason: str | None


class EvaluationGate:
    """Load scoped WARM state, partition tasks, and apply one policy."""

    category = "benchmark_exposure"

    def __init__(
        self,
        *,
        memory: Any,
        tenant_id: str,
        evaluation_subject: str,
        benchmark_id: str,
    ):
        self.memory = memory
        self.tenant_id = normalize_scope_identifier(tenant_id, label="tenant_id")
        self.evaluation_subject = normalize_scope_identifier(
            evaluation_subject,
            label="evaluation_subject",
        )
        self.benchmark_id = normalize_scope_identifier(benchmark_id, label="benchmark_id")

    @property
    def entity_name(self) -> str:
        return f"{self.tenant_id}/{self.evaluation_subject}/{self.benchmark_id}"

    def evaluate(
        self,
        task_ids: Iterable[str],
        policy: EvaluationPolicy | str,
        *,
        run_id: str | None = None,
    ) -> GateDecision:
        normalized_policy = self._normalize_policy(policy)
        classification = self.classify(task_ids)
        requested = classification.requested_tasks
        clean = classification.clean_tasks
        exposed = classification.exposed_tasks
        unknown = classification.unknown_tasks

        selected, excluded, flagged, status, claim_permitted, policy_reason = self._apply_policy(
            normalized_policy,
            requested,
            clean,
            exposed,
            unknown,
            classification.state_available,
        )
        reason = classification.reason or policy_reason
        journaled = self._journal(
            normalized_policy,
            requested,
            clean,
            exposed,
            unknown,
            selected,
            excluded,
            flagged,
            status,
            classification.memory_available,
            classification.state_available,
            claim_permitted,
            reason,
            run_id,
        )
        if classification.state_available and not journaled:
            selected = ()
            status = DecisionStatus.BLOCKED
            claim_permitted = False
            reason = "decision_not_journaled"

        return GateDecision(
            policy=normalized_policy,
            requested_tasks=requested,
            clean_tasks=clean,
            exposed_tasks=exposed,
            unknown_tasks=unknown,
            selected_tasks=selected,
            excluded_tasks=excluded,
            flagged_tasks=flagged,
            status=status,
            memory_available=classification.memory_available,
            state_available=classification.state_available,
            clean_claim_permitted=claim_permitted,
            journaled=journaled,
            reason=reason,
        )

    def classify(self, task_ids: Iterable[str]) -> ExposureClassification:
        """Return scoped CLEAN, EXPOSED, and UNKNOWN partitions without journaling."""

        requested = self._normalize_tasks(task_ids)
        tasks, memory_available, state_available, load_reason = self._load_tasks()

        if not state_available:
            return ExposureClassification(
                requested_tasks=requested,
                clean_tasks=(),
                exposed_tasks=(),
                unknown_tasks=requested,
                memory_available=memory_available,
                state_available=False,
                reason=load_reason,
            )

        clean_list: list[str] = []
        exposed_list: list[str] = []
        unknown_list: list[str] = []
        monitoring_incomplete = load_reason is not None
        for task_id in requested:
            partition = self._partition(tasks.get(task_id))
            if monitoring_incomplete and partition == "CLEAN":
                partition = "UNKNOWN"
            if partition == "CLEAN":
                clean_list.append(task_id)
            elif partition == "EXPOSED":
                exposed_list.append(task_id)
            else:
                unknown_list.append(task_id)
        return ExposureClassification(
            requested_tasks=requested,
            clean_tasks=tuple(clean_list),
            exposed_tasks=tuple(exposed_list),
            unknown_tasks=tuple(unknown_list),
            memory_available=memory_available,
            state_available=True,
            reason=load_reason,
        )

    def _load_tasks(self) -> tuple[Mapping[str, Any], bool, bool, str | None]:
        try:
            entity = self.memory.get_entity(self.category, self.entity_name)
        except Exception as exc:
            if self._is_not_found(exc):
                return {}, True, False, "warm_state_not_found"
            return {}, False, False, f"memory_read_failed:{type(exc).__name__}"

        body: Any = entity.get("body") if isinstance(entity, Mapping) and "body" in entity else entity
        if not isinstance(body, Mapping) or not isinstance(body.get("tasks"), Mapping):
            return {}, True, False, "invalid_warm_state"
        for field, expected in (
            ("tenant_id", self.tenant_id),
            ("evaluation_subject", self.evaluation_subject),
            ("benchmark", self.benchmark_id),
        ):
            actual = body.get(field)
            if actual != expected:
                return {}, True, False, f"scope_mismatch:{field}"
        monitoring_status = body.get("monitoring_status")
        if monitoring_status is None and isinstance(entity, Mapping):
            monitoring_status = entity.get("status")
        has_gap_records = isinstance(body.get("observation_gaps"), list) and bool(
            body.get("observation_gaps")
        )
        load_reason = (
            "incomplete_monitoring"
            if monitoring_status == "INCOMPLETE_MONITORING" or has_gap_records
            else None
        )
        if load_reason is None:
            load_reason = self._read_scoped_observation_gap()
        return body["tasks"], True, True, load_reason

    def _read_scoped_observation_gap(self) -> str | None:
        """Use COLD gap events as a fallback if the WARM marker was not saved."""

        reader = getattr(self.memory, "read_events", None)
        if not callable(reader):
            return "monitoring_read_unavailable"
        page_limit = 1000
        until: str | None = None
        oldest_seen: datetime | None = None

        while True:
            try:
                events = (
                    reader(limit=page_limit)
                    if until is None
                    else reader(limit=page_limit, until=until)
                )
            except Exception as exc:
                return f"monitoring_read_failed:{type(exc).__name__}"
            if not isinstance(events, list):
                return "monitoring_read_failed:invalid_event_result"

            page_timestamps: list[tuple[datetime, str]] = []
            for event in events:
                if not isinstance(event, Mapping):
                    return "monitoring_read_failed:invalid_event"
                extra: Any = event.get("extra", {})
                if isinstance(extra, str):
                    try:
                        extra = json.loads(extra)
                    except json.JSONDecodeError:
                        return "monitoring_read_failed:invalid_event_extra"
                if not isinstance(extra, Mapping):
                    return "monitoring_read_failed:invalid_event_extra"
                if (
                    extra.get("event_type") == "observation_gap_detected"
                    and extra.get("tenant_id") == self.tenant_id
                    and extra.get("evaluation_subject") == self.evaluation_subject
                    and extra.get("benchmark") == self.benchmark_id
                ):
                    return "incomplete_monitoring"

                if len(events) == page_limit:
                    timestamp = event.get("ts")
                    parsed = self._parse_event_timestamp(timestamp)
                    if parsed is None:
                        return "monitoring_read_failed:unpageable_event_result"
                    page_timestamps.append((parsed, timestamp))

            if len(events) < page_limit:
                return None

            oldest_moment, oldest_timestamp = min(page_timestamps, key=lambda item: item[0])
            if sum(moment == oldest_moment for moment, _ in page_timestamps) > 1:
                return "monitoring_read_failed:ambiguous_event_page"
            if oldest_seen is not None and oldest_moment >= oldest_seen:
                return "monitoring_read_failed:unpageable_event_result"
            oldest_seen = oldest_moment
            next_until = self._timestamp_before(oldest_timestamp)
            if next_until is None:
                return "monitoring_read_failed:unpageable_event_result"
            until = next_until

    @staticmethod
    def _parse_event_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _timestamp_before(cls, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if raw.endswith("Z"):
            suffix = "Z"
            timestamp_text = raw[:-1]
        elif raw.endswith("+00:00"):
            suffix = "+00:00"
            timestamp_text = raw[:-6]
        else:
            return None
        parsed = cls._parse_event_timestamp(value)
        if parsed is None:
            return None
        fraction_digits = 0
        if "." in timestamp_text:
            fraction = timestamp_text.rsplit(".", 1)[1]
            if not fraction.isdigit() or not 1 <= len(fraction) <= 6:
                return None
            fraction_digits = len(fraction)
        step = (
            timedelta(seconds=1)
            if fraction_digits == 0
            else timedelta(microseconds=10 ** (6 - fraction_digits))
        )
        before = parsed - step
        prefix = before.strftime("%Y-%m-%dT%H:%M:%S")
        if fraction_digits:
            prefix += "." + f"{before.microsecond:06d}"[:fraction_digits]
        return prefix + suffix

    @staticmethod
    def _partition(task: Any) -> str:
        if task is None:
            return "CLEAN"
        if not isinstance(task, Mapping):
            return "UNKNOWN"
        eligibility = task.get("eligibility")
        if eligibility == "UNSEEN":
            return "CLEAN"
        if eligibility in {"EXPOSED", "INELIGIBLE_FOR_CLEAN_EVAL"}:
            return "EXPOSED"
        return "UNKNOWN"

    @staticmethod
    def _normalize_policy(policy: EvaluationPolicy | str) -> EvaluationPolicy:
        if isinstance(policy, EvaluationPolicy):
            return policy
        try:
            return EvaluationPolicy(str(policy).strip().lower())
        except ValueError as exc:
            raise ValueError("policy must be exclude, flag, or strict") from exc

    @staticmethod
    def _normalize_tasks(task_ids: Iterable[str]) -> tuple[str, ...]:
        normalized: list[str] = []
        for task_id in task_ids:
            value = str(task_id).strip()
            if not value or any(char in value for char in "\r\n\x00"):
                raise ValueError("task identifiers must be non-empty and contain no control characters")
            normalized.append(value)
        return tuple(sorted(set(normalized)))

    @staticmethod
    def _apply_policy(
        policy: EvaluationPolicy,
        requested: tuple[str, ...],
        clean: tuple[str, ...],
        exposed: tuple[str, ...],
        unknown: tuple[str, ...],
        state_available: bool,
    ) -> tuple[
        tuple[str, ...],
        tuple[str, ...],
        tuple[str, ...],
        DecisionStatus,
        bool,
        str,
    ]:
        has_uncertain_state = bool(unknown) or not state_available
        if policy == EvaluationPolicy.EXCLUDE:
            status = DecisionStatus.BLOCKED if has_uncertain_state else (
                DecisionStatus.EXCLUDED if exposed else DecisionStatus.ALLOWED
            )
            return (
                clean,
                exposed,
                (),
                status,
                state_available and not unknown,
                "unknown_state_present" if has_uncertain_state else (
                    "exposed_tasks_excluded" if exposed else "all_tasks_clean"
                ),
            )

        if policy == EvaluationPolicy.FLAG:
            flagged = tuple(sorted(set(exposed + unknown)))
            return (
                requested,
                (),
                flagged,
                DecisionStatus.FLAGGED if flagged else DecisionStatus.ALLOWED,
                state_available and not exposed and not unknown,
                "tasks_flagged" if flagged else "all_tasks_clean",
            )

        blocked = bool(exposed) or has_uncertain_state
        return (
            () if blocked else clean,
            exposed,
            (),
            DecisionStatus.BLOCKED if blocked else DecisionStatus.ALLOWED,
            state_available and not blocked,
            "strict_policy_blocked" if blocked else "strict_policy_passed",
        )

    def _journal(
        self,
        policy: EvaluationPolicy,
        requested: tuple[str, ...],
        clean: tuple[str, ...],
        exposed: tuple[str, ...],
        unknown: tuple[str, ...],
        selected: tuple[str, ...],
        excluded: tuple[str, ...],
        flagged: tuple[str, ...],
        status: DecisionStatus,
        memory_available: bool,
        state_available: bool,
        clean_claim_permitted: bool,
        reason: str,
        run_id: str | None,
    ) -> bool:
        try:
            extra = {
                "event_type": "evaluation_gate_decision",
                "tenant_id": self.tenant_id,
                "evaluation_subject": self.evaluation_subject,
                "benchmark": self.benchmark_id,
                "policy": policy.value,
                "requested_tasks": list(requested),
                "clean_tasks": list(clean),
                "exposed_tasks": list(exposed),
                "unknown_tasks": list(unknown),
                "selected_tasks": list(selected),
                "excluded_tasks": list(excluded),
                "flagged_tasks": list(flagged),
                "status": status.value,
                "memory_available": memory_available,
                "state_available": state_available,
                "clean_claim_permitted": clean_claim_permitted,
                "reason": reason,
            }
            if run_id is not None:
                extra["run_id"] = run_id
            self.memory.write_event(extra=extra)
        except Exception:
            return False
        return True

    @staticmethod
    def _is_not_found(exc: Exception) -> bool:
        return type(exc).__name__ in {"NotFoundError", "KeyError"}
