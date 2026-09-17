# dsh Agent 事件 fixture

Phase 2 的 dsh Adapter 契约测试用这组文件固定"dsh 到底会送来什么"；
Phase 4 之后同一组 fixture 还被受控执行链路（tests/integration/test_dsh_enforcement.py）复用，
因此表里的"预期"一列以**当前阶段**的行为为准。
它们**只保留协议字段**：用户数据、绝对路径与密钥已删除，cwd 统一替换成占位值
/workspace/demo-shop，测试里再由 conftest.dsh_event 换成真实临时项目根。

| 文件 | 工具 | 场景 | 预期 | 关联规则 | 敏感数据 |
| --- | --- | --- | --- | --- | --- |
| pre-tool-use-edit-block.json | edit | controller 引入 from repository import ... | block，ARCH-001@1 | ARCH-001 | 无 |
| pre-tool-use-edit-captured.json | edit | **真实采集**：dsh 送来绝对 Windows 路径、cwd 用正斜杠、可选字段缺省 | allow（规则命中、无违规） | ARCH-001（命中未违规） | 无 |
| pre-tool-use-edit-allow.json | edit | controller 改为依赖 service / util | allow（规则命中、无违规） | ARCH-001（命中未违规） | 无 |
| pre-tool-use-write-block.json | write | 整文件写入一个直接依赖 repository 的 controller | block | ARCH-001 | 无 |
| pre-tool-use-write-allow.json | write | 写入 service 层文件 | allow（范围不匹配，skipped_rules 说明原因） | ARCH-001（范围不匹配） | 无 |
| pre-tool-use-pwsh-execute.json | pwsh | 高权限执行类工具（命令在白名单内） | Phase 4：block（缺 shell.exec 权限或缺绑定审批） | 无（由 Tool Registry 治理） | 无 |
| pre-tool-use-unknown-tool.json | mcp__github__create_issue | 未登记的工具 | 拒绝（失败关闭） | 无 | 无 |
| post-tool-use-edit.json | edit（PostToolUse） | 执行后事件（Phase 4 事后验证入口） | 有对应 pre-check 时验证证据；没有则只记录 | 无 | 无 |
| pre-tool-use-missing-path.json | edit | 工具参数缺 file_path | 拒绝（安全关键字段缺失） | 无 | 无 |
| pre-tool-use-extra-fields.json | edit | 载荷里混入 prompt / system_prompt / sandbox_permissions | 这些内容不进入核心模型 | ARCH-001 | 无（伪造的注入文本） |
| pre-tool-use-read-not-governed.json | read | 只读动作 | Phase 4：allow 且审计标记 not_governed（显式降级） | 无 | 无 |

## 版本与来源

| 项 | 值 |
| --- | --- |
| dsh CLI | 0.1.5-rc.1 |
| Hook 桥 | @deepseek-ai/dsh-hooks-claude-code 0.1.5-rc.2（Claude Code 方言） |
| 采集方式 | 在受控沙箱项目里用 --capture 记录 Hook 真实收到的 stdin 原文，再脱敏 |
| 脱敏内容 | 绝对路径（换成 /workspace/demo-shop）、会话标识、任何用户数据 |

字段形状来自 dsh 的 preToolPayload 构造（session_id / transcript_path / cwd /
hook_event_name / tool_name / tool_input / tool_use_id）。transcript_path 在 dsh 里
恒为空字符串，属于协议字段，因此保留而不是删除。

## 更新规则

1. 先在真实 dsh 上重跑沙箱闭环并重新采集（见 src/adapters/dsh/README.md 第 8 节）；
2. 比对本次与上次的字段差异，确认真实契约变化而不是采集抖动；
3. 更新本目录的 fixture 与上面的版本表；
4. 跑 python -m pytest tests/contract/test_dsh_adapter.py tests/integration/test_dsh_hook.py tests/integration/test_dsh_enforcement.py -q；
5. 在提交信息里说明 dsh 版本变化。

禁止在这里放真实凭据、用户数据或生产日志；fixture 里的任何文本都不得来自真实仓库。
