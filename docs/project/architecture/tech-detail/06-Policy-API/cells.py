# -*- coding: utf-8 -*-
"""06-Policy-API：HTTP 边界上的守卫、认证、预算、幂等与观测（内容源，产物由 build_notebooks.py 生成）。"""
from __future__ import annotations

from notebook_lib import NotebookSpec, code, markdown

SPEC = NotebookSpec(
    stem="06-Policy-API",
    title="Policy API：传输边界，不是第二份业务逻辑",
    summary="用进程内 ASGI 客户端走完 HTTP → 守卫 → 认证 → 预算 → 幂等 → 装配 → 平台判定 → 版本化响应 → 观测，并钉住每一条失败关闭",
    temp_dir=".tmp/tech-detail/06",
    cells=(
        markdown(
            '''
# 06 Policy API：传输边界，不是第二份业务逻辑

这份 notebook 配合同名图 `06-Policy-API.drawio`。图上的九步是：

    HTTP 请求 → 体积与字段守卫 → 认证 → 预算与限流 → 幂等台账
              → 服务装配 → 平台判定 → 版本化响应 → 观测与锚定

**这张图要讲清的一件事**：API 只做"协议 → 领域模型 → 协议"。
同一个上下文，经本地引擎算出的决策载荷与经 API 返回的**整份相等**（比的是 JSON 值，
字段顺序不属于契约）；`src/policy/` 一行都没有为了服务化而改。

六节代码各自回答一个问题：

| 小节 | 回答的问题 |
| --- | --- |
| 1 | 传输协议与决策协议为什么是两套版本？客户端能不能自带证据 |
| 2 | 错误码怎样唯一决定 HTTP 状态？为什么有些错误码刻意同码 |
| 3 | 租户从哪来？认证成功是不是就等于允许 |
| 4 | 预算、超时与幂等：为什么超时绝不等于 allow |
| 5 | 经 HTTP 走完整链路，本地与 API 的决定是否整份相等 |
| 6 | 观测记了什么、没记什么，锚能发现什么 |

**预备知识**：会读 HTTP 请求（方法 + 路径 + 请求头 + JSON 请求体）就够了。
下面**不起端口、不联网**：`policy_api.testing.make_client` 返回一个进程内 ASGI 客户端
（httpx 传输），请求真的经过 FastAPI 的路由与中间件，只是不经过 socket。
所有产物写在 `.tmp/tech-detail/06/` 下，仓库里的真实配置与规则一个字节都不会被改动。
'''
        ),
        code(
            '''
# 先找到仓库根目录：notebook 可能从仓库根启动，也可能从本目录启动，两种都要能跑。
import json
import shutil
import sys
from pathlib import Path


def find_repo_root(start):
    """往上找：同时有 pyproject.toml 与 src/policy/ 的那一层就是仓库根。"""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "policy").is_dir():
            return candidate
    raise SystemExit("没有找到仓库根目录（需要 pyproject.toml 与 src/policy/）")


REPO_ROOT = find_repo_root(Path.cwd())
for extra in (REPO_ROOT / "src", REPO_ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

# 本 notebook 独占的临时目录：每轮从空目录开始。
TEMP = REPO_ROOT / ".tmp" / "tech-detail" / "06"
shutil.rmtree(TEMP, ignore_errors=True)
TEMP.mkdir(parents=True, exist_ok=True)

import yaml

from policy_api.config import hash_token, load_api_config
from policy_api.models import API_SCHEMA_VERSION, SUPPORTED_API_SCHEMA_VERSIONS
from policy_api.testing import build_runtime, make_client

CONFIG_PATH = REPO_ROOT / "api" / "policy-api.yaml"
CONFIG = load_api_config(CONFIG_PATH, root=REPO_ROOT)

# 只把"写入落点"改到本 notebook 的临时目录：租户、规则、客户端、预算一个字都不改。
document = CONFIG.model_dump(mode="json")
document["audit"]["path"] = (TEMP / "run" / "audit.jsonl").relative_to(REPO_ROOT).as_posix()
for spec in document["tenants"]:
    if spec.get("audit_log"):
        spec["audit_log"] = (
            TEMP / "run" / "tenants" / spec["tenant_id"] / "audit.jsonl"
        ).relative_to(REPO_ROOT).as_posix()
DEMO_CONFIG = TEMP / "run" / "policy-api.yaml"
DEMO_CONFIG.parent.mkdir(parents=True, exist_ok=True)
DEMO_CONFIG.write_text(
    yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8", newline=chr(10)
)

RUNTIME = build_runtime(DEMO_CONFIG, root=REPO_ROOT)
CLIENT = make_client(RUNTIME)  # 进程内 ASGI 客户端：真的过路由，只是没有 socket
TOKEN = "local-dev-token"

print("仓库根目录:", REPO_ROOT.name)
print("本笔记本的临时目录:", TEMP.relative_to(REPO_ROOT).as_posix())
print("Python:", sys.version.split()[0], "| API_SCHEMA_VERSION:", API_SCHEMA_VERSION)
print("装配的租户:", ", ".join(RUNTIME.store.ids), "| 装配错误:", RUNTIME.store.errors or "无")
print("观测日志落点:", RUNTIME.request_log.path.relative_to(REPO_ROOT).as_posix())
print("进程存活 / 能否安全服务:",
      CLIENT.get("/v1/health/live").status_code, CLIENT.get("/v1/health/ready").status_code)

assert set(RUNTIME.store.ids) == {"fixture-shop", "local-dev"}
assert not RUNTIME.store.errors
assert SUPPORTED_API_SCHEMA_VERSIONS == {API_SCHEMA_VERSION} == {"1.0"}
assert hash_token(TOKEN) == CONFIG.clients[0].token_sha256, "配置里存的是摘要，不是明文令牌"
'''
        ),
        markdown(
            '''
## 1. 两套版本各自演进，客户端连"提交证据"都做不到

`policy_api.models` 是**传输协议**，`policy.models` 是**领域模型 + 决策协议**，两者刻意分开：

| 版本 | 位置 | 值 | 变了意味着什么 |
| --- | --- | --- | --- |
| 传输协议 | `policy_api.models.API_SCHEMA_VERSION` | 1.0 | 线上请求 / 响应字段变了（删字段、改语义）= 新 API 版本，还必须显式更新 `api/openapi.json` 快照 |
| 决策协议 | `policy.models.SCHEMA_VERSION` | 1.0 | 决策载荷（PolicyDecision）变了 |
| 协议世代 | `policy.models.POLICY_VERSION` | phase-1 | 与决策协议同进同退，**不跟随平台阶段** |

`policy_api` 只从核心**取值**（`DECISION_PAYLOAD_SCHEMA_VERSION`、`POLICY_GENERATION`），
不许自己算一个——"证据说 phase-5、载荷说 phase-1"这类漂移正是这条纪律要避免的。

请求体是**信封 + 载荷**：`api_version` / `request_id` / `tenant` / `trace_id` /
`budget_ms` / `idempotency_key` 是横切字段，`principal` 与 `context` 才是业务载荷。

**输出怎么读**：第一段打印三个版本号，并断言"只取值、不自算"；
第二张表是四条模型层拒绝——缺 `api_version`、未知 `api_version`、客户端自带 `evidence`、
客户端自带 `decision`。它们全是 400，而且 `evidence` 这个字段**根本不在 DTO 里**：
客户端没有任何途径把一份"我自己写的证据"塞进判定。
'''
        ),
        code(
            '''
# 两套版本、信封形态，以及"未发布字段一律拒绝"。
from policy import models as core_models
from policy_api import models as api_models
from policy_api.errors import ErrorCode

decision_versions = (core_models.SCHEMA_VERSION, core_models.POLICY_VERSION)
print(pad("传输协议 API_SCHEMA_VERSION", 34) + api_models.API_SCHEMA_VERSION)
print(pad("决策协议 SCHEMA_VERSION", 34) + core_models.SCHEMA_VERSION)
print(pad("协议世代 POLICY_VERSION", 34) + core_models.POLICY_VERSION)
print(pad("policy_api 只取值、不自算", 34) + str(api_models.POLICY_GENERATION == core_models.POLICY_VERSION))

assert api_models.API_SCHEMA_VERSION == "1.0"
assert decision_versions == ("1.0", "phase-1")
assert api_models.POLICY_GENERATION == core_models.POLICY_VERSION
assert api_models.DECISION_PAYLOAD_SCHEMA_VERSION == core_models.SCHEMA_VERSION

BASE = {
    "api_version": API_SCHEMA_VERSION,
    "request_id": "tech-detail-06",
    "tenant": "local-dev",
    "principal": {"subject": "alice", "roles": ["developer"]},
    "context": {
        "file": "examples/bad_controller.py",
        "layer": "controller",
        "language": "python",
        # 依赖是**调用方显式声明**的输入（Phase 0-4 的契约）：服务端不猜。
        # 第 5 节会演示"不声明依赖"时这条路由得到什么。
        "dependencies": ["repository"],
    },
}
# 失败关闭图：每一节的失败都会往这里加一行，最后一节统一打印并逐行校验状态码。
REJECTED = {}


def post(route, payload, *, token=TOKEN):
    """经进程内 ASGI 客户端发一次真实 HTTP 请求（有请求头、状态码与响应体）。"""

    return CLIENT.post(
        "/v1/" + route, json=payload, headers={"Authorization": "Bearer " + token}
    )


def failure_of(response):
    """失败响应的 (HTTP 状态, 错误码)。"""

    return response.status_code, response.json()["error"]["code"]


dto_cases = (
    ("missing_version", "缺 api_version", {k: v for k, v in BASE.items() if k != "api_version"}),
    ("unknown_version", "未知 api_version = 2.0", {**BASE, "api_version": "2.0"}),
    ("client_evidence", "客户端自带 evidence", {**BASE, "evidence": {"bundle": "client-supplied"}}),
    ("client_decision", "客户端自带 decision", {**BASE, "decision": {"decision": "allow"}}),
)
print()
print(pad("场景", 30) + pad("HTTP", 7) + "错误码")
print("-" * 62)
for key, label, payload in dto_cases:
    status, code = failure_of(post("policy/evaluate", payload))
    REJECTED[key] = (label, status, code)
    print(pad(label, 30) + pad(status, 7) + str(code))

assert {key: REJECTED[key][1:] for key in ("missing_version", "unknown_version", "client_evidence", "client_decision")} == {
    "missing_version": (400, "schema_version_missing"),
    "unknown_version": (400, "schema_version_unknown"),
    "client_evidence": (400, "body_invalid"),
    "client_decision": (400, "body_invalid"),
}
print("小结：传输协议与决策协议各自演进；客户端能发的字段由 DTO 决定，证据只能由服务端产出。")
'''
        ),
        markdown(
            '''
## 2. 错误码 → HTTP 状态：调用方不能自定义状态

`ErrorCode` 是**受控枚举**，`STATUS_BY_CODE` 是它到 HTTP 状态的**唯一**映射：
`ApiError.status` 从表里查，路由处理函数没有任何机会写一个"更合适"的状态码。

三条关键语义：

1. **跨租户与不存在同码**：`tenant_not_found` 与 `not_found` 都是 404，
   `forbidden` 与 `token_scope_mismatch` 都是 403——错误码本身不能变成"某个租户 / 资源
   是否存在"的探针；
2. **超时是 504、依赖不可用是 503**：都不是 200，都不是 allow；
3. **错误响应形状固定**（`error_payload`）：`code` / `detail` / `retryable` /
   `request_id` / `trace_id`，其中 `detail` 会被压成单行并限量，异常原文不透传
   （它可能带绝对路径或内部配置名）。

**输出怎么读**：全表是"错误码 → 状态码"的逐行对照；随后几行是断言——
`ApiError` 的状态码来自错误码而不是调用方构造，404 与 403 上各有两个以上错误码（刻意同码），
504 上只有三个 `*_timeout`，而**没有任何一个错误码对应 200**。
'''
        ),
        code(
            '''
# 错误码 → 状态码：全表 + 关键语义。
from policy_api.errors import STATUS_BY_CODE, ApiError, error_payload

print(pad("错误码", 34) + "HTTP")
print("-" * 44)
for code in ErrorCode:
    print(pad(code.value, 34) + str(STATUS_BY_CODE[code]))
print("-" * 44)
by_status = {}
for code in ErrorCode:
    by_status.setdefault(STATUS_BY_CODE[code], []).append(code.value)
print("错误码总数:", len(STATUS_BY_CODE), "| 覆盖的状态码:", sorted(by_status))
print("404 上的错误码（刻意同码，避免用错误码探测存在性）:", sorted(by_status[404]))
print("403 上的错误码（同上）:", sorted(by_status[403]))
print("504 上的错误码:", sorted(by_status[504]))
print("503 上的错误码:", sorted(by_status[503]))

assert set(STATUS_BY_CODE) == set(ErrorCode), "每个错误码都必须有唯一状态"
assert sorted(by_status[404]) == ["not_found", "tenant_not_found"]
assert "forbidden" in by_status[403] and "token_scope_mismatch" in by_status[403]
assert sorted(by_status[504]) == ["evaluate_timeout", "retrieve_timeout", "validate_timeout"]
assert "knowledge_unavailable" in by_status[503] and "audit_unavailable" in by_status[503]
assert all(status != 200 for status in STATUS_BY_CODE.values())

sample = ApiError(ErrorCode.EVALUATE_TIMEOUT, "策略判定超出预算；未给出结论（不伪造 allow）", retryable=True)
print()
print("状态码来自错误码，不由调用方决定:", sample.kind, "→", sample.status, "| retryable =", sample.retryable)
print("错误响应形状:", ", ".join(sorted(error_payload(sample)["error"])))
assert sample.status == 504 and sample.retryable
assert set(error_payload(sample)["error"]) == {"code", "detail", "retryable", "request_id", "trace_id"}
print("小结：状态码是错误码的推论；没有一条错误路径能返回 200。")
'''
        ),
        markdown(
            '''
## 3. 认证与隔离：租户只来自令牌

`policy_api.auth.authorize` 只回答"你是谁、你能用哪些租户 / 项目"，它**不是**授权结论：
业务动作仍然由 Policy Engine 判定。四条不可交换的顺序：

1. **租户只来自令牌**：请求体里的 `tenant` 只是"我想用哪个"的提示，越权即拒绝；
   拿着多租户令牌却不声明 `tenant` 时，服务端**不会替你选一个**（403）；
2. **失败不透露存在性**：未知令牌与越权租户对外是同一个 401；
3. **认证成功 ≠ 允许**：带着合法令牌请求一个违规文件，得到的仍然是 `block`；
4. **日志里没有明文**：令牌只以 sha256 前 12 位（`token_ref`）出现在观测里。

**输出怎么读**：第一张表是四条认证失败（未知令牌 / 越权租户 / 凭据过期 / 多租户不声明）；
第二段是"认证成功也不放行"的实测，以及运维端点只认 `ops` 角色（同一个服务身份
不会替用户扩权，也不会被用户拿去读运维指标）；最后几行把观测日志的字段名列出来，
并确认 `token` / `authorization` / `credentials` 一个都不在日志里、仓库绝对路径也没进去。
'''
        ),
        code(
            '''
# 认证与隔离 + 观测里没有明文。
from policy_api.auth import authorize

auth = authorize(CONFIG, token=TOKEN, subject="alice", tenant="local-dev")
print("认证成功:", auth.client_id, "| 租户:", auth.tenant, "| 角色:", ",".join(auth.roles))
print("日志里的令牌引用 token_ref:", auth.token_ref, "（sha256 前 12 位；明文不进日志）")
assert auth.tenant == "local-dev" and auth.token_ref == CONFIG.clients[0].token_sha256[:12]

# 过期凭据：只把配置里的一个客户端改成"2000 年就过期"，其余一字不改。
expired_client = CONFIG.clients[0].model_copy(update={"expires_at": "2000-01-01T00:00:00Z"})
expired_config = CONFIG.model_copy(update={"clients": (expired_client, *CONFIG.clients[1:])})
auth_cases = (
    ("unknown_token", "未知令牌", {"token": "not-a-real-token", "tenant": "local-dev"}),
    ("cross_tenant", "越权租户（dsh-agent 用 local-dev）", {"token": "dsh-agent-token", "tenant": "local-dev"}),
    ("expired", "凭据过期", {"token": TOKEN, "tenant": "local-dev", "config": expired_config}),
    ("multi_tenant", "多租户却不声明 tenant", {"token": TOKEN}),
)
print()
print(pad("场景", 40) + pad("HTTP", 7) + "错误码")
print("-" * 70)
for key, label, options in auth_cases:
    used_config = options.pop("config", CONFIG)
    try:
        authorize(used_config, route="evaluate", subject="alice", **options)
        status, code = 200, "authorized（缺陷）"
    except ApiError as error:
        status, code = error.status, error.kind
    REJECTED[key] = (label, status, code)
    print(pad(label, 40) + pad(status, 7) + code)

assert REJECTED["unknown_token"][1:] == (401, "unauthenticated")
assert REJECTED["cross_tenant"][1:] == (401, "unauthenticated")
assert REJECTED["expired"][1:] == (401, "token_expired")
assert REJECTED["multi_tenant"][1:] == (403, "token_scope_mismatch")

# 认证成功 ≠ 允许：同一个令牌请求一个违规文件，判定仍然是 block。
allowed = post("policy/evaluate", {**BASE, "request_id": "06:auth"})
body = allowed.json()
print()
print("认证成功后的判定:", allowed.status_code, body["decision"]["decision"],
      "| 违规规则:", ", ".join(item["rule_id"] for item in body["decision"]["violations"]))
assert allowed.status_code == 200 and body["decision"]["decision"] == "block"

# 运维端点不属于任何租户：它只要求认证 + 运维角色。
developer_metrics = CLIENT.get("/v1/ops/metrics", headers={"Authorization": "Bearer " + TOKEN})
ops_metrics = CLIENT.get("/v1/ops/metrics", headers={"Authorization": "Bearer ops-monitor-token"})  # secret-scan: allow（合成值：用来验证 ops 令牌与 developer 令牌的角色差异，不是真令牌）
REJECTED["metrics_forbidden"] = ("指标端点无权限（developer 令牌）",) + failure_of(developer_metrics)
print("指标端点（developer 令牌）:", failure_of(developer_metrics))
print("指标端点（ops 令牌）:", ops_metrics.status_code, "| 字段:", ", ".join(sorted(ops_metrics.json())))
assert failure_of(developer_metrics) == (403, "metrics_forbidden") and ops_metrics.status_code == 200

# 观测只记摘要：把字段名列出来，并确认凭据与绝对路径都没进去。
rows = RUNTIME.request_log.read_back()
log_text = json.dumps(rows, ensure_ascii=False)
print()
print("请求级日志条数:", len(rows), "| 字段:", ", ".join(sorted(rows[0])))
print("其中一条:", json.dumps({name: rows[0][name] for name in ("route", "status", "tenant", "client_id", "token_ref")}, ensure_ascii=False))
print("日志里出现过请求令牌:", TOKEN in log_text, "| 出现过仓库绝对路径:", str(REPO_ROOT) in log_text)
assert {"route", "status", "tenant", "client_id", "token_ref"} <= set(rows[0])
assert TOKEN not in log_text and str(REPO_ROOT) not in log_text
assert not ({"token", "token_sha256", "authorization", "credentials"} & set(rows[0]))
assert all(len(row["token_ref"]) == 12 for row in rows)
print("小结：认证是授权输入而不是授权结论；日志记的是 token_ref，不是令牌。")
'''
        ),
        markdown(
            '''
## 4. 预算、超时与幂等：没有"降级成 allow"这第三种结果

`budget_for` 决定本次请求的墙钟预算：**路由默认值，调用方只能要更小的**
（要更大一律 503 `request_budget_exceeded`）。`run_with_budget` 在预算内运行操作：

- 正常结束 → `(结果, Elapsed(timed_out=False))`；
- 预算耗尽 → `(None, Elapsed(timed_out=True))`，调用方必须把它翻译成 `evaluate_timeout`（504）。

一句必须诚实的话：Python 没有可移植的线程取消，"超时"的语义是**调用方不再等待、结果被丢弃**，
而不是"工作已经停止"。正因为如此，超时绝不能变成 allow。

幂等台账回答的是"上次那个 key 的结论是什么"，所以它**整份重写**而不是追加写：

| 情况 | 结果 |
| --- | --- |
| 同一个 `idempotency_key` + 同一个请求摘要 | 返回**原来那份响应**，响应头 `Idempotency-Replayed: true` |
| 同一个 key + 不同的请求摘要 | 409 `idempotency_key_conflict`（不覆盖、不合并） |

`rate_limit` 是每个"客户端 + 租户"的令牌桶：容量用尽返回 429 `rate_limited`；
并发闸门抢不到槽位返回 503 `policy_busy`——两者都是"服务端忙"，都不是"允许"。

**输出怎么读**：上半段是预算与超时的实测（注意超时那一行的值是 `None`）；
下半段走真实 HTTP——同一个 `idempotency_key` 发两次看到 `replayed`，
再把请求体里的 `layer` 改一个字，立刻变成 409。
'''
        ),
        code(
            '''
# 预算与超时；幂等台账走真实 HTTP（同一个 key 只有一个结论）。
import time

import policy_api.runtime as runtime_module
from policy_api.runtime import budget_for
from policy_api.timeout import run_with_budget

defaults = {route: budget_for(route, CONFIG, None) for route in ("evaluate", "retrieve", "validate")}
print("路由默认预算(ms):", json.dumps(defaults), "| 调用方要 500ms →", budget_for("evaluate", CONFIG, 500), "ms")
try:
    budget_for("evaluate", CONFIG, 600000)
    too_large = (200, "granted（缺陷）")
except ApiError as error:
    too_large = (error.status, error.kind)
REJECTED["budget_too_large"] = ("要更大的预算",) + too_large
print("调用方要 600000ms →", too_large[0], too_large[1], "（更大一律拒绝）")

value, elapsed = run_with_budget(lambda: "判定结果", budget_ms=500)
slow_value, slow_elapsed = run_with_budget(lambda: time.sleep(0.3), budget_ms=60)
print("正常分支: 值 =", repr(value), "| timed_out =", elapsed.timed_out)
print("超时分支: 值 =", repr(slow_value), "| timed_out =", slow_elapsed.timed_out,
      "| 调用方实际等待约", int(slow_elapsed.milliseconds), "ms")
assert value == "判定结果" and not elapsed.timed_out
assert slow_value is None and slow_elapsed.timed_out


def slow_evaluate(rules, context):
    """把判定拖慢，用来证明"预算到点返回 504"而不是 allow。"""

    time.sleep(0.4)
    from policy.engine import evaluate as real_evaluate

    return real_evaluate(rules, context)


saved_evaluate = runtime_module.evaluate
runtime_module.evaluate = slow_evaluate
try:
    timed_out = post("policy/evaluate", {**BASE, "request_id": "06:timeout", "budget_ms": 60})
finally:
    runtime_module.evaluate = saved_evaluate
REJECTED["evaluate_timeout"] = ("判定超时",) + failure_of(timed_out)
print("HTTP 判定超时:", failure_of(timed_out), "| retryable =", timed_out.json()["error"]["retryable"])
assert failure_of(timed_out) == (504, "evaluate_timeout")
assert timed_out.json()["error"]["retryable"] is True

idempotent = {**BASE, "request_id": "06:idem", "idempotency_key": "tech-detail-06-key"}
first = post("policy/evaluate", idempotent)
second = post("policy/evaluate", idempotent)
conflict = post("policy/evaluate", {**idempotent, "context": {**BASE["context"], "layer": "service"}})
print()
print("首次:", first.status_code, "| 重放:", second.status_code,
      "| 响应头 Idempotency-Replayed:", second.headers.get("Idempotency-Replayed"))
print("同键换请求体:", failure_of(conflict))
REJECTED["idempotency_conflict"] = ("同一个 key 换请求体",) + failure_of(conflict)
assert first.status_code == second.status_code == 200
assert second.headers.get("Idempotency-Replayed") == "true"
assert first.json()["decision"] == second.json()["decision"]
assert failure_of(conflict) == (409, "idempotency_key_conflict")
print("小结：预算到点只有两种结果——拿到结论，或拿到 *_timeout（504）；")
print("      同一个 key 只有一个结论，换请求体是 409 而不是「再算一次」。")
'''
        ),
        markdown(
            '''
## 5. 经 HTTP 走完整链路：本地与 API 的决定整份相等

判定仍然只有 `policy.engine.evaluate` 一条路径，API 只做"协议 → 领域模型 → 协议"。

**输出怎么读**：

1. 第一段是 `POST /v1/policy/evaluate` 的成功响应：`decision` 段是**原样的决策载荷**，
   顶层还有传输协议自己的 `api_version` 与从核心取来的 `policy_version` / `generation`；
2. 第二段把同一份上下文直接交给本地引擎，再断言两份决策载荷**整份相等**，
   并且 `budget_ms` / `idempotency_key` / `api_version` 这些**传输字段没有渗进决策载荷**；
   顺带看一眼 `include_evidence: true` 时的 `skipped_rules`——只提供上下文的调用路径会把
   证据类 checker 的规则记为"需要验证器证据"，而不是当成通过；同一个文件**不声明**
   `dependencies` 时这条路由给出的是 `allow`：上下文是**输入**，服务端不猜依赖，
   需要验证器证据的判定要经 `/v1/validation/evaluate`；
3. 第三段是协议层的失败：不是 JSON、类型不对、请求体超大、未知路由、方法不对、
   伪造 `decision_ref`、租户没配索引；接着是两条"服务端自己出问题"的路径——
   令牌桶容量用尽（429 `rate_limited`）与观测日志不可写（503 `audit_unavailable`）；
4. 最后一段是观测：请求级 JSONL 的锚（`seal`）、校验结果，以及"删掉尾部一条"能否被发现。
   `seal_audit` 是**摘要链锚**，不是防篡改日志——它仍然靠外部锚发现改写。
'''
        ),
        code(
            '''
# 完整链路：HTTP → 守卫 → 认证 → 预算 → 幂等 → 装配 → 平台判定 → 版本化响应 → 观测
from policy.context import build_context
from policy.engine import evaluate
from policy.models import canonical_identifier
from policy_api.auth import authorize as authorize_local
from policy_api.observability import RequestLog, RequestLogEntry, seal_audit, verify_seal
from policy_api.testing import runtime_from_config

response = post("policy/evaluate", {**BASE, "request_id": "06:agree"})
body = response.json()
print("evaluate:", response.status_code, "| 响应字段:", ", ".join(sorted(body)))
print("版本字段: api_version =", body["api_version"],
      "| decision.schema_version =", body["decision"]["schema_version"],
      "| policy_version =", body["policy_version"], "| generation =", body["generation"])
print("decision:", body["decision"]["decision"], "| 违规:",
      ", ".join(item["rule_id"] for item in body["decision"]["violations"]))
print("规则集:", body["rule_set"]["identity"], "|", body["rule_set"]["rules"], "条规则")
# 三个版本字段分属两套协议：api_version 是传输协议、decision.schema_version 是决策协议，
# policy_version / generation 是协议世代名（phase-1），只与决策协议同进同退。
assert body["api_version"] == API_SCHEMA_VERSION
assert body["decision"]["schema_version"] == core_models.SCHEMA_VERSION
assert body["policy_version"] == core_models.POLICY_VERSION == body["generation"]
assert body["decision"]["policy_version"] == core_models.POLICY_VERSION

# 本地引擎：同一个上下文、同一份规则集（project / agent 由服务端注入，这里显式写出来）。
tenant = RUNTIME.store.get("local-dev")
identity = authorize_local(CONFIG, token=TOKEN, subject="alice", tenant="local-dev")
local_context = build_context(
    {
        "request_id": "06:agree",
        **BASE["context"],
        "project": canonical_identifier(tenant.spec.project),
        "agent": canonical_identifier("api:" + identity.client_id),
    },
    repo_root=tenant.project_root,
)
local_decision = evaluate(tenant.rules(), local_context).to_decision_dict()
print()
print("本地引擎 decision:", local_decision["decision"], "| API decision:", body["decision"]["decision"])
print("两份决策载荷整份相等:", local_decision == body["decision"])
print("传输字段有没有渗进决策载荷:",
      sorted({"budget_ms", "idempotency_key", "api_version"} & set(local_decision)) or "没有")
assert local_decision == body["decision"]
assert not ({"budget_ms", "idempotency_key", "api_version"} & set(local_decision))

evidence_view = post("policy/evaluate", {**BASE, "request_id": "06:skipped", "include_evidence": True}).json()
skipped = evidence_view["skipped_rules"]
print()
print("这条路由只提供上下文: matched =", evidence_view["summary"]["matched"],
      "| skipped =", evidence_view["summary"]["skipped"],
      "| decision =", evidence_view["summary"]["decision"])
print("其中一条:", json.dumps(skipped[0], ensure_ascii=False))
assert skipped and all("rule_id" in item and item["reasons"] for item in skipped)
assert any("需要验证器证据" in reason for item in skipped for reason in item["reasons"])

# 诚实的一处：上下文是**输入**，服务端不猜依赖。同一个文件不声明 dependencies 时，
# ARCH-001 没有证据可判——需要验证器证据的判定走 /v1/validation/evaluate。
blind = post("policy/evaluate", {
    **BASE,
    "request_id": "06:blind",
    "context": {k: v for k, v in BASE["context"].items() if k != "dependencies"},
    "include_evidence": True,
}).json()
print()
print("同一个文件、不声明 dependencies:", blind["summary"])
assert blind["decision"]["decision"] == "allow" and blind["summary"]["skipped"] > 0
assert any("需要验证器证据" in reason for item in blind["skipped_rules"] for reason in item["reasons"])
print("      skipped 是显式记录而不是静默通过；要拿到验证器证据，走 /v1/validation/evaluate。")

# 协议层的失败：全部走真实 HTTP。
raw = {"Authorization": "Bearer " + TOKEN}
protocol_cases = (
    ("body_not_json", "请求体不是合法 JSON",
     CLIENT.post("/v1/policy/evaluate", content=b"{oops", headers={**raw, "Content-Type": "application/json"})),
    ("unsupported_media_type", "Content-Type 不是 application/json",
     CLIENT.post("/v1/policy/evaluate", content=json.dumps(BASE), headers={**raw, "Content-Type": "text/plain"})),
    ("body_too_large", "请求体超过上限", CLIENT.post("/v1/policy/evaluate", content=b"x" * 70000, headers=raw)),
    ("unknown_route", "未知路由", post("teleport", {"request_id": "06:404"})),
    ("wrong_method", "方法不对（GET evaluate）", CLIENT.get("/v1/policy/evaluate", headers=raw)),
)
retrieve_body = {
    "api_version": API_SCHEMA_VERSION,
    "tenant": "local-dev",
    "principal": {"subject": "alice"},
    "query": "controller 边界",
    "context": {"file": "examples/bad_controller.py", "layer": "controller"},
}
protocol_cases += (
    ("forged_decision_ref", "伪造 decision_ref",
     post("knowledge/retrieve", {**retrieve_body, "request_id": "06:forged", "decision_ref": "never-computed"})),
    ("knowledge_unavailable", "租户没配索引（依赖不可用）",
     post("knowledge/retrieve", {**retrieve_body, "request_id": "06:served", "decision_ref": "06:agree"})),
)
for key, label, failed in protocol_cases:
    REJECTED[key] = (label,) + failure_of(failed)
print()
print(pad("场景", 38) + pad("HTTP", 7) + "错误码")
print("-" * 68)
for key, label, failed in protocol_cases:
    print(pad(label, 38) + pad(failed.status_code, 7) + failed.json()["error"]["code"])

# 限流：把容量调成 1（只在内存里改这份配置副本），第二次请求就得到 429。
throttled_config = load_api_config(DEMO_CONFIG, root=REPO_ROOT).model_copy(
    update={
        "rate_limit": CONFIG.rate_limit.model_copy(
            update={"capacity": 1, "refill_per_second": 0.0}
        )
    }
)
throttled = make_client(runtime_from_config(throttled_config, root=REPO_ROOT))
first_call = throttled.post(
    "/v1/policy/evaluate", json={**BASE, "request_id": "06:throttle-1"},
    headers={"Authorization": "Bearer " + TOKEN},
)
second_call = throttled.post(
    "/v1/policy/evaluate", json={**BASE, "request_id": "06:throttle-2"},
    headers={"Authorization": "Bearer " + TOKEN},
)
REJECTED["rate_limited"] = ("限流（令牌桶容量用尽）",) + failure_of(second_call)
print()
print("限流: 第 1 次", first_call.status_code, "| 第 2 次", failure_of(second_call))
assert first_call.status_code == 200 and failure_of(second_call) == (429, "rate_limited")

# 观测日志不可写：把"日志的父目录"做成一个文件，写入必然失败 → 503 audit_unavailable。
blocked = TEMP / "run" / "blocked"
blocked.write_text("这是一个文件，不是目录", encoding="utf-8", newline=chr(10))
try:
    RequestLog(blocked / "audit.jsonl", enabled=True).append(
        RequestLogEntry(route="evaluate", outcome="ok", status=200)
    )
    audit_failure = (200, "written（缺陷）")
except ApiError as error:
    audit_failure = (error.status, error.kind)
REJECTED["audit_unavailable"] = ("观测日志不可写",) + audit_failure
print("观测日志不可写 →", audit_failure, "（决定记不下来，就不返回决定）")
assert audit_failure == (503, "audit_unavailable")

# 失败关闭总表：前面每一节记下的行，这里逐行校验"状态码 = STATUS_BY_CODE[错误码]"。
print()
print(pad("全部失败路径", 40) + pad("HTTP", 7) + "错误码")
print("-" * 72)
for key, (label, status, code) in sorted(REJECTED.items(), key=lambda item: (item[1][1], item[0])):
    print(pad(label, 40) + pad(status, 7) + code)
print("-" * 72)
print("共", len(REJECTED), "条路径，没有一条返回 200。")
assert len(REJECTED) == 21, len(REJECTED)
for key, (label, status, code) in REJECTED.items():
    assert code in {item.value for item in ErrorCode}, (key, code)
    assert STATUS_BY_CODE[ErrorCode(code)] == status, (key, status, code)

log = RUNTIME.request_log
rows = log.read_back()
seal = seal_audit(log)
issues = verify_seal(log, seal)
print()
print("请求级日志条数:", len(rows), "| 锚:", json.dumps(
    {name: seal[name] for name in ("seal_schema_version", "records", "chain_digest")}, ensure_ascii=False))
print("校验锚:", "一致" if not issues else issues)
tampered = TEMP / "run" / "audit.tampered.jsonl"
lines = log.path.read_text(encoding="utf-8").splitlines()
tampered.write_text(chr(10).join(lines[:-1]) + chr(10), encoding="utf-8", newline=chr(10))
tamper_issues = len(verify_seal(RequestLog(tampered), seal))
print("删掉尾部一条后再校验:", tamper_issues, "条问题（删尾是发现得了的）")
print("指标（进程内，重启即归零）:",
      json.dumps(RUNTIME.metrics.to_payload()["status_classes"]))
assert not issues
assert seal["records"] >= 1 and seal["chain_digest"].startswith("sha256:")
assert tamper_issues > 0
print("小结：同一份上下文经本地与经 API 得到整份相等的决策载荷；")
print("      而超时、忙碌、依赖不可用与审计不可写，全部是显式错误码，没有一条被翻译成 allow。")
'''
        ),
        markdown(
            '''
## 小结

- **API 不是第二份业务逻辑**：它只做"协议 → 领域模型 → 协议"，判定仍然只有
  `policy.engine.evaluate` 一条路径——本机实测本地与经 API 的决策载荷**整份相等**，
  且 `budget_ms` / `idempotency_key` / `api_version` 这些传输字段没有渗进决策载荷；
- **两套版本各自演进**：`API_SCHEMA_VERSION`（传输协议 1.0）与
  `SCHEMA_VERSION` / `POLICY_VERSION`（决策协议 1.0 / phase-1）互不相干，
  后者只能从核心取值——本次断言了 `POLICY_GENERATION == POLICY_VERSION`；
- **客户端不能自带证据或决策**：`evidence` / `decision` / `rule_set` / `decision_ref`
  都不是 `/v1/policy/evaluate` 的字段，带上它们一律 400 `body_invalid`；
  检索的 `decision_ref` 只能指向本服务算过的 `request_id`，伪造得到 403 `forbidden`；
- **上下文是输入**：`/v1/policy/evaluate` 只按调用方显式声明的上下文判定——不声明
  `dependencies` 就不会有 ARCH-001 的证据，那 42 条被跳过的规则会如实列在 `skipped_rules` 里
  （显式记录，不是静默通过）；需要验证器证据的判定经 `/v1/validation/evaluate`；
- **租户只来自令牌**：请求体里的 `tenant` 只是提示，越权即 401（不透露存在性）；
  多租户不声明是 403 `token_scope_mismatch`；认证成功不等于允许——
  同一个令牌请求违规文件，判定仍是 `block`；
- **失败关闭没有例外**：本节一共打印了 21 条真实失败路径，每一条的状态码都能由
  `errors.STATUS_BY_CODE[错误码]` 推导出来，没有任何一条返回 200；
  **超时是 504、依赖不可用与观测不可写是 503，绝不等于 allow**；
- **观测只记摘要**：令牌以 `token_ref`（sha256 前 12 位）出现，绝对路径不入日志；
  `seal_audit` + `verify_seal` 能发现删尾——但它仍然是摘要链锚，不是防篡改日志，
  锚必须放到日志写不到的地方才有意义。

往下可以接 `07-LangGraph-编排.ipynb`（谁在什么时候来问 API 要一个 Decision），
或者回头看 `05-代码验证器.ipynb`（`/v1/validation/evaluate` 背后跑的就是那套流水线）。
'''
        ),
    ),
)
