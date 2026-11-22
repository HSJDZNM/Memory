# Memory

**Memory 是一个独立于具体 Coding Agent 的软件工程治理层。** 它把工程规范变成机器可执行的规则，对显式上下文稳定地给出 `allow` / `allow_with_warnings` / `block`，并留下「命中了哪些规则、跳过了哪些、依据什么证据」的可重放审计记录。

它不替 Agent 写代码，也不替模型「感觉」对错；它把「什么算合规」变成可执行、可解释、可审计的判定与执行边界。

## 项目介绍

### 它解决什么问题

| 常见问题 | Memory 的做法 |
| --- | --- |
| 规范散在提示词、文档里，靠模型自觉 | 规范变成带版本、作用域、来源的规则数据，可加载、可校验、可哈希 |
| 判定不可解释，出了问题不知道哪条规则 | 每次判定返回命中规则、跳过规则、违规项与证据 |
| 不确定时默认放行 | 未知输入、缺失证据、依赖不可用一律拒绝（fail-closed） |
| 治理只停留在「建议」 | 授权与具体动作绑定，单次使用，执行后必须交证据 |
| 多 Agent 各写一套 | 统一适配协议与能力声明，未审核或已漂移的工具不可用 |
| 服务化后出现第二套判定 | 本地与 API 共用同一条判定路径，决策载荷整份相等 |
| 编排绕过治理 | 编排只做消费者，每次动手都要回到平台拿判定 |

当前内置 **43 条规则、6 类检查器**，覆盖语言、层、模块、操作、Agent 与项目等作用域。

### 五条设计原则

1. **规则是数据，不是提示词。** 规则有 id、版本、作用域、严重级、检查器与来源；改语义必须升版本。
2. **上下文只来自显式声明。** 主体、权限、层、语言、操作都由调用方显式给出；声明不出来就失败关闭。
3. **不确定就拒绝。** 未知版本、未知字段、未知操作、缺失证据一律报错或阻断，绝不默认放行；API 超时或不可达也不等于 allow。
4. **证据先于判定。** 能确定性验证的规则交给 AST / 依赖图 / 外部工具产证据；没有证据的检查器进入「跳过」并写明原因，绝不把「没查」当成「通过」。
5. **授权绑动作，审计可重放。** 授权哈希覆盖工具、参数、主体、权限与上下文，改一个字符旧授权立即失效；审计记录可回放到「为什么」。

### 它不是什么

- **不是沙箱**：白名单与规则不是进程或文件系统隔离。
- **不是 LLM 裁判**：确定性失败不能靠模型解释覆盖。
- **不是「文档自动变规则」**：文档先只读、可检索，转成规则是一次显式、可评审的提炼。
- **不是防篡改日志**：审计链是摘要链，删尾或整链重写发现不了，需要外部锚定或签名。

## 测试结果

### 治理效果：bank k≥3 pilot（n=3，只作描述）

2026 年 10 月，3 题 × 3 臂 × 3 block = 27 次运行，单一模型身份、单一宿主、headless。

| 任务 | A（旧口径） | B（新口径） | C（不治理对照） |
| --- | --- | --- | --- |
| crossmodule 重构（负对照） | 33/33 ×3 | 33/33 ×3 | 33/33 ×3 |
| async 并发 | 14/38、30/38、31/38 | 38/38 ×3 | 38/38 ×3 |
| docs 配置迁移 | 28/39 ×3 | 36/39 ×3 | 39/39 ×3 |

- **27/27 正常运行结束**（exit 0、无超时、无非法记录）；**21 份完整 run-record + 6 份 T-only**。
- **方向计数 3/3**：async 上 A<B；docs 上 A<B 且 B<C；crossmodule 三臂同值（负对照按构造不应有差异）。
- **守卫读数**：21 份完整记录、144 个文件检查；对照组 134 次 `allow` + 10 次 `allow_with_warnings`、0 次 `block`；69 条 `DOC-001@1` 警告（7 run / 10 文件）。
- **防作弊抽样（H2）**：抽 6/10 个测试路径、51 个版本；0 skip/xfail、0 空测试、0 `assert True`；但抽样不盲、只覆盖 60%。
- **独立验收审计**：A1–A12 全部 pass、0 处数字不一致，结论 **pass-with-open-items**。

**怎么读这些数（重要）**

- 这是 pilot 的**描述性读数**，不是效应结论：n=3、单模型、单宿主；**不能**写成「有效 / 显著 / 提升 / 优于」，不能算均值或百分比，也不能外推。
- 6 份 T-only 只作 T 原值来源，不能与 21 份完整记录混读成对照。
- docs 的 B/C 差（36 对 39）只记录为「B 的最终配置未迁移、C 已迁移」，不归因于某条规则。
- H2 的「未发现削弱」只代表 6/10 个路径的静态核对；非盲、未跑测试、无变异自证。

逐 run 证据与开放项见 `docs/project/engineering-policy-platform/readings/`。

### 测试覆盖

- **3430 个测试用例**：单元 2054 / 契约 505 / 集成 754 / 对抗 117。
- 本机全量：**3424 passed、6 skipped**（跳过项均为 Windows 环境限制）。
- 四层范围：单元（模型、范围、聚合、分块、AST、API DTO、编排状态）、契约（决策协议快照、适配映射、检索端口、执行协议、验证器证据、API 传输、引擎等价）、集成（真实 CLI、dsh Hook、检索索引、受控执行、验证器流水线、HTTP API、编排恢复）、对抗（注入、越权、失败关闭、伪造审批、跨租户、平台不可达绝不返回 allow）。

## 使用说明

### 环境要求

Python ≥ 3.11。以下命令均已在本仓库实际执行验证。

### 安装

依赖锁定以 `requirements.lock` 为准，推荐用 [uv](https://docs.astral.sh/uv/)：

```powershell
uv venv
uv pip install -r requirements.lock
```

没有 uv 时，用现有解释器从同一份锁文件安装：

```powershell
python -m pip install -r requirements.lock
```

核心依赖只有 pydantic 与 PyYAML；HTTP 服务与编排按需追加：

```powershell
pip install .                  # 治理核心
pip install ".[api]"           # 再加 HTTP 服务
pip install ".[orchestration]" # 再加编排层
```

### 运行规则检查

```powershell
# 反例：Controller 直接依赖 Repository，退出码 1
uv run python -m policy.check examples/bad_controller.py --layer controller

# 正例：Controller 只依赖 Service，退出码 0
uv run python -m policy.check examples/good_controller.py --layer controller

# 范围不匹配：layer=service 时 ARCH-001 不参与判断，输出会列出跳过原因，退出码 0
uv run python -m policy.check examples/good_controller.py --layer service

# 只校验规则集本身（配置损坏时退出码 2）
uv run python -m policy.check --check-rules
```

退出码：`0` 通过（allow）、`1` 发现违规（block / allow_with_warnings）、`2` 配置或执行错误。加 `--json` 可输出机器可读的决策载荷。

未使用 uv 时，先让解释器找到 `src/`：

```powershell
$env:PYTHONPATH = "src"
python -m policy.check examples/bad_controller.py --dependencies repository
```

### 运行测试

```powershell
uv run python -m pytest tests/unit -q
uv run python -m pytest tests/contract -q
uv run python -m pytest tests/integration -q
uv run python -m pytest tests/security -q

# 全量
uv run python -m pytest -q
```
