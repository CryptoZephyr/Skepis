"""Load and validate the small project configuration used by the CLI."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product
import json
from pathlib import Path
import re
import tomllib
from typing import Any, Mapping, Sequence

from skepis.capture import LocalPathDetector, ProtectedResource
from skepis.policy import EvaluationPolicy
from skepis.scope import normalize_scope_identifier


DEFAULT_CONFIG_NAME = "skepis.toml"
DEFAULT_MEMORY_DB = ".skepis/memory.db"
DEFAULT_POLICY = EvaluationPolicy.EXCLUDE.value
_GLOB_TOKEN = re.compile(r"\*\*|\*|\?|\[[^\]]*\]")


class ConfigError(ValueError):
    """A user-correctable project configuration error."""


@dataclass(frozen=True)
class BenchmarkConfig:
    id: str
    evaluation_subject: str
    fixture: Path
    task_ids: tuple[str, ...]
    protected_paths: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class ProjectConfig:
    config_path: Path
    project_root: Path
    tenant_id: str
    memory_db: Path
    default_policy: EvaluationPolicy
    benchmark: BenchmarkConfig | None = None


def resolve_config_path(value: str | Path | None = None, *, base: str | Path = ".") -> Path:
    """Resolve a config path relative to an explicit command base directory."""

    base_path = Path(base).expanduser().resolve(strict=False)
    path = Path(value or DEFAULT_CONFIG_NAME).expanduser()
    if not path.is_absolute():
        path = base_path / path
    return path.resolve(strict=False)


def parse_policy(value: EvaluationPolicy | str) -> EvaluationPolicy:
    if isinstance(value, EvaluationPolicy):
        return value
    try:
        return EvaluationPolicy(str(value).strip().lower())
    except ValueError as exc:
        raise ConfigError(
            f"unsupported policy {value!r}. Choose exclude, flag, or strict"
        ) from exc


def load_config(
    config_path: str | Path = DEFAULT_CONFIG_NAME,
    *,
    require_benchmark: bool = False,
) -> ProjectConfig:
    """Read and validate a project config without opening Sibyl."""

    path = resolve_config_path(config_path)
    if not path.is_file():
        raise ConfigError(f"config not found: {path}. Run `skepis init` first")
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"malformed config {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"malformed config {path}: root must be a TOML table")
    if "schema_version" in raw:
        raise ConfigError("schema_version is not supported yet")

    project_root = _resolve_path(raw.get("project_root", "."), path.parent, "project_root")
    if not project_root.is_dir():
        raise ConfigError(f"project root does not exist: {project_root}")
    tenant_id = _scope_text(raw.get("tenant_id"), "tenant_id")
    memory_db = _resolve_path_within(
        raw.get("memory_db", DEFAULT_MEMORY_DB),
        project_root,
        "memory_db",
    )
    default_policy = parse_policy(raw.get("default_policy", DEFAULT_POLICY))

    raw_benchmark = raw.get("benchmark")
    if raw_benchmark is not None and not isinstance(raw_benchmark, Mapping):
        raise ConfigError("malformed benchmark config: expected a TOML table")
    benchmark = (
        _parse_benchmark(raw_benchmark, project_root=project_root, tenant_id=tenant_id)
        if raw_benchmark is not None
        else None
    )
    if require_benchmark and benchmark is None:
        raise ConfigError("missing benchmark id in config")
    return ProjectConfig(
        config_path=path,
        project_root=project_root,
        tenant_id=tenant_id,
        memory_db=memory_db,
        default_policy=default_policy,
        benchmark=benchmark,
    )


def initialize_config(
    config_path: str | Path,
    *,
    project_root: str | Path,
    tenant_id: str,
    memory_db: str | Path = DEFAULT_MEMORY_DB,
    default_policy: EvaluationPolicy | str = DEFAULT_POLICY,
) -> ProjectConfig:
    """Create a project config and leave benchmark registration separate."""

    path = resolve_config_path(config_path)
    if path.exists():
        raise ConfigError(f"config already exists: {path}")
    root = Path(project_root).expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise ConfigError(f"project root is not a directory: {root}")
    config = ProjectConfig(
        config_path=path,
        project_root=root,
        tenant_id=_scope_text(tenant_id, "tenant_id"),
        memory_db=_resolve_path_within(memory_db, root, "memory_db"),
        default_policy=parse_policy(default_policy),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_config(config), encoding="utf-8")
    return load_config(path)


def register_benchmark(
    config_path: str | Path,
    *,
    benchmark_id: str | None,
    evaluation_subject: str | None,
    fixture: str | Path | None,
    task_ids: Sequence[str],
    protected_paths: Mapping[str, Sequence[str]],
) -> ProjectConfig:
    """Validate and persist one benchmark registration in an initialized project."""

    base = load_config(config_path)
    if base.benchmark is not None:
        raise ConfigError(
            f"benchmark already registered: {base.benchmark.id}. Reinitialize or edit the config explicitly"
        )
    raw_benchmark = {
        "id": benchmark_id,
        "evaluation_subject": evaluation_subject,
        "fixture": fixture,
        "task_ids": list(task_ids),
        "protected_paths": {str(task_id): list(patterns) for task_id, patterns in protected_paths.items()},
    }
    benchmark = _parse_benchmark(
        raw_benchmark,
        project_root=base.project_root,
        tenant_id=base.tenant_id,
    )
    updated = replace(base, benchmark=benchmark)
    base.config_path.write_text(_render_config(updated), encoding="utf-8")
    return load_config(base.config_path, require_benchmark=True)


def require_benchmark(config: ProjectConfig) -> BenchmarkConfig:
    if config.benchmark is None:
        raise ConfigError("missing benchmark id in config")
    return config.benchmark


def _parse_benchmark(
    raw: Mapping[str, Any],
    *,
    project_root: Path,
    tenant_id: str,
) -> BenchmarkConfig:
    benchmark_id = _scope_text(raw.get("id"), "benchmark id")
    evaluation_subject = _scope_text(raw.get("evaluation_subject"), "evaluation subject")
    fixture = _resolve_path_within(raw.get("fixture"), project_root, "fixture")
    if not fixture.is_file():
        raise ConfigError(f"missing fixture: {fixture}")

    task_ids = _task_ids(raw.get("task_ids"))
    task_set = set(task_ids)
    raw_protected = raw.get("protected_paths", {})
    if not isinstance(raw_protected, Mapping):
        raise ConfigError("malformed protected_paths: expected a TOML table")

    resources: list[ProtectedResource] = []
    for raw_task_id, raw_patterns in raw_protected.items():
        task_id = _scope_text(raw_task_id, "protected task id")
        if task_id not in task_set:
            raise ConfigError(
                f"protected path references unknown task {task_id!r}"
            )
        if not isinstance(raw_patterns, list) or not raw_patterns:
            raise ConfigError(
                f"protected paths for task {task_id!r} must be a non-empty array"
            )
        for raw_pattern in raw_patterns:
            pattern = _text(raw_pattern, f"protected path for task {task_id}")
            resources.append(
                ProtectedResource(tenant_id, benchmark_id, task_id, pattern)
            )

    try:
        detector = LocalPathDetector(project_root, resources)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"invalid protected-resource registration: {exc}") from exc
    _reject_ambiguous_registration(detector)
    normalized_paths: dict[str, list[str]] = {}
    for resource in detector.resources:
        normalized_paths.setdefault(resource.task_id, []).append(resource.pattern)
    return BenchmarkConfig(
        id=benchmark_id,
        evaluation_subject=evaluation_subject,
        fixture=fixture,
        task_ids=task_ids,
        protected_paths={
            task_id: tuple(patterns)
            for task_id, patterns in normalized_paths.items()
        },
    )


def _reject_ambiguous_registration(detector: LocalPathDetector) -> None:
    resources = detector.resources
    for index, left in enumerate(resources):
        for right in resources[index + 1 :]:
            if left.task_key == right.task_key:
                continue
            if left.pattern == right.pattern:
                raise ConfigError(
                    "ambiguous protected-resource registration: "
                    f"{left.pattern!r} belongs to both {left.task_key!r} and {right.task_key!r}"
                )
            hints = set(_literal_hints(left.pattern)) | set(_literal_hints(right.pattern))
            candidates = _witnesses(left.pattern, hints) | _witnesses(right.pattern, hints)
            for candidate in candidates:
                try:
                    _, matches, _ = detector.resolve(candidate)
                except ValueError:
                    continue
                if left.task_key in matches and right.task_key in matches:
                    raise ConfigError(
                        "ambiguous protected-resource registration: "
                        f"{left.pattern!r} overlaps {right.pattern!r}"
                    )


def _literal_hints(pattern: str) -> tuple[str, ...]:
    literal = _GLOB_TOKEN.sub(" ", pattern)
    return tuple(part for part in re.split(r"[/\s]+", literal) if part)


def _witnesses(pattern: str, hints: set[str]) -> set[str]:
    matches = list(_GLOB_TOKEN.finditer(pattern))
    if not matches:
        return {pattern}
    pieces: list[str] = []
    tokens: list[str] = []
    cursor = 0
    for match in matches:
        pieces.append(pattern[cursor : match.start()])
        tokens.append(match.group(0))
        cursor = match.end()
    pieces.append(pattern[cursor:])

    choices: list[tuple[str, ...]] = []
    base_choices = {"x", "a"} | {hint for hint in hints if hint}
    for token in tokens:
        values = set(base_choices)
        if token == "**":
            values |= {"", "x/x"}
            values |= {f"{hint}/x" for hint in hints if hint}
        choices.append(tuple(sorted(values)))

    witnesses: set[str] = set()
    for replacements in product(*choices):
        candidate = pieces[0]
        for replacement, suffix in zip(replacements, pieces[1:]):
            candidate += replacement + suffix
        candidate = re.sub(r"/+", "/", candidate).strip("/")
        if candidate:
            witnesses.add(candidate)
        if len(witnesses) >= 512:
            break
    return witnesses


def _task_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ConfigError("missing task ids")
    tasks: list[str] = []
    for raw_task_id in value:
        task_id = _scope_text(raw_task_id, "task id")
        if task_id in tasks:
            raise ConfigError(f"duplicate task id: {task_id}")
        tasks.append(task_id)
    return tuple(tasks)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"missing {label}")
    normalized = value.strip()
    if any(char in normalized for char in "\r\n\x00"):
        raise ConfigError(f"invalid {label}: control characters are not allowed")
    return normalized


def _scope_text(value: Any, label: str) -> str:
    try:
        return normalize_scope_identifier(_text(value, label), label=label)
    except ValueError as exc:
        raise ConfigError(f"invalid {label}: {exc}") from exc


def _resolve_path(value: Any, base: Path, label: str) -> Path:
    if isinstance(value, Path):
        path = value.expanduser()
    else:
        path_text = _text(value, label)
        path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


def _resolve_path_within(value: Any, base: Path, label: str) -> Path:
    path = _resolve_path(value, base, label)
    try:
        path.relative_to(base.resolve(strict=False))
    except ValueError as exc:
        raise ConfigError(f"{label} must be inside the project root: {path}") from exc
    return path


def _relative_path(path: Path, base: Path) -> str:
    path = path.resolve(strict=False)
    base = base.resolve(strict=False)
    try:
        relative = path.relative_to(base)
    except ValueError:
        return path.as_posix()
    return relative.as_posix() or "."


def _render_config(config: ProjectConfig) -> str:
    lines = [
        f"project_root = {json.dumps(_relative_path(config.project_root, config.config_path.parent))}",
        f"tenant_id = {json.dumps(config.tenant_id)}",
        f"memory_db = {json.dumps(_relative_path(config.memory_db, config.project_root))}",
        f"default_policy = {json.dumps(config.default_policy.value)}",
    ]
    if config.benchmark is None:
        return "\n".join(lines) + "\n"

    benchmark = config.benchmark
    lines.extend(
        [
            "",
            "[benchmark]",
            f"id = {json.dumps(benchmark.id)}",
            f"evaluation_subject = {json.dumps(benchmark.evaluation_subject)}",
            f"fixture = {json.dumps(_relative_path(benchmark.fixture, config.project_root))}",
            f"task_ids = {json.dumps(list(benchmark.task_ids))}",
        ]
    )
    if benchmark.protected_paths:
        lines.extend(["", "[benchmark.protected_paths]"])
        for task_id in sorted(benchmark.protected_paths):
            lines.append(
                f"{json.dumps(task_id)} = {json.dumps(list(benchmark.protected_paths[task_id]))}"
            )
    return "\n".join(lines) + "\n"
