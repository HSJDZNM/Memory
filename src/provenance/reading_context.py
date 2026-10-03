r"""reading_context：读数属于**哪棵树 / 哪一个环境 / 哪一套声明**（台阶 4 的统一形状）。

为什么要有它
============

一份读数如果不写清归属，就会被读成同一件事：

- **哪棵树**（Q1）：同一条命令在两棵树上得到两个结论不是缺陷，**没写清是哪棵树**才是
  （AGENTS 第 48 条）；
- **哪一个环境**（Q2）：真机上的 result=pass 与受限沙箱里的 result=skipped 是同一条命令的
  两个结论，差别只来自环境（19 号 §3.1）——环境跳过不是通过（第 45 条）；
- **哪一套声明**（Q3）：同一个 tool.pytest@1.0 在账本里对应三种行为，差别只来自声明版本
  （18 号 §2 的 R4）。

reading_context 只回答**归属**，不回答**结论**：它不进 policy.engine.evaluate 的任何输入，
也不改变任何 allow / block。

统一形状（21 号 §3，**只有这一份实现**）
======================================

::

    "reading_context": {
      "source": "cli",
      "tree": {"status": "available", "scope": "workspace", "digest": "sha256:...", "revision": "<40 hex>"},
      "declarations": {
        "registry": {"status": "available", "path": "validation/validators.yaml", "digest": "sha256:..."},
        "test_layout": {"status": "not_applicable"}
      },
      "host": {"platform": "Windows-11", "python": "3.13.11", "sandbox": "unknown"},
      "run": {"id": "<uuid>", "started_at": "<ISO-8601 Z>"}   # 有条件的，见下
    }

四条纪律（21 号 §1.3 / §3）：

1. **只放引用，不放正文**：摘要、仓库相对路径、枚举、布尔；不放文件内容、不放凭据、
   **不放绝对路径**（工作区之外的根写 <outside-workspace>，没给写 <unset>）；
2. **取值来自本次运行的真实读数**：取不到写 status="unavailable" + 一句可读的 reason，
   **绝不写一个"看起来像"的常量**；
3. **不适用与读不到分开**：not_applicable（这条路径上没有这个声明）与 unavailable
   （该有却读不到）是两件事，null 只表示该字段不适用；
4. **不猜**：source 由调用点显式传入；推导不出来的写 unknown / unavailable，
   不从文件名、目录或宿主名反推（AGENTS 核心约束 6）。

两条否定性结论（写下来，免得下一个人顺手加）：

- **不进证据载荷**：policy.evidence.EVIDENCE_SCHEMA_VERSION 与
  validators.pipeline.PIPELINE_SCHEMA_VERSION 的载荷要求"相同输入得到**逐字节相同**的证据"
  （AGENTS 第 19 条），而这里面的 run id / 宿主 / 墙钟一律随运行变化——塞进去就破掉那条。
  证据要回答"属于哪棵树"时用既有的 tree.scope / tree_digest（第 48 条）；
- **不是版本轴**：reading_context 是一个**形状**，不是一个载荷，因此它自己没有版本号；
  它的形状变更随**各载荷自己的**版本轴走（AGENTS 第 55 条：OUTPUT_SCHEMA_VERSION /
  REPORT_SCHEMA_VERSION / SANDBOX_RESULT_SCHEMA_VERSION …）。

还有一条**边界**（2026-09-30 裁定①，写下来免得下一个人顺手加回去）：

- **run 是有条件的**：五个顶层键里只有它随运行变化。凡是被要求"相同输入得到逐字节相同的输出"
  的载荷，调用点必须显式 `include_run=False`——落点是 `policy.check --json`（AGENTS 第 19 条
  的同一条纪律，且没有一个消费方读 run）。其余读数保留 run："这份读数什么时候算的"仍然可读。

失败语义（本模块**不抛异常**）
==============================

除了"编程错误"（未知 source / 未知 sandbox 取值）会 raise ValueError，本模块的每个子块
都**降级**而不是抛出：树摘要读不到、git 不可用、声明文件不存在，一律进三态。
理由是它是**旁注**：一份读数不该因为附注写不出来就整份写不出来（第 56 条对账本的同一口径：
写不了只打一行，不改判定、不阻断）。
"""

from __future__ import annotations

import datetime as _datetime
import hashlib
import platform as _platform
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional

from .worktree import ProvenanceError, workspace_tree_digest

__all__ = [
    "DECLARATIONS",
    "DECLARATION_CONTROL_PLANE_FACTS",
    "DECLARATION_INSTRUMENT_CHECKS",
    "OUTSIDE_WORKSPACE",
    "SANDBOX_RESTRICTED",
    "SANDBOX_UNKNOWN",
    "SANDBOX_UNRESTRICTED",
    "SANDBOX_VALUES",
    "SCOPE_WORKSPACE",
    "SOURCE_CLI",
    "SOURCE_EVIDENCE",
    "SOURCE_GATE",
    "SOURCE_HOOK",
    "SOURCE_LIBRARY",
    "SOURCE_SANDBOX_LOOP",
    "SOURCES",
    "STATUS_AVAILABLE",
    "STATUS_NOT_APPLICABLE",
    "STATUS_UNAVAILABLE",
    "STATUS_VALUES",
    "UNSET",
    "build",
    "declaration_block",
    "declaration_digest",
    "display_path",
    "git_revision",
    "host_block",
    "not_applicable",
    "run_block",
    "tree_block",
    "unavailable",
    "utc_now",
]

# --------------------------------------------------------------------------- 枚举

# source 的取值域：**调用点显式传入**，不从文件名 / 目录 / 宿主名反推。
SOURCE_LIBRARY = "library"
SOURCE_CLI = "cli"
SOURCE_HOOK = "hook"
SOURCE_PHASE6_RUNTIME = "phase6-runtime"
SOURCE_API = "api"
SOURCE_GATE = "gate"
SOURCE_SANDBOX_LOOP = "sandbox-loop"
SOURCE_EVIDENCE = "evidence"
SOURCES = (
    SOURCE_API,
    SOURCE_CLI,
    SOURCE_EVIDENCE,
    SOURCE_GATE,
    SOURCE_HOOK,
    SOURCE_LIBRARY,
    SOURCE_PHASE6_RUNTIME,
    SOURCE_SANDBOX_LOOP,
)

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_VALUES = (STATUS_AVAILABLE, STATUS_UNAVAILABLE, STATUS_NOT_APPLICABLE)

# host.sandbox（21 号 §3 的唯一新词）：只报事实，不猜。
# - restricted：本次运行里出现了"沙箱 / 宿主拒绝了工作区之外的操作"的证据；
# - unrestricted：本次把这件事真的做完了，且没有任何被拒证据；
# - unknown：其余（没做过 / 归不了因）——**不是**"没有沙箱"。
SANDBOX_RESTRICTED = "restricted"
SANDBOX_UNRESTRICTED = "unrestricted"
SANDBOX_UNKNOWN = "unknown"
SANDBOX_VALUES = (SANDBOX_RESTRICTED, SANDBOX_UNRESTRICTED, SANDBOX_UNKNOWN)

SCOPE_WORKSPACE = "workspace"

# declarations 的子键名：复用既有词汇（第 50 条：同名同义）。
DECLARATION_REGISTRY = "registry"
DECLARATION_TEST_LAYOUT = "test_layout"
DECLARATION_ADAPTER_CONFIG = "adapter_config"
DECLARATION_WIRING_SCOPE = "wiring_scope"
DECLARATION_OBLIGATIONS_LEDGER = "obligations_ledger"
DECLARATION_REPORT_ONLY_STEPS = "report_only_steps"
# 仪器自证（R-h）读的那张检查登记表：validation/instrument-checks.yaml。
DECLARATION_INSTRUMENT_CHECKS = "instrument_checks"
# 台阶 5 的控制面事实表：validation/control-plane-facts.yaml（只报告读数的那一套声明）。
DECLARATION_CONTROL_PLANE_FACTS = "control_plane_facts"
DECLARATIONS = (
    DECLARATION_ADAPTER_CONFIG,
    DECLARATION_CONTROL_PLANE_FACTS,
    DECLARATION_INSTRUMENT_CHECKS,
    DECLARATION_OBLIGATIONS_LEDGER,
    DECLARATION_REGISTRY,
    DECLARATION_REPORT_ONLY_STEPS,
    DECLARATION_TEST_LAYOUT,
    DECLARATION_WIRING_SCOPE,
)

OUTSIDE_WORKSPACE = "<outside-workspace>"
UNSET = "<unset>"

_REVISION = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


# --------------------------------------------------------------------------- 小工具


def utc_now() -> str:
    """本次运行的墙钟（ISO-8601、Z 结尾）——**只在读数层**，绝不进证据（见模块 docstring）。"""

    return _datetime.datetime.now(_datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def display_path(path: object, *, root: Path | str) -> str:
    """读数里的路径一律仓库相对；工作区之外写 <outside-workspace>，没给写 <unset>。

    path 为 None / 空串 = 这个变量没设（例如 dsh 子进程没拿到 DSH_HOME）；
    root 之内的路径写成 POSIX 相对路径；之外的一律折叠成 <outside-workspace>——
    **不放绝对路径**（AGENTS 第 16/34 条的脱敏纪律）。
    """

    if path is None:
        return UNSET
    text = str(path).strip()
    if not text:
        return UNSET
    try:
        resolved = Path(text).resolve()
    except (OSError, ValueError):
        return OUTSIDE_WORKSPACE
    try:
        relative = resolved.relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return OUTSIDE_WORKSPACE
    return relative.as_posix() or "."


def declaration_digest(path: Path | str | None) -> Optional[str]:
    """配置 / 声明文件的 sha256（sha256: 前缀）；读不到返回 None。

    与 validators.registry.config_digest() **同算法**（同一个值来源的口径由
    tests/contract/test_reading_context_digest_parity.py 逐字符钉住）——
    这里不 import 验证器层，是因为本模块要能在"没有 src 也能跑"的工具里被调用
    （tools/dsh_sandbox_loop.py 就是这一类）。
    """

    if path is None:
        return None
    target = Path(path)
    try:
        if not target.is_file():
            return None
        return "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        return None


# --------------------------------------------------------------------------- 子块


def unavailable(reason: str) -> dict:
    """读不到：**必须**带一句可读的 reason（三态纪律）。"""

    return {"status": STATUS_UNAVAILABLE, "reason": reason}


def not_applicable() -> dict:
    """不适用：这条路径上没有这个东西（**不是**读不到）。"""

    return {"status": STATUS_NOT_APPLICABLE}


def declaration_block(path: Path | str, *, root: Path | str) -> dict:
    """一份声明 / 输入文件的位置与内容摘要（status / path / digest）。"""

    target = Path(path)
    display = display_path(target, root=root)
    digest = declaration_digest(target)
    if digest is None:
        return unavailable("声明文件读不到：" + display)
    return {"status": STATUS_AVAILABLE, "path": display, "digest": digest}


def git_revision(root: Path | str) -> Optional[str]:
    """git rev-parse HEAD；取不到返回 None（不猜、不兜底）。"""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    if completed.returncode != 0 or not _REVISION.fullmatch(value):
        return None
    return value


def tree_block(
    root: Path | str,
    *,
    scope: str = SCOPE_WORKSPACE,
    revision_root: Path | str | None = None,
    digest: str | None = None,
) -> dict:
    """这棵树是哪一棵：轮次级封条 + git 修订号。

    digest 给定时**沿用调用方已经算过的那个值**（不另算一遍）：义务门禁本来就要算树摘要，
    这里再走一遍遍历既慢又可能给出第二个值。取值形如 sha256:... 或 unprovable:...
    （后者按"读不到"处理，并把它原样写进 reason）。

    用 provenance.worktree.workspace_tree_digest（方案 §3.1 的轮次级封条）而**不是**
    evidence_tree_digest：后者不带排除项，实测在本仓库要走 20339 个文件 / 53.6 s
    （含 .venv 与 .tmp），既慢又**不稳定**——.tmp 一写指纹就变，与"哪棵树"的语义相反。
    排除项是声明的（DEFAULT_EXCLUDES），所以同一棵树上的读数稳定、可复核。
    """

    block: dict[str, Any] = {"scope": scope}
    value = digest
    if value is None:
        try:
            value = workspace_tree_digest(root).sha256
        except (ProvenanceError, OSError, ValueError) as error:
            return {
                "status": STATUS_UNAVAILABLE,
                "scope": scope,
                "reason": "树摘要读不到：" + type(error).__name__ + ": " + str(error),
            }
    if not str(value).startswith("sha256:"):
        return {
            "status": STATUS_UNAVAILABLE,
            "scope": scope,
            "reason": "树摘要不可用：" + str(value),
        }
    block["digest"] = str(value)

    revision = git_revision(revision_root if revision_root is not None else root)
    if revision is None:
        return {
            **block,
            "status": STATUS_UNAVAILABLE,
            "reason": "读不到 git 修订号（该目录不是 git 工作树，或 git 不可用）",
        }
    block["revision"] = revision
    block["status"] = STATUS_AVAILABLE
    return block


def _platform_label() -> str:
    """宿主标签：<系统>-<发行版>（例如 Windows-11）；读不到写 unknown。"""

    try:
        system = _platform.system() or "unknown"
        release = _platform.release() or "unknown"
    except Exception:  # noqa: BLE001 - 读数不该让整份载荷写不出来
        return "unknown"
    return system + "-" + release


def host_block(*, sandbox: str = SANDBOX_UNKNOWN, extra: Mapping[str, Any] | None = None) -> dict:
    """哪一个环境、哪一台宿主。

    sandbox 只报事实，**判据由调用点给出**（21 号 §9.1 裁定①：不单独设状态轴）：
    端到端读数按"本次是否发生过工作区之外的操作被拒"判；其余读数不探测沙箱（探测要有副作用），
    一律 unknown。extra 放该读数专有的宿主事实（例如端到端的
    isolated_home / dsh_home / temp_roots）。
    """

    if sandbox not in SANDBOX_VALUES:
        raise ValueError(
            "未知 host.sandbox 取值 " + repr(sandbox) + "：只接受 " + " / ".join(SANDBOX_VALUES)
        )
    block: dict[str, Any] = {
        "platform": _platform_label(),
        "python": _platform.python_version(),
        "sandbox": sandbox,
    }
    if extra:
        block.update(dict(extra))
    return block


def run_block(*, started_at: str | None = None, run_id: str | None = None) -> dict:
    """本次运行自己的标识（**只在读数层**；这就是"逐字节相同"那条纪律要挡的东西）。"""

    return {
        "id": run_id if run_id else str(uuid.uuid4()),
        "started_at": started_at if started_at else utc_now(),
    }


def build(
    *,
    source: str,
    tree: Mapping[str, Any] | None = None,
    declarations: Mapping[str, Mapping[str, Any]] | None = None,
    host: Mapping[str, Any] | None = None,
    run: Mapping[str, Any] | None = None,
    include_run: bool = True,
) -> dict:
    """按统一形状组装一份 reading_context（顺序无关）。

    source / tree / declarations / host 四个恒定；第五个 `run` 是**有条件的**：它带"本次运行"
    的标识，凡是被要求"相同输入得到逐字节相同输出"的载荷都必须显式 `include_run=False`
    （2026-09-30 裁定①；落点是 policy.check --json）。默认 True，其余读数照旧带 run。
    给了 run 又要求不带它 = 自相矛盾：**报错**，不静默丢掉调用方给的值。
    """

    if source not in SOURCES:
        raise ValueError("未知 source " + repr(source) + "：只接受 " + " / ".join(SOURCES))
    if not include_run and run is not None:
        raise ValueError("include_run=False 与 run=... 自相矛盾：不带 run 的载荷不该有人传 run")
    block: dict[str, Any] = {
        "source": source,
        "tree": dict(tree) if tree is not None else unavailable("调用点没有给出树归属"),
        "declarations": {str(name): dict(value) for name, value in (declarations or {}).items()},
        "host": dict(host) if host is not None else host_block(),
    }
    if include_run:
        block["run"] = dict(run) if run is not None else run_block()
    return block
