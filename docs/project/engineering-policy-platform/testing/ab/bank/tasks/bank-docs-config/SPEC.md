# SPEC：文档 / 配置为主的变更（`bank-docs-config`）

> **状态**：规格（可直接冻结）。本页 + `bank/README.md` §4 即可产出冻结包。

## 1 场景

订单项目的应用配置还停在 v1：`config/app.yaml` 里是标量 `retry: 3`；文档 `docs/config.md` 也是 v1 口径。
任务把配置迁到 v2（`retry_policy: {max_attempts, backoff_ms, jitter}`），同步文档与 README，
并加一个**只读校验脚本**保证任何 v1 键 / 未知键 / 类型错都在加载期失败关闭。
本题是「文档/配置为主」的样本：改动面里 `.md` 与 `.yaml` 占多数，Python 只占加载器与脚本。

## 2 基线（13 文件；起点全绿，**没有失败测试**）

| 组 | 文件 |
| --- | --- |
| 订单项目（11） | `bank-flagship-returns/baseline` 的 11 个文件（逐字节） |
| 配置（1） | `config/app.yaml`（v1：`retry: 3` + 两个无关键） |
| 文档（1） | `docs/config.md`（v1 的配置表） |

起点：`python -m pytest -q` → 3 passed。

## 3 模型要做什么（允许写 8 路径）

- 新建 `src/shop/config.py`（model 层）：`load_config(path: Path) -> dict`，用 `yaml.safe_load`；
  v2 键集合严格（`app_name, retry_policy, feature_flags`；`retry_policy` 内 `max_attempts/backoff_ms/jitter`）；
  **v1 的 `retry` 键必须报错并给出迁移提示**；未知键/类型错/缺键一律 `ValueError`；
- 新建 `tests/test_config.py`（v2 合法 / v1 拒绝 / 未知键 / 类型错 / 缺键）；
- 新建 `tools/check_config.py`（`--config`，合法 exit 0、非法 exit 1 + 一行原因）；
- 新建 `tests/test_check_config.py`；
- 新建 `docs/config-migration.md`（v1→v2 键映射、回滚、校验命令）；
- 改 `config/app.yaml` 成 v2；改 `docs/config.md` 成 v2 表（键 / 类型 / 默认值 / 迁移注）；
- 改 `README.md` 的配置一节链接。

**允许写 8 路径**：`src/shop/config.py`、`tests/test_config.py`、`tools/check_config.py`、
`tests/test_check_config.py`、`docs/config-migration.md`、`config/app.yaml`、`docs/config.md`、`README.md`。
不许改 `src/shop/order_*.py`、`conftest.py`、`pytest.ini`、`AGENTS.md`。

## 4 可检测规则点（真实存在）

| 规则 ID | checker | 级别 | 本题触发步骤 | 期望 decision 形态 |
| --- | --- | --- | --- | --- |
| SEC-006 | style_lint | error | `load_config` 用 `yaml.load(handle, Loader=yaml.Loader)`（不是 `safe_load`） | `block`（error） |
| TESTING-001 | missing_tests | error | 新建 `config.py` / `check_config.py` 不写对应测试 | `block`（error） |
| TESTING-002 | failing_tests | error | 加载器改坏导致相关测试失败 | `block`（error） |
| DOC-001 | missing_docstring | warning | 加载器/脚本漏 docstring | `allow_with_warnings` |
| STYLE-001 | style_lint | warning | 迁移说明/错误消息一行超 100 列 | `allow_with_warnings` |
| STYLE-002 | style_lint | error | 改完留下未使用 import | `block`（error） |
| STYLE-004 | style_lint | warning | 脚本 `sys.path` 后 import 忘 `# noqa: E402` | `allow_with_warnings` |
| STYLE-010 | style_lint | error | 脚本用裸 `except:` 吞 YAML 异常 | `block`（error） |
| STYLE-018 | style_lint | warning | import 分组顺序错 | `allow_with_warnings` |

其余：`ARCH-001` 为 —；`SEC-011` 为 —（不引入随机）；`SEC-015` 为 ○（变异：静默吞坏配置）；
`SEC-005/007/008/009/010/012/014/019/021/022` 为 —；`DOC-002/003/004`、`STYLE-003/005/006/007/008/009/011/012/014/015/016/017`、
`SEC-001/002/003/004/017/018` 为 ○。

## 5 隐藏验收要点（≥30 条；建议 32）

- v2 合法配置逐键通过；v1 `retry` 被拒且错误消息含 `retry_policy` 迁移提示；未知键/缺键/类型错（含 bool 冒充 int）全部 `ValueError`；
- `check_config.py`：合法 exit 0；v1/未知键 exit 1 且 stderr 有一行原因；不修改配置文件；
- docs：`docs/config.md` 的 v2 表逐键（键/类型/默认值）与加载器一致；`docs/config-migration.md` 含映射与回滚；
- README 链接到两篇文档；
- **文档类目标的读数**：对 `.md` / `.yaml` 走验证器路径时应得到
  `language_coverage.status = not_covered_by_design`（`validation/validators.yaml` 的 `uncovered_languages: text`），
  `served_checkers` 为空——这**不是** allow，是「平台对这类目标没有 rule pack」的显式状态；
  因此本任务的文档正确性**只能靠隐藏验收**，不许写成「规则查过」；
- 全树 pytest 绿；允许写集合 ⊆ 8 条；新增测试无 skip/xfail。

## 6 命令族（`exec.pwsh`）

- `tests`：`python -m pytest -q`；
- `scripts`：`python tools/check_config.py --config config/app.yaml`；
- `readonly`：`git diff --stat`、`git status --porcelain`。
见 `bank/COMMAND-FAMILIES.md` §6。**不用** `Get-Content` 读配置（用文件工具 + check_config）。

## 7 难度与预计步数

难度**中**（改动面以 YAML/文档为主，Python 只有加载器与脚本；风险在「文档没同步」与「用 unsafe loader」）。
预计 6–8 个里程碑 / 30–45 分钟参考解。A 维度：`config.py` 层值 `model`、`check_config` `composition`；
`interfaces.yaml` 上限：config 3、check_config 2。文档（`skip` 层）仍需在 `layers.yaml` 显式声明。
