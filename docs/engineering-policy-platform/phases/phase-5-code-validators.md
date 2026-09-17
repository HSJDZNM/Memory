# Phase 5：代码验证器

## 目标

用 AST、依赖图、现有 Linter、类型检查和测试产生确定性证据，让 Policy Engine 不依赖 LLM 猜测代码是否合规。

## Validator 契约

```text
validate(target, context, config) → ValidationEvidence[]
```

每条 evidence 至少包含 validator ID/版本、规则 ID、文件、行列、消息、严重级别、工具退出码和可选修复建议。Validator 只产生证据，最终 allow/block 仍由 Policy Engine 决定。

## 渐进开发步骤

### 1. Python AST 最小实现

首个目标仍是 `ARCH-001`。对 Python 可先使用标准库 `ast` 提取 import 与调用依赖，避免在单语言原型阶段过早引入 tree-sitter。需要跨语言或标准库 AST 无法覆盖时，再加入 tree-sitter Adapter。

### 2. 依赖图

把文件、模块和层作为节点，把 import 或解析后的依赖作为边。依赖图必须区分无法解析、外部包和项目内部模块，不能把“解析失败”当作“没有依赖”。

### 3. 外部工具 Adapter

复用 Ruff、类型检查器和 pytest，不重复实现它们。每个 Adapter 固定：

- 工具版本和配置文件；
- 参数 allowlist；
- 工作目录与超时；
- stdout/stderr 大小上限；
- 原始输出到统一 evidence 的映射；
- 工具缺失、崩溃和配置错误的区别。

### 4. 多语言扩展点

Python 规则可参考仓库 PEP 8/257；.NET API 规则可参考本地 .NET Design Guidelines。语言专项规则进入独立 rule pack，核心 Pipeline 不包含语言分支。

### 5. Test Validator

根据 git diff 找到生产文件与测试文件，运行最小相关测试；相关性不足时升级到更大测试集。测试进程必须隔离、限时，并限制网络和写入范围。

### 6. Pipeline 聚合

```text
Code → AST → Dependency → Lint → Type → Tests → Evidence → Policy
```

支持按规则选择 Validator，并明确哪些可并行。一个关键 Validator 缺失或超时不能被其他 PASS 抵消。

## 测试步骤

### Golden fixtures

为每条规则提供最小 good/bad 源文件，断言规则 ID、文件和行列。首批至少包含：

- Controller → Repository（bad）；
- Controller → Service（good）；
- 动态 import 或别名 import；
- 语法错误；
- 无法解析的项目依赖；
- PEP 8 可由 Ruff 检出的风格错误；
- 缺失或错误的 docstring（如果项目采纳 PEP 257）；
- 生产变更缺少对应测试。

### Adapter 失效测试

- 工具不存在；
- 工具版本与锁定版本不符；
- 超时、崩溃、非零退出码；
- 输出为空、乱码或超长；
- 工作目录错误；
- 恶意文件名或输出尝试注入日志。

### 结果归一化

- Windows/POSIX 路径映射一致；
- 同一问题的排序稳定；
- 外部工具版本差异不会静默改变协议；
- 重复 evidence 去重但保留来源；
- 多 Validator 同时失败时最高严重级别正确。

### 测试有效性

每个 good/bad fixture 必须证明：移除违规代码后 bad 测试转为通过，重新引入违规后失败。对于行为测试，至少做一次最小变异或手工破坏，确认测试真的能抓到错误。

### 性能与隔离

- 固定小、中、大 fixture 记录耗时基线；
- 超时能终止子进程及其后代；
- 测试不能访问真实密钥或生产网络；
- 并行 Validator 不互相覆盖临时文件；
- 资源限制触发时产生明确 evidence。

## 观察点

观察 LLM 解释、Policy 决策和 Validator 证据的边界：解释可以变化，规则证据和最终决定必须稳定、可重放。

## 退出条件

- `ARCH-001` 完全由 AST/依赖证据判定；
- 外部工具版本、配置与错误分类可追溯；
- 关键 Validator 超时和缺失均失败关闭；
- good/bad/边界/失效 fixture 完整；
- 新增语言只需新增 Adapter 和 rule pack，不修改核心协议。

通过后进入 [Phase 6](phase-6-multi-agent-adapters.md)。
