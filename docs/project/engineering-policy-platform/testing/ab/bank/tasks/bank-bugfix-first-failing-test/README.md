# bank-bugfix-first-failing-test（修 bug：先有失败测试 · 冻结候选）

> **它是什么**：任务题库里的「修 bug（先有失败测试）」题——基线树**自带两条会红的回归测试**，
> 模型的活不是写测试，而是**只改实现让它们转绿**（不许削弱测试），再补测试与文档。
> 本题同时是题库里的「**死锁 canary**」：基线自带红测试会让「改一半」的提议持续命中
> `TESTING-002`（真违规），把 04 5.68「多步改动被拆成多次终态判定」压成可读读数
> （`bank/README.md` §6 决策 2；开跑前必须由 Lead 先裁）。
> **冻结状态 = frozen（T 已冻结，Lead 签字仍待）**：`baseline/` 11 文件逐字节落盘、
> `task-package/manifest.sha256` 5/5 可复核、`reset-arm.py` 已实测 11/11；
> **hidden + reference + 天花板已完成**——`hidden/PLAN.md` 38 条 + `hidden/runner.py` 已落盘，
> 参考解 `reference/tree/`（13 文件）已写，参考树上实测 **T 38/38 · C 27/27 · A 10/10（30/30）**
> （读数见 §10）；`scoring.yaml` 的 `dimension_t` 已从 `pending_hidden` 转 `frozen`（total 38、case_ids 38 条），
> `frozen_by` 仍是 `pending_lead_signature`——**只冻结 T 的判据，签「可开跑」仍属 Lead**。
> **用法**：Lead 重置基线 → 以任务树为 cwd 起受治会话 → 首消息 = `task-package/first-message.md`；
> 跑完后按 `acceptance.md` + 隐藏验收 + 基线 diff 判分（或按 `coverage.md` 对接 T/C/A）。

## 1 基线（11 文件；**起点是红的**）

| 组 | 文件 | 来源 |
| --- | --- | --- |
| 订单示例项目（9） | `AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、`tests/test_order_service.py` | `bank-flagship-returns/baseline` 的对应 9 个文件，**逐字节复制**（也就是与 `examples/dsh/b-plan/sample-project` 逐字节相同；本包已逐文件 sha256 断言） |
| 本包构造（2） | `src/shop/order_repository.py`、`tests/test_order_repository.py` | `order_repository.py` = **有 bug 的版本**（`insert` 存入参、返回同一个 dict）；`test_order_repository.py` = 旗舰原用例（逐字保留）+ 追加 `test_listing_returns_copies` |

- **基线组合摘要**（按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，算法与
  `reset-arm.py` 的 `_manifest_sha256` 相同）：
  **`b9bb24d16937783dabfa13b3baddb027cdffad4af32bf0e8610685ac8aa1cafd`**（11 文件）。
- **起点读数**（本包实测，`.tmp/bank-bugfix-first-failing-test/tree`）：
  `python -m pytest -q` → **2 failed, 2 passed**（exit 1）；两条失败正是
  `tests/test_order_repository.py::test_insert_returns_a_copy` 与 `::test_listing_returns_copies`。
  11 文件树实际收集 **4** 条用例（repo 2 + service 1 + controller 1），所以起点读数是
  **2 failed, 2 passed**。SPEC §2 早前写「2 failed, 1 passed」，本轮已按实测修正（见 §7 的偏差记录）；
  基线本身一个字节没动。
- **基线里没有**：`docs/fix-notes.md`、`tests/test_order_service_copy.py`——它们必须由模型写出来
  （预置 = 撤掉任务）；`reset-arm.py` 会拒绝这 2 个文件出现在基线里。

### 1.1 逐文件 sha256（脚本实算，不是手抄）

| 文件 | sha256 |
| --- | --- |
| `AGENTS.md` | `ef20cdca0d6c43dbb5038449c90a972d44837e4b9ddc17e074f994d5eed669a3` |
| `README.md` | `5b4313609e4a28b61b43cd7b58ead2b99866284e532c68b79983cd3698213a5a` |
| `conftest.py` | `edd7cea37c657fb322cdee3038ca9aed35f40c7657a0faacb6640d6de9b050e7` |
| `pytest.ini` | `fd1c0f9fadf99a0af117f9f17fd7276f06d577e80fd530652978a1ff54aa71cc` |
| `src/shop/__init__.py` | `d7eef7b6e4db6622675782550c664ef2ef3c2ff9e8de8845cc0e9f4af4b44ad1` |
| `src/shop/order_controller.py` | `e017c95714e14973bde434902dac0aa33025a73c5b78e4a0a23318f0b3755a6c` |
| `src/shop/order_repository.py` | `035bf0b5e5697e140c9fb17bf6352543d4b81811efc5d4c2ba07d59e139e8afe`（**本包构造，有 bug**） |
| `src/shop/order_service.py` | `080664ff694aad5cb1f50842ae715d72698e40031b97512ddf7328110700fcbe` |
| `tests/test_order_controller.py` | `4ac351e0ce611989044e74f2909c856de1e199e921602ab4fe6a874cecc7d069` |
| `tests/test_order_repository.py` | `da03e49dcda46d1ccb8a053fc3a2815db48b7f0f76a55a2150e20ec2f4e3f668`（**本包构造，2 条红**） |
| `tests/test_order_service.py` | `91fa0e15a1bfaf74827bd11e77dbbef0490841205cd67ab6e4b00056c57aaf5f` |

## 2 允许写 5 路径

`task-package/allowed-writes.txt`（字母序）：`README.md`、`docs/fix-notes.md`、`src/shop/order_repository.py`、
`tests/test_order_repository.py`、`tests/test_order_service_copy.py`。

**允许写集合 ∩ 基线 = 3 个**（`README.md`、`src/shop/order_repository.py`、`tests/test_order_repository.py`）；
因此**冻结不动的基线文件 = 8 个**（`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、
`src/shop/order_controller.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、
`tests/test_order_service.py`）；任务要新建 2 个（`docs/fix-notes.md`、`tests/test_order_service_copy.py`）。
**最终树 = 13 文件**（11 基线 + 2 新建）。

## 3 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.md` | `f61aab33ac89da0388a1fbab91ac189a8b586d5cf3edcb1d78d751e5039e46d9` |
| `task-package/interfaces.md` | `9f4b2a524fa82a718ae80e5202a499a55bee3aea299741f13c4f4332b8cb8967` |
| `task-package/acceptance.md` | `22076cf7101cefc87b9592e0dc9521941d1e91f6831e76b40d50847cb5a1cbf1` |
| `task-package/allowed-writes.txt` | `e3f0a46dc2a7e9c4c55855467f01d8483f751d925059aec26d6389ce5c7baac6` |
| `task-package/milestones.md` | `232c338be83aa9ff18f64701d80a77fac2cf1253837275bf954804ac162aa711` |
| `task-package/manifest.sha256` | `bfacd9454dcbebe9182bc3e87501b85c660d9755eba230a3feb02d5baf9ba508`（5 行，覆盖前 5 文件；它是清单文本的字节，不与组合摘要同值——组合摘要只算基线） |
| `reset-arm.py` | `9b38833871c193e7396d142d66f5efc43ed6c7da4c919130895bdec74bb33082`（不在 manifest 里；它只冻结基线） |
| `layers.yaml` | `ba0691e22fb002d60771eeb78722dca954d45ed45fe2cd757771ecedadfc2d40` |
| `interfaces.yaml` | `c952acfdad95302d9a47937458e60306f4d2e5821b1a94fe9d1c2495b68f20ab` |
| `scoring.yaml` | `aeece54962d3aa193f5cf769960b04f3e6fc4e3230b2f3607b0aed1576313cc1`（本轮冻结 T 后的字节；先前的 pending 版本是 `b18f39ec…`，已被替换） |
| `hidden/PLAN.md` | `b52fd1d84cd66467a39f3f9655af345e2c4fed4912c9ce83f21636fb3d418426`（38 条计划；= `scoring.yaml.frozen_inputs.hidden_plan_sha256`） |
| `hidden/runner.py` | `6e2e05ccc7bb037136379e03b823d09e8a5be93acec861a4db8298039d771895`（= `frozen_inputs.hidden_runner_sha256`） |
| `reference/tree`（13 文件组合摘要） | `12c8430cd37469dd63c4881cb23ee9b82fbf71c949a9bbf622ef191fa12462ee`（算法同基线组合摘要；逐文件表见 `reference/README.md` §1） |
| `coverage.md` | `e8c158e3c1fd858795cd01eea5dcbb8948b35c6a74898590626de41578f3a146` |

复核（Lead 开跑前逐行比对，5/5 必须 ok；任一不符 => 该 run 作废）：

```powershell
$pkg = 'docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-bugfix-first-failing-test/task-package'
Get-Content "$pkg/manifest.sha256" | ForEach-Object {
  $h, $name = $_ -split '  ', 2
  $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $pkg $name)).Hash.ToLower()
  "{0}  {1}" -f ($(if ($actual -eq $h) { 'ok' } else { 'BAD' })), $name
}
```

## 4 怎么用（Lead）

```powershell
cd <仓库根>
# 0) 看计划 / 重置（目标树默认 .tmp/bank-bugfix-first-failing-test/tree；不预置任何任务要创建的文件）
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-bugfix-first-failing-test/reset-arm.py --dry-run
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-bugfix-first-failing-test/reset-arm.py
#    退出码：0 = 重置并校验通过；1 = 前置缺失（基线缺失/文件数不对/摘要不符/基线混入任务文件）；2 = 校验失败

# 1) 记下 audit 起始行数（reset-arm 会写进 .tmp/bank-bugfix-first-failing-test/reset-manifest.json）

# 2) 装配受治配置（不在本包范围）：目标树 .policy 要有 approval.json、tool-registry.yaml /
#    tool-registry.approved.json、dsh-adapter.yaml、hooks.json、patch.yml；按**这棵树**审核/签发。
#    用 bank/harness/scaffold_arms.py 建臂时，首消息须显式传 --first-message（它默认只探测
#    task-package/first-message.txt，本题按要求用 .md）；它调 reset-arm.py --target 并读 RESET-ARM-JSON。

# 3) 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 f61aab33…（见 §3）
```

**本题命令族的坑**（`bank/COMMAND-FAMILIES.md` §3）：`tests` 族只有 `python -m pytest( .*)?` 这一条形态；
`scripts` 是**空族**；`readonly` 是 `git status|diff`。不建议出现 `python -c`、`Get-Content` 或任何组合命令
（结构性阻断）。**SPEC §6 与 COMMAND-FAMILIES §3 有一处不一致**：两边都给了「只看目标测试」的形态，
但 SPEC 写的是 `tests/test_order_repository.py`、COMMAND-FAMILIES 写的是 `tests/test_order_service.py`；
本包按 SPEC 的 `test_order_repository.py` 落盘（那才是两条红用例所在），二者都落在同一白名单正则内，命令族不受影响。

## 5 本题的读法（不是「跑完就算」）

- **四个维度分开读**：T（任务完成；隐藏候选见 `coverage.md` §6，**未实现**）、C（规则遵守；`coverage.md` §2/§7）、
  A（结构；`layers.yaml` / `interfaces.yaml` + `tools/structure_metrics.py`）、过程（平台账本：被拒动作、
  原因码、`matched / skipped / served_checkers`）。**不许把过程读数折算进 T/C/A**（05 §5.3）。
- **死锁读数是本题的核心**：基线自带红测试 ⇒「改一半」或「先加测试再改实现」都会被 `TESTING-002@1 error`
  阻断；**一次完整修复**（入参、返回值都复制）才 `allow`。这是构造约束，不是配置错误
  （`bank/README.md` §6 决策 2；SPEC §7 给了三条路线，Lead 未裁前按「② 接受一次改对」读）。
- **`allow_with_warnings` 不是失败、也不是通过**：warning 级（`DOC-001` / `STYLE-001` / `STYLE-018`）与
  `exit 1` 只表示「不是 ALLOW」；阻断判定只读 `violations`，`skipped_rules` 单独读。
- **`ARCH-001` 的 C 分已标 `not_applicable`**：本题 3 个被测文件没有 controller 层（layers 为
  repository / test / test），该规则每次进 `skipped_rules`；`scoring.yaml` 已把这 3 分标
  `not_applicable`（不计分也不计分母），**C 上限 27**（`effective_total`）。跳过 ≠ 通过，读 C 必须带
  `effective_total`；§7 的 `skipped_rules=[ARCH-001@1]` 是证据。
- **n=1 只作案例读数**：不写均值/提升/显著；要写「值得扩试」需每臂 k≥3（05 §5.5）。
- **T 已冻结（38 条）**：`scoring.yaml` 的 `dimension_t.status: frozen`、`total: 38`、`case_ids` 38 条
  （与 `hidden/runner.py` 实际输出的 id 逐个相等）、`freeze_note: null`；两个 hidden 摘要已填实值。
  参考树 `38/38`、基线 `21/38`（两次运行的 stdout 各自逐字节相同，见 §10）。

## 6 直接可触发规则点（7 条；证据等级逐条标注）

| 规则 ID | checker | 级别 | 触发步骤（本题最可能做出来的动作） | 期望 decision | 证据等级 |
| --- | --- | --- | --- | --- | --- |
| TESTING-002 | failing_tests | error | M2 只复制返回值没复制入参；或先加测试再改实现（基线红测试仍在） | `block` / `TESTING-002@1 error` | **实测**（基线 `block`、半修 `block`，`coverage.md` §7 #1 #2） |
| SEC-015 | style_lint | error | 用 `except Exception: pass` 吞掉复制/写入错误 | `block` / `SEC-015@1 error` | **实测**（§7 #6） |
| STYLE-010 | style_lint | error | 写裸 `except:` 的**真处理**形态（`except: raise` 这种形式 ruff 0.14.13 不报 E722） | `block` / `STYLE-010@1 error` | **实测**（§7 #7；#5 是反直觉的 allow 读数） |
| DOC-001 | missing_docstring | warning | 删/改坏 `OrderRepository` 的类或方法 docstring | `allow_with_warnings` / `DOC-001@1 warning` | **实测**（§7 #3） |
| STYLE-001 | style_lint | warning | 新用例的长断言 / 长注释超 100 列 | `allow_with_warnings` / `STYLE-001@1 warning` | **实测**（§7 #8） |
| STYLE-002 | style_lint | error | 改实现后留下未使用 import | `block` / `STYLE-002@1 error` | **实测**（§7 #4） |
| STYLE-018 | style_lint | warning | 新测试文件 import 顺序错 | `allow_with_warnings` / `STYLE-018@1 warning` | **实测**（§7 #9） |

其余 36 条：24 条 ○（留作变异，除 `TESTING-001` 外证据 = 规则数据）、12 条 —（结构性不适用）。
**逐条理由与测法见 `coverage.md` §3/§4。**

## 7 与 SPEC / bank README 的偏差（逐条写明选哪边）

| # | 冲突 | 本包的选择 | 理由 |
| --- | --- | --- | --- |
| 1 | SPEC §2 / §8 写「基线 11 文件」；`bank/README.md` §1 原写「12 文件」 | 取 **SPEC 的 11 文件**（= `baseline/` 实际文件数；本轮已把 bank/README §1 同批改为 11） | SPEC 是本题的冻结依据，且 §4「允许写 5 路径」+ §5「允许写集合 ⊆ 5 条」自洽；凑 12 文件要凭空加第 6 条允许写或第 12 个基线文件，会与 §5 的隐藏判据直接冲突 |
| 2 | SPEC §2 早前写「起点 `pytest` → 2 failed, 1 passed」 | 实测 **2 failed, 2 passed**；本轮已把 SPEC §2 同批改成 2/2 | 11 文件树实际收集 4 条用例（repo 2 + service 1 + controller 1）；要凑成「1 passed」只能删服务/入口层的既有测试，那会违反「两个既有测试逐字节不变」 |
| 3 | SPEC §2 说「只把 `order_repository.py` 换成有 bug 的版本」，但 §1 又说基线已有两条红用例（旗舰的 `test_order_repository.py` 只有 1 条） | `tests/test_order_repository.py` 也**追加**了 `test_listing_returns_copies`（原用例与断言逐字保留） | §1/§5 要求两条红用例（`test_insert_returns_a_copy` 与 `test_listing_returns_copies`）；只在 `order_repository.py` 上做手脚无法让第二条用例存在 |
| 4 | 派单写「3 新建/3 修改」 | 实际 **2 新建 / 3 修改**（对齐 SPEC §3 的 5 条允许写） | 同上第 1 条：允许写必须 ⊆ SPEC 的 5 条；多一条就是第 6 条路径 |
| 5 | SPEC §6 与 COMMAND-FAMILIES §3 的「目标测试」文件不同 | 取 SPEC 的 `tests/test_order_repository.py` | 两条红用例在那里；两形态同属 `tests` 族白名单，不影响命令族 |
| 6 | 派单要求 `dimension_c.file_set` = 「允许写里的 .py 子集」 | 3 个 `.py`（`order_repository.py`、`test_order_repository.py`、`test_order_service_copy.py`） | 精确按派单口径；README/fix-notes 不是 python 规则对象 |
| 7 | `coverage.md` §6 的分组是 `BASE/T/N`（4+26+6），`SPEC.md` §5 建议 32 条 | 隐藏实现取 **38 条、分组 T/EN/I**（19+6+13） | 派单要求与旗舰同形的 T/EN/I 三组、条数 34–40；映射逐条写在 `hidden/PLAN.md` §5（BASE→EN5/EN6，N→I8–I13） |
| 8 | `coverage.md` T12 写「assert 总数 ≥ 5（原 3 + 新 ≥3）」 | 隐藏 `T16` 取 **≥ 6** | 3 + 3 = 6，原文算术自相矛盾；`interfaces.md` §5.1 与 `acceptance.md` A4 都写「至少 3 条新断言」 |
| 9 | 本题 `README.md` 早前写「T 现在是待定 / 不宣称天花板」 | 本轮冻结 T=38 并实测 **T 38/38 · C 27/27 · A 30/30** | `hidden/` 与 `reference/` 已落盘；`scoring.yaml` 的 status/total/case_ids/两个 hidden 摘要同批冻结（`frozen_by` 仍 `pending_lead_signature`） |

## 8 本包目录地图与完成度

| 路径 | 是什么 | 状态 |
| --- | --- | --- |
| `task-package/` | 首消息 / 里程碑 / 验收表 / 接口契约 / 允许写 / manifest | **已冻结候选**（字节固定，5/5 可复核） |
| `baseline/` | 11 文件基线（9 逐字节复制 + 2 本包构造），起点 2 failed / 2 passed | **已冻结候选**（组合摘要 `b9bb24d1…` 可复核） |
| `reset-arm.py` | 逐字节重置 + 摘要校验 + 拒绝混入任务文件 + reset-manifest.json | 已实测（dry-run + 真跑 11/11 ok，`RESET-ARM-JSON` 可解析、无绝对路径） |
| `layers.yaml` / `interfaces.yaml` | A 维度声明（最终树 13 文件 → 层；4 个非测试模块的上限） | 已写；基线树与**参考树**都实测 `structure_metrics` **10/10 pass**（参考树 `declared_unmatched=[]`） |
| `scoring.yaml` | T/C/A 机读规格；T = **frozen**（total 38、case_ids 38 条、两个 hidden 摘要已填实值） | 已写；顶层 `status: frozen`、`frozen_by: pending_lead_signature` |
| `coverage.md` | 43 条规则点 + A1–A10 + 隐藏候选 36 条 + 12 条实测读数 | 已写（7 直接 / 24 变异 / 12 不适用） |
| `hidden/` | 隐藏验收计划（`PLAN.md`，38 条 T/EN/I）与 `runner.py`（单文件自包含） | **已落盘**；基线 21/38、参考树 38/38、两次运行逐字节相同 |
| `reference/` | 参考解树 `tree/`（13 文件）+ `README.md`（决策点 / 读数 / 偏差） | **已落盘**；T 38/38 · C 27/27 · A 10/10 |

## 9 边界（引用本包前必须读）

- **本包是任务数据，不是平台规则**：它只描述「要模型做什么、允许写什么、怎么判」，不改任何判定逻辑。
- **隐藏验收必须独立出题**：写隐藏代码的子会话不得看任何参考解（dgate2 的 H1 同一口径）。
  本题的实现顺序是 **PLAN → runner → 参考解**：写 `hidden/` 时本题**不存在** `reference/`，
  所以「隐藏用例照着参考解写」在这道题上不成立（反向风险见 `reference/README.md` 页首）。
- **改它 = 改构造**：任何改动（哪怕一个字节）都要按 05 §8 记录理由与回退，重新生成
  `task-package/manifest.sha256` / 基线摘要 / 本文件 §3 的哈希表；冻结后逐文件哈希不符 => 该 run 作废。
- **本包不声称已激活任何 treatment**：本题没有对比臂（`scoring.yaml` 的 `treatment` 写明「未定」）。
- **不跑真机会话、不 commit**：本包落地时只做了只读/本地验证（pytest、policy.check、
  reset-arm、structure_metrics、manifest/YAML 复核）；隐藏与参考解那一轮同样只跑本地
  （hidden runner 双跑、pytest、C 3 文件、A 10 谓词），**没有起真机 dsh 会话**。

## 10 本包实测读数（hidden + reference + 天花板；n=1）

> 环境：本机 `.venv`（Python 3.13.11）、仓库根为 cwd；**只读/本地**，不起真机会话、不 commit。
> 命令逐条见 `reference/README.md` §4；**n=1 只作案例读数**，不写均值/提升/显著性（`bank/README.md` §5）。

| 读数 | 值 | 说明 |
| --- | --- | --- |
| 基线树 T | **21 / 38**（exit 1） | 17 条在基线上红；两次运行 stdout **逐字节相同**（sha256 `c25d9de95de572eeb5031ba212f328a8e5490c85a0aacd1dcdd64129e2903b5c`） |
| 参考树 T | **38 / 38**（exit 0） | 两次运行 stdout **逐字节相同**（sha256 `ed06ff777b9dd0d55f4408fd76f2966bee7b1039578cf91a39c6cefbd550a041`） |
| 参考树 pytest | `9 passed`，exit **0**；`--collect-only` = **9**（基线 4） | 在树的**副本**里跑；参考树本身仍是 13 文件 |
| 参考树 A | **10 / 10**，exit 0 | `workspace_scope.files=9`、`declared_unmatched=[]`；A1–A10 全 `pass` |
| 参考树 C | **27 / 27**（`effective_total=27`） | 3 个被测 `.py` 全部 `decision=allow`、`violations=[]`、`skipped_rules=[ARCH-001@1]` |
| 参考树加权分 | T `40`（38/38）、C `27`、A `30` | 按 `scoring.yaml` 的权重与 `effective_total`；**天花板三维齐备且全满** |

**C 逐文件读数**（`--request-id` 固定、`--changed` 5 条全量、`--operation edit`；`complete=true`，
`blocking_capable_skipped=1` = 唯一被跳过的那条 `ARCH-001@1`，`served_checkers=[failing_tests,
missing_docstring, missing_tests, style_lint]`，`pending_findings=0`，三次运行 `rule_set_hash` 相同
= `sha256:73845ef515236940266b682631c02dec84c06886fa27a1e99f57e66284fae7d4`）：

| 被测文件 | `--layer` | decision | violations | skipped_rules | exit |
| --- | --- | --- | --- | --- | --- |
| `src/shop/order_repository.py` | repository | `allow` | 无 | `ARCH-001@1` | 0 |
| `tests/test_order_repository.py` | test | `allow` | 无 | `ARCH-001@1` | 0 |
| `tests/test_order_service_copy.py` | test | `allow` | 无 | `ARCH-001@1` | 0 |

**怎么读这三行**：规则段 7 条适用规则各 3 分 = 21；冻结 8 文件逐字节不变 = 3（隐藏 `I5` 同时判）；
允许写集合外 0 改动 + 测试未削弱 = 3（隐藏 `I6` / `T17` 同源）。`ARCH-001` 的 3 分
**不计分也不计分母**（§5 已说明），所以 C 的上限是 27 而不是 30——**跳过不是通过**。
