# tests/fixtures/invalid_rules/

**故意读不进来的规则夹具**：它们测的是"加载期必须拒绝什么"，不是"判定结果是什么"。

| 目录 | 内容 | 期望 |
| --- | --- | --- |
| `no-language/` | 用 `forbidden_dependency` 但 scope 没有 language 维度 | 加载失败（`RuleFileError`，`field=scope.language`） |
| `wildcard-language/` | 同上，但把 `language` 写成 `*`（显式不限制） | 加载失败（同上） |
| `declared-language/` | 同上，但显式声明 `language: python` | 正常加载 `ARCH-902@1` |

为什么不放进 `tests/fixtures/rules/`：那个目录会被 `tests/integration/test_rule_corpus.py`
逐目录扫描（目录名必须等于规则 id、正反例必须判得出来），放一条**读不进来**的规则在那里
会让语料门禁变红——而它要表达的事实正好相反。

维护：用例在 `tests/unit/test_loader.py`。改动夹具内容前先读那里的断言（错误信息里的
关键字是断言的一部分）。
