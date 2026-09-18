"""Policy API 的部署配置（数据，不是代码）。

`api/policy-api.yaml` 决定：服务身份与预算、租户与各自的规则/索引/验证器配置、
客户端令牌（只存 sha256）、限流与幂等台账位置、运维令牌。

三条硬规则：

1. **每个租户自带边界**：规则目录、检索索引、验证器配置、工作区都在租户里声明；
   没有声明边界的租户不允许装配（"默认集合"这种跨租户搜索在 Phase 7 不存在）。
2. **令牌只存哈希**：配置里出现明文令牌一律拒绝加载——配置文件会被提交、会被备份，
   写明文等于把凭据散出去。
3. **根路径显式**：`service_root` 是解析所有相对路径的锚点，由加载方给出
   （仓库根或测试临时目录），不从配置文件位置推断。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import yaml
from pydantic import Field, ValidationError, model_validator

from policy.models import RuleValidationError, StrictModel

__all__ = [
    "API_CONFIG_SCHEMA_VERSION",
    "SUPPORTED_API_CONFIG_VERSIONS",
    "ApiConfig",
    "AuditLogConfig",
    "Budgets",
    "ClientSpec",
    "ConfigError",
    "Limits",
    "LoadConfig",
    "RetrievalConfig",
    "TenantSpec",
    "TokenInvalid",
    "hash_token",
    "load_api_config",
    "protected_hashes",
]

API_CONFIG_SCHEMA_VERSION = "1.0"
SUPPORTED_API_CONFIG_VERSIONS = frozenset({API_CONFIG_SCHEMA_VERSION})

# 明文令牌的形状：加载时用它做"你这是不是把真 token 提交了"的显式检查。
_PLAINTEXT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{16,}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class ConfigError(Exception):
    """部署配置不可用：服务不得启动（readiness 直接失败）。"""


class TokenInvalid(ConfigError):
    """令牌声明非法（明文、长度不足、哈希形状不对）。"""


def hash_token(token: str) -> str:
    """令牌的存储形态：sha256 十六进制。比较时用等长摘要，不再回推明文。"""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoadConfig(StrictModel):
    """上游预算：请求体、响应、prompt 与上下文长度上限。"""

    max_request_bytes: int = Field(default=65536, ge=256, le=4_194_304)
    # 响应上限：验证报告里的证据条数按它推导上限（见 runtime._evidence_limit）。
    max_response_bytes: int = Field(default=262_144, ge=1024, le=16_777_216)
    # 上下文上限：**逐字段**约束（file / module / task / git_diff），不是整个请求体——
    # "请求体很小但塞了 10MB 的 git_diff"必须在这里被拦住。
    max_context_bytes: int = Field(default=32_768, ge=1024, le=1_048_576)
    # 单条自由文本上限（任务描述、diff 摘要这类"人写的"字段）。
    max_prompt_chars: int = Field(default=8000, ge=0, le=200_000)
    max_concurrency: int = Field(default=8, ge=1, le=256)


class Budgets(StrictModel):
    """每条路由的**墙钟预算**（毫秒）。下游超时返回明确错误，绝不伪造 allow。"""

    evaluate_ms: int = Field(default=2000, ge=10, le=120_000)
    retrieve_ms: int = Field(default=2000, ge=10, le=120_000)
    validate_ms: int = Field(default=10_000, ge=10, le=600_000)


class RetrievalConfig(StrictModel):
    """租户的检索边界：语料清单、索引库与许可映射。"""

    enabled: bool = True
    corpus: Optional[str] = None
    database: Optional[str] = None
    expansion: Optional[str] = None
    licenses: Tuple[str, ...] = ()


class ClientSpec(StrictModel):
    """一个调用者：令牌哈希 + 允许的租户/项目/角色。"""

    client_id: str = Field(min_length=1)
    token_sha256: str
    tenants: Tuple[str, ...] = Field(min_length=1)
    roles: Tuple[str, ...] = ()
    projects: Tuple[str, ...] = ()
    display_name: str = ""
    enabled: bool = True
    # 过期时间（ISO-8601，UTC）。格式非法或已过期都拒绝认证，不做"忽略过期"的降级。
    expires_at: Optional[str] = None

    @model_validator(mode="after")
    def _token_is_hashed(self) -> "ClientSpec":
        value = self.token_sha256.strip().lower()
        if _SHA256_RE.match(value):
            object.__setattr__(self, "token_sha256", value)
            return self
        if _PLAINTEXT_TOKEN_RE.match(self.token_sha256):
            raise ValueError(
                f"client {self.client_id!r} 的 token_sha256 看起来是**明文令牌**；"
                "配置里只允许存 sha256（生成：python -m policy_api.cli clients --hash）"
            )
        raise ValueError(
            f"client {self.client_id!r} 的 token_sha256 不是 64 位十六进制摘要"
        )

    @model_validator(mode="after")
    def _check_tenant_ids(self) -> "ClientSpec":
        for name in self.tenants:
            if not _TENANT_ID_RE.match(name):
                raise ValueError(f"client {self.client_id!r} 声明了非法租户名 {name!r}")
        return self


class AuditLogConfig(StrictModel):
    """观测落点：JSONL 追加写 + 指标快照目录。不可写即失败关闭。"""

    enabled: bool = True
    path: Optional[str] = None
    metrics_path: Optional[str] = None


class TenantSpec(StrictModel):
    """一个租户的完整边界。缺少任何一项都不装配（不猜、不回落）。"""

    tenant_id: str
    display_name: str = ""
    project: Optional[str] = None
    project_root: str = Field(min_length=1)
    rules: Tuple[str, ...] = Field(default_factory=tuple)
    rules_root: Optional[str] = None
    retrieval: Optional[RetrievalConfig] = None
    validation_root: Optional[str] = None
    validators: Optional[str] = None
    audit_log: Optional[str] = None
    # 调用方声明的"未指定边界"时的默认项目名（None = 只有租户边界，没有项目维度）
    default_project: Optional[str] = None
    enabled: bool = True

    @model_validator(mode="after")
    def _check_tenant_id(self) -> "TenantSpec":
        if not _TENANT_ID_RE.match(self.tenant_id):
            raise ValueError(
                f"tenant_id 必须是小写标识符（字母/数字/._-），得到 {self.tenant_id!r}"
            )
        if self.rules_root is not None and not self.rules:
            raise ValueError(f"tenant {self.tenant_id!r} 声明了 rules_root 却没有声明 rules")
        return self


class ApiConfig(StrictModel):
    """一份完整的部署配置。加载是**原子**的：任一处不合法就整体拒绝。"""

    schema_version: str = API_CONFIG_SCHEMA_VERSION
    service_name: str = "engineering-policy-platform"
    deployment: str = "local"
    service_root: Optional[str] = None
    # 配置文件自身所在目录：相对路径的第二锚点（见 policy_api.services.TenantStore）。
    # 它不是"服务根"——服务根决定安全边界，配置目录只决定"这份配置里的相对路径怎么读"。
    config_dir: Optional[str] = None
    base_url: str = "http://127.0.0.1:8088"
    limits: LoadConfig = Field(default_factory=LoadConfig)
    budgets: Budgets = Field(default_factory=Budgets)
    tenants: Tuple[TenantSpec, ...] = ()
    clients: Tuple[ClientSpec, ...] = ()
    audit: AuditLogConfig = Field(default_factory=AuditLogConfig)
    rate_limit: Optional["RateLimitConfig"] = None
    # 允许读取 /v1/ops/metrics 的客户端 id（角色 ops / service-admin 也可，见 ops.METRICS_ROLES）。
    # 指标默认不对普通调用方开放：它包含租户名、错误分类与延迟分布。
    metrics_clients: Tuple[str, ...] = ()
    idempotency_ttl_seconds: int = Field(default=900, ge=0, le=86_400)
    tenants_root: Optional[str] = None
    validators_available: bool = True

    @model_validator(mode="after")
    def _version_supported(self) -> "ApiConfig":
        if self.schema_version not in SUPPORTED_API_CONFIG_VERSIONS:
            raise ValueError(
                f"未知部署配置版本 {self.schema_version!r}；本实现只接受 "
                f"{sorted(SUPPORTED_API_CONFIG_VERSIONS)}"
            )
        return self

    @model_validator(mode="after")
    def _at_least_one_tenant(self) -> "ApiConfig":
        if not self.tenants:
            raise ValueError("部署配置至少要声明一个租户；没有租户就没有可服务的边界")
        known = {item.tenant_id for item in self.tenants}
        if len(known) != len(self.tenants):
            raise ValueError("tenant_id 必须唯一")
        for client in self.clients:
            unknown = sorted(set(client.tenants) - known)
            if unknown:
                raise ValueError(
                    f"client {client.client_id!r} 声明了未定义的租户 {unknown}"
                )
        return self

    def tenant(self, tenant_id: str) -> Optional[TenantSpec]:
        for item in self.tenants:
            if item.tenant_id == tenant_id:
                return item
        return None


class RateLimitConfig(StrictModel):
    """按（客户端，租户）的令牌桶：容量 + 每秒补充速率。"""

    capacity: int = Field(default=60, ge=1, le=100_000)
    refill_per_second: float = Field(default=10.0, gt=0.0, le=10_000.0)


ApiConfig.model_rebuild()


def load_api_config(
    path: Path | str, *, root: Optional[Path | str] = None
) -> ApiConfig:
    """加载部署配置；文件不可读、YAML 非法、字段非法一律抛 ConfigError。"""

    target = Path(path)
    if not target.is_file():
        raise ConfigError(f"API 配置不存在：{target.name}")
    try:
        document = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ConfigError(f"{target.name}: 配置不可读（{type(error).__name__}）") from error
    if not isinstance(document, Mapping):
        raise ConfigError(f"{target.name}: 顶层必须是映射，得到 {type(document).__name__}")
    try:
        config = ApiConfig.model_validate(dict(document))
    except ValidationError as error:
        failure = RuleValidationError.from_pydantic(error, model_name=f"API 配置 {target.name}")
        raise ConfigError(str(failure)) from error
    anchor = Path(root) if root is not None else target.parent.parent
    return config.model_copy(
        update={
            "service_root": str(Path(anchor).resolve()),
            "config_dir": str(target.parent.resolve()),
        }
    )


def protected_hashes(config: ApiConfig) -> tuple[str, ...]:
    """已声明的令牌摘要（用于日志脱敏：任何摘要出现在文本里都不是秘密，但明文必须没有）。"""

    return tuple(sorted(client.token_sha256 for client in config.clients))
