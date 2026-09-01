"""Deterministic fixture evaluator used only by the historical demo."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    project_root = Path(os.environ["SKEPIS_PROJECT_ROOT"])
    request = json.loads(
        Path(os.environ["SKEPIS_EVALUATION_REQUEST"]).read_text(encoding="utf-8")
    )
    fixture = json.loads((project_root / "fixture.json").read_text(encoding="utf-8"))
    scores = {
        task_id: fixture["cases"][task_id]["candidate_output"]
        == fixture["cases"][task_id]["expected"]
        for task_id in request["task_ids"]
    }
    print(
        json.dumps(
            {
                "evaluated_tasks": request["task_ids"],
                "scores": scores,
                "metrics": {
                    "passed": sum(scores.values()),
                    "total": len(scores),
                },
                "score": (sum(scores.values()) / len(scores)) if scores else None,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
