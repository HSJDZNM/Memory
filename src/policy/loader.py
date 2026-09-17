"""规则加载器。

职责边界：只读取明确的规则目录，把 YAML 解析成不可变模型。

- 只扫描调用方显式给出的规则目录；
- 按规范化仓库相对路径排序，保证加载顺序稳定；
- 拒绝重复 ID、空 ID、未知严重级别、不支持的 enforcement；
- 错误信息必须包含文件路径与字段位置；
- 一次性原子替换：任何文件失败都不会留下半套规则。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

import yaml
from pydantic import ValidationError

from .models import Rule, RuleSet, RuleValidationError

__all__ = [
    "LoadedRule",
    "LoaderError",
    "RuleFileError",
    "collect_rule_files",
    "load_rule_file",
    "load_rule_set",
    "load_rules",
]

_SUPPORTED_SUFFIXES = frozenset({".yaml", ".yml"})


class LoaderError(Exception):
    """规则目录不可用或不含可加载规则。"""


class RuleFileError(LoaderError):
    """单个规则文件的问题：语法、结构、字段或重复 ID。"""

    def __init__(
        self,
        message: str,
        *,
        path: Path,
        repo_path: str,
        line: int | None = None,
        column: int | None = None,
        rule_id: str | None = None,
        field: str | None = None,
    ) -> None:
        location = repo_path
        if line is not None:
            location += f":{line}"
            if column is not None:
                location += f":{column}"
        detail = message if field is None else f"{field}: {message}"
        super().__init__(f"{location}: {detail}")
        self.path = path
        self.repo_path = repo_path
        self.line = line
        self.column = column
        self.rule_id = rule_id
        self.field = field


@dataclass(frozen=True)
class LoadedRule:
    """一条已加载的规则及其来源文件，用于审计与诊断。"""

    rule: Rule
    repo_path: str
    path: Path


def _relative_to_root(path: Path, root: Path, repo_root: Path | None) -> str:
    """把规则文件路径规范化为仓库相对路径；路径逃出仓库时直接失败。"""

    anchor = repo_root if repo_root is not None else root
    try:
        relative = path.resolve().relative_to(anchor.resolve())
    except ValueError as error:
        raise LoaderError(
            f"规则文件 {path} 不在规则目录 {anchor} 之内，拒绝加载"
        ) from error
    return relative.as_posix()


def collect_rule_files(
    root: Path | str, *, repo_root: Path | str | None = None
) -> tuple[Path, ...]:
    """收集规则目录下的 YAML 文件，按规范化相对路径排序。

    隐藏目录（以 "." 开头）与隐藏文件被跳过，避免把编辑器临时文件当成规则。
    """

    root_path = Path(root)
    if not root_path.exists():
        raise LoaderError(f"规则目录不存在: {root_path}")
    if not root_path.is_dir():
        raise LoaderError(f"规则目录不是目录: {root_path}")

    repo_anchor = Path(repo_root) if repo_root is not None else None
    discovered: list[tuple[str, Path]] = []
    try:
        for directory, dirnames, filenames in os.walk(root_path):
            dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
            for filename in sorted(filenames):
                if filename.startswith("."):
                    continue
                candidate = Path(directory) / filename
                if candidate.suffix.lower() not in _SUPPORTED_SUFFIXES:
                    continue
                discovered.append(
                    (_relative_to_root(candidate, root_path, repo_anchor), candidate)
                )
    except OSError as error:
        raise LoaderError(f"规则目录不可读: {root_path} ({error})") from error

    discovered.sort(key=lambda item: item[0])
    return tuple(path for _, path in discovered)


def _yaml_error(error: yaml.YAMLError, *, path: Path, repo_path: str) -> RuleFileError:
    mark = getattr(error, "problem_mark", None)
    problem = getattr(error, "problem", None) or str(error)
    line = None if mark is None else mark.line + 1
    column = None if mark is None else mark.column + 1
    return RuleFileError(
        f"YAML 解析失败：{problem}",
        path=path,
        repo_path=repo_path,
        line=line,
        column=column,
    )


def _read_mapping(path: Path, repo_path: str) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise LoaderError(f"{repo_path}: 无法读取规则文件 ({error})") from error

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise _yaml_error(error, path=path, repo_path=repo_path) from error

    if document is None:
        raise RuleFileError("规则文件为空", path=path, repo_path=repo_path)
    if not isinstance(document, dict):
        raise RuleFileError(
            f"规则文件顶层必须是映射，得到 {type(document).__name__}",
            path=path,
            repo_path=repo_path,
        )
    return document


def load_rule_file(
    path: Path | str,
    *,
    repo_path: str | None = None,
    repo_root: Path | str | None = None,
) -> LoadedRule:
    """加载单个规则文件。任何问题都抛出 RuleFileError。"""

    file_path = Path(path)
    if repo_path is None:
        anchor = Path(repo_root) if repo_root is not None else file_path.parent
        repo_path = _relative_to_root(file_path, anchor, anchor)
    if not file_path.is_file():
        raise LoaderError(f"{repo_path}: 规则文件不存在")

    document = _read_mapping(file_path, repo_path)
    try:
        rule = Rule.model_validate(document)
    except ValidationError as error:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ()))
        failure = RuleValidationError.from_pydantic(error, model_name=f"规则文件 {repo_path}")
        raise RuleFileError(
            str(failure),
            path=file_path,
            repo_path=repo_path,
            field=location or None,
            rule_id=document.get("id") if isinstance(document.get("id"), str) else None,
        ) from error

    return LoadedRule(rule=rule, repo_path=repo_path, path=file_path)


def load_rules(
    root: Path | str,
    *,
    repo_root: Path | str | None = None,
) -> tuple[LoadedRule, ...]:
    """加载规则目录下的全部规则；任一文件失败则整体失败（原子语义）。"""

    files = collect_rule_files(root, repo_root=repo_root)
    anchor = Path(repo_root) if repo_root is not None else None
    loaded: list[LoadedRule] = []
    for path in files:
        repo_path = _relative_to_root(path, Path(root), anchor)
        loaded.append(load_rule_file(path, repo_path=repo_path, repo_root=repo_root))
    assert_unique(loaded)
    return tuple(loaded)


def load_rule_set(
    roots: Sequence[Path | str] | Iterator[Path | str],
    *,
    repo_root: Path | str | None = None,
) -> RuleSet:
    """从多个根目录构建规则集；同一规则集内跨目录也禁止重复 ID。"""

    loaded: list[LoadedRule] = []
    for root in roots:
        loaded.extend(load_rules(root, repo_root=repo_root))
    assert_unique(loaded)
    ordered = sorted(loaded, key=lambda item: item.repo_path)
    return RuleSet(
        rules=tuple(item.rule for item in ordered),
        source_paths=tuple(item.repo_path for item in ordered),
    )


def assert_unique(loaded: Sequence[LoadedRule]) -> None:
    """拒绝规则 id 重复；同一 id 的语义变更必须递增 version，而不是并存两份。"""

    seen: dict[str, LoadedRule] = {}
    for item in loaded:
        previous = seen.get(item.rule.id)
        if previous is not None:
            raise RuleFileError(
                f"规则 id {item.rule.id} 重复：已由 {previous.repo_path} 定义",
                path=item.path,
                repo_path=item.repo_path,
                rule_id=item.rule.id,
                field="id",
            )
        seen[item.rule.id] = item


def iter_rules(rules: RuleSet) -> Iterator[Rule]:
    """按加载顺序遍历规则，便于测试与诊断。"""

    return iter(rules.rules)
