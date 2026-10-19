# 2026-10-19 treatment 落地读数：tools/**/*.py 纳入生产文件

> **性质**：D 门 2 treatment 的落地读数 + R-d 字段级差集。裁定见
> `readings/2026-10-19-D-gate2-treatment.md` 第 8 节第 1 条；本文件只记"做了什么、读数是什么、怎么回退"。
> **起点**：HEAD `0208bee`，改动前工作树干净（`git status --porcelain -- validation tests` 空）。
> **解释器**：`.venv/Scripts/python.exe`（Python 3.13.11）；除第 4.2 条说明的"平台钉在 HEAD"之外，命令都在仓库根执行。
> **产物**：逐文件载荷与差集在 `.tmp/treatment-tools/rd/`（临时产物，cleanup 会删；结论、命令与本文件里的逐条差集为准）。
> **边界**：只改 `validation/test-layout.yaml`、新建 `docs/project/engineering-policy-platform/testing/ab/dgate2/configs/**`、
> 两条 `tests/**` 回归；未改 `src/**`、未改 `policies/**`、未改 `AGENTS.md`、未改历史读数；未 git add / commit。

---

## 1 这份读数回答什么

04 5.75 的根因是一句话：`pre_evidence` 下写 `tools/` 的 python 拿不到测试证据
（`TESTING-002` 以 `uncovered_checker/critical` 阻断），因为 `validation/test-layout.yaml` 的
`production_patterns` 只声明 `src/**/*.py`，`select_tests` 对 tools 路径返回 `level="none"`。
A3 v2 的处置是"预置 demo、只运行"绕开它；treatment 把 `tools/**/*.py` 声明成生产文件，
让测试选择有依据。

本文件给四件事的**机械读数**：

1. 同一个固定动作在 A/B 两种配置下判定不同（activation，第 8 节）；
2. 其余动作**判定语义**逐字节不变（R-d 字段级差集，第 5 节）；
3. 5 类反例**两臂都仍然 block**（第 6 节）；
4. 既有测试 0 条需要改语义、全量 suite 无回归，且新增两条能红的回归（第 7 节）。

---

## 2 改动面（含版本轴判断）

| 文件 | 动作 |
| --- | --- |
| `validation/test-layout.yaml` | `production_patterns` 增 `- "tools/**/*.py"`；文件头补 5 行注释（为什么 / 回退）。`version: 2`、`schema_id: test-layout/2` **一个字不动** |
| `docs/project/engineering-policy-platform/testing/ab/dgate2/configs/before/validation/*` | 新建：9 份受跟踪配置的 HEAD 字节快照 + `sha256.txt` |
| `.../configs/after/validation/*` | 新建：改动后工作树字节快照 + `sha256.txt` |
| `.../configs/README.md` | 新建：来源 / 用途 / 不许改 / 逐文件 sha256 / "两份只差 test-layout.yaml" 自证 |
| `tests/unit/test_validator_registry.py` | 新增 1 条**数据钉住**用例（`test_the_repository_test_layout_declares_tools_as_production`） |
| `tests/integration/test_validator_pipeline.py` | 新增 1 条**行为**用例（`test_a_tools_script_is_a_production_file_with_a_real_test_selection`） |

计数：**0 行产品代码**（`src/**` 未动）、**0 条规则 YAML**（`policies/**` 未动）、**0 个协议版本号**（见下）、
**2 条新增用例**（第 7 节给红→绿证明）。

### 2.1 版本轴判断：**不升版**

判据是 AGENTS 第 55 条：数据文件自己的轴（`validators.models.TEST_LAYOUT_SCHEMA_VERSIONS`，接受 `"1"/"2"`）
记录的是**载荷形状**——键集合与字段语义。"加键 / 改语义"才升版。

| 问 | 读数 |
| --- | --- |
| 键集合变了吗 | **没有**。`production_patterns` 本来就有，还是同一个字段 |
| 字段语义变了吗 | **没有**。它一直表示"哪些路径算生产文件"；变的是它**取值**里的一个 glob 元素 |
| 加载期校验变了吗 | **没有**。`tools/**/*.py` 是规范的仓库相对 glob，走与 `src/**/*.py` 同一条校验 |
| 消费方代码变了吗 | **没有**。`TestLayout.is_production` / `select_tests` / `policy.check.resolve_layer` 一行未动 |
| 对照先例 | B2 那次 `1 → 2` 是因为**新增可选字段** `test_support_patterns`（键集合变了）；本轮不是同型 |

因此 **`version: 2` / `schema_id: test-layout/2` 保持**。加载器实测（第 4 节命令 P0）读出
`version=2 schema_id=test-layout/2 production_patterns=('src/**/*.py', 'tools/**/*.py')`。

其余轴一律不动：`policy.check.OUTPUT_SCHEMA_VERSION`（1.2）、`EVIDENCE_SCHEMA_VERSION`、
`PIPELINE_SCHEMA_VERSION`（1.4）、`AUDIT_SCHEMA_VERSION`——第 5 节的 63 条差集里
**没有一条是"新增键"**（全部是既有字段改值 / 既有数组多一个元素）。

---

## 3 before / after 配置快照

权威说明在 `docs/project/engineering-policy-platform/testing/ab/dgate2/configs/README.md`（来源、用途、
不许改、逐文件哈希、自证）。这里只放结论。

**来源**：`before` = `git show HEAD:validation/<f>`（HEAD `0208bee`），逐文件 sha256 已比对，**9/9 与 HEAD 相同**；
`after` = 本次改动后的工作树 `validation/`。**用途**：A 臂 `pre_evidence.registry_root` 指 `before/`，
B 臂与评分器 `--config-root` 指 `after/`（`--config-root` 要的是**含 `validation/` 的那一层**）。

### 3.1 逐文件 sha256（before → after）

| 文件 | before | after |
| --- | --- | --- |
| validation/validators.yaml | 1182a9c724ef073f5ba3dd7dff564d77d2d774e70bcf3f3daca7661fb5abe4dd | 同左 |
| validation/project.yaml | 133743e10b0ad5198ee0d5ad36658d5fc376eac50380d2da59e33e5668dd9f9b | 同左 |
| validation/test-layout.yaml | 69e9d4bbef6daf403ec090c59fbfda763cea5cf5894fa746b9f97ca03a63b3d3 | **af70bee1bb8a886190cda33141d0ccf6d00acd0dde92383dddb0a30f37b9bf2a** |
| validation/ruff.toml | 2ac307f1352104331b35aa6120bd4dc6541bbc1eee1f833703afbb9640a2a33b | 同左 |
| validation/mypy.ini | d579c3c445f1f35935d4fd6bbb42d84c74771b6e0d51ca23ef49ad80d6ea507a | 同左 |
| validation/pytest.ini | 5b07bc2eeae46087dc5c3c52da519db4c20b9e9732b1f2b7139a34903d37c784 | 同左 |
| validation/control-plane-facts.yaml | e514fa834142d224912f9952eed1fd429fba30c3d97b8c101d65ee4186d3ce78 | 同左 |
| validation/channel-coverage.yaml | 21de65bfc410a257b0252148b7c1ad77a0e39219556f88a5f3fafb36633c8951 | 同左 |
| validation/instrument-checks.yaml | 12c9b8bb1799c5fe76f3324a58542d1c3efc0a6c10b0d029bd45f0e5dcb0e1eb | 同左 |

### 3.2 自证：两份只差 test-layout.yaml

| 检查 | 命令 | 读数 |
| --- | --- | --- |
| 逐文件比对 | 上表逐行比 | **8 个相同 / 1 个不同** |
| 差异形态 | `git diff --no-index before/validation/test-layout.yaml after/validation/test-layout.yaml` | 退出码 1；**新增 6 行、删除 0 行**：取值 1 行（`- "tools/**/*.py"`）+ 注释 5 行 |
| 冻结字段 | 读 after 的 `version` / `schema_id` | `2` / `test-layout/2`（未升版，见第 2.1 条） |
| 快照完整性（跑完所有读数后复算） | `Get-FileHash` 逐文件 | before `test-layout` = `69e9d4bb…`、after = `af70bee1…`，与生成时一致 |

**运行期副作用（已写进 README）**：验证器流水线的临时目录锚在 config root 下
（`src/validators/pipeline.py` 的 `config.root/.tmp/validators/<run>`），用完即删；拿这两份当
`--config-root` 跑完会留下**空的** `.tmp/validators/`。它不是配置、不进哈希；本轮已清掉。

---

## 4 固定语料与命令

### 4.1 固定工作区树（18 个文件）

构造：`git archive HEAD examples/dsh/b-plan/sample-project`（11 个文件，与工作树解耦——并行会话在改
`examples/` 与 `tools/structure_metrics.py`，不能拿工作树当固定输入）→ 解开成 `.tmp/treatment-tools/tree/` →
加 5 个文件（附录 A）+ 从 `git show HEAD:tests/fixtures/rules/<ID>/bad.py` 复制 2 个规则夹具。

机器可读清单（`sha256  <relpath>`，与仓库 manifest 同格式）：

```text
ef20cdca0d6c43dbb5038449c90a972d44837e4b9ddc17e074f994d5eed669a3  AGENTS.md
edd7cea37c657fb322cdee3038ca9aed35f40c7657a0faacb6640d6de9b050e7  conftest.py
fd1c0f9fadf99a0af117f9f17fd7276f06d577e80fd530652978a1ff54aa71cc  pytest.ini
5b4313609e4a28b61b43cd7b58ead2b99866284e532c68b79983cd3698213a5a  README.md
d7eef7b6e4db6622675782550c664ef2ef3c2ff9e8de8845cc0e9f4af4b44ad1  src/shop/__init__.py
e017c95714e14973bde434902dac0aa33025a73c5b78e4a0a23318f0b3755a6c  src/shop/order_controller.py
4d4b685f7ce3bbd729a9004b5f20ce0e77701d1be3d514788272398b4b90f054  src/shop/order_repository.py
080664ff694aad5cb1f50842ae715d72698e40031b97512ddf7328110700fcbe  src/shop/order_service.py
c9c1c9782c9848c19143c146c298941e2e9d05ec6e42fdaed09d0a29a736c9a9  tests/fixtures/rules/DOC-001/bad.py
84591d2aaa14fc6ff3f3f18879b127f7cc6779142c105b7e5d60a04dc115bd99  tests/fixtures/rules/STYLE-018/bad.py
0208a54bf84d03adb3e98f6b2e141db4ec9ee253477dffb0d2912e2e8e818c32  tests/test_audit_demo.py
4ac351e0ce611989044e74f2909c856de1e199e921602ab4fe6a874cecc7d069  tests/test_order_controller.py
61e6c0d31b70c3d93b4848e7352816ce2a8ff71a07e509dd9afd0376f977f20c  tests/test_order_repository.py
91fa0e15a1bfaf74827bd11e77dbbef0490841205cd67ab6e4b00056c57aaf5f  tests/test_order_service.py
3cdc1e4ad8c1ab63306fcddaedeeeca2c83e85fe40ab6930743b5bf3fd145585  tests/test_x.py
715acfc0194d1a7cc1c9d8a8497391e701fbe028be23ab88ee2b013a471993fb  tools/audit_demo.py
67ebd10f924e0d42bb63ad1b5c24ea664d75d58620121a64dc35bfbdbaf57044  tools/orphan.py
b96664e1dae536e294fb1ef646305e5434d12db3cc031822df25d1df0b41cd46  tools/x.py
```

（`tests/fixtures/rules/STYLE-018/bad.py` 与 `DOC-001/bad.py` 用它们是因为仓库**没有** `ARCH-001` 的夹具目录
——ARCH-001 是 `source.kind: project-policy`，按 AGENTS 第 40 条不强制正反例；裁定文里的 "ARCH-001" 是举例。）

### 4.2 平台钉在 HEAD（否则 R-d 被并行写入污染）

`policy.check --json` 的 `reading_context.tree` 是**平台树**的读数（`anchor` = `repo_root()`，不是 `--workspace`）。
直接从工作树跑时，并行会话写入未提交文件会让 `tree.digest` 在两次采集之间变——**本轮第一版采集实测到了**：
同一批 9 个 case 出现 3 个不同的 `tree.digest`（`d775fba9…` / `b747d720…` / `1232de67…`），差集里因此多出
"测量装置漂移"条目。处置：把平台代码钉在 HEAD 的副本上。

    git archive --format=tar HEAD  →  .tmp/treatment-tools/platform/
    PYTHONPATH=<repo>/.tmp/treatment-tools/platform/src，cwd=<repo>/.tmp/treatment-tools/platform

钉住后 18 份载荷的 `reading_context.tree.digest` **全部等于** `sha256:f5741389537c21bd85e326965a199ce5515a7a435c7f414a3d9372efe32cbdf6`
（collector 的断言：一次采集里 9 个 case 的 tree.digest 必须唯一，否则退出 3）。
**已知形态**：平台副本不是 git 工作树，所以载荷里 `reading_context.tree.status=unavailable`、
reason 是"读不到 git 修订号（该目录不是 git 工作树，或 git 不可用）"；两侧逐字相同，**不进差集**。
这是"读数如实说装置形态"，不是测量失败（真正的失败会是 `digest` 读不到或不稳定）。

### 4.3 命令模板（9 个 case × 2 臂 = 18 次真实 CLI 调用）

    $REPO = C:\Users\ZNM\Downloads\Memory
    $PYTHONPATH = "$REPO/.tmp/treatment-tools/platform/src"
    $PY = "$REPO/.venv/Scripts/python.exe"
    $TREE = "$REPO/.tmp/treatment-tools/tree"
    $CFG = "$REPO/docs/project/engineering-policy-platform/testing/ab/dgate2/configs/<before|after>"

    $PY -m policy.check <target> --workspace $TREE --layer <L> --operation <OP>
        --changed <target> --config-root $CFG --language <python|"">
        --request-id <case> --json

`--request-id` 固定成 case 名：`--json` 是"输入的纯函数"（不含 run 时戳），固定 id 后两侧载荷可以逐字节配对。
下面 9 条就是实际执行的命令（`<repo>` 展开后与第 4.3 条模板一致；`<before|after>` 分别对应两臂）：

    # P0（不是 case，是声明加载自检）
    $PY -c "from pathlib import Path; from validators.registry import load_test_layout;
            l=load_test_layout(root=Path('.')); print(l.version, l.schema_id, l.production_patterns)"
    # 输出：2 test-layout/2 ('src/**/*.py', 'tools/**/*.py')

    # C1 canary：tools/audit_demo.py 的 create（treatment 的激活点）
    $PY -m policy.check tools/audit_demo.py --workspace $TREE --layer module --operation create
        --changed tools/audit_demo.py --config-root $CFG --language python
        --request-id tools-audit-demo-create --json

    # C2 tools 下另一个脚本（它在 related 级有自己的测试）
    $PY -m policy.check tools/x.py --workspace $TREE --layer module --operation create
        --changed tools/x.py --config-root $CFG --language python --request-id tools-x-create --json

    # C3 tools 下**没有**对应测试的脚本（证明 TESTING-001 仍然阻断）
    $PY -m policy.check tools/orphan.py --workspace $TREE --layer module --operation create
        --changed tools/orphan.py --config-root $CFG --language python --request-id tools-orphan-create --json

    # C4 生产文件对照（src）：必须完全不变
    $PY -m policy.check src/shop/order_service.py --workspace $TREE --layer service --operation edit
        --changed src/shop/order_service.py --config-root $CFG --language python
        --request-id src-order-service-edit --json

    # C5 测试文件对照：必须完全不变
    $PY -m policy.check tests/test_order_service.py --workspace $TREE --layer test --operation edit
        --changed tests/test_order_service.py --config-root $CFG --language python
        --request-id tests-order-service-edit --json

    # C6 支撑文件对照（support 选择）：必须完全不变
    $PY -m policy.check conftest.py --workspace $TREE --layer test --operation edit
        --changed conftest.py --config-root $CFG --language python --request-id conftest-edit --json

    # C7 规则夹具对照 1：必须完全不变
    $PY -m policy.check tests/fixtures/rules/STYLE-018/bad.py --workspace $TREE --layer test
        --operation edit --changed tests/fixtures/rules/STYLE-018/bad.py --config-root $CFG
        --language python --request-id fixture-style018-edit --json

    # C8 规则夹具对照 2：必须完全不变
    $PY -m policy.check tests/fixtures/rules/DOC-001/bad.py --workspace $TREE --layer test
        --operation edit --changed tests/fixtures/rules/DOC-001/bad.py --config-root $CFG
        --language python --request-id fixture-doc001-edit --json

    # C9 文档对照（不声明语言：--language ""）：必须完全不变
    $PY -m policy.check README.md --workspace $TREE --layer docs --operation edit
        --changed README.md --config-root $CFG --language "" --request-id readme-edit --json

采集器：`.venv/Scripts/python.exe .tmp/treatment-tools/collect.py --config-root <before|after> --out .tmp/treatment-tools/rd/<before|after>`。

### 4.4 两臂读数（每例一行）

| # | case（= target） | layer / operation / language | BEFORE（exit / decision / selection / nodeids） | AFTER（exit / decision / selection / nodeids） | 期望 |
| --- | --- | --- | --- | --- | --- |
| C1 | tools/audit_demo.py | module / create / python | **1 / block / none / 0** | **0 / allow / related / 1** | 变（activation） |
| C2 | tools/x.py | module / create / python | **1 / block / none / 0** | **0 / allow / related / 1** | 变（同类：tools 有测试） |
| C3 | tools/orphan.py | module / create / python | 1 / block / none / 0（TESTING-002 critical） | 1 / block / suite / 5（**TESTING-001 error**） | 仍 block（换一条规则） |
| C4 | src/shop/order_service.py | service / edit / python | 0 / allow / related / 1 | 0 / allow / related / 1 | **不变** |
| C5 | tests/test_order_service.py | test / edit / python | 0 / allow / target / 1 | 0 / allow / target / 1 | **不变** |
| C6 | conftest.py | test / edit / python | 0 / allow / support / 5 | 0 / allow / support / 5 | **不变** |
| C7 | tests/fixtures/rules/STYLE-018/bad.py | test / edit / python | 1 / block / none / 0（STYLE-018 + TESTING-002） | 同左 | **不变** |
| C8 | tests/fixtures/rules/DOC-001/bad.py | test / edit / python | 1 / block / none / 0（DOC-001×3 + TESTING-002） | 同左 | **不变** |
| C9 | README.md | docs / edit / **""** | 0 / allow / 无证据段 | 同左 | **不变**（注） |

注（C9）：`--language ""` = 语言未声明，`language_coverage.status=language_unknown`，
`check_volume.complete=false`、`missing_dimensions=["language"]`——这个 allow 是**弱 allow**（没声明语言，验证器无法选），
两臂逐字段相同；它不是本 treatment 造成的，也不在本轮改动范围内。

---

## 5 R-d 字段级差集（63 条：装置 18 / 语义 45）

    $PY tools/decision_diff.py --base .tmp/treatment-tools/rd/before \
        --head .tmp/treatment-tools/rd/after --md
    # 退出码 1（有差异）；合计: added=23 modified=37 removed=3 total=63

### 5.1 按用例分类

| 用例 | 装置读数 | 语义差集 | 语义差集的指针 |
| --- | --- | --- | --- |
| conftest-edit | 2 | **0** | （无） |
| fixture-doc001-edit | 2 | **0** | （无） |
| fixture-style018-edit | 2 | **0** | （无） |
| readme-edit | 2 | **0** | （无） |
| src-order-service-edit | 2 | **0** | （无） |
| tests-order-service-edit | 2 | **0** | （无） |
| tools-audit-demo-create | 2 | 11 | 见 5.3 |
| tools-orphan-create | 2 | 23 | 见 5.4 |
| tools-x-create | 2 | 11 | 见 5.3（与 canary 逐条同形） |

合计校验：装置 `2×9 = 18` + 语义 `11+23+11 = 45` = **63**。

### 5.2 "其余 0" 的机械证明（不是口头承诺）

装置读数 **每例恰好 2 条**，且对所有 9 个用例逐字同形（这条 treatment 改的就是这份声明文件的字节，
所以"这次读的是哪一版 test-layout"必然变）：

| 指针 | before | after | 是什么 |
| --- | --- | --- | --- |
| `evidence.configs.test_layout` | sha256:69e9d4bb… | sha256:af70bee1… | 证据包里"本次流水线读了哪份 test-layout"的摘要 |
| `reading_context.declarations.test_layout.digest` | sha256:69e9d4bb… | sha256:af70bee1… | 同一份摘要的读数层副本（与上一条同源性由 `tests/contract/test_reading_context_digest_parity.py` 钉住） |

**语义投影**（把上面 2 个指针从两侧载荷里删掉、其余 JSON 规范化后逐字节比较）：

| 用例 | identical |
| --- | --- |
| conftest-edit / fixture-doc001-edit / fixture-style018-edit / readme-edit / src-order-service-edit / tests-order-service-edit | **true**（6/6） |
| tools-audit-demo-create / tools-orphan-create / tools-x-create | false（见 5.3 / 5.4） |

也就是说：**非 tools 用例的判定、证据、检查量、served/selection 一个字节都没变**；
63 条差集里 18 条是"声明摘要读数"、45 条全部落在 3 个 tools 用例上。

### 5.3 C1（canary）/ C2（tools/x.py）的 11 条语义差集（逐条）

两组逐条同形（C2 的 nodeids/related 是 `tests/test_x.py`），所以合并成一张表：

| 列 | 指针 | 前值 | 后值 | 解释 |
| --- | --- | --- | --- | --- |
| modified | `evidence.selection.level` | `"none"` | `"related"` | tools 脚本现在是生产文件，按 related 选到同名测试 |
| added | `evidence.selection.nodeids[0]` | （无） | `"tests/test_audit_demo.py"`（C2：`tests/test_x.py`） | 选中的 node id |
| added | `evidence.selection.related[0]` | （无） | 同上 | related 级候选 |
| modified | `evidence.selection.reason` | `"变更集里没有生产文件，测试选择不适用"` | `"按层级 related 选中 1 个测试文件"` | 选择理由 |
| added | `evidence.served_checkers[0]` | （无） | `"failing_tests"` | pytest 真的跑了（执行证据） |
| added | `check_volume.served_checkers[0]` | （无） | `"failing_tests"` | 同一事实的读数层 |
| modified | `evidence.validators[3].reason`（tool.pytest） | `"变更集里没有生产文件，测试选择不适用"` | `"选中的测试全部通过"` | 验证器记录 |
| modified | `evidence.validators[3].tool` | `null` | `{"tool": "pytest", "version": "9.1.1", "status": "ok", "exit_code": 0, "output_bytes": 100, "config": "validation/pytest.ini", "config_sha256": "sha256:5b07bc2e…", "truncated": false}` | 工具调用事实（只作不可信数据） |
| removed | `result.violations[rule_id=TESTING-002]` | `{critical, uncovered_checker, value=failing_tests}` | （无） | 阻断理由消失（不是被掩盖：证据真的进来了） |
| modified | `result.decision` | `"block"` | `"allow"` | 判定翻面 |
| modified | `exit_code` | `1` | `0` | 退出码 |

### 5.4 C3（tools/orphan.py，无对应测试）的 23 条语义差集（逐条）

| 列 | 指针 | 前值 | 后值 | 解释 |
| --- | --- | --- | --- | --- |
| modified | `evidence.selection.level` | `"none"` | `"suite"` | 生产变更，related/package 都选不到 → 升级到整个套件 |
| modified | `evidence.selection.escalated` | `false` | `true` | 升级事实 |
| modified | `evidence.selection.reason` | `"变更集里没有生产文件，测试选择不适用"` | `"按层级 suite 选中 5 个测试文件"` | 选择理由 |
| added | `evidence.selection.nodeids[0..4]` | （无） | tests/test_audit_demo.py、test_order_controller.py、test_order_repository.py、test_order_service.py、test_x.py | 套件被真的跑了 |
| added | `evidence.selection.related[0..4]` | （无） | 同上 | 同一次选择的两个视图 |
| added | `evidence.selection.missing[0]` | （无） | `"tools/orphan.py"` | **这条是关键**：没有对应测试仍然被记成 missing |
| added | `evidence.evidence[rule_id=TESTING-001]` | （无） | `{missing_tests, value=tools/orphan.py, fix="为该文件补一个测试…"}` | 选择阶段的证据 |
| modified | `evidence.validators[3].status` | `"ok"` | `"findings"` | pytest 跑成了、有失败/缺失发现 |
| modified | `evidence.validators[3].evidence_count` | `0` | `1` | 同上 |
| modified | `evidence.validators[3].reason` | `"变更集里没有生产文件，测试选择不适用"` | `null` | 工具记录（findings 时 reason 留空） |
| modified | `evidence.validators[3].tool` | `null` | pytest 调用事实（exit 0、版本 9.1.1） | 同上 |
| added | `evidence.served_checkers[0]` / `check_volume.served_checkers[0]` | （无） | `"failing_tests"` | 执行证据进来了 |
| added | `result.violations[rule_id=TESTING-001]` | （无） | `{error, value=tools/orphan.py}` | **换一条规则仍然阻断** |
| removed | `result.violations[rule_id=TESTING-002]` | `{critical, uncovered_checker}` | （无） | "无法取证"的 critical 换成"真的缺测试"的 error |
| （decision / exit_code） | — | block / 1 | **block / 1** | **判定不变** |

结论：C3 是"treatment 不是大面积放行"的反证——同一类目标缺测试时，阻断从
`TESTING-002 uncovered_checker/critical` 变成 `TESTING-001 missing_tests/error`，**仍然是 block**。

---

## 6 5 类反例的两臂回归

构造：固定树 + 每个类一份变体（只改测试/conftest），目标统一 `tools/audit_demo.py` 的 create
（`--layer module --operation create --changed tools/audit_demo.py --request-id ce-<before|after>-<类>`）。
脚本：`.venv/Scripts/python.exe .tmp/treatment-tools/counterexamples.py`（退出码 0 = 5 类两臂都 block 且
AFTER 侧真的走了 related 选择、且 `failing_tests` 在 `served_checkers` 里）。

| 反例类 | BEFORE exit / decision | BEFORE 证据 | AFTER exit / decision | AFTER 证据 |
| --- | --- | --- | --- | --- |
| 第三方包缺失 | 1 / block | `TESTING-002@1 critical `(uncovered_checker)`、pytest 未调起 | 1 / block | `TESTING-002@1 error`（value=tests/test_audit_demo.py）、pytest=findings、**收集失败**（退出码 2）、原文含 `requests_absent_package` |
| 语法错误 | 1 / block | 同左（uncovered_checker） | 1 / block | `TESTING-002@1 error`、pytest=findings、收集失败、原文含 `SyntaxError` |
| conftest 收集错误 | 1 / block | 同左 | 1 / block | `TESTING-002@1 error`（value=tests/conftest.py）、pytest=findings、收集失败、原文含 `ModuleNotFoundError` |
| 断言失败 | 1 / block | 同左 | 1 / block | `TESTING-002@1 error`（value=test_broken）、pytest=findings、有执行证据 |
| 目标解析不出来 | 1 / block | 同左 | 1 / block | `TESTING-002@1 error`、pytest=findings、收集失败（原文是 `RuntimeError`，没有"缺哪个项目内目标"⇒ 不判「待实现」） |

**关键语义**：BEFORE 侧 5 类都是"取不到证据所以 critical 阻断"；AFTER 侧都是"取到证据、证据说失败所以
按规则自己的 severity（error）阻断"。treatment 让失败从"没查成"变成"查出来失败"，**没有一类变成 allow**。

同一批语义在既有用例里也跑过（真流水线 + 真 pytest；B2 落的那 6 条，规则集收窄到
missing_tests + failing_tests，所以"本机有没有 ruff"不影响红绿）：

    $PY -m pytest -q -n0 tests/integration/test_validator_pipeline.py \
        -k 'support_scope or support_selection_really_runs or collection_failure_without_a_parseable_target or broken_conftest_support_target'
    # 6 passed, 38 deselected in 11.31s；退出码 0

---

## 7 受影响的既有测试：**0 条**；新增 2 条能红的回归

### 7.1 全仓检索：没有一条断言"tools/** 不是生产文件"

检索口径（`grep` 工具，路径 + 命中数）：

| 检索 | 范围 | 命中 |
| --- | --- | --- |
| `production_patterns` | 全仓 | 只有 `validation/test-layout.yaml` + 两份计划/裁定文档的叙述；**tests 里 0 条**断言其取值 |
| `is_production` / `select_tests` | `tests/**` | 都走 `layout.model_copy(update=...)` 或夹具项目自己的声明，**没有**对 `tools/` 路径的断言 |
| `"level=\"none\""` / `"level='none'"` | `tests/**` | 全部是"没有生产文件 / 未声明的 helper"形状，与 tools 无关 |
| `tools/` | `tests/**` | 全部是脚本路径引用（`tools/ci_local.py` 等）与假工具路径（`tests/fixtures/validators/tools/fake_tool.py`，在 `tests/fixtures/**` 下、不是生产文件） |
| `production_patterns` 的组合语料 | `tests/fixtures/rules/_combinations/**` | 条目只改 `src/shop/**` 与 `tests/**`、`conftest.py`，没有 tools 目标 |

⇒ **既有测试 0 条需要按新语义更新**（没有"tools 不是生产文件"这种断言可供翻转）。

### 7.2 全量 suite（改动已生效）

    $PY -m pytest -q -n auto
    # 3046 passed, 6 skipped, 7 warnings in 191.77s；退出码 0
    # 6 个 skip 全是环境性质的（Windows 无 POSIX 权限位 / 不能建符号链接等），与本改动无关

### 7.3 受影响的测试文件（本轮新增用例就在这两个文件里）

    $PY -m pytest -q -n0 tests/unit/test_validator_registry.py tests/integration/test_validator_pipeline.py
    # 88 passed in 50.02s；退出码 0

### 7.4 新增的 2 条回归：改前红 / 改后绿（实际命令与输出）

为什么新增而不是"修既有"：treatment 改的是**判定**，按 AGENTS 第 45 条它需要一条**能红**的仪器；
这也与 B2 的先例一致（B2 用 `test_the_support_selection_really_runs_the_tests` + 一条数据声明用例钉住声明）。

| 用例 | 钉什么 |
| --- | --- |
| `tests/unit/test_validator_registry.py::test_the_repository_test_layout_declares_tools_as_production` | 数据：`production_patterns == ("src/**/*.py", "tools/**/*.py")`；tools 下是生产文件、tests/conftest/README **不是**；`test_patterns` / `test_support_patterns` 逐字未动；`version=2` / `schema_id` 未动 |
| `tests/integration/test_validator_pipeline.py::test_a_tools_script_is_a_production_file_with_a_real_test_selection` | 行为：临时工作区里 `tools/audit_demo.py` + 同名测试 → `selection.level="related"`、`nodeids=["tests/test_audit_demo.py"]`、`missing=[]`、`failing_tests` 进 `served_checkers`、判定 `allow` |

**改后绿**（after 配置）：

    $PY -m pytest -q -n0 \
        tests/unit/test_validator_registry.py::test_the_repository_test_layout_declares_tools_as_production \
        tests/integration/test_validator_pipeline.py::test_a_tools_script_is_a_production_file_with_a_real_test_selection
    # 2 passed in 2.63s；退出码 0

**改前红**（把 `configs/before/validation/test-layout.yaml` 原样放回 `validation/test-layout.yaml` 后重新跑同样的命令）：

    # 换入：validation/test-layout.yaml sha256 = 69e9d4bb…（= HEAD）
    # 2 failed in 1.17s；退出码 1
    #   test_the_repository_test_layout_declares_tools_as_production FAILED（production_patterns 少一条）
    #   test_a_tools_script_is_a_production_file_with_a_real_test_selection FAILED
    #       AssertionError: {'level': 'none', 'nodeids': [], 'missing': [], 'related': [], ...}
    #       assert 'none' == 'related'
    # 换回：validation/test-layout.yaml sha256 = af70bee1…（= 本次改动后）

（红→绿与快照同源：before/after 两份快照就是这两次运行的输入，因此"改前红"不是手写变体，
是把 `configs/before/validation/test-layout.yaml` 逐字节放回。）

### 7.5 文本规范与空白自检

| 检查 | 命令 | 读数 |
| --- | --- | --- |
| 全仓文本规范 | `$PY tools/check_text_conventions.py` | 750 个文本文件、问题 0 处，**退出码 0**（跳过第三方镜像 300 个） |
| 本轮改动文件单独跑 | `$PY tools/check_text_conventions.py <24 个改动文件>` | 24 个文本文件、问题 0 处，**退出码 0** |
| 空白 / 行尾 | `git diff --check` | 空输出，**退出码 0** |
| 规则集自检 | `$PY -m policy.check --check-rules` | 43 条规则加载通过，退出码 0（本轮没动 `policies/**`，只作回归） |

（会话中期全仓检查曾报 1 处，是并行会话的 `tests/unit/test_structure_metrics.py`——不属于本轮改动文件；
该会话修正后复跑为 0 处。本轮改动文件的单独检查自始至终是 0 处。）

---

## 8 activation 读数（A 形态 block / B 形态 allow）

真实 `policy.check` CLI，固定树、同一动作（`tools/audit_demo.py` 的 create），只换 `--config-root`：

    $env:PYTHONPATH='src'
    $PY -m policy.check tools/audit_demo.py --workspace .tmp/treatment-tools/tree --layer module \
        --operation create --changed tools/audit_demo.py \
        --config-root docs/project/engineering-policy-platform/testing/ab/dgate2/configs/before \
        --language python --request-id activation-canary-before --json

| 形态 | 配置 | 退出码 | decision | selection | nodeids | violations | served_checkers |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **A（对照）** | `configs/before` | **1** | **block** | `none` | 0 | `TESTING-002@1 critical, detail=uncovered_checker, value=failing_tests` | 无 `failing_tests` |
| **B（treatment）** | `configs/after` | **0** | **allow** | `related` | 1（`tests/test_audit_demo.py`） | 无 | 含 `failing_tests` |

B 形态的同一命令（只把 `--config-root` 换成 `after`、`--request-id activation-canary-after`）：

    $PY -m policy.check tools/audit_demo.py --workspace .tmp/treatment-tools/tree --layer module \
        --operation create --changed tools/audit_demo.py \
        --config-root docs/project/engineering-policy-platform/testing/ab/dgate2/configs/after \
        --language python --request-id activation-canary-after --json

**交叉校验**：A 形态与 04 5.75 登记的历史读数、以及 `readings/2026-10-19-D-gate2-treatment.md` 第 2.3.5 条的
只读模拟（E15/E16）**同结论**（A：block + `TESTING-002/critical`；B：allow + served 含 `failing_tests`）——
说明本轮的基线是真实行为，不是模拟偏差。另外两条伴随事实：A 形态的 `layer_source` 是 `declared`
（本轮显式给 `--layer module`），两臂相同。

**边界**：这是 `policy.check` 路径，不是真实 Hook；`pre_evidence` 走的是同一条流水线、读同一份
`test-layout.yaml`，但"真实 Hook 上写 tools/audit_demo.py 得到 exit 0"**本轮没有复测**（见第 10 节第 1 条）。

---

## 9 回退方式

| 步 | 动作 | 校验 |
| --- | --- | --- |
| 1 | `validation/test-layout.yaml`：删掉 `- "tools/**/*.py"` 那一行与它上面 5 行注释 | 文件 sha256 回到 `69e9d4bb…`（= HEAD） |
| 2 | 删掉本轮新增的 2 条用例（第 7.4 节） | `pytest tests/unit/test_validator_registry.py tests/integration/test_validator_pipeline.py -q -n0` 回到改动前规模并全绿 |
| 3 | `configs/after/validation/` 重新快照（或整目录删除）；`configs/before/` 保留不动 | `configs/README.md` 的 after 列哈希表重算；"两份只差 test-layout.yaml" **不再成立**时该目录必须重写而不是硬改 |
| 4 | canary 期望改回"常红"（`readings/2026-10-19-D-gate2-treatment.md` 第 8 节第 2 条的退役是显式记录，回退要一起改回） | 04 5.75 状态从"已实施"改回"已裁定待实施"（Lead 的文档动作，不在本轮） |
| 5 | 回退后复跑第 8 节两条命令 | 预期 A 形态仍 block（1）、B 形态也 block（1）——两臂不再不同 = treatment 已撤 |

回退是**删一行数据**，不涉及产品代码、协议版本号或注册表重审。

---

## 10 未核实 / 不覆盖什么

1. **真实 Hook 未复测**：本轮 activation 走 `policy.check`（第 8 节）。dsh `pre_evidence` 用同一条
   `run_pipeline` + 同一份 `test-layout.yaml`，但"PreToolUse `write tools/audit_demo.py` → exit 0"这条现场
   读数没有在本轮重跑（B2 有同型 Hook 读数可参考，但那次的动作是 `edit conftest.py`）。
2. **固定语料 ≠ A3 v2 最终树**：本轮树是 18 个文件的样例项目副本（第 4.1 节），测试数 5 个；
   D 开跑后最终树上的 `selection.nodeids` / `max_nodeids=40` 截断行为可能不同，读数要重采。
3. **层推断未另测**：`production_patterns` 不参与层推断（层只来自 `test_patterns` / `test_support_patterns` / 文件名），
   所以本轮 9 个 case 全部显式给 `--layer`；"不给 `--layer` 时 tools 路径落 `unknown/filename_guess`"这条
   结论是**读代码得出的**，没有另跑（改前改后都一样，不影响差集）。
4. **TESTING-001 changed_only 的其它形态**：只观测了"单个 tools 目标、无测试"（C3）。同一批次里
   多个生产文件、部分有测试的组合没有覆盖（既有 `tests/fixtures/rules/_combinations/` 里也没有 tools 目标）。
5. **评分器尚未落地**：本轮只把 `configs/after` 备成 `--config-root` 的输入；`readings/2026-10-19-D-gate2-treatment.md`
   第 4.0 节草案写的是 `scorer/config-root/validation/`，与本轮的 `configs/` 是**两个位置**，
   需要 Lead 在冻结评分器时决定"沿用本目录"还是"复制成 scorer/config-root"（复制会多一份要钉哈希的副本）。
6. **并行会话的未提交文件不在本轮的可比范围里**：全量 suite（3046 passed）与全仓文本检查都跑在
   工作树上，而工作树里同时有 `tools/structure_metrics.py` / `tests/unit/test_structure_metrics.py` /
   `examples/dsh/b-plan/a3-task-v3/` 等**别的会话**的改动。本轮只保证"本轮改动的 3 个被跟踪文件
   + 新建的快照/读数"的读数；其余文件的红绿归各自的会话，Lead 提交时一并复核。
7. **两臂装配未接**：A/B 臂的 dsh-adapter 还没有把 `pre_evidence.registry_root` 指到 `configs/before|after`；
   本轮证明的是"同一动作、两种配置、两个 decision"，装配与 run-manifest 属 D 门 2 的后续步骤。

---

## 11 建议的 06 记录值（供 Lead 提交时采用）

| 字段 | 建议值 |
| --- | --- |
| id | P-TREAT-TOOLS-001 |
| 时间 | 2026-10-19（提交时按实际） |
| 阶段 / 任务 | D 门 2 / treatment 落地（04 5.75②） |
| 执行者 | treatment-tools（会话） |
| 起点锁 | HEAD `0208bee`；原始工作树干净；`validation/test-layout.yaml` 69e9d4bb… → af70bee1… |
| 做了什么 | `production_patterns` 增 `tools/**/*.py`（不升版）+ 两份受跟踪配置快照 + R-d 63 条差集 + 5 类反例两臂回归 + 2 条能红的回归 |
| 结果 | 符合 |
| 证据指针 | 本文件第 5–8 节；`configs/README.md`；`.tmp/treatment-tools/rd/{diff.md,diff.json}`（临时） |
| 判据 | 04 5.75；D 门 2 裁定第 8 节第 1 条；AGENTS 第 20/45/49/51 条 |
| 偏差 | 无。非 tools 用例的 2 条/例差集是"声明摘要读数"，已在第 5.2 条机械证明为语义 0 |
| 下一步 | Lead 复核并提交；05/06/04 的状态行由 Lead 同批更新；A/B 臂把 `pre_evidence.registry_root` 指向 `configs/before|after` |

---

## 附录 A 语料树新增的 5 个文件（与第 4.1 节的 sha256 一一对应）

    # tools/audit_demo.py
    """订单审计的演示入口：把一次 create 的审计记录打到 stdout。

    D 任务包 v3 要求新建的脚本（treatment 的 canary 动作）：改写它应当被当作生产变更，
    于是按 validation/test-layout.yaml 的 escalation 选到 tests/test_audit_demo.py。
    """

    import json


    def audit_entries() -> list:
        """两条固定的审计记录（演示用，没有副作用）。"""
        return [
            {"action": "create", "order_id": 1},
            {"action": "create", "order_id": 2},
        ]


    def main() -> int:
        """把记录打成 JSON 数组。"""
        print(json.dumps(audit_entries(), ensure_ascii=False))
        return 0


    if __name__ == "__main__":
        raise SystemExit(main())

    # tools/x.py
    """tools 下的另一个脚本（固定语料：它在 related 级有自己的测试）。"""


    def value() -> int:
        """返回一个常数。"""
        return 1

    # tools/orphan.py
    """一个没有对应测试的 tools 脚本（固定语料：用来证明 TESTING-001 仍然阻断）。"""


    def orphan() -> int:
        """返回一个常数。"""
        return 0

    # tests/test_audit_demo.py
    """audit_demo 的行为测试（固定语料：让 tools/audit_demo.py 在 related 级有测试）。"""

    import json
    import subprocess
    import sys
    from pathlib import Path

    DEMO = Path(__file__).resolve().parents[1] / "tools" / "audit_demo.py"


    def test_the_demo_script_prints_two_audit_entries() -> None:
        """真的跑一次脚本：stdout 是两条记录的 JSON 数组。"""
        completed = subprocess.run(
            [sys.executable, str(DEMO)], capture_output=True, text=True, check=False
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout) == [
            {"action": "create", "order_id": 1},
            {"action": "create", "order_id": 2},
        ]

    # tests/test_x.py
    """tools/x.py 的行为测试（固定语料：它在 related 级）。"""

    from pathlib import Path

    SOURCE = Path(__file__).resolve().parents[1] / "tools" / "x.py"


    def test_the_x_script_exists() -> None:
        """脚本在树里。"""
        assert SOURCE.is_file()
