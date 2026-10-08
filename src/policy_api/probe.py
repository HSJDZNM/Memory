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

import http.client
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from adapters.base import Adapter, AdapterConfig, RegistryError
from adapters.models import AgentEvent, AdapterManifest
from policy.models import SCHEMA_VERSION, Decision, PolicyContext

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

    @staticmethod
    def _parse_body(raw: bytes, *, label: str) -> Mapping[str, Any]:
        """把应答正文解析成对象；任何"读不懂"都抛 RegistryError。

        契约是"Policy API 的响应顶层必须是对象"：非 UTF-8、非 JSON、JSON 但不是对象
        都属于**没有可判断的应答**。以前这三种情况里的两种会以 `JSONDecodeError` /
        `UnicodeDecodeError` 直接冒出去（`decide` 只接 RegistryError），第三种
        （`[]` / `null`）会原样返回、然后在 `body.get(...)` 上炸成 AttributeError——
        三条路都不是"阻断"，而是未处理异常。
        """

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RegistryError(f"{label}不是合法 UTF-8（{type(error).__name__}）") from error
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError as error:
            raise RegistryError(f"{label}不是合法 JSON（{type(error).__name__}）") from error
        if not isinstance(parsed, Mapping):
            raise RegistryError(f"{label}顶层必须是对象，拒绝按不确定的语义处理")
        return dict(parsed)

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
                return int(response.status), self._parse_body(
                    response.read(), label="Policy API 响应"
                )
        except urllib.error.HTTPError as error:  # 4xx/5xx 也是"有应答"：读出来再判断
            # 错误响应的正文读不出来 / 不是受控错误信封时，用 invalid_response 表达
            # "有应答但不是我们的协议"：状态码与阻断语义都保留，不让解析细节改写结论。
            try:
                body = self._parse_body(error.read(), label="Policy API 错误响应")
            except (RegistryError, OSError, http.client.HTTPException) as parse_error:
                body = {
                    "error": {
                        "code": "invalid_response",
                        "detail": type(parse_error).__name__,
                    }
                }
            return int(error.code), body
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
            # 网络层失败：不是"没有结论"，而是"策略服务不可用"——必须失败关闭。
            # `http.client.HTTPException`（IncompleteRead / BadStatusLine / …）不是 OSError，
            # 漏掉它就会让"连接中途断了"变成未处理异常，而不是阻断。
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
        # 记下来给 `_build_event` 里进程内构造的 JsonAdapter 用：`Adapter` 只在构造期用锚点
        # 解析路径、不保存它，而 JsonAdapter 不传 base_dir 时会退回 `Path.cwd()`——同一个事件
        # 在不同启动目录下会得到不同的路径事实（规范化随 cwd 漂移）。
        self._base_dir = base_dir

    # ------------------------------------------------------------------ 翻译

    def _build_event(self, raw_event: Mapping[str, Any]) -> AgentEvent:
        """线协议 → 规范事件：与 `JsonAdapter` 同一条路径（phase6 的 canonical-json）。

        HTTP 只是**传输**：事件的规范化规则必须与进程内消费者完全一致，
        否则"经 API 判定"和"本地判定"会从事件解析这一步就开始分叉。
        """

        from adapters.json_adapter import JsonAdapter

        parser = JsonAdapter(
            manifest=self.manifest,
            config=self.config,
            config_path=self.config_path,
            base_dir=self._base_dir,
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
        except Exception as error:  # noqa: BLE001 - 适配器只有"阻断"一种安全失败形态
            # 这条兜底让 docstring 的承诺（"任何异常都转成携带 policy_unavailable 的阻断响应"）
            # 成为事实：这里**没有**放行路径，未预期异常也只会变成阻断（带异常类型），
            # 绝不把"我没算出来"翻译成"策略说可以"。
            return self._unavailable(
                0,
                {
                    "error": {
                        "code": "policy_unavailable",
                        "detail": f"未预期异常 {type(error).__name__}",
                    }
                },
            )
        if status != 200:
            return self._unavailable(status, body)
        decision = body.get("decision")
        if not isinstance(decision, Mapping) or "decision" not in decision:
            return self._unavailable(status, {"error": {"code": "invalid_response"}})
        return decision

    def _unavailable(self, status: int, body: Any) -> Mapping[str, Any]:
        """阻断载荷：错误码取服务端给的，取不到就是 policy_unavailable。

        `body` 可能是**任何东西**（代理的 HTML、非对象 JSON、读失败时的空映射），
        所以只做类型判断，绝不假设它是 Mapping——原来对非对象正文会抛 AttributeError，
        那正好发生在"必须阻断"的路径上。
        """

        candidate = body.get("error") if isinstance(body, Mapping) else None
        error = candidate if isinstance(candidate, Mapping) else {}
        code = str(error.get("code") or "policy_unavailable")
        return {
            # 决策协议版本**只能从核心取**（AGENTS 第 7/31 条）：写死 "1.0" 会让这份
            # 失败关闭载荷被平台自己的消费方（policy.models.parse_decision）以
            # "未知决策协议版本"拒收——拒绝理由从"策略服务不可用"变成"协议版本不认识"，
            # 而它本来是"服务不可达 → 阻断"这条链路上唯一的证据。
            "schema_version": SCHEMA_VERSION,
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
