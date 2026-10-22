# 里程碑顺序（M1–M8；与 `first-message.md` 的「里程碑」一节逐字相同）

M1 写 `tools/check_config.py`（`main()` + `--config` 参数 + `__main__` 入口；`import shop.config` 可暂未实现；本步不运行脚本），然后跑一次 `python -m pytest -q`（基线的 `tests/test_check_config.py` 是静态契约测试，会检查工具公开面，应通过）。
M2 先写 `tests/test_config.py`（只覆盖 A1 / A2 里 `src/shop/config.py` 的加载与失败形态，不 import `tools/` 下的任何东西），然后跑一次 `python -m pytest -q`（此时 `src/shop/config.py` 还不存在，失败是预期）。
M3 再写 `src/shop/config.py` 的最小实现（`yaml.safe_load` + 严格键集与类型校验 + v1 `retry` 拒绝并给出迁移提示），跑一次 `python -m pytest -q`。
M4 把 `config/app.yaml` 改成 v2（`retry_policy` 的三个子键，取值按接口第 4 条），跑一次 `python -m pytest -q`。
M5 把基线的 `tests/test_check_config.py`（静态契约测试）改写为行为测试（覆盖 A4 的两种退出码与输出形态：合法 0 / v1 1 / 未知键 1 / 只读），跑一次 `python -m pytest -q`。
M6 跑 `python tools/check_config.py --config config/app.yaml`，把 stdout 照原文贴出来（合法配置应退出码 0）。
M7 写 `docs/config-migration.md`（三节：键映射 / 回滚 / 校验），并把 `docs/config.md` 改成 v2 表（键 / 类型 / 默认值 / 迁移注）。
M8 给 `README.md` 加 `## 配置` 一节（链接两篇文档并指出 `config/app.yaml`），最后跑一次 `python -m pytest -q` 与 `python tools/check_config.py --config config/app.yaml`，然后用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与脚本输出。

`M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8`；固定顺序、不固定逐条工具调用（05 §5.2）。

## 预期读数（写给 Lead 与读数者，模型看不到本文件）

| 步 | 预期 | 说明 |
| --- | --- | --- |
| M1（写 `tools/check_config.py`） | 本地 `pytest` 绿（基线 3 条 + 静态契约测试 1 条 = 4 passed）；**动手前取证是本题的激活点**：批为空时 A 臂（`tools` 非生产文件）选不到测试 → `TESTING-002` block（selection `none`），B 臂（`tools` 是生产文件）选到基线静态契约测试并跑通 → allow | 基线里的 `tests/test_check_config.py` 就是「同名测试」；本步不运行脚本（`shop.config` 还不存在） |
| M2（先写 `tests/test_config.py`） | 本地 `pytest` 红；**动手前取证**（启用 `pre_evidence` 时）应为 `allow_with_warnings` + `pending_findings`（AGENTS 第 51 条「待实现」），不是 block | 缺失的是**项目内**模块 `shop.config`，不是第三方包 |
| M3 / M5 / M8 的 `pytest` 步 | 本地 `pytest` 绿；取证应 `allow` | 每步只引入本步的实现或文档 |
| M4 之后 | `config/app.yaml` 是 v2；`check_config` 仍 exit 0 | v1 拒绝是本任务的核心岔口 |
| M6 | 命令步（不是写判定），不进写序列 | `python tools/check_config.py --config config/app.yaml` |
| M7 / M8 | 文档类目标在验证器路径上得到 `language_coverage.status = not_covered_by_design` 且 `served_checkers` 为空 | `validation/validators.yaml` 的 `uncovered_languages: text`；这**不是** allow，是「平台对这类目标没有 rule pack」的显式状态 |
| 任何一步「先写实现」 | `TESTING-001`（missing_tests）error -> block | 只对 `src/shop/config.py` 成立（`tools/check_config.py` 在基线里已有同名测试）；见 `validation/test-layout.yaml` 的 `production_patterns` |
| 任何一步打断相关测试 | `TESTING-002`（failing_tests）error -> block | 本题起点没有红测试，一旦红就是自己引入的 |

任务完成判定（A1–A10）用包内 `acceptance.md` + 隐藏用例；A10 用树 diff 对 `allowed-writes.txt`。
