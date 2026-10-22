# bank-crossmodule-refactor（跨模块重构 / 废弃 API · 冻结包）

> **它是什么**：题库第 2 题——把数据层旧 API `OrderRepository.insert/listing` 换成 `add/list_all`，
> 把 service / controller / 三个既有测试的调用点改到新名，再留一个**只转发的兼容门面**
> `src/shop/order_api.py`（旧名只允许出现在门面与它的契约测试里），补门面契约测试、`docs/api.md`
> 与 `README.md` 的结构表；行为必须逐项不变。
> **冻结状态**：`task-package/` 5 文件字节已固定（`manifest.sha256` 5/5 可复核）、基线组合摘要可复核、
> `layers.yaml` / `interfaces.yaml` 可被 `tools/structure_metrics.py` 加载、`reset-arm.py` 已实测；
> **hidden + reference + 天花板已完成**：隐藏 33 条（`hidden/PLAN.md` + `hidden/runner.py`）在 14 文件基线上
> 跑红 **4/33**、在参考树 `reference/tree` 上 **33/33**（两次运行 stdout 逐字节相同）；参考树上实测
> **T 33/33 · C 30/30 · A 30/30**、`pytest` 8 passed；`scoring.yaml` 的 T 段已冻结
> （`status: frozen`、`total: 33`、`case_ids` 33 条、两个 hidden 摘要实算）。
> **`frozen_by` = `Lead`（2026-10-22）**：冻结 T/C/A 判据；“可开跑”仍由使用者另签。
> **用法**：Lead 重置基线 → 以任务树为 cwd 起受治会话 → 首消息 = `task-package/first-message.md`；
> 跑完后按 `task-package/acceptance.md` + 隐藏用例 + 树 diff 判分（或按 `coverage.md` 对接 T/C/A）。

## 1 基线（14 文件；只读，除允许写集合里的 7 个）

| 组 | 文件 | 来源 |
| --- | --- | --- |
| 订单示例项目（11） | `AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`、`tests/test_order_controller.py` | 旗舰题 `bank-flagship-returns/baseline` 的同一组 11 文件，**逐字节复制**（该组与 `examples/dsh/b-plan/sample-project` 逐字节相同） |
| 脚本包（1） | `tools/__init__.py` | 同一份旗舰基线逐字节复制 |
| 只读输入（2） | `config/refund_policy.yaml`、`data/refunds-legacy.jsonl` | 同一份旗舰基线逐字节复制（保留它们，避免与旗舰题基线分叉；本题**不读写**这两份输入） |

- **基线组合摘要**（按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，算法与
  `reset-arm.py` 的 `_manifest_sha256` 相同）：**`b6d6d2f72575d56ce8507ad188c75e6e795c80965106be83bef09d00261d2e91`**（14 文件）。
  它与旗舰题基线的组合摘要**同值**——因为相对路径集合与每个字节都相同（本包逐文件复算过，见 §3 的
  `baseline/` 一致性读数）。
- 基线起点干净：`python -m pytest -q` → `3 passed`（本包已实测，读数见 `coverage.md` §7）。
- **基线里没有**：`src/shop/order_api.py`、`tests/test_order_api.py`、`docs/api.md`——它们必须由模型写出来
  （预置 = 撤掉任务）。`reset-arm.py` 会拒绝这 3 个文件出现在基线里（`TASK_CREATED`）。

## 2 允许写 10 路径

`task-package/allowed-writes.txt`（字母序）：
`README.md`、`docs/api.md`、`src/shop/order_api.py`、`src/shop/order_controller.py`、
`src/shop/order_repository.py`、`src/shop/order_service.py`、`tests/test_order_api.py`、
`tests/test_order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`。

- **允许写 ∩ 基线 = 7**（`README.md`、3 个 `src/shop/order_*.py`、3 个 `tests/test_order_*.py`）；因此
  **冻结不动的基线文件 = 7**：`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、
  `tools/__init__.py`、`config/refund_policy.yaml`、`data/refunds-legacy.jsonl`——一个字节都不许改。
- **3 个新建**：`src/shop/order_api.py`、`tests/test_order_api.py`、`docs/api.md`。

## 3 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.md` | `e9800a4652f486fd9de8de653f0207f33fc1892c543bf051f9a6ec33d8a02e89` |
| `task-package/milestones.md` | `917dba827474b9ba888fefd947bc8240479963f83b4c4405e5a0a0de26cac666` |
| `task-package/acceptance.md` | `343643a69ec405674781313bf0d36f2b504c021e6c1ebc73f30422c221b7bd71` |
| `task-package/interfaces.md` | `17976ca3ef507a2ce61be576336ac82b5c1b6da4ec0f9bfdfc1f50b5da289ceb` |
| `task-package/allowed-writes.txt` | `915044e3aa31a14f92fec88f79bb4b696f47567ee498173a2630061160d4af88` |
| `task-package/manifest.sha256` | `4a423d625dfbbb0b2190a20d5c1a22223c540c7021aab4d6349c5db9239b9923`（5 行，覆盖前 5 文件；不含自身） |
| `reset-arm.py` | `2c0e243347a1261b2d8f863e98da633824cc88b3dc64c0eadaeff47d6c9dd0fe`（不在 manifest 里；它只冻结基线） |
| `layers.yaml` | `0947710bf740d009e618ad3059b58432a960c3065933a4c831c0f41f53c2bd81` |
| `interfaces.yaml` | `73132f8e7069591f6009e31dea41c2d18d450a35db8cf24878ea7417e40fc312` |
| `hidden/PLAN.md` | `58ec41328edbd2269462a71ff8c018ae06baa18e8ff55272314fe0918cc721cc` |
| `hidden/runner.py` | `5bd879f544eda7c46166987a7d017b14bc91567c4cfac74022e308f46f0b0c6c` |
| `scoring.yaml` | 由冻结集现场计算（本文件不写自身摘要的自指）；C/A 段可复核，T 段已冻结（`total: 33`） |
| `baseline/`（14 文件组合摘要） | `b6d6d2f72575d56ce8507ad188c75e6e795c80965106be83bef09d00261d2e91` |

复核（Lead 开跑前逐行比对，5/5 必须 ok；任一不符 => 该 run 作废）：

```powershell
$pkg = 'docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-crossmodule-refactor/task-package'
Get-Content "$pkg/manifest.sha256" | ForEach-Object {
  $h, $name = $_ -split '  ', 2
  $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $pkg $name)).Hash.ToLower()
  "{0}  {1}" -f ($(if ($actual -eq $h) { 'ok' } else { 'BAD' })), $name
}
```

## 4 怎么用（Lead）

```powershell
cd <仓库根>
# 0) 看计划 / 重置（目标树默认 .tmp/bank-crossmodule-refactor/tree，14 文件；不预置任务要创建的 3 个文件）
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-crossmodule-refactor/reset-arm.py --dry-run
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-crossmodule-refactor/reset-arm.py
#    退出码：0 = 重置并校验通过；1 = 前置缺失（基线缺失/文件数不对/摘要不符/基线混入任务文件）；
#    2 = 校验失败（载荷写明 mismatches / extra / undeletable）
```

1. 记下 `reset-arm.py` 打印的 `RESET-ARM-JSON:` 行（`.tmp/bank-crossmodule-refactor/reset-manifest.json` 里同一份内容），
   其中 `audit_start_lines` 是 `ab_measure / measure_all` 的 `--start-line`；载荷**不含绝对路径**。
2. 装配受治配置（不在本包范围）：目标树 `.policy` 要有 `approval.json`、`tool-registry.yaml` /
   `tool-registry.approved.json`、`dsh-adapter.yaml`、`hooks.json`、`patch.yml`；按**这棵树**审核/签发，
   不要照抄另一棵树的条子（审批绑上下文摘要）。命令族：本题 `tests` 族两条、`scripts` 族**空**、
   `readonly` 族 `git diff --stat` / `git status --porcelain`（见 `bank/COMMAND-FAMILIES.md` §2）。
3. 用 `bank/harness/scaffold_arms.py` 建臂时，首消息须显式传
   `--first-message <任务包>/task-package/first-message.md`（它默认只探测 `first-message.txt`）；
   它调 `reset-arm.py --target` 并读 `RESET-ARM-JSON:`。
4. 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 `e9800a46…`（见 §3）。

## 5 直接可触发规则点（7 条；证据等级见最后一列）

「触发步骤」写的是这道题里模型**最可能真的做出来**的动作；M 编号对应 `milestones.md`。

| rule_id | checker | severity | 触发步骤（省事/错法） | 期望 decision | 证据等级 |
| --- | --- | --- | --- | --- | --- |
| ARCH-001 | forbidden_dependency | error | M4/M5 让 `order_controller.py` 直接 `import shop.order_repository` 并持有/实例化 repository（「顺手查一下」） | `block`（`ARCH-001@1 error`） | 实测（变异探针 P3） |
| TESTING-001 | missing_tests | error | M6 新建 `src/shop/order_api.py` 而没有同名测试 `tests/test_order_api.py` | `block`（`TESTING-001@1 error`） | 实测（P4） |
| TESTING-002 | failing_tests | error | M2–M7 改了新名而旧调用点没改全（先删旧名、后改调用点）→ 相关测试变红 | `block`（`TESTING-002@1 error`） | 实测（P5） |
| TESTING-002（pending 通道） | failing_tests | warning | M6 先写 `tests/test_order_api.py`、`shop.order_api` 还不存在（项目内模块缺失） | `allow_with_warnings` + `pending_findings`（severity 强制 warning；不进 `violations`） | 实测（P10） |
| DOC-001 | missing_docstring | warning | 门面/新方法漏 docstring（M2/M6） | `allow_with_warnings`（`DOC-001@1 warning`） | 实测（P6） |
| STYLE-001 | style_lint | warning | 把迁移对照表/说明塞进 Python 注释，单行超 100 列 | `allow_with_warnings`（`STYLE-001@1 warning`） | 实测（P9） |
| STYLE-002 | style_lint | error | 替换 import 后留下未使用的旧 import（M7 删门面残留时最容易） | `block`（`STYLE-002@1 error`） | 实测（P7；同批还命中 `STYLE-018` warning） |
| STYLE-018 | style_lint | warning | 门面里把本地 `from shop.order_repository import …` 放在标准库 import 前面 | `allow_with_warnings`（`STYLE-018@1 warning`） | 实测（P8） |

**跳过 ≠ 通过**：`layer=repository` 时 `ARCH-001` 进 `skipped_rules`（`scope_mismatch`）；
每次读数的 `skipped_rules` 与 `check_volume.blocking_capable_skipped` 必须一起读（实测读数见 `coverage.md` §7）。
逐条 ○/— 与理由见 `coverage.md`。

## 6 本题的读法（不是「跑完就算」）

- **四个维度分开读**：T（任务完成；隐藏 33 条已冻结，参考树 33/33、基线 4/33，见 `hidden/PLAN.md`）、
  C（规则遵守；`scoring.yaml` 的 8 条规则 × 8 个被测 .py）、A（结构；`layers.yaml` / `interfaces.yaml` +
  `tools/structure_metrics.py`）、过程（平台账本：被拒动作、原因码、`matched / skipped / served_checkers`）。
  **不许把过程读数折算进 T/C/A**（05 §5.3）。
- **T 已冻结、签字仍未**：`scoring.yaml` 的 `dimension_t.total: 33` 与 `case_ids`（33 条）取自
  `hidden/runner.py` 的实际 id 集合；`frozen_by` = `Lead`（2026-10-22），**不把「冻结 T」写成「可开跑」**。
- **`allow_with_warnings` 不是失败、也不是通过**：M6 的「待实现」走 `pending_findings`（AGENTS 第 51 条），
  `exit 1` 只表示「不是 ALLOW」；阻断判定只读 `violations`。
- **n=1 只作案例读数**：不写均值/提升/显著；要写「值得扩试」需每臂 k≥3（05 §5.5）。

### 6.1 天花板实测（2026-10，本宿主；完整命令见 `reference/README.md` §4）

| 维度 | 读数 |
| --- | --- |
| T（`reference/tree`） | **33 / 33**，runner 退出 0；两次运行 stdout 逐字节相同（sha256 `3a0d46b5e9c0a6ed875ecbbb5a927cd6067b348ebb0ce38c00ca454467e573ba`） |
| T（14 文件基线） | **4 / 33**，runner 退出 1（只有 `T24`/`EN1`/`EN3`/`EN4` 通过）；两次运行 stdout 逐字节相同（sha256 `f32db9c4a011dbab25293e8c5ebe032da1fb5165721c50fb23e04fbba63f2064`） |
| pytest | `8 passed`（基线 3 → 8），退出 0 |
| A | **10 / 10 pass**，`structure_metrics` 1.1 退出 0（A3 = 5 模块 / 12 个公开定义 / 0 越界；A9 = 5/5 生产文件被测试静态 import） |
| C | 8 个被测 `.py` 全部 `allow`、**0 条 violations**（error 0 / warning 0）⇒ **30 / 30**；`effective_total = 30`，`ARCH-001` 只在 `order_controller.py`（layer=controller）上参与判定，其余 7 个文件进 `skipped_rules`（`scope_mismatch`） |

## 7 目录地图与完成度

| 路径 | 是什么 | 状态 |
| --- | --- | --- |
| `task-package/`（5 文件 + `manifest.sha256`） | 首消息 / 里程碑 / 验收表 / 接口契约 / 允许写 / 清单 | **已冻结候选**（5/5 可复核；三处文本逐字一致已实测） |
| `baseline/` | 14 文件基线树（与旗舰基线逐字节相同） | **已冻结候选**（组合摘要 `b6d6d2f7…` 可复核） |
| `reset-arm.py` | 逐字节重置 + 逐文件校验 + `reset-manifest.json` + 无绝对路径载荷 | **已实测**（dry-run + 真跑 14/14 ok） |
| `layers.yaml` / `interfaces.yaml` | A 维度声明（17 文件 → 层；A3 公开面上限） | 已写；**已在基线副本上实测加载**（10/10 谓词 pass） |
| `scoring.yaml` | T/C/A 机读规格 | **C/A 段可复核；T 段已冻结**（`status: frozen`、`total: 33`、`case_ids` 33 条、两个 hidden 摘要；不冒充 Lead 签字） |
| `coverage.md` | 43 条规则点逐条 ○/— + A1–A10 + 隐藏面 + 实测读数 | 已写（7 直接 / 24 变异 / 12 不适用；9 个探针实测） |
| `hidden/PLAN.md` + `hidden/runner.py` | 隐藏验收计划与代码（33 条 = 25 T + 4 EN + 4 I） | **已落盘**（runner 契约同旗舰：`BANK_TASK_TREE` / 唯一 JSON / 0-1-2 / 副本上跑 / 60 秒超时） |
| `reference/tree` + `reference/README.md` | 参考解（10 条允许写）+ 决策点与读数 | **已落盘**（不参与判分） |
| 天花板（T/C/A 实测） | 参考树上跑隐藏 runner / `policy.check` / `structure_metrics` | **已实测**：T 33/33（基线红 4/33）· C 30/30 · A 30/30 · pytest 8 passed |

## 8 边界（引用本包前必须读）

- **本包是任务数据，不是平台规则**：它只描述「要模型做什么、允许写什么、怎么判」，不改任何判定逻辑。
- **隐藏验收的独立性（如实记缺口）**：`bank/README.md` §4.3 要求写隐藏代码的子会话不得读参考解、不得看实施 diff
  （dgate2 H1 同一口径），Lead 只运行与复核。本题的 `hidden/` 与 `reference/` 由**同一个作者子会话**按顺序产出
  （先 PLAN、先 runner，再建参考树；runner 运行时不读 `reference/`，判据只从 `SPEC.md` / `task-package/` /
  `baseline/` / `layers.yaml` / `interfaces.yaml` 推出）——**独立性弱于旗舰题**，这条缺口留在 H1 的 run-record 里，
  不在这里写成「已独立」。`hidden_plan_sha256` / `hidden_runner_sha256` 已实算并写进 `scoring.yaml`。
- **加键即改协议**：本包的两份载荷（`bank-scoring/2` 与 `bank-crossmodule-refactor.reset-arm/1`）各自带版本；
  加键或改语义必须递增并同批改库里其它引用点（AGENTS 第 55 条）。
- **改它 = 改构造**：任何改动（哪怕一个字节）都要按 05 §8 记录理由与回退，重新生成
  `task-package/manifest.sha256` / 基线摘要 / 本文件 §3 的哈希表；冻结后逐文件哈希不符 => 该 run 作废。
- **本包不声称已激活任何 treatment**：本题不是 dgate2 的 A/B 臂任务；评测臂与 treatment 由 Lead 另定。
  `scoring.yaml` 的 `treatment` 段**显式声明 `arms: {}`**（note 写明未声明对比臂）——不虚构 treatment。
