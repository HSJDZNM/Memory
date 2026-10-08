# AB 测量仪器（task-12）：六个量、独立性、自证

> 交付物：`tools/ab_measure.py` + 本文件。第二个人照着本文的命令可以逐条重算所有数字。
> 本文所有读数都是**实测**；测不到的写 unavailable 并写明原因，**不估计、不猜测**。

## 0. 冻结与引用纪律（先读这一节）

`tools/ab_measure.py` 在本次交付期间是**移动目标**（渐进写盘）。因此：

| 项 | 值 |
| --- | --- |
| 冻结时间戳 | **2026-10-07T20:43:32+08:00** |
| 字节数 | **134417** |
| sha256 | **`57E2AA27AB557E48765817CB711846E4676C988138F1B1CC16461E474F3A609E`** |
| 载荷 schema_version | **1.1**（1.0 → 1.1：见下面的「版本沿革」） |

**版本沿革（旧指纹一律作废，含 132173 B / `40BD64F6…` 那一版）**：

| 指纹 | 时刻 | 为什么变 |
| --- | --- | --- |
| 132173 B / `40BD64F6…` | 20:30:54 | 首次冻结（V-1..V-4 修完） |
| **134417 B / `57E2AA27…`** | **20:43:32** | **红队抓到一条读数错误**：一次真跑了 2136 条用例、`exit_code=1` 的运行，因为输出里出现 `INTERNALERROR` 文本被**优先**判成 `environment_unavailable` ⇒ 同一份载荷同时写着「2132 passed」与「一次都没跑起来」。修法=**先看证据（exit_code + 逐用例条数）再看文本** + 一致性守卫；新增三个键 ⇒ 按 AGENTS 第 55 条把 `schema_version` 显式升到 **1.1** |

**为什么这次没有沿用「冻结优先」**：上一版用冻结挡住的是**缺功能**（`block_class` 分类）；这一版要挡的是**错误读数**。
一份自己都不信自己的载荷会直接污染 A/B 结论，代价高于作废一个哈希。取舍权仍在 lead——新指纹与新读数都在这里。
| 文本规范 | `python tools/check_text_conventions.py` → 检查 563 个文本文件（含本文件），问题 0 处（exit 0） |

**此前的任何读数一律作废**（含 12:20:27Z / 12:22:16Z / 12:24:32Z / 12:25:38Z 各版本）。
本文第 5 节的读数都取自上面这个指纹的版本。

复现指纹的命令（第二个人可逐字重跑）：

```powershell
Get-FileHash tools/ab_measure.py -Algorithm SHA256 | Select-Object -ExpandProperty Hash
(Get-Item tools/ab_measure.py).Length
```

---

## 1. 它是什么 / 怎么跑

**一个工具、一个 JSON**（不拆成多个脚本；写域只允许 `tools/ab_measure.py` 一个文件）。

```powershell
# 六个量全跑（本仓）
python tools/ab_measure.py --tree . --out .tmp/ab-measure/repo-all.json

# 只跑不需要外部输入的两个量
python tools/ab_measure.py --tree . --mode scan,security --out .tmp/ab-measure/repo.json

# 仪器自证（配置隔离 + 敏感性变异 + 独立性变异）
python tools/ab_measure.py --self-check --out .tmp/ab-measure/selfcheck.json

# 改动行口径（外部任务树的基线是归档、不一定有 .git ⇒ 这条是**主路径**，不是备选）
python tools/ab_measure.py --tree <arm_tree> --baseline-tree <baseline_tree> --mode scan,security

# 反事实精确率（被拦下的编辑在隔离子树里重放）
python tools/ab_measure.py --tree <tree> --baseline-tree <base> ^
    --blocked-edits <blocked.jsonl> --mode blocked --deterministic
```

**退出码**（与仓库既有工具同型：0/1 是"仪器说话了"，2 是"仪器拒绝说话"）：

| 码 | 含义 |
| --- | --- |
| 0 | 跑完，每个请求的量都 available 且没有 red |
| 1 | 跑完，但有 `unavailable` 或 red；顶层 `exit_reasons[]` 逐条说明是哪个块 |
| 2 | **用法 / 配置错误，拒绝运行、不产出读数**（缺 `--tree`、未知 mode、树不存在、JSONL 非法……） |

实测（冻结版本）：

```
PS> python tools/ab_measure.py --help        # exit 0，59 行 usage + options（非空）
PS> python tools/ab_measure.py               # exit 2
ab_measure: 缺 --tree <DIR>（或 --self-check）
PS> python tools/ab_measure.py --self-check  # exit 0，all_passed = true
```

---

## 2. 六个量的定义（分子 / 分母 / 位置匹配 / 口径不同怎么记 / 命令）

### 2.1 规范性 —— `scanner`

| 项 | 口径 |
| --- | --- |
| 分子 | 冻结配置下 ruff 的 finding 条数（**不含**"没能分析这个文件"的解析错误） |
| 分母 | 同一批被扫描 `*.py` 的**物理行数**（含空行与注释）÷ 1000 = KLOC |
| 位置匹配 | `(树内相对 POSIX 路径, code, 行号)` 三元组；**列只记录不参与匹配**；行号 1-based；跨行 finding 取起始行；**没有 ± 容差** |
| 口径不同怎么记 | 三个口径**分别报、不许混**：`counts_by_code_changed`（行级交集，主）/ `counts_by_code_touched_files`（整文件）/ `counts_whole_tree`（终态整树）。差额本身就是要读出来的量 |
| 命令 | `ruff check --config <.tmp 冻结 toml> --output-format json --no-cache --no-respect-gitignore --quiet <逐文件>` |

**冻结配置（内嵌在工具里，不读被测树、不读仓库）**：

```toml
line-length = 88
target-version = "py311"
[lint]
select = ["E", "W", "F"]
```

**为什么它独立于策略层**：不读 `policies/**`、不用 `validation/ruff.toml`、不读平台的
Decision / violation / severity。**为什么它不独立于底层 linter**：它和平台用的是**同一条 ruff 二进制**。
这两句写在载荷的**每一个块**里（`homology`），不许只写一次了事。

**三个必须写下来的口径差**：

- `line-length = 88`（上游默认）**不是**本仓库 `validation/ruff.toml` 的 100 ⇒ 本仓 7,745 条里
  **E501 占 7,288 条（94.1%）**，绝大多数是"88 列口径"而不是"真的有问题"。**绝对水平不可跨口径比较，
  只有两臂同口径的差可读**；
- 冻结选择是 `E,W,F` 的**上游基线**，是本仓 `select` 的**超集**；平台刻意排除的码（如 `W605`）
  在本仪器里**照样报**——这正是"独立"的可核查形态；
- 冻结选择之外的码**看不见** ⇒ 绝对数是**结构性低估**（载荷里 `recall_limit` 写明）。

### 2.2 安全性 —— `security`

**路线 A（独立扫描器，优先）**：探测 `bandit` / `semgrep`：`--version` 起不来即记
`present: false` + reason。**本机实测两者都不存在**（PyPI 实测不可用，lead 复测 18 分钟零输出），
载荷里 `route_a.route_a_verified = false` —— 这条分支**从未被执行过**，这句话本身写进载荷。

**路线 B（回退，本机唯一可得）**：ruff 的 `S` 族（冻结 `ab-sec-freeze/1`）+ **自写标准库 AST 检查器**
（`ABSEC-001..010`，无依赖）。**它弱在哪（必须写在结论旁）**：ruff 的 S 族是 bandit 检查的**子集重实现**，
无 taint、无跨函数数据流、无跨文件；自写 AST 检查器是**第二实现而非第二独立检查**（共享 CPython `ast`，
且**没有被任何外部 oracle 校准**）；**依赖漏洞（pip-audit / OSV）完全测不了**（无网、无本地漏洞库）。
⇒ 安全性是**下界**，不是覆盖率。

| 项 | 口径 |
| --- | --- |
| 分子 | 路线 A 可用时用它；否则 = `ruff_S + ab_ast` 两条之和 |
| 分母 | 同 2.1 的 KLOC |
| 分档 | `by_instrument_band` 是**仪器自己**的分档（**不是**上游 ruff/bandit 的 severity），**也不是阻断力** |
| 命令 | 路线 A：`bandit -r -f json -q <tree>`；路线 B：同 2.1 但配置为 `select=["S"]` + 进程内 AST 走查 |

### 2.3 可用性 —— `usability`

外部 oracle，**完全不经过平台与 linter**（同源等级 `externally_independent`）。

| 子量 | 分子 / 分母 | 命令 |
| --- | --- | --- |
| 回归 | 声明的 `pass_to_pass` 中**仍在逐用例结果里且 outcome=passed** 的条数 / 声明条数（Wilson 95%） | `<python> -m pytest ... -p abmeasure_report` |
| 目标修复 | `fail_to_pass` 中 outcome=passed 的条数 / 声明条数 | 同上 |
| 可导入性 | `ok` 的顶层包数 / 探测的包数 | `<python> -c "import <pkg>"`（每包一个子进程） |
| 公开 API | 基线里有、现在没有的模块/名字（**移除 = 破坏性变更**） | 进程内 `ast` 抽取，需 `--api-baseline` |

**三态（与 ab-protocol §1.4 一致）**：`ok` / `red` / `environment_unavailable`。
判定写死：`INTERNALERROR` → environment_unavailable；**pytest 退出码 2/3/4/5 → environment_unavailable**
（**仪器没跑起来，不是被测对象的红**）；只有收集期错误（`collection_errors` 非空）才在退出码 5 时判 red；
`counts.total == 0` 且退出码 0 → environment_unavailable。
**"声明了却没被收集到" = `missing`，不算通过。**

两个实测踩到的坑（都写进代码注释）：
- `-p no:cacheprovider` 会摘掉 cache provider，被测树 `pytest.ini` 里的 `cache_dir` 就变成
  "Unknown config option" → **pytest 退出码 4**。本仓实测原话：`ERROR: Unknown config option: cache_dir`。
  修法：树里声明了 `cache_dir` 就保留插件并 `-o cache_dir=<.tmp>`，没声明才摘掉；
- 把 `WinError 5` / `PytestCacheWarning` 当成 `INTERNALERROR` 会把一次**真的跑通**（2 passed、
  pass_to_pass 2/2 绿）打成 environment_unavailable。修法：只有 pytest 自己喊 `INTERNALERROR` 才算；
  磁盘告警单列 `disk_warnings`（本机确实有，属环境问题）；
- **（红队实测，2026-10-07 修，本版最重要的一条）「先看证据，再看文本」**：一次**真跑了 2136 条用例、
  `exit_code=1`** 的运行（原件 `.tmp/ab-measure/recheck.json`，run `93f2a560`），因为输出里出现
  `INTERNALERROR` 文本，被旧版**优先**判成 `environment_unavailable`。后果不是措辞难看，而是
  **同一份载荷自相矛盾**：它一边写着 `counts = {total: 2136, passed: 2132, failed: 3}`，
  一边说"没有任何一次 pytest 真的跑起来"。红队用「一个 run id + 同一个嵌套对象」排除了"混看两次运行"。
  修法三条：
  1. **判据顺序改成"证据优先"**：`逐用例条数 > 0` 才是"跑起来了"的判据；退出码是分类的**权威**；
     `INTERNALERROR` 文本只在**它自己那条路**（退出码 2/3/4 或逐用例为空）里起作用，且原文另存
     `internal_errors[]` + `internal_error_source`（stdout / stderr），由读的人自己看；
  2. **一致性守卫**：`exit_code ↔ counts ↔ 措辞` 三者必须互相蕴含；不自洽时**不给结论**——
     `pytest_status` 退回 `environment_unavailable`、reason 写"分类不可信，本块不给结论"，
     并给出不自洽的具体三个值。**宁可说"我不可信"，也不产出自己都不信自己的读数**；
  3. **块级断言的措辞跟着证据走**：只有`逐用例结果总和 == 0`才准说"没有任何一次真的跑起来"；
     否则改说"跑出了 N 条结果，但分类不可信 / 环境不可用 ⇒ 不给可用性结论"。
  ⇒ 载荷 `schema_version` **1.0 → 1.1**（新增 `classification_trustworthy` / `internal_errors` /
  `internal_error_source` 三个键，按 AGENTS 第 55 条显式升版）。

  **回归见证**（本机实测，`.tmp/ab-fix`）：一个用例往真实 stdout 写 `INTERNALERROR> …`、另一个用例 `assert False`：
  `pytest_status = red` / `classification_trustworthy = true` / `internal_error_source = stdout` /
  `internal_errors = 1` / exit 1 / `{total: 2, failed: 1, passed: 1}`。
  **旧版会判成 `environment_unavailable`**（文本压过证据），新版按退出码判 red 并把文本另存。

### 2.4 精确 —— `block_precision`（反事实）

**为什么不是人评**：被拦下的编辑在隔离副本里**重放**，看**独立仪器**会不会红。判据预注册（跑之前写死）：

1. 逐文件 `(code, message)` **多重集增量**（主判据，**对行号漂移稳健**）；
2. `--with-tests` 时 `pass_to_pass` 出现新的红。

| 项 | 口径 |
| --- | --- |
| 分母 | **可重建**的被拦编辑条数；**抽样单位 = edit**，不是 finding / 文件 / run |
| 分子 | 判红（TP）的条数 |
| 位置匹配 | 主判据用 `(code, message)` 多重集（不依赖行号）；**行级口径单列两个数**：`rows_added_raw`（直接比 `(row, code)`，**对漂移敏感**）与 `rows_added_shift_aware`（用 diff 的 equal 块把 after 行号回映射到 before 再比） |
| 不可重建 | `reconstructible=false`（`old_string` 不唯一 / 找不到 / patch 应用失败）→ `unreconstructible`，**不进分母**，单独列 |
| 四个计数 | `counts = {TP, FP, unreconstructible, unverifiable}`（协议可以只用计数、不给比率） |

**为什么这不是自证**：判据里**没有**平台的 Decision / violation / severity / treatment_record。
标签只来自冻结配置的 ruff、自写 AST 检查器与 pytest。

实测（@.tmp/ab-demo/@ 两棵树、两条编辑）：

```
CHANGED {"F401": 1} {"F401": 1} whole {"F401": 1}
PRECISION {"FP": 1, "TP": 1, "unreconstructible": 0, "unverifiable": 0} denom 2 precision 0.5 [0.094531, 0.905469]
  E1-unused-import red [{'code': 'F401', 'extra': 1, ...}] 1 1
  E2-comment-only green [] 0 0
```

### 怎么读一条 red（证据通道）—— 红队 S3 的正面回答

一条 @@outcome = red@@ 的 edit **不一定**在 @@new_findings@@ 里有东西：证据可能在 @@new_security@@ 通道。
两条通道**任一非空即判红**（@@--with-tests@@ 时还有第三条：@@counterfactual_tests@@）。
**最小复现**（本机实测，冻结版本）：

@@@
C1-security-only  outcome red | new_findings 0 | new_security 2 | raw 0 | shift_aware 0
                  new_security = [('ABSEC-001', 1), ('S307', 1)]
@@@

⇒ 读的人看到 @@red + new_findings: []@@ 时**不要**先怀疑"红得没证据"：**去 @@new_security@@ 找**。
（红队 S3 提的 @@evidence_channels@@ 键**我没有加**——加键要升 @@schema_version@@，会作废 §0 的冻结指纹；
通道信息本来就**可从既有键推出**，所以这里用文档消解，不用载荷变更消解。）

### 两个行级副口径**只覆盖 norm 通道**（红队 S2：诊断驳回，口径补充接受）

@@rows_added_raw@@ 与 @@rows_added_shift_aware@@ **都只读 @@before["norm"]@@ / @@after["norm"]@@**，
**不读安全通道**。红队据 @@fp-01@@（@@raw = 1@@、@@shift_aware = 0@@、唯一发现在 @@new_security@@）推断
"两个数覆盖的通道不同、差额里混进了通道覆盖差"——**这个诊断不成立**。最小反例（本机实测）：

@@@
C1-security-only  outcome red | new_findings 0 | new_security 2 | raw 0 | shift_aware 0   <- 只有安全通道有发现
C2-shift-only     outcome green | new_findings 0 | new_security 0 | raw 1 | shift_aware 0 <- 纯行漂移
@@@

- C1：**只有**安全通道新增两条，@@raw = 0@@ ⇒ security 发现**不**进这两个数；
- C2：norm 通道一条既有 E501 被整体下移一行，@@raw = 1@@（假新增）、@@shift_aware = 0@@（回映射认出来了）⇒ 正是 M-4① 的修法。

⇒ 红队 @@fp-01@@ 的 @@raw = 1@@ 只能来自**它自己那次编辑里的 norm 通道行漂移**，不是来自安全通道。
**但"口径没写清"这半句我接受**：原说明没写"只覆盖 norm 通道"，已在上文补上。差额仍然要读，
只是它读的是"**norm 通道里有多少假新增**"，不是"两个通道覆盖不同"。

**两条主动写下的局限**：
1. 分母是"可重建子集"，可能**系统性偏向**某类编辑（整文件替换比小改更容易重建）；
2. 它只测 **precision**，不测 recall；`--allowed-edits` 只给 **recall 代理下界**
   （两个集合不是同一个总体，不能与 precision 互补，**永远不写成 recall**）。

**上界与阳性对照（红队 M-4②）**：因为标签来自同一条 ruff 二进制，`precision` 的上界其实是
"**与独立仪器配置的一致率**"，不是"这次 block 是否真的对"。载荷里 `label_semantics` 写死了这句。
要暴露天花板，用 `--known-false-positive-edits <jsonl>` 跑**阳性对照**：已登记为误报的编辑里仪器仍判红的
比例 = `max_achievable_precision`。**对照结论不许算进 A/B 的分子分母。**

### 2.5 高效 —— `efficiency`

| 子量 | 口径 |
| --- | --- |
| 单次判定延迟 | `--latency-cmd '<argv JSON>' --latency-repeats 30`；**剔首个冷启动**并把 `cold_start_ms` 单列；**最近秩法**分位数（不插值）：`ceil(p/100*n)` 号样本；`n` 与全部样本都写出来 |
| 每任务 wall-clock 增量 | 同 `(task_id, replicate)` 配对、按臂取差；报中位数 / p25 / p75 / **配对符号检验**（精确二项、双尾、零差丢弃并计数） |
| 重试次数 | run 记录的 `counts.retries`；定义写死为"同一 task 内上一次被拦之后产生的下一次同类写动作尝试" |

**拒绝项**：没给 `--latency-allow-side-effects` 就**拒绝重复跑**（在可能有副作用的入口上重复 30 次，
测量本身就会干扰被测树）。eval-harness 实测 `entry.side_effect_free = false`（入口会写
audit.jsonl 与 enforcement-ledger）⇒ **本机对真实入口的延迟读数必须是 unavailable**，除非每次都换一棵新臂树。

### 2.6 全自动化 —— `automation`（**操纵检查，不是结局变量**）

| 子量 | 分子 / 分母 |
| --- | --- |
| 受治理写动作覆盖率 | `governed_write_actions / write_actions`（Wilson 95%） |
| bypass 次数 | `governance_status ∈ {bypassed, unauthorized_write}` 的条数（字段缺失 → **unavailable**，不写 0） |
| 人工介入次数 | run 记录 `counts.human_interventions` 的条数；`human_interventions_detail[].kind` 分类 |

**红线**：off 臂 `governed_write_actions = 0`、`human_interventions = 0` 是**构造出来的**，不是测出来的。
把它当价值证据就是拿处理变量冒充结局变量。载荷 `role = "manipulation_check"`，块的 `caveat` 写死这句。

---

## 3. 独立性：实测证据与已知局限

| 主张 | 可核查的证据 |
| --- | --- |
| 不读策略层 | `independence.measured_tree_reads[]` = 本次仪器**自己**打开过的树内路径；`policy_layer_reads` 过滤 `policies/ validation/ knowledge/ registry/ adapters/` —— 实测 **`[]`** |
| 不导入平台代码 | `independence.policy_imports` —— 实测 **`[]`** |
| 不读 `validation/ruff.toml` | `--config <冻结 toml>` 实测能压掉目标树里的配置发现（见 §4）；且删掉策略层后读数逐字节不变 |
| 每个块各自声明同源等级 | `homology` 在 `scanner/security/usability/block_precision/efficiency/automation` 六处各写一次 |

**已知局限（不许掩饰）**：`independent_of_underlying_linter = false`。
规范性与安全回退**共用同一条 ruff 二进制**（同源等级 `half_homologous_same_binary` /
`policy_layer_independent_linter_dependent`）。自写 AST 检查器是 `second_implementation_uncalibrated`。
`measured_tree_reads` **只覆盖仪器自己**打开的文件；ruff / pytest 读什么由 argv 决定，不在清单里——
它不是"平台读过的全集"的证明，只是"仪器没读策略层"的证据。

---

## 4. 自证（AGENTS 第 45 条）：三条预注册判据

命令：`python tools/ab_measure.py --self-check --out .tmp/ab-measure/selfcheck.json`
（本机实测 **exit 0 / `all_passed = true`**；证据文件 `.tmp/ab-measure/<run>/selfcheck-evidence.json`）。

> **注意语义**：这三条里 `red = 自证通过`（仪器有反应 / 没被带走），`green = 自证失败`。
> 写反了会把"仪器是死的"读成"一切正常"。载荷 `note` 里写死了这句。

| 判据 | 预注册内容 | 实测 | 结果 |
| --- | --- | --- | --- |
| 配置隔离 | 树根与 `validation/` 各放诱饵 `ruff.toml`（`line-length=200`、`select=[]` 或只剩 F401）后，读数里**仍然**出现 E501 与 W291 | `{E501:1, F401:1, W291:1}` | **red = 通过** |
| 敏感性变异 | 注入 F401 + `eval()` 后 `violations_total` 与 `findings_total` **都必须严格增加**，`scanner.red` 从 false 变 true | `(0 viol, 0 sec, red=false) → (1 viol, 1 sec, red=true)` | **red = 通过** |
| 独立性变异 | 删掉 `policies/** validation/** knowledge/**` 后 scanner+security 投影**逐字节不变** | `identical=true`，投影摘要两侧相等 | **red = 通过** |

### 4.1 `git archive HEAD` 副本上的两次变异（真实树，不只是合成树）

脚本：`.tmp/ab-ruffprobe/mutation_proof.py`（临时脚本，只在 `.tmp/` 下）；证据：
`.tmp/ab-measure/mutation-proof.json`。原始输出：

```
archive bytes 12195840
read1 exit 1 norm 6316 sec 6791
read2 exit 1 norm 6323 sec 6792
read3 exit 1 removed ['policies', 'validation', 'knowledge']
SENSIBILITY pass 6316 -> 6323 | sec 6791 -> 6792
INDEPENDENCE pass True
```

- **M-敏感**：往 `src/provenance/origin.py` 注入 `import os` + `eval('1 + 1')` ⇒ 规范性 +7、安全性 +1；
- **M-独立**：删掉三个策略层目录 ⇒ 投影**逐字节相同**。

**重复性说明（不许省略）**：这个证据是**两次**变异、**一棵**树、**三条**判据。它证明不了"仪器在所有树上都
敏感 / 都独立"；它证明的是"这两条性质在本机至少各有一个真实见证"。合成的 `--self-check` 与归档树上的
`mutation_proof` 是两条**不同**的见证（前者带诱饵配置，后者是真实仓库），**都不能外推**。

---

## 5. 本机实测读数（冻结版本，供交叉核对）

命令：`python tools/ab_measure.py --tree . --mode scan,security --deterministic`
（`tree.revision = 208295b66809fd6e9d5e5b5fd01cf2e25d11297a`，**exit 1**：`exit_reasons = [scan:red, security:red]`）

| 量 | 读数 |
| --- | --- |
| 规范化文件数 / 物理行数 | 384 / 140,225 |
| 规范性 violations_total | **7,753**（55.289713 / KLOC） |
| 干净文件率（Wilson 95%） | 0.195312，`[0.15876, 0.2379]` |
| 规范性 counts_by_code TOP5 | E501 7296（94.1%）· E402 127 · F811 96 · F401 92 · E702 44 |
| 解析错误（"没能分析这个文件"） | 2（单列，**不进**分子，文件仍在分母） |
| 安全性 findings_total | **6,954** = ruff_S 6,921 + ab_ast 33 |
| 仪器自定分档 | high 53 · medium 55 · low 2 · unknown 6,844 |
| 主导码 | **S101（assert）6,766 条 = 97.30%** |
| 路线 A | bandit ✗ / semgrep ✗ ⇒ `route_a_verified = false` |

**三条口径警告**（读这些数字之前必须知道）：
1. **E501 口径差**：冻结 88 列 vs 本仓 100 列 ⇒ 7,288 条 E501 里绝大部分是口径产物，不是缺陷；
2. **S101 主导**：安全性总量 97.30% 是 `assert`，而本仓 `validation/ruff.toml` **刻意没有** select S101。
   ⇒ 只看总量会被一个码掩盖，必须与 `by_code` / `by_instrument_band` 一起读（载荷 `dominant_code` 已经写明）；
3. **口径不可互比**：本仪器 384 文件 / 55.24 每 KLOC 与 redteam 的 262 文件 / 44.97 每 KLOC
   **是两套配置、两个分母**，**不许互相比较**，只能各自与自己同口径的前后读数比。

---

## 6. 测不了的东西（逐条 unavailable，不写 0、不近似）

| 量 / 子量 | 状态 | 原因 |
| --- | --- | --- |
| 安全性：路线 A（bandit / semgrep） | **unavailable** | 本机不存在，PyPI 实测不可用；`route_a_verified = false` |
| 安全性：依赖漏洞（pip-audit / OSV / safety） | **unavailable** | 无网、无本地漏洞库；**没有任何回退能测它** |
| 安全性：taint / 跨函数数据流 / 跨文件 | **unavailable** | 路线 B 是 AST 级模式匹配，结构上做不到 |
| 精确：被拦编辑的内容 | **unavailable（等输入）** | 需要 ab-protocol 的 `blocked_edits[]` 或 eval-harness 的 `proposed_edits[]`；没有它分母是空的 |
| 精确：按 `block_class` 分类 | **unavailable（分类未实现）** | 我读不了 `block_class` ⇒ 无法把 `infrastructure_failure` 剔出分母 ⇒ 协议侧按「分母 = 0 ⇒ F6」处理 ⇒ **本轮「精确」的结论是 unavailable，不是「精确率高」**（见 §9 第 9 条） |
| 精确：recall | **只有代理下界** | 需要"被放行但确实坏的编辑"这个总体，两个集合不可交换 |
| 精确：ground truth | **unavailable** | 无资深工程师标注；标签只是"与独立仪器的一致率" |
| 高效：单次判定 p50/p95 | **unavailable（等输入）** | 需要可重复调用的单次判定命令；且真实入口有副作用（eval-harness 实测 `side_effect_free=false`）⇒ 需每次一棵新臂树 |
| 全自动化：人工介入 / 覆盖率 / bypass | **unavailable（等输入）** | 需要 run 记录 JSONL；字段缺失时明确 unavailable 而不是 0 |
| 可用性：本仓全套 pytest | **available（red）** | **2136 条：2129 passed / 6 failed / 1 skipped，exit 1**（见下） |

**本仓全套 pytest 的实测状态（2026-10-07 20:52 起为已重跑完的读数，schema 1.1 / `57E2AA27…`）**：

@@@
block status = available | pytest_status = red | red = True
counts = {total: 2136, passed: 2129, failed: 6, skipped: 1}    exit_code = 1
classification_trustworthy = True     internal_error_source = None     internal_errors = 0
reason = "pytest 退出码 1：6 failed / 0 error / 2129 passed（共 2136 条）"
顶层 unavailable[] = [blocked, automation]      # usable 已不在其中
墙钟 = 482.1 s（我侧）
@@@

**这条读数同时是一次"读数错误被修掉"的实证**：同一棵树、同一条命令，**旧版**把这次运行报成
`environment_unavailable / red = false`（"一次都没跑起来"），**新版**报成 `red` 并把 **6 条真实失败**
摆到台面上。⇒ **红队 ③-b 担心的"真实失败被环境告警吞掉"在这台机器上真实发生过**，不是假想风险。

**代价（三个见证）**：可用性是全套件里最贵的一格 —— **r3 493.9 s / 我侧旧版 492.7 s / 我侧新版 482.1 s**，
量级一致（≈8 分钟/次），差额几乎全在"真跑了整套 pytest"。A/B 机时估算必须把它单列。

**另外两条相关实测**：
- `--tree .` 默认 oracle 在**修复前**得到 pytest **退出码 4**，原文 `ERROR: Unknown config option: cache_dir`（§2.3 已修）；
- 小树上的绿案例：`pytest_status=ok / exit 0 / 2 passed / pass_to_pass 2/2`。
- `pass_to_pass` 在本仓仍是 `unavailable`：没给 oracle 就没有声明的 node id（不是"全绿"）。

---

### 6.1 精确：首批真实读数（**由 r3-applicability 产出，不是我产出的**）

按 G14 标注来源与工具版本：产出者 = r3-applicability；工具 = §0 冻结指纹（132173 B / `40db64f6…`）；
原始输出见其文档 `redteam-and-pilot.md` §3.4-ter。

@@@
inputs: 5 条编辑（含 1 条不可重建）        耗时 3.0 s
counts = {TP 4, FP 0, unreconstructible 1, unverifiable 0}
分母 = 4      precision = 1.0      Wilson 95% [0.510, 1.0]
unreconstructible 那条 reason = "old_string 出现 0 次（必须恰好一次）"  -> 不进分母
@@@

**这三行必须一起读，缺一行就是错的**：

1. `precision = 1.0` 的样本量是 **4**，Wilson 下界 **0.510** ⇒ **样本不足**，"1.0"不是"平台的 block 全对"；
2. **同一台机器上实测的天花板是 0.0**（§9 第 4 条）：declared_fp 含"错误码常量被当成凭据"那一类样本时，
   仪器**照样判红** ⇒ 它没有识别这一类的能力。⇒ `precision = 1.0` 只在"被拦集合不含那类样本"时成立；
3. ⇒ 正确的结论句是「**本轮 precision 读数 1.0（n=4，Wilson 下界 0.510），但仪器对已登记误报类样本无判别力，
   天花板实测 0.0**」，**不是**「block 的精确率是 1.0」。

（本轮 `block_class` 分类未实现 ⇒ 按协议侧 F6，正式结论里的「精确」仍是 **unavailable**，见 §9 第 9 条；
上面的四个计数是**原始读数**，不是"已可用的精确率"。）

---

## 7. 同源声明（哪些半同源、哪些完全独立）

| 量 | 同源等级 | 影响结论强度吗 |
| --- | --- | --- |
| 规范性 `scanner` | `policy_layer_independent_linter_dependent` | **影响**：只能主张"与策略层无关"，不能主张"与平台无关" |
| 安全性路线 B（ruff S） | `half_homologous_same_binary` | **影响**：与规范性**不是独立证据**，两个量一起动不构成"两个独立来源都同意" |
| 安全性路线 B（自写 AST） | `second_implementation_uncalibrated` | **影响**：不同源但未校准、覆盖窄，只能当补充 |
| 可用性 `usability` | `externally_independent` | **不影响**：pytest 与逐用例结果不经过平台与 linter |
| 精确 `block_precision` | `label_from_independent_instruments_only` | **影响**：标签独立于平台的 Decision，但底层仍是同一条 ruff ⇒ 上界是"一致率" |
| 高效 `efficiency` | `wall_clock` | **不影响**（但只测墙钟，不解释墙钟） |
| 全自动化 `automation` | `manipulation_check` | **影响**：它是"处理有没有被施加"，不是结局 |

---

## 8. 交流记录

### 8.1 与 ab-protocol（task-11，A/B 协议）

| 谁提了什么 | 我的回应 | 最终怎么定 |
| --- | --- | --- |
| 三臂 off/advisory/enforced；advisory = exit0_shim | **接受** | 接受（拆门禁效应与反馈效应的前提） |
| 工具名 `ab_scan.py` / `ab_test_oracle.py` | **反驳**：写域只许 `tools/ab_measure.py` 一个文件 | 接受我的：一个工具、一个 JSON、`--mode` 分块 |
| `counts_by_code_changed` 口径（行级 vs 整文件） | **反驳"只报一个数"**：两个都报，差额本身是要读的量；行 = new-side `+` 行 | 接受，并加第三个 `counts_whole_tree`，三个不许混 |
| "相同输入逐字节相同" | **反驳**：带 `run.id` / 计时的载荷不可能逐字节相同 | `--deterministic` 去 `run` + 计时块标 `not_applicable`；只承诺 `--mode scan,usable,security,blocked` |
| 缺 `blocked_edits[]` / `write_actions_*` / `human_interventions` | 我点名要三个字段 | **全部加**；并加 `block_class` 三分、`human_interventions_detail[]` |
| `infrastructure_failure` 不计入任何分子分母 | **接受** | 接受（否则会把平台故障读成治理成本） |
| 目标树锚在本仓之外；`--baseline-tree` 是主路径 | **接受** | 已实现：标准库 `difflib` 自 diff，**不需要 git** |
| 可用性 oracle 降级为 `U1不含 / U1含` 两份 node id 清单 | **接受** | 已实现 `--test-selection label=path`（可重复），不再自己扫 `tests/` |
| P1 可以是四个计数、不给比率 | **接受** | `counts = {TP, FP, unreconstructible, unverifiable}` |
| `feedback_envelope_body_sha256` 要我暴露 | **部分接受** | **已消解**：对方改为「生产侧只原样存字节 + 原文哈希，**规范化只有测量侧一份实现**」⇒ 不存在两份实现口径不一致的问题；另加交叉校验（我算的原文哈希必须等于生产侧存的，不等 ⇒ 该 run 作废） |
| `block_class` 的用法 | 我问「要不要先过滤」 | 对方答 **「不要过滤，要分类」**：三类各报计数，红线只落在「只有 `policy_violation` 进 P1 分母」。`field 缺失 ⇒ unknown`，绝不静默当成 `policy_violation`。**我接受这个设计，但我的工具当前没有实现它**（见 §6 缺口表） |

**已消解的分歧（2026-10-07，ab-protocol 回执）**：我曾指对方 §1.5 的 `N1/N2/N3`（同源等级）与 §(d) 的
`N1/N2/N3`（三个 tree_scope）**同名两义**（AGENTS 第 50 条）。
**对方驳回了我的诊断**（本文件里 `N1/N2/N3` 从头到尾只有一个意思，tree_scope 本来就是另一个枚举），
**但采纳了我的结论**：`N1/N2/N3` 全文替换为 `NORM_LINES`/`NORM_FILES`/`NORM_TREE`、
`tree_scope ∈ {final, changed_lines, changed_files, whole_tree, base}`、同源等级改用拼写完整的词。
⇒ **这条按「诊断被驳回、结论被采纳、分歧消解」记录，不再算未解决。**
对方另立规则：短码只在一张表内部用；跨表 / 跨文档 / 跨会话引用必须用自证含义的名字。

### 8.2 与 r3-applicability（红队）

| 攻击 | 我的回应 | 结局 |
| --- | --- | --- |
| I1 分母错（能力外 / unmapped 进分母） | **部分接受**：冻结配置里没有映射表，"unmapped"是平台概念；但**接受更强的形态**：选择之外的码看不见 ⇒ 结构性低估 | 已写进 `recall_limit` |
| I2 位置匹配口径未写死 | **接受** | §2.1 写死（三元组、列不匹配、无容差、取起始行） |
| I3 缺工具静默降级 / 拿平台 Decision 兜底 | **接受**（最重红线） | 无任何路径读平台 Decision；缺东西一律 unavailable |
| I4 变异不自证 | **接受** | §4 三条判据 + §4.1 归档树两次变异 |
| I5 warning 当阻断力 | **接受** | 仪器没有 severity→阻断力概念；安全分档标注为仪器自定、非阻断力 |
| I6 被拦下当防住了 | **接受** | 反事实存在的原因；`blocked ≠ correct` |
| I7 读数不带 reading_context | **接受** | 每份载荷都带（`source="cli"`，lead 裁定不扩枚举） |
| I8 仪器读了 treatment 配置 | **反驳，并证伪** | 红队自己复验（顶层 + 嵌套两级诱饵）后**接受**；§4 的独立性变异同向 |
| **M-3** 无入口点 / exit 0 + 零输出 | **接受为真实观测**（渐进写盘的中间态），已修 | `--help` exit 0 非空；无参 exit 2；`--self-check` exit 0 |
| **M-4①** `(path,code,line)` 集合差在插入类编辑上系统性多报假新增 | **接受并修** | 主判据改成 `(code, message)` 多重集（对漂移稳健）；行级口径拆成 `rows_added_raw` 与 `rows_added_shift_aware`（diff 回映射） |
| **M-4②** block_precision 把已登记误报判成真阳性 ⇒ 上界是"与 ruff 的一致率" | **接受并修** | 载荷 `label_semantics` 写死"不是 ground truth"；新增 `--known-false-positive-edits` 阳性对照算 `max_achievable_precision` |
| **V-1** 顶层 `unavailable[]` 漏列块级 unavailable | **接受并修** | 汇总覆盖所有 `status == unavailable` 的块；实测顶层 3 条 = 三个块 |
| **V-2** pytest 退出码 4 + counts.total=0 被报成 red | **接受并修** | 2/3/4/5 → environment_unavailable；块整体 unavailable；与 ab-protocol §1.4 三态映射一致 |
| **V-3** 顶层包探测按字符拆开（"s, r, c"） | **接受并修** | `--import-roots` 先按逗号切；实测 `import_roots = ["src", "."]` |
| **V-4** 未请求的块不出现 | **接受并修** | 未请求的块显式 `status = "not_requested"` |
| r3 建议：块头写"总量由 S101 主导，占比 X%" | **接受** | `dominant_code = {code: S101, share: 0.972965}` |
| r3 的 fallback 262 文件 / 44.97 每 KLOC 与我的 384 / 55.24 | **接受为口径差** | §5 警告 3：**不许互比** |

**已关闭的分歧（2026-10-07）**：我建议不改名、改用 `label_semantics` + `upper_bound_note` + 可跑阳性对照。
**r3 已复验并撤回改名要求**，原话理由是"你的理由成立——判据不止 ruff"，并评价"可测量的替代 > 改名词"。
⇒ 按"**不改名**"记录，**分歧关闭**。

**同一封回执里另外三条闭合**：
- **M-4① 关闭（对方复验通过）**：r3 用 3 个插入样本复测新版本，`raw / shift_aware` 差额 = **3 / 3 / 5**，
  与它上一轮自己量到的"假新增"**逐条相等** ⇒ shift-aware 修法有效；主判据不受影响（三条都只报 1 条 F401）。
- **S3（可读性）接受**：`red` 而 `new_findings = []` 会让人先怀疑"红得没证据"——证据在 `new_security` 通道。
  已在 §2.4 新增「怎么读一条 red（证据通道）」并用最小复现钉住。**没有加 `evidence_channels` 键**
  （加键要升版、会作废冻结），改用文档消解，因为通道信息**可从既有键推出**。
- **S2（"两个副口径覆盖的通道不同"）诊断驳回、补充接受**：不成立——两个数**都只读 norm 通道**。
  最小反例：`C1-security-only`（只有安全通道新增 2 条，`raw = 0 / shift_aware = 0`）与
  `C2-shift-only`（纯行漂移，`raw = 1 / shift_aware = 0`）。**但"口径没写清"这半句我接受**，
  已在 §2.4 写明"只覆盖 norm 通道"。
- **S2/③-a（同一份载荷自相矛盾）—— 成立，已修，见 §2.3 第三条**：r3 用"一个 run id + 同一个嵌套对象"
  排除了"混看两次运行"与"看成不同块"，并补了一条我没想到的事实：`stderr_tail = ""`（空）而 reason 引用了
  "pytest 自己报的 INTERNALERROR" ⇒ **载荷没有携带支撑自己归因的证据**。
  我按它给的最小判据（`exit_code ↔ counts ↔ 措辞` 互相蕴含）修了，并把 `schema_version` 升到 1.1。
  这次我**没有**用冻结挡：**缺功能可以留缺口，错误读数不行**。
- **③-b（分类规则必须是"这个失败是不是环境造成的"，而不是"有没有出现环境告警"）—— 接受**：
  与 §2.3 第三条同一根因（分类 / 措辞与它记录的计数、退出码、证据三者脱节），已一并修。

### 8.3 与 eval-harness（task-15，臂运行时）

| 谁提了什么 | 我的回应 | 结局 |
| --- | --- | --- |
| `measurement_input.json` 布局与键 | **接受布局** | — |
| `changed_files` 口径 | **接受两个键都给**（declared + actual）；我另用 `--baseline-tree` 自算行级 | 已实现 |
| (c) 反事实需要哪棵树 | **反驳 `tree_before/tree_after` 够用**：enforced 臂 refused 时两棵树逐字节相同，被拦编辑**根本不在里面** | 对方**照单全收**，实现 `proposed_edits[]`（每次受治理写动作一条） |
| 缺 oracle 声明块 | 我列出 `python / test_command.argv / pass_to_pass / fail_to_pass` 等字段 | 已落地并**真的跑了** |
| `entry.side_effect_free` | 我要这个键来决定敢不敢重复跑 | 对方如实写 **false** ⇒ 我对真实入口的延迟读数 = unavailable |
| 操纵检查不许当成绩 | 双方一致 | 我的 `role = manipulation_check` 与 `caveat` |
| 对方实测：sanitization 不删 `tests/`；oracle 必须独立空配置 + `--rootdir` | **接受为输入事实** | 我的 oracle 用树自己的配置 + 显式 `-o cache_dir`；本机实测踩到 `cache_dir` 冲突（§2.3） |

### 8.4 与 eval-extend（task-14，任务集）

我提的 6 处补全（`patch` / `test_command.argv` / `python` / 真实 node id / status 与 reason 分开 /
`source{url,sha256}`）对方**全部落地**；对方另加 `test_select_style = append_node_ids | by_keyword | none`
与 `test_patch`。我**接受** `by_keyword`（裸函数名任务只能 `-k` 选）：本工具的选择清单由调用点给，
不自己猜选择器，所以取值域扩展不影响我。

### 8.5 与 lead

| 裁定 | 我的执行 |
| --- | --- |
| `reading_context.source` 用既有的 `cli`，**不扩枚举**（不改 `src/provenance/reading_context.py`） | 已按此实现 |
| 必须跟进 ab-protocol 的三个缺字段；若拒绝则记为未解决分歧 | 对方**全部加了**，无分歧 |
| M-3（无入口点）是 P0，必须"跑起来必有输出 + 无参 exit 2" | 已修并给出原始输出（§1） |
| 六条修好到什么程度报什么程度，不许拖交付 | §6 列出未验证项（本仓全量 pytest 未重跑完） |

---

## 9. 未验证 / 缺口清单（交付时仍然存在的）

> **这一节每一条的出处与见证范围**（2026-10-07 收口时补；红队的交接表点到、我照办）：
> 下列条目**除注明"双方独立确认""红队实测/受控复现"者外，都是"本机 + 我这一次调用"的观测，
> 没有第二方独立见证**——按 §10.1 第 3 条，否定结论必须带范围。
> 逐条见证现状：
> - **有第二方独立见证**：§9 第 1 条那 6 条确定性失败（红队同版本 2 次）、
>   §9 第 10 条 (a) 树摘要失效（红队用 policy.check 打出的原文）；
> - **只有红队**：\`pytest-cache-files-*\` 的"不可读 ⇒ 收集期 rc=2"（受控复现，我未复现）、
>   两种删除失败、残留 4 → 8、天花板 = 0.0；
> - **只有我**：路线 A 分支从未执行、\`--with-tests\` 未测、真实延迟 0 条、\`block_class\` 未实现、
>   自证各 1 个见证、\`check_text_conventions.py\` 的 563 文件 0 问题（红队最后一次全仓是 561，
>   之后只在单文件模式下核过自己的文件）；
> - **两边都不代答**：G13（per-run 独立 dsh home）——各自记 \`unavailable\`。
> - **红队明确未核**：本文件的 sha256（他们从未对它取哈希）⇒ 引用本文的哈希时，出处是**我**。

1. ~~本仓全量 pytest 未重跑完~~ → **已重跑完（2026-10-07 20:52）**：见 §6，
   `available(red) / 2136 条 / 6 failed / exit 1 / trustworthy=true`。
   **这条我原来写错了，按红队的更强实验更正**：我先写"这套测试在本机不是逐次可重复的"，
   证据是"旧版 3 failed vs 新版 6 failed"。红队**同版本重复 2 次**（同一批 node id，5.69 s / 5.60 s），
   **失败集合完全相同**，且 `git status --porcelain` 对相关文件无输出。
   ⇒ 正确写法是"**当前基线树上有 6 条确定性失败**"；"3 vs 6"跟着**工具版本 / 树状态**走，**不跟着运行**走。
   **判据收紧（接受）**：要主张不可重复，必须**同版本重复 ≥2 次且失败集合不同**——单靠版本间差异不算。
   这 6 条逐条可查（我侧载荷 `repo-v11.json`）：`tests/contract/test_wiring_inventory.py::test_wiring_json_contract`、
   `tests/integration/test_cli.py::test_json_reading_context_names_the_entry_the_tree_and_the_declarations`、
   `tests/integration/test_obligations_gate.py::test_the_payload_says_which_tree_and_which_ledger_it_read`、
   `tests/integration/test_provenance_loop.py::test_provenance_loop_reads_r_e`、
   `tests/unit/test_exemption_expiry.py::test_json_payload_key_set_and_its_version_axis`、
   `tests/unit/test_wiring.py::test_reading_context_names_the_tree_and_the_scope_declaration`。
   **共同形状**：都是 reading_context 断言（如 `test_wiring.py:780` 的
   `assert block["tree"]["status"] == "available"`）——**根因见下面第 10 条**。
2. **红队据此指出的后果（我接受，比"稳不稳定"重要）**：基线本来就红 ⇒ `U1`（恢复后重跑）**不能直接当
   可用性主结局**，必须先把基线红**钉死成"已知失败集合"**并分列，否则两臂都在一条红基线上比较，读数没有意义。
2. **路线 A（bandit / semgrep）分支从未执行过**：`route_a_verified = false`，解析代码未经真实输出检验。
3. **`--with-tests` 的反事实路径未测**（需要 oracle 与可跑的测试树；本仓全量跑不动）。
4. **~~阳性对照未跑~~ → 已由红队实测，天花板 = 0.0**（**不是我产出的读数**，来源标注如下）：
   r3-applicability 用本仓 `policies/security/SEC-004.yaml:22-23` 自己登记的误报构造了一条编辑
   （`src/policy_api/errors.py` 加 `TOKEN_REVOKED = "token_revoked"`，属"错误码常量不是凭据"那一类），
   喂给 `--known-false-positive-edits`：`declared_false_positives = 1` / `instrument_says_red = 1` /
   **`max_achievable_precision = 0.0`**。
   ⇒ `upper_bound_note` 从"论证"变成"读数"：**declared_fp 含这类样本时，这台机器报出的 precision 天花板就是 0**。
   按 G14，引用它必须带：产出者 = r3-applicability、工具版本 = 本文件 §0 的冻结指纹、原始输出见其文档 §3.4-ter。
5. **`--latency-cmd` 未在真实入口上跑过**：`side_effect_free = false` ⇒ 按设计拒绝；
   真实延迟读数**为 0 条**，只有机制。
6. **`--test-selection` 未在真实 node id 清单上跑过**（只有小树上的 2 条）。
7. **`efficiency.runs` / `automation` 未在真实 run 记录上跑过**：需要 ab-protocol / eval-harness 的 JSONL。
8. **实测覆盖**：M-敏感 / M-独立各 1 个见证（合成树 + 归档树各一套），**不能外推**到"所有树上都成立"。
9. **`block_class` 未实现 ⇒ 本轮「精确」的正确读法是 unavailable，不是「精确率很高」**：
   ab-protocol 裁定「不要过滤，要分类」（三类各报计数、只有 `policy_violation` 进 P1 分母、
   字段缺失记 `unknown`）。我的工具**当前不读这个字段**，所以 `counts.TP/FP` **可能混进
   `infrastructure_failure` 条目**。
   **对方据此把它当协议内的前置条件处理，不当作我的待办**：无法分类的阻断一律记 `unknown` ⇒
   按「只有 `policy_violation` 进分母」⇒ **分母 = 0** ⇒ 触发 F6 ⇒ **`精确` 写四个计数、不给比率**。
   **⇒ 本轮结论里「精确」必须写成 `unavailable`，原因是分类未实现，不是精确率高。**
   实现它要给 `blocked` 块加键并改分母语义 ⇒ 按 AGENTS 第 55 条必须升 `schema_version` 1.0 → 1.1
   ⇒ 作废 §0 的冻结指纹。**ab-protocol 明写「不建议 lead 为此刻意重开冻结」**（P1 本轮零样本，
   重开收益 < 作废一个已发布冻结的成本）；取舍权仍在 lead。

   > **一条结构性相撞（记下来，免得下一个人以为是失误）**：**冻结纪律（G14：引用读数必须带
   > 时间戳 + 大小 + sha256）与协议升版纪律（AGENTS 第 55 条：加键就要升版）在这里正面相撞**——
   > 冻结一个载荷，等于给它加了一道「修它就要作废自己」的锁。这不是谁做错了：两者各自都对，
   > 相撞时只能由 lead 裁。把它写下来比事后解释「为什么没修」有用。
10. **仪器会污染被测树：`pytest-cache-files-*`（查到根因、修不动、已整块回退、如实留缺口）**：
    根因链（本机实测）：pytest 的 `--basetemp` 在 ACL 拒绝下**退回**
    `tempfile.mkdtemp(prefix="pytest-cache-files-", dir=rootdir)` ⇒ **在被测树根建目录**；
    这些目录自身**拒绝访问** ⇒ `provenance.worktree.workspace_tree_digest` 读不过去 ⇒
    `reading_context.tree.status` 变成 `unavailable` ⇒ **上面第 1 条那 6 条 reading_context 测试确定性失败**。
    证据：仓库根现有 **13 个** `pytest-cache-files-*`（生成时刻 20:35–21:00，横跨我的运行与红队的运行）；
    整个 `.tmp/` 下有**数百个**同前缀目录，分布在 `round-08` / `round-15` / `w1` / `w3-wiring` 等
    **多个会话的产物**里 ⇒ 不是某个仪器的实现细节。
    **速率：机制确认，速率未复现——两个数分开报，口径比数字重要**。
    - **我侧**（整套 pytest + 我的插件 argv + 显式 `--workdir`）：每次运行后树根 **+2**；
    - **红队侧**（单用例；一次显式 `--basetemp`、两次不带）：起始 13，三次运行后仍是 **13 ⇒ 增量 0 / 0 / 0**。
    ⇒ **"每次 +2" 不是一个机器常数**，它**依赖调用方式**；引用它必须连"在哪种调用下"一起写。
    **我没有查清它在我这里发生在哪个时刻**（我的清理快照没看到它们 ⇒ 观测上是"晚于我的检查"，
    这是**观测**，不是机制结论）。红队给的"这些是空目录、git 不跟踪空目录 ⇒ `git status` 里一条都不出现"
    是**另一条独立事实**（"看不见 ≠ 不存在"），但**不是我那次漏检的原因**——我用的不是 git 而是 `Path.glob`。
    两条原因别混：**它不可见于常规卫生检查（红队）** 与 **它晚于我的快照出现（我）**。
    **我试过修，没修成，已回退**：加"每次唯一 basetemp + 先建目录 + 跑完删除本次新增"之后，
    实测每次仍在树根新增 2 个，`tree_litter_*` 恒为空——那会读成"**没有污染**"，是一个**假读数**。
    ⇒ 整块回退，宁可留缺口也不留假绿。回退是**逐字节**的：`tools/ab_measure.py` 回到
    `57E2AA27…` / 134417 B —— **红队已独立核验过的那个指纹**，所以这次没有新指纹、没有作废任何已发布读数。

    **因果链已被红队端到端独立确认**（用**另一个**工具，不是我这条路径）：
    `python -m policy.check src/policy/scope.py --json` 的载荷里出现
    `"tree": {"status": "unavailable", "reason": "树摘要读不到：UnprovableError: 读不到目录：…pytest-cache-files-0697x19k（拒绝访问。）"}`
    ⇒ 拒绝访问的 litter → 树摘要 `UnprovableError` → `tree.status = unavailable` → 那 6 条断言 `available` 的契约测试确定性失败。**逐环成立。**

    **两条比"6 条测试红"更严重的推论（红队提，我接受并转报 lead）**：
    1. **不是"某人的仪器坏了"，而是整棵树的读数被降级**：这台机器上**任何带 `reading_context` 的载荷都证明不了
       自己读的是哪棵树**（AGENTS 第 48 条要的正是这个）⇒ **A/B 的 `reading_context` 不能当作"哪棵树"的证据**；
    2. **这些目录对常规卫生检查不可见**：它们是**空目录**，git 不跟踪空目录 ⇒ `git status --porcelain` 一条都不出现。
       "看不见"不等于"不存在"——所以我上面那条"我试过修却没看见"的观测，值得被当成一个**通用教训**记下来。
    **可核对的痕迹（留给下一个人，不靠我的话）**：`.tmp/ab-fix` 下每次运行留下**一对**目录，创建时刻与运行时刻对齐——
    `20:43:14 / 20:43:25`、`21:02:37 / 21:02:39`、`21:02:57 ×2`。
    这是**我测到的**。**我推不出来的**：为什么我的"跑后快照"没看见它们（观测：晚于快照出现；机制：**未查**，写 unavailable）。
    按红队立的尺子，这两句必须分开写——**"别人为什么这样"的句子，拆成「我测到的」与「我推出来的（未验证）」**；
    推不出来就写 unavailable。这条尺子我采纳，并用在**我自己**身上。

    **根治方案不是"清理垃圾"，是"换尺"（红队提，我接受并补一条轴分析）**：

    把 `pytest-cache-files-*` 加进 `src/provenance/worktree.py` 的 `DEFAULT_EXCLUDES` 会**改变
    `workspace_tree_digest` 覆盖的集合** ⇒ ① 旧摘要与新摘要**不可比**（不是"漂移"，是**换了一把尺**）；
    ② 任何以旧摘要为锚的基线 / 读数（含红队载荷里的 `reading_context.tree`）之后**要么重记、要么标注不可比**。

    **轴分析（我补的，供 lead 裁）**：按 AGENTS 第 55 条的判据（**这个载荷的键集合或语义变没变**），
    受影响的**不是** `provenance` 的那两条轴：`RECEIPT_SCHEMA_VERSION` 是 provenance CLI **收据载荷**的轴、
    `wiring_scope.SCHEMA_VERSION` 是**边界声明数据文件**的轴——换 `DEFAULT_EXCLUDES` **不动这两个载荷的键集**。
    它动的是**很多载荷里同一个值**（`reading_context.tree.digest`）的**含义**；而 AGENTS 第 55 条明写
    **`provenance.reading_context` 不是一条轴、它的形状变更随各载荷自己的轴走**。
    ⇒ **今天没有任何一条轴覆盖"树摘要这把尺"**。那本身就是一个必须写下来的结论：
    换尺要么先**新建一条尺的轴**（例如给 `tree` 加一个 `digest_rule` 之类的标识——那会同时动**所有**
    带 `reading_context` 的载荷的键集），要么**别换尺**。

    **三个选项与它们的测量后果（我按测量口径排，不替 lead 决策）**：

    | 选项 | 换不换尺 | 测量后果 |
    | --- | --- | --- |
    | A. 只清理目录（清 13 + 数百个） | **不换** | 摘要恢复可算，**但下一次 pytest 跑完又会复发**（跑步机）；且目录不可读，清理本身可能要先修 ACL |
    | B. 加进 `DEFAULT_EXCLUDES` | **换尺** | 一次性根治，但旧摘要**全部不可比**，且**今天没有轴**覆盖这次换尺（见上） |
    | C. 遍历时跳过不可读目录、把缺口写进读数 | **换尺（更隐蔽）** | 摘要变成"**部分覆盖**"的摘要；不写清就是**静默少算**，与失败关闭的取向相反 —— **不推荐** |
    我的倾向写成理由而非结论：**A 不换尺但会复发、B 根治但换尺且无轴**，取舍权在 lead。

    **D. 两个新事实（本机实测，2026-10-07 晚）——它们**否掉了一个被提出的选项 E**，必须一起读**：

    **事实 1：垃圾落在 `pytest 的 rootdir`（= 被测树的根），不在"该次运行的 workdir"里。**
    逐目录点过：`.tmp/ab-fix` 下 `wd` / `wd2` / `wd3` / `wd4` **各自 0 个** `pytest-cache-files-*`，
    而**树根 `.tmp/ab-fix` 有 10 个**（每次运行 +2）。`.tmp/ab-fix` 有 `pytest.ini` ⇒ 它就是 rootdir。
    ⇒ 红队提出的"合成口径：每次运行 +2、**落在该次运行自己的工作目录**"**在位置上不成立**；
    两个读数（他 0 / 我 +2）的差**不是分母不同**，而是**rootdir 不同**（他的调用没有把 rootdir 放在仓库根，或未触发该退回路径）。

    **事实 2：候选杠杆 `PYTEST_DEBUG_TEMPROOT` 实测无效（预注册后被证伪）。**
    在同一棵树上把 `PYTEST_DEBUG_TEMPROOT` 指向 `.tmp/ab-fix-temproot` 再跑一次：
    **树根仍是 +2（10 → 12）**，且该 temp root **根本没被创建**（`Test-Path` = False）。
    ⇒ 记下来，**免得下一个人再试一遍**。

    **⇒ 因此"选项 E"（强制 workdir/basetemp 落在已排除路径下 ⇒ 不换尺也不复发）我的判定是：**
    - **它的"断言"半句可用**（"运行前后根目录的 `pytest-cache-files-*` 集合不变"是一条便宜、有效的 canary，应该常驻）；
    - **它的"杠杆"半句不成立**：我的 workdir **本来就在 `.tmp/` 下**，垃圾照样落在**树根** ⇒
      "把 workdir 放进 `.tmp/`"**控制不了落点**。要控制落点得控制 **rootdir**，而 rootdir 是**被测树的属性**，
      不是调用方随便能改的（改它等于换一棵被测树）——这一步我**没有**验证到底该动哪个变量，写 `unavailable`。

    **D2. 红队随后在自己的**一次性树**`.tmp/ab-pilot/roottest/` 上又挖到更重的一条（他们的读数，我照引）**：
    @@
    run1/run2  cache_dir=被拒路径          rc=0  litter=0
    run3       -o cache_dir=.cache-writable  rc=0  litter=1   <- 可写相对 cache_dir 之后出现 litter
    run4       -o cache_dir=.cache-writable  rc=2  litter=3   <- 出现即收集期报错：PermissionError / 1 error during collection
    run5       cache_dir=被拒（回到 run1）    rc=2  litter=3   <- **回不去了**：树被自己毒住
    @@
    ⇒ 他们据此提出：**任何"在某棵树里跑过测试"都可能毒化那棵树**；对 A/B 的含义是——
    **臂树一旦被毒化，U1/U2 读的就不是"这棵树跑得怎么样"，而是"它被毒成什么样"**，
    必须按**环境失败**分列。**这条我接受**。可核对的痕迹：`pytest-cache-files-5f8scpvx / ntjldi4n / rvyu71rt`
    就在 `.tmp/ab-pilot/roottest/`（**我没有动他们的树**：我是把整棵树**复制**到 `.tmp/ab-r3copy` 再跑的）。

    **D3. 我做了能区分假设的那次测量，结论是"**毒化的判据是不可读性，不是目录名**"**：
    受控树 `.tmp/ab-poison`（复制自一棵已知能跑通的小树）里**故意建两个** `pytest-cache-files-fake1/fake2`
    —— 普通 `mkdir`、**可读可写**：
    @@
    block status available | pytest_status ok | red False
    exit_code 0 | trustworthy True | counts {total: 2, passed: 2} | collection_errors []
    @@
    ⇒ **只是"存在这个名字的目录"既不毒化收集、也不毒化读数**。红队的 run3–run5 与我的仓库根观测里，
    那些目录都是**pytest 自己造的、且拒绝访问**的。
    **⇒ 判据收紧为：不可读（ACL 拒绝）的 `pytest-cache-files-*` 才是毒源。**
    **我做不到的一条也写清楚**：我**没有**在仓库根（或任何非一次性树里）**故意**造一个不可读目录来复现"收集期失败"
    —— 那属仓库级副作用、无授权不做。所以"不可读 ⇒ 收集期 rc=2"这条**我只在红队的树上见过，未独立复现**，写 `unavailable`。

    **⇒ 两种失败模式必须分开记，它们不是一件事**：
    | 模式 | 触发 | 观测者 |
    | --- | --- | --- |
    | (a) **树摘要失效** `tree.status = unavailable` | 不可读目录 → `workspace_tree_digest` 抛 `UnprovableError` | 我（仓库根 13 个）+ 红队（`policy.check --json` 原文）**双方独立确认** |
    | (b) **收集期失败** `rc=2 / 1 error during collection` | 不可读 litter 出现在 rootdir（红队配置下） | **只有红队**；我没有在仓库根复核（**13 个不可读目录在场时，我的 2136 条照样收集成功**） |

    **⇒ 给 A/B 的一条硬要求（红队提，我接受并加了判据）**：臂树**每次运行用全新副本**，
    并在**运行前后各查一次**"树根 `pytest-cache-files-*` 集合 + 它们**是否可读**"；
    命中就按**环境失败**分列（与 B8 同级），**不许**把毒化后的红算成被测对象的红。

    **D4. 红队把 (b) 从"只有我见过"补成"受控复现"，并撞到一堵对**清理裁决**决定性的墙**（他们的读数，我照引）：
    - **A 情形独立复现**：普通 `mkdir` 出的可读同名目录 ⇒ `rc=0 / 2 passed`、无收集错误 ⇒ **只有不可读才是毒源**；
    - **B 情形受控复现**：`icacls <dir> /deny <user>:(OI)(CI)(F)` 造一个不可读目录 ⇒
      pytest **`rc=2 / Interrupted: 2 errors during collection`**，而且**运行中自己又生成了一个不可读目录**；
    - **新墙**：他们**撤不掉自己造的拒绝**——`icacls /remove:d` → **`rc=5（拒绝访问）`**，目录仍不可读；
      再跑一次 → `rc=2`、收集错误从 2 涨到 **4**。⇒ ① **"清掉那 13 个"在当前权限下未必做得到**，
      **尝试本身可能留下更多不可读目录**（失败是渐进的）；② 他们**没有**在仓库根试清理、也**没有**跑 `tools/cleanup.py`
      （他们的硬约束禁止）⇒ **"cleanup 会不会失败"没有被测**，只有风险。
    - **他们的实验残留（如实交底）**：`.tmp/ab-pilot/poison2/` 里有 **2 个造出来、撤不掉的拒绝目录**
      （`ccc333` / `sjhsxg2i`）⇒ **常规清理 `.tmp/` 时可能在这里失败，而他们无法自清**。我按事实记在这里（不动它）。

    **D5. 我的只读核查（`icacls` 查询，**不做任何删除**）**：当前用户 `desktop-4qltpcn\znm`；
    `icacls pytest-cache-files-0697x19k`（仓库根那个）与 `icacls .tmp\ab-pilot\poison2\ccc333` **都是
    "Successfully processed 0 files; Failed processing 1 files" + `Access is denied`**
    ⇒ **连 ACL 都读不到**，所以**不能用常规 `icacls` 修复/撤销**（撤销要先能读）。
    **一句必须写下的推理边界**：**"读不到 ACL" ≠ "删不掉"**——Windows 上删除子项看的是**父目录**的
    "删除子项"权限，不是子目录自身的 ACL。我**没有测删除**（那是我写域之外的仓库级动作）。
    ⇒ 给 lead 的可操作结论只有两条：**（i）常规修复路径（读 ACL → 改 ACL）在这台机器上走不通**；
    **（ii）"能不能删"我原本保留为未测的推理问题——红队随后把它测掉了，见 D6。**

    **D6. 红队把"能不能删"测了：在当前权限上下文下，**不可执行**（他们的读数，我照引并收窄）**：
    @@
    Remove-Item <denied dir> -Recurse -Force   -> 访问被拒绝，exists after = True
    cmd /c "rmdir /s /q <denied dir>"          -> exists after = True
    @@
    他们的残留也在长：`.tmp/ab-pilot/poison2/` 里 `pytest-cache-files-*` **4 个 → 8 个**（与"渐进"一致）；
    仓库根 **13 → 13**（他们始终没碰）。

    **⇒ 更正我 D5 里那句保留意见**：我说"Windows 删除子项看**父目录**的 delete-child 权限，
    所以别把'读不到 ACL'读成'不可能删'"——**这个推理本身没错，但在本机这个配置下两种删除都失败**，
    所以它是**不可执行**，不是"可能有救"。**按实测写，不按推理写**（这正是我们那把尺子）；我把上面那句改成现在这样。

    **两条边界，必须与结论一起读**：
    1. **类别边界**：红队测的是**他们自己 `icacls /deny … (OI)(CI)(F)` 造出来的那类**拒绝目录；
       **仓库根那 13 个是不是同一类，谁都核不了**（ACL 读不到）⇒ 对仓库根只能写**风险**，不写读数；
    2. **权限上下文边界**：两次删除尝试都在**同一个非提权用户**（`desktop-4qltpcn\znm`）下做的。
       "逻辑上不可能"与"**当前权限下不可执行**"是两句话——后者留着一扇**未测**的门（换主体 / 提权），
       我和红队都**没有**去开那扇门（越权、且不在写域）。要给 lead 的准确措辞是
       "**在当前权限上下文中不可执行**"，不是"不可能"。
11. **一条仍未消解的分歧**：r3 建议把 `precision` 改名为 `ruff_agreement`；我保留键名 + 写死
    `label_semantics` + 加阳性对照算天花板（理由见 §8.2）。按上文原样保留。

---

## 10. 读数的纪律（红队立的尺子，我采纳；其中一条改的正是**我**）

这一轮里双方各有一次以上的**表述过强**，红队每次自己收紧之后把尺子交出来。它们不是礼节条款——
**每一条都对应一次真实误读**，所以写进仪器文档而不是留在对话里。

### 10.1 四条尺子

1. **"落在哪 / 谁做的"必须用能区分假设的测量**；代理观测（例如"创建时刻相邻"）**不足以定位位置或机制**。
   *出处*：红队用它纠正自己"垃圾落在该次运行的 workdir"的和解——我逐目录点数把它推翻了（`wd*` 各 0、树根 +2）。
2. **"别人为什么这样"必须拆成两句**：「我测到的」与「我推出来的（推理，未验证）」；推不出来写 `unavailable`。
   *出处*：红队纠正自己对我"漏检原因"的归因（我用的是 `Path.glob`，不经 git ⇒ 他们的归因不成立）。
3. **否定结论必须写清它成立的*范围*（谁、什么权限、试了什么）**，范围外一律 `unavailable`。
   **两个工具 ≠ 两个权限上下文。**
   *出处*（三次修订后定稿；**这一格本身就是第 3 条的应用**：连"谁改了什么"都带范围）：
   **完整形状是"两条句子各被改过；其中一条被同一方连收两次"**（红队补全，我采纳）：
   1. **句子 A（我的）**："别把'读不到 ACL'读成'不可能删'"——**被改过一次，由红队的实测结果改的**
      （他们测出两种删除都失败 ⇒ 我据此把 D5 重写成 D6）；
   2. **句子 B（红队的）**："不可执行"——**被同一方（我）连着收紧了两次**：
      先在实测之前给范围（"读不到 ACL ≠ 删不掉"），再在实测之后收紧（"在我**实测的那个权限上下文**里"）；
   3. 更正后的准确形态是"**在我实测的那个权限上下文里不可执行**"，**换主体 / 提权那扇门未测**。
   **⇒ 两个形状不许压平**：压成"各改正一个人的一半"，既抹掉"句子 A 也被改过"，
   也抹掉"句子 B 是被同一方连收两次"——而后者正是**表述过强的复发形态**，比对称分工更值得记住。
   （我自己的两次不准确也留在这里：先写成"改正的是我的措辞"，后写成"两次收紧落在同一句话上"——
   前者漏了结论侧的归属，后者漏了句子 A。）
4. **要主张"不可重复"，必须同版本重复 ≥2 次且失败集合不同**；版本间差异不算。
   *出处*：**这条改的是我**——我据"旧版 3 failed vs 新版 6 failed"写了"这套测试不可重复"，
   红队同版本重复 2 次、失败集合完全相同，把它推翻成"**当前基线树上有 6 条确定性失败**"。我接受并改写了 §9 第 1 条。

### 10.2 它们怎样改变本仪器与 A/B 的读法

- 本文里所有**否定性读数**（"测不了""不可用""没有 X"）都必须带范围：
  **在本机 / 在当前权限上下文 / 在我这次调用方式下**；范围之外不写结论；
- 本文里所有**"落在哪"型结论**（例如"垃圾落在 rootdir"）都给出**能区分的测量**（逐目录点数），
  不用相邻性之类的代理；
- A/B 的**负结论**（"治理没有效果""没有差异"）同样受第 3 条约束：必须写清它覆盖的样本、臂、
  重复数与环境；**范围之外的"没有"不算结论**。这一条我已转报 lead。
- **并且要写读数的出处**（红队补，我采纳）：**仪器指纹 + 时间戳 + 范围**。
  理由就是这一整轮在证明的事——**读数有保质期、有范围**：本文件 §0 已经因为一次读数错误换过一次指纹，
  而"不可读目录"这类环境状态会随时改变同一棵树的读数。⇒ 一句"没有差异"若不带出处，
  读者无法判断它出自**哪个版本的仪器、哪棵树、哪个权限上下文**，也就无法判断它还成不成立。
  这条与 AGENTS 的 G14（引用读数必须带时间戳 + 大小 + sha256）同源，只是把"引用"扩到了"**否定结论**"。
