# 里程碑顺序（M1–M7；与 `first-message.md` 的「里程碑」一节逐字相同）

M1 先写 `tests/test_config.py`（只覆盖 A1 / A2 里 `src/shop/config.py` 的加载与失败形态，不 import `tools/` 下的任何东西），然后跑一次 `python -m pytest -q`，把结果照原文贴出来（此时 `src/shop/config.py` 还不存在，失败是预期）。
M2 再写 `src/shop/config.py` 的最小实现（`yaml.safe_load` + 严格键集与类型校验 + v1 `retry` 拒绝并给出迁移提示），跑一次 `python -m pytest -q`。
M3 把 `config/app.yaml` 改成 v2（`retry_policy` 的三个子键，取值按接口第 4 条），跑一次 `python -m pytest -q`。
M4 先写 `tests/test_check_config.py`（覆盖 A4 的两种退出码与输出形态），再写 `tools/check_config.py`，跑一次 `python -m pytest -q`。
M5 跑 `python tools/check_config.py --config config/app.yaml`，把 stdout 照原文贴出来（合法配置应退出码 0）。
M6 写 `docs/config-migration.md`（三节：键映射 / 回滚 / 校验），并把 `docs/config.md` 改成 v2 表（键 / 类型 / 默认值 / 迁移注）。
M7 给 `README.md` 加 `## 配置` 一节（链接两篇文档并指出 `config/app.yaml`），最后跑一次 `python -m pytest -q` 与 `python tools/check_config.py --config config/app.yaml`，然后用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与脚本输出。

`M1 → M2 → M3 → M4 → M5 → M6 → M7`；固定顺序、不固定逐条工具调用（05 §5.2）。

## 预期读数（写给 Lead 与读数者，模型看不到本文件）

| 步 | 预期 | 说明 |
| --- | --- | --- |
| M1 的「先写测试」 | 本地 `pytest` 红；**动手前取证**（启用 `pre_evidence` 时）应为 `allow_with_warnings` + `pending_findings`（AGENTS 第 51 条「待实现」），不是 block | 缺失的是**项目内**模块 `shop.config`，不是第三方包 |
| M2 / M4 / M5 / M6 / M7 | 本地 `pytest` 绿；取证应 `allow` | 每步只引入本步的实现或文档 |
| M3 之后 | 若还留着 v1 的 `retry`，`check_config` 必须 exit 1 且 stderr 一行含 `retry_policy` | v1 拒绝是本任务的核心岔口 |
| 任何一步「先写实现」 | `TESTING-001`（missing_tests）error -> block | 生产文件变更必须带同名测试（见 `validation/test-layout.yaml` 的 `production_patterns`） |
| 任何一步打断相关测试 | `TESTING-002`（failing_tests）error -> block | 本题起点没有红测试，一旦红就是自己引入的 |
| M6 / M7 | 文档类目标在验证器路径上得到 `language_coverage.status = not_covered_by_design` 且 `served_checkers` 为空 | `validation/validators.yaml` 的 `uncovered_languages: text`；这**不是** allow，是「平台对这类目标没有 rule pack」的显式状态 |

任务完成判定（A1–A10）用包内 `acceptance.md` + 隐藏用例；A10 用树 diff 对 `allowed-writes.txt`。
