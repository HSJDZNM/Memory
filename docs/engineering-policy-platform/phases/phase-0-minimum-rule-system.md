# Phase 0：最小规则系统

## 目标

证明一个程序可以读取机器可执行规则，并对固定上下文稳定地产生 PASS/FAIL。此阶段只实现一条架构规则 `ARCH-001`，不接 Agent、不做 RAG、不启动服务。

## 计划目录

```text
policies/architecture/ARCH-001.yaml
examples/good_controller.py
examples/bad_controller.py
src/policy/models.py
src/policy/loader.py
src/policy/engine.py
src/policy/check.py
tests/unit/test_models.py
tests/unit/test_loader.py
tests/unit/test_engine.py
tests/integration/test_cli.py
```

正式开始此阶段时才创建 Python 依赖清单、锁文件和 CI，并把实际命令写入根 README。

## 开发步骤

### 1. 固定 Rule Schema

先只支持 `id`、`version`、`name`、`description`、`scope`、`severity`、`enforcement`、`rule`、`message` 和 `source`。未知顶层字段默认报错，以便尽早发现拼写错误。

### 2. 定义不可变核心模型

建立 `Rule`、`PolicyContext`、`Violation`、`ValidationResult`。模型负责类型与枚举验证，不负责文件读取或规则匹配。

### 3. 实现 Rule Loader

Loader 完成以下工作：

1. 只读取明确的规则目录；
2. 按规范化相对路径排序；
3. 把 YAML 解析为模型；
4. 拒绝重复 ID、空 ID、未知严重级别和不支持的 enforcement；
5. 错误信息包含文件路径和字段位置；
6. 一次加载要么全部成功，要么不替换当前规则集。

### 4. 实现最小匹配器

`ARCH-001` 只在 `layer=controller` 时生效。当上下文依赖包含 `repository` 时产生 violation；依赖只有 `service` 时通过。匹配器不能读取全局状态或调用 LLM。

### 5. 实现 Engine

`evaluate(context)` 接收模型对象并返回 `ValidationResult`。结果中的 violation 按 `rule_id` 稳定排序，便于测试和审计。

### 6. 实现 CLI

目标接口：

```powershell
python -m policy.check examples/bad_controller.py
python -m policy.check examples/good_controller.py
```

建议退出码：`0=通过`、`1=发现违规`、`2=配置或执行错误`。脚本输出面向人，Engine 结果保持结构化。

### 7. 建立最小 CI

CI 只安装锁定依赖并运行本阶段测试。不要在此时加入服务、数据库、Embedding 或 Agent SDK。

## 实施记录（2026-09，Phase 0 已完成）

本节记录实际落地的接口与命令。原始计划保留在上文，两者的差异在这里说明，避免文档与代码漂移。

### 实际 Rule Schema

```yaml
id: ARCH-001                 # 必填；^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*-\d+$，审计身份为 ARCH-001@1
version: 1                   # 必填；>= 1
name: controller-service-boundary  # 必填；稳定标识符
description: ...             # 必填；人可以读的一句话
scope:
  language: python           # 可选；缺省 = 不限制
  layer: controller          # 可选；缺省 = 不限制
  extra_policy: skip         # 可选；skip 记录并忽略未知 scope 键，reject 直接让加载失败
severity: error              # 必填；info | warning | error
enforcement:
  type: deterministic        # 必填；Phase 0 只接受 deterministic
  checker: forbidden_dependency  # 必填；未知 checker 在 Engine 阶段报错而非放行
rule:
  forbidden_dependency:
    - repository             # 必填；至少一项，去空白 + 小写后比较
message: Controller 必须通过 Service 访问 Repository。  # 必填；输出给人与 Agent 的原因
source:
  kind: project-policy       # 必填；project-policy | standard（共享对话不能作为可执行来源）
  path: policies/architecture/ARCH-001.yaml   # 可选；仓库相对路径
  url: ...                   # 可选；仅参考
  note: ...                  # 可选
```

模型全部 `extra="forbid"` 且 `frozen=True`：未知字段报错，实例创建后不可修改。
`scope` 是唯一例外：未知 scope 键按 `extra_policy` 处理（默认记录并忽略），
这样既支持未来维度（module、operation）平滑加入，也不会因为拼错 `langauge` 而静默失效
——`language` 拼错会让规则范围变宽，因此默认策略只忽略未知键，不做模糊匹配。

### 标识符规范化策略

`canonical_identifier` 只做"去首尾空白 + 小写"。
因此 `Repository` 与 `repository` 等价（表驱动测试第 4 行固定了这个结果），
而 `order_repository` 与 `order-repository` **不**等价：不做分隔符互转，
否则会把合法的包名误判成依赖命中。

### 落地命令

```powershell
uv sync --all-extras
uv run python -m pytest tests/unit -q
uv run python -m pytest tests/integration -q
uv run python -m policy.check examples/bad_controller.py --dependencies repository   # 退出码 1
uv run python -m policy.check examples/good_controller.py --dependencies service     # 退出码 0
uv run python -m policy.check --check-rules                                         # 规则集自检
uv run python tools/phase_evidence.py --out artifacts/phase-0-evidence.json
```

CLI 的依赖来源只有两种：显式 `--dependencies a,b`，或文件的顶层 import 名（仅用于报告）。
判定只使用显式依赖，不做 AST 语义推断，避免"猜测依赖"造成的假阴性与假阳性；
Phase 5 引入 `ast` 验证器后再由确定性证据替换这一输入。

### 计划外的补充（同阶段内，不引入新依赖）

- `--json`：输出对齐 `PolicyDecision` 契约的结构化结果，供后续 Adapter 复用；
- `--check-rules`：只校验规则集，配置损坏时退出码 2；
- 规则集 `identity`：对规则 JSON 取 sha256，作为阶段证据里的 `rule_set_hash`；
- `requirements.in` / `requirements.lock`：本仓库当前环境用 pip 生成的最小锁定；
  有 uv 的环境应改为 `uv lock` 生成带哈希的 `uv.lock`（见根 README 的技术栈表）。

### 环境限制（重放时必须知道）

本阶段实现与测试在 DSH 受限沙箱（workspace-write）内完成，遇到两个与项目无关的平台限制：

1. `uv sync` 无法在该沙箱里探测解释器（uv 查询 Python 时被拒绝访问），
   因此本地用 `python -m pip install -r requirements.in` 验证，CI 仍使用 `uv sync --all-extras`；
2. 沙箱拒绝 `tempfile.mkdtemp`/`chmod`，因此测试不使用 pytest 的 `tmp_path`，
   改用 `tests/conftest.py` 的 `tmp_root` fixture（仓库内 `.tmp/tests/<uuid>/`）。

3. 沙箱拒绝在仓库根目录写 pytest 的缓存文件，pytest 因而在根目录留下 `pytest-cache-files-*/`
   空目录，且沙箱内同样拒绝删除它们（`PermissionError`）。这是环境现象，不是仓库缺陷：
   普通开发机上 `pytest.ini` 已把缓存指向 `.tmp/.pytest_cache`，不会污染仓库根目录。
   这类残留只出现在受限沙箱（普通开发机不会产生），因此不随仓库提供清理脚本——
   按仓库约定，不为一次性环境问题增加工具；在普通 PowerShell 里手工删除即可。

以上都不影响规则、Loader 与 Engine 的行为，在普通开发机上命令与 CI 一致。

### 临时产物约定

会话产生的一切临时文件都写在 `.tmp/`（已在 `.gitignore` 中），包括：

- `.tmp/.pytest_cache/`：pytest 缓存（见 `pytest.ini` 的 `cache_dir`）；
- `.tmp/artifacts/`：阶段验收证据与 JUnit 报告（`tools/phase_evidence.py`）；
- `.tmp/notebook-demo/`：学习手册里故意写坏规则的演示文件。

`python tools/cleanup.py` 一次删除 `.tmp/`、`__pycache__/`、`.pytest_cache/`、`.uv-cache/`。
删除失败的路径会明确报错并以退出码 1 结束，不会假装成功。

### 验收证据

`python tools/phase_evidence.py` 生成的 `artifacts/phase-0-evidence.json` 记录：
实现版本、规则集哈希、每条测试命令、用例数、失败数、JUnit 报告路径与时间戳。
最近一次本地结果：99 个用例通过（单元 75 + 集成 24），0 失败。

## 测试步骤

### 模型测试

- 合法规则可构造；
- 缺失 `id`、非法 severity、未知 enforcement 被拒绝；
- 未知字段被拒绝而不是静默忽略；
- 模型序列化后关键字段不丢失。

### Loader 测试

- 单个合法 YAML 得到 `ARCH-001@1`；
- 空目录得到空规则集；
- 重复 ID、破损 YAML 和错误类型给出包含路径的错误；
- 多文件按路径稳定加载；
- 其中一个文件失败时不会留下半套规则。

### Engine 表驱动测试

| Layer | Dependencies | 预期 |
| --- | --- | --- |
| controller | repository | FAIL / ARCH-001 |
| controller | service | PASS |
| service | repository | PASS，规则范围不匹配 |
| controller | `Repository` | 在规范化策略明确后保持固定结果 |
| controller | 空集合 | PASS |

### CLI 集成测试

- bad fixture 输出规则 ID、原因和期望依赖方向，退出码为 1；
- good fixture 输出通过信息，退出码为 0；
- 规则目录不可读或配置损坏时退出码为 2；
- 相同输入连续运行两次，输出与退出码一致。

## 观察点

记录一条规则从 YAML 到模型、匹配、violation 和 CLI 输出的完整链路。重点理解“文档中的建议”与“可由程序稳定判断的规则”之间的差异。

## 退出条件

- 所有测试在干净环境通过；
- bad/good CLI 示例可由另一位开发者重放；
- 没有引入本阶段禁止的依赖；
- 根 README、锁文件与 CI 命令一致；
- 测试证据符合 [测试策略](../testing/test-strategy.md)。

通过后才能进入 [Phase 1](phase-1-policy-engine.md)。
