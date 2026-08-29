"""The thin command-line surface for a local Skepis project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
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
from skepis.eval.runner import run_fixture
from skepis.policy import EvaluationGate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skepis", description="Local-first exposure-aware evaluation tooling")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="initialize a project config")
    init.add_argument("--root", default=".", help="project root, default: current directory")
    init.add_argument("--config", help="config path, default: skepis.toml under the project root")
    init.add_argument("--tenant-id", help="explicit local or Sibyl tenant scope")
    init.add_argument("--memory-db", default=DEFAULT_MEMORY_DB)
    init.add_argument("--policy", default="exclude")

    benchmark = commands.add_parser("benchmark", help="manage benchmark registration")
    benchmark_commands = benchmark.add_subparsers(dest="benchmark_command", required=True)
    register = benchmark_commands.add_parser("register", help="register one benchmark and its protected paths")
    register.add_argument("--config", help="config path, default: skepis.toml")
    register.add_argument("--id", dest="benchmark_id")
    register.add_argument("--evaluation-subject")
    register.add_argument("--fixture")
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

    evaluation = commands.add_parser("eval", help="run a policy-gated evaluation")
    evaluation_commands = evaluation.add_subparsers(dest="evaluation_command", required=True)
    run = evaluation_commands.add_parser("run", help="run the configured fixture through the policy gate")
    run.add_argument("--config", help="config path, default: skepis.toml")
    run.add_argument("--fixture", help="optional fixture override")
    run.add_argument("--policy", help="exclude, flag, or strict")
    run.add_argument("--json", action="store_true", dest="as_json")
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
    tenant_id = args.tenant_id or str(uuid.uuid4())
    config = initialize_config(
        config_path,
        project_root=root,
        tenant_id=tenant_id,
        memory_db=args.memory_db,
        default_policy=args.policy,
    )
    _open_memory(config.memory_db)
    print("Initialized Skepis project")
    print(f"CONFIG: {config.config_path}")
    print(f"MEMORY_DB: {config.memory_db}")
    print(f"TENANT_ID: {config.tenant_id}")
    return 0


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
    return {
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
        print("JOURNALED: false")
    return 0


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
    return 0


def _cmd_eval_run(args: argparse.Namespace) -> int:
    config = load_config(resolve_config_path(args.config), require_benchmark=True)
    benchmark = require_benchmark(config)
    policy = parse_policy(args.policy or config.default_policy)
    fixture = (
        _resolve_fixture(args.fixture, config.project_root)
        if args.fixture
        else benchmark.fixture
    )
    if not fixture.is_file():
        raise ConfigError(f"missing fixture: {fixture}")
    memory = _open_memory(config.memory_db)
    try:
        result, exit_code = run_fixture(
            fixture,
            memory=memory,
            policy=policy.value,
            tenant_id=config.tenant_id,
            evaluation_subject=benchmark.evaluation_subject,
            benchmark_id=benchmark.id,
            allowed_task_ids=benchmark.task_ids,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid fixture: {exc}") from exc
    if args.as_json:
        print(json.dumps(result, sort_keys=True))
    else:
        _print_partitions(result, include_selection=True)
        print(f"SCORE: {result['score']}")
        print(f"CLEAN_CLAIM_PERMITTED: {str(result['clean_claim_permitted']).lower()}")
    return exit_code


def _resolve_fixture(value: str, project_root: Path) -> Path:
    fixture = Path(value).expanduser()
    if not fixture.is_absolute():
        fixture = project_root / fixture
    fixture = fixture.resolve(strict=False)
    try:
        fixture.relative_to(project_root.resolve(strict=False))
    except ValueError as exc:
        raise ConfigError(f"fixture must be inside the project root: {fixture}") from exc
    return fixture


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


def _display_tasks(tasks: Any) -> str:
    if tasks is None:
        return "not applied"
    return " ".join(tasks) if tasks else "none"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "benchmark" and args.benchmark_command == "register":
            return _cmd_register(args)
        if args.command == "exposure" and args.exposure_command == "status":
            return _cmd_status(args)
        if args.command == "exposure" and args.exposure_command == "read":
            return _cmd_protected_read(args)
        if args.command == "eval" and args.evaluation_command == "run":
            return _cmd_eval_run(args)
        raise ConfigError("no command selected")
    except ConfigError as exc:
        print(f"skepis configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"skepis error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
