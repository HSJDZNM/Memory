# R1 事实核验（Verifier）：F1–F39 / N1–N6 逐条判定

> 角色：事实核验员（共享任务 task-5）。核验窗口：2026-09-22 20:29–20:40（仓库时钟，Get-Date 实测）。
> 判定列只用三个值：**OK / 错 / 无法验证**；证据列区分【实测】（本轮真跑过命令）与【读码】（真的读过源码或数据）。
> 纪律：证据里的每个 file:line 都是我自己打开/搜索到的位置；每条命令都是我自己跑的；核验不了的写【无法验证】，不猜。
> 本文件只做核验，不提设计提案；凡涉及"设计应当如何"的内容一律放最后一节并标注【提案】。

## 0. 核验环境、命令清单与核验边界

环境（实测）：Windows + PowerShell；python 3.13.11；fastapi 0.128.0 / pydantic 2.12.3 / PyYAML 6.0.3（python -c 打印）。
仓库是 src 布局：所有 python -m <pkg> 必须先 $env:PYTHONPATH='src'（README.md:69 写的约定）。
**不设 PYTHONPATH 时 7 个入口全部 ModuleNotFoundError**（本轮实测），因此任何界面/文档给出的命令都不能省这一段。

【实测】只读命令与结论（未运行任何 --write / --approve / --record / cleanup / pytest）：

| # | 命令 | 关键输出 | 退出码 |
| --- | --- | --- | --- |
| 1 | $env:PYTHONPATH='src'; python -B -m policy.check --check-rules --json（20:31） | count=26，identity=sha256:a6c9655a… | 0 |
| 2 | 同上，7 分钟后重跑（20:37:59） | count=45，identity=sha256:dc4e96ac… | 0 |
| 3 | python -B -m policy_api.cli openapi --check | [openapi] 与快照一致（api_version=1.0） | 0 |
| 4 | python -B -m adapters.cli matrix --json | dsh approved=true/enforcement=full；generic-json、legacy-post-only read_only | 0 |
| 5 | 7 个入口 python -B -m <pkg> --help | 子命令清单见 F9 行 | 0（每个） |

核验边界（本轮**没有**做的事，避免读者高估本文件的覆盖面）：
- 没有启动 serve、没有发真实 HTTP 请求（只读纪律）：F7/F12 的运行时行为用契约快照 + 源码 + openapi --check 覆盖，未做端到端探测；
- 没有跑 pytest / tools/ci_local.py（会写 .pytest_cache 与 .tmp）：F21/F24 只做读码 + 步骤名核验；
- **规则集计数是移动靶**：本轮 7 分钟内从 26 变 45（见 F13），任何数字都必须带测量时间与命令。

## 1. F1–F39 逐条判定

| 编号 | 判定 | 证据（实测 / 读码） | 备注与更正 |
| --- | --- | --- | --- |
| F1 | OK | README.md:3-5 逐句对上（独立于具体 Coding Agent 的治理层 / 机器可执行规则 / allow·allow_with_warnings·block / 可重放审计证据） | — |
| F2 | OK | docs/architecture/README.md:8：6 层 × 4 个能力节点，① 消费方/入口 ② 接入与协议转换 ③ 判定核心 ④ 能力层 ⑤ 数据与契约 ⑥ 证据与门禁，层名逐字一致 | — |
| F3 | OK | docs/architecture/功能清单.md:47-60：表 12 行（编号 1–12）+ "主要入口" 列 | r0 引 :45-60，表头在 :47，内容一致 |
| F4 | OK | docs/engineering-policy-platform/README.md:49-57（九阶段状态列）、功能清单.md:35-43（1.1 完成度） | 除两个"未完成项"外还有两类显式**未采纳**：功能清单.md:38（向量检索未采纳）、:40（mypy 端口就位、未启用类型规则）。"完成度"类页面必须把"完成 / 未完成 / 未采纳"三分开 |
| F5 | OK | 功能清单.md:27-29 三条唯一；代码侧：langgraph 只经 import_module 出现在 src/orchestration/langgraph_engine.py:87-88（构造引擎时），src/policy 无 Web 框架导入（contract.py:204-216 是同一检查的另一实现） | — |
| F6 | OK | docs/architecture/术语与口径.md:76 "## §2 编号对照表"，:82-89 台阶 1–7 逐行 | — |
| F7 | OK | contract.py:44-51 ENDPOINTS 六条；app.py:43-47 route_table、:48 _OPS_ROUTES；app.py:295 health/live、:309-310 health/ready；runtime.py:73 ROUTES 六名；api/openapi.json 恰六条 paths（:758 /:779 /:802 /:954 /:985 /:1137）；metrics 限 roles ops 或 service-admin 或 metrics_clients（ops.py:28、:37-43；api/policy-api.yaml:44-45） | 【实测】openapi --check 退出 0 = 快照与代码一致。**但"只有 6 条路由"只对契约与 ROUTES 成立**：ASGI 应用还挂了第 7 个端点 GET /v1/openapi.json（app.py:181 设 openapi_url + fastapi/applications.py:1092 add_route(include_in_schema=False)、无认证依赖）。见遗漏 #2 |
| F8 | OK | 六条路由里没有 enforce / 写路由（同上）；受控写入入口是注册表的 orc.policy.edit（tool-registry.yaml:317） | — |
| F9 | OK | 【实测】7 个入口 --help 全部退出 0，真实子命令：retrieval.cli {index,query,context,verify,stats,rules,quarantine,vector}；enforcement.cli {registry,precheck,execute,approve,trace,verify,self-check}；validators.cli {check,pipeline,registry,probe}；adapters.cli {matrix,approve,check,inspect,events}；policy_api.cli {serve,self-check,openapi,clients,smoke,seal}；orchestration.cli {self-check,graph,status,run}；policy.check **没有子命令**（扁平 flag：--check-rules/--json/--validators/--keep-temp 等） | 备注：src/policy/__main__.py:1 明写 "python -m policy 等价于 python -m policy.check"，即判定 CLI 有两个等价入口；两处都要求 PYTHONPATH=src |
| F10 | OK | tools/ 下 *_loop.py 恰 6 个（glob 实测）：dsh_sandbox_loop / enforcement_loop / validator_loop / agent_loop / api_loop / orchestration_loop；tools/README.md:12-17 恰为这 6 行 | — |
| F11 | OK | grep src 全目录：fastapi 只在 policy_api（app.py:23-25、:27；testing.py:59），uvicorn 只在 serve.py:43；langgraph 只在 orchestration/langgraph_engine.py:87-88（import_module，构造时） | — |
| F12 | OK | api/README.md:55-56 的承诺在 src/policy_api/serve.py:53-56 落地：readiness 不过就打印"拒绝启动"并且走不到 :62 的 uvicorn.run | — |
| F13 | **错** | 【实测 20:37:59】python -m policy.check --check-rules --json → count=**45**、identity=sha256:dc4e96ac…；磁盘 policies/ 45 份 YAML（architecture 1 / coding 23 / security 19 / testing 2）；而 git ls-files policies 只有 6。加载器读文件系统、不读 git：loader.py:196-228（collect_rule_files → load_rules → load_rule_set） | **正确事实**：不是 6 份。ID 全集 = ARCH-001、DOC-001…005、STYLE-001…018、SEC-001…012/014/015/017/018/019/021/022、TESTING-001/002。20:31 实测 26 份（identity sha256:a6c9655a…），20:37 已是 45 份：新增 policies/security/SEC-*.yaml 19 份（mtime 20:35–20:36，全部 untracked，见 git status）。**会议期间有人正在写规则** |
| F14 | OK | knowledge/corpus.yaml、knowledge/query_expansion.yaml 都在 git ls-files；.tmp/retrieval/index.sqlite3（1601536 字节）与 eval-index.sqlite3 实测存在 | 索引是构建产物，且 console 生成器直接读它（build_site.py:221） |
| F15 | OK | registry/tool-registry.yaml:14-16 文件头明写"Phase 8 起这张表按 Agent 分段"；每个工具带 agent 字段（dsh 见 :43-46；orchestrator 见 :293-302 orc.fs.write、:317-345 orc.policy.edit approval: required）；registry/tool-registry.approved.json 存在 | — |
| F16 | OK | validation/ 六个文件实测存在（git ls-files validation）：validators.yaml、project.yaml、test-layout.yaml、ruff.toml、mypy.ini、pytest.ini | — |
| F17 | OK | adapters/{dsh,generic-json,legacy-post-only}/manifest.yaml 三份；adapters/approved.json 三条（:3-15 dsh full、:16-30 generic-json read_only、:31-45 legacy read_only） | 【实测】adapters.cli matrix --json 退出 0：dsh approved=true + enforcement=full；另两个 read_only。**备注**：README.md:15-16 还点名第 4 个合成消费者 http-api，它只在 tools/api_loop.py:287-290 定义、adapters/ 下没有 manifest → "3 个消费者"只对 adapters/ 目录成立 |
| F18 | OK | api/policy-api.yaml 顶层键：limits:18、budgets:26、rate_limit:31、audit:38、metrics_clients:44、tenants:47、clients:80；clients 只存 token_sha256（:84 /:91 /:98） | "六段"不穷尽：还有 idempotency_ttl_seconds:36 与 metrics_clients:44 两段 |
| F19 | OK | tools/cleanup.py:24-31 白名单 + :66 --dry-run；AGENTS.md "临时文件与产物"节 | 白名单比 AGENTS.md 写的多 .mypy_cache/.ruff_cache；pytest 缓存今天在 .tmp/.pytest_cache（pytest.ini:3） |
| F20 | OK | tools/phase_evidence.py:781 默认输出 .tmp/artifacts/phase-<CURRENT_PHASE>-evidence.json；:36-43 汇总 8 个阶段结果文件；tools/README.md:9 的描述与之相符 | 本轮未执行该脚本（会写 .tmp），只做读码 |
| F21 | OK | .github/workflows/phase-8.yml 步骤名实测：:49 规则集自检、:53/:63 AST 重放、:81/:84 验证器注册表、:101/:112 失败关闭、:124 验证器闭环、:139 dsh 沙箱闭环、:143 语料完整性、:162 检索基线、:176 注册表哈希、:184 受控执行闭环、:235 多 Agent 一致性、:239/:243/:247 支持矩阵与事件与闭环、:251/:255/:259/:301 API、:305/:309/:312 编排与阶段证据 | — |
| F22 | OK | tools/ci_local.py:212-216 四个开关（--full / --list / --hook / --python）；AGENTS.md:65-71 明写"GitHub 侧故意不启用规则集/分支保护" | — |
| F23 | OK | 六个脚本都在 tools/（git ls-files 实测）：check_text_conventions、check_repo_consistency、check_notebook、check_arch_canon、check_arch_style、secret_scan | check_notebook.py 在 tools/README.md:22，r0 引的 :23-30 区间不含它（陈述仍成立） |
| F24 | OK | pytest.ini:3-5（cache_dir=.tmp/.pytest_cache、testpaths=tests、markers contract/integration/security）；磁盘 tests/{unit,contract,integration,security,fixtures} 五个目录实测存在 | — |
| F25 | OK | AGENTS.md:151-154（sequence + prev_digest 摘要链、"不是防篡改日志"）、:237-241（seal --out、--verify、锚须分离）；policy_api.cli seal 子命令与 --out/--verify 在 --help 实测；observability.py:392-400 校验锚版本与链末值 | — |
| F26 | OK | designs/ 顶层 5 份 md（可行性评估 / 前端交互逻辑 / 后端契约与连接证据 / 评审意见 / 分块策略对比）+ console/{6 html, README.md, build_site.py, assets/{app.js,style.css,data.js}} + os/meeting/r0-facts.md；git status 显示 ?? docs/engineering-policy-platform/designs/ | data.js 确由生成器写出（build_site.py:607）；"5 份文档"不含本次会议的 os/meeting/ |
| F27 | OK | console/README.md:19-24 六行与磁盘六个 html 文件名逐一对应：index / data / authoring / gates / activation / system | — |
| F28 | OK | build_site.py:162-163 load_rule_set([ROOT/"policies"])、:177 knowledge/corpus.yaml、:188 docs/*/manifest.json、:201 validation/validators.yaml、:213 policy.checkers.SUPPORTED_CHECKERS、:221 .tmp/retrieval/index.sqlite3、:257 policy_api.runtime.ROUTES | 七个来源与 r0 列的完全一致；**该生成器不读任何审批/注册表文件**（见遗漏 #5） |
| F29 | OK | console/README.md:61-64（无写路径 / orc.policy.edit + action_hash / 预演是浏览器内模拟 / 先修 B1 与 B2） | **编号实测存在**：B1、B2 定义在 可行性评估.md:301-302，评审意见.md:14/:18/:97/:115 展开；缺口编号是 **G1–G8**（后端契约与连接证据.md:498、:680；可行性评估.md:178），红线编号是 **R1–R12**（可行性评估.md:97-112，R1 在 :101、R12 在 :112）；原型渲染见 build_site.py:79-101 与 system.html:24/:27/:30。**没有** F/G 混编或其它编号体系 |
| F30 | OK | console/README.md:33-39；键名在代码里也确证：app.js:61 与 :71 读写 localStorage 的 'console.state'；灰按钮见 activation.html:20（disabled + data-tip 说明无路由与替代命令） | — |
| F31 | OK | AGENTS.md:220-224（约束 30 原文）与 F31 逐句一致：传输边界不是第二份业务逻辑 / 判定只有 policy.engine.evaluate 一条路径 / 本地与经 API 的决定整份相等 | — |
| F32 | OK | AGENTS.md:225-228（31：两套版本各自演进）、:229-232（32：租户只来自令牌、客户端不能自带证据或决策、服务身份不替用户扩权）、:233-236（33：超时与服务不可达绝不等于 allow） | 四条陈述各自对得上原文 |
| F33 | OK | AGENTS.md:141-144（13：授权只认结构化记录 + 哈希不一致不可用）、:145-147（14：action_hash 覆盖面 / 短时效单次 / 高风险必须人工审批）、:148-150（15：事后验证必须交证据 / unsupported）、:151-154（16：审计不可写则不执行） | — |
| F34 | OK | AGENTS.md:155-162（17：白名单只做完整匹配 + 结构性阻断组合命令与被禁片段）、:177-180（22：按声明模板调用 / 超时终止整棵进程树 / 输出脱敏限量） | — |
| F35 | **错** | 陈述内容全部出自**约束 24**（AGENTS.md:186-193：能力上限由声明推出 / post_only 上限 read_only / capability_unavailable / 绝不跳过治理） | **引用编号多引 25**：约束 25（AGENTS.md:194-199）讲的是 AgentEvent 是唯一交换协议、agent_id 由装配处钉死、payload 受控字段、路径基准是工作区——与 F35 的三句话没有任何对应。正确引法：约束 24（若要覆盖"事件协议"另引 25） |
| F36 | OK | AGENTS.md:242-247（35：编排层是消费者、唯一框架导入点）、:248-254（36：图状态不放正文、checkpoint 单文件原子替换、凭据比对、不沿用旧 allow）、:255-258（37：分支只由 Decision、终态只由 STATUS_BY_CODE）、:259-262（38：审批绑平台 action_hash）、:263-266（39：写入走 Phase 4 链、NodeContext.commit、side_effect_unknown、幂等两道闸） | 五个编号逐条对上 |
| F37 | **错** | 四个被引编号各自成立：约束 2（AGENTS.md:112-113 规则与语料是数据）、19（:167-169 验证器只产证据不判定）、21（:174-176 验证器注册表与项目档案是数据）、27（:207-211 一致性套件场景是语义描述） | **引用编号不全**：F37 一句话里列了五类数据，其中"工具表是数据"的出处是**约束 13**（:141-144）与 39（:263-264），"能力声明是数据"的出处是**约束 24**（:186-189），两者都不在 2/19/21/27 里。正确引法：2/13/19/21/24/27 |
| F38 | OK | AGENTS.md:117-118（5：相同输入相同结论、violation 按 rule_id 稳定排序、RuleSet.identity 与加载顺序无关）、:119（6：上下文只接受显式字段，不得按文件名/目录/用户消息推断） | — |
| F39 | OK | 约束 3（AGENTS.md:114-115 未知字段/枚举/scope/操作/checker/协议版本一律报错）、20（:170-173 关键验证器不可用失败关闭 + "解析失败"不等于"没有依赖"）、33（:233-236 未知 api_version/未知字段/未知操作枚举全部结构化错误码） | 33 的对应点是"未知一律报错"在 API 层的实例，与前两条不重叠但成立 |

## 2. N1–N6 逐条判定

| 编号 | 判定 | 证据（实测 / 读码） | 备注与更正 |
| --- | --- | --- | --- |
| N1 | OK | 【实测】git ls-files 里 package.json 命中 **0**；git ls-files 的 .js/.html/.css 命中也是 0（只剩 .json 数据文件） | 磁盘上确有 326 个 package.json，但**全部在 .tmp/ 下**（外部工具产物、gitignored），不影响"仓库无前端工程"的判定 |
| N2 | OK | 文档转规则操作平台-前端交互逻辑.md:73 标题逐字："## 3. 草稿规则生命周期状态机【提案：草稿存储今天不存在】" | — |
| N3 | OK | docs/engineering-policy-platform/README.md:39 记"无 CORS、只能同源"；src/policy_api 全目录搜 CORS / cors / middleware / add_middleware **0 命中**（即没有任何中间件，也没有 CORS 配置）；六条路由无写路由 | 原型的连接自检会去探测响应里的 access-control-allow-origin（app.js:407），那是"验证不存在"，不是后端能力 |
| N4 | OK | 审批是文件 + 结构化记录：enforcement/approvals.py:70 load_approval、:90 verify_approval；enforcement.cli 有 approve 子命令；六条路由里没有任何"待审批列表/审批中心" | 与 AGENTS.md:259-262 的"找到的审批文件原样交给 pre-check 复验"一致 |
| N5 | OK | 前端交互逻辑.md:21-31 列出今天真实存在的三个身份；api/policy-api.yaml:80-101 三个 client（local-dev / dsh-agent / ops-monitor），roles 只有 developer 与 ops | **一处口径不齐**：ops.py:28 的 METRICS_ROLES 还含 service-admin，而配置文件里没有任何 client 声明该角色 → "角色枚举只有 developer 与 ops"对配置成立、对代码常量不成立（见遗漏 #8） |
| N6 | OK | 功能清单.md:41（Phase 6 第二真实 Agent 待外部环境）、:43（Phase 8 真实模型作者未接入）；README.md:15-17 同口径；AGENTS.md:5-6 仓库现状段 | — |

## 3. 详细核验记录（本节的每条都对应上表的一行；上表是结论，这里是过程）

### 3.1 F7：六条路由与方法、metrics 的访问限制（逐条）

- 契约里的六条（唯一真相源 contract.py）：
  - POST /v1/policy/evaluate → 运行时名 evaluate（contract.py:45；app.py:210-213 add_api_route(methods=["POST"])，:262-265）；
  - POST /v1/knowledge/retrieve → retrieve（contract.py:46；app.py:216-218）；
  - POST /v1/validation/evaluate → validate（contract.py:47；app.py:222-225）；
  - GET /v1/health/live → live（contract.py:48；app.py:295 @app.get）；
  - GET /v1/health/ready → ready（contract.py:49；app.py:309-310）；
  - GET /v1/ops/metrics → metrics（contract.py:50；app.py:281-284 add_api_route(methods=["GET"])）。
- runtime.py:73 ROUTES = ("evaluate","retrieve","validate","health","readiness","metrics")，六个运行时名与上表一一对应（health 两条共用一个运行时名段）。
- 预算路由只有三条：contract.py:52 BUDGET_ROUTES = ("evaluate","retrieve","validate")。
- 契约快照自洽：【实测】python -B -m policy_api.cli openapi --check → "[openapi] 与快照一致（api_version=1.0）"、退出 0；api/openapi.json 的 paths 恰六条（:758 health/live、:779 health/ready、:802 knowledge/retrieve、:954 ops/metrics、:985 policy/evaluate、:1137 validation/evaluate）。
- metrics 的访问限制（三层，全部读码）：
  - runtime.py:810-813 先取 ops.metrics_token_ok(config, auth)，不通过抛 METRICS_FORBIDDEN（:815，不透露资源是否存在）；
  - ops.py:28 METRICS_ROLES = ("ops", "service-admin")；:40 角色交集命中即放行；
  - ops.py:42-43 否则要求 auth.client_id 落在 config.metrics_clients 里；
  - 配置侧：api/policy-api.yaml:44-45 metrics_clients: [ops-monitor]；:96-101 ops-monitor 的 roles: [ops]。
  - 反向确认：api/policy-api.yaml:81-87 的 local-dev 是 developer 角色且不在 metrics_clients → 按代码只能拿到 403 METRICS_FORBIDDEN（本轮**没有**发 HTTP 请求，属读码推断）。
- 第 7 个端点（上表 F7 备注）：app.py:181 设 openapi_url="/v1/openapi.json"；FastAPI 0.128 在应用启动时注册该路由（site-packages/fastapi/applications.py:1092 add_route(self.openapi_url, openapi, include_in_schema=False)），没有依赖注入、也不经过 app.py:185 的 handle_route（那里才解析 Authorization）。所以它不在 ENDPOINTS 的六条里，但进程上确实可达。

### 3.2 F9：七个入口的真实子命令（--help 实测，全部退出 0）

| 入口 | 真实子命令（raw 输出摘要） | 备注 |
| --- | --- | --- |
| python -m policy.check | 无子命令；扁平 flag：file（位置参数）、--rules、--dependencies、--layer、--language、--module、--project、--agent、--task、--request-id、--trace-id、--operation、--workspace、--config-root、--changed、--validators、--json、--check-rules、--keep-temp | src/policy/__main__.py:1 明写与 python -m policy 等价 |
| python -m retrieval.cli | index / query / context / verify / stats / rules / quarantine / vector | 全局 --root/--corpus/--db/--json |
| python -m enforcement.cli | registry / precheck / execute / approve / trace / verify / self-check | 无全局参数 |
| python -m validators.cli | check / pipeline / registry / probe | --changed-from-git、--show 等 |
| python -m adapters.cli | matrix / approve / check / inspect / events | --allow-unapproved 明确只用于审核前本地检查 |
| python -m policy_api.cli | serve / self-check / openapi / clients / smoke / seal | --check 与 --write 只作用于 openapi |
| python -m orchestration.cli | self-check / graph / status / run | run --engine {auto,reference,langgraph} |

- 不加 PYTHONPATH=src 时七条全部 ModuleNotFoundError（实测），这是任何界面"复制命令"功能必须带上的前缀。

### 3.3 F10：闭环脚本

- 磁盘实测（glob tools/*loop*.py）恰 6 个：dsh_sandbox_loop.py、enforcement_loop.py、validator_loop.py、agent_loop.py、api_loop.py、orchestration_loop.py。
- tools/README.md:12-17 是这 6 个的说明，逐行对上；其中 :16 的 orchestration_loop、:12 的 dsh_sandbox_loop 会写 .tmp/artifacts 下的结果文件（phase_evidence.py:37-43 读回它们）。
- 另有 api_loop.py:287-290 定义的第 4 个协议消费者 http-api（见 3.5）。

### 3.4 F13：规则集实测与时间线（本文件最重要的一条）

- 时间线（同一命令、同一工作目录）：
  - 20:31 python -B -m policy.check --check-rules --json → rule_set.count = 26，identity = sha256:a6c9655aac58c8a34bdcb5009fed785719e7cd399c2f41d2fcf2ff86e3984073，退出 0；
  - 20:35–20:36 磁盘出现 policies/security/SEC-*.yaml（19 份，LastWriteTime 实测）；
  - 20:37:52 目录计数：policies 下 YAML 45 份，子目录 architecture 1 / coding 23 / security 19 / testing 2；
  - 20:37:59 重跑同一命令 → count = 45，identity = sha256:dc4e96ac1d631186ea80ab858d1f75737a9c407c1559c12c43f3d965eb285786，退出 0。
- git 侧：git ls-files policies = 6 行；git status 显示新增规则均为 untracked（policies/security/ 整个目录、policies/coding/DOC-002…005、STYLE-003…018）。**r0 的"现 6 份"极可能来自 git ls-files，而不是 loader。**
- 为什么以 loader 为准：loader.py:196-210 load_rules 用 collect_rule_files(root) 列目录（读文件系统），:213-228 load_rule_set 把多个根目录的规则合并、按 repo_path 排序、assert_unique 拒绝重复 ID；任一文件损坏都在返回前抛错（:181-191 RuleFileError），因此"原子加载"成立（AGENTS.md:116 的约束 4）。
- ID 全集（实测输出）：ARCH-001@1；DOC-001@1…DOC-005@1；STYLE-001@1…STYLE-018@1；SEC-001@1…SEC-012@1、SEC-014@1、SEC-015@1、SEC-017@1、SEC-018@1、SEC-019@1、SEC-021@1、SEC-022@1；TESTING-001@1、TESTING-002@1。
- 规则形态抽样（policies/security/SEC-001.yaml:1-30）：头部引用 OWASP 原文，:17 id、:18 version、:21-23 scope/severity=error、:24-26 enforcement(checker: style_lint)、:27-30 rule.style_lint.tool=ruff + codes [S102, S307] —— 与功能清单.md:49-60 的"规则是 YAML 数据"口径一致。

### 3.5 F17：三个适配器与"真实产品"

- 声明文件：adapters/dsh/manifest.yaml、adapters/generic-json/manifest.yaml、adapters/legacy-post-only/manifest.yaml（git ls-files 实测，各配 adapter.yaml 与 fixtures）。
- 审核记录：adapters/approved.json 三条，字段含 agent_version / enforcement / manifest_digest / protocol / protocol_version / requested_enforcement；dsh 是 enforcement=full（:6）且 protocol=canonical-tool-table（:12）。
- 【实测】python -B -m adapters.cli matrix --json（退出 0）三条事实：dsh approved=true、enforcement=full、pre_hook/post_hook declared=true；generic-json approved=true、enforcement=read_only、ceiling_reasons 只有"Adapter 主动把上限收紧到 read_only"；legacy-post-only approved=true、enforcement=read_only、blocking=post_only、pre_hook declared=false。
- "只有 dsh 是真实产品"的旁证：dsh 的 agent_version=0.1.5-rc.1（approved.json:4，真实产品版本号），另两个是 third-party-0.9.0 与 legacy-agent-2.4.7（合成夹具版本号）。
- 口径边界：README.md:15-16 把"generic-json、legacy-post-only 与 Phase 7 的 http-api"并列为合成协议消费者，而 http-api 只存在于 tools/api_loop.py:287-290（HttpApiAdapter，agent_id="http-api"），adapters/ 下没有它的 manifest 与审核条目。

### 3.6 F26–F30：既有 designs 资产（含编号体系的实测）

- 目录实测（17 个文件，全部 untracked）：
  - 5 份设计文档（顶层 md）：可行性评估（40048B）、前端交互逻辑（49382B）、后端契约与连接证据（78963B）、评审意见（25711B）、分块策略对比（23913B）；
  - console/：6 个 HTML（index 3730B / data 25923B / authoring 6106B / gates 3949B / activation 3266B / system 8382B）、README.md（3324B）、build_site.py（34981B）、assets/style.css（7096B）、assets/app.js（19766B）、assets/data.js（560912B，生成产物）；
  - os/meeting/r0-facts.md（本次会议基线）。
- 六页与覆盖范围：console/README.md:19-24 的表格逐行对上文件名；页面标题也写在生成器里（build_site.py:33-38 的六元组 index/data/authoring/gates/activation/system）。
- F28 的七个数据来源逐一确证（见上表）；build_site.py:607 用 write_page("assets/data.js", "window.CONSOLE_DATA = " + json.dumps(...)) 生成数据文件，:596 写 HTML，:58 的说明也写明"assets/style.css、assets/app.js 手写、不生成"。
- 编号体系（r0 要求核验的部分）：
  - B1 / B2：定义在 可行性评估.md:301（B1 新建规则文件无需人工审批，给出 nodes.py:93-97 与 tool-registry.yaml:293-315）与 :302（B2 漂移静默：runtime.py:679 硬编码 []）；展开在 评审意见.md:14/:18/:97/:115/:197-203；原型展示在 build_site.py:118-121 与 index.html:21。
  - 缺口编号是 **G1–G8**：定义见 后端契约与连接证据.md:498（G1 语料与镜像状态读取）到 :680（G8 任务模型，明确"建议暂不新增"）；另有 可行性评估.md:178 的缺口清单概述；原型渲染 build_site.py:79-86、system.html:27。
  - 红线编号是 **R1–R12**：定义见 可行性评估.md:97（"## 4. 设计红线（不变量）"）表内 :101（R1 判定只有一条路径）到 :112（R12 不引入 LLM 判定）；原型渲染 build_site.py:90-101、system.html:30。
  - 结论：r0 里出现的 B1/B2 与"缺口/红线"都真实存在；**没有**第二套 F 编号或 G/R 混编。
- F30 的交互约定在代码里可验证：localStorage 键在 app.js:61（getItem）与 :71（setItem），键名 'console.state'；灰按钮见 activation.html:20（disabled + data-tip 写明"没有写路径，真实提交必须走 Phase 4 受控执行链"）；悬停提示由 data-tip 属性驱动（system.html:18 的标签页与 data.html:20 的缺口提示）。

### 3.7 F31–F39：与 AGENTS.md 原文的逐条比对表

| r0 编号 | 引用的约束号 | AGENTS.md 原文行号 | 比对结论 |
| --- | --- | --- | --- |
| F31 | 30 | 220-224 | 一致（三个断言都在原文里） |
| F32 | 31 / 32 / 33 | 225-228 / 229-232 / 233-236 | 一致（四条断言各自可指到原文句子） |
| F33 | 13 / 14 / 15 / 16 | 141-144 / 145-147 / 148-150 / 151-154 | 一致 |
| F34 | 17 / 22 | 155-162 / 177-180 | 一致 |
| F35 | 24 / 25 | 186-193 / 194-199 | **错**：三句内容全出自 24；25 讲 AgentEvent 协议，无对应内容 |
| F36 | 35 / 36 / 37 / 38 / 39 | 242-247 / 248-254 / 255-258 / 259-262 / 263-266 | 一致（含 side_effect_unknown、NodeContext.commit） |
| F37 | 2 / 19 / 21 / 27 | 112-113 / 167-169 / 174-176 / 207-211 | **错**：四号本身成立，但句子里的"工具表是数据"=13（141-144）、"能力声明是数据"=24（186-189）未被引用 |
| F38 | 5 / 6 | 117-118 / 119 | 一致 |
| F39 | 3 / 20 / 33 | 114-115 / 170-173 / 233-236 | 一致（33 提供"未知一律结构化报错"的 API 实例） |

### 3.8 N1–N6 的细节

- N1：【实测】git ls-files 全量里搜 "package.json" 命中 0 行；搜 .js/.html/.css/.ts/.vue 命中 0 行（只剩 .json 数据文件）。磁盘上的 326 个 package.json 全部落在 .tmp/ 下（分组统计：.tmp = 326，其余 = 0）。
- N2：前端交互逻辑.md:73 是章节标题本身带【提案】标记，且 :79 起是 D0–Dn 状态机的门禁表 —— "今天不存在"是作者自述，不是本文推断。
- N3：在 src/policy_api 全目录搜 CORS / cors / middleware / add_middleware 四项，**0 命中**；六条路由（3.1）没有写路由；engineering-policy-platform/README.md:39 的"无 CORS、只能同源"是实测结论的转述。
- N4：src/enforcement/approvals.py 的函数只有 load_approval(:70) / verify_approval(:90) / approval_payload(:131) 等文件级操作，没有服务端查询接口；六条路由里也没有审批相关路径。
- N5：api/policy-api.yaml:81-87 / :89-94 / :96-101 三个 client；roles 取值只有 developer 与 ops；token_sha256 是唯一凭据形态（原文见 :84 注 sha256("local-dev-token")）。
- N6：功能清单.md:41 与 :43 的状态列就是"待外部环境 / 未接入"两处，与 README.md:15-17、AGENTS.md:5-6 同口径。


### 3.9 原始输出摘录（供复核；均可在本机只读重跑）

A) 规则集（20:37:59，$env:PYTHONPATH='src'; python -B -m policy.check --check-rules --json）：

    "rule_set": {
      "count": 45,
      "identity": "sha256:dc4e96ac1d631186ea80ab858d1f75737a9c407c1559c12c43f3d965eb285786",
      "ids": ["ARCH-001@1", "DOC-001@1", ... "SEC-012@1", "SEC-014@1", "SEC-015@1",
              "SEC-017@1", "SEC-018@1", "SEC-019@1", "SEC-021@1", "SEC-022@1",
              "TESTING-001@1", "TESTING-002@1"],
      "schema_version": "1.0",
      "sources": ["policies/architecture/ARCH-001.yaml", ... "policies/security/SEC-022.yaml",
                  "policies/testing/TESTING-001.yaml", "policies/testing/TESTING-002.yaml"]
    }
    EXITCODE=0

B) 同一命令在 20:31 的输出（同一台机器、同一目录，仅相隔约 7 分钟）：

    "count": 26,
    "identity": "sha256:a6c9655aac58c8a34bdcb5009fed785719e7cd399c2f41d2fcf2ff86e3984073",
    EXITCODE=0

C) 契约快照（python -B -m policy_api.cli openapi --check）：

    [openapi] 与快照一致（api_version=1.0）
    EXITCODE=0

D) 适配器矩阵（python -B -m adapters.cli matrix --json，节选）：

    dsh               approved=true  enforcement=full       blocking=pre_execute
                      ceiling_reasons=[]  manifest_digest=sha256:e3adea73...
    generic-json      approved=true  enforcement=read_only  ceiling_reasons=["Adapter 主动把上限收紧到 read_only"]
    legacy-post-only  approved=true  enforcement=read_only  blocking=post_only  pre_hook.declared=false
    EXITCODE=0

E) 缺 PYTHONPATH 时的失败形态（任何一个入口都一样）：

    python : ... Error while finding module specification for 'policy.check'
    (ModuleNotFoundError: No module named 'policy')
    EXITCODE=1

F) 七个入口 --help 的子命令行（原样摘抄）：

    retrieval.cli    {index,query,context,verify,stats,rules,quarantine,vector}
    enforcement.cli  {registry,precheck,execute,approve,trace,verify,self-check}
    validators.cli   {check,pipeline,registry,probe}
    adapters.cli     {matrix,approve,check,inspect,events}
    policy_api.cli   {serve,self-check,openapi,clients,smoke,seal}
    orchestration.cli {self-check,graph,status,run}
    policy.check     无子命令（扁平 flag）
    EXITCODE=0（七条全部）


## 4. 判定汇总

| 判定 | 数量 | 编号 |
| --- | --- | --- |
| OK | 42 | F1–F12、F14–F34、F36、F38、F39、N1–N6 |
| 错 | 3 | F13（规则数 6 → 实测 45）、F35（多引约束 25）、F37（漏引约束 13 与 24） |
| 无法验证 | 0 | — |

补充说明（避免"0 条无法验证"被读成"全部端到端验证过"）：
- 三条**错**都属可判定的硬事实，不是措辞口味：F13 差 39 份规则、F35 与 F37 是可逐行比对的编号引用；
- F4/F20/F21/F24 的"完成/通过"来自文档与 CI 步骤清单，本轮**没有**跑 pytest 与 ci_local，因此它们是读码级结论，不是实测级结论；
- F7 的 6 条路由有双重证据（契约快照 + openapi --check 实测），但"运行时还多一个未认证端点"这一点只在源码级确证（见遗漏 #2）。

## 5. 需要 Lead 注意的四个点（按影响排序）

1. **F13 的规则集是移动靶，任何硬编码都会当天过期。** 7 分钟内 26 → 45，且 45 份里 39 份 untracked（git ls-files 只有 6）。OS 设计里凡出现"规则数量 / 规则 ID 列表 / 规则集哈希"的地方，都必须写成"从 API 或 CLI 现算"，并规定取不到时不显示数字。附带风险：CI 只看到已提交的 6 份，本地 loader 看到 45 份——**同一台机器上"门禁绿的规则集"与"运行期加载的规则集"不是同一份**。
2. **最高红线今天已经有一个既成违反点**：原型 app.js:197-198 在浏览器里按 severity 推出 block / allow_with_warnings，:265-272 用 level==='no' 计数判"预演通过"。判定表在核心是 policy/models.py:184 与 :984-999，唯一路径是 policy/engine.py:109-167。原型自己的注释说这是"浏览器内模拟"，但代码真的在算结论——OS 设计要么把它改成调用后端，要么显式写成风险与禁用条款，不能沉默保留。
3. **"6 条路由"作为路由表真相源会漏项**：/v1/openapi.json 无认证可达（app.py:181 + fastapi/applications.py:1092）。如果路由页/缺口页要展示"今天有什么 HTTP 面"，必须把它算进去，并明确它是未认证的。
4. **B1 未修之前，"审批"板块是装饰**：新建规则文件的整文件写入走 orc.fs.write（tool-registry.yaml:293-302，approval: none），只有以 old_string 片段替换改 policies/ 才走 orc.policy.edit（approval: required，:317-345）；判据是 src/orchestration/nodes.py:93-97 的 tool_id 属性。任何"提交 → 审批 → 生效"的流程，如果不先修这条，页面上的审批闸门与真实写入路径是两回事。

## 6. r0 之外的重要遗漏（读码发现，最多 8 条）

1. **规则集分叉**：本地 live 规则集 45 份（loader 读盘）vs 已提交 6 份（git ls-files policies）；新增的 19 份在 policies/security/ 下、带 OWASP 原文引用（policies/security/SEC-001.yaml:1-30），并且 ID 有空洞（SEC-013 / 016 / 020 不存在）。任何"ID 连续生成"或"以 git 为真相源"的设计与现状冲突。证据：F13 行的实测 + policies/security/SEC-001.yaml:17。
2. **未认证的第 7 个端点**：GET /v1/openapi.json 由 FastAPI 自动注册（app.py:181、fastapi/applications.py:1092，include_in_schema=False，无依赖注入），docs_url / redoc_url 已关但它开着。对"界面能不能不带令牌拿 schema"是个决定性事实。
3. **界面层已有第二份判定**：见第 5 节第 2 点（app.js:197-198、:265-272 对 policy/models.py:984-999）。
4. **API 的漂移字段恒为空**：src/policy_api/runtime.py:679 写死 "hash_drift": []，而 AGENTS.md:139-140 要求漂移不许静默（retrieval.cli verify 退出 1 才是真算的那条）。任何用 retrieve 响应当"漂移状态"数据源的页面都会把"未核对"显示成"无漂移"。
5. **生成器不读审批/注册表数据**：build_site.py 读规则集、语料、镜像 manifest、validators.yaml、索引库、ROUTES（:162-:257），但不读 registry/tool-registry.approved.json 与 adapters/approved.json。今天"能力与审批状态"在页面上**没有数据源**，只能靠 hard-code（build_site.py:79-101 就是硬编码的 G/R 列表）。
6. **两个"已审核"真相源不一致**：adapters/approved.json:18-21 存档的 ceiling_reasons 仍写着"manifest 与已审核哈希不一致或尚未审核"，而运行期实测（adapters.cli matrix --json）generic-json 的 approved=true、ceiling_reasons 只剩 1 条。谁在页面上代表"审批状态"，必须在设计里指定一个来源。
7. **"设置即能力"的假象**：policies/security/ 的 19 份规则今天是否可判定，取决于它们的 checker 有没有验证器供证——注册表侧只有 validation/validators.yaml（build_site.py:201）；OS 设计里"规则已生效"必须由 policy.engine.evaluate 的实际结论（matched / skipped）支撑，不能由"文件在目录里"推出。
8. **角色枚举只能来自配置、不能来自代码常量**：ops.py:28 METRICS_ROLES = ("ops", "service-admin")，但 api/policy-api.yaml:80-101 的三个 client 只声明 developer 与 ops。界面上任何"角色/权限"选择器若从代码常量取，会给出一个今天无人拥有的角色。

## 7. 事实引用（本文件新增、可被后续轮次引用）

- V1【实测】live 规则集 = 45 份、identity=sha256:dc4e96ac…（2026-09-22 20:37:59，`python -m policy.check --check-rules --json`）；20:31 为 26 份 / sha256:a6c9655a…。（修正 F13）
- V2【实测】`python -m policy_api.cli openapi --check` → 与快照一致，退出 0（api/openapi.json 与代码同源可信）。
- V3【实测】`python -m adapters.cli matrix --json` → 3 个协议消费者，只有 dsh 是 enforcement=full。
- V4【读码】ASGI 实际挂 7 个端点（6 条契约路由 + 未认证 GET /v1/openapi.json）。
- V5【读码】原型在浏览器里算 block / allow_with_warnings（第二份判定的既成事实）。
- V6【读码】runtime.py:679 的 hash_drift 恒为 []（与 AGENTS.md:139-140 冲突）。
- V7【读码】B1 的判据在 src/orchestration/nodes.py:93-97：old is None 时 tool_id = orc.fs.write（approval: none）。
