"""规则加载器。

职责边界：只读取明确的规则目录，把 YAML 解析成不可变模型。

- 只扫描调用方显式给出的规则目录；
- 按规范化仓库相对路径排序，保证加载顺序稳定；
- 拒绝重复 ID、空 ID、未知严重级别、不支持的 enforcement；
- 拒绝"用依赖类 checker 却没有声明 language 维度"的规则（见 assert_language_declared）；
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

from .models import WILDCARD, Rule, RuleSet, RuleValidationError, ScopeValue

__all__ = [
    "LoadedRule",
    "LoaderError",
    "RuleFileError",
    "assert_language_declared",
    "collect_rule_files",
    "load_rule_file",
    "load_rule_set",
    "load_rules",
]

_SUPPORTED_SUFFIXES = frozenset({".yaml", ".yml"})

# 依赖类 checker：判定完全建立在"依赖集"这一个维度上，因此它们的规则必须显式声明 language。
#
# 为什么这不是形式主义：依赖提取（adapters.textfacts.governed_dependencies）只在语言被
# **显式解析成 python** 时才可能给出非空依赖集；language 为 None（声明不出来）或不是 python
# 时结果都是空元组。于是"规则不声明 language"意味着它对任何上下文都相关，语言未知时
# 依赖集是空的，依赖类 checker 只能判 allow —— 而这个 allow 的理由（语言不知道）不会写进
# 决策的任何地方，它与"确实没有禁用依赖"逐字相同。
#
# 今天没有洞，只是因为 43 条规则里唯一用 forbidden_dependency 的 ARCH-001 恰好在 scope 里
# 写了 language: python：那是**规则作者的纪律**，不是代码保证。本检查把它变成加载期的失败。
# 新增依赖类 checker 时必须一起加到这里（engine 侧的分派表见 policy.checkers）。
_LANGUAGE_DEPENDENT_CHECKERS = frozenset({"forbidden_dependency"})


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

    def _on_walk_error(error: OSError) -> None:
        # os.walk 的 onerror 默认是 None：底层 scandir 失败（无权限、目录刚被删）会被
        # **静默忽略**，于是"规则目录里少读了几条"和"规则集本来就只有这几条"长得一模一样。
        # 规则集是判定的唯一依据，读不全就必须失败关闭（AGENTS.md 核心层约束第 3 条：
        # 未知一律报错，不得静默忽略）。
        raise LoaderError(f"规则目录不可读: {root_path} ({error})")

    try:
        for directory, dirnames, filenames in os.walk(root_path, onerror=_on_walk_error):
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


def _is_unrestricted(declared: ScopeValue) -> bool:
    """该维度的声明是否等于"显式不限制"（`*`，或含 `*` 的列表）。

    语义必须与 policy.scope 的匹配一致（那里是私有的 _is_wildcard）：含 `*` 的列表
    同样表示"这一维度不参与限制"，而不是"只匹配字面量 *"。
    """

    return declared == WILDCARD or (isinstance(declared, tuple) and WILDCARD in declared)


def assert_language_declared(loaded: LoadedRule) -> None:
    """依赖类 checker 的规则必须声明 language 维度；不声明或显式不限制都在加载期拒绝。

    为什么只能在加载期拦：判定期拿不到这个信息。依赖类 checker 看到的只有依赖集本身，
    "语言解析不出来"在那里与"这次改动没有依赖"是**同一种输入**（都是空元组），
    它没有可依据的东西去拒绝放行——那是构造上下文那一层才知道的事实。
    规则数据是唯一能在加载期被检查的地方，所以"记得写 language"这条纪律只能在这里
    变成会失败的检查（AGENTS.md 第 3、20 条：未知维度不得静默、证明不了不得放行）。

    边界（写下来，别假装全覆盖）：本检查拦住"不声明"与"显式 *"这两条静默路径。
    声明了具体语言时，语言不匹配会让规则**显式跳过**（skipped_rules 里写明 language
    不匹配），那不是静默；而"声明了多种语言、其中非 python 的那一段依赖集仍为空"
    属于依赖提取本身的边界（只有 python 有提取实现），不在这里判。
    """

    rule = loaded.rule
    if rule.enforcement.checker not in _LANGUAGE_DEPENDENT_CHECKERS:
        return
    declared = rule.scope.declared_dimensions.get("language")
    if declared is not None and not _is_unrestricted(declared):
        return
    shape = (
        "scope 里没有声明 language 维度"
        if declared is None
        else f"scope.language={declared!r} 等于「该维度不限制」（{WILDCARD}）"
    )
    raise RuleFileError(
        f"依赖类 checker（{rule.enforcement.checker}）的规则必须声明 language 维度，"
        f"本规则 {shape}：语言解析不出来时是 null，依赖集因此是空元组，"
        "依赖类 checker 只能静默放行 —— 而放行的理由（语言未知）不会出现在决策的"
        "任何位置，它与「确实没有禁用依赖」逐字相同。请显式声明该维度"
        "（例如 scope.language: python）。",
        path=loaded.path,
        repo_path=loaded.repo_path,
        rule_id=rule.id,
        field="scope.language",
    )


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

    loaded = LoadedRule(rule=rule, repo_path=repo_path, path=file_path)
    # 加载期语义检查（不是格式检查）：不满足就无法安全判定，宁可整份规则集读不进来。
    assert_language_declared(loaded)
    return loaded


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
