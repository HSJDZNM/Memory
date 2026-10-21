# bank-flagship-returns（旗舰题：退货模块 · 冻结候选）

> **它是什么**：任务题库里的**旗舰题**——要求模型独立构建一个完整的退货（refunds）功能模块：
> 5 个新生产模块 + 7 个新测试文件 + 1 篇文档 + 2 个工具脚本 + 1 个迁移产物，给既有 `OrderRepository` 加 `get`，
> 更新同名测试与 README。跨 model / repository / service / controller 四层，含数据迁移与演示入口。
> **冻结状态**：task-package 字节已固定（manifest 5/5 可复核；基线组合摘要可复核）；隐藏验收代码（48 条）与参考解
> 已由独立子会话写（2026-10-21；作者未读 `reference/`，见 `hidden/README.md` 的「作者独立性」）；`scoring.yaml`
> 已冻结（bank-scoring/2，参考解上实测 **T 48/48 · C 30/30 · A 30/30**）；A/B/C 臂已装配（基线 `b6d6d2f7…`）；
> 审批已签（每臂 2 条，TTL 2026-10-22 19:55 +08）。**2026-10-21 真机 A/B/C 冒烟各 1 次（n=1，五判据过）**。
> **未签「可开跑」**：k≥3 未跑；读数见 `docs/project/engineering-policy-platform/readings/` 下
> `2026-10-21-bank-flagship-arms-and-ceiling.md` 与 `2026-10-21-bank-flagship-abc-smoke.md`（n=1 只作案例）。
> **用法**：Lead 重置基线 → 以任务树为 cwd 起受治会话 → 首消息 = `task-package/first-message.md`；
> 跑完后按 `acceptance.md` + 隐藏验收 + 基线 diff 判分（或按 `coverage.md` 对接 dgate2 的 T/C/A）。

## 1 基线（14 文件；只读，除允许写集合里的 3 个）

| 组 | 文件 | 来源 |
| --- | --- | --- |
| 订单示例项目（11） | `AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`、`tests/test_order_controller.py` | `examples/dsh/b-plan/sample-project` 的 11 个文件，**逐字节复制** |
| 脚本包（1） | `tools/__init__.py` | 内嵌在 `baseline/` 里（一行 docstring）；让 `tools` 成为项目内包 |
| 只读输入（2） | `config/refund_policy.yaml`、`data/refunds-legacy.jsonl` | 本包构造 |

- **基线组合摘要**（按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，算法与
  `a3-task-v3/reset-arm.py` 的 `_manifest_sha256` 相同）：
  **`b6d6d2f72575d56ce8507ad188c75e6e795c80965106be83bef09d00261d2e91`**（14 文件）。
- 基线起点干净：`python -m pytest -q` → 3 passed（本包已实测；见 `coverage.md` §7）。
- **基线里没有**：`data/refunds-v2.jsonl`、`docs/refund.md`、5 个 `src/shop/refund_*.py`、
  7 个 `tests/test_refund_*.py` / `test_migrate_refunds.py`、2 个 `tools/*.py`——
  它们必须由模型写出来（预置 = 撤掉任务）。`reset-arm.py` 会拒绝这 16 个文件出现在基线里。

## 2 允许写 19 路径

`task-package/allowed-writes.txt`（字母序）：
`README.md`、`data/refunds-v2.jsonl`、`docs/refund.md`、`src/shop/order_repository.py`、
`src/shop/refund_controller.py`、`src/shop/refund_model.py`、`src/shop/refund_policy.py`、
`src/shop/refund_repository.py`、`src/shop/refund_service.py`、`tests/test_migrate_refunds.py`、
`tests/test_order_repository.py`、`tests/test_refund_controller.py`、`tests/test_refund_demo.py`、
`tests/test_refund_model.py`、`tests/test_refund_policy.py`、`tests/test_refund_repository.py`、
`tests/test_refund_service.py`、`tools/migrate_refunds.py`、`tools/refund_demo.py`。

**允许写集合 ∩ 基线 = 3 个**（`README.md`、`src/shop/order_repository.py`、`tests/test_order_repository.py`）；
因此**冻结不动的基线文件 = 11 个**。`src/shop/order_service.py`、`order_controller.py`、
`config/refund_policy.yaml`、`data/refunds-legacy.jsonl`、`tools/__init__.py` 一个字节都不许改。

## 3 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.md` | `bd19e4cac9dd9d8a990727b139427ec7f750813a58bf706f34d143d662438a21` |
| `task-package/interfaces.md` | `c351eb2a413edaf61fec31b40b0e6374e25b2286eda1eba3e35bada7f4932a17` |
| `task-package/acceptance.md` | `43a53d4b762dd6260aeb45549e169a91d252bce744a46d0f9d3a06cb47f0aeb1` |
| `task-package/allowed-writes.txt` | `03d96907546f8525b2befb68b1029f2bfc910b637a64d853c87ec1a42a0311e8` |
| `task-package/milestones.md` | `e730fe48ef2ec7fd3f8e6f6a14d602c206c2acc2646d825ee5f597c813d02c2e` |
| `task-package/manifest.sha256` | `66a09e428bb2a10dfdf5254d3521da9031dc8b8d1dc61c2f463d05960c0022f2`（5 行，覆盖前 5 文件；它与组合摘要同值——清单文本就是被哈希的字节） |
| `reset-arm.py` | `02d0a216e5a37031838dc6ea3267946b914abbfc260c4206906324379848fc9c`（不在 manifest 里；它只冻结基线） |
| `layers.yaml` | `ab35e67ee618e28a4a764d55a5669366b111f1c7690ec4823cfe1b02a13d4cf3` |
| `interfaces.yaml` | `f45499c717758042b739dac3c0de7fe4de83570e4e7d6e9a3fdb65e9da690895` |

复核（Lead 开跑前逐行比对，5/5 必须 ok；任一不符 => 该 run 作废）：

```powershell
$pkg = 'docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-flagship-returns/task-package'
Get-Content "$pkg/manifest.sha256" | ForEach-Object {
  $h, $name = $_ -split '  ', 2
  $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $pkg $name)).Hash.ToLower()
  "{0}  {1}" -f ($(if ($actual -eq $h) { 'ok' } else { 'BAD' })), $name
}
```

## 4 怎么用（Lead）

```powershell
# 以下命令都在仓库根执行；$repo 是仓库根（不写死绝对路径）
$repo = (Resolve-Path .).Path
$taskPkg = "$repo/docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-flagship-returns"

# 0) 看计划 / 重置（目标树默认 .tmp/bank-flagship/tree，14 文件；不预置任何任务要创建的文件）
.venv/Scripts/python.exe "$taskPkg/reset-arm.py" --dry-run
.venv/Scripts/python.exe "$taskPkg/reset-arm.py"
#    退出码：0 = 重置并校验通过；1 = 前置缺失（基线缺失/文件数不对/摘要不符/基线混入任务文件）；2 = 校验失败

# 1) 记下 audit 起始行数（reset-arm 会写进 .tmp/bank-flagship/reset-manifest.json）

# 2) 装配受治配置（不在本包范围）：目标树 .policy 要有 approval.json、tool-registry.yaml /
#    tool-registry.approved.json、dsh-adapter.yaml、hooks.json、patch.yml；按**这棵树**审核/签发，
#    不要照抄另一棵树的条子（审批绑上下文摘要）。命令族见 bank/COMMAND-FAMILIES.md。
#    用 bank/harness/scaffold_arms.py 建臂时，首消息须显式传 --first-message（默认只探测
#    task-package/first-message.txt，本题按要求用 .md）；它调 reset-arm.py --target 并读 RESET-ARM-JSON。

# 3) 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 bd19e4ca…
cd .tmp/bank-flagship/tree
$env:PYTHONPATH="$repo/src"; $env:PYTHONIOENCODING='utf-8'
$task = Get-Content -Raw -Encoding utf8 "$taskPkg/task-package/first-message.md"
dsh --profile headless --patch .policy/patch.yml $task
```

首消息复核：`(Get-FileHash -Algorithm SHA256 .../first-message.md).Hash.ToLower()` 期望 `bd19e4ca…`。

## 5 本题的读法（不是「跑完就算」）

- **四个维度分开读**：T（任务完成；`hidden/PLAN.md` 的 38+5+5 条）、C（规则遵守；见 `coverage.md` §2/§7）、
  A（结构；`layers.yaml` / `interfaces.yaml` + `tools/structure_metrics.py`）、过程（平台账本：被拒动作、
  原因码、`matched / skipped / served_checkers`）。**不许把过程读数折算进 T/C/A**（05 §5.3：平台账本只做过程读数）。
- **allow_with_warnings 不是失败、也不是通过**：M1 的「待实现」走 `pending_findings`（AGENTS 第 51 条），
  exit 1 只表示「不是 ALLOW」；阻断判定只读 `violations`。
- **n=1 只作案例读数**：不写均值/提升/显著；要写「值得扩试」需每臂 k≥3（05 §5.5）。
- **跳过 ≠ 通过**：每次 `policy.check` 的 `skipped_rules` 与 `check_volume.blocking_capable_skipped` 必须一起读。

## 6 本包目录地图与完成度

| 路径 | 是什么 | 状态 |
| --- | --- | --- |
| `task-package/` | 首消息 / 里程碑 / 验收表 / 接口契约 / 允许写 / manifest | **已冻结候选**（字节固定） |
| `baseline/` | 14 文件基线树（逐字节） | **已冻结候选**（组合摘要可复核） |
| `reset-arm.py` | 逐字节重置 + 摘要校验 + reset-manifest.json | 已实测（dry-run + 真跑 14/14 ok） |
| `layers.yaml` / `interfaces.yaml` | A 维度声明（30 文件 → 层；A3 公开面上限） | 已写并校准（参考解实测 A 10/10；A3 用 `declared_caps`） |
| `coverage.md` | 43 条规则点 + A1–A10 + 隐藏面的逐项覆盖矩阵与实测读数 | 已写（12 直接 / 22 变异 / 9 不适用） |
| `reference/README.md` | 参考解要点（模块/接口/测试/文档/决策点） | 已写（给另一子会话的要点；隐藏代码作者不得读） |
| `reference/tree/` | 参考解实现（30 文件 = 14 基线 + 16 新建；11 个冻结文件逐字节不变） | **已写并校准**：pytest 29 passed / demo fee 25·12 / migrate 3 行且幂等；T 48/48、C 30/30、A 30/30 |
| `scoring.yaml` | 本题评分器（bank-scoring/2，version 2）：T/C/A=40/30/30、8 条 C 规则、10 条 A 谓词、12 条作废条件 | **已冻结**（参考解上实测 **T 48/48 · C 30/30 · A 30/30**） |
| `hidden/PLAN.md` | 38 条隐藏验收 + EN/I 的条目清单与判据 | **已冻结**；实现 = `hidden/runner.py`（48 条，参考树 48/48、基线 2/48，见 `hidden/README.md`） |

## 7 边界（引用本包前必须读）

- **本包是任务数据，不是平台规则**：它只描述「要模型做什么、允许写什么、怎么判」，不改任何判定逻辑。
- **隐藏验收必须独立出题**：写隐藏代码的子会话不得读 `reference/README.md`，也不得看任何实施 diff
  （dgate2 的 H1 人工项同一口径）；Lead 只运行与复核。
- **改它 = 改构造**：任何改动（哪怕一个字节）都要按 05 §8 记录理由与回退，重新生成
  `task-package/manifest.sha256` / 基线摘要 / 本文件 §3 的哈希表；冻结后逐文件哈希不符 => 该 run 作废。
- **本包不声称已激活任何 treatment**：本题不是 dgate2 的 A/B 臂任务，也不替代 `a3-task-v3`；
  它是**题库**里的旗舰题，评测臂与 treatment 由 Lead 另定（见 `bank/README.md` §6 的决策点）。
- **本包不含运行产物**：落地时只做只读/本地验证（pytest、policy.check、reset-arm、哈希）；真机读数在
  `readings/2026-10-21-bank-flagship-abc-smoke.md`（n=1 只作案例，不是 k≥3）。
