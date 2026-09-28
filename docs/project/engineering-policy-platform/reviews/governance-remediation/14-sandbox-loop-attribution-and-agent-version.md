# 修复轮 14：沙箱闭环的归因分类 + 适配器声明版本与宿主的比对（2026-09-27）

> 输入是 [08 多规则开发轮 2](../governance-capability/08-multirule-dev-round-two.md) 之后由本机实测点名的两条小缺陷：
> (1) `tools/dsh_sandbox_loop.py` 把「dsh 起不来」的原因**归错类**；(2) 适配器声明的 `agent_version` 与这台机器上真正装着的宿主版本**从没有任何比对**。
> 两条都由子会话执行（task-4 / task-5），第三条子会话做独立验收（task-6），Lead 负责端到端复核与全量门禁。

> **先读这段**：本文是 2026-09-27 的**冻结记录**。修完的只是这两条；本轮**新登记的三条**（Q6–Q8）写在 §5，没有被修。

## 0. 一句话

**两条缺陷都修好了，而且都用先红后绿证明**：缺陷 1 的旧判据会把**两种完全不同的原因**说成同一句话
（真机证据：两条不同日志产出的 reason 字符串 sha256 前 16 位**逐字节相同** `adb76c98428b5903`）；
缺陷 2 的漂移此前**完全静默**（一致性套件 87 项、events、matrix 全绿），现在有了会红的检查 `adapters.cli host-version --check`，并已接进门禁。

**但这一轮最大的收获不是这两条**：为了复核 `projectDir` 指向的项目被删掉之后会发生什么，本轮第一次拿到了
**插件把失败归错原因**的活体证据——「误导性报错」不再是从代码推断，而是真实会话里 10 次工具调用全被拒 + 模型自己写下的困惑（§5 Q6）。

## 1. 本轮的范围与分工

| 条目 | 现状 | 判据 |
| --- | --- | --- |
| 缺陷 1 `dsh_could_not_start()` 归因过宽 | **已修** | 按**被拒路径**分类；归不了因时**不产生环境跳过** |
| 缺陷 2 声明版本 vs 宿主版本 | **已修** | 新子命令 `host-version`，四状态互不折叠，且**不做运行期拦截** |
| 治理通道是否被改坏 | **没坏** | 修复后的真实受治理会话：五类 checker 参与、事前事后 57/57 成对、3 次 block |

三条子会话的写域互不重叠（上一轮学到的教训）：

| 任务 | 负责 | 写域 |
| --- | --- | --- |
| task-4 缺陷 1 | `fix-loop` | `tools/dsh_sandbox_loop.py`、`tests/integration/test_dsh_sandbox_loop.py`、`.tmp/round-10/a/` |
| task-5 缺陷 2 | `fix-version` | `src/adapters/`、`adapters/`、`tests/unit/`、`tests/contract/`、`.tmp/round-10/b/` |
| task-6 独立验收 | `verify-fixes` | `.tmp/round-10/c/`（仓库源码只读） |

## 2. 缺陷 1：把「dsh 起不来」的原因归错类

### 2.1 修前：两种原因，同一句话

旧判据是**两个 token 集的合取**：整篇日志里出现 `EPERM/EACCES/WinError 5` **且**出现 `profiles/cordis/.dsh/dsh-home` 任一 token → 判成「写 `$DSH_HOME` 下 profile 被拒」。

真机日志（`.tmp/phase-2-sandbox/logs/block-run.txt`）里那段文本**同时**含着两种路径，但它们出现在**不同的角色**上：

```text
# 配置里声明过的插件路径（栈帧，不是被拒的东西）
at file:///C:/Users/ZNM/Downloads/Memory/.tmp/round-09/dsh-home/profiles/headless/#spill-local
# 真正被 OS 拒绝的路径
Error: EPERM: operation not permitted, mkdtemp 'C:\Users\ZNM\AppData\Local\Temp\dsh-spill-XXXXXX'
```

于是被拒的路径被配置里提到过的路径顶替了。独立验收给出了最硬的一条证据：

> 修前，「真因 = profile 写不进去」与「真因 = 系统 temp 的 `mkdtemp` 被拒」两条日志，
> 产出的 reason 字符串**逐字节相同**（sha256 前 16 位 `adb76c98428b5903`），且都断言「不允许写 `$DSH_HOME` 下 profiles」——
> 而后者恰好**没有**把真正的被拒路径写出来。

### 2.2 修后：按被拒路径分类，归不了因就不跳过

```text
落在 $DSH_HOME（或日志自曝的 <root>/profiles）        → dsh_startup_denied_kind=profile_write_denied
落在 dsh 启动临时区（temp 根 / dsh- scratch）且有启动崩溃原文 → other_path_denied
其余一律 None                                        → 不产生环境跳过，这条闭环按 fail 收场
```

新增诊断字段：`dsh_startup_denied_kind` / `dsh_startup_denied_path` / `dsh_startup_denied_paths` / `dsh_startup_denied_syscall` / `dsh_startup_denied_home_roots`；
`result` 仍为 `skipped`、`--require-dsh` 仍退出 1、**skip 绝不记 pass**（都有用例钉住）。

### 2.3 红→绿

| 证据 | 内容 |
| --- | --- |
| `.tmp/round-10/a/red-pytest.txt` | 实现前：模块没有新 API，`EXIT=2` |
| `.tmp/round-10/a/green-pytest.txt` | 实现后：**19 passed**（9 条合成日志判据表 + 整条判定路径驱动，**不依赖 dsh 可执行文件**） |
| `.tmp/round-10/a/attribution-evidence.txt` | 同一批 10 条日志喂修前 HEAD 与修后：真机 temp 日志 修前 `True` → 修后 `other_path_denied`；无关 EPERM 与「启动崩但路径无关」修前被洗成跳过 → 修后保持 fail；`[Errno 13]` 形态修前漏判 → 修后判对 |
| `.tmp/round-10/c/out/version-mutation-final.json`（验收侧） | 独立重算：修前 FAILURES = 2 条（真机 + 合成对抗），修后 0 条 |

### 2.4 与 Lead 前提的一处差异（必须与结论一起读）

Lead 当时的说法是「本机起不来 dsh」。写手实测后更正：**本会话里系统 temp 可写时，`--require-dsh` 是 pass / 退出 0**；
要复现起不来，条件是**系统 temp 不可写**。写手用 `icacls` 造出不可写 temp 才复现出那条失败。
Lead 自己复跑的读数与之一致：清掉旧日志后用默认 `DSH_HOME` 跑 `tools/dsh_sandbox_loop.py --require-dsh` → **pass / 退出 0**（block 场景真被拦、allow 场景真放行）。

**所以这条缺陷的真实表述是**：「在 temp 不可写的那类环境里，它把原因归错了」——而不是「本机永远起不来」。

## 3. 缺陷 2：适配器声明的版本与宿主实际版本从没比对过

### 3.1 修前：一条完全静默的漂移

| 事实 | 读数 |
| --- | --- |
| 宿主实际版本 | `dsh --version` = **0.1.6-alpha.2**（`@deepseek-ai/dsh` 与三个 hook 包同号） |
| 仓库声明 | `adapters/dsh/manifest.yaml` 与 `adapters/approved.json` 都写 **0.1.5-rc.1** |
| 判定载荷里的版本 | 直接取配置值（`src/adapters/dsh/adapter.py`），与宿主无关 |
| 契约测试的断言 | 断的是 `tests/conftest.py` 自己写进配置的字面量——**自指断言**，宿主怎么漂都不会红 |
| 修前的门禁 | 一致性套件 87 项 / `events` / `matrix` **全部 exit 0** |

字段语义写着「已实测的 Agent 产品版本」（`adapters/models.py`），而声明与实测早已不一致——**没有任何一条绿灯会因它变色**。

### 3.2 修后：一条显式的比对检查（兼容「读不到」）

形态选了**精确比对**而不是版本区间：字段语义就是「已实测」，区间会让那句话继续不成立；而且预发布版本的先后要靠比较规则，
手写比较器等于新增一个「判错了却报绿」的来源。

```text
python -m adapters.cli host-version [--check] [--require-runtime] [--probe-binary AGENT=PATH]

  dsh               [match]         声明 0.1.6-alpha.2 = 宿主 0.1.6-alpha.2
  generic-json      [not_declared]  没有声明 host_version 读法（合成协议消费者）
  legacy-post-only  [not_declared]  同上
  合计：实际比对 1/3；match 1，drift 0，unavailable 0，not_declared 2
```

| 退出码 | 含义 |
| --- | --- |
| 0 | 报告模式 / 声明与宿主一致；读不到宿主时**也**是 0（既不是通过也不是失败） |
| 1 | `drift`（宿主升了、声明没跟）或 `full` 却没声明读法；`--require-runtime` 下 `unavailable` 也变 1 |
| 2 | 用法错误 |

**关键设计：它不做运行期拦截**（同状态下一致性套件仍 exit 0）。版本不匹配说明「声明没跟上」，
不是「这个动作危险」——把它塞进判定会把正常工作封死，那与「拒绝理由要给出可用替代」的原则相反。

堵住绕过：删掉声明块不会变成空检查——`full` 却没声明读法即失败，且删块会让 manifest 哈希漂移、装配被拒。

### 3.3 红→绿与变异（验收侧独立做的六步）

| 步 | 期望 | 实测 |
| --- | --- | --- |
| GREEN1 | pass / 0 | pass / 0 |
| M1 假版本（未重审） | 红 | exit 2——**红在注册表哈希失配，不是版本检查**（只跑这一步会把既有防线误当成本检查有效） |
| M2 假版本 + 重新审核 | 红 | exit 1 / `result=fail` / `dsh=drift`，理由点名两个版本与修复动作 |
| GREEN2 恢复 | 绿 | pass / 0 |
| M3 宿主读不到 | 既不通过也不失败 | `unavailable` / exit 0；加 `--require-runtime` → exit 1 |

### 3.4 判定路径没被动过（这一条比「测试全绿」更重要）

验收侧把 **11 个 dsh 事件 fixture**（6 个「能判定」 + 5 条拒绝路径）在**修前树与修后树**上各跑一遍：
**整行相同**——含 event / context / decision / violations / matched / skipped 与拒绝原文，`rule_set_identity` 也相同。

## 4. 独立验收（task-6 的四条 + 五条偏差）

| 交付 | 读数 |
| --- | --- |
| 缺陷 1 修前/修后 | 绑定冻结修订（pre `79d33a03fa53` / post `1225EDF1F80C`）；6 用例：修前 FAILURES=[case2 真机, case5 合成对抗]，修后 **none** |
| 缺陷 2 变异 | 六步全过（见 §3.3）；`unavailable` 与 `drift` 不折叠 |
| 判定不变 | 11 fixture 逐字段全等 |
| 端到端（只喂载荷，走生产 Hook CLI） | exit 2 / `policy_block` / 审计 `decision=block, executed=false` / violations **11 条覆盖 5 类**（critical 2 · error 5 · warning 4）/ 目标文件 sha 前后不变 |
| 回归 | 同一 10 文件集 修前 **229 passed** / 修后 **229 passed**；连同写手新增 3 个测试文件共 **277 passed** |

验收者主动报的五条偏差（**这才是独立验收的价值**）：

1. **【主要】** `host-version --check` 当时**没有任何门禁在跑**：workflow 与 `ci_local.py` 都没有它，契约测试只钉「声明了读法 / 结构良好 / 删掉会哈希漂移」，
   **没有一条把真实声明值与本机真实宿主版本比**——宿主再升级仍会全绿，「静默」那半句没被自动关闭。（Lead 已在收口时接进门禁，见 §7）
2. `approved.json` 的 `reviewed_by` 变成写手本人，「重新审核」这一次**不是独立复核**（哈希确实是重算的，验收者复算过）；
3. 修后诊断字段 `dsh_startup_denied_home_roots` 在真机日志下有一条畸形项（POSIX 正则吃进 Windows `file://` URL），不影响判定，是**脏诊断**；
4. Lead 的对照探针用 `json.loads(stdout)` 取判定，但 Hook 阻断时 stdout 按契约**为空**（`hooks.py`），所以它的 `governed_decision` 恒为 `None`——读数口径问题；
5. 验收者自己返工一次：`trees/pre` 里曾混进写手的新测试文件，回头逐项核对确认那棵树仍早于本轮 src 改动、`conftest` 两树逐字节相同，对比才成立。

诚实边界（照抄）：只有 case2 是**真机日志**，case5 是合成对抗；端到端走的是「生产 Hook CLI + 喂载荷」，**不是**真实 dsh Agent 会话；
本次 block 被 `TESTING-001/002`（`tool.pytest` crashed，**修前就存在**）**过度决定**，所以 block 本身不证明那 5 类在拦人，能证明的是 violations 里 5 类都真报了。

## 5. 本轮新显现的问题（Q6–Q8）

### Q6 · 插件在「工作目录不存在」时，报的是「找不到 node.exe」（重要：真实会话里量到的误导）

**怎么撞上的**：Lead 为端到端复核铺受治项目时，``scaffold_full.py`` 在那个时刻把 `projectDir` 写成了 `.tmp/round-10/project`；
随后那个目录没被用到（治理三件套最终落在 `.tmp/round-10/lead/project`），于是 `cordis.patch.yml` 里留了一条**指向已不存在目录**的 `projectDir`。

**症状**：受治理会话在**任何工具调用之前**就全线失败关闭，模型侧原文（两次会话各 10 次调用、逐次一致）：

```text
policy-hook: Hook 无法执行（spawn C:\Program Files\nodejs\node.exe ENOENT），按失败关闭拒绝该工具调用
```

**误导在哪里**：

1. 报的是**可执行文件** `node.exe`，而它**存在且可执行**（Lead 当场实测：spawn 它打印 42 正常）；
2. 真正不存在的是**工作目录**（`projectDir`）——Node 的 spawn 在 cwd 不存在时把这个错归给了可执行文件；
3. 于是模型花了一整轮推理在「Node 没装 / 路径不对」上，并在汇报里写下「需要在环境侧修好 Hook 的 Node 运行时」——**方向被报错带偏**。

**为什么值得单独登记**：G12 那一族说的是「故障即拦住」（这条做到了：失败关闭、文件零落地、审计可读）；
Q6 说的是**再往上一层**：拦住了，但**告诉人一个错的原因**。对一个要靠拒绝理由自证的平台，
「拒绝得对、理由错」和「没拦住」一样要修。

**可见的修复方向**（本轮不做）：插件在把 spawn 错误翻译成理由时，先判定工作目录是否存在，
并把「要启动的东西」与「在哪个目录启动」分开写进理由；回归用例可以直接喂一个不存在的 `projectDir`。

**本轮的实际处置**：重新生成 `.tmp/round-10/dsh-home/profiles/governed-full/cordis.patch.yml`（`projectDir` 指向真实项目）后，同一条任务书跑通（见 §6）。
这是**接线修正**，不是代码修复——Q6 本身仍然成立。

### Q7 · `TESTING-001/002` 与「先写测试」的冲突第三次复现，且这次模型把绕法写进了汇报（重要，与 08 轮 Q1 同源）

修复后的受治理会话（§6）落地 7 个新文件、25 passed，但**有 3 次判定是 block**，全部来自同一处冲突。模型的原文：

> 对 `src/invsvc/audit_repository.py` 的两次提交都被 `TESTING-001@1` 与 `TESTING-002@1`（severity=critical）拦下，原文是「关键验证器不可用，按失败策略阻断：`tool.pytest@1.0` 状态 crashed（退出码 2：`ERROR collecting tests/test_audit_repository.py … ImportError`）」……
> 修正做法是真正补上 `AuditEntry`，并在新模块尚未落地时**把对应测试暂存为可通过的占位**（因为「测试先写」而模块未存在时，收集期 ImportError 会让校验器 exit 2 从而 critical 阻断模块写入），随后逐个落地模块再逐个写回真实断言。

这就是 [08 轮 Q1](../governance-capability/08-multirule-dev-round-two.md) 记的同一个机制，但现在有三点强化：

1. **第三次独立复现**（08 轮 Lead 臂、08 轮 gov-dev 臂、本轮）；
2. 本轮是**修完两条缺陷之后**的会话，说明它与那两条无关，是独立的结构性问题；
3. 第一次看到模型写下的**绕法**：「把测试暂存为可通过的占位」——为了让「生产文件能落地」，它必须先把测试写弱。

**这条的代价不再是「多花几分钟」**：项目自己的约定（先写测试）与平台自己的约束（写生产代码时测试必须已存在）互相拆台，
而被惩罚的正是**正确的开发顺序**，绕过去的办法是**先提交一个不测任何东西的占位**。这是本轮最值得进下一轮的一件事。

### Q8 · `host-version` 的检查「有、但没人跑」（次要，收口时已处置）

验收者实测：修好的检查**没有任何门禁触达**——`.github/workflows/phase-8.yml` 与 `tools/ci_local.py` 都没有它。
等于「修了一条会红的检查，却没有任何地方会为它红」。
Lead 收口时把它接进两处（见 §7）：workflow 新增一步，并加进 `ci_local.py` 的 `CODE_STEPS`。
**这条留一个尾巴**：CI 上没装 dsh 时该步骤读不到宿主版本（退出 0，不是通过也不是失败），所以它在 CI 里更像「本机门禁」；
要让它成为 CI 硬门禁，需要 CI 里也有 dsh，或改成对 fixture 声明做比对——属下一轮的选题。

## 6. 端到端：修完之后的树，治理通道还能不能拦人

Lead 用**修完的树**重新铺一个受控项目（`.tmp/round-10/lead/project`），跑了两次真实受治理会话：

| 会话 | 任务 | 结果 |
| --- | --- | --- |
| 违规载荷（生产 Hook 入口） | 五类违规齐全的一份 `legacy_controller` | **exit 2 / `policy_block`**，命中 ARCH-001@1（error）、DOC-001@1 ×2（warning）、SEC-007@2（error）…；审计 0 → 3 条 |
| 真实受治理开发会话 | 实现「审计日志子系统」（9 个动作、多文件） | **exit 0 / 322.6 s**；新建 7 + 修改 2；会话内 **25 passed** |

开发会话的账本读数：

| 指标 | 实测 |
| --- | --- |
| 审计记录 / Pre / Post | **191 / 76 / 57** |
| 判定分布 | `allow 32` / `allow_with_warnings 2` / **`block 3`** |
| 参与判定的规则数 | `[0, 42, 43]`（跳过 `[0, 1, 43]`） |
| 取证状态 | `collected 37` + `not_applicable 1` |
| 服务的 checker | `missing_docstring 33` / `style_lint 33` / `failing_tests 30` / `missing_tests 30` / `forbidden_dependency 2` |
| 事前事后成对 | **57 / 57，pre_only 0、post_only 0** |
| 事后核对 | `post_validated 18` |

**结论**：这两条修复**没有碰坏治理链路**——五类 checker 仍参与、事前事后仍成对、`block` 仍会发生并留下带违规清单的记录。

## 7. 收口：门禁与文档同步

| 动作 | 内容 |
| --- | --- |
| 门禁接线（Q8） | `.github/workflows/phase-8.yml` 新增步骤 `Agent version vs host version`（`python -m adapters.cli host-version --check`）；`tools/ci_local.py` 的 `CODE_STEPS` 同步加同名步骤 |
| 文档同步 | `tools/README.md` 的沙箱闭环说明改成两类归因（写手报的遗留项）；`examples/dsh/dsh-adapter.yaml` 的 `agent_version` 与 manifest 对齐，并新增契约测试把两者钉死（变异验证：改一处即红） |
| 全量门禁 | `python tools/ci_local.py --full --timings` → **33 步全部通过（rc=0），505.5 秒**；主测试批 **1768 passed / 0 failed / 0 error / 1 skipped**（跳过=本机不能建符号链接）；新步骤 `Agent version vs host version` 在列表里，exit 0（0.56 s） |

**门禁结论的适用边界（N28）**：它只对跑的那一刻的工作树成立；本轮在门禁之后没有再改任何代码类文件。

## 8. 复现

全部命令在仓库根执行；解释器 `C:\Users\ZNM\miniconda3\python.exe`；跑仓库模块前设 `$env:PYTHONPATH='src'`。

```text
# 1) 缺陷 1：判据与新用例（不依赖 dsh 可执行文件）
python -m pytest tests/integration/test_dsh_sandbox_loop.py -q          # 19 passed
python tools/dsh_sandbox_loop.py --require-dsh                          # temp 可写时 pass/0；不可写时 skipped/1 + kind=other_path_denied
python .tmp/round-10/a/attribution_evidence.py                          # 修前/修后 同一批日志的归因对照

# 2) 缺陷 2：声明 vs 宿主
python -m adapters.cli host-version --check                             # 0=match、1=drift、2=用法错误
python -m pytest tests/unit/test_host_version_drift.py tests/contract/test_adapter_version_declaration.py -q
python -m pytest tests/contract/test_dsh_layer_declaration.py -q        # 含新增的「示例与 manifest 同口径」

# 3) 独立验收的四组证据（验收者自己的入口与脚本）
python .tmp/round-10/c/harness/run_matrix.py                            # 缺陷 1：修前/修后 六用例
#   其余见 .tmp/round-10/c/REPORT.md 第 0 节的入口表

# 4) 端到端：修复后的树上的真实受治理会话（必须在不受限 shell 里起，见 N25）
cmd /c .tmp\round-10\lead\run_governed.cmd --label dev-audit-after-fix-3 ^
    --project-dir .tmp\round-10\lead\project ^
    --task-file .tmp\round-10\prompts\dev-audit.txt --timeout 1500

# 5) 全量门禁（串行：同一工作树同时只允许一个 ci_local）
python tools/ci_local.py --full --timings
```

产物（`.tmp/` 内，不提交）：

| 路径 | 内容 |
| --- | --- |
| `.tmp/round-10/a/` | 缺陷 1 的红→绿、归因对照、真实 loop 前后证据 |
| `.tmp/round-10/b/` | 缺陷 2 的红→绿、六步变异、最终全绿 |
| `.tmp/round-10/c/` | 独立验收：四份产物 + REPORT.md + 冻结修订树 |
| `.tmp/round-10/lead/` | Lead 的端到端受控项目、读数与探针 |

## 9. 建议的下一轮

| # | 事项 | 为什么现在不做 |
| --- | --- | --- |
| 1 | **Q7**：让「测试已落地、目标模块还不存在」成为「待实现」状态，而不是 validator crashed | 涉及取证侧状态机与 S1 的检查顺序，是一次显式设计；08 轮已登记为 Q1，本轮第三次复现 |
| 2 | **Q6**：把「工作目录不存在」与「可执行文件不存在」分开报 | 要改插件侧的错误翻译与理由生成，并补一条不存在的 `projectDir` 的回归用例 |
| 3 | Q8 的尾巴：让 `host-version` 在 CI 上也能成为硬门禁（或改成对 fixture 声明比对） | 需要 CI 环境里也有 dsh，或另设一条不依赖宿主的比对 |
| 4 | 修后诊断字段的脏项（`home_roots` 里的畸形路径） | 是诊断字段而非判定字段，随下一次改动顺手收 |
| 5 | `approved.json` 重新审核由写手本人完成一事 | 单人仓库的结构性限制，记在案、不假装解决 |
