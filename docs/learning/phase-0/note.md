# Phase 0 对象与关系：最小规则系统

本文回答三个问题：**Phase 0 做了什么、系统里有哪些对象、它们之间是什么关系**。
内容与仓库代码一致，每个对象都能在源码里找到对应定义。

对照阅读：

- 设计文档：[../../engineering-policy-platform/phases/phase-0-minimum-rule-system.md](../../engineering-policy-platform/phases/phase-0-minimum-rule-system.md)
- 可执行讲解：[walkthrough.ipynb](walkthrough.ipynb) / [walkthrough.py](walkthrough.py)

---

## 一、任务内容

一句话目标：**证明一个程序能读取机器可执行规则，并对固定上下文稳定地产生 PASS/FAIL**。

完整链路只有五步：

```text
YAML Rule -> Rule Loader -> Policy Engine -> PASS / FAIL -> Test Evidence
```

拆成六项可验收的具体工作：

| # | 工作 | 产物 | 可观察结果 |
| --- | --- | --- | --- |
| 1 | 固定 Rule Schema | `policies/architecture/ARCH-001.yaml` | 未知字段报错，不静默忽略 |
| 2 | 定义不可变核心模型 | `src/policy/models.py` | 缺必填字段/非法枚举被拒绝 |
| 3 | 实现 Loader | `src/policy/loader.py` | 按路径排序、拒绝重复 ID、原子加载 |
| 4 | 实现最小匹配器 | `src/policy/engine.py` | 表驱动得出 BLOCK / ALLOW |
| 5 | 实现 CLI | `src/policy/check.py` | 退出码 0 / 1 / 2 |
| 6 | 最小 CI 与证据 | `.github/workflows/phase-0.yml`、`tools/phase_evidence.py` | 99 用例通过 + 规则集哈希 |

本阶段**只有一条规则**：`ARCH-001` —— Controller 不得直接依赖 Repository。

---

## 二、对象清单

系统里的对象分四族：规则侧（什么不允许）、上下文档（检查谁）、输出侧（查出什么）、组件（怎么算）。

### 族 1：规则侧 —— 描述“什么是不允许的”

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| `Rule` | 模型 | id、version、name、description、scope、severity、enforcement、rule、message、source | 一条机器可执行规则 |
| `RuleScope` | 模型 | language?、layer?、extra_policy | 规则管谁；两个维度都可缺省 |
| `Enforcement` | 模型 | type、checker | 用什么方式执行；Phase 0 只接受 deterministic |
| `ForbiddenDependencyRule` | 模型 | forbidden_dependency | 唯一被禁止的依赖清单 |
| `SourceRef` | 模型 | kind、path?、url?、note? | 规则的本地来源（共享对话不能当来源） |
| `RuleSet` | 模型 | rules、source_paths、identity | 一次加载的规则集合；identity 是整份规则的 sha256 |

### 族 2：上下文档 —— 描述“这次要检查什么”

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| `PolicyContext` | 模型 | request_id、file、layer（必填）、language、module、dependencies、project、agent、operation、task、git_diff、principal、trace_id | 一次检查的输入 |
| `Principal` | 模型 | subject、roles | 请求主体，后续阶段用于鉴权 |
| `Operation` | 枚举 | read / create / edit / delete / execute | 被治理的操作类型 |

### 族 3：输出侧 —— 描述“检查出了什么”

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| `Violation` | 模型 | rule_id、rule_version、severity、message、evidence | 一条违规；一个依赖值一条 |
| `Evidence` | 模型 | kind、subject、value、file?、line?、detail? | 违规的结构化依据 |
| `ValidationResult` | 模型 | decision、request_id、matched_rules、violations、policy_version | 一次判断的完整结果 |
| `Decision` | 枚举 | allow / allow_with_warnings / block | 三种决策；未识别值按协议错误处理 |
| `Severity` | 枚举 | info / warning / error | 违规严重级别，由规则声明 |

### 族 4：组件 —— 提供行为，不持有状态

| 组件 | 位置 | 职责 | 关键函数 |
| --- | --- | --- | --- |
| Loader | `loader.py` | 文件 -> 模型；只读不判断 | load_rule_file、load_rules、load_rule_set、collect_rule_files、assert_unique |
| Engine | `engine.py` | 规则集 + 上下文 -> 结果；只判断不读文件 | evaluate、rule_matches_context、skipped_rule_id、insufficient_context_violation |
| CLI | `check.py` | 路径 -> 上下文、渲染、退出码 | run、build_context、infer_layer、parse_dependencies、exit_code_for |
| 错误类型 | 各模块 | 区分“文件坏”和“上下文坏” | LoaderError / RuleFileError / PolicyContextError / EngineError |

---

## 三、关系

### 3.1 组成关系：一个对象由哪些对象构成

```text
Rule                               PolicyContext                  ValidationResult
|- RuleScope                       |- Principal                    |- Decision            (1)
|  |- language                     |  |- roles                     |- request_id
|  |- layer                        |- Operation            (1)      |- matched_rules
|  |- extra_policy                 |- dependencies                 |- Violation          (0..n)
|- Enforcement            (1)                                         |- rule_id / rule_version
|  |- type                                                             |- Severity        (1)
|  |- checker                                                          |- message
|- ForbiddenDependencyRule                                            |- Evidence        (1)
|  |- forbidden_dependency (1..n)                                        |- kind / subject / value
|- Severity               (1)                                            |- file / line / detail
|- SourceRef              (1)

RuleSet (1) --contains--> Rule (1..n)
```

### 3.2 数据流关系：一条 CLI 命令内部的顺序

```text
1. 文件系统                     2. 模型                 3. 判断                4. 输出

policies/**/*.yaml
   | collect_rule_files（按规范化相对路径排序）
   v
loader.load_rule_set --> RuleSet ------+
                                       +--> engine.evaluate(rule_set, context) --> ValidationResult
examples/bad_controller.py             |         |
   | build_context                      |         |- 范围匹配：rule.scope <-> context.language / layer
   v                                   |         |- 依赖判定：forbidden_dependency <-> context.dependencies
PolicyContext -------------------------+         |- 产生 Violation --> _decide --> Decision
   ^
   |- infer_layer（按文件名推断 layer，推不出就是 unknown）
   |- parse_dependencies（--dependencies -> 规范化 + 排序）
```

### 3.3 派生关系：三个单向推导

| 派生 | 规则 | 代码位置 |
| --- | --- | --- |
| Violation <- Rule + PolicyContext | 只有 scope 命中且依赖落在 forbidden_dependency 才产生 | `engine._violations_for` |
| Decision <- Violation | 无违规 -> allow；有 error -> block；只有 warning -> allow_with_warnings | `models._expected_decision` |
| 退出码 <- Decision | allow -> 0，其余 -> 1 | `check.exit_code_for` |

注意：**异常路径不进 Decision**。规则读不到、规则损坏、未知 checker、路径不合法，直接返回退出码 2，
不产生 Decision 对象——避免“配置错误”被误当成“检查通过”。

### 3.4 依赖方向：谁不许依赖谁

```text
CLI (check.py) --> Loader --> models
      \----------> Engine --> models
```

- Loader 不 import Engine，Engine 不 import Loader：文件读取与规则判断互不知道对方存在；
- 两者只共享 models；
- Engine 不接触文件系统、全局状态、LLM，所以相同输入必然相同输出；
- CLI 是唯一同时接触三者与文件系统的地方。

### 3.5 匹配语义：规则侧与上下文档怎么对上

| ARCH-001 声明 | 要求 | 结果 |
| --- | --- | --- |
| `scope.language: python` | context.language == python | 不满足 -> 跳过该规则 |
| `scope.layer: controller` | context.layer == controller | 不满足 -> 跳过该规则 |
| `rule.forbidden_dependency: [repository]` | context.dependencies 含 repository | 命中 -> 一条 Violation，severity=error -> block |

对应的真相表（也是表驱动测试的内容）：

| layer | dependencies | 决策 |
| --- | --- | --- |
| controller | [`repository`] | BLOCK / ARCH-001@1 |
| controller | [`service`] | ALLOW |
| service | [`repository`] | ALLOW（范围不匹配，规则根本不参与） |
| controller | [`Repository`] | BLOCK（大小写规范化后仍命中） |
| controller | [] | ALLOW |

### 3.6 审计身份的传递链

```text
Rule.id + Rule.version --> Rule.canonical_id = "ARCH-001@1"
        |
        |- 进入 ValidationResult.matched_rules
        \- 进入 Violation.rule_id + rule_version --> 输出里的 ARCH-001@1

RuleSet.identity（sha256）--> 阶段证据的 rule_set_hash
```

含义：规则语义一改必须递增 version，审计里就能区分当时用的是哪一版；
rule_set_hash 是整份规则集的指纹，规则内容改一个字就变。

---

## 四、边界：Phase 0 明确不做的

| 不引入 | 原因 | 何时引入 |
| --- | --- | --- |
| Agent 接入（dsh / MCP / SDK） | 本阶段不接 Agent | Phase 2 / 6 |
| 检索（FTS5 / 向量） | 只需要判断“是否合规”，不需要“该知道什么” | Phase 3 |
| 服务化（FastAPI） | 核心协议未稳定 | Phase 7 |
| 编排（LangGraph） | 编排不是核心依赖 | Phase 8 |
| LLM 判断 | 能确定性验证的规则不许用模型裁决 | 永不作为否决权 |

对应到对象层面，Phase 0 **没有** PolicyEvent、KnowledgeChunk、Retriever、Validator、AuditSink、
ControlledExecutor 这些对象——它们分别在 Phase 2、3、5、4 才出现。

---

## 五、最容易记混的三点

1. `Rule.scope` 与 `PolicyContext` 不是一回事：前者是规则**声明**管谁（写在 YAML 里），
   后者是这次**实际**要检查谁（CLI 或 Adapter 给）。两者取交集才产生判断。
2. `Severity` 属于规则，`Decision` 属于结果：规则自己声明 error/warning；
   Decision 是 Engine 汇总所有违规后**算**出来的，不能由规则直接指定。
3. `Violation` 一条对应一个依赖值：`forbidden_dependency` 里两项且都命中，就产生两条 Violation
   （同一个 rule_id），而不是一条带两个值的违规。

---

## 六、后续阶段按同一约定补充

新增阶段时，在本目录的兄弟目录（`docs/learning/phase-1/` 等）放齐：

```text
note.md / walkthrough.ipynb / walkthrough.py / README.md
```

并更新 `docs/learning/README.md` 的索引表。具体步骤见该文件。
