# 2026-10-21 新会话交接提示词

> **2026-10-21 会话内更新**：§3 的 C4 只读探针、C1-b 批次进判定（opt-in）、受治侧 registry 1.4 同步与重审、
> AGENTS 第 55 条轴表拆分、间接执行面裁定均已在本次会话完成（提交 `82ff5e5` / `4758679` / `b0cfc45` / `8d6a1c7` /
> `951c9c1` / `72df19e` 与本行所在提交）；余下事项见 04、06 与 §3.5（D 实验每臂 k≥3，**本轮未跑**）。
> 本文件此后按历史交接文档对待：结论以 04/06 为准。

> **用法**：把本文件 §1 起整段作为新会话的第一条消息（或作为系统提示的附录）。它假设读者是一个**没有本会话上下文的新 agent**，
> 自包含地给出：仓库、现状、剩余任务与验收、纪律、命令。
> 本文件写于 HEAD `ea1e8ab` 之后（工作树干净、门禁 26/26）；开工前先 `git log -1` 确认 HEAD 没再前进。

## 0 角色与仓库

你是本仓库（`C:\Users\ZNM\Downloads\Memory`，Python src 布局，`.venv/Scripts/python.exe`，pytest）的 **Lead agent**。
分支 `main`，单人仓库。安装/测试/CLI 命令以根 `README.md` 为准且必须保持可执行。

**环境事实（本机实测，别当建议忽略）**：
- `tools/ci_local.py` 的 pytest 步骤用 xdist 多进程共享 `.tmp/tmp/pytest-of-ZNM`；在 `workspace-write` 沙箱下工作进程读不到控制器建的临时目录（PermissionError → INTERNALERROR，pytest 步骤 exit 3）。**跑门禁必须 danger-full-access**（R-A-GATE-07..10 四次都是这样跑的）。
- `.tmp` 下有 52 个 ACL 残留目录删不掉（`cleanup.py` 退出 1，非代码失败）；`.tmp/.pytest_cache` 建不出来只会产生 PytestCacheWarning。
- 同一工作树同时只允许一个 `ci_local.py` 在跑（`.tmp/ci-local.lock`）；门禁约 5–8 分钟。

## 1 必读（按顺序，别跳）

1. `AGENTS.md`：56 条仓库纪律。**重点**：10（失败关闭）、13/14/17（受控执行与命令最小权限）、38（自审）、45（仪器要能失败）、50（口径诚实）、52（失败关闭≠理由正确）、55（加键就是改协议）、56（义务账）。
2. `docs/project/engineering-policy-platform/README.md`：文档索引与"现在做到哪"（本会话刚更新）。
3. `04-open-work.md`：**未完成工作的唯一去处**。先读 5.80（AGENTS 预算）、5.83（B1 残留）、5.84（C3 两段）、5.86（B3 六条）、5.87（执行面）、5.88（C1-a 五条）。
4. `05-implementation-plan.md` §4（阶段 A/B/C/D 与门）、§5（D 实验）、§8（变更控制：第 9 条是本轮授权与落地记录）。
5. `06-plan-progress.md` §7.2–§7.7（本轮 C/R/P/D 记录；**格式与三态口径**照它写）。
6. 最新读数（全是本轮落地证据）：
   - `readings/2026-10-20-B1-param-domain.md`（审批 1.3 参数域）
   - `readings/2026-10-20-B3-read-guard.md`（只读族读面）
   - `readings/2026-10-20-C3-final-tree-gate.md`（整树门禁）
   - `readings/2026-10-21-C3-control-plane-write-guard.md`（`.policy` 写面）
   - `readings/2026-10-21-C3-git-surface-guard.md`（`.git`/CI 执行面）
   - `readings/2026-10-21-C1-a-batch-ledger.md`（批次台账只报告）
   - `readings/2026-10-21-C1C2C4-adjudication-draft.md`（C1/C2/C4 裁定草案，含建议与门）

## 2 现在的状态（已验证，别重做）

| 项 | 结论 | 证据 |
| --- | --- | --- |
| B1 审批「参数域」 | 协议 1.2→1.3；注册表 1.0→1.1；族数据；R-d 18 行逐条相等、负例全拒 | `fe292b9`、B1 读数 |
| B3 只读族读面闸门 | 18 条矩阵 7 条新拦、8 条 0 误伤；「400 份真实会话回放」**未取得** | `9a88112`、B3 读数 |
| C3 整树门禁 v1 | 只读工具；0/1/2 退出码；`RuleSet.identity` 钉住 | `aca9491` |
| C3 控制面写面 | `.policy` 写入 8/8 翻面（审批条子/审计账本曾可被写） | `8e6a3cb` |
| C3 执行面 | `.git` 与 `.github/workflows` 7/7 翻面、20 条相等 | `45d6168` |
| C1-a 批次台账 | 只报告；审计 1.3→1.4（`batch_ref`+`batch` 四态）；开/关 decision 逐字节相等 | `05a05d5` |
| 文档 | 04/05/06/07/README 已同步；门禁 26/26（R-A-GATE-10） | `526f73c`/`ea1e8ab` |

## 3 剩余任务（按优先级；每项都要读数 + 用例 + 文档 + 提交）

### 3.1 C4 验证探针（只读，建议先做，约 1 天）
**问题**：dsh 宿主在回合收尾前派发 `agent/turn-stopping`，约定是监听器里调用 `agent.steer(...)` 注入一条新指令（没有 "block" 返回值）；仓库插件目前**没有订阅**该事件（05 §3.1）。
**交付**：一个只读探针（`tools/` 或 `.tmp` 起，稳定后升格并按第 55 条建轴），在桌面 profile 的插件里订阅该事件，验证 `agent.steer` 是否存在、调用后宿主是否重读收件箱再跑一步；两种结果都落读数（可用 / 不可用）。
**验收**：真机两例（有未结清：多跑一步且第二次不再注入；没有：回合正常结束）或明确"宿主不可用"并收口；不新增任何阻断。
**边界**：不改判定、不动 `src/policy`；插件侧改动遵循 52 条（理由措辞是跨侧契约）。

### 3.2 C1-b 批次进判定（先交裁定草案，约 2–3 天）
**前置**：裁定「未结算批次不得当作通过」的语义、以及"批次里包含被 block 的提议"如何过滤（04 5.88③④）。
**交付**：批次进 `pre_evidence` 取证树的实现 + 协议升版（按实际载荷变哪份算）+ 门（三步判定与合并判定逐个相等）+ 真实 Hook 三次 edit 读数（C1-a 欠的那条真机读数）。
**边界**：不改 `policy.engine.evaluate`；失败关闭；预算不等式重算。

### 3.3 受治侧同步与重审（约 1 天）
把仓库侧的 `registry/tool-registry.yaml`（1.4：`read_guard` + `.policy`/`.git`/`.github/workflows` 前缀 + 命令族/默认值）同步到受治侧 `tool-registry.local.yaml`，重新 `registry --approve`，并在真实受治会话里验证：读面越界被拦、`.policy` 写入被拦、审计里出现 `batch_ref`。
**验收**：真实会话读数（不是夹具）；受治台账/审计可复核。

### 3.4 AGENTS 版本轴表拆分（5.80 的长期修复，约 0.5 天）
把第 55 条那张轴表拆成 `docs/project/architecture/版本轴登记表.md`，AGENTS 只留入口 + 纪律；拆分后 AGENTS 应 < 60 KB、加载不再截断；同批更新 04 5.80 与 06 记录。**这是后面每次登记新轴不再挤压的前提。**

### 3.5 D 实验加跑（按需，每臂 k≥3）
用 `testing/ab/dgate2/` 的冻结包（评分器组合摘要 `e3ef9e91…`、任务包 v3、hidden runner、run-manifest/run-record），每臂再跑至少 2 次同题 run；跑前 `make_manifest.py --check --strict`，跑后三份 manifest `--strict`。**n=1 只写案例；k≥3 且过预注册决策规则才可写「值得扩试」**（05 §5.5）。

### 3.6 间接执行面裁定（04 5.87 残项）
`tools/**` 经 CI 调用的路径、`.gitattributes` 仍可被写类工具改。先出裁定（是否纳入受保护前缀 / 是否按「规则 + 审批」），再决定是否改注册表（改则重审）。

## 4 纪律（血泪，违反一次就锁死会话）

1. **改 Hook 导入链上的模块后立刻自检**：`src/enforcement/**`、`src/adapters/dsh/**`、`src/policy/**` 每次写入后跑
   `$env:PYTHONPATH="src"; .venv\Scripts\python.exe -c "import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks; print('ok')"`
   exit 0 才做下一步（2026-10-20 因漏一行 import 锁死整台受治会话，靠使用者手工修）。
2. **加键就是改协议**（55）：新增键/取值集合变化必须按该协议自己的轴升版，同批改所有写死版本号的断言/快照/生成物。
3. **改注册表必须重审**（`registry --approve --reviewer dshznm`，单人仓库自审，不假装第三方），再 `registry --verify`。
4. **审批条子只能使用者签**，代理不得自签；D 实验/真实受治会话要条子就说清楚要签什么。
5. **失败关闭**：未知字段/版本/枚举一律拒；"跑不成"不记通过；读数里绝对路径、密钥、时戳该脱敏的脱敏，载荷该逐字节相同的必须相同。
6. **提交**：Conventional Commits；一个任务一个提交；推送前跑门禁（本机 danger-full-access）。
7. **记录**：06 用三态（符合/不符合/跑不成/作废）+ 证据指针；不写均值/百分比/显著；读数不指向 `.tmp`（会被 cleanup 删）。
8. **别删 `.tmp` 下的 ACL 残留目录**（删不掉，且 `cleanup.py` 会报 52 项失败，属已知）。

## 5 命令速查

```powershell
cd C:\Users\ZNM\Downloads\Memory
$env:PYTHONPATH="src"
git log --oneline -5; git status --porcelain          # 起点
.venv\Scripts\python.exe -m pytest tests/unit/test_xxx.py -n0 -q
.venv\Scripts\python.exe -m enforcement.cli registry --verify
.venv\Scripts\python.exe tools/approval_allowlist_audit.py --check --registry registry/tool-registry.yaml --approved registry/tool-registry.approved.json
.venv\Scripts\python.exe tools/ci_local.py              # 需 danger-full-access；约 5–8 分钟
```

## 6 第一次行动建议

1. `git log -1` + `git status`，确认 HEAD 与工作树；
2. 读 04 的 5.80/5.83/5.84/5.86/5.87/5.88 与最新读数（§1）；
3. 从 §3.1（C4 探针）开始；若用户另有指定，按指定优先级。
4. 每完成一项：读数 → 用例 → 04/05/06/07/README 同步 → 提交 → 门禁 → 06 读数行。
