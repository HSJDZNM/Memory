# T1 · hook-chain 实施记录（G2 / G12 / G3 可见性 / G11）

> 工作流：T1 hook-chain（共享任务板 task-1）。根因 R1，缺口 G2 / G12 / G3(可见性) / G11。
> 写域：`src/adapters/dsh/policy-hook.plugin.mjs`、`src/adapters/dsh/hooks.py`、
> `src/adapters/dsh/README.md`、`tests/contract/test_policy_hook_chain.py`（新）、
> `tests/unit/test_hook_skip_visibility.py`（新）、本文件。
> 本文只写**亲眼看到的输出**；推断、近似与不确定的地方单独标注。

## 0. 一句话

R1 的根因实测成立：Python 侧的事后链路是全的，**缺的就是插件里那一行注册**。本轮把
`tools/post-execute` 注册上，并把这件事变成**会失败的检查**（成对契约 + 真模块假 ctx 探针 +
真实产物判定）；同时把"自检缺席 = 通过"改成失败关闭，把"跳过"与"通过"在审计里分开，
把会进入 AI 上下文的约定文档的来源与哈希留痕。

**真实会话未验证**（本机受限沙箱：dsh 的 `ctx.shell` 用管道 stdio，spawn 直接 EPERM）。
按仓库约定这条只记 `skipped` + reason + reproduce，不记 pass；证据链与复现命令见第 4 节。

## 1. 修改清单（相对路径 + 行号）

| 文件 | 位置 | 改动 |
| --- | --- | --- |
| `src/adapters/dsh/policy-hook.plugin.mjs` | 全文（81 → 168 行） | 注册 `tools/post-execute`；抽出共用的 `runHook()`；post 阶段 exit 2 → `{kind:'block', feedback}`；非 0 非 2 与 spawn 异常一律拒绝；post 载荷带 `tool_response`（复用官方 `blocksToText` 口径，超 4000 字符截断并标注） |
| `src/adapters/dsh/hooks.py` | 108 | `CONTEXT_DOCUMENTS`：显式声明的约定文档清单（AGENTS.md / CLAUDE.md） |
| 〃 | 111 | `call_action_id()`：pre/post 共用的 action_id 口径（与 enforcement.py 一致） |
| 〃 | 154 | `context_documents()`：路径 + sha256 + bytes，读不到写 present=False |
| 〃 | 274 | `AuditLedger.has_record()`：按 reason_code + session 去重 |
| 〃 | 456 / 497 | `rule_visibility()` / `rule_visibility_not_applicable()`：G3 的计数与分类 |
| 〃 | 518 | `_record_context_injection()`：G11 留痕（每会话一次，排在判定记录之后） |
| 〃 | 566-586 | `handle()` 记录 `hook_event` / `tool_use_id` / `action_id`，并把异常分支拆到 `_handle_guarded()` |
| 〃 | 637 | 判定记录 `update(rule_visibility(decision))` |
| 〃 | 849 | 执行类动作写 `rule_visibility_not_applicable()` |
| 〃 | 1001 / 1033 | `post_execute_outcome()` 拆成"审计包装 + `_post_decision_outcome()`"：post 阶段现在也写一条 `hook_event="PostToolUse"` 的 Phase 2 记录 |
| 〃 | 1094-1110 | `run_hook(..., allow_unverified_wiring=…)`（库内显式宽松，CLI 不宽松；理由写在 docstring） |
| 〃 | 1173-1197 | `check_wiring()`：`hooks_config_path is None` → 返回错误（修前返回空串） |
| 〃 | 1262-1276 | `--allow-unverified-wiring`（默认关闭） |
| 〃 | 1300-1325 | `main()`：自检与普通调用都按 CLI 默认拒绝缺席 |
| `src/adapters/dsh/README.md` | 30 / 126 | 事件名与失败关闭条目的口径更新 |
| 〃 | 255-345 | 新增第 9 节：G2 / G3 / G11 / G12 的修复与"会失败的检查" |
| 〃 | 346+ | 第 10 节复现命令补上新的测试与审计检查 |
| `tests/contract/test_policy_hook_chain.py` | 新文件，10 个用例 | 成对契约（源码级 + 真 node 假 ctx + 真实产物）与 CLI 失败关闭 |
| `tests/unit/test_hook_skip_visibility.py` | 新文件，10 个用例 | G3 计数/分类（确定性）+ 真实审计字段 + G11 留痕 + 事后记录可区分 |

## 2. 已核对到的真实 API 与版本（不是凭印象写的）

本机实际安装（2026-09-25 实测）：

| 项 | 实测值 | 怎么得到的 |
| --- | --- | --- |
| dsh CLI | 0.1.6-alpha.2 | `dsh --version` |
| `@deepseek-ai/dsh` | 0.1.6-alpha.2 | 读 `C:\Users\ZNM\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\package.json` |
| `dsh-hooks-claude-code` / `dsh-hooks-codex` | 0.1.6-alpha.2 | 同上（在 dsh 的嵌套 node_modules 下） |

> 注意：`src/adapters/dsh/README.md` 第 1 节的版本表还停在 0.1.5-rc.1/rc.2（那是 Phase 2 的调查记录）。
> 本机现在装的是 0.1.6-alpha.2，**签名核对就是对这个版本做的**；同一份表里 adapter 配置声明的
> `agent_version: 0.1.5-rc.1` 属于 `adapters/dsh/adapter.yaml`（不在 T1 写域），本轮没有改。

事件注册与回调签名（逐行读过实现）：

    dsh-hooks-claude-code/lib/index.js:251-267   ctx.on('tools/pre-execute',  async (exec, next) => …)
    dsh-hooks-claude-code/lib/index.js:268-294   ctx.on('tools/post-execute', async (exec, result, next) => …)
    dsh-hooks-codex/lib/index.js:235-274         同上两个事件（Codex 方言）
    dsh-hooks-claude-code/lib/index.js:347-349   blocksToText(content)：只取 type=='text' 的块并连接
    dsh-hooks-claude-code/lib/index.js:350-357   base(agent, event)：session_id / transcript_path / cwd / hook_event_name
    dsh-hooks-claude-code/lib/index.js:378-386   postToolPayload(exec, result)：tool_name / tool_input / tool_use_id / tool_response

补充佐证（lead 独立核对，2026-09-25）：在 GUI 的实现本体
`C:/Users/ZNM/AppData/Local/Programs/DeepSeek Harness/resources/app.asar`（117 MB，可直接检索字符串）里
同样查到 `tools/post-execute`，签名就是 `async (exec, result, next)`；官方文档口径为
"post-execute 是能带反馈阻塞或向下游决策添加上下文的 waterfall"，并明确
"**被 pre-execute 拒绝的调用同样会经过它**"。后者直接决定了第 3.1 节的断言方式：
被阻断的动作不进入配对要求，见 `test_a_blocked_call_that_still_reaches_post_is_not_reported_as_validated`。

结论（决定了插件的形状）：

- **pre 阶段**返回 `{kind:'deny', reason}` → 工具不执行；
- **post 阶段**副作用已经发生，官方桥的做法是返回 `{kind:'block', feedback:[{type:'text',text}]}`，
  也就是"把这次工具结果标成错误 + 给出理由"，**没有回滚语义**；
- post 的 `result` 是带 `content` 块的结果对象，官方桥用 `blocksToText(result.content)` 折叠成文本。

不确定的部分（如实标注）：插件是**进程内**的，这两条签名核对的是同目录同版本的官方桥实现；
本机没有把 `policy-hook` 装进 desktop profile（那是仓库外的主机配置，见 remediation plan"明确不做"），
所以"dsh 真的会调用这个回调"没有在真实会话里被观察到 —— 见第 4.4 节。

## 3. 逐条：改了什么 + 哪条检查会因此变红

### 3.1 G2 · 事后钩子成对注册

- 修后插件注册两个事件；pre 的转发逻辑一行不改（线协议、退出码语义都不变）。
- 新增"成对"的落点：每次调用都在审计里带 `hook_event` 与 `action_id`，post 阶段也写一条
  Phase 2 记录，于是"缺哪一段"可以在产物上判定，而不是读源码猜。
- 不会踩既有闭环：post 记录**不带** `governed` 与 `event_id`——
  `tools/dsh_sandbox_loop.py` 的 `last_governed()` 取"最后一条 governed 的 pre 记录"，
  事后记录若带 `governed` 会把它取走、改变既有断言；带 `event_id` 则会污染
  `AuditLedger.lookup()` 的重放判定（同一 event_id 的"参数被改过"误报）。

**会失败的检查**（都在 `tests/contract/test_policy_hook_chain.py`）：

| 用例 | 修前会红在哪 |
| --- | --- |
| `test_the_plugin_registers_pre_and_post_together` | 修前源码里没有 `ctx.on('tools/post-execute'` |
| `test_the_plugin_forwards_post_execute_with_the_tool_response` | 修前 `registrations['tools/post-execute']` 是 undefined，harness 直接抛错 |
| `test_an_allowed_governed_edit_leaves_both_pre_and_post_stages` | 修前审计里只有 PreToolUse 记录，`unpaired_actions()` 返回该 action_id |
| `test_the_pairing_check_itself_can_fail` | 检查器本身的对照：只有 pre 的动作必须被点出来 |

### 3.2 G12 · 插件失败关闭 + 接线自检缺席 = 失败关闭

- 插件：`exit 0` 才是放行；`exit 2` 是策略阻断；**其余非 0 与 spawn 异常一律拒绝**
  （pre → `deny`，post → `block`）。
- `check_wiring(config, hooks_config_path=None, allow_unverified_wiring=False)` 现在返回错误；
  `--self-check` 与普通调用路径都默认拒绝缺席；唯一出路是显式命名的 `--allow-unverified-wiring`。
- 库内 `run_hook()` 的默认是 `allow_unverified_wiring=True`：它服务集成测试、学习手册与探针
  （它们不是"由 Agent 运行时启动的 Hook 进程"），而**生产入口 CLI 默认 False**。这条不对称是刻意的，
  代价与理由写在 `run_hook` 的 docstring 与 README 第 9.4 节。

**会失败的检查**：`test_self_check_without_hooks_config_is_fail_closed`、
`test_the_only_way_out_is_the_named_waiver`、`test_a_hook_call_without_hooks_config_blocks_instead_of_allowing`、
`test_the_plugin_denies_every_non_zero_non_two_exit_code_and_every_spawn_failure`。

修前/修后对照（隔离基线 = 当前源码 + HEAD 版 `hooks.py`，同一条命令）：

    修前（HEAD hooks.py）: python -m adapters.dsh.hooks --config <cfg> --self-check
                           [policy] self-check ok            exit=0   ← 缺席即通过（缺口本体）
    修后（工作树）        : 同一条命令
                           [policy] wiring error: 接线自检缺席：没有提供 hooks.json 路径，…  exit=2
    修后 + 显式豁免       : 加 --allow-unverified-wiring
                           [policy] self-check ok            exit=0

### 3.3 G3 · 跳过可见性（只标注，不接 Phase 5 流水线）

审计记录新增（既有字段与 `AUDIT_SCHEMA_VERSION="1.0"` 一律不动）：
`rule_count` / `effective_rule_count` / `skipped_rule_count` / `skipped_reason`（按 checker 归类）/
`checker_scope` + `checker_scope_note`（写明 pre-execute 只做文本类 checker）/
`skipped_rule_ids_unknown`（跳过名单里出现"规则集里没有"的 rule_id）。
没有文件维度的受控动作写 `effective_rule_count: 0` + `skipped_reason={"phase1_not_applicable": N}`。

**会失败的检查**：`tests/unit/test_hook_skip_visibility.py` 的
`test_skip_reason_groups_by_checker_and_never_counts_as_checked`（确定性）、
`test_the_audit_of_an_allowed_edit_reports_the_split`（真实产物）、
`test_existing_audit_fields_are_kept_unchanged`（只增不改）。

### 3.4 G11 · 注入留痕（近似）

`reason_code="context_injection"` 的记录，每会话一条，内容是
`{approximate: true, documents: [{path, present, sha256, bytes}], note}`。
只按显式声明的文件名在项目根查找；读不到的写 `present: false`。

**会失败的检查**：`test_the_session_records_which_context_documents_are_in_play`、
`test_the_injection_record_is_written_once_per_session`。

### 3.5 副作用：既有测试的连带修改

**没有改任何既有测试文件**（写域限制）。因本轮改动而需要更新的既有用例见第 5.2 节。

## 4. 真实命令与真实输出

### 4.1 测试

    python -m pytest tests/unit/test_hook_skip_visibility.py tests/contract/test_policy_hook_chain.py -q
    → 20 passed, 1 warning in 6.48s

    python -m pytest tests/unit -q
    → 672 passed, 1 skipped, 1 warning in 18.24s   （这一轮 0 失败；skipped = 本机不允许创建符号链接，与本轮无关）
    → 我最后一次跑同一命令：669 passed, 4 failed —— 4 条**全部**在 tests/unit/test_wiring.py
      （T2 的新文件，当时正在写）：test_dialect_bridge_is_recognised_as_wired /
      test_profile_patch_with_js_tag_is_not_a_parse_failure /
      test_audit_target_not_declared_is_no_audit_target / test_status_matrix_covers_the_required_states。
      T1 的两个文件没有任何一条出现在失败列表里。

    python -m pytest tests/integration/test_dsh_hook.py tests/integration/test_dsh_enforcement.py tests/contract/test_dsh_adapter.py -q
    → 5 failed, 89 passed, 2 warnings in 15.19s
      FAILED tests/integration/test_dsh_hook.py::test_cli_blocks_with_exit_code_2_and_quiet_stdout      ← 本轮改动引起（见 5.2，lead 统一改）
      FAILED tests/integration/test_dsh_hook.py::test_cli_allows_with_exit_code_0_and_quiet_stdout      ← 本轮改动引起（见 5.2，lead 统一改）
      FAILED tests/integration/test_dsh_hook.py::test_allow_calls_the_executor_exactly_once_without_rewriting_arguments
             ← 与 T1 无关：T3 正在改 proposed_dependencies（实测 ('service','service.orderservice','util','util.clock') vs 期望 ('service','util')）
      FAILED tests/contract/test_dsh_adapter.py::test_controller_dependency_bypasses_are_not_structurally_allowed[…]
      FAILED tests/contract/test_dsh_adapter.py::test_adapter_yaml_zero_directory_hits_are_the_intended_layer_mapping
             ← 两条都在 T3 写域（adapter.py / adapter.yaml）

另外两条仓库门禁（不是 ci_local，是它调用的同一条命令）：

    python tools/check_text_conventions.py
    → 检查 574 个文本文件，问题 0 处，跳过第三方镜像 300 个      exit=0

    ruff check --config validation/ruff.toml src/adapters/dsh/hooks.py
    → 工作树 7 errors；HEAD 版 hooks.py（隔离基线）同样 7 errors
      ⇒ 本轮**没有引入新的 lint 违规**（那 6×E501 + 1×D401 都是既有代码）
    ruff check --config validation/ruff.toml tests/contract/test_policy_hook_chain.py tests/unit/test_hook_skip_visibility.py
    → 0 errors

### 4.2 G2 修前/修后（真插件模块 + 假 ctx）

    # 把 HEAD 版插件导出到 .tmp 后，用同一个假 ctx 探针各跑一次
    node .tmp/hook-chain/registration_probe.mjs <HEAD 版插件>        → ["tools/pre-execute"]
    node .tmp/hook-chain/registration_probe.mjs src/adapters/dsh/policy-hook.plugin.mjs
                                                                    → ["tools/pre-execute","tools/post-execute"]

假 ctx 探针（`tests/contract/test_policy_hook_chain.py` 内的 harness，观察而不断言）实际观察到：

| 场景 | 观察结果 |
| --- | --- |
| pre + exit 0 | `{kind:'enter'}`，调用了一次 `next()`，载荷 `hook_event_name=PreToolUse` 且不带 `tool_response` |
| pre + exit 2 | `{kind:'deny', reason:'blocked by ARCH-001'}`，没有调用 `next()` |
| pre + exit 1 | `{kind:'deny'}`，理由含"退出码 1" |
| pre + spawn 异常 | `{kind:'deny'}`，理由含 `spawn EPERM` |
| post + exit 0 | `{kind:'enter'}`，载荷 `hook_event_name=PostToolUse`、`tool_response='line-1line-2'`（content blocks 折叠）、`tool_use_id` 原样 |
| post + 结果直接是字符串 | `tool_response='plain text result'`（形状变化不会被静默读成空结果） |
| post + 9000 字符结果 | 截断到 4046 字符并带 `已截断` 标注 |
| post + exit 2 / exit 1 / spawn 异常 | `{kind:'block', feedback:[{type:'text',text:…}]}`（把结果标成错误，不回滚） |

### 4.3 真实 dsh 闭环（默认 `DSH_HOME`）

    python tools/dsh_sandbox_loop.py
    → result=fail，block/allow 两个场景 dsh_exit_code=1、审计为空
      日志原文（block-run.txt / allow-run.txt 相同）：
      Error: EPERM: operation not permitted, open 'C:\Users\ZNM\.dsh\profiles\headless\cordis.yml'
        at prepareProfile (…/dsh/lib/profile-boot-BNu17Y9U.js:188:2)

dsh **连启动都没起来**（`$DSH_HOME` 在受控工作区之外，沙箱拒绝写 profile），
而这个脚本的"环境跳过"判定只认日志里的 `spawn EPERM` / `Hook 无法执行` 标记，
所以它判了 `fail` 而不是 `skipped`。**这是 `tools/dsh_sandbox_loop.py` 的一条未覆盖环境跳过路径**
（该文件不在 T1 写域，交 lead 决定是否补）。

### 4.4 真实 dsh 闭环（把 `DSH_HOME` 重定向到工作区内后）

    $env:DSH_HOME='<workspace>/.tmp/hook-chain/dsh-home'; python tools/dsh_sandbox_loop.py
    → result=skipped, environment_skipped=true, sandbox_blocked_spawn=true, 退出码 0
      reason: "Hook 进程起不来（spawn EPERM）：受限沙箱禁止管道 stdio，而 dsh 的 ctx.shell 正是用管道捕获 Hook 输出。…"
      reproduce: "在不受限的 shell 里执行：cd .tmp/phase-2-sandbox/demo-shop && dsh --profile headless --patch .policy/patch.yml \"…\""

即：脚本按仓库约定如实写了 reason + reproduce，**没有把"跑不了"记成 pass**。

### 4.5 真实 dsh 会话（手工，`DSH_HOME` 重定向到工作区内）

    dsh --profile headless --patch .policy/patch.yml "用 edit 工具在 src/shop/order_controller.py 的 create 方法后面加一个方法 def ping(self) -> str: 内部返回 'pong'，然后一句话报告结果。"

真实观察（日志 `.tmp/hook-chain/manual-allow-run.txt`）：

- dsh 起来了、模型跑起来了、插件被调用了 —— 模型最终报告（原文）：
  「**未能完成**：`src/shop/order_controller.py` 的 `create` 方法后未添加 `def ping(self) -> str`，
  因为该沙箱项目的策略 Hook 因无法 spawn（EPERM，沙箱禁止管道 stdio）而按失败关闭，
  `read`/`edit`/`pwsh` 全部被拒，即使在 `danger-full-access` 下重试同一操作仍被拒绝…」
- `.policy/audit.jsonl` 不存在、`captures` 目录不存在（Hook 进程从未启动）；
- `order_controller.py` 的 sha256 未变（`53b53a25…ed66`）；
- 日志里出现 `spawn EPERM`（正是该闭环脚本的 marker）。

**结论**：插件在真实 dsh 会话里确实被调用（模型收到了它返回的拒绝理由并据此停手），
失败关闭在真实运行时成立；但**真实会话无法产生 post_* 记录**——Hook 进程根本起不来。
所以 G2 的证据链到"真插件模块 + 假 ctx + 手工喂 PostToolUse + 真实产物成对判定"为止，
真实会话这一环明确标注**未验证**（原因、日志与复现命令都在上面）。

### 4.6 为什么仍然选 `tools/post-execute`（lead 提到的 `tools/result`）

官方字符串里有 `tools/result`（"Observe final tool outcomes on tools/result; use tools/post-execute only to
transform a result."）。本轮仍挂在 `tools/post-execute`，理由：

1. Python 侧的事后链路本来就以 PostToolUse 为入口（`enforcement.py` 的 `post()`、
   注册表的 `post_checks`、`post_execute_outcome()`），换事件等于重构另一条链；
2. 契约要断言的正是"**被 pre 拒绝的调用也会经过 post**"这一类（见 3.1），
   `tools/result` 的语义是"最终结果观察"，会丢掉这一类的可判定性；
3. lead 要求不要两个都注册。
   将来若迁移到 `tools/result`，必须同时改 Python 侧事件分派与注册表语义，属于另一个工作流。

## 5. 没做的 / 近似 / 未验证 / 需要 lead 决定

### 5.1 明确不做（与 remediation plan 一致）

| 项 | 为什么不做 |
| --- | --- |
| 把 Phase 5 验证器流水线接进 pre 路径（G3 的"真修"） | 架构变更；本轮只做**如实标注**（effective / skipped 计数） |
| 对注入内容做策略校验（G11 的"真修"） | 需要对注入链路的所有权；本轮只做来源 + 哈希留痕 |
| 把插件装进本机 desktop profile | 仓库外的主机配置，需要重启 GUI，无法在本会话内验收 |

### 5.2 因本轮改动需要更新的既有测试（不在 T1 写域，lead 统一改）

`tests/integration/test_dsh_hook.py`：

    L477  completed = run_cli(["--config", str(dsh_config_path)], json.dumps(raw))
       →  completed = run_cli(
              ["--config", str(dsh_config_path),
               "--hooks-config", str(REPO_ROOT / "examples" / "dsh" / "hooks.json")],
              json.dumps(raw),
          )
    L487  同上（allow 用例）
    L494  test_cli_blocks_on_malformed_stdin 不用改：非法 stdin 在 run_hook 之前就被
          捕获（startup_error → exit 2 + "BLOCKED"），实测通过。

理由：这两条用例直接调 CLI 且没传 `--hooks-config`；而仓库里所有真实接线模板
（`examples/dsh/hooks.json` / `examples/dsh/profile-patch.yml` / `tools/dsh_sandbox_loop.py`）
都传了它。`REPO_ROOT` 与那份 hooks.json 在该文件里已被其他用例使用。

### 5.3 未验证 / 近似

1. **真实会话的 post 阶段未验证**（环境限制，见 4.5）。所有 G2 结论都来自假 ctx + 手工 PostToolUse + 真实产物。
2. **插件回调会不会真的被 dsh 调用**：本机没有把插件装进 desktop profile，
   所以"进程内注册"这一步只在 node 假 ctx 里验证过；Python 侧 CLI 与真实 dsh 会话的分派已验证（4.5）。
3. **G11 的注入时刻是近似**：记录的是"本会话第一次 Hook 调用"这个时刻，不是 dsh 真正把
   AGENTS.md 注入上下文的时刻；记录里 `approximate: true` 明说，没有假装它是注入事件。
4. `run_hook()` 的库内默认（`allow_unverified_wiring=True`）**没有自动化检查防误用**：
   它只在 docstring 与 README 第 9.4 节写明"生产入口是 CLI"。受影响调用点（实测 grep）：
   `tests/integration/test_dsh_hook.py:384`、`tests/integration/test_dsh_enforcement.py` 16 处、
   `tools/build_learning_notebook.py` 11 处、`docs/project/learning/phase-2/walkthrough.py` 11 处、
   `docs/project/architecture/tech-detail/notebooks/**` 若干。把库内默认也改成严格需要同步改这些文件
   （其中手册由 `tools/build_learning_notebook.py` 生成，改了会让 ci_local 的
   "Learning notebooks are in sync" 一起红），超出 T1 写域，交 lead 决定。

### 5.4 遗留风险

| 风险 | 说明与处置 |
| --- | --- |
| 事后记录不带 `governed` / `event_id` | 有意为之（见 3.1）。消费方要把 pre/post 接回同一动作时**必须用 `action_id`**；README 第 9.1 节已写明 |
| 审计新增字段但 `AUDIT_SCHEMA_VERSION` 仍是 `"1.0"` | 任务要求"只增不改"；本仓库的消费方按字段读、不按版本拒绝。若将来出现严格的 schema 消费方，需要显式升版本 |
| `tools/dsh_sandbox_loop.py` 的环境跳过判定不覆盖"dsh 自身起不来" | 实测 `result=fail`（4.3）；建议在该脚本里把 profile 写入 EPERM 也判成 skipped + reason + reproduce（该文件不在 T1 写域） |
| `tests/integration/test_dsh_hook.py` 的 2 处调用 | 见 5.2，lead 统一改 |

## 6. 给 V1 的复核入口（不听我自述，直接跑）

    # G2：注册成对（真插件 + 假 ctx）
    node .tmp/hook-chain/registration_probe.mjs src/adapters/dsh/policy-hook.plugin.mjs
    # 期望 ["tools/pre-execute","tools/post-execute"]；把参数换成 HEAD 导出的插件则只有 pre

    # G2：真实产物成对
    python -m pytest tests/contract/test_policy_hook_chain.py -q

    # G12：自检缺席 = 失败关闭
    python -m adapters.dsh.hooks --config <cfg> --self-check      # 期望 exit 2
    python -m adapters.dsh.hooks --config <cfg> --self-check --allow-unverified-wiring   # 期望 exit 0

    # G3：审计里必须出现 effective_rule_count / skipped_rule_count / skipped_reason
    python -m pytest tests/unit/test_hook_skip_visibility.py -q
