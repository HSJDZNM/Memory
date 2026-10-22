# 参考解（bank-crossmodule-refactor）

> **它是什么**：把 14 文件基线按 `SPEC.md` §3 做完之后的**参考树** + 决策点 + 实测读数。
> **它不参与判分**：T 由 `hidden/runner.py` 判、C 由 `policy.check` 判、A 由 `tools/structure_metrics.py` 判；
> 本目录只用来说明「这题可达、天花板在哪」。参考树不写 `.policy/**`（装配数据由 Lead 另签）。

## 1 改动面（10 条允许写 = 7 改 + 3 新建）

| 路径 | 动作 | 要点 |
| --- | --- | --- |
| `src/shop/order_repository.py` | 改 | `insert→add`、`listing→list_all`；复制语义逐字不变；旧名 0 处（含 docstring） |
| `src/shop/order_service.py` | 改 | `create` 调 `self.repository.add(payload)`；`listing→list_all`；构造器与 import 不变 |
| `src/shop/order_controller.py` | 改 | `listing→list_all` 调 `self.service.list_all()`；仍只 import `shop.order_service` |
| `src/shop/order_api.py` | 新建 | `OrderApi(repository)` 只转发的兼容门面；两个旧名方法各一行 `return self.repository.<新名>(...)` |
| `tests/test_order_repository.py` | 改 | 旧名断言改新名；保留「写入返回副本」，补一条「列出返回副本」 |
| `tests/test_order_service.py` | 改 | `create` + `list_all` |
| `tests/test_order_controller.py` | 改 | `create` + `list_all` |
| `tests/test_order_api.py` | 新建 | 4 条：替身转发（两方法各一）、经门面的副本语义、两个方法 docstring 的弃用与新名 |
| `docs/api.md` | 新建 | `## 对照表` / `## 废弃期限` / `## 迁移示例` 三节；四个词 + `v2.0` + 围栏代码块 |
| `README.md` | 改 | 结构表加 `src/shop/order_api.py` 一行（业务/兼容门面）+ 文末链接 `docs/api.md` |

冻结的 7 个文件（`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`tools/__init__.py`、
`config/refund_policy.yaml`、`data/refunds-legacy.jsonl`）**一个字节都没动**（T24 的 7/7 逐字节校验）。

## 2 决策点

1. **先 expand 再 contract**：`milestones.md` 的 M2/M4/M5 要求先留两行薄转发让调用点继续可跑，M7 再删。
   参考树是**终态**（薄转发已删），中间态不在树里；它只用来证明「终态可达且旧名清零」。
2. **门面放 service 层**（`layers.yaml` 已声明 `src/shop/order_api.py: service`）：它依赖 repository，
   与 `order_service` 同向；若声明成 controller 会让 A1 的分层方向与 ARCH-001 的适用面同时变味。
3. **门面只转发、不复制、不 new**：`insert` / `listing` 都只有一行 `return self.repository.<新名>(...)`；
   构造器只保存传入对象。这样 T11–T17（同一对象透传、异常原样穿出、import 面）与 SPEC §3 的
   「只读兼容门面」一致；顺手做防御性拷贝会让 `id()` 变，反而不满足契约。
4. **弃用说明写在方法 docstring 里**（「已弃用的旧名：原样转发到 `OrderRepository.add(payload)`」）：
   `DOC-001`（warning）与隐藏 T16 判的是同一个事实；说明里带新名，迁移者不用翻文档就知道改叫什么。
5. **测试用替身 + 真仓库两条路**：替身证明「参数与返回值原样透传、没有第二次调用」；真 `OrderRepository`
   证明「经门面写入仍返回副本」。只写替身会漏掉副本语义，只写真仓库漏掉透传与调用次数。
6. **`docs/api.md` 的迁移示例同时给新旧两种写法**：先给过渡期的 `OrderApi` 用法，再给 `v2.0` 之后的
   `repository.add(...)` / `repository.list_all()`——这样「废弃期限」那句话有可执行的落点。
7. **`tests/test_order_repository.py` 多一条 `list_all` 副本用例**：允许写包含该文件；收集数从 3 变 4，
   对应 `scoring.yaml` 的 B2「收集数 >= 4」与隐藏 EN2。

## 3 实测读数（2026-10，本宿主；命令见 §4）

| 维度 | 读数 | 证据 |
| --- | --- | --- |
| T（隐藏） | **33 / 33**，runner 退出 0 | 两次运行 stdout **逐字节相同**，sha256 = `3a0d46b5e9c0a6ed875ecbbb5a927cd6067b348ebb0ce38c00ca454467e573ba`（T21 已按 2026-10-22 H1 改判删除） |
| T（基线红） | **4 / 33**，runner 退出 1 | 仅 `T24`（冻结文件本来就对）、`EN1`（基线 3 passed）、`EN3`、`EN4` 通过；两次运行逐字节相同，sha256 = `f32db9c4a011dbab25293e8c5ebe032da1fb5165721c50fb23e04fbba63f2064` |
| pytest | `8 passed`（基线 3 → 8） | 参考树副本里 `python -m pytest -q`，退出 0 |
| A（结构） | **10 / 10 pass**，`structure_metrics` 退出 0 | `schema_version: 1.1`；A3 = 5 模块 / 12 个公开定义 / 0 越界；A9 = 5/5 生产文件被测试静态 import |
| C（规则） | **8 / 8 allow，0 条 violations**（error 0、warning 0） | `effective_total = 30`（8 条规则 × 3 + 冻结 3 + 旁路 3）⇒ **30 / 30**；`ARCH-001` 在 7 个非 controller 层进 `skipped_rules`（`scope_mismatch`），在 `src/shop/order_controller.py` 上真参与判定 |

**逐文件 C 读数**（`--layer` 取 `layers.yaml` 的值；`--changed` 为 10 条允许写逐条）：

| 文件 | layer | decision | violations | skipped |
| --- | --- | --- | --- | --- |
| `src/shop/order_api.py` | service | allow | — | ARCH-001@1 |
| `src/shop/order_controller.py` | controller | allow | — | — |
| `src/shop/order_repository.py` | repository | allow | — | ARCH-001@1 |
| `src/shop/order_service.py` | service | allow | — | ARCH-001@1 |
| `tests/test_order_api.py` | test | allow | — | ARCH-001@1 |
| `tests/test_order_controller.py` | test | allow | — | ARCH-001@1 |
| `tests/test_order_repository.py` | test | allow | — | ARCH-001@1 |
| `tests/test_order_service.py` | test | allow | — | ARCH-001@1 |

**「跳过 ≠ 通过」**：上表的 `ARCH-001@1` 是 `scope_mismatch`（规则 scope 是 `layer=controller`），
`check_volume.blocking_capable_skipped = 1`；controller 那份 `blocking_capable_skipped = 0`、
5 个 checker 全部 `served_checkers`。C 的 8 条规则里没有 N/A，所以 `effective_total` 仍是 30。

## 4 复现命令（Git Bash / pwsh 逐条执行，cwd = 仓库根）

```powershell
$TASK = 'docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-crossmodule-refactor'
$TREE = "$TASK/reference/tree"

# T：隐藏验收（33/33，退出 0；两次运行 stdout 逐字节相同）
$env:BANK_TASK_TREE = $TREE
.venv/Scripts/python.exe "$TASK/hidden/runner.py"

# pytest：8 passed
Push-Location $TREE; .venv/Scripts/python.exe -m pytest -q; Pop-Location

# A：10/10 pass（退出 0）
.venv/Scripts/python.exe tools/structure_metrics.py --workspace $TREE `
  --layers "$TASK/layers.yaml" --interfaces "$TASK/interfaces.yaml" --json

# C：逐文件（每个 .py 一次；--changed 写 10 次；--request-id 固定）
$env:PYTHONPATH = 'src'
$changed = Get-Content "$TASK/task-package/allowed-writes.txt" | ForEach-Object { @('--changed', $_) }
.venv/Scripts/python.exe -m policy.check src/shop/order_controller.py --workspace $TREE `
  --config-root . --layer controller --operation edit @changed `
  --request-id bank-crossmodule-reference-src-shop-order_controller --json
```

（其余 7 个文件的 `--layer`：`order_api`/`order_service` = service、`order_repository` = repository、
4 个测试 = test；`--request-id` 每个文件一个固定值 `bank-crossmodule-reference-<path-slug>`。）

## 5 与 SPEC / 计划骨架的偏差（都是实测发现的构造问题，不是放宽判据）

1. **旧名全树扫描只能覆盖「可改写」的 .py**：`conftest.py` 里有 `sys.path.insert(0, str(SRC))`——
   这是标准库调用，不是被废弃的 `OrderRepository.insert`，而 `conftest.py` 是冻结文件（T24 逐字节钉住）。
   所以 `hidden/PLAN.md` 的 T05 收成「**非冻结** .py 里旧名只出现在门面与它的契约测试里」；
   `interfaces.md` §3 的「其余所有 .py 文件里 0 处」按字面执行会让这题**无解**（基线自带的冻结文件里
   就有一处 `insert`）。这是隐藏 runner 在参考树上第一次跑就红出来的，记在 `PLAN.md` §6。
2. **`list_all` 的副本语义是浅拷贝**：基线 `dict(row)` 只复制顶层键，所以 `{"a": {"b": 1}}` 的嵌套对象
   在基线与参考树里都被共享。`coverage.md` §6 的 T08 计划里写着「改嵌套 dict 不影响内部」，
   那等于要求与基线**不等价**；`PLAN.md` 的 T08 只判顶层键与 list/行对象身份（SPEC §3 的「每行新的 dict」
   不包含深拷贝承诺）。
3. **`docs/api.md` 的 `add(` / `list_all(` 必须出现在迁移示例里**：只写「转发到 add」不够——
   `task-package/first-message.md` 的 A7 明确要求示例里出现 `add(` / `list_all(`；参考解的示例
   同时给过渡期写法与 `v2.0` 之后的直接用法。
4. **收集数是 8 不是 4**：参考解在 `tests/test_order_repository.py` 补了一条 `list_all` 副本用例
   （3 + 1 + 4 = 8）。`scoring.yaml` 的 B2 与隐藏 EN2 只要求 `>= 4`，多写不算违规。
5. **没有写 `.policy/**`**：参考树只是「最终代码树」，装配（审批 / 工具注册表 / hooks / pre_evidence）
   由 Lead 按这棵树另签；本目录不伪造凭据。

## 6 这份参考解**不**证明什么

- 不证明模型会按 M1–M9 的顺序做（里程碑顺序是过程维度，T 不判）；
- 不证明「中间态被 TESTING-002 / TESTING-001 / ARCH-001 拦住」——那是 `coverage.md` §7 的探针 P3–P10，
  它们是规则读数，不进 T；
- 不证明测试断言没有被改弱（H2 人工抽样）；
- 不构成 A/B 证据：本题 `treatment.arms` 为空，参考树只是天花板，n=1 也不写「值得扩试」。
