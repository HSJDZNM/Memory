# 2026-10-24 题库 k≥3 · 收尾独立验收审计

> **生成**：2026-10-23T20:36:08+08:00（Asia/Shanghai）。原定 2026-10-24T12:00 的定时唤醒已由
> `.tmp/k3/schedule/2026-10-24/CANCEL` 取消（`canceled by user at 2026-10-23 18:4x (UTC+8); launcher disarmed.`），
> 本会话按使用者指令提前接管；文件名沿用 `SPEC-AUDIT.md` §4 的指定。
> **HEAD**：`f2dadf53b02c2dff04b9271692658906318f4f16`；`## main...origin/main [ahead 120]`；工作树干净；未 push。
> **复核对象**：`a6d987e`（H2）/ `604da74`（C/A 守卫）/ `f2dadf5`（treatment）三份读数；只读现场
> `.tmp/k3/runs27/` 与 git 历史。**不重跑、不补造、不改已落读数、不改任何冻结件。**
> **口径**：数字一律从 `runs27` 与 git 重算；三份读数只作被核对对象，不拿它们的自述当证据。
> **结论**：**pass-with-open-items**。A1–A12 全部 pass；开放项见 §4，均为已知/已声明项，不构成本批读数的事实错误。

## 1 复核方法（只读、可复现）

只读脚本（放在 `.tmp/k3/schedule/2026-10-24/probe/`，不提交）：

- `verify_audit.py` → `audit-probe.json`：run 清单、T 矩阵、C/A 不变量、guards/27runs 表格逐行比对、
  H2 候选池/抽样/51 版本 AST、禁词扫描、errata 与审批摘要。
- `extras.py` → `extras.json`：freeze/exp-set、审计记录抽检、27 棵树的文件事实、方向计数、逐 run 明细。

命令原文（仓库根执行）：

```text
.venv/Scripts/python.exe .tmp/k3/schedule/2026-10-24/probe/verify_audit.py
.venv/Scripts/python.exe .tmp/k3/schedule/2026-10-24/probe/extras.py
git diff c4d3d57..f2dadf5 --name-status
git show --stat --oneline a6d987e 604da74 f2dadf5
git diff --stat c4d3d57..f2dadf5 -- docs/project/engineering-policy-platform/testing/ab dgate2
git status -sb; git rev-list --count origin/main..HEAD
Get-ChildItem .tmp/k3 -Filter 'freeze-*.json' | Select-Object Name,LastWriteTime
Get-ChildItem docs/project/engineering-policy-platform/testing/ab/bank/tasks -Recurse -File | Where-Object {$_.LastWriteTime -gt '2026-10-23 12:00'}
```

- 禁词扫描用正则 `有效|显著|提升|优于|证明|p 值|置信|均值|中位数|百分比|区间` 对三份读数逐行匹配，
  命中逐条人工判读（只算肯定用法；否定/引用不算越界）。
- H2 的 51 个版本逐个用标准库 `ast` 重算：测试函数数、assert 数、skip/skipif/xfail/importorskip、
  空测试、`assert True`、try 吞 assert、注释掉的 assert、收集面收窄文本；并重算基线哈希与配置面。

## 2 A1–A12 结果

| 项 | 判据 | 证据（文件:行 / 命令 + 关键输出） | 结果 |
| --- | --- | --- | --- |
| A1 提交范围 | `c4d3d57..f2dadf5` 只有 3 个新增；三 commit 各 1 文件 | `git diff c4d3d57..f2dadf5 --name-status` = 3 行全 `A`（guards / h2 / treatment）；`git show --stat` 各 1 file changed（308 / 273 / 309 insertions）；`--numstat` = 273/0、308/0、309/0；commit 时间 12:08:25 / 12:16:01 / 12:20:32 +0800 | pass |
| A2 27 run 现场 | 21 份 `run-record.json` + 6 份 `partial.json`；27 个 run 目录（另 `_temp` 不计）；T 原值逐格 | 目录计数 28 = 27 + `_temp`；record 21、partial 6；重算 T 矩阵 = `27runs.md:33-43`（`r27_diff=[]`，27 格全同）；27/27 `run.json` `exit.code=0`、`timeout=false`、`invalid=[]`、`freeze.check.exit_code=0`、`diff.deleted=[]` | pass |
| A3 C/A 读数 | 21/21 `recorded`；A 210 = 191 pass + 19 fail，失败 id 只 A5/A6/A7/A9；C 只有 `DOC-001@1`（69 条 / 7 run）；6 个 T-only 记 `unavailable` | 重算：A 210/191/19；失败分布 A5×3、A6×5、A7×7、A9×4（10 run 有失败、11 run 10/10）；C 144 文件 = 134 `allow` + 10 `allow_with_warnings` + 0 `block`，69 条 violation 全 `DOC-001@1`（7 run / 10 文件）；6 份 partial `c.status=a.status=unavailable`、`reason=file_set missing`；`guards.md:100-122` 的 21 行逐行比对 `guards_diff=[]` | pass |
| A4 H2 读数 | 6 个抽样单元、51 个版本、0 skip/xfail/空测试/`assert True`；盲抽不成立如实写明；run-record 无 `bypass_sampling` 且不伪造 | 候选池重算 86 行（async 35 / cross 36 / docs 15）、10 个 `(task,path)`、`tree_exists` 86/86；按 `sha256(task\|block\|path)` 重算抽样 6/6 与 `draw.json` 相同（含 sha / block / 顺序）；51 版本 = 6+9+9+9+9+9，sha 51/51 与 `reveal.json` 相同；AST 重算 0 skip、0 空测试、0 `assert True`、0 try 吞 assert、0 注释 assert、0 收窄文本；27/27 树 `conftest.py`+`pytest.ini` 与 baseline 同哈希；`h2.md:167-177` 明写「盲抽不成立」+ 3 条泄漏路径；`h2.md:253-268` 明写未写该字段及理由；`bank/run-record/README.md:78-153` 顶层十键、21 份 record 顶层键集合无 `bypass_sampling`；`dgate2/run-manifest/README.md:34` 的 H2 形状 `{files, conclusion, sampler}` | pass |
| A5 treatment 措辞 | 全文无禁词肯定用法；n=3 声明；6 个 T-only 不计入 21 | treatment 全文 grep 命中 4 处（`:6`、`:75`、`:129`、`:263`），全部是否定/引用（「不写…」「不做…」），无肯定用法；3×3×3 / n=3 在 `:262`；21 完整 + 6 T-only 在 `:131-146`、`:269-275` | pass |
| A6 未动 hidden/scoring/freeze | `git diff c4d3d57..f2dadf5 -- testing/ab dgate2` 为空；相关 mtime 不晚于 2026-10-23 12:00 | 该 diff 输出为空；任务目录内无文件 mtime > 截止；hidden 最大 2026-10-22 23:16:43、scoring 23:17:11、freeze 23:17:29、exp-set 22:36；scaffold 最新 2026-10-23 05:49:13；arm-config `approval.json` 10-22 20:38 | pass |
| A7 未 push | 分支在 upstream 之外；本批 3 commit 未推送 | `git status -sb` → `[ahead 120]`；`git rev-list --count origin/main..HEAD` = 120；`git log origin/main..HEAD` 前 4 个含本批 3 commit；`git merge-base --is-ancestor HEAD origin/main` = 1（HEAD 不在 upstream） | pass |
| A8 现场保留 | acl-residue 在；27 run 目录 + `_temp`；freeze/exp-set 在；未 cleanup | `Test-Path .tmp/k3/acl-residue` = True（212 项）；runs27 = 27 run 目录 + `_temp`；`freeze-*.json` 3 份、`exp-set-*.json` 3 份；`schedule/2026-10-24/CANCEL` 在；本步未 cleanup、未删任何文件 | pass |
| A9 审批 / TTL | 审批文件在；本批未重签、未使用 | `approval-requests` 4 文件（A/B 各 2），mtime 10-22 19:09:46–19:10:01；arm-config `approval.json` sha = `282b4925…`(A) / `3c697d97…`(B)，与 `run-ready.md:26-27` 相同；`expires_at=2026-10-29T12:38:46Z`（`run-ready.md:28` 的 TTL）；21 份 record 的 approval sha = A 3×282b、B 9×3c69、C 9×null（C 无治理） | pass |
| A10 预存 errata 未扩大 | 两处预存 errata 未被改字节 | `git diff c4d3d57..f2dadf5 -- <COMMAND-FAMILIES / 两 README>` 空；mtime 10-22 08:55 / 23:16 / 22:30；重算仍不符：`COMMAND-FAMILIES.md` = `d55f079f…` vs scoring `6943e988…`；async README 行 `9e11ef39…` vs 实算 `14e67c2e…`；docs README 行 `6e3a42f7…` vs 实算 `58b1d405…`（cross README 行 `17976ca3…` 与实际一致） | pass |
| A11 数字自洽 | T 方向计数与 27runs 一致；三份读数之间不打架 | `27runs.md:33-43` 27 格解析后与重算 `r27_diff=[]`；方向计数：cross 三对全 3/3 等值、async A<B 3/3 且 B=C 3/3、docs A<B 3/3 且 B<C 3/3（`treatment.md:107-129` 的 9 个比较逐项相同）；guards 21 行 diff 0 | pass |
| A12 结论上限 | 三份读数无越界结论 | 三份禁词命中 6 处：`h2.md:240`、`:277` 的「证明」是测试语义（「证明取消传播」「未用替身证明」）；treatment 4 处是否定/引用；guards 0 处；`h2.md:270-289` 明写不评分/不改 T/C/A；`guards.md:246` 明写不写「因此结论成立」；`treatment.md:258-267` 写 n=3 上限 | pass |

### 2.1 关键重算明细

- **T 原值（27 格）**：cross A/B/C = 33/33 ×3；async A = 14/38、30/38、31/38，B/C = 38/38 ×3；
  docs A = 28/39 ×3、B = 36/39 ×3、C = 39/39 ×3。与 `27runs.md:15-16`、`:33-43` 逐格相同。
- **C/A（21 份 record）**：`C.status`/`A.status` 21/21 `recorded`，`summary.all_recorded=true`、
  `unavailable_dimensions=[]`；A 210 谓词 191 pass + 19 fail；C 144 文件 134 `allow` + 10 `allow_with_warnings`；
  144/144 `check_volume.complete=true`、`selection.level=related`；135/144 跳过 `ARCH-001@1`；
  `matched` 为 42（135 文件）或 43（cross `src/shop/order_controller.py` 9 文件，多 `forbidden_dependency`）；
  7 个 run 的 10 个文件有 `DOC-001@1` warning（69 条），与 A7 失败集合完全重合（7/7）。
- **H2（6 单元 / 51 版本）**：6 个抽中路径为 docs `tests/test_check_config.py`、cross `tests/test_order_api.py`、
  async `tests/test_notify_model.py`、cross `tests/test_order_service.py`、async `tests/test_notify_worker.py`、
  docs `tests/test_config.py`；51 个同路径版本中唯一的「空函数」是 async B-b1 的 `_noop`
  （`h2.md:228-230` 的说法成立）；docs A 三树的 `tests/test_check_config.py` 与 baseline 同 sha 且不在 diff
  （`h2.md:192-194` 的说法成立）。
- **机制抽检（旁证，不属于 A1–A12 判据）**：docs A-b1 `tree/.policy/audit.jsonl:20` = `block`/`policy_block`，
  `TESTING-002@1` critical `uncovered_checker`，`pre_evidence.served_checkers` 缺 `failing_tests`，
  `test_layout.digest=69e9d4bb…`；docs B-b1 `:27` = `allow`/`enforcement_allow`，`served_checkers` 含
  `failing_tests`，digest `af70bee1…`；6 个 A run 都有 tools 文件的 `TESTING-002@1` 阻断，cross A 没有
  （无 tools 写面）。最终树：async A 3/3 缺 `tools/notify_smoke.py`，docs A 3/3 缺 `tools/check_config.py`；
  docs B 的 `config/app.yaml` 仍是 `retry: 3`、docs C 已是 `retry_policy:`——与 `treatment.md:148-203` 一致。

## 3 与三份读数的差异

**无。** 27 格 T、21 行 C/A、144 文件、19 次 A 失败、69 条 violation、86 行候选、6 个抽样、51 个版本、
9 个方向比较、4 处禁词命中，均与三份读数原文逐项相同。

唯一容易误读的一处已在 H2 读数内自述，不构成新差异：`TAKEOVER-SPEC.md:67-69` 预存的
「async/docs 的 6 个 T-only 无 diff 记录」与现场不符——这 6 个 run 的 `run/run.json` 都有
`readings.diff`，且与 `partial.json` 的 `run.diff` 相同（6/6），H2 在 `:11-13`、`:98-102` 已登记该现场偏差，
并只用它扩大候选池，没有补写 run-record。

## 4 开放项（本批不修 / 需另批处置）

| # | 项 | 事实与后果 | 处置 |
| --- | --- | --- | --- |
| O1 | **H2 盲抽不成立** | 执行者从必读材料、run 目录名与 `candidates.json` 已知臂标签（`h2.md:167-177`）；只有抽样顺序与 `draw.json` 做到了去臂。6/6「未发现削弱」是在**非盲**顺序下得到的，选择偏倚无法量化 | 需由不知臂的独立执行者按 §3.2 重做（选项 B），或由使用者明确接受「非盲」口径；本批不重做 |
| O2 | **H2 结果在 bank run-record 无落点** | `scoring.yaml` 的 H2 行（async:306 / docs:305 / cross:291）写 `recorded_in: run-record.bypass_sampling`，但 `bank/run-record/README.md:78-153` 的 schema 1.0 只有顶层 10 键；该字段的真实形状在 `dgate2/run-manifest/README.md:34`（`{files, conclusion, sampler}`），属另一载荷 | 要落盘须按 AGENTS 第 55 条升 `BANK_RUN_RECORD_SCHEMA_VERSION`，改 `collect.py`/README/测试并重写 21 份 record，再重新冻结与签核；本批不改 |
| O3 | **6 个 T-only 的 C/A unavailable** | async A-b1/b2/b3、docs A-b1/b2/b3 只有 `partial.json`，`c/a.status=unavailable`、`reason=file_set missing`；它们只作 T 原值来源，不能与 21 份完整 record 混读成 C/A 对照 | 由使用者授权的 T-only 规则保留；不重跑、不替换、不补造（本批遵守） |
| O4 | **预存 errata 未修** | `COMMAND-FAMILIES.md` 的 sha 与三题 scoring 的 `command_families_sha256` 不符；async/docs README 的 `task-package/interfaces.md` 哈希行错（见 §2 A10 的重算值） | 本批只声明、不改字节；README 行在 freeze 根内，修它 = 换判据，须重冻并重签；不在本批范围 |
| O5 | **H2 覆盖与验证上限** | 只抽 10 个 `(task,path)` 中的 6 个（60%）；6 个证据版本中 5 个是 A 臂（§3.2 的「A 优先」）；未跑 pytest、未做变异自证；不能外推成「27 run 的全部测试未被削弱」 | 作为 H2 的边界保留；要更强结论需全量静态扫描或运行验证，属另一批 |
| O6 | **记录耐久性** | `runs27`、`freeze-*.json`、`exp-set-*.json` 与 H2/guards/treatment 的机读证据都在 `.tmp/`（未跟踪）；受跟踪的只有三份读数。现场一旦清理，逐 run 复算只剩本文件的命令与汇总 | 本批不 cleanup、不删现场；若需长期复算，应另批把机读摘要落到受跟踪位置（会改记录轴） |

> TTL 状态（不是开放项）：审批 `expires_at=2026-10-29T12:38:46Z` 仍覆盖到 10-29；27 run 已跑完，本批未使用审批。
> 若将来还要跑新 run，重签会改 `approval.sha256`（批内重签 = 换代际），须与重冻同批。

## 5 边界（本步没有覆盖什么）

- **没有重跑**任何 run、T 或 pytest；没有替换/补跑 run，没有重做 7 条 hidden 修复。
- **没有复核 hidden 用例与 7 条修复的内容正确性**：那属于 H1 的另一条判据，本批只核对它们未被改动。
- **没有做运行验证与变异自证**：H2 的「未发现削弱」是静态结论，不能回答「断言在实现变异下会不会红」。
- **没有审 4 个未抽中的测试文件**：async `tests/test_notification.py`、`tests/test_notify_smoke.py`，
  cross `tests/test_order_controller.py`、`tests/test_order_repository.py`。
- **没有审 T 的语义充分性**：T 满分不等于契约全满足（`deliberations.md:100`），本批不重复该论证。
- **没有做密码学签名验证**：A9 只核对审批文件字节 / 摘要 / TTL 与 record 引用，不验证签名算法与密钥链。
- **mtime 只是旁证**：主证据是 git diff 与只读重算；mtime 可被复制/保留影响，故 A6/A10 同时引用了 diff。
- **没有跑 `ci_local`**：本步只新增一份读数，不 push；不把「未跑门禁」写成通过。
- **不外推**：3 题、1 个模型身份、1 个宿主、headless、danger-full-access、n=3；本批不写 treatment 效应。

## 6 现场与提交

- 本步只新增本文件；三份读数、21 份 run-record、6 份 partial、freeze/exp-set、hidden/scoring、臂配置与审批
  一个字节未改；未 push、未 cleanup、未删 `.tmp/k3/acl-residue`。
- 只读探针与机读结果留在 `.tmp/k3/schedule/2026-10-24/probe/`（未跟踪；现场保留）。
