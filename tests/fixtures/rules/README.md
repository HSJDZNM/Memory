# 规则语料夹具：每条规则的正反例

这里放的是「由镜像文档提炼的规则」的可判定语料，唯一消费者是
`tests/integration/test_rule_corpus.py`。它只回答一个问题：**这条规则到底判不判得出来？**

## 契约

| 项 | 约定 |
| --- | --- |
| 目录名 | 必须等于规则 id（`policies/<domain>/<ID>.yaml` 里的 `id`，大小写一致），例如 `tests/fixtures/rules/STYLE-003/` |
| `bad.py` | 必须触发本条规则：该规则出现在 `violations` 里，且不是被「关键验证器不可用 / 没有验证器」顶掉的 |
| `good.py` | 必须不触发本条规则：不在 `violations` 里，也不在 `skipped_rules` 里（被 skip 说明范围压根没命中） |
| 必须齐全 | `source.kind == "standard"`（由镜像文档提炼）的规则必须两个文件都有，缺一个就 FAIL；`project-policy`（项目自订）不强制，但一旦有夹具就会被同样判定 |
| 必须能解析 | 两个文件都要是合法 Python：语法错误会让 `py.ast` 失败关闭，需要 docstring 证据的规则会被 critical 顶掉 |
| 只约束自己 | `good.py` 里出现**别的**规则违规是允许的，`bad.py` 同理；测试只断言本条规则 |
| 建议最小化 | `bad.py` 尽量只触发本条规则：文件里其他 error / critical 级违规会把整体决策抬成 `block`（允许，但「恰好 allow_with_warnings」只在没有其他阻断项时才检查） |
| 不要 noqa | `# noqa` 会让 Ruff 不再报诊断，规则就永远判不出来——测试会以「bad.py 没有命中」失败 |

本目录里的 `README.md` 不是夹具：目录里既没有 `good.py` 也没有 `bad.py` 时，它不参与任何断言。

## 判定口径：真实证据，不 mock

夹具走的是与 CLI、Hook 完全相同的判定链路：

1. `validators.pipeline.run_pipeline` 按**命中的规则**选验证器（内置 `py.source` /
   `py.ast` / `py.docstring` 与外部 `tool.ruff`），Ruff 是**真的子进程调用**：不 mock、
   不伪造证据、不跳过真实调用；
2. 上下文固定为 `layer="fixture"`、`language="python"`、**不声明 `operation`**；
   工作区 = 仓库根，目标 = 夹具的仓库相对路径（正斜杠）；
3. 证据包交给唯一判定入口 `policy.engine.evaluate`：`error` / `critical` → `block`，
   `info` / `warning` → `allow_with_warnings`。

所以夹具的 `layer` 只有 `fixture`：规则的 `scope` 里如果写了别的 `layer`（或要求
`operation`），它在这条语料里根本不会命中——测试会以「scope 没有命中夹具上下文」失败。
这是刻意的：那说明这条规则的正反例需要另一种调用方式，而不是测试该放宽断言。

「诊断码 → 规则」的归属是数据，改证据口径要同时改两处：`validation/ruff.toml` 的
`select`（工具会报哪些码）与规则文件里的 `rule.style_lint.codes`（这个码归哪条规则）。
没有归属的诊断只计入报告的 `unmapped_findings`，不参与判定。

本机没有可用的 Ruff 时，语料用例 `pytest.skip`（写明原因），绝不伪装成通过。

## 本地复跑

```powershell
# 全量语料（每条规则两个文件，真的跑两次流水线）
python -m pytest tests/integration/test_rule_corpus.py -q

# 只跑一条规则的反例 / 正例
python -m pytest "tests/integration/test_rule_corpus.py::test_counterexample_hits_its_rule[STYLE-003]" -q
python -m pytest "tests/integration/test_rule_corpus.py::test_positive_example_passes_its_rule[STYLE-003]" -q

# 用 CLI 看同一份判定（--json 里有完整证据、blockers 与决策）
$env:PYTHONPATH = "src"
python -m policy.check tests/fixtures/rules/STYLE-003/bad.py --layer fixture --json
python -m policy.check tests/fixtures/rules/STYLE-003/good.py --layer fixture
```

CLI 退出码：`0` = allow，`1` = 有违规（`allow_with_warnings` 也算，它需要人看一眼），
`2` = 配置 / 规则集错误。`--json` 里 `result.violations[].rule_id` 是裸 id，
`matched_rules` 与 `skipped_rules[].rule_id` 是审计身份 `ID@版本`，两者不是一回事。

## 常见失败与处理

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 覆盖率门禁列出 `tests/fixtures/rules/<ID>/good.py` | 新规则没有夹具 | 按上面的契约补齐正反例 |
| 「bad.py 没有命中 <ID>」 | 反例没有触发该规则的诊断码 | 看失败信息里的 `violations（全部）` 与 `served_checkers`：是证据没产生，还是码没归属 |
| 「<ID> 的反例被判成失败关闭」 | 夹具不是合法 Python，或验证器不可用 | 修夹具；失败信息里的 `blockers` 写着哪个验证器、什么原因 |
| 「<ID> 的 scope 没有命中夹具上下文」 | 规则 scope 写了别的 `layer` 或要求 `operation` | 这类规则需要另一种调用方式，不是语料夹具能覆盖的 |
| 「目录名不是当前规则集里的规则 id」 | 目录名拼错 / 规则被删 / 大小写不一致 | 改名或删除目录 |
| 用例被 skip | 本机没有可用的 Ruff | 装上 Ruff（`>=0.6,<1`）再跑，不要把它改成"通过" |

## 敏感数据

**没有**。夹具里不得出现真实凭据、用户数据或生产日志；需要「像密钥」的字面量时用合成值，
并在行内注明它是合成值。
