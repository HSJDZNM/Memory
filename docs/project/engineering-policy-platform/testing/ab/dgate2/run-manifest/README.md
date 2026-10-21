# D 门 2 · run-manifest（18 字段契约）

`scorer/scorer.yaml` 的 `run_manifest_fields` 规定了每次 run 必须记下的 18 个字段。本目录把它
变成**可生成、可校验**的载荷：`run_manifest.py` 现场计算每个字段并写出确定性 JSON；
`--check` 重算冻结类摘要并逐项比对。它**不**生成 `scorer/manifest.sha256`，也**不**改动任何冻结输入。

| 文件 | 作用 |
| --- | --- |
| `run_manifest.py` | 生成 / 校验（`RUN_MANIFEST_SCHEMA_VERSION = "1.1"`；1.0 首次建轴，1.1 新增 `platform_generation`） |
| `README.md` | 本文件：字段表、用法、退出码、确定性与边界 |
| `tests/unit/test_dgate2_run_manifest.py` | 18 字段契约、三态、确定性、摘要漂移与退出码的回归 |

## 1 字段表

「开跑前」= 只给 `--arm/--out` 时的状态；「跑后」= 给了对应输入后的目标状态。
`--strict` 下不允许任何 `pending`；`not_applicable` 只能是人工明确裁定（H4）。

| id | 来源 | 算法 / 校验 | 开跑前 | 跑后 |
| --- | --- | --- | --- | --- |
| `head` | `git rev-parse HEAD` | 40/64 位十六进制；与冻结记录的 HEAD 比对由读数消费者做 | recorded | recorded |
| `worktree_clean` | `git status --porcelain` | 先排除 `--out` 自身条目，再判 `clean`；`entries` 排序保存 | recorded | recorded |
| `scorer_manifest_sha256` | `scorer/manifest.sha256` | 文件字节 sha256 = 组合摘要（scorer/README §4） | recorded | recorded |
| `manifest_check` | 实时跑 `scorer/make_manifest.py` | `--check --strict` 的 `{exit_code, strict, result_line}` | recorded | recorded |
| `task_package_manifest_sha256` | task-package 目录 | 清单文件字节 sha256 + 逐行核对 5 个文件，记 `files_ok/files_bad` | recorded | recorded |
| `first_message_sha256` | `first-message.txt` | 文件 sha256，且必须等于任务包清单里那一行 | recorded | recorded |
| `configs_after_sha256_txt` | `configs/after/sha256.txt` | 文件字节 sha256 + 逐行核对它声明的 9 个文件 | recorded | recorded |
| `criterion_sources` | scorer.yaml `freeze.criterion_sources` | memo 用冻结值并比对（`matches_frozen`）；04/05 记 run 时 sha256 | recorded | recorded |
| `rule_set_identity` | `policy.loader.load_rule_set` | `identity` + 8 条规则的 `{rule_id, version, expected_version, version_ok}` | recorded | recorded |
| `hidden_digests` | hidden 两个文件 | 文件 sha256 与 `scorer/manifest.sha256` 两行比对 | recorded | recorded |
| `reference_tree` | `--reference-tree DIR` | `files_digest`（排序后的「`<sha256>  <relpath>`」文本再 sha256）+ 逐文件摘要 + layers/interfaces 摘要 | pending | recorded（量了 A 维度） |
| `arms` | `--arm-facts JSON` | 抽取树摘要 / session id / `launch.patch` / launcher 沙箱；记录原始 JSON 的 sha256 | pending | recorded |
| `readings` | `--run-record JSON` | 结构校验 `schema_version / arm / dimensions{T,C,A}`；存 `{sha256, summary, dimensions}` | pending | recorded |
| `hidden_author` | `--human-items JSON` | H1：`{author, saw_impl_diff}` 原样记录（不判内容质量） | pending | recorded |
| `bypass_sampling` | `--human-items JSON` | H2：`{files, conclusion, sampler}` 原样记录 | pending | recorded |
| `a4_review` | `--human-items JSON` | H3：`{location, conclusion}` 原样记录 | pending | recorded |
| `nondeterminism_ruling` | `--human-items JSON` | H4：`{applicable:false, reason}` → not_applicable；或 `{diff_pointer, ruling, basis}` → recorded | pending | recorded / not_applicable |
| `platform_generation` | `--platform-facts JSON` | 逐键严格校验（未知键 / 类型错 / 枚举错 = 退出 2）；`budget` 由工具按三值现场重算；跨字段矛盾（serial、into_decision、degraded）记 problems → 退出 1 | pending | recorded |

每条字段的形状固定为 `{status, value, source}`；`pending` / `not_applicable` 另带 `reason`。
生成模式汇总一行：`fields=18 recorded=… pending=… not_applicable=… manifest_check=… combined_digest=sha256:…`。

## 2 三条用法

以下命令都在仓库根执行，`R=docs/project/engineering-policy-platform/testing/ab/dgate2/run-manifest`。

```powershell
# ① 开跑前：先记一份只有冻结事实的清单（reference_tree / arms / readings / H1–H4 都是 pending）
.venv/Scripts/python.exe $R/run_manifest.py --arm A --out .tmp/dgate2/run-manifest-A.json

# ①′ 开跑前补平台代际事实（1.1 起；任何 k≥3 run 之前必须给）
.venv/Scripts/python.exe $R/run_manifest.py --arm A --out .tmp/dgate2/run-manifest-A.json \
  --platform-facts .tmp/dge2/platform-facts-A.json

# ② 跑完：补参考树、臂事实、run-record 与四项人工记录（输入都写成仓库相对路径）
.venv/Scripts/python.exe $R/run_manifest.py --arm A --out .tmp/dgate2/run-manifest-A.json \
  --platform-facts .tmp/dge2/platform-facts-A.json \
  --reference-tree .tmp/dge2/ref \
  --arm-facts .tmp/dge2/arm-facts-A.json \
  --run-record .tmp/dge2/run-record-A.json \
  --human-items .tmp/dge2/human-items.json

# ③ 校验：非 --strict 允许 pending；--strict 是完整性门禁（human 项缺 → human_items_unrecorded）
.venv/Scripts/python.exe $R/run_manifest.py --check .tmp/dgate2/run-manifest-A.json
.venv/Scripts/python.exe $R/run_manifest.py --check .tmp/dgate2/run-manifest-A.json --strict
```

`--arm-facts` 的四种抽取事实写成最小形态即可；**也接受 C 臂的完整 run-manifest**（未知键一律忽略，
只抽 `tree_digest` / `session_id` / `launch.patch` / `launcher_sandbox`，另记原始 JSON 的 sha256）：

```json
{
  "arm": "A",
  "tree_digest": "<参考树组合摘要>",
  "session_id": "session-…",
  "launch": {"patch": ".policy/patch.yml"},
  "launcher_sandbox": "workspace-write"
}
```

C 臂可直接把 `.tmp/dge2/c-arm/run-manifest.json` 传给 `--arm-facts`（`patch_argument` 为 null、
`launcher.sandbox` 照常抽取）。**C 臂的 `patch` 必须为 null**：给了非 null 时生成模式会把清单写出来
但退出 1，`--check` 同样判红（「不治理臂不挂 patch」是 C 的定义，不是可选项）。
A/B 臂必须**显式**声明 `patch`（可以是 null）与 `launcher_sandbox`（取值
`workspace-write` / `danger-full-access` / `unknown`）。

`--run-record` 最少要这样；本工具只做结构校验，不替评分器算分：

```json
{"schema_version": "1.0", "arm": "A", "status": "ok",
 "dimensions": {"T": {"score": 40}, "C": {"score": 30}, "A": {"score": 30}}}
```

`--human-items` 的四个键与 scorer/README 第 6 节一致：

```json
{
  "hidden_author": {"author": "session-…", "saw_impl_diff": false},
  "bypass_sampling": {"files": ["tests/test_order_service.py"], "conclusion": "未发现空转", "sampler": "lead"},
  "a4_review": {"location": "tools/audit_demo.py 的构造处", "conclusion": "是组合根"},
  "nondeterminism_ruling": {"applicable": false, "reason": "两次读数逐字节相同"}
}
```

### 2.1 `--platform-facts` 的形状（1.1 起；任何 k≥3 run 之前必给）

```json
{
  "host": {
    "entry": "desktop",
    "dsh_runtime": "0.2.1-rc.2",
    "dsh_source": "app_bundled",
    "dsh_entry": "<install>/resources/runtime/cli/bin/dsh.cmd",
    "profile": "desktop-gui",
    "session_sandbox": "workspace-write",
    "file_policy": "danger-full-access",
    "sandbox": "unrestricted"
  },
  "start": {"head": "<40/64 位十六进制>", "worktree_clean": true},
  "run": {"serial": true, "ci_local_lock_held": false, "concurrent_sessions": 1},
  "declarations": {
    "adapter_config": {"path": "<governed>/.policy/dsh-adapter.yaml", "sha256": "<摘要>", "agent_version": "0.2.1-rc.2", "into_decision": true, "max_targets": 20},
    "registry": {"path": "<governed>/.policy/tool-registry.local.yaml", "sha256": "<摘要>", "registry_schema_version": "1.4", "approved_path": "<governed>/.policy/tool-registry.approved.json", "approved_sha256": "<摘要>", "approved_reviewed_by": "dshznm", "approved_reviewed_at": "<approved.json 里的值>"},
    "approval": {"path": "<governed>/.policy/approval.json", "sha256": "<摘要>"},
    "test_layout": {"path": "validation/test-layout.yaml", "sha256": "<摘要>"}
  },
  "batch_ledger": {"enabled": true, "into_decision": true, "max_targets": 20, "ttl_hours": 24, "schema_version": "1.1"},
  "audit_schema_version": "1.5",
  "pre_evidence": {"enabled": true, "timeout_ms": 20000},
  "timeouts": {"tool_timeout_ms": 5000, "hooks_timeout_ms": 30000},
  "model": {"id": "<会话 header 的模型标识>", "params": {"temperature": 0}, "first_message_sha256": "<任务包首消息摘要>"},
  "observations": {"batch": {"decisions": 9, "with_batch": 6, "settled": 6, "truncated": 0, "unreadable": 0, "degraded": false}}
}
```

- 键集合是闭集：**任何未知键都退出 2**（不部分接受）；枚举/类型/摘要形状同样。
- `budget` **不写在输入里**：工具按 `pre_evidence.timeout_ms + timeouts.tool_timeout_ms < timeouts.hooks_timeout_ms`
  现场算 `{applicable, ok, left_ms, right_ms, inequality}`；不成立 = 清单不合格（退出 1）。
  未开 pre_evidence 时记 `{applicable:false, reason}`。
- 跨字段矛盾记 `problems`（退出 1）：`run.serial` 与 `ci_local_lock_held/concurrent_sessions`、
  `adapter_config.into_decision` ↔ `batch_ledger.into_decision`、`degraded` 与 `unreadable/truncated`。
- 路径字段只接受**仓库相对路径**或 `<install>` / `<npm-global>` / `<governed>` / `<DSH_HOME>` /
  `<temp>` / `<workspace>` / `<outside-workspace>` token；`host.dsh_entry` 只接受 token（宿主不在仓库里）。
- `model.first_message_sha256` 必须等于 `first_message_sha256` 字段算出的摘要（跨字段核对，不符退出 1）。

## 3 退出码与输出

| 模式 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| 生成 | 已写盘，且没有摘要 / 臂约束问题（pending 不算失败） | **已写盘但清单不合格**：`manifest_check` 非 0、任务包 / configs / hidden 摘要不符、判据原文冻结值不符、C 臂带 patch 等；stderr 逐条点名 | 用法错误 / 读不到声明：`--out` 不在仓库内、`--reference-tree` 不存在、arm-facts / run-record / human-items 结构不合法、规则集加载失败 |
| 校验 | `RESULT: PASS`（非 `--strict` 允许 pending，并列出 pending 字段） | `RESULT: FAIL`：缺字段 / 多字段（点名 id）、状态非法、摘要现场重算不符、臂约束不满足；`--strict` 下仍有 pending | 清单读不到 / 不是合法 JSON / 参数组合错误 |

- 生成模式 stdout **一行摘要**；不合格项在 stderr，以 `run-manifest: 清单不合格：…` 开头。
- 校验模式 stdout 逐条 `PROBLEM: …`，最后一行 `RESULT: PASS …` 或 `RESULT: FAIL（…）`。
- `--strict` 的 FAIL 会写明：human 四项还 pending → `human_items_unrecorded`；其它 pending →
  `incomplete_freeze`（两类同时存在时都写）。
- 任何输出都不出现绝对路径：仓库内写仓库相对 POSIX 路径，仓库外写 `<outside-workspace>`。

## 4 确定性口径

- JSON 键排序、UTF-8、LF、单尾换行；没有由工具生成的时戳 / run id，没有绝对路径；
- 列表按稳定键排序（porcelain 条目、清单文件、参考树文件、8 条规则、files_ok/bad）；
- 同一输入两次生成逐字节相同（测试钉住）；`--out` 自身条目在判 `worktree_clean` 前先排除；
- `worktree_clean` 记录的是**写清单之前**的状态。若 `--out` 落在一个尚未被跟踪的目录里，git 会把
  整个目录折叠成一条 `?? <dir>/`——那条不是 `--out` 本身，会被**如实记录**（不掩盖同目录的其它
  未跟踪文件），因此这种清单的 `clean=false` 是事实而不是缺陷；正式 run 应在提交后的干净起点生成。
- `head` / `worktree_clean` 是起点快照，`--check` **不重算**（清单文件自身就会弄脏工作树）。

## 5 边界（引用本清单之前先看）

1. **人工项只记形状、不判质量**：`hidden_author` 的作者是否独立、`bypass_sampling` 的抽样是否充分、
   `a4_review` 的结论是否成立，都是人的裁定；本工具不替人填，也不把「记了」当成「判过了」。
2. **参考树是读数对象，不冻结**（04-open-work 5.79②）：它不在 `scorer/manifest.sha256` 里；
   `--check` 不重算 `reference_tree`（树可能已删），只校验记录的形状。
3. **run-record 只做结构校验**：至少含 `schema_version / arm / dimensions{T,C,A}`；arm 必须与
   `--arm` 一致、三维齐全；分数与逐 case 语义由评分器与 run 报告负责。
4. **`--check` 现场重算的字段**：`scorer_manifest_sha256` / `manifest_check` /
   `task_package_manifest_sha256` / `first_message_sha256` / `configs_after_sha256_txt` /
   `hidden_digests` / `rule_set_identity`，外加 `criterion_sources` 里**冻结的 memo**。
   04/05 是活文档（scorer.yaml 冻结时已裁定按 run 时值记录），`--check` 不拿它们与清单比对——
   run 期间是否被改写，由读 run-manifest 的 run 报告按 `spec_text_drift` 判定。
5. **臂事实只抽四类**：未知键不拒绝、不复制；原始 JSON 的 sha256 记在 `arms.source_sha256`，
   以后可据此核对「这份 manifest 取自哪份启动记录」。
6. **`platform_generation` 反过来：全量复制、未知键一律拒收**（1.1 起）。它不抽摘要就够，而是把
   宿主 / 沙箱 / 每臂配置与审批 / 批次代际 / 预算 / 模型逐键写进载荷，让「这次 run 的平台是哪一代」
   不依赖任何 `.tmp` 旁文件。`budget` 是唯一由工具**算出**的子对象（三值现场重算）。
7. **不替代 `make_manifest.py`**：冻结门禁仍是 `scorer/make_manifest.py --check --strict`；
   `manifest_check` 字段是它的实时读数。
8. **pending 不是通过**（AGENTS 第 51 条）：开跑前清单允许 pending；`--strict` 才是完整性门禁。
   `platform_generation` 在没给 `--platform-facts` 时就是 pending —— 开跑前的清单不是「平台代际已记录」。

## 6 建议登记进 AGENTS 第 55 条 dgate2 条目的一句话（由 Lead 落）

> `dgate2/run-manifest/run_manifest.py` 的 `RUN_MANIFEST_SCHEMA_VERSION = "1.1"`（18 字段 run-manifest 载荷：**1.0 = 首次建轴**（三态字段 + 摘要现场重算）；**1.1 = 新增 `platform_generation`**（2026-10-21 实验冻结裁决，宿主/沙箱/配置审批/批次代际/预算/模型/起点）；加键或改语义必须按本条递增，并同批改 README 与测试）。

## 7 与 scorer/README 的对应

| scorer/README | 本工具落点 |
| --- | --- |
| §4 冻结顺序与组合摘要 | `scorer_manifest_sha256` / `manifest_check`（每次 run 记同一份组合摘要） |
| §5 复核命令 | `manifest_check.result_line`（`make_manifest.py --check --strict` 的末行 RESULT） |
| §6 人工项 H1–H4 | `hidden_author` / `bypass_sampling` / `a4_review` / `nondeterminism_ruling` |
| §11 冻结记录 | `head` / `criterion_sources` / `rule_set_identity` / `hidden_digests` / `arms` / `readings` |
| §11.3 升版（v2 → v3） | `platform_generation` + `RUN_MANIFEST_SCHEMA_VERSION` 1.1（字段集合变了） |
