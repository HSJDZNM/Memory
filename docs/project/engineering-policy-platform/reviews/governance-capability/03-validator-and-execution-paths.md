# 03 · 验证器路径与执行链能力取证（T3）

> 本文只回答两个问题：**除了动手前那一条规则，平台到底还能查出什么**，以及
> **受治理会话能不能自己跑测试**。所有结论都来自平台自己的入口（真 ruff / 真 pytest /
> 真 approvals / 真 pre-check / 真 Hook），没有另写一套解析器或判定器。
> 每条结论后面都跟着可复现命令与原始证据路径；测不到的地方写在 §3。

## 结论层摘要

1. **验证器路径能真正给出结论的规则数是 43/43**（按"文件 × 层"分散在不同上下文里），
   而仅上下文路径（Phase 2 的 PreToolUse Hook）对同一个文件只有 **0/43**，
   对 controller 层文件是 **1/43**（只有 ARCH-001）。差额全部记在 `skipped_rules` 里，
   不是"通过"。
2. 在故意写坏的多文件项目上，证据路径一次跑出 **15 条规则命中**（12 条 ruff 规则 +
   DOC-001 + TESTING-001 + TESTING-002）并给出 `block`；关键验证器缺失时（无变更集、
   allowlist 少跑、语法错误）**一律失败关闭**，critical 违规不被同批 PASS 抵消。
3. **mypy 缺失目前不影响任何结论**：43 条规则里没有一条使用 `type_check` checker，
   所以 tool.mypy 根本不会被选中。它**不是"通过了"，而是"没启用"**；一旦有规则声明
   `type_check`，`tool.mypy` 是 critical，会以 critical 违规阻断（注册表与 probe 都已证明）。
4. **模式化审批（binding=pattern）确实修好了"同一条 pytest 命令过不了审批"这件事**：
   平台自己的 `enforcement.cli approve --binding pattern` 签出的 `approval.json`
   让 `python -m pytest -q` 从 `approval_required` 变成 `allow_delegated`（exit 0）。
5. **但"审批修好了" ≠ "会话现在能跑测试"**，实测有三条互相独立的阻碍：
   - **会话里根本没有 `bash` / `run_code` 工具**（工具清单只有 `pwsh`），
     另两种只存在于注册表与 Hook 层，真实会话发不出这两类调用；
   - **命令确实被执行了，结果却回不到模型**：PostToolUse 的 `exit_code_zero` 事后验证
     拿不到退出码 → `post_check_failed` / `repair_required` → Hook 失败关闭 →
     dsh 用策略错误替换掉工具输出。这是**当前链路的最后一公里，且与审批无关**；
   - **平台侧驱动跑不了 pwsh**：本机 `shutil.which("pwsh")` 为 None，
     Phase 4 的 `shell_command` 驱动（`shell=[pwsh, ...]`）报 `process_error`（WinError 2）。
6. 反向对照：**没有审批的那个项目连 `__pycache__` 都没有**（pytest 从未跑起来）；
   有模式化审批的那个项目 pytest **真的跑了**（`test_order_service.cpython-313-pytest-9.1.1.pyc`
   的 mtime 落在会话窗口内）。所以"跑不起来"和"结果拿不到"是两件事，本文把它们分开写。

---

## 0 · 取证边界与可复现前提

| 项 | 值 |
| --- | --- |
| 仓库 | `C:\Users\ZNM\Downloads\Memory`（HEAD `d35b3bc`，分支 `feat/rules-and-os-platform`） |
| 解释器 | `C:\Users\ZNM\miniconda3\python.exe`（Python 3.13.11，有 pydantic / PyYAML / pytest 9.1.1 / ruff 0.14.13） |
| 规则集 | `policies/` 43 条，loader identity `sha256:50202675b6ca401368bdd75ad67b440e66849f27faf237a2265043a8eaa4b33c` |
| 本机外部工具 | ruff ✅ 0.14.13；pytest ✅ 9.1.1；**mypy ❌**；**pwsh ❌**（`shutil.which("pwsh") is None`，只有 Windows PowerShell 5.1）；bash = WSL `C:\WINDOWS\system32\bash.EXE` |
| 我的隔离产物 | `.tmp/governance-capability/grading/`（valproj / syntaxproj / project / project-approval / evidence） |
| 我的 profile | `$DSH_HOME/profiles/governed-grade`、`governed-grade-approval`（Lead 的 `governed` 与本工作流无关） |
| 没碰的东西 | 没有跑 `tools/ci_local.py`；没有改 `harness/`、`src/`、`tests/`、`registry/`、`policies/` |

所有 Python 模块调用都带 `PYTHONPATH=src`。

---

## 1 · 线 1：验证器路径 —— 43 条里有多少条能真正给出结论

### 1.1 两条路径不是同一个入口（先把这件事钉死）

| | 仅上下文路径（pre） | 证据路径（Phase 5） |
| --- | --- | --- |
| 入口 | `python -m adapters.dsh.hooks`（PreToolUse，生产 CLI；受治理会话走的就是这条） | `python -m validators.cli pipeline`（内部：`policy.engine.evaluate(..., evidence=...)`） |
| 判定输入 | 只有 `PolicyContext`（file / layer / language / operation / dependencies） | 上下文 + `EvidenceBundle`（真 ruff / 真 pytest / 内置 AST / 依赖图 / docstring） |
| 可判定的 checker | 只有 `forbidden_dependency` | `forbidden_dependency` + `missing_docstring` + `style_lint` + `missing_tests` + `failing_tests` |

**注意**：`python -m policy.check` **不是**"仅有上下文"的入口——它也调 `run_pipeline` 并把
evidence 交给 `evaluate`（`src/policy/check.py:463`、`:496`）。本次实测里它的输出与
`validators.cli pipeline` 在"判定结果"上一致（证据文件 `evidence/pre-*.json` 与
`evidence/pipeline-*.json`），**不要拿它当 pre 路径的对照**。

### 1.2 隔离项目与复现命令

被测项目 `.tmp/governance-capability/grading/valproj/`（7 个文件，故意同时命中多个规则族）：
`src/gradesvc/{__init__,grade_repository,grade_service,grade_controller,legacy_utils}.py` +
`tests/test_grade_service.py`。其中 `grade_controller.py` 直接 import 仓储层（ARCH-001）、
`legacy_utils.py` 无模块 docstring 且含 12 类 ruff 诊断、`tests/test_grade_service.py`
有一条故意失败的用例。

```powershell
# 关键单例复现（其余用例见 §4 的矩阵脚本）
$env:PYTHONPATH="C:\Users\ZNM\Downloads\Memory\src"
python -m validators.cli pipeline src/gradesvc/legacy_utils.py ^
  --workspace .tmp/governance-capability/grading/valproj --layer module --operation edit ^
  --changed src/gradesvc/legacy_utils.py --changed src/gradesvc/grade_controller.py ^
  --changed tests/test_grade_service.py --json
# 原始输出：.tmp/governance-capability/grading/evidence/pipeline-legacy_utils.json
```

### 1.3 路径 × 规则族（实测结论表）

同一个文件、同一层、同一 operation，两条路径的对照（原始数据：`evidence/path-comparison.json`）：

| 文件（layer） | 路径 | 规则总数 | 进入范围 | **真正判定** | 被跳过 | 判定结果 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `src/gradesvc/legacy_utils.py`（module） | Hook（pre） | 43 | 43 | **0** | 43 | `allow`（`enforcement_allow`） |
| 同上 | 证据 | 43 | 42 | **42** | 0 | `block`（15 条规则命中） |
| `src/gradesvc/grade_controller.py`（controller） | Hook（pre） | 43 | 43 | **1**（ARCH-001） | 42 | `allow` |
| 同上 | 证据 | 43 | 43 | **43** | 0 | `block`（ARCH-001 + TESTING-001/002） |
| `src/gradesvc/grade_service.py`（service） | Hook（pre） | 43 | 43 | **0** | 43 | `allow` |
| 同上 | 证据 | 43 | 42 | **42** | 0 | `block`（TESTING-001/002） |

按规则族展开（"能判定"= 该族规则在对应路径上真的产出了结论，而不是被记为 skipped）：

| checker（条数） | 仅上下文路径 | 证据路径 | 本次实测命中 |
| --- | --- | --- | --- |
| `style_lint`（39 条） | ❌ 全部 skipped（"需要验证器证据"） | ✅ 39 条全部进入判定 | 12 条命中（SEC-001/004、STYLE-001/002/003/005/006/009/010/011/015/018） |
| `missing_docstring`（DOC-001） | ❌ skipped | ✅ 判定（内置 AST） | 3 处（模块 + 2 个函数） |
| `forbidden_dependency`（ARCH-001） | ⚠️ **仅 layer=controller 时**判定（1/43） | ✅ 判定（依赖图） | 1 处（controller 直连 repository） |
| `missing_tests`（TESTING-001） | ❌ skipped | ✅ 判定（需变更集 + pytest） | 2 处 |
| `failing_tests`（TESTING-002） | ❌ skipped | ✅ 判定（需变更集 + pytest） | 1 条（`test_intentionally_failing`） |
| `type_check`（0 条） | 无规则 | **不选中**（没有规则要它） | — |

**回答核心问题：43 条规则在证据路径上全部可以给出结论**（按上下文分散：普通 python 文件
42/43，controller 层 43/43）；同一批规则在仅上下文路径上是 0/43（controller 层 1/43）。
"能不能给结论"与"有没有命中"是两件事：39 条 style_lint 里有 27 条这次**查过且干净**。

### 1.4 失败关闭实测（跳过 ≠ 通过）

四个针对性用例（原始输出在 `evidence/pipeline-*.json`，摘要脚本 `digest_special_cases.py`）：

| 场景 | 命令要点 | 平台结论 | 关键原文 |
| --- | --- | --- | --- |
| 没有变更集 | 去掉 `--changed` | `block`，TESTING-001/002 以 **critical** 阻断 | `tool.pytest unavailable`："缺少变更集（--changed / git diff）：测试验证器需要知道这次改了什么，没有变更集属于证据不足" |
| allowlist 少跑验证器 | `--validators py.source,tool.ruff` | `block`，DOC-001 + TESTING-001/002 以 **critical** 阻断 | `pipeline not_selected`："没有验证器为 checker missing_tests 提供证据（rule pack 未覆盖）" |
| 目标文件语法错误 | `syntaxproj/src/brokensvc/messy.py` | `block`，DOC-001 以 **critical** 阻断 | `py.ast failed`："语法错误 src/brokensvc/messy.py:7:14：invalid syntax（解析不了的文件不能被判定为没有依赖问题）" |
| 只跑证据不判定 | `validators.cli check`（对比用） | — | 证据与判定分离：`check` 只产证据，`pipeline` 才给 allow/block |

同批里其他规则的 PASS **没有**抵消这些 critical 违规——这正是 AGENTS.md 第 20 条要的行为。

### 1.5 mypy 缺失对结论的影响：是"没启用"，不是"通过了"

- 平台自己的 probe：`python -m validators.cli probe --json` → `tool.mypy@1.0 unavailable`，
  reason `找不到可执行文件 mypy（PATH 与解释器同目录都没有）`，requirement `>=1.8,<2`；
  同一份输出末尾写明"缺失或不匹配的关键工具：1（用到它们的规则会失败关闭）"。
- 注册表 `validation/validators.yaml`：`tool.mypy` 声明 `checkers: [type_check]`、
  `critical: true`。
- 43 条规则里**没有任何一条**的 `enforcement.checker` 是 `type_check`（`evidence/rule-universe.json`），
  所以 `_select_specs` 根本不会选中 tool.mypy——我的 8 个用例里，验证器列表里从来没有它
  （见 `evidence/pipeline-*.json` 的 `evidence.validators`）。
- 因此：**mypy 缺失对当前 43 条规则的结论零影响；但这个"零影响"来自"没有规则用它"，
  不来自"它通过了"。** 一旦有规则声明 `type_check`，它会走 §1.4 里 pytest 那条失败关闭路径
  （critical 阻断），不会静默降级。

### 1.6 一条必须写出来的边界：对解析不了的文件，`style_lint` 的"已判定"是空判定

语法错误用例里，platform 把 **39 条 style_lint 规则记成"已判定、未发现"**（`tool.ruff` 状态 `ok`、
`evidence_count=0`）。但同一次运行里 `unmapped_findings=1`——那一条正是 ruff 0.14 对语法错误报的
`{"code": "invalid-syntax"}`（旧版是 E999）。`src/validators/adapters/ruff.py` 按"规则数据声明的
`codes`"归属诊断，没有规则认领 `invalid-syntax`，于是它只计数、不参与判定；
`tool.ruff` 的 `requires` 只有 `py.source`，不受 `py.ast` 失败影响 → style_lint 仍然"served"。

结论要说全：**整份文件的判定仍然是 `block`**（DOC-001 由 `py.ast` 失败关闭兜住、
TESTING-001 也命中），所以失败关闭姿态是成立的；但**单看 style_lint 这 39 条，
"已判定"在这份文件上是空的**——ruff 其实没能检查它。这是"跳过 ≠ 通过"的一个反向例子：
**"判定过"也不总等于"真的查过"**，读审计时要知道这个区别。

### 1.7 39 条 ruff 规则的"归属 × 选中"是双向一致的（平台自己的契约测试）

```powershell
$env:PYTHONPATH="C:\Users\ZNM\Downloads\Memory\src"
python -m pytest "tests/contract/test_validator_protocol.py::test_ruff_codes_are_declared_and_selected_in_both_directions" -q
# 1 passed in 0.21s
```

它保证"规则声明的码都被 `validation/ruff.toml` 的 `select` 选中"，因此 39 条 style_lint 规则
**都有能力**产出证据——上面 12 条命中、27 条干净不是"码没启用"造成的假干净。

---

### 1.8 交叉复核：T1 §5 的四个"容易写错"的触发形态，在流水线里逐条复现

T1 的 `01-rule-coverage-matrix.md` §5 用 stdin + `validation/ruff.toml` 逐码实测 60 个码。
我用**真实验证器流水线**（文件路径而非 stdin，走"诊断码 → 规则数据归属"的映射）复刻了它
标注的四个易错形态——夹具 `.tmp/governance-capability/grading/xcheck/src/xcheck/forms.py`，
复现脚本 `.tmp/governance-capability/grading/run_xcheck.py`，原始输出
`.tmp/governance-capability/grading/evidence/xcheck-forms.json`。**四条全部一致，没有分歧**：

| 形态 | T1 的口径 | 我的流水线实测 | 一致？ |
| --- | --- | --- | --- |
| E501 | 100 列不报、101 列报 | 第 7 行正好 100 列 → 无证据；第 8 行 101 列 → `STYLE-001` 证据 `Line too long (101 > 100)` | ✅ |
| D401 | 中文 docstring 不触发 | 英文 `Returns the resource body.` → `DOC-004` 1 条（第 12 行）；中文 `返回资源正文。`（docstring 首行在第 20 行，第 21 行是空行）→ 0 条 | ✅ |
| S310 | 仅变量 URL 触发 | `urlopen(url)`（第 29 行）→ `SEC-010` 码 S310；`urlopen("http://example.com/")`（第 34 行）→ 无 | ✅ |
| S609 | 仅列表形态触发 | `Popen(["chmod","777","*.py"], shell=True)`（第 44 行）→ S602 + **S609**；`Popen("ls", shell=True)`（第 39 行）→ 只有 S602 | ✅ |

两点补充（读矩阵时有用）：证据条目里的 `value` 就是 ruff 码，因此"码级结论"与"规则级结论"
能在同一份产物里对上；但**码与规则不是一一对应**——SEC-007 一条就吃 S602/S605/S609，
我的用例里它一次产出 3 条证据（S602@39、S602@44、S609@44）。这次运行 `unmapped_findings=0`，
只能说明**这份夹具语法正确、ruff 的每条诊断都有规则归属**；它**不是**"语法错误也会被归属"
的证据——语法错误恰恰相反：ruff 0.14 报的是无归属的 `invalid-syntax`（`unmapped_findings=1`），
见 §1.6。两件事必须分开读，否则下一个人会把"有归属"推广到它不成立的地方。

---

## 2 · 线 2：执行链 —— 受治理会话能不能自己跑测试

### 2.1 三种执行类工具在注册表里长什么样

`registry/tool-registry.yaml`：

| 工具 | risk | driver | 审批 | 事后检查 | 要点 |
| --- | --- | --- | --- | --- | --- |
| `exec.pwsh`（tool_name `pwsh`） | `privileged_execution` | `shell_command`（`[pwsh, -NoLogo, -NoProfile, -NonInteractive, -Command]`） | **required** | `[exit_code_zero]` | 7 条白名单（含 `^python -m pytest( .*)?$`）；禁组合片段与 `../` `--output` `--ext-diff` `--no-index` |
| `exec.bash`（`bash`） | 同上 | `shell_command`（`[bash, -lc]`） | **required** | `[exit_code_zero]` | 5 条白名单 |
| `exec.run_code`（`run_code`） | 同上 | **`none`**（平台不执行，只交给运行时） | **required** | `[]` | 不是命令类；改用 `code_check`（`python_forbidden_surface`）结构性静态检查 |

### 2.2 Hook 层：三种工具各得到什么 reason_code（实测）

命令模板（三条都用同一个 PreToolUse 事件形状，只换 `tool_name` / `tool_input`）：

```powershell
$env:PYTHONPATH="C:\Users\ZNM\Downloads\Memory\src"
# <event>.json 里 tool_name = pwsh | bash | run_code，tool_input = {command|code, description}
Get-Content <event>.json -Raw | python -m adapters.dsh.hooks ^
  --config .policy/dsh-adapter.yaml --hooks-config .policy/hooks.json --audit .policy/audit-exec-X.jsonl
```

**阶段 A：`.policy/approval.json = []`（没有任何审批）**

| 事件 | 命令/代码 | CLI 退出码 | reason_code | 原文要点 |
| --- | --- | ---: | --- | --- |
| pwsh | `python -m pytest -q` | 2 | `approval_required` | "该动作需要人工审批，但没有提供与当前 action_hash 绑定的审批记录" |
| bash | `python -m pytest -q` | 2 | `approval_required` | 同上（`exec.bash`） |
| run_code | `import subprocess; subprocess.run([...pytest...])` | 2 | **`code_blocked`** | "代码命中 2 处禁止面（kind=python_forbidden_surface）：第 1 行 导入 subprocess；第 2 行 属性 subprocess.run" |
| run_code | `print(sum(range(3)))` | 2 | `approval_required` | 静态检查通过，仍卡审批 |

**阶段 B：`.policy/approval.json` = 平台自己签发的 `binding=pattern` 审批（`tool_id=exec.pwsh`，`param_patterns={"command": "^python -m pytest( .*)?$"}`，`max_uses=20`）**

| 事件 | 命令/代码 | 退出码 | reason_code | 说明 |
| --- | --- | ---: | --- | --- |
| pwsh | `python -m pytest -q` | **0** | `enforcement_allow` → **`allow_delegated`** | **同一条命令从"卡审批"变成"放行"** |
| pwsh | `python -m pytest tests/test_order_service.py -q` | **0** | `allow_delegated` | 模式允许同族的不同调用 |
| pwsh | `git status` | 2 | `approval_invalid` | "参数 'command' 的取值不匹配审批模式 '^python -m pytest( .*)?$'（整串匹配）" |
| pwsh | `python -m pytest -q; echo done` | 2 | `command_composition_blocked` | `;` 在审批之前就被结构性阻断 |
| pwsh | `python -c "print(1)"` | 2 | `command_not_allowlisted` | 白名单独立于审批 |
| bash | `python -m pytest -q` | 2 | `approval_invalid` | **"审批绑定的工具与当前动作不一致"**——一份审批只覆盖一个 tool_id |
| run_code | `print(sum(range(3)))` | 2 | `approval_invalid` | 同上 |
| run_code | subprocess 跑 pytest | 2 | `code_blocked` | **无论有没有审批，run_code 都跑不了 pytest** |
| pwsh（换成 exec.bash 的审批） | `python -m pytest -q` | 2 | `approval_invalid` | 印证"一个 approval.json 只放得下一条记录" |

### 2.3 模式化审批怎么签发（平台自己的命令）与它的边界

```powershell
$env:PYTHONPATH="C:\Users\ZNM\Downloads\Memory\src"
python -m enforcement.cli approve --request evidence/approval-request-exec.pwsh.json ^
  --out evidence/approval-pattern-exec.pwsh.json ^
  --granted-by t3-reviewer --roles reviewer ^
  --binding pattern --param-pattern "command=^python -m pytest( .*)?$" ^
  --max-uses 20 --ttl 3600 --note "T3 取证"
# 产物被拷到 <project>/.policy/approval.json（bridge 只读这一个文件、且只认单个 JSON 对象）
```

独立复核（`enforcement.cli precheck`，dry_run，不执行）：

```
decision: allow   approval 检查 passed：
approval_id=approval-e342b1262b20 granted_by=t3-reviewer binding=pattern max_uses=20 used=0 patterns=['command']
```

**边界（都是实测出来的，不是推断）**：

1. **审批按 `tool_id` 绑定**：给 `exec.pwsh` 签的条子对 `exec.bash` / `exec.run_code` 一律
   `approval_invalid`（"审批绑定的工具与当前动作不一致"）。要让会话同时能用两种工具，
   需要分别签发——而 `.policy/approval.json` 只解析**一个 JSON 对象**
   （`src/enforcement/approvals.py:164-181`，写成数组直接判"审批文件必须是 JSON 对象"→ 视为没有审批）。
   **结论：当前一次只能授权一个执行类工具。**
2. **单次绑定（`binding=action`）在真实会话里不可用**——这就是 pattern 档要解决的问题，实测复现：
   用平台签一条 action 绑定（`action_id=sess-t3-action:A-pwsh-same-id`），
   - 用**同一个** `tool_use_id` 调用 → `allow_delegated`（exit 0）；
   - 用**运行时现生成**的另一个编号调用 → `approval_invalid`：
     "审批绑定的 action_hash 与当前动作不一致：参数、主体或 schema 已经变化，旧审批作废"。
   人签条子时不可能预知下一个 `tool_use_id`，所以 action 档在会话里等于"永远过不去"。
3. **模式化不等于放行一切**：次数上限（`max_uses`，先占用后执行，进审计的
   `approval_use: 第 1/20 次（binding=pattern）`）、整串正则、主体一致、签发角色
   （`granted_by_roles` 必须与注册表 `approvals.require_role: reviewer` 有交集）缺一不可。

### 2.4 "审批修好了" ≠ "会话能跑测试"：三条互相独立的阻碍

**(a) 会话的工具清单里没有 bash / run_code。** 两个真实受治理会话（`governed-grade` /
`governed-grade-approval`）里，模型可用的执行类工具**只有 `pwsh`**；它在总结里明确写了
"本会话暴露的 shell 工具只有 pwsh，没有名为 bash 的工具"，对 run_code 同理。§2.2 里
bash / run_code 的结论因此是**Hook 层**的结论（"如果运行时发出这类调用会怎样"），
**不是会话层的**。会话层唯一能观察到的等价尝试是"用 pwsh 跑 `bash -lc "..."`"→
`command_not_allowlisted`。

**(b) 命令真的执行了，但结果回不到模型（最后一公里）。** 见 §2.5——这一条与审批、
与 pwsh 是否存在都无关，是 PostToolUse 事后验证的设计缺口。

**(c) 平台侧驱动跑不了 pwsh。** 本机 `shutil.which("pwsh")` 为 None（只有 Windows
PowerShell 5.1）。让**平台自己**执行这条命令（`enforcement.cli execute`）：

```
pre   : decision=allow, reason_code=allow, grant_id=grant-6141b5cbd1f44890   ← 授权全通过
执行  : detail="命令不可执行：[WinError 2] 系统找不到指定的文件。" driver=shell_command
        status=failed, reason_code=process_error
final : outcome=repair_required, reason_code=process_error
```

对照：`exec.run_code` 让平台执行时是 `status=delegated`、`final.outcome=delivered`、
`post=not_required`——平台**没有假装执行过**，只是把动作交回运行时。

注意区分：**(c) 是"平台侧驱动"的结论；(a)/(b) 才是"会话侧"的结论。** 会话侧用的
`pwsh` 工具是 dsh 自己的实现，它在本机确实起来了（见 §2.5 的字节码证据）。

### 2.5 真实受治理会话：到底发生了什么

两次真实会话（同一条提示词，要求依次用 pwsh / bash / run_code 跑 `python -m pytest -q`）：

```powershell
python .tmp/governance-capability/harness/run_session.py --label grading-exec-noapproval ^
  --project-dir .tmp/governance-capability/grading/project --profile governed-grade ^
  --task-file .tmp/governance-capability/grading/prompts/exec-pytest.txt
python .tmp/governance-capability/harness/run_session.py --label grading-exec-withapproval ^
  --project-dir .tmp/governance-capability/grading/project-approval --profile governed-grade-approval ^
  --task-file .tmp/governance-capability/grading/prompts/exec-pytest.txt
```

| | 会话 1（无审批，36.7s，exit 0） | 会话 2（exec.pwsh 模式化审批，101.6s，exit 0） |
| --- | --- | --- |
| `python -m pytest -q` 的 PreToolUse | `approval_required`（exit 2） | `enforcement_allow` → `allow_delegated`（exit 0） |
| 该命令的 PostToolUse | `post_not_required` | `post_repair_required` |
| 项目里有没有 pytest 的字节码缓存 | **没有 `__pycache__`** → pytest 从未跑起来 | **有**：`tests/__pycache__/test_order_service.cpython-313-pytest-9.1.1.pyc`，mtime `20:15:42`，落在会话窗口 `20:15:35–20:17:17` 内 → **pytest 真的跑了** |
| 模型最终拿到 pytest 结果了吗 | 没有 | **也没有** |

会话 2 里模型看到的原文（来自 `.tmp/governance-capability/logs/grading-exec-withapproval.log`）：

```
policy-hook: Hook 退出码 1，未知状态按失败关闭拒绝：[policy] POST-CHECK repair_required (post_check_failed)
detail: exit_code_zero: 命令没有退出码：结果不可判定
该动作已经执行，副作用无法撤销：按 repair_required 处理，需要人工或后续修复流程介入
```

**根因（代码级 + 可复现）**：PostToolUse 的 `exit_code_zero` 事后验证只认
`process.exit_code`（`src/enforcement/postcheck.py:426`），而 dsh 桥接重建的
`ExecutionRecord` 恒为 `status=DELEGATED`、**不带 exit_code**
（`src/adapters/dsh/enforcement.py:309-325`）；PostToolUse 载荷里的 `tool_response`
只被留成摘要 + ≤400 字符摘录（`post_event_fields`），**从来没有人从中取退出码**。
于是这条验证器**必然**失败 → `repair_required` → Hook 失败关闭 → dsh 用策略错误
替换掉工具输出 → 真实 pytest 输出到不了模型面前。

我把它单独复现了一遍（不依赖会话，`project-approval`，独立审计文件）：

```
PreToolUse  exit=0   （enforcement_allow → allow_delegated）
PostToolUse exit=2   POST-CHECK repair_required (post_check_failed)
                     detail: exit_code_zero: 命令没有退出码：结果不可判定
```

——即使我在 `tool_response` 里写"2 passed"，结论也一样：**这条事后验证根本不解析文本**。

**一处需要如实标注的差异**：CLI 自己返回 **2**（`EXIT_BLOCK`，插件约定 exit 2 = 阻断），
而会话侧看到的是"**Hook 退出码 1**"。两者都落进失败关闭分支（`policy-hook.plugin.mjs`
把 `exitCode !== 0 && !== 2` 也判成拒绝），治理姿态不受影响；但我没有继续下钻 dsh 的
shell 服务为什么把 2 转述成 1，**按"未定因"记录**。

---

## 3 · 没测到 / 测不了 / 只部分成立（不许美化）

1. **bash 与 run_code 在真实会话里不存在**，所以"受治理会话用 bash 跑测试会怎样"只有
   **Hook 层**结论（`approval_invalid` / `command_not_allowlisted` / `code_blocked`），
   没有会话层结论。工具清单是会话事实，不是我编的报错文本。
2. **"会话跑测试"的最终结论是"执行成功、结果被吞"**，而不是"被治理层挡住"：
   依据是 pytest 的 `.pyc`（时间窗吻合）与 PostToolUse 的 `repair_required`。
   但**我没有直接看到 pytest 的 stdout**（正是因为它被替换掉了），所以
   "测试到底通过没有"这件事**在本机当前配置下无法从会话侧证明**——
   我只能证明"命令被执行过"+"输出没到模型"。
3. **`post_repair_required` 的那条链只在 pwsh 上实测**；bash 有同样的 `post_checks`，
   按代码应同病，但我没有在 bash 上跑通 pre（它缺自己的审批条子，而一个 approval.json
   只能放一条记录）→ **未实测，按推断标注**。
4. **mypy 的失败关闭没有被"真规则"触发过**：43 条里没有 `type_check` 规则。我引用的证据是
   平台自己的 `probe` 输出 + 注册表声明 + §1.4 里同一条代码路径（pytest missing）的实测行为。
   要真正端到端验证，需要一条声明 `type_check` 的规则——那超出我的写域（`policies/` 不归我）。
5. **`style_lint` 对不可解析文件的空判定**只在 `syntaxproj` 一个用例上观察到
   （`unmapped_findings=1` 与 ruff 直跑输出一致）；我没有穷举其他无归属码。
6. **ruff 版本敏感**：本机 ruff 0.14.13 用 `"code": "invalid-syntax"`（无 E999 别名）。
   不同 ruff 版本下这条边界的行为可能不同。
   **2026-09-26 更正**：本条初版还写了"`validation/ruff.toml` 的注释仍按旧口径写 E999"——**那是错的**，
   `validation/` 整个目录不含 `E999`（修复轮逐字检索）。错误说法只在 `docs/` 内部传播。
   N17 的修复见 [00 修复计划 §5.2](../governance-remediation/00-remediation-plan.md)。
7. 两次会话都只有 **一次提示词**；模型每次自发尝试的命令序列不同（会话 2 共 23 次工具调用），
   所以"会话会不会换一种写法绕过"这类问题**没有统计意义上的结论**。

---

## 4 · 复现命令清单

```powershell
# 0) 前提
cd C:\Users\ZNM\Downloads\Memory
$env:PYTHONPATH="C:\Users\ZNM\Downloads\Memory\src"; $env:PYTHONIOENCODING="utf-8"

# 1) 规则集事实（43 条 / checker 分布 / identity）
python .tmp/governance-capability/grading/dump_rules.py
#   -> evidence/rule-universe.json

# 2) 证据路径矩阵：8 个用例，原始 JSON 全部落盘
python .tmp/governance-capability/grading/run_validator_matrix.py
python .tmp/governance-capability/grading/aggregate_validators.py
python .tmp/governance-capability/grading/digest_special_cases.py

# 3) 仅上下文路径（真 PreToolUse Hook）
python .tmp/governance-capability/grading/run_hook_path.py
python .tmp/governance-capability/grading/aggregate_paths.py
#   -> evidence/path-comparison.json

# 4) 执行链：阶段 A（无审批）+ 签发 pattern 审批 + 阶段 B
python .tmp/governance-capability/grading/run_execution_chain.py
python .tmp/governance-capability/grading/run_execution_chain2.py      # bash / run_code 分别签条子
python .tmp/governance-capability/grading/run_action_binding_contrast.py  # action vs pattern
python .tmp/governance-capability/grading/run_post_check_probe.py       # pre+post 的退出码
python .tmp/governance-capability/grading/digest_line2.py               # precheck / execute
python .tmp/governance-capability/grading/digest_execution_chain.py

# 5) 真实受治理会话（两次）
python .tmp/governance-capability/harness/run_session.py --label grading-exec-noapproval ^
  --project-dir .tmp/governance-capability/grading/project --profile governed-grade ^
  --task-file .tmp/governance-capability/grading/prompts/exec-pytest.txt
python .tmp/governance-capability/harness/run_session.py --label grading-exec-withapproval ^
  --project-dir .tmp/governance-capability/grading/project-approval --profile governed-grade-approval ^
  --task-file .tmp/governance-capability/grading/prompts/exec-pytest.txt

# 6) 平台自己的契约测试（ruff 码双向一致）
python -m pytest "tests/contract/test_validator_protocol.py::test_ruff_codes_are_declared_and_selected_in_both_directions" -q
```

---

## 5 · 原始证据清单（都在 `.tmp/governance-capability/grading/` 下）

| 证据 | 路径 |
| --- | --- |
| 规则集事实（43 条 / identity / 每条 checker） | `evidence/rule-universe.json` |
| 证据路径 8 个用例的完整 JSON（含 evidence / blockers / result） | `evidence/pipeline-*.json` |
| 同上但走 `policy.check`（证明它也是证据路径） | `evidence/pre-*.json` |
| 两条路径的对照汇总 | `evidence/path-comparison.json` |
| 仅上下文路径的 Hook 审计（每文件一份） | `valproj/.policy/audit-pre-*.jsonl` |
| 执行链阶段 A/B 的 Hook 记录 | `evidence/exec-A-*.json`、`evidence/exec-B-*.json` |
| 三条模式化审批与它们的请求文档 | `evidence/approval-pattern-*.json`、`evidence/approval-request-*.json` |
| action vs pattern 绑定对照 | `evidence/action-binding-contrast.json` |
| 平台侧 precheck / execute 的完整输出 | `evidence/precheck-pwsh-pattern.json`、`execute-pwsh-platform.json`、`execute-run_code-platform-fresh.json` |
| PostToolUse 复现（pre+post 退出码） | `evidence/post-check-probe.json` |
| 真实会话产物 | `.tmp/governance-capability/evidence/grading-exec-*.json`、`logs/grading-exec-*.log` |
| 会话里工具实际发出的命令（Hook 采集） | `project/.policy/captures/`、`project-approval/.policy/captures/` |
| 会话审计 | `project/.policy/audit.jsonl`、`project-approval/.policy/audit.jsonl` |

## 6 · 如果要把"会话能跑测试"修好，缺的是哪几件（仅供参考，不属于本次取证结论）

1. `exit_code_zero` 需要有退出码可读：PostToolUse 载荷或 dsh 桥接必须把进程退出码
   结构化地带进 `ExecutionRecord`；否则所有 `post_checks: [exit_code_zero]` 的
   执行类工具**永远到不了 `validated`**，放行一次就等于吞掉一次工具输出。
2. 一个 `approval.json` 只能授权一个 `tool_id`：要覆盖多种执行工具，
   需要多记录支持（或在注册表层改成"按工具分文件"）。
3. 会话侧要真的能用 `bash` / `run_code`，得先把它们装配进 profile 的工具清单；
   而 `run_code` 想跑 pytest 与它自己的 `code_check` 结构性冲突
   （`subprocess` / `os` 都是禁止面）——这条不是配置问题，是能力设计问题。
