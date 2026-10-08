# AB-3 红队与试点：攻击协议与仪器 + 最小可行试验的原始读数

> **这份文件是什么**：task-13（对抗性复核者 + 试点执行者）的产出。两件事：
> ① 对 `ab-protocol.md` 与 `measurement-instruments.md` / `tools/ab_measure.py` 的**攻击清单**（每条：攻击 / 为什么成立 / 怎么检测 / 怎么修）；
> ② **实跑**四项最小可行试验的**原始输出**（不写"基本可行"）。
>
> **写域**：只有本文件；试点产物全在 `.tmp/ab-pilot/`。**没有**改 `policies/**`、`src/**`、`validation/**`、`tests/**`、`tools/**`、`evaluation/**` 或任何别人的文件。
> **口径**：凡是我跑的标【实测】并给命令与原始输出；引用别人的标来源小节；没测到的一律写 `unavailable + 原因`，不估计。
> **状态**：本文件在 lead 的"收敛指令"下落地——已做成的写清楚，没跑完的照实写成缺口（§7）。

## 0 结论先行

> **本节也有保质期（2026-10-07 20:40+08:00 追记）**：下面第 1 条写「六个量一个都不能算作它的读数」，
> 那是 **12:20–12:22Z** 版本的事实。**同一晚 12:24–12:39Z 的版本已经可跑**：见 **§3.1-bis**（更正读数）、
> **§3.4-ter**（P1 首批读数 + 天花板 0.0）、**§3.1-ter**（V-1/V-2/V-3 独立复验）。
> 我按自己对别人提的同一条纪律处理：**不改上文的原始记录，只在最前面加指路**。
> 判决随之更新：**B1 已关闭、B4 已关闭**，但 **A/B 仍不能跑**（B2/B3/B6/B7 与 B8 未清）。

1. **A/B 现在不能跑**（不是"基本可行"，也不是"只差调参"）。六个量里**只有 2 个（规范性、高效）我用自己的 fallback 拿到了首读**；
   `tools/ab_measure.py` 在 2026-10-07T12:20:27Z 的状态是**没有入口点**：跑它 **exit 0 / 0.2 s / stdout 与 stderr 全空 / --out 文件不存在**（§3.1）。
   按它自己冻结的退出码语义，exit 0 = 「跑完且每个量都 available 且没有 red」——**一个静默空转被自己的语义报成成功**，这正是本次红队要抓的形状。
2. **"净化树"在本仓自举路线上无效**（【实测】，§3.2）：删光 `policies/`、`validation/`、`AGENTS.md` 等 13 条路径之后，
   在**同一棵净化树里、以它为 cwd** 跑 `python -m policy.check`，平台照样加载 **43 条规则**并给出判定。
   机制在 `src/policy/check.py:165-172` 的 `repo_root()`：它**从模块位置向上回溯**找含 `policies/` 或 `.git` 的目录。
   ⇒ "树里没有平台产物"**不等于**"平台不可达"。lead 已据此裁定目标树锚到**本仓之外**——本条攻击保留为**自举路线的证伪记录**。
3. **`block_precision` 在安全类上不是精确率**（【实测】，§3.4）：`src/policy_api/errors.py` 被平台 `block`（SEC-004 / S105，43–44 行），
   独立仪器**也**在 43–44 行报 S105 ⇒ 按协议判据它是"确认的真阳性"；而 `policies/security/SEC-004.yaml:22-23` 把**同一个位置**明写为**误报**。
   ⇒ 这台仪器只能测「**与 ruff 的一致率**」，测不了精确率；它结构性看不见本仓早已登记的那一类误报（方案 §1 记：192 文件扫描里 22 个 SEC 命中中 16 个是启发式误报）。
4. **规范性 / 高效的 fallback 首读**（我自己的冻结配置，**不是** ab_measure 的读数）：262 文件 / 115,511 行 / 5,195 findings = **44.97 条每 KLOC**，
   干净文件率 **0.0763**；判定延迟 **p50 = 1721.1 ms、p95 = 1930.6 ms**（n = 31，剔除首个冷启动 1668.4 ms）。
5. **反事实的第 1 批样本**：3 个"插入未使用导入"的真实编辑，平台全部 `block`（STYLE-002 / F401 正好落在插入行），
   冻结仪器**同样在那一行**报 F401，标准库 AST 第二实现**也**判它未使用 ⇒ **3/3 被独立实现确认**（构造样本、同一构型，**不能当比率**）。

## 1 攻击协议（10 条）

> 每条：**攻击 / 为什么成立 / 怎么检测 / 怎么修**。[S1] = 会让你得出错误结论；[S2] = 会让你算不准。
> P1–P8 指 ab-protocol 冻结协议的点（`ab-protocol.md` §1.4 / §2.1 / §4 / §7）；P9–P10 是我加的。

### P1 [S1] 门禁 vs 反馈的归因：`enforced − advisory` 差的不只是"门禁"

- **攻击**：enforced 臂的阻断会**机械地删掉产物**（写没落地，终态树里就不可能有那个构造），advisory 臂把产物留在树里。
  于是终态规范性差里有一块是**由构造决定的**，不是"Agent 变好了"。
- **怎么检测**：结局拆两个分别报：① **终态产物**（被拒构造在终态树里的出现率，**按构造分别计数**）；
  ② **能力/行为**（`retries_after_block`、`block_class`、任务成功 U1）。并断言：enforced 臂里被拒构造的终态出现率**应当**≈0——
  这一条**不能**当成治理有效的证据。
- **怎么修**：协议已有 `block_class`，**缺"终态产物按构造分别计数"这一列**。补上，并把"终态更规范"与"Agent 更能干"分成两句话。
- **状态**：机制已接受；"按构造分别计数"**未落地**（§6 U-2）。

### P2 [S1] 负价值判据：把"CI 含 0"当"无效应"

- **攻击**：`规范性效应量 CI 含 0` 是**未拒绝**，不是**无效应**；配对 n = 20–50 时几乎任何中等效应都含 0，
  于是"负价值"主要由**功效不足**触发，而同一份协议第 3 条又判"未达功效"——**两条规则互相打架**。
- **怎么修**：换成**等价检验**（CI 完全落在 ±MDE 内才算"无效应"）+ 写死优先级（功效不足 > 负价值）。
- **状态**：已改（`ab-protocol.md` §7.1 F1 + 排除优先级第 6 级高于第 7 级）。**接受**。

### P3 [S1] 测试 oracle 可被游戏：`U1` 也挡不住全部绕过面

- **攻击**：绕过面不止"改测试/加 skip"：`conftest.py` collection hook、`pytest.ini` addopts、`skipif`/`xfail`、**删掉整个测试文件**、
  把测试**重写成断言新（错误）行为**、mock 打掉断言目标、**新文件遮蔽被测模块**。
- **怎么检测**（四条机器检查，不需要人）：① 测试文件 sha256 与基线比对；② `--collect-only -q` 的 **node id 集合 + 条数**比对；
  ③ 标准库 `ast` 数改动文件里的 `assert` 与 `assert*`；④ **冻结测试恢复重跑**。
- **状态**：`U1` 已升主结局，且明确**不声称"U1 不可游戏"**（后两条绕过面 U1 也挡不住）。**接受**；四条检查里 ①–③ 仍需逐条落名。

### P4 [S1] 污染检查面：只查工作树里的文件不够

- **攻击**：① **git 历史**（【实测】：`git show HEAD:policies/coding/DOC-001.yaml` 打出了规则正文）——clone + `git rm` 路线净化后仍可读；
  ② **全局 .dsh home**（本机 `%USERPROFILE%\\.dsh` **存在**，含 `profiles/{desktop,governed,…}`，其中 4 个 `cordis.patch.yml` 命中 `policy-hook|policy_hook|policy.check`）——树级 grep **证明不了**"hook 未挂载"；
  ③ **行为级**：Agent 自己主动跑 `ruff`/`pytest`（ruff 在 PATH 上）时，"off 臂"其实没 off。
- **怎么修**：① 断言任务树里没有平台产物、且平台检出不在任务树内（新路线下 `.git` 无关）；
  ② 全局 home 扫描 + **运行时行为探针**；③ `agent_self_tool_runs{ruff,pytest,other_lint}` 记成**协变量**。
- **状态**：已改（§4.3 L5/L4 + §4.6 保留为自举路线证伪记录）。**接受**（适用范围收窄）。

### P5 [S2] 仪器独立性只有两根轴，第三根最容易被忽略

- **攻击**：独立有三根轴：**配置**（不读 `validation/ruff.toml`）、**实现**（本机只有 ruff ⇒ 不独立）、**触发**（平台与仪器是否读**同一次** ruff 输出）。
  第三根不成立时，"独立确认"退化成"同一次调用的两次转述"。
- **怎么修**：各自独立调用（含 `--no-cache`）并记录 argv。`ab-instruments` §3 已固定。**接受**。

### P6 [S1] 两臂失败模式不对称，失败被算成处理效应

- **攻击**：enforced 臂有 off 臂**根本不存在**的失败：Hook 起不来（dsh 侧"超时/崩溃 = 放行"）、`evidence_unavailable`、
  `capability_unavailable`、`startup_error`。把它们算进"被拦下/任务失败"，会把**平台故障读成治理的成本**，结论系统性偏向负价值。
- **怎么修**：`block_class ∈ {policy_violation, fail_closed, infrastructure_failure}` 分列计数；`infrastructure_failure` **不进任何分子分母**；
  结论旁必须写"off 臂不存在这一类失败"。**已改**（§7 排除第 5 级）。**接受**。

### P7 [S2] 顺序/学习效应：**不可判**，只能用结构消除

- **攻击**：反事实顺序**不可观测**，随机化只能平衡不能消除；小 N 下顺序效应检验功效≈0，"没检出"不能写。
  真正能消除它的是**结构**：每 `(task, replicate)` 全新**会话** + 全新**工作树**（否则 enforced 臂的修复会改善 off 臂随后看到的树）。
- **状态**：已改（§4.2 P6；顺序效应只报 CI、不当门禁）。**接受**。

### P8 [S2] 多重比较与配对结构

- **攻击**：三臂 × 三主结局的"6 个检验"其实是**同一批配对样本**上的对比，独立检验会低估相关性；逐规则/逐文件的次结局不预注册就是选择性报告。
- **怎么修**：预注册主结局 + Holm/BH；配对分析用配对检验/混合模型（task 为随机效应）；次结局只报告并标明未校正。**建议保留**。

### P9 [S1]（我加的）**"净化"是路径删除，不是可达性控制**

- **攻击**：净化清单按**路径**删，但平台的可达性由**调用它的那份代码**决定，不由树里有啥决定。
- **为什么成立**：【实测】§3.2 —— 13 条路径全删光后，在净化树里跑平台仍加载 43 条规则（`rule_set_hash = sha256:50202675…`，与本仓一致）。
  两种调用方式都复现：`PYTHONPATH=<真 src>` 与 `PYTHONPATH=<净化树的 src>` **都**加载了 43 条规则。
- **怎么检测**（比路径断言强，且本机可跑）：
  1. 从臂内打印 `repo_root()` 与解析到的规则根，断言两者都在**平台检出**内、且都**不在任务树内**；
  2. 断言平台载荷里的 `rule_set_hash` **等于平台检出**的期望哈希；
  3. 用**显式 `--rules <平台检出>/policies`** 调用，并断言**不传它时必须失败**。
- **怎么修**：把 P8（平台检出不在任务树内）升级为上面三条**代码路径断言**；拿不到 fs 级隔离就记 `code_path_verified`，**不**写 `fs_isolated`（§5 已按此判）。

### P10 [S2]（我加的）**读数不带"这次测量读了哪些文件"的证据**

- **攻击**：仪器声称"不读 `validation/ruff.toml`"，这件事只能靠**读了哪些路径**来证。
- **怎么修**：`ab-instruments` §3 已给 `independence.measured_tree_reads[]`；**接受**，并要求它每次运行非空且不含 `policies/`、`validation/`。

## 2 攻击仪器（8 条）

> 对 `tools/ab_measure.py` + `measurement-instruments.md`。I1–I8 已在交流里发给 ab-instruments（§6.2），这里是**判决与新增证据**。

- **I1 [S1] 分母错**：能力外/未映射进分母。**部分接受**：仪器的冻结配置里没有"映射表"这个概念，所以不存在"把 unmapped 算进分母"；
  但**接受更强的形态**：冻结选择之外的码它**看不见** ⇒ 绝对数是**结构性低估**（我的 fallback 也如此：select 只有 6 个码，5,195 条里 5,101 条是 E501）。
  要求：每个计数块写 `recall_limit`，禁止把绝对数当"真相"。
- **I2 [S1] 位置匹配口径**：**接受并追加实测缺陷**——§3.4 的**行位移假象**：`(path, code, line)` 集合差会把**插入点之上**的所有既有发现误判成"新增"。
  我在 3 个样本上分别多得到 3 / 3 / 5 条**假新增**（全是 E501）。修：diff 感知（基准行号 ≥ 插入点则 +shift）或只在**改动行集合**上比。
- **I3 [S1] 静默降级**：**接受**（§3/§4 明写不读平台 Decision、缺东西一律 `unavailable`）。
  **实证反例是我给出来的**：`tools/ab_measure.py` 自身**静默空转却 exit 0**（§3.1）——与"缺工具静默降级"同族，只是发生在入口层。
- **I4 [S2] 变异不自证**：**接受**（已预注册 M-敏感 / M-独立）。**未完成**：原始 JSON 我**没有收到**（§6 U-1）。
- **I5 [S1] 把 warning 当阻断力**：**接受**。本仓 `repo_scan` 是 error 108 / warning 2,046（**94.99% 是 warning**），
  任何把"发现数"当"阻断力"的读法都会高估一个量级。仪器只报计数与 `counts_by_code{}` 的做法正确。
- **I6 [S2] 把"被拦下"当"防住了"**：**接受，但用词要更狠**。§3.4 证明："独立仪器也报"**不等于**"这个 finding 是真的"。
  建议块头写死：**`block_precision` 的上界是"与 ruff 的一致率"，不是精确率**；要测精确率必须换 oracle，而本机（无 bandit/semgrep、PyPI 不可用）**换不了**。
- **I7 [S2] 读数不带 `reading_context`**：**接受**（§1 freeze 已有）。
- **I8 [S1] 仪器读了 treatment 的配置**：**我反驳失败——接受其反驳，并把验证做得更狠**。
  诱饵实验（顶层 + **嵌套**）：【实测】不带 `--config` 时诱饵 `ruff.toml`（`select=["E501"], line-length=200`）生效 → `[]`；
  带冻结 `--config` 时 → 报出 `F401 + E501`；**嵌套诱饵**（`decoy2/sub/ruff.toml`）同样被压掉。
  ⇒ `--config` 的等价隔离**成立**，而且比他们自己举的例更强（他们只测了顶层）。

## 3 实跑四项（原始输出）

### 3.1 (a) `tools/ab_measure.py` 在本仓库上跑通 —— **unavailable（拒绝作为读数）**

观测时间 2026-10-07（文件 mtime `2026-10-07T12:20:27Z`，49,503 B）。

`@text
$ python tools/ab_measure.py --tree . --mode scan,security --out .tmp/ab-measure/repo.json
EXIT=0   WALL_S=0.2
stdout: (空)
stderr: (空)
.tmp/ab-measure/repo.json 存在 = False
$ grep -c "__main__|def main|sys.exit" tools/ab_measure.py   → 0 处（只有第 47 行 import argparse）
`@

**补充观测（本文档落地前最后一次查）**：文件在 `2026-10-07T12:22:16Z` 已长到 92,877 B，但 `__main__` / `def main` 仍为 **0 处** ⇒ 到该时刻仍未交付入口点（§6 U-1 因此保持未决）。

**结论**：该工具此刻**没有入口点**（不是"跑得不好"，是"跑不了且说自己跑好了"）。
按它自己冻结的退出码语义（`0` = 跑完且每个量都 available、没有 red），
**exit 0 + 零输出 + 无产物文件**是最坏的一种组合。⇒ 六个量**一个都不能算作它的读数**。

**我的 fallback 首读**（**明确不是** ab_measure 的读数；冻结配置 `.tmp/ab-pilot/frozen.toml`，`select = [F401, E501, S105, S106, S107, S608]`）：

| 量 | 读数 | 口径 / 命令 |
| --- | --- | --- |
| 规范性 | 262 文件 / 115,511 行 / **5,195 findings** = **44.97 条每 KLOC**；干净文件率 **0.0763**；`E501` 5,101 / `F401` 72 / `S105` 14 / `S106` 8 | `ruff check --config .tmp/ab-pilot/frozen.toml --output-format json --no-cache <262 个 git 跟踪 .py，排除 tests/fixtures/>` |
| 安全性 | `S` 命中 **22**（`S105` 14 + `S106` 8）——**只有 2 个 S 码在冻结选择里**，bandit/semgrep 全部不存在 | 同上；这 22 条里有本仓已登记的误报（§3.4） |
| 可用性 | **unavailable** | 原因：本次没有可用的冻结测试 oracle 输入（未提供 `--oracle` / pass_to_pass 清单） |
| 精确 | **3/3 被独立实现确认**（n=3，构造样本，**不给比率**） | §3.4 |
| 高效 | **p50 = 1721.1 ms / p95 = 1930.6 ms**（n = 31，剔首个冷启动 1668.4 ms） | §3.3 |
| 全自动化 | **unavailable** | 原因：本次没有 run/action JSONL 输入（协议侧尚未产出） |

### 3.2 (b) 两臂可分离的证明 —— **自举路线下不成立；外部路线下给判据**

**构造**（`git checkout-index --all --prefix=.tmp/ab-pilot/arm-off/`）：834 个跟踪文件，**无 `.git`**（不是 clone），无未跟踪产物。

**按 ab-instruments 的净化清单删除 13 条路径** → 断言 (a) 全绿（原始输出）：

`@text
policies exists = False          AGENTS.md exists = False        validation exists = False
knowledge exists = False         docs/project/engineering-policy-platform exists = False
docs/project/architecture = False  docs/mirrors = False          tests/fixtures/rules = False
tests/fixtures/decisions = False  evaluation = False              registry = False
examples/dsh = False             .git exists = False             .dsh/.policy dirs = 0
`@

**断言 (b)（规则身份正则）在它自己的保留集上就是红的**（原始输出）：

`@text
正则 \\b(ARCH|SEC|STYLE|DOC|TESTING)-\\d{3}\\b  →  matches = 558 over 80 files
   docs/project/rule-effects/规则效果演示报告.md   x62     ← 不在清单里
   tests/unit/test_loader.py                      x52     ← 保留集
   tests/unit/test_hook_violation_visibility.py   x33     ← 保留集
   tests/unit/test_validator_checkers.py          x31     ← 保留集
   docs/project/rule-effects/多违规案例检测报告.md  x28     ← 不在清单里
按目录聚合（前 6）：tests/unit 247、tests/integration 94、docs/project 90、tests/fixtures 31、tests/contract 27、tools/** 若干
`@

⇒ 两条结论：① **`docs/project/rule-effects/**` 与 `docs/project/reviews/**` 不在清单里**（90 条命中，纯新增泄漏面）；
② 断言 (b) 若按原文扫全树，会把**它自己保留的 `tests/**`** 判脏——说明这条"正则兜底"要么红得没法用，要么被范围豁免到形同虚设。**这不是自欺，但是未定义**。

**决定性观测**（原始输出）：

`@text
# cwd = 净化树（policies/ validation/ 全无）
$ cd .tmp/ab-pilot/arm-off
$ PYTHONPATH=<真仓>/src  python -m policy.check src/policy/models.py --json
    "rule_count": 43, "decision": "allow", "rule_set_hash": "sha256:50202675b6ca401368bdd75ad67b440e66849f27faf237a2265043a8eaa4b33c"
$ PYTHONPATH=<净化树自己>/src  python -m policy.check src/policy/models.py --json
    "rule_count": 43, "effective_rule_count": 40, "skipped_rule_count": 3      ← 同样加载了真仓的 43 条规则

# 从净化树里按相对路径读 treatment：
$ Get-Content .tmp/ab-pilot/arm-off/../../../policies/coding/DOC-001.yaml   → 打出了规则正文
# 历史泄漏（自举路线）：
$ git show HEAD:policies/coding/DOC-001.yaml                               → 打出了规则正文
# 本工作区里还留着 50 个含 policies/ 的旧 .tmp 树
`@

**机制**：`src/policy/check.py:165-172`

`@python
def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        if (candidate / "policies").is_dir() or (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()
`@

规则根**跟随调用它的代码**向上回溯；净化树嵌在本仓内部时，回溯逃逸到真仓库根。

**按 lead 的新路线（目标树在本仓之外、平台从工作树外的独立检出运行）重写断言**——(b) 的可分离性应断言这三条：

1. **`platform_code_outside_task_tree`**：从臂内打印 `policy.check.repo_root()` 与解析到的规则根，两者都必须在**平台检出**内、且都**不在任务树内**；
2. **`rule_set_hash_matches_checkout`**：平台载荷里的 `rule_set_hash` 必须等于平台检出的期望值；
3. **`explicit_rules_required`**：用显式 `--rules <平台检出>/policies` 调用；**不传它时必须失败**（本条能红 = 真检查）。
   附一条行为探针：**控制臂必须"跑一次写动作、看有没有平台介入"**，而不是只 grep 文件缺席。

### 3.3 (c) 判定延迟（n = 32，原始数字）

命令：`python -m policy.check src/policy/models.py --json`（含进程启动；cwd = 本仓根；`PYTHONPATH=src`），
每轮用 `[Diagnostics.Stopwatch]` 计时，原始 32 行落在 `.tmp/ab-pilot/latency.jsonl`：

`@text
1668.4 1811.4 1845.4 1914.5 1798.8 1721.1 1729.6 1622.1 1710.9 1801.7 1881.7 1714.2 1742.1 2063.9 1822.5 1765.4
1817.6 1696.9 1616.5 1930.6 1793.2 1878.6 1705.0 1611.3 1694.0 1624.8 1613.5 1626.3 1595.8 1640.7 1679.4 1661.3
WALL_TOTAL_S = 55.9      （32 次，含进程启动）
`@

| 统计量 | 值（ms） |
| --- | --- |
| 冷启动（第 1 次，剔除） | 1668.4 |
| min / max（n = 31） | 1595.8 / 2063.9 |
| **p50**（最近秩法） | **1721.1** |
| **p95**（最近秩法） | **1930.6** |

口径限制：这是 **CLI 端到端**（进程启动 + 导入 + 载入 43 条规则 + 取证 + 判定），**不是** hook 常驻进程内的单次判定；
hook 路径的单次延迟本次**没有测**（unavailable：需要真实 PreToolUse 载荷与挂载环境）。两者不可互换。

### 3.4 (d) 反事实精确率的第 1 批样本 + **两条仪器缺陷**

**样本构造**：取 3 个真实仓库文件，把一条**未使用的导入**（`import tempfile`）插进顶层导入块末尾（用 `ast` 定位插入行，
不改其它字节），得到"放行后的树"里的那份文件；`sha256` 前后都记（`.tmp/ab-pilot/cf-report.json`）。

| 样本 | 文件 | 插入行 | 平台判定 | 平台在该行的命中 | 冻结仪器在该行的新增命中 | AST 第二实现 |
| --- | --- | --- | --- | --- | --- | --- |
| cf-01 | `src/policy/scope.py` | 26 | **block** | STYLE-002 / error / F401 | F401 | 判 `tempfile` 未使用 |
| cf-02 | `src/retrieval/query.py` | 29 | **block** | STYLE-002 / error / F401 | F401 | 同上 |
| cf-03 | `src/validators/selection.py` | 17 | **block** | STYLE-002 / error / F401 | F401 | 同上 |

⇒ **3/3**：平台的阻断被**独立实现**在**同一行同一码**上确认。**但这是 3 个同构型的构造样本，不是比率**（n = 3、非随机抽样），
按纪律写"样本不足"，不给精确率。

**缺陷 D-1（行位移假象，[S1]）**：同一批比较里，冻结仪器还"新增"了
`E501@41/94/154`、`E501@42/132/137`、`E501@38/69/84/129/170` —— 它们**全部**只是因为在插入点**上方**动了行号而 +1。
⇒ 任何 `(path, code, line)` 集合差的"新增发现"判据，在**插入**类编辑上会**系统性多报**（本样本 3 次里多报 3 / 3 / 5 条）。
**修**：diff 感知匹配（基准行号 ≥ 插入点 → +shift），或只在**改动行集合**上比。

**缺陷 D-2（`block_precision` 不是精确率，[S1]）**：取一个**真实会被拦下**的文件 `src/policy_api/errors.py`：

`@text
平台：decision = block
  SEC-004  error  line=43  value=S105
  SEC-004  error  line=44  value=S105
  STYLE-001 warning line=141 value=E501
冻结仪器（独立配置、独立调用）：S105@43, S105@44, E501@140, E501@141
`@

按协议的判据（"独立仪器在改动行上新增至少一条 → red"），这一条会被记成**确认的真阳性**。
但 `policies/security/SEC-004.yaml:22-23` **明写**：

> 误报：`TOKEN_EXPIRED = "token_expired"` 这类错误码常量被判 hardcoded password（**实测 `src/policy_api/errors.py:43`**，同文件 `:44` 亦然）。

⇒ **同一个位置，平台判"违规"、独立仪器"确认"、而本仓自己的规则注释判"误报"**。
两条结论：① `block_precision` 的上界是「**与 ruff 的一致率**」，不是精确率；② 这类误报**结构性测不出来**，
因为仪器与平台共享同一个底层 linter 的启发式。**修（只能三选一）**：改名成 `ruff_agreement`；或换外部 oracle（本机拿不到 bandit/semgrep、PyPI 实测不可用 ⇒ **现在换不了**）；
或把"已登记误报清单"作为**独立的人工 oracle 子集**（本仓已有 16/22 的核对结论，方案 §1 第 10.4 节）参与打分。

## 4 成本实测

| 项 | 墙钟 | 说明 |
| --- | --- | --- |
| (a) ab_measure | **0.2 s** | 空转；**不是**一次真实测量 |
| (a) 我的 fallback 首读 | ≈ 20 s | 262 文件 ruff 一次调用 + 行数统计 |
| (b) 净化树构造 + 5 轮断言 | ≈ 3 min | 834 文件 checkout-index + 13 条删除 + 正则扫全树 + 3 次平台调用 |
| (c) 延迟 32 次 | **55.9 s**（实测计时） | 1.75 s/次（含进程启动） |
| (d) 反事实 4 次平台调用 + 2 台仪器 | ≈ 40 s | 每次平台调用 ≈ 1.7–2.1 s，与 (c) 一致 |

> 口径：**只有 (c) 是精确计时**（脚本内的 Stopwatch 总时长）；(a)(b)(d) 的三行是我按命令边界估的，**标为估**，不要当实测数字引用。

**据此修订"全量 A/B 要多少机时"的量级**：
- **判定侧不贵**：每 1,000 次判定 ≈ 1,000 × 1.72 s ≈ **29 分钟**（p50）。
- **贵的是模型侧与测试侧，而这两项本次都没测**：
  - 模型调用（token/墙钟）——本次**没有**真实 Agent 运行，unavailable；
  - 测试 oracle（pytest 全套 + `.tmp/tmp` ACL 绕法）——本次**没有**跑（§7）；
  - 反事实重建：每个被拦编辑 = 1 次平台判定 + 1 次仪器扫描 + 1 次树复制；按 50 任务 × 3 臂 × 10 编辑 ≈ 1,500 次重建 ≈ **45 分钟**（判定）+ 复制的文件 I/O。
- ⇒ 结论：**"机时"不是 A/B 的主要成本，模型 token 与人工编排才是**；任何引用别处"跑一次 8 小时"数字来估本项目的说法**没有依据**。

## 5 可实施性判决

**判决：A/B 不能现在跑。** 逐项列"补什么才能跑"，每条带**判据**（能红/能绿）：

| # | 缺口 | 级别 | 补什么 | 判据 |
| --- | --- | --- | --- | --- |
| B1 | 测量仪器无入口点：`exit 0` + 零输出 + 无产物 | S1 | 补 `__main__`/`main()`；无参数/无入口 → **exit 2** + `exit_reasons` | 跑一次 `--tree . --mode scan,security` 必须**产出 JSON 且 exit ∈ {0,1}**；把入口注释掉必须 **exit 2**（修复前会红） |
| B2 | 隔离判据是"路径删除"，可被"调用哪份代码"绕过（§3.2） | S1 | 三条代码路径断言：`platform_code_outside_task_tree` / `rule_set_hash_matches_checkout` / `explicit_rules_required` | 把平台检出**移进**任务树 → 三条断言必须红；移到树外 → 绿 |
| B3 | `block_precision` 与平台同源，测不了精确率（§3.4 D-2） | S1 | 改名 `ruff_agreement`，或引入外部 oracle（现在没有），或把已登记误报清单当人工 oracle 子集 | 用 `src/policy_api/errors.py` 当**阳性对照**：指标必须**不再**把它算成真阳性 |
| B4 | 位置匹配不是 diff 感知（§3.4 D-1） | S1 | diff 感知的新增发现判据 | 用本文档的 3 个插入样本当**变异体**：naive 版必须报出假新增，修后必须归零 |
| B5 | L4 行为探针缺正向对照（§1 P4） | S2 | 在临时 run 里**故意挂上** hook，证明探针**会红** | 挂 hook → `runtime_hook_marker_seen = true`；不挂 → false（两段读数都落盘） |
| B6 | 可用性 oracle 在"净化树"上跑不动（ab-protocol 实测 12 个模块收集失败） | S1 | 新路线下任务树自带自己的测试；`U1` 只认 `COMMON`，并**双报** `U1含/U1不含` | 两臂都必须 `collect` 成功；`COMMON` 为空 ⇒ 该 task 无效 |
| B7 | 外部任务树 + 独立平台检出**尚未建立** | S1 | 找一个本仓之外的真实仓库当任务树；平台检出放到树外 | 树里 `grep -r "ARCH-[0-9]{3}"` = 0；`repo_root()` 不在树内 |

**现在就能跑的部分**（不需要上面任何一条）：判定延迟、我这种 fallback 规范性/安全首读、反事实的**计数**（不是比率）。
**先把 B1 + B2 + B3 补掉**，再谈 B6/B7——因为前三条会让**已经跑出来的读数**失去意义。

## 6 交流记录（谁提了什么 / 接受还是反驳 / 最终怎么定 / 未解决的分歧）

### 6.1 ab-protocol（task-11）

| # | 谁提的 | 内容 | 对方回应 | 最终 |
| --- | --- | --- | --- | --- |
| L-1 | 我（红队） | 8 条可证伪点逐条判决：**真能证伪** 1/3/4/5/8；**测不出来或不足以判定** 2/6/7；并指出漏掉的最危险一条 = **两臂失败模式不对称** | 全部接受：第 2 条改 ±MDE 等价界 + 功效优先级更高；第 6 条 `U1` 升主结局并**反驳"U1 不可游戏"**；第 7 条改结构隔离；`block_class` 三分 | 已冻结（`ab-protocol.md` §1.4 / §4 / §7） |
| L-2 | 我（红队） | 污染检查面不够：git 历史 / 全局 `.dsh` home / Agent 自跑 linter | ①②③ 全接受；① 被 lead **限定适用范围**：目标是本仓之外的树，本条保留为**自举路线的证伪记录** | 已冻结（§4.3 L5/L4、§4.6） |
| L-3 | ab-protocol | 请我攻：L4 探针强度 / `U1含 vs U1不含` 的差额 / P8 怎么证伪 | 见 L-4、L-5、L-6 | 三条**未回**（U-1/U-2/U-3） |
| L-4 | 我（红队） | **L4 探针是单向的、且未标定**：① 它的"会打标记"证据来自 `--self-check`，**正常 PreToolUse 是否打标记未经我验证**；② 若 harness 只收 Agent 的 stdio，hook 子进程的 stderr 会被吞 → **假阴性**；③ 标记不带 `request_id` 时，别的进程打出标记会造成**假阳性** → 整 run 被误废 | 待回应 | **未解决分歧 U-1** |
| L-5 | 我（红队） | **`U1含` 与 `U1不含` 的差额本身就是处理效应**：治理面模块只在 treatment 臂可收集（off 臂实测收集失败）。⇒ 该差额**不能**当结局报告，只能当"支撑集属性"；收不齐的臂里 `U1含` 应记 `unavailable` 而不是 0/fail；**两臂差值禁止计算** | 待回应 | **未解决分歧 U-2** |
| L-6 | 我（红队） | **P8 的路径前缀断言不够**（§3.2 已证：树里没有 `policies/` 也照样加载 43 条规则）。本机**给不出文件系统级隔离**，但能给**更强的代码路径探针**（§3.2 的三条断言） | 待回应 | **未解决分歧 U-3** |

### 6.2 ab-instruments（task-12）

| # | 谁提的 | 内容 | 对方回应 | 最终 |
| --- | --- | --- | --- | --- |
| M-1 | 我（红队） | 接口冻结请求 7 条 + 仪器攻击 I1–I8 | §1–§7 逐条答完；I1/I2/I3/I4/I5/I6/I7 接受，I8 **反驳** | 已冻结 |
| M-2 | 我（红队） | 复验 I8：**诱饵配置实验**（顶层 + 嵌套），`--config` 确实压掉被测树的配置 ⇒ **接受其反驳**，并指出我的验证比他们自己举的例更强 | —— | 分歧关闭 |
| M-3 | 我（红队） | **I3 的实证反例**：`tools/ab_measure.py` 无入口点却 `exit 0`（§3.1）。按它自己的语义，exit 0 = 全部 available 且无 red ⇒ 静默空转被报成成功 | 待回应 | **未解决分歧 U-4** |
| M-4 | 我（红队） | **I2 的实证缺陷**：`(path, code, line)` 集合差在插入类编辑上系统性多报（3/3/5 条假新增）；**I6 的实证反例**：`errors.py` 的已登记误报被"独立仪器确认"（§3.4） | 待回应 | **未解决分歧 U-4** |

### 6.3 与 eval-harness（AB-5 臂运行时）

| # | 谁提的 | 内容 | 结果 |
| --- | --- | --- | --- |
| H-1 | eval-harness | 送"净化清单 + 断言命令"请我攻，自陈 5 处怀疑 | 已给证据：`docs/project/rule-effects/**`、`docs/project/reviews/**` **不在清单里**（90 条命中）；断言 (b) 在保留集上已红；**树里没有 `policies/` 也照样加载 43 条规则**（§3.2）。**未解决分歧 U-3**（路径前缀断言 vs 代码路径断言） |

### 6.4 未解决分歧清单（不和稀泥）

- **U-1**：`tools/ab_measure.py` 当前的"exit 0 + 零输出 + 无产物"是否算缺陷。我判 **S1 缺陷**（按它自己的退出码语义）；
  若 ab-instruments 主张"文件正在写、尚未交付"，那也必须是 `unavailable`（**不是**可用读数）——两种读法都不允许把它当"跑通"。
  **同一条也适用于 L4 探针的标定**（L-4）：我要求的正向对照（挂上 hook 必须变红）**没有收到**。
- **U-2**：`U1含` 该不该报"两臂差额"。我判**不该**（差额由处理决定，不是结局）；ab-protocol 主张"两个数都报、差额来自哪几个模块也写"。
  折中我只接受一半：**两个数都报，但只报"哪些模块进不来"的清单，不报"差值"**。
- **U-3**：`isolation_level` 能到哪一档。我判本机只能到 `code_path_verified`（拿不到 fs 级隔离）——
  除非补上 §5 B2 的三条断言，否则**不许**写 `fs_isolated`；这一条我与 ab-protocol 一致，与 eval-harness 的"路径前缀断言"不一致。
- **U-4**：`block_precision` 的名字与分母。我主张**改名**或加"`errors.py` 阳性对照必须不再算真阳性"的判据；
  ab-instruments 目前只写了两个局限（可重建子集偏置、只测 precision 不测 recall）。**未决**。

## 7 我没验证什么

1. **没有外部任务树**：本仓之外的仓库、独立平台检出都**没有建立**；(b) 的断言按新语义只给了**判据**，没有在真实外部树上跑过。
2. **没有真实 Agent 运行**：一次模型调用都没发；token、模型版本漂移、会话隔离**全部未测**（unavailable）。
3. **没有跑测试 oracle**：`pytest` 一次都没跑（本机 `.tmp/tmp` ACL 已知会 INTERNALERROR），所以"可用性"那一格是 unavailable，
   而不是"通过/不通过"。`COMMON` 支撑集我**没有**独立复算（引用 ab-protocol 的 2136→1832/12 errors）。
4. **没有跑 ab_measure 的任何一条真实读数**：它此刻没有入口点（§3.1）；我的首读是**自己的**冻结配置，**不能**当它的读数——
   两者在 `select` 集合上不同（我 6 个码 vs 平台 60 个码），绝对数**不可比**。
5. **反事实样本是构造的**：3 个 F401 插入 + 1 个已登记误报文件；**不是随机抽样**，n = 3/1 **不给比率**；
   没有覆盖"平台误拦"的其他类别。
6. **延迟只测了 CLI 路径**：hook 常驻路径、插件路径、并发下的延迟**都没测**；本机只有一台机器，没有异机复现。
7. **没有做 L4 探针的正向对照**（挂上 hook 看标记是否出现）——这是 §5 B5 要求的，我**没做**，所以 L4 的强度我判"未标定"。
8. **没有验证 `--config` 对 `per-file-ignores` / `extend` 等更复杂的被测树配置也压得住**（我只测了顶层与嵌套的 `select`/`line-length`）。
9. **没有审计平台侧对 A/B 的改动**：`src/policy/check.py`、`validation/**` 等的当前字节我按只读引用，**没有**核过它们是否被本轮任务改过。
10. **两处待对方确认**：ab-protocol 的三条回执（U-1/U-2/U-3）与 ab-instruments 的 M-3/M-4 回执**截至本文档没有收到**；
   本文档按我当前的合理假设写完，收到回应后应在「交流记录」里补一行，**不改已有证据**。

## 3.1-bis (a) 的更正读数（【实测】，2026-10-07T12:24:32Z–12:26Z；**不改上文历史**）

> 上文 §3.1 是我在 12:20:27Z / 12:22:16Z 两次观测的**原始记录**，按"不回改历史"保留。
> ab-protocol 指出那是"写盘中途的版本"——**成立**。但他们的更正**本身也过期了**：我在 **12:24:32Z** 的版本上复验，
> `--self-check` 是 **exit 0 / all_passed = true**（他们说的是 exit 1 / all_passed=false）。两次都是同一份**正在被重写**的文件的不同快照。
> ⇒ 纪律（正是他们自己加进反面清单的那条）：**引用第三方读数必须带时间戳 + 文件指纹**。我测的版本：

| 项 | 值 |
| --- | --- |
| 文件 | `tools/ab_measure.py` |
| 我测得的版本 | size **126,545 B**，mtime **2026-10-07T12:24:32Z**（12:25:38Z 已变成 127,102 B / `sha256:b8dbb260…` ⇒ 它仍在被改） |
| 无参运行 | **exit 2** + stderr `ab_measure: 缺 --tree <DIR>（或 --self-check）` ⇒ §5 的 **B1 入口点条件已满足** |
| `--self-check` | **exit 0**，`all_passed = true`（含 `config_isolation.verdict = red` = 自证通过） |
| `--tree . --mode scan,security` | exit 1 / 14.3 s / 2.7 MB stdout / `--out` 文件存在 ⇒ **(a) 现在可跑** |
| `--tree .`（全 mode） | exit 1 / 17.7 s / 3.17 MB stdout |

**六个量的首读（**用他们的仪器**，all-mode，12:24:32Z 版本）**：

| 量 | 状态 | 读数 |
| --- | --- | --- |
| 规范性 | available | 384 文件 / 140,040 物理行 / 7,730 violations = **55.20 条每 KLOC**；干净文件率 **0.1953**（Wilson 95% 0.1588–0.2379）；解析失败文件 1 个（2 条）；`E501` 7,273 条占 94% |
| 安全性 | available（半同源） | 6,954 findings = **49.66/KLOC**；`by_implementation`：ruff_S 6,921 / 自写 AST 33；**route A（bandit/semgrep）unavailable**，`route_a_verified = false`；`S101` 6,766 条占绝大多数、`unknown` 档 6,844 |
| 可用性 | available 但**读数不可采** | `pytest_status = red` 且 `red = true`，**但 `counts = {total: 0, passed: 0, failed: 0, error: 0}`、`pytest_sets.default.exit_code = 4`（pytest 的 usage error）** ⇒ 见 V-2 |
| 精确 | **unavailable** | 没有 `--blocked-edits`；四个计数 = TP 0 / FP 0 / unreconstructible 0 / unverifiable 0、分母 0 |
| 高效 | **unavailable** | 没有 `--latency-cmd` |
| 全自动化 | **unavailable** | 没有 `--actions` / `--runs` |

**口径不可比声明（他们自己写的，我确认）**：`scanner.caliber.line_length = 88`，**不是**本仓 `validation/ruff.toml` 的 100。
⇒ ① 他们的 384 文件读数、② 上文 §3.1 我的 262 文件 fallback、③ 平台的 262 文件读数，是**三套不同口径**，**不许互比**。

**这次复验新抓到的 4 条缺陷（给 ab-instruments）**：

- **V-1 [S1] 顶层 `unavailable[]` 汇总漏项**：`block_precision.status = "unavailable"` 且块级 `unavailable = [{what: "block_precision.precision", …}]`，
  但顶层 `unavailable[]` **只有 `automation` 一条**。读摘要的人会得出"只有 1 个量不可用"，而实际是 2 个。
- **V-2 [S1] 把"跑不了"报成"红的结局"**：usability 的 pytest 调用 `exit_code = 4`（usage error）、`counts.total = 0`，
  块级却给 `pytest_status = "red"` / `red = true`。这正是 §1 P6 攻击的形状：**基础设施失败被算成结局**。
  修：`exit_code ∈ {2,3,4}` 或 `counts.total == 0` 时该块必须 `status = "unavailable"` + reason（或单列 `infrastructure_failure`），**不许**进 red、更不许进任何分子分母。
- **V-3 [S2] 顶层包探测把字符串当可迭代对象**：`usability.imports.reason` 原文是"在被测树的 **s, r, c, ,, .** 下没找到带 `__init__.py` 的顶层包"——
  输入被逐字符拆开了（应为 `src`、`.`）。证据就是这句原文。
- **V-4 [S2] "未请求的块"与"unavailable 的块"形状不同**：`--mode scan,security` 时另外四块**直接不出现**且 `unavailable[]` 为空；
  全 mode 时才出现并逐条写 reason。只跑子集的人会误读成"四个量都测了且没问题"。修：未请求的块也显式出现（`status = not_requested`）。

**§5 判决更新（12:26Z）**：**B1 已关闭**（入口点 + 误用 exit 2 + 全 mode 可跑，见上表）；但**新增 V-1 / V-2 两条 S1**。
⇒ 需要先补的清单从 "B1 + B2 + B3" 改成 **"V-1 + V-2 + B2 + B3"**（V-2 与 B3 同族：都是让"不可用/同源"别冒充结局）。

## 6.3-bis eval-harness 的回执（逐条）与新增缺口 B8

| # | 我提的 | 对方回应 | 我的复回 |
| --- | --- | --- | --- |
| H-1 | 净化清单漏 `docs/project/rule-effects/**` / `docs/project/reviews/**` | **接受一半**：确实漏了；但 lead 已裁定树锚在平台之外（固定夹具项目），这两条路径在新路线上不在任务树里；自举路线上补。给了读数：夹具基线 **6 文件 0 命中**；自举路线（本仓副本）**1089 命中** | **接受其限定**（我的攻击是自举路线专属）。**但两个数字不可比**：我量到的是 **558 命中 / 80 文件**（正则 `\\b(ARCH\|SEC\|STYLE\|DOC\|TESTING)-\\d{3}\\b`，作用域 = 按净化清单删 13 条路径后的 834 文件树）；他们的 1089 是**另一套正则/作用域**。⇒ 按本仓纪律，**两个数都要带口径**（正则原文 + 扫描根 + 是否排除 fixtures），否则不可比、不许互相印证。 |
| H-2 | 删掉 `policies/` 仍加载 43 条规则 | **接受并已实现为断言**：新增 `runtime_probe`（从任务树里跑一次判定）+ 正向对照 `--probe-platform-path`；控制臂 `clean=True`，正向对照 `clean=False` 且给出"加载到了 43 条规则 `sha256:50202675b6ca40136`…" | **接受，且交叉验证成立**：他们报的哈希前缀与我在 §3.2 实测的 `rule_set_hash = sha256:50202675b6ca401368bdd75ad67b440e66849f27faf237a2265043a8eaa4b33c` **同源**。这条从"我的复现"变成了"他们的断言"，正是 P9/B2 要的形状。 |
| H-3 | `.git` 泄漏面 | **接受**：`vcs_dir_absent` 降级为"自举路线证伪断言"，新路线记 `not_applicable`（复制忽略 `.git`） | 接受。 |
| H-4 | advisory 的反馈必须真的到达 Agent | **部分接受**：保证"判定来自真实入口、臂不执行阻断"，但不负责把反馈送进 Agent 上下文（属 dsh 插件与任务集）；给 decision + audit 引用作可核对 marker；建议断言放 AB-1/AB-3 | **保留分歧（U-5）**：`audit 里有 decision` ≠ `Agent 看到了反馈`。若无人保证送达，`advisory` 就是"off + 记账"，`enforced − advisory` 会退化成整个治理效应，协议第 1 条的拆分失去意义。**我要求的不是他来送，而是"送达"这件事有人认领并断言**（建议 AB-1 在臂定义里写死、AB-5 提供 marker）。在有人认领之前，协议**不许**把该臂称作"反馈臂"。 |
| H-5 | 降级不许把"跑不了"读成"拦住了" | **接受**：判据 = "audit 有 block **且** 文件哈希不变"，exit_code 非 0/2 一律记 unavailable；`block_class` 分列**尚未实现**，已进缺口清单 | 接受（未实现部分记缺口）。 |
| H-6 | 反馈文本逐字相同要在"两臂都产生"的前提下比 | **接受**：L4 同时报 `marker_seen` 与 `expected`（off 臂是 false，不是"空==空"） | 接受。 |
| H-7 | （对方主动补的一条，我没攻） | **L5（宿主 `.dsh` 接线 0 命中）在本机是红的：26 处指向本仓/插件**，照实记 fail 未放宽 | **这条比我预想的更硬，直接改判决**（见 B8）。同时要口径：我自己的扫描是 `Get-ChildItem $env:USERPROFILE\.dsh -Recurse -File -Include *.json,*.yaml,*.yml | Select-String "policy-hook\|policy_hook\|policy.check"` → **4 个文件命中**；他们的"26 处"是**另一套模式/单位**（处 vs 文件）。⇒ 同样必须带口径。 |

### 新增缺口（判决表补充）

| # | 缺口 | 级别 | 补什么 | 判据 |
| --- | --- | --- | --- | --- |
| **B8** | **宿主级接线在本机是红的**（`%USERPROFILE%\.dsh` 里有多处指向本仓/插件的 policy 接线；我实测 4 个文件命中，eval-harness 实测 26 处命中——口径待统一） ⇒ **本机无法证明控制臂干净** | S1 | 要么在**没有全局接线**的宿主/环境上跑两臂，要么先停用全局接线并**重新探针**；把 L5 的"红"写进结论的**环境前提**，不许当成"跑之前顺手清一下" | 在目标宿主上：L5 命中 = 0（带口径的正则与作用域），**且**运行时行为探针在该宿主上不出现 `[policy]` 标记；两条都绿才允许开跑 |

⇒ **对 §5 的影响**：B8 与 B6/B7 同级（都是"环境不满足"），但它更靠前——**它决定"这台机器能不能当实验机"**。

## 3.4-ter P1（精确）的**首批真实读数** + 仪器天花板实测（【实测】，工具冻结版 132,173 B / sha256 40BD64F6…）

> ab-protocol 把"`精确` 全链路零读数"列为剩余攻击面。我用 §3.4 那 3 个插入样本 + 1 个**本仓已登记的误报**当输入，
> 跑通了全链路（反事实树构造 → delta → 计数）。命令：
> `python tools/ab_measure.py --tree .tmp/ab-pilot/base --mode blocked --blocked-edits .tmp/ab-pilot/blocked.jsonl --known-false-positive-edits .tmp/ab-pilot/knownfp.jsonl --out .tmp/ab-measure/precision-2.json`
> （`.tmp/ab-pilot/base` = `git checkout-index` 出来的 834 文件基线树；**3.0 s** 跑完 5 条编辑。）

| 读数 | 值 |
| --- | --- |
| `counts` | **TP 4 / FP 0 / unreconstructible 1 / unverifiable 0** |
| 分母 | 4（抽样单位 = edit） |
| `precision`（Wilson 95%） | **1.0**（[0.510, 1.0]）——**构造样本，不是估计**：3 条是同构型的 F401 插入 + 1 条已登记误报 |
| `p1-cf-04`（故意不可重建） | `outcome = unreconstructible`，reason = "old_string 在目标文件里出现 0 次（必须恰好一次）" ⇒ 不可重建路径**有读数**，且**不进分母** |

**① 我的 M-4① 攻击被他们修好了，而且两边的数字逐条对上**：新版本把行级口径单列成两个数
`secondary_caliber_rows_added_raw`（对行号漂移敏感）与 `..._shift_aware`（用 diff 的 equal 块回映射）：

| 编辑 | `raw` | `shift_aware` | 差额 = 我 §3.4 独立量到的假新增 |
| --- | --- | --- | --- |
| p1-cf-01 | 4 | 1 | **3** |
| p1-cf-02 | 4 | 1 | **3** |
| p1-cf-03 | 6 | 1 | **5** |

⇒ 我上一轮用**自己的**比较器量到"多报 3 / 3 / 5 条"，与新版 `raw − shift_aware` **逐条相等**。**B4 关闭**（不是"他们说修了"，是两套独立实现互证）。

**② 仪器天花板实测 = 0.0（我把本仓已登记的误报当阳性对照喂了进去）**：
`fp-01` 的编辑 = 在 `src/policy_api/errors.py` 里加一行 `TOKEN_REVOKED = "token_revoked"`（与 `SEC-004` 注释里登记的误报同类：**错误码常量，不是凭据**）。
- 主口径：`outcome = red`（仪器把这条**非缺陷**判红）；
- 阳性对照块：`declared_false_positives = 1`、`instrument_says_red = 1`、**`max_achievable_precision = 0.0`**。
⇒ **M-4② / I6 从"论证"变成"读数"**：在这台机器上，只要 declared_fp 集含这类样本，precision 的**天花板就是 0**。
那个 `precision = 1.0` 因此**只能**读成"这批样本里平台与仪器一致"，**不能**读成"平台的 block 有 1.0 的精确率"。

**③ 我自己差点报的一个假缺陷（留档，因为"证伪自己"也要能被读到）**：`fp-01` 的记录里 `new_findings = []` 而 `outcome = red`，
我第一反应是"红得没有证据"。查完整记录后**撤回**：证据在 `new_security` 通道里（`S105` + 自写 `ABSEC-009`，各 `extra: 1`）。
⇒ 不是缺陷，但有一条 **[S3] 可读性**问题：`outcome=red` 配空的 `new_findings` 极易被误读成"无证据的红"；
建议在 `red` 旁加 `evidence_channels: ["new_findings","new_security"]` 之类的指引（**建议，不是缺陷**）。

**④ 一条新的 [S2]（要他们确认口径）**：同一对 `raw / shift_aware` 覆盖的**通道不同**——`fp-01` 的唯一发现在 `new_security``里，
于是 `raw = 1` 而 `shift_aware = 0`。既然 `secondary_caliber` 的说明写的是"**差额本身是要读出来的量**"，
那么"差额"里就混进了"通道覆盖范围不同"这一项。**建议**：两个数都声明各自覆盖哪些通道（norm / security / tests）。

## 3.1-ter V-1 / V-2 / V-3 的**独立复验**（我跑的，不是引用他们的）

冻结版 `sha256:40bd64f605f9c988…` / 132,173 B。命令 = `python tools/ab_measure.py --tree . --out .tmp/ab-measure/recheck.json`。
**墙钟 493.9 s**（对比上一版同一命令 17.7 s——差额几乎全部来自 usability 这次**真的把整套 pytest 跑了一遍**）。

| 项 | 我复验到的 | 判决 |
| --- | --- | --- |
| **V-1** 顶层 `unavailable[]` | **3 条**：`usable` / `blocked` / `automation`（上一版只有 1 条） | **已修**（与他们自报的 3 条一致，独立确认） |
| **V-2** usability 归因 | `pytest_status = environment_unavailable`、`red = false`、`status = unavailable`（上一版是 `red = true`） | **已修** |
| **V-3** imports | `imports.reason = null`（上一版是"在被测树的 s, r, c, ,, . 下…"） | **已修** |
| 成本 | **整套 pytest ≈ 8 分钟/次**（493.9 s − 上一版 17.7 s） | 新增成本读数：可用性块是全套件里**最贵**的一格 |

**但复验发现一条新的 [S2]（措辞与自己的数字矛盾）**：同一次运行里
`usability.pytest_setss` 的计数是 `{total: 2136, passed: 2132, failed: 3, skipped: 1}`、`default.exit_code = 1`（pytest 语义 = 有测试失败），
而顶层 `unavailable` 里 usable 的 reason 原文写着"**没有任何一次 pytest 真的跑起来（全部 environment_unavailable）**"。
⇒ 读的人会同时看到"2136 条、2132 过"和"一次都没跑起来"。两者不可能都为真：要么计数来自某个真的跑起来的 set（那么 reason 的措辞是错的），
要么计数是残留/聚合错（那么计数是错的）。**我不替他们判定是哪一种**（我没有独立跑 pytest），只把矛盾摆出来：
**reason 文本必须与同一载荷里的计数一致**——这正是本仓"口径诚实"纪律里最容易被忽略的一条（数字对、话不对）。

**第二个观察 [S2]**：那 3 条 failed 与 `PytestCacheWarning … [WinError 5] 拒绝访问`（已知的 `.tmp/tmp` ACL 问题）同现在一份载荷里。
**分类规则必须是"失败是不是环境造成的"**，而不是"有没有出现环境告警"：如果 ACL 告警把 `exit_code = 1` 整体改判成 `environment_unavailable`，
那么**一次真实的测试失败会被环境问题吞掉**——这与我 §1 P6 攻击的是同一个方向（环境问题淹没处理效应），只是换了一侧。

## 3.1-quater ③-a 的矛盾**已确认**（同一份载荷、同一次 run）+ 我自己一条诊断**撤回**

**载荷身份**（我保存的原件）：`.tmp/ab-measure/recheck.json`，`sha256 202391d91980d24542552f40…`，3,455,435 B，
`reading_context.run.id = 93f2a560-36b3-48d8-9e71-46f304774e54`，`started_at = 2026-10-07T12:38:52.866036Z`，
`tool.argv = ["--tree", ".", "--out", ".tmp/ab-measure/recheck.json"]`。

**同一份载荷、同一个嵌套对象里同时成立**（ab-instruments 列的三可能里，**(ii) 混看两次运行**与 **(iii) 看成不同块**都被这一条排除）：

| JSON 指针 | 值 |
| --- | --- |
| `usability.pytest_sets.default.status` | `available` |
| `usability.pytest_sets.default.exit_code` | **1**（pytest 语义 = 有测试失败，不是 INTERNALERROR；INTERNALERROR 应是 3） |
| `usability.pytest_sets.default.counts` | `{total: 2136, passed: 2132, failed: 3, skipped: 1}` |
| `usability.pytest_sets.default.pytest_status` | `environment_unavailable` |
| `usability.pytest_sets.default.reason` | "**没有任何一次 pytest 真的跑起来（全部 environment_unavailable）**：pytest 自己报的 INTERNALERROR…`PytestCacheWarning … [WinError 5]`…" |
| `unavailable[0].reason`（block=`usable`） | 同一句话 |

⇒ 就是 **(i) 真矛盾**：同一次 run 里"2136 条 / 2132 过 / 3 失败 / exit 1"与"一次都没跑起来"并存。
**并且载荷没有携带支撑自己归因的证据**：`pytest_sets.default.stderr_tail = ""`（空），而 reason 引用了 INTERNALERROR。
⇒ 这是**读数错误**（同一个键下两种互斥事实），比"缺功能"严重；取舍（修 ⇒ 冻结指纹作废）由 lead 裁，我不替他定。

**我撤回自己的一条诊断（[S2] ④，"raw / shift_aware 覆盖的通道不同"）**：ab-instruments 给了**最小反例**，我接受其驳回——
`C1`（只有安全通道新增 `ABSEC-001 + S307`）：`raw = 0 / shift_aware = 0` ⇒ 安全发现**不进**这两个数；
`C2`（纯行漂移一条既有 E501）：`raw = 1 / shift_aware = 0`。
⇒ 我那个 `fp-01` 的 `raw = 1` **正是 C2 的形状**（norm 通道里一条既有发现被整体下移一行），不是"通道覆盖不同"。
**我怎么错的**：我从**一个样本**反推机制，而没有像他们这样先做最小反例——这正是我在别人的仪器上反复要求的做法。**按同一把尺子，我认这条错。**

## 3.1-quinquies 新冻结版独立复验（✅）+ 把"不可重复"更正为"确定性失败"

**指纹稳定**：`tools/ab_measure.py` = **134,417 B / sha256 `57e2aa27ab557e48765817cb…` / 12:43:06Z**，跑前跑后**同一个指纹**（我特意前后各取一次）。
命令 `python tools/ab_measure.py --tree . --out .tmp/ab-measure/recheck-v11.json`，**墙钟 490.7 s**。

| 我独立复验到的 | 值 | 与 ab-instruments 自报 |
| --- | --- | --- |
| `schema_version` | **1.1** | 一致 |
| `pytest_status / red / status` | `red / true / available` | 一致 |
| `counts` | `{total: 2136, passed: 2129, failed: 6, skipped: 1}`、`exit_code = 1` | 一致 |
| `classification_trustworthy / internal_error_source / internal_errors` | `true / null / []` | 一致 |
| `reason` | "pytest 退出码 1：6 failed / 0 error / 2129 passed（共 2136 条）" | 一致（**措辞与计数终于一致**） |
| 顶层 `unavailable[]` | `[blocked, automation]`（`usable` 已移出） | 一致 |
| `scanner.metrics` | 384 文件 / **7,753** / **55.289713** 每 KLOC | 一致 |
⇒ **③-a（真矛盾）与 ③-b（真失败被环境告警吞掉）两条都在新版本上关闭**，而且第三条见证齐了（r3 493.9 / 他们旧版 492.7 / 他们新版 482.1 / **我新版 490.7**）。

**并且我顺手复现了他们的根因**：我自己那条 `-p no:cacheprovider` 的命令**exit 4 / "ERROR: Unknown config option: cache_dir"** ⇒
"`-p no:cacheprovider` 让 `cache_dir` 变成未知选项" 这个诊断，**我这边逐字复现**（不是听他们说）。

**把"不可重复"更正为"确定性失败"**（这条会改他们的缺口清单）：那 6 条失败**不是随机漂移**——
我单独跑那 6 个 node id，**两次都是 `6 failed`（5.69 s / 5.60 s），node id 完全相同**：

`@text
tests/contract/test_wiring_inventory.py::test_wiring_json_contract
tests/integration/test_cli.py::test_json_reading_context_names_the_entry_the_tree_and_the_declarations
tests/integration/test_obligations_gate.py::test_the_payload_says_which_tree_and_which_ledger_it_read
tests/integration/test_provenance_loop.py::test_provenance_loop_reads_r_e
tests/unit/test_exemption_expiry.py::test_json_payload_key_set_and_its_version_axis
tests/unit/test_wiring.py::test_reading_context_names_the_tree_and_the_scope_declaration
`@

且 `git status --porcelain` 对 `tools/exemption_expiry.py / obligations_gate.py / provenance_loop.py / wiring_scope.py` **无输出**（这几个文件没有被本地改动）。
⇒ "3 failed（旧版）vs 6 failed（新版）"的差别**跟着工具版本走**，不是跟着运行走；**同版本我没测出漂移**（每版各 1–2 次）。
**结论要改口径**：现在能说的是"**6 条确定性失败**"，不是"这套测试不可重复"；要说"不可重复"，必须**同版本**重复跑 ≥2 次且失败集合不同。

**这对 A/B 是更硬的坏消息（B6 升级）**：基线树的自带测试**本来就红**（6 条确定性失败，至少 1 条是 `assert 'unavailable' == 'available'` 的键集/口径断言）。
⇒ 可用性主结局 `U1`（冻结测试恢复重跑）在**红基线上**无法直接使用：要么先把基线红**钉死成"已知失败集合"**并从分母里分列，
要么先修红——**不能**直接拿"pass_to_pass 是否仍绿"当读数。

## 3.1-sexies 回应"每次 pytest 是否 +2 个 `pytest-cache-files-*`"：**机制确认，速率未复现**

**ab-instruments 问的**：跑完一次 pytest，数一下 rootdir 里 `pytest-cache-files-*` 的增量；若"每次 +2"在我侧也成立，它就是**这台机器的 pytest 行为**，可进成本/风险表。

**我测的（原始输出）**：

`@text
[start] pytest-cache-files-* dirs in rootdir = 13
run A（1 个 node id，--basetemp=.tmp/ab-pilot/ptA）→ dirs = 13   (1 failed in 0.65s)
run B（同一 node id，无 --basetemp）                → dirs = 13   (1 failed in 0.61s)
run C（同上，再跑一次）                             → dirs = 13   (1 failed in 0.63s)
`@

⇒ **在我侧增量 = 0（三次）**，不是 +2。所以"每次 +2"**不能**被升级成"这台机器的 pytest 行为"——
它至少**依赖调用方式**（我这边是单用例 + 其中一次显式 `--basetemp`；他们是整套/带插件 argv）。要把速率写成常数，得先写清**在哪种调用下**。

**但机制那一段我端到端确认了**（这条比速率重要）。同一棵树上跑 `python -m policy.check src/policy/scope.py --json`：

`@text
"reading_context": {
  "tree": {
    "reason": "树摘要读不到：UnprovableError: 读不到目录：C:\\Users\\ZNM\\Downloads\\Memory\\pytest-cache-files-0697x19k（拒绝访问。）",
    "scope": "workspace",
    "status": "unavailable"
  }
}
`@

⇒ 他们的链条 **逐环成立**：rootdir 下有**拒绝访问**的 `pytest-cache-files-*` 目录 → 工作区树摘要 `UnprovableError` →
`reading_context.tree.status = unavailable` → 断言 `available` 的那 6 条 reading_context 契约测试**确定性失败**（§3.1-quinquies）。

**推论（比"6 条测试红"严重）**：
1. 这不是"某个人的仪器坏了"，而是**整棵树的读数都被降级**——任何带 `reading_context` 的载荷在这台机器上**证明不了自己读的是哪棵树**（本仓第 48 条要的正是这件事）；
2. 这些目录**对常规卫生检查不可见**：它们是**空目录**，而 git 不跟踪空目录，所以 `git status --porcelain` 里**一条都不出现**（我实测 `git status` 对它们无输出）——
   "看不见"不等于"不存在"，这正好是"测不到就要说测不到"的又一个现场；
3. 清理属**仓库级动作**，不在我写域，也不在 ab-instruments 写域 ⇒ 已由他们报 lead，我不擅自动手。

## 3.1-septies **撤回**我对 ab-instruments 漏检原因的那半句归因（同一错误模式的第 2 次）

我在 §3.1-sexies 的推论里写了「你那次的清理快照**恰好踩在这一点上**（git 不可见）」——**这半句我撤回**。
ab-instruments 的更正：他们的清理快照用 `Path.glob`，**不经过 git**；他们漏检的观测事实是「**那些目录晚于我的快照出现**」。
⇒ 两条原因是**各自独立**的，我把它们混成一条，属于**替别人的实现机制做推断**，而我没有、也无法再核对那份被逐字节回退的实现。

**证据边界（写清楚）**：我**能**证的只有两条自己的观测——① `git status --porcelain` 对那 13 个目录无输出（抽查最新一个是**空目录**，git 不跟踪空目录）；
② `reading_context.tree.status = unavailable` 及其 reason 原文。我**不能**证他们为什么漏检——那需要看他们的实现或过程日志，**我没有**。

**这是我第二次犯同一类错**（第一次是把 `raw / shift_aware` 的通道差异从一个样本推成结论，§3.1-quater）。
⇒ 给自己加一条可执行的规则，写在这里当尺子：**凡"别人为什么这样"的句子，一律分成两句写——「我测到的 X」与「我推出来的 Y（推理，未验证）」**；
推不出来的就写 @unavailable@。我对别人提的"不许估计"，先用在归因上。

## 3.1-octies 两个测量**并不冲突**：litter 是"落在该次运行的 workdir 里"（trace 已核）+ 选项 E

**我核了他们给的痕迹**（`.tmp/ab-fix`，22 个条目，按创建时刻）：

`@text
20:43:12 tests / pytest.ini     20:43:13 wd      20:43:14 pytest-cache-files-jfknz6ai + lt80hghf + out.json
20:43:24 wd2                    20:43:25 pytest-cache-files-io7veccf + ivxkbyib + out2.json
21:02:36 wd3                    21:02:37 pytest-cache-files-fp1x9g0s + 3m6th7pa + hyg1.json
                                21:02:39 pytest-cache-files-q9ps700u + ngx7t4w9 + hyg2.json
21:02:56 wd4                    21:02:57 pytest-cache-files-hnjxw6us + eb8ebbej + hyg3.json
`@

**合成的口径（比我们各自的说法都准）**：每跑一次确实产生 **2 个** `pytest-cache-files-*`，但它们**落在该次运行自己的工作目录里**
（他们的 `wd/wd2/wd3/wd4` 都在 `.tmp/ab-fix/`"下 ⇒ litter 也落在那里）；**只有工作目录/临时根指向仓库根时，它们才落在仓库根**。
⇒ 我的 `0 / 0 / 0`（根目录计数）与他们的 `+2`（自己的工作目录）**不矛盾**，是两个不同分母上的真读数。
我**撤回**上一轮"不能升级成机器常数"里隐含的"两方读数对不上"的意味：对得上，只是**分母不同**；正确的说法是"**每次运行 +2，落在该次运行的 workdir**"。
（仍然保留证据边界：trace 与他们的"晚于快照出现"**一致**，但我**无法**核他们快照的时刻——那部分仍是 unavailable。）

**加一个选项 E（不改尺、只改跑法）**——它让 lead 不必在"跑步机"与"换尺"之间二选一：

| 选项 | 换不换尺 | 测量后果 |
| --- | --- | --- |
| A 只清理目录 | 不换 | 摘要恢复可算，但**复发**（只要还有一次运行的 workdir 指向根） |
| B 加进 `DEFAULT_EXCLUDES` | **换尺** | 一次根治，但旧摘要不可比，且**今天没有轴**覆盖它 |
| C 跳过不可读目录并写进读数 | **换尺（更隐蔽）** | 摘要变成"部分覆盖"，不写清就是**静默少算**，与失败关闭取向相反——不推荐 |
| **E 强制 workdir 落在已排除目录 + 断言（新增）** | **不换** | 每次运行的 workdir/basetemp 必须在已排除路径（如 `.tmp/`）下；并断言"运行前后根目录的 `pytest-cache-files-*` 集合不变"。**不换尺、不复发**；代价是**每条调用路径都要带 workdir** |

E 的"修复前会红"证明是现成的：**不带 workdir 跑一次 → 根目录集合变化（或落在根）；带上 → 不变**。
我这三次 @0 / 0 / 0@ 只说明"我这三次的 workdir 没指向根"，**不足以**证明 E——要证明 E 必须**故意**把 workdir 指向根一次，看它是否 +2。**这一步我没做**（会再往根目录扔两个不可读目录，属仓库级副作用，我不在无授权时做）。

## 3.1-nonies 我接受 ab-instruments 的驳斥（第 3 次同类错）+ 我自己找杠杆的实测：**litter 会自毒**

**① 我的"和解"错了，我撤回。** 他们说"落点跟着 **rootdir（被测树根）** 走，不是跟着该次运行的 workdir"，证据是逐目录点数的：
`wd / wd2 / wd3 / wd4 各 0`，而 `.tmp/ab-fix`（含 `pytest.ini`" ⇒ 它是 rootdir）每次运行 +2、累计 10。**这个证据比我的强**：
我给的是**创建时刻相邻**（litter 与 `wd*` 同秒出现），那只证明"同一次运行产生"，**不证明落点**。
**我怎么错的（第 3 次同一模式）**：我又一次用**代理观测**（时间戳相邻）去定**位置/机制**，而没有做那个只要一条命令的判别测量（**在 `wd*` 里数 vs 在 rootdir 里数**）。
⇒ 尺子加一条：**凡"落在哪 / 谁做的"，必须用能区分假设的那个测量，而不是与两个假设都相容的观测。** 前两次分别是 §3.1-quater（通道差异）与 §3.1-septies（漏检原因）。

**② 我自己试了"杠杆"（在他们的结论 `unavailable` 那一格上），结果**反直觉**，并且发现一个更严重的东西**。
在**我自己的**一次性树 `.tmp/ab-pilot/roottest/`（含 `pytest.ini` + 一个用例；**没有碰仓库根**）上做对照：

`@text
before: 0
run1 cache_dir=被拒(../../.pytest_cache)  rc=0 litter=0
run2 cache_dir=被拒                      rc=0 litter=0
run3 -o cache_dir=.cache-writable         rc=0 litter=1     ← 可写的相对 cache_dir 之后**出现了** litter
run4 -o cache_dir=.cache-writable         rc=2 litter=3     ← 一旦出现，下一次直接**收集期报错**
     ERROR pytest-cache-files-rvyu71rt - PermissionError: [WinError 5] 拒绝访问。:...
     !!! Interrupted: 1 error during collection !!!
run5 cache_dir=被拒（回到 run1 的配置）    rc=2 litter=3     ← **回不去了**：树已被自己产生的目录毒住
仓库根计数：13 → 13（我的实验**没有**往仓库根扔新目录）
`@

**我测到的**：① 在这套配置下，**可写相对 `cache_dir` 之后出现了 litter**，而被拒的 `cache_dir` 两次都没有；
② 一旦 litter 出现，**后续在该 rootdir 里的 pytest 会因它收集期报错（rc=2）**——即 **litter 是自毒的，不只是"垃圾累积"**。
**我推不出来的**：为什么是 run3 触发（机制、哪个 pytest 分支创建它）——**写 `unavailable`**，不推。
**可核对的**：三个目录名 `pytest-cache-files-5f8scpvx / ntjldi4n / rvyu71rt` 就在 `.tmp/ab-pilot/roottest/`，谁都能复算。

**③ 这三条一起改了对 lead 的选项表**：
- 选项 E 的**杠杆半句**：不仅"未验证"——**我试的方向（cache_dir）在这套配置下是反向的**（它制造了 litter）。**杠杆未知**，标 `unavailable`；
- 选项 E 的**断言半句**：**更该常驻**了——因为 litter 不只是脏，它**会让同一 rootdir 的后续运行收集期失败**；
- **新风险入表**：任何"在某棵树里跑过测试"的动作，都可能**永久毒化那棵树**（13 个已存在于仓库根，且对 `git status` 不可见）。
  对 A/B 的直接含义：**臂树一旦被毒化，U1/U2 的读数就不再是"这棵树跑得怎么样"，而是"这棵树被毒成什么样"**——这属于"环境失败"而非"结局"，必须分列（与 B8 同级）。

## 3.1-decies 受控复现：**可读同名目录无害 / ACL 拒绝才是毒源**，而且**拒绝不可自行撤销**（新风险）

**受控树** `.tmp/ab-pilot/poison2/`（`pytest.ini` + 2 个用例；**仓库根 13 → 13 未变**）：

| 情形 | 我测到的 | 结论 |
| --- | --- | --- |
| **A** 建两个**可读**的同名目录 `pytest-cache-files-aaa111 / bbb222`（普通 `mkdir`） | `rc = 0`，`2 passed`，无收集错误 | **ab-instruments 的收窄成立**：**只是名字不毒化**（我独立复现，不是采信） |
| **B** 用 `icacls <dir> /deny <user>:(OI)(CI)(F)` 造一个**不可读**目录 `ccc333` | 可读性探针：`ccc333 -> PermissionError`；**运行中又新生成一个 `sjhsxg2i`（同样 PermissionError）**；pytest **`rc = 2`**，`Interrupted: 2 errors during collection` | **不可读 ⇒ 收集期失败**：这把他们标 `unavailable`"我只在你的树上见过、未独立复现"的**那一格补上了**——现在是**受控复现**（不是意外） |
| **C** 用 `icacls <dir> /remove:d <user>` 撤销拒绝 | **`rc = 5`（拒绝访问）**，目录**仍然不可读**；再跑 `rc = 2` / 4 个收集错误 | **我造的这个拒绝，我自己撤不掉**；而且**每跑一次更多**（失败是**渐进**的） |

**因此新增两条风险（进 lead 的表）**：
1. **"清理"可能做不到，而且尝试本身有副作用**：我以 owner 身份加的拒绝，`/remove:d` 返回 **rc=5** ⇒
   在**当前权限**下，一个被拒绝的目录**未必能被删/改**。**我没有**在仓库根试过清理（无授权），也**没有**跑 `tools/cleanup.py`（我的硬约束禁止）；
   但**警告成立**：谁去清那 13 个目录，**先在一次性树上验证能不能清掉**，别在仓库根第一次试——**失败会留下更多不可读目录**。
2. **我的实验残留**：`.tmp/ab-pilot/poison2/` 里有 **2 个我造出、我撤不掉的拒绝目录**（`ccc333 / sjhsxg2i`，外加 A 的两个可读目录）。
   它们**在 `.tmp/` 下** ⇒ 常规清理（删 `.tmp/`）**可能在这里失败**。**我无法自清**，如实登记，请 lead 决定用什么权限处理。

**证据边界**：我能证的是"**我造的拒绝 ⇒ 收集期 rc=2**"与"**我的账户撤不掉它**"；
我**不能**证仓库根那 13 个的拒绝是怎么来的、是否同源，也不能证管理员权限下能否删除——**都没测，写 `unavailable`**。

## 3.1-undecies 实测"删不掉"：ACL 读不到 + **两种删除方式都失败**（决定 lead 选项 A 的可行性）

**ab-instruments 的只读查询我复核了**（同一结果）：`icacls <dir>` 对 `.tmp\ab-pilot\poison2\pytest-cache-files-ccc333`
与仓库根的 `pytest-cache-files-0697x19k` **都是 "Access is denied"** ⇒ **连 ACL 都读不到**，"读 ACL → 改 ACL"这条修复路径不成立。

**他们保留的那半句（"读不到 ACL ≠ 不可能删"）我测了——在我造的这一类拒绝目录上，它删不掉**：

`@text
Remove-Item .tmp\ab-pilot\poison2\pytest-cache-files-ccc333 -Recurse -Force
  → 对路径"...ccc333"的访问被拒绝；exists after = True
cmd /c "rmdir /s /q .tmp\ab-pilot\poison2\pytest-cache-files-sjhsxg2i"
  → exists after = True（目录仍在）
仓库根计数：13 → 13（我的实验始终没有碰它）
`@

⇒ **在本机当前权限下，"不可读目录"= 既读不到 ACL、也删不掉**（两种常规删除方式各测一次，都失败）。
**残余也在长**：`.tmp/ab-pilot/poison2/` 下的 `pytest-cache-files-*` 从 4 个长到 **8 个**（其中 `aaa111/bbb222` 是我造的可读目录、
其余是 pytest 自己造的不可读目录）——这与"失败是渐进的"一致。

**证据边界（不许外推）**：我测的是**我用 `icacls /deny <user>:(OI)(CI)(F)` 造出来的**拒绝目录；
仓库根那 13 个**是不是同一类 ACL 我无法核对**（它们的 ACL 我读不到）。⇒ 对仓库根的结论是**风险，不是读数**。

**对 lead 选项表的最终影响**：
- **选项 A（清理）在当前权限下被实测为"不可执行"**（不是"成本高"）：读不到 ACL、删不掉、连我自己加的拒绝都撤不回；
- 因此现实选项收敛为：① **换一个有权限的执行者/机制**（候选：`diagnose-windows-sandbox-acl` 技能，见下），或 ② **换尺/排除**，或 ③ **接受 `reading_context.tree = unavailable`**；
- **一条操作纪律**：任何"在树里跑测试"的动作都可能**在该树里留下删不掉的目录** ⇒ A/B 的臂树必须**每次全新副本 + 用完丢弃**，
  且丢弃前先查"有没有不可读的 `pytest-cache-files-*` "（只查名字会漏，见 §3.1-decies 的 A 情形）。

**关于 `diagnose-windows-sandbox-acl` 技能**：ab-instruments 提到它但没跑，我**也不跑**——它会**改 ACL**（仓库/系统级副作用），不在我的写域，且直接违反"尝试可能更糟"这条刚被实测的教训。
它是**候选执行者**，不是我能自行使用的工具；要不要用、谁用，交 lead 定。

## 3.1-duodecies 边界再收紧一格（**接受 ab-instruments 的更正**）：是"当前权限上下文下不可执行"，不是"不可能"

他们在 §3.1-undecies 之后指出一条**我没写全的边界**，我接受并据此更正我自己的措辞：

- 我那两次删除（`Remove-Item -Recurse -Force` 与 `cmd /c "rmdir /s /q"`）都是在**同一个非提权用户** `desktop-4qltpcn\znm` 下做的；
- 因此准确写法是"**在我实测的那个权限上下文里不可执行**"，**不是**"不可能删"——后者会**关掉一扇其实没测过的门**（换主体 / 提权）；
- 那扇门**我和 ab-instruments 都没去开**（越权、且不在任何人的写域）⇒ 标 **未测**，不标"没救"。

**我的推理错误在哪**：我把"两次失败"直接升格成"不可执行"这一**绝对**表述，而我的两次尝试并不是两个独立主体——
它们只是**同一个人在同一权限下试了两种工具**。两个工具 ≠ 两个权限上下文。⇒ 尺子再加一条：
**"否定结论"必须写清它成立的*范围*（谁、在什么权限下、试了什么）**；范围外的部分一律 @unavailable@。
（这是本轮第 4 次收紧自己的表述：1 通道差异、2 漏检原因、3 代理观测定位、4 否定结论的范围。）

## 7.1 我的否定结论的**范围声明**（把 ab-instruments §10 第 3 条用在我自己的交付物上）

ab-instruments 把这一轮的四把尺子写成了他们的 §10，并指明其中一条**改正了谁**。我接受，并且**按同一条尺子回头查了自己的文档**：
下面每一条否定结论都补上"它成立的**范围**"与"范围之外（未测）"。**正文里三处措辞（§0 第 3 条、§3.4 D-2、§5 B3）按本表读**——
我不回改正文，按本仓"不回改历史"的同一纪律在此收紧。

| 否定结论（正文原话） | 它的**范围**（谁 / 哪里 / 什么条件下） | **范围之外**（未测 ⇒ @unavailable@） |
| --- | --- | --- |
| "测不了精确率"（§0 / §3.4 D-2 / §5 B3） | **本机现有仪器**：只有 ruff 0.14.13 + 自写 AST；bandit / semgrep / pylint / mypy / radon / vulture / pip-audit **全部不存在**，PyPI 实测不可用 | 换一台有独立扫描器的机器；**或**引入人工 oracle 子集（本仓已有 16/22 的核对结论可用，但**我没做**） |
| "（换 oracle）**换不了**"（§2 I6 / §3.4 D-2） | **本机 + 本次会话**（不允许新装依赖、无网安装） | 有网 / 有预装扫描器的环境 |
| "不可读目录**删不掉**"（§3.1-undecies） | **非提权用户** `desktop-4qltpcn\znm`，且只试了 `Remove-Item -Recurse -Force` 与 `cmd /c rmdir /s /q` **两种工具** | **提权 / 换主体**（未测）；`diagnose-windows-sandbox-acl`（未跑） |
| "**6 条确定性失败**"（§3.1-quinquies） | **本机这棵树** + 当次工具指纹 `134417 B / 57E2AA27…`；**同版本重复 2 次**、失败集合相同 | 别的机器 / 干净检出；**清理后是否转绿未测** |
| "**本机不能证明控制臂干净**"（§5 B8） | **本机宿主** `%USERPROFILE%\.dsh`，按 eval-harness 与我的**两套不同口径**（各自命中数不可互证） | 换宿主；**per-run 独立 dsh home（G13）未实测** |
| "**A/B 现在不能跑**"（§5 判决） | **本机 + 本轮交付时刻**的仪器 / 协议 / 臂运行时状态（B1、B4 已关闭；V-1/V-2 已修） | 补齐 B2/B3/B6/B7/B8 之后；换环境之后 |
| "延迟 **p50/p95**"（§3.3） | `python -m policy.check <file> --json`（**含进程启动**），单机，本仓 @ src/policy/models.py` | hook 常驻 / 插件路径 / 并发 / 异机 —— **均未测** |
| "可用性 ≈ 8 分钟/次"（§4） | **整套 pytest 在本机这棵树上**，四个见证（493.9 / 490.7 / 492.7 / 482.1 s） | 别的树 / 别的机器 / 增量跑（只跑子集） |

**一条兜底读法**：本文件里**没有**出现在上表的否定句，它的范围就是它**所在小节明确写出的那棵树 / 那次运行 / 那个版本**；
两者都没写清的，按 @unavailable@ 读，**不许**当"到处都成立"。

### 7.1-补 归属标签**更正**（接受 ab-instruments 的读法）：不是"各改正一半"，是"**同一句被连收两次**"

我在 §7.1 的附注里把第 3 条写成"**两半，各改正一个人的一半**"。ab-instruments 指出这个**总起句不准**，我接受。
按记录，实际形状是三步：

1. **他们先给范围**：用"读不到 ACL ≠ 删不掉"指出我那句话**没写清权限上下文**；
2. **我给出结论**：实测两法皆失败之后，我**写成**"不可执行"——这是**产出**，不是一次更正；
3. **他们再收紧范围**：把那句改成"在**我实测的那个权限上下文里**不可执行"。

⇒ 正确的记忆点不是"两人各有贡献"，而是：**同一条句子被连着收紧了两次**——那是"**表述过强**"的复发形态。
我的括号内容（范围那半来自他们、绝对表述那半来自我）本身没错，**错的是给它加了一个对称的总起句**。

**再补一处他们没说的**（不是反驳，是把两条句子分开记）：他们那句"别把'读不到 ACL'读成'不可能删'"**也被改过一次**——
**由我的实测结果改的**（他们据此把 D5 重写了）。所以完整记录是：
**两条句子各被改过，但"我那句"是被同一方连收两次**；把它压成"各改正一半"，两种形状都会被抹平。

**这就是本轮的收口**：我把这条留在这里，因为它示范了我们那把尺子最难的一半——**
不是"承认自己错了"，而是把"错在哪、谁改的、改了几次"记到不会读歪的程度**。
