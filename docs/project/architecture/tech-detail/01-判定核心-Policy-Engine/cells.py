
# -*- coding: utf-8 -*-
"""01-判定核心-Policy-Engine：一次判定怎么算出来（内容源，产物由 build_notebooks.py 生成）。"""
from __future__ import annotations

from notebook_lib import NotebookSpec, code, markdown

SPEC = NotebookSpec(
    stem="01-判定核心-Policy-Engine",
    title="单技术：Policy Engine 内部流程",
    summary="把图上的九步逐步跑一遍：规则集与上下文、范围匹配、跳过原因、证据门禁、checker 分派、稳定排序、审批标记与三值判定",
    temp_dir=".tmp/tech-detail/01",
    cells=(
        markdown(
            '''
# 01 判定核心：Policy Engine 内部流程

这份 notebook 配合同名图 `01-判定核心-Policy-Engine.drawio`。图回答一个问题——**一次判定到底是怎么算出来的**；
notebook 把图上的九步逐步跑一遍，每一步都留下能核对的输出，关键结论用 `assert` 钉住。

| 步骤 | 图上节点（第二行锚点） | 本 notebook 里的代码锚点 |
| --- | --- | --- |
| 1 | 规则集就绪 · RuleSet.identity | `policy.loader.load_rule_set` |
| 2 | 上下文规范化 · 只接受显式字段 | `policy.context.build_context` / `normalize_context` |
| 3 | 范围匹配 · 同维 OR / 跨维 AND | `policy.engine.matching_rules` |
| 4 | 跳过要写原因 · skipped ≠ 通过 | `ValidationResult.skipped_rules` |
| 5 | 证据门禁 · blocker_for / serves | `policy.evidence.EvidenceBundle` |
| 6 | checker 分派 · checker_handler | `policy.checkers` |
| 7 | 违规稳定排序 · violations.sort | `Violation.sort_key` |
| 8 | 审批标记 · requires_approval | `RequiredAction.APPROVAL` |
| 9 | 三值判定 · allow / warning / block | `policy.models.expected_decision` |

图外还有两条红色旁路，本 notebook 也会各跑一次：**无证据不判通过**（验证器不可用 / 未覆盖 → critical 阻断）
与**高风险要人批**（`RequiredAction.APPROVAL`）。

**预备知识**：认识 Python 的函数、字典与 `try / except` 就够了。全部代码只调用仓库里已经测试过的模块，
不联网、不装包、不改仓库真实文件；本 notebook 的写操作一律落在它独占的 `.tmp/tech-detail/01/` 下。
'''
        ),
        code(
            '''
# 先找到仓库根目录：notebook 可能从仓库根启动，也可能从本目录启动，两种都要能跑。
import sys
from pathlib import Path


def find_repo_root(start):
    """往上找：同时有 pyproject.toml 与 src/policy/ 的那一层就是仓库根。"""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "policy").is_dir():
            return candidate
    raise SystemExit("没有找到仓库根目录（需要 pyproject.toml 与 src/policy/）")


REPO_ROOT = find_repo_root(Path.cwd())
for extra in (REPO_ROOT / "src", REPO_ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

# 本 notebook 独占的临时目录：生成器会检查仓库不许因此多出未被忽略的文件。
TEMP = REPO_ROOT / ".tmp" / "tech-detail" / "01"
TEMP.mkdir(parents=True, exist_ok=True)

from policy import checkers, context as context_module, engine, loader, models

# —— 第 1 步：规则集就绪。加载器按来源路径排序，规则集身份与调用方给的顺序无关。
RULE_ROOTS = sorted(path for path in (REPO_ROOT / "policies").iterdir() if path.is_dir())
RULES = loader.load_rule_set(RULE_ROOTS, repo_root=REPO_ROOT)
SHUFFLED_RULES = loader.load_rule_set(list(reversed(RULE_ROOTS)), repo_root=REPO_ROOT)

print("仓库根目录:", REPO_ROOT.name)
print("临时目录:", TEMP.relative_to(REPO_ROOT).as_posix())
print("规则目录（按名字排序）:", ", ".join(path.name for path in RULE_ROOTS))
print("规则集:", len(RULES), "条规则 | 身份:", RULES.identity[:26] + "...")
print("前两条来源:", ", ".join(RULES.source_paths[:2]))
print("协议:", models.SCHEMA_VERSION, "| 世代:", models.POLICY_VERSION)
print("引擎支持的 checker:", ", ".join(sorted(checkers.SUPPORTED_CHECKERS)))

# 把目录顺序倒过来再加载一次：规则集身份与规则清单必须一模一样。
assert SHUFFLED_RULES.identity == RULES.identity, (SHUFFLED_RULES.identity, RULES.identity)
assert SHUFFLED_RULES.ids == RULES.ids
print("目录顺序倒过来加载，身份与清单不变:", SHUFFLED_RULES.identity == RULES.identity)

# 加载门禁：未知 checker 在加载阶段就报错，而不是等到判定时静默跳过。
broken_dir = TEMP / "bad-rules"
broken_dir.mkdir(parents=True, exist_ok=True)
original = (REPO_ROOT / "policies" / "architecture" / "ARCH-001.yaml").read_text(encoding="utf-8")
(broken_dir / "ARCH-500.yaml").write_text(
    original.replace("checker: forbidden_dependency", "checker: no_such_checker"), encoding="utf-8"
)
try:
    loader.load_rules(broken_dir, repo_root=REPO_ROOT)
except loader.LoaderError as error:
    print("未知 checker 在加载阶段被拒绝:", " ".join(str(error).split())[:72])
else:
    raise AssertionError("未知 checker 本应让加载失败：那会让规则悄悄失效")


# —— 第 2 步：上下文规范化。同一个文件的三种写法必须收敛成同一个值。
def build(file, **fields):
    """按核心层入口造一个规范化上下文；安全关键字段缺失时它会直接失败。"""
    payload = {"request_id": "nb-01", "file": file, "layer": "controller", "language": "python"}
    payload.update(fields)
    return context_module.build_context(payload, repo_root=REPO_ROOT)


windows_path = "src" + chr(92) + "order" + chr(92) + "controller.py"
variants = ("src/order/controller.py", "./src//order/controller.py", windows_path)
normalized = [build(item).file for item in variants]
print()
print("三种写法 ->", normalized)
assert normalized == ["src/order/controller.py"] * 3, normalized

steady = build("src/order/controller.py")
assert context_module.normalize_context(steady).model_dump() == steady.model_dump()
print("再规范化一次仍是同一个值（幂等）")

# 失败关闭：安全关键字段缺失、未知操作都拒绝，绝不猜一个默认值。
for fields in ({"layer": None}, {"operation": "deploy"}):
    try:
        build("src/order/controller.py", **fields)
    except models.PolicyContextError as error:
        print("已按预期拒绝", sorted(fields), "->", " ".join(str(error).split())[:52])
    else:
        raise AssertionError(f"{fields} 本应失败关闭")
'''
        ),
        markdown(
            '''
## 1. 读上面这段输出：规则集与上下文

**规则集就绪（第 1 步）**：`RULES.identity` 是规则内容的 sha256 指纹，用来把一份决定绑定到一版规则。
输出里特意把规则目录**倒序**再加载一次——身份与规则清单完全一样，因为 loader 会按来源路径排序，
顺序是它自己定的，不是调用方给的。这就是图上"与加载顺序无关"的含义。

同一段还演示了加载门禁：把 `checker` 写成一个不存在的名字，加载阶段就报错。
理由很直接——未知执行方式如果被放过，规则会"看起来在管这件事、实际什么都没查"。
这类失效在运行期看不出来，只能在加载时拦下。

**上下文规范化（第 2 步）**：三种写法（正常斜杠路径、带 `./` 与重复斜杠、Windows 反斜杠）
收敛成同一个仓库相对路径；再规范化一次不变（幂等）；缺 `layer` 或写一个不存在的操作都直接失败。
这一层只发生在 Adapter 边界，引擎内部不再猜任何字段——这是"相同输入得到相同结论"的第一层保证。
'''
        ),
        code(
            '''
# 第 3 步：范围匹配。跨维度是 AND（都要满足），同维度多值是 OR（满足其一即可）。
# 下面这张表用的全是仓库里真实的规则：ARCH-001（管 controller 层）与 TESTING-001（管变更操作）。
ARCH_RULE = next(rule for rule in RULES.rules if rule.id == "ARCH-001")
ARCH_RULES = models.RuleSet(rules=(ARCH_RULE,))

matrix = (
    ({}, "两条规则都要的维度都没给全：operation 缺失"),
    ({"operation": "edit"}, "edit 落在 [create, edit] 里（同维多值 = OR）"),
    ({"operation": "create"}, "create 同样落在列表里"),
    ({"operation": "read"}, "read 不在列表里：范围不匹配"),
    ({"layer": "service", "operation": "edit"}, "layer 不等：ARCH-001 出局；TESTING-001 的两个维度都满足"),
    ({"language": "go"}, "language 不等：跨维度 AND，两条都出局"),
)

print(pad("补充的维度", 42) + pad("ARCH-001", 12) + pad("TESTING-001", 14) + "说明")
print("-" * 118)
rows = []
for fields, note in matrix:
    context = build("src/order/controller.py", **fields)
    matched, skipped = engine.matching_rules(RULES, context)
    record = {
        "fields": fields,
        "hits": {rule.id for rule in matched},
        "reasons": {item.rule_id: item.reasons[0] for item in skipped},
    }
    rows.append(record)
    print(
        pad(fields or "（什么都不补充）", 42)
        + pad("命中" if "ARCH-001" in record["hits"] else "跳过", 12)
        + pad("命中" if "TESTING-001" in record["hits"] else "跳过", 14)
        + note
    )

# 同一张表用 assert 钉死：OR、AND、"声明了维度但上下文缺值"三种语义各一条。
assert "ARCH-001" in rows[0]["hits"] and "TESTING-001" not in rows[0]["hits"]
assert "<missing>" in rows[0]["reasons"]["TESTING-001@1"], rows[0]["reasons"]
assert {"ARCH-001", "TESTING-001"} <= rows[1]["hits"]
assert {"ARCH-001", "TESTING-001"} <= rows[2]["hits"]
assert "TESTING-001" not in rows[3]["hits"]
assert "ARCH-001" not in rows[4]["hits"] and "TESTING-001" in rows[4]["hits"]
assert not ({"ARCH-001", "TESTING-001"} & rows[5]["hits"])
print()
print("上下文缺 operation 时的跳过原因:", rows[0]["reasons"]["TESTING-001@1"])
print("只写 read 时的跳过原因:", rows[3]["reasons"]["TESTING-001@1"])

# 未知 checker 有两道闸。第一道在模型层：连"手工造的规则对象"都进不了 RuleSet。
from pydantic import ValidationError

ghost = ARCH_RULE.model_copy(
    update={
        "id": "ARCH-500",
        "enforcement": ARCH_RULE.enforcement.model_copy(update={"checker": "no_such_checker"}),
    }
)
try:
    models.RuleSet(rules=(ghost,))
except ValidationError as error:
    detail = " ".join(str(error).split()).split("Value error, ", 1)[-1].split(" [type=")[0]
    print()
    print("模型层拒绝未知 checker:", detail[:96])
else:
    raise AssertionError("未知 checker 本应在模型校验阶段被拒绝")

# 第二道闸在引擎里：就算有人绕过校验把规则塞进来（model_construct 不做校验），
# 命中时 engine 也会以 EngineError 拒绝执行——未知执行方式不得放行、也不得静默跳过。
smuggled = models.RuleSet.model_construct(rules=(ghost,))
try:
    engine.matching_rules(smuggled, build("src/order/controller.py"))
except engine.EngineError as error:
    print("引擎仍然拒绝执行:", " ".join(str(error).split())[:64])
else:
    raise AssertionError("未知 checker 不得被静默跳过：那等于这条规则从未生效")
'''
        ),
        markdown(
            '''
## 2. 跳过要写原因：skipped 不等于通过（第 4 步）

范围没命中的规则不是"通过"，而是"这次不参与判断"。所以它必须带着原因进 `skipped_rules`：

- 一条规则可能因为**范围**不匹配被跳过（例如 `layer service != controller`）；
- 也可能因为**没有证据**被跳过——这就是第 5 步证据门禁要回答的事。

下面这段只给上下文、不给证据，看引擎怎么把这两种原因分开写清楚。它用的是**全部 43 条规则**。
'''
        ),
        code(
            '''
# 第 4 步：只给上下文（没有验证器证据）时，证据类规则进 skipped_rules 并写明原因。
context = build("src/order/controller.py")
verdict = engine.evaluate(RULES, context)

print("决策:", verdict.decision.value, "| 参与判断:", verdict.matched_rules)
print("跳过:", len(verdict.skipped_rules), "条 | 规则总数:", len(RULES))
print()
print(pad("规则", 14) + pad("checker", 22) + "跳过原因")
print("-" * 118)
reasons = {item.rule_id: item.reasons[0] for item in verdict.skipped_rules}
checkers_of = {rule.canonical_id: rule.enforcement.checker for rule in RULES.rules}
for rule_id in ("DOC-001@1", "STYLE-001@1", "TESTING-001@1"):
    print(pad(rule_id, 14) + pad(checkers_of[rule_id], 22) + reasons[rule_id])

# 四条断言把"跳过"的语义钉住。
assert verdict.decision is models.Decision.ALLOW
assert verdict.matched_rules == ("ARCH-001@1",), verdict.matched_rules
assert len(verdict.skipped_rules) == len(RULES) - len(verdict.matched_rules)
assert "需要验证器证据" in reasons["DOC-001@1"], reasons["DOC-001@1"]

# allow 不等于"什么都没发生"：同一个上下文只要真的依赖了 repository，立刻 block。
hit = engine.evaluate(RULES, build("src/order/controller.py", dependencies=("repository",)))
assert hit.decision is models.Decision.BLOCK and hit.violations[0].canonical_id == "ARCH-001@1"
print()
print("同样的上下文加上 dependencies=repository ->", hit.decision.value, "（ARCH-001@1）")

# 相同输入必须得到相同结论：重跑一次的决策载荷逐项相等。
repeat = engine.evaluate(RULES, build("src/order/controller.py"))
assert repeat.to_decision_dict() == verdict.to_decision_dict()
print("同一份输入重跑一次，决策载荷完全相同:", repeat.to_decision_dict() == verdict.to_decision_dict())
'''
        ),
        markdown(
            '''
## 3. 证据门禁与 checker 分派（第 5、6 步）

引擎自己没有"怎么看代码"的知识，它只消费**验证器流水线**交给它的证据包 `EvidenceBundle`：

| 证据包里的东西 | 引擎拿它做什么 |
| --- | --- |
| `served_checkers` | `serves(checker)`：这个 checker 真的有验证器跑成功了 |
| `blockers` | `blocker_for(checker)`：关键验证器没跑成，需要它的规则直接 critical 阻断 |
| `dependencies` / `evidence` | 交给对应 checker 的判定函数，变成带文件与行号的 violation |

分工是：**验证器只产证据，判定永远由引擎做**。流水线自己会在 `.tmp/validators/<run-id>/` 下
开一次性的运行期目录（每个验证器一个子目录），与本 notebook 的 `.tmp/tech-detail/01/` 互不干扰。

第 6 步就是查表：`checker_handler(checker)` 返回该 checker 的判定函数。表里只有两类——
上下文类（只看 `PolicyContext` 就能判）与证据类（没有证据就不能判）。
'''
        ),
        code(
            '''
# 第 5、6 步：跑一次真实的验证器流水线，把它的证据包交给引擎判定。
import shutil

from validators.pipeline import PipelineRequest, run_pipeline
from validators.registry import load_config

FIXTURE_PROJECT = REPO_ROOT / "tests" / "fixtures" / "validators" / "project"
WORKSPACE = TEMP / "fixture-project"
if WORKSPACE.exists():
    # 生成器会从两个工作目录各跑一遍，第二遍要能覆盖上一遍留下的副本。
    shutil.rmtree(WORKSPACE)
shutil.copytree(FIXTURE_PROJECT, WORKSPACE)

VALIDATION = load_config(root=REPO_ROOT)
TARGET = "src/shop/order_controller_bad.py"
evidence_context = context_module.build_context(
    {"request_id": "nb-01-evidence", "file": TARGET, "layer": "controller", "language": "python"},
    repo_root=WORKSPACE,
)
report = run_pipeline(
    PipelineRequest(target=TARGET, workspace=WORKSPACE, context=evidence_context, rules=ARCH_RULES),
    config=VALIDATION,
)
bundle = report.bundle

print("受控工作区:", WORKSPACE.relative_to(REPO_ROOT).as_posix(), "（夹具项目的一次性副本）")
print("跑过的验证器:", ", ".join(item.validator + "=" + item.status.value for item in report.validators))
print()
print(pad("checker", 24) + pad("有验证器为它产证据", 20) + "让该 checker 无法判定的阻断点")
print("-" * 100)
for name in sorted(checkers.SUPPORTED_CHECKERS):
    blocker = bundle.blocker_for(name)
    print(
        pad(name, 24)
        + pad(bundle.serves(name), 20)
        + ("无" if blocker is None else blocker.validator + " " + blocker.status.value)
    )

print()
print(pad("依赖名", 14) + pad("形态", 16) + pad("解析", 12) + pad("文件", 36) + "行")
print("-" * 100)
for fact in bundle.dependencies:
    print(
        pad(fact.name, 14)
        + pad(fact.kind.value, 16)
        + pad(fact.resolution.value, 12)
        + pad(fact.file or "-", 36)
        + str(fact.line)
    )

# 证据到位：ARCH-001 由依赖证据判定，文件与行号来自证据，严重级别来自规则。
evidenced = engine.evaluate(ARCH_RULES, evidence_context, evidence=bundle)
violation = evidenced.violations[0]
print()
print("决策:", evidenced.decision.value, "| 违规:", violation.canonical_id, violation.severity.value)
print("证据:", violation.evidence.file + ":" + str(violation.evidence.line), "=", violation.evidence.value)
print("说明:", violation.evidence.detail)
assert bundle.serves("forbidden_dependency") and bundle.blocker_for("forbidden_dependency") is None
assert evidenced.decision is models.Decision.BLOCK
assert violation.canonical_id == "ARCH-001@1"
assert violation.severity is models.Severity.ERROR
assert violation.evidence.file == TARGET and isinstance(violation.evidence.line, int)

# 第 6 步查表：每个 checker 都有判定函数，两类 checker 互不重叠。
print()
print(pad("checker", 24) + pad("类别", 12) + "分派到的判定函数")
print("-" * 84)
for name in sorted(checkers.SUPPORTED_CHECKERS):
    kind = "上下文类" if name in checkers.CONTEXT_CHECKERS else "证据类"
    print(pad(name, 24) + pad(kind, 12) + checkers.checker_handler(name).__name__)

assert set(checkers.CONTEXT_CHECKERS) | set(checkers.EVIDENCE_CHECKERS) == set(checkers.SUPPORTED_CHECKERS)
assert not (set(checkers.CONTEXT_CHECKERS) & set(checkers.EVIDENCE_CHECKERS))
used_checkers = {rule.enforcement.checker for rule in RULES.rules}
assert used_checkers <= set(checkers.SUPPORTED_CHECKERS)
assert set(checkers.SUPPORTED_CHECKERS) - used_checkers == {"type_check"}, sorted(used_checkers)
print()
print("仓库里的规则用到:", ", ".join(sorted(used_checkers)))
print("唯一没有规则启用的 checker: type_check（mypy 未接入，下一条旁路会用到它）")
'''
        ),
        markdown(
            '''
## 4. 旁路一：无证据不判通过

图右侧那个红框是这张图最重要的一步。**没有证据不等于没有问题**，两种情况都必须失败关闭：

1. **验证器不可用**：关键验证器没跑成（缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法 / 本次没被选中），
   需要它的规则由 `blocker_for(checker)` 命中，产生 **critical** 违规；
2. **未覆盖**：有规则要用某个 checker，却没有任何验证器为它声明过证据，同样 critical。

两条都用 `assert` 钉住，并额外验证一句容易被忽略的话：**同一批里的其他 PASS 抵消不了它。**
'''
        ),
        code(
            '''
# 旁路一的第 1 种情况：验证器不可用。只跑 py.source，依赖验证器没被选中。
narrow = run_pipeline(
    PipelineRequest(
        target=TARGET,
        workspace=WORKSPACE,
        context=evidence_context,
        rules=ARCH_RULES,
        only=("py.source",),
    ),
    config=VALIDATION,
)
blocker = narrow.bundle.blocker_for("forbidden_dependency")
assert narrow.bundle.serves("forbidden_dependency") is False
assert blocker is not None and blocker.status.value == "not_selected"

unavailable = engine.evaluate(ARCH_RULES, evidence_context, evidence=narrow.bundle)
print("验证器不可用（只跑 py.source）:")
print("  阻断点:", blocker.validator, "状态", blocker.status.value)
print("  决策:", unavailable.decision.value, "| 严重级别:", sorted({item.severity.value for item in unavailable.violations}))
print("  给调用方的理由:", unavailable.violations[0].message[:78])
assert unavailable.decision is models.Decision.BLOCK
assert all(item.severity is models.Severity.CRITICAL for item in unavailable.violations)

# 旁路一的第 2 种情况：未覆盖。type_check 没有任何验证器为它产证据。
uncovered_rule = models.Rule(
    id="TYPES-001",
    version=1,
    name="type-check-required",
    description="示例规则：类型检查必须通过。本仓库没有启用它（mypy 未接入），用来演示未覆盖 checker 的失败关闭。",
    scope=models.RuleScope(language="python"),
    severity=models.Severity.ERROR,
    enforcement=models.Enforcement(
        type=models.EnforcementType.DETERMINISTIC, checker="type_check"
    ),
    rule=models.TypeCheckRule(type_check=models.TypeCheckSpec(tool="mypy")),
    message="类型检查未通过或未执行。",
    source=models.SourceRef(kind="project-policy", path="policies/coding/DOC-001.yaml"),
)
uncovered = engine.evaluate(models.RuleSet(rules=(uncovered_rule,)), evidence_context, evidence=bundle)
print()
print("未覆盖（没有验证器声明 type_check）:")
print("  决策:", uncovered.decision.value, "| 严重级别:", sorted({item.severity.value for item in uncovered.violations}))
print("  给调用方的理由:", uncovered.violations[0].message[:78])
assert uncovered.decision is models.Decision.BLOCK
assert uncovered.violations[0].severity is models.Severity.CRITICAL

# 抵消不了：一条单独跑能 PASS 的规则，与未覆盖的规则放在同一批里仍然阻断。
quiet_rule = ARCH_RULE.model_copy(
    update={
        "id": "ARCH-777",
        "rule": ARCH_RULE.rule.model_copy(update={"forbidden_dependency": ("orm",)}),
    }
)
quiet = engine.evaluate(models.RuleSet(rules=(quiet_rule,)), evidence_context, evidence=bundle)
mixed = engine.evaluate(models.RuleSet(rules=(quiet_rule, uncovered_rule)), evidence_context, evidence=bundle)
print()
print("单独跑 ARCH-777（证据里没有 orm）->", quiet.decision.value, "| 违规", len(quiet.violations), "条")
print("与未覆盖的规则放在同一批 ->", mixed.decision.value, "| critical 违规", len(mixed.violations), "条")
assert quiet.decision is models.Decision.ALLOW and not quiet.violations
assert mixed.decision is models.Decision.BLOCK
assert any(item.severity is models.Severity.CRITICAL for item in mixed.violations)
'''
        ),
        markdown(
            '''
## 5. 收尾三步：稳定排序、审批标记、三值判定（第 7–9 步）

**稳定排序（第 7 步）**：违规列表按 `sort_key = (规则身份, 证据值, 证据主体)` 排序。
规则在文件里怎么写、按什么顺序加载，都不影响输出顺序——否则审计记录每次 diff 都在变，比对就没有意义。

**审批标记（第 8 步）**：规则可以声明 `enforcement.requires_approval`。一旦范围命中，
即使**一条违规都没有**，决策也是 `block` 并带上 `required_action=approval`：
授权是前置条件，不能被降级成"提醒一下"。

**三值判定（第 9 步）**：决策只有三种取值，映射关系固定：

| 最高严重级别 | 决策 |
| --- | --- |
| 没有违规，也没有审批要求 | `allow` |
| `info` / `warning` | `allow_with_warnings` |
| `error` / `critical`，或者要求人工审批 | `block` |

下面这段用真实的 ARCH-001 复制出几份变体（冻结模型只能 `model_copy`，不能直接改字段）来验证这三步。
'''
        ),
        code(
            '''
# 第 7、8、9 步：稳定排序、审批标记、三值判定。


def variant(rule_id, severity, *, requires_approval=False, forbidden=("repository",)):
    """以真实的 ARCH-001 为原型复制一条变体：只换身份、严重级别、禁止依赖与审批开关。"""
    return ARCH_RULE.model_copy(
        update={
            "id": rule_id,
            "severity": models.Severity(severity),
            "enforcement": ARCH_RULE.enforcement.model_copy(
                update={"requires_approval": requires_approval}
            ),
            "rule": ARCH_RULE.rule.model_copy(update={"forbidden_dependency": tuple(forbidden)}),
        }
    )


# 第 7 步：三条规则、四条违规，连跑三次 + 打乱输入顺序，结论与顺序都不许变。
three = (
    variant("ARCH-010", "error", forbidden=("orm", "repository")),
    variant("ARCH-002", "error"),
    variant("CODING-003", "warning", forbidden=("logging",)),
)
ordering_context = build("src/order/controller.py", dependencies=("orm", "repository", "logging"))
ordered = engine.evaluate(models.RuleSet(rules=three), ordering_context)
shuffled = engine.evaluate(models.RuleSet(rules=(three[2], three[0], three[1])), ordering_context)
again = engine.evaluate(models.RuleSet(rules=three), ordering_context)

print(pad("违规（规则身份，证据值）", 42) + "严重级别")
print("-" * 96)
for item in ordered.violations:
    print(pad(str((item.canonical_id, item.evidence.value)), 42) + item.severity.value)
print()
keys = [item.sort_key for item in ordered.violations]
assert keys == sorted(keys), "违规必须按 sort_key 稳定排序"
assert [item.sort_key for item in shuffled.violations] == keys
assert shuffled.to_decision_dict() == ordered.to_decision_dict() == again.to_decision_dict()
assert ordered.matched_rules == ("ARCH-002@1", "ARCH-010@1", "CODING-003@1")
print("连跑与打乱的结论、顺序完全相同:", shuffled.to_decision_dict() == ordered.to_decision_dict())

# 第 8 步：审批门禁——没有违规也要 block + required_action=approval。
gate = engine.evaluate(
    models.RuleSet(rules=(variant("ARCH-004", "warning", requires_approval=True),)),
    build("src/order/controller.py", dependencies=("service",)),
)
print()
print(
    "审批门禁: 决策",
    gate.decision.value,
    "| 违规",
    len(gate.violations),
    "条 | required_action",
    gate.required_action.value,
)
assert gate.decision is models.Decision.BLOCK
assert not gate.violations and gate.required_action is models.RequiredAction.APPROVAL

# 第 9 步：三值判定表。
print()
print(pad("规则的 severity", 18) + pad("有违规时", 24) + "无违规时")
print("-" * 60)
table = {}
for level in ("info", "warning", "error", "critical"):
    single = models.RuleSet(rules=(variant("ARCH-001", level),))
    hot = engine.evaluate(single, build("src/order/controller.py", dependencies=("repository",)))
    clean = engine.evaluate(single, build("src/order/controller.py", dependencies=("service",)))
    table[level] = (hot.decision.value, clean.decision.value)
    print(pad(level, 18) + pad(hot.decision.value, 24) + clean.decision.value)

assert table["info"] == ("allow_with_warnings", "allow")
assert table["warning"] == ("allow_with_warnings", "allow")
assert table["error"] == ("block", "allow") and table["critical"] == ("block", "allow")
print()
print("三种取值之外没有第四条路：allow_with_warnings 只是「可以继续，但请看一眼」。")
'''
        ),
        markdown(
            '''
## 小结

- **九步是一条直线**：规则集就绪 → 上下文规范化 → 范围匹配 → 跳过写原因 → 证据门禁 →
  checker 分派 → 违规稳定排序 → 审批标记 → 三值判定；每一步的输入输出都能单独复现。
- **确定性落在三处实现细节**：规则集身份与加载顺序无关（loader 按来源路径排序后再算 sha256）、
  上下文先规范化再比较、违规按 `sort_key` 排序。"相同输入得到相同结论"说的就是这三件事。
- **skipped ≠ 通过**：只提供上下文的调用路径会把证据类规则写进 `skipped_rules` 并写明
  "需要验证器证据"，`matched_rules` 只包含真正判过的规则；同一批里的 PASS 也抵消不了 critical 阻断。
- **两条失败关闭旁路各管一半**：证据缺失（验证器不可用 / 未覆盖）由引擎转成 critical 阻断；
  高风险动作由 `requires_approval` 转成 `block + RequiredAction.APPROVAL`，与有没有违规无关。
- **引擎不认识代码，也不认识 Agent**：它只读 `PolicyContext` 与 `EvidenceBundle`，
  不读文件、不调工具、不调模型，也不知道 dsh 的存在；证据的生产属于 Phase 5 验证器层。

接下来按兴趣往下走：`02-dsh-Hook-内部流程.ipynb`（同一条判定在真实 Agent 前置钩子里怎么被调用）、
`05-代码验证器.ipynb`（证据怎么产出并绑定到规则上）、`09-能不能成为规则.ipynb`（一段要求够不够格成为规则）。
'''
        ),
    ),
)
