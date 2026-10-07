# evaluation/：外部第三方语料与它们的读数

> 这份 README 说的是**数据**：我们从上游取什么、按谁的口径读、取了之后钉住什么、
> 以及**这份数据证明不了什么**。工具实现见 [../tools/eval_corpus.py](../tools/eval_corpus.py)。

## 1 这份目录是什么

W1「规则保真度」的语料层。它让「外部第三方行级标注」在这台机器上**可复现地**取到、可校验、可读成统一注解：

* 上游归档只在运行期取到 `.tmp/eval-corpora/<id>@<revision>/`（`.tmp/` 已在 `.gitignore` 里），
  **用完即删**（`python tools/cleanup.py`），仓库不提交任何上游原文；
* 仓库只提交 `evaluation/corpora/<id>.lock.json`：上游 revision + 文件清单 + 逐文件 sha256；
* 漂移不许静默：`--verify` 逐文件比 sha256，并对每个数据集跑结构自检，任一不通过就退出 1。

它**不是**判定路径：这里没有 `rule_id`，也没有 allow / block。「码 → rule_id」的映射由
`policies/**/*.yaml` 的 `rule.style_lint.codes` 推出，由 `tools/governance_eval.py`（harness）负责——
本目录不复制第二份真相。

## 2 怎么取（全部可以离线重跑）

```text
python tools/eval_corpus.py --fetch all            # 取语料（codeload tarball，sha 钉死在 tools/eval_corpus.py）
python tools/eval_corpus.py --record-lock all      # 记 lock（**只在显式换 revision 时做**）
python tools/eval_corpus.py --verify               # 漂移校验 + 结构自检（不联网）
python tools/eval_corpus.py --list                 # 登记项 + 本地状态 + 注解数 + skipped 明细
python tools/eval_corpus.py --annotations <id>     # 打印注解与作用域
python tools/eval_corpus.py --annotations <id> --json
```

其它开关：`--root <目录>`（默认 `.tmp/eval-corpora`）、`--lock-dir <目录>`（默认 `evaluation/corpora`）、
`--offline`（禁止联网：本地缺语料就报错，**不回落**到任何缓存或默认值）。

`tools/eval_corpus_extra.py`（owner=eval-extend）存在时会被自动发现并合并；不存在时照常工作。
两条硬规则：只允许 `https://`（其它 scheme 直接拒绝），归档顶层目录必须等于登记表里的 `archive_root`
——拼错 sha、拼错目录、`paths` 一条都没命中，全部显式报错，绝不静默少取文件。

## 3 目录布局

```text
evaluation/
├── README.md                 # 本文件
└── corpora/
    ├── bandit-functional.lock.json       # 132 个文件
    └── pycodestyle-testsuite.lock.json   # 45 个文件
```

lock 的键：`schema_version` / `dataset` / `revision` / `url` / `license` / `license_source` /
`tier` / `expectation_kind` / `archive_root` / `paths` / `registry_ref` / `file_count` / `files[]`。
`files[]` 的每一项是 `{path, sha256, size}`，按路径排序，**不含时间戳**——相同语料必须得到逐字节相同的 lock。

## 4 两个数据集

### 4.1 bandit-functional（PyCQA/bandit，Apache-2.0）

**oracle 不是** `tests/functional/test_functional.py`：那个文件的 `expect` 字典只有
`SEVERITY` / `CONFIDENCE` 两级**计数**，既没有码也没有行号（见第 9 节）。

真正的行级 oracle 在 `bandit/plugins/**.py` 的 docstring 里 —— 那段由真跑输出粘回去的示例。
生成模板是 `bandit/formatters/text.py:84`（`">> Issue: [{test_id}:{test}] {text}"`）与
`:101`（`"   Location: %s:%s:%s"`），所以 `Location: examples/x.py:<line>[:<col>]` 里的行号
**就是 bandit 自己上报的行号**。

码的三条来源（全部机器可读，**不 import 上游测试模块**——import 会执行上游测试代码）：

| 来源 | 位置 | 本次实测条数 |
| --- | --- | --- |
| `>> Issue: [B324:hashlib]` 括号里的码 | docstring 原文 | 15 / 48 |
| 拥有该 docstring 的函数的 `@test.test_id("B602")` | `bandit/core/test_properties.py:53`，用 `ast.unparse` 读字面量 | 12 / 48 |
| 模块 docstring 标题行的 `B201: ...` | docstring 原文 | 21 / 48 |

来源②③解析出的码必须真的在该文件的 `@test.test_id` 声明集合里，否则该条记
`code_not_declared_in_file` 跳过（可见，不静默）。解析覆盖率 48/48 = 100%。

### 4.2 pycodestyle-testsuite（PyCQA/pycodestyle，MIT/Expat）

oracle = `testing/data/*.py` 里形如 `#: E501` / `#: E201:1:6` / `#: Okay` 的行级标注。
**规范实现在上游 `tests/test_data.py`**，本解析器按它同一口径实现：

| 上游原文位置 | 它定义了什么 |
| --- | --- |
| `tests/test_data.py:15` | `CASE_RE = re.compile('^(#:.*\\n)', re.MULTILINE)` |
| `tests/test_data.py:28-61` `get_tests()` | 把 src 切成 (注释, 注释之后的源码) 对；注释之前的第一个非空段按 `'#: Okay'` 处理；块为空则跳过 |
| `tests/test_data.py:64-95` `test()` | `Okay` = 期望零诊断；`noeol` = 跑之前把块尾换行去掉；含 `:` 的 token 走精确位置，否则按 `code[:4]` 匹配 |
| `testing/support.py:20-26` | 精确位置的口径：`f'{code}:{line_number}:{offset + 1}'`，即 `#: E201:1:6` 的 `1:6` 是**块内** 1 基 行:列 |
| `pycodestyle.py:1761` `readlines()` | 解码口径：`tokenize.open`，失败回落 `latin-1`（本工具用同一口径） |

**一处刻意偏离**：上游 `get_tests()` 只在「块非空」时才把行号往前推，于是空块之后它给出的
case id 会偏小。实测 `testing/data/E30.py`：真实在第 19 行的 `#: E302:2:1`，上游会记成 16
（`16: "#:"` / `17-18: 空行` / `19: "#: E302:2:1"`）。那个 id 只作 pytest 展示用、不参与匹配；
本工具按**真实行号**计算。这也是唯一一处偏离——已用一次独立的朴素行扫描对账过（见第 7 节）。

## 5 `line` / `scope` 的口径（契约 v1.1）

* `Annotation.line` = **上游给这条期望锚定的那一行**，1 基：
  * bandit：`Location:` 里的行号；
  * pycodestyle：那条 `#:` 注释所在的行（与上游 pytest case id 同一行）。
  两个数据集里 `line` 都 `>= 1`，**不出现 0**（上游都给到了行粒度）。
* 期望的**作用域**由 `annotation_scopes(dataset_id, *, root)` 给出，1 基闭区间：

| 数据集 | `scope_start` | `scope_end` | `expected_lines` |
| --- | --- | --- | --- |
| bandit-functional | = `line` | = `line` | `(line,)` |
| pycodestyle-testsuite | `#:` 行 + 1 | 下一个 `#:` 行 - 1，或文件末行 | 上游给了 `:line:col` 的那些 token 换算出的**绝对行**；空元组 = 上游只给到作用域 |
| 文件级（`line == 0`） | `0` | `0` | 必须为空元组 |

**点作用域会被归一化成"精确位置"**：只要 `scope_start == scope_end >= 1` 且 `expected_lines` 为空，
就把那一行写进 `expected_lines`。理由是它**本来就只有一行可命中**——这是把已经成立的事实写出来，
不是新增期望（作用域一个数都没改）。为什么必须做：harness 的 `position_bucket`
（`tools/governance_eval.py:601`）按「`expected_lines` 为空 **且** `scope_end == scope_start`」判**文件桶**，
那里的匹配会放宽成「这个文件里出现过这个码」。**关掉归一化的实测红数**（红样例见 6.1）：

| | 关掉归一化 | 归一化之后 |
| --- | --- | --- |
| 被读成"文件级"的 `line > 0` scope（**原始**，含 `Okay` 负例） | **215** | 15 |
| 其中真正的**行级正例期望**（扣掉单行 `Okay` 负例） | **200** | **0** |

（215 = pep8-naming 32 + tryceratops 63 + pycodestyle 单行块 120；其中 pycodestyle 的 120 里有 15 条是
单行 `#: Okay` 负例，所以"行级正例被误读"的准确数字是 **200**——上一条口径报告里我写的 215 是原始数，
这里更正为 200/0；残留的 15 条是负例控制，见下。）

两个例外不归一化：`[0, 0]`（文件级哨兵，本来就没有行号）与 `code == "Okay"`（负例，语义是"零诊断"，
没有位置）。`Okay` 不归一化是**故意的**：它进的是 harness 的 `blank_scopes` 负例控制通道，
把它的块范围缩成一个点等于篡改负例控制。

### 5.0 三个计数器必须对得上（实测恒等式）

`--annotations` 的总数、`位置桶`、`文件级/行级` 三套计数说的是同一个集合，必须能逐条对账。
修复后实测（`line / scope / file` 三桶口径照抄 `tools/governance_eval.py:601`）：

| 数据集 | kept | line | scope | file | 文件级 | 行级 | 行级正例被读成 file |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bandit-functional | 46 | 46 | 0 | 0 | 0 | 46 | 0 |
| pep8-naming-testsuite | 43 | 32 | 0 | 11 | 11 | 32 | 0 |
| pycodestyle-testsuite | 657 | 272 | 370 | 15 | 0 | 657 | 0 |
| pydocstyle-testcases | 72 | 0 | 0 | 72 | 72 | 0 | 0 |
| tryceratops-samples | 63 | 63 | 0 | 0 | 0 | 63 | 0 |
| flake8-logging-tests / isort-tests / pyflakes-messages | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **合计** | **881** | **413** | **370** | **98** | **83** | **798** | **0** |

五条恒等式全部成立：

1. `kept == line + scope + file`：881 = 413 + 370 + 98
2. `kept == 文件级 + 行级`：881 = 83 + 798
3. `file == 文件级 + Okay_in_file`：98 = 83 + 15（`Okay` 是**负例**，不是文件级正例）
4. `line + scope == 行级 − Okay_in_file`：413 + 370 = 798 − 15
5. 行级**正例**被读成文件桶的条数 = **0**

第 3/4 条那 15 条差额必须点名，否则「file 桶 98」与「文件级 83」看起来像打架——它们不是同一件事。

**harness 侧已经把它变成直接等式**（2026-10-07，eval-harness 按 Lead 裁定 A 落地）：`position_bucket`
新增 **`POSITION_BLANK`** 通道（先判负例 → 再判 `line <= 0` → 再判点作用域/expected_lines → 最后多行作用域），
负例既不当正例也不丢。于是四通道口径下（他们的实跑，不是我的复算）：

| 通道 | line | scope | blank | file | 合计 |
| --- | --- | --- | --- | --- | --- |
| 全部 8 个数据集 | 413 | 296 | **89** | **83** | 881 |

`file = 83` 就是**文件级**本身，`blank = 89` 就是全部 `#: Okay` 负例（我的 3 桶读法里它们被拆成
file 桶 15 + scope 桶 74）。两套读法逐项对得上：
`296 + 74 = 370`、`83 + 15 = 98`、`413 + 296 + 89 + 83 = 881`。
**引用位置桶时必须说清是哪一套口径**（3 通道 / 4 通道），否则同一个数据集会读出两个数。

### 5.1 文件级 vs 行级：**两个数不许合并**

`line == 0` 表示**上游只给到文件级/定义级粒度**（例：pydocstyle 的断言是 `(定义名, 消息)`，
根本没有行号；pep8-naming 有一部分标记只写到用例粒度）。它的作用域是哨兵值 `[0, 0]`，
含义是「**这个文件里**出现了这个码」，**不是**「第 0 行出现了这个码」：

| | 行级（`line > 0`） | 文件级（`line == 0`） |
| --- | --- | --- |
| 能与诊断行比对吗 | 能（`scope_start`–`scope_end` 闭区间，精确位置见 `expected_lines`） | **不能**，只能对「文件里有没有这个码」 |
| 能算行级 P/R 吗 | 能 | **不能**——分母不是同一件事，混在一起算会同时污染两端 |
| 作用域 | 真实闭区间，`scope_start >= 1` | 哨兵 `[0, 0]` |
| `expected_lines` | 可非空 | 必须为空 |

因此 `--list` / `--annotations` / `--verify` 三处都把两个数**分开打印**
（`file-level` / `line-level`），任何「注解 N 条」的引用都必须能拆开。
`--annotations --json` 的载荷**刻意不加**这两个键（Lead 2026-10-07 裁定：`ANNOTATION_SCHEMA_VERSION`
`"1"` 是本会话首次建立、从未发布，首次发布前的形状修正在同一版本号内，先例是 AGENTS 第 55 条的
`OUTPUT_SCHEMA_VERSION` 1.2）；消费方要程序化地拿这个拆分，用
`sum(1 for a in load_annotations(...) if a.line == 0)` 自己算即可。
本目录自带的两个数据集**全部是行级**（`line == 0` 的条数 = 0）；
文件级来自 [../tools/eval_corpus_extra.py](../tools/eval_corpus_extra.py) 登记的语料
（实测：pydocstyle-testcases 72 条全是文件级，pep8-naming-testsuite 43 条里 11 条是文件级）。

为什么必须分开：pycodestyle 的期望是**块级**的（`#: E501` 管的是它之后的一整段源码），
单个 `line` 装不下；只按 `(file, line, code)` 等值匹配会把它判成全错。

**消费者注意：注解与作用域怎么配对。** `load_annotations()` 与 `annotation_scopes()` 各调一次
`annotation_report()`，是**两次独立解析**，两次拿到的 `Annotation` 是不同对象：

* ✅ 只调一次 `annotation_scopes()`，从 `scope.annotation` 取注解——同一次调用里是同一批对象；
* ❌ **不要按 `id()` 配对**：frozen dataclass 每次重建，实测 `0/657` 配上，
  于是静默退回"没有作用域"的回落分支（eval-harness 踩过：657 条会被整批读成"行级锚定行"）；
* ⚠️ 按值（`==`）配对能配上 657/657，但 pycodestyle 上有 **3 组**同一个注解值对应不同
  `expected_lines` 的歧义（`#: E252:1:15 E252:1:16` 这类多 token 用例），所以它只是"能用"，不是"正确"；
* 自检：`len(annotation_scopes(...))` 必须等于 `len(load_annotations(...))`，不等就是解析器或过滤坏了。

两个上游 token 不是码，**别喂给 policies 求 rule_id**：

* `code == "Okay"`：上游自己的 token，表示「这一块期望零诊断」。它是**负例**（本次 89 条），
  请当「期望空白」处理；
* `noeol`：上游指令（跑之前先 rstrip 掉块尾换行），**不产出注解**，只进 skipped 计数（本次 7 条）。

`corpus_files(dataset_id, *, root)` 返回的是**有 ground truth 的文件**（= 注解出现过的文件），
不是「目录下所有 `.py`」：bandit 的 `examples/` 有 94 个 `.py`，只有 33 个带上游行级期望；
把没标注的文件也当「期望空白」，会把该工具的正常诊断整批算成误算之外的**误报**。

## 6 结构自检（不通过即退出 1，禁止降级）

```text
python tools/eval_corpus.py --annotations bandit-functional     # 末行必须打印 self-check : ok
python tools/eval_corpus.py --annotations pycodestyle-testsuite # 同上
python tools/eval_corpus.py --verify                            # 每个数据集都跑一次
python -c "import importlib.util,sys,pathlib; s=importlib.util.spec_from_file_location('eval_corpus','tools/eval_corpus.py'); m=importlib.util.module_from_spec(s); sys.modules['eval_corpus']=m; s.loader.exec_module(m); print(m.structural_self_check('bandit-functional', root=pathlib.Path('.tmp/eval-corpora')))"
```

判据（每一条都要求成立，任一不成立就打印失败行并以退出码 1 结束）：

1. `line > 0` 的注解：作用域必须是合法闭区间（`1 <= scope_start <= scope_end`）；
2. `line > 0` 的注解：**上游给了精确位置的每一条**，换算出的绝对行必须落在该块自己的
   `[scope_start, scope_end]` 内；
3. `line > 0` 的注解：作用域末端不得超过目标文件的行数；
4. `line == 0`（文件级）的注解：作用域必须是**零作用域 `[0, 0]`**，且 `expected_lines` 必须为空；
5. 零作用域 `[0, 0]` **只对 `line == 0` 合法**——带行号的注解给出 `[0, 0]` 一律判失败；
6. 目标文件必须存在、且在语料根之内，锚定行不得超过文件行数。

注意：锚定行（`line`）**不要求**落在作用域内——pycodestyle 的锚定行就是 `#:` 那一行，
而期望作用的是它之后的块，两者天然相差一行。要求锚定行在域内会把正确解析判成错误。

**为什么第 4/5 条要写这么细**：这个仓库曾经把 `[0, 0]` 一律判成「非法闭区间」，
于是**文件级注解整批被丢弃**（实测 pydocstyle-testcases `kept=0 / skipped=72`、
pep8-naming-testsuite 少 11 条）——那不是"严格"，那是把契约明确允许的一种形状吃掉。
现在 `[0, 0]` 是**合法**取值，但它只挂在文件级注解上，行级的强度一个字没放松。

**自检仍然会红**（用四个桩数据集实测，桩在 `.tmp/line0-test/`，不属仓库内容）：

| 桩 | 期望 | 实测 |
| --- | --- | --- |
| `line == 0` + 零作用域 | 保留，自检通过，退出 0 | annotations=1（file-level 1 / line-level 0），`self-check : ok` |
| `line = 3` + 零作用域 `[0, 0]` | 自检失败，退出 1 | `D200 target/a.py:3: 零作用域 [0, 0] 只对文件级注解（line == 0）合法；带行号的注解必须给出真实闭区间` |
| `line = 3` + 作用域 `[3, 3]` + 精确位置 `9` | 自检失败，退出 1 | `E501 target/a.py:3: 精确位置 9 落在作用域 [3, 3] 之外` |
| `line == 0` + 零作用域 + 精确位置 `2` | 自检失败，退出 1 | `D205 target/a.py:0: 零作用域 [0, 0] 上不许挂精确位置 [2]（文件级期望没有行号）` |

### 6.1 红样例：证明这两个修复是**承重**的（AGENTS 第 45 条）

上面的判据只能证明"现在是对的"，证明不了"坏了会红"。所以按第 45 条做**显式变异**：
把 `tools/eval_corpus.py` 复制到 `.tmp/self-proof/`，在副本上把某一处改回去 → 读数必须变红 →
撤回变异（重新写入原文件内容）→ 必须变绿。**变异本身也做断言**（`assert mutated != pristine`）：
变异没生效就不算"红了"。

复现：

```text
python .tmp/self-proof/mutate.py        # 两个变异：apply -> 红 -> restore -> 绿，全部自断言
python .tmp/self-proof/consistency.py   # 第 5.0 节的五条恒等式
```

实测（2026-10-07）：

| 变异 | 锚点 | 变异后（红） | 撤回后（绿） |
| --- | --- | --- | --- |
| M1 关掉点作用域归一化 | `and scope.scope_start == scope.scope_end` → `and False` | 被读成文件桶的 `line > 0` scope = **215**（扣掉 `Okay` 负例后 **200**） | **15**（扣掉 `Okay` 后 **0**） |
| M2 关掉 `[0, 0]` 文件级哨兵的放行 | `if scope.scope_start == 0 and scope.scope_end == 0:` → `if False:` | pydocstyle-testcases `kept=0` / `self_check_failures=72` | `kept=72` / `self_check_failures=0` |

```
[OK ] M1 关掉点作用域归一化
       变异后 误判成文件桶的 line>0 scope（原始 / 扣掉 Okay 负例） = (215, 200)
       撤回后 误判成文件桶的 line>0 scope（原始 / 扣掉 Okay 负例） = (15, 0)
[OK ] M2 关掉 [0,0] 文件级哨兵的放行
       变异后 pydocstyle kept / self_check_failures = (0, 72)
       撤回后 pydocstyle kept / self_check_failures = (72, 0)

红样例全部成立: True
```

**这两条红样例覆盖不到什么**（照第 45 条写清）：

* M1 只驱动"语料层输出的 `expected_lines`"这一条路径；它**不覆盖** `tools/governance_eval.py`
  的 `position_bucket` 之后的行为——那边要不要改成按 `[0, 0]` 判文件桶，是 harness 自己的口径决定；
* M2 只覆盖 `_self_check` 对 `[0, 0]` 的放行；它**不覆盖**"上游期望指向的目标文件不存在 /
  行号越界"那两条（bandit 的 2 条上游漂移），那两条走的是 `skipped` 通道，不是自检；
* 两个变异都是**单点文本替换**，覆盖不到"三桶口径变了但自检还是绿的"这类跨组件漂移——
  那要靠第 5.0 节的五条恒等式，而不是自检。

## 7 实测读数（2026-10-07；命令见下）

复现命令：

```text
python tools/eval_corpus.py --list
python tools/eval_corpus.py --annotations bandit-functional
python tools/eval_corpus.py --annotations pycodestyle-testsuite --json
```

### 7.1 总量

| 数据集 | revision | 注解 | 文件级 | 行级 | 文件 | lock 覆盖文件 | skipped | 结构自检 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bandit-functional | `68ebe11e…` | 46 | 0 | 46 | 33 | 132 | 2 | ok |
| pycodestyle-testsuite | `f39d0999…` | 657 | 0 | 657 | 42 | 45 | 7 | ok |
| pep8-naming-testsuite | `1587bfe4…` | 43 | 11 | 32 | 14 | 14 | 0 | ok |
| pydocstyle-testcases | `8d0cdfc9…` | 72 | 72 | 0 | 12 | 18 | 0 | ok |
| tryceratops-samples | `ca149be9…` | 63 | 0 | 63 | 15 | 32 | 0 | ok |
| flake8-logging-tests | `ee5d482b…` | 0 | 0 | 0 | 0 | 2 | 0 | ok |
| isort-tests | `92c56855…` | 0 | 0 | 0 | 0 | 63 | 0 | ok |
| pyflakes-messages | `9f0a7f9c…` | 0 | 0 | 0 | 0 | 16 | 0 | ok |

后三个数据集的 `load_annotations()` 返回空列表：它们的期望是**片段级**的（在测试代码里就地断言），
既不产出行级标注也不产出文件级标注。它们仍然有 lock、仍然过 `--verify`（文件完整性与 sha256 成立），
但**不向 harness 提供任何 ground truth**——引用它们时必须说清这一点，别把「有 lock」读成「有标注」。

* 本目录自带的两个数据集里 `line == 0`（文件级）的条数都是 **0**：上游都给到了行粒度；
  其余数据集的文件级/行级拆分见上表，**两列不许相加成一个数**（见 5.1）。
* 八个数据集合计 **881 条注解 = 文件级 83 + 行级 798**，skipped 9（bandit 2 条上游漂移 + pycodestyle 7 条 `noeol` 指令）。
* pycodestyle：479 个 case（= 上游 `get_tests()` 的 case 数，逐条对得上），657 条注解，
  其中 89 条是 `Okay` 负例、333 条带精确位置（分布在 272 个 case 上），作用域跨度 1–425 行。
* bandit：46 条的 scope 全部退化成点（`scope_start == scope_end == line`），因此 46 条全部带精确位置。
* 位置桶（harness 的 `position_bucket` 口径，实测于归一化之后）：
  bandit 46 line / 0 scope / 0 file；pycodestyle 272 line / 370 scope / 15 file（那 15 条是**单行 `Okay` 负例**，
  它们是负例控制、不是正例期望）；pep8-naming 32/0/11；tryceratops 63/0/0；pydocstyle 0/0/72。
* 一次独立对账：用**不依赖上游 `get_tests()` 的朴素行扫描**（按真实行号扫 `#:`）重建
  `(码, 绝对行)` 多重集，与本解析器**完全相等**（479 case / 657 条，逐文件零差异）。

### 7.2 与平台已声明码的交集

平台的码集从 `policies/**/*.yaml` 的 `rule.style_lint.codes` 读出（不另写映射表）：
**34 个 S 码 / 11 个 E 码**。

| 数据集 | 命中平台已声明码 | 能力外码 | 负例(`Okay`) |
| --- | --- | --- | --- |
| bandit-functional | 22 条（17 个 S 码） | 24 条（23 个 B 码） | 0 |
| pycodestyle-testsuite | 71 条（**11/11 个 E 码全部命中**） | 497 条（66 个 E/W 码） | 89 |

bandit 侧**平台已声明但这份语料一条都没命中**的 17 个码：
`S102 S301 S302 S303 S307 S308 S310 S311 S312 S313 S314 S315 S316 S317 S318 S321 S323`。

### 7.3 按 rule_id 的可用标注条数（样本量诚实）

17 条纯 S 码规则（bandit-functional）：

| 规则 | 级别 | 码 | N |
| --- | --- | --- | --- |
| SEC-001 | error | S102, S307 | 0 |
| SEC-002 | error | S301, S302 | 0 |
| SEC-003 | error | S303, S324 | 1 |
| SEC-004 | error | S105, S106, S107 | 3 |
| SEC-005 | error | S323, S501 | 1 |
| SEC-006 | error | S506 | 1 |
| SEC-007 | error | S602, S605, S609 | 6 |
| SEC-008 | error | S608 | 1 |
| SEC-009 | error | S313–S318 | 0 |
| SEC-010 | error | S310 | 0 |
| SEC-011 | error | S311 | 0 |
| SEC-012 | warning | S308, S611, S701 | 3 |
| SEC-014 | error | S113 | 2 |
| SEC-015 | error | S110, S112 | 2 |
| SEC-019 | error | S104 | 1 |
| SEC-021 | error | S312, S321 | 0 |
| SEC-022 | warning | S612 | 1 |

合计 22 条；`N = 0` 的有 **6 条**：SEC-001 / SEC-002 / SEC-009 / SEC-010 / SEC-011 / SEC-021。
这 6 条规则在这份语料上**没有任何可用于计算精确率/召回率的标注**——它们的读数只能是
`insufficient_sample`，不许报成 0% 或 100%。

10 条纯 E 码规则（pycodestyle-testsuite）：

| 规则 | 级别 | 码 | N |
| --- | --- | --- | --- |
| STYLE-001 | warning | E501 | 19 |
| STYLE-003 | warning | E401 | 1 |
| STYLE-004 | warning | E402 | 3 |
| STYLE-006 | error | E711 | 8 |
| STYLE-007 | error | E712 | 8 |
| STYLE-008 | warning | E713, E714 | 8 |
| STYLE-009 | error | E721 | 11 |
| STYLE-010 | error | E722 | 3 |
| STYLE-011 | warning | E731 | 3 |
| STYLE-012 | warning | E741 | 7 |

合计 71 条；`N = 0` 的 **0 条**。

### 7.4 文件面

| 数据集 | 有 ground truth 的文件 | 至少命中一个平台已声明码 | 纯能力外 |
| --- | --- | --- | --- |
| bandit-functional | 33 | 15 | 18 |
| pycodestyle-testsuite | 42 | 8 | 34 |

## 8 上游自身的不一致（**不是**我方解析失败）

上游在本次钉死的 revision 里，自己带的 2 条 `Location:` 指向不可用的目标。本工具**不猜、不钳位**，
把它们记进 `skipped` 并计数。原文逐字如下：

**(1) `bandit/plugins/pytorch_load.py:26-32` 指向一个不存在的文件**

```text
        >> Issue: Use of unsafe PyTorch load
        Severity: Medium   Confidence: High
        CWE: CWE-502 (https://cwe.mitre.org/data/definitions/502.html)
        Location: examples/pytorch_load_save.py:8
        7    loaded_model.load_state_dict(torch.load('model_weights.pth'))
        8    another_model.load_state_dict(torch.load('model_weights.pth',
                map_location='cpu'))
        9
```

同一个归档里 `examples/pytorch_load_save.py` **不存在**（`examples/` 下只有 `pytorch_load.py`）。
对应 `skipped` 条目：`target_missing | B614 examples/pytorch_load_save.py:8（声明于 bandit/plugins/pytorch_load.py）`。

**(2) `bandit/plugins/exec.py:17-21` 指向一个越界的行号**

```text
    >> Issue: Use of exec detected.
       Severity: Medium   Confidence: High
       CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
       Location: ./examples/exec.py:2
    1 exec("do evil")
```

`examples/exec.py` 全文只有 1 行（`exec("do evil")`），**没有第 2 行**——上游自己的示例块都只印了第 1 行。
对应 `skipped` 条目：`target_line_out_of_range | B102 examples/exec.py:2（该文件只有 1 行；声明于 bandit/plugins/exec.py）`。

**这两条不参与 `--verify` 的判定**（否则 verify 会永久红，于是没人再看它——那才是真正的静默）。
它们由 `--list`（`skipped` 明细）、`--annotations`（`skipped:` 段）与 `--verify`（`NOTE` 行，不参与退出码）三处显式打印。

## 9 这份语料**不能**证明什么

* **`tests/functional/test_functional.py` 里没有行级 oracle。** 实测（`ast` 遍历全部 935 行）：
  它的 `expect` 字典只有 `{"SEVERITY": {...}, "CONFIDENCE": {...}}` 两级**计数**，例：

  ```python
  def test_crypto_md5(self):
      expect = {"SEVERITY": {"UNDEFINED": 0, "LOW": 0, "MEDIUM": 16, "HIGH": 9},
                "CONFIDENCE": {"UNDEFINED": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 25}}
      self.check_example("crypto-md5.py", expect)
  ```

  全文件只有 1 个 `"B201"` 字面量（在 `test_baseline_filter` 的 JSON 夹具里）和 2 处
  `profile={"exclude": ["B308"]}`；`examples/*.py` 里也只有 4 行 `# B704` 注释。
  因此「（示例文件, 行号, B 码）」这个 oracle **在那里不存在**——方案 §4.5 第一行的描述是错的。
  这份计数**不能**当行级 oracle 用：它的 SEVERITY/CONFIDENCE 分级与 ruff 的 S 码集不同构，
  拿它对齐行级 P/R 只会把「工具分级口径差异」算成平台的账，噪声大于信息。它顶多做**文件级聚合**。
* 按码的样本量极不均衡（第 7.3 节）：bandit 侧 6 条规则 N=0、SEC-007 一条占 6/22。
  在这份语料上算出来的「精确率/召回率」只对**被标注到的码**成立，且小 N 的码必须带区间或直接标 `insufficient_sample`。
* 只有 L1（实现保真度）：它说明平台的判定与所声明证据工具的口径一致，**不说明**这条诊断值得报；
  也不测缺陷真假、不测规则之外有没有漏。
* 与上游工具的口径差异**不是平台的账**：bandit 的 B 码与 ruff 的 S 码只是同号，判定范围并不逐条相同。
* 语料是**英文 Python 代码**，覆盖不了「非 Python 目标」「中文语境」这两类问题。

## 10 许可与「哪些语料不入库」

| 数据集 | 许可 | 许可原文（实测） | 入库？ |
| --- | --- | --- | --- |
| bandit-functional | Apache-2.0 | `LICENSE`（10142 字节，首行 `Apache License / Version 2.0, January 2004`） | 否，运行期取到 `.tmp/` |
| pycodestyle-testsuite | MIT/Expat | `LICENSE`（1254 字节，`Licensed under the terms of the Expat License`） | 否，运行期取到 `.tmp/` |

仓库只提交 `evaluation/corpora/*.lock.json`（路径 + sha256 + 大小 + 上游 revision + 许可元数据），
**不提交任何上游原文**。GPL / LGPL / `license: other` 的语料（pylint、semgrep、AgentHarm 等）
同样只在运行期取用到 `.tmp/` 下，不得分发、不得入仓；它们与平台码集的交集见
[eval-datasets.yaml](../docs/project/engineering-policy-platform/testing/eval-datasets.yaml)。

## 11 谁能读 / 维护纪律

* **读者**：任何人都可以读 lock 与 `--annotations --json` 的读数；`--json` 载荷带
  `schema_version`（= `tools/eval_corpus.py` 的 `ANNOTATION_SCHEMA_VERSION`）。
  两个版本轴各自独立：注解记录形状轴 `ANNOTATION_SCHEMA_VERSION`、lock 轴 `LOCK_SCHEMA_VERSION`
  （AGENTS 第 55 条：形状变一个字都要动它）。
* **换 revision 是显式动作**：改 `tools/eval_corpus.py` 里的 `BANDIT_REVISION` /
  `PYCODESTYLE_REVISION` → `--fetch` → `--record-lock` → 把 lock 的 diff 送评审。
  `--verify` 会同时比对 lock 里的 `revision` 与登记表，对不上就报「上游 revision 漂移」。
* **跨 revision 的数字不许直接比较**；每个读数都要带 `reading_context`（哪棵树 / 哪个环境 / 哪套声明），
  与 `docs/project/engineering-policy-platform/testing/governance-value-eval-plan.md` 第 6.5 条同一条纪律。
* 语料根 `.tmp/eval-corpora/` 是构建产物，可以随时删掉重取（`python tools/cleanup.py`）。
