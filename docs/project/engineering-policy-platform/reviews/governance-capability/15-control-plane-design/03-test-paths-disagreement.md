# 03 · 「哪些路径算测试」两份声明的不一致（101 个文件）

- **来源（两份声明本身，都在 tracked 树里）**：
  `validation/test-layout.yaml`（sha256[:16] **`337D638B510D550D`**，1742 B）与
  `examples/dsh/dsh-adapter.yaml`（**`985A6EE75EFF2825`**，4427 B）
- **来源（原始计数）**：`.tmp/round-15/design/A/probe_testpaths.py`（A 方面探针）与 `A/A-position.md:84-92`；
  我自己的重算脚本与原始输出在 `.tmp/round-15/verify/plan/recount_testpaths.py`、`testpaths-raw.txt`
- **摘录日期**：2026-09-28；**来源树**：检查点 `e235626c`（两份声明均在该提交里，重算不依赖 .tmp）
- **口径**：本文的 101 是**我按自己的 glob 翻译器重算的**，不是抄 A 的数字（见 §3）。

## 1 两份声明的原文位置

| 声明 | 位置 | 内容 |
| --- | --- | --- |
| 平台级（唯一权威口径，AGENTS 第 49 条） | `validation/test-layout.yaml:21-23` | `test_patterns: ["tests/**/test_*.py", "tests/**/*_test.py"]`；:13-20 的注释自称「口径只有一份」 |
| Adapter 声明（第二处人写） | `examples/dsh/dsh-adapter.yaml:22-24` | `test_paths: ["tests/**/*.py"]`、`test_layer: test`；:16-21 的注释解释 M1 的教训 |
| 规则出处 | `AGENTS.md` 第 49 条（P4/P5） | 「同一个测试文件不许在 Hook 路径与验证器路径上得到两个层」 |

## 2 不一致的具体读数（一个例子的双向）

以 `tests/conftest.py` 为例（我自己算的）：

| 判据 | 读数 |
| --- | --- |
| 平台 `layout.is_test("tests/conftest.py")` | **False**（两条 pattern 都要求文件名以 `test_` 开头或以 `_test.py` 结尾） |
| Adapter `test_paths` 命中 | **True**（`tests/**/*.py`） |

同样形态的另两例：`tests/api_support.py`、`tests/fixtures/rules/DOC-001/bad.py` —— 都是 False / True。

**层**（不只是「算不算测试」，还会影响 layer）的例子：
`tests/fixtures/validators/project/src/shop/order_controller.py`
（我用 tracked 树里的两个生产函数亲自读到，不是转述 A）：

| 路径 | 读数 | 依据 |
| --- | --- | --- |
| Adapter 路径 `AdapterConfig.layer_resolution(...)` | layer = **test** | adapter 的 `test_paths` 先命中 |
| 验证器路径 `policy.check.resolve_layer(...)` | platform `is_test` = False → 落到 `infer_layer(file)` = **controller** | `src/policy/check.py` 的 `resolve_layer` 源码：declared → platform_test_layout → filename_guess |

这正是 AGENTS 第 49 条禁止的形态：**同一个测试文件在两条路径上得到两个层**。

## 3 计数：101（以及它依赖的口径）

- 我自己实现 `**` 语义后重算：`tests/` 下 **184** 个 .py 文件，其中 **101** 个「平台判定 ≠ Adapter 判定」。
- **口径依赖**：若把 `**/` 解释成「至少一段目录」（不允许匹配 0 段），同一个脚本给 **97**。A 的探针与平台自身的匹配语义取的是「0 段也可」，
  所以 101 是与平台一致的读数；**引用时请带这个前提**。
- **方向**：101 条全部是 `platform=False / adapter=True`，**没有一条反向**（adapter 的 pattern 是平台两条的超集）。
- 分类：101 条全部是「非 `test_*` / 非 `*_test.py`」的辅助与夹具文件（tests 下的 support 模块、夹具项目、规则正反例）。

## 4 全部 101 条（相对仓库根，每行 3 条）

`````
tests/api_support.py  tests/conftest.py  tests/enforcement_support.py
tests/fixtures/agent_events/workspace/src/shop/__init__.py  tests/fixtures/agent_events/workspace/src/shop/order_controller.py  tests/fixtures/agent_events/workspace/src/shop/order_repository.py
tests/fixtures/agent_events/workspace/src/shop/order_service.py  tests/fixtures/rules/DOC-001/bad.py  tests/fixtures/rules/DOC-001/good.py
tests/fixtures/rules/DOC-002/bad.py  tests/fixtures/rules/DOC-002/good.py  tests/fixtures/rules/DOC-003/bad.py
tests/fixtures/rules/DOC-003/good.py  tests/fixtures/rules/DOC-004/bad.py  tests/fixtures/rules/DOC-004/good.py
tests/fixtures/rules/SEC-001/bad.py  tests/fixtures/rules/SEC-001/good.py  tests/fixtures/rules/SEC-002/bad.py
tests/fixtures/rules/SEC-002/good.py  tests/fixtures/rules/SEC-003/bad.py  tests/fixtures/rules/SEC-003/good.py
tests/fixtures/rules/SEC-004/bad.py  tests/fixtures/rules/SEC-004/good.py  tests/fixtures/rules/SEC-005/bad.py
tests/fixtures/rules/SEC-005/good.py  tests/fixtures/rules/SEC-006/bad.py  tests/fixtures/rules/SEC-006/good.py
tests/fixtures/rules/SEC-007/bad.py  tests/fixtures/rules/SEC-007/good.py  tests/fixtures/rules/SEC-008/bad.py
tests/fixtures/rules/SEC-008/good.py  tests/fixtures/rules/SEC-009/bad.py  tests/fixtures/rules/SEC-009/good.py
tests/fixtures/rules/SEC-010/bad.py  tests/fixtures/rules/SEC-010/good.py  tests/fixtures/rules/SEC-011/bad.py
tests/fixtures/rules/SEC-011/good.py  tests/fixtures/rules/SEC-012/bad.py  tests/fixtures/rules/SEC-012/good.py
tests/fixtures/rules/SEC-014/bad.py  tests/fixtures/rules/SEC-014/good.py  tests/fixtures/rules/SEC-015/bad.py
tests/fixtures/rules/SEC-015/good.py  tests/fixtures/rules/SEC-017/bad.py  tests/fixtures/rules/SEC-017/good.py
tests/fixtures/rules/SEC-018/bad.py  tests/fixtures/rules/SEC-018/good.py  tests/fixtures/rules/SEC-019/bad.py
tests/fixtures/rules/SEC-019/good.py  tests/fixtures/rules/SEC-021/bad.py  tests/fixtures/rules/SEC-021/good.py
tests/fixtures/rules/SEC-022/bad.py  tests/fixtures/rules/SEC-022/good.py  tests/fixtures/rules/STYLE-001/bad.py
tests/fixtures/rules/STYLE-001/good.py  tests/fixtures/rules/STYLE-002/bad.py  tests/fixtures/rules/STYLE-002/good.py
tests/fixtures/rules/STYLE-003/bad.py  tests/fixtures/rules/STYLE-003/good.py  tests/fixtures/rules/STYLE-004/bad.py
tests/fixtures/rules/STYLE-004/good.py  tests/fixtures/rules/STYLE-005/bad.py  tests/fixtures/rules/STYLE-005/good.py
tests/fixtures/rules/STYLE-006/bad.py  tests/fixtures/rules/STYLE-006/good.py  tests/fixtures/rules/STYLE-007/bad.py
tests/fixtures/rules/STYLE-007/good.py  tests/fixtures/rules/STYLE-008/bad.py  tests/fixtures/rules/STYLE-008/good.py
tests/fixtures/rules/STYLE-009/bad.py  tests/fixtures/rules/STYLE-009/good.py  tests/fixtures/rules/STYLE-010/bad.py
tests/fixtures/rules/STYLE-010/good.py  tests/fixtures/rules/STYLE-011/bad.py  tests/fixtures/rules/STYLE-011/good.py
tests/fixtures/rules/STYLE-012/bad.py  tests/fixtures/rules/STYLE-012/good.py  tests/fixtures/rules/STYLE-014/bad.py
tests/fixtures/rules/STYLE-014/good.py  tests/fixtures/rules/STYLE-015/bad.py  tests/fixtures/rules/STYLE-015/good.py
tests/fixtures/rules/STYLE-016/bad.py  tests/fixtures/rules/STYLE-016/good.py  tests/fixtures/rules/STYLE-017/bad.py
tests/fixtures/rules/STYLE-017/good.py  tests/fixtures/rules/STYLE-018/bad.py  tests/fixtures/rules/STYLE-018/good.py
tests/fixtures/validators/project/src/shop/__init__.py  tests/fixtures/validators/project/src/shop/broken_syntax.py  tests/fixtures/validators/project/src/shop/dynamic_dependency.py
tests/fixtures/validators/project/src/shop/no_module_docstring.py  tests/fixtures/validators/project/src/shop/order_controller.py  tests/fixtures/validators/project/src/shop/order_controller_bad.py
tests/fixtures/validators/project/src/shop/order_repository.py  tests/fixtures/validators/project/src/shop/order_service.py  tests/fixtures/validators/project/src/shop/style_offences.py
tests/fixtures/validators/project/src/shop/submodule_controller_bad.py  tests/fixtures/validators/project/src/shop/unowned_lint_code.py  tests/fixtures/validators/project/src/shop/unresolved_dependency.py
tests/fixtures/validators/tools/fake_tool.py  tests/orchestration_support.py
`````

## 5 怎么复核（不需要 .tmp）

1. 读两份声明：`validation/test-layout.yaml:21-23`、`examples/dsh/dsh-adapter.yaml:22-24`。
2. 重算：把 `tests/` 下所有 `*.py` 按两份 pattern 各判一次，取「判定不同」的集合——平台语义是 `**/` 可匹配 0 段目录。
   参考实现（我用的翻译器）见 `.tmp/round-15/verify/plan/recount_testpaths.py`（**只在 .tmp 里**；也可按上句重写十余行）。
3. 层读数：`AdapterConfig.layer_resolution(rel).layer` 与 `policy.check.resolve_layer(...)`（两份源码都在 tracked 树）。
- **原件不在时**：A 的探针与我的原始输出不可读，但**计数与清单可以按第 2 步重现**——这是本归档里唯一完全可重算的读数。
- 本文件**未核实**的项：无（101、97、方向、例子、层读数都是我自己算/读的）。
