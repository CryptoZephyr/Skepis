"""The thin command-line surface for a local Skepis project."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys
import uuid
from typing import Any

from skepis.config import (
    ConfigError,
    DEFAULT_MEMORY_DB,
    initialize_config,
    load_config,
    parse_policy,
    register_benchmark,
    require_benchmark,
    resolve_config_path,
)
from skepis.capture import (
    LocalPathCapture,
    LocalPathDetector,
    ProtectedReadBoundary,
    ProtectedReadError,
    ProtectedResource,
)
from skepis.eval import CommandEvaluator, EvaluatorError, run_evaluation
from skepis.integration import connect_project
from skepis.policy import EvaluationGate
from skepis.report import (
    ReportError,
    build_report,
    derive_monitoring_coverage,
    load_latest_evaluation,
    render_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skepis", description="Local-first exposure-aware evaluation tooling")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="set up a project for Skepis")
    init.add_argument("--root", default=".", help="project root, default: current directory")
    init.add_argument("--config", help="config path, default: skepis.toml under the project root")
    init.add_argument("--tenant-id", help="explicit local or Sibyl tenant scope")
    init.add_argument("--memory-db", default=DEFAULT_MEMORY_DB)
    init.add_argument("--policy", help="advanced policy override: exclude, flag, or strict")
    init.add_argument("--benchmark-id", "--benchmark", dest="benchmark_id")
    init.add_argument("--evaluation-subject", "--agent", dest="evaluation_subject")
    init.add_argument(
        "--fixture",
        help="optional benchmark metadata file; task metadata is discovered when reliable",
    )
    init.add_argument("--evaluator-command", "--evaluator", dest="evaluator_command")
    init.add_argument("--evaluator-working-directory")
    init.add_argument("--evaluator-timeout", type=float, default=300.0)
    init.add_argument("--task", dest="task_ids", action="append", default=[])
    init.add_argument(
        "--protected",
        dest="protected",
        action="append",
        default=[],
        metavar="TASK=PATH",
    )
    init.add_argument(
        "--non-interactive",
        action="store_true",
        help="require all setup values from flags instead of prompting",
    )
    init.add_argument("--json", action="store_true", dest="as_json")

    connect = commands.add_parser(
        "connect",
        help="connect the existing Skepis MCP server to a project coding agent",
    )
    connect.add_argument("--root", default=".", help="project root, default: current directory")
    connect.add_argument("--config", help="config path, default: skepis.toml under the project root")
    connect.add_argument(
        "--client",
        choices=("auto", "claude", "cursor"),
        default="auto",
        help="client to configure, default: detect Claude Code or Cursor",
    )
    connect.add_argument("--json", action="store_true", dest="as_json")

    benchmark = commands.add_parser("benchmark", help="manage benchmark registration")
    benchmark_commands = benchmark.add_subparsers(dest="benchmark_command", required=True)
    register = benchmark_commands.add_parser("register", help="register one benchmark and its protected paths")
    register.add_argument("--config", help="config path, default: skepis.toml")
    register.add_argument("--id", dest="benchmark_id")
    register.add_argument("--evaluation-subject")
    register.add_argument(
        "--fixture",
        help="optional deterministic fixture metadata for tests or demos",
    )
    register.add_argument(
        "--evaluator-command",
        "--evaluator",
        dest="evaluator_command",
        help="developer evaluator command; it receives SKEPIS_TASK_IDS and SKEPIS_EVALUATION_REQUEST",
    )
    register.add_argument("--evaluator-working-directory")
    register.add_argument("--evaluator-timeout", type=float, default=300.0)
    register.add_argument("--task", dest="task_ids", action="append", default=[])
    register.add_argument(
        "--protected",
        dest="protected",
        action="append",
        default=[],
        metavar="TASK=PATH",
        help="repeat for each protected project-relative path",
    )

    exposure = commands.add_parser("exposure", help="inspect persisted exposure state")
    exposure_commands = exposure.add_subparsers(dest="exposure_command", required=True)
    status = exposure_commands.add_parser("status", help="show CLEAN, EXPOSED, and UNKNOWN tasks")
    status.add_argument("--config", help="config path, default: skepis.toml")
    status.add_argument("--task", dest="task_ids", action="append", default=[])
    status.add_argument("--json", action="store_true", dest="as_json")
    protected_read = exposure_commands.add_parser(
        "read",
        help="read one registered protected resource through the capture boundary",
    )
    protected_read.add_argument("--config", help="config path, default: skepis.toml")
    protected_read.add_argument("--path", required=True, help="protected project-relative path")
    protected_read.add_argument("--session-id", required=True)
    protected_read.add_argument("--observed-at")
    protected_read.add_argument("--encoding", default="utf-8")
    protected_read.add_argument("--json", action="store_true", dest="as_json")

    inspect = commands.add_parser(
        "inspect",
        help="explain exposed or uncertain tasks when a review is needed",
    )
    inspect.add_argument("--config", help="config path, default: skepis.toml")
    inspect.add_argument("--task", dest="task_ids", action="append", default=[])
    inspect.add_argument("--json", action="store_true", dest="as_json")

    evaluation = commands.add_parser("eval", help="run a policy-gated evaluation")
    evaluation.add_argument(
        "evaluation_action",
        nargs="?",
        choices=("run",),
        help="optional legacy spelling: `skepis eval run`",
    )
    run = evaluation
    run.add_argument("--config", help="config path, default: skepis.toml")
    run.add_argument("--task", dest="task_ids", action="append", default=[])
    run.add_argument("--policy", help="exclude, flag, or strict")
    run.add_argument("--json", action="store_true", dest="as_json")

    report = commands.add_parser(
        "report",
        help="render a portable report from a completed policy-gated evaluation",
    )
    report.add_argument("--config", help="config path when reading the latest Sibyl run")
    report.add_argument(
        "--input",
        type=Path,
        help="saved JSON from `skepis eval run --json`; omit to read the latest Sibyl run",
    )
    report.add_argument("--run-id", help="select a specific completed Sibyl run")
    report.add_argument("--format", choices=("text", "json", "markdown"))
    report.add_argument("--json", action="store_true", dest="as_json")
    report.add_argument("--output", type=Path, help="write the rendered report to a file")
    return parser


def _open_memory(path: Path) -> Any:
    from sibyl_memory_client import MemoryClient

    path.parent.mkdir(parents=True, exist_ok=True)
    return MemoryClient.local(str(path))


def _make_capture(config: Any, benchmark: Any, memory: Any) -> LocalPathCapture:
    resources = [
        ProtectedResource(config.tenant_id, benchmark.id, task_id, pattern)
        for task_id, patterns in benchmark.protected_paths.items()
        for pattern in patterns
    ]
    return LocalPathCapture(
        memory=memory,
        detector=LocalPathDetector(config.project_root, resources),
        tenant_id=config.tenant_id,
        evaluation_subject=benchmark.evaluation_subject,
        benchmark_id=benchmark.id,
    )


def _cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve(strict=False)
    config_path = resolve_config_path(args.config, base=root)
    setup_values = (
        args.benchmark_id,
        args.evaluation_subject,
        args.fixture,
        args.evaluator_command,
        args.evaluator_working_directory,
        args.task_ids,
        args.protected,
    )
    interactive = not args.non_interactive and sys.stdin.isatty()

    if config_path.exists():
        config = load_config(config_path)
        if config.benchmark is not None:
            if any(value for value in setup_values):
                raise ConfigError(
                    f"benchmark already registered: {config.benchmark.id}. "
                    "Run init without benchmark options to review readiness."
                )
            _ensure_memory_available(config)
            _print_ready_summary(config, args.as_json)
            return 0
    else:
        config = None

    fixture_path = _resolve_optional_path(args.fixture, root)
    fixture_metadata = _load_fixture_metadata(fixture_path) if fixture_path else {}

    if config is None and not interactive and not any(setup_values):
        config = initialize_config(
            config_path,
            project_root=root,
            tenant_id=args.tenant_id or str(uuid.uuid4()),
            memory_db=args.memory_db,
            default_policy=args.policy or "exclude",
        )
        _ensure_memory_available(config)
        if args.as_json:
            print(json.dumps({
                "status": "INITIALIZED",
                "config": str(config.config_path),
                "memory_db": str(config.memory_db),
                "tenant_id": config.tenant_id,
                "next": "skepis init --benchmark-id ...",
            }, sort_keys=True))
        else:
            print("Initialized Skepis project")
            print(f"CONFIG: {config.config_path}")
            print(f"MEMORY_DB: {config.memory_db}")
            print(f"TENANT_ID: {config.tenant_id}")
            print("Next: skepis init --benchmark-id ...")
        return 0

    benchmark_id = args.benchmark_id or fixture_metadata.get("benchmark")
    if not benchmark_id and interactive:
        benchmark_id = _prompt_init_value("Benchmark ID")
    evaluation_subject = args.evaluation_subject or fixture_metadata.get("evaluation_subject")
    if not evaluation_subject and interactive:
        evaluation_subject = _prompt_init_value("Agent or evaluation subject")

    task_ids = list(args.task_ids)
    if not task_ids:
        discovered_tasks = fixture_metadata.get("task_ids")
        if isinstance(discovered_tasks, list):
            task_ids = [str(task_id).strip() for task_id in discovered_tasks if str(task_id).strip()]
    if not task_ids and interactive:
        task_ids = _prompt_task_ids()

    if args.protected:
        protected_paths = _parse_protected(args.protected)
    else:
        discovered_protected = fixture_metadata.get("protected_paths")
        protected_paths = (
            {
                str(task_id): [str(pattern) for pattern in patterns]
                for task_id, patterns in discovered_protected.items()
                if isinstance(patterns, list)
            }
            if isinstance(discovered_protected, dict)
            else {}
        )
        if not protected_paths and interactive:
            protected_paths = _prompt_protected_paths()

    evaluator_command_text = args.evaluator_command
    if not evaluator_command_text and interactive:
        evaluator_command_text = _prompt_init_value("Evaluator command")
    if not benchmark_id:
        raise ConfigError("missing benchmark id; pass --benchmark-id or run init in a terminal")
    if not evaluation_subject:
        raise ConfigError(
            "missing evaluation subject; pass --evaluation-subject or run init in a terminal"
        )
    if not task_ids:
        raise ConfigError("missing task ids; pass one or more --task values")
    if not evaluator_command_text:
        raise ConfigError(
            "missing evaluator command; pass --evaluator-command or run init in a terminal"
        )

    if config is None:
        config = initialize_config(
            config_path,
            project_root=root,
            tenant_id=args.tenant_id or str(uuid.uuid4()),
            memory_db=args.memory_db,
            default_policy=args.policy or "exclude",
        )
    elif args.policy is not None and parse_policy(args.policy) != config.default_policy:
        raise ConfigError(
            "the existing project policy is explicit; change it in project configuration"
        )

    config = register_benchmark(
        config.config_path,
        benchmark_id=benchmark_id,
        evaluation_subject=evaluation_subject,
        fixture=fixture_path,
        task_ids=task_ids,
        protected_paths=protected_paths,
        evaluator_command=_parse_evaluator_command(evaluator_command_text),
        evaluator_working_directory=args.evaluator_working_directory,
        evaluator_timeout_seconds=args.evaluator_timeout,
    )
    _ensure_memory_available(config)
    _print_ready_summary(config, args.as_json)
    return 0


def _resolve_optional_path(value: str | Path | None, base: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


def _load_fixture_metadata(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise ConfigError(f"could not read benchmark metadata {path}: {type(exc).__name__}") from exc
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _prompt_init_value(label: str) -> str:
    try:
        value = input(f"{label}: ").strip()
    except EOFError as exc:
        raise ConfigError(f"missing {label.lower()}") from exc
    if not value:
        raise ConfigError(f"missing {label.lower()}")
    return value


def _prompt_task_ids() -> list[str]:
    value = _prompt_init_value("Task IDs, comma-separated")
    task_ids = [item.strip() for item in value.split(",") if item.strip()]
    if not task_ids:
        raise ConfigError("missing task ids")
    return task_ids


def _prompt_protected_paths() -> dict[str, list[str]]:
    print("Protected resource mappings use TASK=PROJECT_RELATIVE_PATH. Leave blank when done.")
    values: list[str] = []
    while True:
        try:
            value = input("Protected resource: ").strip()
        except EOFError:
            break
        if not value:
            break
        values.append(value)
    return _parse_protected(values)


def _ensure_memory_available(config: Any) -> None:
    try:
        _open_memory(config.memory_db)
    except Exception as exc:
        raise ConfigError(
            f"Sibyl memory unavailable: {type(exc).__name__}. Install the Python dependencies and retry."
        ) from exc


def _ready_summary(config: Any) -> dict[str, Any]:
    benchmark = require_benchmark(config)
    pattern_count = sum(len(patterns) for patterns in benchmark.protected_paths.values())
    return {
        "status": "READY",
        "benchmark": benchmark.id,
        "agent": benchmark.evaluation_subject,
        "tasks": len(benchmark.task_ids),
        "protected_resources": pattern_count,
        "policy": config.default_policy.value.upper(),
        "memory": "available",
        "next": "skepis connect",
        "config": str(config.config_path),
    }


def _print_ready_summary(config: Any, as_json: bool) -> None:
    summary = _ready_summary(config)
    if as_json:
        print(json.dumps(summary, sort_keys=True))
        return
    print("Skepis ready.")
    print()
    print(f"Benchmark: {summary['benchmark']}")
    print(f"Agent: {summary['agent']}")
    print(f"Tasks: {summary['tasks']}")
    print(f"Protected resources: {summary['protected_resources']} patterns")
    print(f"Policy: {summary['policy']}")
    print(f"Memory: {summary['memory']}")
    print()
    print(f"Next: {summary['next']}")


def _parse_protected(values: list[str]) -> dict[str, list[str]]:
    protected: dict[str, list[str]] = {}
    for value in values:
        task_id, separator, pattern = value.partition("=")
        if not separator or not task_id.strip() or not pattern.strip():
            raise ConfigError(
                f"invalid protected resource {value!r}. Use TASK=PROJECT_RELATIVE_PATH"
            )
        protected.setdefault(task_id.strip(), []).append(pattern.strip())
    return protected


def _cmd_register(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    config = register_benchmark(
        config_path,
        benchmark_id=args.benchmark_id,
        evaluation_subject=args.evaluation_subject,
        fixture=args.fixture,
        task_ids=args.task_ids,
        protected_paths=_parse_protected(args.protected),
        evaluator_command=(
            _parse_evaluator_command(args.evaluator_command)
            if args.evaluator_command
            else None
        ),
        evaluator_working_directory=args.evaluator_working_directory,
        evaluator_timeout_seconds=args.evaluator_timeout,
    )
    benchmark = require_benchmark(config)
    print(f"Registered benchmark: {benchmark.id}")
    print(f"EVALUATION_SUBJECT: {benchmark.evaluation_subject}")
    print(f"TASKS: {len(benchmark.task_ids)}")
    print(f"PROTECTED_TASKS: {len(benchmark.protected_paths)}")
    return 0


def _selected_tasks(requested: list[str], available: tuple[str, ...]) -> tuple[str, ...]:
    selected = tuple(requested) if requested else available
    unknown = sorted(set(selected) - set(available))
    if unknown:
        raise ConfigError(f"unknown task id: {unknown[0]}")
    return selected


def _status_payload(config: Any, classification: Any) -> dict[str, Any]:
    benchmark = require_benchmark(config)
    result = {
        "benchmark": benchmark.id,
        "evaluation_subject": benchmark.evaluation_subject,
        "requested_tasks": list(classification.requested_tasks),
        "clean_tasks": list(classification.clean_tasks),
        "exposed_tasks": list(classification.exposed_tasks),
        "unknown_tasks": list(classification.unknown_tasks),
        "selected_tasks": None,
        "status": "INSPECTED",
        "memory_available": classification.memory_available,
        "state_available": classification.state_available,
        "reason": classification.reason,
        "journaled": False,
    }
    result["monitoring_coverage"] = derive_monitoring_coverage(result)
    return result


def _cmd_status(args: argparse.Namespace) -> int:
    config = load_config(resolve_config_path(args.config), require_benchmark=True)
    benchmark = require_benchmark(config)
    task_ids = _selected_tasks(args.task_ids, benchmark.task_ids)
    memory = _open_memory(config.memory_db)
    gate = EvaluationGate(
        memory=memory,
        tenant_id=config.tenant_id,
        evaluation_subject=benchmark.evaluation_subject,
        benchmark_id=benchmark.id,
    )
    result = _status_payload(config, gate.classify(task_ids))
    if args.as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        _print_partitions(result, include_selection=False)
        _print_monitoring(result["monitoring_coverage"])
        print("JOURNALED: false")
    return 0


def _cmd_connect(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve(strict=False)
    config = load_config(resolve_config_path(args.config, base=root), require_benchmark=True)
    result = connect_project(
        config.project_root,
        config.config_path,
        requested_client=args.client,
    )
    result.update(
        {
            "project": str(config.project_root),
            "benchmark": require_benchmark(config).id,
            "agent": require_benchmark(config).evaluation_subject,
        }
    )
    if args.as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        _print_connect_result(result)
    return 0 if result["status"] == "CONNECTED" else 2


def _print_connect_result(result: dict[str, Any]) -> None:
    if result["status"] == "NO_CLIENT":
        print("No supported MCP client detected.")
        print()
        print("Skepis MCP is ready for manual configuration.")
        print("Supported project clients: Claude Code and Cursor.")
        print()
        print("Add this server entry to the client's project MCP config:")
        print(json.dumps(result["manual_configuration"], indent=2, sort_keys=True))
        return
    if result["status"] == "FAILED":
        print(f"Detected: {', '.join(result['detected'])}")
        print(f"Project: {result['project']}")
        print()
        print("Skepis MCP connection could not be verified.")
        print(f"Reason: {result['reason']}")
        print("Check the client configuration and run skepis connect again.")
        return

    print(f"Detected: {', '.join(result['detected'])}")
    print(f"Project: {result['project']}")
    print()
    for client in result["configured"]:
        print(f"✓ Skepis MCP configured for {client['label']}")
        print(f"✓ Connection verified, {len(client['tools'])} tools available")
    print()
    print("Skepis is connected.")
    print("Continue using your coding agent normally.")


def _cmd_inspect(args: argparse.Namespace) -> int:
    from skepis.mcp import inspect as inspect_workflow

    config_path = resolve_config_path(args.config)
    try:
        result = inspect_workflow(config_path, args.task_ids or None)
    except (ImportError, ModuleNotFoundError) as exc:
        raise ConfigError(
            "Sibyl memory is unavailable. Install the Python dependencies and retry."
        ) from exc
    if args.as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        _print_human_inspection(result)
    return 0


def _print_human_inspection(result: dict[str, Any]) -> None:
    eligibility = result["eligibility"]
    provenance = result["provenance"]
    exposed = set(eligibility["exposed_tasks"])
    unknown = set(eligibility["unknown_tasks"])
    events = {
        event.get("task"): event
        for event in provenance.get("events", [])
        if isinstance(event, dict) and event.get("task")
    }

    print("Why didn't these tasks count?")
    print()
    for task_id in eligibility["requested_tasks"]:
        print(task_id)
        if task_id in exposed:
            print("EXPOSED")
            event = events.get(f"{result['benchmark']}/{task_id}")
            if event and event.get("observed_at"):
                print(f"Protected material was accessed at {event['observed_at']}")
            else:
                print("Registered protected material was accessed")
        elif task_id in unknown:
            print("UNKNOWN")
            print(_inspection_unknown_reason(eligibility, provenance))
        else:
            print("CLEAN")
            print("No recorded exposure in available monitoring history")
        print()

    coverage = result["monitoring_coverage"]
    print(
        "Monitoring: "
        f"protected reads {coverage['protected_reads']}, "
        f"generic agent access {coverage['generic_agent_access']}, "
        f"Sibyl state {coverage['sibyl_state']}"
    )


def _inspection_unknown_reason(eligibility: dict[str, Any], provenance: dict[str, Any]) -> str:
    reason = eligibility.get("reason") or provenance.get("reason")
    if reason in {"incomplete_monitoring", "provenance_truncated"}:
        return "Monitoring history is incomplete"
    if reason == "warm_state_not_found":
        return "Sibyl exposure state is unavailable"
    if reason and str(reason).startswith("monitoring_"):
        return "Monitoring history is unavailable"
    return "Eligibility could not be established"


def _cmd_protected_read(args: argparse.Namespace) -> int:
    config = load_config(resolve_config_path(args.config), require_benchmark=True)
    benchmark = require_benchmark(config)
    memory = _open_memory(config.memory_db)
    boundary = ProtectedReadBoundary(
        capture=_make_capture(config, benchmark, memory),
        root=config.project_root,
    )
    try:
        result = boundary.read(
            args.path,
            session_id=args.session_id,
            observed_at=args.observed_at,
        )
    except ProtectedReadError as exc:
        raise ConfigError(str(exc)) from exc

    try:
        content = result.content.decode(args.encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ConfigError(
            f"protected read was captured but content cannot be decoded as {args.encoding!r}"
        ) from exc

    if args.as_json:
        print(
            json.dumps(
                {
                    "content": content,
                    "content_encoding": args.encoding,
                    "receipt": result.receipt.as_dict(),
                },
                sort_keys=True,
            )
        )
    else:
        sys.stdout.write(content)
        if content and not content.endswith("\n"):
            sys.stdout.write("\n")
        print(f"CAPTURE: {result.capture.outcome.value}", file=sys.stderr)
        print(f"TASK: {result.receipt.task_key}", file=sys.stderr)
        task_id = result.receipt.task_key.rsplit("/", 1)[-1]
        print(f"Skepis: {task_id} was exposed.", file=sys.stderr)
        print("It will not count as clean evaluation evidence.", file=sys.stderr)
    return 0


def _cmd_eval_run(args: argparse.Namespace) -> int:
    config = load_config(resolve_config_path(args.config), require_benchmark=True)
    benchmark = require_benchmark(config)
    policy = parse_policy(args.policy or config.default_policy)
    if benchmark.evaluator is None:
        raise ConfigError("missing evaluator command in benchmark config")
    task_ids = _selected_tasks(args.task_ids, benchmark.task_ids)
    try:
        evaluator = CommandEvaluator(
            benchmark.evaluator.command,
            project_root=config.project_root,
            working_directory=benchmark.evaluator.working_directory,
            timeout_seconds=benchmark.evaluator.timeout_seconds,
        )
        memory = _open_memory(config.memory_db)
        result, exit_code = run_evaluation(
            evaluator=evaluator,
            memory=memory,
            policy=policy.value,
            tenant_id=config.tenant_id,
            evaluation_subject=benchmark.evaluation_subject,
            benchmark_id=benchmark.id,
            task_ids=task_ids,
            project_root=config.project_root,
        )
    except (EvaluatorError, TypeError, ValueError) as exc:
        raise ConfigError(f"invalid evaluator configuration: {exc}") from exc
    if args.as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        _print_human_evaluation(result)
    return exit_code


def _print_human_evaluation(result: dict[str, Any]) -> None:
    report = build_report(result)
    evaluation = report["evaluation"]
    eligibility = report["task_eligibility"]
    counts = eligibility["counts"]
    claim = report["clean_claim"]
    monitoring = report["monitoring"]

    if not claim["permitted"]:
        print("Clean evaluation could not be established.")
        print()
        _print_evaluation_counts(counts)
        print()
        print(_human_evaluation_reason(claim["reason"], counts))
        print()
        print("Run `skepis inspect` for details.")
    else:
        print("Skepis Evaluation")
        print()
        print(f"{evaluation['evaluation_subject']} x {evaluation['benchmark']}")
        print()
        _print_evaluation_counts(counts)
        print()
        if counts["selected"]:
            print(f"Evaluating {counts['selected']} clean tasks...")
        else:
            print("Evaluating no clean tasks.")
        print()
        _print_score(evaluation, evaluation.get("metrics", {}))
        if counts["excluded"]:
            print(f"{counts['excluded']} exposed tasks excluded")
        if counts["flagged"]:
            print(f"{counts['flagged']} exposed or uncertain tasks flagged")
        print()
        print("Clean claim: permitted")

    print()
    print(
        "Monitoring: "
        f"protected reads {monitoring['protected_reads']}, "
        f"generic agent access {monitoring['generic_agent_access']}, "
        f"Sibyl state {monitoring['sibyl_state']}"
    )


def _print_evaluation_counts(counts: dict[str, int]) -> None:
    print(f"{counts['requested']} requested")
    print(f"{counts['eligible']} clean")
    print(f"{counts['exposed']} previously exposed")
    if counts["unknown"]:
        print(f"{counts['unknown']} unknown")


def _print_score(evaluation: dict[str, Any], metrics: Any) -> None:
    if isinstance(metrics, dict):
        passed = metrics.get("passed")
        total = metrics.get("total")
        if (
            isinstance(passed, (int, float))
            and not isinstance(passed, bool)
            and isinstance(total, (int, float))
            and not isinstance(total, bool)
        ):
            print(f"Passed: {passed:g} / {total:g}")
    score = evaluation.get("score")
    if score is None:
        print("Score: not provided")
    else:
        print(f"Score: {score}")


def _human_evaluation_reason(reason: Any, counts: dict[str, int]) -> str:
    if reason == "warm_state_not_found":
        return "Sibyl exposure state is unavailable, so unknown tasks cannot support a clean claim."
    if counts["unknown"]:
        return "Monitoring history is incomplete, so unknown tasks cannot support a clean claim."
    messages = {
        "strict_policy_blocked": "The selected policy blocked exposed or uncertain tasks.",
        "decision_not_journaled": "The policy decision could not be durably recorded.",
        "run_not_fully_journaled": "The evaluation result could not be durably recorded.",
        "evaluator_did_not_evaluate_all_selected_tasks": (
            "The evaluator did not return a complete result for every selected task."
        ),
    }
    if isinstance(reason, str) and reason.startswith("evaluator_failed:"):
        return "The evaluator did not return a complete result."
    return messages.get(str(reason), "The evaluation did not produce enough evidence for a clean claim.")


def _cmd_report(args: argparse.Namespace) -> int:
    if args.input is not None and args.run_id is not None:
        raise ConfigError("--run-id can only be used when reading the latest Sibyl run")
    if args.as_json and args.format is not None:
        raise ConfigError("--json cannot be combined with --format")

    if args.input is not None:
        try:
            source = json.loads(args.input.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ReportError(f"could not read report input {args.input}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ReportError(f"report input is not valid JSON: {exc}") from exc
        if not isinstance(source, dict):
            raise ReportError("report input must be a JSON object")
    else:
        config = load_config(resolve_config_path(args.config), require_benchmark=True)
        benchmark = require_benchmark(config)
        memory = _open_memory(config.memory_db)
        source = load_latest_evaluation(
            memory,
            tenant_id=config.tenant_id,
            evaluation_subject=benchmark.evaluation_subject,
            benchmark_id=benchmark.id,
            run_id=args.run_id,
        )

    report = build_report(source)
    output_format = _report_format(args.format, args.as_json, args.output)
    rendered = render_report(report, output_format)
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            raise ReportError(f"could not write report {args.output}: {exc}") from exc
    return 0


def _report_format(
    requested: str | None,
    as_json: bool,
    output: Path | None,
) -> str:
    if as_json:
        return "json"
    if requested is not None:
        return requested
    if output is not None:
        suffix = output.suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix in {".md", ".markdown"}:
            return "markdown"
    return "text"


def _parse_evaluator_command(value: str) -> tuple[str, ...]:
    raw = value.strip()
    if not raw:
        raise ConfigError("evaluator command cannot be empty")
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"malformed evaluator command JSON: {exc}") from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ConfigError("evaluator command JSON must be an array of strings")
        return tuple(parsed)
    try:
        parts = shlex.split(raw, posix=os.name != "nt")
    except ValueError as exc:
        raise ConfigError(f"malformed evaluator command: {exc}") from exc
    if os.name == "nt":
        parts = [
            part[1:-1]
            if len(part) >= 2 and part[0] == part[-1] and part[0] in {"'", '"'}
            else part
            for part in parts
        ]
    if not parts:
        raise ConfigError("evaluator command cannot be empty")
    return tuple(parts)


def _print_partitions(result: dict[str, Any], *, include_selection: bool) -> None:
    print(f"BENCHMARK: {result['benchmark']}")
    print(f"EVALUATION_SUBJECT: {result['evaluation_subject']}")
    print(f"CLEAN: {_display_tasks(result['clean_tasks'])}")
    print(f"EXPOSED: {_display_tasks(result['exposed_tasks'])}")
    print(f"UNKNOWN: {_display_tasks(result['unknown_tasks'])}")
    if include_selection:
        print(f"SELECTED: {_display_tasks(result['selected_tasks'])}")
        print(f"EXCLUDED: {_display_tasks(result['excluded_tasks'])}")
        print(f"FLAGGED: {_display_tasks(result['flagged_tasks'])}")
    print(f"STATUS: {result['status']}")


def _print_monitoring(coverage: dict[str, str]) -> None:
    print(f"PROTECTED_READS: {coverage['protected_reads']}")
    print(f"GENERIC_AGENT_ACCESS: {coverage['generic_agent_access']}")
    print(f"SIBYL_STATE: {coverage['sibyl_state']}")


def _display_tasks(tasks: Any) -> str:
    if tasks is None:
        return "not applied"
    return " ".join(tasks) if tasks else "none"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "connect":
            return _cmd_connect(args)
        if args.command == "benchmark" and args.benchmark_command == "register":
            return _cmd_register(args)
        if args.command == "exposure" and args.exposure_command == "status":
            return _cmd_status(args)
        if args.command == "exposure" and args.exposure_command == "read":
            return _cmd_protected_read(args)
        if args.command == "inspect":
            return _cmd_inspect(args)
        if args.command == "eval" and args.evaluation_action in {None, "run"}:
            return _cmd_eval_run(args)
        if args.command == "report":
            return _cmd_report(args)
        raise ConfigError("no command selected")
    except (ConfigError, ReportError) as exc:
        print(f"skepis configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"skepis error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
