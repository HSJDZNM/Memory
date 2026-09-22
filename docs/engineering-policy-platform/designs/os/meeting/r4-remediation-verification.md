# R4 · 评审修复复核

> 日期：2026-09-22。本文只记录 R3 之后的修复证据；R3 的 `3 条阻断级`、`33 OK / 6 wrong / 4 unverifiable` 是历史基线，不改写原始会议记录。

## 结论

P-1 的三项阻塞与前端第二判定均已修复。操作台仍是静态原型，尚未新增 HTTP 写入路由；因此“代码已修复”不等于“操作台已上线”。

## 证据

| 项目 | 修复 | 复核证据 |
| --- | --- | --- |
| B1 受保护写入 | 新建 `policies/**` 使用 `orc.policy.write`；编辑使用 `orc.policy.edit`；普通编排写工具阻断 `policies`、`registry`、`adapters`、`api`、`validation` | `tests/contract/test_enforcement_protocol.py`、`tests/unit/test_orchestration_state.py`、`tests/security/test_enforcement_adversarial.py` |
| B2 真实漂移 | `retrieve.index.hash_drift` 读取 `LoadedCorpus.verification.drift`，返回排序后的 `dataset:source_path` | `tests/integration/test_api_http.py::test_retrieve_reports_real_corpus_hash_drift` |
| B3 幂等超限 | 台账拒绝无法完整保存的响应，返回 503 `idempotency_unavailable`，不写空对象条目 | `tests/unit/test_api_contract.py`、`tests/integration/test_api_http.py::test_oversized_idempotent_response_fails_explicitly_without_a_false_replay` |
| 前端第二判定 | `severity` 只做枚举校验，Decision 只来自 Policy API | `tests/contract/test_console_design.py` |
| 编排判定幂等边界 | `EvaluateCall`、`RetrieveCall`、`ValidateCall` 不再发送编排动作幂等键；动作幂等仍由 checkpoint 与 Phase 4 台账负责 | `tests/contract/test_orchestration_engine.py::test_policy_calls_never_send_orchestration_idempotency_key`、`python tools/orchestration_loop.py --json` |

## 本次运行

```text
$env:PYTHONPATH='src'; python -m enforcement.cli registry --approve --reviewer codex-review
→ registry_digest=sha256:68237f8c271a5c29f2109f457c11a64e30574f1f46512d14f285c0b6fa78a3ed

$env:PYTHONPATH='src'; python -m pytest tests/contract/test_enforcement_protocol.py tests/unit/test_orchestration_state.py tests/unit/test_api_contract.py tests/integration/test_api_http.py tests/contract/test_console_design.py tests/security/test_enforcement_adversarial.py -q
→ 136 passed

$env:PYTHONPATH='src'; python -m pytest tests/contract/test_orchestration_engine.py tests/integration/test_orchestration_runtime.py tests/security/test_orchestration_adversarial.py -q
→ 51 passed

$env:PYTHONPATH='src'; python tools/orchestration_loop.py --json
→ `result: pass`；8/8 场景通过，端到端场景完成 9 步、2 次受控动作；两个引擎报告一致。
```

注册表审核命令会在每次变更后重跑；测试中的 pytest cache 警告只与受限环境的缓存目录权限有关，不影响上述测试结果。

## 未在本记录中宣称

- 没有新增 `enforce` API 路由。
- 没有把静态页面的构建期快照当作运行期事实。
- 没有把 `python tools/orchestration_loop.py` 或全仓门禁的结果从未运行状态推断为通过；需要时应按当前工作树重新运行。
