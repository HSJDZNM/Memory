"""Phase 6 学习手册的单元内容（被 tools/build_learning_notebook.py 引用）。

单独成文件的原因：build_learning_notebook.py 已经有六千多行，Phase 6 的讲解再塞进去会让
"生成器"和"某一阶段的内容"混在一起。**改动手册内容 = 改这个文件**，然后运行：

    python tools/build_learning_notebook.py --phase phase-6

生成器会从两个工作目录各跑一遍全部代码单元，并核对这里写过的结构断言。

单元顺序与其它阶段一致：先介绍 markdown，再放起步代码，然后每个小节都是
"说明 markdown → 代码"；代码里有逐段注释，单元末尾打印小结。
"""

from __future__ import annotations

from typing import Any

__all__ = ["PHASE_6_CELLS", "check_phase_6_structure"]


def _markdown(text: str) -> tuple[str, str]:
    return ("markdown", text)


def _code(text: str) -> tuple[str, str]:
    return ("code", text)


PHASE_6_CELLS: list[tuple[str, str]] = [
    _markdown("""
        # Phase 6 学习手册：多 Agent Adapter

        这份 notebook 用**实际运行的代码**解释 Phase 6：怎样让多个 Agent Runtime 通过同一套
        事件与决策协议接受一致治理，而**不修改 Policy Engine**。它不引入新代码，只调用仓库里
        已经通过测试的模块，因此每一段输出都可以自己重跑验证。

        ## Phase 6 要证明的事

            Agent Runtime（dsh / 第三方 JSON 消费者 / 只有 PostToolUse 的旧 Agent）
              → Adapter.to_policy_event(raw)   → 规范事件 AgentEvent（受控字段 + 摘要）
              → AgentRuntime.handle(…, raw)    → trace 校验 → 上下文 → 能力门禁 → 熔断 → 幂等
              → Policy Engine（未改动一行）     → PolicyDecision
              → Adapter.to_agent_response      → 原生响应（钩子类是退出码：2 = 阻断）

        一句话：**同一个语义事件，不管从哪个 Agent 来，都得到同一套结论**；而能力不足的 Agent
        在接入时就被算成只读，受治理动作得到 capability_unavailable，绝不「跳过治理」。

        ## 阅读路线

        | 小节 | 回答的问题 |
        | --- | --- |
        | 0 | 跑这份 notebook 需要什么前提 |
        | 1 | 规范事件长什么样？受控字段与版本轴为什么是硬约束 |
        | 2 | 能力声明是数据：支持矩阵（full / read_only / unsupported）怎么算出来 |
        | 3 | 同一个语义场景怎样渲染成三家的线协议 |
        | 4 | 一致性套件跑了什么、每个 Adapter 覆盖了多少项 |
        | 5 | 能力不足的 Agent 会怎样（不是跳过治理） |
        | 6 | 跨 Agent 隔离：命名空间、主体、trace、熔断 |
        | 7 | 事件 → 上下文 → 决策 → 原生响应的完整链路 |
        | 8 | 不一致会被发现吗（改声明不审核 / 路径越界 / 未知工具） |
        | 9 | 命令行与退出码 |
        | 10 | 多 Agent 闭环与这一阶段明确不做的事 |

        每个代码单元后面都有小结，说明「这段输出意味着什么」。这份 notebook **不联网、不调用 LLM、
        不改仓库真实文件**：受控工作区是 tests/fixtures/agent_events/workspace/ 这个只读探针项目，
        演示产物写在 .tmp/notebook-demo/phase-6/ 下，跑完用 python tools/cleanup.py 清理即可。

        ## 三个角色

        - **规范事件**（AgentEvent）：与实现无关的交换协议，任何 Agent 只要产出它就能接入；
        - **Adapter**：只做协议转换——把某家的报文翻译成规范事件，把结论翻译回该家的响应；
        - **Runtime**：所有 Agent 共用的判定入口，负责隔离、幂等、trace 与熔断。
        """),
    _code("""
        # 0. 起步：定位仓库、准备规则与三个 Adapter

        # 手册可能从仓库根启动，也可能从 docs/learning/phase-6/ 启动：向上找到 pyproject.toml 为止。
        import json
        import shutil
        import sys
        from pathlib import Path


        def find_repo_root(start):
            candidate = Path(start).resolve()
            for _ in range(8):
                if (candidate / 'pyproject.toml').is_file():
                    return candidate
                candidate = candidate.parent
            raise AssertionError('找不到仓库根：没有 pyproject.toml')


        REPO_ROOT = find_repo_root(Path.cwd())
        NOTEBOOK_DIR = REPO_ROOT / 'docs' / 'learning' / 'phase-6'
        # 让解释器找到 src/ 与 tools/：仓库不把 src 装进 site-packages，全靠这条路径。
        for extra in (REPO_ROOT / 'src', REPO_ROOT / 'tools'):
            if str(extra) not in sys.path:
                sys.path.insert(0, str(extra))

        from adapters.base import AdapterRegistry, ceiling_from_capabilities  # noqa: E402
        from adapters.conformance import (  # noqa: E402
            SCENARIOS,
            conformance_enforcer,
            conformance_evidence,
            render_event,
            run_conformance,
        )
        from adapters.loader import load_adapters, load_registry_from_repo  # noqa: E402
        from adapters.models import (  # noqa: E402
            CANONICAL_EVENT_SCHEMA_VERSION,
            AdapterEventError,
            AgentEvent,
            EnforcementLevel,
            EventType,
            parse_canonical_event,
        )
        from adapters.runtime import AgentRuntime, sanitize_message  # noqa: E402
        from policy.loader import load_rule_set  # noqa: E402


        def pad(text, width, align='left'):
            # 表格对齐用：中文（全角）在等宽字体里占 2 列，而 f-string 的 <N 数的是字符个数，
            # 中英混排时列会被挤歪；按显示宽度补空格才是对的。
            text = str(text)
            width_now = sum(2 if ord(char) > 0x2E7F else 1 for char in text)
            return text + ' ' * max(1, width - width_now)


        # 受控工作区：一致性套件与闭环都只在这里判定，它是仓库内的只读探针项目。
        WORKSPACE = REPO_ROOT / 'tests' / 'fixtures' / 'agent_events' / 'workspace'
        # 「越界」的基准是受控工作区的同级路径：绝对路径落在它上面才是真的越界。
        OUTSIDE = WORKSPACE.parent / 'outside-workspace.py'
        # 演示产物只写 .tmp/，不碰仓库真实文件。
        DEMO = REPO_ROOT / '.tmp' / 'notebook-demo' / 'phase-6'
        # 每轮从空目录开始：台账是本轮的幂等记录，上一轮的文件会让本轮事件立刻被判成重放或熔断，
        # 那样失败原因就与被测行为无关了。
        shutil.rmtree(DEMO, ignore_errors=True)
        DEMO.mkdir(parents=True, exist_ok=True)

        rules = load_rule_set([REPO_ROOT / 'policies'], repo_root=REPO_ROOT)
        # 注册表加载时会比对 adapters/approved.json 的已审核哈希：改能力声明没重新审核就加载失败。
        registry = load_registry_from_repo(REPO_ROOT)
        adapters = load_adapters(
            ['dsh', 'generic-json', 'legacy-post-only'], root=REPO_ROOT, registry=registry
        )

        # dsh 声明的是完整 enforcement：写类动作必须同时有 Phase 5 证据与 Phase 4 授权链路。
        # 这两个接线由 adapters.conformance 提供（一致性套件与闭环用同一份实现）。
        enforcer = conformance_enforcer(
            adapters['dsh'], workspace=WORKSPACE, state_root=DEMO / 'enforcement'
        )
        EVidence = {'dsh': conformance_evidence}

        print('仓库根:', REPO_ROOT.name)
        print('受控工作区:', WORKSPACE.relative_to(REPO_ROOT).as_posix())
        print('接入的 Agent:', ', '.join(sorted(adapters)))
        """),
    _markdown("""
                ## 1. 规范事件：协议在这里固化

                1. `schema_version` 是**兼容轴**：消费方看不懂必须拒绝，不能降级成放行；
                2. `EventType` 是受控枚举：未知事件类型一律拒绝；
                3. `payload` 只允许受控字段（`path` / `params` / `text` / `cwd`），其余原始输入只留摘要。

        """),
    _code("""
                # 1. 规范事件 Schema
                print('规范事件协议版本:', CANONICAL_EVENT_SCHEMA_VERSION)
                print('受控事件类型:', ', '.join(item.value for item in EventType))

                document = {
                    'schema_version': CANONICAL_EVENT_SCHEMA_VERSION,
                    'event_id': 'sess-1:call-1',
                    'event_type': 'tool.pre_execute',
                    'request_id': 'sess-1:call-1',
                    'tool': 'edit',
                    'operation': 'edit',
                    'payload': {'path': 'src/shop/order_controller.py', 'params': {'new_string': 'x = 1'}},
                }
                event = parse_canonical_event(document, agent_id='generic-json')
                print()
                print('一条规范事件:', event.event_type.value, '|', event.path)
                print('需要判定:', event.decision_requested, '| 载荷摘要:', event.payload_digest[:32] + '...')
                print()
                print('未知事件类型会被拒绝：')
                try:
                    parse_canonical_event({**document, 'event_type': 'tool.teleport'}, agent_id='generic-json')
                except AdapterEventError as error:
                    print('   ', str(error)[:72])
                print('小结：协议只有一份，Agent 之间的差异全部留在 Adapter 里。')

        """),
    _markdown("""
                ## 2. 能力声明是数据：支持矩阵怎么算出来

                每个 Agent 在自己的 `adapters/<agent_id>/manifest.yaml` 里声明事件名、字段名、工具表、阻断能力与审批能力；平台据此算出它**声明的能力上限**，并与 `adapters/approved.json` 的已审核哈希比对。`full` 仍不等于运行时已自动接好 Phase 4/5。

                1. 没有执行前事件，或阻断能力不是 `pre_execute` → 上限 `read_only`；
                2. 没有工具表 → 上限 `read_only`；
                3. 申请值本身更低时以申请值为准（主动收紧是合法的）。

        """),
    _code("""
                # 2. 支持矩阵：数据 → 结论
                listing = registry.as_list()
                print('已审核清单:', listing.approved_path)
                print('审核人:', listing.reviewed_by, '| 时间:', listing.approved_at)
                print()
                print(pad('agent', 20) + pad('上限', 14) + pad('产品版本', 20) + pad('协议', 22) + pad('工具', 6) + '审核')
                print('-' * 96)
                for item in listing.descriptors:
                    print(
                        pad(item.agent_id, 20)
                        + pad(item.enforcement.value, 14)
                        + pad(item.agent_version, 20)
                        + pad(item.protocol, 22)
                        + pad(len(item.tools), 6)
                        + ('是' if item.approved else '否')
                    )
                print()
                for item in listing.descriptors:
                    if item.ceiling_reasons:
                        print('原因 [' + item.agent_id + ']: ' + '；'.join(item.ceiling_reasons))
                print()
                counts = (len(listing.governed()), len(listing.read_only()), len(listing.unsupported()))
                print('三种状态:', counts[0], '个完整 enforcement /', counts[1], '个只读 /', counts[2], '个不支持')

        """),
    _markdown("""
                ## 3. 一个语义事件怎么渲染成三家的线协议

                - `dsh` 用 `PreToolUse` + `edit` + `file_path` / `new_string`；
                - `generic-json` 用规范事件本身；
                - `legacy-post-only` 只有 `PostToolUse`，用 `save_file`。

                因此新增一个 Agent 只增加渲染分支，核心测试期望里没有 Agent 专用分支。

        """),
    _code("""
                # 3. 同一场景 → 三种报文
                scenario = next(item for item in SCENARIOS if item.name == 'block-controller-edit')
                print('场景:', scenario.name)
                print('说明:', scenario.description)
                print()
                for agent_id in sorted(adapters):
                    try:
                        raw = render_event(
                            adapters[agent_id], scenario, index=0, workspace=WORKSPACE, outside=str(OUTSIDE)
                        )
                    except AdapterEventError as error:
                        print(pad(agent_id, 20) + '不适用: ' + str(error)[:60])
                        continue
                    lookup = raw.get('tool_input', raw.get('payload', {}))
                    tool = raw.get('tool_name') or raw.get('tool')
                    path = lookup.get('file_path') or lookup.get('path')
                    print(pad(agent_id, 20) + pad(str(tool), 12) + str(path))
                print()
                dsh_raw = render_event(adapters['dsh'], scenario, index=0, workspace=WORKSPACE, outside=str(OUTSIDE))
                print('dsh 报文键:', ', '.join(sorted(dsh_raw)))

        """),
    _markdown("""
                ## 4. 一致性套件：同一组语义事件、同一套结论

                八条要求：等价事件产生等价上下文；路径与 operation 保留；**block 不触发原生工具**；**allow 只触发一次**；未知事件与版本被拒绝；错误响应可读但不泄露内部信息；重复 event ID 幂等；跨 Agent 隔离与循环限制。

                报告必须让每个 Adapter 都产生检查项。能力受限的写动作应明确得到 `capability_unavailable`；
                manifest 根本没声明的事件记为 `declared_inapplicable`，不能伪装成行为已通过。

        """),
    _code("""
                # 4. 跑一遍一致性套件
                import uuid
                # 每次运行都用全新的套件目录：台账与 trace 登记表都是本轮的记录。
                suite_dir = DEMO / ('conformance-' + uuid.uuid4().hex[:8])
                print('一致性套件目录:', suite_dir.relative_to(REPO_ROOT).as_posix())
                report = run_conformance(
                    adapters=adapters,
                    rules=rules,
                    workspace=WORKSPACE,
                    outside=OUTSIDE,
                    ledger_dir=suite_dir / 'ledger',
                    trace_path=suite_dir / 'traces.jsonl',
                    breaker_limit=3,
                )
                conformance_result = 'pass' if report.ok else 'fail'
                print('一致性套件结论:', conformance_result)
                print('参与套件的 Adapter:', ', '.join(report.adapters))
                print('场景数:', len(report.scenarios), '| 检查项:', len(report.checks), '| 失败:', len(report.failures))
                for item in report.failures[:3]:
                    print('   FAIL', item.adapter, item.scenario, item.name, '|', item.detail)
                print()
                per_adapter = {}
                for item in report.checks:
                    per_adapter[item.adapter] = per_adapter.get(item.adapter, 0) + 1
                for agent_id in sorted(per_adapter):
                    print(pad(agent_id, 20) + str(per_adapter[agent_id]) + ' 项检查')
                print()
                print('场景:', ', '.join(report.scenarios))

        """),
    _markdown("""
        ## 5. 能力不足会怎样：不是跳过治理

        `legacy-post-only` 只有 `PostToolUse`：它能事后把结果标成错误，但**副作用已经发生**。
        平台在接入阶段就把它算成 `read_only`，写类动作因此得到 `capability_unavailable`。

        这正是计划第 6 步的要求：**能力不足应在接入时显式失败或降级为只读，而不是被标记为
        完整 enforcement。** 下面同时跑一个具备执行前阻断能力的 Agent 作对照——注意 dsh 的
        写类动作必须同时接上 Phase 5 证据与 Phase 4 授权链路，这正是「声明 ≠ 接线」。
        """),
    _code("""

                # 5. 能力不足的 Agent 会被显式拒绝
                runtime = AgentRuntime(
                    adapters=adapters,
                    rules=rules,
                    ledger_path=DEMO / 'capability.jsonl',
                    workspace=WORKSPACE,
                    breaker_limit=30,
                    enforcers={'dsh': enforcer},
                    evidence_providers=EVidence,
                )
                ceiling = ceiling_from_capabilities(adapters['legacy-post-only'].manifest)
                print('上限:', ceiling.level.value, '| 申请值:', ceiling.requested)
                print('原因:', '；'.join(ceiling.reasons))
                print()
                calls = []
                legacy = runtime.handle(
                    'legacy-post-only',
                    {
                        'hook_event_name': 'PostToolUse',
                        'session_id': 'learn-legacy-1',
                        'tool_name': 'save_file',
                        'tool_use_id': 'call-1',
                        'cwd': str(WORKSPACE),
                        'tool_input': {'file_path': 'src/shop/order_controller.py', 'text': 'value = 1'},
                    },
                    execute=calls.append,
                )
                print('legacy-post-only 结论:', legacy.response.decision.value, '| 原因码:', legacy.outcome_code)
                print('原生工具被调用:', len(calls), '次')
                print('给 Agent 的说明:', legacy.response.message[:70])
                print()
                # 对照：dsh 有执行前钩子，并且接上了证据与授权链路，写类动作会走完整判定。
                dsh_calls = []
                accepted = runtime.handle(
                    'dsh',
                    {
                        'hook_event_name': 'PreToolUse',
                        'session_id': 'learn-dsh-1',
                        'tool_name': 'edit',
                        'tool_use_id': 'call-1',
                        'cwd': str(WORKSPACE),
                        'tool_input': {
                            'file_path': 'src/shop/order_service.py',
                            'old_string': 'pass',
                            'new_string': 'value = 1',
                        },
                    },
                    execute=dsh_calls.append,
                )
                print('dsh 结论:', accepted.response.decision.value, '| 原因码:', accepted.outcome_code, '| 工具被调用:', len(dsh_calls), '次')
                print()
                print('小结：「拦不住」与「不拦」是两件事。前者被显式写成 capability_unavailable，后者不存在。')

        """),
    _markdown("""
                ## 6. 跨 Agent 隔离：命名空间、trace、熔断

                | 风险 | 机制 |
                | --- | --- |
                | A 的判定替 B 放行 | 台账键 `<adapter.namespace>:<event_id>`；默认 agent id，多份同型号 Agent 用 `ledger_alias` 区分 |
                | 自称别人的身份 | `agent_id` 由装配处钉死；主体只认 Adapter 的显式声明 |
                | 伪造父 trace | trace 登记表按 `owner_agent` 校验来源 |
                | 互相触发的死循环 | 同一 Agent 在时间窗口内的事件数到上限即熔断 |
                | 重复 event_id | 幂等台账：重放阻断，换参数则拒绝 |

        """),
    _code("""

                # 6. 隔离与熔断
                isolated = AgentRuntime(
                    adapters=adapters,
                    rules=rules,
                    ledger_path=DEMO / 'isolation.jsonl',
                    trace_path=DEMO / 'isolation-traces.jsonl',
                    workspace=WORKSPACE,
                    breaker_limit=2,
                    enforcers={'dsh': enforcer},
                    evidence_providers=EVidence,
                )

                # (1) 命名空间：同一个 event_id 在两个 Agent 下是两条互不相干的记录。
                first = isolated.handle(
                    'dsh',
                    {
                        'hook_event_name': 'PreToolUse',
                        'session_id': 'shared',
                        'tool_name': 'edit',
                        'tool_use_id': 'call-1',
                        'cwd': str(WORKSPACE),
                        'tool_input': {
                            'file_path': 'src/shop/order_service.py',
                            'old_string': 'pass',
                            'new_string': 'v = 1',
                        },
                    },
                    execute=lambda event: None,
                )
                second = isolated.handle(
                    'generic-json',
                    {
                        'schema_version': '1.0',
                        'event_id': 'shared:call-1',
                        'event_type': 'tool.pre_execute',
                        'request_id': 'shared:call-1',
                        'tool': 'read',
                        'operation': 'read',
                        'payload': {'path': 'src/shop/order_service.py'},
                    },
                    execute=lambda event: None,
                )
                keys = sorted({item.get('ledger_key') for item in isolated.history_for('dsh') if item.get('ledger_key')})
                print('dsh:', first.outcome_code, '| generic-json:', second.outcome_code)
                print('台账键:', ', '.join(keys))
                print()

                # (2) trace 来源：引用一条从未发放过的父 trace，等于伪造来源。
                forged = isolated.handle(
                    'dsh',
                    {
                        'hook_event_name': 'PreToolUse',
                        'session_id': 'forged',
                        'tool_name': 'edit',
                        'tool_use_id': 'call-1',
                        'cwd': str(WORKSPACE),
                        'tool_input': {
                            'file_path': 'src/shop/order_service.py',
                            'old_string': 'pass',
                            'new_string': 'v = 2',
                        },
                        'parent_trace_id': 'never-issued',
                    },
                    execute=lambda event: None,
                )
                print('伪造父 trace:', forged.response.decision.value, '| 原因码:', forged.outcome_code)
                print()

                # (3) 熔断：上限 2，却连着发 5 条受治理事件——循环必须被终止。
                codes = []
                for index in range(5):
                    outcome = isolated.handle(
                        'dsh',
                        {
                            'hook_event_name': 'PreToolUse',
                            'session_id': 'loop-' + str(index),
                            'tool_name': 'edit',
                            'tool_use_id': 'call-' + str(index),
                            'cwd': str(WORKSPACE),
                            'tool_input': {
                                'file_path': 'src/shop/order_service.py',
                                'old_string': 'pass',
                                'new_string': 'step_' + str(index) + ' = ' + str(index),
                            },
                        },
                        execute=lambda event: None,
                    )
                    codes.append(outcome.outcome_code)
                print('连续 5 次受治理事件（上限 2）:', codes)
                print()
                print('小结：循环在第', codes.index('request_busy') + 1, '次被终止，而不是一直跑下去。')

        """),
    _markdown("""
                ## 7. 一次判定的完整链路

                Adapter 负责**翻译**；Runtime 负责**隔离与顺序**（trace → 上下文 → 能力门禁 → 原子 claim → Phase 5 证据 → Policy → Phase 4 pre/post → callback）；Engine 负责**判定**——Phase 6 没有改动它一行。

        """),
    _code("""

                # 7. 事件 → 规范事件 → 上下文 → 决策
                raw = {
                    'hook_event_name': 'PreToolUse',
                    'session_id': 'learn-chain',
                    'tool_name': 'edit',
                    'tool_use_id': 'call-1',
                    'cwd': str(WORKSPACE),
                    'tool_input': {
                        'file_path': 'src/shop/order_controller.py',
                        'old_string': 'pass',
                        'new_string': 'from repository import OrderRepository',
                    },
                }
                adapter = adapters['dsh']
                # 第一步：原始报文 → 规范事件（只保留受控字段，载荷另有摘要）。
                event = adapter.to_policy_event(raw, workspace=WORKSPACE)
                print('规范事件:', event.event_type.value, '|', event.tool, '|', event.path)
                print('载荷摘要:', event.payload_digest[:32] + '...')
                print()
                # 第二步：规范事件 → PolicyContext（layer 来自声明的映射，主体来自配置）。
                context = adapter.to_policy_context(event, workspace=WORKSPACE)
                print('上下文:', json.dumps(json.loads(context.model_dump_json()), ensure_ascii=False))
                print()
                chain = AgentRuntime(
                    adapters={'dsh': adapter},
                    rules=rules,
                    ledger_path=DEMO / 'chain.jsonl',
                    workspace=WORKSPACE,
                    enforcers={'dsh': enforcer},
                    evidence_providers=EVidence,
                )
                calls = []
                structured = chain.handle('dsh', raw, execute=calls.append)
                print('结论:', structured.response.decision.value, '| 原因码:', structured.outcome_code)
                print('命中规则:', ', '.join(structured.response.matched_rules))
                print('原生工具被调用:', len(calls), '次')
                print()
                # 第三步：决策 → 该 Agent 能理解的原生响应（钩子类是退出码：2 = 阻断）。
                native = adapter.response_from_decision(structured.response, event=structured.event)
                print('原生响应（dsh 线协议）退出码:', native['exit_code'], '= 2 表示阻断')
                print()
                print('小结：Adapter 只翻译、Runtime 只编排，判定仍然只发生在 Policy Engine。')

        """),
    _markdown("""
                ## 8. 不一致会被发现吗

                1. 改了能力声明却没重新审核 → 哈希比对失败；
                2. 路径越界 → 拒绝（含只读动作）；
                3. 未知工具或版本 → 拒绝，并给出可读但不泄露内部信息的原因。

        """),
    _code("""
                # 8. 漂移、越界与未知
                approved = json.loads((REPO_ROOT / 'adapters' / 'approved.json').read_text(encoding='utf-8'))
                tampered = json.loads(json.dumps(approved))
                tampered['adapters']['dsh']['manifest_digest'] = 'sha256:' + '0' * 64
                drifted = AdapterRegistry([registry.manifest('dsh')], approved=tampered)
                descriptor = drifted.as_list().get('dsh')
                print('漂移检测:', '已发现' if not descriptor.approved else '漏了')
                print('   说明:', descriptor.ceiling_reasons[-1][:70])
                escaped = {
                    'hook_event_name': 'PreToolUse',
                    'session_id': 'learn-escape',
                    'tool_name': 'edit',
                    'tool_use_id': 'call-1',
                    'cwd': str(WORKSPACE),
                    'tool_input': {'file_path': str(OUTSIDE), 'old_string': 'pass', 'new_string': 'x = 1'},
                }
                try:
                    adapter.to_policy_event(escaped, workspace=WORKSPACE)
                    print('越界路径: 放行了（缺陷）')
                except AdapterEventError as error:
                    print('越界路径: 已拒绝 -', str(error)[:60])
                for label, patch in (
                    ('未知工具', {'tool_name': 'definitely_not_a_tool'}),
                    ('未知事件', {'hook_event_name': 'ToolTeleport'}),
                ):
                    broken = dict(raw)
                    broken.update(patch)
                    try:
                        adapter.to_policy_event(broken, workspace=WORKSPACE)
                        print(label + ': 放行了（缺陷）')
                    except AdapterEventError as error:
                        print(label + ': 已拒绝 -', str(error)[:60])
                leaked = chain.handle(
                    'dsh',
                    {**raw, 'session_id': 'learn-leak', 'tool_input': {'file_path': str(OUTSIDE), 'new_string': 'x'}},
                    execute=lambda event: None,
                )
                printed = json.dumps(leaked.response.model_dump(mode='json'), ensure_ascii=False)
                print('响应里是否含仓库绝对路径:', str(REPO_ROOT) in printed)
                print('脱敏示例:', sanitize_message('failed at ' + str(REPO_ROOT) + '/src/a.py'))

        """),
    _markdown("""
        ## 9. 命令行与退出码

        适配层有自己的命令组（python -m adapters.cli）：

        - matrix：打印支持矩阵；能力声明未审核或哈希漂移时退出码 1；
        - approve --reviewer <name>：审核能力声明并写 adapters/approved.json（改 manifest 后必须重跑）；
        - check：跑一致性套件（--json 写在子命令前后都行）；
        - events：检查每个 Agent 的兼容性 fixture 是否存在；
        - inspect --agent <id> --event <file>：看一条事件被翻译成了什么。

        退出码：**0** 通过、**1** 检查失败（漂移 / 能力不足 / 一致性失败）、**2** 用法或配置错误。
        下面用子进程调用它们——和你在终端里敲的是同一条路径。
        """),
    _code("""
        # 9. 命令行与退出码
        import os
        import subprocess


        def run_adapter_cli(*args):
            # 与 CI 同一条路径：PYTHONPATH=src，工作目录是仓库根。
            env = dict(os.environ)
            env['PYTHONPATH'] = str(REPO_ROOT / 'src')
            env['PYTHONIOENCODING'] = 'utf-8'
            return subprocess.run(
                [sys.executable, '-m', 'adapters.cli', *args],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                encoding='utf-8',
                check=False,
            )


        cli_exits = {}
        checked = run_adapter_cli('--json', 'check')
        cli_exits['check'] = checked.returncode
        checked_payload = json.loads(checked.stdout)
        print('退出码:', checked.returncode, '| 一致性套件:', checked_payload['conformance']['result'],
              '| 检查项:', checked_payload['conformance']['checks'])

        matrix_run = run_adapter_cli('matrix')
        cli_exits['matrix'] = matrix_run.returncode
        print('退出码:', matrix_run.returncode, '| 支持矩阵:', matrix_run.stdout.splitlines()[1].strip())

        fixtures = run_adapter_cli('events')
        cli_exits['events'] = fixtures.returncode
        print('退出码:', fixtures.returncode, '| 缺失的 fixture:', json.loads(fixtures.stdout)['missing'])

        # 未审核的清单等于「没有审核记录」：装配必须失败，而不是先跑起来再说。
        unapproved = run_adapter_cli('--approved', '.tmp/does-not-exist.json', 'check')
        cli_exits['unapproved'] = unapproved.returncode
        print('退出码:', unapproved.returncode, '| 未审核清单被拒绝:', unapproved.stderr.strip()[-40:])
        print()
        print('小结：能力声明没有审核记录、或检查不通过，命令一律以非 0 退出——CI 据此阻断。')
        """),
    _markdown("""
        ## 10. 多 Agent 闭环

        仓库提供一个闭环工具 tools/agent_loop.py：它跑 7 个场景 + 一致性套件，把结论写成 JSON
        供阶段证据引用，也是「改完代码怎么自证」的最短路径。下面直接调用它。
        """),
    _code("""

                # 10. 多 Agent 闭环
                import agent_loop

                exit_code = agent_loop.main(['--json'])
                payload_path = REPO_ROOT / '.tmp' / 'artifacts' / 'phase-6-agents-result.json'
                payload = json.loads(payload_path.read_text(encoding='utf-8'))
                print('闭环退出码应为 0，实际得到:', exit_code)
                print('结论:', payload['result'])
                print()
                print(pad('场景', 46) + '结果')
                print('-' * 60)
                for item in payload['scenarios']:
                    print(pad(item['name'], 46) + ('通过' if item['passed'] else '失败'))
                print()
                print('一致性套件检查项:', payload['conformance']['checks'], '| 失败:', len(payload['conformance']['failures']))
                print('支持矩阵:', ', '.join(sorted(payload['matrix'])))
                print()
                print('小结：「能跑通」与「可重放」是两件事——闭环把每一轮的结论都落成 JSON，谁都能重跑。')

        """),
    _markdown("""
        ## 11. 边界与不做的事

        - **不做判定**：Adapter 只翻译、Runtime 只编排，allow / block 始终由 Policy Engine 决定；
          决策协议没有新增字段（仍是 schema_version 1.0 / policy_version phase-1）；
        - **不假设所有 Agent 都有同样的 Hook**：能力声明是数据，full 只是**能力上限**——写类动作
          还要求 Phase 5 证据与 Phase 4 授权链路同时到位，缺任一项都失败关闭；
        - **只接入了一个真实产品**：仓库里只有 dsh 是真实产品，generic-json 与 legacy-post-only 是
          合成协议消费者（分别代表「产出规范事件的自研 Agent」与「只有 PostToolUse 的旧 Agent」）；
          接第二个真实产品前要先核实它的版本与钩子契约，流程见阶段文档的 Adapter 升级流程；
        - **不做跨进程分布式锁**：幂等靠台账文件的原子 claim + 追加写，同一部署的多份 Agent 用
          ledger_alias 区分命名空间；跨机器的并发控制属于运行时的存储层，不在本阶段；
        - **不做防篡改审计**：台账是摘要链而不是签名日志，外部锚定属于 Phase 7。

        相关文件：

        - 阶段设计与实施记录：docs/engineering-policy-platform/phases/phase-6-multi-agent-adapters.md
        - 协议与能力声明：src/adapters/models.py、src/adapters/base.py
        - 运行时与套件：src/adapters/runtime.py、src/adapters/conformance.py
        - 三种协议实现：src/adapters/dsh_adapter.py、event_adapter.py、json_adapter.py
        - 数据：adapters/<agent>/（manifest.yaml / adapter.yaml / approved.json）
        - 测试：tests/contract/test_agent_adapters.py、tests/integration/test_multi_agent_runtime.py、
          tests/security/test_multi_agent_adversarial.py

        跑完别忘了清理演示产物：python tools/cleanup.py。
        """),
]


def check_phase_6_structure(namespace: dict[str, Any]) -> list[str]:
    """核对手册里写过的关键结论（生成期断言）。"""

    problems: list[str] = []
    report = namespace.get('report')
    if report is None:
        problems.append('Phase 6 手册没有产生一致性套件报告')
        return problems
    if not report.checks:
        problems.append('一致性套件一项都没跑')
    if report.failures:
        problems.append('一致性套件出现失败: ' + str([item.to_dict() for item in report.failures]))
    if {item.adapter for item in report.checks} != set(report.adapters):
        problems.append('一致性套件报告列出了没有实际检查项的 Adapter')
    if len(report.adapters) < 2:
        problems.append('参加一致性套件的 Adapter 少于两个，退出条件不成立')
    if namespace.get('conformance_result') != 'pass':
        problems.append('一致性套件的结论不是 pass')

    structured = namespace.get('structured')
    if structured is None or structured.response.decision.value != 'block':
        problems.append('链路演示里的违规改动没有被阻断')
    if namespace.get('calls'):
        problems.append('阻断的动作竟然触发了原生工具')

    accepted = namespace.get('accepted')
    if accepted is None or accepted.outcome_code not in ('allow', 'allow_with_warnings'):
        problems.append('dsh 完整写链演示没有真正得到 allow')

    first = namespace.get('first')
    if first is None or first.outcome_code not in ('allow', 'allow_with_warnings'):
        problems.append('隔离演示里的 dsh 写动作没有走完整门禁')

    codes = namespace.get('codes')
    if not codes or 'request_busy' not in codes:
        problems.append('熔断演示没有出现 request_busy')

    loop = namespace.get('payload')
    if not isinstance(loop, dict) or loop.get('result') != 'pass':
        problems.append('多 Agent 闭环没有通过')
    exits = namespace.get('cli_exits') or {}
    if (exits.get('check'), exits.get('matrix'), exits.get('events')) != (0, 0, 0):
        problems.append('适配层 CLI 的正常路径退出码不是 0: ' + str(exits))
    if exits.get('unapproved') != 2:
        problems.append('未审核清单必须以退出码 2 拒绝，实际: ' + str(exits.get('unapproved')))
    if namespace.get('exit_code') != 0:
        problems.append('多 Agent 闭环的退出码不是 0')
    return problems
