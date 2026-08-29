import json
import multiprocessing
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skepis.capture import (
    AccessSignal,
    CaptureOutcome,
    LocalPathCapture,
    LocalPathDetector,
    ProtectedResource,
)
from skepis.policy import DecisionStatus, EvaluationGate


class FakeMemory:
    def __init__(self, entities=None, read_error=None, write_error=None):
        self.entities = dict(entities or {})
        self.read_error = read_error
        self.write_error = write_error
        self.events = []

    def get_entity(self, category, name):
        if self.read_error is not None:
            raise self.read_error
        key = (category, name)
        if key not in self.entities:
            error = type("NotFoundError", (Exception,), {})
            raise error(name)
        return {"body": self.entities[key]}

    def set_entity(self, category, name, body, *, status=None):
        self.entities[(category, name)] = body
        return {"body": body, "status": status}

    def write_event(self, *, extra=None, **_):
        if self.write_error is not None:
            raise self.write_error
        self.events.append(extra)
        return f"event-{len(self.events)}"

    def read_events(self, *, limit=50, since=None, until=None):
        return [{"extra": event} for event in self.events[-limit:]]


class FileBackedMemory:
    """Small process-shared memory double for testing capture outcomes."""

    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get_entity(self, category, name):
        key = f"{category}:{name}"
        state = self._read()
        if key not in state:
            error = type("NotFoundError", (Exception,), {})
            raise error(name)
        return {"body": state[key]}

    def set_entity(self, category, name, body, *, status=None):
        state = self._read()
        time.sleep(0.03)
        state[f"{category}:{name}"] = body
        self.path.write_text(json.dumps(state), encoding="utf-8")
        return {"body": body, "status": status}

    def write_event(self, *, extra=None, **_):
        return f"event-{os.getpid()}"

    def read_events(self, *, limit=50, since=None, until=None):
        return []


def _capture_worker(root_text, state_text, task_id, ready, results):
    root = Path(root_text)
    memory = FileBackedMemory(state_text)
    capture = LocalPathCapture(
        memory=memory,
        detector=LocalPathDetector(
            root,
            [
                ProtectedResource(
                    "tenant-a",
                    "checkout-benchmark",
                    task_id,
                    f"evals/{task_id}/solution.patch",
                )
            ],
        ),
        tenant_id="tenant-a",
        evaluation_subject="checkout-agent",
        benchmark_id="checkout-benchmark",
    )
    ready.wait()
    result = capture.observe(
        AccessSignal(
            root / f"evals/{task_id}/solution.patch",
            f"2026-08-29T23:10:{task_id[-2:]}Z",
            f"session-{task_id}",
            observation_id=f"observation-{task_id}",
        )
    )
    results.put(result.outcome.value)


def make_gate(memory, *, tenant_id="tenant-a", evaluation_subject="checkout-agent", benchmark_id="checkout-benchmark"):
    return EvaluationGate(
        memory=memory,
        tenant_id=tenant_id,
        evaluation_subject=evaluation_subject,
        benchmark_id=benchmark_id,
    )


def make_capture(memory, root, *resources):
    return LocalPathCapture(
        memory=memory,
        detector=LocalPathDetector(root, resources),
        tenant_id="tenant-a",
        evaluation_subject="checkout-agent",
        benchmark_id="checkout-benchmark",
    )


class HardeningTests(unittest.TestCase):
    def test_ambiguous_mapping_stays_review_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            capture = make_capture(
                memory,
                root,
                ProtectedResource("tenant-a", "checkout-benchmark", "checkout-17", "evals/**/solution.patch"),
                ProtectedResource("tenant-a", "checkout-benchmark", "checkout-18", "evals/checkout-17/**"),
            )

            result = capture.observe(
                AccessSignal(root / "evals/checkout-17/solution.patch", "2026-08-29T20:30:00Z", "session-a")
            )

            self.assertEqual(result.outcome, CaptureOutcome.NEEDS_REVIEW)
            self.assertFalse(result.monitoring_complete)
            self.assertEqual(result.matches, ("checkout-benchmark/checkout-17", "checkout-benchmark/checkout-18"))
            body = memory.entities[("benchmark_exposure", capture.entity_name)]
            self.assertEqual(body["monitoring_status"], "INCOMPLETE_MONITORING")
            self.assertEqual(body["tasks"], {})
            self.assertEqual(memory.events[0]["event_type"], "observation_gap_detected")

    def test_duplicate_exposure_is_idempotent_and_journaled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            capture = make_capture(
                memory,
                root,
                ProtectedResource("tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/solution.patch"),
            )
            signal = AccessSignal(
                root / "evals/checkout-17/solution.patch",
                "2026-08-29T20:31:00Z",
                "session-a",
                observation_id="same-observation",
            )

            first = capture.observe(signal)
            second = capture.observe(signal)

            self.assertEqual(first.outcome, CaptureOutcome.RECORDED)
            self.assertEqual(second.outcome, CaptureOutcome.DUPLICATE)
            body = memory.entities[("benchmark_exposure", capture.entity_name)]
            self.assertEqual(body["tasks"]["checkout-17"]["eligibility"], "EXPOSED")
            self.assertEqual(body["tasks"]["checkout-17"]["observed_event_ids"], ["same-observation"])
            self.assertTrue(memory.events[1]["duplicate"])

    def test_sibyl_unavailable_fails_closed(self):
        memory = FakeMemory(read_error=ConnectionError("sibyl unavailable"), write_error=ConnectionError("sibyl unavailable"))

        decision = make_gate(memory).evaluate(["checkout-16"], "strict")

        self.assertFalse(decision.memory_available)
        self.assertFalse(decision.state_available)
        self.assertEqual(decision.unknown_tasks, ("checkout-16",))
        self.assertEqual(decision.selected_tasks, ())
        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)
        self.assertFalse(decision.journaled)

    def test_missing_observation_reader_fails_closed(self):
        memory = FakeMemory({
            ("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark"): {
                "tenant_id": "tenant-a",
                "evaluation_subject": "checkout-agent",
                "benchmark": "checkout-benchmark",
                "tasks": {"checkout-17": {"eligibility": "UNSEEN"}},
            }
        })
        memory.read_events = None

        decision = make_gate(memory).evaluate(["checkout-17"], "strict")

        self.assertEqual(decision.unknown_tasks, ("checkout-17",))
        self.assertEqual(decision.selected_tasks, ())
        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)
        self.assertEqual(decision.reason, "monitoring_read_unavailable")

    def test_unavailable_adapter_is_explicit_and_cannot_create_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            capture = make_capture(
                memory,
                root,
                ProtectedResource("tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/solution.patch"),
            )

            result = capture.mark_observation_gap(
                reason="codex_activity_surface_unavailable",
                session_id="session-a",
                observed_at="2026-08-29T20:32:00Z",
                source_adapter="codex_activity",
            )

            self.assertEqual(result.outcome, CaptureOutcome.INCOMPLETE_MONITORING)
            self.assertFalse(result.monitoring_complete)
            body = memory.entities[("benchmark_exposure", capture.entity_name)]
            self.assertEqual(body["monitoring_status"], "INCOMPLETE_MONITORING")
            self.assertEqual(body["tasks"], {})
            self.assertEqual(memory.events[0]["event_type"], "observation_gap_detected")
            self.assertEqual(memory.events[0]["monitoring_status"], "INCOMPLETE_MONITORING")

    def test_observation_gap_blocks_a_clean_claim(self):
        memory = FakeMemory({
            ("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark"): {
                "tenant_id": "tenant-a",
                "evaluation_subject": "checkout-agent",
                "benchmark": "checkout-benchmark",
                "tasks": {"checkout-17": {"eligibility": "UNSEEN"}}
            }
        })
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = make_capture(
                memory,
                root,
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/solution.patch"
                ),
            )
            capture.mark_observation_gap(
                reason="codex_activity_surface_unavailable",
                session_id="session-a",
                observed_at="2026-08-29T20:33:00Z",
                source_adapter="codex_activity",
            )

            decision = make_gate(memory).evaluate(["checkout-17"], "strict")

            self.assertEqual(decision.unknown_tasks, ("checkout-17",))
            self.assertEqual(decision.selected_tasks, ())
            self.assertEqual(decision.status, DecisionStatus.BLOCKED)
            self.assertFalse(decision.clean_claim_permitted)
            self.assertEqual(decision.reason, "incomplete_monitoring")

    def test_persisted_gap_event_blocks_clean_claim_when_warm_update_fails(self):
        class EventOnlyMemory(FakeMemory):
            def set_entity(self, category, name, body, *, status=None):
                raise RuntimeError("write unavailable")

            def read_events(self, *, limit=50, since=None, until=None):
                return [{"extra": event} for event in self.events]

        memory = EventOnlyMemory({
            ("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark"): {
                "tenant_id": "tenant-a",
                "evaluation_subject": "checkout-agent",
                "benchmark": "checkout-benchmark",
                "tasks": {"checkout-17": {"eligibility": "UNSEEN"}}
            }
        })
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = make_capture(
                memory,
                root,
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/solution.patch"
                ),
            )
            capture.mark_observation_gap(
                reason="codex_activity_surface_unavailable",
                session_id="session-a",
                observed_at="2026-08-29T20:34:00Z",
                source_adapter="codex_activity",
            )

            decision = make_gate(memory).evaluate(["checkout-17"], "strict")

            self.assertEqual(decision.status, DecisionStatus.BLOCKED)
            self.assertFalse(decision.clean_claim_permitted)
            self.assertEqual(decision.reason, "incomplete_monitoring")

    def test_partial_warm_cold_write_failure_blocks_clean_claim(self):
        class WarmThenColdFailureMemory(FakeMemory):
            def write_event(self, *, extra=None, **_):
                raise RuntimeError("cold write unavailable")

        memory = WarmThenColdFailureMemory()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = make_capture(
                memory,
                root,
                ProtectedResource(
                    "tenant-a",
                    "checkout-benchmark",
                    "checkout-17",
                    "evals/checkout-17/solution.patch",
                ),
            )
            result = capture.observe(
                AccessSignal(
                    root / "evals/checkout-17/solution.patch",
                    "2026-08-29T20:35:00Z",
                    "session-a",
                )
            )

            self.assertEqual(result.outcome, CaptureOutcome.INCOMPLETE_MONITORING)
            body = memory.entities[("benchmark_exposure", capture.entity_name)]
            self.assertEqual(body["tasks"]["checkout-17"]["eligibility"], "EXPOSED")
            self.assertEqual(body["monitoring_status"], "INCOMPLETE_MONITORING")

            decision = make_gate(memory).evaluate(["checkout-16"], "strict")

            self.assertEqual(decision.unknown_tasks, ("checkout-16",))
            self.assertEqual(decision.selected_tasks, ())
            self.assertEqual(decision.status, DecisionStatus.BLOCKED)
            self.assertFalse(decision.clean_claim_permitted)

    def test_concurrent_capture_preserves_both_exposures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            state_path.write_text("{}", encoding="utf-8")
            context = multiprocessing.get_context("spawn")
            ready = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_capture_worker,
                    args=(str(root), str(state_path), task_id, ready, results),
                )
                for task_id in ("checkout-17", "checkout-18")
            ]

            for process in processes:
                process.start()
            ready.set()
            for process in processes:
                process.join(10)

            self.assertTrue(all(process.exitcode == 0 for process in processes))
            self.assertEqual(
                sorted(results.get(timeout=2) for _ in processes),
                ["RECORDED", "RECORDED"],
            )
            state = json.loads(state_path.read_text(encoding="utf-8"))
            body = state["benchmark_exposure:tenant-a/checkout-agent/checkout-benchmark"]
            self.assertEqual(
                set(body["tasks"]),
                {"checkout-17", "checkout-18"},
            )
            self.assertEqual(
                {task["eligibility"] for task in body["tasks"].values()},
                {"EXPOSED"},
            )

    def test_old_persisted_gap_event_is_found_past_first_event_page(self):
        class PagedEventMemory(FakeMemory):
            def __init__(self, entities, events):
                super().__init__(entities)
                self.read_until_values = []
                self.events = events

            def read_events(self, *, limit=50, since=None, until=None):
                self.read_until_values.append(until)
                selected = [
                    event
                    for event in self.events
                    if (since is None or event["ts"] >= since)
                    and (until is None or event["ts"] <= until)
                ]
                return sorted(
                    selected,
                    key=lambda event: (event["ts"], event["id"]),
                    reverse=True,
                )[:limit]

        base = datetime(2026, 8, 29, tzinfo=timezone.utc)
        events = [
            {
                "id": f"event-{index:04d}",
                "ts": (base + timedelta(seconds=index)).isoformat().replace("+00:00", "Z"),
                "extra": {
                    "event_type": "unrelated_event",
                    "tenant_id": "tenant-a",
                    "evaluation_subject": "checkout-agent",
                    "benchmark": "other-benchmark",
                },
            }
            for index in range(1001)
        ]
        events[0]["extra"] = {
            "event_type": "observation_gap_detected",
            "tenant_id": "tenant-a",
            "evaluation_subject": "checkout-agent",
            "benchmark": "checkout-benchmark",
        }
        memory = PagedEventMemory(
            {
                ("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark"): {
                    "tenant_id": "tenant-a",
                    "evaluation_subject": "checkout-agent",
                    "benchmark": "checkout-benchmark",
                    "tasks": {"checkout-17": {"eligibility": "UNSEEN"}},
                }
            },
            events,
        )

        decision = make_gate(memory).evaluate(["checkout-17"], "strict")

        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)
        self.assertEqual(decision.reason, "incomplete_monitoring")
        self.assertEqual(len(memory.read_until_values), 2)
        self.assertIsNone(memory.read_until_values[0])
        self.assertIsNotNone(memory.read_until_values[1])

    def test_scope_delimiters_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "path separators"):
            make_gate(FakeMemory(), tenant_id="tenant/a")

    def test_mismatched_warm_scope_fails_closed(self):
        memory = FakeMemory({
            ("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark"): {
                "tenant_id": "tenant-b",
                "evaluation_subject": "checkout-agent",
                "benchmark": "checkout-benchmark",
                "tasks": {"checkout-17": {"eligibility": "UNSEEN"}},
            }
        })

        decision = make_gate(memory).evaluate(["checkout-17"], "strict")

        self.assertFalse(decision.state_available)
        self.assertEqual(decision.unknown_tasks, ("checkout-17",))
        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)
        self.assertEqual(decision.reason, "scope_mismatch:tenant_id")

    def test_cross_project_state_does_not_bleed_between_scopes(self):
        category = "benchmark_exposure"
        entities = {
            (category, "tenant-a/checkout-agent/project-a"): {
                "tenant_id": "tenant-a",
                "evaluation_subject": "checkout-agent",
                "benchmark": "project-a",
                "tasks": {"checkout-17": {"eligibility": "EXPOSED"}}
            },
            (category, "tenant-a/checkout-agent/project-b"): {
                "tenant_id": "tenant-a",
                "evaluation_subject": "checkout-agent",
                "benchmark": "project-b",
                "tasks": {"checkout-17": {"eligibility": "UNSEEN"}}
            },
            (category, "tenant-b/checkout-agent/project-a"): {
                "tenant_id": "tenant-b",
                "evaluation_subject": "checkout-agent",
                "benchmark": "project-a",
                "tasks": {"checkout-17": {"eligibility": "UNSEEN"}}
            },
        }
        memory = FakeMemory(entities)

        other_benchmark = make_gate(memory, benchmark_id="project-b").evaluate(["checkout-17"], "strict")
        other_tenant = make_gate(memory, tenant_id="tenant-b", benchmark_id="project-a").evaluate(["checkout-17"], "strict")

        for decision in (other_benchmark, other_tenant):
            self.assertEqual(decision.exposed_tasks, ())
            self.assertEqual(decision.selected_tasks, ("checkout-17",))
            self.assertEqual(decision.status, DecisionStatus.ALLOWED)
            self.assertTrue(decision.clean_claim_permitted)

    def test_exposed_task_cannot_enter_clean_or_selected_partition(self):
        memory = FakeMemory({
            ("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark"): {
                "tenant_id": "tenant-a",
                "evaluation_subject": "checkout-agent",
                "benchmark": "checkout-benchmark",
                "tasks": {"checkout-17": {"eligibility": "EXPOSED"}}
            }
        })

        decision = make_gate(memory).evaluate(["checkout-17"], "exclude")

        self.assertEqual(decision.clean_tasks, ())
        self.assertEqual(decision.exposed_tasks, ("checkout-17",))
        self.assertEqual(decision.selected_tasks, ())
        self.assertEqual(decision.excluded_tasks, ("checkout-17",))
        self.assertEqual(decision.status, DecisionStatus.EXCLUDED)

    def test_known_clean_task_is_not_falsely_excluded(self):
        memory = FakeMemory({
            ("benchmark_exposure", "tenant-a/checkout-agent/checkout-benchmark"): {
                "tenant_id": "tenant-a",
                "evaluation_subject": "checkout-agent",
                "benchmark": "checkout-benchmark",
                "tasks": {"checkout-16": {"eligibility": "UNSEEN"}}
            }
        })

        decision = make_gate(memory).evaluate(["checkout-16"], "exclude")

        self.assertEqual(decision.clean_tasks, ("checkout-16",))
        self.assertEqual(decision.exposed_tasks, ())
        self.assertEqual(decision.selected_tasks, ("checkout-16",))
        self.assertEqual(decision.excluded_tasks, ())
        self.assertEqual(decision.status, DecisionStatus.ALLOWED)
        self.assertTrue(decision.clean_claim_permitted)


if __name__ == "__main__":
    unittest.main()
