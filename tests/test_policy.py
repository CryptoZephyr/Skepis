import unittest

from skepis.policy import DecisionStatus, EvaluationGate, EvaluationPolicy


class FakeMemory:
    def __init__(self, body=None, read_error=None, write_error=None):
        self.body = body
        self.read_error = read_error
        self.write_error = write_error
        self.events = []

    def get_entity(self, _category, _name):
        if self.read_error is not None:
            raise self.read_error
        if self.body is None:
            error = type("NotFoundError", (Exception,), {})
            raise error("missing")
        return {"body": self.body}

    def write_event(self, *, extra=None, **_):
        if self.write_error is not None:
            raise self.write_error
        self.events.append(extra)
        return f"event-{len(self.events)}"

    def read_events(self, *, limit=50, since=None, until=None):
        return [{"extra": event} for event in self.events[-limit:]]


def make_gate(memory):
    return EvaluationGate(
        memory=memory,
        tenant_id="tenant-a",
        evaluation_subject="checkout-agent",
        benchmark_id="checkout-benchmark",
    )


def scoped_body(tasks):
    return {
        "tenant_id": "tenant-a",
        "evaluation_subject": "checkout-agent",
        "benchmark": "checkout-benchmark",
        "tasks": tasks,
    }


class EvaluationGateTests(unittest.TestCase):
    def test_partitions_and_excludes_exposed_tasks(self):
        memory = FakeMemory(scoped_body({
            "checkout-17": {"eligibility": "EXPOSED"},
            "checkout-18": {"eligibility": "INELIGIBLE_FOR_CLEAN_EVAL"},
        }))

        decision = make_gate(memory).evaluate(
            ["checkout-18", "checkout-16", "checkout-17"],
            EvaluationPolicy.EXCLUDE,
        )

        self.assertEqual(decision.clean_tasks, ("checkout-16",))
        self.assertEqual(decision.exposed_tasks, ("checkout-17", "checkout-18"))
        self.assertEqual(decision.unknown_tasks, ())
        self.assertEqual(decision.selected_tasks, ("checkout-16",))
        self.assertEqual(decision.excluded_tasks, ("checkout-17", "checkout-18"))
        self.assertEqual(decision.status, DecisionStatus.EXCLUDED)
        self.assertTrue(decision.clean_claim_permitted)
        self.assertTrue(decision.journaled)
        self.assertEqual(memory.events[0]["event_type"], "evaluation_gate_decision")

    def test_flag_policy_keeps_tasks_and_marks_exposed(self):
        memory = FakeMemory(scoped_body({"checkout-17": {"eligibility": "EXPOSED"}}))

        decision = make_gate(memory).evaluate(["checkout-16", "checkout-17"], "flag")

        self.assertEqual(decision.selected_tasks, ("checkout-16", "checkout-17"))
        self.assertEqual(decision.flagged_tasks, ("checkout-17",))
        self.assertEqual(decision.status, DecisionStatus.FLAGGED)
        self.assertFalse(decision.clean_claim_permitted)

    def test_strict_policy_blocks_exposed_tasks(self):
        memory = FakeMemory(scoped_body({"checkout-17": {"eligibility": "EXPOSED"}}))

        decision = make_gate(memory).evaluate(["checkout-16", "checkout-17"], "strict")

        self.assertEqual(decision.selected_tasks, ())
        self.assertEqual(decision.excluded_tasks, ("checkout-17",))
        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)

    def test_strict_policy_allows_known_clean_tasks(self):
        memory = FakeMemory(scoped_body({"checkout-17": {"eligibility": "UNSEEN"}}))

        decision = make_gate(memory).evaluate(["checkout-17", "checkout-16"], "strict")

        self.assertEqual(decision.selected_tasks, ("checkout-16", "checkout-17"))
        self.assertEqual(decision.status, DecisionStatus.ALLOWED)
        self.assertTrue(decision.clean_claim_permitted)

    def test_unknown_state_blocks_clean_claim(self):
        memory = FakeMemory(scoped_body({"checkout-17": {"eligibility": "UNRECOGNIZED"}}))

        decision = make_gate(memory).evaluate(["checkout-16", "checkout-17"], "exclude")

        self.assertEqual(decision.clean_tasks, ("checkout-16",))
        self.assertEqual(decision.unknown_tasks, ("checkout-17",))
        self.assertEqual(decision.selected_tasks, ("checkout-16",))
        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)

    def test_missing_sibyl_state_fails_closed(self):
        memory = FakeMemory()

        decision = make_gate(memory).evaluate(["checkout-16", "checkout-17"], "strict")

        self.assertTrue(decision.memory_available)
        self.assertFalse(decision.state_available)
        self.assertEqual(decision.clean_tasks, ())
        self.assertEqual(decision.unknown_tasks, ("checkout-16", "checkout-17"))
        self.assertEqual(decision.selected_tasks, ())
        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)
        self.assertTrue(decision.journaled)

    def test_memory_read_failure_fails_closed_even_if_journal_fails(self):
        memory = FakeMemory(read_error=RuntimeError("offline"), write_error=RuntimeError("offline"))

        decision = make_gate(memory).evaluate(["checkout-16"], "exclude")

        self.assertFalse(decision.memory_available)
        self.assertFalse(decision.state_available)
        self.assertEqual(decision.unknown_tasks, ("checkout-16",))
        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)
        self.assertFalse(decision.journaled)

    def test_unguarded_gate_journal_blocks_clean_evaluation(self):
        memory = FakeMemory(
            scoped_body({"checkout-17": {"eligibility": "UNSEEN"}}),
            write_error=RuntimeError("journal unavailable"),
        )

        decision = make_gate(memory).evaluate(["checkout-17"], "strict")

        self.assertEqual(decision.clean_tasks, ("checkout-17",))
        self.assertEqual(decision.selected_tasks, ())
        self.assertEqual(decision.status, DecisionStatus.BLOCKED)
        self.assertFalse(decision.clean_claim_permitted)
        self.assertFalse(decision.journaled)
        self.assertEqual(decision.reason, "decision_not_journaled")

    def test_classification_is_read_only(self):
        memory = FakeMemory(scoped_body({"checkout-17": {"eligibility": "EXPOSED"}}))

        classification = make_gate(memory).classify(["checkout-16", "checkout-17"])

        self.assertEqual(classification.clean_tasks, ("checkout-16",))
        self.assertEqual(classification.exposed_tasks, ("checkout-17",))
        self.assertEqual(classification.unknown_tasks, ())
        self.assertEqual(memory.events, [])


if __name__ == "__main__":
    unittest.main()
