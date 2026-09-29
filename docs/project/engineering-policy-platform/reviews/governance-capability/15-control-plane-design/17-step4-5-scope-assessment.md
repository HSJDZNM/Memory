# 17 · §3.6 前置评估：台阶 4–5 的两份整数清单与逐条结论

- **执行**：2026-09-29（本机）；控制面重构会话（**唯一写者**）。
- **依据**：方案 **§3.6**（台阶 4–5 的前置评估）与 **D-2 冻结**（先交清单，清单交出即停）；
  本文是**评估**，不是排期、更不是开工单。
- **来源树**：分支 `refactor/control-plane`，读数采集于 `f60f633`（台阶 3c 之后）；
  每条读数的来源逐条写在表里。
- **口径**：
  1. **只用整数，不用比例**（方案 §3.5 禁止比例）；
  2. **对象** = 某件东西要**服务**的对象（被检查的对象 / 被报告的对象），不是"代码里有什么"；
  3. 结论只有两个取值：**建机制** / **写声明**；两者都不做时写 **不做**；
  4. 每条结论必须回答 §3.6 的那句判据：**"让一个已声明 `out_of_scope` 的对象不再红"不是建机制的理由**。

---

## 1 判据（方案 §3.6 原文的三句，逐字引用）

1. **前置问题**：这一步要建的东西，服务对象里**已声明 `out_of_scope` 的有几个、在范围内的有几个**，
   两份清单都列出来；
2. **判据**：若某条检查的全部用途是「让一个已声明 `out_of_scope` 的对象不再红」，
   它属于收缩承诺面的工作，**不该建机制**（写一条声明即可）；只有当对象**在范围内**时，检查才有资格建；
3. **可证伪**：若评估结论是「全部该建」，必须交出「这些对象都在范围内」的清单；交不出，
   就必须有一部分降级为声明。

---

## 2 台阶 4 · 覆盖账与仪器自证

### 2.1 清单甲：**已经声明「不治理」的对象**（整数 = **2**）

| # | 对象 | 取值 | 来源（可复核） |
| --- | --- | --- | --- |
| 1 | `desktop-entry-points`（桌面 GUI 的 profile 装不装策略桥） | `decision=out_of_scope`、`kind=agent_runtime`、`owner=host`、`expires_at=2026-12-31`、`renewals=[]` | `adapters/wiring-scope.yaml:22-34` |
| 2 | `ci-agent-runtime`（CI 机器上按设计没有 Agent 运行时） | `decision=expected_absent`、`owner=ci`、`expires_at=2026-12-31`、`renewals=[]` | `adapters/wiring-scope.yaml:36-46` |

**另有一条同类决定还没有数据载体**：`.github/workflows/phase-8.yml` 里那句
"平台治理受控会话、不治理使用者日常入口"（方案 §3.5 点名的"H4 边界裁定"）——它今天只活在**注释**里，
没有被上面这份声明收录。**这一条是"写声明"的候选**（见 §2.3 第 9 条）。

### 2.2 清单乙：**在范围内**的对象（4 组）

| 组 | 对象 | 取值（整数 + 明细） | 来源 |
| --- | --- | --- | --- |
| B1 **平台自己的接线面** | `adapters.cli wiring` 发现的通道 | **12 个**，全部 `kind=dsh-profile`：`wired 7`（governed / governed-grade / governed-grade-approval / governed-wmsvc / verify-bc / verify-gov / verify-manual）、`not_wired 4`（desktop / headless / verify-dead / web）、`hooks_config_missing 1`（verify-exit2）；报告自带 `counts={total:12, wired:6, failed:6}`、`fact_counts={wiring_ok:7, freshness_ok:6}` | 本次实跑 `python -m adapters.cli wiring --json` |
| B2 **仓库自己的门禁步骤** | `tools/ci_local.py` 的步骤表 | **会跑 33 条** + 本机跳过 13 条（`bash-only`，CI 上执行）；`--list` 同时报"改动文件 795 个" | 本次实跑 `python tools/ci_local.py --list` |
| B3 **仪器自证的对象** | 探针与闭环里的每条检查 | `tools/governance_gap_probe.py` **G01–G13 = 13 条**；`tools/provenance_loop.py` **5 个封条场景**（tools/README 的口径）；台阶 3c 新增 `tools/obligations_gate.py`（**1 个 warn 期实例**） | `tools/README.md` + 本次实跑 |
| B4 **写者 / 会话** | 本工作树、`.tmp/ci-local.lock`、轮次命名空间 | 台阶 −2 已有：每会话一棵树 + 一把锁（W1/W3/W7 三条现场事件的服务对象） | 方案 §4 台阶 −2 与 AGENTS"工作方式"第 5 条 |

**注意 B1 里的分档**：`dsh:desktop` 正对应清单甲第 1 条（已声明不治理）；
其余 11 条**没有**任何声明覆盖 —— 其中 `dsh:web` / `dsh:headless` /
`dsh:verify-dead` 三条是**未声明的通道**（既不在范围内、也不在清单甲里）。

### 2.3 逐条结论（台阶 4 要建的 8 件东西）

| # | 要建的东西 | 服务对象（在范围 / 已声明不治理） | 结论 | 理由（一句话） |
| --- | --- | --- | --- | --- |
| 1 | `governs` 轴（按 `kind` 分档 + "有意治理另一棵树"的声明位） | 12 个通道（其中 1 个已被声明不治理） | **建机制** | 分档正是为了不把已声明不治理的那 1 个算成缺口；没有它，`dsh:desktop` 会让账永远红 |
| 2 | `reading_context` | 所有报告的读者（人 + 评审） | **建机制（薄）** | "这份读数属于哪棵树 / 哪个环境"必须与读数同时出现；针脚里的树摘要在台阶 0 已可用 |
| 3 | 声明差集（三数 + 五个差集） | 12 个通道 vs 3 条声明 | **建机制** | 反方判决条件（方案 §B.3）要求 `in_scope_not_wired` 是**红条件**；本次实跑 `account@@ / `differences` **都读不到**（`null`） |
| 4 | 退出码语义（0/1/2/3 表） | 所有新检查 | **写声明** | 方案 §5.3 已经给了表；落地形态是把它写进 `tools/README.md` 与门禁步骤表，不需要机制 |
| 5 | 豁免到期与续期 | 2 条已声明不治理（`expires_at=2026-12-31`） | **建机制（小）** | 到期必须变红：否则"不在范围内"就是一张永不过期的空白支票（R-b 的 `relaxed_by + expires_at`） |
| 6 | 会话窗口 | 会话内的写者 | **写声明** | 台阶 −2 的"每会话一棵树 + 一把锁"已经是它的服务对象；再建一层窗口是重复机制 |
| 7 | 仪器自证（R-h 三态皆红） | 33 条门禁步骤 + 13 条探针检查 + 5 个封条场景 | **建机制** | 对象的**全部**都在范围内（它们是平台自己的仪器），且"无 mutation_id 又无 gap_note → 红"这条要求本身要能被守住（J5） |
| 8 | 写权租约 | 并发写者（W1/W7） | **写声明** | 单写者 + 每会话一棵树 + `.tmp/ci-local.lock` 已覆盖；新租约机制没有服务对象 |
| 9 | **（清单甲/乙的补口）** 给 3 条未声明通道（`dsh:web` / `dsh:headless` / `dsh:verify-dead`）定性 | 3 条通道 | **写声明** | 它们的"红"全部来自"未被声明"，而不是"该接没接"；按判据，这是收缩承诺面的工作 |
| 10 | **（同上）** 把 CI 注释里的边界裁定收进数据 | 1 条决定（使用者日常入口） | **写声明** | 方案 §3.5 明说"把已经做出但只写在 CI 注释里的决定提升为顶层契约"——载体是 `adapters/wiring-scope.yaml`，不是新机制 |

### 2.4 这一步的整数结论

- **已声明不治理：2 条**（+1 条只写在 CI 注释里，待收进数据）；
- **在范围内：4 组**（12 个通道 / 33 条门禁步骤 / 18 条仪器检查 / 3 类写者对象）；
- **结论分布：建机制 5 件、写声明 5 件**（第 9、10 条是清单驱动的补口）。
  因此**不是"全部该建"** —— §3.6 第 3 条的可证伪要求当场满足。

---

## 3 台阶 5 · 控制面事实表与跨源互证

### 3.1 清单甲：**已声明「不治理」的对象**（整数 = **2**；本台阶**不新增**）

与 §2.1 **同一份声明**（`adapters/wiring-scope.yaml` 的 `desktop-entry-points` 与
`ci-agent-runtime`）。下面要互证的三组对象**没有一条**落在"已声明不治理"里 ——
这决定了它们的结论只能落在"建机制"或"只报告"两格，**不能**用"写一条不治理声明"逃掉。

### 3.2 清单乙：**在范围内**的对象（3 组互证 + 表本身）

| 组 | 对象 | 取值（整数 + 明细） | 来源 |
| --- | --- | --- | --- |
| C1 **测试路径的两份声明** | 平台级 `test_patterns`（2 条）与 Adapter 级 `test_paths`（1 条） | `tests/**/test_*.py`、`tests/**/*_test.py` vs `tests/**/*.py`；**184 个 `tests/**/*.py` 里 101 个两条路径判定不一致**（方向全是 `platform=False / adapter=True`，0 条反向）；另一个声明所在（`adapters/*/adapter.yaml` **3 个配置全都没有**声明 `test_paths`） | `validation/test-layout.yaml:21-23`、`examples/dsh/dsh-adapter.yaml:22-24`、归档 03 号（可重算） |
| C2 **工具表 / 检查器三处声明** | 注册表 / manifest / 代码工具表 | 注册表 **10 个**工具（`registry/tool-registry.yaml` 的 `tools`：fs.edit、fs.write、fs.read、exec.pwsh、exec.bash、exec.run_code、orc.fs.edit、orc.fs.write、orc.policy.write、orc.policy.edit）；manifest **38 / 6 / 1**（dsh / generic-json / legacy-post-only）；代码 `TOOL_TABLE`（dsh）**38**；已审核哈希 **3 个 adapter**（`adapters/approved.json` 的 `adapters` 键）+ 注册表已审核 **10 个**工具 | 本次实跑 + `registry/`、`adapters/` |
| C3 **预算不等式** | 两套结论 | 仓库实例：`examples/dsh/hooks.json` 的 `timeout=30s` vs `examples/dsh/dsh-adapter.yaml` 的 `timeout_ms=5000`（该配置**没有**声明 `pre_evidence`）；.tmp 实例（台阶 3c 的 A 项目）：`timeout=120s` vs `pre_evidence.timeout_ms 60000 + timeout_ms 5000` | 本次实跑 |
| C4 **host-version 声明 vs 观测记录** | 1 个 manifest 声明 `host_version`（dsh）+ 1 条观测 | `agent_version=0.1.6-alpha.2`；`adapters/host-versions.observed.json` 的 `entries` **= 1** | `adapters/dsh/manifest.yaml`、`adapters/host-versions.observed.json` |
| C5 **事实表 / 检查表本身** | `validation/control-plane.yaml`（facts 9 字段 + checks 8 字段 + 连接键双向必查） | **今天不存在**；本次实跑 `adapters.cli wiring` 的 `account@@ 与 `differences` 都是 `null` | 方案 §3.2；本次实跑 |

### 3.3 逐条结论（台阶 5 要建的 6 件东西）

| # | 要建的东西 | 服务对象（在范围 / 已声明不治理） | 结论 | 理由 |
| --- | --- | --- | --- | --- |
| 1 | facts 表（9 字段，只放指针不放值） | C1–C4 的事实 + 版本轴一族 | **建机制（先只报告）** | 事实的**载体**全是平台自己的声明，全部在范围内；"配置写错就起不来"的风险由 L5 闸吸收（先 warn 跑一轮） |
| 2 | checks 表（8 字段，`last_run` / `status` 一律加载期报错） | 33 条门禁步骤 + 18 条仪器检查 | **建机制（先只报告）** | 同上；"只放指针"这条纪律把"表变成第二份真相"的口子堵住 |
| 3 | 连接键 `facts.key ↔ checks.covers` 双向必查 | 上面两张表 | **建机制** | 没有它，两张表就是各说各话；悬空即红是这张表唯一的存在理由 |
| 4 | 合并谓词（一份实现、两个调用点） | C1 的 101 个不一致 | **建机制** | 101 是**在范围内**的真实缺口（同一个测试文件在 Hook 路径与验证器路径上得到两个层）；写声明修不了它 |
| 5 | 跨源互证（分组） | C1 / C2 / C3 | **C1 建机制、C2 只报告、C3 建机制** | C1：101 个不一致且在范围内；C2：38 ↔ 38 的对齐**已经**由契约测试守住（`test_validator_protocol` 一族），剩下的是 registry ↔ manifest 的**覆盖关系**，先只报告更合适；C3：两套结论都要给（方案判据原文） |
| 6 | L5 上线闸 | 任何**新的加载期 FATAL** | **写声明** | 它已经写在方案 §4 台阶 5 里；落地形态是"新 FATAL 一律先 warn + 非零退出跑一轮"，是纪律不是机制 |
| 7 | **（C4 的处置）** host-version 两端一致 | 1 个 manifest + 1 条观测 | **写声明** | AGENTS 第 54 条已经给了四种形态与门禁步骤；事实表只需要**登记指针**，不重复建机制 |

### 3.4 这一步的整数结论

- **已声明不治理：2 条**（与台阶 4 同一份声明；本台阶不新增）；
- **在范围内：5 组**（测试路径 2 份声明 / 工具表 3 处 / 预算 2 套 / host-version 2 端 / 表本身 2 张）；
- **结论分布：建机制 4 件、只报告 1 件、写声明 2 件**。同样**不是"全部该建"**。

---

## 4 可证伪自检（§3.6 第 3 条）

| 台阶 | 要建的东西 | 建机制 | 写声明 | 只报告 |
| --- | --- | --- | --- | --- |
| 4 | 10 件（含清单驱动的两条补口） | 5 | 5 | 0 |
| 5 | 7 件（含 C4 的处置） | 4 | 2 | 1 |

**两条清单都交出来了**（清单甲：2 条已声明不治理；清单乙：4 组 + 5 组在范围内），
且结论**不是**"全部该建" —— 按 §3.6 第 3 条，这一步**不需要**再交出"这些对象都在范围内"的
额外证明，因为已经有一部分被降级为声明。

**一条必须一起交出去的观察**：台阶 4 的清单乙里有 **3 条未声明的通道**
（`dsh:web` / `dsh:headless` / `dsh:verify-dead`）。
它们今天的红**不来自"该接没接"**，而来自"没人声明过它们算什么"。按判据，处置是**写声明**；
但"写声明"这个动作正是 D-2 冻结**明确禁止**的（"评审通过之前不建任何机制（含『写一条声明』
这类收缩动作）"）。所以本文件**只列出来，不动手**。

---

## 5 冻结与不做（D-2）

- 本文件**只交清单**：没有新建 `validation/control-plane.yaml`、没有改
  `adapters/wiring-scope.yaml`、没有给任何检查加退出码；
- **不排期**：台阶 4–5 的具体落地顺序与预算不在本文范围内；
- **不动**"写声明"这类收缩动作（D-2 原文）；
- 台阶 0–3 的既有结论不受本文件影响（§3.6 的边界：收缩承诺面修不了 H4 假绿、归因指错对象）。

---

## 6 未核实（逐条）

1. **12 个通道的定性只查了两处**：`adapters/wiring-scope.yaml` 与
   `.github/workflows/phase-8.yml` 的注释；没有逐通道去问"它是不是其实在别处被声明过"。
2. **101 的口径依赖**：把 `**/` 解释成"至少一段目录"会得到 97（归档 03 号 §3 已写明）；
   本文引用的是与平台匹配语义一致的 101。
3. **C2 只数了数**：registry 的 10 个工具与 manifest 的 38 个工具之间的**交集**没有逐项比对
   （结论表里的"覆盖关系"因此是**未逐项核实**的）。
4. **C3 的"两套结论"里，仓库内实例只有 1 个**（`examples/`）；另一套来自台阶 3c 的 .tmp 实例，
   不是仓库内的第二处声明。
5. **B2 的 33 条**是`"会跑"`的条数；本机跳过 13 条（`bash-only`）并不等于 CI 上的条数
   （CI 上那 13 条会执行）。

---

## 7 复现命令（只读）

```powershell
# B1：发现的通道（12 个）与它们的接线 / 新鲜度事实
.venv\Scripts\python.exe -m adapters.cli wiring --json      # 需要 PYTHONPATH=src

# B2：门禁步骤表（会跑 33 / 本机跳过 13）
.venv\Scripts\python.exe tools\ci_local.py --list

# 清单甲：已声明不治理的两条
.venv\Scripts\python.exe -m provenance.cli wiring-scope --check

# C1：两份测试路径声明（101 的口径与全部清单）
#   见 03-test-paths-disagreement.md §3/§4（可重算，两份声明都在 tracked 树里）

# C3：预算不等式的仓库实例
#   examples/dsh/hooks.json 的 timeout 与 examples/dsh/dsh-adapter.yaml 的 timeout_ms
```
