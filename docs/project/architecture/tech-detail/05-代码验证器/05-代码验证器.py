"""代码验证器：只产证据，不判定：tech-detail 讲解 notebook 的纯 Python 版本。

由 docs/project/architecture/tech-detail/notebooks/build_notebooks.py 生成，内容与同名的
.ipynb 逐字相同（那份里每段代码也是一个单元）。直接运行本文件即可复现全部输出：

    python docs/project/architecture/tech-detail/notebooks/05-代码验证器.py

内容改动请修改 nb_cells/ 下对应的内容源后重新生成，不要直接编辑本文件。
"""

# ----------------------------------------------------------------------------
# # 05 代码验证器：只产证据，不判定
#
# 这份 notebook 配合同名图 `05-代码验证器.drawio`。图上的九步是一条直线：
#
#     变更集 → 读取 + 内容哈希 → 验证器注册表 → 最小相关测试
#            → 标准库 AST → 外部工具探针 → 按模板调用 → 证据包 → 交回判定核心
#
# **这张图要讲清的一件事**：验证器只回答"代码里有哪些事实"，不回答"这段代码能不能过"。
# allow / block 仍然只有 `policy.engine.evaluate` 一个出口——所以下面每一节都把
# "拿到证据"和"做出判定"分开打印。
#
# 六节代码各自回答一个问题：
#
# | 小节 | 回答的问题 |
# | --- | --- |
# | 1 | 谁能产生证据？为什么这件事写在 YAML 里，而不是写在代码里 |
# | 2 | 为什么"解析失败"不等于"没有依赖" |
# | 3 | 依赖图怎样把 import 变成参与规则匹配的组件名，还带行号 |
# | 4 | 外部工具怎样被发现、按模板调用，证据里到底有什么 |
# | 5 | 工具缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法会怎样 |
# | 6 | 关键验证器没跑成时，谁被阻断、别的验证器能不能"抵消"它 |
#
# **预备知识**：会读 Python 的 `import` 与函数调用就够了。演示工作区是从
# `tests/fixtures/validators/project` 复制到 `.tmp/tech-detail/05/` 下的一份副本，
# 仓库里的真实文件一个都不会被改动；所有临时产物都写在那个目录里。
# ----------------------------------------------------------------------------

# 先找到仓库根目录：notebook 可能从仓库根启动，也可能从本目录启动，两种都要能跑。
import shutil
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

# 本 notebook 独占的临时目录：只在这里写文件。
TEMP = REPO_ROOT / ".tmp" / "tech-detail" / "05"
TEMP.mkdir(parents=True, exist_ok=True)

# 演示工作区：每轮从夹具项目重新复制一份，上一轮的残留不会影响这一轮。
WORKSPACE = TEMP / "shop"
shutil.rmtree(WORKSPACE, ignore_errors=True)
shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "validators" / "project", WORKSPACE)

print("仓库根目录:", REPO_ROOT.name)
print("本笔记本的临时目录:", TEMP.relative_to(REPO_ROOT).as_posix())
print("演示工作区:", WORKSPACE.relative_to(REPO_ROOT).as_posix())
print("Python:", sys.version.split()[0])
print("夹具里的生产文件:", ", ".join(sorted(path.name for path in (WORKSPACE / "src" / "shop").glob("*.py"))))

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
# ## 1. 谁能产生证据，是数据决定的
#
# `validation/validators.yaml` 声明四件事：**哪个验证器**、在**哪个阶段**跑、为**哪些 checker**
# 提供证据、用**哪个外部工具与哪份配置**。代码只负责解释这份数据：
#
# - 新增一门语言 = 加一个 rule pack + 一个 Adapter，核心流水线不改一行；
# - 注册表里出现代码没实现的验证器 id，**加载阶段就报错**——不是"这次少跑一个"；
# - `critical: true` 的验证器只要没跑成，需要它的规则就以 critical 阻断。
#
# **输出怎么读**：第一张表是"checker → 谁为它产证据"（checker 是规则体的名字，
# 比如 `style_lint` 就是"外部 linter 的诊断"）；第二段是同一个文件的内容哈希与静态事实。
# 证据必须绑定到**具体一份内容**上——同名文件改了内容，旧证据就不该再被复用。
# ----------------------------------------------------------------------------

# 注册表是数据；证据的第一块砖是"读到的那份内容"。
from validators.pipeline import KNOWN_VALIDATOR_IDS
from validators.python_ast import parse_module
from validators.registry import load_config
from validators.source import read_source

CONFIG = load_config(root=REPO_ROOT)
REGISTRY = CONFIG.registry

print("阶段顺序:", " → ".join(REGISTRY.stages))
print("默认上限: 单个源文件", REGISTRY.defaults.max_source_bytes, "字节 |",
      "单次证据上限", REGISTRY.defaults.max_evidence, "条 |",
      "并行度", REGISTRY.defaults.max_parallel)
print()
print(pad("checker", 22) + pad("为它提供证据的验证器", 26) + "形态")
print("-" * 76)
checkers = REGISTRY.checkers_for_language("python")
for checker in sorted(checkers):
    owners = checkers[checker]
    spec = REGISTRY.spec(owners[0])
    kind = "内置（标准库）" if spec.kind.value == "builtin" else "外部工具"
    print(pad(checker, 22) + pad(",".join(owners), 26) + kind)
print()
print("注册表里的验证器:", ", ".join(spec.id for spec in REGISTRY.validators))

assert tuple(REGISTRY.stages) == ("source", "ast", "dependency", "docstring", "lint", "type", "tests")
assert {spec.id for spec in REGISTRY.validators} == set(KNOWN_VALIDATOR_IDS), "注册表声明了实现里没有的验证器"
assert all(spec.critical for spec in REGISTRY.validators), "每个验证器都声明了 critical（失败关闭）"
assert set(checkers) == {
    "failing_tests", "forbidden_dependency", "missing_docstring",
    "missing_tests", "style_lint", "type_check",
}, sorted(checkers)

TARGET = "src/shop/order_controller_bad.py"
source = read_source(TARGET, workspace=WORKSPACE, language="python",
                     max_bytes=REGISTRY.defaults.max_source_bytes)
facts = parse_module(source.text)

print()
print("被验证文件:", source.digest.file, "| 语言:", source.digest.language)
print("内容哈希:", source.digest.sha256, "| 行数:", source.digest.lines, "| 字节:", source.digest.bytes)
print()
print(pad("import 的模块", 30) + pad("别名", 8) + pad("形态", 14) + "行")
print("-" * 62)
for item in facts.imports:
    print(pad(item.module or "<动态>", 30) + pad(item.alias or "-", 8) + pad(item.kind, 14) + str(item.line))
print()
print("模块 docstring:", "有" if facts.module_docstring else "没有")
print("定义:", ", ".join(item.qualified for item in facts.definitions))
print("语法错误:", "无" if facts.syntax_error is None else facts.syntax_error.message)

assert source.digest.sha256.startswith("sha256:") and len(source.digest.sha256) > 20
assert any(item.module == "shop.order_repository" for item in facts.imports)
assert facts.syntax_error is None

# 动态 import 不会被丢掉：它只是"暂时没有目标"，这一点在第 2 节会变成阻断理由。
dynamic = parse_module((WORKSPACE / "src" / "shop" / "dynamic_dependency.py").read_text(encoding="utf-8"))
print()
print("动态 import（无法静态确定目标）:",
      [(item.expression, item.constant, item.line) for item in dynamic.dynamic_unresolved])
assert dynamic.dynamic_unresolved
assert all(item.module == "" and not item.constant for item in dynamic.dynamic_unresolved)
print("小结：import、别名、行号、docstring 都是静态事实；动态 import 也是一条事实，不是没有依赖。")

# ----------------------------------------------------------------------------
# ## 2. "解析失败"不等于"没有依赖"
#
# 有三种输入会让 `py.ast` / `py.depgraph` 直接报"拿不到事实"：
#
# 1. **语法错误**——文件根本解析不了；
# 2. **动态 import 的目标不是常量字符串**——`importlib.import_module(name)` 要到运行时才知道目标；
# 3. **项目内模块解析不到具体文件**——看起来是项目内模块，索引里却没有它。
#
# 三种都必须**阻断**。理由很直白：如果把"解析不了"当成"没有依赖"，那么只要把违规依赖写成
# 一行 `importlib.import_module("shop.order_repository")`，ARCH-001 就永远查不出来。
#
# **输出怎么读**：下面每一行都是 `decision = block`。"阻断点"记录的是**哪个验证器没跑成**、
# 状态是什么、它让哪些 checker 无法判定；"违规"才是给规则用的结论。
# 两者分属证据层与判定层——这正是这张图的核心设计。
# ----------------------------------------------------------------------------

# 三种"解析失败"都必须阻断；判定走 Policy Engine 那一条路。
from policy.context import build_context
from policy.engine import evaluate
from policy.evidence import FAIL_CLOSED_STATUSES
from policy.loader import load_rule_set
from validators.pipeline import PipelineRequest, run_pipeline

RULES = load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)


def decide(target, *, layer="controller", operation=None, workspace=None, only=(), changed=(), config=None):
    """跑一次真实流水线并判定：证据来自验证器，allow / block 来自 Policy Engine。"""

    workspace = WORKSPACE if workspace is None else workspace
    policy_context = build_context(
        {
            "request_id": "tech-detail-05",
            "file": target,
            "layer": layer,
            "language": "python",
            "operation": operation,
        },
        repo_root=workspace,
    )
    report = run_pipeline(
        PipelineRequest(
            target=target,
            workspace=workspace,
            context=policy_context,
            rules=RULES,
            only=only,
            changed_files=changed,
        ),
        config=CONFIG if config is None else config,
    )
    return report, evaluate(RULES, policy_context, evidence=report.bundle)


CASES = (
    ("src/shop/broken_syntax.py", "语法错误"),
    ("src/shop/dynamic_dependency.py", "动态 import 目标不是常量字符串"),
    ("src/shop/unresolved_dependency.py", "项目内模块解析不到文件"),
)
outcomes = {}
for target, label in CASES:
    report, result = decide(target)
    outcomes[target] = (report, result)
    blocker = report.blockers[0]
    print("场景:", label, "→", target)
    print("  决策:", result.decision.value,
          "| 阻断点:", blocker.validator, "/", blocker.status.value,
          "| 无法判定的 checker:", ",".join(blocker.checkers))
    print("  理由:", blocker.reason[:96])
    print()

assert {result.decision.value for _, result in outcomes.values()} == {"block"}
for target, (report, result) in outcomes.items():
    assert report.blockers, target
    assert all(blocker.status in FAIL_CLOSED_STATUSES for blocker in report.blockers), target
    assert any(item.severity.value == "critical" for item in result.violations), target
    assert not set(report.served_checkers).intersection(report.blockers[0].checkers), target

reasons = {target: report.blockers[0].reason for target, (report, _) in outcomes.items()}
assert "语法错误" in reasons["src/shop/broken_syntax.py"]
assert "动态 import 的目标不是常量字符串" in reasons["src/shop/dynamic_dependency.py"]
assert "索引里没有" in reasons["src/shop/unresolved_dependency.py"]
assert "解析不了的文件不能被判定为没有依赖问题" in reasons["src/shop/broken_syntax.py"]
print("三种解析失败都落成 critical 阻断；同一批里其他验证器拿到的 PASS 抵消不了它们。")

# ----------------------------------------------------------------------------
# ## 3. 从 import 到"组件名"，再到最小相关测试
#
# 依赖图把每条 import 解析成四种结果之一：`internal`（项目内文件）、`stdlib`（标准库）、
# `external`（外部包）、`unresolved`（解析不了，见上一节）。只有 `internal` 会被翻译成
# **组件名**（`validation/project.yaml` 里的 repository / service / controller …）——
# 规则匹配的是组件名而不是文件名，所以"换个文件名"绕不过 ARCH-001。
#
# 同一节还要看**测试选择**：`validation/test-layout.yaml` 声明了从窄到宽的升级层级
# `related`（同名测试）→ `package`（同包测试）→ `suite`（整个套件）。
#
# **输出怎么读**：依赖表里"依赖名"一列就是参与规则匹配的名字，最后两列是解析结果与行号；
# 选中的测试会被**真的跑起来**——`tool.pytest` 退出码 1 时，每个失败用例都会变成一条
# `failing_tests` 证据（消息里带用例名）。改了生产代码却没有对应测试，则是 `missing_tests` 证据。
# ----------------------------------------------------------------------------

# 依赖图 → 组件名 → ARCH-001；变更集 → 最小相关测试 → 真的跑起来。
from validators.depgraph import build_dependencies, build_module_index
from validators.selection import select_tests

INDEX = build_module_index(WORKSPACE, CONFIG.project)
BAD = "src/shop/order_controller_bad.py"
bad_source = read_source(BAD, workspace=WORKSPACE, language="python",
                         max_bytes=REGISTRY.defaults.max_source_bytes)
dependencies = build_dependencies(
    parse_module(bad_source.text),
    target_path=BAD,
    profile=CONFIG.project,
    index=INDEX,
    validator="py.depgraph@1.0",
)
rows = [
    (item.name, item.module or "-", item.kind.value, item.resolution.value, item.line)
    for item in dependencies.dependencies
]
print("索引到的模块数:", len(INDEX.modules), "| 依赖图节点:", ", ".join(dependencies.nodes))
print(pad("依赖名（参与规则匹配）", 24) + pad("模块", 30) + pad("形态", 14) + pad("解析", 12) + "行")
print("-" * 92)
for name, module, kind, resolution, line in rows:
    print(pad(name, 24) + pad(module, 30) + pad(kind, 14) + pad(resolution, 12) + str(line))
print("未解析项:", [item.reason for item in dependencies.unresolved] or "无")
assert ("repository", "shop.order_repository", "from_import", "internal", 3) in rows
assert not dependencies.unresolved

bad_report, bad_result = decide(BAD)
good_report, good_result = decide("src/shop/order_controller.py")
arch = [item for item in bad_result.violations if item.rule_id == "ARCH-001"]
print()
print("反例决策:", bad_result.decision.value, "| 正例决策:", good_result.decision.value)
for item in arch:
    print("  [" + item.severity.value + "]", item.rule_id, "→",
          item.evidence.file + ":" + str(item.evidence.line))
    print("     证据说明:", item.evidence.detail)
print("正例解析出的依赖:", [fact.name for fact in good_report.dependencies] or "（无）")
assert bad_result.decision.value == "block" and good_result.decision.value == "allow"
assert arch and arch[0].evidence.line == 3 and arch[0].evidence.file == BAD

print()
print(pad("目标文件", 36) + pad("选中的层级", 12) + pad("测试用例", 26) + "缺测试")
print("-" * 94)
selection = {}
for target in ("src/shop/order_service.py", "src/shop/order_controller_bad.py"):
    chosen = select_tests(
        target_path=target,
        changed_files=(target,),
        layout=CONFIG.layout,
        workspace=WORKSPACE,
        max_nodeids=CONFIG.layout.limits.max_nodeids,
    )
    selection[target] = chosen
    print(pad(target, 36) + pad(chosen.level, 12) + pad(",".join(chosen.nodeids) or "<无>", 26)
          + (",".join(chosen.missing) or "无"))
assert selection["src/shop/order_service.py"].level == "related"
assert selection["src/shop/order_controller_bad.py"].level == "suite"
assert selection["src/shop/order_controller_bad.py"].missing == ("src/shop/order_controller_bad.py",)

# operation=edit 才会让 TESTING-001/002 参与判断：没有"正在变更"这件事时它们不该命中。
passing_report, passing_result = decide(
    "src/shop/order_service.py", layer="service", operation="edit",
    changed=("src/shop/order_service.py",),
)
pytest_record = passing_report.record("tool.pytest")
print()
print("变更集里的文件:", passing_report.selection["nodeids"],
      "（层级", passing_report.selection["level"] + "）")
print("正例 + 变更集:", passing_result.decision.value,
      "| tool.pytest:", pytest_record.status.value, "|", pytest_record.reason)
assert passing_result.decision.value == "allow"
assert pytest_record.status.value == "ok"

# 把同名测试改成"必然失败"，同一套流水线必须给出 TESTING-002 的证据。
FAILING = TEMP / "shop-failing"
shutil.rmtree(FAILING, ignore_errors=True)
shutil.copytree(WORKSPACE, FAILING)
(FAILING / "tests" / "test_order_service.py").write_text(
    "def test_placeholder():\n    assert False, '故意失败：演示 TESTING-002'\n",
    encoding="utf-8",
    newline="\n",
)
failing_report, failing_result = decide(
    "src/shop/order_service.py", layer="service", operation="edit",
    changed=("src/shop/order_service.py",), workspace=FAILING,
)
failing_evidence = [item for item in failing_report.evidence if item.checker == "failing_tests"]
print()
print("反例（把同名测试改成必然失败）:", failing_result.decision.value)
for item in failing_evidence:
    print("  ", item.rule_id, "|", item.location.file, "|", item.message[:76])
assert failing_result.decision.value == "block"
assert failing_evidence and failing_evidence[0].rule_id == "TESTING-002"
assert "FAILED" in failing_evidence[0].message and "test_placeholder" in failing_evidence[0].message
print("小结：选中的测试真的运行；失败用例逐条变成证据，而不是一句「测试没过」。")

# ----------------------------------------------------------------------------
# ## 4. 外部工具：能被发现、按模板调用、输出必须脱敏
#
# 外部工具**不是包依赖**：Ruff / mypy / pytest 都不在 `pyproject.toml` 里，
# 而是运行时被**探针**发现的。探针只报告事实（有没有、什么版本、满不满足声明区间），
# `python -m validators.cli probe` 恒以 0 退出——"缺工具就不放行"发生在**判定**那一侧。
#
# 调用参数只能来自注册表里的模板（`tool.argv` 逐个占位符展开），环境变量走白名单，
# 超时终止整棵进程树，输出先脱敏再进证据。每条证据里必须能看到：
#
# - 验证器 ID 与版本（`tool.ruff@1.0`）、规则 ID（`STYLE-001`）、严重级别；
# - 文件与行列（`src/shop/style_offences.py:8:101`）；
# - 工具退出码（`exit_code`）与**配置文件哈希**（`config_sha256`）——回答"这个结论用的是哪份配置"。
#
# **输出怎么读**：第一张表是本机探针的原始事实；第二张表是真实 Ruff 跑出来的证据；
# 最后几行检查的是证据的纪律——不含绝对路径、不含耗时、同一输入两次运行逐字节相同。
# ----------------------------------------------------------------------------

# 探针报告事实；真实 Ruff 产出证据；证据必须可比较、可重放。
import json
import os
import subprocess


def validators_cli(*args):
    """在仓库根下跑 validators.cli：PYTHONPATH 显式给出，因此与当前工作目录无关。"""

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "validators.cli", *args],
        cwd=str(REPO_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


probe_run = validators_cli("probe", "--json")
assert probe_run.returncode == 0, probe_run.stderr
tools = {item["validator"]: item for item in json.loads(probe_run.stdout)["tools"]}
print(pad("验证器", 16) + pad("工具", 12) + pad("状态", 16) + pad("版本", 12) + "声明区间")
print("-" * 78)
for name in sorted(tools):
    item = tools[name]
    print(pad(name, 16) + pad(item["tool"], 12) + pad(item["status"], 16)
          + pad(item["version"] or "-", 12) + item["requirement"])
missing = sorted(name for name, item in tools.items() if item["status"] != "ok")
print()
print("本机缺失或不匹配的关键工具:", missing)
print("原因:", tools[missing[0]]["reason"] if missing else "（无）")
# 这是本机的**环境事实**（Ruff 装了、mypy 没装）。环境一变它就立刻报出来，不会默默变绿。
assert missing == ["tool.mypy@1.0"], missing
assert tools["tool.ruff@1.0"]["status"] == "ok"
assert tools["tool.mypy@1.0"]["version"] is None

report, result = decide("src/shop/style_offences.py")
print()
print("真实 Ruff 跑出的证据（决策:", result.decision.value + "）：")
print(pad("规则 ID", 12) + pad("级别", 10) + pad("文件:行:列", 44) + pad("退出码", 8) + "配置哈希")
print("-" * 96)
for item in report.evidence:
    where = item.location.file + ":" + str(item.location.line) + ":" + str(item.location.column)
    print(pad(item.rule_id, 12) + pad(item.severity.value, 10) + pad(where, 44)
          + pad(item.tool.exit_code, 8) + item.tool.config_sha256[:19])
print()
print("没有规则归属的诊断（只计数、不判定）:", report.unmapped_findings)
assert all(item.validator == "tool.ruff@1.0" for item in report.evidence)
assert all(item.tool.tool == "ruff" and item.tool.exit_code == 1 for item in report.evidence)
assert all(item.tool.version and item.tool.config_sha256.startswith("sha256:") for item in report.evidence)
assert ("STYLE-001", 8) in {(item.rule_id, item.location.line) for item in report.evidence}

payload = json.dumps(report.to_payload(), ensure_ascii=False, sort_keys=True)
again, _ = decide("src/shop/style_offences.py")
same_bytes = payload == json.dumps(again.to_payload(), ensure_ascii=False, sort_keys=True)
print()
print("同样输入两次运行，证据逐字节相同:", same_bytes)
print("证据里含仓库绝对路径:", str(REPO_ROOT) in payload, "| 证据里含耗时字段:", "duration_ms" in payload)
print("这份报告自己会不会给出 allow / block:", hasattr(report, "decision") or hasattr(report, "passed"))
assert same_bytes
assert str(REPO_ROOT) not in payload and "duration_ms" not in payload
assert not hasattr(report, "decision") and not hasattr(report, "passed")
print("小结：证据可比较、可重放；判定字段只出现在 evaluate 的返回值里。")

# ----------------------------------------------------------------------------
# ## 5. 六种"没跑成"落在六个显式状态上
#
# 外部工具的失效不是一个笼统的"出错了"，而是六个互不相同的状态：
#
# | 状态 | 什么时候出现 |
# | --- | --- |
# | `unavailable` | 可执行文件找不到（PATH 与解释器同目录都没有） |
# | `version_mismatch` | 版本不满足注册表声明的区间 |
# | `timeout` | 超过超时上限，整棵进程树被终止 |
# | `crashed` | 工具自己非零退出（内部错误） |
# | `config_error` | 工具报用法或配置错误 |
# | `output_invalid` | 输出不是合法 UTF-8、不是合法 JSON |
#
# 它们**全部**属于"失败关闭状态"。注意 `empty`（退出码 0 + 空输出）在**进程层**是 ok——
# "空输出要不要当成 `output_invalid`"是适配器映射阶段的决定，不是进程层的判断。
#
# 图上那个红色方框写的是"没证据就阻断"，它对应 `src/policy/checkers.py` 里的两个函数：
# `blocker_violation`（关键验证器没跑成 → 以 **critical** 表达，不管规则自己声明的是
# warning 还是 error）与 `uncovered_checker_violation`（有规则要用某个 checker，
# 却没有任何验证器为它产证据）。两者都阻断。
#
# **输出怎么读**：第一张表用假工具（`tests/fixtures/validators/tools/fake_tool.py`）
# 把六种状态逐个做出来，不需要真的装一个坏工具；第二段是**真流水线**——把 `tool.ruff` 的
# 命令换成本机不存在的可执行文件（只改内存里这份注册表副本，磁盘上的 YAML 一字不动）；
# 第三段把 allowlist 收窄成 `py.source`，你会看到**一个验证器都没跑**、三条 checker
# 全部没有证据；最后三行是**证据包**（交给判定核心的唯一入口）。
# ----------------------------------------------------------------------------

# 六种失效状态；然后把它接回"关键验证器不可用 → critical 阻断"。
from dataclasses import replace

from policy.evidence import ValidatorKind
from validators.adapters.base import build_argv, probe_tool, run_tool
from validators.models import ToolSpec, ValidatorSpec

FAKE_TOOL = REPO_ROOT / "tests" / "fixtures" / "validators" / "tools" / "fake_tool.py"
TOOL_TMP = TEMP / "tool-tmp"
TOOL_TMP.mkdir(parents=True, exist_ok=True)


def fake_spec(behaviour, *, timeout_ms=2000):
    """把假工具伪装成 tool.ruff：命令、版本探测与 argv 都照注册表的形状写。"""

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
    probe = probe_tool(spec.tool, timeout_ms=timeout_ms, max_output_bytes=65536,
                       workspace=WORKSPACE, tmp_dir=TOOL_TMP)
    if not probe.ok:
        return probe.status.value, probe.reason or ""
    argv = build_argv(spec.tool, probe, python=sys.executable, workspace=WORKSPACE,
                      config=None, paths=("src/shop/style_offences.py",))
    run = run_tool(spec.tool, probe, argv, workspace=WORKSPACE, tmp_dir=TOOL_TMP,
                   timeout_ms=timeout_ms, max_output_bytes=1024, findings_exit_codes=(1,))
    return run.status.value, (run.reason or ("退出码 " + str(run.exit_code)))


print(pad("假工具行为", 16) + pad("状态", 18) + "说明")
print("-" * 96)
classified = {}
for behaviour in ("ok", "findings", "empty", "garbage", "config_error", "crash", "slow", "old"):
    status, reason = classify(behaviour)
    classified[behaviour] = status
    print(pad(behaviour, 16) + pad(status, 18) + reason[:56])
print()
assert classified == {
    "ok": "ok",
    "findings": "ok",
    # 进程层：退出码 0 + 空输出仍然是"跑完了"；映射阶段才会判 output_invalid。
    "empty": "ok",
    "garbage": "output_invalid",
    "config_error": "config_error",
    "crash": "crashed",
    "slow": "timeout",
    "old": "version_mismatch",
}, classified
fail_closed_names = sorted(item.value for item in FAIL_CLOSED_STATUSES)
assert fail_closed_names == [
    "config_error", "crashed", "failed", "output_invalid", "timeout", "unavailable", "version_mismatch",
], fail_closed_names
print("失败关闭状态集合:", ", ".join(fail_closed_names))

# 真流水线：tool.ruff 的命令换成不存在的可执行文件（只改内存里的注册表副本）。
swapped = tuple(
    spec.model_copy(update={"tool": spec.tool.model_copy(update={"command": ("definitely-not-a-real-tool",)})})
    if spec.id == "tool.ruff"
    else spec
    for spec in REGISTRY.validators
)
broken_config = replace(CONFIG, registry=REGISTRY.model_copy(update={"validators": swapped}))
broken_report, broken_result = decide("src/shop/style_offences.py", config=broken_config)

print()
print("换成不存在的可执行文件后，决策:", broken_result.decision.value)
for blocker in broken_report.blockers:
    print("  阻断点:", blocker.validator, "/", blocker.status.value, "/", ",".join(blocker.checkers))
    print("  理由:", blocker.reason)
print("  拿到证据的 checker:", ", ".join(broken_report.served_checkers))
print("  同一批验证器的状态:",
      ", ".join(item.validator + "=" + item.status.value for item in broken_report.validators))
critical = [item for item in broken_result.violations if item.severity.value == "critical"]
print("  critical 违规:", len(critical), "条 | 第一条:", critical[0].message[:70])
assert broken_result.decision.value == "block"
assert [item.validator_id for item in broken_report.blockers] == ["tool.ruff"]
assert broken_report.blockers[0].status.value == "unavailable"
assert broken_report.blockers[0].checkers == ("style_lint",)
assert "style_lint" not in broken_report.served_checkers
assert all(item.status.value == "ok" for item in broken_report.validators if item.validator_id != "tool.ruff")
assert critical and "关键验证器不可用" in critical[0].message
print("小结：py.source / py.ast / py.depgraph 都成功了，但 style_lint 没有证据——PASS 抵消不了它。")

# 再看图上那个红色方框："没证据就阻断"。没有验证器为某个 checker 产证据时同样阻断——
# "少跑一个验证器"不等于"少一条规则"。
narrow_report, narrow_result = decide(BAD, only=("py.source",))
print("只跑 py.source 时：")
print("  决策:", narrow_result.decision.value)
print("  命中规则:", len(narrow_result.matched_rules), "条 |",
      "critical 违规:", sum(1 for item in narrow_result.violations if item.severity.value == "critical"))
print("  真的跑了的验证器:", [item.validator_id for item in narrow_report.validators] or "（一个都没有）")
uncovered = {
    blocker.checkers[0]: blocker.reason
    for blocker in narrow_report.blockers
    if blocker.validator_id == "pipeline"
}
print("  没有验证器提供证据的 checker:", ", ".join(sorted(uncovered)))
for checker in sorted(uncovered):
    print("    " + pad(checker, 22) + uncovered[checker][:56])
assert narrow_result.decision.value == "block"
assert set(uncovered) == {"forbidden_dependency", "missing_docstring", "style_lint"}
assert all(blocker.status.value == "not_selected" for blocker in narrow_report.blockers)
assert narrow_report.validators == () and narrow_report.served_checkers == ()
print("  为什么一个都没跑：验证器是**按 checker 选**出来的，而 py.source 不为任何 checker 提供证据；")
print("  把它写进 allowlist 的结果不是「少跑几条」，而是「那三条 checker 全部没人管」。")

# 证据包是交给核心的唯一入口；引擎只读它，不关心它是怎么来的。
bundle = narrow_report.bundle
print()
print("证据包协议:", bundle.schema_version, "| 字段:", ", ".join(sorted(bundle.to_payload())))
print("证据包是否带阻断点:", bundle.blocked, "| serves('style_lint'):", bundle.serves("style_lint"))
assert bundle.schema_version == "1.0"
assert bundle.blocked and not bundle.serves("style_lint")
assert bundle.blocker_for("style_lint") is not None
print("小结：注册表里少一个验证器、命令行少写一个名字，结果都是「证据不完整 → 不放行」。")

# ----------------------------------------------------------------------------
# ## 小结
#
# - **验证器只产证据**：`run_pipeline` 返回的报告里没有 allow / block 字段；
#   判定只出现在 `evaluate(rules, context, evidence=bundle)` 之后——本机实测这一点成立；
# - **证据绑内容、可比较**：带验证器 ID 与版本、规则 ID、文件行列、严重级别、
#   工具退出码与配置哈希；不含绝对路径、不含耗时，同一输入两次运行逐字节相同；
# - **"谁能产生证据"是数据**：`validation/validators.yaml` 里出现代码没实现的验证器 id，
#   加载阶段就报错；`critical: true` 的验证器没跑成，需要它的规则以 critical 阻断；
# - **"解析失败"不等于"没有依赖"**：语法错误、动态 import 目标不是常量、
#   项目内模块解析不到文件，三种都拿到 blocker + critical 违规（本节逐条断言过理由文本）；
# - **缺工具 = 失败关闭**：`python -m validators.cli probe` 恒以 0 退出、只报告事实；
#   本机 Ruff 在、mypy 不在。mypy 服务的 checker 是 `type_check`，今天没有任何规则声明它，
#   所以缺 mypy 暂时不阻断任何文件；一旦有规则声明它，`tool.mypy` 的 `critical: true`
#   就会像上面 `tool.ruff` 那样阻断——**"缺工具"和"没问题"是两件不同的事**。
#
# 往下可以接 `06-Policy-API.ipynb`（这套证据怎样经 HTTP 服务化，而判定路径不变），
# 或者 `09-能不能成为规则.ipynb`（一段文档要求够不够格成为一条规则）。
# ----------------------------------------------------------------------------
