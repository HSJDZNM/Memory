# Phase 1：Policy Engine

## 目标

把 Phase 0 的单规则判断升级为可解释、可扩展但仍保持确定性的 Policy Engine。核心新增能力是上下文规范化、范围匹配、严重级别汇总和统一 Decision。

## 本阶段不做

- 不连接 dsh 或其他 Agent；
- 不做知识检索；
- 不执行真实工具；
- 不启动 HTTP 服务；
- 不让规则内嵌任意 Python 表达式或动态代码。

## 开发步骤

### 1. 完善 PolicyContext

加入 `request_id`、`project`、`file`、`language`、`operation`、`agent`、`task`、`module`、`layer`、`dependencies`、`git_diff` 和 `principal`。明确哪些字段必需，哪些字段可空。

### 2. 建立上下文规范化器

- Windows 与 POSIX 路径统一为仓库相对 `/` 路径；
- language、operation、layer 使用受控枚举或规范化小写值；
- 去重并稳定排序 dependencies；
- 路径逃出仓库、空主体或未知操作被拒绝；
- 不根据文件名猜测 principal、权限或审批状态。

### 3. 实现 Scope Matcher

首版支持精确值、值列表和 `*`。多个 scope 字段采用 AND，同字段多个值采用 OR。没有声明的 scope 字段表示“不限制”，而不是匹配空值。

Matcher 返回：

```text
matched: true/false
reasons: 每个字段的比较结果
specificity: 命中的非通配字段数
```

### 4. 定义严重级别与决策表

| 最高严重级别 | Decision |
| --- | --- |
| 无 violation | `allow` |
| info / warning | `allow_with_warnings` |
| error / critical | `block` |

如果规则显式要求人工审批，Decision 先以 `block` 表达，并附上 `required_action=approval`；不要用一个模糊的 warning 代替授权。

### 5. 实现解释信息

Decision 同时记录 `matched_rules`、`skipped_rules` 的原因摘要、violations、证据、规则集哈希和 trace ID。用户输出可以简化，但审计模型不能丢失这些字段。

### 6. 固定协议版本

核心结果增加 `schema_version`。未知版本拒绝消费，为 Phase 2 Adapter 和 Phase 7 API 提供稳定边界。

## 测试步骤

### 规范化测试

- `src\\order\\controller.py` 与 `src/order/controller.py` 结果一致；
- `..` 逃逸路径被拒绝；
- operation 大小写策略固定；
- dependencies 去重且顺序稳定；
- 安全关键字段缺失时失败关闭。

### Scope 矩阵

覆盖 language、module、layer、operation 的单字段、多字段、列表、通配和缺失值组合。每个未命中用例同时断言未命中原因。

### 决策聚合

- 无规则命中得到 allow；
- 多个 warning 得到 allow_with_warnings；
- warning + error 得到 block；
- critical 始终 block；
- 规则输入顺序变化不改变 violation 排序和最终决定；
- 重复规则 ID 在加载阶段失败，不能在聚合阶段覆盖。

### 协议快照

对一个 allow、一个 warning 和一个 block 结果保存 JSON fixture。后续修改协议必须显式更新 `schema_version` 或说明兼容性。

### 性能基线

用固定生成器创建 10、100、1000 条简单规则，记录匹配耗时与内存，只建立基线，不提前优化。性能测试必须使用固定随机种子。

## 观察点

同一规则在不同上下文中可能命中或跳过。观察 Decision 如何把“规则是否相关”和“是否违规”分开表达，并能解释每一步。

## 退出条件

- 核心模型中没有任何 Agent SDK 类型；
- Scope 与 severity 的全部组合有表驱动测试；
- Decision JSON 契约稳定并带版本；
- 相同上下文和规则集哈希产生相同决定；
- 性能基线已记录但未引入不必要缓存。

通过后进入 [Phase 2](phase-2-dsh-adapter.md)。

---

## 实施记录（2026-09，Phase 1 已完成）

本节记录实际落地的接口、命令与偏差，避免文档与代码漂移。原始计划保留在上文。

### 实际新增与变化

| 位置 | 内容 |
| --- | --- |
| `src/policy/context.py` | 新增：`build_context`、`normalize_context`、`repo_relative_path`、`normalize_operation` |
| `src/policy/scope.py` | 新增：`match_scope`、`compare_dimension`、`dimension_value`、`ScopeMatchResult`、`DimensionComparison` |
| `src/policy/models.py` | `Severity.CRITICAL`、`ScopeValue` 选择器、`Enforcement.requires_approval`、`RequiredAction`、`SkippedRule`、`ProtocolError`、`SCHEMA_VERSION`、`parse_decision`、`expected_decision` |
| `src/policy/engine.py` | 使用 Scope Matcher；结果带上 matched / skipped / 哈希 / trace；新增 `explain` |
| `src/policy/check.py` | 显式 `--layer`（仍可按文件名推断并标注）、`--module` 不再推断、`--trace-id`、输出命中/跳过原因、`exit_code` 移到 CLI 包装层 |
| `tools/policy_bench.py` | 新增：固定种子的规则生成器与匹配基线（测试与阶段证据共用） |
| `tools/phase_evidence.py` | 增加 `decision_protocol` 与 `performance` 段；套件加入 `tests/contract` |
| `tests/unit/test_context.py`、`test_scope.py`、`test_decisions.py` | 新增：规范化、范围矩阵、决策聚合 |
| `tests/contract/test_decision_protocol.py`、`tests/fixtures/decisions/*.json` | 新增：allow / warning / block / approval 四份协议快照与版本拒绝测试 |
| `tests/integration/test_performance_baseline.py` | 新增：固定种子的性能基线用例 |
| `docs/learning/phase-1/` | 新增学习手册；`tools/build_learning_notebook.py` 改为按阶段生成 |
| `.github/workflows/phase-1.yml` | 取代 `phase-0.yml`：Phase 0 的重放用例 + Phase 1 的契约、快照、基线与手册校验 |

### 协议：PolicyDecision 1.0

`schema_version: "1.0"`，字段固定为：

```text
schema_version, decision, request_id, trace_id, rule_set_hash,
matched_rules, skipped_rules[{rule_id, reasons}], violations[],
required_action, policy_version
```

- `ValidationResult.to_decision_dict()` 与 `parse_decision()` 严格互逆（契约测试逐字段比对）；
- 未知 `schema_version`、未知 `decision`、未知 `required_action` 一律抛 `ProtocolError`；
- CLI 的 `exit_code` 属于包装层，不属于协议载荷；
- 快照更新方式：`$env:POLICY_UPDATE_SNAPSHOTS = "1"` 后运行 `python -m pytest tests/contract -q`，
  并在提交信息里说明兼容性。

### 与原始计划的差异（都需要知道）

1. **scope 未知维度默认策略从 skip 改为 reject**。原计划只要求支持精确值/列表/通配，
   没有规定未知维度的默认行为。Phase 1 选择拒绝，因为拼错维度名会让规则悄悄放大适用范围，
   属于"无法通过测试发现的失效"。确需忽略时显式写 `extra_policy: skip`，并记入匹配原因。
2. **`PolicyContext.language` 取消默认值 python**。默认值会让非 Python 文件被 Python 规则
   静默命中或漏判；"不知道语言"现在必须显式写 null，并在 skipped_rules 里体现。
3. **CLI 不再从文件路径推断 module**。原 Phase 0 实现按父目录推断，猜错会让规则在错误范围生效；
   layer 的推断保留（并标注为 CLI 便利功能），因为示例重放需要它。
4. **`RuleSet.identity` 改为与加载顺序无关**：先对规则载荷排序再求 sha256，
   否则同一组规则换个目录顺序就会得到不同的 `rule_set_hash`。
5. **新增 `critical` 严重级别**：决策表按设计文档实现；`insufficient_context_violation`
   现在用 critical 表达"安全关键上下文缺失"。
6. **规则集哈希变化**：`exclude_none` + 排序后，`ARCH-001@1` 的规则集哈希变为
   `sha256:4fd2a0d4cc8f74fc1a2fe8abeb1cf9758f483fd0242a609b1be6182535482bec`。

### 落地命令

```powershell
python -m pytest tests/unit -q            # 212 用例
python -m pytest tests/contract -q        # 24 用例（协议快照）
python -m pytest tests/integration -q     # 35 用例
python -m policy.check examples/bad_controller.py --dependencies repository   # 退出码 1
python -m policy.check examples/good_controller.py --layer service --dependencies repository  # 退出码 0，报告跳过原因
python -m policy.check --check-rules --json
python tools/policy_bench.py --counts 10 100 1000                             # 性能基线
python tools/phase_evidence.py            # .tmp/artifacts/phase-1-evidence.json
```

### 性能基线（本机 Python 3.13.11 / Windows，固定种子 20260101）

| 规则数 | 每次评估耗时 | 内存峰值 | 说明 |
| --- | --- | --- | --- |
| 10 | ≈ 0.5 ms | ≈ 60 KiB | 20 个上下文 × 3 轮 |
| 100 | ≈ 4 ms | ≈ 475 KiB | 线性增长，无意外 |
| 1000 | ≈ 40 ms | ≈ 4.6 MiB | 含大量 pydantic 对象构造 |

基线只作回归参照：**没有引入缓存**。数据来自 `tools/policy_bench.py`（单独运行时观测值）；
机器负载会明显影响耗时（紧接着整套测试运行时观测到约 2 倍数值），因此测试只断言数量级上限，
不做精确比较。规则集哈希只取决于种子，不受环境与负载影响。

### 环境限制（重放时必须知道）

与 Phase 0 相同，本阶段实现与测试在 DSH 受限沙箱（workspace-write）内完成：

1. `uv sync` 无法在该沙箱里探测解释器，本地用 `python -m pip install -r requirements.in` 验证，
   CI 仍使用 `uv sync --all-extras`；
2. 沙箱拒绝 `tempfile.mkdtemp`/`chmod`，测试继续使用 `tests/conftest.py` 的 `tmp_root`；
3. 沙箱里 pytest 在 `.tmp/.pytest_cache` 上写不进缓存，转而在缓存目录的父目录创建
   `.tmp/pytest-cache-files-*/` 兜底目录，且沙箱同样拒绝删除它们（`PermissionError`）。
   `tools/cleanup.py` 会如实报告失败并以退出码 1 结束，不会假装成功；
   普通开发机上 `pytest.ini` 的 `cache_dir` 正常工作，不会产生这些目录；
4. 手册生成器会执行"配置错误"示例单元，因此标准错误里会出现
   `config error: 规则目录不存在: policies/does-not-exist`；这是预期输出，不是失败。

### 验收证据

`python tools/phase_evidence.py` 生成的 `.tmp/artifacts/phase-1-evidence.json` 记录：
实现版本、规则集哈希、决策协议版本、每个套件的命令/用例数/失败数、性能基线、JUnit 报告路径与时间戳。
最近一次本地结果：**271 个用例通过（单元 212 + 契约 24 + 集成 35），0 失败**。
