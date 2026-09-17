"""Tool Registry：数据化的工具授权表 + 已审核哈希校验。

三个职责，边界严格：

1. **加载与校验**：读显式给出的注册表 YAML（拒绝重复键、未知字段、未知枚举），
   把它变成不可变的 ToolSpec 集合；任何结构性错误都抛 RegistryError（配置错误 → 退出码 2）。
2. **已审核哈希**：注册表是运行时描述，它必须与一份独立的审核产物
   （registry/tool-registry.approved.json，由 `python -m enforcement.cli registry --approve`
   显式重写）逐条对齐。不一致的工具**不可使用**：模型改了工具描述、或者有人手动改了参数表，
   都不会悄悄生效。
3. **权限解析**：角色 → 权限的映射同样写在注册表里；未知角色不授予任何权限。

这里刻意不导入 adapters：核心层不知道 dsh 的存在，注册表只是数据。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml

from policy.models import canonical_identifier

from .models import (
    REGISTRY_SCHEMA_VERSION,
    SUPPORTED_REGISTRY_SCHEMA_VERSIONS,
    RegistryError,
    ToolSpec,
    digest_of,
    to_timestamp,
    utc_now,
)

__all__ = [
    "APPROVED_SCHEMA_VERSION",
    "DEFAULT_APPROVED_PATH",
    "DEFAULT_REGISTRY_PATH",
    "ApprovedTool",
    "LoadedRegistry",
    "ToolRegistry",
    "approve_registry",
    "load_registry",
    "load_registry_document",
    "registry_document_from_mapping",
    "write_approved",
]

APPROVED_SCHEMA_VERSION = "1.0"
DEFAULT_REGISTRY_PATH = "registry/tool-registry.yaml"
DEFAULT_APPROVED_PATH = "registry/tool-registry.approved.json"

_REGISTRY_FIELDS = (
    "registry_schema_version",
    "version",
    "defaults",
    "permissions",
    "roles",
    "approvals",
    "tools",
)
_DEFAULT_FIELDS = ("timeout_ms", "grant_ttl_seconds", "max_grant_ttl_seconds")


class _StrictLoader(yaml.SafeLoader):
    """拒绝重复键的 YAML 加载器：策略配置不得有歧义。"""


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> Any:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"发现重复键 {key!r}：工具注册表不得有歧义",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _require(mapping: Mapping[str, Any], key: str, *, where: str) -> Any:
    if key not in mapping:
        raise RegistryError(f"{where} 缺少必需字段 {key!r}")
    return mapping[key]


def _as_mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RegistryError(f"{where} 必须是映射，得到 {type(value).__name__}")
    return value


def _as_token_mapping(value: Any, *, where: str) -> dict[str, tuple[str, ...]]:
    mapping = _as_mapping(value, where=where)
    parsed: dict[str, tuple[str, ...]] = {}
    for raw_key, raw_items in mapping.items():
        key = canonical_identifier(str(raw_key))
        if not key:
            raise RegistryError(f"{where} 出现空键")
        if not isinstance(raw_items, (list, tuple)) or not raw_items:
            raise RegistryError(f"{where}.{key} 必须是非空列表")
        items: list[str] = []
        for item in raw_items:
            if not isinstance(item, str) or not item.strip():
                raise RegistryError(f"{where}.{key} 的值必须是非空字符串，得到 {item!r}")
            canonical = canonical_identifier(item)
            if canonical in items:
                raise RegistryError(f"{where}.{key} 出现重复值 {item!r}")
            items.append(canonical)
        parsed[key] = tuple(items)
    return parsed


@dataclass(frozen=True)
class ToolRegistry:
    """一份已加载的工具注册表。

    approved 里的哈希是**上一次人工审核**的结果；工具是否可用取决于两者是否一致。
    """

    path: str
    version: int
    tools: tuple[ToolSpec, ...]
    permissions: Mapping[str, str]
    roles: Mapping[str, tuple[str, ...]]
    approval_role: str
    default_timeout_ms: int = 5000
    grant_ttl_seconds: int = 60
    max_grant_ttl_seconds: int = 300
    approved: Mapping[str, str] = None  # type: ignore[assignment]
    approved_metadata: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.approved is None:
            object.__setattr__(self, "approved", {})
        if self.approved_metadata is None:
            object.__setattr__(self, "approved_metadata", {})

    def tool(self, tool_id: str) -> Optional[ToolSpec]:
        for spec in self.tools:
            if spec.id == tool_id:
                return spec
        return None

    def tool_by_name(self, agent: str, tool_name: str) -> Optional[ToolSpec]:
        """按（Agent, 工具名）解析工具；同名多工具属于注册表缺陷，加载阶段已拒绝。"""

        agent_token = canonical_identifier(agent)
        name_token = tool_name.strip()
        for spec in self.tools:
            if canonical_identifier(spec.agent) == agent_token and spec.tool_name == name_token:
                return spec
        return None

    def approval_reason(self, spec: ToolSpec) -> str:
        """工具不可用时的原因；可用时返回空串。"""

        recorded = self.approved.get(spec.id)
        if recorded is None:
            return (
                f"{spec.id}: 已审核清单里没有这条工具（或审核清单缺失）。"
                "运行时描述与已审核哈希不一致时拒绝使用："
                "请先复核 registry/tool-registry.yaml，再运行 "
                "enforcement.cli registry --approve --reviewer <name>"
            )
        if recorded != spec.schema_hash:
            return (
                f"{spec.id}: 工具描述哈希与已审核值不一致"
                f"（当前 {spec.schema_hash}，已审核 {recorded}）："
                "参数表 / 权限 / 风险级别被改动过，必须先重新审核"
            )
        return ""

    def is_approved(self, spec: ToolSpec) -> bool:
        return not self.approval_reason(spec)

    def permissions_for(self, roles: Sequence[str]) -> tuple[str, ...]:
        """角色 → 权限。未知角色不授予任何权限（失败关闭），并由调用方记录原因。"""

        granted: set[str] = set()
        for role in roles:
            granted.update(self.roles.get(canonical_identifier(role), ()))
        return tuple(sorted(granted))

    def unknown_roles(self, roles: Sequence[str]) -> tuple[str, ...]:
        return tuple(
            sorted(role for role in roles if canonical_identifier(role) not in self.roles)
        )

    @property
    def identity(self) -> str:
        """注册表身份：全部工具描述 + 角色/权限表，与工具声明顺序无关。"""

        return digest_of(self.registry_payload())

    def registry_payload(self) -> dict[str, Any]:
        return {
            "registry_schema_version": REGISTRY_SCHEMA_VERSION,
            "version": self.version,
            "permissions": dict(sorted(self.permissions.items())),
            "roles": {key: list(value) for key, value in sorted(self.roles.items())},
            "approvals": {"require_role": self.approval_role},
            "defaults": {
                "timeout_ms": self.default_timeout_ms,
                "grant_ttl_seconds": self.grant_ttl_seconds,
                "max_grant_ttl_seconds": self.max_grant_ttl_seconds,
            },
            "tools": [spec.approved_payload() for spec in sorted(self.tools, key=lambda s: s.id)],
        }

    def approval_role_members(self) -> tuple[str, ...]:
        """持有 repo.approve 权限的角色：审批记录的授予者必须属于其中之一。"""

        return tuple(sorted(role for role, perms in self.roles.items() if "repo.approve" in perms))


@dataclass(frozen=True)
class LoadedRegistry:
    registry: ToolRegistry
    document: Mapping[str, Any]
    approved_document: Mapping[str, Any]
    approved_path: Optional[Path]


def registry_document_from_mapping(document: Mapping[str, Any]) -> ToolRegistry:
    """把注册表映射解析成 ToolRegistry（不含已审核哈希）。"""

    if not isinstance(document, Mapping):
        raise RegistryError(f"工具注册表必须是映射，得到 {type(document).__name__}")

    unknown = sorted(set(document) - set(_REGISTRY_FIELDS))
    if unknown:
        raise RegistryError(
            f"工具注册表出现未知字段 {unknown}；允许的字段为 {sorted(_REGISTRY_FIELDS)}"
        )

    schema_version = str(
        _require(document, "registry_schema_version", where="工具注册表")
    ).strip()
    if schema_version not in SUPPORTED_REGISTRY_SCHEMA_VERSIONS:
        raise RegistryError(
            f"未知注册表协议版本 {schema_version!r}；只接受 "
            f"{sorted(SUPPORTED_REGISTRY_SCHEMA_VERSIONS)}，拒绝按旧口径解释权限"
        )

    version = _require(document, "version", where="工具注册表")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise RegistryError(f"version 必须是正整数，得到 {version!r}")

    defaults = _as_mapping(document.get("defaults", {}), where="defaults")
    unknown_defaults = sorted(set(defaults) - set(_DEFAULT_FIELDS))
    if unknown_defaults:
        raise RegistryError(f"defaults 出现未知字段 {unknown_defaults}")
    default_timeout = defaults.get("timeout_ms", 5000)
    if (
        not isinstance(default_timeout, int)
        or isinstance(default_timeout, bool)
        or default_timeout <= 0
    ):
        raise RegistryError(f"defaults.timeout_ms 必须是正整数毫秒，得到 {default_timeout!r}")

    def _positive_seconds(key: str, fallback: int) -> int:
        value = defaults.get(key, fallback)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise RegistryError(f"defaults.{key} 必须是正整数秒，得到 {value!r}")
        return value

    grant_ttl = _positive_seconds("grant_ttl_seconds", 60)
    max_grant_ttl = _positive_seconds("max_grant_ttl_seconds", 300)
    if grant_ttl > max_grant_ttl:
        raise RegistryError(
            f"defaults.grant_ttl_seconds（{grant_ttl}s）不得大于 max_grant_ttl_seconds"
            f"（{max_grant_ttl}s）：允许结果必须落在硬上限内"
        )

    raw_permissions = _as_mapping(document.get("permissions", {}), where="permissions")
    permissions: dict[str, str] = {}
    for raw_key, raw_note in raw_permissions.items():
        key = canonical_identifier(str(raw_key))
        if not key or "." not in key:
            raise RegistryError(f"权限名必须是 <域>.<动作> 形式，得到 {raw_key!r}")
        permissions[key] = "" if raw_note is None else str(raw_note)

    roles = _as_token_mapping(document.get("roles", {}), where="roles")
    for role, granted in roles.items():
        unknown_permissions = sorted(set(granted) - set(permissions))
        if unknown_permissions:
            raise RegistryError(
                f"roles.{role} 授予了未声明的权限 {unknown_permissions}；"
                "权限必须先写进 permissions 才能被授予"
            )

    raw_approvals = _as_mapping(document.get("approvals", {}), where="approvals")
    unknown_approvals = sorted(set(raw_approvals) - {"require_role"})
    if unknown_approvals:
        raise RegistryError(f"approvals 出现未知字段 {unknown_approvals}")
    approval_role = canonical_identifier(str(raw_approvals.get("require_role", "reviewer")))
    if approval_role not in roles:
        raise RegistryError(f"approvals.require_role={approval_role!r} 不是已声明的角色")

    raw_tools = _require(document, "tools", where="工具注册表")
    if not isinstance(raw_tools, (list, tuple)) or not raw_tools:
        raise RegistryError("tools 必须是非空列表：空注册表等于没有可用的受控工具")

    specs: list[ToolSpec] = []
    seen_ids: set[str] = set()
    seen_names: set[tuple[str, str]] = set()
    for index, raw_tool in enumerate(raw_tools):
        where = f"tools[{index}]"
        item = _as_mapping(raw_tool, where=where)
        payload = dict(item)
        if "timeout_ms" not in payload:
            payload["timeout_ms"] = default_timeout
        try:
            spec = ToolSpec.model_validate(payload)
        except Exception as error:  # pydantic ValidationError
            raise RegistryError(f"{where} 不合法：{error}") from error

        if spec.id in seen_ids:
            raise RegistryError(f"{where}: 工具 ID {spec.id} 重复")
        seen_ids.add(spec.id)
        key = (canonical_identifier(spec.agent), spec.tool_name)
        if key in seen_names:
            raise RegistryError(
                f"{where}: {spec.agent} 的工具名 {spec.tool_name} 已被占用；"
                "同名多工具会让按名解析产生歧义"
            )
        seen_names.add(key)

        unknown_permissions = sorted(set(spec.required_permissions) - set(permissions))
        if unknown_permissions:
            raise RegistryError(f"{where}: 声明的权限 {unknown_permissions} 不在 permissions 表里")
        for param in spec.parameters:
            if param.requires_permission and param.requires_permission not in permissions:
                raise RegistryError(
                    f"{where}.{param.name}: 提权所需的权限 {param.requires_permission!r} 未声明"
                )
        specs.append(spec)

    return ToolRegistry(
        path="",
        version=version,
        tools=tuple(sorted(specs, key=lambda item: item.id)),
        permissions=permissions,
        roles=roles,
        approval_role=approval_role,
        default_timeout_ms=default_timeout,
        grant_ttl_seconds=grant_ttl,
        max_grant_ttl_seconds=max_grant_ttl,
    )


def load_registry_document(path: Path | str) -> Mapping[str, Any]:
    """读取注册表 YAML；语法、重复键、类型错误一律抛 RegistryError。"""

    registry_path = Path(path)
    if not registry_path.is_file():
        raise RegistryError(f"工具注册表不存在: {registry_path}")
    try:
        text = registry_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RegistryError(f"工具注册表不可读: {registry_path}（{error}）") from error
    try:
        document = yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as error:
        raise RegistryError(f"工具注册表解析失败: {registry_path}（{error}）") from error
    if document is None:
        raise RegistryError(f"工具注册表为空: {registry_path}")
    return _as_mapping(document, where="工具注册表")


def load_approved_document(path: Path | str | None) -> tuple[Mapping[str, Any], Optional[Path]]:
    """读取已审核哈希清单；文件缺失时返回空清单（所有工具都不可用）。"""

    if path is None:
        return {}, None
    approved_path = Path(path)
    if not approved_path.is_file():
        return {}, approved_path
    try:
        document = json.loads(approved_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryError(f"已审核清单不可解析: {approved_path}（{error}）") from error
    if not isinstance(document, Mapping):
        raise RegistryError(f"已审核清单必须是 JSON 对象: {approved_path}")

    schema_version = document.get("approved_schema_version")
    if schema_version != APPROVED_SCHEMA_VERSION:
        raise RegistryError(
            f"未知已审核清单版本 {schema_version!r}；只接受 {APPROVED_SCHEMA_VERSION!r}，"
            "拒绝按旧口径判断工具是否被审核过"
        )
    tools = document.get("tools", {})
    if not isinstance(tools, Mapping):
        raise RegistryError("已审核清单的 tools 必须是对象")
    hashes: dict[str, str] = {}
    for tool_id, item in tools.items():
        if not isinstance(item, Mapping) or not isinstance(item.get("schema_hash"), str):
            raise RegistryError(f"已审核清单里 {tool_id!r} 的条目缺少 schema_hash")
        hashes[str(tool_id)] = str(item["schema_hash"])
    return {
        "approved_schema_version": schema_version,
        "registry_digest": document.get("registry_digest"),
        "reviewed_by": document.get("reviewed_by"),
        "approved_at": document.get("approved_at"),
        "tools": hashes,
        "raw": dict(document),
    }, approved_path


def load_registry(
    path: Path | str = DEFAULT_REGISTRY_PATH,
    *,
    approved_path: Path | str | None = DEFAULT_APPROVED_PATH,
) -> LoadedRegistry:
    """加载注册表 + 已审核哈希清单。注册表结构性错误直接失败关闭。"""

    document = load_registry_document(path)
    registry = registry_document_from_mapping(document)
    approved, resolved_approved_path = load_approved_document(approved_path)
    hashes: Mapping[str, str] = approved.get("tools", {}) if approved else {}
    object.__setattr__(registry, "path", Path(path).as_posix())
    object.__setattr__(registry, "approved", dict(hashes))
    object.__setattr__(registry, "approved_metadata", approved or {})
    return LoadedRegistry(
        registry=registry,
        document=document,
        approved_document=approved,
        approved_path=resolved_approved_path,
    )


def approve_registry(
    registry: ToolRegistry, *, reviewer: str, registry_digest: Optional[str] = None
) -> dict[str, Any]:
    """生成已审核清单的内容（不落盘）：把当前工具描述哈希登记为已审核。"""

    if not isinstance(reviewer, str) or not reviewer.strip():
        raise RegistryError("reviewer 不能为空：审核产物必须能追到人")
    return {
        "approved_schema_version": APPROVED_SCHEMA_VERSION,
        "registry_version": registry.version,
        "registry_digest": registry_digest or registry.identity,
        "reviewed_by": reviewer.strip(),
        "approved_at": to_timestamp(utc_now()),
        "tools": {
            spec.id: {"schema_hash": spec.schema_hash, "schema_version": spec.schema_version}
            for spec in sorted(registry.tools, key=lambda item: item.id)
        },
    }


def write_approved(document: Mapping[str, Any], path: Path | str) -> Path:
    """把已审核清单写到磁盘（显式动作：只在 registry --approve 时调用）。"""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(dict(document), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target
