"""验证器注册表与项目档案的加载。

三份数据文件（都在 validation/ 下）：

- validators.yaml：验证器注册表（阶段、checker、工具、超时、失败关闭）；
- project.yaml：语言识别、模块解析根与"路径 → 架构组件"的映射；
- test-layout.yaml：生产文件 ↔ 测试文件的对应关系与测试进程上限。

加载语义与规则加载器一致：原子、拒绝未知字段、拒绝重复 ID、错误信息带文件与字段位置。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, FrozenSet, Mapping, Optional

import yaml
from pydantic import ValidationError

from policy.checkers import SUPPORTED_CHECKERS
from policy.models import RuleValidationError

from .models import ProjectProfile, Registry, TestLayout, ValidatorSpec

__all__ = [
    "ANALYSIS_FAILURE_AWARE_VALIDATORS",
    "DEFAULT_PROJECT",
    "DEFAULT_REGISTRY",
    "DEFAULT_TEST_LAYOUT",
    "RegistryError",
    "ValidationConfig",
    "config_digest",
    "load_config",
    "load_project",
    "load_registry",
    "load_test_layout",
    "repo_root",
]

DEFAULT_REGISTRY = "validation/validators.yaml"
DEFAULT_PROJECT = "validation/project.yaml"
DEFAULT_TEST_LAYOUT = "validation/test-layout.yaml"

# 能声明 tool.analysis_failure_codes 的验证器：实现里真的会读这份名单的那些。
# **数据声明的能力必须有实现承接**——否则某个工具写上一串"本次分析不成立"的码却没人读，
# 就又造出一个"看起来在管、实际什么都没查"。新增一个工具支持它时，同时改这里与对应适配器。
ANALYSIS_FAILURE_AWARE_VALIDATORS: FrozenSet[str] = frozenset({"tool.ruff"})


class RegistryError(Exception):
    """注册表或项目档案不可用、不一致（失败策略：配置错误 → 退出码 2 / 失败关闭）。"""


def repo_root() -> Path:
    """仓库根目录：从本模块位置向上回溯到含 validation/ 或 .git 的目录。"""

    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "validation").is_dir() or (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RegistryError(f"{path}: 无法读取配置文件 ({error})") from error

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = "" if mark is None else f":{mark.line + 1}:{mark.column + 1}"
        raise RegistryError(f"{path}{location}: YAML 解析失败：{error}") from error

    if document is None:
        raise RegistryError(f"{path}: 配置文件为空")
    if not isinstance(document, dict):
        raise RegistryError(f"{path}: 顶层必须是映射，得到 {type(document).__name__}")
    return document


def _validate(model: Any, document: Mapping[str, Any], *, path: Path, label: str) -> Any:
    try:
        return model.model_validate(dict(document))
    except ValidationError as error:
        failure = RuleValidationError.from_pydantic(error, model_name=f"{label} {path}")
        raise RegistryError(str(failure)) from error


def config_digest(path: Path | str | None) -> Optional[str]:
    """配置文件的 sha256（带 sha256: 前缀）；没有配置时返回 None。"""

    if path is None:
        return None
    target = Path(path)
    if not target.is_file():
        return None
    return "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()


def _assert_unique(names: list[str], *, path: Path, label: str) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise RegistryError(f"{path}: {label} 出现重复 ID {name!r}")
        seen.add(name)


def _check_registry(registry: Registry, *, path: Path, root: Path) -> None:
    """注册表的跨字段不变量：任何一条不满足都拒绝加载。"""

    stages = registry.stages
    _assert_unique(list(stages), path=path, label="stages")
    stage_index = registry.stage_index()

    _assert_unique([item.id for item in registry.validators], path=path, label="validators")
    _assert_unique([item.id for item in registry.rule_packs], path=path, label="rule_packs")
    _assert_unique(
        [item.language for item in registry.uncovered_languages],
        path=path,
        label="uncovered_languages",
    )

    # 自相矛盾必须报错：同一个语言既有 rule pack、又被声明为"按设计不取证"。
    # 放过去的话，"不取证"会被 rule pack 悄悄覆盖（或者反过来），两种读法都能自称合规。
    covered = {pack.language for pack in registry.rule_packs}
    contradictions = sorted({item.language for item in registry.uncovered_languages} & covered)
    if contradictions:
        raise RegistryError(
            f"{path}: uncovered_languages 与 rule_packs 自相矛盾：{contradictions} "
            "既有 rule pack 又声明「按设计不取证」；要么给它 rule pack，要么别声明它不取证"
        )

    by_id = {item.id: item for item in registry.validators}
    # 第一遍先把**所有** spec 的阶段合法性查完，再查依赖顺序：依赖顺序那一遍要读
    # `stage_index[target.stage]`，而 target 可能是列表里**靠后**的那一条（它的阶段
    # 在单遍循环里还没被查过）。不先查完，"被依赖者声明了未定义的阶段"就会在那一行
    # 抛裸 KeyError——加载期的配置错误变成未处理异常，退出码与错误分类都丢了，
    # 而本函数承诺的是"任何一条不满足都拒绝加载"。
    for spec in registry.validators:
        if spec.stage not in stage_index:
            raise RegistryError(
                f"{path}: {spec.id} 声明了未定义的阶段 {spec.stage!r}；已声明的阶段为 {list(stages)}"
            )
    for spec in registry.validators:
        unknown = sorted(set(spec.checkers) - SUPPORTED_CHECKERS)
        if unknown:
            raise RegistryError(
                f"{path}: {spec.id} 声明了引擎不认识的 checker {unknown}；"
                f"受支持的 checker 为 {sorted(SUPPORTED_CHECKERS)}"
            )
        for required in spec.requires:
            target = by_id.get(required)
            if target is None:
                raise RegistryError(f"{path}: {spec.id} 依赖未声明的验证器 {required!r}")
            if stage_index[target.stage] >= stage_index[spec.stage]:
                raise RegistryError(
                    f"{path}: {spec.id}（阶段 {spec.stage}）依赖 {required}"
                    f"（阶段 {target.stage}）；依赖必须先于依赖者执行"
                )
        if spec.tool is not None and spec.tool.config is not None:
            config_path = root / spec.tool.config
            if not config_path.is_file():
                raise RegistryError(
                    f"{path}: {spec.id} 声明的工具配置不存在：{spec.tool.config}"
                    "（配置读不到属于配置错误，不允许静默用默认配置跑）"
                )
        if (
            spec.tool is not None
            and spec.tool.analysis_failure_codes
            and spec.id not in ANALYSIS_FAILURE_AWARE_VALIDATORS
        ):
            raise RegistryError(
                f"{path}: {spec.id} 声明了 tool.analysis_failure_codes，但实现里没有适配器读它"
                f"（目前支持：{sorted(ANALYSIS_FAILURE_AWARE_VALIDATORS)}）；"
                "要么实现检测，要么别声明——声明了没人读的名单等于没查"
            )
        if spec.tool is not None and not spec.tool.argv and spec.tool.version_args:
            raise RegistryError(
                f"{path}: {spec.id} 的外部工具没有声明 argv；参数必须来自 allowlist，不能自由拼"
            )

    for pack in registry.rule_packs:
        for name in pack.validators:
            if name not in by_id:
                raise RegistryError(f"{path}: rule pack {pack.id} 引用了未声明的验证器 {name!r}")

    declared = {checker for spec in registry.validators for checker in spec.checkers}
    missing = sorted(SUPPORTED_CHECKERS - declared)
    if missing:
        raise RegistryError(
            f"{path}: 这些 checker 没有任何验证器声明为它们提供证据：{missing}；"
            "规则一旦用到它们就只能失败关闭，因此在加载阶段就报错"
        )

    # 注册表是数据，但不是任意数据：声明了实现里没有的验证器 id 就是配置错误。
    # 函数内导入避免与 pipeline 形成模块级环（pipeline 依赖本模块）。
    from .pipeline import KNOWN_VALIDATOR_IDS

    ghost = sorted({spec.id for spec in registry.validators} - set(KNOWN_VALIDATOR_IDS))
    if ghost:
        raise RegistryError(
            f"{path}: 这些验证器在实现里不存在：{ghost}；"
            f"当前实现支持 {sorted(KNOWN_VALIDATOR_IDS)}（见 AGENTS 核心约束 21）"
        )


def load_registry(
    path: Path | str | None = None, *, root: Path | str | None = None
) -> Registry:
    """加载并校验验证器注册表。"""

    anchor = Path(root) if root is not None else repo_root()
    target = Path(path) if path is not None else anchor / DEFAULT_REGISTRY
    document = _read_mapping(target)
    registry = _validate(Registry, document, path=target, label="验证器注册表")
    _check_registry(registry, path=target, root=anchor)
    return registry


def load_project(
    path: Path | str | None = None, *, root: Path | str | None = None
) -> ProjectProfile:
    """加载项目档案（语言识别、模块根、组件映射）。"""

    anchor = Path(root) if root is not None else repo_root()
    target = Path(path) if path is not None else anchor / DEFAULT_PROJECT
    document = _read_mapping(target)
    profile = _validate(ProjectProfile, document, path=target, label="项目档案")
    _assert_unique([item.name for item in profile.components], path=target, label="components")
    _assert_unique(
        [item.language for item in profile.languages], path=target, label="languages"
    )
    # python_roots 的合法性由模型校验（ProjectProfile._check_python_roots，与消费方同口径）：
    # 这里不再重复一遍较弱的检查——两处口径只会漂移。
    return profile


def load_test_layout(
    path: Path | str | None = None, *, root: Path | str | None = None
) -> TestLayout:
    anchor = Path(root) if root is not None else repo_root()
    target = Path(path) if path is not None else anchor / DEFAULT_TEST_LAYOUT
    document = _read_mapping(target)
    layout = _validate(TestLayout, document, path=target, label="测试布局")
    _assert_unique([item.level for item in layout.escalation], path=target, label="escalation")
    return layout


@dataclass(frozen=True)
class ValidationConfig:
    """一次运行用到的全部配置，以及它们的来源路径（证据里要能追溯）。"""

    root: Path
    registry: Registry
    registry_path: Path
    project: ProjectProfile
    project_path: Path
    layout: TestLayout
    layout_path: Path

    def spec(self, validator_id: str) -> Optional[ValidatorSpec]:
        return self.registry.spec(validator_id)

    def config_path(self, spec: ValidatorSpec) -> Optional[Path]:
        if spec.tool is None or spec.tool.config is None:
            return None
        return self.root / spec.tool.config


def load_config(
    *,
    root: Path | str | None = None,
    registry: Path | str | None = None,
    project: Path | str | None = None,
    test_layout: Path | str | None = None,
) -> ValidationConfig:
    """一次加载三份数据；任何一份失败都不返回半个配置（原子语义）。"""

    anchor = Path(root) if root is not None else repo_root()
    registry_path = Path(registry) if registry is not None else anchor / DEFAULT_REGISTRY
    project_path = Path(project) if project is not None else anchor / DEFAULT_PROJECT
    layout_path = Path(test_layout) if test_layout is not None else anchor / DEFAULT_TEST_LAYOUT
    return ValidationConfig(
        root=anchor,
        registry=load_registry(registry_path, root=anchor),
        registry_path=registry_path,
        project=load_project(project_path, root=anchor),
        project_path=project_path,
        layout=load_test_layout(layout_path, root=anchor),
        layout_path=layout_path,
    )
