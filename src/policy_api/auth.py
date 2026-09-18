"""认证与租户解析：先验证调用者，再谈业务动作。

三条不可交换的顺序：

1. **认证成功 ≠ 允许某个工具**：这里只回答"你是谁、你能用哪些租户/项目"，
   业务动作仍然由 Policy Engine 判定，服务身份**不能替最终用户扩权**；
2. **租户只来自令牌**：请求体里没有 tenant 字段，客户端不能自选边界；
3. **失败不透露存在性**：令牌未知、租户未授权、租户不存在对外都是同一类错误
   （401 / 404），并且令牌只以 sha256 形式参与比较与日志。

本项目没有外部 IdP：令牌是"部署配置里声明的静态凭据"，有效期由配置的 `expires_at`
决定，签名与轮换属于后续阶段（API 只保证"不认证就不服务"）。
"""

from __future__ import annotations

import datetime
import hmac
import re
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from policy.models import canonical_identifier

from .config import ApiConfig, ClientSpec, hash_token
from .errors import ApiError, ErrorCode

__all__ = [
    "AuthContext",
    "allows_project",
    "authorize",
    "client_by_token",
    "parse_authorization",
    "parse_expiry",
]

_BEARER_RE = re.compile(r"^Bearer[ \t]+(\S+)$")
_EXPIRY_FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class AuthContext:
    """认证结果：它是**授权输入**，不是授权结论。"""

    client_id: str
    token_sha256: str
    subject: str
    roles: Tuple[str, ...]
    tenant: str
    projects: Tuple[str, ...]
    anonymous: bool = False

    @property
    def token_ref(self) -> str:
        """日志里出现的令牌引用：摘要前 12 位（既不可反推，也能把两次调用串起来）。"""

        return self.token_sha256[:12]


def parse_authorization(header: Optional[str]) -> str:
    """从 Authorization 头取令牌；形状不对就是 401，不尝试"猜一个 fallback"。"""

    if header is None or not header.strip():
        raise ApiError(ErrorCode.UNAUTHENTICATED, "缺少 Authorization 头")
    match = _BEARER_RE.match(header.strip())
    if match is None:
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Authorization 头必须是 'Bearer <token>'")
    return match.group(1)


def parse_expiry(value: Optional[str]) -> Optional[datetime.datetime]:
    """解析 `expires_at`；格式非法直接拒绝（不把"看不懂的过期时间"当成永不过期）。"""

    if value is None:
        return None
    text = value.strip()
    for pattern in _EXPIRY_FORMATS:
        try:
            parsed = datetime.datetime.strptime(text, pattern)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    raise ApiError(
        ErrorCode.UNAUTHENTICATED,
        f"client 的 expires_at 不是可识别的 ISO-8601 时间：{text!r}",
    )


def client_by_token(config: ApiConfig, token: str) -> ClientSpec:
    """按令牌找到客户端声明。

    逐个比较 sha256（hmac.compare_digest）而不是先建字典按明文取键：先算哈希再比较，
    令牌明文不参与任何索引结构，比较也走常量时间。客户端数量是部署量级的（个位数到几十），
    这点开销换来的确定性是值得的。
    """

    digest = hash_token(token)
    found: Optional[ClientSpec] = None
    for client in config.clients:
        if hmac.compare_digest(client.token_sha256, digest):
            found = client
            break
    if found is None:
        raise ApiError(ErrorCode.UNAUTHENTICATED, "令牌未通过认证")
    return found


def allows_project(
    client: "ClientSpec", project: Optional[str], *, tenant_project: Optional[str] = None
) -> bool:
    """项目边界：令牌显式声明的项目 **加上** 租户自己声明的那个项目。

    租户的 `project` 是**配置里的边界**（不是请求方自选的），因此它天然属于该令牌的
    可达范围；令牌再额外声明 `projects` 只能**收窄到更具体的项目**，不能扩到别的项目。
    """

    if project is None:
        return True
    if tenant_project is not None and project == tenant_project:
        return True
    if not client.projects:
        # 客户端没有声明项目范围 = 它只被授权到"租户声明的那个项目"。
        return False
    return project in client.projects


def authorize(
    config: ApiConfig,
    *,
    token: str,
    subject: str,
    tenant: Optional[str] = None,
    project: Optional[str] = None,
    route: str = "",
    now: Optional[datetime.datetime] = None,
) -> AuthContext:
    """认证 + 解析租户与项目边界。任何一步不满足都失败关闭。

    运维路由（`route="metrics"`）**不属于任何租户**：指标是服务级事实，
    它只要求认证成功 + 运维角色，不要求租户/项目边界（也就不会因为"没声明租户"而 403）。
    """

    client = client_by_token(config, token)
    if not client.enabled:
        raise ApiError(ErrorCode.UNAUTHENTICATED, "该客户端已被禁用")

    moment = now or datetime.datetime.now(datetime.timezone.utc)
    expiry = parse_expiry(client.expires_at)
    if expiry is not None and moment >= expiry:
        raise ApiError(ErrorCode.TOKEN_EXPIRED, "凭据已过期；请换一份有效凭据")

    if route == "metrics":
        return AuthContext(
            client_id=client.client_id,
            token_sha256=client.token_sha256,
            subject=subject,
            roles=tuple(client.roles),
            tenant="",
            projects=tuple(client.projects),
        )

    if not client.tenants:
        raise ApiError(ErrorCode.FORBIDDEN, "该客户端没有被授权任何租户")

    if tenant is not None:
        if tenant not in client.tenants:
            # 不是"这个租户不存在"而是"你不能用它"：对外只给 401，避免租户名成为探针。
            raise ApiError(ErrorCode.UNAUTHENTICATED, "令牌未通过认证")
        resolved = tenant
    elif len(client.tenants) == 1:
        resolved = client.tenants[0]
    else:
        raise ApiError(
            ErrorCode.TOKEN_SCOPE_MISMATCH,
            "该凭据被授权多个租户，必须显式声明 tenant（不得由服务端替你选一个）",
        )

    spec = config.tenant(resolved)
    if spec is None or not spec.enabled:
        raise ApiError(ErrorCode.TENANT_NOT_FOUND, "请求的租户边界不可用")

    tenant_project = None if spec.project is None else canonical_identifier(spec.project)
    if not allows_project(client, project, tenant_project=tenant_project):
        raise ApiError(ErrorCode.PROJECT_NOT_ALLOWED, "该凭据没有被授权这个项目边界")

    roles: Sequence[str] = client.roles
    return AuthContext(
        client_id=client.client_id,
        token_sha256=client.token_sha256,
        subject=subject,
        roles=tuple(roles),
        tenant=resolved,
        projects=tuple(client.projects),
    )
