# 2026-10-19 D 门 2 冻结包 run-ready 复核（chain-verify）

> 读数对象：`HEAD c44f9db` 的干净工作树。被复核的冻结包 = `docs/project/engineering-policy-platform/testing/ab/dgate2/{scorer,hidden,configs}` +
> `examples/dsh/b-plan/a3-task-v3/task-package` + `tools/{structure_metrics,decision_diff}.py`，即 `scorer/make_manifest.py` 清单覆盖的 25 个文件。
>
> 目的：只读重跑 A / C / T 与 activation，回答「冻结包与评分链是否可跑、可复现」。本文件不改任何冻结输入、判据或产品代码；
> 全部命令为本地 python（不启动 dsh、不联网）。证据口径：每条读数 = 命令 + 退出码 + 载荷关键值；跑不成的当场写「跑不成 + 原因」，
> 不折成通过、也不编读数。参考树不是仓库文件（04:306 5.79②），下文对它的摘要都只对它的一份字节副本重算，数值由命令当场重算。

## 0 起点锁

| 项 | 读数 | 命令 / 退出码 |
| --- | --- | --- |
| HEAD | `c44f9db`（docs: 同步 D 门 2 冻结后的现状） | `git log --oneline -1` → 0 |
| 工作树 | 干净（`git status --porcelain` 输出为空） | `git status --porcelain` → 0 |
| 冻结组合摘要 | `sha256:e3ef9e91e8cdd6d8347f8e72eb429faca7156a924c85ca75f1d416302edd649a` | `make_manifest.py --check --strict` → 0（§1.1） |
| 任务包冻结 | `task-package/manifest.sha256` 5/5 ok，自身 `sha256:44d85e7e3bfc58ccfc6deb4bf39e19d056b7e89792c4113e00fd324c86c19217` | 逐行重算 → 0（§1.2） |
| 首消息 | `sha256:123c938c28a176ede6e2d888bea83b21e4a32684e5c4824283eeb376ee92625c`（5121 B / 46 行） | `Get-FileHash` → 0（§1.2） |
| 参考树副本 | 16 文件，`files_digest = sha256:7ea8d5e5…a6f361`（全文见 §1.4） | 对 `.tmp/dgate2-w2/ref` 重算（由 `.tmp/lead-v3/ref` 复制并排除 `__pycache__` / `.pytest_cache` / `*.pyc`） |
| 配置副本 | before / after 各 9 文件，9/9 与冻结 `sha256.txt` 一致 | 逐文件重算 → 0（§1.3） |

**配置副本说明**（对命令原文的一处环境偏离，先说清）：冻结路径是 `docs/.../dgate2/configs/{before,after}`；验证器流水线会往
`--config-root` 下写 `.tmp/validators/`（`configs/README.md:25`），会把目录造进冻结目录、超出本会话写区。因此 §1.4 / §1.5 的
`--config-root` 用它们的**字节副本** `.tmp/dgate2-w2/configs/{before,after}`；副本 9/9 与冻结 `sha256.txt` 一致（§1.3），配置输入与冻结等价。

## 1 六组读数

### 1.1 冻结复核（组合摘要）

```powershell
$S = 'docs/project/engineering-policy-platform/testing/ab/dgate2/scorer'
.venv/Scripts/python.exe "$S/make_manifest.py" --check --strict   # → 0
.venv/Scripts/python.exe "$S/make_manifest.py" --print            # → 0（stdout=清单文本，stderr=combined_digest）
```

| 读数项 | 命令与退出码 | 值 | 三态 |
| --- | --- | --- | --- |
| 清单复核 | `make_manifest.py --check --strict` → 0 | `RESULT: PASS（25 个文件逐字节一致，0 条 pending）` | 符合 |
| 25 文件构成 | 同上 + 解析 `manifest.sha256` | 任务包 6 / `configs/after` 10 / scorer 5 / hidden 2 / tools 2 = 25；路径升序；清单里没有 `scorer/manifest.sha256` 自身 | 符合 |
| 组合摘要 | `sha256(manifest.sha256 文件字节)` | `sha256:e3ef9e91e8cdd6d8347f8e72eb429faca7156a924c85ca75f1d416302edd649a`；与冻结记录 `e3ef9e91…` 前缀一致（06:205 R-A-D2-04、04:305、05:176） | 符合 |
| `--print` 自洽 | `make_manifest.py --print` → 0 | stdout 原始字节 `sha256:949869d4…`（Windows 文本模式把 LF 翻成 CRLF）；按 LF 归一化后 `sha256:e3ef9e91…` = `manifest.sha256` 文件字节 sha = stderr 的 `combined_digest`；只读不写 | 符合（附换行翻译说明） |

复核时（本文件写作前）再跑一次 `--check --strict` → 0、`RESULT: PASS（25 个文件逐字节一致，0 条 pending）`。冻结 `configs/after/` 下已存在一个 19:11 创建的空 `.tmp/validators/`（早于本次读数；清单跳过 `.tmp`，`configs/README.md:25` 已预告该副作用；本次未再写冻结目录）——这也是 §1.4 / §1.5 改用配置字节副本的原因。

### 1.2 任务包 v3

```powershell
$pkg = 'examples/dsh/b-plan/a3-task-v3/task-package'
# 逐行复核（与 examples/dsh/b-plan/a3-task-v3/README.md:106-112 同一段脚本）
Get-Content "$pkg/manifest.sha256" | ForEach-Object {
  $h, $name = $_ -split '  ', 2
  $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $pkg $name)).Hash.ToLower()
  '{0}  {1}' -f ($(if ($actual -eq $h) { 'ok' } else { 'BAD' })), $name
}
(Get-FileHash -Algorithm SHA256 "$pkg/first-message.txt").Hash.ToLower()
.venv/Scripts/python.exe examples/dsh/b-plan/a3-task-v3/reset-arm.py --dry-run   # → 0
```

| 读数项 | 命令与退出码 | 值 | 三态 |
| --- | --- | --- | --- |
| 5/5 逐行 | 上面的 PowerShell 循环 → 0 | `ok` × 5（acceptance.md / allowed-writes.txt / first-message.txt / interfaces.md / milestones.md），`pkg_fail=0` | 符合 |
| manifest 自身 | `Get-FileHash` → 0 | `sha256:44d85e7e3bfc58ccfc6deb4bf39e19d056b7e89792c4113e00fd324c86c19217`（README:101 同值） | 符合 |
| 首消息 | `Get-FileHash` → 0 | `sha256:123c938c28a176ede6e2d888bea83b21e4a32684e5c4824283eeb376ee92625c`；5121 B / 46 行 / 单尾 LF（README:96 同值） | 符合 |
| README §4 表格 | 上两条 + 逐项重算 | 7/7 相等：first-message `123c938c`、interfaces `ee94acc6`、acceptance `6cbcc6fa`、allowed-writes `c03bd30a`、milestones `115e9979`、manifest `44d85e7e`、reset-arm.py `62b4fa8a`（表中为前缀，完整值逐项相等） | 符合 |
| dry-run 不写盘 | `reset-arm.py --dry-run` → 0 | 目标 `.tmp/a3b3/task-project` 已存在 12 文件，逐文件打印 `same` ×12；脚本自算基线清单 sha = `4e7c4073…`；跑前跑后树摘要同为 `sha256:4e7c4073…`（= v3 README:35 的基线组合摘要） | 符合 |

### 1.3 两臂配置

```powershell
$cfg = 'docs/project/engineering-policy-platform/testing/ab/dgate2/configs'
Get-Content "$cfg/before/sha256.txt" | ForEach-Object { ... }   # 逐行 Get-FileHash 比对 → 0
Get-Content "$cfg/after/sha256.txt"  | ForEach-Object { ... }   # 同上 → 0
git diff --no-index "$cfg/before/validation/test-layout.yaml" "$cfg/after/validation/test-layout.yaml"   # → 1
```

| 读数项 | 命令与退出码 | 值 | 三态 |
| --- | --- | --- | --- |
| before | 逐行比对 → 0 | 9 行、9/9 ok；`sha256.txt` 自身 `sha256:780dd26c…`；`test-layout.yaml` `sha256:69e9d4bb…` | 符合 |
| after | 逐行比对 → 0 | 9 行、9/9 ok；`sha256.txt` 自身 `sha256:3fea3de0…`；`test-layout.yaml` `sha256:af70bee1…` | 符合 |
| 两目录差异 | `git diff --no-index` → 1（有差异） | 只有 `validation/test-layout.yaml`；新增 6 行 / 删除 0 行（1 行取值 + 5 行注释） | 符合 |
| treatment 原文 | 读两个 `test-layout.yaml` | 见下：差异仅为 `tools/**/*.py` 一行 | 符合 |
| 行序表述 | 读 `configs/README.md:69` | 两份 `sha256.txt` 的行序是固定的配置优先级序、不是字母序；文档写「按 relpath 排序」与实测不符（不影响 9/9 逐文件核对；after 的 `sha256.txt` 自身字节在冻结清单里，before 由自己的 `sha256.txt` 冻结、按设计不在清单） | 文档小偏差（不占红） |

```yaml
# configs/before/validation/test-layout.yaml:18-19
production_patterns:
  - "src/**/*.py"

# configs/after/validation/test-layout.yaml:23-25
production_patterns:
  - "src/**/*.py"
  - "tools/**/*.py"
```

treatment = 在 `production_patterns` 增 `tools/**/*.py` 一项；其余 8 个文件两臂逐字节相同。

### 1.4 参考树、A / C / T

**参考树**（`.tmp/dgate2-w2/ref`，16 文件，不含缓存）：

```
AGENTS.md  README.md  conftest.py  pytest.ini
src/shop/{__init__,order_audit,order_controller,order_repository,order_service}.py
tests/{test_audit_demo,test_order_audit,test_order_controller,test_order_repository,test_order_service}.py
tools/{__init__,audit_demo}.py
```

| 读数项 | 命令与退出码 | 值 | 三态 |
| --- | --- | --- | --- |
| files_digest | 逐文件 `sha256` 后按 relpath POSIX 字符串升序拼 `<sha256>  <relpath>\n` 再取 sha256 | `sha256:7ea8d5e53c893e3e0310ec94b03b52e44d11e25abbd28edb624817c554a6f361`（16 文件） | 符合 |
| layers.yaml | `Get-FileHash` → 0 | `sha256:8baa7039354c66597bc803e9d24cc9f12d6eea2844c24f02a546964bd4e5c10c`；16 个键，与 16 文件集的对称差 = 空 | 符合 |
| interfaces.yaml | `Get-FileHash` → 0 | `sha256:dda6fb855d545e3e31b6795688abe22efb4a4ad8dfb26e8db3d033e536898ab9`；7 条 | 符合 |
| 只读 | 全部 A/C/M5/T 跑完后再清点 | 仍 16 文件、0 个 `__pycache__` / `.pytest_cache` / `.pyc` | 符合 |

**A 维度**（10 条谓词）：

```powershell
$REF = '.tmp/dgate2-w2/ref'
.venv/Scripts/python.exe tools/structure_metrics.py --workspace $REF `
  --layers "$S/layers.yaml" --interfaces "$S/interfaces.yaml" --json
```

| 读数项 | 命令与退出码 | 值 | 三态 |
| --- | --- | --- | --- |
| 两次运行 | 同一命令 ×2 → 0 / 0 | 两次 stdout 逐字节相同，`sha256:a536e50d24f250325dc46b077bda5b39e151975d836baee1f9d4350c06024705` | 符合 |
| summary | 同上 | `{"failed": 0, "passed": 10}`；A1–A10 全 `pass` | 符合 |
| workspace_scope | 同上 | `files 13`、`files_digest sha256:c9135251…`、`edges_internal 11`、`unresolved 0`、`root "."`；`layers.digest` = `8baa7039…`、`interfaces.digest` = `dda6fb85…`（与 §1.4 文件哈希逐个相等） | 符合 |
| A3 / A4 明细 | 同上 | A3 `declared_caps`：7 模块 / 15 个公开定义 / 0 违规；A4：`composition_files 1`、`default_wiring_instantiations 2`、0 违规 | 符合 |

注：`workspace_scope.files_digest` 是 13 个 `.py` 的口径，与本节 16 文件 `files_digest` 不是同一算法，不能互比；能互比的是 `layers.digest` / `interfaces.digest`（逐字节相等）。

**C 维度**（8 个改动 `.py`，每文件一次；模板照 `scorer/README.md:53-66`）：

```powershell
$env:PYTHONPATH = 'src'
$changed = @('README.md','src/shop/order_audit.py','src/shop/order_controller.py','src/shop/order_service.py',
             'tests/test_audit_demo.py','tests/test_order_audit.py','tests/test_order_controller.py',
             'tests/test_order_service.py','tools/audit_demo.py')
# 对下面 8 个文件逐个跑（--layer 取 layers.yaml 里该文件的值）
.venv/Scripts/python.exe -m policy.check <file> --workspace $REF `
  --config-root .tmp/dgate2-w2/configs/after --layer <value> --operation edit `
  --changed <9 条，每条一次> --request-id dgate2-verify-<slug> --json
```

| 文件 | layer | decision / exit | violations | served_checkers | skipped_rules | complete | layer_source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| src/shop/order_audit.py | model | allow / 0 | 0 | failing_tests, missing_docstring, missing_tests, style_lint | ARCH-001@1（layer model != controller） | true | declared |
| src/shop/order_controller.py | controller | allow / 0 | 0 | 上列 + forbidden_dependency | 无（effective 43） | true | declared |
| src/shop/order_service.py | service | allow / 0 | 0 | failing_tests, missing_docstring, missing_tests, style_lint | ARCH-001@1（layer service != controller） | true | declared |
| tests/test_audit_demo.py | test | allow / 0 | 0 | 同上 | ARCH-001@1（layer test != controller） | true | declared |
| tests/test_order_audit.py | test | allow / 0 | 0 | 同上 | 同上 | true | declared |
| tests/test_order_controller.py | test | allow / 0 | 0 | 同上 | 同上 | true | declared |
| tests/test_order_service.py | test | allow / 0 | 0 | 同上 | 同上 | true | declared |
| tools/audit_demo.py | composition | allow / 0 | 0 | 同上 | ARCH-001@1（layer composition != controller） | true | declared |

| 合计项 | 命令与退出码 | 值 | 三态 |
| --- | --- | --- | --- |
| 规则命中 | 8 次运行汇总 | 8 条规则（ARCH-001 / TESTING-001 / TESTING-002 / STYLE-002 / STYLE-018 / DOC-001 / STYLE-001 / STYLE-010）在 8 个文件上 0 violation => 各 3 分 = **24/24** | 符合 |
| 公共字段 | 8 次运行 | `rule_set_hash = sha256:73845ef515236940266b682631c02dec84c06886fa27a1e99f57e66284fae7d4`（8 次全同） | 符合 |
| 两次逐字节相同 | 对 `src/shop/order_audit.py` 再跑一次 | 同一 `--request-id` 下 stdout `sha256:c089974c…`，与首次相同 | 符合 |

**T 维度**（隐藏验收 30 + 入口 5 + 接口 5）：

```powershell
$env:POLICY_TREE = '.tmp/dgate2-w2/ref'
$env:DGATE2_TMPDIR = '.tmp/dgate2-w2/tdir'
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/dgate2/hidden/runner.py --json
```

对照探针（一次性；0700 目录创建后本进程也删不掉，重跑要换目录名）：

```powershell
.venv/Scripts/python.exe -c "import os,shutil; p=os.path.join('.tmp/dgate2-w2','probe700'); shutil.rmtree(p, ignore_errors=True); os.mkdir(p, 0o700); os.mkdir(os.path.join(p,'child'))"   # → 1（WinError 5）
.venv/Scripts/python.exe -c "import os,shutil; p=os.path.join('.tmp/dgate2-w2','probe777'); shutil.rmtree(p, ignore_errors=True); os.mkdir(p, 0o777); os.mkdir(os.path.join(p,'child'))"   # → 0
```

| 读数项 | 命令与退出码 | 值 | 三态 |
| --- | --- | --- | --- |
| 原环境（第一次） | 上面的命令 → **1** | `summary {passed: 30, total: 40}`；失败 `T22/T23/T25/T26/T27/EN1..EN5`，全部是 `PermissionError: [WinError 5]`，路径在 `DGATE2_TMPDIR` 下的 `<copy>/tree` | **跑不成（宿主）** |
| 原环境（第二次） | 同上 → 1 | 与第一次 stdout **不同**（`sha256:ac05e4f3…` vs `f8f6e123…`）：失败 detail 带出了临时副本的绝对路径 | 跑不成（宿主） |
| 原因（对照探针） | 上面的两条探针 → **1** / **0** | `tempfile.mkdtemp` 以 0700 建目录（`runner.py:99-110`、`test_acceptance_dgate2.py:158-169`），本机文件沙箱让 0700 目录不可再写；副本建不出来，所以 10 条需要子进程的用例失败 | 跑不成（宿主） |
| 环境缓解后 | 同命令 + `$env:PYTHONPATH='.tmp/dgate2-w2/shim'` → 0 / 0 | `summary {passed: 40, total: 40}`、`schema_version "1.0"`、`tree ".tmp/dgate2-w2/ref"`；两次 stdout 逐字节相同 `sha256:f0b9b46e…`；跑前跑后 `files_digest` 同为 `sha256:7ea8d5e5…`（16 文件、缓存 0） | 符合（仅限缓解环境） |
| 缓解的性质 | 读垫片源码 | `.tmp/dgate2-w2/shim/sitecustomize.py` 只把 `tempfile.mkdtemp` 的创建模式从 0700 改成 0777；冻结的 runner / 隐藏用例一个字节未改，子进程还剔除了 `PYTHONPATH` | 边界 |
| 现运行时（danger-full-access）无 shim 复跑 | `$env:POLICY_TREE='.tmp/dgate2-w2/ref'`；`$env:DGATE2_TMPDIR='.tmp/lead-check'`；`runner.py --json` → **0** | `summary {passed: 40, total: 40}`、`fails []`、`schema_version "1.0"`；复跑者 = Lead，时间 2026-10-19T21:33:38+08:00（按其 `DGATE2_TMPDIR` 目录最后写入时间） | **符合（现运行时）** |

说明：上两行「原环境」是旧 workspace-write（partial）沙箱形态的历史读数，保留不删；本子会话的权限在启动时固定为 workspace-write，对同一命令仍得 30/40（旧形态），新增行是 Lead 在其 danger-full-access 运行时下的复跑记录，不是本子会话的实测。

新增行的命令原文（Lead 复跑）：

```powershell
# 时间 2026-10-19T21:33:38+08:00；复跑者 Lead
$env:POLICY_TREE = '.tmp/dgate2-w2/ref'
$env:DGATE2_TMPDIR = '.tmp/lead-check'
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/dgate2/hidden/runner.py --json   # → 0
```

已知读数里的 `6531789280…`（hidden/README.md:226）是 `.tmp/lead-v3/ref` 的载荷摘要；本次 `tree` 标签不同（`.tmp/dgate2-w2/ref`），摘要本就不同，但**同一命令两次逐字节相同**这一条成立。

### 1.5 activation（M5b / M5a）

```powershell
$env:PYTHONPATH = 'src'
# M5b：树 = 参考树（12 文件基线 + M1–M4 产物 + tools/audit_demo.py + tests/test_audit_demo.py）
.venv/Scripts/python.exe -m policy.check tools/audit_demo.py --workspace .tmp/dgate2-w2/ref `
  --config-root .tmp/dgate2-w2/configs/before --layer composition --operation edit `
  --changed tools/audit_demo.py --request-id dgate2-m5b-before-edit --json
# 把 --config-root 换成 .../configs/after、--request-id 换成 dgate2-m5b-after-edit 再跑一次
# M5a：树 = 参考树 - tools/audit_demo.py（15 文件），文件换成 tests/test_audit_demo.py，--layer test
```

| 读数项 | 命令与退出码 | 值 | 三态 |
| --- | --- | --- | --- |
| M5b before | `policy.check tools/audit_demo.py ... --config-root <configs/before> --changed tools/audit_demo.py` → 1 | block / TESTING-002 critical / `evidence.detail=uncovered_checker` / served 不含 failing_tests | 符合 |
| M5b after | 同参数只换 `<configs/after>` → 0 | allow / 0 violation / served 含 failing_tests | 符合 |
| M5b（9 条 changed） | 同上但 `--changed` 带 9 条 → 0 / 0 | 两臂都 allow（测不出 treatment） | 不符合（与派发期望，见下） |
| M5a（两臂） | 树 = 参考树 - `tools/audit_demo.py`；`policy.check tests/test_audit_demo.py ... --layer test --changed tests/test_audit_demo.py` → 1 / 1 | allow_with_warnings / pending 指向 `tools.audit_demo`；两臂相同 | 符合 |

明细（同一批运行，逐字段）：

| 形态 | 臂 | exit | decision | violations | served_checkers | selection / pending |
| --- | --- | --- | --- | --- | --- | --- |
| M5b（单路径，edit） | before | **1** | **block** | `TESTING-002` v1 / **critical**；`evidence.detail = uncovered_checker`、`subject = TESTING-002@1`、`value = failing_tests` | missing_docstring, missing_tests, style_lint（**不含** failing_tests） | `selection.reason = 变更集里没有生产文件，测试选择不适用` |
| M5b（单路径，edit） | after | **0** | **allow** | 空 | failing_tests, missing_docstring, missing_tests, style_lint | `level = related`、`nodeids = [tests/test_audit_demo.py]` |
| M5b（单路径，create） | before / after | 1 / 0 | block / allow | 同上 | 同上 | 同上（`--operation` 不改变翻面） |
| M5b（9 条 changed） | before | 0 | allow | 空 | 含 failing_tests | 与「A 臂应 block」的派发期望**不符**（见下） |
| M5b（9 条 changed） | after | 0 | allow | 空 | 含 failing_tests | 同上 |
| M5a（单路径，create） | before | 1 | **allow_with_warnings** | 空 | missing_docstring, missing_tests, style_lint | pending_findings = `TESTING-002/warning/failing_tests`，subject `tests/test_audit_demo.py`，value `tools.audit_demo` |
| M5a（单路径，create） | after | 1 | **allow_with_warnings** | 空 | 同上 | 同上（两臂 decision / violations / pending / served 全同） |

**M5b 的 9 条 changed 与派发文本不符（最重要的一条差异，如实写）**：按 §1.4 的 C 模板把 9 条路径全带上时，变更集里有
`src/shop/order_audit.py` 等生产文件，测试选择因此适用、`failing_tests` 在 before 臂也被服务，于是两臂都 `allow`，
**看不见 treatment**。activation 的判据是「那一次写动作的变更集」；v3 任务包 README:76-86 与 treatment §2.3.5 给的都是
`--changed tools/audit_demo.py` 单路径形态——只有这个形态复现 block/allow 翻面。建议正式 run 按单路径形态记录该读数；
若坚持 9 条形态，那一读数测不出 treatment，必须换判据重新冻结。

### 1.6 判据与文档哈希（run-manifest 的 criterion_sources）

```powershell
(Get-FileHash -Algorithm SHA256 docs/project/engineering-policy-platform/04-open-work.md).Hash.ToLower()
(Get-FileHash -Algorithm SHA256 docs/project/engineering-policy-platform/05-implementation-plan.md).Hash.ToLower()
(Get-FileHash -Algorithm SHA256 docs/project/engineering-policy-platform/readings/2026-10-19-D-gate2-treatment.md).Hash.ToLower()
```

| 文件 | run 时 sha256 | 冻结记录 | 结论 |
| --- | --- | --- | --- |
| `readings/2026-10-19-D-gate2-treatment.md` | `37861959ce345a1177aac5cab053a0b159e92f46b298ef0e2bc2bc096fba68b6`（50358 B） | `scorer.yaml:36` 的 `criterion_sources` 同值 | 符合：判据原文钉死，改它 = 换判据 |
| `04-open-work.md` | `d3ccc2ef7776a13e1874b2a104cd6fedfb4f748145ed6b9cee1428ad76a58d58`（131367 B） | `scorer.yaml:39` 的 `sha256_at_freeze = 3542d0f4…` | 活文档：run 时计算并记进 run-manifest；与 freeze 值不同属设计内 |
| `05-implementation-plan.md` | `581a7a0864fb14acc83c16766f949300a04bb626ce5b085b734a42dffd19fb49`（24930 B） | `scorer.yaml:42` 的 `sha256_at_freeze = cd12251f…` | 同上 |

结论：memo 的冻结值与 `scorer.yaml` 的 `criterion_sources` **逐字节一致**；04 / 05 是活文档，run-manifest 必须记 run 时值。

## 2 交叉校验（与 scorer/README §10/§11 的已知读数）

| 已知项（来源） | 已知值 | 本次值 | 一致 |
| --- | --- | --- | --- |
| A（scorer/README.md:227） | reference 树 10/10；files 13、edges_internal 11、unresolved 0 | 10/10；files 13、edges 11、unresolved 0 | 是 |
| A3 明细（scorer/README.md:227） | declared_caps：7 模块 / 15 个公开定义 / 0 违规 | 同 | 是 |
| C（scorer/README.md:228） | 8/8 exit 0、allow、0 violation、layer_source declared、check_volume complete；rules 24/24 | 同 | 是 |
| T（scorer/README.md:230；hidden/README.md:225） | 参考树 40/40、exit 0 | 原环境 30/40（宿主权限）；缓解后 40/40、exit 0 | 逻辑一致；原环境跑不成（§1.4） |
| T 确定性（hidden/README.md:226） | 两次相同，sha256 65317892… | 同命令两次逐字节相同；摘要因 `tree` 标签不同而不同 | 是（同口径下） |
| 组合摘要（06:205 R-A-D2-04） | `e3ef9e91…` | `e3ef9e91e8cdd6…` | 是 |
| 任务包 manifest（c-arm/README.md:21） | `44d85e7e…` | 同值 | 是 |
| 首消息（v3 README:96） | `123c938c…` | 同值 | 是 |
| 两臂配置（scorer/README.md:214） | `69e9d4bb…` → `af70bee1…` | 同值 | 是 |
| M5b（v3 README:63） | before block、after allow | 单路径形态同；9 条形态两臂 allow | 单路径是；9 条否（§1.5） |
| M5a（v3 README:62） | allow_with_warnings + pending | 同（两臂同） | 是 |

## 3 结论与边界

**总体**：冻结复核、任务包、两臂配置、A、C、activation（M5b 单路径 + M5a）在冻结包上都可复现，读数与冻结记录一致；
T 在**现运行时（danger-full-access）无 shim 40/40、exit 0**；旧 workspace-write（partial）形态下是 30/40（宿主 0700 目录权限），
两种形态分别记录在 §1.4，历史读数不删。

| 维度 | 三态 | 依据 |
| --- | --- | --- |
| 冻结复核 / 25 文件 / 组合摘要 | 符合 | §1.1（`e3ef9e91…`，exit 0） |
| 任务包 v3 | 符合 | §1.2（5/5、`123c938c…`、dry-run exit 0 且不写盘） |
| 两臂配置 | 符合 | §1.3（各 9/9；只差 `test-layout.yaml`） |
| A 维度 | 符合 | §1.4（10/10、两次逐字节相同） |
| C 维度 | 符合 | §1.4（8/8 allow、24/24、两次逐字节相同） |
| T 维度 | **现运行时符合**（旧 workspace-write 形态下跑不成，已按三态分别记录） | §1.4：danger-full-access 无 shim 40/40、exit 0（复跑者 Lead）；旧形态 30/40、exit 1；对照探针与缓解读数保留 |
| activation | 符合（单路径）/ 不符合（9 条派发形态） | §1.5：M5b 单路径 before block / after allow；9 条两臂 allow |
| 判据来源 | 符合 | §1.6：memo 与 `scorer.yaml:36` 完全一致 |

**边界（引用本读数时不能越过）**：

1. **参考树未冻结**（04:306 5.79②）：16 文件摘要只描述 `.tmp` 里的这份副本；正式 A/B/C 的树是模型产物，不是这棵。
2. **hidden/README.md:186（§6）列了 13 条边界与规格含糊**（派发文本写 11 条，以文件为准）：A8 的 v2 残留、§4.1 冻结清单与 v3 冲突、
   A6 无基线 skip 清单、runner 不读 `layers.yaml` / `interfaces.yaml`、`runner.py` 退出码 2 分支只部分实测等，都仍成立。
3. **`--json` 包装不带 `run`**；`result.request_id` 就是命令行给的固定值，不给 `--request-id` 时是 `cli-<uuid4>`，两次运行因此不同
   （`src/policy/check.py:31-39`）。「两次逐字节相同」的前提是固定 request-id；本次每个文件用固定 `dgate2-verify-<slug>`。
4. **T 的宿主限制**：0700 临时目录在旧 workspace-write 沙箱内不可写（`mode700 → WinError 5`）；现运行时（danger-full-access）已 40/40。
   冻结代码不改，处置在环境侧：正式 run 若在同一旧沙箱内启动，会复现 30/40；应在不受该 ACL 限制的环境跑 T。
   按 **A-4**，正式 A/B/C 臂用一次性 `danger-full-access` 启动，T 的宿主限制因此**不构成阻断**；但 run-manifest 必须记
   **launcher / session 两种沙箱形态**（c-arm README 第 7 节第 5 条，`c-arm/README.md:285-287`）。
5. **失败路径的脱敏缺口**：T 原环境两次读数不同，是因为失败 detail 带出了临时副本绝对路径，与 hidden/README §1.1
   「不含绝对路径」只在全过路径成立——这也是「不跑成不能记成通过」的一个具体形态。
6. **本次未核实的**：dsh / 真 Hook 路径、真模型行为、30 条隐藏验收的独立质量、以及 `tools/ci_local.py` 门禁（由 Lead 统一跑）。
7. **本读数只证明冻结包与评分链在参考树上可复现，不等于 A/B/C 主实验开跑**。开跑前仍需：`--check --strict` 复核、
   17 个 run-manifest 字段写全、按 A-4 记两种沙箱形态、以及 M5b 读数按单路径形态记录。

注：§2 交叉校验表的 T 行记的是旧 workspace-write 形态的历史读数（未改）；现运行时读数见 §1.4 新增行与本节三态表。
