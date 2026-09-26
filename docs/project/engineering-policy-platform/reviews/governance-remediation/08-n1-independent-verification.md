# 08 · N1 独立验收（V1）

> 角色：V1 verifier（共享任务 **task-5**）。**本轮没有改任何产品代码 / 测试 / 注册表 / 配置**：
> 全部写入只落在本文件与 `.tmp/verifier-n1/**`。
> 仪器：自建 10 件，全部在 `.tmp/verifier-n1/`（`probe_n1.py` / `probe_language_gate.py` /
> `ruff_scope.py` / `assert_diff.py` / `ast_equal.py` / `make_tree.py` / `compare.py` /
> `diff_probe_reports.py` / `tree_hash.py` / `scope.json`）。
> 基线（Lead 冻结）：**1430 passed, 1 skipped**。
> 验收窗口：2026-09-26 13:00 起（工作区 HEAD = `4f9f2e15`）。
> 语义判据：07-ruff-cleanup-and-n1.md §7。

## 0. 结论（三态）

| 验收项 | 结论 | 证明到哪一步 | 没证明的部分 |
| --- | --- | --- | --- |
| 1 · G6 在多 Agent 路径不再可绕过 | **通过** | 修复前 3 段文本在 3 条 Phase 6 路径上**全部放行**（原始输出见 §2.2）；修复后 4 条路径逐格同结论、依赖集逐项相同；反向对照（回退接线）再次变红 | 没有单独驱动 Phase 6 `runtime.py` 的受控写链路（它与被测路径共用同一个接线点 `base.Adapter.to_policy_context`，只有代码阅读层面的证据）；没有驱动 Phase 7 API 路径 |
| 2 · ruff in-scope 清零 / 边界不变 | **通过** | 30 个 in-scope 文件合计 **163 → 0**；改动集里另外 8 个 .py **0 → 0**；边界 `tools/build_learning_notebook.py` **113 → 113**、`docs/project/learning/phase-2/walkthrough.py` **19 → 19**、`nb_cells/nb02.py` **27 → 27**、`docs/**/*.py` 合计 **949 → 949** | 没有跑 `ruff format --check`（本轮范围只有 `ruff check`） |
| 3 · 无回归 | **通过** | `1463 passed, 1 skipped`（基线 1430/1，0 失败），运行窗口内 414 个被测文件逐字节冻结（§4.2）；`tests/contract/test_dsh_adapter.py` 的 159 条断言 / 409 个字符串常量与开工前快照 **AST 逐项相同**（§4.3） | 只证明了"该文件断言未变"，没有证明整个仓库每一行都没变（超出验收范围） |
| 4 · 不静默（language 门控） | **通过** | 非 python 分支有测试覆盖（变异实验：删掉守卫后契约测试与集成测试各 1 条变红，见 §5.2）；"依赖集为空"与"静默放行"由 `skipped_rules` 的 `language text != python` 区分 | 没有做分支覆盖率（覆盖率工具未安装），用的是"变异能否被测试杀死"这个更强的替代 |

---

## 1. 实验设置：先造"修前的红"

### 1.1 修前基线怎么来

T1 动手之前（2026-09-26 13:00），把当时的工作区快照复制到
`.tmp/verifier-n1/pre-fix/`（`src` / `policies` / `adapters` / `validation` / `knowledge` /
`registry` / `tools` / `tests` + `pyproject.toml` / `pytest.ini`）。

**为什么不能拿 `git show HEAD:` 当修前基线**：本轮开工时工作区相对 HEAD 已有 60+ 个改动
（上一轮的治理修复未提交），`git show HEAD:src/adapters/dsh/adapter.py` 拿到的是**更早**的版本，
用它会把"上一轮已修好的 Phase 2 路径"也算成红的。因此基线取"开工瞬间的工作区副本"，
并用 sha256 证明它确实是 T1 落地前的状态（§2.1 的 blob 记录）。

### 1.2 探针测什么

`probe_n1.py` 只依赖被测树自己的 `src/` `policies/` `adapters/`，每条路径都把异常记成
`error`（不让"跑崩了"看起来像"放行了"），并内置一个**必须放行**的对照样例
（`from shop.order_service import OrderService`）——一个把所有输入都判成 block 的探针是假绿，不是证据。

同一段文本走四条路径，比较**同一条规则 ARCH-001 的结论**与 `PolicyContext.dependencies`：

| 路径 | 入口 |
| --- | --- |
| `p2-dsh` | Phase 2：`adapters.dsh.adapter.to_policy_event` → `to_policy_context` |
| `p6-json` | Phase 6：`JsonAdapter`（canonical-json / generic-json）→ `base.to_policy_context` |
| `p6-dsh` | Phase 6：`DshAdapter`（canonical-tool-table / dsh 桥）→ `base.to_policy_context` |
| `p6-hook` | Phase 6：`EventAdapter`（hook-command / legacy-post-only）→ `base.to_policy_context` |

（`legacy-post-only` 的能力上限是 read_only，但**依赖提取与能力门是两件事**：
这里测的是 `_tool_payload` → `to_policy_context` 的口径，所以照常驱动它。）

## 2. 验收项 1：G6 在多 Agent 路径上不再可绕过 —— **通过**

### 2.1 修前的红（原始输出）

    .venv/Scripts/python.exe .tmp/verifier-n1/probe_n1.py \
        --root .tmp/verifier-n1/pre-fix --tag pre-fix --out .tmp/verifier-n1/pre-fix.json
    .venv/Scripts/python.exe .tmp/verifier-n1/compare.py \
        --before .tmp/verifier-n1/pre-fix.json --after .tmp/verifier-n1/live-final.json

修前（`*=带 UNPROVEN_DYNAMIC_IMPORT 标记`）：

    case                    exp      | p2-dsh       | p6-json      | p6-dsh       | p6-hook
    1-relative-import       True     | BLOCK        | allow        | allow        | allow
    2-dynamic-literal       True     | BLOCK        | allow        | allow        | allow
    3-dynamic-nonliteral    True     | BLOCK*       | allow        | allow        | allow
    4-dotted-literal        True     | BLOCK        | BLOCK        | BLOCK        | BLOCK
    5-allow-control         False    | allow        | allow        | allow        | allow
    6-unparseable           True     | BLOCK        | BLOCK        | BLOCK        | BLOCK

**三件必须同时看到的事**：

1. 任务书点名的三段文本（相对导入 / 字面量动态导入 / 非字面量动态导入）在三条 Phase 6 路径上
   **全部放行**，而 Phase 2 路径全部阻断 —— 这正是 G6 的形态：同一段改动，换个入口就绕过；
2. 放行是**静默**的：`p6-json / p6-dsh / p6-hook` 的 `deps` 分别是
   `[]` / `[]` / `[]`（相对导入）与 `["importlib"]`（两段动态导入）——
   账本上写的是 allow + 一个看起来正常的依赖集；
3. 对照组 4（字面量点分导入）在四条路径上都阻断、对照组 5（正常 service 依赖）在四条路径上都放行 ——
   说明这个探针能区分"阻断"与"放行"，不是把所有输入都判红。

### 2.2 修后（原始输出）

    case                    exp      | p2-dsh       | p6-json      | p6-dsh       | p6-hook
    1-relative-import       True     | BLOCK        | BLOCK        | BLOCK        | BLOCK
    2-dynamic-literal       True     | BLOCK        | BLOCK        | BLOCK        | BLOCK
    3-dynamic-nonliteral    True     | BLOCK*       | BLOCK*       | BLOCK*       | BLOCK*
    4-dotted-literal        True     | BLOCK        | BLOCK        | BLOCK        | BLOCK
    5-allow-control         False    | allow        | allow        | allow        | allow
    6-unparseable           True     | BLOCK        | BLOCK        | BLOCK        | BLOCK

`compare.py` 的"逐格差异"一节给出 9 处 `allow -> BLOCK`（三路径 × 三段文本），
其余格子不变；"各路径结论是否一致"一节每个案例都是 `deps_equal=True`。

非字面量动态导入的依赖集（四条路径逐项相同）：

    ["<unproven-dynamic-import>", "importlib"]

`policy.checkers.UNPROVEN_DYNAMIC_IMPORT` 的取值就是 `'<unproven-dynamic-import>'`
（`python -c "from policy.checkers import UNPROVEN_DYNAMIC_IMPORT"` 实测），探针按该常量比对，不是自造字符串。

### 2.3 反向对照（回退接线 → 重新变红 → 恢复 → 变绿）

    .venv/Scripts/python.exe .tmp/verifier-n1/make_tree.py \
        --target .tmp/verifier-n1/regressed --mutation revert-wiring
    .venv/Scripts/python.exe .tmp/verifier-n1/probe_n1.py \
        --root .tmp/verifier-n1/regressed --tag reverted-wiring --out .tmp/verifier-n1/reverted-wiring.json

`revert-wiring` 的变异内容（只发生在副本里，工作区一行未动）：把
`base.Adapter._dependencies_for` 里"没有显式 dependencies 时按 language 从 text 派生"的三行
换成 `return ()` —— 也就是**把 Phase 6 的接线拆掉**。结果：

    case                    exp      | p2-dsh       | p6-json      | p6-dsh       | p6-hook
    1-relative-import       True     | BLOCK        | allow        | allow        | allow
    2-dynamic-literal       True     | BLOCK        | allow        | allow        | allow
    3-dynamic-nonliteral    True     | BLOCK*       | allow        | allow        | allow
    4-dotted-literal        True     | BLOCK        | allow        | allow        | allow
    5-allow-control         False    | allow        | allow        | allow        | allow
    6-unparseable           True     | BLOCK        | allow        | allow        | allow

    == 修后是否每格都等于期望 ==
    FAIL：15 格（三路径 × 5 个应阻断案例）

恢复 = 同一份探针再对**未被修改的工作区**跑一次，仍然全绿（§2.2）。因此
"探针的绿"确实是由那处接线产生的，不是环境漂移。

### 2.4 探针灵敏度的两组额外对照（证明它在测它声称在测的东西）

| 变异（同样只改副本） | 期望 | 实测 |
| --- | --- | --- |
| `old-from-regex`：把共享层的 from 正则换回修复前的口径（模块名不许有前导点） | 只有"相对导入"一格变红 | 只有 `1-relative-import` 变得四条路径全部 allow，其余案例不变 |
| `drop-dynamic-marker`：不再登记 `UNPROVEN_DYNAMIC_IMPORT` | 只有"非字面量动态导入"一格变红 | 只有 `3-dynamic-nonliteral` 变得四条路径全部 allow，其余案例不变 |

这两组说明：探针不是"看到 BLOCK 就算过"，它对**具体的失效形态**敏感。

### 2.5 这一项的边界（没证明的部分）

- 没有单独驱动 Phase 6 `runtime.py` 的受控写链路：它复用同一个接线点
  （`base.Adapter.to_policy_context`），这是**代码阅读**得出的，不是执行证据；四条被驱动的路径
  已经覆盖了本轮改动的四个调用点中的全部四个（Phase 2 dsh + json + dsh桥 + hook）。
- 没有驱动 Phase 7 API 与 Phase 5 AST 路径：它们不属于 G6 的"多 Agent 路径"，本轮未验。

---

## 3. 验收项 2：ruff —— **通过**

### 3.1 口径与文件集

命令（全部逐文件跑，判定只看 ruff 的原始输出）：

    ruff check --config validation/ruff.toml --output-format concise --no-cache <file>

仪器 `.tmp/verifier-n1/ruff_scope.py` 把每一次调用的整份 stdout/stderr 都写进
`.tmp/verifier-n1/ruff-*.json`，便于复核。

一个必须写下来的坑：`concise` 格式的 stdout 里除了违规行还有一行汇总
（`Found 8 errors.`），**数行数会把汇总也数进去**（实测 8 条被数成 10 条）。
仪器因此只认 `<path>:<line>:<col>: <CODE>` 形态的行；上面的 10 条就是修前 `src/adapters/cli.py`
的原始条数，和 07 号文档 §2 的逐文件清单对得上。

文件集分三块：

| 块 | 内容 | 为什么这么分 |
| --- | --- | --- |
| `in_scope`（30 个） | T1（3）+ T2（2）+ T3（10）+ T4（12）+ 三个 Phase 6 接线文件（`json_adapter.py` / `event_adapter.py` / `dsh_adapter.py`） | 07 号文档 §2 的"本轮要清到 0"的全部对象 |
| `change_set_extra`（8 个） | `src/policy/context.py`、`src/policy/models.py`、`src/validators/globs.py`、`src/adapters/wiring.py`、`tests/contract/test_policy_hook_chain.py`、`tests/contract/test_wiring_inventory.py`、`tests/unit/test_hook_skip_visibility.py`、`tests/unit/test_wiring.py` | 它们在 `git status` 的改动集里，但**不在** T3/T4 的逐文件清单里。§2 的口径是"改动集里的每个 .py"，所以单独计数，防止清单外漏判 |
| 边界（明确排除） | `tools/build_learning_notebook.py`、`docs/**/*.py` | 07 号文档 §2 的边界：notebook 生成链与讲义内容源 |

### 3.2 修前 → 修后

| 桶 | 开工瞬间（`--root .tmp/verifier-n1/pre-fix`） | 收尾（`--root .`） |
| --- | --- | --- |
| `in_scope` 合计 | **163** | **0** |
| `change_set_extra` 合计 | 0 | 0 |
| `tools/build_learning_notebook.py` | 113 | **113**（不变） |
| `docs/project/learning/phase-2/walkthrough.py` | 19 | **19**（不变） |
| `docs/project/architecture/tech-detail/notebooks/nb_cells/nb02.py` | 27 | **27**（不变） |
| `docs/**/*.py` 合计 | 949 | **949**（不变） |

> 与 07 号文档 §2 表格里"148"的差异：那份是 Lead 在 2026-09-25 对当时树的实测，
> 文件集是"44 文件改动集"；本报告用的是 T1/T2/T3/T4 任务书里逐文件列出的**并集**（30 个），
> 且在 2026-09-26 13:01 的树上实测。两个数不可直接相减——**判定以本报告 §3.1 的文件集为准**。

修前逐文件条数（30 个文件里 28 个非零）：

| 文件 | 条数 | 文件 | 条数 |
| --- | --- | --- | --- |
| `src/adapters/cli.py` | 8 | `src/enforcement/precheck.py` | 8 |
| `src/adapters/dsh/hooks.py` | 7 | `src/enforcement/ledger.py` | 4 |
| `src/enforcement/cli.py` | 9 | `src/enforcement/action.py` | 3 |
| `src/enforcement/models.py` | 5 | `src/policy/checkers.py` | 2 |
| `src/enforcement/approvals.py` | 1 | `src/enforcement/codecheck.py` | 1 |
| `src/adapters/dsh/adapter.py` | 3 | `src/adapters/base.py` | 4 |
| `src/adapters/json_adapter.py` | 3 | `src/adapters/event_adapter.py` | 6 |
| `src/adapters/dsh_adapter.py` | 2 | `tests/contract/test_approval_binding_modes.py` | 17 |
| `tests/contract/test_dsh_adapter.py` | 8 | `tests/contract/test_path_scope_boundaries.py` | 1 |
| `tests/contract/test_run_code_static_check.py` | 5 | `tests/contract/test_tool_table_drift.py` | 2 |
| `tests/enforcement_support.py` | 1 | `tests/integration/test_dsh_hook.py` | 6 |
| `tests/integration/test_enforcement_cli.py` | 31 | `tests/integration/test_governance_gap_probe.py` | 2 |
| `tests/integration/test_dependency_path_consistency.py` | 5 | `tools/ci_local.py` | 1 |
| `tools/dsh_sandbox_loop.py` | 1 | `tools/governance_gap_probe.py` | 17 |

（`src/adapters/textfacts.py` 在开工瞬间就是 0；`tests/contract/test_dependency_extraction_parity.py`
当时还不存在。两者在收尾时都是 0。）

### 3.3 `tools/governance_gap_probe.py`：blob 前后值与行为不变

| 时点 | sha256（文件字节） | git blob | 行数 / 字节 |
| --- | --- | --- | --- |
| 开工瞬间 | `E0E2E390C753A980…` | `57972412E092…` | 2142 / 100562 |
| 收尾（T4 换行后） | `BFA60D0C0E89C4AC…` | `e41547F3EB34…` | 2175 / 100831 |

**行为不变的证明不是"AST 相同"**：这个文件把自己的探针脚本以字符串字面量的形式嵌在里面，
一次括号换行就会改变字面量 → 模块 AST 必然不同（`ast_equal.py` 如实报 `False`，
差异落在 `check_g07` 之前那段内嵌脚本的 `out["layer_for_backward_compatible"] = (…)` 处，
是**加了括号**，不是改了算式）。

**补充**：`ast_equal.py` 支持 `--baseline file --before <path>`，可用于"注释级改动"的判定——
注释不进 AST，因此"AST identical: True"就直接证明行为不可能变（前提是该注释不在内嵌脚本字符串里；
若落在字符串里，AST 必然不同，此时以行为比对为准）。

真正有说服力的是**同一份探针 + 同一份被测根 + 旧文件 vs 新文件**跑出来的报告是否逐项相同：

    .venv/Scripts/python.exe .tmp/verifier-n1/pre-fix/tools/governance_gap_probe.py \
        --root .tmp/verifier-n1/pre-fix --phase after \
        --work .tmp/verifier-n1/gapwork-old2 --json-out .tmp/verifier-n1/gap-old2.json
    .venv/Scripts/python.exe tools/governance_gap_probe.py \
        --root .tmp/verifier-n1/pre-fix --phase after \
        --work .tmp/verifier-n1/gapwork-new3 --json-out .tmp/verifier-n1/gap-new3.json
    .venv/Scripts/python.exe .tmp/verifier-n1/diff_probe_reports.py \
        --a .tmp/verifier-n1/gap-old2.json --b .tmp/verifier-n1/gap-new3.json

（`--root` 刻意指向 `pre-fix` 快照：这样探针的写操作全部落在快照自己的 `.tmp/` 下，
不会与正在跑的 pytest 抢仓库的 `.tmp/artifacts/`。）

收尾复核（在同一次运行里先钉住新探针的 blob = `e41547f3eb34f46b…`，再跑两边）：

    A: ok=True exit=None gaps=13
    B: ok=True exit=None gaps=13
    逐项结论相同: True
    facts（归一化后）相同: True
    （两次探针进程退出码都是 0："结论: 13/13 与「after」预期一致"）

比较器会先把 work 目录名与 `run-<ts>-<pid>-<hash>` 归一化，再逐字节比 facts —— 路径与 run id
不属于行为，时间戳/耗时字段整体剔除。

---

## 4. 验收项 3：无回归 —— **通过**

### 4.1 全量 pytest

    .venv/Scripts/python.exe .tmp/runlock.py -m pytest -q
    # 1463 passed, 1 skipped, 2 warnings in 256.73s (0:04:16)
    # pytest_exit=0

- 用例数 **1463 ≥ 基线 1430**；skip 仍是 **1** 条，且是既有的那条
  （`tests/unit/test_validator_facts.py:109: 本机不允许创建符号链接（Windows 需要开发者模式）`），
  **不是**新跳过的用例；
- 失败 0 条。两条 warning 分别是 starlette 的 DeprecationWarning 与 pytest 自己
  `.tmp/.pytest_cache` 写不进去的 `PytestCacheWarning`（沙箱只读面），都与被测代码无关。

### 4.2 运行窗口内代码是冻结的（否则结果对最终状态无效）

    .venv/Scripts/python.exe .tmp/verifier-n1/tree_hash.py --out .tmp/verifier-n1/hashes-before.txt
    # 跑测试
    .venv/Scripts/python.exe .tmp/verifier-n1/tree_hash.py --out .tmp/verifier-n1/hashes-after.txt
    # before_manifest=CF78A1388BE4BE9A…  after_manifest=CF78A1388BE4BE9A…
    # FROZEN: 运行窗口内被测文件逐字节未变

清单覆盖 `src/ tests/ tools/ policies/ adapters/ validation/ registry/ knowledge/` 与
`pyproject.toml` / `pytest.ini` 等，共 **414 个文件**（清单文件本身落在 `.tmp/verifier-n1/` 下，不入清单）。

### 4.3 `tests/contract/test_dsh_adapter.py` 的断言未被改动

用 **AST 比对**而不是 git diff：ruff 的 E501 修法是重新换行，换行会让 git diff 的每一行都变成 +/-，
但它不改变 AST。基线取开工前快照（不是 `git show HEAD:` —— 那个版本比本轮更早，
相对它有 537/11 行的差异，全部来自上一轮未提交的改动）。

    .venv/Scripts/python.exe .tmp/verifier-n1/assert_diff.py \
        --path tests/contract/test_dsh_adapter.py --baseline snapshot

    asserts: baseline=159 worktree=159 identical=True
    strings: baseline=409 worktree=409 identical=True
    blob worktree=8306e4a3e8e2af85127c59e695ae7eb24628fc21  blob HEAD=17efb8a734c53b40cb83927bfb13bf616b45273a
    git diff --numstat: 537	11	tests/contract/test_dsh_adapter.py

- **159 条 `assert` 语句的 `ast.dump`（不含位置信息）逐个相同**：没有改断言、没有删断言、没有加断言；
- **409 个字符串常量逐个相同**：断言之外的期望值（消息文本、表驱动的输入）也没被改；
- 该文件在本轮的 ruff 变化是 **8 → 0**（§3.2 的逐文件表），T4 只做了换行；
- `git diff --numstat` 相对 HEAD 是 537/11 —— 那是**上一轮**的改动，不是本轮的；
  本轮的位移无法用 git 表达，所以才用"开工瞬间快照"作基线。


---

## 5. 验收项 4：不静默（language 门控）—— **通过**

要求是两件事：**非 python 分支必须有测试覆盖**，且 **"依赖集为空"与"静默放行"必须可区分**。
"文件里有这条断言"不等于"覆盖"——所以这里给的是可以被杀死的证据。

### 5.1 直接断言（T2 写的测试）

- `tests/contract/test_dependency_extraction_parity.py::test_governed_dependencies_are_gated_by_the_declared_language`
  对 `language="text"` 与 `language=None` 断言结果为 `()`，并保留 python 对照
  （没有对照的话，`()` 到底来自门控还是来自"实现根本没提取"就分不清）。
- `tests/integration/test_dependency_path_consistency.py::test_non_python_target_is_not_a_silent_pass`
  走**真实** `.md` 目标，同时断言 language 来自配置声明、依赖集为空、
  规则落在 `skipped_rules` 且原因里含 `"language"`，最后用 python 目标做反证。

### 5.2 覆盖是被证明的：变异实验（kill the mutant）

从**同一棵冻结的树**造两份副本，一份原样（control），一份把守卫换成 `if False:`（mutant），
跑同一组测试。若 mutant 相对 control 没有新增失败，就说明这条分支其实没被测到。

    .venv/Scripts/python.exe .tmp/verifier-n1/make_tree.py \
        --target .tmp/verifier-n1/copy-clean2 --mutation none
    .venv/Scripts/python.exe .tmp/verifier-n1/make_tree.py \
        --target .tmp/verifier-n1/mutant-guard2 --mutation drop-language-guard
    .venv/Scripts/python.exe .tmp/runlock.py -m pytest \
        "<copy>/tests/contract/test_dependency_extraction_parity.py" \
        "<copy>/tests/integration/test_dependency_path_consistency.py" -q

结果（两份副本取自**同一棵冻结的树**，唯一差别就是那一行守卫）：

    CONTROL（copy-clean2，无变异）: 42 passed, 0 failed   （exit 0，2.30s）
    MUTANT （mutant-guard2，守卫→if False）: 2 failed, 40 passed （exit 1，2.75s）

    FAILED .../test_dependency_extraction_parity.py::test_governed_dependencies_are_gated_by_the_declared_language
    FAILED .../test_dependency_path_consistency.py::test_non_python_target_is_not_a_silent_pass
    E  AssertionError: assert ('.repository',) == ()
        （契约侧 parity.py:175、集成侧 consistency.py:459 都是同一处断言）

**结论：这条分支是被测试真正守住的** —— 删掉守卫后，契约测试与集成测试**各有一条**变红，
失败原因就是"非 python 的文本被当成了 python 来提取"。若 mutant 与 control 结果相同，
就说明这条分支只是"文件里有几行断言"，而不是"覆盖"。

### 5.3 "依赖集为空"与"静默放行"可区分（我的独立探针）

`probe_language_gate.py` 不走 T2 的测试，直接驱动真实 Phase 6 路径（generic-json → JsonAdapter）。
同一段 `from . import repository` 落在 `docs/notes.md` 上（命中 `default_language: text`）：

    {"language": "text", "layer": "docs", "dependencies": [], "decision": "allow",
     "matched_rules": [], "skipped_rules": [{"rule_id": "ARCH-001@1",
                                             "reasons": ["language text != python"]}],
     "violations": []}

落在 python controller 上（同一段文本）：

    {"language": "python", "layer": "controller", "dependencies": [".repository"],
     "decision": "block", "matched_rules": ["ARCH-001@1"], "skipped_rules": [], "violations": ["ARCH-001"]}

两者的分界写在**决策载荷里**：非 python 的 allow 一定伴随"这条规则没有参与判定"的显式记录
（rule_id + 原因 `language text != python`），而不是"判定过了、通过"。
`matched_rules` 与 `skipped_rules` 因此是互斥且可观测的两个集合 —— 这就是"可区分"的可执行定义。

**一处必须写下来的边界**：非 python 分支刻意**不**登记 `UNPROVEN_*` 标记。标记的语义是
"这段 **python** 文本的依赖集无法证明"；用在非 python 上会让语义错位（把"不适用"说成"证明不了"）。
防"静默"的责任因此落在 scope 的 language 维度 + `skipped_rules` 上，二者已由 5.1 / 5.3 证明。

---

## 6. 发现与需要 Lead 裁决的事

### 6.1 【需要裁决】本轮的治理缺口探针 **看不到** N1 这个缺口

`tools/governance_gap_probe.py` 的 G06 检查（1403–1460 行）只驱动
`python -m adapters.dsh.hooks` —— 也就是 **Phase 2 的 dsh 钩子路径**。
它从不驱动 Phase 6 的 `JsonAdapter` / `EventAdapter` / `base.to_policy_context`。

实测（不是推断）：

    .venv/Scripts/python.exe .tmp/verifier-n1/pre-fix/tools/governance_gap_probe.py \
        --root .tmp/verifier-n1/pre-fix --phase after --work .tmp/verifier-n1/gapwork-old2 \
        --json-out .tmp/verifier-n1/gap-old2.json
    # -> 结论: 13/13 与「after」预期一致 ; exit=0

`--root` 指向的是 **T1 落地前** 的快照，那时 G6 在 Phase 6 路径上仍然放行（§2.1），
但探针依旧 13/13 全过、退出 0。**结论：这个探针不能作为 N1 的验收证据**；
它的 G06 证明的是"上一轮修好的 Phase 2 路径没有回退"，不是"多 Agent 路径不再绕过"。

建议（二选一，我不改产品代码，留给 Lead）：
1. 给 G06 增加一组走 Phase 6 规范事件（`generic-json` 的 `payload.text`）的用例；
2. 或在 07 号文档里显式写明"G06 探针只覆盖 Phase 2 路径，Phase 6 路径由
   `tests/integration/test_dependency_path_consistency.py` 与 V1 探针覆盖"。
   不写下来的话，后来者会以为 `13/13` 把 N1 也盖住了。

### 6.2 【留档】T2 的测试在 13:09 前后短暂与实现不一致（已修，且是修严不是放宽）

我在 13:09 从当时的工作区复制的一份副本里，跑出 3 条失败：

    FAILED test_dependency_extraction_parity.py::test_non_literal_dynamic_import_is_unproven_not_ignored
    FAILED test_dependency_extraction_parity.py::test_governed_dependencies_registers_names_and_markers
    FAILED test_dependency_extraction_parity.py::test_governed_dependencies_are_gated_by_the_declared_language
    3 failed, 38 passed

原因：用例文本 `UNPROVEN_DYNAMIC_IMPORT_TEXT` 里含一行 `import importlib`，
所以 `propose_dependencies(...).names` 正确结果是 `("importlib",)`，而当时的断言写的是 `()`
（`governed_dependencies(...)` 同理，正确结果是标记 + `"importlib"`）。
T2 随后把期望改成 `("importlib",)` / 标记 + 名字 —— **新期望比旧期望更严格**，属于修正而不是放宽。
留档的理由：如果最终状态又回到 `()`，本轮不能算全绿；截至收尾，live 版本是修好的（§4）。

### 6.3 【口径说明】in-scope 的"163"与 07 号文档 §2 的"148"不是同一个数

- 07 号文档：2026-09-25 实测，文件集 = 当时 `git status` 的 44 文件改动集；
- 本报告：2026-09-26 13:01 实测，文件集 = T1/T2/T3/T4 任务书逐文件清单的**并集**（30 个）。

两者都指向同一件事（"本轮要动的文件必须清到 0"），但不能相互验证。判定一律以 §3.1 的文件集与
`.tmp/verifier-n1/ruff-*.json` 的原始输出为准。

### 6.4 【无需裁决，但要知道】`p6-hook` 这条路径的语义

`legacy-post-only` 的能力上限是 `read_only` + `blocking: post_only`，它的写类动作本来就
不承担前置阻断（能力门在接入时就把上限算出来）。所以我在 §2 里对这一条路径比对的是
**"登记的依赖集"**（`context.dependencies`）而不是"拦没拦住"——T2 的
`test_event_adapter_path_registers_the_same_dependencies` 也是同一个口径。
"结论相同"这条要求由 `p6-json` / `p6-dsh` 两条真正有前置阻断能力的路径承担。

---

## 7. 复现清单

### 7.1 仪器

| 文件 | 作用 |
| --- | --- |
| `.tmp/verifier-n1/probe_n1.py` | 四路径 G6 探针（含放行对照、异常可见） |
| `.tmp/verifier-n1/probe_language_gate.py` | language 门控 / skipped_rules 探针 |
| `.tmp/verifier-n1/ruff_scope.py` | 逐文件 ruff 计数（只数违规行，留原始输出） |
| `.tmp/verifier-n1/assert_diff.py` | 断言 AST 比对（把"换行位移"与"改断言"分开） |
| `.tmp/verifier-n1/ast_equal.py` | 整模块 AST 等价（用于内嵌脚本之外的格式改动） |
| `.tmp/verifier-n1/make_tree.py` | 隔离副本 + 4 种变异（回退接线 / 删语言守卫 / 删标记 / 换旧正则） |
| `.tmp/verifier-n1/compare.py` | 两次探针报告的逐格对照 |
| `.tmp/verifier-n1/diff_probe_reports.py` | 两次缺口探针报告的结论/facts 比对 |
| `.tmp/verifier-n1/tree_hash.py` | 运行窗口内"代码是否冻结"的逐文件 sha256 清单 |
| `.tmp/verifier-n1/scope.json` | in-scope / 改动集其余 / 边界 三块文件清单 |

### 7.2 一键复现（按顺序）

    # 0) 修前基线（已经做过了；这里给出当时的口径）
    #    开工瞬间把工作区复制到 .tmp/verifier-n1/pre-fix/，之后所有"修前"结论都相对它

    # 1) G6：修前红 → 修后绿
    .venv/Scripts/python.exe .tmp/verifier-n1/probe_n1.py --root .tmp/verifier-n1/pre-fix --tag pre-fix --out .tmp/verifier-n1/pre-fix.json
    .venv/Scripts/python.exe .tmp/verifier-n1/probe_n1.py --root . --tag live-final --out .tmp/verifier-n1/live-final.json
    .venv/Scripts/python.exe .tmp/verifier-n1/compare.py --before .tmp/verifier-n1/pre-fix.json --after .tmp/verifier-n1/live-final.json

    # 2) 反向对照：回退接线 → 重新变红
    .venv/Scripts/python.exe .tmp/verifier-n1/make_tree.py --target .tmp/verifier-n1/regressed --mutation revert-wiring
    .venv/Scripts/python.exe .tmp/verifier-n1/probe_n1.py --root .tmp/verifier-n1/regressed --tag reverted-wiring --out .tmp/verifier-n1/reverted-wiring.json
    .venv/Scripts/python.exe .tmp/verifier-n1/compare.py --before .tmp/verifier-n1/live-final.json --after .tmp/verifier-n1/reverted-wiring.json

    # 3) ruff
    .venv/Scripts/python.exe .tmp/verifier-n1/ruff_scope.py --root .tmp/verifier-n1/pre-fix --tag pre-fix --out .tmp/verifier-n1/ruff-pre-fix.json --skip-docs
    .venv/Scripts/python.exe .tmp/verifier-n1/ruff_scope.py --root . --tag live-final --out .tmp/verifier-n1/ruff-live-final.json

    # 4) 无回归
    .venv/Scripts/python.exe .tmp/runlock.py -m pytest -q
    .venv/Scripts/python.exe .tmp/verifier-n1/assert_diff.py --path tests/contract/test_dsh_adapter.py --baseline snapshot

    # 5) 不静默
    .venv/Scripts/python.exe .tmp/verifier-n1/probe_language_gate.py --root . --tag live-final --out .tmp/verifier-n1/language-gate-final.json
    .venv/Scripts/python.exe .tmp/verifier-n1/make_tree.py --target .tmp/verifier-n1/copy-clean2 --mutation none
    .venv/Scripts/python.exe .tmp/verifier-n1/make_tree.py --target .tmp/verifier-n1/mutant-guard2 --mutation drop-language-guard
    .venv/Scripts/python.exe .tmp/runlock.py -m pytest <copy2>/tests/contract/test_dependency_extraction_parity.py <copy2>/tests/integration/test_dependency_path_consistency.py -q

    # 6) 边界外行为不变
    .venv/Scripts/python.exe .tmp/verifier-n1/pre-fix/tools/governance_gap_probe.py --root .tmp/verifier-n1/pre-fix --phase after --work .tmp/verifier-n1/gapwork-old2 --json-out .tmp/verifier-n1/gap-old2.json
    .venv/Scripts/python.exe tools/governance_gap_probe.py --root .tmp/verifier-n1/pre-fix --phase after --work .tmp/verifier-n1/gapwork-new3 --json-out .tmp/verifier-n1/gap-new3.json
    .venv/Scripts/python.exe .tmp/verifier-n1/diff_probe_reports.py --a .tmp/verifier-n1/gap-old2.json --b .tmp/verifier-n1/gap-new3.json

### 7.3 我没有做的事

- 没有跑 `python tools/ci_local.py`（Lead 独占排他锁，且它跑的是全套门禁，不属于本任务）；
- 没有跑 Phase 6 `runtime.py` 的受控写链路、Phase 7 API、Phase 5 AST 路径（见 §2.5）；
- 没有做分支覆盖率测量：`coverage` / `pytest-cov` **没有安装**（`import coverage` 与
  `import pytest_cov` 都 ModuleNotFoundError），因此 §5.2 用"变异能否被测试杀死"替代 ——
  这比行覆盖率更强（覆盖率只证明"执行到了"，变异证明"断了会被发现"）；
- 没有改任何产品代码 / 测试 / 配置：本文件之外，写入全部落在 `.tmp/verifier-n1/**`。---

## 8. 附录

### 8.1 关键文件的开工 → 收尾 sha256

| 文件 | 开工瞬间（快照） | 收尾 |
| --- | --- | --- |
| `src/adapters/textfacts.py` | `28CBA08070BE9923` | `2C6CBB99F1442F1D` |
| `src/adapters/base.py` | `84DEA2D35B3D93F8` | `5C7683C400C303DF` |
| `src/adapters/dsh/adapter.py` | `285938C64D99E1C4` | `4604300284F9DE6C` |
| `src/adapters/json_adapter.py` | `526CD6D7D706AC46` | `5E7A9A729D617919` |
| `src/adapters/event_adapter.py` | `E97269DA1DBDFD12` | `3B5D91639BE13F2B` |
| `src/adapters/dsh_adapter.py` | `4D17E8381765A0A8` | `109794F3F842B0E5` |
| `tests/contract/test_dsh_adapter.py` | `B0F80E28B0A87B76` | `1D2D525279816887` |
| `tests/integration/test_dependency_path_consistency.py` | `3395FCCF752ECBFA` | `2F8EE5DFE840606C` |
| `tests/contract/test_dependency_extraction_parity.py` | （开工时不存在） | `C5DFF7290AE47BDB` |
| `tools/governance_gap_probe.py` | `E0E2E390C753A980` | `BFA60D0C0E89C4AC` |

### 8.2 与 Lead 口径的对账

Lead 在收尾同步里给的数字是"本轮改动集 **38 个 in-scope .py 合计 0 条**"。
本报告的两个桶相加正好是 38：`in_scope` 30 + `change_set_extra` 8 —— 两边说的是同一件事，
只是我把"T3/T4 任务书逐文件列出的"与"改动集里剩下的"分开计数，好让"清单外漏判"这件事可判定。

### 8.4 报告出具之后的一次改动：G06 范围注释（已独立复核）

本报告 §3.3 / §8.1 记录的 `tools/governance_gap_probe.py` 收尾状态是
`sha256 BFA60D0C0E89C4AC…` / `blob e41547F3EB34…`（本轮验证窗口内）。
出具之后，Lead 按 §6.1 的裁决 (b) 在该文件的 G06 段加了一段**范围声明注释**，随后把两组证明交我复核。
我用同一套方法独立复核，结论：改动确实是**纯注释、且严格增量**。

| 复核项 | 命令 | 结果 |
| --- | --- | --- |
| 对照副本确实是改动前那一份 | `sha256(.tmp/lead-probe-before/governance_gap_probe.py)` | `BFA60D0C0E89C4AC` —— 与本报告 §8.1 记录的收尾 sha256 **逐字符相同** |
| 改动形态 | `difflib.unified_diff` 逐行比对 | 新增 14 行、删除 **0** 行、新增行里**非注释 0 行** |
| AST | `ast_equal.py --baseline file --before …` | `AST identical: True`（2175 → 2189 行，100831 → 101980 B） |
| 行为 | 同一 `--root`（`.tmp/verifier-n1/pre-fix`）跑新旧两份探针，再 `diff_probe_reports.py` | 都 exit 0 / 13/13；`逐项结论相同: True`、`facts（归一化后）相同: True` |

复核后当前 blob = `6dce2a474374ca20…`（sha256 `06AACE201E486E38…`）。
注释内容与裁决 (b) 一致：写明 G06 只驱动 Phase 2 的 `python -m adapters.dsh.hooks`、
写明"G6 曾在 Phase 6 路径独立成立而那棵树上本探针照样 13/13"、
**先列两个 git 跟踪的测试文件**、V1 探针只作附注并标明"构建产物、cleanup 会删、可重建"。

因此 §3.3 的"blob 前后值"读作**本轮验证窗口内**的前后值；窗口之后的这次注释改动有本节的独立复核。

### 8.3 锁与副本

本报告的所有 pytest 调用都经 `.venv/Scripts/python.exe .tmp/runlock.py -m pytest …`，
且**一律在主树根目录调用**（runlock 自己会把 cwd 钉在主树）。
`make_tree.py` 造的副本只复制 `src/ tests/ tools/ policies/ adapters/ validation/ knowledge/ registry/`
与几个根文件，**不含 `.tmp/`** —— 因此副本里没有第二把 runlock，也不会有副本自己的锁目录。
副本测试走的是主树那把锁（这正是"同一工作树同时只允许一个测试运行"想要的语义）。
