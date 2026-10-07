# OpenCodeReview 全量审查报告（Memory / Engineering Policy Platform）

> 工具：open-code-review (ocr) v1.12.12，委托模式（delegate）。OCR 负责确定性工程（文件选择 `ocr scan --preview` + 规则解析 `ocr delegate rule`）；
>
> 评审由 32 个独立评审子会话（各自约 35% 上下文）执行，另有 2 个复核子会话对 high/medium 做对抗性复核。

## 1. 覆盖（OCR 的选择，不是本次裁剪）

| 项 | 值 |
| --- | --- |
| 扫描范围（仓库文件，含未跟踪、遵守 .gitignore） | 863 |
| 可审文件（will_review=true） | 291 |
| 被排除 | 572 |
| 可审代码行数 | 118922 |
| 评审包 / 评审子会话 | 32 |
| 逐文件登记（reviewed 或 skipped） | 291 / 291，自检 0 缺失 |

排除原因（OCR 内置默认，非本次裁剪）：

- `unsupported_ext` 345：.md 340、.txt 3、.in 1、.lock 1 —— OCR 不审 Markdown 等扩展名；
- `default_path` 226：`tests/**` 223（`**/test_*.py`、`**/fixtures/**` 等默认排除）、`adapters/**/fixtures` 3；
- `too_large` 1：`evaluation/results/fidelity-<hash>.json`（26,566 行，构建产物）。

## 2. 复核后的结论分布

| 严重级别 | 条数 |
| --- | --- |
| critical | 0 |
| high | 9 |
| medium | 58 |
| low | 97 |

复核范围：14 条 high 全部 + medium 抽样 11 条；立场是默认结论为错、去代码里找反证。结果 `confirmed 17` / `partial 8` / `refuted 0` / `unverifiable 0`。
被降级的 7 条（事实成立、级别被夸大）已按修正后级别归位：

- `src/adapters/base.py:205` high → **medium**：事实核对无误：base.py:211-214 把 ** 一律编成 .*，按源码重算 **/*.md → ^.*/[^/]*\.md$（README.md=false、manage.py=false），而 src/validators/globs.py:36-39 与 src/adapters/dsh/adapter.p…
- `src/adapters/wiring.py:2231` high → **medium**：2231-2235 确实以尾随逗号收尾，note 成了 1 元组；_Governs 是普通 frozen dataclass（wiring.py:2147-2161，note: str 无运行时校验），to_dict（:2179）会把元组原样写进 JSON，其余三个分支都是字符串——这些属实。修正：该分支要求同一通道有…
- `src/policy_api/contract.py:261` high → **medium**：事实核对无误：contract.py:21 只导入 STATUS_BY_CODE/ErrorCode，ApiError 全文件仅在 :261 的 raise 出现（grep 确认无别的绑定），CLI 走 cli.py:183-196 → _tenant_for_token(:252-261) 时抛 NameError，…
- `tools/governance_eval.py:3416` high → **medium**：事实核对无误：:3400 `baseline_path = Path(args.check or args.baseline)` 让 --check 与默认 --baseline 共用一条读取路径，:3416-3428 在文件不存在时只写 action="missing" + hint、不改 payload['resu…
- `tools/phase_evidence.py:139` high → **medium**：139 行确实硬编码 "0.1.5-rc.1"，而 adapters/dsh/manifest.yaml:21、adapters/approved.json:4、adapters/host-versions.observed.json:10 都是 0.1.6-alpha.2，同一 dict 的 hook_bridge(…
- `docs/mirrors/owasp-cheatsheets/manifest.json:32` medium → **low**：解析实测属实：124 篇文档共 174 条 crosswalk.asvs，26 条以 ':' 结尾（V15.1:、V7: 等），根因确为 tools/owasp_cheatsheets/04_index.py:21 的 s["title"].split()[0] 未剥标点。但 src/ 与 tools/ 中没有任何代码…
- `src/orchestration/checkpoint.py:235` medium → **low**：代码事实成立：:237-254 的 revalidate 分支直接 return，update 里没有 approvals，于是 rule_set_hash/index_version 与 tool_schema_hash 同时变化时 :255-267 的 REAPPROVE 清理不可达（tests/unit/test…

类别分布：bug 102 / maintainability 32 / documentation 17 / security 6 / performance 4 / test 3

## 3. 高优先级（复核后）（9 条）

### `adapters/dsh/adapter.yaml:13-24` · bug · 已复核：成立

层的声明顺序把测试文件判成了生产层：`**/*_controller.py`（第 14 行）与 `**/*_repository.py`（第 18 行）先于 `**/*.py` 命中，而这份 Phase 6 的 adapter 配置（以及它们的模型 src/adapters/base.py::AdapterConfig）没有、也不接受 test_paths / test_layer，于是 tests/test_shipment_controller.py 在运行时路径上 layer=controller、tests/unit/test_order_repository.py layer=repository，而同一文件在平台路径（policy.check，§49 的唯一口径）是 layer=test（layer_source=platform_test_layout）。同一个文件两条路径两个层，正是 AGENTS §41 记的 M1 缺陷（生产层规则罩住测试文件，ARCH-001 会把测试里的真实装配对象图判成违规），§49 明确要求不许出现。改法：在 layers 顶部显式加 `- pattern: "tests/**/*.py"` / `layer: test`（并让 base.AdapterConfig 也支持加载期自证）。adapters/generic-json/adapter.yaml:10-21 与 adapters/legacy-post-only/adapter.yaml:13-21 是同一份写法、同一个问题。

> 证据：layers: `**/*_controller.py` -> controller 在 `**/*.py` -> module 之前；实测 layer_for('tests/test_shipment_controller.py')='controller'，平台 resolve_layer 同路径返回 ('test','platform_test_layout')

> 复核：读了 adapters/dsh/adapter.yaml:13-24、src/adapters/base.py:133-221/381-396、validation/test-layout.yaml:21-23、src/policy/check.py:328-352，并按其源码重算了正则：base._compile_glob 下 tests/test_shipment_controller.py 命中 **/*_controller.py（排在 **/*.py 之前）→ layer=controller，tests/unit/test_order_repository.py → repository；同路径在 policy.chec…

### `docs/project/architecture/tech-detail/01-判定核心-Policy-Engine/01-判定核心-Policy-Engine.ipynb:34-786` · test · 已复核：成立

被审查的这份 .ipynb 带着 Jupyter 运行痕迹，已与内容源 cells.py 脱钩（工作区改动，未提交：git diff HEAD 为该文件 +170/-21）：单元 1/3/5/7/9/11 的 outputs 非空、execution_count 为 1–6，metadata 被写成编辑器形态（kernelspec.display_name="base"、language_info.version="3.13.11" 等）。生成器的规范形态是 execution_count 恒为 null、outputs 恒为 []、metadata 只含固定五项（build_notebooks.py 的 KERNELSPEC / build_notebook）；HEAD 里的版本正是规范形态，说明脏态是本次未提交的本地改动。后果是两处门禁都会红：CI 与 ci_local 的 "Tech-detail notebooks are in sync"（build_notebooks.py --check 逐字节比对，实测该文件 ipynb_match=False），以及 tools/check_repo_consistency.py 的 check_notebook_form（实测报出本文件 12 条痕迹项）。修法：git checkout -- 该文件（单元内容与规格仍逐字相同，无需改 cells.py），或重新生成。

> 证据：34/37: "execution_count": 1, "outputs": [ / 772/786: "display_name": "base", ... "version": "3.13.11" —— 而生成器写出的形态是 execution_count: None、outputs: []、metadata 仅 kernelspec/language_info 五项

> 复核：逐行核对 01-...ipynb:34/37（"execution_count": 1、outputs 非空）与 :772/786（display_name "base"、language_info 多出 codemirror_mode/nbconvert_exporter/pygments_lexer + version 3.13.11）；grep 数出 6 个代码单元 execution_count=1..6、6 个 output_type 块（check_repo_consistency.py:257-266 会按 outputs/execution_count 各报一条 = 结论里的 12 条）。生成器规范形态见 build…

### `docs/project/architecture/tech-detail/08-单条规则-从文档到判定/08-单条规则-从文档到判定.ipynb:36-39` · documentation · 已复核：成立

这份 .ipynb 是被 Jupyter「运行并保存」过的产物，不是生成器的输出：8 个代码单元全部带 execution_count（1/3/4/5/6/7/8/9）与 stdout outputs（第 36、39、124、127、196、199、286、289、385、388、481、484、592、595、721、724 行），metadata 也从生成器的 kernelspec.display_name="Python 3" 变成 "base"，language_info 多出 codemirror_mode/nbconvert_exporter/pygments_lexer/version 3.13.11 四个键（第 920-936 行）。而 build_notebooks.build_notebook 明确「生成器只写代码与说明，不写运行痕迹：execution_count 与 outputs 永远为空」，同一目录的 .py 与 cells.py 也确实是干净形态——也就是说这份产物与内容源已经不一致：CI 的 `python docs/project/architecture/tech-detail/build_notebooks.py --check`（.github/workflows/phase-8.yml:240）是逐字节比较，必然报「08-单条规则-从文档到判定.ipynb 与内容源不一致」；本地 tools/check_repo_consistency.py 的 check_notebook_form() 也会按「第 N 个单元带执行输出」/「execution_count 不为空」各报 8 处漂移（仓库里 01、08 两章有同样问题，其余八章干净）。附带副作用：第 735 行的 stdout 把本机绝对路径写进了仓库——`store error: 索引库不存在: c:\Users\ZNM\Downloads\Memory\.tmp\tech…`。改法：重新生成产物（`python docs/project/architecture/tech-detail/build_notebooks.py --only 08`）并提交，之后不要在 Jupyter / VS Code 里运行这份 notebook 后保存。

> 证据：第 36-39 行："execution_count": 1, … "outputs": [ …；第 921 行 "display_name": "base"；第 735 行输出含 c:\Users\ZNM\Downloads\Memory\.tmp\tech…

> 复核：08-...ipynb:36/39（execution_count 1、outputs 非空）、:735（stdout 里写进绝对路径 c:\Users\ZNM\Downloads\Memory\.tmp\tech…）、:921（display_name "base"）逐项属实；grep 数出 8 个代码单元 execution_count=1,3,4,5,6,7,8,9、8 个 output_type 块，与结论完全一致，git diff --numstat 为 +236/-27（未提交）。门禁同 P27：build_notebooks.py:233-238/354-364 与 .github/workflows/phase-8.…

### `src/orchestration/client.py:369-386` · bug · 已复核：成立

「平台没能查」被翻译成「代码有违规」：_violations_from 只把 evidence.value 搬进 ViolationRef.evidence_value，把 evidence.detail 整段丢掉，而 models.decision_reason 用的正是 `evidence_value in {"uncovered_checker","blocker"}`（models.py:279）。判定侧这两个通道写的是：uncovered_checker_violation → value=checker 名、detail="uncovered_checker"（src/policy/checkers.py:413）；blocker_violation → value=验证器 status、detail=reason（同文件 395-400）。于是真实载荷里这两类 critical 阻断永远被判成 policy_violation，repair 节点按「可修」去规划并改动文件，而 nodes.py:518-520 明确要求这类必须停在 BLOCKED、不产生任何 Change（H1/R3）；同时 ValidationSummary 的 reason_code 会被写错并进 checkpoint。现有用例只用 evidence_value="blocker" 手工构造（tests/unit/test_orchestration_repair_reason.py:150），没走过这条映射，所以一直是绿的。修法：分类依据从 evidence.detail 取值（与 adapters/dsh/hooks.py:333 同口径），或让 decision_reason 同时比对 detail。

> 证据：371-374: kind/value 取自 evidence，detail 未取；384: evidence_value=value；models.py:279: if all(item.evidence_value in UNREPAIRABLE_VIOLATION_DETAILS ...)；checkers.py:413: evidence=Evidence(kind="validator", ..., value=checker, detail="uncovered_checker")

> 复核：_violations_from 只搬 evidence.kind/value（client.py:371-374、384），detail 整段丢弃；而两个"平台没能查"的构造点把标记写在 detail：checkers.py:412-414（value=checker、detail="uncovered_checker"）与 :395-400（value=验证器 status、detail=reason），models.py:279 却拿 evidence_value 去比 {'uncovered_checker','blocker'}（models.py:250-253 的注释自己写明标记在 detail）——真实载荷必然被判成…

### `src/retrieval/indexer.py:208-229` · bug · 已复核：成立

文档内容未变时走 unchanged 短路（只比 content_hash + chunker_version），清单里的文档元数据（visibility / tier / language / license / source_url / title / manifest_hash）永远不会写回 documents 行。这些列正是检索的行级过滤依据：store.search 用 d.visibility='public' 实现受限过滤，d.tier / d.language 做过滤，来源信息也直接从行里取。于是把某数据集在 corpus.yaml 里改成 visibility: restricted 后重跑 index：input_hash 变化会触发 ingest，但每个文档仍是 unchanged，documents.visibility 保持 public，不带 --allow-restricted 的检索照样返回这份已声明受限的内容（静默失败开启）；tier / language 过滤同理用的是旧值，报告里还写着 unchanged。建议把元数据纳入短路比较（或无条件 upsert_document、只跳过 chunk 重写），至少发现元数据变化时刷新文档行。

> 证据：if (existing is not None and existing.content_hash == content_hash and existing.chunker_version == CHUNKER_VERSION): ... continue（全程未调用 upsert_document）；store.search: if not allow_restricted: conditions.append("d.visibility = ?")

> 复核：208-229 的 unchanged 短路只比 content_hash + chunker_version，全程不调用 upsert_document；元数据只在 upsert_document(store.py:386-408) 里写（visibility/tier/language/source_url/license/manifest_hash），而检索过滤正是读 documents 行（store.py:846-854 `d.visibility = ?`、d.tier、d.language）。CLI 的授权集合 _granted_datasets(cli.py:178-185) 只按清单声明的数据集名放行、与 visi…

### `src/validators/adapters/pytest_runner.py:177-183` · bug · 已复核：成立

选择为空时的提前返回没有收窄 served，而 AdapterResult.served 的约定是「空 = 与注册表声明相同」（base.py:159-161），pipeline._from_adapter 也按 `result.served or spec.checkers` 记账（pipeline.py:1150）。于是「pytest 根本没被调起」的运行（例如变更集/目标里没有 src/**/*.py 生产文件，select_tests 返回 level=none、nodeids=()）会被记成 missing_tests 与 failing_tests 都服务过，TESTING-002（severity=error）在零执行证据下静默通过——引擎只在 `not bundle.serves(checker)` 时才以 uncovered_checker_violation 阻断（policy/engine.py:159-161）。这与同文件退出码 5 那一支自相矛盾：那一支至少真的把 pytest 跑起来了，却显式只记 served=(missing_tests,)（第 272-281 行）。修法：这一支同样传 served=(MISSING_TESTS_CHECKER,)（missing_tests 的证据来自选择阶段，failing_tests 没有任何执行证据）。

> 证据：if not selection.nodeids: return AdapterResult(status=... , evidence=..., reason=selection.reason, payload={...}) # 无 served=

> 复核：177-183 的空选择早退没传 served，而 AdapterResult.served 的约定是"空 = 与注册表声明相同"（src/validators/adapters/base.py:159-162）、pipeline.py:1150 用 `result.served or spec.checkers` 记账；同一文件 exit_code==5 分支（:265-281）却显式只记 served=(MISSING_TESTS_CHECKER,)，两处自相矛盾。该分支可达：selection.py:127-128 在变更集与目标都不是生产文件时返回 level=none、nodeids=()；此时引擎不报 uncovered…

### `tools/ab_measure.py:1087-1091` · bug · 已复核：成立

`--oracle` 的 `python` 字段只在“没有 argv”的回退分支里用到：主路径把 `test_command.argv` 当作完整命令行交给 subprocess。而冻结的 oracle 输入格式（tools/ab_tasks.py:248-254 与本文件 3041/2303 行 help 都写明 `test_command.argv` 是**解释器之后**的参数、`python` 单独给）产出的是 `["-m","pytest",…]`，于是 subprocess 直接 FileNotFoundError → 转成 unavailable，可用性 oracle 在这份输入下**永远起不来**，U1 读数恒为 unavailable。修法：argv[0] 不是可执行文件时前置 `python`，或把两种 argv 形态收敛成一种并写进契约。

> 证据：1087-1091: `argv = [str(item) for item in (spec.get("argv") or [])]` / `python = str(oracle.get("python") or sys.executable)` / `if not argv:` 才拼 `[python, "-m", "pytest", …]`；1104-1110 直接把 argv 交给 run_command

> 复核：1087-1091 只在 `not argv` 时才用 python 拼命令行，1104-1115 把 spec['argv'] 原样交给 run_command（直接 subprocess.run，无 shell、不解析解释器；argv[0]='-m' 即 FileNotFoundError → STATUS_UNAVAILABLE，:385-390）。生产方 tools/ab_tasks.py:248-254 的 argv 正是 ['-m','pytest',…] 且带 argv_note"argv 是解释器之后的参数"、python 在 :256 单独给，本文件 :2303/:3041 的 help 同口径，故按该冻结格式产出…

### `tools/ab_measure.py:1092-1097` · bug · 已复核：成立

`cwd = tree / str(spec.get("cwd") or ".")`：oracle 的 cwd 被当成相对**被测树**解析，但两个生产方给的都不是这个基准——tools/ab_tasks.py:251 给 `<root>/<instance>/baseline`（相对进程 CWD 或绝对），tools/ab_arm.py:599 给 `display(tree)`（相对仓库根）。相对形态下 `cwd.is_dir()` 为假 → oracle 直接 unavailable；给绝对路径时 pathlib 会丢掉左边的 tree，在反事实路径（1644 行 tree=target_root）上就会去跑原始基线树，第三条红通道（--with-tests）恒不触发。修法：按明确声明的基准解析 cwd，反事实路径强制落在 target_root 内。

> 证据：1092-1097: `cwd = tree / str(spec.get("cwd") or ".")` … `return {"status": STATUS_UNAVAILABLE, "reason": "oracle 的 cwd 不存在：" …}`；1644: `run_pytest_oracle(tree=target_root, …)`

> 复核：1092-1097 用 `cwd = tree / str(spec.get('cwd') or '.')`，而两个生产方都不以此为基准：ab_tasks.py:251 给 str(baseline_dir)（绝对路径），ab_arm.py:599 给 display(tree)（仓库相对，实测 measurement_input.json:93 = ".tmp/ab-arms/20261007T122320Z-78d1c9/enforced/tree"）。相对形态下 tree/'.tmp/…' 不存在 → 直接 STATUS_UNAVAILABLE（"oracle 的 cwd 不存在"）；绝对形态下 pathlib 会丢掉左边的 …

### `tools/provenance_loop.py:246-247` · test · 已复核：成立

self-check-comparator 场景自称做了"仪器自证"（把比对换成恒 pass 的替身，证明那条红来自 compare_seals 本身），但代码只是 `stub = "pass"` 这个字符串常量，再断言 `stub == "pass"`——没有任何替身真的被注入或替换，该断言恒真，这条场景在它的宣称目的上永远不可能变红。AGENTS.md §45 要求仪器自证必须给出"修复前会红"的显式变异证明，做不到就写明"覆盖不到"。建议：真的把比对函数替换为恒 pass 的替身（例如抽出可注入 comparator 的辅助函数）并断言替身下不再报 external_write；否则删掉该场景，把"比对器未做变异证明"如实写进读数。

> 证据：`stub = "pass" # 关掉比对：假装两次封条相等` / `ok = real.state == "external_write" and stub == "pass"`

> 复核：239-259 的"仪器自证"里 `stub = "pass"` 只是字符串常量，ok = (real.state == 'external_write') and (stub == 'pass') 的后半截恒真，没有任何替身被注入或替换（:242-245 仍真跑 compare_seals），因此证明不了 :250 的 what 所声称的"把比对换成恒 pass 的替身，同一个场景不再报红"。该 ok 直接决定报告 result 与退出码（:277-298，`failed = [record for record in records if not record['ok']]`），即这条自证在它宣称的目的上永远不会红——正是 AG…

## 4. 中优先级（58 条）

### `.github/workflows/phase-8.yml:12-14` · maintainability · 已复核：成立

整个 phase-8 job 没有 `timeout-minutes`，工作流也没有 `concurrency`（同文件 `push` 与 `pull_request` 都会触发）。这个 job 串行跑全量 pytest + 多个闭环脚本，任一步挂起会占满 runner 默认 6 小时上限，并让同分支的重复推送各起一条 run。按工作流规则（Missing timeout / No concurrency control）补 `timeout-minutes`（如 30）与带 `cancel-in-progress` 的 `concurrency` 组。

### `.github/workflows/phase-8.yml:19-22` · security · 未复核

引用第三方 Action 未钉到 commit SHA：`actions/checkout@v7` 与 `astral-sh/setup-uv@v7`。规则只豁免 `actions/*` 的 `v4` 形态；第三方（astral-sh）用可变 tag 可被重打，升级 Chain 上有供应链风险。建议把 `astral-sh/setup-uv` 钉到完整 commit SHA（`actions/checkout` 至少保持与仓库其它引用一致）。

### `adapters/approved.json:5-7` · bug · 未复核

dsh 条目持久化的 ceiling_reasons 是一句与同一记录自相矛盾的话："manifest 与已审核哈希不一致或尚未审核"，但同一条目的 manifest_digest 就是当前 manifest 的哈希、enforcement 是 full，运行期重算的理由为空。原因是这条理由由 approve 时的**瞬时**状态拼出（src/adapters/base.py:852-861 只在 digest 不匹配时追加），所以每次"改声明→重新 approve"都会把一条假理由永久写进审核产物；读过 approved.json 的人会以为 dsh 未审核。改法：审核产物不要持久化 ceiling_reasons（它属于读数，不…

### `api/openapi.json:958-967` · bug · 未复核

契约快照把 GET /v1/ops/metrics 的**成功**响应（200）描述成错误信封：content 引用 #/components/schemas/ErrorResponse，description 写 "200：结构化错误（见 ErrorResponse）"。按这份快照生成客户端的调用方会把指标响应当成错误对象解析，而其他三条路由的 200 都是 "决策 / 检索结果 / 验证证据（载荷是受控 JSON）"。根因在生成侧 src/policy_api/app.py:60,291：_METRICS_STATUS_CODES=(200,403) 被整组丢进 _error_response_doc，成功码 200 也被套上错…

### `docs/mirrors/owasp-cheatsheets/manifest.json:8-10` · bug · 未复核

顶层计数自相矛盾：pages_candidate=122，但实际 pages_saved=124（pages 数组长度也是 124）、pages_excluded=4，即“候选”应为 128；122+4≠124，缺口 6。tools/owasp_cheatsheets/05_verify.py 只把这几个数打印出来、不做核对，所以这条不一致不会被任何门禁发现。计数是这份清单对被抓取范围的唯一声明，对不上就等于没有可核对的账。修法：在生成器里按 len(pages)+len(EXCLUDED) 现算（或修正常量并说明 6 页的来源），并让 05_verify 校验三者相等。

### `docs/project/architecture/tech-detail/07-LangGraph-编排/07-LangGraph-编排.py:686` · bug · 未复核

第 1 轮「修复」的改动正文与第 0 轮完全相同：`support.write_change()` 的默认正文里那句话是「处理创建请求（编排层改写过的版本）。」，其中不存在子串「处理创建请求。」，所以这里的 `.replace(...)` 静默不生效——BROKEN 与 FIXED 的 content 逐字节相同，只有 summary 不同（Change.digest 覆盖 summary，于是两轮的 action_id 还不一样，更掩盖了这一点）。后果：本节演示的「验证失败 → 修复 → 再验证」在修复那一步其实什么都没改，读者会以为修复节点真的改写了受控文件；现有断言只钉步数与工具调用次数，抓不到。建议直接传显式正文（conte…

### `docs/project/architecture/tech-detail/build_notebooks.py:384-386` · bug · 未复核

工作区守卫按后缀放行，比它声称的范围宽得多：`after - before` 里任何以 .ipynb/.py 结尾的 `git status --porcelain` 行都被当成"本次生成的产物"，因此某个单元把仓库里任意 .py 改坏（` M src/policy/models.py`）、或新建 `?? src/evil.py`、或删掉 ` D src/x.py` 都不会让生成失败——而 382–383 行的注释说只允许"本目录刚生成的两份产物"。建议改成与本次真正写入的 notebook_path/script_path 精确比对（其余 porcelain 行一律计入 unexpected），否则这条守卫对最危险的写入形态（改源…

### `evaluation/results/fidelity-baseline.json:1` · maintainability · 未复核

版本化基线把「0 条标注 = 设计如此」这个结论投影掉了：三个片段级数据集只有 `"annotations": 0`，而 `expected_empty` / `empty_reason`（由 tools/governance_eval.py 产出，含「片段级期望不产出 Annotation」的理由）没有被 baseline_record 收进去。于是单看基线无法把「设计如此」与「语料没取到」分开——这正是 tools/governance_eval.py:1079-1097 明确要求分开的两种情形。建议在 baseline_record 的 datasets 投影里补 `expected_empty` 与 `empty_reaso…

### `examples/dsh/dsh-adapter.yaml:22-24` · bug · 未复核

test_paths 声明得比平台数据宽得多：`tests/**/*.py` 把 tests/ 下**所有** .py 都当成测试（layer=test），而 validation/test-layout.yaml 的平台 test_patterns 只有 `tests/**/test_*.py` 与 `tests/**/*_test.py`。于是 tests/conftest.py、tests/api_support.py、tests/fixtures/rules/SEC-*/bad.py（刻意写坏的夹具）、tests/fixtures/agent_events/workspace/src/shop/order_controlle…

### `src/adapters/base.py:205-221` · bug · 复核：部分成立（级别已修正）

`_compile_glob` 把 `**` 一律编译成 `.*`，于是 `**/` 变成"至少一层目录"（`**/*.py` → `^.*/[^/]*\.py$`），根目录文件全部落空：`README.md` 不在 `**/*.md` 的覆盖里，`manage.py` / `conftest.py` / `setup.py` 也不在 `**/*.py` 里。仓库另两份同语义实现明确把 `**/` 定义为"零个或多个目录"（`src/validators/globs.py:5-11`，并把"至少一层"这个写法记为治理覆盖缺口 G8；`src/adapters/dsh/adapter.py:417-451` 同），04-open-wo…

### `src/adapters/base.py:142` · bug · 已复核：成立

`AdapterConfig.schema_version` 只有默认值、没有任何校验：`adapter.yaml` 写 `schema_version: "9.9"` 会被静默接受，并按 1.0 的键语义解释。这违反 AGENTS.md §3（未知协议版本一律报错，不得静默忽略）与 §55（`ADAPTER_CONFIG_SCHEMA_VERSION` 是登记在册的版本轴）。同一模块的 `_load_approved`（base.py:981-985，未知 approved 版本即 RegistryError）与 `models.AdapterManifest._check_manifest_version`（models.py:…

### `src/adapters/dsh/hooks.py:1225-1228` · security · 未复核

非写类工具进入 Phase 4 受控链路的判据手写成一个二元组，漏掉了 HIGH_RISK_LEVELS 里的 external_side_effect：若注册表把某个在 TOOL_TABLE 里是 READ_ONLY/NO_FILE 的工具声明成 external_side_effect，它既不命中上面的 EXECUTE 分支、也不命中这个元组，于是直接落到下面的 not_governed 分支放行——被登记为高风险却没有授权、参数白名单与审批门禁（AGENTS §13/§14）。现有契约测试挡不住这条：tests/contract/test_enforcement_protocol.py:326 的 expected 只约束 r…

### `src/adapters/dsh/pre_evidence.py:171-178` · bug · 未复核

超时只约束等待方，停不住取证，且影子副本的删除落在可能被直接杀掉的孤儿线程里。`worker` 是 daemon 线程，173 行 `worker.join(timeout)` 超时后 175 行立刻抛 PreEvidenceError，但线程会继续跑完整条 Phase 5 流水线（含 pytest / ruff 子进程），预算并没有终止工作；而 `shutil.rmtree(shadow, ignore_errors=True)` 在 238-240 行的 `finally` 里，也就是在这个孤儿线程里执行——Hook 是「一次工具调用一个进程」，抛错后进程随即退出，daemon 线程被解释器直接杀掉，rmtree 通常根本不会跑…

### `src/adapters/json_adapter.py:43-65` · bug · 未复核

`agent_response_from_decision` 的字段白名单与决策协议载荷不匹配，两条入参路径都必然抛异常，函数实际不可用。（a）传 `ValidationResult` 时走 45-46 行取 `to_decision_dict()`，而该载荷固定含 `rule_set_hash` / `skipped_rules` / `pending_findings`（src/policy/models.py:1033-1060），allowed 只有 8 个键 → 63-65 行 `unknown` 非空 → 抛 AdapterEventError；即 isinstance(ValidationResult) 分支永远走不到…

### `src/adapters/models.py:666-674` · maintainability · 未复核

AdapterLoad 这个 frozen dataclass 在全仓库没有任何构造点或引用点（`grep AdapterLoad` 只命中本文件 667 行的定义），也不在本模块 __all__ 里：它更像是「加载结果由 loader 返回」这一设计的遗留物，实际 loader.py 并不返回它。它把自己写成「一次加载的结果：manifest、配置、路径与可审计的注册表身份」，却既不参与装配也不参与审计，读者会以为存在一条已接线路径。建议：删除，或让 loader 真正返回它并加入 __all__（两者择一，别留半成品）。

### `src/adapters/runtime.py:116-119` · bug · 复核：部分成立（级别已修正）

脱敏正则 _PATH_RE 的第二个分支 `(?:/)[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+` 会命中**相对路径**中间的那一段，把拒绝理由里的仓库相对路径啃成残片：sanitize_message("路径 src/adapters/models.py 不是仓库相对路径…") → "路径 src<path> 不是仓库相对路径…"，"policies/coding/ARCH-001.yaml" → "policies<path>"，连 URL（https://example.com/a/b → http<path>）也会被改写。这个函数是**每一条**拒绝/错误响应的正文来源（_refuse / Runti…

### `src/adapters/runtime.py:182-194` · bug · 未复核

_process_file_lock 的 finally 无条件执行解锁，即使锁从未拿到也会调一次 LK_UNLCK：Windows 上取锁 5 秒超时后在 175 行抛 RuntimeLedgerError，紧接着 188 行的 msvcrt.locking(..., LK_UNLCK) 自己抛 PermissionError，把「台账锁超时」这个真正的原因替换掉（异常从 finally 抛出，覆盖在途异常），调用方只看到一句 Windows 权限错误。更糟的是 handle 的兜底 except Exception 会把这条 PermissionError 归到 internal_error，而 RuntimeLedgerErr…

### `src/adapters/wiring.py:2231-2235` · bug · 复核：部分成立（级别已修正）

`note = (...)` 里最后一个字符串后多了一个逗号（2234 行），整个右值于是成了 **1 元组**而不是字符串：走「同档多条声明判决一致」这条分支时，`channels[].governs.note` 在 JSON 里是数组（[同档 2 条声明判决一致（…）：decision=in_scope；不挑一条，declared_by 写 null]），而同一个键在另外三个分支里都是字符串，`_Governs.note` 的类型标注也是 `str`。同一个键出现两种类型（AGENTS.md §50/§55 最忌讳的形态），按字符串读的消费方会拿到 list。删掉那个尾随逗号即可；顺带说：这一分支没有任何用例覆盖（tests 里…

### `src/adapters/wiring.py:1183-1188` · bug · 未复核

`_audit_facts` 先把整份审计文件 `read().splitlines()` 读进内存，再在超过 `MAX_AUDIT_LINES`（50000）时取**头部**：`lines = lines[:MAX_AUDIT_LINES]`。审计 JSONL 是追加写的（src/adapters/dsh/hooks.py:514 以 open("a") 打开），最新记录在**尾部**，所以文件一大，「最后一条留痕」就退化成第 5 万行那条老记录，`age`/`stale` 会把一条正在被写入的活跃通道判成 `stale`（通道 `ok=False` → `--check` 退出 1，判据正是 failures/result），而…

### `src/enforcement/approvals.py:84` · bug · 未复核

审批记录的协议版本既不校验、也没有走自己声明的版本轴：ApprovalRecord.schema_version 默认取 ENFORCEMENT_SCHEMA_VERSION（第 84 行），load_approval 只做 model_validate、verify_approval 也不比对，而第 59 行定义的 APPROVAL_SCHEMA_VERSION 全仓库只有 __all__ 引用（死常量）。后果是任何未知版本的审批文件都被静默接受并按其字段放行——违反 AGENTS 第 3 条（未知协议版本一律报错，不得静默忽略或默认放行）与第 55 条（它把 approval 登记为独立版本轴）。建议：比照 enforcemen…

### `src/enforcement/approvals.py:226-229` · bug · 未复核

审批的两个时间字段没有时区校验，无时区的审批文件会让校验路径抛未处理的 TypeError。granted_at / expires_at 是裸 datetime（99-100 行），pydantic 会把 "2026-10-07T10:00:00" 原样解析成 naive datetime；_check_shape（132 行）只在两者时区**不一致**时报错，两者都 naive 时照样通过。之后 verify_approval 用 aware 的 moment（precheck.py:200 的 utc_now()）比较第 226 行 → "can't compare offset-naive and offset-aware …

### `src/enforcement/drivers.py:272-295` · bug · 已复核：成立

超时只终止直接子进程，不终止进程树。shell 前缀是 pwsh/bash（drivers_for → ShellCommandDriver(shell=spec.shell)），被执行的命令是孙进程；subprocess.run(timeout=...) 超时后只 kill 直接子进程，孙进程会继续跑，而返回的 detail 却写死“已终止”，平台据此把本次执行记成 failed/execution_timeout 并认为副作用已经停下——实际副作用可能仍在继续，这与“受控执行”的语义相反。本仓库已有正确做法可复用：src/validators/adapters/base.py::_terminate_tree（Windows 优…

### `src/enforcement/executor.py:367-382` · bug · 未复核

执行已经发生，但台账写入失败被 `except LedgerError: pass` 静默吞掉：既没有进 notes，也没有留下任何链上痕迹。同一个方法里审计写入失败会用 note 如实上报（_audit 的文档字符串明写“不让它变成静默成功”），台账这一条成了例外；而 kind=execution 的记录正是 precheck 熔断的失败计数来源（precheck.py:549 failures_since 读 ok=false / limit_key），这条记录丢了就等于窗口内失败数少算，熔断不会按事实触发，调用方也读不到“这次执行没被记账”。建议与审计同样处理：把错误写进 notes（或写一条审计记录说明台账不可写）。

### `src/enforcement/postcheck.py:400-403` · bug · 未复核

事后验证器把「跳过」记成 passed：_outcome(name, True, ...) 映射为 CheckStatus.PASSED + ReasonCode.ALLOW，于是「目标不存在，跳过语法检查」（401 行）与「非 Python 目标，Phase 4 不做语法检查」（403 行）在审计与 PostEvidence.validators 里与「真的解析通过」逐字同类；375 行「非文件动作，跳过内容一致性检查」同理。判定结果不受影响（validate 只把 FAILED 计入 failed），所以这是证据口径问题，但本仓库其它地方正是靠状态值把「跳过≠通过」写清楚（precheck 大量使用 CheckStatus.SK…

### `src/enforcement/precheck.py:976-982` · bug · 未复核

台账写失败时决定被翻成 block，但此前的审计记录已经落盘为 allow 并带 grant_id：审计链与最终返回的 PreDecision 自相矛盾。pre_execute 先写审计（801 行，payload 里 decision=allow、grant_id=grant-xxx），再在 960-982 行登记授权与台账；ledger.record_grant/append 抛 LedgerError 时只把局部 decision 改成 BLOCK、grant=None，既不补写一条纠正记录，也不撤销那条审计。读审计链的人会得出「这次动作被允许且签发过授权」的结论，而实际返回的是阻断——这正是 679-681 行注释明令禁止的…

### `src/enforcement/registry.py:222-225` · bug · 未复核

approvals.require_role 是纯装饰性声明：它被解析（308-310 行还校验它必须存在于 roles）、被写进 registry_payload（213 行，进入注册表身份），但从不参与任何判定。审批权判定在 225 行按硬编码权限名 "repo.approve" 取角色，precheck 只把这个成员集交给 verify_approval（precheck.py:448）。后果：把注册表改成 approvals.require_role: owner（本意「只有 owner 能批」）只改变哈希、不改变谁能批——reviewer 仍可批；反过来若把审批权限改名，成员集变空、所有审批被拒（方向是失败关闭，但声明与行…

### `src/policy_api/app.py:202-205` · performance · 未复核

`handle_route` 是 `async def`，却直接在事件循环线程上调用同步阻塞的 `runtime.handle(...)`；`runtime.handle` 内部经 `run_with_budget` 起线程并 `join(budget_ms)`（runtime.py:542/663/784），而预算上限是 `budgets.validate_ms`（默认 10s、上限 600s）。uvicorn 单进程（serve.py 的 `uvicorn.run` 没给 workers）下所有请求被串行阻塞，连 `/v1/health/live`、`/v1/health/ready`（319 行的 `runtime.readi…

### `src/policy_api/cli.py:100-112` · bug · 未复核

`run()` 在分派任何子命令之前先无条件 `_load(args)`，于是 `clients --hash`（docstring 写的就是从 stdin 读令牌输出 sha256，`_clients` 的 hash 分支根本不需要配置）在配置缺失、不可读、或**配置里写了明文令牌**时都以退出码 2 失败；而 config.py:120-124 拒绝明文令牌时给出的修复指引恰恰就是这条命令——用户被指向一个同样跑不起来的入口，唯一补救路径（生成摘要替换明文）被自己堵死。建议把 `--hash` 分支提到 `_load` 之前（它只读 stdin）。

### `src/policy_api/contract.py:261` · bug · 复核：部分成立（级别已修正）

`ApiError` 在本文件里从未导入（第 21 行只导入 `STATUS_BY_CODE, ErrorCode`），这一行会抛 `NameError` 而不是预期的 `ApiError`。`smoke()` 使用一个不在配置里的令牌（CLI 传错令牌就是这条路径）时，本应得到的 `unauthenticated` 结构化失败被 NameError 吃掉：调用方拿到的是未处理异常与 traceback，错误分类丢失。建议把导入改成 `from .errors import ApiError, STATUS_BY_CODE, ErrorCode`。

### `src/policy_api/observability.py:175-176` · performance · 未复核

`self._written.append(payload)` 在任何情况下都执行——第 187 行之后的分支只决定「要不要落盘」，不决定「要不要留在内存」。注释说这一份「只保留在内存里：仅用于测试与 --dry-run」，但正式路径（path 已配置、正在写 JSONL）同样每请求追加一条且永不清理，单条上限 16KB。长时间运行的 API 进程于是把所有请求记录累积在内存里，这与模块第一句「失败关闭 / 只记摘要」的设计意图无关，是纯粹的泄漏。建议：只在 `not self.active` 时 append（或给这个仅供测试用的缓冲加容量上限）。

### `src/policy_api/probe.py:164` · bug · 未复核

失败关闭载荷把决策协议版本写死成 `"1.0"`，而核心是 `SCHEMA_VERSION = "1.1"`，`SUPPORTED_SCHEMA_VERSIONS` 只含 1.1（AGENTS.md 第 7/55 条：1.0 载荷一律拒收，版本只能从核心取值、不许自己算一个）。后果：策略服务不可达时产出的这份阻断载荷，被平台自己的协议消费方（`policy.models.parse_decision`、`orchestration.client._parse_validation`）判为「决策载荷无法解析 / PlatformUnavailableError」，拒绝理由从「策略服务不可用」变成「协议版本不认识」。第 130 行的 `…

### `src/policy_api/runtime.py:550-551` · performance · 已复核：成立

`_decisions` 只增不减：每次 evaluate 都以 `(tenant, request_id)` 为键把整份 `ValidationResult` 留在进程内存，而 `request_id` 完全由调用方提供（DTO 上限 200 字符），除 `_policy_facts` 读取外全仓没有任何删除、TTL 或容量上限。长跑服务里这是稳定增长的内存占用（本仓库其它台账都带 TTL 或上限，只有这里没有），并且可以被「每次换一个 request_id」的请求放大成内存耗尽。建议：给这份 decision_ref 存储加显式的有界窗口（TTL 或 LRU 上限，例如复用 `idempotency_ttl_seconds` 的…

### `src/policy/check.py:1064-1069` · bug · 未复核

`--obligations` 的账本 IO 失败会以未捕获的 OSError 冒泡，退出码退化成 1（=发现违规），而不是本文件自己声明的 2。obligations.py 只把 `_check_existing` 里**读第一行**的 OSError 包成 ObligationsError；`_append` 的追加写（obligations.py:194 `path.open("a", ...)`）与 `load` 的整体读（obligations.py:416 `path.open("r", ...)`）都会原样抛 OSError（只读账本文件/只读目录、被其它进程占用、mkdir 失败等）。这个 try 只 `except…

### `src/retrieval/cli.py:470-509` · bug · 未复核

`_dispatch` 的错误处理链没有覆盖 pydantic 校验错误：`_retrieval_query()`（196-207 行，把 `--limit` / `--file` 等原样交给 RetrievalQuery）是在 470 行的 try 内被调用的（479/497/500 行），而 except 只接 ContextBudgetError、(CorpusError, ProtocolError, StoreError, RetrievalError) 与 json.JSONDecodeError——RetrievalError 是 Exception 子类（models.py:106），pydantic 的 Valid…

### `src/retrieval/models.py:428-435` · bug · 未复核

CorpusManifest.restricted_datasets 只被规范化与“引用未声明数据集”校验使用，没有任何生产代码消费它（全仓 grep 只命中 models.py 自身与测试夹具）。真正生效的是每个数据集自己的 visibility 字段（写进 documents.visibility，检索期按 d.visibility 过滤），而 CLI 的 _granted_datasets 会把清单里所有数据集（含受限的）都放进 AccessScope，唯一开关是 allow_restricted。因此在清单里把数据集登记进 restricted_datasets、而 dataset.visibility 仍是 public …

### `src/validators/adapters/base.py:548-557` · bug · 未复核

输出限量先按字节切片再解码：切点落在多字节字符中间时 out.decode("utf-8") 抛 UnicodeDecodeError，于是「输出超长」被归类成 output_invalid，理由写成「工具输出不是合法 UTF-8」——工具其实跑成了、输出也是合法 UTF-8，失败关闭的理由是假的（AGENTS §52）。另外 truncated 用 stdout+stderr 的总长判定、截断却按每条流各给 max_output_bytes，会出现「标记为已截断但两条流都没被截」的读数。修法：先以 errors="replace"（或回退到合法边界）解码，再按字符截断，并统一总量/单流的口径。

### `src/validators/cli.py:126-133` · security · 已复核：成立

--changed-from-git 的值被原样拼进 git 参数，既没有 `--` 分隔也没有前导 `-` 检查：`--changed-from-git=--output=<路径>` 会让 git 把输出写到任意文件（--output=<file> 是 git diff 的合法选项），--no-index / --ext-diff 同理。这正是 AGENTS §17 在受控执行层结构性阻断的那类「选项注入」——白名单正则只描述命令长什么样，描述不了这个选项会干什么；而 README/使用说明把它作为公开用法。修法：拒绝以 - 开头的 ref（或先 `git rev-parse --verify` 校验再 diff）。

### `src/validators/depgraph.py:235-239` · bug · 未复核

相对导入的越界判定差一级：drop = level - 1，只在 `drop > len(package)` 时才判 unresolved，于是 `drop == len(package)`（例如包深度 1 的 src/shop/a.py 里写 `from .. import x`）会取到空前缀，被解析成**顶层模块** x。Python 对同一写法抛「attempted relative import beyond top-level package」；本模块自己的口径是「解析失败必须留痕，绝不把解析不了当作没有依赖」（模块 docstring / AGENTS §20）。后果是凭空造出一条指向无关顶层模块的依赖边（可能让 for…

### `tools/ab_arm.py:651` · bug · 未复核

--task 被定义了却从未被读取：run_one 没有 task 形参，main 也不传 args.task，task_id 只从 preset 或 --path / DEFAULT_TASK 推出（337 行）。文件头部用法示例（第 9 行 --run --task demo-1 ...）因此无效，实验记录里的 task_id 会变成目标路径或 synthetic-edit——按任务名归档、比对跨臂读数的下游会归错。建议把 args.task 传进 run_one 并让它覆盖 spec 的 task_id，或删掉这个参数与示例。

### `tools/ab_arm.py:1077-1113` · bug · 未复核

bootstrap_route 在**净化之后**的臂树上判定（tree/policies、tree/AGENTS.md、tree/validation），而这三条恰恰是 SANITIZATION 无条件删除的路径（sanitize_tree 每次 prepare_arm 都跑），所以它恒为 False：route 永远报 external_task_tree（默认 --baseline . 明明是本仓副本），vcs_dir_absent.status 永远是 not_applicable——那条「bootstrap 路线证伪」断言从不生效，读数与真实路线不符。建议改用净化不会删掉的标记（如 tree/tests、tree/pypr…

### `tools/ab_arm.py:1102-1118` · bug · 未复核

运行时探针「取不到读数」被读成了「干净」：probe_claim.status 为 unavailable（子进程超时 / OSError，例如受限沙箱下 capture_output 的 spawn 被拒 / 输出解析失败）时，只有 fail 才会 append 到 problems，于是 clean 仍为 True，--assert-clean 退出 0，run.json 的 arm_tree.clean 也是 True。本文件自己写明「净化是路径删除不是可达性控制，所以必须用行为证据」，探针没跑成 = 这条证据缺失，却给出干净结论（与 AGENTS §45「仪器必须能失败」及本文件 run_one 里「跑不了记 unavail…

### `tools/ab_measure.py:1650-1658` · bug · 已复核：成立

反事实的第三条红通道在**测试没跑起来时静默判绿**：`run_pytest_oracle` 起不来/超时时返回 `{"status":"unavailable","reason":…}`（1094、1117 行），里面没有 `pytest_status` 键，于是 red / environment_unavailable 两个分支都不进——entry 保持 CF_GREEN、`reasons` 一个字都不写，而 CF_GREEN 会进分母被计成 FP（1663-1684 行）。“缺东西”因此变成“仪器说这次 block 不必要”，precision 被系统性压低且读不出来。修法：trial 不可用时把该条标成 CF_UNVERI…

### `tools/ab_measure.py:2876-2884` · bug · 未复核

`--cf-scope tree` 是**静默无效**的开关：`counterfactual(..., scope=...)` 的 `scope` 参数在函数体内一次都没被引用（只有签名 1563 行），重扫永远只对 `applied["files"]` 逐文件做（1601-1603 行），而载荷把 `args.cf_scope` 原样写进 `block_precision.scope`（2878 行）。用户以为做了全树重扫、载荷也这么写，实际口径是 file。修法：实现 tree 分支，或删掉该选项并在载荷里显式标 not_implemented。

### `tools/ab_tasks.py:144-147` · bug · 未复核

取任务元数据的请求既没带 `revision` 也没用 `dataset_id`：`urlencode` 里数据集名硬写成 `princeton-nlp/SWE-bench_Verified`（145 行），而 `SOURCES[...].revision`（声称钉死的数据集 sha）只写进读数与锁文件（157/567 行），从不参与请求；`--verify` 的 revision 比对（619 行）只是把锁与代码里同一个常量对一遍。于是 tasks.lock.json 里那条 revision 与真正取到的字节没有绑定关系（真取到什么只能靠本地文件 sha256 事后比对），换成别的 hf-rows 数据集时也会静默写进 SWE-…

### `tools/ab_tasks.py:320-324` · bug · 未复核

pytest 的 stdout 被截到最后 4000 字符（323 行）后再解析逐用例结果：`verify_oracle` 用 `_outcomes(result["stdout_tail"])`（490 行）、`run_oracle` 用 `tail.count(" PASSED"/" FAILED")`（401-405 行）。“-rA”的短摘要行数随用例数增长，p2p 集合一大（SWE-bench 常见几十上百条）前缀就被裁掉：被裁掉的 FAILED 不计入 `p2p_red` → `pass_to_pass_all_green` 可能为真，一条本该 reject 的任务被接受；PASSED/FAILED 计数同样偏小。修法：逐…

### `tools/ci_local.py:339-342` · bug · 未复核

`_changed_paths()` 读 `git status --porcelain` 时完全不看 `status.returncode`：命令失败（例如 `GIT_INDEX_FILE` 指向不存在/不可写的索引、仓库权限异常）时 stdout 可能为空，`dirty` 静默变成空列表，未提交的工作树改动于是从「这次改了哪些文件」里消失，按改动范围选步会少跑 CODE/RETRIEVAL/ORCHESTRATION 各组步骤——`--hook` 下这正是「推送被放行、门禁其实没跑」的形状。同一仓库的 `tools/check_text_conventions.py:57-74` 对这种失败写得很明确：「失败不能退化成空集合：那…

### `tools/dsh_sandbox_loop.py:108` · bug · 已复核：成立

AGENT_VERSION 硬编码成 "0.1.5-rc.1"，而仓库里 agent_version 的权威声明已经是 0.1.6-alpha.2（adapters/dsh/manifest.yaml:21，adapters/approved.json 与 adapters/host-versions.observed.json 同值）。这个常量被写进受控项目生成的 Adapter 配置（第 232 行）与结论载荷（第 1286 行），而 Adapter 只认配置里的 agent_version（src/adapters/dsh/hooks.py:686）——真实跑在 0.1.6-alpha.2 宿主上的会话，审计与 .tmp/ar…

### `tools/eval_corpus_extra.py:476-486` · bug · 未复核

_scan_pydocstyle 对 @expect(...) 装饰器重复计数：ast.walk 先产出 FunctionDef/AsyncFunctionDef/ClassDef 节点（476-481 行按 node.decorator_list 收码），随后又产出装饰器自身的 ast.Call 节点，落进 482-486 行的 elif 再收一次。实测对语料文件 all_import.py 调用 _scan_pydocstyle：原文 @expect( 出现 2 次，counts 得 {'D103': 4}；全语料 --report 的 expectations 合计 307（ann 72，其中差值大部分来自 line=0 的按…

### `tools/eval_corpus_extra.py:1049-1067` · bug · 未复核

_collect_pyflakes 把「期望参数不是 ast.Attribute」误当成「上游显式断言零输出」。classes 只收 Attribute（1049 行），declared_empty=not classes（1067 行）于是在 self.flakes(src, IsLiteral)（Name）与 self.flakes(src, *expected)（Starred）时都取 True、codes=()。实测 .tmp/eval-corpora/pyflakes-messages@9f0a7f9c…：28 处非 Attribute 期望参数里 26 处被接受为 declared_empty=True（test_is_…

### `tools/governance_eval.py:3416-3428` · bug · 复核：部分成立（级别已修正）

`--check` 与默认 `--baseline` 共用同一条读取路径：目标不是文件时只写一个 `action: missing` 的提示块，`payload["result"]` 保持原值，于是「显式要求比对却读不到基线」仍然返回退出码 0（第 3451 行）。这与文件头第 19–20 行的退出码契约（1 = 有判据 fail 或**读不到**，「读不到一律显式写出原因，绝不静默 pass」）以及 AGENTS §45（自己的仪器也要能失败）直接矛盾：`--check` 路径写错、或基线文件没随代码取到，都会得到一次绿色门禁（`--check`/`--baseline` 目前还没有任何调用方，但它是漂移门禁的唯一入口）。建议：只…

### `tools/governance_eval.py:2152-2157` · bug · 未复核

同一段判定链路（`build_context` / `run_pipeline` / `evaluate`）在 `run_dataset` 里被 try/except 包住并落成显式读数（第 1183–1193 行，注释写明「判定链路任何异常都记成显式读数」），在片段物化这条路径上没有任何保护：异常会穿过 `run_fidelity` 抛出 `main`（那里只捕 `Unavailable` / `UsageError`），结果是 traceback、不写读数产物、「读不到」的结构化理由全部丢失。建议照 run_dataset 的写法把单文件失败记进 entry 的 status/reason 后继续。

### `tools/governance_eval.py:2544-2545` · bug · 未复核

`repo_scan_complete` 判据只看逐文件失败的 `repo_scan.errors`，完全忽略 `scan.unavailable`：`git ls-files --cached` 失败（`list_repo_files` 抛 Unavailable，被第 3077 行捕获后只写进 `scan.unavailable`）或 thresholds 里 `repo_scan.enabled: false` 时，`scan.errors` 为空，判据记 pass——一次「什么都没扫」的跑法拿到绿灯，P2/P3 也随之变成无依据的空值，而文件头第 19 行明说「扫描不完整」应退出 1。建议把 `scan.unavailabl…

### `tools/governance_eval.py:2633-2634` · bug · 已复核：成立

`baseline_record` 把两项读数取成 `payload["capability_out"]["counts"]` 与 `payload["unmapped"]["counts"]`，但载荷里这两块只有 `annotations` / `codes` / `diagnostics` / `note`（第 3196–3208 行），没有 `counts` 键，于是版本化基线与 `--check` 的漂移比对这些字段恒为 `null`：这两项读数怎么变，基线都不会红。建议改成读真实键（capability_out: annotations/codes；unmapped: codes/annotations/diagnosti…

### `tools/install_hooks.py:72-75` · bug · 未复核

安装 pre-push 钩子时直接把脚本写进 .git/hooks/pre-push，却没有给文件加可执行位（全文件没有任何 chmod）。POSIX 上 Path.write_text 新建文件是 0o644，而 git 的 find_hook() 用 access(X_OK) 找不到可执行钩子时按“没有钩子”处理，于是 pre-push 静默不跑——本该拦住推送的门禁等于不存在。文件自身支持 POSIX 布局（第 37 行候选含 .venv/bin/python，脚本头是 #!/bin/sh），所以这不是平台外的情况。建议在 HOOK.write_text(...) 之后补 HOOK.chmod(HOOK.stat().st_m…

### `tools/mirror_docs.py:995-996` · bug · 未复核

parent_of() 对**非分组镜像**（spec['groups'] 为空）一律返回 'review/index.md'：run() 在 groups 为空时把 gid 置成 'shared'（line 1054），于是 gitlab-code-review 与 python-pep-code-style 的每一条 manifest 记录都写上了这个只属于 google-eng-practices 的本地路径，而这两个镜像里根本没有 review/ 目录。已提交的 docs/mirrors/gitlab-code-review/manifest.json（20 页）与 docs/mirrors/python-pep-code-…

### `tools/mirror_docs.py:1026-1028` · bug · 未复核

注释声称「抓取全部成功后才清空旧产物」，但代码只在抓取抛异常时才保住旧产物：sitemap 发现返回空清单时（sitemap 改版 / 返回非 XML 页面，sitemap_scope_urls 得到 urls=[]）discover() 会正常返回 {}，pages 为空 → 旧镜像被 rmtree 删除并写出 pages_saved: 0 的 manifest.json，已有镜像静默丢失。建议：pages 为空（或 saved == 0）时直接报错退出，不删除旧产物。

### `tools/phase_evidence.py:139-145` · bug · 复核：部分成立（级别已修正）

agent_adapter() 把 dsh 的产品事实硬编码成字面量，其中 agent_version 写的是 0.1.5-rc.1，而当前声明与已审核/已观测记录都是 0.1.6-alpha.2（adapters/dsh/manifest.yaml:21、adapters/approved.json:4、adapters/host-versions.observed.json:10）。阶段证据因此会记下一个与声明相互矛盾的版本，而且这处副本没有任何检查覆盖（examples/dsh/dsh-adapter.yaml 的同款副本有 tests/contract/test_dsh_layer_declaration.py 钉住）。同一…

### `tools/retrieval_eval.py:435-465` · bug · 未复核

退出码只看 `gated`，而 gated 是"--gate 要求的方法"与"--method 实际跑过的方法"的交集：`--method fts5 --gate vector` 会得到空列表，`all([]) == True`，于是 result=pass、退出 0，而 payload 里 gated_methods 仍写着 ["vector"]——被门槛的方法一次都没跑却报通过（`--method fts5 --gate both` 同样只跑了一半）。这是门槛工具的失败开放。建议：argparse 阶段校验 gate ⊆ method 并报错退出 2，或把"要求门槛但未评测"的方法直接计为不满足。

## 5. 低优先级（97 条）

### `docs/mirrors/owasp-cheatsheets/manifest.json:32` · bug · 复核：部分成立（级别已修正）

crosswalk.asvs 的取值形态不统一：174 条里有 26 条带尾随冒号（"V15.1:"、"V16.2:"、"V7:" 等），其余是不带冒号的 "V2.1"。同名字段在同一份清单里出现两种写法，按字符串匹配这些编号的消费方（索引、检索、对比 ASVS 章节）会漏配；尾随冒号来自“按空白切分章标题取首词”的抽取方式，没有剥掉标点。修法：生成时 strip 掉尾随的 ':'（并给 ASVS 编号加形如 ^V\d+(\.\d+)*$ 的形态校验），再重新生成清单。

### `docs/mirrors/python-pep-code-style/manifest.json:118-124` · maintainability · 未复核

references 字段存的不是引用链接，而是 PEP 8 正文里一段说明性散文（"Hanging indentation is a type-setting style..."、"Barry’s GNU Mailman style guide http://..." 等）。键名承诺的是“参考资料”，实际内容是一段被误抓的正文段落，属于抽取串位：读这份清单的人会以为列出了该页的引用来源，实际拿到的是无关段落。修法：修正抓取选择器（references 只收链接/文献条目），或把该字段改名为与内容相符的键；两者都做不了就先清空，别留下名不副实的数据。

### `docs/project/architecture/tech-detail/02-dsh-Hook-内部流程/cells.py:372-373` · documentation · 未复核

这一节写「下面把六条失败路径各跑一次」，但枚举把同一件事写了两遍、又漏掉真正存在的第六条：「重放同一次调用」与「**上一次已经放行过的那次调用再来一遍**」指的是同一个场景（都是 `run_hook(event("pre-tool-use-edit-allow.json"))` 再来一次 → `event_replay`），而紧随其后的代码只跑 5 条（第 433-439 行 `cases`：未知工具 / 未知事件 / 越界路径 / 超时 / 重放）；第六条「接线不等式不满足」在第 4 节第 521-529 行才跑。小结第 771-772 行却按六条（含接线不等式）写，前后口径不一致，按本节枚举核对的人会以为少跑了一条。建议：枚举与…

### `docs/project/architecture/tech-detail/03-检索-SQLite-FTS5/03-检索-SQLite-FTS5.py:14` · documentation · 未复核

开头宣称「九个步骤按顺序**真的跑一遍**」，但本文件只有 7 个编号步骤（第 105、144、253、300、367、434、559 行的 `# ---- 1)` … `# ---- 7)`），正文只有 5 个小节（第 89、235、350、419、541 行）；内容源 03-检索-SQLite-FTS5/cells.py 第 11 行的 summary 与 tech-detail/README.md 第 47 行的 03 行也都只列 8 段链路——没有任何一种口径能数出九步。这句是「配合同名图」时代的遗留：`git log -S 九个步骤` 显示 4010b85 的原句是「这份 notebook 配合同名图 `03-检索-SQL…

### `docs/project/architecture/tech-detail/03-检索-SQLite-FTS5/cells.py:18` · documentation · 未复核

开头（第 18 行）说『九个步骤按顺序真的跑一遍』，但本文件只有 7 个编号步骤（# ---- 1) 到 # ---- 7)，正文只有 5 个小节（## 1 到 ## 5）；SPEC 的 summary（第 11 行）与 docs/project/architecture/tech-detail/README.md:47 都把这条链路写成 8 段。别的章节里『九步』都有 9 行步骤表或 9 段链路图支撑，只有这里对不上，读者会去找不存在的两步。建议把『九个步骤』改成『七个步骤』（或删掉数字），改完重跑 build_notebooks.py 重新生成同名 .py / .ipynb。

### `docs/project/architecture/tech-detail/04-受控执行/cells.py:451-454` · bug · 未复核

第 444 行已经显式允许 outcome.evidence 为 None（effect = None if outcome.evidence is None else ...），但第 451-454 行在守护断言（第 460 行 assert effect is not None and effect.changed）之前就先解引用 effect.changed / effect.sha256_before / effect.sha256_after / effect.diff_digest。一旦这次执行没有产出证据（例如执行被拒或事后验证没跑成），读者看到的是 AttributeError: 'NoneType' object …

### `docs/project/architecture/tech-detail/07-LangGraph-编排/07-LangGraph-编排.py:88-116` · maintainability · 未复核

死导入：下面这些名字在整份文件里只出现在导入行，代码里从未引用——DecisionOutcome(88)、PlatformReadiness(89)、RetrievalOutcome(90)、END(99)、LIMIT_RULES(100)、StageStatus(112)、OrchestrationConfig(116)。这些导入都带 `# noqa: E402`，说明作者预期它们会被 ruff 检查，但仓库里没有任何一步对 docs/** 跑 ruff（ci_local 的步骤全部读自 workflow，里面只有 pytest 与各阶段自检；validation/ruff.toml 只服务验证器流水线），F401 不会替这里报出…

### `docs/project/architecture/tech-detail/07-LangGraph-编排/07-LangGraph-编排.py:867` · documentation · 未复核

版本口径过期，并把两条版本轴写混了：正文说 `STATE_SCHEMA_VERSION`「当前 1.0」，但 src/orchestration/models.py:57 里它已经是 1.1（台阶 3a 因为 ValidationSummary.reason_code 与 ViolationRef.evidence_kind 进了状态而递增），1.0 是 checkpoint 自己的另一条轴 `CHECKPOINT_SCHEMA_VERSION`（src/orchestration/checkpoint.py:49）的值。仓库里别处都只写「有自己的版本轴」而不写死数字，所以只有这一页会把读者带偏。建议改成不写死具体值，或改写成 1.…

### `docs/project/architecture/tech-detail/09-能不能成为规则/09-能不能成为规则.py:276-284` · maintainability · 未复核

判据三的表格里 `known` 被赋值四次却从未被读取（第 276、278、280、282 行 `origin, known = …`，第 284 行只用 `origin` 与 `used` 拼输出行），属于死变量；而上方 markdown 声称「这一格把 6 个维度的取值口径也一起摆出来」，实际打印的三列表里根本没有取值那一列——取值范围算出来又被丢掉，讲解与代码对不上。建议把 `known` 作为一列打印（例如 `pad("，".join(known) or "（无）")`），确实不需要就删掉这个变量。同内容的 09-能不能成为规则.ipynb 同理；真正的改动点在内容源 09-能不能成为规则/cells.py（那里的行号是 2…

### `docs/project/architecture/tech-detail/build_notebooks.py:157` · bug · 未复核

`next(...)` 没有默认值：只要某个单元（含 markdown 单元）出现字面量 "pad(" 而该章没有任何代码单元，这里就抛 StopIteration，脚本以 traceback 退出；而 guard_spec 里专门为这种情况写的"没有任何代码单元：那就不是「可执行讲解」了"（210–211 行）永远来不及报。给 next 加默认值，或先判断有没有代码单元再注入 TABLE_HELPER。

### `evaluation/thresholds.yaml:28` · documentation · 未复核

第 28 行注释写「id 取 `eval-datasets.yaml` 的条目 id 原文」，但 evaluation/ 下并没有这个文件——真实的唯一登记表是 docs/project/engineering-policy-platform/testing/eval-datasets.yaml（evaluation/README.md:461 用相对路径指的就是它）。照注释去 evaluation/ 找会找不到，把数据集的唯一真相源说成一份不存在的文件。建议注释里写全路径。

### `knowledge/corpus.yaml:149` · documentation · 未复核

rule_sources 的现状注释写"policies/** 里有 39 条规则来自 6 篇 PEP 与 15 篇 OWASP Cheat Sheet 镜像"，但本文件实际登记 38 条 rule_sources（python-pep-code-style 19 条 + owasp-cheatsheets 19 条），policies/ 下 source.kind=standard 的规则也正好 38 条（与 AGENTS.md 的"38 条由镜像原文提炼"一致）；"6 篇 PEP"也与本文件只登记 2 篇 PEP 文档不符。数字偏大 1 会让"文档→规则"覆盖面的判断出错。

### `src/adapters/base.py:263-284` · maintainability · 未复核

`EventAdapter` 这个 Protocol 是死声明，而且与包级同名导出冲突：全仓只有声明处与 `base.__all__`（base.py:70）提到它，`loader.build_adapter` 用的是 `event_adapter.EventAdapter`（loader.py:27 / 52，一个 `Adapter` 子类），`adapters/__init__.py:37` 又把这个**同名的具体类**当作包级 `EventAdapter` 导出。于是 `from adapters import EventAdapter` 得到实现类、`from adapters.base import EventAdapte…

### `src/adapters/cli.py:763-774` · bug · 未复核

`--record-check` 形态只对活体探测有意义的三面旗子里，`--probe-binary` / `--require-runtime` 被显式拒绝（第 763-774 行，理由写得很清楚：静默忽略会把"我明明指定了"变成空操作），但 `--timeout-ms` 漏了：它在第 742 行被解析成 `timeout_ms`，而 record-check 分支（821-838）从头到尾没引用它，于是 `python -m adapters.cli host-version --record-check --timeout-ms 1` 会一声不响地成功。建议把 `--timeout-ms` 一并纳入 host_only_fla…

### `src/adapters/conformance.py:353-366` · maintainability · 未复核

`render_event` 的 `outside` 参数从未被读取：函数体在第 366 行用 `Path(workspace).resolve().parent / "outside-workspace.py"` 自己重算同一个值，参数在正文里没有任何引用。这条参数还被 `_run_scenario`（543 / 558）与 `run_conformance`（691 / 781）原样透传，`cli.run_check`（cli.py:282）专门算好再传进来——调用方以为"越界目标由我指定"，实际被静默忽略：传一个别的路径不会有任何效果（当前两边算法恰好一致，所以现在看不出问题）。建议删掉整条参数链，或真的改用传入值（用它替换第…

### `src/adapters/conformance.py:383` · maintainability · 未复核

`scenario.event_type.endswith("teleport")` 恒为 False，是一段不可达判断：SCENARIOS 里 12 条场景的 `event_type` 全是 `EventType.TOOL_PRE_EXECUTE.value`（"tool.pre_execute"），`EventType` 枚举里也没有 teleport 类成员；"协议故意不认的事件名"是靠 `wire_name` 表达的，且紧随其后的第 384-385 行已经用显式名单处理了 unknown-event / unknown-version。因此这个三元表达式永远走 `_tool_name(...)` 分支，子句只会让读者以为存在…

### `src/adapters/dsh/enforcement.py:138-142` · bug · 未复核

post_event_fields 用 str(...) 取三个标识字段：载荷里 session_id 为 null（或数字、列表、对象）时会得到 "None"/"123" 这类非空字符串，下面的非空判断因此照样通过，等于把标识'编'出来而不是失败关闭。这与同一条链路上的既有纪律相反：hooks.call_action_id 用 `raw.get(...) or ""` 把 None 变成空串并返回 None，其 docstring 明说'编出来的标识会让事后核对接错动作，比没有标识更危险'；PreToolUse 侧的 read_payload 也会直接拒绝非字符串的 session_id/tool_use_id，两侧口径不一致。建…

### `src/adapters/dsh/enforcement.py:446-448` · bug · 未复核

FINAL_DECISION 的 outcome 把除 validated 以外的所有状态都折叠成 repair_required，于是 PostStatus.INCONSISTENT（证据自相矛盾，同一份记录里的 post_status 就是 inconsistent，Hook 侧据此报 post_inconsistent，enforcement.PostOutcome 里它也是一个独立取值）在 outcome 这一栏被写成 repair_required——同一条记录里两个字段对同一件事给出两个名字（AGENTS 第 50 条）。修法：outcome 直接用 decision.status.value，或写一张 PostStat…

### `src/adapters/dsh/hooks.py:894-901` · bug · 未复核

_severity_visibility 的 advisory_rule_count 只数 `rule_set.get("warning", 0)`，而决策表里非阻断级别是 ALLOWING_SEVERITIES = {INFO, WARNING}（policy/models.py:241，SEVERITY 枚举里 info 是合法值、加载器也不拒绝）。规则集一旦出现 severity=info 的规则，blocking_capable_rule_count + advisory_rule_count ≠ rule_count，随附的 severity_note（'只有 error / critical 拦得住（N 条）…（M 条 …

### `src/adapters/dsh/hooks.py:1898-1906` · bug · 未复核

run_hook 把 PostToolUse 事件直接交给 post_execute_outcome，从不经过 handle()，而 _capture() 只在 handle() 里被调用（第 1145 行）：因此带 --capture 时同一份目录里只会有 PreToolUse 事件，PostToolUse 收到的原始 stdin 静默不落盘。这与两处声明不符：--capture 的帮助文本是'把收到的原始事件写到该目录（用于采集脱敏 fixture；不影响判定）'，tests/fixtures/agent_events/dsh/README.md 的'采集方式'写的是整组 fixture（表格里含 post-tool-use-e…

### `src/adapters/json_adapter.py:86` · bug · 未复核

`violations` 里非 Mapping 的条目被静默丢弃：86 行 `[dict(item) for item in violations if isinstance(item, Mapping)]`。 同一个函数上一行（63-65 行）还在对未知字段失败关闭，这里却把畸形条目从给 Agent 的响应里悄悄抹掉——消费方会看到比决策载荷更少的违规，且没有任何痕迹，与「未知字段一律报错、不得静默忽略」的口径（AGENTS.md 第 3 条）相反。建议发现非 Mapping 条目即抛 AdapterEventError，或明确把它记成错误通道而不是过滤掉。

### `src/adapters/runtime.py:20-21` · documentation · 未复核

模块 docstring 第 4 条仍写「熔断：同一个 `request_id` 下的受治理事件数超过上限即阻断」，而实现早已按 AGENTS.md §26 改成「同一 Agent 在窗口内的受治理事件数」（796 行 _window_events(agent_id)、794-795 行注释明说按 request_id 计数是实测出来的坑且「别再改回去」）。安全语义的模块级说明与实现相反，后来者照 docstring 改代码就会退回旧口径。建议：把第 20-21 行改写成按 Agent 窗口计数的口径。

### `src/adapters/runtime.py:29-40` · maintainability · 未复核

死导入：第 40 行 `from policy.models import SCHEMA_VERSION` 在本文件（含 __all__ 与全部注解）再无第二次出现；第 29 行的 `import re` 也被 sanitize_message 内部的局部 `import re`（204 行）遮住，模块级那一次没有任何读者。前者尤其危险：policy.models.SCHEMA_VERSION 是决策协议轴，摆在适配层运行时的导入表里会造成「这里也管协议版本」的错觉（运行时真正的版本轴是 AGENT_RUNTIME_SCHEMA_VERSION）。建议：删掉两行导入，并删掉 204 行的局部 import。

### `src/adapters/runtime.py:1429-1453` · bug · 未复核

_adapt_failure 走 _refuse 时没有传 response_kind（_refuse 默认 ResponseKind.JSON），因此「Adapter 事件转换失败」这一类拒绝给出口的响应形态与能力声明不一致：dsh / legacy-post-only 的 manifest 三处都声明 response_kind: exit_code，其余所有拒绝点（790-1237 行）都老老实实传了 response_kind。目前 hook_command_result 只按 decision 算退出码，所以不影响阻断语义，但 AgentResponse 的 response_kind 字段是对外载荷的一部分，消费者按它分…

### `src/enforcement/action.py:172-192` · bug · 未复核

_check_constraints 只对字符串取值生效：`if isinstance(value, str): text = value`，其余类型 text 为 None，max_chars / pattern / enum 三项校验全部跳过；而 string_list 参数规范化后是 tuple（第 168 行），注册表里给它声明的 pattern / enum / max_chars 会被静默忽略（integer / boolean 上的 enum、pattern 同理）。同一份参数模型对相邻的字段组合写了显式拒绝（enforcement/models.py:615-618：path_kind 在非 path 类型上"会被静…

### `src/enforcement/cli.py:361` · maintainability · 未复核

注册表协议版本在这条 --json 载荷里写成字面量 "1.0"，而仓库唯一的版本常量是 models.REGISTRY_SCHEMA_VERSION（registry.py:209 的 registry_payload 用的就是常量）。一旦注册表协议升版（改 registry/tool-registry.yaml 的 registry_schema_version 与常量），这里仍会报 1.0，读的人会按错误版本解释权限表，也不符合 AGENTS.md §55“版本轴只有一处声明”。改为引用 models.REGISTRY_SCHEMA_VERSION。

### `src/enforcement/cli.py:704-733` · bug · 未复核

审计文件缺失被读成“校验通过”。FileAuditSink._scan() 在 path 不存在时返回空列表，于是 verify() 没有任何 issue，本命令打印“审计链校验通过”并退出 0——产物根本没有生成，门禁却是绿的。同一个 CLI 的 verdict 子命令对同一情况直接报 CliError（cli.py:743-744「审计文件不存在」），两处口径相反。CI 里 verify 就是门禁（.github/workflows/phase-8.yml:207），建议把“文件不存在”作为显式状态（不适用/配置错误，非 0 退出），不要真空通过。

### `src/enforcement/drivers.py:352-375` · maintainability · 未复核

三个模块级辅助函数全仓库无任何引用（含 tests/ 与文档）：default_drivers 的文档写“测试与简单场景用”，但 tests/ 里没有调用；python_executable 的文档写“测试与示例用它构造确定性的 argv”，同样没有调用方（tools/ci_local.py 中的同名标识是 argparse 的 dest，与本函数无关）；environment_with 也无引用。它们不在 __all__ 里、也没有消费方，属于死代码：要么接上调用点，要么删除（若作为端口预留，应在模块文档里写明并加用例覆盖）。

### `src/enforcement/executor.py:555-558` · bug · 未复核

collect_post=False 时不跑事后验证（post 保持 None），但 _final 的 else 分支照样给出 outcome=delivered、detail="执行完成，事后验证通过"——把“没有收集事后证据”写成“事后验证通过”。这段 detail 会进审计的 FINAL_DECISION 记录与 CLI 输出，是读的人判断该动作是否被验证过的直接依据。建议 post is None 时给出显式措辞（例如“执行完成，未收集事后证据”），不要复用验证通过的文案。

### `src/enforcement/postcheck.py:218-223` · maintainability · 未复核

死代码：模块私有函数 _change_expectation（218-223 行）在整个仓库里没有任何引用（grep 只有定义处），函数体还忽略 request 参数、在 effect=file_write 时恒返回 True；ruff/mypy 都不会报「未使用的模块级函数」，建议直接删除。另：362-365 行的 DELEGATED 分支与紧随其后的 `if effect.changed` 分支返回语句逐字相同（被后者完全覆盖），是等价冗余分支，会让人误以为委派执行与平台执行在这里走了不同判定。

### `src/enforcement/registry.py:104-122` · bug · 未复核

角色/权限表的键先经 canonical_identifier（strip+lower）规范化再写进 dict，大小写不同的重复键被静默合并、后者覆盖前者，加载期不报错。_as_token_mapping（106-121 行）里 roles: {Reviewer: [repo.approve], reviewer: [repo.read]} 会得到 roles["reviewer"]=(repo.read,)，前一份权限清单无声消失；288-293 行的 permissions 同理由规范化后的键覆盖（那里只丢备注，影响较小）。这与本模块「拒绝重复键、配置不得有歧义」的加载纪律相悖：规范化后的重复键应当报 RegistryError…

### `src/orchestration/approvals.py:31-42` · maintainability · 未复核

approval_binding_digest（31-34）与 ApprovalDecision（37-42）在仓库里零引用：除 __all__ 与自身定义外，src / tests / tools 全仓 grep 不到任何使用点（gate.use 只返回 ApprovalUse，没有任何地方构造 ApprovalDecision）。前者还与自己的 docstring 不符——文字说绑定“这三件事”（action_hash、动作、工具），函数只接受 action_hash 与 action_id，返回值就是 f"{action_hash}|{action_id}"。建议要么接上（例如 gate.use 返回 ApprovalDeci…

### `src/orchestration/approvals.py:190-193` · maintainability · 未复核

verify_approval 抛错时被统一翻译成 ApprovalError("审批被平台拒绝：ApprovalError")：Phase 4 给出的具体理由（例如“审批签发时间在未来”“审批人没有审批权”）被丢掉，原始异常只挂在 __cause__ 上，不会进 state / run 记录；同时沿用异常类的默认 code = APPROVAL_MISSING，于是“审批人角色不符”会被记成“缺少与当前 action_hash 绑定的审批记录”。终态仍是 needs_human，但归因是错的，人也看不到该怎么改（AGENTS.md §52：拦住只完成一半，还要给对的原因）。建议把 Phase 4 的 detail 原样带进 err…

### `src/orchestration/checkpoint.py:235-267` · bug · 复核：部分成立（级别已修正）

恢复时 REVALIDATE 分支在 reapprove 之前 return：当兼容性同时命中 rule_set_hash/index_version 与 tool_schema_hash 变化时，cleared 只清 traces/validation/test_validation/contexts/stage，`approvals` 一个都不清，`_REAPPROVE_DIMENSIONS` 的清理（第 255-267 行）永不执行——而第 216 行的文档与 AGENTS.md §36 都写明「工具 schema 变了旧审批作废」。旧 ApprovalUse（绑着旧 action_hash）会留进新一轮状态与后续 check…

### `src/orchestration/cli.py:331-334` · bug · 未复核

第 331-333 行注释声称「--json 在子命令前后都能用」，但放在子命令之前时会被 common 子解析器的默认值 False 覆盖（argparse 自 3.7 起把子解析器解析进新 namespace 再整体写回父 namespace；实测 3.11：['--json','self-check'] → False，['self-check','--json'] → True），于是 `python -m orchestration.cli --json status --task-id x` 静默退回人类可读输出，脚本拿不到 JSON。修法：子命令的 --json 用 default=argparse.SUPPRESS，…

### `src/orchestration/client.py:534-546` · bug · 未复核

`_get` 的 200 分支直接 json.loads(raw)，json.JSONDecodeError 不在 534-546 的 except 里（HTTPError 分支 540-543 反而专门捕获它）：健康检查返回 200 + 非 JSON 时 readiness() 抛裸 JSONDecodeError，而不是像 _post（500-507）与第 545-546 行注释「拿不到凭据如实说不知道」那样按 unknown 处理，能力查询失败被上报成「编排自己坏了」。修法：200 分支同样捕获 json.JSONDecodeError 并返回 (status, {})。

### `src/orchestration/nodes.py:556-563` · maintainability · 未复核

`_apply_change` 的形参 `round_index` 声明了却从不被读：`repair` 在第 553 行显式传它，函数体内（556-734 行）没有任何引用——轮次其实是由 `_action_id` 内部的 `state.counters.repair_rounds` 决定的，传不传结果一样。留着会让后来者以为轮次参与了幂等键的构造。建议删掉形参，或真的把它用进键里。同一文件第 489 行的 `_REPAIRABLE_REASONS` 同样无人引用（只有 `_UNREPAIRABLE_REASONS` 被 `repair` 读），也是同一类死代码。

### `src/orchestration/tools.py:376-379` · maintainability · 未复核

`tool_params` 是死代码：全仓库没有任何调用点（唯一同名命中是 tests/security/test_multi_agent_adversarial.py:147 的测试函数名，不是调用），也不在模块 `__all__` 里。它渲染的是「只留键、不留值」的摘要，看起来是给展示路径准备的，但那条路径并不存在。建议删除，或真正接进使用它的地方并在 `__all__` 登记。

### `src/policy_api/app.py:43-47` · maintainability · 未复核

`route_table` 在 `__all__` 里导出，但全仓库没有任何读取点（只有本文件第 40 行的 `__all__` 与第 43 行的定义）；同一份 URL→运行时路由名映射又在 `create_app` 里以四元组形式硬编码了一遍（208-227 行）。两份声明之间没有绑定，改一处漏一处就会让「台账键/指标键/错误分类都用运行时名字」这个约定与真实路由悄悄分叉。建议删掉，或让 `create_app` 的路由注册直接从 `route_table` 生成。

### `src/policy_api/app.py:179-181` · security · 未复核

`docs_url=None` 的理由写的是「它会把全部 schema 暴露给未认证的访问者」，但紧挨着的 `openapi_url="/v1/openapi.json"` 仍然开着：FastAPI 的 openapi 路由不带任何依赖，`create_app` 里也没有认证中间件（认证发生在 `runtime.handle` 内部），未认证调用方照样能拿到整份 paths、DTO 形状与 `ErrorCode` 枚举——正是被关掉的交互文档所暴露的那份 schema。要么给该路由加认证或关掉它，要么把理由改成「只是不提供交互界面」，否则注释与代码互相矛盾。

### `src/policy_api/contract.py:207-209` · maintainability · 未复核

`_core_is_framework_free` 在找不到 `src/policy` 时返回 True：自检于是报 `core_has_no_framework: ok`，但它一个字都没读——这正是 AGENTS.md 第 45 条说的「仪器不会失败」。以 wheel/zip 形态安装（`__file__` 落在 site-packages，`parents[2]/src/policy` 不存在）时，这条检查的默认结果是「通过」，而它本该是「查不了」。建议目录不存在时返回 False，或把该检查显式记为「未执行 / 不适用」而不是 ok。

### `src/policy_api/idempotency.py:306-312` · bug · 未复核

过期时间写入与解析的格式不一致：写入端（第 287-290 行）用 `datetime.isoformat()`，当微秒恰为 0 时 isoformat **不输出小数部分**（`...T12:00:00Z` 而不是 `...T12:00:00.000000Z`），而 `_fresh` 用 `strptime(expires, "%Y-%m-%dT%H:%M:%S.%fZ")` 解析，这种形态抛 ValueError → 第 311 行按「不能证明还有效」当过期处理，条目被删掉并重新执行一次判定，静默丢掉幂等保证（台账里的记录本身是合法的）。建议：写入端固定 `timespec="microseconds"`，或解析端改用 `dat…

### `src/policy_api/ops.py:153-154` · bug · 未复核

运算符优先级让兜底文案成为不可达分支：`"没有可服务的租户：" + ", ".join([...]) or "未装配任何租户"` 被解析为 `("没有可服务的租户：" + join) or "未装配任何租户"`，左操作数恒为非空字符串，`or` 的右支永远不执行。而恰好触发它的场景（没有任何租户、也没有装配错误）会输出一句悬空的「没有可服务的租户：」。建议显式分支：`detail = "没有可服务的租户：" + ", ".join([*failed, *missing]) if (failed or missing) else "未装配任何租户"`。

### `src/policy_api/runtime.py:949-954` · maintainability · 未复核

`_recordable(status, facts)` 的 `facts` 形参在函数体里从未被读取（只看 `status`），而调用点第 364 行郑重地把它传了进来——形参与实现不一致，读代码的人会以为「可重放」还取决于 facts（例如决策/违规计数），实际不取决于。建议删掉该参数，或真的按 facts 判定并在文档串里写明规则。

### `src/policy/check.py:38-42` · documentation · 未复核

模块文档串说 --json 外层包装「当前形状记为 1.1」，但同一文件里 OUTPUT_SCHEMA_VERSION = "1.2"（第 143 行，其注释与 AGENTS 第 55 条都把 1.2 记为现形状：顶层多一份 reading_context）。这份版本号正是消费方判断「外层键集合是哪一版」的依据，文档与常量互相矛盾时，按文档串读键集合的人会读错一版。建议：把文档串那段改成与常量一致（1.2 = 现形状，1.1 = 只有 check_volume 无 additional 形状），或直接引用 OUTPUT_SCHEMA_VERSION 而不复述字面量。

### `src/policy/evidence.py:6` · documentation · 未复核

模块文档串写着「证据不改变决策协议：PolicyDecision 仍是 schema_version 1.0」，但决策协议已经是 1.1（models.py:108 SCHEMA_VERSION = "1.1"，SUPPORTED_SCHEMA_VERSIONS 只收 1.1，1.0 载荷按 AGENTS 第 7/55 条一律拒收）。这是与实现相反的协议代际陈述，会让人以为存在 1.0 兼容窗口。建议：改为指向 policy.models.SCHEMA_VERSION / POLICY_VERSION，不写死字面量。

### `src/policy/models.py:874-891` · bug · 未复核

_normalize_dependencies 用 raise TypeError（第 880 行）拒绝字符串取值，但 pydantic 只把 ValueError/AssertionError 转成 ValidationError，TypeError 会原样穿出 PolicyContext(**payload)。于是 build_context 的 except ValidationError（context.py:178）与 API 的 except PolicyContextError（policy_api/runtime.py:207）都抓不到它："dependencies 写成了字符串"这类形状错误变成未处理异常，而不是既…

### `src/policy/models.py:1124-1131` · bug · 未复核

parse_decision 对非字符串的 schema_version 抛的是 TypeError 而不是 ProtocolError：第 1127 行 `version not in SUPPORTED_SCHEMA_VERSIONS` 在 frozenset 上查不可哈希对象（例如 "schema_version": ["1.1"]）会抛 TypeError: unhashable type。函数的契约是"版本不符一律 ProtocolError"，而消费方只捕 ProtocolError（retrieval/cli.py:297、orchestration/client.py:392），于是坏载荷变成未处理异常，而不是可控的…

### `src/provenance/cli.py:48-55` · security · 未复核

`_display` 的兜底分支会把**工作区之外的路径按绝对路径原样写进回执**，与它自己的 docstring「回执里的路径一律相对根渲染：绝对路径不进产物」矛盾：只要 `--declaration` / `--platform` / `--out` 指到 root 之外（例如 `--root . --declaration C:\tmp\decl.txt`），`relative_to` 抛 ValueError 走兜底 `target.as_posix()`，产物里就留下 `C:/tmp/decl.txt`。这正是 AGENTS 第 16/19/34 条要求脱敏的东西，同一仓库的 `provenance.reading_con…

### `src/provenance/cli.py:155-166` · bug · 未复核

`--peer-evidence` 只校验了「JSON 能解析」：顶层不是映射时（文件内容是 `[]` / `"x"` / `5`）`json.loads` 照样成功，随后 `worktree.resolve_landing_state` 里 `peer_evidence.get("verifier", "")`（worktree.py:449）抛 AttributeError。该异常不是 `LandingStateError`，第 164 行的 except 接不住，于是带 traceback 退出 1——而退出码 1 在本模块的契约里是「判据 fail」，一次用法错误被读成判据不通过。建议 `json.loads` 之后显式要求…

### `src/retrieval/chunker.py:8-9` · documentation · 未复核

模块文档第 8 行承诺「代码块是**原子单元**：不在中间切断，也不与其它块合并」，但 `_pack` 的打包路径 2（465-498 行：`joined <= max_chars` 就把块继续装进 current）允许把相邻的正文块与代码块合成同一个 chunk，flush() 再把它标成 ChunkKind.MIXED（459-461 行）；tests/unit/test_chunker.py::test_mixed_block_kind_is_reported 正是钉住这个行为。实现与既有用例都说明混块是设计的一部分，只有文档这句话是错的，读者会据此认为正文与代码永不共享 chunk（进而误判 chunk 的 kind/边界语…

### `src/retrieval/chunker.py:341-361` · bug · 未复核

章节内块的行号整体少 1。`find_sections` 遇到标题时把 `current_start` 设为标题所在行（379-381 行），但标题行本身不进 buffer（382 行的 continue 跳过 append），buffer 的第一行实际是标题的下一行；而 flush() 又用 `current_start` 作为 `iter_blocks(text, line_start=current_start)` 的基点（343 行），于是除前言外的每个章节，其 Section.line_start 与块内 Block.line_start 都比真实行号小 1。实测 `find_sections('# A\nprose on…

### `src/retrieval/corpus.py:230-233` · bug · 未复核

verify_corpus 是增量式的：它以 loaded.verification.issues 为基底再追加本轮算出的 missing_file / hash_mismatch / size_mismatch / license_source_missing。但 load_corpus 返回的对象里 verification 已经是同一次计算的产物（第 328 行），CLI 的 verify 又在它之上再调一次（cli.py:337），于是每条文件/哈希/大小/许可问题都会在 --json 的 issues 与文本输出里出现两遍。ok 与退出码不受影响，但读报告的人、按条数统计的消费方会读到双份。建议让 verify_corpu…

### `src/retrieval/vector.py:154-155` · bug · 未复核

VectorRetriever.retrieve 直接取 self.store.index_version（第 155 行）与 self.store.embeddings(...)（第 193 行），没有捕获 StoreError；同样的调用在 FtsRetriever 里是包在 try/except StoreError 中并返回 status=unavailable / reason=index_missing 的（retriever.py:148-160）。本文件对后面的 candidates 反而做了捕获（第 214 行），说明这是漏掉的一处。索引库损坏或不可读时，向量路径会抛异常而不是给出结构化的 unavailable，…

### `src/validators/adapters/pytest_runner.py:345-353` · bug · 未复核

「待实现」的证明建立在完整模块索引上，但 ModuleIndex.truncated（depgraph.py:65，扫描超过 max_files=20000 时置位）从未被任何消费方读取：索引被截断时「模块不在索引里」推不出「模块不存在」，_pending_target 会把它当成「项目内还不存在」，于是一次真的收集失败被降级成 pending（warning 放行），与本文件「可能漏、不误报」的声明正好相反。修法：`if index is None or index.truncated: pending = False`（证明不了就落回真违规）。

### `src/validators/adapters/ruff.py:187-192` · bug · 未复核

location = item.get("location") or {} 之后直接调用 location.get(...)，但 try 只捕 (TypeError, ValueError)：工具输出是不可信数据，只要 location 不是对象（换版或包装器产出 "location": []）就会抛 AttributeError，最终被 pipeline 的 except Exception 记成 crashed（pipeline.py:916），而不是本模块承诺的 output_invalid。修法：先 isinstance(location, Mapping) 再取值（或把 AttributeError 一并纳入捕获）。

### `src/validators/docstrings.py:48` · bug · 未复核

内置 docstring 验证器把证据 severity 硬编码成 Severity.WARNING（第 48 行与第 88 行），没有像 ruff/mypy/pytest 三个适配器那样取 rule.severity。证据 severity 不是纯展示：validators.cli 的 _evidence_exit_code（cli.py:237-241）靠它决定 check 的退出码，render_report（pipeline.py:395）也把它打进报告。只要出现一条声明 severity: error 的 missing_docstring 规则，check 就会以 0 退出、报告标成 warning，而 pipeline…

### `src/validators/models.py:93-99` · bug · 未复核

_check_command 只在 `not any(values)` 时报错（即全部为空才拒绝），但错误信息写的是「tool.command 不能有空元素」——校验没有实现它声称的规则：["", "ruff"] 与 ["ruff", ""] 都能通过加载，前者要到探测阶段才变成 unavailable，后者会把一个空参数交给子进程。修法：改成 `if not all(values)`（或逐个检查空串）。

### `src/validators/python_ast.py:265` · bug · 未复核

模块 docstring 与定义 docstring 用了两套判空口径：定义走 `_has_docstring()`（要求字面量 strip 后非空，144-154 行），模块却只判 `_docstring_of(tree) is not None`（265 行）——只要第一条语句是字符串字面量就算「有 docstring」。实测 `parse_module('""').module_docstring` 与 `parse_module('" "').module_docstring` 都是 True，而 `def f(): ""` 的 DefinitionFact.docstring 是 False。后果：docstrings.p…

### `tests/api_support.py:166-167` · bug · 未复核

占位符残留守卫漏掉带数字的占位符：`\{[a-z_]+\}` 匹配不到 `{token_sha2}`（模板 288 行的替换目标之一），所以一旦那条 `replace("{token_sha2}", ...)` 被删掉，`leftover` 仍然为空、317 行的"必须当场失败"不会触发（配置里会留下字面量）。改成 `\{[a-z0-9_]+\}`。

### `tests/enforcement_support.py:224` · test · 未复核

空工具表被静默替换成默认工具表：`tools or TEST_REGISTRY_TOOLS` 在 `tools=()` 时为真值判断回落到 6 个内置工具，`write_registry(root, tools=())`（252 行同一条路径）也一样，调用方想声明"这个注册表没有任何工具"会拿到另一份数据，用例静默跑偏而不是报错。改成 `TEST_REGISTRY_TOOLS if tools is None else tools`。

### `tests/orchestration_support.py:413-416` · documentation · 未复核

两处 docstring 里出现 `@@BT@@` 标记（413、416 行），仓库里没有任何工具或文档定义它，同一文件其它 24 处都用普通反引号，读者看到的是坏文本（应为 `RecordingToolRunner` / `PlatformToolRunner`）。改回反引号即可。

### `tools/ab_arm.py:362-370` · bug · 未复核

给了 --tool write --new X（未给 --content）时，发给 Hook 的 tool_input.file_text 取自 new_value（362 行），但 370 行先把 new_value 置 None，再以 content=None 调 apply_edit（456 行）→ 走 edit 分支、old 为 None，必然 applied=False，记 action=apply_failed + unavailable，理由却是「old_string 在目标文件里找不到（唯一匹配）」——对一次 write 调用，这个归因是错的（AGENTS §52：拒绝理由必须正确）。建议 write 分支把同一份内…

### `tools/ab_arm.py:493` · bug · 未复核

把**目录**传给了只读单文件的 sha256_file：Path.read_bytes() 抛 OSError 被吞成 None，于是 run.json / self-proof.json 的 baseline.digest 恒为 null（同一函数用在 baseline / path 这种真实文件上才有值）。「基线是哪棵树」的绑定字段被静默置空，读的人会以为基线没有摘要。建议改调 tree_digest(baseline)（或 provenance.worktree.workspace_tree_digest），并在失败时显式写 reason 而不是 null。

### `tools/ab_arm.py:575` · bug · 未复核

交给下游的 measurement_input.json 里 governance.violations_by_severity 被写死成 {}，而同块的 diagnostic_count 是从 audit 记录算出来的：审计记录里本来就有 violations / violations_by_severity（AGENTS §46），判定真的报了违规时这份载荷仍写「按级别分布为空」，读者无法把它与「没有违规」分开。建议从已读到的 records 折叠出真实分布；若本工具确实不算这一项，就删掉这个键，别用一个恒空值冒充读数。

### `tools/ab_arm.py:1451-1458` · maintainability · 未复核

死代码：normalized 算出来从未被使用（下面的匹配仍用原始 node 做 endswith + 子串），行 1451-1458 的归一化意图（"x.py::case" → "x.py::case" 形态）没有落到匹配上，与 junit 的 classname 命名不一致时只会被读成 missing。建议删掉这一行，或真的用归一化后的值参与匹配。

### `tools/ab_arm.py:1563-1566` · bug · 未复核

L5 只扫 $USERPROFILE/.dsh 或 $HOME/.dsh，忽略仓库自己认定的其他 dsh 配置根（$DSH_HOME、%APPDATA%/dsh、%LOCALAPPDATA%/dsh，见 src/adapters/wiring.py::_dsh_home_candidates）——接线挂在 $DSH_HOME 下就扫不到。且根不存在时该函数返回 status=not_applicable（没有 hit_count 键），leak_assertions 用 wiring.get("hit_count", 0) == 0 把它判成 L5 pass：**没看却说 pass**，与该函数注释「每条只有 pass/fail/u…

### `tools/ab_measure.py:893-897` · bug · 未复核

unified diff 的 `is_new` 永远不会是 True：解析只在 `+++ …` 行上判 `endswith("/dev/null")`（新文件的 /dev/null 出现在 `---` 行），赋的又是默认值 False，全文件没有第二处赋值。于是 `_changes_from_diff`（2619 行）算出的 `whole_file` 对新增文件恒为 False，与 840 行“new_file 整文件视为改动”的口径不一致。当前消费方只读 `lines`，所以暂无可观察后果，但字段本身是错的。修法：在 `--- /dev/null` 时置 True，或删掉该字段。

### `tools/ab_measure.py:2572-2576` · bug · 未复核

`evidence_digest` 与它旁边的 `evidence_path` 指向的文件对不上：先把 `json_dumps(payload)` 写盘，之后才往 payload 里加 `evidence_path`，再用**加了键之后**的 payload 算摘要。于是 `sha256(证据文件) != evidence_digest`，这条自报摘要无法用来校验那份文件（读的人按名字会以为可以）。修法：先定稿 payload 再写盘再算摘要，或让摘要只覆盖写盘的那份文本。

### `tools/api_loop.py:46` · maintainability · 未复核

模块级常量 `AGENT_FIXTURE` 定义后从未被任何代码引用（全仓库检索该名字只有定义这一处），是死代码：`scenario_consumers_agree()` 用的是 `DEMO_ROOT / "workspace"`（第 274 行）而不是这个探针夹具路径。建议：删掉该常量；如果它本来是「受控工作区应指向 tests/fixtures/agent_events/workspace」的意图，则把用错的地方改成它。

### `tools/check_arch_style.py:81-84` · bug · 未复核

`check_docs()` 对 `ARCH.glob("*.md")` 的结果没有任何空集合守卫：`docs/project/architecture` 若被改名、移动或路径写错，`glob` 返回空、`problems` 为空，`main()` 会打印「概括性与精确性平衡，未发现失衡项」并退出 0——一次什么都没检查的空集合被报成「通过」，正是本仓库反复强调要避免的静默失效形态（`tools/check_repo_consistency.py:243-247` 对 notebook 空集合就显式记问题：「检查器不会静默通过一个空集合」）。建议：文档集合为空时记一条问题并退出 1（说明期望目录里至少有一份 .md）。

### `tools/ci_local.py:1220-1229` · bug · 未复核

执行计划为空时门禁仍报「通过」。`main()` 没有 `plan` 非空的守卫：若三个 ALWAYS 步骤（Repository consistency gate / Secret scan gate / Text conventions）因 run 块被改成 heredoc、`/tmp/` 之类而被 `_looks_unsafe()` 判成 bash-only，`plan` 就是空的，脚本照样打印「本机检查全部通过（0 步）」并 `return 0`，pre-push 钩子据此放行一次「一步都没执行」的门禁。仓库对同类空集合是有明文纪律的（`tools/check_text_conventions.py:115-117`「git…

### `tools/control_plane_facts.py:999-1003` · documentation · 未复核

这段 note 的自述已过期，而它是会被 --json 与门禁读数看到的载荷字段：工具已经接成本机门禁的只报告步骤（tools/ci_local.py:193-204 的 ReportOnlyStep(name="Control plane facts (report only)", args=("tools/control_plane_facts.py",))，tools/README.md:24 也写「已接为本机门禁的只报告步骤」），validation/instrument-checks.yaml:624-641 那一行已把 13 个 fact key 全部写进 covers_facts——fact_without_check…

### `tools/control_plane_facts.py:1300-1310` · bug · 未复核

人类可读输出的读数与「未评不是 0」这条口径相反。第 1309-1310 行按 cell["is_red"] 渲染标签，而未评格的 is_red 在 _cell() 里恒为 False（第 880 行），于是一次四格全未评的运行会打印四行 `[ok] <key>: unavailable`——扫标签的读者会读成通过，而同一文件 _cell 的注释正写着「未评不是不红」。同一段第 1301 行 _rows_text(len(budget["inventory_fact"]["channels"])) 也永远拿不到 None（len() 恒为 int），所以清点不可用时照样打印「wiring 通道预算 0 条（matched=False…

### `tools/enforcement_loop.py:256` · bug · 未复核

--keep 被解析却从未使用：args.keep 在全文没有第二个引用，main() 第 259 行无条件调用 prepare()，而 prepare() 第 56 行第一件事就是 shutil.rmtree(DEMO_ROOT, ignore_errors=True)。也就是说这个开关既不保留演示目录（与 help 里写的「保留演示目录（默认保留）」正相反），传了也毫无效果；同一仓库的 tools/dsh_sandbox_loop.py:247 是按 keep 分支实现的。建议要么实现（keep 时跳过 rmtree）要么删掉该参数并把 help 改对。

### `tools/eval_corpus.py:881-884` · bug · 未复核

_drop_reason 用字符串前缀（str.startswith）判断目标是否落在语料根内，这不是路径包含关系判定：同级目录只要名字以语料根目录名开头（如 …/eval-corpora/bandit-functional@<sha>-x/a.py），resolve() 之后仍会通过检查，随后 target.read_bytes() 会读它、按语料文件统计行数并写进 skipped 文案；「范围之外」本该拦住的这条路径漏掉了。annotation.file 来自上游 docstring 的 Location（_bandit_scan 375-378 行），是可构造的任意相对路径。改法：用 target.is_relative_to…

### `tools/eval_corpus.py:1393-1405` · documentation · 未复核

--json 的帮助写「与 --annotations/--list 搭配」（1393 行），但 --list 分支（1404-1405 行）调用 _command_list(root, lock_dir)，而 _command_list 的签名（1260 行）没有 as_json 参数、也从不读 args.json：`python tools/eval_corpus.py --list --json` 会静默退回文本输出（evaluation/README.md 也只记录 --annotations --json）。要么让 --list 真正输出 JSON，要么把帮助文本限制为 --annotations。

### `tools/governance_eval.py:171` · maintainability · 未复核

声明后从未使用的常量 / 属性 / 参数：`CORPUS_OPTIONAL`（第 171 行）全文件仅此一处（契约完整性只检查 `CORPUS_REQUIRED`）；`Unit.key` 属性（第 526–528 行）没有调用点；`per_rule(..., field_name)` 的 `field_name`（第 1479 行）与 `compute_gv04(..., suite)` 的 `suite`（第 1734 行）在函数体内无引用（调用处还照传）。仓库 ruff 的 select 未启用 ARG 系列，门禁不会替这里说话。建议删除，或让它们真正参与（如用 `CORPUS_OPTIONAL` 做契约检查、用 `Unit.k…

### `tools/governance_eval.py:1057-1062` · bug · 未复核

`module.lock_path` 抛异常时写下的 `outcome.lock`（含「锁文件位置推不出来」的 problems）会被紧随其后的 `module.verify` 分支**无条件覆盖**（第 1063–1077 行两条路径都重新赋值），这条诊断永远到不了载荷；此时 `lock_file` 仍是 None、`present` 记成 None，而 run_fidelity 的锁判据只查 `present is False` 与 `ok is not True`（第 3084–3093 行），于是「锁位置推不出来 + verify 报通过」会静默放过锁判据。建议把位置推断失败的事实合并进第二次赋值（而不是被覆盖），并让 `p…

### `tools/governance_eval.py:1194-1209` · maintainability · 未复核

`FileOutcome` 的五个字段只写不读：`raw_argv`（1172）、`decision`（1194）、`skipped_rule_ids`（1195）、`coverage_reason`（1207）、`unmapped_findings`（1209）赋值后全文件没有任何读取点（无 asdict/vars/__dict__ 之类的通用序列化，`dataset_payload` 也不含逐文件明细），这些逐文件读数被静默丢弃：文件级 Decision、language_coverage 的 reason、非结构性 skipped_rules 清单在载荷里都看不到，读者无法从审计复算「这个文件为什么没被查/判成什么」。建议要么…

### `tools/governance_eval.py:3138` · bug · 未复核

聚合调用传了 `blank_tokens=suite.blank_code_tokens`（第 2971–2973 行），逐数据集的调用（第 3138 行）没传，于是同一个 `blank_exclusion.blank_tokens` 键在顶层是 `["OKAY"]`、在 `datasets[].l1b` 里是 `[]`（已提交读数实测如此），`expected_pairs_with_blank_code` 也恒为 0——同名两义（AGENTS §50）：读者会以为该数据集没有空白期望标记、负例控制没生效。建议第 3138 行同样传 `blank_tokens=suite.blank_code_tokens`。

### `tools/governance_gap_probe.py:2191-2199` · performance · 未复核

--only 只过滤报告、不限制实际执行：factory(env) 在 wanted 判定之前被无条件调用，13 项缺口每次都全部跑完（各自起多个子进程，G04 里还有 time.sleep(2)），跑完再 continue 掉不需要的结果。这与 --help 写的“只跑指定缺口”不符，调试单项也要等全部跑完（单条命令默认超时 180s）。修法二选一：把过滤前移到 factory 调用之前（需要一份静态的 函数名→id 映射），或把帮助文本改成“只报告指定缺口”。

### `tools/instrument_self_proof.py:574-576` · documentation · 未复核

模块文档（第 68 行）写“影子索引落在 .tmp/instrument-self-proof/，用完即删”，但实现里只 mkdir，没有任何删除：GIT_INDEX_FILE 指向的 <SCRATCH>/shadow-index 会一直留在磁盘上（本文件没有 unlink/rmtree/shutil）。要么在 evaluate/run 结束时（含 --json 路径）删掉它，要么把文档改成“留在 .tmp/ 下，随 tools/cleanup.py 清理”。

### `tools/learn_site.py:249-254` · documentation · 未复核

_absolutize 的文档字符串写在第一条语句之后，因此它只是一个被求值后丢弃的字符串表达式：既不是 docstring（help()/pydoc/文档工具看不到），也掩护了“这段说明属于哪个函数”的事实。把这段三引号字符串移到函数体第一行，或改成 # 注释。

### `tools/mirror_docs.py:325` · maintainability · 未复核

python-pep-code-style 的站点配置里 outbound_why 出现了两次（line 263 与 line 325），同在一个 dict 字面量内，Python 静默保留后一个，前一份措辞（「不属本次镜像范围」）成为死配置，两处措辞已经不一致也没人会发现。建议删掉其中一份。

### `tools/mirror_docs.py:634` · bug · 未复核

sitemap 索引正则把 \s* 写成 s*：`<loc>s*([^<\s]+)` 要求 URL 紧跟 <loc>，一旦索引写成 `<loc>\n https://...` 就一个子 sitemap 也匹配不到；而兜底分支（line 636 用的是正确的 \s*）只在 subs 为空时执行，部分条目格式化时不会触发，子 sitemap 会被静默漏掉（发现范围缩小、无人察觉）。同一条正则尾部用的就是 \s*，可见是笔误。建议改成 r"<sitemap>.*?<loc>\s*([^<\s]+)\s*</loc>"。

### `tools/mirror_docs.py:930` · bug · 未复核

outline 模式的目录树宽度用 max(len(r[0]) for r in rows)，而 rows 由 ok（成功保存的页）推出：全部页面抓取失败或发现为空时 ok 为空、rows 为空，max() 抛 ValueError；此时旧镜像已被删除，工具以 traceback 收场，真实原因（每一页都 FAIL）被盖住。建议 rows 为空时跳过宽度计算，或直接以「0 页」报错退出。

### `tools/orchestration_loop.py:650-651` · maintainability · 未复核

make_run 用 shutil.rmtree(area, ignore_errors=True) 清运行目录，与同文件 remove_tree()（line 213-247）写下的纪律直接矛盾——那段 docstring 正是在说 ignore_errors=True 会把清理失败吞掉、让真正的占用原因被后来的错误盖住（闭环在本机因此连续失败过）。这里失败被忽略后紧跟 area.mkdir(exist_ok=True)，于是上一次运行遗留的 checkpoint/ledger 会被本次运行当成自己的状态（引擎见到 checkpoint 就转 resume 语义），场景可能在不干净的状态上给出 PASS。建议改用 remove_t…

### `tools/owasp_cheatsheets/03_build.py:20-29` · maintainability · 未复核

`asvs_sub` 是死变量：第 20 行建、第 29 行填，此后从未被读（`tags()` 只用 asvs_ch / pc / t10 / mas）。ASVS 小节标题的首词被算出来又丢掉，读代码的人会以为它进了 crosswalk。建议删除这两行，或把它落进 `tags()` 的输出。

### `tools/owasp_cheatsheets/pipeline.py:17-21` · bug · 未复核

第 17 行把 - / -- 开头的参数全部丢掉，于是 python pipeline.py --help（或任何拼错的 flag）得到空 args，走 todo = STAGES → **真的把 5 个阶段全跑一遍**（含 02_fetch 的网络抓取），而不是报用法错误或打印帮助；未知参数被静默忽略也与仓库「未知一律报错、不得静默忽略」的口径相反。建议识别到任何未知 flag 时打印用法并返回 2。

### `tools/pep_site.py:292-299` · maintainability · 未复核

front_extra() 是站点钩子（docstring 写「写入 front matter 的站点特有字段」），但引擎 tools/mirror_docs.py 只调用 pre_markdown / post_markdown / manifest_extra / manifests / pathmap / urlmap_extra，从不调用 front_extra——全仓库没有第二个引用。后果是它声称写入 front matter 的 Author/Status/Type/Created 只进了 manifest.json 的 pep_fields：docs/mirrors/python-pep-code-style/pep-…

### `tools/pep_site.py:318-322` · maintainability · 未复核

_rel() 定义后从未被调用：全仓库（含 getattr 形式的钩子查找）唯一命中就是这一行定义，是一段死代码，函数体内还做了 import posixpath。建议删除，或接上真正需要它的调用点。

### `tools/phase_evidence.py:328` · maintainability · 未复核

registry_schema_version 硬编码为 "1.0"，而 enforcement.models.REGISTRY_SCHEMA_VERSION 就是同一个值、并且已由本函数正在导入的 enforcement.registry 再导出。AGENTS.md §55 要求版本轴只有一处来源：注册表协议升版时这处副本会静默留在旧值，证据随之说谎。建议改从 enforcement.registry 导入该常量。

### `tools/policy_bench.py:108-127` · maintainability · 未复核

generate_contexts(count, *, seed=DEFAULT_SEED) 声明了 seed 却在函数体内一次都没用到（上下文只由 index 决定），而 measure() 又刻意传 `seed=seed`——读代码的人会以为这组上下文随种子变化、"同种子→同结论"覆盖了上下文生成这一环，实际没有。建议删掉该参数（或在生成里真正使用它）。

### `tools/secret_scan.py:85-88` · security · 未复核

scan() 对读不出/解不出 UTF-8 的文件直接 `return []`，而 main 仍把它计入"已扫描 N 个文件"。于是一个非 UTF-8 编码（如 UTF-16）的受版本控制文本文件里若藏着凭据，门禁会给出一份"干净"的绿报告——这是发布级安全门禁的失败开放（对比仓库对"无结果/无权限/不可用"三态的要求，AGENTS.md §11）。建议：把无法解码的文件作为显式发现（或至少打印警告并退出 2），而不是静默跳过。

### `tools/validator_loop.py:203-210` · maintainability · 未复核

scenario_missing_tool_fails_closed 把 5 个配置文件复制到 .tmp/phase-5-demo/missing-tool-config/validation/，但下一行用 `load_config(root=REPO_ROOT, registry=<临时注册表>)`：src/validators/registry.py 的 load_config 以 root 为 anchor 解析 project/test-layout（281-292 行）、_check_registry 也以 root 解析工具配置路径（160 行），所以那 5 份副本永远不会被读到，场景实际依赖的是仓库真实的 valida…

### `validation/instrument-checks.yaml:47` · documentation · 未复核

covers 口径段写"gate 44 行与 report-only 2 行是短句"，与本文件头部（第 12 行 gate_step 42、第 16 行 report_only_step 4）以及表内实际条数（gate-step 42 条、report-only 4 条、合计 64）矛盾；python tools/instrument_self_proof.py 的读数同样是 42/4。学习手册下线与台阶 5 接控制面读数之后计数改了，这一段没跟着改——读的人会按错的规模理解登记表覆盖面。改成 42 / 4 即可。

## 6. 逐包覆盖

| pack | 文件 | reviewed | skipped | 结论 |
| --- | --- | --- | --- | --- |
| P01 | 7 | 7 | 0 | 3 |
| P02 | 8 | 8 | 0 | 5 |
| P03 | 5 | 5 | 0 | 6 |
| P04 | 6 | 6 | 0 | 5 |
| P05 | 7 | 7 | 0 | 6 |
| P06 | 3 | 3 | 0 | 5 |
| P07 | 6 | 6 | 0 | 3 |
| P08 | 3 | 3 | 0 | 6 |
| P09 | 7 | 7 | 0 | 6 |
| P10 | 15 | 15 | 0 | 8 |
| P11 | 9 | 9 | 0 | 8 |
| P12 | 10 | 10 | 0 | 4 |
| P13 | 10 | 10 | 0 | 6 |
| P14 | 9 | 9 | 0 | 4 |
| P15 | 13 | 13 | 0 | 5 |
| P16 | 4 | 4 | 0 | 9 |
| P17 | 2 | 2 | 0 | 8 |
| P18 | 8 | 8 | 0 | 4 |
| P19 | 4 | 4 | 0 | 4 |
| P20 | 3 | 3 | 0 | 4 |
| P21 | 1 | 1 | 0 | 8 |
| P22 | 5 | 5 | 0 | 4 |
| P23 | 4 | 4 | 0 | 8 |
| P24 | 40 | 40 | 0 | 7 |
| P25 | 39 | 39 | 0 | 6 |
| P26 | 24 | 24 | 0 | 4 |
| P27 | 7 | 7 | 0 | 4 |
| P28 | 6 | 6 | 0 | 2 |
| P29 | 6 | 6 | 0 | 2 |
| P30 | 6 | 6 | 0 | 3 |
| P31 | 6 | 6 | 0 | 2 |
| P32 | 8 | 8 | 0 | 5 |

## 7. 局限与边界

1. **委托模式**：本机未配置 LLM 端点，因此走 OCR 官方委托模式 —— OCR 出文件清单与规则，评审由宿主 Agent 的子会话完成；OCR 自带的 LLM 评审链路（`ocr review` / `ocr scan`）未启用。
2. **测试与 Markdown 文档不在覆盖内**：`tests/**` 223 个文件、340 个 .md 被 OCR 默认规则排除（原因见 §1）。这是工具默认，不是本次裁剪；要补审需自定义 `rule.json` 或另跑一轮。
3. **复核是抽样**：14 条 high 全部复核、medium 抽样 11 条、low 未复核；0 条被推翻，但未复核条目仍可能有误报。
4. **只审查、未改代码**：本次没有修改仓库任何文件（新增的只有本报告与 .tmp/ 下的中间产物）。

## 8. 复现

```text
npm install --prefix .tmp/ocr-cli --ignore-scripts @alibaba-group/open-code-review   # 全局前缀与 npm 缓存都在沙箱外，故装在仓库内
ocr scan --preview --format json             # 文件选择 -> .tmp/ocr-fullscan/preview.json
ocr delegate rule --format json <paths...>   # 逐包规则 -> .tmp/ocr-review/rules/P##.json
node .tmp/ocr-review/aggregate.mjs           # 汇总 + 自检（覆盖/行号/枚举）
node .tmp/ocr-review/build-report.mjs        # 本报告
```
