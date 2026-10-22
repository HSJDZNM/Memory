# 验收表（bank-docs-config）

> 判定方式三档：**隐藏用例**（另一子会话按隐藏 PLAN 实现，最终树只读）、
> **树执行**（在最终树的副本里跑命令，只看退出码 / 输出 / 字节）、**树 diff**（最终树 vs 14 文件基线）。
> 本表与 `first-message.md` 的「验收表」逐字对应（A1–A10 的措辞同源）；改一处必须改另一处。

| id | 检查 | 判定方式 |
| --- | --- | --- |
| A1 | `load_config` 对 v2 合法配置逐键返回（`app_name`、`retry_policy.max_attempts`、`retry_policy.backoff_ms`、`retry_policy.jitter`、`feature_flags`），类型与值域严格（`max_attempts` 是 int 且 >= 1、`backoff_ms` 是 int 且 >= 0、`jitter` 是 bool、`feature_flags` 是非空 str 列表） | 隐藏用例 |
| A2 | `load_config` 失败关闭：v1 的 `retry`、未知键、缺键、类型错（含用 `true` 冒充 int）、YAML 语法错误一律 `ValueError`；v1 `retry` 的消息含 `retry_policy`；任何错误消息不含绝对路径 | 隐藏用例 |
| A3 | `config/app.yaml` 已是 v2（三个顶层键 + `retry_policy` 三个子键，没有顶层 `retry`），`load_config` 能读它，且 `python tools/check_config.py --config config/app.yaml` 退出码 0 | 树执行 |
| A4 | `check_config.py` 的行为：合法退出码 0 且 stdout 恰一行；v1 / 未知键退出码 1 且 stderr 恰一行（v1 那行含 `retry_policy`）；运行前后被校验文件字节不变 | 树执行 + 隐藏用例 |
| A5 | `check_config.py` 通过 `shop.config.load_config` 做校验（AST 里能证明它被导入并被调用），没有在脚本里重写键集合 | 隐藏用例（AST） |
| A6 | `docs/config.md` 的 v2 表逐键与加载器一致：`## 配置键（v2）` 段内的表头四列依次为 键、类型、默认值、迁移注，5 行的键列依次是 `app_name`、`retry_policy.max_attempts`、`retry_policy.backoff_ms`、`retry_policy.jitter`、`feature_flags`，类型列依次是 `str`、`int (>= 1)`、`int (>= 0)`、`bool`、`list[str]`，默认值列 5/5 为 `无默认（必填）`，迁移注列非空且 `retry_policy.max_attempts` 那行含 `retry` | 隐藏用例 |
| A7 | `docs/config-migration.md` 含三个二级标题 `## 键映射`、`## 回滚`、`## 校验`，每节都有非空正文；键映射节含 `retry`、`retry_policy.max_attempts`、`retry_policy.backoff_ms`、`retry_policy.jitter`；回滚节含 `retry_policy`、`retry` 与 `config/app.yaml`；校验节含完整命令 `python tools/check_config.py --config config/app.yaml` | 隐藏用例 |
| A8 | `README.md` 新增 `## 配置` 一节并链接 `docs/config.md` 与 `docs/config-migration.md`、指出 `config/app.yaml`；原有三个二级标题 `## 结构`、`## 跑测试`、`## 这份项目为什么长这样` 逐字保留 | 隐藏用例 |
| A9 | 项目根 `python -m pytest -q` 全绿；`--collect-only -q` 收集数 >= 10；新增 / 修改的测试没有 `skip` / `skipif` / `xfail`，每个新测试文件至少一条 assert | 树执行 |
| A10 | 改动文件集合属于 `task-package/allowed-writes.txt` 的 8 条；基线 14 文件里不属于允许写的 10 个逐字节不变（`tests/test_check_config.py` 在允许写集合里，M5 会改写它） | 树 diff |

## 补充口径（判据细节，与前表不冲突）

- **A6 的单元格比较口径**：去掉首尾空白与包裹的反引号后逐字比较；表格必须在 `## 配置键（v2）` 这一节内，5 行数据行的顺序即表里列出的顺序。
- **A7 的「非空正文」**：二级标题之后至少一行非空白、且不是另一个标题。
- **A9 的收集数**：基线 3 条 + `tests/test_config.py` 至少 5 条 + `tests/test_check_config.py` 至少 2 条 = 10；用参数化写更多不扣分。
- **A10 的基线一侧**：14 个基线文件里，允许写集合占 4 个（`README.md`、`config/app.yaml`、`docs/config.md`、`tests/test_check_config.py`），其余 10 个逐字节不变才满分。
- **基线静态契约测试**：`tests/test_check_config.py` 在基线里是静态契约测试（工具文件不存在时 skip）；A9 的「不许 skip / xfail」判的是最终树——M5 改写后的行为测试不许 skip / xfail。
- **文档类目标的读数（不在 A 表里）**：对 `.md` / `.yaml` 走验证器路径时应得到
  `language_coverage.status = not_covered_by_design`（`validation/validators.yaml` 的 `uncovered_languages: text`）、
  `served_checkers` 为空——这**不是** allow。本任务的文档正确性只能靠隐藏验收与 A6–A8 的结构判据，
  不许在读数里写成「规则查过」。
