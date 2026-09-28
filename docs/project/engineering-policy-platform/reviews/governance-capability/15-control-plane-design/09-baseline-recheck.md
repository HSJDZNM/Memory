# 09 · 台阶 −1② 基线读数重采（30 臂矩阵 + 11 fixture + 树摘要）

- **执行**：2026-09-28 23:20–23:35 +08:00（本机）；控制面重构会话（唯一写者）。只读对照 + 在新树里重跑，**未改任何平台源码**（唯一的临时改动是 §5 的正面控制，已按摘要证明撤回）。
- **post_tree（本文件读数属于它）**：`C:\Users\ZNM\Downloads\Memory-refactor` = 分支 `refactor/control-plane` @ `f6b9b79294a061e0d6b7c38dc9e663e4aaf61406`；读数时刻 `git status --porcelain` 为空。
- **pre_tree（对照读数的来源）**：`C:\Users\ZNM\Downloads\Memory\.tmp\round-10\c\trees\post`——round-10 记录里 `decisions-post.json` 的 `tree` 字段就是它。**它自己不是 git 仓库**：`git -C` 会一路上溯回答**主树**的 HEAD（实测 `6fa800e`），所以本文件不把任何修订号记在它头上。
- **仪器（逐字节未改，哈希为证）**：`probe_matrix.py` sha256 `2b447c7b1007009b52aa3a8239a5f24ba306cc77e40c10c003109f61485845b3`、`scaffold_full.py` `54beeb162b7ef0f5a518d52a9387ea41f89316acf1799dc27aa0be1fc61bb79a`（与 `01` 引用的原件同一组值，见原件 `instrument-hashes.json`）；fixture 侧 `decision_invariance.py` `2f8a962a3189197441B3D99C96222FFFC854CBCDD4ED92BAA94474EF7CF8D5BC`、`compare_decisions.py` `10a11ba62799df3782b5c6528498840f8e03ac5ef475e9f4b84ad133990c247d`。四份都是**原样复制**后调用，没有第二份实现。
- **解释器**：`C:\Users\ZNM\miniconda3\python.exe`（3.13.11 / pydantic 2.12.3 / pytest 9.1.1）——与 round-09 矩阵 `environment.interpreter` 同一路径，故读数可比。门禁本身仍按 `08` 的约定用 `CI_LOCAL_PYTHON` 指向主树 `.venv`（本台阶**没有跑门禁**，见 §7）。
- **声明范围（§4 摘要用的口径）**：`src` / `policies` / `validation` / `registry` / `adapters` / `knowledge` / `tests/conftest.py` / `tests/fixtures/agent_events/dsh` / `pyproject.toml` / `requirements.lock`。
- **原件位置**：新树 `.tmp/refactor-baseline/`（被 `.gitignore` 忽略）。与 `README.md` 同一口径：`tools/cleanup.py` 之后原件不可复核，本文件给结论与可重算入口。
- **开工清单 `08-refactor-kickoff.md` 在 `feat` @ `6fa800e` 上**；本分支基于 `f6b9b79`，**本树里没有该文件**。

## 1 台阶 −1② 的三条判据：本轮都满足

| 判据（方案 §4 · 台阶 −1 的红→绿） | 本轮读数 | 结论 |
| --- | --- | --- |
| 矩阵**偏差 = 0** | 30/30 臂、248 检查、`summary.deviations = []`、`instrument_errors = []`、进程 exit 0 | 满足 |
| **11 个 fixture 逐字段全等** | `whole_row_same` **11/11**、`rows_with_any_difference = []`、`all_decision_paths_identical = true` | 满足 |
| **两棵树的 sha256 都写出来** | pre `7a5b2311243d78f261995acb36932e32e83fa15427a5c6b79ce67a3ce1f1e354` / post `884b0384441a8abe7d3f142f674f722627b499e829abef6e9351d90dc698fe30`（口径见 §4） | 已写出 |

**别把「偏差 = 0」读成比它更强的话**——§6 有三条限定，其中第 1 条正是「`exit 1` 不等于偏差非 0」。

## 2 30 臂矩阵

### 2.1 五次运行的读数（判据取 run1）

| 运行 | started_at (UTC) | seconds | 臂 | 检查 | 偏差 | 仪器异常 | exit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| round-09 基线（主树） | 2026-09-27T15:31:00Z | 57.356 | 30/30 | 248 | **0** | 0 | 0 |
| run1 新树 @`f6b9b79` | 2026-09-28T15:23:18Z | 56.404 | 30/30 | 248 | **0** | 0 | 0 |
| run2 新树 · 重复 | 2026-09-28T15:24:38Z | 52.343 | 30/30 | 248 | **0** | 0 | 0 |
| run3 撤回变异 A 后 | 2026-09-28T15:28:02Z | 52.344 | 30/30 | 248 | **0** | 0 | 0 |
| run4 撤回变异 B 后 | 2026-09-28T15:31:16Z | 51.759 | 30/30 | 248 | **0** | 0 | 0 |
| 变异 B（正面控制） | 2026-09-28T15:30:23Z | 51.990 | 20/30 | 248 | **61** | 0 | 1 |

新树与基线的 `environment` 只有两处**声明**差异：`repo` 与 `matrix_root`（树不同）。`interpreter` 相同（miniconda 3.13.11）；`python_version` 相同；`hook_cli` 相同；`rule_set` 相同（43 条：error 24 / warning 19；style_lint 39、forbidden_dependency / missing_docstring / missing_tests / failing_tests 各 1）。

### 2.2 与 round-09 的**独立**逐条对照（不是抄仪器自报）

工具：新树 `.tmp/refactor-baseline/compare_matrix.py`（sha256[:16] `67bd1ca31f442a3d`）。规则：按 `(step, key, op)` 对齐 248 条检查，分组比较 `structure = (step,key,op,expected)` / `actual` / `ok` / `text = (name,classify,note)`；`deviations` 与 `instrument_errors` 另从两份 JSON 的 `summary` 直读。

| 对照 | structure | actual | ok | text | 计数差 |
| --- | --- | --- | --- | --- | --- |
| round-09 基线 ↔ run1（**判据**） | 0 | **2** | 0 | 0 | 0 |
| run1 ↔ run2（同树重复） | 0 | **2** | 0 | 0 | 0 |
| run1 ↔ run3 / run1 ↔ run4 | 0 | 2 | 0 | 0 | 0 |
| run1 ↔ 变异 B（正面控制） | 0 | 64 | **61** | 0 | 0 |

### 2.3 那 2 处 `actual` 差是**每次运行新铸的审批号**，不是树差异

两处都在 `block-composite-command` 臂的 `stderr` `contains` 检查里（248 条里的 2 条），差的是同一段文字中的 `approval-<12 hex>`：基线 `approval-306caad9f660`、本次 `approval-1a0a026d55dd`。
机制（读源码，不是猜）：`src/enforcement/cli.py:637` —— `approval_id=args.approval_id or "approval-" + uuid.uuid4().hex[:12]`；脚手架 `--sign-pytest-approval` 每次运行新签一张审批，臂的 `.policy/approval.json` 里 `granted_at` / `expires_at` 也随之刷新。
**同树重复（run1 ↔ run2）出现同样的 2 处差**，所以它是运行期随机，不是「两棵树不同」。两条检查本身都 `ok=true`（`op=contains`，没有人钉这个值）。
口径后果：对矩阵说「248 条读数逐字节全等」是**错的**；能成立的说法是「248 条检查的期望、判定与全部观察值中，除 2 条 run-scoped 文本外逐条一致」。

## 3 11 个 fixture

### 3.1 先自证仪器忠实（否则「全等」可能只是我不会用）

把 round-10 记录里的 `out/decisions-post.json` 放在 pre 位，再在**它自己那棵树**上重跑一次 `decision_invariance.py`（同一 `--project`、同一 tree），用**未改动的** `compare_decisions.py` 比：`document_minus_meta_identical = true`、`differing_top_level_keys = []`、11/11 `whole_row_same`。
含义：我的调用口径能复现历史读数；后面新树上出现的任何差异都不能归给「调用方式」。

### 3.2 新树读数（判据）

| 项 | 读数 |
| --- | --- |
| pre / post | round-10 `trees/post` / `Memory-refactor` @ `f6b9b79` |
| fixture 数 | 11（清单相同：6 个 `evaluated` + 5 个在映射阶段显式拒绝） |
| `rule_count` / `rule_set_identity` | 43 / `sha256:50202675b6ca401368bdd75ad67b440e66849f27faf237a2265043a8eaa4b33c`（**两边相同**） |
| `whole_row_same` | **11/11** |
| `rows_with_any_difference` | **[]** |
| `all_decision_paths_identical` | **true** |
| `document_minus_meta_identical` | false——**唯一**顶层差 = `policies_dir`（树路径） |

与 round-10 自己那一对（pre/post）**同形**：那次也是「`policies_dir` 差、行全等」。判定读数（`decision` / `violations` / `matched_rules` / `skipped_rules` / `event` / `context` / 拒绝原文）逐字段相同。

### 3.3 这 11 条覆盖什么、不覆盖什么

它走的是 **Phase 2 Hook 的上下文路径**（`to_policy_event` → `to_policy_context` → `policy.engine.evaluate`），**没有 Phase 5 验证器流水线**——所以 `skipped_rules` 里那些「需要验证器证据」的 rule 在本路径上仍是 skipped。`failing_tests` / `style_lint` 那几条 checker 的**执行**不在本读数范围内（见 §7）。

## 4 树摘要（声明范围）

方法：逐文件 `sha256`，按相对路径排序后用 `\n` 连接再做 `sha256`（工具 `.tmp/refactor-baseline/tree_digest.py`，sha256[:16] `2c2a3e1f8874635e`）；跳过 `__pycache__` / `.pytest_cache` / `.mypy_cache` / `.ruff_cache` / `.git` / `node_modules` 与 `*.egg-info`。**这不是**方案 §3.1 的 `referenced_inputs_digest`（那个还没实现），是本轮临时、可重算的声明摘要。

| 树 | 摘要 sha256 | 文件数 | 字节 | git |
| --- | --- | --- | --- | --- |
| pre `…\Memory\.tmp\round-10\c\trees\post` | `7a5b2311243d78f261995acb36932e32e83fa15427a5c6b79ce67a3ce1f1e354` | 188 | 1992055 | **不是** git 仓库根（无自有修订号） |
| post `…\Downloads\Memory-refactor` | `884b0384441a8abe7d3f142f674f722627b499e829abef6e9351d90dc698fe30` | 189 | 2082350 | `HEAD = f6b9b79…`，`status --porcelain` 空 |

**两棵树在声明范围内并不相同**：新增 1 个、修改 11 个、删除 0 个（工具 `diff_trees.py`，sha256[:16] `b6eadc7346905641`）：

| 文件 | pre sha256[:12] | post sha256[:12] | 字节 |
| --- | --- | --- | --- |
| `adapters/host-versions.observed.json` | —— | `6f7952097244` | —— → 475 |
| `src/adapters/cli.py` | `0fb7fde14673` | `cee89a461623` | 34032 → 43513 |
| `src/adapters/dsh/README.md` | `ae47a8d9f172` | `d19987fb0a78` | 66607 → 76067 |
| `src/adapters/dsh/policy-hook.plugin.mjs` | `d8d5b5440ac8` | `a7be5bdb17ee` | 13953 → 18307 |
| `src/adapters/dsh/pre_evidence.py` | `5e122a2ccd8e` | `14a938caa128` | 32027 → 33192 |
| `src/adapters/host_version.py` | `ca8df3a3d235` | `00f2ad2fc87a` | 16289 → 49007 |
| `src/policy/checkers.py` | `f03704692507` | `798fbffc3ef3` | 13020 → 15660 |
| `src/policy/engine.py` | `8746001a62cf` | `dd49b006bde4` | 7315 → 8089 |
| `src/policy/evidence.py` | `1b1e43ab12c6` | `ca444e87bdfa` | 16765 → 21876 |
| `src/validators/adapters/base.py` | `9c89363c1bb3` | `cc22e765dbe0` | 26308 → 27025 |
| `src/validators/adapters/pytest_runner.py` | `587c2d68702b` | `1a567e47fa61` | 7940 → 27404 |
| `src/validators/pipeline.py` | `8c82810c0af4` | `fad8f87ea65b` | 43178 → 47114 |

**所以「11 个 fixture 逐字段全等」是一条跨这 12 个文件仍然成立的读数**——比「两棵树相同」更强，也更需要写清：它的意思是**判定路径对这些改动不敏感**（这 12 个文件里包含 `src/policy/engine.py` / `checkers.py` / `evidence.py` 与 `src/validators/adapters/pytest_runner.py`）。

## 5 正面控制（方案 §5.1 J2 要求的那半条）

J2 原文要求「故意在内核目录改一行 → 必须变红」。本轮做了两次，都在 `src/policy/engine.py:167`（`decision=expected_decision(...)` 那一行），改完即跑，跑完 `git checkout --` 撤回：

| 变异 | 结果 | 证据 |
| --- | --- | --- |
| **B**：`decision=Decision.BLOCK` | 30 臂跑完、20/30 臂一致、**61/248 检查不一致**、`instrument_errors=0`、exit **1**；偏差落在 10 条 allow 臂（`control-clean-write` 11、`pe-off-multiviolation` 10、`doc-warning-only` 8、`dep-allow-service` 7、`layer-test-controller` 7…），**10 条 block 臂上 0 条偏差** | `mutation-b.json` / `mutation-b.md` / `logs/mutation-b.log` |
| **A**：`decision=Decision.ALLOW` | 30 臂跑完，随后**仪器自己崩**：`probe_matrix.py:1646` `TypeError: 'NoneType' object is not subscriptable`，**没有落证据文件**，exit **1** | `logs/mutation-a.log`（无 JSON） |

**撤回的证明（不是「我记得改回来了」）**：撤回后重算摘要 = `884b0384441a8abe7d3f142f674f722627b499e829abef6e9351d90dc698fe30`（与变异前逐位相同），`git status --porcelain` 为空；并各重跑一次矩阵（run3 / run4）回到 30/30、248、0 偏差、exit 0。

变异 B 的红**不是**「allow 翻成 block」那么干净——它 10 条 allow 步的 `reason_code` 变成 `internal_error`（`decision` 读作 null），也就是说：恒 block 之后，Hook 的方向仍是失败关闭，但**理由说错了**。这不是本台阶要修的缺陷，记在这里是因为它正好是 AGENTS 第 52 条那类「失败关闭不等于理由正确」。

## 6 本轮新发现（三条，都会影响后续台阶）

1. **`probe_matrix.py` 的 `exit 1` 是二义的**：正常路径下 1 = 「有检查不一致」（`main()` 末尾 `return 0 if not deviations else 1`），但**未捕获异常也让 Python 退 1**，而且证据 JSON 只在全部臂跑完**之后**才写（`:1702-1708`）。变异 A 就是这种：exit 1、零证据。这与方案 §5.3 想解决的「退出码语义过载」是同一类问题——**只读 exit code 会把「仪器崩了」读成「偏差非 0」**。
2. **矩阵里有一条检查的观察值永不稳定**：`block-composite-command` 的 `stderr` 里带 `approval-<12hex>`（`src/enforcement/cli.py:637` 用 `uuid.uuid4()`）。`op=contains` 让它照样绿，但「逐字节全等」这类更强的说法对矩阵不成立（§2.3）。
3. **判定稳定的读数是「跨修复轮」而不是「跨相同树」**：pre/post 两棵树在声明范围内有 12 个文件不同（含内核三件 `policy/engine.py`、`policy/checkers.py`、`policy/evidence.py`），11 条 fixture 仍逐字段全等。这**支持**方案 §1 的「判定内核健康」，但它的强度取决于「那 11 条 fixture 恰好不压这些改动」——§3.3 已写明它们不覆盖验证器流水线。

## 7 不证明什么 / 未核实

- **本台阶没有跑门禁**（`tools/ci_local.py`）：`08` 的 P1 只要求确认新树里门禁**能起**（用 `CI_LOCAL_PYTHON` 指向主树 `.venv`，`--list` 通过；新树自己没有 `.venv`）。**未核实**：新树 `--full` 全绿（那要二十多分钟，且门禁的写域在 `.tmp/`，与本台阶的读数无关）。
- **不覆盖**：Phase 5 验证器流水线、Phase 4 受控执行、Phase 6 运行时、API、编排层——它们不在 30 臂与 11 fixture 的范围内。
- **不覆盖真实 dsh 会话**：本机沙箱禁止 Node 管道 stdio，与 `01` 的边界同一条。
- **没有重跑第二方** `verify-matrix.py`（round-09 的第二方逐条重算是另一份仪器）；本轮做的是**我自己**用另一份脚本对 248 条做逐条对照（§2.2）。
- **`Decision.ALLOW` 那次崩溃的根因已定位**（`worst` 为 `None` 时仍在拼 gap 文案），但**没有修**——修仪器不在台阶 −1② 的范围里。
- **未核实**：round-10 记录那次 fixture 读数用的解释器（记录里没有）；本文件只声明**本轮**用的是 miniconda 3.13.11。

## 8 复核入口（全部只读，原件在新树 `.tmp/refactor-baseline/`）

```powershell
# 0) 两棵树、两个摘要（本次实测值见 §4）
python .tmp/refactor-baseline/tree_digest.py --root C:\Users\ZNM\Downloads\Memory-refactor --label post
# 1) 矩阵：跑一次（约 52–57 秒）
C:\Users\ZNM\miniconda3\python.exe .tmp/refactor-baseline/harness/probe_matrix.py \
  --json .tmp/refactor-baseline/instruments/hook-matrix/hook-matrix.json \
  --report .tmp/refactor-baseline/instruments/hook-matrix/hook-matrix.md
# 2) 与 round-09 逐条对照（0/2/0/0）
python .tmp/refactor-baseline/compare_matrix.py --baseline .tmp/refactor-baseline/baseline-hook-matrix.json \
  --current .tmp/refactor-baseline/instruments/hook-matrix/hook-matrix.json \
  --out .tmp/refactor-baseline/matrix-comparison.json
# 3) 11 fixture：新树上跑一遍，再与 round-10 的读数比
python .tmp/refactor-baseline/fixtures/harness/decision_invariance.py --tree C:\Users\ZNM\Downloads\Memory-refactor \
  --project C:\Users\ZNM\Downloads\Memory\.tmp\round-10\c\tmp\decisions\project \
  --config .tmp/refactor-baseline/fixtures/tmp/config/dsh-adapter.yaml \
  --out .tmp/refactor-baseline/fixtures/out/decisions-post.json
python .tmp/refactor-baseline/fixtures/harness/compare_decisions.py   # 打印 whole_row_same 等
```

| 证据（新树 `.tmp/refactor-baseline/` 下） | sha256[:16] | 字节 |
| --- | --- | --- |
| baseline-hook-matrix.json | 3096b8b35e7b4275 | 388497 |
| baseline-decision-invariance-diff.json | e707efd545536473 | 4035 |
| instruments/hook-matrix/hook-matrix.json | 9085f8eee8351754 | 387025 |
| instruments/hook-matrix/hook-matrix.md | c831d1fccec48620 | 20505 |
| instruments/hook-matrix/hook-matrix-run2.json | b34c93102f0898bf | 387031 |
| instruments/hook-matrix/hook-matrix-run3.json | 00a1cab817d30be4 | 387027 |
| instruments/hook-matrix/hook-matrix-run4.json | 245856097dc3d089 | 387027 |
| instruments/hook-matrix/mutation-b.json | a2c68ae61398bf31 | 371236 |
| instruments/hook-matrix/mutation-b.md | 3758d0d39db748fd | 29468 |
| matrix-comparison.json | f71da706ce16f60c | 13751 |
| matrix-comparison-run1-run2.json | 5dc097c3ff0f5a6b | 13772 |
| matrix-comparison-run1-run3.json | 7a823ebb42c1c6ea | 13772 |
| matrix-comparison-mutation-b.json | e5f41b3a38fbca99 | 58249 |
| fixtures/out/decisions-post.json | d912f00a04ae0fe5 | 75663 |
| fixtures/out/decision-invariance-diff.json | 04089f047d52f4a4 | 4013 |
| selfcheck/out/decision-invariance-diff.json | 27b9c9807e69bd5a | 4011 |
| tree-diff.json | 4b985f666b5ba0d5 | 2782 |
| digest-pre.json | 401b3427116f9c4c | 1081 |
| digest-post.json | ff0c22ab76b5da74 | 1020 |
| logs/mutation-a.log | 86cb541fb47e5cda | 5508 |
| logs/mutation-b.log | d389ffae1d84edcc | 4180 |
| logs/run4.log | 11fd0447d7453ad3 | 4196 |

`baseline-hook-matrix.json` = `3096b8b35e7b4275`，与 `01` 引用的 round-09 `hook-matrix.json` **同哈希**（原件复制，未重新生成）。`instruments/hook-matrix/mutation-a.json` **不存在**——那正是 §5 变异 A 的读数：仪器崩在写证据之前。

---

**签署口径**：本文件的每个数字都能用上面的命令重算；凡我没亲自跑出来的，都标了「未核实」。
