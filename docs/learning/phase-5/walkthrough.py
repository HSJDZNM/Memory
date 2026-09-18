"""Phase 5 学习手册的纯 Python 版本（由 tools/build_learning_notebook.py 生成）。

notebook 里每一段代码都按顺序出现在下面；直接运行本文件即可复现全部输出：

    python docs/learning/phase-5/walkthrough.py

内容改动请修改 tools/build_learning_notebook.py 后重新生成，不要直接编辑本文件。
"""

# ----------------------------------------------------------------------------
# # Phase 5 学习手册：代码验证器（Code Validators）
#
# 这份 notebook 用**实际运行的代码**解释 Phase 5：怎样把"模型说这段代码合规"换成
# "确定性证据说这段代码合规"。它不引入新代码，只调用仓库里已经通过测试的模块，
# 因此每一段输出都可以自己重跑验证。
#
# ## Phase 5 要证明的事
#
#     Code → Source（哈希）→ AST（import / 调用 / 定义）→ Dependency（解析 + 组件）
#          → Docstring / Lint / Type / Tests（外部工具探针）
#          → Evidence（带验证器 ID/版本、规则 ID、文件行列、工具退出码、配置哈希）
#          → Policy Engine（allow / allow_with_warnings / block）
#
# 一句话：**验证器只产证据，判定仍由 Policy Engine 做**；关键验证器没跑成就失败关闭，
# "解析失败"绝不等于"没有依赖"。
#
# ## 阅读路线
#
# | 小节 | 回答的问题 |
# | --- | --- |
# | 0 | 跑这份 notebook 需要什么前提 |
# | 1 | 验证器注册表与项目档案里有什么，为什么它们是数据 |
# | 2 | 标准库 ast 能拿到哪些事实（import / 别名 / 动态 import / 定义） |
# | 3 | 依赖图怎样把 import 解析成"项目内 / 标准库 / 外部包 / 无法解析" |
# | 4 | 证据怎样变成 violation：ARCH-001 由 AST 证据判定并给出行号 |
# | 5 | 哪些情况失败关闭（语法错误 / 动态 import / 缺工具 / checker 无验证器） |
# | 6 | 外部工具适配器怎样区分缺失、版本不符、超时、崩溃、配置错误、输出非法 |
# | 7 | 测试验证器怎样选择最小相关测试，相关性不足时怎样升级 |
# | 8 | 命令行与退出码；这一阶段明确不做什么 |
#
# 每个代码单元后面都有小结，说明"这段输出意味着什么"。
# 这份 notebook **不联网、不调用 LLM、不改仓库真实文件**：演示工作区从
# `tests/fixtures/validators/project` 复制到 `.tmp/learning/phase-5-<uuid>/` 下，
# 跑完用 `python tools/cleanup.py` 清理即可。
# ----------------------------------------------------------------------------

import shutil
import sys
import uuid
from pathlib import Path

# 手册要能从两个工作目录跑：仓库根目录，以及 docs/learning/phase-5/。
_candidate = Path.cwd()
REPO_ROOT = _candidate
while not (REPO_ROOT / "src" / "policy").is_dir() and REPO_ROOT != REPO_ROOT.parent:
    REPO_ROOT = REPO_ROOT.parent
for _path in (REPO_ROOT / "src", REPO_ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

FIXTURE_PROJECT = REPO_ROOT / "tests" / "fixtures" / "validators" / "project"
WORKSPACE = REPO_ROOT / ".tmp" / "learning" / ("phase-5-" + uuid.uuid4().hex[:8])
shutil.copytree(FIXTURE_PROJECT, WORKSPACE)
print("仓库根目录:", REPO_ROOT.name)
print("演示工作区:", WORKSPACE.relative_to(REPO_ROOT).as_posix())
print("夹具项目里的文件:", sorted(p.name for p in (WORKSPACE / "src" / "shop").glob("*.py"))[:4], "...")


# 表格对齐用的小工具：中文（全角）字符在等宽字体里占 2 列，而 f"{文本:<10}"
# 数的是"字符个数"——中英混排时列会被挤歪。按显示宽度补空格才是对的。
import unicodedata


def display_width(text):
    """文本在等宽字体里占多少列：全角/宽字符算 2 列，其余算 1 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(text))


def pad(text, width, align="left"):
    """按显示宽度把文本补齐到 width 列，让每一列都从同一个位置开始。"""
    text = str(text)
    blanks = " " * max(0, width - display_width(text))
    if align == "right":
        return blanks + text
    if align == "center":
        left = len(blanks) // 2
        return blanks[:left] + text + blanks[left:]
    return text + blanks

# ----------------------------------------------------------------------------
# ## 1. 验证器注册表与项目档案：谁能产生证据是数据决定的
#
# `validation/validators.yaml` 声明"哪个验证器、在哪个阶段、为哪些 checker、用哪个工具、
# 版本区间与配置文件"；`validation/project.yaml` 声明"哪种路径是什么语言、哪个文件属于哪个组件"。
# 代码只负责解释数据——**新增语言 = 加一个 rule pack + 一个 Adapter，核心流水线不改**。
# ----------------------------------------------------------------------------

from validators.registry import load_config

CONFIG = load_config(root=REPO_ROOT)
REGISTRY = CONFIG.registry

print("阶段顺序:", " → ".join(REGISTRY.stages))
print()
print(pad("checker", 22) + pad("提供证据的验证器", 26) + "备注")
print("-" * 76)
checkers = REGISTRY.checkers_for_language("python")
registry_facts = {"stages": list(REGISTRY.stages), "checkers": {}, "validators": {}}
for checker, owners in checkers.items():
    registry_facts["checkers"][checker] = list(owners)
    spec = REGISTRY.spec(owners[0])
    note = "内置（标准库）" if spec.kind.value == "builtin" else "外部工具"
    print(pad(checker, 22) + pad(",".join(owners), 26) + note)
print()
for spec in REGISTRY.validators:
    registry_facts["validators"][spec.id] = {
        "stage": spec.stage,
        "critical": spec.critical,
        "checkers": list(spec.checkers),
    }
print("注册表里的验证器:", ", ".join(item.id for item in REGISTRY.validators))
print("提示: 规则体与 checker 必须一致；未知 checker 或未实现的验证器 id 在加载阶段就报错。")

# ----------------------------------------------------------------------------
# ## 2. 标准库 ast：先把"代码里写了什么"变成事实
#
# `validators.python_ast.parse_module` 只解析、不执行：import（含别名与相对导入）、
# 动态 import（常量参数解析成模块名，非常量参数留成"无法解析"）、调用链与定义（含 docstring）。
# ----------------------------------------------------------------------------

from validators.python_ast import parse_module

BAD_CONTROLLER = "src/shop/order_controller_bad.py"
DYNAMIC = "src/shop/dynamic_dependency.py"

bad_facts = parse_module((WORKSPACE / BAD_CONTROLLER).read_text(encoding="utf-8"))
dynamic_facts = parse_module((WORKSPACE / DYNAMIC).read_text(encoding="utf-8"))

ast_facts = {
    "imports": [(item.module, item.alias, item.kind, item.line) for item in bad_facts.imports],
    "definitions": [(item.kind, item.qualified, item.docstring) for item in bad_facts.definitions],
    "dynamic": [(item.module, item.constant) for item in dynamic_facts.dynamic_unresolved],
}
print("被验证文件:", BAD_CONTROLLER)
print(pad("import 模块", 30) + pad("别名", 8) + pad("形态", 14) + "行")
print("-" * 60)
for module, alias, kind, line in ast_facts["imports"]:
    print(pad(module, 30) + pad(alias or "-", 8) + pad(kind, 14) + str(line))
print()
print("定义:", ", ".join(item[1] for item in ast_facts["definitions"]))
print("动态 import（无法静态解析）:", ast_facts["dynamic"])
print("小结：import 与行号是后面所有依赖判定的原始事实；动态 import 不会消失，它会变成失败关闭的理由。")

# ----------------------------------------------------------------------------
# ## 3. 依赖图：把 import 解析成"项目内 / 标准库 / 外部包 / 无法解析"
#
# `validators.depgraph` 按项目档案的 `python_roots` 建模块索引，再把 import 解析到具体文件；
# 项目内文件再按组件映射（`validation/project.yaml`）得到参与规则匹配的名字（repository / service …）。
# **解析失败必须与"外部包"分开**：前者是失败关闭，后者只是"项目外的依赖"。
# ----------------------------------------------------------------------------

from validators.depgraph import build_dependencies, build_module_index

INDEX = build_module_index(WORKSPACE, CONFIG.project)
dependencies = build_dependencies(
    bad_facts,
    target_path=BAD_CONTROLLER,
    profile=CONFIG.project,
    index=INDEX,
    validator="py.depgraph@1.0",
)

dependency_facts = {
    "indexed": len(INDEX.modules),
    "facts": [
        (item.name, item.module, item.kind.value, item.resolution.value, item.line)
        for item in dependencies.dependencies
    ],
    "unresolved": [item.reason for item in dependencies.unresolved],
    "nodes": list(dependencies.nodes),
}
print("索引到的模块数:", dependency_facts["indexed"])
print(pad("依赖名", 14) + pad("模块", 30) + pad("形态", 14) + pad("解析", 12) + "行")
print("-" * 80)
for name, module, kind, resolution, line in dependency_facts["facts"]:
    print(pad(name, 14) + pad(module or "-", 30) + pad(kind, 14) + pad(resolution, 12) + str(line))
print()
print("依赖图节点:", ", ".join(dependency_facts["nodes"]))
print("未解析项:", dependency_facts["unresolved"] or "无")
print("小结：examples.bad_repository 被解析成组件 repository —— 规则匹配的是组件名，不是文件名。")

# ----------------------------------------------------------------------------
# ## 4. 证据 → 判定：ARCH-001 完全由 AST / 依赖图证据判定
#
# 验证器把证据交给 `policy.engine.evaluate(..., evidence=...)`；引擎按规则的 checker 分派，
# 把证据变成 violation，并把文件与行号一起写进决策载荷。**严重级别来自规则，不来自证据。**
# ----------------------------------------------------------------------------

from policy.context import build_context
from policy.engine import evaluate
from policy.loader import load_rule_set
from validators.pipeline import PipelineRequest, run_pipeline

RULES = load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)


def decide(target, *, layer="controller", operation=None, workspace=None):
    """跑一次流水线并判定：与 CLI 用的是同一条链路。"""

    workspace = WORKSPACE if workspace is None else workspace
    context = build_context(
        {
            "request_id": "learn-phase-5",
            "file": target,
            "layer": layer,
            "language": "python",
            "operation": operation,
        },
        repo_root=workspace,
    )
    report = run_pipeline(
        PipelineRequest(target=target, workspace=workspace, context=context, rules=RULES),
        config=CONFIG,
    )
    return report, evaluate(RULES, context, evidence=report.bundle)


bad_report, bad_result = decide(BAD_CONTROLLER)
good_report, good_result = decide("src/shop/order_controller.py")

decision_facts = {
    "bad_decision": bad_result.decision.value,
    "good_decision": good_result.decision.value,
    "matched": list(bad_result.matched_rules),
    "served_checkers": list(bad_report.served_checkers),
    "violations": [
        {
            "rule_id": item.rule_id,
            "severity": item.severity.value,
            "file": item.evidence.file,
            "line": item.evidence.line,
            "value": item.evidence.value,
        }
        for item in bad_result.violations
    ],
}
print("反例决策:", decision_facts["bad_decision"], "| 正例决策:", decision_facts["good_decision"])
print("参与判断的规则:", ", ".join(decision_facts["matched"]))
print("本次拿到证据的 checker:", ", ".join(decision_facts["served_checkers"]))
print()
for item in bad_result.violations:
    print("[" + item.severity.value + "]", item.canonical_id, item.evidence.file + ":" + str(item.evidence.line))
    print("  reason:", item.message)
    print("  evidence:", item.evidence.detail)
print()
print("正例的依赖:", [fact.name for fact in good_report.dependencies])
print("小结：依赖不是调用方声明的，而是从源码解析出来的——行号也在证据里。")

# ----------------------------------------------------------------------------
# ## 5. 失败关闭：拿不到证据就不判定通过
#
# 关键验证器缺失、版本不符、超时、崩溃、配置错误、输出非法，以及"没有任何验证器为某个
# checker 提供证据"，都会让需要它的规则以 `critical` 阻断。语法错误、动态 import 目标不是常量、
# 项目内模块解析失败同样阻断：**解析不了的文件不能被判定为"没有依赖问题"。**
# ----------------------------------------------------------------------------

dynamic_report, dynamic_result = decide(DYNAMIC)
syntax_report, syntax_result = decide("src/shop/broken_syntax.py")
narrow_report, narrow_result = decide(BAD_CONTROLLER)

from policy.engine import evaluate as _evaluate
from validators.pipeline import PipelineRequest as _Request
from validators.pipeline import run_pipeline as _run

# "只跑 py.source"：依赖与 docstring 的 checker 没有验证器 → 失败关闭
_context = build_context(
    {"request_id": "learn-phase-5-narrow", "file": BAD_CONTROLLER, "layer": "controller", "language": "python"},
    repo_root=WORKSPACE,
)
narrow_report = _run(
    _Request(
        target=BAD_CONTROLLER,
        workspace=WORKSPACE,
        context=_context,
        rules=RULES,
        only=("py.source",),
    ),
    config=CONFIG,
)
narrow_result = _evaluate(RULES, _context, evidence=narrow_report.bundle)

fail_closed_facts = {
    "dynamic": {
        "decision": dynamic_result.decision.value,
        "blockers": [(item.validator, item.status.value, item.reason) for item in dynamic_report.blockers],
    },
    "syntax": {
        "decision": syntax_result.decision.value,
        "blockers": [(item.validator, item.status.value, item.reason) for item in syntax_report.blockers],
    },
    "narrow": {
        "decision": narrow_result.decision.value,
        "blockers": [(item.validator, item.status.value) for item in narrow_report.blockers],
    },
}
print(pad("场景", 18) + pad("决策", 8) + "阻断点")
print("-" * 90)
for name, item in fail_closed_facts.items():
    blockers = "; ".join(entry[0] + "(" + entry[1] + ")" for entry in item["blockers"])
    print(pad(name, 18) + pad(item["decision"], 8) + blockers)
print()
print("动态 import 的理由:", fail_closed_facts["dynamic"]["blockers"][0][2][:60], "...")
print("语法错误的理由:", fail_closed_facts["syntax"]["blockers"][0][2][:60], "...")
print("阻断时的严重级别:", sorted({item.severity.value for item in dynamic_result.violations}))
print("小结：失败关闭不是“报个警告”，它是 critical 级别的阻断，其他 PASS 抵消不了。")

# ----------------------------------------------------------------------------
# ## 6. 外部工具适配器：缺失、版本不符、超时、崩溃、配置错误、输出非法的区别
#
# 外部工具的输出是**不可信数据**：参数只能来自声明模板 + 受校验的替换值，环境变量走白名单，
# 超时要终止整棵进程树，输出先脱敏再进证据。这里用假工具（`tests/fixtures/validators/tools/fake_tool.py`）
# 演示各种失效状态，不需要真的装坏工具。
# ----------------------------------------------------------------------------

import tempfile
from pathlib import Path as _Path
from policy.evidence import ValidatorStatus
from validators.adapters.base import build_argv, probe_tool, run_tool

FAKE_TOOL = REPO_ROOT / "tests" / "fixtures" / "validators" / "tools" / "fake_tool.py"
TOOL_TMP = WORKSPACE / ".tool-tmp"
TOOL_TMP.mkdir(parents=True, exist_ok=True)


def fake_spec(behaviour, *, timeout_ms=2000):
    from policy.evidence import ValidatorKind
    from validators.models import ToolSpec, ValidatorSpec

    return ValidatorSpec(
        id="tool.ruff",
        version="1.0",
        kind=ValidatorKind.EXTERNAL,
        stage="lint",
        checkers=("style_lint",),
        critical=True,
        timeout_ms=timeout_ms,
        tool=ToolSpec(
            command=("{python}", str(FAKE_TOOL), "ruff", behaviour),
            version_args=("--version",),
            version_pattern=r"ruff ([0-9][0-9A-Za-z.\-+]*)",
            version_requirement=">=0.6,<1",
            argv=("check", "--output-format=json", "{paths}"),
        ),
    )


def classify(behaviour, *, timeout_ms=2000):
    spec = fake_spec(behaviour, timeout_ms=timeout_ms)
    probe = probe_tool(
        spec.tool,
        timeout_ms=timeout_ms,
        max_output_bytes=65536,
        workspace=WORKSPACE,
        tmp_dir=TOOL_TMP,
    )
    if not probe.ok:
        return probe.status.value, probe.reason[:40]
    argv = build_argv(
        spec.tool,
        probe,
        python=sys.executable,
        workspace=WORKSPACE,
        config=None,
        paths=(BAD_CONTROLLER,),
    )
    run = run_tool(
        spec.tool,
        probe,
        argv,
        workspace=WORKSPACE,
        tmp_dir=TOOL_TMP,
        timeout_ms=timeout_ms,
        max_output_bytes=1024,
        findings_exit_codes=(1,),
    )
    return run.status.value, (run.reason or ("退出码 " + str(run.exit_code)))[:44]


tool_facts = {"classification": {}}
print(pad("假工具行为", 16) + pad("状态", 18) + "说明")
print("-" * 90)
# 注意：empty 在这里是 ok（进程正常结束、退出码 0）；把"空输出"判成 output_invalid
# 是**适配器映射阶段**的决定（JSON 解析不了就不能当作"没有诊断"），而不是进程层的判断。
for behaviour in ("ok", "findings", "empty", "garbage", "config_error", "crash", "slow", "old"):
    status, reason = classify(behaviour)
    tool_facts["classification"][behaviour] = status
    print(pad(behaviour, 16) + pad(status, 18) + reason)
print()
missing = probe_tool(
    fake_spec("ok").tool,
    timeout_ms=1000,
    max_output_bytes=1024,
    workspace=WORKSPACE,
    tmp_dir=TOOL_TMP,
)
print("版本探测（正常）:", missing.status.value, missing.version)
print("小结：每一种失效都落在显式状态上；“工具没装”永远不会被当成“没有问题”。")

# ----------------------------------------------------------------------------
# ## 7. 测试验证器：按变更集选择最小相关测试
#
# `validation/test-layout.yaml` 声明生产文件与测试文件的对应关系与升级层级：
# `related（同名测试）→ package（同包测试）→ suite（整个套件）`。
# 改了生产代码却没有对应测试，是 `TESTING-001` 的违规；选中的测试跑失败了，是 `TESTING-002`。
# ----------------------------------------------------------------------------

from validators.selection import select_tests

def selection_rows(target, changed):
    selection = select_tests(
        target_path=target,
        changed_files=tuple(changed),
        layout=CONFIG.layout,
        workspace=WORKSPACE,
        max_nodeids=CONFIG.layout.limits.max_nodeids,
    )
    return selection

selection_facts = {"levels": {}, "missing": None}
print(pad("目标文件", 34) + pad("变更集", 34) + pad("层级", 10) + "选中的测试")
print("-" * 100)
for target, changed in (
    ("src/shop/order_service.py", ("src/shop/order_service.py",)),
    ("src/shop/order_repository.py", ("src/shop/order_repository.py",)),
):
    selection = selection_rows(target, changed)
    selection_facts["levels"][target] = selection.level
    print(
        pad(target, 34)
        + pad(changed[0], 34)
        + pad(selection.level, 10)
        + (",".join(selection.nodeids) or "<无>")
    )

import shutil as _shutil

NO_TESTS = WORKSPACE / "no-tests-copy"
_shutil.rmtree(NO_TESTS, ignore_errors=True)
_shutil.copytree(WORKSPACE / "src", NO_TESTS / "src")
selection = select_tests(
    target_path="src/shop/order_service.py",
    changed_files=("src/shop/order_service.py",),
    layout=CONFIG.layout,
    workspace=NO_TESTS,
    max_nodeids=10,
)
selection_facts["missing"] = list(selection.missing)
print()
print("没有任何测试文件的工作区 → missing:", selection_facts["missing"], "| 原因:", selection.reason)
print("小结：相关测试会被真的运行（Phase 5 的闭环里有通过/失败两种重放）；找不到测试是显式证据。")

# ----------------------------------------------------------------------------
# ## 8. 命令行与退出码
#
# - `python -m validators.cli registry / probe / check / pipeline`：注册表事实、工具探针、只产证据、证据+判定；
# - `python -m policy.check <file> --layer <layer>`：默认就走验证器流水线；
# - 退出码：`0` 通过、`1` 违规或失败关闭、`2` 配置或用法错误（注册表不可用、路径越界、未知验证器）。
# ----------------------------------------------------------------------------

import json
import os
import subprocess


def run_validator_cli(*args, module="validators.cli"):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return completed


cli_codes = {}
registry_run = run_validator_cli("registry", "--json")
cli_codes["registry"] = registry_run.returncode
print("退出码:", registry_run.returncode, "| 注册表里的验证器:", len(json.loads(registry_run.stdout)["validators"]))

narrow = ("--validators", "py.source,py.ast,py.depgraph")
# policy.check 没有子命令（验证器那条链路直接就是默认行为），validators.cli 才有 check/pipeline。
bad_run = run_validator_cli(BAD_CONTROLLER, "--layer", "controller", "--workspace", "tests/fixtures/validators/project", *narrow, module="policy.check")
cli_codes["bad"] = bad_run.returncode
print("退出码:", bad_run.returncode, "| 反例决策:", json.loads(bad_run.stdout)["result"]["decision"] if bad_run.stdout.startswith("{") else "block")

good_run = run_validator_cli("src/shop/order_controller.py", "--layer", "controller", "--workspace", "tests/fixtures/validators/project", *narrow, module="policy.check")
cli_codes["good"] = good_run.returncode
# 正例在这里也是 1：把验证器限制成 py.* 之后，style_lint 没有任何验证器提供证据 →
# 引擎按失败关闭阻断。这是 Phase 5 的核心语义：**"少跑一个验证器"不等于"少一条规则"**。
print("退出码:", good_run.returncode, "| 正例被限制成 py.* 后仍然阻断（style_lint 没有证据）:", "关键验证器不可用" in good_run.stdout)

uncovered = run_validator_cli("check", BAD_CONTROLLER, "--layer", "controller", "--workspace", "tests/fixtures/validators/project", "--validators", "py.source")
cli_codes["uncovered"] = uncovered.returncode
print("退出码:", uncovered.returncode, "| 只跑 py.source 时依赖判定没有证据（失败关闭）")

escape = run_validator_cli("check", "../outside.py", "--layer", "controller", "--workspace", "tests/fixtures/validators/project")
cli_codes["escape"] = escape.returncode
print("退出码:", escape.returncode, "| 路径越界:", escape.stderr.strip().splitlines()[-1][:60] if escape.stderr.strip() else "")
print("小结：证据不足、路径越界、注册表读不到都不会给出“通过”。")

# ----------------------------------------------------------------------------
# ## 9. 边界与不做的事
#
# - **不做判定**：验证器只产证据，allow / block 由 Policy Engine 决定；证据不写进决策协议（协议仍是 1.0）；
# - **不做类型检查的默认启用**：mypy 端口与失败语义已就位，但仓库没有启用类型规则——
#   本机与 CI 都没装 mypy，启用它会让所有 Python 文件在缺工具时一次性判红，这是数据决定的事；
# - **不做多语言**：标准库 ast 只覆盖 Python；新增语言 = 新增 Adapter + rule pack（核心流水线无语言分支）；
# - **不做真正的沙箱**：外部工具在本机进程里跑，隔离靠白名单环境变量、参数 allowlist、
#   超时终止进程树与输出脱敏；操作系统的文件系统 / 网络隔离属于运行时的沙箱，不在本阶段；
# - **不进 dsh Hook 的默认链路**：Phase 2 的 Hook 只提供上下文，证据类 checker 的规则会记进
#   `skipped_rules` 并写明"需要验证器证据"——这是显式记录，不是静默放行（把验证器接进 Hook 属于 Phase 6）。
#
# 相关文件：
#
# - 阶段设计与实施记录：`docs/engineering-policy-platform/phases/phase-5-code-validators.md`
# - 证据协议与 checker 分派：`src/policy/evidence.py`、`src/policy/checkers.py`
# - 验证器实现：`src/validators/`（python_ast / depgraph / docstrings / selection / adapters / pipeline / cli）
# - 数据：`validation/validators.yaml`、`validation/project.yaml`、`validation/test-layout.yaml`、工具配置
# - 规则包：`policies/coding/`（DOC-001、STYLE-001、STYLE-002）、`policies/testing/`（TESTING-001、TESTING-002）
# - 夹具与假工具：`tests/fixtures/validators/`
# - 闭环结论：`python tools/validator_loop.py` → `.tmp/artifacts/phase-5-validators-result.json`
# ----------------------------------------------------------------------------
