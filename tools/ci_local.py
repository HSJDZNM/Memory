"""在本机按 CI 的顺序跑同一批检查。

为什么需要它：CI 有二十多步，手工挑着跑一定会漏。本仓库就发生过一次——改了 pre-check 的
检查链却漏跑"手册同步"，PR 因此变红。这个脚本把 workflow 当作唯一真相读出来，在本地按
同样顺序执行，并按"这次改了什么"决定跑多少；红了就退出 1，pre-push 钩子据此拦住推送。

例外（FULL_ONLY_STEPS）："学习手册同步"只在 --full 下执行。默认与 --hook 模式被改动选中时
会**点名列为未执行**并写明原因，GitHub CI 上照跑。这是有意的取舍：上面那次"漏跑手册同步、
PR 变红"的形态会重新变成可能——代价是推送前少等约 2.5 分钟，改了 src/ 的分支合并前要跑一次 --full。

用法：

    python tools/ci_local.py              # 按改动范围自动选择（默认；学习手册同步推迟到 --full）
    python tools/ci_local.py --full       # 跑全部能在本机跑的步骤（合并前跑这个）
    python tools/ci_local.py --list       # 只列出会跑哪些步骤，不执行
    python tools/ci_local.py --hook       # pre-push 钩子用：更简短、失败即退出码 1
    python tools/ci_local.py --full --python C:\\path\\to\\python.exe
    python tools/ci_local.py --full --timings   # 另把每步耗时写成 .tmp/ci-local-timings.json
    python tools/ci_local.py --full --verbose   # 步骤输出原样打到控制台（排查时用）

控制台输出：默认每步只打一行（`[ 3/31] 步骤名 ... ok  1m 23.9s`），步骤自己的 stdout+stderr
写进 `.tmp/ci-local-logs/<序号>-<步骤名>.log`（每次运行先清空）；失败的那一步把日志最后
40 行打出来并给出全文路径；最后的耗时汇总只列最慢 5 步（--timings 的 JSON 仍是全量）。
--hook 在开头打一行"运行中"，成功时不再打任何东西，失败时打日志尾部与阻断原因。
通过 / 失败只由退出码决定，与输出去向无关；--verbose 下子进程直连控制台，与过去逐字相同。

耗时可见性：一次全量本机门禁要二十多分钟，而“为什么是二十多分钟”过去只能靠猜——步骤是串行的，
墙钟时间就是各步之和，却没有任何一步报出自己的耗时。所以执行路径**总是**在最后打印一张按耗时降序的
汇总表（--hook 模式不打印：钩子成功时保持安静）；--timings 再把同样的事实写成
.tmp/ci-local-timings.json（含改动文件数、逐步耗时与退出码）。
这一步只观察，不改变任何步骤的执行与通过条件。

    # 同一个覆盖，但 pre-push 钩子也用得上（钩子不接受参数）：
    $env:CI_LOCAL_PYTHON = "C:\\path\\to\\python.exe"; git push

并发语义：同一工作树**同时只允许一个实例**真正执行步骤。脚本用一把排他锁
（`<仓库根>/.tmp/ci-local.lock`，操作系统咨询锁、非阻塞）把"同时跑"从静默出错变成显式
拒绝：第二个实例**一步都不执行**，打印持锁者 pid 与起始时间后退出 1（`--hook` 模式下写明
阻断推送）。进程无论怎么死，锁都由操作系统释放，所以不会留下陈旧锁；要恢复只需等它跑完。
理由：ci_local 与它调起的 tools/orchestration_loop.py 共用固定路径的状态
（.tmp/phase-8-orchestration/、.tmp/artifacts/、.tmp/retrieval/），并行会互相拆台——
实测出现过"编排闭环 5/8 场景 FAIL"的假红，而单独跑一律通过。

每个步骤子进程还拿到 TMPDIR/TEMP/TMP = 仓库内 .tmp/tmp/（按需创建）：临时目录不可写时
Python 的 tempfile 会回退到 os.getcwd()，0 字节的 tmpXXXXXXXX 会落进仓库根、把 git status
弄脏（见 temp_root() 的说明）。

**本地「只报告」步骤**（REPORT_ONLY_STEPS）：这些步骤**不在 workflow 里**，只在本机门禁执行。
它们是 L5 上线闸的读数（方案 §4 台阶 5：新检查先以"报告 + 非零退出"跑满一个轮次，升格判据是
"跑过 N≥1 次且 0 命中"），因此**永远不计入门禁失败**：非零退出只把命中读数
（`--json` 的 `hits`，或输出里的 `HITS:` 行）打印出来，退出码不受影响。
每条豁免都必须写 `reason` 与 `expires_at`：没有到期日的豁免是一张永不过期的空白支票
（方案 §5.2 R-b 的同一纪律）；**到期检查只报告**——到期前 14 天提醒、过期标红（`RED`），
两者都不改退出码（读数由 `tools/exemption_expiry.py` 给出，规则只有那一份实现）。

**门禁退出码**（完整表在 `tools/README.md`，这里只记本脚本自己返回什么，免得两处各说一套）：

| 码 | 本脚本的含义 |
| --- | --- |
| `0` | 全部步骤通过（**只报告步骤的非零退出不算失败**） |
| `1` | 有 workflow 步骤失败 / 拿不到排他锁 / workflow 里有未登记的步骤 |
| `2` | argparse 的用法错误 |

`3`（封条失效：`external_write` / `unprovable`）属于 `python -m provenance.cli seal` 的
封条语义，**本脚本不返回 3**——两套语义不要混读（方案 §5.3）。

只用标准库 + PyYAML（已在锁定依赖里）。bash-only 的步骤（heredoc、set +e、grep -q、
cat > /tmp）在 Windows 上无法直接执行，脚本会**显式跳过并打印原因**，不假装跑过。
workflow 里新增了步骤却没有登记进分组时，脚本**失败关闭**（退出码 1）而不是悄悄少跑——
"这个名字我认不出来"必须是一个结论，不能是一段沉默。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import IO, Any, NamedTuple, Optional, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

# 本地解释器：优先用仓库自己的 .venv，其次退回当前解释器。
# `CI_LOCAL_PYTHON` 与 `--python` 是同一条逃生通道，区别只在于**钩子也能用**：
# pre-push 钩子不接受参数（git 会把它自己的参数传进来），而受限环境里
# `.venv` 可能缺依赖、也装不进去，此时用环境变量指向一个已验证的解释器。
_VENV = ROOT / ".venv" / "Scripts" / "python.exe"
if not _VENV.is_file():
    _VENV = ROOT / ".venv" / "bin" / "python"
_OVERRIDE = os.environ.get("CI_LOCAL_PYTHON", "").strip()
PYTHON = _OVERRIDE or (str(_VENV) if _VENV.is_file() else sys.executable)

# 这些标记说明该步骤是 bash-only（heredoc、set +e、grep -q、/tmp 路径），本机不执行。
BASH_ONLY_MARKERS = ("<<'PY'", "<<'JSON'", "set +e", "set -e", "grep -q", "cat >", "/tmp/")

# 本机不执行的步骤（登记豁免，每条都要写明原因）：它们都是"装环境"类，本机用已有的 .venv。
# 没登记进分组、也不在本表里的步骤会被 unregistered_steps() 抓出来，main() 直接失败关闭。
NOT_RUN_ON_HOST = {
    "Install uv": "装 uv：本机用已有 .venv，不重复装环境",
    "Install pinned dependencies": "装依赖：本机用已有 .venv，不重复装环境",
    "Install external linter (ruff)": "装 ruff：本机用 validation/ruff.toml 指定的已有工具",
}


class ReportOnlyStep(NamedTuple):
    """一条本机「只报告」步骤：**登记在这里就等于登记了一条带到期日的豁免**。

    字段刻意都是必填：没有 `reason` 的豁免读不出"为什么允许它不阻断"，
    没有 `expires_at` 的豁免是永不过期的空白支票（方案 §5.2 R-b）。
    `args` 是传给当前解释器（PYTHON / --python 覆盖后的那个）的参数表——
    这样"用哪个解释器跑"与 workflow 步骤是同一个口径，测试也能换成自己的解释器。

    刻意用 `NamedTuple` 而不是 `@dataclass`：`@dataclass` 在装饰期要求模块已登记进
    `sys.modules`，而回归测试与 `tools/exemption_expiry.py` 都是按文件路径
    `spec_from_file_location` + `exec_module` 加载本模块的（不登记 `sys.modules`），
    用 `@dataclass` 会让这些加载方直接报 `AttributeError`（实测）。
    """

    name: str
    args: tuple[str, ...]
    reason: str
    expires_at: str
    adopted: str
    reads: str


# 本机「只报告」步骤（**不在 workflow 里**：它们在 CI 上没有账本 / 没有宿主状态可读，
# 或者本来就只是给本机评审看的读数）。非零退出**不计入门禁失败**，只打印命中读数。
#
# 升格（变成阻断步）需要评审按 L5 判据认定"跑过 N≥1 次且 0 命中"，并且 0 命中必须来自
# 至少一次真实读数；在升格之前，到期日就是这条豁免的复核点（tools/exemption_expiry.py）。
REPORT_ONLY_STEPS: tuple[ReportOnlyStep, ...] = (
    ReportOnlyStep(
        name="Obligations gate (report only)",
        args=(
            "tools/obligations_gate.py",
            "--ledger",
            ".tmp/obligations/repo.jsonl",
            "--json",
        ),
        reason=(
            "台阶 3c 的义务账门禁：判罚与读数在这一步，L5 试用期内非零退出只报告"
            "（方案 §3.3 / AGENTS 第 56 条）；账本在 .tmp 下，CI 上没有可读的账本"
            "（2026-10-04 续期至 12-31：试用期内仓库门禁里账本一直不存在、读数为不适用，"
            "L5 判据未满足；随 12-31 统一复审，届时决定找真实实例还是撤销）"
        ),
        expires_at="2026-12-31",
        adopted="2026-09-30",
        reads="--json 的 hits / ledger_count / not_applicable_ledgers 与每个账本的 obligations_open",
    ),
    ReportOnlyStep(
        name="Exemption expiry report (report only)",
        args=("tools/exemption_expiry.py",),
        reason=(
            "豁免到期检查：这个文件自己的豁免表 + adapters/wiring-scope.yaml 的声明，"
            "到期前 14 天提醒、过期标红（方案 §4 台阶 4 / R-b：放宽必须有到期日）"
        ),
        expires_at="2026-12-31",
        adopted="2026-09-30",
        reads=(
            "默认文本输出里的 HITS: 行（不带 --json；退出码恒为 0，命中数只能从这一行读，"
            "输出里没有这一行时读数为「读不出命中数」）"
        ),
    ),
    # 仪器自证（R-h，控制面重构线交接，见 26 号文档第 1 节）。name 是跨文件身份：
    # tools/instrument_self_proof.py 按 AST 读这里的 name= 字面量，作为对象清单第 4 族，
    # 并与 validation/instrument-checks.yaml 的 "report-only:<name>" 一行双向比对——
    # 改名要同一个提交同步登记表，否则仪器自证报 no_check_id（只报告、不阻断）。
    ReportOnlyStep(
        name="Instrument self-proof (report only)",
        # 不带 --json：它的载荷没有 hits 键（不是账本），读数走默认输出里的 HITS: 行。
        args=("tools/instrument_self_proof.py",),
        reason=(
            "仪器自证（R-h）：每条仪器检查都要能证明自己会红；只报告，"
            "非零退出不计入门禁失败（方案 §4 台阶 4 / 25 号 §7 方案 A）"
        ),
        expires_at="2026-12-31",
        adopted="2026-10-03",
        reads="默认输出里的 HITS: 行（不带 --json；退出码恒为 0，命中数只能从这一行读）",
    ),
    # 控制面事实表 × 跨源互证（台阶 5，控制面重构线交接，见 28 号文档第 1 节）。
    # name 同样是跨文件身份（仪器自证第 4 族 + 登记表 "report-only:<name>" 一行），
    # 改名要同一个提交同步登记表。
    # HITS 今天非 0（C1 存量不一致），只报告、不计入门禁失败。
    ReportOnlyStep(
        name="Control plane facts (report only)",
        # 不带 --json：它的载荷没有 hits 键（不是账本），读数走默认输出里的 HITS: 行。
        args=("tools/control_plane_facts.py",),
        reason=(
            "控制面事实表 × 跨源互证（台阶 5）：facts 表与检查登记表的连接键双向必查、"
            "C1/C2/C3 三组跨源读数；只报告，非零退出不计入门禁失败（27 号 §3 / §7）"
        ),
        expires_at="2026-12-31",
        adopted="2026-10-03",
        reads="默认输出里的 HITS: 行（不带 --json；退出码恒为 0，命中数只能从这一行读）",
    ),
)

# 按改动范围分组的步骤名（前缀匹配）。名字取自 workflow 里的 name:，改 workflow 时要同步。
ALWAYS_STEPS = (
    "Repository consistency gate",
    "Secret scan gate",
    "Text conventions",
)
CODE_STEPS = (
    "Unit, contract",
    "Rule set self-check",
    "AST evidence replay",
    "Example replay",
    "Scope skip reason",
    "Validator registry is loadable",
    "Validator registry declares what is implemented",
    "External tool probe",
    "Validators fail closed",
    "Syntax errors fail closed",
    "Validator closed loop",
    # "dsh adapter contract and hook behaviour" 已从 workflow 删除：它单独重跑的两份测试文件
    # 本来就在全量 pytest 里。
    "dsh hook wiring",
    "Real dsh sandbox loop",
    # 这一步跑的是 workflow 里的 host-version --record-check（CI 形态：不依赖宿主，
    # 比对「声明 vs 提交进仓库的观测记录 + 记录钉住的 manifest 哈希」）。活体形态
    # （--check）在没有 dsh 的机器上退 0，不能当门禁；两者同名同组，改 workflow 这里同步。
    "Agent version vs host version",
    "Tool registry must match",
    "Enforcement self-check",
    "Enforcement refuses unknown parameters",
    "Controlled execution closed loop",
    "Audit chain verification",
    "Multi-agent conformance suite",
    "Adapter support matrix is approved",
    "Adapter event fixtures exist",
    "Agent channel wiring inventory",
    "Multi-agent closed loop",
    "Policy API self-check",
    "Policy API contract snapshot",
    "Policy API ASGI contract",
    "Policy API closed loop",
    # "Performance baseline" 已从 workflow 删除：只记录、永远退 0，阶段验收证据步骤本来就调用
    # 同一份 policy_bench.run_baseline() 并写进证据。
    # 阶段验收证据与上面的 pytest 步骤**必须同组**：前者要引用后者刚写出的 junit 报告，
    # 同组才保证"要么都跑、要么都不跑"，复用的报告永远来自本次门禁。
    "Phase 8 acceptance evidence",
)
HANDBOOK_STEPS = (
    "Learning notebooks are in sync",
    "Learning notebook structure",
    "Tech-detail notebooks are in sync",
)
# 检索语料只在 docs/mirrors/ 下（knowledge/corpus.yaml 的每个 dataset 都指向镜像目录），
# 所以这一组由 mirrors 与检索代码触发；本项目自产的 docs/project/** 改动与语料无关，
# 不该顺带重建索引、跑评测基线（过去 docs/ 一改就全跑，还连带触发阶段验收证据）。
RETRIEVAL_STEPS = (
    "Retrieval corpus integrity",
    "Retrieval index is idempotent",
    "Retrieval refuses to answer without sources",
    "Retrieval evaluation baseline",
    "Tool registry must match",
)
ORCHESTRATION_STEPS = (
    "Orchestration self-check",
    "Orchestration closed loop",
)

# 只在 --full 下执行的步骤（前缀匹配 -> 原因）。按改动范围自动选择时（默认，以及 pre-push 钩子的
# --hook）即使被改动选中也**不执行**，而是显式列为"推迟到 --full"——不静默丢掉。
# GitHub CI 上照跑，这里只改本机的执行时机：推送前不跑，合并前用 --full 跑。
# 学习手册同步要把 9 个阶段手册的全部代码单元执行一遍（本机约 2.5 分钟，是本机门禁第二重的一步），
# 守的是"手册与实现同步"，不是产品行为；HANDBOOK_PREFIXES 又含 src/，几乎每次改代码都会选中它。
FULL_ONLY_STEPS = {
    "Learning notebooks are in sync": (
        "推迟到 --full：学习手册同步要执行全部阶段手册代码单元，"
        "合并前用 --full 跑（GitHub CI 照跑）"
    ),
}

# 改了这些前缀，就要跑对应的那一组。
CODE_PREFIXES = (
    "src/",
    "tests/",
    "tools/",
    "examples/",
    "policies/",
    "registry/",
    "adapters/",
    ".github/",
)
RETRIEVAL_PREFIXES = ("knowledge/", "src/retrieval/", "docs/mirrors/", "tools/retrieval_eval.py")
HANDBOOK_PREFIXES = (
    "src/",
    "tools/build_learning_notebook.py",
    "docs/project/learning/",
    "docs/project/architecture/tech-detail/",
)
ORCHESTRATION_PREFIXES = (
    "src/orchestration/",
    "tools/orchestration_loop.py",
    "tests/orchestration_support.py",
)


def _workflow_path() -> Path:
    files = sorted(WORKFLOW_DIR.glob("*.y*ml"))
    if not files:
        raise SystemExit("没有找到 .github/workflows/*.yml：无法知道 CI 跑什么")
    return files[0]


def _steps() -> list[tuple[str, str]]:
    """从 workflow 读 (步骤名, run 文本)；没有 run 的步骤（uses:）跳过。"""

    document = yaml.safe_load(_workflow_path().read_text(encoding="utf-8"))
    jobs = document.get("jobs") or {}
    collected: list[tuple[str, str]] = []
    for job in jobs.values():
        for step in job.get("steps") or []:
            run = step.get("run")
            if isinstance(run, str) and run.strip():
                collected.append((str(step.get("name", "")), run))
    return collected


def _changed_paths() -> list[str]:
    """相对 origin/main（取不到就相对 HEAD~1）的改动文件。"""

    for base in ("origin/main...HEAD", "HEAD~1"):
        completed = subprocess.run(
            ["git", "diff", "--name-only", base],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        if completed.returncode == 0:
            tracked = [line for line in completed.stdout.splitlines() if line.strip()]
            break
    else:
        tracked = []
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True,
    )
    dirty = [line[3:].strip() for line in status.stdout.splitlines() if len(line) > 3]
    return sorted(set(tracked) | set(dirty))


def _touched(changed: list[str], prefixes: tuple[str, ...]) -> bool:
    return any(item.startswith(prefixes) for item in changed)


def _selected_names(full: bool) -> list[str]:
    if full:
        return []  # 空 = 全选
    changed = _changed_paths()
    wanted = list(ALWAYS_STEPS)
    if _touched(changed, CODE_PREFIXES):
        wanted += list(CODE_STEPS)
    if _touched(changed, RETRIEVAL_PREFIXES):
        wanted += list(RETRIEVAL_STEPS)
    if _touched(changed, HANDBOOK_PREFIXES):
        wanted += list(HANDBOOK_STEPS)
    if _touched(changed, ORCHESTRATION_PREFIXES):
        wanted += list(ORCHESTRATION_STEPS)
    return wanted


def registered_prefixes() -> tuple[str, ...]:
    """所有已登记分组的步骤名前缀。"""

    return tuple(ALWAYS_STEPS + CODE_STEPS + HANDBOOK_STEPS + RETRIEVAL_STEPS + ORCHESTRATION_STEPS)


def unregistered_steps() -> list[str]:
    """workflow 里有 run 块、却既没登记进分组、也没写进 NOT_RUN_ON_HOST 的步骤名。

    这类步骤在按改动范围选择时**两个桶都不会进**：既不执行，也不会被打印成"跳过"。
    本仓库正是这样漏跑过真实检查（步骤名没同步进分组，本地永远看不见），
    所以调用方必须失败关闭，而不是把它们当空气。
    """

    prefixes = registered_prefixes()
    missing: list[str] = []
    for name, _run in _steps():
        if not name:
            missing.append("<未命名步骤>")
            continue
        if name in NOT_RUN_ON_HOST:
            continue
        if any(name.startswith(prefix) for prefix in prefixes):
            continue
        missing.append(name)
    return sorted(set(missing))


def _local_lines(run: str) -> list[str]:
    """把 CI 的 run 块翻译成本机可执行的行；顺带做"动作词白名单"。"""

    # 反斜杠续行的多行命令先接成一行，否则续行会被误判成"不是本项目的 python 调用"。
    joined = run.replace("\\" + chr(10), " ")

    lines: list[str] = []
    for raw in joined.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 只允许"调本项目脚本或模块"的动作，避免把任意 shell 塞进钩子
        if line.startswith(".venv/bin/python "):
            line = PYTHON + " " + line[len(".venv/bin/python ") :]
        lines.append(line)
    return lines


def _looks_unsafe(lines: list[str]) -> bool:
    joined = "\n".join(lines)
    if any(marker in joined for marker in BASH_ONLY_MARKERS):
        return True
    return any(not line.startswith(PYTHON) for line in lines)


def temp_root() -> Path:
    """门禁及其子进程共用的临时根：仓库内 .tmp/tmp/（按需创建）。

    为什么必须显式给：TMPDIR/TEMP/TMP 都不可写时，Python 的 tempfile 会**回退到 os.getcwd()**
    （_candidate_tempdir_list 的最后一站就是 cwd），于是临时文件落进仓库根。实测（受限沙箱里
    %TEMP% 的写入被拒/不存在）pytest 的全局捕获会在会话一开始就往仓库根丢两个 0 字节的
    tmpXXXXXXXX：它们被活进程独占、活到会话结束，期间 git status 变脏，文本约定检查还会在
    「先列出来、后读不到」的窗口里读到已经不存在的文件。给一个可写的临时根把这条回退路堵死。

    ROOT 取**调用时刻**的模块属性，不在导入时固化——单测会把它 monkeypatch 到临时目录。
    """

    directory = Path(ROOT) / ".tmp" / "tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        # 建不出可写的临时根就没有回退可言：失败关闭，而不是让子进程把临时文件丢进仓库根。
        raise SystemExit("ci_local: 无法创建临时根 %s：%s" % (directory, error)) from error
    return directory


def _step_environment(*, capture: bool = False) -> dict[str, str]:
    """每个步骤子进程的环境：换掉 PYTHONPATH，并把临时根钉在仓库内 .tmp/tmp/。

    三个变量都设：tempfile 依次看 TMPDIR / TEMP / TMP，少设一个就可能在别的平台上又回退；
    子进程（pytest、外部工具、闭环脚本）无论怎么再派生，都拿得到这个可写目录。

    capture=True（输出写进日志文件，见 LOG_DIR_NAME）时另设两项，都只影响输出、不影响判定：
    PYTHONIOENCODING=utf-8——stdout 不再是控制台时，Windows 上的 Python 会改用区域编码（cp936）
    写输出，GBK 以外的字符（仓库里有 ⇄ ↔ ⊆ 这类）会让步骤以 UnicodeEncodeError 假红；
    PYTHONUNBUFFERED=1——重定向到文件后 stdout 变成块缓冲，traceback（stderr）会跑到它前面的
    正常输出之前，日志读起来前后颠倒。--verbose 直连控制台，环境与过去逐字相同。
    """

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    root = str(temp_root())
    environment["TMPDIR"] = root
    environment["TEMP"] = root
    environment["TMP"] = root
    if capture:
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUNBUFFERED"] = "1"
    return environment


# --------------------------------------------------------------------------- 步骤输出
#
# 默认把每一步的 stdout+stderr 原样写进 `.tmp/ci-local-logs/<序号>-<步骤名>.log`，控制台每步只留
# 一行（进度 + 结论 + 耗时）；失败的那一步再把日志尾部打出来，并给出全文路径。
# 为什么：一次全量门禁在控制台上是两千多行，其中约 1800 行是"阶段验收证据"打印的 JSON，
# 真正要看的"哪步红了、为什么"被淹没在里面。通过 / 失败只由退出码决定，与输出去向无关——
# 这里只改"打到哪"，不改"跑什么、怎么判"。要看原样滚动的输出用 --verbose。
LOG_DIR_NAME = "ci-local-logs"
TAIL_LINES = 40
TIMING_TOP = 5


def log_dir() -> Path:
    """步骤日志目录：`ROOT / ".tmp" / LOG_DIR_NAME`（ROOT 取调用时刻的值，单测会替换它）。"""

    return Path(ROOT) / ".tmp" / LOG_DIR_NAME


def _reset_log_dir() -> Path:
    """建好日志目录并清掉上一次的 *.log：目录里只有本次运行的日志，不会读到旧的。"""

    directory = log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for stale in directory.glob("*.log"):
        try:
            stale.unlink()
        except OSError:
            pass  # 删不掉的旧日志不影响本次：本次的文件名按序号覆盖写
    return directory


def _log_name(index: int, name: str) -> str:
    """`03-unit-contract-integration-and-security-tests.log`：序号保证按执行顺序排列。"""

    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()[:60] or "step"
    return "%02d-%s.log" % (index, slug)


def _display_path(path: Path) -> str:
    """仓库内的路径报成仓库相对（正斜杠），仓库外报绝对路径。"""

    try:
        return path.resolve().relative_to(Path(ROOT).resolve()).as_posix()
    except ValueError:
        return str(path)


def _run_line(line: str, *, env: dict[str, str], log: IO[bytes] | None) -> int:
    """执行一行 workflow 命令；log 为 None 时输出直连控制台（--verbose），否则写进日志文件。"""

    if log is not None:
        log.write(("$ %s\n" % line).encode("utf-8"))
        log.flush()
    # shell=True 是这里唯一能表达语义的写法：`line` 来自仓库自己的
    # .github/workflows 的 run 块，是 **shell 语法**（`-c "import x"` 的引号由 shell
    # 解释）。改成列表参数就必须自己实现一遍引号规则：shlex 的 posix 模式会吃掉
    # Windows 路径里的反斜杠，posix=False 又会把引号留在参数里；
    # tests/unit/test_ci_local.py 正好用 `-c "import ci_local_probe"` 钉住了这个形态。
    # 注入面已经关闭：_looks_unsafe 要求每一行都必须以本项目解释器开头，
    # 且不含 BASH_ONLY_MARKERS（heredoc / set +e / grep -q / cat > / /tmp）。
    completed = subprocess.run(  # noqa: S602 - 见上：命令来自仓库 workflow，非外部输入
        line,
        cwd=str(ROOT),
        env=env,
        shell=True,
        stdout=log,
        stderr=subprocess.STDOUT if log is not None else None,
    )
    return completed.returncode


def _print_log_tail(path: Path, *, stream: IO[str]) -> None:
    """把失败步骤日志的最后 TAIL_LINES 行打出来，并给出全文路径。"""

    try:
        text = path.read_bytes().decode("utf-8", "replace")
    except OSError as error:
        print("  （读不到日志 %s：%s）" % (_display_path(path), error), file=stream)
        return
    lines = text.splitlines()
    shown = lines[-TAIL_LINES:]
    print(
        "  ---- 日志最后 %d 行（共 %d 行，全文：%s）----"
        % (len(shown), len(lines), _display_path(path)),
        file=stream,
    )
    # 本进程的 stdout 被重定向时（例如 `> run.txt`），Windows 上它的编码是区域编码（cp936）：
    # 日志里 GBK 以外的字符按 replace 降级，别让"打印失败日志"这一步自己抛异常。
    encoding = getattr(stream, "encoding", None) or "utf-8"
    for item in shown:
        safe = ("  " + item).encode(encoding, "replace").decode(encoding, "replace")
        print(safe, file=stream)
    print("  ----", file=stream, flush=True)


PlanGroups = tuple[list[tuple[str, list[str]]], list[tuple[str, str]], list[tuple[str, str]]]


def full_only_reason(name: str) -> str | None:
    """步骤名命中 FULL_ONLY_STEPS（前缀匹配）时返回推迟原因，否则 None。"""

    for prefix, reason in FULL_ONLY_STEPS.items():
        if name.startswith(prefix):
            return reason
    return None


def _plan_steps(full: bool) -> PlanGroups:
    """把 workflow 的步骤筛成三份：本机要执行的、本机跳过的、登记豁免的。

    规划只读 workflow，不写 `.tmp`，所以 `--list` 与取锁之前都可以调用它。
    """

    wanted = _selected_names(full)
    plan: list[tuple[str, list[str]]] = []
    skipped: list[tuple[str, str]] = []
    not_run: list[tuple[str, str]] = []
    for name, run in _steps():
        if name in NOT_RUN_ON_HOST:
            not_run.append((name, NOT_RUN_ON_HOST[name]))
            continue
        if wanted and not any(name.startswith(prefix) for prefix in wanted):
            continue
        deferred = full_only_reason(name)
        if deferred and not full:
            # 被改动范围选中、但只在 --full 下执行：列进"本机跳过"并写明原因，不静默丢掉。
            skipped.append((name, deferred))
            continue
        lines = _local_lines(run)
        if not lines:
            not_run.append((name, "run 块里没有本机可执行的命令"))
            continue
        if _looks_unsafe(lines):
            skipped.append((name, "bash-only（heredoc / set +e / grep / /tmp），CI 上执行"))
            continue
        plan.append((name, lines))
    return plan, skipped, not_run


# --------------------------------------------------------------------------- 排他锁
#
# ci_local.py 与它调起的工具（tools/orchestration_loop.py、检索索引、阶段证据）都用**固定路径**
# 的共享状态（.tmp/phase-8-orchestration/、.tmp/artifacts/、.tmp/retrieval/）。两个实例同时跑会
# 互相拆台：实测出现过"编排闭环 5/8 场景 FAIL、二审 exit 1"，而单独跑一律通过——并发会跑出假红。
# 所以同一工作树同时只允许一个实例真正执行步骤，第二个**显式失败退出**（退出码 1，与"红了就退出 1
# / pre-push 钩子据此阻断"一致）：把"同时跑"从静默出错变成显式拒绝。
#
# 刻意**不加 --no-lock、不认环境变量**绕过：并发就是不允许。本仓库的立场是失败关闭，不做
# "看起来有保护"的中间态（同 AGENTS.md 里"GitHub 侧不启用分支保护"的取舍）。
#
# 机制是操作系统咨询锁，且**非阻塞**（绝不挂起等待）：Windows 用 msvcrt.locking(LK_NBLCK)，
# POSIX 用 fcntl.flock(LOCK_EX | LOCK_NB)。锁在进程结束时由 OS 释放，所以不可能留下陈旧锁——
# 不采用"文件存在即上锁"那种写法。
LOCK_OFFSET = 1_048_576  # 1 MiB：锁字节放这里，与文件开头的元数据隔开（Windows 的坑见下）
LOCK_METADATA_BYTES = 4096  # 读元数据只读文件开头这一段，绝不碰 LOCK_OFFSET 附近


def lock_path() -> Path:
    """锁文件路径：`ROOT / ".tmp" / "ci-local.lock"`。

    ROOT 取**调用时刻**的模块属性，不在导入时固化——单测会把它 monkeypatch 到临时目录。
    """

    return Path(ROOT) / ".tmp" / "ci-local.lock"


def lock_metadata(argv: Sequence[str] | None = None) -> dict[str, Any]:
    """本次实例的元数据：pid / 启动时间 / argv 摘要。持锁者把它写进锁文件开头。"""

    effective = list(sys.argv[1:] if argv is None else argv)
    return {
        "pid": os.getpid(),
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "argv": " ".join(effective)[:400],
    }


def read_lock_metadata(path: Path | None = None) -> dict[str, Any] | None:
    """读锁文件开头的元数据（第二个实例靠它报出持锁者 pid）；读不到就返回 None。

    ⚠️ Windows 陷阱：msvcrt.locking 走的是 LockFile 语义，是**强制锁**——被锁的字节区间别的
    进程**读不到**（POSIX 的 flock 是咨询锁，没有这个问题）。所以锁字节写在 LOCK_OFFSET、
    元数据写在文件开头：第二个实例才读得到持锁者 pid，而不是"信息不可读"。
    """

    target = lock_path() if path is None else Path(path)
    try:
        descriptor = os.open(target, os.O_RDONLY)
    except OSError:
        return None
    try:
        raw = os.read(descriptor, LOCK_METADATA_BYTES)
    except OSError:
        return None
    finally:
        os.close(descriptor)
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return None
    try:
        document = json.loads(text.splitlines()[0])
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


class LockHandle:
    """一把已经持有的排他锁；`release()` 之后失效（重复调用是安全的空操作）。"""

    def __init__(self, path: Path, stream: IO[bytes]) -> None:
        self.path = path
        self._stream: IO[bytes] | None = stream

    def release(self) -> None:
        """清掉元数据、解锁、关掉文件描述符；重复调用什么都不做。"""

        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            # 顺序很重要：**先清元数据、再解锁**。反过来的话，另一个实例可能已经拿到锁并写好
            # 它自己的 pid，而本进程随后的截断会把那个 pid 抹掉，它就只能报"信息不可读"。
            stream.seek(0)
            stream.truncate(0)
            stream.flush()
            _unlock_stream(stream)
        finally:
            stream.close()

    def __enter__(self) -> "LockHandle":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _lock_stream(stream: IO[bytes]) -> None:
    """在 LOCK_OFFSET 处非阻塞加 1 字节排他锁；已被别人占着就抛 OSError（绝不等待）。"""

    descriptor = stream.fileno()
    stream.flush()
    if os.name == "nt":
        import msvcrt

        # msvcrt.locking 锁的是**当前文件位置**起的 1 字节，所以先把它挪到 LOCK_OFFSET。
        # LockFile 允许锁超出文件末尾的区间，因此不必把锁文件撑到 1 MiB。
        os.lseek(descriptor, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_stream(stream: IO[bytes]) -> None:
    """释放 `_lock_stream` 加在 LOCK_OFFSET 处的那 1 字节锁。"""

    descriptor = stream.fileno()
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


def try_acquire_lock(metadata: dict[str, Any] | None = None) -> LockHandle | None:
    """非阻塞取锁：拿到返回句柄，被别的实例占着返回 None（绝不等待，调用方据此退出 1）。

    拿到锁之后**先把元数据写进文件开头再返回**：任何能看到这把锁被占着的人都能读到"是谁在占、
    什么时候开始的"。跨进程可读的只有文件内容，所以这一步是契约的一部分。
    """

    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 只 O_CREAT、**不加** O_TRUNC：截断会把持锁者写在开头的 pid 抹掉（Windows 的强制锁也挡不住
    # 别的进程截断同一个文件），第二个实例就只能报"信息不可读"。
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    stream = os.fdopen(descriptor, "r+b")
    try:
        _lock_stream(stream)
    except OSError:
        stream.close()
        return None
    payload = metadata if metadata is not None else lock_metadata()
    stream.seek(0)
    stream.truncate(0)
    stream.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    stream.flush()
    return LockHandle(path, stream)


def _describe_lock_holder(holder: dict[str, Any] | None) -> str:
    """把锁文件里的元数据压成一行给人看的描述。"""

    if not holder:
        return "持锁者：锁文件里没有可读的元数据"
    parts = ["持锁者 pid=%s" % holder.get("pid", "<未记录>")]
    if holder.get("started_at"):
        parts.append("起始时间 %s" % holder["started_at"])
    if holder.get("argv"):
        parts.append("argv: %s" % holder["argv"])
    return "，".join(parts)


def _report_lock_conflict(holder: dict[str, Any] | None, *, hook: bool) -> None:
    """拿不到锁时把"谁在占、怎么办"写到 stderr：锁路径、持锁者 pid、起始时间、处置建议。"""

    print("ci_local: 已经有一个实例在执行本机门禁，拒绝并发。", file=sys.stderr)
    print("ci_local: 锁文件 %s" % lock_path(), file=sys.stderr)
    print("ci_local: %s" % _describe_lock_holder(holder), file=sys.stderr)
    print(
        "ci_local: 等它跑完再跑，不要并发——两个实例共用 .tmp/ 下的固定路径状态"
        "（phase-8-orchestration / artifacts / retrieval），同时跑会互相拆台、跑出假红。",
        file=sys.stderr,
    )
    print(
        "ci_local: 锁由操作系统持有，持锁进程一死就自动释放（不会留陈旧锁）；"
        "确认没有实例在跑就直接重试。",
        file=sys.stderr,
    )
    if hook:
        print("ci_local: 阻断推送 —— 有实例在跑时不重复执行 CI 步骤。", file=sys.stderr)


def _format_duration(seconds: float) -> str:
    """把秒数压成“1m 02s”这种一眼能读的形态（不足 1 分钟只报秒）。"""

    if seconds < 60:
        return "%.1fs" % seconds
    minutes, rest = divmod(seconds, 60.0)
    return "%dm %04.1fs" % (int(minutes), rest)


def report_timings(
    entries: Sequence[tuple[str, str, float, int]],
    *,
    changed: int,
    hook: bool,
    write_json: bool,
    top: int | None = None,
) -> Path | None:
    """打印（并可写出）逐步耗时。只观察，不参与任何通过 / 失败的判定。

    为什么默认就打印：门禁是**串行**的，墙钟时间等于各步之和；过去一次全量跑二十多分钟，
    输出里却没有一个字说明时间花在哪，于是“为什么这么慢”只能靠猜。这里把事实摆在最后。
    钩子模式（--hook）保持安静：它成功时不打印任何东西是既有的行为契约。
    top 给定时只列最贵的前 top 步（默认模式下每步的耗时已经在它自己那一行里，汇总只需点出大头）；
    --timings 写出的 JSON 始终是全量。
    """

    total = sum(item[2] for item in entries)
    output: Path | None = None
    if not hook and entries:
        ranked = sorted(entries, key=lambda item: -item[2])
        shown = ranked if top is None else ranked[:top]
        suffix = "" if len(shown) == len(ranked) else "，最慢 %d 步" % len(shown)
        print(
            "\n=== 执行耗时（合计 %s，%d 步%s）==="
            % (_format_duration(total), len(entries), suffix)
        )
        for name, _command, seconds, returncode in shown:
            share = (100.0 * seconds / total) if total else 0.0
            print("%9s  %5.1f%%  rc=%-3s %s" % (_format_duration(seconds), share, returncode, name))
    if write_json:
        output = Path(ROOT) / ".tmp" / "ci-local-timings.json"
        payload = {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "changed_files": changed,
            "steps": len(entries),
            "total_seconds": round(total, 3),
            "entries": [
                {
                    "name": name,
                    "command": command,
                    "seconds": round(seconds, 3),
                    "returncode": returncode,
                }
                for name, command, seconds, returncode in entries
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + chr(10),
            encoding="utf-8",
            newline=chr(10),
        )
        if not hook:
            print("耗时明细已写入: %s" % output)
    return output


# --------------------------------------------------------------------------- 只报告步骤
#
# 这几步**不进 failures**：L5 试用期内它们的非零退出只是读数（命中数），不是门禁结论。
# 它们不会因为"输出读不出来"而阻断——读不出来就照实说"读不出命中数"，
# 读者可以自己重跑那一条命令（命令原文打在标题行上）。


def json_objects(output: str) -> list[dict]:
    """把一段输出里**完整的 JSON 对象**切出来（允许它跨多行）。

    为什么不能逐行 `json.loads`：`obligations_gate.py --json` 打的是
    `json.dumps(..., indent=2)` 的**多行**载荷，第一行只有一个 `{` —— 逐行解析**永远**
    读不到它，读数于是退化成"读不出命中数"（2026-09-30 第 17 轮门禁运行里实测就是这一行）。
    这里按花括号配平把对象切出来整体解析；解析不了就跳过 —— 读不到不许被写成结论。
    """

    found: list[dict] = []
    lines = output.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("{"):
            index += 1
            continue
        depth = 0
        chunk: list[str] = []
        for line in lines[index:]:
            chunk.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                break
        try:
            payload = json.loads("\n".join(chunk))
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            found.append(payload)
        index += max(1, len(chunk))
    return found


_HITS_LINE_RE = re.compile(r"^HITS:\s*(\d+)")


def report_only_reading(step: ReportOnlyStep, output: str) -> tuple[int | None, str]:
    """取读数：`(命中数, 读数文本)`；命中数读不出时为 None（**不许**当成 0）。

    结构化优先（`--json` 的 `hits` / `ledger_count`），其次 `HITS:` 文本行。
    为什么允许读文本行：`obligations_gate.py` 的文本读数里 `HITS: n / m` 是**稳定的机器行**
    （它由同一份 `hits` 计算得出，不是"解析 reasons 文本"那类口径）；给 `--json` 的步骤
    仍然优先走结构化字段。命中数与读数文本出自同一次解析，结论行与读数不会各说一套。
    """

    if "--json" in step.args:
        for payload in json_objects(output):
            if "hits" in payload:
                # 账本不存在 = 不适用：0 命中**不是**一次真实读数，读数里必须看得出这一档，
                # 否则"什么都没读到"会被读成"跑过了、0 命中"（升格判据就靠这句话）。
                not_applicable = payload.get("not_applicable_ledgers")
                suffix = (
                    "（不适用 %s：没有账本可读，不算一次真实读数）" % not_applicable
                    if not_applicable
                    else ""
                )
                hits = payload.get("hits")
                text = "hits=%s / %s 个账本%s" % (hits, payload.get("ledger_count"), suffix)
                count = hits if isinstance(hits, int) and not isinstance(hits, bool) else None
                return count, text
    for line in output.splitlines():
        stripped = line.strip()
        match = _HITS_LINE_RE.match(stripped)
        if match:
            return int(match.group(1)), stripped
        if stripped.startswith("HITS:"):
            return None, stripped  # 有 HITS: 行但读不出整数：照原文给，命中数不猜
    return None, "读不出命中数（重跑上面那条命令看原始输出）"


def report_only_hits(step: ReportOnlyStep, output: str) -> str:
    """读数文本（见 report_only_reading）。"""

    return report_only_reading(step, output)[1]


def report_only_verdict(returncode: int, count: int | None) -> str:
    """REPORT-ONLY 行的结论段：命中数取自读数，**不由退出码推断**。

    有的只报告步骤退出码恒为 0（`exemption_expiry.py`），命中只在读数里；
    过去"退出码 0 ⇒ 0 命中"会把一次有命中的读数写成"0 命中"。读不出命中数时照实说。
    """

    if count is None:
        return "退出码 %s（命中数读不出）" % returncode
    return "%s 命中（退出码 %s）" % (count, returncode)


def run_report_only_steps(
    steps: Sequence[ReportOnlyStep],
    *,
    hook: bool,
    logs: Path | None = None,
    first_index: int = 1,
) -> list[tuple[str, str, float, int]]:
    """跑只报告步骤，返回耗时明细（与 workflow 步骤进同一张表）。

    退出码**只被打印、不被判罚**：任何非零（含启动失败）都不进 failures。
    `--hook` 模式下**什么都不打印**：只报告步骤的非零退出不改变门禁结论，
    而钩子的行为契约是"成功时保持安静"——读数留给常规（非钩子）的门禁运行与 `--list`。

    读数解析始终拿子进程的**完整** stdout+stderr（capture_output，不截断）。
    logs 给定时（默认的精简输出）：不打印 `=== … ===` 标题块，完整输出另写进
    `logs/<序号>-<步骤名>.log`，控制台只留 REPORT-ONLY 那一行并附日志路径；
    logs 为 None（--verbose）时与过去逐字相同。
    """

    entries: list[tuple[str, str, float, int]] = []
    # 子进程输出被管道接住、按 UTF-8 解码：子进程也必须按 UTF-8 写，否则 Windows 上它会用
    # 区域编码（cp936）写中文，GBK 以外的字符还会让它自己抛 UnicodeEncodeError。
    environment = _step_environment(capture=True)
    for offset, step in enumerate(steps):
        command = [PYTHON, *step.args]
        display = " ".join(command)
        log_path = (
            logs / _log_name(first_index + offset, step.name) if logs is not None else None
        )
        if not hook and log_path is None:
            print("\n=== %s（只报告） ===\n$ %s" % (step.name, display), flush=True)
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=str(ROOT),
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            returncode = completed.returncode
            output = (completed.stdout or "") + (completed.stderr or "")
        except OSError as error:
            returncode = -1
            output = "启动失败：" + str(error)
        entries.append((step.name, display, time.perf_counter() - started, returncode))
        if log_path is not None:
            # 完整输出落盘（钩子模式也写：读数虽然不出声，事后要能查）。
            # 写失败只影响留档，不影响读数。
            try:
                log_path.write_text(
                    "$ %s\n%s" % (display, output), encoding="utf-8", newline=chr(10)
                )
            except OSError:
                log_path = None
        if hook:
            # 钩子的契约是"成功时保持安静"：只报告步骤不改结论，因此它红也不出声。
            continue
        # 结论里的命中数取自读数，不由退出码推断：退出码恒为 0 的步骤（exemption_expiry）
        # 命中只在 HITS: 行里，写死"退出码 0 ⇒ 0 命中"会把有命中的读数报成 0。
        count, reading = report_only_reading(step, output)
        verdict = report_only_verdict(returncode, count)
        where = "（日志：%s）" % _display_path(log_path) if log_path is not None else ""
        print(
            "REPORT-ONLY: %s —— %s；读数 %s；豁免到期 %s（不计入门禁失败）%s"
            % (step.name, verdict, reading, step.expires_at, where),
            flush=True,
        )
    return entries


def main(argv: list[str] | None = None) -> int:
    global PYTHON

    parser = argparse.ArgumentParser(description="在本机按 CI 的顺序跑同一批检查")
    parser.add_argument("--full", action="store_true", help="跑全部能在本机跑的步骤")
    parser.add_argument("--list", action="store_true", help="只列出会跑哪些步骤")
    parser.add_argument("--hook", action="store_true", help="pre-push 钩子模式：更简短")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help=(
            "步骤输出原样打到控制台"
            "（默认写进 .tmp/ci-local-logs/，控制台每步一行，失败才打日志尾部）"
        ),
    )
    parser.add_argument(
        "--timings",
        action="store_true",
        help="把每步耗时写成 .tmp/ci-local-timings.json（汇总表在非 --hook 模式下总是打印）",
    )
    parser.add_argument(
        "--python",
        dest="python_executable",
        help="覆盖步骤使用的 Python：.venv 存在但不可加载时用（也可设 CI_LOCAL_PYTHON）",
    )
    args = parser.parse_args(argv)

    if args.python_executable:
        candidate = Path(args.python_executable).resolve()
        if not candidate.is_file():
            parser.error(f"--python 指向的文件不存在: {candidate}")
        PYTHON = str(candidate)

    missing = unregistered_steps()
    if missing:
        print(
            "ci_local: workflow 里有 %d 个步骤没有登记进任何分组：" % len(missing),
            file=sys.stderr,
        )
        for name in missing:
            print("  - " + name, file=sys.stderr)
        print(
            "ci_local: 按改动范围选择时它们既不执行、也不报告跳过。把它们登记进 "
            "ALWAYS/CODE/HANDBOOK/RETRIEVAL/ORCHESTRATION_STEPS 之一，"
            "或写进 NOT_RUN_ON_HOST 并写明原因。",
            file=sys.stderr,
        )
        return 1

    # `--list` 不取锁：它不写 `.tmp`，而且别的实例正在跑时也可能有人只想看看清单。
    # 规划本身也是只读的，所以它同样留在锁外面。
    if args.list:
        plan, skipped, not_run = _plan_steps(args.full)
        print("改动文件 %d 个；本次会跑：" % len(_changed_paths()))
        for name, _ in plan:
            print("  - " + name)
        if skipped:
            print("本机跳过（CI 上仍然执行）：")
            for name, why in skipped:
                print("  - %s：%s" % (name, why))
        if not_run:
            print("本机不执行（已登记豁免）：")
            for name, why in not_run:
                print("  - %s：%s" % (name, why))
        if REPORT_ONLY_STEPS:
            print("本机只报告（不在 workflow 里；非零退出不计入失败，带到期日）：")
            for step in REPORT_ONLY_STEPS:
                print(
                    "  - %s：%s（豁免到期 %s，登记于 %s；读数 %s）"
                    % (step.name, step.reason, step.expires_at, step.adopted, step.reads)
                )
        return 0

    # 从这里往后才真正执行步骤：先拿排他锁，拿不到就**一步都不跑**。
    # 位置有讲究：必须在 unregistered_steps() 的失败关闭检查与 `--list` 之后（两者都不写
    # `.tmp`，也不该被别的实例的运行挡住），又必须在任何步骤执行之前。
    # 先读一次元数据：拿不到锁时，它属于"此刻正占着锁"的那个人。放在尝试之前读，
    # 是为了避免"对方刚好在失败之后释放、元数据被清空"这个窗口——那样就报不出持锁者 pid 了。
    holder = read_lock_metadata()
    try:
        lock = try_acquire_lock(lock_metadata(argv))
    except OSError as error:
        print("ci_local: 建立排他锁失败（%s）：%s" % (lock_path(), error), file=sys.stderr)
        print(
            "ci_local: 拿不到这把锁就没有排他保证，本机门禁失败关闭，一步都不执行。",
            file=sys.stderr,
        )
        return 1
    if lock is None:
        # 前一次读不到（文件刚建好或被清空）就再读一次：此刻持锁者仍然在。
        _report_lock_conflict(holder or read_lock_metadata(), hook=args.hook)
        return 1

    try:
        changed = _changed_paths()
        plan, skipped, not_run = _plan_steps(args.full)
        if not args.hook:
            print(
                "改动文件 %d 个；执行 %d 步（本机跳过 %d 步，登记豁免 %d 步，只报告 %d 步）"
                % (len(changed), len(plan), len(skipped), len(not_run), len(REPORT_ONLY_STEPS))
            )
            # 推迟到 --full 的步骤单独点名：它们是被改动选中却没跑的，不能只藏在"跳过 N 步"里。
            for name, why in skipped:
                if full_only_reason(name):
                    print("  - 未执行 %s：%s" % (name, why))

        failures: list[str] = []
        # 默认（含 --hook）把步骤输出写进日志文件，控制台只留每步一行；--verbose 恢复原样滚动。
        # 判定只看退出码，两种模式跑的是同一批命令、同一个判定。
        capture = not args.verbose
        step_environment = _step_environment(capture=capture)
        logs = _reset_log_dir() if capture else None
        if capture and args.hook:
            # 钩子模式成功时不逐步打印；只留一行，免得推送时两三分钟毫无动静、被当成卡死。
            print(
                "ci_local: 本机门禁运行中（%d 步，输出写进 %s/）…"
                % (len(plan), _display_path(logs)),
                file=sys.stderr,
                flush=True,
            )
        # 逐步计时：门禁是串行的，墙钟时间 = 各步之和，所以“哪一步最贵”是可直接测量的量。
        timings: list[tuple[str, str, float, int]] = []
        for index, (name, lines) in enumerate(plan, start=1):
            log_path = logs / _log_name(index, name) if logs is not None else None
            if capture and not args.hook:
                # 先打步骤名再跑：长步骤（pytest 一分多钟）期间看得出卡在哪一步。
                print("[%2d/%d] %s ..." % (index, len(plan), name), end="", flush=True)
            step_started = time.perf_counter()
            step_code = 0
            # buffering=0：本进程写的 "$ 命令" 行与子进程写的输出共用同一个文件位置，
            # 不能让本进程的缓冲区把顺序打乱（多行步骤会交替写）。
            log = open(log_path, "wb", buffering=0) if log_path is not None else None  # noqa: SIM115
            try:
                for line in lines:
                    if log is None and not args.hook:
                        print("\n=== %s ===\n$ %s" % (name, line), flush=True)
                    started = time.perf_counter()
                    returncode = _run_line(line, env=step_environment, log=log)
                    timings.append((name, line, time.perf_counter() - started, returncode))
                    if returncode != 0:
                        step_code = returncode
                        break
            finally:
                if log is not None:
                    log.close()
            elapsed = _format_duration(time.perf_counter() - step_started)
            if capture and not args.hook:
                if step_code == 0:
                    print(" ok  %s" % elapsed)
                else:
                    print(" FAIL rc=%s  %s" % (step_code, elapsed))
            if step_code == 0:
                continue

            where = "（日志：%s）" % _display_path(log_path) if log_path is not None else ""
            failures.append("%s -> 退出码 %s%s" % (name, step_code, where))
            if log_path is not None:
                _print_log_tail(log_path, stream=sys.stderr if args.hook else sys.stdout)
            if args.hook:
                print("ci_local: 阻断推送 —— %s" % failures[-1], file=sys.stderr)
                print(
                    "ci_local: 修好再推；确需跳过用 git push --no-verify",
                    file=sys.stderr,
                )
                return 1

        # 只报告步骤在所有 workflow 步骤之后跑：它们的非零退出**不进 failures**，
        # 因此顺序不影响通过 / 失败的判定，只影响读数出现的先后。
        # 日志序号接在 workflow 步骤之后，同一目录里按执行顺序排列。
        timings.extend(
            run_report_only_steps(
                REPORT_ONLY_STEPS, hook=args.hook, logs=logs, first_index=len(plan) + 1
            )
        )

        # 无论红绿都先把耗时摆出来：红了的时候“卡在哪一步”与“哪一步最贵”同样重要。
        report_timings(
            timings,
            changed=len(changed),
            hook=args.hook,
            write_json=args.timings,
            top=TIMING_TOP if capture else None,
        )
        if logs is not None and not args.hook:
            print("步骤日志: %s/" % _display_path(logs))

        if failures:
            print("\n失败 %d 处：" % len(failures), file=sys.stderr)
            for item in failures:
                print("  - " + item, file=sys.stderr)
            return 1
        if not args.hook:
            print(
                "\n本机检查全部通过（%d 步）" % len(plan)
                + (
                    "；只报告 %d 步（非零退出不计入失败）" % len(REPORT_ONLY_STEPS)
                    if REPORT_ONLY_STEPS
                    else ""
                )
            )
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
