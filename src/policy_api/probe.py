"""HTTP Adapter：把 Agent 的规范事件**通过真正的 HTTP** 送往 Policy API。

它不是"第二个 Agent 产品"，而是第二个**协议消费者**：证明同一套规则既可以用
本地 SDK 判定，也可以经 API 判定，并且两者给出**等价决定**（Phase 7 的退出条件之一）。

三条纪律与 Phase 6 完全一致：

1. **能力上限由声明推出**：它消费的是规范事件，命中 `pre_hook`，因此上限是 `full`；
   但真正的受控执行仍在 Agent 侧，API 只回答"允不允许"；
2. **主体由装配处钉死**：令牌来自装配，事件载荷里的 principal 只是上下文声明；
3. **API 不可用即失败关闭**：网络错误、非 2xx、响应缺字段一律转成阻断响应
   （`policy_unavailable`），绝不放行。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from adapters.base import Adapter, AdapterConfig, RegistryError
from adapters.models import AgentEvent, AdapterManifest
from policy.models import Decision, PolicyContext

__all__ = ["HttpApiAdapter", "HttpApiClient"]

# 一次 HTTP 调用的上限：比服务端预算大一点，让服务端的超时先发生（这样错误分类更准确）。
DEFAULT_TIMEOUT_SECONDS = 30.0


class HttpApiClient:
    """极简 JSON-over-HTTP 客户端：标准库 `urllib`，核心与测试都不需要额外依赖。"""

    def __init__(
        self,
        base_url: str,
        *,
        token: str,
        opener: Optional[Callable[[Any], Any]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self.calls: list[dict[str, Any]] = []

    def post(self, path: str, payload: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
        data = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        self.calls.append({"path": path, "request_id": payload.get("request_id")})
        try:
            with self._opener(request, timeout=self.timeout) as response:  # type: ignore[call-arg]
                raw = response.read().decode("utf-8")
                return int(response.status), json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:  # 4xx/5xx 也是"有应答"：读出来再判断
            raw = error.read().decode("utf-8")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"error": {"code": "invalid_response"}}
            return int(error.code), body
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # 网络层失败：不是"没有结论"，而是"策略服务不可用"——必须失败关闭。
            raise RegistryError(
                f"Policy API 不可达（{type(error).__name__}）"
            ) from error


class HttpApiAdapter(Adapter):
    """把 AgentEvent 经 HTTP 送往 Policy API 的 Adapter。"""

    def __init__(
        self,
        *,
        manifest: AdapterManifest,
        config: AdapterConfig,
        config_path: Path | str,
        client: HttpApiClient,
        base_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(
            manifest=manifest, config=config, config_path=config_path, base_dir=base_dir
        )
        self.client = client

    # ------------------------------------------------------------------ 翻译

    def _build_event(self, raw_event: Mapping[str, Any]) -> AgentEvent:
        """线协议 → 规范事件：与 `JsonAdapter` 同一条路径（phase6 的 canonical-json）。

        HTTP 只是**传输**：事件的规范化规则必须与进程内消费者完全一致，
        否则"经 API 判定"和"本地判定"会从事件解析这一步就开始分叉。
        """

        from adapters.json_adapter import JsonAdapter

        parser = JsonAdapter(
            manifest=self.manifest, config=self.config, config_path=self.config_path
        )
        return parser._build_event(raw_event)

    def to_policy_context(self, event: AgentEvent, *, workspace: Optional[Path | str] = None) -> PolicyContext:
        """取上下文：本地翻译（维度声明与 Agent 无关），服务端只做判定。

        这样做不是为了省一次往返，而是为了让"上下文从哪来"保持**单一来源**：
        维度（layer/language/operation/file）由 Adapter 的声明决定，
        API 不会根据文件名或载荷再猜一次。
        """

        return super().to_policy_context(event, workspace=workspace)

    def decide(
        self, event: AgentEvent, *, workspace: Optional[Path | str] = None
    ) -> Mapping[str, Any]:
        """经 HTTP 取决策。任何异常都转成携带 `policy_unavailable` 的阻断响应。"""

        context = self.to_policy_context(event, workspace=workspace)
        payload = {
            "api_version": "1.0",
            "request_id": event.request_id,
            "trace_id": event.trace_id,
            "principal": {
                "subject": context.principal.subject if context.principal else "unknown",
                "roles": sorted(context.principal.roles) if context.principal else [],
            },
            "context": {
                "file": context.file,
                "layer": context.layer,
                "language": context.language,
                "module": context.module,
                "operation": None if context.operation is None else context.operation.value,
                "dependencies": list(context.dependencies),
                "agent": context.agent,
                "project": context.project,
            },
        }
        try:
            status, body = self.client.post("/v1/policy/evaluate", payload)
        except RegistryError as error:
            # 网络层失败不是"没有结论"，而是"策略服务不可用"：必须失败关闭。
            return self._unavailable(0, {"error": {"code": "policy_unavailable", "detail": str(error)}})
        if status != 200:
            return self._unavailable(status, body)
        decision = body.get("decision")
        if not isinstance(decision, Mapping) or "decision" not in decision:
            return self._unavailable(status, {"error": {"code": "invalid_response"}})
        return decision

    def _unavailable(self, status: int, body: Mapping[str, Any]) -> Mapping[str, Any]:
        error = body.get("error") if isinstance(body.get("error"), Mapping) else {}
        code = str((error or {}).get("code") or "policy_unavailable")
        return {
            "schema_version": "1.0",
            "decision": Decision.BLOCK.value,
            "request_id": "",
            "trace_id": None,
            "matched_rules": [],
            "violations": [
                {
                    "rule_id": "API-000",
                    "rule_version": 1,
                    "severity": "critical",
                    "message": f"策略服务不可用（HTTP {status} / {code}）；按失败策略阻断",
                    "evidence": {"kind": "api", "subject": "policy-api", "value": code},
                }
            ],
            "required_action": None,
        }
