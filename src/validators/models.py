"""验证器注册表的数据模型：validation/*.yaml 的形状。

注册表是数据：谁能产生证据、在哪个阶段跑、用哪个工具、超时多久、缺工具时算不算失败关闭，
全部写在 YAML 里；代码只负责解释它。未知字段、未知阶段、未知验证器引用一律在加载阶段报错——
配置写错不能让门禁悄悄少跑一个验证器。
"""

from __future__ import annotations

import re
from typing import Literal, Mapping, Optional, Tuple

from pydantic import Field, field_validator, model_validator

from policy.evidence import ValidatorKind
from policy.models import (
    PolicyContextError,
    StrictModel,
    canonical_identifier,
    normalize_repo_path,
)

__all__ = [
    "KNOWN_FACTS",
    "KNOWN_PLACEHOLDERS",
    "ComponentSpec",
    "EscalationLevel",
    "LanguageSpec",
    "ProjectProfile",
    "Registry",
    "RegistryDefaults",
    "RulePack",
    "TestLayout",
    "TestLimits",
    "ToolSpec",
    "UncoveredLanguage",
    "ValidatorSpec",
]

# 验证器可以声明提供的"事实"种类（受控枚举：拼错就是配置错误，不是"少提供一点"）。
KNOWN_FACTS = frozenset({"source", "syntax", "imports", "calls", "dependencies"})

# 外部工具命令行里允许出现的占位符。argv 必须与声明逐字一致（占位符除外），
# 因此"多传一个参数"不是运行时自由，而是加载阶段就失败。
KNOWN_PLACEHOLDERS = {
    "{python}": "当前解释器（sys.executable）",
    "{target}": "受验证文件的绝对路径",
    "{paths}": "按受验证文件与工作区展开的路径参数",
    "{nodeids}": "测试选择得到的 node id",
    "{workspace}": "工作区根目录的绝对路径",
    "{config}": "工具配置文件（ToolSpec.config 的绝对路径）",
    "{tmp}": "本次运行专属的临时目录",
}

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9]+)*$")
_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.\-+]*$")
_PLACEHOLDER_RE = re.compile(r"\{[a-z]+\}")


def _check_identifier(value: str, *, field: str) -> str:
    normalized = value.strip().lower()
    if not _IDENTIFIER_RE.match(normalized):
        raise ValueError(f"{field} 必须形如 py.ast / tool.ruff（小写点分标识），得到 {value!r}")
    return normalized


def _check_placeholders(values: Tuple[str, ...], *, field: str, allow: Tuple[str, ...]) -> None:
    for item in values:
        for match in _PLACEHOLDER_RE.finditer(item):
            if match.group(0) not in allow:
                raise ValueError(
                    f"{field} 里出现未知占位符 {match.group(0)}；"
                    f"允许的占位符为 {sorted(KNOWN_PLACEHOLDERS)}"
                )
        if _PLACEHOLDER_RE.sub("", item) == "" and item not in allow:
            raise ValueError(f"{field} 不能只有占位符：{item!r}")


class ToolSpec(StrictModel):
    """外部工具适配器的固定参数：命令、版本探测、参数 allowlist、配置与输出上限。"""

    command: Tuple[str, ...] = Field(min_length=1, description="基础命令，例如 [ruff]")
    version_args: Tuple[str, ...] = ("--version",)
    version_pattern: str = r"(\d+\.\d+[0-9A-Za-z.\-+]*)"
    version_requirement: str = Field(default="", description='例如 ">=0.6,<1"；空表示不限制')
    argv: Tuple[str, ...] = Field(default=(), description="除基础命令外的固定参数（可含占位符）")
    config: Optional[str] = Field(default=None, description="配置文件（仓库相对路径，必须存在）")
    analysis_failure_codes: Tuple[str, ...] = Field(
        default=(),
        description=(
            "工具诊断里表示「本次分析不成立」的码；命中即失败关闭（不是「没有发现问题」）。"
            "码表是数据：换工具版本、换码都改这里，不在适配器里硬编码"
        ),
    )
    description: str = ""

    @field_validator("command")
    @classmethod
    def _check_command(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        # all 而不是 any：any 只要有一个非空就放行，于是 ("ruff", "") 这种带空元素的 argv
        # 能过检查——而错误信息说的正是"不能有空元素"（复核发现）。空白串同样算空。
        if not all(item.strip() for item in values):
            raise ValueError("tool.command 不能有空元素")
        _check_placeholders(values, field="tool.command", allow=("{python}",))
        return values

    @field_validator("argv")
    @classmethod
    def _check_argv(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        _check_placeholders(values, field="tool.argv", allow=tuple(KNOWN_PLACEHOLDERS))
        return values

    @field_validator("version_pattern")
    @classmethod
    def _check_pattern(cls, value: str) -> str:
        try:
            compiled = re.compile(value)
        except re.error as error:
            raise ValueError(f"tool.version_pattern 不是合法正则：{error}") from None
        if compiled.groups < 1:
            raise ValueError("tool.version_pattern 必须包含一个捕获组，用于取出工具版本")
        return value

    @field_validator("analysis_failure_codes")
    @classmethod
    def _check_analysis_failure_codes(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        """名单本身也要合法：空码与重复码（大小写不敏感）都是配置错误。"""

        seen: set[str] = set()
        for item in values:
            token = str(item).strip()
            if not token:
                raise ValueError("tool.analysis_failure_codes 里不能有空码")
            key = token.upper()
            if key in seen:
                raise ValueError(
                    "tool.analysis_failure_codes 出现重复码 " + token + "（比较时大小写不敏感）"
                )
            seen.add(key)
        return values

    @field_validator("config")
    @classmethod
    def _check_config(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        # 与消费方同一条口径（policy.models.normalize_repo_path）：反斜杠 / 盘符 / UNC /
        # ".." / 路径元字符都在这里被拒，返回的也是归一化之后的形态——校验看到的路径必须与
        # 后面交给外部工具的那一个逐字节相同。旧实现只查前导 "/" 与精确的 ".." 段：
        # C:/tools/ruff.toml 与 C:../x.toml（"C:.." 不是一个 ".." 段）都被当成仓库相对路径，
        # 随后作为**工具配置**交给外部工具，等于让仓库外的文件当受控配置。
        try:
            return normalize_repo_path(value)
        except PolicyContextError as error:
            raise ValueError(f"tool.config 必须是仓库内的相对路径：{error}") from error


class ValidatorSpec(StrictModel):
    """一个验证器的声明：它是谁、在哪个阶段、为哪些 checker 提供证据、依赖谁。"""

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: ValidatorKind
    stage: str = Field(min_length=1)
    checkers: Tuple[str, ...] = ()
    facts: Tuple[str, ...] = ()
    requires: Tuple[str, ...] = ()
    critical: bool = True
    timeout_ms: Optional[int] = Field(default=None, ge=1)
    max_output_bytes: Optional[int] = Field(default=None, ge=1)
    description: str = ""
    tool: Optional[ToolSpec] = None

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        return _check_identifier(value, field="validators[].id")

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        normalized = value.strip()
        if not _VERSION_RE.match(normalized):
            raise ValueError(f"validators[].version 必须是版本串，得到 {value!r}")
        return normalized

    @field_validator("stage")
    @classmethod
    def _check_stage(cls, value: str) -> str:
        return _check_identifier(value, field="validators[].stage")

    @field_validator("checkers", "facts", "requires", mode="before")
    @classmethod
    def _check_sequence(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        return tuple(value)

    @field_validator("facts")
    @classmethod
    def _check_facts(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        unknown = sorted(set(values) - KNOWN_FACTS)
        if unknown:
            raise ValueError(f"未知 fact {unknown}；受支持的事实种类为 {sorted(KNOWN_FACTS)}")
        return tuple(sorted(set(values)))

    @model_validator(mode="after")
    def _kind_matches_tool(self) -> "ValidatorSpec":
        if self.kind is ValidatorKind.EXTERNAL and self.tool is None:
            raise ValueError(f"{self.id}: kind=external 必须声明 tool")
        if self.kind is ValidatorKind.BUILTIN and self.tool is not None:
            raise ValueError(f"{self.id}: kind=builtin 不能声明 tool（内置验证器不调用外部命令）")
        if self.id in self.requires:
            raise ValueError(f"{self.id}: requires 不能引用自己")
        return self


class RegistryDefaults(StrictModel):
    """全局默认值：单个验证器没写时按这些值执行。"""

    timeout_ms: int = Field(default=10000, ge=1)
    max_output_bytes: int = Field(default=262144, ge=1)
    max_source_bytes: int = Field(default=1048576, ge=1)
    max_message_chars: int = Field(default=500, ge=16)
    max_evidence: int = Field(default=200, ge=1)
    max_parallel: int = Field(default=2, ge=1, le=8)
    probe_timeout_ms: int = Field(default=5000, ge=1)


class RulePack(StrictModel):
    """语言 → 验证器集合：新增语言只加一个 rule pack 与相应 Adapter，核心不改。"""

    id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    validators: Tuple[str, ...] = Field(min_length=1)
    description: str = ""

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _PACK_ID_RE.match(normalized):
            raise ValueError(
                f"rule_packs[].id 必须形如 python-core（小写短横线分段），得到 {value!r}"
            )
        return normalized

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("rule_packs[].language 不能为空")
        return normalized


class UncoveredLanguage(StrictModel):
    """「按设计不取证」的语言：平台**显式**声明"这门语言没有 rule pack，也不打算验证它"。

    存在的理由（07 号报告 P2）：只有 python 有 rule pack 时，任何非 python 目标在取证路径上
    只能得到 `RegistryError`（→ `evidence_unavailable` → 退出码 2）——连"本次没有任何规则
    需要验证器证据"的文档写入也被一并拦下。失败关闭本身没错（AGENTS 第 20/42 条），
    错的是**没有地方表达**这件事。

    声明的形态是数据而不是代码里的 if 分支（AGENTS 第 2/21 条），因此 `reason` 是必填的：
    空理由等于把"平台为什么不查这门语言"重新变成不可读，评审就无从谈起。
    """

    language: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("uncovered_languages[].language 不能为空")
        return normalized

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(
                "uncovered_languages[].reason 不能为空："
                "「按设计不取证」必须给出可被评审的理由"
            )
        return normalized


class Registry(StrictModel):
    """完整的验证器注册表。"""

    version: int = Field(ge=1)
    schema_id: str = Field(min_length=1, description="数据文件协议标识，例如 validator-registry/1")
    defaults: RegistryDefaults = RegistryDefaults()
    stages: Tuple[str, ...] = Field(min_length=1)
    rule_packs: Tuple[RulePack, ...] = ()
    uncovered_languages: Tuple[UncoveredLanguage, ...] = ()
    validators: Tuple[ValidatorSpec, ...] = Field(min_length=1)

    def stage_index(self) -> Mapping[str, int]:
        return {name: index for index, name in enumerate(self.stages)}

    def spec(self, validator_id: str) -> Optional[ValidatorSpec]:
        for item in self.validators:
            if item.id == validator_id:
                return item
        return None

    def packs_for(self, language: str) -> Tuple[RulePack, ...]:
        token = canonical_identifier(language)
        return tuple(pack for pack in self.rule_packs if pack.language == token)

    def uncovered(self, language: str) -> Optional[UncoveredLanguage]:
        """该语言是否被声明为"按设计不取证"；没声明返回 None（调用方按失败关闭处理）。"""

        token = canonical_identifier(language)
        for item in self.uncovered_languages:
            if item.language == token:
                return item
        return None

    def validators_for_language(self, language: str) -> Tuple[ValidatorSpec, ...]:
        """该语言启用的验证器，按阶段顺序（同阶段按 id）稳定排列。"""

        index = self.stage_index()
        names = sorted({name for pack in self.packs_for(language) for name in pack.validators})
        specs = [spec for spec in (self.spec(name) for name in names) if spec is not None]
        return tuple(
            sorted(specs, key=lambda item: (index.get(item.stage, len(index)), item.id))
        )

    def checkers_for_language(self, language: str) -> Mapping[str, Tuple[str, ...]]:
        """checker → 为该语言提供证据的验证器（按阶段顺序）。"""

        mapping: dict[str, list[str]] = {}
        for spec in self.validators_for_language(language):
            for checker in spec.checkers:
                mapping.setdefault(checker, []).append(spec.id)
        return {key: tuple(value) for key, value in sorted(mapping.items())}


class ComponentSpec(StrictModel):
    """路径模式 → 架构组件（层）。只有数据说了算，不从文件名猜。"""

    name: str = Field(min_length=1)
    match: Tuple[str, ...] = Field(min_length=1)
    description: str = ""

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        return canonical_identifier(value)


class LanguageSpec(StrictModel):
    """路径模式 → 语言。语言是数据：新增语言只加一行，核心流水线里没有语言分支。"""

    language: str = Field(min_length=1)
    pattern: Tuple[str, ...] = Field(min_length=1)

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("languages[].language 不能为空")
        return normalized


class ProjectProfile(StrictModel):
    """项目档案：语言识别、模块解析根与"路径 → 架构组件"的映射。

    这些必须是数据而不是代码里的 if：语言识别错了会让语言专项规则在错误的文件上生效，
    组件映射错了会让依赖规则判错对象。
    """

    version: int = Field(ge=1)
    schema_id: str = Field(min_length=1, description="数据文件协议标识，例如 project-profile/1")
    languages: Tuple[LanguageSpec, ...] = ()
    python_roots: Tuple[str, ...] = (".",)
    unmatched: Literal["top_level_package"] = "top_level_package"
    components: Tuple[ComponentSpec, ...] = ()

    @field_validator("python_roots")
    @classmethod
    def _check_python_roots(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        """模块解析根必须是**项目内**的相对目录（"." = 项目根本身）。

        与消费方同一条口径（policy.models.normalize_repo_path，allow_root=True）：反斜杠、
        盘符、UNC、".." 与路径元字符都在加载期被拒，而且**存下来的值是归一化之后的形态**
        ——pipeline 随后做 request.workspace / root，校验与使用必须看到同一个字符串
        （复核发现：旧守卫只在加载器里查前导 "/" 与按 "/" 切的 ".."，于是
        ..\\..\\outside 与 C:\\outside 都能过）。
        """

        normalized: list[str] = []
        for item in values:
            try:
                normalized.append(normalize_repo_path(str(item), allow_root=True))
            except PolicyContextError as error:
                raise ValueError(f"python_roots 必须是项目内的相对目录：{error}") from error
        return tuple(normalized)

    def language_for(self, path: str) -> Optional[str]:
        from .globs import glob_match

        for spec in self.languages:
            for pattern in spec.pattern:
                if glob_match(pattern, path):
                    return spec.language
        return None

    def component_for(self, path: str) -> Optional[str]:
        """按声明顺序匹配第一个命中的组件；没有命中返回 None（调用方决定用什么名字）。"""

        from .globs import glob_match

        for component in self.components:
            for pattern in component.match:
                if glob_match(pattern, path):
                    return component.name
        return None


class EscalationLevel(StrictModel):
    """测试选择的相关性层级：从窄到宽，相关性不足时升级。"""

    level: Literal["related", "package", "suite"]
    match: Tuple[str, ...] = Field(min_length=1)
    description: str = ""


class TestLimits(StrictModel):
    """测试进程的硬限制：node id 数量、超时与输出上限。"""

    max_nodeids: int = Field(default=40, ge=1)
    timeout_ms: int = Field(default=120000, ge=1)
    max_output_bytes: int = Field(default=262144, ge=1)


class TestLayout(StrictModel):
    """生产文件与测试文件的对应关系，以及测试进程的资源上限。"""

    version: int = Field(ge=1)
    schema_id: str = Field(min_length=1, description="数据文件协议标识，例如 validator-registry/1")
    language: str = Field(min_length=1)
    production_patterns: Tuple[str, ...] = Field(min_length=1)
    test_patterns: Tuple[str, ...] = Field(min_length=1)
    escalation: Tuple[EscalationLevel, ...] = ()
    limits: TestLimits = TestLimits()

    def is_production(self, path: str) -> bool:
        from .globs import glob_match

        return any(glob_match(pattern, path) for pattern in self.production_patterns)

    def is_test(self, path: str) -> bool:
        from .globs import glob_match

        return any(glob_match(pattern, path) for pattern in self.test_patterns)
