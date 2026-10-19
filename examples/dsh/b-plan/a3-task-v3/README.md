# A3 v3 任务包（A3-T1「订单审计台账」· 冻结）

> **用途**：A3 干跑第三轮的**冻结构造**，同时是 D 门 2 treatment 的**激活点**：
> treatment = `validation/test-layout.yaml` 的 `production_patterns` 增 `tools/**/*.py`；
> v3 把任务改成**要求模型自己新建 `tools/audit_demo.py` 与它的契约测试** `tests/test_audit_demo.py`，
> 于是同一个写动作在 A 臂（`production_patterns` 不含 `tools/**`）被拦、B 臂（含）放行。
> A3 v2 把 demo 预置进基线、任务只运行 —— treatment 在 v2 上**激活不了**（这正是 v3 存在的理由）。
> **任务树** = `sample-project` 的 11 文件 + `tools/__init__.py` = **12 文件**（不含任何 scaffold）；
> **允许写 9 路径**（v2 的 7 条 + 新建的 `tools/audit_demo.py` 与 `tests/test_audit_demo.py`）。
> 裁定：`docs/project/engineering-policy-platform/readings/2026-10-19-D-gate2-treatment.md`
> §2.3.5（同一动作 A 臂 block / B 臂 allow 的实测）与 §8 第 1/2 条（treatment = 04 5.75② + 任务包 v3）。
> 12 文件基线与 M5 三步是本轮**实测**定下来的（读数见 §3），不是拍脑袋的构造。

## 1 基线 12 文件

| 组 | 文件 |
| --- | --- |
| 源码（4） | `src/shop/__init__.py`、`src/shop/order_controller.py`、`src/shop/order_repository.py`、`src/shop/order_service.py` |
| 测试（3） | `tests/test_order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py` |
| 项目根（4） | `conftest.py`、`pytest.ini`、`README.md`、`AGENTS.md` |
| `tools` 包（1） | `tools/__init__.py`（内容一行：`"""项目脚本包（演示与运维脚本）。"""`；与逐字节对照的那份同哈希 `f66ec004…`） |

`reset-arm.py` 只从 `examples/dsh/b-plan/sample-project` 逐字节复制 11 个文件，再写入第 12 个
`tools/__init__.py`（内容内嵌在 `reset-arm.py` 里，所以这个包不需要任何 scaffold 目录）；
基线里出现 `scaffold/`、`tools/audit_demo.py` 或 `tests/test_audit_demo.py` 一律**直接拒绝**——
那两个文件必须由模型在 M5a/M5b 亲手写出来。

**为什么必须有 `tools/__init__.py`（实测，不是口味问题）**：M5a 先写测试，它 `from tools.audit_demo import main`。
树里没有 `tools/__init__.py` 时，收集期的 `ModuleNotFoundError: No module named 'tools'` 会被判成
**第三方包缺失** → `TESTING-002` critical **阻断**（实测 block）；有它之后缺的是**项目内**模块
`tools.audit_demo` → 走 AGENTS 第 51 条的「待实现」：`allow_with_warnings` + `pending_findings`。
这一个文件的差别就是「先写测试被拦死」与「先写测试被放行」的差别。

基线组合摘要（按相对路径排序的 `<sha256>  <relpath>` 清单文本再取 sha256，算法与 v2 的 `reset-arm.py` 相同）：
**`4e7c4073480c0c4227d4e6f39ae2a04a86b4eba11a6c62d5b8634f86ad924c42`**。

基线树 = `sample-project` 的 11 文件 + 内嵌的 `tools/__init__.py`。树 diff 的基线要**同时**给这两处
（`ab_measure --baseline-tree` 只吃一棵树）：要么先跑一次 `reset-arm.py` 再用它写出的
`.tmp/a3b3/task-project` 当基线副本，要么把 `tools/__init__.py` 补进基线副本再比。

## 2 允许写 9 路径（`task-package/allowed-writes.txt`，字母序）

1. `README.md`
2. `src/shop/order_audit.py`（新建）
3. `src/shop/order_controller.py`
4. `src/shop/order_service.py`
5. `tests/test_audit_demo.py`（新建）
6. `tests/test_order_audit.py`（新建）
7. `tests/test_order_controller.py`
8. `tests/test_order_service.py`
9. `tools/audit_demo.py`（新建）

第 5 与第 9 条是 v3 相对 v2 多出来的两条（v2 是 7 条）。两条**都必须**允许：只放 `tools/audit_demo.py`
而不放它的契约测试时，treatment 落地后这个新建动作会被 `TESTING-001`（`missing_tests`，error）拦下
（实测：A 臂 `TESTING-002` critical / B 臂 `TESTING-001` error —— 两臂都是 block，treatment 不翻面）。
`tools/__init__.py` 在基线里、**不在**允许写集合里（改它等于改基线）。

## 3 M5 三步与每一步的预期读数

| 步 | 动作 | A 臂（`configs/before`） | B 臂（`configs/after`） |
| --- | --- | --- | --- |
| M5a | 新建 `tests/test_audit_demo.py`（import 版，脚本还不存在） | `allow_with_warnings`（exit 1 = 非 ALLOW，**不是阻断**） | 同左 |
| M5b | 新建 `tools/audit_demo.py`（`main() -> list[dict]` + `__main__` 打印） | **`block`** / `TESTING-002@1` critical / `uncovered_checker`（exit 1） | **`allow`**（exit 0；`served_checkers` 含 `failing_tests`） |
| M5c | `python -m pytest -q` 与 `python tools/audit_demo.py` | 脚本已落盘则两臂相同：pytest 全绿、demo exit 0、stdout 合法 JSON 数组 | 同左 |

**翻面发生在 M5b**，且同时依赖三件事：①12 文件基线里有 `tools/__init__.py`（否则 M5a 就先阻断）；
②M5a 先写测试（否则 M5b 没有 related 测试 → `TESTING-001` 又拦一次）；③`tools/audit_demo.py` 确实由任务创建。

M5a 的 `pending_findings` 形状（实测）：`rule_id=TESTING-002`、`severity=warning`、
`evidence.kind=failing_tests`、`evidence.subject=tests/test_audit_demo.py`、`evidence.value=tools.audit_demo`。
它是**独立的 warning 通道**（AGENTS 第 51 条）：不产生 violation、不进 `violations`，
decision 仍是 `allow_with_warnings`——「待实现」既不是失败，也不是通过。

复现（两臂只差 `--config-root`；读数全是 `policy.check`，不启动 dsh）：

```powershell
# M5a：树 = 12 文件基线 + import 版 tests/test_audit_demo.py
$env:PYTHONPATH='src'
python -m policy.check tests/test_audit_demo.py --workspace <树> --layer test \
  --operation create --changed tests/test_audit_demo.py --config-root <configs/after> --json
# -> allow_with_warnings（pending: tools.audit_demo）
# M5b：同一棵树 + 参考实现 + tools/audit_demo.py
python -m policy.check tools/audit_demo.py --workspace <树> --layer module \
  --operation create --changed tools/audit_demo.py --config-root <configs/before> --json
# -> block / TESTING-002@1 critical / uncovered_checker
```

`configs/before` / `configs/after` = `docs/project/engineering-policy-platform/testing/ab/dgate2/configs/`
的两份快照（只差 `test-layout.yaml` 一个文件：`69e9d4bb…` → `af70bee1…`）。它们**不含**本包的哈希，
换快照 = 换输入，读数要重做。

## 4 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.txt` | `123c938c28a176ede6e2d888bea83b21e4a32684e5c4824283eeb376ee92625c`（5121 B / 46 行，UTF-8/LF/单尾换行） |
| `task-package/interfaces.md` | `ee94acc612eb079281963671a2cba46bb0a6b2c82c9785529b45c36123cc875c` |
| `task-package/acceptance.md` | `6cbcc6fa604da9b5b25cfa8fc08a6b7166d3ec7a31c4e2d4cc5f8d3df47ee654` |
| `task-package/allowed-writes.txt` | `c03bd30ad5dd076dd49026f8e4dbd4ca56bfda4f93100ddccca23dd9275fc1fe` |
| `task-package/milestones.md` | `115e997989a79230caf53e5d5aabd2d300bec5c63785afe02c0b4157dd7cf5ea` |
| `task-package/manifest.sha256` | `44d85e7e3bfc58ccfc6deb4bf39e19d056b7e89792c4113e00fd324c86c19217`（409 B / 5 行，覆盖前 5 文件） |
| `reset-arm.py` | `62b4fa8af4f388afa4ef6c492740a0e984ec08555ce635d1005530080142f2db`（16520 B；不在 manifest 里——manifest 只覆盖 `task-package/` 的 5 个文件） |

复核（Lead 开跑前逐行比对，5/5 必须 ok；任一不符 => 该 run 作废）：

```powershell
$pkg = 'examples/dsh/b-plan/a3-task-v3/task-package'
Get-Content "$pkg/manifest.sha256" | ForEach-Object {
  $h, $name = $_ -split '  ', 2
  $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $pkg $name)).Hash.ToLower()
  "{0}  {1}" -f ($(if ($actual -eq $h) { 'ok' } else { 'BAD' })), $name
}
```

## 5 怎么用（Lead）

```powershell
cd C:/Users/ZNM/Downloads/Memory
# 0) 看计划 / 重置：目标树默认 .tmp/a3b3/task-project（12 文件，不含 scaffold、不含任务要创建的两个文件）
.venv/Scripts/python.exe examples/dsh/b-plan/a3-task-v3/reset-arm.py --dry-run
.venv/Scripts/python.exe examples/dsh/b-plan/a3-task-v3/reset-arm.py
#    退出码：0 = 重置并校验通过；1 = 前置缺失（基线树/文件数/基线里混进了任务要创建的文件）；2 = 校验失败

# 1) 记下 audit 起始行数（ab_measure 的 --start-line）：看 reset-arm 打出的「audit start lines」
#    （没有 .policy 时是 0 / exists=false —— 那是「还没有受治账」，不是「没有动作」）

# 2) 装配受治配置（不在本包范围）：目标树 .policy 要有 approval.json、tool-registry.yaml
#    + tool-registry.approved.json、dsh-adapter.yaml、hooks.json、patch.yml。
#    审批绑的是上下文摘要：按**这棵树**审核/签发，不要照抄另一棵树的条子。

# 3) 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 123c938c…
cd .tmp/a3b3/task-project
$env:PYTHONPATH='C:/Users/ZNM/Downloads/Memory/src'; $env:PYTHONIOENCODING='utf-8'
$task = Get-Content -Raw -Encoding utf8 C:/Users/ZNM/Downloads/Memory/examples/dsh/b-plan/a3-task-v3/task-package/first-message.txt
dsh --profile headless --patch .policy/patch.yml $task
```

首消息复核：

```powershell
(Get-FileHash -Algorithm SHA256 examples/dsh/b-plan/a3-task-v3/task-package/first-message.txt).Hash.ToLower()
# 期望 123c938c28a176ede6e2d888bea83b21e4a32684e5c4824283eeb376ee92625c
```

启动若被 `workspace-write` 文件沙箱拒绝（写 `~/.dsh/profiles/headless/cordis.yml` EPERM），
按裁定 A-4 对**同一条启动命令**做一次性 `danger-full-access` 授权，并在 run-manifest 记
`launcher_sandbox=danger-full-access` + 跑后哈希复核。

## 6 与 v2 的差异（五点）

1. **基线 11 → 12 文件**：多一个 `tools/__init__.py`（让 `tools` 成为项目内包，M5a 的收集失败因此
   走「待实现」而不是第三方包缺失的 critical）。
2. **允许写 7 → 9**：多出 `tools/audit_demo.py` 与 `tests/test_audit_demo.py`（两条都必需，理由见 §2）；
   首消息第 5 行末尾「demo 已在基线预置，只运行、不要修改它」整句删掉。
3. **M5 拆成三步**（M5a 写测试 → M5b 写脚本 → M5c 跑），第 4 点改成 demo 的契约
   （`main() -> list[dict]` + `__main__` 打印），A7 改成「脚本由任务创建、exit 0、stdout 是合法 JSON 数组」，
   A8 改成 9 个路径。M1–M4、M6、M7、代码约定、pwsh 两参数约束、「被拒不重试」与 v2 逐字一致。
4. **无 scaffold**：`reset-arm.py` 不再复制 `a3-task-v2/scaffold/`，第 12 个文件内嵌在它里面；
   基线里出现 `scaffold/` 或任务要创建的两个文件会被直接拒绝。
5. **判定口径**：v2 的 demo 是「基线预置、只运行、不许改」，v3 的 demo 由任务创建、A7 直接判运行结果；
   组合摘要因此是 12 文件的 `4e7c4073…`（v2 是 12 文件的 `eb481089…`，但两者内容不同）。

## 7 边界

- **这是任务数据，不是平台规则**：本目录只描述「要模型做什么、允许写什么」，不改任何判定逻辑。
  真正改判定的那一处是 treatment 自己（`validation/test-layout.yaml` 的 `production_patterns`），
  它在仓库侧、不在这里。
- **改它 = 改构造**：任何改动（哪怕一个字节）都必须按 05 §8 记录理由与回退，然后重新冻结
  `task-package/manifest.sha256` 与本文第 4 节的哈希表；冻结后逐文件哈希不符 => 该 run 作废。
- **v2 是冻结历史**：`a3-task-v2/` 一个字节都不改，v3 是新目录；两版并存，v2 仍可复现旧 run。
- **本包不声称 treatment 生效**：activation 的判据 = 同一个固定动作在 A/B 两臂得到不同 decision。
  §3 的 M5b 就是那个动作（A 臂 block / B 臂 allow）；跑起来两臂都拿到这个读数，才算激活。
- **M5a 的 `allow_with_warnings` 不是「测试通过了」**：它是「待实现」的 warning 通道（AGENTS 第 51 条），
  测试是否通过要等 M5b 之后由 `failing_tests` 重新算。
- 任务完成判定（A1–A8）用包内 `acceptance.md` + 隐藏用例；A8 用树 diff 对 `allowed-writes.txt`。
