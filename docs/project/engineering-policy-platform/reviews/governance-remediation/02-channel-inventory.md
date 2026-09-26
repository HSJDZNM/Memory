# T2 · Agent 通道清点（channel inventory）实施记录

> 根因 **R2**（接线状态是"配置事实"，运行期不可自证）、缺口 **G13 / G1**。
> 计划、写域与验收口径见 [00-remediation-plan.md](00-remediation-plan.md)；
> 缺口原文见 [../governance-coverage-gaps.md](../governance-coverage-gaps.md)。
>
> 一句话结论：**本机 3 个 dsh 运行时通道（desktop / headless / web）全部 `not_wired`**，
> `python -m adapters.cli wiring --check` 退出 **1** 并逐个点名；
> desktop 通道恰好承载 Agent Teams（bundles 里有 `@deepseek-ai/dsh-experimental-agent-team-profile`），
> 也就是说 G1 的"Agent Teams 零治理零留痕"从一个口头结论变成了**一条会失败的命令输出**。

## 1. 交付物

| 文件 | 内容 |
| --- | --- |
| `src/adapters/wiring.py`（新，1405 行） | 通道探测、状态机、工具漂移报告；无副作用、只读 |
| `src/adapters/cli.py`（改，+151/-3） | 新增 `wiring` 子命令（`run_wiring` / `_print_wiring` / 解析器注册 / `--require-runtime`） |
| `tests/unit/test_wiring.py`（新） | 72 个用例：状态机逐状态、确定性排序、绝对路径脱敏、跳过终态、预算读不到、参数校验 |
| `tests/contract/test_wiring_inventory.py`（新） | 16 个用例：CLI 退出码契约、JSON 形状、与运行期自检互相验证 |
| 本文件 | 实测证据、接线模板、遗留风险 |

只读依赖：`adapters.dsh.adapter.TOOL_TABLE`（T3 的唯一声明源，**不复制**）、
`policy.checkers`（经 adapter 间接导入）。**没有**修改 `src/adapters/dsh/*`、注册表或任何数据文件。

## 2. 状态机：什么算"接线成立"

状态是显式枚举（`ChannelStatus`）。**只有 `wired` 算通过**：
`WiringReport.ok = 至少探到 1 个通道 且 所有通道都是 wired`——一个通道都没探到不是"全绿"，是"没得证明"。

| 状态 | 触发条件（读得到什么、读不到什么） |
| --- | --- |
| `wired` | 桥挂上了 + hooks 配置里有指向 `adapters.dsh.hooks` 的命令 + 审计目标存在且有新鲜留痕 |
| `not_wired` | patch 层里没有桥；或桥/命令存在但没有一条指向 `adapters.dsh.hooks` |
| `hooks_config_missing` | profile patch 层不存在；或桥没声明 hooks 配置路径；或声明的文件不存在 |
| `hooks_config_unparsable` | patch 层 YAML 语法错误 / 结构不是列表或映射；或 hooks.json 不是合法 JSON |
| `no_audit_target` | 命令没有 `--audit`，adapter 配置也没有 `audit_log`：留痕无从证明 |
| `audit_never_written` | 声明了审计目标但文件不存在，或存在而没有任何可解析记录 |
| `stale` | 最后一条留痕距"现在"超过阈值（`--stale-after`，默认 7 天） |
| `timeout_budget_violated` | **算出来不满足**：dsh 侧 timeout（`timeoutMs` / hooks `timeout`，取两者最小值）不大于内部预算 `timeout_ms`——dsh 会先杀掉 Hook，而被杀等于放行（AGENTS.md 第 10 条） |
| `timeout_budget_unknown` | **根本算不出来**：读数缺失 / 解析失败 / 非法（adapter 配置读不到、`timeout_ms` 非法、`timeoutMs` 是 `!!js` 表达式、方言桥没声明任何 dsh 侧超时）——证明不了不等式成立 |
| `profile_unreadable` | patch 路径不是普通文件 / 读不到（编码、IO） |
| `hooks_config_unreadable` | hooks 配置是个目录 / 读不到 |
| `audit_unreadable` | 审计目标是个目录 / 读不到 |
| `audit_unparsable` | 审计文件存在但**一行都解析不出**（全是被杀出来的半行 / 非 JSON） |

三条刻意设计：

1. **"读不到"绝不折叠成"正常"**：不存在、不可解析、读不出来各有独立状态，全部让 `--check` 变红；
2. **"没找到"与"没找"分开**：相对路径按 `bridge.projectDir` → `--project-root` → profile 目录
   依次解析，并把**试过的每一个基准**写进 detail；
3. **不制造假红**：dsh 的 patch 层允许 `!!js` 表达式，裸 `yaml.safe_load` 会把真机上完全正常的
   `cordis.patch.yml` 判成"不可解析"（本机 desktop profile 就是这样）。
   模块用`认识结构但不执行表达式`的 loader，退化成占位值并记一条警告——
   否则这条检查第一次运行就会教人忽略它。

**第 4、5 条来自 Lead 裁决（2026-09-25）：预算不等式从"记一条 warning"升级为"阻断"，
读不到预算也阻断。**

- **算出来不满足 -> `timeout_budget_violated`**。理由不是"看着更严"，而是仓库自己的口径：
  AGENTS.md 第 10 条要求"内部预算小于 Agent 侧超时（否则被杀=放行）"，
  `src/adapters/dsh/hooks.py` 的 `check_wiring()` 也把这一条当错误字符串返回。
  **运行期判错、静态清点判过就是两套口径**——正是本轮要消灭的东西。
  `tests/contract/test_wiring_inventory.py::test_timeout_budget_check_agrees_with_the_hook_self_check`
  把两边钉在同一个结论上；`test_unprovable_budget_fails_the_check` 守住"读不到 -> `--check` 非 0"。
- **算不出来 -> `timeout_budget_unknown`**。"读不到"不等于"不等式成立"：`--config` 指向的
  adapter 配置缺失 / 不可解析 / `timeout_ms` 非法、`timeoutMs` 是 `!!js` 表达式、
  方言桥没有任何可读的 dsh 侧超时——一律失败态，绝不 `wired`。

**这里有一处清点故意比 `check_wiring()` 更严，写清楚（Lead 要求"读不到就说清楚"）：**

| 情形 | 运行期 `check_wiring()` | 清点 `wiring` | 为什么清点更严是安全的 |
| --- | --- | --- | --- |
| 两侧都能读到且满足不等式 | 通过 | `wired` | 一致 |
| 两侧都能读且不满足 | 报错 | `timeout_budget_violated` | 一致 |
| **adapter 配置读不到** | **通过**（它不读 adapter 配置） | `timeout_budget_unknown` | 运行期真正发生的是 Hook 进程 `load_config` 失败 -> 退出码 2 -> **每次调用都被阻断**；清点的结论与这个真实行为一致，而 `check_wiring` 只检查 hooks.json 这一小段 |
| **没声明任何 dsh 侧超时** | 通过（它只在声明了 timeout 时才比） | `timeout_budget_unknown` | 无法证明"内部预算 < 被杀阈值"；要求显式声明是失败关闭方向，代价只是多写一行配置 |

两个"读不到"里没有真正合法却被拒的情形：`timeout_ms` 缺省 5000ms 与插件 `DEFAULT_TIMEOUT_MS`
缺省 30000ms 都**当作可读的默认值**处理（不是 unknown），并由两条测试盯着这两个数不许漂移：
`test_internal_budget_default_matches_the_runtime_loader`（读运行期 `load_config`）与
`test_in_process_default_timeout_matches_the_plugin_source`（读插件源码）。

### 2.1 三个终态：`pass` / `fail` / `skipped`

`result` 是三值，**`skipped` 绝不是 `pass`**（G3 的教训"跳过不等于通过"用在清点上）：

| 终态 | 什么时候出现 | `--check` 退出码 |
| --- | --- | --- |
| `pass` | 至少 1 个通道，且每个通道都 `wired` | 0 |
| `fail` | 发现了运行时，但存在未接线 / 配置读不到 / 解不开 / 无留痕 / 预算击穿的通道 | 1 |
| `skipped` | **探遍了所有候选根，本机根本没有可发现的 Agent 运行时**：`environment_skipped: true` + `skip_reason` + `reproduce` | 0（加 `--require-runtime` 时为 1） |

两条边界写清楚：

- 显式 `--dsh-home <不存在的路径>` **不是** skipped，是 `fail`——那是"你声称有运行时"；
- dsh 根存在、但 `profiles/` 缺失或里面没有任何 profile，也是 `fail`——那是"运行时配置坏了"。

**为什么不接进 GitHub Actions**：那里永远没有 Agent 运行时，接了只会得到一个永远 `skipped` 的步骤，
把"没得证明"变成仪式。本机门禁（`tools/ci_local.py`）由 Lead 接入；`--require-runtime`
可以让"环境跳过"变红灯，与 `tools/dsh_sandbox_loop.py` 的 `--require-dsh` 是同一条思路。

## 3. 本机实测事实（2026-09-25，$DSH_HOME = C:/Users/ZNM/.dsh）

| 事实 | 值 | 来源 |
| --- | --- | --- |
| dsh 配置根 | `$DSH_HOME`（环境变量指向），`~/.dsh` 同时存在；`%APPDATA%/dsh`、`%LOCALAPPDATA%/dsh` 不存在 | `probe.candidates` |
| profiles 目录条目 | `desktop` / `headless` / `web`（`node_modules` 不是 profile：既无 `cordis.yml` 也无 `cordis.patch.yml`，被跳过并在 notes 里点名） | `probe.notes` |
| desktop bundles | `@deepseek-ai/dsh-base`、`@deepseek-ai/dsh-experimental-agent-team-profile`、`@deepseek-ai/dsh-experimental-auto-review`、`@deepseek-ai/dsh-experimental-voice-input-bundle`、`@deepseek-ai/dsh-web-app` | `channels[].bundles` |
| 三个 profile 的 patch 层 | 都读得到、可解析（desktop 含 `!!js` 标签，按占位值继续） | `wiring` 输出 |
| 桥（`policy-hook.plugin.mjs` / `@deepseek-ai/dsh-hooks-*`） | **三个 profile 一个都没有** | 同上 |
| `hooks.json` / `*.plugin.mjs` | 全 `$DSH_HOME` 递归**没有任何**这类文件 | Lead 独立探测（见任务简报）+ 本命令一致结论 |
| 审计 JSONL 留痕 | 没有可声明的目标（没接线就没有 `--audit`），因此是 `not_wired` 而非 `no_audit_target` | `wiring` 输出 |

> 上一次修前基线：同一台机器上不存在任何"哪个通道没接线"的可执行结论；
> `hooks.check_wiring()` 在 `hooks_config_path is None` 时直接返回空串（= 通过）。

## 4. 命令与真实输出

系统解释器（3.13，已装 pytest/pydantic/PyYAML），仓库未安装成包，因此显式给 `PYTHONPATH`：

```powershell
$env:PYTHONPATH='src'
python -m adapters.cli wiring            # 报告：退出码 0
python -m adapters.cli wiring --json     # 同一份事实的机器可读形式
python -m adapters.cli wiring --check    # 门禁：任一通道未接线 / 无留痕 -> 退出 1
```

`wiring`（节选，完整输出见 CI/本地重跑；路径一律相对 `$DSH_HOME`，不出现绝对路径）：

```text
Agent 通道清点：dsh 配置根 = $DSH_HOME（来源 env:DSH_HOME）
  探测状态：ok；通道 3 个
  dsh:desktop  [not_wired]
      profile patch 里没有挂载策略桥（policy-hook.plugin.mjs / @deepseek-ai/dsh-hooks-*）：该通道零治理零留痕
      bundles：@deepseek-ai/dsh-base, @deepseek-ai/dsh-experimental-agent-team-profile, ...
  dsh:headless  [not_wired]
      ...
  dsh:web  [not_wired]
      ...
  说明：跳过不是 profile 的目录（既没有 cordis.yml 也没有 cordis.patch.yml）：profiles/node_modules
```

`wiring --check` 的 stderr 与退出码（**这就是本轮要的"会失败的检查"**）：

```text
结果：fail（未接线 / 无留痕 3 个通道）
  FAIL dsh:desktop: not_wired — profile patch 里没有挂载策略桥（...）：该通道零治理零留痕
  FAIL dsh:headless: not_wired — profile patch 里没有挂载策略桥（...）：该通道零治理零留痕
  FAIL dsh:web: not_wired — profile patch 里没有挂载策略桥（...）：该通道零治理零留痕
加 --check 可以让它成为门禁（退出码 1）
check_exit=1
```

`--json` 关键字段（真实值）：

```json
{
  "probe": {"dsh_home": "$DSH_HOME", "dsh_home_source": "env:DSH_HOME", "status": "ok",
            "candidates": [{"label": "env:DSH_HOME", "exists": true},
                           {"label": "default:~/.dsh", "exists": true},
                           {"label": "env:APPDATA/dsh", "exists": false},
                           {"label": "env:LOCALAPPDATA/dsh", "exists": false}]},
  "counts": {"total": 3, "wired": 0, "failed": 3},
  "result": "fail",
  "tools": {"declaration_source": "src/adapters/dsh/adapter.py:TOOL_TABLE",
            "declared_count": 38, "observation_status": "observed", "sessions_scanned": 8,
            "observed_not_in_table": [], "report_only": true}
}
```

退出码口径：`0` = `pass` 或 `skipped`（或报告模式）；`1` = `fail`（仅 `--check`），
或 `skipped` 加上 `--require-runtime`；`2` = 用法错误（`--now` 非法、`--stale-after <= 0`、
`--project-root` 不存在）。机器可读的判据始终是 `result` 字段，不是退出码本身：
`skipped` 的退出码是 0，但它**不是** `pass`。

## 5. 接线模板（可复现，但"真正装上"不在本会话验收范围）

dsh 的接线是**两层，缺一层都不生效**（详见 `src/adapters/dsh/README.md` 第 3 节）。
仓库里已有可直接使用的样例：`examples/dsh/profile-patch.yml`、`examples/dsh/hooks.json`。

第一层：把桥挂到 profile 上（`$DSH_HOME/profiles/<name>/cordis.patch.yml`），
或用 `--patch <file>` 叠加一层而不改别人的文件：

```yaml
- insert:
    - id: policy-hook
      name: '<仓库绝对路径>/src/adapters/dsh/policy-hook.plugin.mjs'
      config:
        command: >-
          python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml
          --hooks-config .policy/hooks.json --audit .policy/audit.jsonl
        timeoutMs: 30000            # 必须大于 dsh-adapter.yaml 的 timeout_ms
        projectDir: '<受治理项目的绝对路径>'
```

第二层：`--hooks-config` 指向的 hooks.json（matcher 必须留空，匹配全部工具）：

```json
{
  "hooks": {
    "PreToolUse": [
      { "hooks": [ { "type": "command",
        "command": "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml --hooks-config .policy/hooks.json --audit .policy/audit.jsonl",
        "timeout": 30 } ] }
    ]
  }
}
```

装好之后的验收方式（本命令自己）：

```powershell
python -m adapters.cli wiring --check
# 期望：result=pass，channels 里对应通道 status=wired
```

**不在本会话验收范围内**：desktop profile 属于本机 GUI 的运行时配置，
把补丁装进去需要重启 GUI 才会生效，而重启会中断当前会话；
本轮的处置是把"没装"变成**可发现、可失败**的结论（第 4 节），而不是假装装上了。
装的时候注意：`--hooks-config` 指的那份 hooks.json 里**也必须有**指向
`adapters.dsh.hooks` 的命令——否则 Hook 的运行期自检会对每次调用判 `wiring_error`
（本模块把这种组合报成 `not_wired`，见 `tests/unit/test_wiring.py` 的同名用例）。

## 6. 工具漂移（只报告，本轮不作为阻断项）

- **声明源**：`src/adapters/dsh/adapter.py:TOOL_TABLE`（只读导入，38 项，T3 已补 Agent Teams 工具）；
- **观察源**：`$DSH_HOME/sessions/**/*.jsonl[.zstd]` 里最近 N 份（默认 8）会话记录，
  只取 `data.header.tools[].name`（该会话可用的工具清单）与
  `data.message.content[]` 中 `type=tool_use` 的 `name`（真的被调用过的工具）；
  **不读、不留任何会话正文**；
- 本机实测：`observation_status=observed`，扫描 8 份，`observed_not_in_table=[]`；
- 观察源不可用（目录不存在 / 缺 zstandard / 读不到）时状态是
  `observation_unavailable`，**不是"无漂移"**；声明表读不到时也不报漂移
  （拿不到表就说"这些工具不在表里"是另一种假安全感）。

## 7. 测试：哪些检查会因此变红

> 记录一次真实被抓住的缺陷（不是假设）：实现"环境跳过"终态时，
> `probe_wiring` 里代表"非 profile 目录"的局部列表与代表终态的布尔量**重名**，
> 于是在真机（`profiles/node_modules` 被跳过）上整份报告被读成 `skipped`——
> 而当时 74 个用例全绿，因为它们构造的夹具里没有那么多余目录。
> 是"改完再跑一次真机命令"抓住了它：`wiring --check` 退出 0。修复 = 改名 + 补上面那条回归用例
> （夹具里必须同时有一个非 profile 目录和一个未接线 profile）。

| 会失败的检查 | 断言什么 |
| --- | --- |
| `tests/contract/test_wiring_inventory.py::test_wiring_check_exits_non_zero_and_names_the_unwired_channel` | 未接线 -> 退出 1，且 stderr 出现 `dsh:desktop` 与 `not_wired` |
| `...::test_unreadable_configuration_never_passes` | 配置读不到 -> 退出 1、`wired=false`、`result=fail` |
| `...::test_missing_dsh_home_fails_the_check_and_says_so` | 探不到 dsh 根 -> 退出 1（**不是真空通过**） |
| `...::test_wiring_json_contract` / `test_wiring_json_exposes_required_channel_statuses` | 状态枚举与 JSON 形状是协议：改名/删除会红 |
| `...::test_wiring_verdict_agrees_with_the_hook_self_check` 等 3 个 | 与运行期 `hooks.check_wiring` 两套独立实现**结论必须一致**（含超时不等式：运行期判错 <=> 清点 `timeout_budget_violated`） |
| `...::test_no_runtime_is_skipped_in_the_cli_and_require_runtime_turns_it_red` | `skipped` 退出 0 但 `result != "pass"` 且写明 reason；`--require-runtime` 让它退出 1 |
| `...::test_unprovable_budget_fails_the_check` | **预算事实读不到（缺失 / 不可解析）-> `--check` 退出 1**，状态 `timeout_budget_unknown`、`wired=false` |
| `...::test_wiring_output_contains_no_absolute_paths` | 报告里不出现夹具绝对路径 |
| `tests/unit/test_wiring.py::test_status_matrix_covers_the_required_states` | 需求点名的 7 种状态都做得出来，且只有 wired 通过 |
| `...::test_missing_patch_layer_is_explicit_failure_not_pass` | "配置读不到不等于通过" |
| `...::test_observed_runtime_tools_are_reported_but_never_block` | 漂移只报告：出现表外工具时 `ok` 不受影响 |
| `...::test_channels_are_sorted_by_channel_id_and_output_is_deterministic` | 同样输入同样输出（含倒序创建 profile） |
| `...::test_profile_patch_with_js_tag_is_not_a_parse_failure` | `!!js` 不许被判成配置损坏（假红） |
| `...::test_timeout_budget_violation_blocks` / `::test_hooks_timeout_over_budget_also_blocks` | 预算击穿是失败态（进程内 timeoutMs 与方言桥 hooks timeout 两条路径都覆盖） |
| `...::test_adapter_config_missing_makes_the_budget_unprovable` / `::test_unparsable_adapter_config_makes_the_budget_unprovable` / `::test_invalid_timeout_ms_in_adapter_config_is_unprovable` | 预算读不到 / 解不开 / 非法 -> `timeout_budget_unknown`（`ok=false`） |
| `...::test_adapter_config_without_timeout_ms_uses_the_runtime_default` / `::test_in_process_default_timeout_matches_the_plugin_source` | 两个缺省值（5000ms / 30000ms）必须等于运行期真实默认值，漂移会红 |
| `...::test_js_expression_in_timeout_ms_makes_the_budget_unprovable` | `!!js` 形式的 dsh 侧超时：不是"配置损坏"，但数值读不出 -> 证明不了 -> 失败态 |
| `...::test_plugin_default_timeout_is_used_when_timeout_ms_is_absent` / `::test_invalid_timeout_ms_declaration_is_not_wired` / `::test_dialect_bridge_without_any_declared_timeout_is_unprovable` | 没写 timeoutMs = 用插件默认值（wired）；写了非法值 = 通道起不来（not_wired）；方言桥什么都不声明 = 证明不了 |
| `...::test_no_discoverable_runtime_is_skipped_not_passed` / `::test_explicit_missing_dsh_home_is_a_failure_not_a_pass_nor_a_skip` | 环境跳过 vs 显式指定不存在的 dsh 根，两种情形结论不同且都不可读成通过 |
| `...::test_a_skipped_directory_never_turns_the_whole_report_into_skipped` | **回归**：真机 `profiles/` 里有个 `node_modules`，它只能进 notes，不能把整份结果变成 `skipped` |

跑法：

```powershell
python -m pytest tests/unit/test_wiring.py tests/contract/test_wiring_inventory.py -q
```

## 8. 没做 / 不做 / 已由 Lead 裁决

1. **没做**：把补丁真正装进本机 desktop profile（仓库外的主机配置 + 需要重启 GUI，见第 5 节）；
2. **已裁决（2026-09-25）**：`wiring --check` **接进本机门禁**（`tools/ci_local.py`，由 Lead 接入），
   **不接 GitHub Actions**——那里永远没有 Agent 运行时，接了只会得到一个永远 `skipped` 的步骤，
   把"没得证明"变成仪式。跳过语义见第 2.1 节：`--check` 对 `skipped` 退出 0 但 `result="skipped"`，
   需要更严时用 `--require-runtime` 把它变红；
3. **已裁决（2026-09-25）**：预算不等式从警告**升级为阻断项**（见第 2 节第 4 条），
   并与运行期 `hooks.check_wiring` 用契约用例钉成同一结论；
   **"读不到预算"同样是失败态**（`timeout_budget_unknown`）：算不出来 != 成立，
   见第 2 节两张表与"清点故意更严"的对照说明；
4. **不做**：别的 Agent 产品（Claude Code / Codex 原生安装）的通道探测——
   本机没有它们的配置根可证；`ChannelReport.kind` 留了扩展位，但目前只有 `dsh-profile`；
5. **不做（已裁决）**：本轮不清理 `src/adapters/cli.py` 的既有 ruff 违规——
   作为"既有问题"登记在第 9.1 节，附复现命令。

## 9. 遗留风险

| 风险 | 现状 | 处置 |
| --- | --- | --- |
| 会话记录格式耦合（`session.v3/v4.jsonl.zstd`） | 只读 `data.header.tools` 与 `data.message.content` 两处；读不到就是 `observation_unavailable` | 格式变了漂移会退化成"不可用"而不是错报，届时补渲染分支 |
| `zstandard` 不在 `requirements.lock` | 本机系统解释器有；CI 上没有 -> 漂移观察退化成显式不可用（**不阻断**，因为漂移本轮只报告） | 若要让 CI 也观察，需要把 `zstandard` 加进依赖或改用别的观察源（Lead 决定） |
| hooks 配置的遍历逻辑与 `hooks.check_wiring` 各写一份 | 两个实现由 3 个契约用例互相钉住 | 若 T1 改了 `check_wiring` 的遍历口径，契约用例会红 |
| 审计"部分损坏行"只记警告 | 与 `AuditLedger` 容忍被截断最后一行的口径一致 | 结论只基于可解析记录，且必须打印警告 |
| 清点在"预算读不到"上比 `check_wiring()` 更严 | 那个运行期函数不读 adapter 配置，只在"hooks.json 声明了 timeout 且不满足"时报错；清点把"证明不了"判成失败（对照表见第 2 节） | 方向是失败关闭：运行期真实的后果是 Hook `load_config` 失败 -> 退出码 2 -> 每次调用都被阻断，清点与这个行为一致。将来若出现**合法却读不到**的情形，必须带着证据改这一条，不许默默放行 |

### 9.1 既有问题（不是本轮引入，本轮不清理）

`src/adapters/cli.py` 在 HEAD 版本就有 8 处 `validation/ruff.toml` 违规
（`I001` + 5 处 `F401` 未使用导入 + 2 处 `E501`）。本轮新增的行全部符合 E501，
也没有顺手改这些既有行——按 Lead 裁决本轮不清理（AGENTS.md 工作方式第 2 条：改动聚焦）。
复现（对 HEAD 版本按同一路径跑 ruff；必须给 `--stdin-filename` 才会套用仓库配置）：

```powershell
git show HEAD:src/adapters/cli.py | python -m ruff check --config validation/ruff.toml --stdin-filename src/adapters/cli.py -
```

输出（HEAD）：`I001` × 1、`F401` × 5、`E501` × 2 —— 共 8 条，与本轮改动无关。

**2026-09-26 更新：已清理。** 范围由用户裁决为"本轮改动集里的 `src/` + `tests/` + 手写 `tools/`"，
即上面的 `src/adapters/cli.py`（8 条）与同一批文件里的其它既有违规**一起清到 0**；
逐文件清单、边界（notebook 生成链与 `docs/` 明确排除且**计数不变**）与独立验收见
[07-ruff-cleanup-and-n1.md](07-ruff-cleanup-and-n1.md) §2 与
[08-n1-independent-verification.md](08-n1-independent-verification.md) §3。
本轮**没有新增任何 `noqa`**，也没有改 `validation/ruff.toml`（它的 sha256 会写进验证器证据）。
上面那 8 条不再是遗留项——本节保留原文只作为"当时为什么没清"的记录。
