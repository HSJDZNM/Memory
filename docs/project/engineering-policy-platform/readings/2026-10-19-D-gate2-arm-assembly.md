# 2026-10-19 D 门 2 开跑装配：A/B 两臂受治树与真实 Hook 探针

> 用途：A/B/C 主实验开跑前的**装配读数**。装配动作只写 `.tmp/dgate2-arms/`（cleanup 会删），
> 本文件记录的是当时的事实、命令与退出码；条子由使用者签，**代理未签发任何审批**。
> 判据：05 §5.1/§5.4/§5.6；04 5.78；`readings/2026-10-19-D-gate2-treatment.md` §2.3.5/§4。

## 1 装配了什么

| 项 | 值 |
| --- | --- |
| A 臂树 | `.tmp/dgate2-arms/A/task-project`，`reset-arm.py` exit 0，**12 文件**，基线摘要 `4e7c4073…`（与 v3 README §1 一致） |
| B 臂树 | `.tmp/dgate2-arms/B/task-project`，同上；两树逐字节同基线（差别只在 `.policy` 的 treatment 声明） |
| 树里没有 | `tools/audit_demo.py`、`tests/test_audit_demo.py`（任务要模型在 M5a/M5b 亲手写）、`.policy/approval.json`、审计/台账 |
| `.policy`（每臂 6 个文件） | `dsh-adapter.yaml`、`hooks.json`、`patch.yml`、`pwsh-request.json`、`tool-registry.yaml`、`tool-registry.approved.json` |
| registry 副本 | `registry/tool-registry.yaml` + `registry/tool-registry.approved.json` 成对复制；`enforcement.cli registry --verify` **两臂各 exit 0（10 个工具全 ok）** |
| Hook 自检 | `adapters.dsh.hooks --self-check`（cwd=树根）**两臂各 exit 0**，stderr 的 `effective-paths` 指向 `.policy/audit.jsonl` / `.policy/enforcement-ledger.jsonl` |

### 1.1 treatment 的接线（两臂唯一的语义差）

| 臂 | `pre_evidence.registry_root` | `validation/test-layout.yaml` 的 `production_patterns` |
| --- | --- | --- |
| A | `…/testing/ab/dgate2/configs/before` | 只有 `src/**/*.py` |
| B | `…/testing/ab/dgate2/configs/after` | 增 `tools/**/*.py` |

其余键与 A3 v2 的受治配置同形：`project_root: ..`、`rules: <repo>/policies`、裸文件名路径、
budget 不等式 20000 + 5000 < 30000；`patch.yml` 的 `projectDir` 分别指向两臂树根，
插件是 `src/adapters/dsh/policy-hook.plugin.mjs`。

## 2 真实 Hook 探针（M5b 形态，**不是正式 run**）

**做法**：把每臂树复制成 `…/<arm>/probe-tree`，补一个 `tests/test_audit_demo.py`（取自参考树），
再把 `write tools/audit_demo.py` 的 PreToolUse 载荷（第 2 代：`hook_payload_version="1.0"` +
`session_cwd` + `session_id`/`tool_use_id`）喂给该臂的真实 Hook CLI。**臂树本身未被修改**。

| 臂 | hook exit | decision | violations | served_checkers | 说明 |
| --- | --- | --- | --- | --- | --- |
| A | **2** | block | `TESTING-002@1` critical，`detail=uncovered_checker`、`value=failing_tests` | 无 `failing_tests` | before 配置下 `tools/**` 不是生产文件 → 选不出测试 → 失败关闭 |
| B | **2** | block | `TESTING-002@1` error，`evidence=real failing test`（`test_main_returns_audit_entries` AttributeError） | **含 `failing_tests`** | after 配置下 `tools/**` 是生产文件 → 真的跑了测试 → 真违规 |

**结论（可证伪的读法）**：同一动作在两臂得到**不同的证据形状**——A 是「没有证据」（uncovered_checker），
B 是「有证据且测试失败」。这正是 treatment 要改变的那条链路；B 的 block 是**真违规**，因为探针把
参考树的测试/脚本放进**基线树**（基线没有 `OrderService.audit_entries`），不是平台缺陷。
正式 run 里模型自己写的测试与脚本一致时，M5b 的 B 臂预期为 allow（见 `examples/dsh/b-plan/a3-task-v3/README.md` §3）。

## 3 使用者要做的两件事（签发，**代理不得自签**）

1. **确认开跑**：回复一句「开跑 A/B/C」（04 5.78 的最后一个前置）。
2. **签两张条子**（A/B 各一张；写进各臂 `.policy/approval.json`）。命令与 pattern 与 A3 同形
   （单引号防 PowerShell 吃掉 `$`），签完把两条 `Get-FileHash` 的 sha256 报给 Lead 写进 run-manifest：
   `approval-pwsh-d-armA` / `approval-pwsh-d-armB`，`--max-uses 200 --ttl 604800`，
   pattern = `^(python -m pytest( .*)?|python tools/[A-Za-z0-9_./-]+[.]py( .*)?)$` + `description=.*`。
   **签之前不要跑 `python tools/cleanup.py`**：它会删掉 `.tmp/dgate2-arms/`，条子随之丢失。

## 4 边界

- 探针不是正式读数：没有模型、没有任务完成度、没有 T/C/A 计分；它只证明**接线**。
- `.tmp/` 里的树、探针副本、条子都是现场产物；受跟踪的证据只有本文件与两臂的构造命令。
- 正式 run 的 run-manifest 必须记：两臂树摘要 `4e7c4073…`、`launcher_sandbox`、条子 sha256 与 `expires_at`、
  `first_message_sha256=123c938c…`、以及每臂的 session id（c-arm README 第 6/7 节的口径同型）。
- 本装配没有改动任何冻结输入（`make_manifest.py --check --strict` 仍 PASS）。
