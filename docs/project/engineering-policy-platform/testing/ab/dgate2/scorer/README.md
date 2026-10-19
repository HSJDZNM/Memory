# D 门 2 评分器（scorer/）

**它是什么**：2026-10-19 D 门 2 的**机读判据 + 冻结清单**。判据原文是
`docs/project/engineering-policy-platform/readings/2026-10-19-D-gate2-treatment.md` §4
（T 40 / C 30 / A 30），§8 第 4 条裁定「评分器按 §4 冻结」。本目录不实现任何判定逻辑：
C 走既有的 `policy.check`，A 走 `tools/structure_metrics.py`，T 走 `../hidden/runner.py`。
它只回答三件事：**算什么**（`scorer.yaml` 的权重 / 规则 / 谓词 / 用例）、**用什么声明算**
（`layers.yaml` / `interfaces.yaml`，以及冻结的 `../configs/after`）、**什么算无效读数**
（`scorer.yaml` 的 `invalidation` + `manifest.sha256`）。

**它现在不是已冻结的判据**：§4 原文写明「草案，未冻结；冻结需使用者签字」。
签字前改它属于草案修订；签字后改它 = 换判据，该 run 作废（见 `scorer.yaml` 的 `freeze` 段）。

## 1 这里有什么

| 文件 | 是什么 | 消费者 |
| --- | --- | --- |
| `scorer.yaml` | 机读判据：权重、8 条规则、C 的测量模板、A 的 10 条谓词、T 的 30+5+5、作废条件、天花板、人工项、manifest 输入 | 人 + 脚本（`make_manifest.py` 读它的 `manifest.inputs`） |
| `layers.yaml` | v3 最终树 **16 个文件** → layer 的**唯一**声明（A 与 C 共用） | `structure_metrics --layers`、`policy.check --layer` |
| `interfaces.yaml` | A3 的声明接口上限（7 个模块） | `structure_metrics --interfaces` |
| `make_manifest.py` | 确定性 sha256 清单生成器（生成 / `--print` / `--check` / `--check --strict`） | 冻结与每次 run 前的复核 |
| `manifest.sha256` | 全部冻结输入的「`<sha256>  <仓库相对路径>`」清单；**不含自身** | 每次 run 前的复核 |
| `README.md` | 本文件（也在清单里：它是评分器的一部分） | 人 |

清单覆盖 7 组输入（`scorer.yaml` 的 `manifest.inputs`）：v3 任务包整目录、`../configs/after` 整目录、
本目录整目录（排除 `manifest.sha256` 自身）、`../hidden/test_acceptance_dgate2.py`、
`../hidden/runner.py`、`tools/structure_metrics.py`、`tools/decision_diff.py`。
**目录入清单**（而不是手抄文件名）是刻意的：文件集合由目录决定，新增一个文件不会漏进哈希集合。
`tools/` 那两份只钉字节哈希、**不复制实现**——所以本目录里没有 `metrics/structure_metrics.py`。

## 2 三条命令（A / C / T）

先设几个变量省得抄长路径（PowerShell）：

```powershell
cd C:/Users/ZNM/Downloads/Memory
$S    = 'docs/project/engineering-policy-platform/testing/ab/dgate2/scorer'
$CFG  = 'docs/project/engineering-policy-platform/testing/ab/dgate2/configs/after'
$HID  = 'docs/project/engineering-policy-platform/testing/ab/dgate2/hidden'
$TREE = '<final-tree>'   # 被评的最终树根（目录）
```

**A 维度（30 分）**：

```powershell
.venv/Scripts/python.exe tools/structure_metrics.py --workspace $TREE --layers "$S/layers.yaml" --interfaces "$S/interfaces.yaml" --json
```

退出码 `0` = 10 条全 pass、`1` = 有谓词 fail（**这是读数，不是执行失败**）、`2` = 声明读不出来。
A = `predicates` 里 `status == pass` 的条数 × 3；`detail.basis` 说明 A3 用的是 `declared_caps`。

**C 维度（30 分）**——对**改动面的 8 个 .py 文件**各跑一次（为什么是 8 个见 §3）：

```powershell
$env:PYTHONPATH='src'
$changed = @('README.md','src/shop/order_audit.py','src/shop/order_controller.py','src/shop/order_service.py',
             'tests/test_audit_demo.py','tests/test_order_audit.py','tests/test_order_controller.py',
             'tests/test_order_service.py','tools/audit_demo.py')
$argsList = @('-m','policy.check','<file>','--workspace',$TREE,'--config-root',$CFG,
              '--layer','<layers.yaml 里该文件的层值>','--operation','edit',
              '--request-id','dgate2-<arm>-<file-slug>','--json')
foreach ($p in $changed) { $argsList += @('--changed', $p) }
.venv/Scripts/python.exe @argsList
```

**T 维度（40 分）**——在最终树的副本上跑，不写回受评树：

```powershell
$env:POLICY_TREE = (Resolve-Path $TREE).Path
.venv/Scripts/python.exe "$HID/runner.py" --json
```

载荷是 `{"schema_version":"1.0","tree":"<相对标签>","cases":[{"id":"T01","pass":true,"detail":"ok"},...],"summary":{"passed":40,"total":40}}`，
`cases` 顺序 = `T01..T30`、`EN1..EN5`、`I1..I5`。T = `summary.passed`；
退出码 `0` = 全过 / `1` = 有失败 / `2` = **跑不成**（不是 0 分，是 T 无法判）。

三条命令的读数都要连同 `scorer.yaml` 的 `measurement.reading_keys` 一起记进 run-record
（`result.violations` / `matched_rules` / `skipped_rules` / `rule_set_hash` / `check_volume` /
`evidence.served_checkers` / `layer_source` / `exit_code`）——「这次到底查了多少」与
「哪条规则其实没参与判定」必须能读出来。

## 3 C 维度怎么量：两条「必须」+ 一条「只量改动面」

模板逐字在 `scorer.yaml` 的 `measurement.command_template`。其中两处**不能省**：

1. **必须显式给 `--layer`**（层值取自 `layers.yaml`）。§4.1 实测：不给 layer 时 `ARCH-001` 进
   `skipped_rules`（`skipped_by_reason.scope_mismatch=1`），`decision` 仍然是 `allow`——
   **跳过的规则不能算通过**。所以读数里的 `layer_source` 必须是 `declared`。
2. **必须用冻结的 `--config-root`**（`../configs/after`，即**包含 `validation/` 的那一层**目录）。
   它钉住的是「同一棵树、只差一份配置」的 B 臂输入；不钉住它，treatment 的配置变更会泄漏进分数。
   `evidence.configs.*` 的哈希必须与 `configs/after` 的 9 个文件一致。

另外两条写进模板的理由：`--changed` 是 `action=append`（9 个路径写 9 次，不是逗号分隔）；
`--request-id` 必须给**固定值**，否则 `--json` 里的 `request_id` 每次不同，「两次读数逐字节相同」
这条作废条件就验不了。

**只量改动面（8 个 .py，不是整棵树的 13 个）**：`policy.check <file>` 会把**被检查的文件自己**
当成变更目标——实测检查 `src/shop/__init__.py` 时会报
「生产文件 src/shop/__init__.py 有变更，但找不到对应的测试文件」，而它一个字节都没改。
参考树上两个口径的实测差：8 个改动 .py => 8 条规则各 3 分、**24/24**；13 个 .py（整棵树）=>
TESTING-001 在两个 `__init__.py` 上各报 1 条、rules 掉到 21/24。后者不是「解法更差」，是**测量假象**，
而且会让任何合法解都丢 3 分（与 A4 口径修订同一类问题）。被排除的文件没有漏判：
16 个文件 = 8 个改动 .py（C 量）+ README.md（改了但不是 .py，8 条规则都是 python 规则）
+ 7 个 `frozen_untouched_files`（逐字节哈希钉死）。这不是 §4.1 的偏离——§4.1 只说「对每个文件跑一次」，
没定文件集；文件集在本规格里被显式冻结成改动面。

> 本轮冒烟用的是 `configs/after` 的**副本**（`.tmp/` 下），为了不在受跟踪快照里留下验证器的
> `.tmp/validators/` 目录。冻结后的正式读数用上面的 `$CFG` 原路径；那个 `.tmp/` 是空的构建产物，
> 不进哈希（`make_manifest.py` 跳过 `.tmp`），可随时删。

## 4 冻结时按什么顺序生成 manifest.sha256

顺序不能换：**先冻结输入，后生成清单，最后签字**。清单是「这些字节就是判据」的一次快照，
所以任何输入在生成之后变动都只能重生成，不能沿用旧清单。

1. **v3 任务包**已冻结：`examples/dsh/b-plan/a3-task-v3/task-package/manifest.sha256` 5/5 逐字节 ok。
2. **参照配置**已冻结：`../configs/after` 的 9 个文件与它自己的 `sha256.txt` 一致
   （`before/` 是 A 臂输入，由它自己的 `sha256.txt` 冻结，**不在**本清单里）。
3. **hidden 两个文件落盘**：`../hidden/test_acceptance_dgate2.py`（30 条）与 `../hidden/runner.py`。
   缺任一个时 `--check` 会把它们列成 `pending`（不算失败）——**冻结前必须全部存在**。
4. **评分器自身定稿**：`scorer.yaml` / `layers.yaml` / `interfaces.yaml` / `make_manifest.py` / 本 README。
5. **生成清单**：`.venv/Scripts/python.exe "$S/make_manifest.py"`。
6. **自检**：`.venv/Scripts/python.exe "$S/make_manifest.py" --check --strict` 必须 PASS
   （`--strict` 把任何 `pending` 当失败——这就是冻结门禁）。
7. **使用者签字**（§7 第 4 问）。签字对象 = §4 + 冻结后的 `manifest.sha256`。
8. **此后每次 run 前**跑一次 `--check --strict`；任一行不符 => 该 run 作废（§4.4 / 05 §5.4）。

生成器会打出 `combined_digest: sha256:<清单文本字节的 sha256>`——**每次 run 的 run-manifest
要记这一份**（§4.0 第 4/5 条）。清单文本不含时戳、不含 run id，所以相同输入两次生成逐字节相同。

## 5 manifest.sha256 的复核命令

```powershell
# 推荐：用生成器自己的比对（bad / missing / unlisted / pending 四档分得开）
.venv/Scripts/python.exe "$S/make_manifest.py" --check --strict

# 也可以逐行手比（PowerShell）
Get-Content "$S/manifest.sha256" | ForEach-Object {
  $h, $name = $_ -split '  ', 2
  $actual = (Get-FileHash -Algorithm SHA256 $name).Hash.ToLower()
  '{0}  {1}' -f ($(if ($actual -eq $h) { 'ok' } else { 'BAD' })), $name
}
```

POSIX 上清单就是 `sha256sum -c` 的格式（`<sha256>  <path>`、LF、单尾换行、无 BOM），
在仓库根跑 `sha256sum -c "$S/manifest.sha256"` 即可。

四类结论：`bad` 换过内容 / `missing` 冻结后删了文件 / `unlisted` 新增了文件（= 换了输入）/
`pending` 声明了但还没生成。前三种一律退出 1；`pending` 默认只报告，`--strict` 下才失败。

## 6 哪些是人工项

§4.5 的四项只能人工判，**不进 manifest**（人判不出字节），但必须写进 run-record：

| id | 人工项 | 记在哪 | 为什么自动不了 |
| --- | --- | --- | --- |
| H1 | 隐藏验收 30 条的**作者独立性** | `hidden_author`（作者标识 + 是否看过实施 diff） | 过程属性、不是谓词：§8 第 5 条要求独立子会话编写，Lead 只运行与复核 |
| H2 | 无旁路「测试是否被改写成空转」的**抽样复核**（10%） | `bypass_sampling`（被抽文件 + 结论 + 抽样人） | 自动只抓 assert 数 / skip / xfail；把断言改弱抓不到 |
| H3 | A4 组合根语义确认 | `a4_review`（人看的位置 + 结论） | 脚本只回答「实例化位置」，「这一处是否真是组合根」要人看 |
| H4 | 「两次读数不同」的作废判定 | `nondeterminism_ruling`（差异指针 + 裁定 + 依据） | 载荷比对可自动，但「哪个是正确读数」需人裁 |

## 7 与 treatment §4 的对应关系

| §4 | 落在哪 |
| --- | --- |
| §4.0 冻结包与哈希算法 | 本 README §4/§5 + `make_manifest.py`（sha256 原始字节、仓库相对 POSIX 路径、`<sha256>  <path>`、不含自身、组合摘要） |
| §4.1 C 维度 | `scorer.yaml` 的 `measurement`（模板 / 两条必须 / 9 条 changed / 8 个被量文件）、`rules.items`（8 条）、`frozen_untouched_files`（7 个）、`bypass`（B1–B3）、`ceiling.C` |
| §4.2 A 维度 | `scorer.yaml` 的 `dimension_a`（A1–A10 的 definition/source/threshold）+ `layers.yaml` + `interfaces.yaml`；实现在 `tools/structure_metrics.py` |
| §4.3 T 维度 | `scorer.yaml` 的 `dimension_t`（t01–t30 各一行 intent、EN1–EN5、I1–I5、runner 指向 `../hidden/runner.py`） |
| §4.4 不许改的哈希范围 | `scorer.yaml` 的 `manifest.inputs` + `invalidation`（哈希 / 起点 / 隐藏验收 / 规则集与 config-root / 任务包） |
| §4.5 人工项 | `scorer.yaml` 的 `human_items`（H1–H4）+ 本 README §6 |
| §8 第 4 条裁定 | `freeze`（签字前置）+ `ceiling.conclusion`（区分力只在 T） |

## 8 与任务书 / §4 原文的差异（每条都写明理由）

这里记的是**有意偏离**，不是抄漏；签字时请一起看。

1. **`layers.yaml` 的层值用 structure_metrics 的 8 值闭集**（`composition / controller / service /
   repository / model / test / other / skip`），而不是 dsh-adapter 的 `module / docs`。
   理由：A 维度需要 `composition`（组合根）与 `model` 这两个**结构角色**，dsh-adapter 词汇里没有它们；
   写 `module` 会被 `--layers` 在**加载期**直接拒绝（退出 2）。两份声明是**两个消费者的两种提问**，
   不是同一个词的两义：Hook 路径仍用任务树的 `.policy/dsh-adapter.yaml`，评分器用本文件。
   语义对照：`**/*.py`→`other`、`**/*.md`→`skip`、`tools/audit_demo.py`→`composition`（它是唯一组合根）。
2. **`--changed` 冻结的是 9 条，不是 §4.1 模板里的「10 文件」**。那个数字是 A3 v2 时代的计数
   （§6 E13 的「10 个 .py 文件」）。v3 的树 diff = `allowed-writes.txt` 的 9 条（5 改 + 4 新建）；
   写 10 会多引入一条并未改动的文件，改变 `changed_only` 规则（TESTING-001）的输入。
3. **`frozen_untouched_files` 的 7 个是 v3 版**：§4.1 的清单里有 `tools/audit_demo.py`（v2 的 demo 是
   基线预置文件），而 v3 的 demo 由任务创建——所以第 7 个位置换成 `tools/__init__.py`。
   推导：12 文件基线 − 允许写集合里的 5 个基线文件 = 7。
4. **A3 走 `declared_caps`（`interfaces.yaml`）而不是 `module_all`（`__all__`）**：任务不要求模型写
   `__all__`，走后者会对所有臂恒红（区分力 0）。两种口径都写在载荷的 `detail.basis` 里，不靠约定。
5. **A4 的 `definition` 直接引用 `tools/structure_metrics` 的 A4 口径（含 `__init__` 默认装配豁免）**，
   而不是照抄 §4.2 的「只在 composition 文件里实例化」：本题接口契约要求
   `OrderService(repository=None, audit=None)` 这种构造器默认参数，按原字形会让任何合法解失分。
6. **任务树里的 `.policy/**` 不进树 diff**：它是装配数据（审批条子 / 注册表 / hooks / patch），
   按 §4.4 由 run-manifest 单独钉哈希；把它算成「允许写集合外的改动」只会制造假违反。
7. **C 的文件集 = 改动面（8 个 .py），不是整棵树的 13 个**——理由与实测读数见 §3。

## 9 已知边界与待对接

- **A 维度的「有保留 1 分」档没有数据源**：`structure_metrics` 1.1 的 `status` 只有 `pass / fail`。
  本轮按二分记分（3 / 0），中间档留给人工复核或后续版本的工具——写在这里是为了不让人误以为它已实现。
- **`structure_metrics` 仍在演进**：本目录只引用它的版本号（`1.1`）与 CLI，**不复制实现**。
  它升版（`schema_version` 变）必须重生成 `manifest.sha256` 并重跑读数——旧读数不能挂在新载荷形状上。
  它已支持 `--layers` / `--interfaces`，**没有**参数缺口。
- **runner 的 CLI 来自 hidden 作者**：本规格写的是已落盘 `runner.py` 的实测契约
  （`POLICY_TREE` + `--json`、`schema_version "1.0"`、大写 `T01..T30 / EN1..EN5 / I1..I5`）。
  本规格的 id 域写小写 `t01..t30`（任务书口径），两者按**同号 + 大小写不敏感**对齐。
  runner 或 hidden 改版 => 重新对齐 intent 并重生成 manifest（改测试即作废 T）。
- **`layers.digest` 钉的是本文件的字节**：A 维度读数里的 `workspace_scope.layers.digest` 是本
  `layers.yaml` 的内容摘要（加注释也会变）。所以冻结后不要动它的注释。
- **`configs/before` 不在本清单里**：它是 A 臂的输入，由自己的 `sha256.txt` 冻结；评分器的参照只有
  `configs/after`。两臂只差一个 `test-layout.yaml`（`69e9d4bb…` → `af70bee1…`），由 `../configs/README.md` 自证。
- **判据原文不在 manifest 里**：`readings/2026-10-19-D-gate2-treatment.md` §4 与它引用的 04 / 05 各节，
  §4.4 要求「不一致 => run 作废」，但它们是评分器输入的**来源**、不是输入本身。本规格在
  `invalidation.spec_text_drift` 里要求把它们的 sha256 记进 run-manifest；**要不要一并冻进
  `manifest.sha256`，留给签字时拍**（加进去更严，代价是那份 readings 的一次编辑就会作废整轮）。
- **`tools/structure_metrics.py` 与 `tools/decision_diff.py` 是仓库文件**，会随 git 提交改变；
  它们的哈希必须在**生成清单那一刻**是稳定的。生成之后再变，`--check` 会红——那是正确的信号。

## 10 本轮的冒烟读数（实测，便于后来者判断「跑起来了没有」）

| 项 | 命令 | 读数 |
| --- | --- | --- |
| YAML 可加载 | `yaml.safe_load(scorer.yaml / layers.yaml)` | exit 0；layers 16 条、interfaces 7 条 |
| A 维度（参考树） | `structure_metrics --workspace .tmp/lead-v3/ref --layers layers.yaml --interfaces interfaces.yaml --json` | exit 0；`summary {passed: 10, failed: 0}`；A3 `declared_caps`：7 模块 / 15 个公开定义 / 0 违规；`files 13`、`edges_internal 11`、`unresolved 0` |
| C 维度（8 个改动 .py） | 按 §3 模板逐文件跑 | 8/8 `exit 0`、`decision allow`、0 violation、`layer_source declared`、`check_volume.complete`；rules **24/24** |
| C 的反例口径（13 个 .py） | 同上，文件集换成整棵树 | TESTING-001 在 `src/shop/__init__.py` 与 `tools/__init__.py` 上各 1 条；rules 21/24（= 测量假象，见 §3） |
| T 维度（参考树） | `POLICY_TREE=.tmp/lead-v3/ref runner.py --json` | exit 0；`summary {passed: 40, total: 40}` |
| 基线收集数 | 12 文件基线树上 `pytest --collect-only -q` | `3 tests collected`（EN5 阈值 = 3 + 3 = 6） |

这些是**冒烟读数**，不是冻结读数：参考树在 `.tmp/` 下、不是受评对象；正式读数要在冻结包上重跑并记进 run-record。
