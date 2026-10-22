# 隐藏验收 PLAN（bank-docs-config）

> **它是什么**：本题隐藏验收的**冻结清单**——39 条用例（T01–T26 / EN1–EN7 / I1–I6；I7 已按 2026-10-22 H1 改判删除），
> 每条写清「断言要点」与「反向构造（什么形态会让这条红）」。`hidden/runner.py` 逐条实现本清单；
> 两者同批落盘，id 集合必须逐个相等（`runner.py` 的 `CASE_IDS` 是本文件的机读副本）。
> **不参与判分的东西**：参考解实现、过程账本、会话读数；T 只读最终树。
> **本文件不写的**：任何「待定」——每条的判据都在下面写死；写不出的面干脆不列（见 §5）。

## 0 契约（与 `bank/README.md` §4.3、旗舰 `hidden/` 同形）

- 被评树只从环境变量 **`BANK_TASK_TREE`** 读入（相对路径按调用 cwd 解析）；**一个字节都不写**：
  pytest / 脚本 / 模块导入全在树的副本里跑（临时目录，退出即删）；
- stdout 唯一载荷（UTF-8）：
  `{"schema_version": "1.0", "tree": "<相对标签>", "cases": [{"id", "pass", "detail"}], "summary": {"passed", "total"}}`；
  **无时戳 / run id / 绝对路径**；`cases` 顺序固定 `T01..T26, EN1..EN7, I1..I6`；
  同一 cwd + 同一棵树两次运行**逐字节相同**；
- 退出码：**全过 0 / 有失败 1 / 跑不成 2**。2 = 「判不了」（缺 `BANK_TASK_TREE`、树不存在、
  用例集合不完整、树复制失败、PyYAML 不可用），**不是 0 分**；
- 每条用例独立 try/except：一条异常只让该条 fail，`detail` = 异常类型 + 脱敏短消息；
- 子进程超时 60 秒；解释器 = 运行 runner 的 `sys.executable`；子进程环境
  `PYTHONDONTWRITEBYTECODE=1`，不继承 `PYTHONPATH` / `PYTEST_ADDOPTS`；
- **反向用例**（断言「期望失败 / 期望拒绝」，不是「跑成 = 通过」）：
  T04–T18 的全部拒绝面、T21、T25、T26、EN4、EN5、EN6、EN7、I5。

**组的口径**：`T` = 任务内容（加载器语义 / 配置 / 文档 / README / 树形状）；
`EN` = 入口（pytest 与校验脚本的命令级行为）；`I` = 接口契约（签名 / AST / 只读 / 分层）。

## 1 T 组（26 条；加载器、配置、文档、README、树形状）

| id | 断言要点 | 反向构造（这条红的方式） |
| --- | --- | --- |
| T01 | `load_config` 对 v2 合法配置返回 **dict**，顶层键集合恰为 `{app_name, retry_policy, feature_flags}`，`retry_policy` 是 dict 且键集合恰为 `{max_attempts, backoff_ms, jitter}`；取值逐键 `demo-shop / 3 / 100 / true / [checkout, search]`；类型严格（两个毫秒/次数键是 int 且**不是 bool**，`jitter` 是 bool，flags 是 list[str]） | 把 `max_attempts` 写成 `true`；直接返回 `yaml.safe_load` 的原始 dict（嵌套未规范化）；返回缺键/多键的 dict |
| T02 | 边界合法值通过：`max_attempts: 1`、`backoff_ms: 0`、`jitter: false`、`feature_flags: []`；带 `#` 注释与行内注释的 YAML 也能读（证明不是 `json.loads`） | 用 `json.loads` 解析（注释 / 无引号键过不去）；把 `backoff_ms >= 0` 写成 `> 0`；把空 `feature_flags` 判非法 |
| T03 | 副本语义：同一文件两次调用结果相等但**不是同一对象**（顶层 dict 与 `retry_policy` 都是新对象）；修改返回值后再次调用仍是原值 | 返回模块级缓存对象（两次是同一对象）；把 yaml 原始 dict 直接返回（嵌套层被共享） |
| T04 | v1 的 `retry: 3`（无 `retry_policy`）→ **ValueError**，且 `str(exc)` 含子串 `retry_policy` | 接受 `retry` 并静默忽略（不抛）；抛 `KeyError` / `TypeError`；消息只说「未知键」不含迁移目标名 |
| T05 | `retry: 3` 与完整 `retry_policy` **并存** → ValueError | 只校验「`retry_policy` 在就通过」，不拒多余顶层键 |
| T06 | 未知顶层键 `timeout: 5` → ValueError | 只判必需键齐全（`all(k in data)`），不判键集合相等 |
| T07 | 缺顶层键（缺 `feature_flags` / 缺 `app_name`）→ ValueError | 用 `data.get()` 给默认值 / 只判 `retry` |
| T08 | `retry_policy` 内未知键 `max_retries: 3` → ValueError | 只判三个必需子键存在，不判子键集合相等 |
| T09 | `retry_policy` 内缺键（缺 `backoff_ms` / 缺 `jitter`）→ ValueError | 用 `.get("jitter", False)` 补默认 |
| T10 | `app_name: 3` 与 `app_name: ""` → ValueError | 用 `str(v)` 转换（int → `"3"`）；只判 `isinstance(str)` 不判非空 |
| T11 | `max_attempts` 的四种错法全部 ValueError：`true`（bool 冒充 int）、`0`、`-1`、`"3"` | `isinstance(v, int)` 接受 `True`（bool 是 int 子类）；不判 `>= 1`；用 `int(v)` 转换 |
| T12 | `backoff_ms` = `-1` / `"100"` / `true`；`jitter` = `1` / `"true"` / `0` → 全部 ValueError | `jitter` 用真值判断（`if not jitter`），1/0 被当成合法；`backoff_ms` 用 `int()` 转换；不判 `>= 0` |
| T13 | `feature_flags` 四种错法：字符串 `"checkout"`、元素为 int、元素为 `""`、值为 `null` → ValueError | 不判 `isinstance(v, list)`（字符串可迭代 → 逐字符都是非空 str → 通过）；不判元素非空 |
| T14 | 顶层不是映射：YAML 列表、标量字符串、**空文件**（`safe_load` → `None`）→ ValueError | 用 `dict(data)` 转换（list 抛 TypeError 而非 ValueError）；`data or {}` 把空文件当空配置 |
| T15 | YAML 语法错误 → ValueError（不是 `yaml.YAMLError` 漏出） | 不捕 `yaml.YAMLError`（它是 `YAMLError`，不是 `ValueError` 子类） |
| T16 | 文件不存在 / 路径是目录 → ValueError | 让 `OSError` / `IsADirectoryError` 直接漏出 |
| T17 | 错误消息不含绝对路径：对 **7 类**失败（v1 `retry` / 未知顶层键 / 缺顶层键 / `app_name` 为空 / `max_attempts: true` / `feature_flags` 是字符串 / 文件不存在），`str(exc)` 不含传入路径的父目录、不匹配盘符绝对路径、不含传入路径本身（正反斜杠两种形态） | 把 `path` 直接拼进**任意一条**消息（而不是 `path.name`）——每条消息单独检查，只改一条也会红 |
| T18 | 加载器 AST：至少 1 处 `yaml.safe_load`（或 `from yaml import safe_load` 后的调用）；无 `yaml.load` / `yaml.full_load` / `yaml.unsafe_load` / `Loader=` 关键字；无 `eval` / `exec` / `compile` / `__import__` / `importlib.import_module` | `yaml.load(f, Loader=yaml.Loader)`（SEC-006 的真实错法）；`eval(text)` 解析配置；`importlib.import_module("shop.config")` |
| T19 | 树里的 `config/app.yaml` 已是 v2：`safe_load` 后键集与取值逐键等于冻结值（`demo-shop` / 3 / 100 / true / `[checkout, search]`），无顶层 `retry`；且 `load_config` 读同一文件返回相等结构、类型严格 | 仍留 `retry: 3`；取值改成 5 / 200 / false；只改键名不改取值；加载器拒绝这棵树自己的配置 |
| T20 | `docs/config.md` 的 `## 配置键（v2）` 段内表格：表头四列依次 键 / 类型 / 默认值 / 迁移注；**恰 5 行**数据，键列依次 `app_name`、`retry_policy.max_attempts`、`retry_policy.backoff_ms`、`retry_policy.jitter`、`feature_flags`；类型列依次 `str`、`int (>= 1)`、`int (>= 0)`、`bool`、`list[str]`；默认值列 5/5 为 `无默认（必填）`；迁移注列非空且 `max_attempts` 行含 `retry`（单元格口径：去首尾空白与反引号后逐字比） | 留 v1 三行表；类型列只写 `int` 不写 `int (>= 1)`；表格放在别的标题下或没有该标题；多一行 `retry` |
| T21 | `docs/config.md` 的 v1 口径已替换：没有 `## 配置键（v1）` 标题；任何表格的数据行里第一个单元格（去反引号后）不等于 `retry` | 只加 v2 表、v1 表原样留着；或只改标题不改表 |
| T22 | `docs/config-migration.md`：`## 键映射` / `## 回滚` / `## 校验` 各恰 1 次、按此顺序、每节至少一行非空正文（非标题）；键映射节含 `retry`、`retry_policy.max_attempts`、`retry_policy.backoff_ms`、`retry_policy.jitter`；回滚节含 `retry_policy`、`retry`、`config/app.yaml`；校验节含完整命令 `python tools/check_config.py --config config/app.yaml` | 文件缺失；只有键映射一节；命令写成 `python -m tools.check_config`；回滚节只写「改回去」不点路径 |
| T23 | `README.md` 恰有一个 `## 配置` 标题；四个二级标题的位置严格递增：`## 结构` < `## 跑测试` < `## 配置` < `## 这份项目为什么长这样`（各恰 1 次）；`## 配置` 节正文同时含 `docs/config.md`、`docs/config-migration.md`、`config/app.yaml` | 配置节插到文末或插在 `## 结构` 前；只链一篇文档；不点配置文件路径 |
| T24 | `README.md` 去掉 `## 配置` 整节（标题行到下一个二级标题前）后，与**基线 README** 逐行相同（行尾空白去掉、连续空行压成一个、去首尾空行） | 顺手改写「这份项目为什么长这样」的一句；删掉 `## 跑测试` 的代码块；把配置节写成覆盖原小节 |
| T25 | 最终树文件集合恰为 **18** 条 = 14 基线 ∪ 8 允许写（= 14 基线 + 4 新建；`tests/test_check_config.py` 属于基线一侧；忽略 `.policy`、隐藏段、`__pycache__`、`*.pyc`）；缺任一允许写、或出现任何额外路径都 fail | 图省事新增 `tools/__init__.py`；留下 `docs/config-v2.md` 草稿；漏写 `docs/config-migration.md` |
| T26 | 10 个冻结基线文件逐字节不变（`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`order_controller.py`、`order_repository.py`、`order_service.py`、`tests/test_order_*.py`）：sha256 与内嵌基线逐条相等 | 给 `order_service.py` 加一行注释；改 `pytest.ini` 的 `testpaths`；顺手「整理」`__init__.py` |

## 2 EN 组（7 条；入口命令级行为）

| id | 断言要点 | 反向构造（这条红的方式） |
| --- | --- | --- |
| EN1 | 在树副本根跑 `python -m pytest -q`：退出码 **0**；末行匹配 `\d+ passed` 且匹配不到 `\d+ (failed\|error)`；输出里没有 `ERROR` 行 | 参考树里留一条红测试；新增测试 import 失败（收集期错误）；`conftest.py` 被改坏 |
| EN2 | `python -m pytest --collect-only -q`：退出码 0，解析出 `N tests collected`，**N >= 10** | 两个新测试文件一共只写 2 个 test 函数；把用例塞进一个函数 |
| EN3 | `python tools/check_config.py --config config/app.yaml`（cwd = 树副本根）：退出码 0；**stdout 恰一行**非空文本；stderr 无非空行 | 脚本合法时也打两行；没插 `sys.path` 导致 import 失败；合法配置被判非法 |
| EN4 | 同一脚本对 v1 配置（临时文件，绝对路径传入）：退出码 **1**；stderr **恰一行**且含 `retry_policy`；stdout 无输出；stderr 不含盘符绝对路径 | `traceback.print_exc()`（多行）；吞异常后 exit 0；错误消息拼了完整路径 |
| EN5 | 未知键配置、文件不存在：各退出码 1、stderr 恰一行 | 未捕 `ValueError`（traceback 多行）；文件不存在时 exit 0 |
| EN6 | 只读：对树内 `config/app.yaml` 与一个临时 v1 文件，运行前后 sha256 相同 | 脚本解析后回写（顺手格式化）；把配置「规范化」后覆盖 |
| EN7 | 缺 `--config`：`python tools/check_config.py` 退出码 **2**（argparse 用法错）、stderr 非空 | 把 `--config` 写成可选 + 默认路径（退出码 0/1）；自己 `sys.exit(1)` 代替用法错 |

## 3 I 组（6 条；接口契约；I7 已按 2026-10-22 H1 改判删除）

| id | 断言要点 | 反向构造（这条红的方式） |
| --- | --- | --- |
| I1 | `shop.config.load_config` 是函数：签名恰一个必填位置参数、名字 `path`，无默认值、无 `*args/**kwargs` | `def load_config(path, strict=True)`；参数名写成 `p`；写成类方法 |
| I2 | UTF-8 与非 ASCII：`app_name: 演示店`、`feature_flags: [结算]` 能原样读出；读前后文件字节不变 | 用 `open(path)` 依赖宿主默认编码（中文乱码 / UnicodeDecodeError）；读后回写 |
| I3 | `tools.check_config.main` 是函数，一个参数 `argv` 默认 `None`；`main(["--config", <合法>]) == 0`、`main(["--config", <v1>]) == 1`（返回 int）；AST 有 `if __name__ == "__main__":` 且体内 `SystemExit(main())` 或 `sys.exit(main())` | `def main():` 无参数；`main` 返回 `None` 只靠 `sys.exit` 副作用；缺 `__main__` 守卫 |
| I4 | 脚本走 `shop.config.load_config`：AST 有 `import shop.config` 或 `from shop.config import ...`；有对 `load_config(...)` 的调用；有对 `sys.path.insert/append` 的调用；源码里没有字符串常量恰为 `max_attempts` / `backoff_ms` / `jitter`（键集合没被重写） | 脚本自己写 `EXPECTED = {"max_attempts", ...}` 重写键集合；只 import 不用；不插 `sys.path` 靠环境碰运气 |
| I5 | `tests/test_config.py` 至少 5 个 `test_*` 函数、`tests/test_check_config.py`（M5 改写后的行为测试，不是基线的静态契约测试）至少 2 个；各至少 1 条 `assert`；AST 无 `skip` / `skipif` / `xfail` / `importorskip`（基线的静态契约测试不在最终树里）；`tests/test_config.py` 不 import 任何 `tools` 模块 | 五个 case 塞进一个 test 函数；`@pytest.mark.skip`；test_config.py 顺手 import `tools.check_config` |
| I6 | docstring：`src/shop/config.py` 模块与 `load_config` 都有非空 docstring；`tools/check_config.py` 模块与 `main` 都有非空 docstring | 删 docstring（DOC-001 的真实错法）；docstring 写成空串 |

## 4 计数与映射（39 条）

| 组 | 条目 | 数 | A 验收表对应 |
| --- | --- | --- | --- |
| T | T01–T26 | 26 | A1 / A2 / A3 / A6 / A7 / A8 / A10 |
| EN | EN1–EN7 | 7 | A3 / A4 / A9 |
| I | I1–I6 | 6 | A1 / A4 / A5 / A9 |
| **合计** | `T01..T26, EN1..EN7, I1..I6` | **39** | `scoring.yaml` 的 `dimension_t.total = 39`、`case_ids` 与本表逐个相等；I7 已按 H1 改判删除 |

`scoring.yaml` 里的 `planned_min_total = 30` 是**下限**；本 PLAN 落在 34–40 的建议区间内（39）。

## 5 已知边界（不写进断言的面，以及为什么）

- **不做**「文档类目标的验证器读数」：`.md` / `.yaml` 在验证器路径上是
  `language_coverage.status = not_covered_by_design`、`served_checkers = []`（AGENTS 第 47 条）。
  它不是 allow，也不该由隐藏用例断言成「规则查过」——那条读数由 C / 过程账本读，不在这里。
- **不断言** `# noqa: E402`：题面的代码约定不构成判据（`README.md` §6 已把 STYLE-004 记成实测负例）。
- **不断言**注释文字、文档章节以外的措辞、测试函数名、`main` 的打印文案（只判行数与内容子串）。
- **不跑** `policy.check` / `structure_metrics`：T 只判「题做完了没有」；C / A 是另外两维。
- **不判** `config/app.yaml` 的注释是否更新（接口只要求「注释可以更新」，不是判据）。
- **不判**测试是否覆盖「bool 冒充 int」之外的每个类型错——测试质量由 C 的 `failing_tests` 与 I5 的形态判据共同兜底，
  隐藏用例不去猜测试函数个数以外的内容。

## 6 作者独立性

本文件与 `runner.py` 由**未参与本题实施**的子会话写成：只读了本题的 `SPEC.md`、`README.md`、
`coverage.md`、`layers.yaml`、`interfaces.yaml`、`scoring.yaml`、`task-package/`、`baseline/`、
`bank/README.md` §4/§5 与旗舰题的 `hidden/README.md`（runner 契约部分）；
**没有读** `readings/**`、没有读任何 `reference/` 实现（本题没有参考解）、没有读其它题的 hidden 用例。
先写 PLAN，后写 runner；参考解在本清单落盘之后才写。
