import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from skepis.cli import main
from skepis.eval import run_evaluation
from skepis.report import build_report, load_latest_evaluation, render_report


def evaluation_result(**overrides):
    result = {
        "run_id": "run-payments-001",
        "benchmark": "payments-regression",
        "evaluation_subject": "payments-agent",
        "policy": "exclude",
        "requested_tasks": [
            "refund-idempotency",
            "oauth-refresh-expiry",
            "inventory-race-condition",
        ],
        "clean_tasks": ["inventory-race-condition", "refund-idempotency"],
        "exposed_tasks": ["oauth-refresh-expiry"],
        "unknown_tasks": [],
        "selected_tasks": ["inventory-race-condition", "refund-idempotency"],
        "excluded_tasks": ["oauth-refresh-expiry"],
        "flagged_tasks": [],
        "status": "EXCLUDED",
        "memory_available": True,
        "state_available": True,
        "clean_claim_permitted": True,
        "reason": "exposed_tasks_excluded",
        "evaluated_tasks": ["inventory-race-condition", "refund-idempotency"],
        "evaluation_result": {
            "evaluated_tasks": ["inventory-race-condition", "refund-idempotency"],
            "metrics": {
                "received_count": 2,
                "scores": {"inventory-race-condition": 1.0},
                "candidate_output": "hidden answer must not be copied",
            },
            "score": 0.5,
            "details": {"hidden_answer": "hidden answer must not be copied"},
            "extra": {"secret": "hidden answer must not be copied"},
        },
        "metrics": {
            "received_count": 2,
            "scores": {"inventory-race-condition": 1.0},
            "candidate_output": "hidden answer must not be copied",
        },
        "score": 0.5,
        "evaluation_complete": True,
        "evaluation_error": None,
        "evaluation_started_journaled": True,
        "gate_decision_journaled": True,
        "evaluation_completed_journaled": True,
        "journaled": True,
    }
    result.update(overrides)
    return result


class ReportTests(unittest.TestCase):
    def test_build_report_uses_gate_partitions_and_omits_raw_evaluator_details(self):
        report = build_report(evaluation_result())

        self.assertEqual(report["report_version"], 1)
        self.assertEqual(report["evaluation"]["benchmark"], "payments-regression")
        self.assertEqual(report["evaluation"]["evaluation_subject"], "payments-agent")
        self.assertEqual(report["evaluation"]["evaluated_tasks"], [
            "inventory-race-condition",
            "refund-idempotency",
        ])
        self.assertEqual(report["evaluation"]["score"], 0.5)
        self.assertEqual(report["task_eligibility"]["counts"], {
            "requested": 3,
            "eligible": 2,
            "exposed": 1,
            "unknown": 0,
            "selected": 2,
            "excluded": 1,
            "flagged": 0,
        })
        self.assertEqual(report["clean_claim"], {
            "permitted": True,
            "reason": "exposed_tasks_excluded",
        })
        self.assertEqual(report["monitoring"]["generic_agent_access"], "INCOMPLETE_MONITORING")
        self.assertEqual(report["monitoring"]["sibyl_state"], "AVAILABLE")
        serialized = json.dumps(report, sort_keys=True)
        self.assertNotIn("hidden answer must not be copied", serialized)
        self.assertNotIn("details", serialized)
        self.assertNotIn("extra", serialized)

    def test_report_never_allows_a_clean_claim_for_an_incomplete_or_unjournaled_run(self):
        report = build_report(evaluation_result(
            evaluation_complete=False,
            journaled=False,
            clean_claim_permitted=True,
            reason="evaluator_did_not_evaluate_all_selected_tasks",
        ))

        self.assertFalse(report["clean_claim"]["permitted"])
        self.assertEqual(
            report["clean_claim"]["reason"],
            "evaluator_did_not_evaluate_all_selected_tasks",
        )
        self.assertFalse(report["provenance"]["journaled"])

    def test_report_surfaces_an_incomplete_capture_boundary(self):
        report = build_report(evaluation_result(
            clean_claim_permitted=False,
            reason="incomplete_monitoring",
        ))

        self.assertEqual(report["monitoring"]["status"], "INCOMPLETE_MONITORING")
        self.assertEqual(
            report["monitoring"]["protected_reads"],
            "INCOMPLETE_MONITORING",
        )
        self.assertEqual(
            report["monitoring"]["generic_agent_access"],
            "INCOMPLETE_MONITORING",
        )

    def test_render_report_supports_json_and_markdown(self):
        report = build_report(evaluation_result())

        rendered_json = render_report(report, "json")
        self.assertEqual(json.loads(rendered_json), report)

        rendered_markdown = render_report(report, "markdown")
        self.assertIn("# Skepis Clean Evaluation Report", rendered_markdown)
        self.assertIn("Clean claim permitted: YES", rendered_markdown)
        self.assertIn("Generic agent access: INCOMPLETE_MONITORING", rendered_markdown)
        self.assertNotIn("hidden answer must not be copied", rendered_markdown)

    def test_cli_report_reads_saved_evaluation_and_writes_portable_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "evaluation.json"
            output_path = root / "skepis-report.md"
            input_path.write_text(
                json.dumps(evaluation_result()),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main([
                    "report",
                    "--input",
                    str(input_path),
                    "--format",
                    "markdown",
                    "--output",
                    str(output_path),
                ])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            rendered = output_path.read_text(encoding="utf-8")
            self.assertIn("# Skepis Clean Evaluation Report", rendered)
            self.assertIn("Benchmark: payments-regression", rendered)
            self.assertNotIn("hidden answer must not be copied", rendered)

    def test_load_latest_evaluation_selects_the_scoped_completed_run(self):
        class Memory:
            def read_events(self, *, limit=1000):
                return [
                    {
                        "ts": "2026-09-01T10:00:00Z",
                        "extra": {
                            "event_type": "evaluation_completed",
                            "run_id": "other-run",
                            "tenant_id": "tenant-a",
                            "evaluation_subject": "payments-agent",
                            "benchmark": "payments-regression",
                        },
                    },
                    {
                        "ts": "2026-09-01T10:01:00Z",
                        "extra": {
                            **evaluation_result(),
                            "event_type": "evaluation_completed",
                            "tenant_id": "tenant-a",
                        },
                    },
                ]

        loaded = load_latest_evaluation(
            Memory(),
            tenant_id="tenant-a",
            evaluation_subject="payments-agent",
            benchmark_id="payments-regression",
        )

        self.assertEqual(loaded["run_id"], "run-payments-001")

    def test_report_source_can_be_loaded_from_a_json_encoded_event(self):
        class Memory:
            def read_events(self, *, limit=1000):
                event = {
                    **evaluation_result(),
                    "event_type": "evaluation_completed",
                    "tenant_id": "tenant-a",
                }
                return [{"ts": "2026-09-01T10:01:00Z", "extra": json.dumps(event)}]

        loaded = load_latest_evaluation(
            Memory(),
            tenant_id="tenant-a",
            evaluation_subject="payments-agent",
            benchmark_id="payments-regression",
        )

        self.assertEqual(loaded["benchmark"], "payments-regression")

    def test_report_reads_the_canonical_result_journaled_by_the_evaluation_runner(self):
        class Memory:
            def __init__(self):
                self.events = []

            def get_entity(self, _category, _name):
                return {
                    "body": {
                        "tenant_id": "tenant-a",
                        "evaluation_subject": "payments-agent",
                        "benchmark": "payments-regression",
                        "tasks": {"refund-idempotency": {"eligibility": "UNSEEN"}},
                    }
                }

            def write_event(self, *, extra=None, ts=None, **_):
                self.events.append({"extra": extra, "ts": ts})
                return f"event-{len(self.events)}"

            def read_events(self, *, limit=1000):
                return self.events[-limit:]

        memory = Memory()
        result, exit_code = run_evaluation(
            evaluator=lambda request: {
                "evaluated_tasks": list(request.task_ids),
                "score": 1.0,
                "metrics": {"received_count": len(request.task_ids)},
            },
            memory=memory,
            task_ids=["refund-idempotency"],
            policy="strict",
            tenant_id="tenant-a",
            evaluation_subject="payments-agent",
            benchmark_id="payments-regression",
        )

        self.assertEqual(exit_code, 0)
        loaded = load_latest_evaluation(
            memory,
            tenant_id="tenant-a",
            evaluation_subject="payments-agent",
            benchmark_id="payments-regression",
            run_id=result["run_id"],
        )
        report = build_report(loaded)
        self.assertTrue(report["clean_claim"]["permitted"])
        self.assertEqual(report["evaluation"]["score"], 1.0)
        self.assertEqual(report["evaluation"]["evaluated_count"], 1)
        self.assertEqual(report["monitoring"]["protected_reads"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
