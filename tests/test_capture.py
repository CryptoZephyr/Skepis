import tempfile
import unittest
from pathlib import Path

from skepis.capture import (
    AccessSignal,
    CaptureOutcome,
    LocalPathCapture,
    LocalPathDetector,
    ProtectedResource,
)


class FakeMemory:
    def __init__(self):
        self.entities = {}
        self.events = []

    def get_entity(self, category, name):
        key = (category, name)
        if key not in self.entities:
            error = type("NotFoundError", (Exception,), {})
            raise error(name)
        return {"body": self.entities[key]}

    def set_entity(self, category, name, body, *, status=None):
        self.entities[(category, name)] = body
        return {"body": body, "status": status}

    def write_event(self, *, extra=None, ts=None, **_):
        event_id = f"event-{len(self.events) + 1}"
        self.events.append({"id": event_id, "extra": extra, "ts": ts})
        return event_id


def make_capture(memory, root, *resources):
    detector = LocalPathDetector(root, resources)
    return LocalPathCapture(
        memory=memory,
        detector=detector,
        tenant_id="tenant-a",
        evaluation_subject="checkout-agent",
        benchmark_id="checkout-benchmark",
    )


class LocalPathCaptureTests(unittest.TestCase):
    def test_unique_mapping_writes_warm_and_cold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            capture = make_capture(
                memory,
                root,
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/solution.patch"
                ),
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-18", "evals/checkout-18/solution.patch"
                ),
            )
            result = capture.observe(
                AccessSignal(
                    root / "evals/checkout-17/solution.patch",
                    "2026-08-29T18:00:00Z",
                    "session-a",
                    observation_id="obs-17",
                )
            )

            self.assertEqual(result.outcome, CaptureOutcome.RECORDED)
            body = memory.entities[("benchmark_exposure", capture.entity_name)]
            self.assertEqual(body["tasks"]["checkout-17"]["eligibility"], "EXPOSED")
            self.assertEqual(memory.events[0]["extra"]["event_type"], "benchmark_material_observed")
            self.assertEqual(memory.events[0]["extra"]["task"], "checkout-benchmark/checkout-17")

    def test_duplicate_observation_preserves_state_and_journals_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            capture = make_capture(
                memory,
                root,
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/solution.patch"
                ),
            )
            signal = AccessSignal(
                root / "evals/checkout-17/solution.patch",
                "2026-08-29T18:00:00Z",
                "session-a",
                observation_id="same-observation",
            )
            first = capture.observe(signal)
            second = capture.observe(signal)

            self.assertEqual(first.outcome, CaptureOutcome.RECORDED)
            self.assertEqual(second.outcome, CaptureOutcome.DUPLICATE)
            self.assertEqual(len(memory.events), 2)
            self.assertTrue(memory.events[1]["extra"]["duplicate"])
            self.assertEqual(
                memory.entities[("benchmark_exposure", capture.entity_name)]["tasks"]["checkout-17"]["eligibility"],
                "EXPOSED",
            )

    def test_windows_separator_maps_to_the_same_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            detector = LocalPathDetector(
                root,
                [
                    ProtectedResource(
                        "tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/hidden/**"
                    )
                ],
            )

            task_key, matches, normalized = detector.resolve(
                str(root / "evals/checkout-17/hidden/input.txt").replace("/", "\\")
            )

            self.assertEqual(task_key, "checkout-benchmark/checkout-17")
            self.assertEqual(matches, ("checkout-benchmark/checkout-17",))
            self.assertEqual(normalized, "evals/checkout-17/hidden/input.txt")

    def test_ambiguous_mapping_is_needs_review_and_marks_gap(self):
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
                AccessSignal(
                    root / "evals/checkout-17/solution.patch",
                    "2026-08-29T18:00:00Z",
                    "session-a",
                )
            )

            self.assertEqual(result.outcome, CaptureOutcome.NEEDS_REVIEW)
            self.assertFalse(result.monitoring_complete)
            self.assertEqual(result.matches, ("checkout-benchmark/checkout-17", "checkout-benchmark/checkout-18"))
            self.assertEqual(memory.events[0]["extra"]["event_type"], "observation_gap_detected")
            body = memory.entities[("benchmark_exposure", capture.entity_name)]
            self.assertEqual(body["monitoring_status"], "INCOMPLETE_MONITORING")
            self.assertEqual(body["tasks"], {})

    def test_non_objective_signal_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            capture = make_capture(
                memory,
                root,
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/solution.patch"
                ),
            )
            result = capture.observe(
                AccessSignal(
                    root / "evals/checkout-17/solution.patch",
                    "2026-08-29T18:00:00Z",
                    "session-a",
                    objective=False,
                )
            )

            self.assertEqual(result.outcome, CaptureOutcome.IGNORED_NON_OBJECTIVE)
            self.assertEqual(memory.events, [])
            self.assertEqual(memory.entities, {})

    def test_adapter_gap_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = FakeMemory()
            capture = make_capture(
                memory,
                root,
                ProtectedResource(
                    "tenant-a", "checkout-benchmark", "checkout-17", "evals/checkout-17/solution.patch"
                ),
            )
            result = capture.mark_observation_gap(
                reason="codex_activity_surface_unavailable",
                session_id="session-a",
                observed_at="2026-08-29T18:00:00Z",
                source_adapter="codex_activity",
            )

            self.assertEqual(result.outcome, CaptureOutcome.INCOMPLETE_MONITORING)
            self.assertFalse(result.monitoring_complete)
            self.assertEqual(memory.events[0]["extra"]["monitoring_status"], "INCOMPLETE_MONITORING")


if __name__ == "__main__":
    unittest.main()
