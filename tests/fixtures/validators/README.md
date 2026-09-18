# Phase 5 验证器夹具

这些文件只服务 `tests/` 与 `tools/validator_loop.py`，不属于运行时代码，也不被仓库自己的
pytest 收集（`tests/conftest.py` 里的 `collect_ignore_glob` 只屏蔽收集：夹具项目内部的
`tests/` 在"测试验证器"运行时必须能被真的收集到）。

## project/：最小受控项目（工作区）

| 文件 | 用途 | 预期结果 | 关联规则 |
| --- | --- | --- | --- |
| `src/shop/order_controller.py` | Controller 只依赖 Service | 依赖解析成 `service`，allow | ARCH-001 |
| `src/shop/order_controller_bad.py` | Controller 直接依赖 Repository | 依赖解析成 `repository`（第 3 行），block | ARCH-001 |
| `src/shop/order_service.py` / `order_repository.py` | 依赖目标 | 分别解析成 service / repository 组件 | —— |
| `src/shop/dynamic_dependency.py` | `importlib.import_module(name)` | 依赖无法静态确定 → 失败关闭 | ARCH-001 |
| `src/shop/unresolved_dependency.py` | 顶层包存在但模块不存在 | 解析失败 → 失败关闭 | ARCH-001 |
| `src/shop/broken_syntax.py` | 语法错误 | 解析不了 → 失败关闭 | ARCH-001 / DOC-001 |
| `src/shop/style_offences.py` | 超长行 + 未使用导入 | Ruff 报 E501 / F401 → 映射到 STYLE-001 / STYLE-002 | STYLE-001 / STYLE-002 |
| `src/shop/no_module_docstring.py` | 模块没有 docstring | py.docstring 报模块缺 docstring | DOC-001 |
| `tests/test_order_service.py` | 与生产文件同名的测试 | 测试选择落在 related 层级并真正运行 | TESTING-001 / TESTING-002 |

敏感数据：**没有**。夹具里不含真实凭据、用户数据或生产日志；`tools/fake_tool.py` 里出现的
`Authorization: Bearer ...` 是脱敏测试用的合成值，行内标了 `secret-scan: allow` 并写明理由。

## tools/fake_tool.py：外部工具的失效与边界扮演者

| 行为 | 用途 |
| --- | --- |
| `ok` / `findings` | 正常结果与诊断映射（含"没有规则归属"的诊断码 W291） |
| `empty` / `garbage` / `flood` | 输出为空 / 非 UTF-8 / 超长 → output_invalid 或截断 |
| `config_error` / `crash` | 工具自报用法错误 → config_error；内部错误 → crashed |
| `slow` | 超时；同时产生一个心跳子进程，用于验证"超时终止整棵进程树" |
| `old` | 版本低于声明区间 → version_mismatch |
| `injection` | 诊断消息里塞入换行、ANSI、绝对路径与合成凭据 → 必须被脱敏 |

它靠 `validation/validators.yaml` 的 `tool.command` 注入（测试构造临时注册表），
因此不需要改动仓库的运行时数据。
