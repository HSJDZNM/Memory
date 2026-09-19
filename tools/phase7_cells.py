"""Phase 7 学习手册的单元内容（被 tools/build_learning_notebook.py 引用）。

单独成文件的原因与 Phase 6 一样：build_learning_notebook.py 已经六千多行，把某一阶段的
讲解再塞进去会让"生成器"和"内容"混在一起。**改动手册内容 = 改这个文件**，然后运行：

    python tools/build_learning_notebook.py --phase phase-7

生成器会从两个工作目录（仓库根与 docs/learning/phase-7/）各跑一遍全部代码单元，
并核对这里写过的结构断言。

本阶段**不使用 exit_code_markers**：Phase 7 是 HTTP / 进程内调用，没有 CLI 退出码
（只有用到 policy_api.cli.run 时才需要），失败一律以结构化错误码与 HTTP 状态码表达。

所有临时产物写在 .tmp/learning-phase-7/ 下，且每轮先删再建——手册会被跑两遍，
第二次不能因为"文件已存在"失败。
"""

from __future__ import annotations

from typing import Any

__all__ = ["PHASE_7_CELLS", "check_phase_7_structure"]


def _markdown(text: str) -> tuple[str, str]:
    return ("markdown", text)


def _code(text: str) -> tuple[str, str]:
    return ("code", text)


PHASE_7_CELLS: list[tuple[str, str]] = [
    _markdown("""
# Phase 7 学习手册：Policy API

这份 notebook 用**实际运行的代码**解释 Phase 7：把已经稳定的核心能力（规则判定、
检索、验证器）服务化，同时说清楚"服务化之后语义没有变"。它不引入新代码，只调用仓库里
已经通过测试的模块，因此每一段输出都可以自己重跑验证。

## Phase 7 要证明的事

    HTTP 请求（JSON + Authorization: Bearer）
      -> policy_api.models.*     DTO（传输协议：信封 + 三个请求体）
      -> ApiRuntime.handle      认证 -> 租户/项目边界 -> 限流/并发 -> 幂等 -> 预算
      -> policy.engine.evaluate 判定（**核心一行未改**）
      -> 决策载荷原样透出 + 脱敏观测（JSONL / 指标 / 摘要链锚定）

一句话：**API 是传输边界，不是第二份业务逻辑**——同一个上下文经本地 SDK 与经 API
必须得到整份相等的决策载荷——JSON 值相等，字段顺序不属于契约（第 7 节会当场断言这一条）。

## 阅读路线

| 小节 | 回答的问题 |
| --- | --- |
| 0 | 跑这份 notebook 需要什么前提 |
| 1 | DTO 与领域模型为什么要分开？两套版本各自怎么演进 |
| 2 | 错误码 -> HTTP 状态码：为什么调用方不能自定义状态 |
| 3 | 部署配置是数据：租户、客户端、预算，明文令牌为什么被拒 |
| 4 | 认证与隔离：令牌 -> 租户/项目边界，失败一律 401 / 403 |
| 5 | 预算与超时：为什么"超时"不等于 allow |
| 6 | 幂等台账：同键同摘要返回原响应，同键换请求体 409 |
| 7 | 进程内走完整链路：本地引擎与 API 的决定整份相等 |
| 8 | readiness 与观测：记了什么、没记什么、锚定怎么校验 |
| 9 | 哪些地方会失败关闭（一张表） |

每个代码单元末尾都有小结。**这份 notebook 不联网、不起端口、不调用 LLM**：
第 7 节用 policy_api.testing.build_runtime + call 在进程内调用同一条判定路径
（HTTP 层只是它的一个调用方），所有产物写在 .tmp/learning-phase-7/ 下，
跑完用 python tools/cleanup.py 清理即可。

## 三个角色

- **DTO**（policy_api.models）：线上协议。它认识 api_version / budget_ms /
  idempotency_key 这些传输字段，而核心的 PolicyContext 不认识它们；
- **ApiRuntime**（policy_api.runtime）：部署边界上的横切关注点——认证、隔离、限流、
  幂等、预算、观测。它**不做判定**；
- **Policy Engine**（policy.engine）：唯一的判定入口，Phase 7 没有改它一行。
"""),
    _markdown("""
## 0. 前提：怎么跑、需要什么

- Python >= 3.11（仓库实际用 3.13）、pydantic 2、PyYAML；
- **不需要安装 src/**：下面第一个代码单元自己把 src/ 与 tools/ 加进 sys.path；
- **不需要起服务、不需要网络**：第 7 节用进程内调用助手 policy_api.testing.call；
- **不碰仓库真实文件**：所有演示产物写在 .tmp/learning-phase-7/ 下，而且每个代码单元
  开始前先清理——这份手册会被**从两个工作目录各跑一遍**（仓库根与 docs/learning/phase-7/），
  临时目录因此必须每轮从零开始。

```powershell
$env:PYTHONPATH = 'src'
jupyter lab docs/learning/phase-7/walkthrough.ipynb   # 交互式阅读
python docs/learning/phase-7/walkthrough.py           # 纯 Python 版，直接看输出
```

第一个代码单元的末尾会多出一小段生成器追加的表格工具函数（pad / display_width）：
中英混排的表格必须按**显示宽度**补位——f-string 的宽度写法数的是字符个数，
而中文在等宽字体里占 2 列，列会被挤歪。
"""),
    _code("""
# 0. 起步：定位仓库、把 src/ 加进 sys.path、准备一个干净的演示目录

import json
import shutil
import sys
from pathlib import Path


def find_repo_root(start):
    '''从当前工作目录向上找仓库根：含 pyproject.toml / policies / .git 的那一层。'''

    candidate = Path(start).resolve()
    for _ in range(8):
        if any((candidate / marker).exists() for marker in ('pyproject.toml', 'policies', '.git')):
            return candidate
        candidate = candidate.parent
    raise AssertionError('找不到仓库根')


REPO_ROOT = find_repo_root(Path.cwd())
NOTEBOOK_DIR = REPO_ROOT / 'docs' / 'learning' / 'phase-7'
# 仓库不把 src 装进 site-packages：import policy 与 policy_api 全靠这条路径。
for extra in (REPO_ROOT / 'src', REPO_ROOT / 'tools'):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import policy_api  # noqa: E402
import policy_api.models as api_models  # noqa: E402
from policy import models as core_models  # noqa: E402
from policy_api.config import ConfigError, hash_token, load_api_config  # noqa: E402
from policy_api.errors import STATUS_BY_CODE, ApiError, ErrorCode, error_payload  # noqa: E402
from policy_api.models import (  # noqa: E402
    API_SCHEMA_VERSION,
    SUPPORTED_API_SCHEMA_VERSIONS,
    EvaluateRequest,
)
from pydantic import ValidationError  # noqa: E402


def display_width(text):
    '''文本在等宽字体里占多少列：全角/宽字符算 2 列，其余算 1 列。'''

    return sum(2 if ord(char) > 0x2E7F else 1 for char in str(text))


def pad(text, width, align='left'):
    '''按显示宽度把文本补齐到 width 列（中英混排的表格靠它对齐）。'''

    text = str(text)
    blanks = ' ' * max(0, width - display_width(text))
    if align == 'right':
        return blanks + text
    return text + blanks


# 演示产物只写 .tmp/：每轮先删再建，第二次运行不能因为"文件已存在"失败。
DEMO = REPO_ROOT / '.tmp' / 'learning-phase-7'
shutil.rmtree(DEMO, ignore_errors=True)
DEMO.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = REPO_ROOT / 'api' / 'policy-api.yaml'

print('Python:', sys.version.split()[0])
print('仓库根:', REPO_ROOT.name, '| 工作目录:', Path.cwd().name or str(Path.cwd()))
print('policy_api 版本:', policy_api.__version__)
print('演示目录:', DEMO.relative_to(REPO_ROOT).as_posix(), '（每轮从空目录开始）')
"""),
    _markdown("""
## 1. DTO 与领域模型分开：两套版本各自演进

policy_api.models 是**传输协议**，policy.models 是**领域模型 + 决策协议**。
两套版本刻意分开：

| 版本 | 位置 | 值 | 变了意味着什么 |
| --- | --- | --- | --- |
| 传输协议 | policy_api.models.API_SCHEMA_VERSION | 1.0 | 线上请求/响应字段变了（删字段、改语义）= 新 API 版本，且必须显式更新 api/openapi.json 快照 |
| 决策协议 | policy.models.SCHEMA_VERSION | 1.0 | 决策载荷（PolicyDecision）变了 |
| 协议世代名 | policy.models.POLICY_VERSION | phase-1 | 与决策协议同进同退，**不跟随平台阶段** |

policy_api 只从核心**取值**（DECISION_PAYLOAD_SCHEMA_VERSION = SCHEMA_VERSION、
POLICY_GENERATION = POLICY_VERSION），不许自己算一个——"证据说 phase-5、载荷说 phase-1"
这类漂移正是这条纪律要避免的。

请求体是**信封 + 载荷**：api_version / request_id / tenant / trace_id / budget_ms /
idempotency_key / credentials 是横切字段，principal / context 是业务载荷。三条拒绝
规则都发生在模型层：

1. 缺 api_version -> schema_version_missing（400）；
2. 未知 api_version -> schema_version_unknown（400）；
3. 未发布字段（例如客户端想自带一份 evidence）-> extra="forbid" -> 400 body_invalid。
   证据只能由服务端的验证器流水线产出，客户端连"提交证据"这个动作都做不到。
"""),
    _code("""
# 1. DTO 与领域模型：两套版本、信封形态、未知字段一律拒绝

api_schema_version = API_SCHEMA_VERSION
decision_versions = (core_models.SCHEMA_VERSION, core_models.POLICY_VERSION)
print('传输协议 API_SCHEMA_VERSION:', api_schema_version,
      '| 本服务接受的版本:', sorted(SUPPORTED_API_SCHEMA_VERSIONS))
print('决策协议 policy.models.SCHEMA_VERSION:', core_models.SCHEMA_VERSION)
print('协议世代 policy.models.POLICY_VERSION:', core_models.POLICY_VERSION)
print('policy_api 只取值、不自算版本:', api_models.POLICY_GENERATION == core_models.POLICY_VERSION)
print()

base = {
    'api_version': api_schema_version,
    'request_id': 'learn:dto',
    'tenant': 'local-dev',
    'principal': {'subject': 'alice', 'roles': ['developer']},
    'context': {'file': 'examples/bad_controller.py', 'layer': 'controller'},
}
request = EvaluateRequest.model_validate(base)
print('请求体顶层字段:', ', '.join(sorted(request.model_dump(exclude_none=True))))
print('context 字段:', ', '.join(sorted(request.context.model_dump(exclude_none=True))))
print()


def dto_rejection(body):
    '''返回这个请求体被拒绝的方式：错误码，或 pydantic 的字段错误。'''

    try:
        EvaluateRequest.model_validate(body)
    except ApiError as error:
        return error.kind
    except ValidationError as error:
        first = error.errors()[0]
        where = '.'.join(str(part) for part in first['loc'])
        return 'body_invalid <- ' + where + ': ' + str(first['msg'])
    return '放行了（缺陷）'


dto_cases = {
    'missing_version': {key: value for key, value in base.items() if key != 'api_version'},
    'unknown_version': {**base, 'api_version': '2.0'},
    'unknown_field': {**base, 'evidence': {'bundle': 'client-supplied'}},
}
dto_reports = {label: dto_rejection(body) for label, body in dto_cases.items()}
dto_error_codes = {label: text.split(' <-')[0] for label, text in dto_reports.items()}
print(pad('场景', 18) + '拒绝方式')
print('-' * 72)
for label, text in dto_reports.items():
    print(pad(label, 18) + text)
print()
print('小结：传输协议 1.0 与决策协议 1.0 / phase-1 各自演进；缺版本、未知版本、未知字段'
      '都不得静默忽略，客户端也无法自带证据。')
"""),
    _markdown("""
## 2. 错误码 -> 状态码：调用方不能自定义 HTTP 状态

ErrorCode 是**受控枚举**，STATUS_BY_CODE 是它到 HTTP 状态的唯一映射：
ApiError.status 从表里查，路由处理函数没有任何机会写一个"更合适"的状态码。
三条关键语义：

1. **跨租户与不存在同码**：tenant_not_found 与 not_found 都是 404，forbidden 与
   token_scope_mismatch 都是 403——错误码本身不能成为"某个租户/资源是否存在"的探针；
2. **超时是 504、依赖不可用是 503**：都不是 200，都不是 allow；
3. **错误响应形状固定**（error_payload）：code / detail / retryable / request_id /
   trace_id，其中 detail 经 redact_detail 压成单行并限量，异常原文不透传
   （它可能带绝对路径或内部配置名）。
"""),
    _code("""
# 2. 错误码 -> 状态码

status_codes = {code.value: STATUS_BY_CODE[code] for code in ErrorCode}
print(pad('错误码', 34) + 'HTTP')
print('-' * 42)
for code in ErrorCode:
    print(pad(code.value, 34) + str(STATUS_BY_CODE[code]))
print('-' * 42)
print('错误码总数:', len(status_codes))
print('404 上的错误码（刻意同码，避免用错误码探测存在性）:',
      sorted(name for name, value in status_codes.items() if value == 404))
print()

sample_error = ApiError(ErrorCode.EVALUATE_TIMEOUT, '策略判定超出预算 2000ms；未给出结论（不伪造 allow）',
                        retryable=True)
api_error_status = sample_error.status
print('状态码来自错误码，不由调用方决定:', sample_error.kind, '->', api_error_status)
print('错误响应形状: error ->', ', '.join(sorted(error_payload(sample_error)['error'])))
print()
print('小结：状态码是错误码的**推论**；跨租户与不存在同码，所以错误码不能用来探测资源是否存在。')
"""),
    _markdown("""
## 3. 配置即数据：api/policy-api.yaml

部署配置决定服务身份、预算、限额、限流、**租户边界**与**客户端令牌**（只存 sha256）。
三条硬规则：

1. **每个租户自带边界**：规则目录、项目根、（可选）检索索引与验证器配置。
   没有声明边界的租户不装配——"默认集合"这种跨租户搜索在 Phase 7 不存在；
2. **令牌只存 sha256**：配置里出现明文令牌一律拒绝加载，因为配置文件会被提交、被备份，
   写明文等于把凭据散出去；
3. **路径锚点显式**：先按 --root（这里是仓库根）解析，解析不到再按配置文件所在目录。

租户 local-dev 的 project_root 是 "."（仓库根），fixture-shop 指向 Phase 5 的夹具项目
tests/fixtures/validators/project；两者用的都是仓库里的 policies/，所以"本地引擎与 API
的决定一致"这件事比的是**判定**，不是"两套规则碰巧给出同样的结果"。
"""),
    _code("""
# 3. 加载仓库的部署配置（数据，不是代码）

config = load_api_config(CONFIG_PATH, root=REPO_ROOT)
tenant_ids = [item.tenant_id for item in config.tenants]
client_ids = [item.client_id for item in config.clients]
budgets = config.budgets.model_dump()
print('服务:', json.dumps({'schema_version': config.schema_version, 'service_name': config.service_name,
                          'deployment': config.deployment, 'base_url': config.base_url}, ensure_ascii=False))
print('预算(ms):', json.dumps(budgets), '| 幂等台账 TTL(s):', config.idempotency_ttl_seconds)
print('限流:', json.dumps(config.rate_limit.model_dump()),
      '| 并发上限:', config.limits.max_concurrency,
      '| 指标白名单:', list(config.metrics_clients))
print()
print(pad('租户', 14) + pad('项目', 14) + pad('项目根', 36) + pad('规则目录', 34) + '验证器配置')
print('-' * 112)
for item in config.tenants:
    print(pad(item.tenant_id, 14) + pad(item.project or '-', 14)
          + pad(Path(item.project_root).as_posix(), 36)
          + pad(','.join(item.rules), 34) + (item.validators or '（未配置）'))
print()
print(pad('客户端', 14) + pad('令牌摘要前12位', 18) + pad('可用租户', 26) + pad('角色', 12) + '过期')
print('-' * 86)
for client in config.clients:
    print(pad(client.client_id, 14) + pad(client.token_sha256[:12], 18)
          + pad(','.join(client.tenants), 26) + pad(','.join(client.roles) or '-', 12)
          + (client.expires_at or '不过期'))
print()
print('配置里存的是摘要、不是明文:', hash_token('local-dev-token') == config.clients[0].token_sha256)
print()

# 明文令牌：写一份坏配置，加载必须失败——不是"先跑起来再说"。
bad_dir = DEMO / 'bad-config'
bad_dir.mkdir(parents=True, exist_ok=True)
bad_config = bad_dir / 'policy-api.yaml'
bad_config.write_text(chr(10).join([
    'schema_version: "1.0"',
    'tenants:',
    '  - tenant_id: local-dev',
    '    project_root: .',
    '    rules_root: .',
    '    rules: [policies]',
    'clients:',
    '  - client_id: leaked',
    '    token_sha256: super-secret-plaintext-token',
    '    tenants: [local-dev]',
]) + chr(10), encoding='utf-8', newline=chr(10))
config_error = ''
try:
    load_api_config(bad_config, root=REPO_ROOT)
except ConfigError as error:
    config_error = str(error)
plaintext_rejected = bool(config_error) and '明文令牌' in config_error
print('明文令牌被拒绝加载:', plaintext_rejected)
print('   ', config_error.split('->')[-1].strip()[:88])
print()
print('小结：租户边界、客户端、预算、限流与观测落点全部来自这一份数据；'
      '明文令牌连加载都过不去。')
"""),
    _markdown("""
## 4. 认证与隔离：令牌 -> 租户/项目边界

policy_api.auth.authorize 只回答"你是谁、你能用哪些租户/项目"，它**不是**授权结论：
业务动作仍由 Policy Engine 判定（服务身份不替用户扩权）。四条不可交换的顺序：

1. **租户只来自令牌**：请求体里的 tenant 只是"我想用哪个"的提示，越权即拒绝；
2. **多租户必须显式声明**：一个令牌被授权多个租户时，服务端**不会替你选一个**；
3. **失败不透露存在性**：未知令牌与越权租户对外是同一个 401；
   "租户不可用"（404 tenant_not_found）只在令牌授权的租户无法服务时才是另一回事；
4. **日志里没有明文**：令牌只以 sha256 前 12 位（AuthContext.token_ref）出现在观测里，
   认证用 hmac.compare_digest 逐条比较摘要，明文不参与任何索引结构。
"""),
    _code("""
# 4. 认证：正确路径 + 四条失败路径

from policy_api.auth import authorize

auth = authorize(config, token='local-dev-token', subject='alice', tenant='local-dev')
auth_tenant = auth.tenant
auth_token_ref = auth.token_ref
print('认证成功:', auth.client_id, '| 租户:', auth.tenant, '| 角色:', ','.join(auth.roles))
print('日志里的令牌引用 token_ref:', auth.token_ref, '（sha256 前 12 位；明文不进日志）')
print()

# 过期凭据：把配置里的一个客户端改成"2000 年就过期"，其余一字不改。
expired_client = config.clients[0].model_copy(update={'expires_at': '2000-01-01T00:00:00Z'})
expired_config = config.model_copy(update={'clients': (expired_client, *config.clients[1:])})

auth_cases = (
    ('unknown_token', '未知令牌', config,
     {'token': 'not-a-real-token', 'subject': 'alice', 'tenant': 'local-dev'}),
    ('cross_tenant', '越权租户（dsh-agent 用 local-dev）', config,
     {'token': 'dsh-agent-token', 'subject': 'alice', 'tenant': 'local-dev'}),
    ('expired', '凭据过期', expired_config,
     {'token': 'local-dev-token', 'subject': 'alice', 'tenant': 'local-dev'}),
    ('multi_tenant', '多租户却不声明 tenant', config,
     {'token': 'local-dev-token', 'subject': 'alice'}),
)
auth_results = {}
print(pad('场景', 40) + pad('HTTP', 7) + '错误码')
print('-' * 68)
for key, label, used_config, kwargs in auth_cases:
    try:
        authorize(used_config, route='evaluate', **kwargs)
        auth_results[key] = (200, 'authorized')
    except ApiError as error:
        auth_results[key] = (error.status, error.kind)
    status, kind = auth_results[key]
    print(pad(label, 40) + pad(status, 7) + kind)
auth_failure_codes = {key: kind for key, (status, kind) in auth_results.items()}
print()
print('AuthContext 是**授权输入**而不是授权结论：认证成功不等于允许某个工具。')
print('小结：租户只来自令牌；未知令牌 / 越权租户 / 过期都是 401，多租户不声明是 403。')
"""),
    _markdown("""
## 5. 预算与超时：(None, timed_out=True) 不是 allow

budget_for 决定本次请求的墙钟预算：**路由默认值，调用方只能要更小的**（要更大一律
503 request_budget_exceeded）。run_with_budget 在预算内运行操作：

- 正常结束 -> (结果, Elapsed(timed_out=False))；
- 预算耗尽 -> (None, Elapsed(timed_out=True))，调用方必须把它翻译成
  evaluate_timeout / retrieve_timeout / validate_timeout（504）。

一句必须诚实的话：Python 没有可移植的线程取消，"超时"的语义是**调用方不再等待、
结果被丢弃**，而不是"工作已经停止"。正因为如此，超时绝不能变成 allow。
"""),
    _code("""
# 5. 预算与超时

import time
from policy_api.runtime import budget_for
from policy_api.timeout import run_with_budget

budget_defaults = {route: budget_for(route, config, None)
                   for route in ('evaluate', 'retrieve', 'validate')}
granted = budget_for('evaluate', config, 500)
try:
    budget_for('evaluate', config, 100000)
    budget_too_large = (200, 'granted')
except ApiError as error:
    budget_too_large = (error.status, error.kind)
print('路由默认预算(ms):', json.dumps(budget_defaults))
print('调用方要 500ms ->', granted, 'ms（更小是允许的）')
print('调用方要 100000ms ->', budget_too_large[0], budget_too_large[1], '（更大一律拒绝）')
print()

value, elapsed = run_with_budget(lambda: '判定结果', budget_ms=500)
slow_value, slow_elapsed = run_with_budget(lambda: time.sleep(0.25), budget_ms=60)
timeout_result = (slow_value is None, slow_elapsed.timed_out)
print('正常分支: 值 =', value, '| timed_out =', elapsed.timed_out)
print('超时分支: 值 =', slow_value, '| timed_out =', slow_elapsed.timed_out,
      '| 调用方实际等待约', int(slow_elapsed.milliseconds), 'ms')
print()
print('小结：预算到点只有两种结果——拿到结论，或拿到 *_timeout（504）；'
      '没有"降级成 allow"这第三种。线程仍会把那次判定跑完，但结果被丢弃。')
"""),
    _markdown("""
## 6. 幂等台账：同一个 key 只有一个结论

判定类路由（evaluate / retrieve）不写业务状态，但它们的结论会被写进观测日志、
可能被上层当成"已经授权过一次"的依据，因此同样按键去重：

| 情况 | 结果 |
| --- | --- |
| 同一个 idempotency_key + 同一个请求摘要 | 返回**原来那份响应**，响应头 Idempotency-Replayed: true |
| 同一个 key + 不同的请求摘要 | 409 idempotency_key_conflict（不覆盖、不合并） |
| 台账读写不可用 | 503 idempotency_unavailable（宁可拒绝，也不重复判定一次） |

台账是**每个租户一份**、**整份重写**的 JSONL：条目键是
<client_id>|<api_version>|<route>|<key>，读取时顺带压缩过期项。整份重写而不是追加写，
是因为"同一个 key 只能有一个结论"——追加写会留下互相矛盾的历史，而台账要回答的
正是"上次那个 key 的结论是什么"。
"""),
    _code("""
# 6. 幂等台账（写在 .tmp/learning-phase-7/ 下）

from policy_api.idempotency import IdempotencyLedger, request_digest

ledger = IdempotencyLedger(DEMO / 'idempotency' / 'local-dev.jsonl', ttl_seconds=900)
key = 'learn-key-1'
digest = request_digest({'route': 'evaluate', 'payload': {'request_id': 'learn:ledger'}})


def ledger_lookup(value):
    '''查一次台账；冲突时返回 ApiError 而不是抛出去，方便打印。'''

    try:
        return ledger.lookup(client_id='local-dev', api_version=API_SCHEMA_VERSION,
                             route='evaluate', key=key, digest=value)
    except ApiError as error:
        return error


miss = ledger_lookup(digest)
ledger.record(client_id='local-dev', api_version=API_SCHEMA_VERSION, route='evaluate',
              key=key, digest=digest, status=200,
              body={'decision': 'allow', 'request_id': 'learn:ledger'})
hit = ledger_lookup(digest)
conflict = ledger_lookup('0' * 64)
ledger_codes = {'hit_status': hit.status, 'conflict': conflict.status}
print('首次查询（台账为空）:', miss)
print('同键同摘要:', hit.status, json.dumps(hit.body, ensure_ascii=False),
      '| 摘要前 12 位:', hit.digest[:12])
print('同键换摘要:', conflict.status, conflict.kind)
print()

entry = next(iter(ledger.entries().values()))
print('台账条目的键:', entry['entry_key'])
print('台账字段:', ', '.join(sorted(entry)))
print()
print('小结：同一个 key 只有一个结论——重放返回原响应，换请求体是 409，'
      '不是"再算一次"；台账按租户分文件，A 的 key 永远不会命中 B 的台账。')
"""),
    _markdown("""
## 7. 进程内走完整链路：本地引擎与 API 的决定整份相等

policy_api.testing.build_runtime + call 在**进程内**调用 ApiRuntime.handle——和 HTTP
层调的是同一个函数，只是没有 socket。本节要证明三件事：

1. policy.engine.evaluate 算出的决策载荷，与 API 返回的 body["decision"]
   **整份相等**（整份字典相等）——API 只做"协议 -> 领域模型 -> 协议"，不改写核心协议；
   这里比的是 **JSON 值**：两侧的序列化入口不同，字段顺序不属于契约；
2. 失败关闭在真实链路上生效：未知字段 400、未认证 401、伪造 decision_ref 403；
3. **授权先于可用性**：retrieve 先回答"这次请求有没有资格用那份决策"，再去问
   "语料 / 索引在不在"。所以伪造引用得到 403 forbidden，而合法引用在没有配置索引的
   租户上得到 503 knowledge_unavailable——两个错误码不会被混成一个。检索的 context
   也是**必需**的：文件与层级必须由调用方显式声明，服务端不推断，也不允许
   "没有上下文就按租户的默认集合检索"（那等于把边界交给服务端猜）。

为了让本地与 API 用**同一份规则集**，本节用仓库配置构建运行时，只把**写入落点**
（观测日志与租户台账）改到 .tmp/learning-phase-7/ 下，其余字段一字不改。
"""),
    _code("""
# 7. 进程内整条链路：build_runtime + call

import yaml
from policy.context import build_context
from policy.engine import evaluate
from policy.models import canonical_identifier
from policy_api.testing import build_runtime, call

document = config.model_dump(mode='json')
document['audit']['path'] = (DEMO / 'run' / 'audit.jsonl').relative_to(REPO_ROOT).as_posix()
for spec in document['tenants']:
    if spec.get('audit_log'):
        spec['audit_log'] = (DEMO / 'run' / 'tenants' / spec['tenant_id']
                             / 'audit.jsonl').relative_to(REPO_ROOT).as_posix()
demo_config = DEMO / 'run' / 'policy-api.yaml'
demo_config.parent.mkdir(parents=True, exist_ok=True)
demo_config.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
                       encoding='utf-8', newline=chr(10))

runtime = build_runtime(demo_config, root=REPO_ROOT)
TOKEN = 'local-dev-token'
print('装配的租户:', ', '.join(runtime.store.ids), '| 装配错误:', runtime.store.errors or '无')
print('观测日志落点:', runtime.request_log.path.relative_to(REPO_ROOT).as_posix())
print('幂等台账落点:', runtime.ledger_for('local-dev').path.relative_to(REPO_ROOT).as_posix())
print()

context = {'file': 'examples/bad_controller.py', 'layer': 'controller', 'language': 'python',
           'dependencies': ['repository']}
evaluate_body = {'api_version': API_SCHEMA_VERSION, 'request_id': 'learn:agree',
                 'tenant': 'local-dev',
                 'principal': {'subject': 'alice', 'roles': ['developer']},
                 'context': context}
response = call(runtime, 'evaluate', evaluate_body, token=TOKEN)
print('evaluate:', response.status, json.dumps(response.body['summary'], ensure_ascii=False))
print('命中规则:', ', '.join(response.body['decision']['matched_rules']),
      '| 违规规则:', ', '.join(item['rule_id'] for item in response.body['decision']['violations']))
print('规则集:', response.body['rule_set']['hash'][:26] + '...',
      '|', response.body['rule_set']['rules'], '条规则 |', response.body['rule_set']['identity'])
print('耗时:', response.body['timing'])
print()

# 本地引擎：同一个上下文、同一份规则集（agent 与 project 由服务端注入，这里显式写出来）
tenant = runtime.store.get('local-dev')
api_identity = authorize(config, token=TOKEN, subject='alice', tenant='local-dev')
local_context = build_context(
    {'request_id': 'learn:agree', **context,
     'project': canonical_identifier(tenant.spec.project),
     'agent': canonical_identifier('api:' + api_identity.client_id)},
    repo_root=tenant.project_root,
)
local_decision = evaluate(tenant.rules(), local_context).to_decision_dict()
remote_decision = response.body['decision']
decision_equal = local_decision == remote_decision
remote_decision_code = remote_decision['decision']
violation_rule_ids = [item['rule_id'] for item in remote_decision['violations']]
print('本地引擎 decision:', local_decision['decision'], '| API decision:', remote_decision['decision'])
print('整份决策载荷相等:', decision_equal)
print()

# 失败关闭：未知字段 / 未认证 / 伪造 decision_ref / 授权通过但依赖不可用
unknown_field = call(runtime, 'evaluate', {**evaluate_body, 'request_id': 'learn:unknown',
                                           'evidence': {'client': 'supplied'}}, token=TOKEN)
unauthenticated = call(runtime, 'evaluate', {**evaluate_body, 'request_id': 'learn:noauth'},
                       token='not-a-real-token')
retrieve_body = {'api_version': API_SCHEMA_VERSION, 'tenant': 'local-dev',
                 'principal': {'subject': 'alice'}, 'query': 'controller 边界',
                 'context': {'file': 'examples/bad_controller.py', 'layer': 'controller'}}
forged = call(runtime, 'retrieve', {**retrieve_body, 'request_id': 'learn:forged',
                                    'decision_ref': 'never-computed'}, token=TOKEN)
served = call(runtime, 'retrieve', {**retrieve_body, 'request_id': 'learn:served',
                                    'decision_ref': 'learn:agree'}, token=TOKEN)
print('未知字段:', unknown_field.status, unknown_field.body['error']['code'])
print('未认证:', unauthenticated.status, unauthenticated.body['error']['code'])
print('伪造 decision_ref:', forged.status, forged.body['error']['code'])
print('合法 decision_ref（该租户没配索引）:', served.status, served.body['error']['code'])
retrieve_codes = {'forged': forged.body['error']['code'], 'served': served.body['error']['code']}
print()
print('小结：判定仍然只有 policy.engine.evaluate 一条路径；API 与本地得到整份相等的'
      '决策载荷，而授权结论先于可用性结论。')
"""),
    _markdown("""
## 8. readiness 与观测：记了什么、没记什么

- **liveness 与 readiness 是两件事**：/v1/health/live 只回答"进程还活着"；
  readiness() 回答"能**安全地提供策略服务**"——逐租户检查规则集 / 索引 / 验证器 /
  观测日志，任何一项失败就不是 ready；
- 请求级 JSONL 只记摘要：request_id / trace_id / 主体 / 租户 / 规则集哈希 / 索引版本 /
  Decision / 耗时 / 错误分类 / 状态码；
- **不记**：完整 Prompt、文档正文、原始工具参数、令牌、绝对路径、控制字符
  （落盘前复用 Phase 4 已经验证过的 redact_text / sanitize_payload）；
- 观测日志**不可写就失败关闭**（503 audit_unavailable）：决定记不下来，就不返回决定；
- **一个已知的实现缺陷**（手册照实显示、不做绕过）：租户的 validators 是配置里的相对
  路径，而它由加载方按**进程工作目录**解析；租户的其余路径都按 --root 锚定，只有它漏了。
  于是从仓库根启动时 readiness 是 ready，从 docs/learning/phase-7/ 启动时同一个租户
  会被如实报成"验证器不可服务"——readiness 没有说谎，但配置的锚定规则被破坏了一处；
- seal_audit 把摘要链末值封成可对外发布的锚，verify_seal 检查日志是否被动过。
  它是**摘要链不是防篡改日志**：锚必须放到日志写不到的地方才有意义。
"""),
    _code("""
# 8. readiness、观测记录与锚定

from policy_api.observability import RequestLog, seal_audit, verify_seal

readiness = runtime.readiness(force=True)
readiness_state = readiness['state']
readiness_tenants = {item['tenant']: item['ok'] for item in readiness['tenants']}
readiness_checks = {(item['tenant'], check['check']): check['ok']
                    for item in readiness['tenants'] for check in item['checks']}
# readiness 的结论必须与逐项检查**一致**：任何一项失败就不是 ready。
readiness_aggregate_ok = (readiness_state == 'ready') == all(readiness_tenants.values())
readiness_rule_sets_ok = all(ok for (tenant, name), ok in readiness_checks.items() if name == 'rule_set')
readiness_index_checks_ok = all(ok for (tenant, name), ok in readiness_checks.items() if name == 'index')
readiness_failures = [(item['tenant'], check['check'], check['detail'])
                      for item in readiness['tenants'] for check in item['checks'] if not check['ok']]
readiness_failed_checks = tuple((tenant, name) for tenant, name, detail in readiness_failures)
try:
    cwd_label = Path.cwd().relative_to(REPO_ROOT).as_posix() or '.'
except ValueError:
    cwd_label = str(Path.cwd())
print('工作目录:', cwd_label)
print('readiness:', readiness_state, '| ready =', readiness['ready'], '|', readiness['detail'])
print()
print(pad('租户', 14) + pad('可服务', 8) + '检查项')
print('-' * 88)
for item in readiness['tenants']:
    checks = ' | '.join(name['check'] + ('=ok' if name['ok'] else '=fail') for name in item['checks'])
    print(pad(item['tenant'], 14) + pad('是' if item['ok'] else '否', 8) + checks)
print()
for tenant_id, name, detail in readiness_failures:
    print('未通过的检查:', tenant_id + '/' + name, '->', detail)
if ('fixture-shop', 'validators') in readiness_failed_checks:
    print('   说明：租户 fixture-shop 的 validators 是配置里的**相对路径**')
    print('   （validation/validators.yaml），而它由加载方按**进程工作目录**解析；')
    print('   从仓库根启动时能解析，从 docs/learning/phase-7/ 启动时解析不到。')
    print('   这是实现里的一个真实缺陷（租户的其余路径都按 --root 锚定，只有 validators 漏了），')
    print('   手册照实显示它，而不是改配置把它绕过去。')
print()
print('readiness 的结论与逐项检查一致:', readiness_aggregate_ok)
print()

log = runtime.request_log
rows = log.read_back()
# 取那次成功的 evaluate 记录：它才带 decision / violations / rule_set_hash。
last = next(row for row in rows if row['request_id'] == 'learn:agree')
log_path_under_demo = str(log.path).startswith(str(DEMO))
log_fields = tuple(sorted(last))
print('日志记录数:', len(rows), '| 落点在演示目录内:', log_path_under_demo)
print('一条记录:', json.dumps({name: last[name] for name in
      ('route', 'outcome', 'status', 'tenant', 'client_id', 'token_ref', 'decision',
       'violations', 'elapsed_ms', 'replayed')}, ensure_ascii=False))
print('记录字段:', ', '.join(log_fields))
not_recorded = ('token', 'token_sha256', 'authorization', 'credentials', 'prompt',
                'document', 'params', 'text', 'file')
log_omits_secrets = tuple(name for name in not_recorded if name in log_fields)
log_has_absolute_path = str(REPO_ROOT) in json.dumps(last, ensure_ascii=False)
print('这些字段没有出现在日志里:', ', '.join(log_omits_secrets) or '（一个都没有）')
print('日志里含仓库绝对路径:', log_has_absolute_path)
print()

seal = seal_audit(log)
issues = verify_seal(log, seal)
seal_ok = not issues
print('锚:', json.dumps({name: seal[name] for name in
      ('seal_schema_version', 'records', 'chain_digest')}, ensure_ascii=False))
print('校验锚:', '一致' if seal_ok else issues)
tampered_copy = DEMO / 'run' / 'audit.tampered.jsonl'
lines = log.path.read_text(encoding='utf-8').splitlines()
tampered_copy.write_text(chr(10).join(lines[:-1]) + chr(10), encoding='utf-8', newline=chr(10))
tamper_issues = len(verify_seal(RequestLog(tampered_copy), seal))
print('把尾部删掉一条后再校验:', tamper_issues, '条问题（删尾是发现得了的）')
print()
print('指标（进程内，重启即归零）:', json.dumps(runtime.metrics.to_payload()['status_classes']))
print('小结：readiness 把"进程活着"与"能安全服务"分开；观测只记摘要、不记原文与凭据，'
      '而锚把"日志有没有被动过"变成一个可校验的结论。')
"""),
    _markdown("""
## 9. 哪些地方会失败关闭

Phase 7 的纪律是：**任何一步失败都返回结构化错误码，"策略不可用"绝不等价于
"策略说可以"。**下面这张表的每一行都来自本次运行真实发生的调用，不是抄来的清单。

| 场景 | 结果 |
| --- | --- |
| 缺 / 未知 api_version | 400 schema_version_missing / schema_version_unknown |
| 未发布字段（例如自带 evidence） | 400 body_invalid |
| 未认证 / 越权租户 / 凭据过期 | 401 unauthenticated / token_expired |
| 多租户不显式声明 | 403 token_scope_mismatch |
| 伪造 decision_ref | 403 forbidden |
| 依赖不可用（索引 / 规则集 / 验证器） | 503 knowledge_unavailable / rule_set_unavailable / validator_unavailable |
| 要更大的预算 | 503 request_budget_exceeded |
| 判定超时 | 504 evaluate_timeout |
| 观测日志不可写 | 503 audit_unavailable |
| 指标端点无权限 | 403 metrics_forbidden |
| 未知路由 | 404 not_found |

注意"同码"这一列的设计：not_found（资源不存在）与 tenant_not_found（租户不可用）
都是 404，forbidden 与 token_scope_mismatch 都是 403——**错误码不能成为存在性探针**。
"""),
    _code("""
# 9. 失败关闭对照表（每一行都是本次运行真实发生的调用）

import policy_api.runtime as runtime_module
from policy_api.observability import RequestLogEntry


def slow_evaluate(rules, context):
    '''把判定拖慢，用来证明"预算到点返回 504"而不是 allow。'''

    time.sleep(0.3)
    from policy.engine import evaluate as real_evaluate
    return real_evaluate(rules, context)


saved_evaluate = runtime_module.evaluate
runtime_module.evaluate = slow_evaluate
try:
    timed_out = call(runtime, 'evaluate', {'api_version': API_SCHEMA_VERSION,
                                           'request_id': 'learn:timeout', 'tenant': 'local-dev',
                                           'budget_ms': 50, 'principal': {'subject': 'alice'},
                                           'context': context}, token=TOKEN)
finally:
    runtime_module.evaluate = saved_evaluate
print('判定超时:', timed_out.status, timed_out.body['error']['code'],
      '| retryable =', timed_out.body['error']['retryable'])
print()

metrics_forbidden = call(runtime, 'metrics', {}, token=TOKEN)
unknown_route = call(runtime, 'teleport', {'request_id': 'learn:route'}, token='dsh-agent-token')

# 观测日志不可写：把"日志的父目录"做成一个文件，写入必然失败。
blocked = DEMO / 'blocked'
blocked.write_text('这是一个文件，不是目录', encoding='utf-8')
try:
    RequestLog(blocked / 'audit.jsonl', enabled=True).append(
        RequestLogEntry(route='evaluate', outcome='ok', status=200))
    audit_code = '放行了（缺陷）'
except ApiError as error:
    audit_code = error.kind

fail_closed_rows = [
    ('missing_version', '缺 api_version', '400', dto_error_codes['missing_version']),
    ('unknown_version', '未知 api_version', '400', dto_error_codes['unknown_version']),
    ('unknown_field', '未发布字段（自带 evidence）', '400', dto_error_codes['unknown_field']),
    ('unknown_token', '未知令牌', str(auth_results['unknown_token'][0]), auth_failure_codes['unknown_token']),
    ('cross_tenant', '越权租户', str(auth_results['cross_tenant'][0]), auth_failure_codes['cross_tenant']),
    ('expired', '凭据过期', str(auth_results['expired'][0]), auth_failure_codes['expired']),
    ('multi_tenant', '多租户不声明 tenant', str(auth_results['multi_tenant'][0]),
     auth_failure_codes['multi_tenant']),
    ('forged_decision_ref', '伪造 decision_ref', str(forged.status), retrieve_codes['forged']),
    ('no_index', '依赖不可用（没配索引）', str(served.status), retrieve_codes['served']),
    ('budget_too_large', '要更大的预算', str(budget_too_large[0]), budget_too_large[1]),
    ('evaluate_timeout', '判定超时', str(timed_out.status), timed_out.body['error']['code']),
    ('audit_unavailable', '观测日志不可写', '503', audit_code),
    ('metrics_forbidden', '指标端点无权限', str(metrics_forbidden.status),
     metrics_forbidden.body['error']['code']),
    ('unknown_route', '未知路由', str(unknown_route.status), unknown_route.body['error']['code']),
]
fail_closed = {key: code for key, label, status, code in fail_closed_rows}
print(pad('场景', 32) + pad('HTTP', 7) + '错误码')
print('-' * 62)
for key, label, status, code in fail_closed_rows:
    print(pad(label, 32) + pad(status, 7) + code)
print('-' * 62)
print('共', len(fail_closed_rows), '条路径，全部是显式错误码；没有一条返回 allow。')
print()
print('小结：超时 504、忙碌 503、依赖不可用 503、审计不可写 503——'
      '服务异常绝不会被翻译成"允许"。')
"""),
    _markdown("""
## 10. 边界与不做的事

- **不做第二份业务逻辑**：API 只做"协议 -> 领域模型 -> 协议"，判定仍然只有
  policy.engine.evaluate 一条路径；决策协议没有新增字段
  （仍是 schema_version 1.0 / policy_version phase-1）；
- **不做客户端自带证据 / 自带决策**：evaluate 的请求体里没有 evidence 字段；
  retrieve 的 decision_ref 只能指向本服务算过的 request_id，且规则集世代必须一致；
- **指标端点不属于任何租户**：它是服务级事实，只要求认证 + 运维角色
  （ops / service-admin 或配置里的 metrics_clients）；
- **没有 TLS、没有反向代理、没有连接池调优**：uvicorn 直接监听 127.0.0.1，
  这些属于部署环境；仓库内能证明的是认证、隔离、预算、幂等与观测的存在性与失败语义；
- **超时是"调用方不再等待"**，不是"工作已经停止"；指标只在进程内，重启即归零；
  并发闸门保证的是"不会无限排队"，不是"服务端一定有容量"；
- **锚仍然不是防篡改日志**：删尾或整链重写靠外部锚发现，而"锚放到哪里"是部署方的决定。

相关文件：

- 阶段设计与实施记录：docs/engineering-policy-platform/phases/phase-7-policy-api.md
- DTO 与错误码：src/policy_api/models.py、src/policy_api/errors.py
- 配置、认证与租户装配：src/policy_api/config.py、auth.py、services.py
- 运行时：src/policy_api/runtime.py（认证 -> 幂等 -> 预算 -> 分派 -> 观测）、
  timeout.py、idempotency.py、observability.py、ops.py
- 传输层与契约：src/policy_api/app.py、contract.py、api/policy-api.yaml、api/openapi.json
- 进程内助手与闭环：src/policy_api/testing.py、tools/api_loop.py
- 测试：tests/contract/test_api_protocol.py、tests/security/test_api_adversarial.py

跑完别忘了清理演示产物：python tools/cleanup.py。
"""),
]


def check_phase_7_structure(namespace: dict[str, Any]) -> list[str]:
    """核对手册里写过的关键数值、键名与结论（生成期断言）。"""

    problems: list[str] = []

    if namespace.get('api_schema_version') != '1.0':
        problems.append('API_SCHEMA_VERSION 与文档不一致: ' + repr(namespace.get('api_schema_version')))
    if namespace.get('decision_versions') != ('1.0', 'phase-1'):
        problems.append('决策协议版本与文档不一致: ' + repr(namespace.get('decision_versions')))

    expected_dto = {
        'missing_version': 'schema_version_missing',
        'unknown_version': 'schema_version_unknown',
        'unknown_field': 'body_invalid',
    }
    if namespace.get('dto_error_codes') != expected_dto:
        problems.append('DTO 拒绝方式与文档不一致: ' + repr(namespace.get('dto_error_codes')))

    status_codes = namespace.get('status_codes') or {}
    expected_status = {
        'unauthenticated': 401,
        'token_expired': 401,
        'token_scope_mismatch': 403,
        'forbidden': 403,
        'metrics_forbidden': 403,
        'tenant_not_found': 404,
        'not_found': 404,
        'idempotency_key_conflict': 409,
        'rate_limited': 429,
        'knowledge_unavailable': 503,
        'rule_set_unavailable': 503,
        'validator_unavailable': 503,
        'audit_unavailable': 503,
        'request_budget_exceeded': 503,
        'evaluate_timeout': 504,
        'retrieve_timeout': 504,
        'validate_timeout': 504,
    }
    for name, expected in expected_status.items():
        if status_codes.get(name) != expected:
            problems.append(f'错误码 {name} 的状态码应当是 {expected}，实际 {status_codes.get(name)}')
    if sorted(name for name, value in status_codes.items() if value == 404) != ['not_found', 'tenant_not_found']:
        problems.append('404 上的错误码与文档不一致（跨租户与不存在必须同码）')
    if namespace.get('api_error_status') != 504:
        problems.append('ApiError(EVALUATE_TIMEOUT).status 应当是 504，实际 ' + repr(namespace.get('api_error_status')))

    if namespace.get('tenant_ids') != ['local-dev', 'fixture-shop']:
        problems.append('部署配置的租户与文档不一致: ' + repr(namespace.get('tenant_ids')))
    if namespace.get('client_ids') != ['local-dev', 'dsh-agent', 'ops-monitor']:
        problems.append('部署配置的客户端与文档不一致: ' + repr(namespace.get('client_ids')))
    if namespace.get('budgets') != {'evaluate_ms': 2000, 'retrieve_ms': 2000, 'validate_ms': 10000}:
        problems.append('路由预算与文档不一致: ' + repr(namespace.get('budgets')))
    if namespace.get('plaintext_rejected') is not True:
        problems.append('明文令牌没有被拒绝加载')

    if namespace.get('auth_tenant') != 'local-dev':
        problems.append('认证结果的租户与文档不一致: ' + repr(namespace.get('auth_tenant')))
    if namespace.get('auth_token_ref') != '0cd48eed4973':
        problems.append('token_ref 应当是 sha256 前 12 位，实际 ' + repr(namespace.get('auth_token_ref')))
    expected_auth = {
        'unknown_token': 'unauthenticated',
        'cross_tenant': 'unauthenticated',
        'expired': 'token_expired',
        'multi_tenant': 'token_scope_mismatch',
    }
    if namespace.get('auth_failure_codes') != expected_auth:
        problems.append('认证失败路径与文档不一致: ' + repr(namespace.get('auth_failure_codes')))

    if namespace.get('budget_defaults') != {'evaluate': 2000, 'retrieve': 2000, 'validate': 10000}:
        problems.append('budget_for 的默认值与文档不一致: ' + repr(namespace.get('budget_defaults')))
    if namespace.get('budget_too_large') != (503, 'request_budget_exceeded'):
        problems.append('"要更大预算"的结果与文档不一致: ' + repr(namespace.get('budget_too_large')))
    if namespace.get('timeout_result') != (True, True):
        problems.append('run_with_budget 的超时分支不是 (None, timed_out=True)')

    if namespace.get('ledger_codes') != {'hit_status': 200, 'conflict': 409}:
        problems.append('幂等台账的两种结果与文档不一致: ' + repr(namespace.get('ledger_codes')))

    if namespace.get('decision_equal') is not True:
        problems.append('本地引擎与 API 的决策载荷不是整份相等')
    if namespace.get('remote_decision_code') != 'block':
        problems.append('示例上下文应当得到 block，实际 ' + repr(namespace.get('remote_decision_code')))
    if 'ARCH-001' not in (namespace.get('violation_rule_ids') or []):
        problems.append('示例的违规里没有 ARCH-001')
    if namespace.get('retrieve_codes') != {'forged': 'forbidden', 'served': 'knowledge_unavailable'}:
        problems.append('retrieve 的授权/可用性结论与文档不一致: ' + repr(namespace.get('retrieve_codes')))

    if namespace.get('readiness_aggregate_ok') is not True:
        problems.append('readiness 的结论与逐项检查不一致: '
                        + repr(namespace.get('readiness_tenants')))
    readiness_tenants = namespace.get('readiness_tenants') or {}
    if readiness_tenants.get('local-dev') is not True:
        problems.append('local-dev 租户的 readiness 检查没有全部通过: '
                        + repr(namespace.get('readiness_failed_checks')))
    if namespace.get('readiness_rule_sets_ok') is not True:
        problems.append('有租户的规则集加载检查没有通过: '
                        + repr(namespace.get('readiness_failed_checks')))
    if namespace.get('readiness_index_checks_ok') is not True:
        problems.append('"该租户未启用检索"被当成了索引不可用（readiness 的索引检查应当通过）')
    if namespace.get('readiness_state') not in ('ready', 'degraded'):
        problems.append('readiness 状态不在受控枚举里: ' + repr(namespace.get('readiness_state')))
    if namespace.get('log_path_under_demo') is not True:
        problems.append('观测日志没有落在 .tmp/learning-phase-7/ 下')
    if namespace.get('log_omits_secrets') != ():
        problems.append('观测日志里出现了不该记录的字段: ' + repr(namespace.get('log_omits_secrets')))
    if namespace.get('log_has_absolute_path') is not False:
        problems.append('观测日志里出现了仓库绝对路径')
    if namespace.get('seal_ok') is not True:
        problems.append('摘要链锚定校验没有通过')
    if not namespace.get('tamper_issues'):
        problems.append('删掉尾部记录后锚校验仍然通过（缺陷）')

    expected_fail_closed = {
        'missing_version': 'schema_version_missing',
        'unknown_version': 'schema_version_unknown',
        'unknown_field': 'body_invalid',
        'unknown_token': 'unauthenticated',
        'cross_tenant': 'unauthenticated',
        'expired': 'token_expired',
        'multi_tenant': 'token_scope_mismatch',
        'forged_decision_ref': 'forbidden',
        'no_index': 'knowledge_unavailable',
        'budget_too_large': 'request_budget_exceeded',
        'evaluate_timeout': 'evaluate_timeout',
        'audit_unavailable': 'audit_unavailable',
        'metrics_forbidden': 'metrics_forbidden',
        'unknown_route': 'not_found',
    }
    if namespace.get('fail_closed') != expected_fail_closed:
        problems.append('失败关闭对照表与文档不一致: ' + repr(namespace.get('fail_closed')))
    return problems
