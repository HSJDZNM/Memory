# T4 · enforcement-availability 实施记录（G5 / G4 / G9）

> 对应根因 R4（"在范围内"这一个语义被写了四遍）与 R5（声明式数据与运行期现实之间没有漂移检测）。
> 写域：`src/enforcement/*.py`、`src/policy/context.py`、`src/policy/models.py`、
> `registry/tool-registry.yaml`、`registry/tool-registry.approved.json`、
> `tests/{contract,unit,integration}/` 相关测试、本文件。
> 每条结论都对着一次真实执行；修前 / 修后用同一份探针在 `.tmp/governance-baseline.zip` 快照上对照。

## 0. 一句话

三个缺口的共同形状是**"声明与运行期现实不一致"**：路径归属的声明散了四处（G5）、
审批的声明只表达得了"这一次调用"（G4）、工具的第二道闸只写在文档里（G9）。
本轮的修法一律是**把区别写成数据、把结论写成会失败的检查**。

## 1. 修前基线（真实输出，`.tmp/governance-baseline.zip` 快照）

同一份探针 `.tmp/enforcement-availability/repro_failing_checks.py`：

| 探针 | 修前（baseline 快照） | 修后（当前工作树） |
| --- | --- | --- |
| G5 目录参数接受"等于工作区根" | FAIL → `TypeError: repo_relative_path() got an unexpected keyword argument 'allow_root'` | PASS |
| G5b 文件参数传 `.` 仍被拒 | PASS → `PolicyContextError` | PASS（**没有放宽**） |
| G4 模式化审批可签发 | FAIL → `ValidationError: 5 validation errors for ApprovalRecord / action_hash Field required` | PASS |
| G9 `exec.run_code` 有第二道闸 | FAIL（`no code_check`） | PASS |

修前逐项实测（同一个快照）：

- G5：`.` → `PolicyContextError: 路径必须指向仓库内的文件: '.'`；绝对工作区根 →
  `PolicyContextError: 路径不在仓库 … 之内，拒绝处理`；`sub/dir` 正常。探针三条对照与 V1 的实测一致。
- G4：同一条命令、同一个主体，只换 `action_id` →
  `ApprovalError: 审批绑定的 action_hash 与当前动作不一致…旧审批作废`。
- G9：`exec.run_code` = `driver=none`、`post_checks=[]`、`allowed_commands=[]`、无 `command_param`，
  参数只有 `code` / `description` —— 第二道闸在数据里根本不存在。

## 2. G5 · 路径口径统一（可用性缺陷）

**根因**：同一个语义（"这个路径在受控范围内吗"）四处实现，边界上不一致；"等于根"在别处
记成 `.`，而这里不接受 `.`，且报错说"参数错误"。

**改法**（区别写成数据，不是代码特判）：

| 位置 | 改动 |
| --- | --- |
| `src/policy/models.py` `normalize_repo_path(value, *, allow_root=False)` | 空段时：`allow_root=True` 归一化为 `.`；默认仍拒绝（"要的是文件"） |
| `src/policy/context.py` `repo_relative_path(..., allow_root=False)` | 绝对路径**恰好等于** repo_root 时：默认报"这里要的是文件，不是目录"，`allow_root=True` 返回 `.` |
| `src/enforcement/models.py` `ParamSpec.path_kind: PathKind = FILE` | 新枚举 `file \| directory \| any`，默认 `file`；非 path 参数上声明 `path_kind` 直接报错 |
| `src/enforcement/action.py` `_normalize_path(...)` | 先判**范围**（`repo_relative_path`，越界 → `path_out_of_scope`），再判**类型**（`.` 给 file 参数 → `param_invalid`，"它不是文件"） |
| `registry/tool-registry.yaml` | `exec.pwsh` / `exec.bash` 的 `workdir` 声明 `path_kind: directory` |

**为什么不用"根目录特判"**：特判会把"某个参数名"写进代码，注册表就不再是唯一事实源；
`path_kind` 让"我要文件还是目录"变成可审核、可哈希、可回归的数据。

**错误码如实**：`ActionRequestError` 现在带结构化 `reason_code`（`src/enforcement/models.py`），
`_fail()` 一路传下去（`src/enforcement/action.py`）。越界报 `path_out_of_scope`，
"不是文件"报 `param_invalid` —— 两者不再混成一句"参数错误"。

**六种边界**（`tests/contract/test_path_scope_boundaries.py`，10 项）：
绝对根 → `.`、`.` → `.`、`./` → `.`、`sub` → `sub`、越界 → `path_out_of_scope`、
文件参数传 `.`（`fs.write` 与 `fs.edit` 两条）→ `param_invalid`，另加"上下文里的 `file` 仍要文件"
与"未知 / 错位 `path_kind` 报错"。

## 3. G4 · 模式化审批（保留单次绑定为更严格档）

**根因**：审批只绑 `action_hash`，而 `action_hash` 覆盖运行期生成的 `action_id` / `tool_use_id`；
换一个调用编号，条子立刻作废。静态声明只表达得了"这一次调用"，表达不了"这一类调用"。

**两种档位**（`src/enforcement/approvals.py`）：

| binding | 绑什么 | 约束 |
| --- | --- | --- |
| `action`（默认，更严格） | `action_hash` + `action_id` 逐位一致 | `max_uses` 必须为 1；不得声明 `param_patterns` |
| `pattern` | 工具 + 规范化参数模式 + 主体/角色 + 生效窗口 + 次数上限 | 不得声明 `action_hash`/`action_id`；`param_patterns` 必须非空 |

**不可削弱的性质**（逐条写进测试）：

1. 同一 `action_id` 绝不执行第二次 —— 由台账 + 审计链把关，**与审批档位无关**
   （`test_the_same_action_id_can_never_run_twice_even_with_pattern_approval` 断言 `action_replay`）；
2. 参数一变、模式匹配不上即拒绝（`verify_approval` 对规范化取值做 `re.fullmatch`）；
3. 次数上限**先原子占用再执行**（`EnforcementLedger.claim_approval_use`：先追加、再复核，
   并发抢输的一方按超限拒绝），占用写进台账与审计（`approval_use` 检查项 + payload 字段）；
4. 用尽 / 过期 / 跨主体 / 角色不足一律拒绝；
5. 未知字段、自相矛盾的字段组合（action 档写 `max_uses>1` 或 `param_patterns`、
   pattern 档写 `action_hash`、pattern 档无模式）一律拒绝；
6. 失败关闭不留死锁：审计不可写而阻断时，认领与审批额度**都归还**
   （`approval_use_released`），修好后同一个 `action_id` 可以重试。

**签发入口**：`python -m enforcement.cli approve --binding pattern --max-uses N --param-pattern "NAME=REGEX"`；
矛盾开关（action 档给 `--param-pattern` / `--max-uses`、pattern 档漏模式、模式指向未声明参数）
一律以退出码 2 拒绝。

> **口径澄清（环境限制）**：本机 `shutil.which("pwsh")` 为 None、bash 走 WSL 被拒绝，
> 因此**"受治理会话现在能跑 pytest 了"这句话在本机无法端到端证明**。
> 能证明的是链路本身：审批不再因为运行期生成的调用编号而失效，且换编号之后
> 防重放与次数上限仍然生效。测试与端到端用例都用 `@PYTHON@`（当前解释器）驱动，
> 不用 pwsh / bash，避免把环境问题混进结论。

## 4. G9 · `run_code` 的第二道闸（结构化静态检查）

**选 (a)：结构化静态检查**，理由：`(b) 显式降级` 只是把"没有门禁"写清楚，而这类工具的
动作语义（一段代码）本来就是**可判定的文本**；能查而不查，等于把缺口留成默认值。
但 (a) 必须做成**数据驱动 + 封闭枚举 + 失败关闭**，否则只是把 G9 换成一条更好看的 G9。

| 位置 | 改动 |
| --- | --- |
| `src/enforcement/models.py` `SUPPORTED_CODE_CHECKS` | 已实现检查的**封闭枚举**（当前只有 `python_forbidden_surface`），未知值加载期报错 |
| `src/enforcement/models.py` `CodeCheckSpec` | `param` / `language` / `forbidden_imports` / `forbidden_calls` / `forbidden_attributes` / `known_gaps`；三个禁止面全空 = 加载期报错（"声明了却什么都没查"） |
| `src/enforcement/codecheck.py`（新） | `ast` 解析 + 遍历；**解析不了 = 拒绝**（`code_parse_failed`），命中 → `code_blocked`；结果按行号 / 类别 / 名字排序，确定性输出 |
| `src/enforcement/models.py` `ToolSpec` 不变量 | `driver=none` 且 `effect=process` 的工具必须在 **`code_check`** 与 **`ungoverned`（显式降级声明）** 之间选一个；**两者都不写 = 加载期报错**（没有默认值） |
| `src/enforcement/precheck.py` | 新增 `code_check` 检查项（在审批之前）；`ungoverned` 的工具输出 `governance_coverage`（`reason_code=ungoverned_declared`，status=skipped）并让决策至少 `allow_with_warnings`，同时进审计 |
| `registry/tool-registry.yaml` `exec.run_code` | 声明 `code_check`（禁 `os`/`pathlib`/`shutil`/`subprocess`/`socket`/`sys`/`importlib`/`ctypes`/… 导入、禁 `open`/`exec`/`eval`/`__import__`/`getattr`/… 调用、禁 `os`/`subprocess`/… 属性链） |

### 4.1 诚实标注：静态检查**不是**沙箱

命令白名单的边界在 AGENTS.md 第 17 条里已经写过一次（"白名单不是沙箱"）；这里是同一句话
的另一个实例。检查看的是**语法结构**，下面这些形态覆盖不到，且**不能靠往清单里加名字解决**：

| 已知不可覆盖的形态 | 例子 | 为什么加名单没用 |
| --- | --- | --- |
| 用下标 / 容器取出函数再调用 | `(lambda: 0).__globals__["__builtins__"]["open"]` | 被禁的名字根本不出现在 AST 的 Name / Attribute 位置 |
| 拼接字符串构造名字 | `"op" + "en"` | 名字是运行期才有的值，静态检查看不到 |
| 自定义 `__getattr__` / 元类间接暴露的属性 | `obj.anything` | 属性表由运行期决定 |
| 把调用藏进数据结构再取出 | 字典 / 列表存可调用对象 | 结构里没有"被禁的名字" |

这些形态写在注册表的 `known_gaps` 里（数据），并会：
① 出现在 `code_check` 的 PASSED detail 里（进审计）；② 触发 `code_check_structural_only` 警告，
让决策变成 `allow_with_warnings` —— **"查过了"不许被读成"隔离了"**。
`tests/contract/test_run_code_static_check.py::test_known_bypass_is_recorded_instead_of_hidden`
把"当前拦不住"这件事固定成测试：既防有人把它当沙箱，也防有人悄悄缩小 `known_gaps` 的登记。
真正的隔离属于运行时的文件系统与进程沙箱，不在本阶段。

## 5. 注册表审核（哈希会变）

改动 `registry/tool-registry.yaml` 之后**必须重新审核**，否则运行时描述与已审核哈希不一致、
工具直接不可用。本轮跑的是：

```
$env:PYTHONPATH='src'; python -m enforcement.cli registry --approve --reviewer enforcement-availability
{ "approved": "registry/tool-registry.approved.json",
  "registry_digest": "sha256:803e310f37b553f17efc4a61ca5cb3a9d12e0d55a7a2ab558bd6912e0cf08e9b",
  "reviewed_by": "enforcement-availability", "tools": 10, "approved_at": "2026-09-25T16:37:10Z" }

$env:PYTHONPATH='src'; python -m enforcement.cli registry --verify   # 10/10 ok（含 exec.run_code）
$env:PYTHONPATH='src'; python -m enforcement.cli self-check          # self-check ok
```

## 6. 会失败的检查（每条修复对应哪些测试）

| 缺口 | 检查（新增 / 更新） | 修前会红在哪 |
| --- | --- | --- |
| G5 | `tests/contract/test_path_scope_boundaries.py`（10 项） | 修前 `repo_relative_path` 没有 `allow_root`；`.` 直接 `PolicyContextError` |
| G4 | `tests/contract/test_approval_binding_modes.py`（13 项）、`tests/integration/test_enforcement_cli.py` 两条 | 修前 `ApprovalRecord` 没有 `binding` / `param_patterns` / `max_uses` 字段；换 `action_id` 必 `approval_invalid` |
| G9 | `tests/contract/test_run_code_static_check.py`（14 项） | 修前 `ToolSpec` 没有 `code_check`；`exec.run_code` 的第二道闸不存在 |

对照证据：`.tmp/enforcement-availability/repro_failing_checks.py` 在修前快照上 3/3 FAIL，
在当前工作树上 3/3 PASS（G5b 两次都 PASS，证明没有放宽文件参数）。

## 6.1 独立验收探针（V1）在本次改动后的实测

```
python tools/governance_gap_probe.py --phase after --only G05 --quiet   -> ok=True
python tools/governance_gap_probe.py --phase after --only G09 --quiet   -> ok=True（连跑两次都 ok）
python tools/governance_gap_probe.py --phase after --only G04 --quiet   -> ok=True
```

G04 的实测事实（探针自己打印的）：`pattern_mode_supported=true`、
`different_action_id_decision=allow`、`different_command_decision=block`、
`subject_swap_decision=block`、`expired_decision=block`、`max_uses_enforced=true`、
`replay_fresh_approval_blocked_as_replay=true` —— 全部与探针的 after 预期一致。

**修正记录（保留，便于复查）**：本轮中途 G04 曾出现一次 `0/1 一致`，唯一不一致项是
`replay_fresh_approval_blocked_as_replay`（期望 `action_replay`，实测 `approval_invalid`）。
当时的归因是探针的重放子用例把为 `python -m pytest tests -q` 签的模式
（`--param-pattern "command=.*pytest.*"`）复用到命令为 `Write-Output probe-g04` 的请求上：
模式不匹配 → 第一道检查就判 `approval_invalid`，动作从未占用 action_id，于是观察不到重放。
这条归因已随 V1 修正探针而消失（当前实测 ok=True）；本仓库自己固定这条性质的两处断言是
`tests/contract/test_approval_binding_modes.py::test_the_same_action_id_can_never_run_twice_even_with_pattern_approval`
（断言 `ACTION_REPLAY`）与
`tests/integration/test_enforcement_cli.py::test_pattern_approval_makes_a_governed_session_rerunnable`
（断言 CLI 输出 `final: blocked (action_replay)`）。

另外本机 `shutil.which("pwsh")` 为 None：`exec.pwsh` 的 `execute` 到不了驱动，
探针里 `replay_first_executed=false` 与 `platform_driver_available=false` 正是这个环境事实，
而不是治理行为——所以本轮的结论只写到"审批链路不再因运行时编号失效"这一层。

## 7. 没做的、以及遗留风险

| 项 | 状态 | 说明 |
| --- | --- | --- |
| "受治理会话能跑 pytest"的端到端结论 | **未证明** | 本机没有 pwsh、bash 走 WSL 被拒；只能证明审批链路本身（见 §3 口径澄清） |
| 动态代码形态的静态覆盖 | **不做** | 结构性检查的固有边界；已用 `known_gaps` + 测试 + 警告如实标注（见 §4.1） |
| `run_code` 的事后证据 | **仍缺** | driver=none ⇒ 平台拿不到执行证据；本轮补的是**事前**第二道闸。事后证据要么等 Agent 侧回传，要么换驱动 |
| `ungoverned` 声明的现实使用者 | 无 | 目前 10 个工具都走了检查或既有门禁；该档位是为"确实不可治理"的委派工具准备的显式出口，且必须带 reason + declared_by，并在 pre-check / 审计里显形 |
| Hook 层把范围问题包成 `enforcement_param_error` | **未改** | `src/adapters/dsh/hooks.py:669` 是 T1 的写域。底层现在给了结构化 `ActionRequestError.reason_code`，T1 可以直接采用；本轮未越界修改 |

## 8. 参考

- 根因与验收口径：`docs/project/engineering-policy-platform/reviews/governance-remediation/00-remediation-plan.md`
- 缺口实测：`docs/project/engineering-policy-platform/reviews/governance-coverage-gaps.md`
- 命令白名单的同一句边界：`AGENTS.md` 第 17 条
