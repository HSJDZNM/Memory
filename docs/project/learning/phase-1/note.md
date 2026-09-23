# Phase 1 对象与关系：Policy Engine

本文回答三个问题：**Phase 1 做了什么、系统里多了哪些对象、它们之间是什么关系**。
内容与仓库代码一致，每个对象都能在源码里找到对应定义。

对照阅读：

- 设计文档：[../../engineering-policy-platform/phases/phase-1-policy-engine.md](../../engineering-policy-platform/phases/phase-1-policy-engine.md)
- 可执行讲解：[walkthrough.ipynb](walkthrough.ipynb) / [walkthrough.py](walkthrough.py)

---

## 一、任务内容

一句话目标：**把 Phase 0 的单规则判断升级为可解释、可扩展但仍保持确定性的 Policy Engine**。

完整链路：

```text
原始请求 -> PolicyContext 规范化 -> Scope 匹配 -> Severity 决策 -> Decision（带协议版本与解释）
```

拆成六项可验收的具体工作（对应设计文档的六个开发步骤）：

| # | 工作 | 产物 | 可观察结果 |
| --- | --- | --- | --- |
| 1 | 补全 PolicyContext 并写清必需/可空 | `src/policy/models.py` | 缺 request_id / file / layer 直接失败，不猜 |
| 2 | 上下文规范化器 | `src/policy/context.py` | 反斜杠路径与斜杠路径得到同一个上下文 |
| 3 | Scope Matcher | `src/policy/scope.py` | 精确值 / 值列表 / 通配 / 缺值全部可解释 |
| 4 | 严重级别与决策表 | `engine.py` + `models.expected_decision` | info/warning 告警，error/critical 阻断 |
| 5 | 解释信息 | `ValidationResult` | matched_rules、skipped_rules、violations、哈希、trace |
| 6 | 固定协议版本 | `models.SCHEMA_VERSION` / `parse_decision` | 未知版本被拒绝消费 |

本阶段**仍然只有一条真实规则**：`ARCH-001`（Controller 不得直接依赖 Repository）。
所有新能力都用测试内联规则与合成规则验证，不改动仓库里的规则文件。

### 与 Phase 0 的行为差异（有意为之）

| 变化 | Phase 0 | Phase 1 | 理由 |
| --- | --- | --- | --- |
| scope 未知维度 | 记录并忽略（skip 默认） | **直接报错**（reject 默认） | 拼错维度名会让规则悄悄放大适用范围，比误报更危险 |
| context.language 默认值 | python | 无默认（None） | 默认成 python 会让非 Python 文件被 Python 规则静默命中 |
| CLI 的 module | 按文件父目录推断 | 只接受显式 `--module` | 猜错模块会让规则在错误范围上生效 |
| 决策载荷 | 只有 decision/request_id/matched_rules/violations/policy_version | 增加 schema_version、trace_id、rule_set_hash、skipped_rules、required_action | 协议版本与解释信息是后续阶段的稳定边界 |
| CLI JSON 的 exit_code | 放在 result 里 | 提到包装层 | result 必须能被 `parse_decision` 原样解析 |
| severity 枚举 | info / warning / error | 增加 **critical** | 需要"阻断且必须立刻处理"的级别 |
| 规则集哈希 | 依赖规则顺序 | 与顺序无关（内容排序后求哈希） | 目录遍历顺序不该影响审计身份 |

---

## 二、对象清单

系统里的对象分五族：规则侧、上下文档、范围匹配侧、输出侧（协议）、组件。

### 族 1：规则侧 —— 描述"什么是不允许的"

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| `Rule` | 模型 | id、version、name、description、scope、severity、enforcement、rule、message、source | 一条机器可执行规则 |
| `RuleScope` | 模型 | language?、layer?、module?、operation?、project?、agent?、extra_policy | 规则管谁；每个维度都可缺省 = 不限制 |
| `ScopeValue` | 联合类型 | 字符串 或 字符串元组 | 单值 / 多值（OR）/ 星号通配 |
| `Enforcement` | 模型 | type、checker、requires_approval | 执行方式；requires_approval 表示授权门禁 |
| `ForbiddenDependencyRule` | 模型 | forbidden_dependency | 被禁止的依赖清单 |
| `SourceRef` | 模型 | kind、path?、url?、note? | 规则的本地来源 |
| `RuleSet` | 模型 | rules、source_paths、identity | 规则集合；identity 是内容排序后的 sha256 |

### 族 2：上下文档 —— 描述"这次要检查什么"

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| `PolicyContext` | 模型 | **必填**：request_id、file、layer；**可空**：project、agent、operation、language、module、task、dependencies、git_diff、principal、trace_id | 一次检查的输入 |
| `Principal` | 模型 | subject、roles | 请求主体；只能显式提供，不得推断 |
| `Operation` | 枚举 | read / create / edit / delete / execute | 受控操作类型 |

### 族 3：范围匹配侧 —— 回答"这条规则此刻相关吗"

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| `ScopeMatchResult` | 模型 | matched、reasons、failures、comparisons、ignored_dimensions、specificity | 一次范围匹配的完整解释 |
| `DimensionComparison` | 模型 | dimension、declared、actual、matched、wildcard、reason | 单个维度的比较结果 |

### 族 4：输出侧 —— 描述"检查出了什么"，也是对外协议

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| `ValidationResult` | 模型 | schema_version、decision、request_id、trace_id、rule_set_hash、matched_rules、skipped_rules、violations、required_action、policy_version | 一次判断的完整结果 |
| `SkippedRule` | 模型 | rule_id、reasons | 未参与判断的规则及其原因 |
| `Violation` | 模型 | rule_id、rule_version、severity、message、evidence | 一条违规；一个依赖值一条 |
| `Evidence` | 模型 | kind、subject、value、file?、line?、detail? | 违规的结构化依据 |
| `Decision` | 枚举 | allow / allow_with_warnings / block | 三种决策；未识别值按协议错误处理 |
| `Severity` | 枚举 | info / warning / error / **critical** | 由规则声明；决定是否阻断 |
| `RequiredAction` | 枚举 | approval | 决策要求的前置动作 |

### 族 5：组件 —— 提供行为，不持有状态

| 组件 | 位置 | 职责 | 关键函数 |
| --- | --- | --- | --- |
| Context 规范化器 | `context.py` | 原始映射 -> 规范化 PolicyContext；拒绝猜测 | build_context、normalize_context、repo_relative_path、normalize_operation |
| Scope Matcher | `scope.py` | 规则范围 + 上下文 -> 可解释的匹配结果 | match_scope、compare_dimension、dimension_value |
| Engine | `engine.py` | 规则集 + 上下文 -> 决策；不读文件、不访问全局状态 | evaluate、explain、skipped_rule_id、rule_matches_context |
| 协议入口 | `models.py` | 决策载荷 <-> 模型；版本校验 | to_decision_dict、parse_decision、expected_decision |
| Loader | `loader.py` | 文件 -> 模型；原子加载 | load_rule_set、load_rules、assert_unique |
| CLI | `check.py` | 参数 -> 上下文、渲染、退出码 | run、infer_layer、render_text、render_json |
| 性能基线 | `tools/policy_bench.py` | 固定种子生成规则并测量 | generate_rules、generate_contexts、measure、run_baseline |
| 错误类型 | 各模块 | 区分"文件坏""上下文坏""协议坏""执行方式不支持" | LoaderError / RuleFileError / PolicyContextError / ProtocolError / EngineError |

---

## 三、关系

### 3.1 组成关系

```text
Rule                                  PolicyContext                 ValidationResult
|- RuleScope                          |- Principal                   |- schema_version
|  |- language / layer / module        |  |- roles                    |- decision            (1)
|  |- operation / project / agent      |- Operation           (1)     |- request_id
|  |- extra_policy（加载策略）          |- dependencies (tuple)        |- trace_id
|- Enforcement                        |- file / layer（必填）         |- rule_set_hash
|  |- type / checker                   |- language / module ...       |- matched_rules       (n)
|  |- requires_approval                                              |- skipped_rules       (n)
|- ForbiddenDependencyRule                                          |   |- rule_id
|  |- forbidden_dependency (tuple)                                  |   |- reasons (tuple)
|- SourceRef                                                        |- violations          (n)
|- message / severity                                               |   |- Evidence
                                                                    |   |   |- kind / subject / value
ScopeMatchResult                                                    |   |   |- file? / line? / detail?
|- matched                                                          |- required_action?    (0..1)
|- reasons / failures (tuple)                                       |- policy_version
|- comparisons (n) -> DimensionComparison
|   |- dimension / declared / actual / matched / wildcard / reason
|- ignored_dimensions (tuple)
|- specificity（只读属性，不参与决策）
```

### 3.2 一次判断的流向

```text
原始映射（dict）
   |  build_context：路径、大小写、枚举、去重、失败关闭
   v
PolicyContext（已规范化）
   |
   |  evaluate(rules, context)
   |     |- normalize_context（幂等，保证入口一致）
   |     |- 对每条规则 match_scope：
   |     |     命中 -> matched_rules；检查 checker 是否可执行
   |     |     未命中 -> skipped_rules + 失败原因
   |     |- _violations_for：上下文依赖 ∩ forbidden_dependency
   |     |- 稳定排序（规则身份 -> 证据值 -> 证据主体）
   |     |- expected_decision：无违规 allow / info|warning 告警 / error|critical 阻断
   |     |                     命中要求审批的规则 -> block + required_action=approval
   v
ValidationResult
   |  to_decision_dict -> PolicyDecision 载荷（带 schema_version）
   v
parse_decision（消费侧，未知版本或未知决策值直接拒绝）
```

### 3.3 必须成立的不变量

| 不变量 | 含义 | 由谁保证 |
| --- | --- | --- |
| 唯一表示 | 同一个文件、同一次操作只有一种上下文写法 | context.build_context、模型校验器 |
| 失败关闭 | 安全关键字段缺失、未知操作、未知协议版本一律拒绝 | build_context、parse_decision |
| 相关性与违规分离 | matched/skipped 回答"规则相关吗"，violations 回答"违规了吗" | ScopeMatchResult + ValidationResult |
| 确定性 | 相同上下文与相同规则集哈希得到相同 decision 与相同顺序 | engine.evaluate 的稳定排序 |
| 顺序无关 | 规则加载顺序、输入顺序不影响结论与哈希 | 排序后的 matched/skipped/violations、RuleSet.identity |
| 不可变 | 规则、上下文、结果创建后不可修改 | pydantic frozen=True |
| 解释完整 | 用户输出可以简化，协议载荷不缺字段 | to_decision_dict 与契约测试 |

---

## 四、边界与已知取舍

### 4.1 本阶段不做什么

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| 接 Agent（dsh / SDK） | 核心层不依赖任何 Agent 类型 | Phase 2 |
| 知识检索 | 还没有固定评测证明需要 | Phase 3 |
| 执行真实工具 | 执行器必须绑定已授权决策 | Phase 4 |
| AST / Lint / 类型检查 | 确定性代码证据属于验证器 | Phase 5 |
| HTTP 服务 | 核心协议刚稳定，不需要进程外共享 | Phase 7 |
| 规则内嵌表达式 | 规则是数据，不能变成动态代码 | 永不 |
| 缓存与预编译 | 基线显示还不需要 | 有证据再说 |

### 4.2 明确写下来的取舍

1. **声明了维度但上下文没有该值 -> 不命中**。这会让规则"该管却没管"，属于偏向漏判的选择；
   补偿手段是把原因写进 skipped_rules，让每次漏判都可见，而不是静默通过。
   Phase 2 的 Adapter 必须提供完整维度，Phase 4 才能在风险评估里用上这些原因。
2. **审批是前置门禁**：`requires_approval: true` 的规则只要范围命中就 block +
   `required_action=approval`，与是否违规无关；违规仍然单独记录在 violations 里。
   这条规则写得比较严格（"命中即需授权"），换来的是绝不会把授权降级成一句 warning。
3. **未知 scope 维度默认报错**：与 Phase 0 相反。放宽范围的错误无法通过测试发现，
   只能靠加载失败暴露出来。
4. **specificity 只解释不决策**：目前没有任何规则优先级机制，多规则同时命中时
   按严重级别聚合。specificity 先收集起来，等真正需要优先级时再定义语义。
5. **性能只建基线**：1000 条规则的匹配包含大量 pydantic 对象构造，
   属于"够用且可解释"的量级；没有证据证明需要缓存，因此不提前引入。

### 4.3 后续阶段可以直接依赖的稳定契约

- `policy.build_context`：Adapter 把原始事件变成上下文的唯一入口；
- `policy.evaluate`：规则集 + 上下文 -> ValidationResult；
- `ValidationResult.to_decision_dict` / `policy.parse_decision`：决策协议的双向边界；
- `SCHEMA_VERSION` 与 `SUPPORTED_SCHEMA_VERSIONS`：协议版本协商依据；
- `Decision` / `Severity` / `RequiredAction` / `Operation` 枚举：不允许出现未识别的值。
