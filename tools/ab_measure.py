#!/usr/bin/env python3
r"""AB 独立测量仪器：把六个量变成**任何一棵树上都能重算**的读数。

它回答什么
==========

| 量 | 载荷键 | 一句话口径 |
| --- | --- | --- |
| 规范性 | scanner | 冻结配置下的 ruff（**不读** validation/ruff.toml）在全树 / 改动行上的 finding |
| 安全性 | security | 独立安全扫描器优先；本机装不上 -> ruff 的 S 子集 + 自写标准库 AST 检查器 |
| 可用性 | usability | 外部 oracle：pytest 的逐用例结果 + 模块可导入性 + 公开 API 前后差集 |
| 精确 | block_precision | **反事实**：被拦下的编辑在隔离子树里重放，独立仪器是否变红 |
| 高效 | efficiency | 单次判定延迟 p50/p95（最近秩法、剔首个冷启动）、每任务 wall-clock 增量 |
| 全自动化 | automation | 受治理写动作覆盖率、bypass 计数、人工介入次数（**操纵检查**） |

三条不许破的纪律
================

1. **R1 不许自证**：本工具**没有一条路径**读平台的 Decision / violation / severity / 规则集。
   红绿标签只来自冻结配置的 ruff、自写 AST 检查器、pytest 与测试结果。
   independence.measured_tree_reads 与 independence.policy_imports 是这件事的**可核查**证据；
2. **缺东西写 unavailable，绝不写 0**：装不上 / 没给输入 / 字段缺失都进 unavailable[]，
   逐条带 reason 与 hint。0 与"没有数据"在载荷里是两种不同的形状；
3. **独立的是策略层，不是底层 linter**：规范性、安全回退、独立性三处的读数是同一条
   ruff 二进制产出的——这一句写在**每一个块**里（homology），不许只写一次了事。

退出码
======

==== ==========================================================
0    跑完，每个请求的量都 available 且没有 red
1    跑完，但有 unavailable 或 red（顶层 exit_reasons[] 说明原因）
2    用法 / 配置错误，**拒绝运行、不产出读数**
==== ==========================================================

载荷带 schema_version（本载荷自己的轴）+ reading_context（source="cli"：
src/provenance/reading_context.py 的 SOURCES 是闭集，"CLI 调用"这个语义已经准确，
不为此扩枚举）。

注：--deterministic 去掉 reading_context.run 并把计时块标 not_applicable；
**只有** --deterministic --mode scan,usable,security,blocked 这一组承诺相同输入逐字节相同。
带计时的载荷承诺逐字节相同是假的，本工具不承诺。
"""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import math
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
import time
import uuid
import warnings
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from provenance import reading_context as reading  # noqa: E402
from provenance.worktree import ProvenanceError, workspace_tree_digest  # noqa: E402

# --------------------------------------------------------------------------- 版本与常量

#: 本载荷（--json 的顶层对象）自己的版本轴。键集合或语义变了就动它（AGENTS 第 55 条）。
#: 1.0 = 首版固定形状；1.1 = pytest 分类修缮（2026-10-07，红队实测 .tmp/ab-measure/recheck.json）：
#:   新增键 classification_trustworthy / internal_errors / internal_error_source，
#:   并改语义——**先看证据（exit_code + 逐用例条数）再看文本**，三者不自洽时不给结论。
SCHEMA_VERSION = "1.1"

TOOL_ID = "ab_measure"
TOOL_VERSION = "1.0"

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_APPLICABLE = "not_applicable"

#: 仪器**自带**的冻结配置。--config <path> 单独使用即可压掉目标树里的配置发现：
#: 本机实测（ruff 0.14.13）把目标树里的 ruff.toml 换成诱饵配置（select=["F401"]、
#: line-length=200）后，--config <file> 仍按这里的口径报出 E501(>88) 与 W291；
#: 而 --config "key = value" 形态**会**让诱饵的 line-length 漏进来（实测 E501 消失）。
#: 所以：只用路径形态。--isolated 与 --config 同用会被 ruff 直接拒绝（RC=2，实测）。
FROZEN_PROFILES: Mapping[str, Mapping[str, Any]] = {
    "norm": {
        "id": "ab-norm-freeze/1",
        "select": "E,W,F",
        "line_length": 88,
        "target_version": "py311",
        "why": (
            "pycodestyle + pyflakes 的上游基线（ruff 默认规则集的超集）。"
            "line-length=88 是上游默认值，**不是**本仓库 validation/ruff.toml 的 100——"
            "两者不可直接比较，这是刻意保留的口径差。"
        ),
    },
    "sec": {
        "id": "ab-sec-freeze/1",
        "select": "S",
        "line_length": 88,
        "target_version": "py311",
        "why": (
            "flake8-bandit 的确定性出口（ruff 的 S 族）。它与 scanner 块同源："
            "同一条 ruff 二进制，因此只能算半同源。"
        ),
    },
}

#: 独立安全扫描器的安装探测顺序（路线 A）。全部拿不到时走路线 B 回退。
SECURITY_SCANNERS: Sequence[Mapping[str, Any]] = (
    {
        "name": "bandit",
        "argv": ("bandit", "-r", "-f", "json", "-q", "<tree>"),
        "version_argv": ("bandit", "--version"),
        "why": "独立实现（AST + 插件），与 ruff 不同源；覆盖的 CWE 面比 ruff 的 S 族宽。",
    },
    {
        "name": "semgrep",
        "argv": ("semgrep", "--json", "--quiet", "--config", "auto", "<tree>"),
        "version_argv": ("semgrep", "--version"),
        "why": "规则库 + 跨函数模式匹配；本机需要联网取规则，网络不可用时不可得。",
    },
)

#: 走目录遍历时明确排除的目录名（仪器自己的口径，与 ruff 默认排除取并集）。
DEFAULT_EXCLUDES = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    ".tox",
    ".tmp",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".eggs",
    "node_modules",
    "build",
    "dist",
    "site-packages",
)

#: 平台的策略层落在被测树里的这些前缀下。仪器**从不打开**它们——
#: measured_tree_reads 是这件事的可核查证据。
POLICY_LAYER_PREFIXES = ("policies/", "validation/", "knowledge/", "registry/", "adapters/")

_PARSE_ERROR_CODES = ("invalid-syntax", "E902", "syntax-error")

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WIN_ABS = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]*")
_POSIX_ABS = re.compile(r"(?<![\w.])/(?:[^\s\"'<>|/]+/)+[^\s\"'<>|]*")
_MESSAGE_LIMIT = 300

_SECRET_NAME = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api_?key|apikey|private_?key|access_?key|credential)"
)
_PLACEHOLDER = re.compile(
    r"(?i)^(<.*>|\{\{.*\}\}|x{3,}|\*{3,}|change.?me|example|placeholder|dummy|your[_-].*"
    r"|none|null|test|todo)$"
)


# --------------------------------------------------------------------------- 小工具


def sha256_bytes(payload: bytes) -> str:
    """字节串的 sha256: 前缀摘要。"""

    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    """文本按 UTF-8 编码后的摘要（换行先归一成 LF）。"""

    return sha256_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def utc_now() -> str:
    """本工具自己的墙钟（只在读数层，绝不进任何判定）。"""

    return reading.utc_now()


def sanitize(text: object, *, root: Optional[Path] = None, limit: int = _MESSAGE_LIMIT) -> str:
    """脱敏：控制字符去掉、绝对路径折掉、长度截断。

    只保留可读摘要，不放正文、不放绝对路径（AGENTS 第 16/34 条的脱敏纪律）。
    """

    value = "" if text is None else str(text)
    value = _CONTROL_CHARS.sub(" ", value)
    if root is not None:
        root_text = str(root)
        value = value.replace(root_text + os.sep, "").replace(root_text + "/", "")
    value = _WIN_ABS.sub("<abs>", value)
    value = _POSIX_ABS.sub("<abs>", value)
    value = value.replace("\\", "/")
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        value = value[: limit - 3] + "..."
    return value


def rel_posix(path: Path, *, root: Path) -> str:
    """树内相对 POSIX 路径；树外写 <outside-tree>（不放绝对路径）。"""

    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except (OSError, ValueError):
        return "<outside-tree>"


def display_root(root: Optional[Path]) -> str:
    """被测树本身的显示名：仓库内写相对路径，仓库外不泄露绝对路径。"""

    if root is None:
        return "<unset>"
    return reading.display_path(root, root=REPO)


def count_physical_lines(payload: bytes) -> int:
    """物理行数（含空行与注释）：KLOC 的分母就是它。"""

    if not payload:
        return 0
    lines = payload.count(b"\n")
    if not payload.endswith(b"\n"):
        lines += 1
    return lines


def json_dumps(payload: object) -> str:
    """稳定序列化：键排序、UTF-8、LF、单换行结尾。"""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------- 统计


Z_95 = 1.959963984540054


def wilson(successes: int, total: int, *, z: float = Z_95) -> Optional[list]:
    """Wilson 95% 区间（比例的唯一口径）；total == 0 返回 None（样本不足）。"""

    if total <= 0:
        return None
    phat = successes / total
    denominator = 1.0 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    spread = (
        z
        * math.sqrt(phat * (1.0 - phat) / total + z * z / (4 * total * total))
        / denominator
    )
    return [round(max(0.0, centre - spread), 6), round(min(1.0, centre + spread), 6)]


def nearest_rank(sorted_samples: Sequence[float], percentile: float) -> Optional[float]:
    """最近秩法分位数（不插值）：ceil(p/100 * n) 号样本，1-based。"""

    if not sorted_samples:
        return None
    rank = max(1, math.ceil(percentile / 100.0 * len(sorted_samples)))
    return round(float(sorted_samples[rank - 1]), 3)


def median(sorted_samples: Sequence[float]) -> Optional[float]:
    """中位数（偶数个取两中间值的平均）。"""

    if not sorted_samples:
        return None
    size = len(sorted_samples)
    middle = size // 2
    if size % 2 == 1:
        return round(float(sorted_samples[middle]), 3)
    return round((float(sorted_samples[middle - 1]) + float(sorted_samples[middle])) / 2.0, 3)


def paired_sign_test(deltas: Sequence[float]) -> dict:
    """配对符号检验（精确二项、双尾）。零差丢弃并如实计数。"""

    nonzero = [value for value in deltas if value != 0]
    positives = sum(1 for value in nonzero if value > 0)
    size = len(nonzero)
    if size == 0:
        return {
            "n": 0,
            "positive": 0,
            "negative": 0,
            "zero_dropped": len(deltas),
            "p_value": None,
        }
    tail = sum(math.comb(size, k) for k in range(0, min(positives, size - positives) + 1))
    p_value = min(1.0, 2.0 * tail / (2**size))
    return {
        "n": size,
        "positive": positives,
        "negative": size - positives,
        "zero_dropped": len(deltas) - size,
        "p_value": round(p_value, 6),
    }


# --------------------------------------------------------------------------- 读数登记


class ReadLedger:
    """记录**本仪器自己**打开过的、被测树内的每一个路径。

    这是"仪器独立于策略层"的可核查证据：如果它读了 policies/**，这份清单里就会出现那个路径。
    外部子进程（ruff / pytest）读什么由它们的 argv 决定，本清单**不覆盖**它们——
    这句话本身也写在载荷里，免得读者以为它覆盖了。
    """

    def __init__(self, root: Optional[Path]) -> None:
        self.root = root
        self.paths: set = set()

    def note(self, path: Path) -> None:
        """登记一次读取（树外路径折叠成 <outside-tree>）。"""

        if self.root is None:
            return
        self.paths.add(rel_posix(Path(path), root=self.root))

    def as_list(self) -> list:
        """排序后的清单（确定性）。"""

        return sorted(self.paths)


READS = ReadLedger(None)
SUBCOMMANDS: list = []


def read_bytes(path: Path) -> bytes:
    """读文件字节，并把它记进本仪器的读取账。"""

    READS.note(Path(path))
    return Path(path).read_bytes()


def run_command(
    argv: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: float = 300.0,
    stdin_bytes: Optional[bytes] = None,
) -> dict:
    """跑一条外部命令，返回结构化结果（**不改任何 allow/block**）。

    只跑 argv 数组，绝不过 shell：参数里的引号 / 管道 / 分号因此不构成注入面，
    命令也能被第二个人逐字复核。
    """

    SUBCOMMANDS.append(
        {
            "argv": [sanitize(part, root=cwd) for part in argv],
            "cwd": display_root(cwd) if cwd else "<unset>",
        }
    )
    started = time.perf_counter()
    try:
        completed = subprocess.run(  # noqa: S603 - argv 数组、无 shell、超时终止
            list(argv),
            cwd=str(cwd) if cwd else None,
            env=dict(env) if env is not None else None,
            input=stdin_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "可执行文件不存在：" + sanitize(error, root=cwd),
            "argv": list(argv),
        }
    except subprocess.TimeoutExpired:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "命令超时（" + str(timeout) + " 秒）：" + sanitize(argv[0], root=cwd),
            "argv": list(argv),
        }
    except OSError as error:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "命令起不来：" + sanitize(error, root=cwd),
            "argv": list(argv),
        }
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "status": STATUS_AVAILABLE,
        "exit_code": completed.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout": completed.stdout.decode("utf-8", errors="replace"),
        "stderr": completed.stderr.decode("utf-8", errors="replace"),
        "argv": list(argv),
    }


# --------------------------------------------------------------------------- 树遍历


def iter_python_files(tree: Path, extra_excludes: Iterable[str] = ()) -> list:
    """按相对路径排序的全部 *.py（排除目录名取 DEFAULT_EXCLUDES 并上 extra）。"""

    excluded = set(DEFAULT_EXCLUDES) | {item.strip() for item in extra_excludes if item.strip()}
    found: list = []
    for current, dirnames, filenames in os.walk(tree):
        dirnames[:] = sorted(name for name in dirnames if name not in excluded)
        for name in sorted(filenames):
            if name.endswith(".py"):
                found.append(Path(current) / name)
    found.sort(key=lambda item: rel_posix(item, root=tree))
    return found


def tree_facts(tree: Path, extra_excludes: Iterable[str] = ()) -> dict:
    """被扫描文件的清单 + KLOC 分母（分子/分母必须来自同一批文件）。"""

    files = iter_python_files(tree, extra_excludes)
    total_lines = 0
    for path in files:
        try:
            total_lines += count_physical_lines(read_bytes(path))
        except OSError:
            continue
    return {
        "files": files,
        "file_count": len(files),
        "physical_lines": total_lines,
        "kloc": round(total_lines / 1000.0, 6),
    }


# --------------------------------------------------------------------------- 冻结配置


def frozen_config_text(profile: str) -> str:
    """冻结配置的 TOML 文本（**内嵌**，不来自被测树、不来自仓库）。"""

    spec = FROZEN_PROFILES[profile]
    codes = ", ".join(json.dumps(code) for code in str(spec["select"]).split(","))
    lines = [
        "# " + str(spec["id"]) + " —— 由 tools/ab_measure.py 内嵌生成，不读仓库配置。",
        "# " + str(spec["why"]),
        "line-length = " + str(spec["line_length"]),
        "target-version = " + json.dumps(spec["target_version"]),
        "",
        "[lint]",
        "select = [" + codes + "]",
        "",
    ]
    return "\n".join(lines)


def materialize_config(profile: str, workdir: Path) -> dict:
    """把冻结配置写到 .tmp 下并返回路径与摘要。"""

    text = frozen_config_text(profile)
    path = workdir / ("ab-frozen-" + profile + ".toml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return {
        "path": path,
        "digest": sha256_text(text),
        "profile_id": FROZEN_PROFILES[profile]["id"],
        "select": FROZEN_PROFILES[profile]["select"],
        "line_length": FROZEN_PROFILES[profile]["line_length"],
    }


# --------------------------------------------------------------------------- ruff 读数


def ruff_version(ruff: str) -> dict:
    """ruff 的版本读数；拿不到就 unavailable（不猜）。"""

    result = run_command([ruff, "--version"], timeout=30.0)
    if result["status"] != STATUS_AVAILABLE or result.get("exit_code") != 0:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": sanitize(result.get("reason", "ruff --version 失败")),
        }
    match = re.search(r"(\d+\.\d+\.\d+)", result["stdout"])
    if not match:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "无法从 ruff --version 解析版本号：" + sanitize(result["stdout"]),
        }
    return {"status": STATUS_AVAILABLE, "version": match.group(1)}


def normalize_finding(raw: Mapping[str, Any], *, tree: Path, cwd: Path) -> dict:
    """把 ruff 的 JSON finding 归一成仪器的三元组（路径 / 码 / 行）。"""

    filename = str(raw.get("filename") or "")
    location = raw.get("location") or {}
    return {
        "file": rel_posix(Path(filename), root=tree) if filename else "<unknown>",
        "row": int(location.get("row") or 0),
        "col": int(location.get("column") or 0),
        "code": str(raw.get("code") or ""),
        "message": sanitize(raw.get("message"), root=cwd),
    }


def is_parse_error(code: str) -> bool:
    """这个码是不是"ruff 没能分析这个文件"（不是代码缺陷，单独一档）。"""

    return code in _PARSE_ERROR_CODES


def run_ruff_profile(
    *,
    tree: Path,
    files: Sequence[Path],
    ruff: str,
    config: Mapping[str, Any],
    workdir: Path,
    chunk_size: int = 200,
) -> dict:
    """按冻结配置扫描给定文件清单，返回归一化 finding。

    **逐文件显式传参**而不是传目录：传目录时 ruff 的 --exclude 相对哪个"项目根"解析
    取决于配置文件位置，会让"我数的文件"与"ruff 扫的文件"出现两个口径。
    分成小块是因为 Windows 命令行有长度上限。
    """

    if not files:
        return {
            "status": STATUS_AVAILABLE,
            "findings": [],
            "runs": [],
            "note": "文件清单为空：没有可扫描的目标（不是失败）。",
        }
    findings: list = []
    runs: list = []
    targets = list(files)
    chunks = [targets[index : index + chunk_size] for index in range(0, len(targets), chunk_size)]
    for chunk in chunks:
        argv = [
            ruff,
            "check",
            "--config",
            str(config["path"]),
            "--output-format",
            "json",
            "--no-cache",
            "--no-respect-gitignore",
            "--quiet",
            *[str(item) for item in chunk],
        ]
        result = run_command(argv, cwd=workdir, timeout=900.0)
        if result["status"] != STATUS_AVAILABLE:
            return {"status": STATUS_UNAVAILABLE, "reason": result["reason"], "runs": runs}
        if result.get("exit_code") not in (0, 1):
            return {
                "status": STATUS_UNAVAILABLE,
                "reason": "ruff 退出码 " + str(result.get("exit_code")) + "："
                + sanitize(result.get("stderr")),
                "runs": runs,
            }
        runs.append({"argv": result["argv"], "exit_code": result["exit_code"], "files": len(chunk)})
        text = result["stdout"].strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            return {
                "status": STATUS_UNAVAILABLE,
                "reason": "ruff JSON 解析失败：" + sanitize(error),
                "runs": runs,
            }
        if not isinstance(payload, list):
            return {"status": STATUS_UNAVAILABLE, "reason": "ruff JSON 不是数组", "runs": runs}
        for item in payload:
            findings.append(normalize_finding(item, tree=tree, cwd=workdir))
    findings.sort(key=lambda item: (item["file"], item["row"], item["col"], item["code"]))
    return {"status": STATUS_AVAILABLE, "findings": findings, "runs": runs}


def bucket_by_code(findings: Sequence[Mapping[str, Any]]) -> dict:
    """按码计数（键排序，确定性）。"""

    counts: dict = {}
    for item in findings:
        code = str(item.get("code") or "<none>")
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items()))


def split_parse_errors(findings: Sequence[Mapping[str, Any]]) -> tuple:
    """把"没能分析这个文件"从"代码缺陷"里分出来（两件事，两个数）。"""

    defects = [item for item in findings if not is_parse_error(str(item.get("code")))]
    parse_errors = [item for item in findings if is_parse_error(str(item.get("code")))]
    return defects, parse_errors


# --------------------------------------------------------------------------- 自写 AST 安全检查器
#
# 它是**第二实现**，不是第二**独立检查**：与 ruff 共享 CPython 的 ast 模块，覆盖面也窄得多
# （无 taint、无数据流、无跨文件、无依赖漏洞）。仪器把它标成 S2（未校准的第二实现），
# 绝不把它写成"独立安全扫描"。

SECURITY_RULES: Sequence[Mapping[str, str]] = (
    {"id": "ABSEC-001", "title": "eval/exec/compile 作用于非字面量", "why": "任意代码执行"},
    {"id": "ABSEC-002", "title": "subprocess 调用带 shell=True", "why": "命令注入"},
    {"id": "ABSEC-003", "title": "os.system / os.popen 直接执行字符串", "why": "命令注入"},
    {"id": "ABSEC-004", "title": "反序列化不可信数据（pickle/marshal/dill/shelve）", "why": "反序列化 RCE"},
    {"id": "ABSEC-005", "title": "yaml.load 未指定 SafeLoader", "why": "YAML 反序列化 RCE"},
    {"id": "ABSEC-006", "title": "MD5 / SHA1 用于安全场景", "why": "弱哈希"},
    {"id": "ABSEC-007", "title": "tempfile.mktemp 的竞态", "why": "TOCTOU"},
    {"id": "ABSEC-008", "title": "调用点显式关闭 TLS 校验（verify=False）", "why": "中间人"},
    {"id": "ABSEC-009", "title": "硬编码凭据字面量", "why": "凭据泄露"},
    {"id": "ABSEC-010", "title": "SQL 由 f-string / % / format 拼进 execute", "why": "SQL 注入"},
)

_UNSAFE_YAML_LOADERS = ("Loader", "UnsafeLoader", "FullLoader", "CUnsafeLoader", "yaml.Loader")
_WEAK_HASHES = ("md5", "sha1")
_DESERIALIZERS = (
    "pickle.load",
    "pickle.loads",
    "marshal.loads",
    "dill.loads",
    "dill.load",
    "shelve.open",
    "jsonpickle.decode",
)
_SHELL_RUNNERS = ("os.system", "os.popen", "os.spawnl", "os.spawnv", "commands.getoutput")


def _dotted(node: Optional[ast.AST]) -> str:
    """把 Name / Attribute 链写成点号名字（解析不出来就返回空串）。"""

    parts: list = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    else:
        return ""
    return ".".join(reversed(parts))


def _const_str(node: Optional[ast.AST]) -> Optional[str]:
    """常量字符串取值（不是字符串常量就返回 None）。"""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_true(node: Optional[ast.AST]) -> bool:
    """是不是字面量 True。"""

    return isinstance(node, ast.Constant) and node.value is True


def _is_false(node: Optional[ast.AST]) -> bool:
    """是不是字面量 False。"""

    return isinstance(node, ast.Constant) and node.value is False


def _keyword(call: ast.Call, name: str) -> Optional[ast.AST]:
    """取关键字参数的值（没有这个关键字返回 None）。"""

    for item in call.keywords:
        if item.arg == name:
            return item.value
    return None


def _security_finding(path_rel: str, node: ast.AST, code: str, message: str) -> dict:
    """构造一条与 ruff finding 同形状的安全发现。"""

    return {
        "file": path_rel,
        "row": int(getattr(node, "lineno", 0) or 0),
        "col": int(getattr(node, "col_offset", 0) or 0) + 1,
        "code": code,
        "message": sanitize(message),
    }


def _check_call(call: ast.Call, path_rel: str) -> list:
    """一条 Call 上的全部检查。"""

    found: list = []
    name = _dotted(call.func)
    first = call.args[0] if call.args else None

    if name in ("eval", "exec", "compile") and not isinstance(first, ast.Constant):
        found.append(_security_finding(path_rel, call, "ABSEC-001", name + " 的参数不是字面量"))
    if name.startswith("subprocess.") and _is_true(_keyword(call, "shell")):
        found.append(_security_finding(path_rel, call, "ABSEC-002", name + "(shell=True)"))
    if name in _SHELL_RUNNERS:
        found.append(_security_finding(path_rel, call, "ABSEC-003", name + " 直接执行字符串"))
    if name in _DESERIALIZERS:
        found.append(_security_finding(path_rel, call, "ABSEC-004", name + " 反序列化不可信数据"))
    if name in ("yaml.load", "yaml.unsafe_load"):
        loader = _dotted(_keyword(call, "Loader")) or _dotted(_keyword(call, "loader"))
        unsafe = name == "yaml.unsafe_load" or not loader or loader in _UNSAFE_YAML_LOADERS
        if unsafe:
            found.append(
                _security_finding(path_rel, call, "ABSEC-005", name + " 未使用 SafeLoader")
            )
    weak = name in ("hashlib." + item for item in _WEAK_HASHES)
    if name == "hashlib.new" and _const_str(first) in _WEAK_HASHES:
        weak = True
    if weak:
        found.append(_security_finding(path_rel, call, "ABSEC-006", name + " 是弱哈希"))
    if name == "tempfile.mktemp":
        found.append(_security_finding(path_rel, call, "ABSEC-007", "tempfile.mktemp 有竞态"))
    if _is_false(_keyword(call, "verify")):
        found.append(_security_finding(path_rel, call, "ABSEC-008", "verify=False 关闭了 TLS 校验"))
    if name.endswith(".execute") and first is not None:
        dynamic = isinstance(first, ast.JoinedStr) or (
            isinstance(first, ast.BinOp) and isinstance(first.op, ast.Mod)
        )
        if isinstance(first, ast.Call) and isinstance(first.func, ast.Attribute):
            dynamic = dynamic or first.func.attr == "format"
        if dynamic:
            found.append(
                _security_finding(path_rel, call, "ABSEC-010", name + " 的 SQL 由字面量拼接")
            )
    return found


def _check_assignment(node: ast.AST, path_rel: str) -> list:
    """赋值节点上的硬编码凭据检查。"""

    targets: list = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
        value = node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        targets = [node.target]
        value = node.value
    else:
        return []
    text = _const_str(value)
    if text is None or len(text) < 8 or _PLACEHOLDER.match(text):
        return []
    for target in targets:
        if isinstance(target, ast.Name) and _SECRET_NAME.search(target.id):
            return [
                _security_finding(
                    path_rel, node, "ABSEC-009", "名字像凭据的变量被赋了字符串字面量"
                )
            ]
    return []


def scan_security_ast(tree: Path, files: Sequence[Path]) -> dict:
    """跑自写 AST 安全检查器；语法错误单独一档（不是安全发现）。"""

    findings: list = []
    parse_errors: list = []
    for path in files:
        rel = rel_posix(path, root=tree)
        try:
            source = read_bytes(path).decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            parse_errors.append({"file": rel, "reason": "读不到：" + sanitize(error)})
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                module = ast.parse(source, filename=rel)
        except SyntaxError as error:
            parse_errors.append(
                {"file": rel, "reason": "语法错误：" + sanitize(error.msg) + " @" + str(error.lineno)}
            )
            continue
        for node in ast.walk(module):
            if isinstance(node, ast.Call):
                findings.extend(_check_call(node, rel))
            else:
                findings.extend(_check_assignment(node, rel))
    findings.sort(key=lambda item: (item["file"], item["row"], item["col"], item["code"]))
    return {"status": STATUS_AVAILABLE, "findings": findings, "parse_errors": parse_errors}


# --------------------------------------------------------------------------- 改动行口径


def iter_all_files(tree: Path, extra_excludes: Iterable[str] = ()) -> list:
    """树内全部普通文件（按相对路径排序），用于逐行 diff。"""

    excluded = set(DEFAULT_EXCLUDES) | {item.strip() for item in extra_excludes if item.strip()}
    found: list = []
    for current, dirnames, filenames in os.walk(tree):
        dirnames[:] = sorted(name for name in dirnames if name not in excluded)
        for name in sorted(filenames):
            found.append(Path(current) / name)
    return found


def _decode_lines(payload: bytes) -> Optional[list]:
    """按 UTF-8 解成行表；不是文本就返回 None（二进制不参与行级口径）。"""

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.splitlines()


def changed_lines_from_trees(base: Path, tree: Path, extra_excludes: Iterable[str] = ()) -> dict:
    """逐行 diff 出 new-side 的 + 行集合（行级口径的主实现，标准库 difflib）。"""

    base_map = {rel_posix(item, root=base): item for item in iter_all_files(base, extra_excludes)}
    tree_map = {rel_posix(item, root=tree): item for item in iter_all_files(tree, extra_excludes)}
    result: dict = {}
    for rel in sorted(set(base_map) | set(tree_map)):
        old_path = base_map.get(rel)
        new_path = tree_map.get(rel)
        if old_path is None:
            lines = _decode_lines(read_bytes(new_path)) if new_path else None
            result[rel] = {
                "lines": list(range(1, len(lines) + 1)) if lines else [],
                "whole_file": True,
                "reason": "new_file",
            }
            continue
        if new_path is None:
            result[rel] = {"lines": [], "whole_file": False, "reason": "deleted"}
            continue
        old_bytes = read_bytes(old_path)
        new_bytes = read_bytes(new_path)
        if old_bytes == new_bytes:
            continue
        old_lines = _decode_lines(old_bytes)
        new_lines = _decode_lines(new_bytes)
        if old_lines is None or new_lines is None:
            result[rel] = {"lines": [], "whole_file": True, "reason": "binary_or_not_utf8"}
            continue
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
        touched: set = set()
        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
            if tag in ("replace", "insert"):
                touched.update(range(j1 + 1, j2 + 1))
        result[rel] = {"lines": sorted(touched), "whole_file": False, "reason": "diff"}
    return result


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_TARGET = re.compile(r"^\+\+\+ (?:b/)?(.*)$")


def parse_unified_diff(diff_text: str) -> dict:
    """解析 unified diff：每个文件的 new-side + 行号、hunk、以及可应用的替换序列。"""

    files: dict = {}
    current: Optional[str] = None
    cursor = 0
    pending: list = []

    def flush() -> None:
        if current is not None and pending:
            files.setdefault(current, {"lines": set(), "hunks": [], "is_new": False})
            files[current]["hunks"].extend(pending)

    for raw in diff_text.replace("\r\n", "\n").split("\n"):
        if raw.startswith("--- "):
            flush()
            pending = []
            continue
        match = _DIFF_TARGET.match(raw)
        if match:
            name = match.group(1).strip()
            name = name[2:] if name.startswith("b/") else name
            current = name
            if current not in files:
                files[current] = {"lines": set(), "hunks": [], "is_new": False}
            if raw.strip().endswith("/dev/null"):
                files[current]["is_new"] = False
            continue
        if raw.startswith("+++ "):
            continue
        header = _HUNK_HEADER.match(raw)
        if header and current is not None:
            cursor = int(header.group(3))
            pending.append({"old_start": int(header.group(1)), "start": cursor, "rows": []})
            continue
        if current is None or not pending:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            pending[-1]["rows"].append(["+" + raw[1:], cursor])
            files[current]["lines"].add(cursor)
            cursor += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            pending[-1]["rows"].append(["-" + raw[1:], None])
        elif raw.startswith(" "):
            pending[-1]["rows"].append([" " + raw[1:], cursor])
            cursor += 1
    flush()
    for entry in files.values():
        entry["lines"] = sorted(entry["lines"])
    return files


def apply_unified_diff(root: Path, parsed: Mapping[str, Any]) -> dict:
    """严格应用 unified diff：上下文对不上就整条失败（不猜、不模糊匹配）。"""

    applied: list = []
    failed: list = []
    for rel, entry in sorted(parsed.items()):
        target = root / rel
        original = target.read_bytes().decode("utf-8") if target.is_file() else ""
        lines = original.split("\n")
        offset = 0
        ok = True
        for hunk in entry["hunks"]:
            rows = hunk["rows"]
            old_rows = [row[0][1:] for row in rows if row[0][0] in (" ", "-")]
            new_rows = [row[0][1:] for row in rows if row[0][0] in (" ", "+")]
            start = hunk["old_start"] - 1 + offset
            if lines[start : start + len(old_rows)] != old_rows:
                ok = False
                break
            lines[start : start + len(old_rows)] = new_rows
            offset += len(new_rows) - len(old_rows)
        if not ok:
            failed.append({"file": rel, "reason": "hunk 上下文对不上"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines), encoding="utf-8", newline="")
        applied.append({"file": rel, "lines": entry["lines"]})
    return {"applied": applied, "failed": failed}


# --------------------------------------------------------------------------- 可用性：pytest oracle

PYTEST_PLUGIN_NAME = "abmeasure_report"
PYTEST_PLUGIN_SOURCE = r'''"""ab_measure 的逐用例结果导出插件（只写一行 JSON，不改测试行为）。"""

import json
import os

_STATE = {"tests": {}, "collected": [], "collect_errors": []}


def pytest_collection_finish(session):
    _STATE["collected"] = sorted(str(item.nodeid) for item in session.items)


def pytest_collectreport(report):
    if report.failed:
        _STATE["collect_errors"].append(str(report.nodeid))
        detail = getattr(report, "longrepr", None)
        if detail:
            _STATE["collect_errors"].append(str(detail)[:400])


def pytest_runtest_logreport(report):
    node = str(report.nodeid)
    entry = _STATE["tests"].setdefault(node, {"outcome": "passed", "phases": []})
    entry["phases"].append([str(report.when), str(report.outcome)])
    if report.outcome == "failed":
        entry["outcome"] = "failed" if report.when == "call" else "error"
    elif report.outcome == "skipped" and entry["outcome"] == "passed":
        entry["outcome"] = "skipped"


def pytest_sessionfinish(session, exitstatus):
    path = os.environ.get("AB_MEASURE_REPORT")
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(_STATE, handle, ensure_ascii=False, sort_keys=True)
'''


def write_pytest_plugin(workdir: Path) -> Path:
    """把逐用例结果插件写到 .tmp 下（不加依赖、不写被测树）。"""

    directory = workdir / "plugin"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (PYTEST_PLUGIN_NAME + ".py")
    path.write_text(PYTEST_PLUGIN_SOURCE, encoding="utf-8", newline="\n")
    return directory


def _declares_cache_dir(tree: Path) -> bool:
    """被测树自己声明了 cache_dir 吗（决定要不要摘掉 cache provider）。"""

    for name in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"):
        path = tree / name
        if not path.is_file():
            continue
        try:
            if "cache_dir" in path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def _oracle_env(
    tree: Path, plugin_dir: Path, report_path: Path, basetemp: Path, extra: Mapping,
    *, disable_cache: bool = True,
) -> dict:
    """oracle 的环境：白名单 + 显式 PYTHONPATH + 强制 basetemp（绕已知 ACL 问题）。"""

    env: dict = {}
    for key in (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SystemRoot",
        "COMSPEC",
        "WINDIR",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "LANG",
        "LC_ALL",
        "NUMBER_OF_PROCESSORS",
    ):
        if key in os.environ:
            env[key] = os.environ[key]
    parts = [str(plugin_dir), str(tree / "src"), str(tree)]
    if os.environ.get("PYTHONPATH"):
        parts.append(os.environ["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["AB_MEASURE_REPORT"] = str(report_path)
    # 两条路都要，因为 -p no:cacheprovider 会摘掉 cache provider，于是被测树 pytest.ini 里的
    # cache_dir 变成"未知配置项"→ pytest 退出码 4（本仓实测就是这个）。
    # 树里声明了 cache_dir ⇒ 保留插件、把缓存重定向到 .tmp；没声明 ⇒ 直接摘掉插件。
    addopts = "--basetemp=" + str(basetemp)
    if disable_cache:
        addopts += " -p no:cacheprovider"
    else:
        cache_dir = basetemp / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        addopts += " -o cache_dir=" + str(cache_dir)
    env["PYTEST_ADDOPTS"] = addopts
    for key, value in (extra or {}).items():
        env[str(key)] = str(value)
    return env


def _count_outcomes(tests: Mapping[str, Any]) -> dict:
    """逐用例结果 -> 计数。"""

    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for entry in tests.values():
        outcome = str(entry.get("outcome") or "unknown")
        counts[outcome] = counts.get(outcome, 0) + 1
    counts["total"] = len(tests)
    return counts


def run_pytest_oracle(
    *,
    tree: Path,
    oracle: Mapping[str, Any],
    workdir: Path,
    extra_args: Sequence[str] = (),
    timeout_s: float = 900.0,
) -> dict:
    """跑仓库自带测试：外部 oracle（U1，完全独立于策略层与 linter）。"""

    spec = oracle.get("test_command") or {}
    argv = [str(item) for item in (spec.get("argv") or [])]
    python = str(oracle.get("python") or sys.executable)
    if not argv:
        target = "tests" if (tree / "tests").is_dir() else "."
        argv = [python, "-m", "pytest", "-q", "--tb=no", target]
    cwd = tree / str(spec.get("cwd") or ".")
    if not cwd.is_dir():
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "oracle 的 cwd 不存在：" + str(spec.get("cwd")),
        }
    limit = float(spec.get("timeout_s") or timeout_s)
    plugin_dir = write_pytest_plugin(workdir)
    report_path = workdir / "pytest-report.json"
    basetemp = workdir / "pytest-tmp"
    if report_path.exists():
        report_path.unlink()
    full_argv = [
        *argv,
        "-p",
        PYTEST_PLUGIN_NAME,
        "--tb=no",
        *[str(item) for item in extra_args],
    ]
    env = _oracle_env(
        tree, plugin_dir, report_path, basetemp, spec.get("env") or {},
        disable_cache=not _declares_cache_dir(cwd),
    )
    result = run_command(full_argv, cwd=cwd, env=env, timeout=limit)
    if result["status"] != STATUS_AVAILABLE:
        return {"status": STATUS_UNAVAILABLE, "reason": result["reason"], "argv": full_argv}
    combined = result["stdout"] + "\n" + result["stderr"]
    report: dict = {"tests": {}, "collected": [], "collect_errors": []}
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {"tests": {}, "collected": [], "collect_errors": []}
    counts = _count_outcomes(report.get("tests") or {})
    exit_code = result.get("exit_code")
    # **先看证据，再看文本**（2026-10-07 修，红队实测 .tmp/ab-measure/recheck.json
    # run 93f2a560）：一次真跑了 2136 条用例、exit_code=1 的运行，因为输出里出现 INTERNALERROR
    # 文本，被旧版**优先**判成 environment_unavailable，于是同一份载荷里同时写着
    # "2132 passed" 与 "一次都没跑起来"。那是**读数错误**，不是措辞问题。
    internal = [line.strip() for line in combined.splitlines() if "INTERNALERROR" in line]
    internal_source = (
        "stdout"
        if any("INTERNALERROR" in line for line in result["stdout"].splitlines())
        else "stderr"
        if any("INTERNALERROR" in line for line in result["stderr"].splitlines())
        else "unknown"
    )
    disk_warnings = [
        line.strip()
        for line in combined.splitlines()
        if "WinError 5" in line or "Access is denied" in line or "PytestCacheWarning" in line
    ]
    ran = counts["total"] > 0
    collection_failure = exit_code == 5 and bool(report.get("collect_errors"))
    if not ran and exit_code == 0:
        status = "environment_unavailable"
        reason = "pytest 退出码 0 但逐用例结果是空的（0 个用例）——没有东西可测，不是结局。"
    elif not ran:
        status = "environment_unavailable"
        reason = (
            "pytest 没有产出任何逐用例结果（退出码 " + str(exit_code) + "）："
            + sanitize((result["stderr"] or result["stdout"])[-400:])
        )
    elif exit_code in (2, 3, 4):
        status = "environment_unavailable"
        reason = (
            "pytest 退出码 " + str(exit_code) + "（中断 / 内部错误 / 用法错误）："
            "虽然收集到 " + str(counts["total"]) + " 条逐用例结果，但这一次运行本身不完整，"
            "**不给可用性结论**：" + sanitize((result["stderr"] or result["stdout"])[-400:])
        )
    elif collection_failure:
        status = "red"
        reason = "收集期失败（pytest 退出码 5，collection_errors 非空）"
    elif exit_code == 5:
        status = "environment_unavailable"
        reason = (
            "pytest 退出码 5 且没有任何收集错误：这次**没有东西可跑**（选择器 / 路径不对），"
            "不是被测对象的红。"
        )
    elif exit_code == 0:
        status = "ok"
        reason = "全部通过"
    else:
        status = "red"
        reason = (
            "pytest 退出码 " + str(exit_code) + "：" + str(counts["failed"]) + " failed / "
            + str(counts["error"]) + " error / " + str(counts["passed"]) + " passed（共 "
            + str(counts["total"]) + " 条）"
        )
    # ---- 一致性守卫（红队给的最小判据：exit_code ↔ counts ↔ 措辞 必须互相蕴含）----
    # 三者不自洽时**不给结论**：宁可写"分类不可信"，也不产出"自己都不信自己"的读数。
    red_by_evidence = collection_failure or (exit_code == 1 and ran)
    trustworthy = (status == "red") == red_by_evidence
    if not trustworthy:
        detail = ""
        if internal:
            detail = (
                " 输出里出现 INTERNALERROR 文本（来源 " + internal_source + "），"
                "但退出码不是 3、且已经收集到逐用例结果 ⇒ 该文本**不能**作为环境归因的证据。"
            )
        status = "environment_unavailable"
        reason = (
            "分类不可信，本块不给结论：exit_code=" + str(exit_code) + "、逐用例结果 "
            + str(counts["total"]) + " 条、" + str(counts["failed"]) + " failed，"
            "与分类「" + reason + "」三者不自洽。" + detail
        )
    return {
        "classification_trustworthy": trustworthy,
        "internal_errors": [sanitize(item, root=tree, limit=200) for item in internal[:3]],
        "internal_error_source": internal_source if internal else None,
        "status": STATUS_AVAILABLE,
        "pytest_status": status,
        "reason": reason,
        "exit_code": exit_code,
        "argv": [sanitize(item, root=tree) for item in full_argv],
        "cwd": rel_posix(cwd, root=tree) if cwd != tree else ".",
        "timeout_s": limit,
        "counts": counts,
        "collected": sorted(str(item) for item in (report.get("collected") or [])),
        "collection_errors": list(report.get("collect_errors") or []),
        "disk_warnings": [sanitize(item, root=tree, limit=200) for item in disk_warnings[:5]],
        "tests": {str(key): str(value.get("outcome")) for key, value in (report.get("tests") or {}).items()},
        "stdout_tail": sanitize(result["stdout"][-1200:], root=tree, limit=1200),
        "stderr_tail": sanitize(result["stderr"][-1200:], root=tree, limit=1200),
    }


def normalize_nodeid(nodeid: str, tree: Path) -> str:
    """用例标识归一化：反斜杠转正斜杠、去掉指进被测树的绝对前缀。"""

    value = str(nodeid).replace("\\", "/")
    prefix = tree.resolve().as_posix()
    if value.startswith(prefix):
        value = value[len(prefix) :].lstrip("/")
    while value.startswith("./"):
        value = value[2:]
    return value


def _split_nodeid(nodeid: str) -> tuple:
    """nodeid -> (文件, 其余)；没有 :: 时其余为空。"""

    if "::" in nodeid:
        head, tail = nodeid.split("::", 1)
        return head, tail
    return nodeid, ""


def declared_outcomes(oracle: Mapping[str, Any], tests: Mapping[str, str], tree: Path) -> dict:
    """声明的 pass_to_pass / fail_to_pass 在本次结果里各自怎样。"""

    normalized = {normalize_nodeid(key, tree): value for key, value in tests.items()}
    result: dict = {}
    for key, field in (("pass_to_pass", "pass_to_pass"), ("fail_to_pass", "fail_to_pass")):
        declared = [normalize_nodeid(item, tree) for item in (oracle.get(field) or [])]
        if not declared:
            result[key] = {
                "status": STATUS_UNAVAILABLE,
                "reason": (
                    "oracle 没有给出 " + field + " 的真实 node id 清单："
                    "没有它就只能报全套结果，不能断言「原有测试是否仍绿」。"
                ),
            }
            continue
        still_green: list = []
        regressed: list = []
        missing: list = []
        for node in declared:
            outcome = normalized.get(node)
            if outcome is None:
                missing.append(node)
            elif outcome == "passed":
                still_green.append(node)
            else:
                regressed.append({"nodeid": node, "outcome": outcome})
        result[key] = {
            "status": STATUS_AVAILABLE,
            "declared": len(declared),
            "still_green": len(still_green),
            "regressed": regressed,
            "missing": missing,
            "ratio": round(len(still_green) / len(declared), 6),
            "ratio_ci95": wilson(len(still_green), len(declared)),
            "still_green_ids": still_green,
        }
    return result


def probe_imports(*, tree: Path, python: str, workdir: Path, roots: Sequence[str]) -> dict:
    """模块可导入性：每个顶层包各起一个子进程（可导入性不能用 importlib 在自进程里试）。"""

    packages: list = []
    for root_name in roots:
        root = tree / root_name
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and (entry / "__init__.py").is_file():
                packages.append((root_name, entry.name))
    if not packages:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": "在被测树的 " + ", ".join(roots) + " 下没找到带 __init__.py 的顶层包",
        }
    env = _oracle_env(tree, workdir / "plugin", workdir / "import-report.json", workdir / "pytest-tmp", {})
    results: list = []
    for root_name, name in packages:
        argv = [python, "-c", "import " + name]
        outcome = run_command(argv, cwd=tree, env=env, timeout=120.0)
        if outcome["status"] != STATUS_AVAILABLE:
            results.append({"root": root_name, "package": name, "result": "unavailable",
                            "detail": outcome["reason"]})
            continue
        code = outcome.get("exit_code")
        detail = sanitize((outcome["stderr"] or "").strip().splitlines()[-1] if outcome["stderr"].strip() else "")
        results.append(
            {
                "root": root_name,
                "package": name,
                "result": "ok" if code == 0 else ("importerror" if "ModuleNotFoundError" in outcome["stderr"]
                                                  or "ImportError" in outcome["stderr"] else "error"),
                "exit_code": code,
                "detail": detail,
            }
        )
    ok = sum(1 for item in results if item["result"] == "ok")
    return {
        "status": STATUS_AVAILABLE,
        "import_roots": list(roots),
        "packages": results,
        "import_ok": ok,
        "import_total": len(results),
        "import_ok_ratio": round(ok / len(results), 6) if results else None,
        "import_ok_ratio_ci95": wilson(ok, len(results)),
    }


def api_surface(tree: Path, files: Sequence[Path]) -> dict:
    """公开 API 面：模块级公开函数 / 类名 + __all__（用 ast，不用导入）。"""

    modules: dict = {}
    for path in files:
        rel = rel_posix(path, root=tree)
        try:
            module = ast.parse(read_bytes(path).decode("utf-8"), filename=rel)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        names: set = set()
        for node in module.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    names.add(node.name)
        for node in module.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            ):
                for item in getattr(node.value, "elts", []):
                    text = _const_str(item)
                    if text:
                        names.add(text)
        if names:
            modules[rel] = sorted(names)
    return {"status": STATUS_AVAILABLE, "modules": dict(sorted(modules.items()))}


def compare_api_surface(current: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict:
    """当前面与基线面的差集：**移除**是破坏性变更，新增不是。"""

    current_modules = current.get("modules") or {}
    baseline_modules = baseline.get("modules") or {}
    removed: list = []
    added: list = []
    for rel, names in sorted(baseline_modules.items()):
        now = set(current_modules.get(rel) or [])
        gone = sorted(set(names) - now)
        if rel not in current_modules:
            removed.append({"module": rel, "missing": sorted(names), "reason": "module_absent"})
        elif gone:
            removed.append({"module": rel, "missing": gone, "reason": "names_removed"})
    for rel, names in sorted(current_modules.items()):
        before = set(baseline_modules.get(rel) or [])
        fresh = sorted(set(names) - before)
        if fresh:
            added.append({"module": rel, "names": fresh})
    return {"removed": removed, "added": added, "breaking": bool(removed)}

# --------------------------------------------------------------------------- 反事实：精确
#
# 口径（**先写死再跑**，见 docs/.../measurement-instruments.md 的预注册小节）：
#   * 主判据 = 逐文件的 (code, message) **多重集差**（对行号漂移稳健）；
#   * 次判据 = 新增 finding 是否落在本次改动的 + 行上（口径差额如实两个都报）；
#   * 分母 = **可重建**的被拦编辑条数；抽样单位 = edit；不可重建的不进分母；
#   * 标签只来自冻结配置的 ruff / 自写 AST 检查器 / pytest，**没有平台的 Decision**。

CF_RED = "red"
CF_GREEN = "green"
CF_UNRECONSTRUCTIBLE = "unreconstructible"
CF_RECONSTRUCT_FAILED = "reconstruct_failed"
CF_UNVERIFIABLE = "unverifiable"


def load_jsonl(path: Path) -> list:
    """读 JSONL（每行一个对象）；空行跳过。格式非法由调用点转成退出码 2。"""

    records: list = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        if not isinstance(payload, dict):
            raise ValueError(str(path) + ":" + str(number) + " 不是 JSON 对象")
        records.append(payload)
    return records


def _multiset(findings: Sequence[Mapping[str, Any]]) -> dict:
    """(code, message) 多重集。"""

    counts: dict = {}
    for item in findings:
        key = (str(item.get("code") or ""), str(item.get("message") or ""))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _multiset_delta(before: Mapping, after: Mapping) -> list:
    """after 比 before 多出来的条目（含条数增加）。"""

    delta: list = []
    for key, count in sorted(after.items()):
        extra = int(count) - int(before.get(key, 0))
        if extra > 0:
            delta.append({"code": key[0], "message": key[1], "extra": extra})
    return delta


def line_backmap(before: bytes, after: bytes) -> dict:
    """after 行号 -> before 行号（只在 equal 块里有映射，改动行没有）。

    这是对 r3-applicability 的 M-4① 的正面回答：直接比 (row, code) 集合会把
    插入点之上的既有发现全判成"新增"。有了回映射，漂移过的旧发现能被认出来。
    """

    old_lines = _decode_lines(before)
    new_lines = _decode_lines(after)
    if old_lines is None or new_lines is None:
        return {}
    mapping: dict = {}
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[j1 + offset + 1] = i1 + offset + 1
    return mapping


def _edit_kind(record: Mapping[str, Any]) -> str:
    """编辑形态：replacement / write / diff（三选一）。"""

    if record.get("old_string") is not None and record.get("new_string") is not None:
        return "replacement"
    if record.get("new_content") is not None:
        return "write"
    if record.get("unified_diff") is not None:
        return "diff"
    return "unknown"


def apply_edit(record: Mapping[str, Any], base_tree: Path, target_root: Path) -> dict:
    """把一条编辑应用到一个隔离副本上，返回重建结果与失败原因。"""

    kind = _edit_kind(record)
    rel = str(record.get("path") or "")
    if not rel:
        return {"status": CF_UNRECONSTRUCTIBLE, "reason": "记录里没有 path"}
    if rel.startswith("/") or ":" in rel[:3] or ".." in rel.replace("\\", "/").split("/"):
        return {"status": CF_UNRECONSTRUCTIBLE, "reason": "path 不是树内相对路径"}
    source = base_tree / rel
    destination = target_root / rel
    destination.parent.mkdir(parents=True, exist_ok=True)

    if kind == "replacement":
        if not source.is_file():
            return {"status": CF_UNRECONSTRUCTIBLE, "reason": "前置树里没有 " + rel}
        original = source.read_bytes().decode("utf-8")
        old = str(record.get("old_string"))
        new = str(record.get("new_string"))
        occurrences = original.count(old)
        if occurrences != 1:
            return {
                "status": CF_UNRECONSTRUCTIBLE,
                "reason": "old_string 在目标文件里出现 " + str(occurrences) + " 次（必须恰好一次）",
            }
        destination.write_text(original.replace(old, new), encoding="utf-8", newline="")
        return {"status": CF_RED, "files": [rel]}
    if kind == "write":
        destination.write_text(str(record.get("new_content")), encoding="utf-8", newline="")
        return {"status": CF_RED, "files": [rel]}
    if kind == "diff":
        parsed = parse_unified_diff(str(record.get("unified_diff")))
        if not parsed:
            return {"status": CF_UNRECONSTRUCTIBLE, "reason": "unified_diff 解析不出任何文件"}
        for name in parsed:
            origin = base_tree / name
            if origin.is_file():
                target = target_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(origin.read_bytes())
        outcome = apply_unified_diff(target_root, parsed)
        if outcome["failed"]:
            return {
                "status": CF_UNRECONSTRUCTIBLE,
                "reason": "patch 应用失败：" + sanitize(outcome["failed"][0]["reason"]),
            }
        return {"status": CF_RED, "files": [item["file"] for item in outcome["applied"]]}
    return {
        "status": CF_UNRECONSTRUCTIBLE,
        "reason": "记录里既没有 old_string/new_string，也没有 new_content 或 unified_diff",
    }


def _file_findings(tree: Path, rel: str, workdir: Path, ruff: str, configs: Mapping) -> dict:
    """对一个文件跑冻结配置 + 自写 AST 检查器（反事实的最小重扫单位）。"""

    path = tree / rel
    if not path.is_file():
        return {"status": STATUS_UNAVAILABLE, "reason": "文件不存在：" + rel}
    norm = run_ruff_profile(
        tree=tree, files=[path], ruff=ruff, config=configs["norm"], workdir=workdir
    )
    sec = run_ruff_profile(tree=tree, files=[path], ruff=ruff, config=configs["sec"], workdir=workdir)
    ast_result = scan_security_ast(tree, [path])
    if norm["status"] != STATUS_AVAILABLE or sec["status"] != STATUS_AVAILABLE:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": norm.get("reason") or sec.get("reason") or "扫描失败",
        }
    norm_defects, norm_parse = split_parse_errors(norm["findings"])
    return {
        "status": STATUS_AVAILABLE,
        "norm": norm_defects,
        "norm_parse_errors": norm_parse,
        "sec": sec["findings"],
        "ast": ast_result["findings"],
        "ast_parse_errors": ast_result["parse_errors"],
    }


def changed_lines_for_file(before: bytes, after: bytes) -> dict:
    """同一个文件改动前后的 new-side 行集合（行级口径，标准库 difflib）。"""

    old_lines = _decode_lines(before)
    new_lines = _decode_lines(after)
    if old_lines is None or new_lines is None:
        return {"lines": [], "whole_file": True, "reason": "binary_or_not_utf8"}
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    touched: set = set()
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert"):
            touched.update(range(j1 + 1, j2 + 1))
    return {"lines": sorted(touched), "whole_file": False, "reason": "diff"}


def counterfactual(
    *,
    edits: Sequence[Mapping[str, Any]],
    base_tree: Path,
    workdir: Path,
    ruff: str,
    configs: Mapping,
    scope: str,
    with_tests: Optional[Mapping[str, Any]] = None,
    oracle: Optional[Mapping[str, Any]] = None,
    max_edits: int = 0,
) -> dict:
    """对每条编辑做反事实：它在隔离副本里会不会被**独立仪器**判红。"""

    results: list = []
    selected = list(edits)
    truncated = False
    if max_edits and len(selected) > max_edits:
        selected = selected[:max_edits]
        truncated = True
    root = workdir / "cf"
    for index, record in enumerate(selected):
        edit_id = str(record.get("edit_id") or ("edit-" + str(index)))
        entry: dict = {
            "edit_id": edit_id,
            "task_id": record.get("task_id"),
            "arm": record.get("arm"),
            "kind": _edit_kind(record),
            "path": record.get("path"),
        }
        target_root = root / (str(index).zfill(4) + "-" + re.sub(r"[^0-9A-Za-z_.-]", "_", edit_id))
        if target_root.exists():
            shutil.rmtree(target_root, ignore_errors=True)
        target_root.mkdir(parents=True, exist_ok=True)
        applied = apply_edit(record, base_tree, target_root)
        entry["reconstruct"] = applied["status"]
        if applied["status"] != CF_RED:
            entry["outcome"] = applied["status"]
            entry["reason"] = applied["reason"]
            results.append(entry)
            continue
        touched = [str(item) for item in applied["files"]]
        entry["files"] = touched
        verdict = CF_GREEN
        reasons: list = []
        for rel in touched:
            after = _file_findings(target_root, rel, workdir, ruff, configs)
            before = _file_findings(base_tree, rel, workdir, ruff, configs)
            if after["status"] != STATUS_AVAILABLE or before["status"] != STATUS_AVAILABLE:
                verdict = CF_UNVERIFIABLE
                reasons.append(
                    "基线或反事实扫描失败：" + str(before.get("reason") or after.get("reason"))
                )
                break
            try:
                old_bytes = (base_tree / rel).read_bytes()
            except OSError:
                old_bytes = b""
            new_bytes = (target_root / rel).read_bytes()
            venue = changed_lines_for_file(old_bytes, new_bytes)
            entry.setdefault("changed_lines", {})[rel] = {
                "count": len(venue["lines"]),
                "whole_file": venue["whole_file"],
            }
            norm_delta = _multiset_delta(_multiset(before["norm"]), _multiset(after["norm"]))
            sec_delta = _multiset_delta(
                _multiset(list(before["sec"]) + list(before["ast"])),
                _multiset(list(after["sec"]) + list(after["ast"])),
            )
            entry.setdefault("new_findings", []).extend(
                [{"file": rel, **item} for item in norm_delta]
            )
            entry.setdefault("new_security", []).extend([{"file": rel, **item} for item in sec_delta])
            old_rows = {(int(item["row"]), str(item["code"])) for item in before["norm"]}
            new_rows = {(int(item["row"]), str(item["code"])) for item in after["norm"]}
            backmap = line_backmap(old_bytes, new_bytes)
            entry.setdefault("secondary_caliber_rows_added_raw", 0)
            entry.setdefault("secondary_caliber_rows_added_shift_aware", 0)
            entry["secondary_caliber_rows_added_raw"] += len(new_rows - old_rows)
            for row, code in sorted(new_rows):
                back = backmap.get(row)
                if back is None or (back, code) not in old_rows:
                    entry["secondary_caliber_rows_added_shift_aware"] += 1
            if norm_delta or sec_delta:
                verdict = CF_RED
        if with_tests is not None and verdict == CF_RED:
            reasons.append("测试未参与判定（已经由独立仪器判红）")
        if with_tests is not None and verdict == CF_GREEN:
            trial = run_pytest_oracle(
                tree=target_root,
                oracle=oracle or {},
                workdir=workdir / ("cf-tests-" + str(index)),
                timeout_s=float((oracle or {}).get("test_command", {}).get("timeout_s") or 900.0),
            )
            entry["counterfactual_tests"] = {
                "pytest_status": trial.get("pytest_status"),
                "counts": trial.get("counts"),
            }
            if trial.get("pytest_status") == "red":
                verdict = CF_RED
                reasons.append("反事实树上的仓库自带测试变红")
            elif trial.get("pytest_status") == "environment_unavailable":
                entry["tests_note"] = "测试环境不可用，未参与判定：" + sanitize(trial.get("reason"))
        entry["outcome"] = verdict
        entry["reasons"] = reasons
        entry["criterion"] = "per_file_(code,message)_multiset_delta"
        results.append(entry)
    denominator = [item for item in results if item["outcome"] in (CF_RED, CF_GREEN)]
    reds = [item for item in denominator if item["outcome"] == CF_RED]
    unreconstructible = [item for item in results if item["outcome"] == CF_UNRECONSTRUCTIBLE]
    failed = [item for item in results if item["outcome"] == CF_RECONSTRUCT_FAILED]
    unverifiable = [item for item in results if item["outcome"] == CF_UNVERIFIABLE]
    return {
        "role": "outcome",
        "inputs": {"edits": len(edits), "evaluated": len(selected), "truncated": truncated},
        "counts": {
            "TP": len(reds),
            "FP": len(denominator) - len(reds),
            "unreconstructible": len(unreconstructible),
            "unverifiable": len(unverifiable),
        },
        "counts_note": (
            "协议可以只用这四个计数、不给比率（lead 裁定的 P1 现实形态）。"
            "precision 是**派生量**，只在分母 > 0 时有意义。"
        ),
        "results": results,
        "denominator": len(denominator),
        "red": len(reds),
        "green": len(denominator) - len(reds),
        "precision": round(len(reds) / len(denominator), 6) if denominator else None,
        "precision_ci95": wilson(len(reds), len(denominator)),
        "unreconstructible": [{"edit_id": item["edit_id"], "reason": item.get("reason")}
                              for item in unreconstructible],
        "reconstruct_failed": [{"edit_id": item["edit_id"], "reason": item.get("reason")}
                               for item in failed],
        "unverifiable_detail": [{"edit_id": item["edit_id"], "reason": item.get("reasons")}
                                for item in unverifiable],
        "secondary_caliber": (
            "行级口径单列两个数：rows_added_raw（直接比 (row, code) 集合，**对行号漂移敏感**，"
            "红队 M-4① 已实测它会多报）与 rows_added_shift_aware（用 diff 的 equal 块把 after 行号"
            "回映射到 before 行号后再比）。主判据不用它们，但差额本身是要读出来的量。"
        ),
        "label_semantics": (
            "agreement_with_independent_instruments —— **不是** ground truth。"
            "标签来自与平台同一条 ruff 二进制（外加自写 AST 与 pytest），所以 precision 的上界是"
            "「与独立仪器配置的一致率」，不是「这次 block 是否真的对」。"
        ),
        "upper_bound_note": (
            "红队 M-4② 给的形态：平台 block 的某个位置被平台自己的规则文档声明为误报，而冻结仪器"
            "**照样报红** ⇒ 该样本会被算成真阳性。要暴露这个上界，用 "
            "--known-false-positive-edits 跑阳性对照（declared_fp 里仪器仍判红的比例 = 仪器的天花板），"
            "或者换外部 oracle（本机装不上 bandit/semgrep，走不通）。"
        ),
        "caliber": (
            "分母 = 可重建的被拦编辑条数（抽样单位 edit，不是 finding / 文件 / run）；"
            "red 的判据是逐文件 (code,message) 多重集增量（对行号漂移稳健），"
            "标签只来自冻结配置的 ruff 与自写 AST 检查器（--with-tests 时再加 pytest）。"
        ),
    }


# --------------------------------------------------------------------------- 高效


def measure_latency(
    *,
    argv: Sequence[str],
    repeats: int,
    workdir: Path,
    cwd: Optional[Path],
    allow_side_effects: bool,
) -> dict:
    """单次判定延迟：跑 repeats 次、**剔首个冷启动**、最近秩法报 p50/p95。"""

    if not allow_side_effects:
        return {
            "status": STATUS_UNAVAILABLE,
            "reason": (
                "没有声明 --latency-allow-side-effects：在可能有副作用的入口上重复跑 N 次，"
                "测量本身就会干扰被测树，因此拒绝。"
            ),
            "hint": "确认该命令无副作用（含只写 .tmp）后加 --latency-allow-side-effects。",
        }
    samples: list = []
    cold = None
    for index in range(max(1, repeats)):
        started = time.perf_counter()
        result = run_command(argv, cwd=cwd, timeout=600.0)
        elapsed = (time.perf_counter() - started) * 1000.0
        if result["status"] != STATUS_AVAILABLE:
            return {"status": STATUS_UNAVAILABLE, "reason": result["reason"], "samples_ms": samples}
        if index == 0:
            cold = round(elapsed, 3)
        else:
            samples.append(round(elapsed, 3))
    ordered = sorted(samples)
    return {
        "status": STATUS_AVAILABLE,
        "command": [sanitize(part, root=cwd) for part in argv],
        "repeats": repeats,
        "cold_start_ms": cold,
        "dropped_first_sample": True,
        "n": len(ordered),
        "samples_ms": ordered,
        "min_ms": ordered[0] if ordered else None,
        "max_ms": ordered[-1] if ordered else None,
        "median_ms": median(ordered),
        "p50_ms": nearest_rank(ordered, 50.0),
        "p95_ms": nearest_rank(ordered, 95.0),
        "method": "nearest-rank（不插值）：ceil(p/100 * n) 号样本，1-based",
        "deterministic": False,
    }


def efficiency_from_runs(records: Sequence[Mapping[str, Any]], baseline_arm: str = "off") -> dict:
    """每任务 wall-clock 增量：同 (task_id, replicate) 配对、按臂取差 + 配对符号检验。"""

    if not records:
        return {"status": STATUS_UNAVAILABLE, "reason": "没有 run 记录（--runs 未给或为空）"}
    wall: dict = {}
    retries: dict = {}
    for record in records:
        arm = str(record.get("arm") or "unknown")
        task = str(record.get("task_id") or "")
        replicate = str(record.get("replicate") or 0)
        timing = record.get("timing") if isinstance(record.get("timing"), Mapping) else {}
        value = timing.get("wall_ms", record.get("wall_clock_ms"))
        if value is not None:
            wall[(task, replicate, arm)] = float(value)
        counts = record.get("counts") if isinstance(record.get("counts"), Mapping) else {}
        if counts.get("retries") is not None:
            retries.setdefault(arm, []).append(float(counts["retries"]))
    arms = sorted({key[2] for key in wall})
    per_arm: dict = {}
    for arm in arms:
        deltas: list = []
        samples: list = []
        for task, replicate, candidate in sorted(wall):
            if candidate != arm:
                continue
            base = wall.get((task, replicate, baseline_arm))
            if base is None:
                continue
            samples.append(wall[(task, replicate, arm)])
            deltas.append(wall[(task, replicate, arm)] - base)
        ordered = sorted(samples)
        per_arm[arm] = {
            "paired_n": len(deltas),
            "wall_ms_median": median(ordered),
            "wall_ms_p25": nearest_rank(ordered, 25.0),
            "wall_ms_p75": nearest_rank(ordered, 75.0),
            "delta_vs_" + baseline_arm + "_ms_median": median(sorted(deltas)) if deltas else None,
            "delta_sign_test": paired_sign_test(deltas),
        }
    return {
        "status": STATUS_AVAILABLE,
        "baseline_arm": baseline_arm,
        "arms": per_arm,
        "retries_median": {arm: median(sorted(values)) for arm, values in sorted(retries.items())},
        "retries_definition": (
            "retries = 同一 task 内上一次被拦之后产生的下一次同类写动作尝试（来自 run 记录的 "
            "counts.retries）；不是工具调用总数。"
        ),
        "runs_used": len(records),
    }


# --------------------------------------------------------------------------- 全自动化（操纵检查）


def automation_from(
    *, actions: Sequence[Mapping[str, Any]], runs: Sequence[Mapping[str, Any]]
) -> dict:
    """受治理写动作覆盖率 / bypass / 人工介入次数。

    **角色是操纵检查，不是结局变量**：off 臂没有治理路径，覆盖率与介入次数在臂之间的差
    是"处理有没有被施加"的构造性差异，把它当成绩就是拿处理变量冒充结局变量。
    """

    unavailable: list = []
    coverage: dict = {}
    if actions:
        writes = [item for item in actions if str(item.get("operation") or "") == "write"]
        governed = [item for item in writes if item.get("governed") is True]
        coverage = {
            "write_actions": len(writes),
            "governed_write_actions": len(governed),
            "governed_write_coverage": round(len(governed) / len(writes), 6) if writes else None,
            "governed_write_coverage_ci95": wilson(len(governed), len(writes)),
        }
        if all("governance_status" not in item for item in actions):
            unavailable.append(
                {
                    "what": "automation.bypass_count",
                    "reason": "--actions 的每一条记录都没有 governance_status 字段："
                    "bypass 的定义是「写动作绕过了治理」，没有这个字段就无法区分「没绕过」"
                    "与「没记录」。",
                }
            )
        else:
            bypassed = [
                item
                for item in actions
                if str(item.get("governance_status") or "") in ("bypassed", "unauthorized_write")
            ]
            coverage["bypass_count"] = len(bypassed)
            coverage["bypass_ids"] = [str(item.get("action_id")) for item in bypassed]
    elif runs:
        totals = [item.get("counts", {}) for item in runs if isinstance(item.get("counts"), Mapping)]
        if totals and any("write_actions" in item for item in totals):
            per_arm: dict = {}
            for record in runs:
                counts = record.get("counts") if isinstance(record.get("counts"), Mapping) else {}
                if "write_actions" not in counts:
                    continue
                arm = str(record.get("arm") or "unknown")
                bucket = per_arm.setdefault(arm, {"write": 0, "governed": 0, "bypass": 0, "human": 0})
                bucket["write"] += int(counts.get("write_actions") or 0)
                bucket["governed"] += int(counts.get("governed_write_actions") or 0)
                bucket["bypass"] += int(counts.get("bypass_actions") or 0)
                bucket["human"] += int(counts.get("human_interventions") or 0)
            coverage = {"by_arm": per_arm}
            for arm, bucket in sorted(per_arm.items()):
                bucket["governed_write_coverage"] = (
                    round(bucket["governed"] / bucket["write"], 6) if bucket["write"] else None
                )
                bucket["governed_write_coverage_ci95"] = wilson(bucket["governed"], bucket["write"])
        else:
            unavailable.append(
                {
                    "what": "automation.governed_write_coverage",
                    "reason": "run 记录里没有 counts.write_actions / governed_write_actions",
                }
            )
    else:
        unavailable.append(
            {
                "what": "automation.governed_write_coverage",
                "reason": "没有 --actions 也没有 --runs：没有可数的写动作记录",
            }
        )

    human: dict = {"status": STATUS_UNAVAILABLE}
    if runs:
        entries = [
            record
            for record in runs
            if isinstance(record.get("counts"), Mapping)
            and "human_interventions" in record["counts"]
        ]
        if entries:
            per_arm_human: dict = {}
            for record in entries:
                arm = str(record.get("arm") or "unknown")
                per_arm_human[arm] = per_arm_human.get(arm, 0) + int(
                    record["counts"]["human_interventions"]
                )
            kinds: dict = {}
            for record in runs:
                for item in record.get("human_interventions_detail") or []:
                    key = str(item.get("kind") or "unknown")
                    kinds[key] = kinds.get(key, 0) + 1
            human = {"status": STATUS_AVAILABLE, "by_arm": dict(sorted(per_arm_human.items())),
                     "by_kind": dict(sorted(kinds.items()))}
        else:
            human = {
                "status": STATUS_UNAVAILABLE,
                "reason": (
                    "run 记录里没有 counts.human_interventions 字段：人工介入必须被机器数出来，"
                    "不能从「模型说了什么」里推断。"
                ),
            }
    else:
        human = {"status": STATUS_UNAVAILABLE, "reason": "没有 --runs：没有可数的人工触点记录"}
    return {
        "role": "manipulation_check",
        "coverage": coverage,
        "human_interventions": human,
        "unavailable": unavailable,
        "caveat": (
            "这一块回答「处理有没有被施加」，不回答「有没有用」：off 臂 governed_write_actions=0、"
            "human_interventions=0 是构造出来的，不是测出来的。把它当价值证据就是拿处理变量"
            "冒充结局变量。"
        ),
    }

# --------------------------------------------------------------------------- 同源声明（每块各写一次）

HOMOLOGY: Mapping[str, Mapping[str, Any]] = {
    "scanner": {
        "independent_of_policy_layer": True,
        "independent_of_underlying_linter": False,
        "grade": "policy_layer_independent_linter_dependent",
        "note": (
            "不读 policies/**、不用 validation/ruff.toml、不读平台的 Decision/violation/severity；"
            "但底层是同一条 ruff 二进制，所以规范性只能算「独立于策略层」。"
        ),
    },
    "security_ruff": {
        "independent_of_policy_layer": True,
        "independent_of_underlying_linter": False,
        "grade": "half_homologous_same_binary",
        "note": "与 scanner 块同一条 ruff 二进制 → 半同源，两个量不是独立证据。",
    },
    "security_ast": {
        "independent_of_policy_layer": True,
        "independent_of_underlying_linter": True,
        "grade": "second_implementation_uncalibrated",
        "note": (
            "自写 AST 检查器与 ruff 不同源，但**没有被任何外部 oracle 校准**，"
            "且无 taint / 无数据流 / 无跨文件 / 无依赖漏洞：它是第二实现，不是第二独立检查。"
        ),
    },
    "usability": {
        "independent_of_policy_layer": True,
        "independent_of_underlying_linter": True,
        "grade": "externally_independent",
        "note": "pytest 与逐用例结果完全不经过平台与 linter。",
    },
    "block_precision": {
        "independent_of_policy_layer": True,
        "independent_of_underlying_linter": False,
        "grade": "label_from_independent_instruments_only",
        "note": (
            "反事实的红绿标签只来自冻结配置的 ruff、自写 AST 检查器与 pytest；"
            "平台的 Decision / severity / treatment_record 一个都不参与。"
        ),
    },
    "efficiency": {
        "independent_of_policy_layer": True,
        "independent_of_underlying_linter": True,
        "grade": "wall_clock",
        "note": "秒表只测墙钟，不解释墙钟。",
    },
    "automation": {
        "independent_of_policy_layer": True,
        "independent_of_underlying_linter": True,
        "grade": "manipulation_check",
        "note": "纯计数，且角色是操纵检查而非结局变量。",
    },
}

#: 安全分档是**仪器自己的**（不是上游 ruff / bandit 给的），也**不是阻断力**。
SECURITY_BANDS: Mapping[str, tuple] = {
    "high": (
        "ABSEC-001", "ABSEC-002", "ABSEC-003", "ABSEC-004", "ABSEC-005",
        "S102", "S301", "S302", "S303", "S307", "S308", "S310", "S311", "S312",
        "S313", "S314", "S315", "S316", "S317", "S318", "S321", "S323", "S324",
        "S501", "S506", "S602", "S605", "S608", "S609", "S611", "S612", "S701",
    ),
    "medium": ("ABSEC-008", "ABSEC-009", "ABSEC-010", "S104", "S105", "S106", "S107",
               "S110", "S112", "S113"),
    "low": ("ABSEC-006", "ABSEC-007"),
}


def band_of(code: str) -> str:
    """码 -> 仪器自己的分档（未列出的写 unknown）。"""

    for band, codes in SECURITY_BANDS.items():
        if code in codes:
            return band
    return "unknown"


# --------------------------------------------------------------------------- 块组装


def build_scanner_block(
    *, tree: Path, facts: Mapping[str, Any], ruff: str, ruff_info: Mapping[str, Any],
    config: Mapping[str, Any], changes: Optional[Mapping[str, Any]],
) -> dict:
    """规范性：冻结配置下的 ruff（全树 + 改动行 + 改动文件三个口径）。"""

    block: dict = {
        "role": "outcome",
        "homology": HOMOLOGY["scanner"],
        "instrument": {
            "name": "ruff",
            "version": ruff_info.get("version"),
            "profile": config["profile_id"],
            "select": config["select"],
            "line_length": config["line_length"],
            "config_path": reading.display_path(config["path"], root=REPO),
            "config_digest": config["digest"],
            "argv_template": [
                "<ruff>", "check", "--config", "<frozen toml>", "--output-format", "json",
                "--no-cache", "--no-respect-gitignore", "--quiet", "<files...>",
            ],
            "isolation_note": (
                "--config <path> 单独使用即可压掉被测树里的配置发现（实测：诱饵 "
                "ruff.toml 的 line-length 不生效）；--isolated 与 --config 同用被 ruff 拒绝。"
            ),
        },
        "unavailable": [],
    }
    if ruff_info.get("status") != STATUS_AVAILABLE:
        block["status"] = STATUS_UNAVAILABLE
        block["unavailable"].append({"what": "scanner", "reason": ruff_info.get("reason")})
        return block
    outcome = run_ruff_profile(
        tree=tree, files=facts["files"], ruff=ruff, config=config, workdir=config["path"].parent
    )
    if outcome["status"] != STATUS_AVAILABLE:
        block["status"] = STATUS_UNAVAILABLE
        block["unavailable"].append({"what": "scanner", "reason": outcome["reason"]})
        return block
    defects, parse_errors = split_parse_errors(outcome["findings"])
    kloc = facts["kloc"]
    scanned = {rel_posix(path, root=tree) for path in facts["files"]}
    clean_files = len(scanned - {item["file"] for item in defects})
    block["status"] = STATUS_AVAILABLE
    block["metrics"] = {
        "files_scanned": facts["file_count"],
        "physical_lines": facts["physical_lines"],
        "kloc": kloc,
        "violations_total": len(defects),
        "violations_per_kloc": round(len(defects) / kloc, 6) if kloc else None,
        "clean_files": clean_files,
        "clean_file_ratio": round(clean_files / facts["file_count"], 6) if facts["file_count"] else None,
        "clean_file_ratio_ci95": wilson(clean_files, facts["file_count"]),
        "counts_by_code": bucket_by_code(defects),
        "parse_errors": len(parse_errors),
        "parse_error_files": sorted({item["file"] for item in parse_errors}),
    }
    block["findings"] = defects
    block["red"] = bool(defects)
    block["recall_limit"] = (
        "冻结选择（" + str(config["select"]) + "）之外的码**看不见**：绝对数是结构性低估。"
        "两臂用同一套冻结配置 ⇒ 差值可比；绝对水平不可当「真相」。"
    )
    block["caliber"] = {
        "position_match": "(树内相对 POSIX 路径, code, 行号) 三元组；列只记录不参与匹配；"
        "行号 1-based；跨行 finding 取起始行；**没有 ± 容差**。",
        "denominator": "被扫描的 *.py 文件数与物理行数（含空行与注释）；解析失败的文件仍在分母里。",
        "line_length": "冻结 88 列，**不是**本仓库 validation/ruff.toml 的 100：口径差刻意保留，"
        "两者不可直接比较。",
    }
    if changes is None:
        block["changed"] = {
            "status": STATUS_UNAVAILABLE,
            "reason": "没有 --baseline-tree 也没有 --diff：算不出 new-side 的 + 行集合。",
            "hint": "外部任务树的基线是归档、不一定有 .git ⇒ 用 --baseline-tree（标准库 difflib，不需要 git）。",
        }
    else:
        changed_lines = changes["changed_lines"]
        touched = set(changes["touched_files"])
        by_line: dict = {}
        for item in defects:
            venue = changed_lines.get(item["file"])
            if venue and item["row"] in set(venue["lines"]):
                by_line[item["code"]] = by_line.get(item["code"], 0) + 1
        by_file: dict = {}
        for item in defects:
            if item["file"] in touched:
                by_file[item["code"]] = by_file.get(item["code"], 0) + 1
        block["changed"] = {
            "status": STATUS_AVAILABLE,
            "tree_scope": "final",
            "changed_file_count": len(touched),
            "counts_by_code_changed": dict(sorted(by_line.items())),
            "counts_by_code_touched_files": dict(sorted(by_file.items())),
            "counts_whole_tree": block["metrics"]["counts_by_code"],
            "caliber": (
                "主口径 = 行级交集：finding 的 row ∈ 该文件 new-side 的 + 行集合（replace 落在 + 侧，"
                "修改被覆盖；纯删除不产生新行；新文件/重命名整文件视为改动）。"
                "三个口径**不许混进同一个数**：差额本身就是要读出来的量。"
            ),
        }
    return block


def build_security_block(
    *, tree: Path, facts: Mapping[str, Any], ruff: str, config: Mapping[str, Any],
    workdir: Path, probe_scanners: bool = True,
) -> dict:
    """安全性：路线 A（独立扫描器，本机没有）+ 路线 B（ruff S 子集 + 自写 AST）。"""

    block: dict = {
        "role": "outcome",
        "homology": {"route_a": HOMOLOGY["security_ruff"], "route_b_ruff": HOMOLOGY["security_ruff"],
                     "route_b_ast": HOMOLOGY["security_ast"]},
        "route_a": {"attempted": probe_scanners, "scanners": [], "available": [], "note": ""},
        "unavailable": [],
    }
    if probe_scanners:
        for spec in SECURITY_SCANNERS:
            name = str(spec["name"])
            probe = run_command(list(spec["version_argv"]), timeout=30.0)
            if probe["status"] != STATUS_AVAILABLE:
                block["route_a"]["scanners"].append(
                    {"name": name, "present": False, "reason": probe["reason"],
                     "why_independent": spec["why"]}
                )
                continue
            version = sanitize(probe["stdout"].strip() or probe["stderr"].strip(), limit=120)
            entry: dict = {"name": name, "present": True, "version": version,
                           "why_independent": spec["why"]}
            argv = [
                name if part == name else (str(tree) if part == "<tree>" else part)
                for part in spec["argv"]
            ]
            outcome = run_command(argv, cwd=workdir, timeout=900.0)
            entry["argv"] = [sanitize(part, root=workdir) for part in argv]
            entry["exit_code"] = outcome.get("exit_code")
            if outcome["status"] == STATUS_AVAILABLE:
                entry["ran"] = True
                findings = _parse_route_a(name, outcome.get("stdout") or "", tree=tree)
                entry["findings_total"] = len(findings)
                entry["findings"] = findings
                block["route_a"]["available"].append(name)
            else:
                entry["ran"] = False
                entry["reason"] = outcome["reason"]
            block["route_a"]["scanners"].append(entry)
        block["route_a"]["note"] = (
            "路线 A 是本机**装不上**的独立扫描器：全部 present=false 时，读数的独立性只能到"
            "路线 B（半同源）。这条分支在本机从未被执行过 ⇒ route_a_verified=false。"
        )
        block["route_a"]["route_a_verified"] = bool(block["route_a"]["available"])
    else:
        block["route_a"]["note"] = "本次没有探测路线 A（probe_scanners=False）"

    ast_result = scan_security_ast(tree, facts["files"])
    ruff_sec = run_ruff_profile(
        tree=tree, files=facts["files"], ruff=ruff, config=config, workdir=workdir
    )
    if ruff_sec["status"] != STATUS_AVAILABLE:
        block["status"] = STATUS_UNAVAILABLE
        block["unavailable"].append({"what": "security.route_b_ruff", "reason": ruff_sec["reason"]})
        return block
    ruff_findings = [
        item for item in ruff_sec["findings"] if not is_parse_error(str(item.get("code")))
    ]
    ast_findings = ast_result["findings"]
    all_findings = sorted(
        [*ruff_findings, *ast_findings],
        key=lambda item: (item["file"], item["row"], item["col"], item["code"]),
    )
    kloc = facts["kloc"]
    bands: dict = {}
    for item in all_findings:
        band = band_of(str(item["code"]))
        bands[band] = bands.get(band, 0) + 1
    block["status"] = STATUS_AVAILABLE
    block["instrument"] = {
        "route_b_ruff": {
            "name": "ruff", "profile": config["profile_id"], "select": config["select"],
            "version": ruff_version(ruff).get("version"),
        },
        "route_b_ast": {
            "name": "ab_ast_security", "version": TOOL_VERSION,
            "checks": [dict(item) for item in SECURITY_RULES],
        },
    }
    block["metrics"] = {
        "findings_total": len(all_findings),
        "findings_per_kloc": round(len(all_findings) / kloc, 6) if kloc else None,
        "by_implementation": {"ruff_S": len(ruff_findings), "ab_ast": len(ast_findings)},
        "by_code": bucket_by_code(all_findings),
        "by_instrument_band": dict(sorted(bands.items())),
        "ast_parse_errors": len(ast_result["parse_errors"]),
    }
    block["findings"] = all_findings
    block["red"] = bool(all_findings)
    if all_findings:
        counts = bucket_by_code(all_findings)
        top_code = max(counts, key=lambda key: counts[key])
        block["dominant_code"] = {
            "code": top_code,
            "count": counts[top_code],
            "share": round(counts[top_code] / len(all_findings), 6),
            "note": (
                "总量被这一个码主导时，**只看总数会掩盖其余码**："
                "by_code 与 by_instrument_band 必须一起读（红队 S-5 的口径建议）。"
            ),
        }
    block["band_note"] = (
        "分档是**仪器自己**定的（不是上游 ruff / bandit 的 severity），也**不是阻断力**："
        "它只把码归成三类，方便读的人不被总数掩盖。"
    )
    block["weakness"] = (
        "路线 B 的弱点（必须写在结论旁）：ruff 的 S 族是 bandit 检查的**子集重实现**，"
        "无 taint、无跨函数数据流；自写 AST 检查器再多一层窄覆盖；"
        "**依赖漏洞（pip-audit / OSV）完全测不了**（无网、无本地漏洞库）。"
        "因此安全性是**下界**，不是覆盖率。"
    )
    return block


def _parse_route_a(name: str, text: str, *, tree: Path) -> list:
    """路线 A 的输出解析（bandit / semgrep 各一套）。本机未执行过这条分支。"""

    findings: list = []
    try:
        payload = json.loads(text or "{}")
    except json.JSONDecodeError:
        return findings
    if name == "bandit":
        for item in payload.get("results") or []:
            findings.append(
                {
                    "file": rel_posix(Path(str(item.get("filename") or "")), root=tree),
                    "row": int(item.get("line_number") or 0),
                    "col": int(item.get("col_offset") or 0) + 1,
                    "code": str(item.get("test_id") or ""),
                    "message": sanitize(item.get("issue_text")),
                    "band": str(item.get("issue_severity") or "unknown").lower(),
                }
            )
    elif name == "semgrep":
        for item in payload.get("results") or []:
            findings.append(
                {
                    "file": rel_posix(Path(str(item.get("path") or "")), root=tree),
                    "row": int((item.get("start") or {}).get("line") or 0),
                    "col": int((item.get("start") or {}).get("col") or 0),
                    "code": str((item.get("check_id") or "").split(".")[-1]),
                    "message": sanitize(item.get("extra", {}).get("message")),
                    "band": str((item.get("extra") or {}).get("severity") or "unknown").lower(),
                }
            )
    findings.sort(key=lambda item: (item["file"], item["row"], item["col"], item["code"]))
    return findings


def build_usability_block(
    *, tree: Path, oracle: Optional[Mapping[str, Any]], workdir: Path,
    import_roots: Sequence[str], api_baseline: Optional[Mapping[str, Any]],
    test_selections: Sequence[tuple], files: Sequence[Path], timeout_s: float,
) -> dict:
    """可用性：外部 oracle（pytest 逐用例结果）+ 可导入性 + 公开 API 面。"""

    block: dict = {
        "role": "outcome",
        "homology": HOMOLOGY["usability"],
        "unavailable": [],
        "pytest_sets": {},
    }
    if oracle is None:
        if (tree / "tests").is_dir():
            oracle = {}
        else:
            block["unavailable"].append(
                {
                    "what": "usability.pytest",
                    "reason": "没有 --oracle，被测树里也没有 tests/：没有外部 oracle 可跑。",
                    "hint": "给 --oracle <json>（含 python / test_command.argv / pass_to_pass / "
                    "fail_to_pass），或把测试放回 tests/。",
                }
            )
    if oracle is not None and not test_selections:
        trial = run_pytest_oracle(tree=tree, oracle=oracle, workdir=workdir, timeout_s=timeout_s)
        block["pytest_sets"]["default"] = trial
        if trial["status"] != STATUS_AVAILABLE:
            block["unavailable"].append({"what": "usability.pytest", "reason": trial["reason"]})
    else:
        for label, nodeids in test_selections:
            trial = run_pytest_oracle(
                tree=tree, oracle=oracle or {}, workdir=workdir / ("set-" + label),
                extra_args=[str(item) for item in nodeids], timeout_s=timeout_s,
            )
            block["pytest_sets"][label] = trial
            if trial["status"] != STATUS_AVAILABLE:
                block["unavailable"].append(
                    {"what": "usability.pytest." + label, "reason": trial["reason"]}
                )
    states = [trial.get("pytest_status") for trial in block["pytest_sets"].values()]
    ran = [state for state in states if state in ("ok", "red")]
    # 逐用例结果的总条数：**决定"跑没跑起来"的是它，不是分类标签**。
    # （红队实测：旧版在这里断言"一次都没跑起来"，而同一份载荷的 counts.total = 2136。）
    outcomes_total = sum(
        int((trial.get("counts") or {}).get("total") or 0) for trial in block["pytest_sets"].values()
    )
    if not ran:
        # 红队 V-2：一个都没真的跑起来 ⇒ 这是**仪器不可用**，不是"可用性红"。
        block["status"] = STATUS_UNAVAILABLE
        if outcomes_total == 0:
            block["reason"] = "没有任何一次 pytest 真的跑起来（全部 environment_unavailable，且逐用例结果为空）"
        else:
            block["reason"] = (
                "pytest 跑出了逐用例结果（共 " + str(outcomes_total) + " 条），但本次分类判为不可信 / "
                "环境不可用 ⇒ **不给可用性结论**，逐条原因见 pytest_sets[].reason"
            )
        block["unavailable"].append(
            {
                "what": "usability.pytest",
                "reason": block["reason"] + "："
                + "；".join(sorted({str(t.get("reason")) for t in block["pytest_sets"].values()})),
            }
        )
    else:
        block["status"] = STATUS_AVAILABLE
    worst = "red" if "red" in ran else ("ok" if "ok" in ran else "environment_unavailable")
    block["pytest_status"] = worst
    block["red"] = worst == "red"
    if block["pytest_sets"]:
        primary = block["pytest_sets"].get("default") or list(block["pytest_sets"].values())[0]
        block["counts"] = primary.get("counts")
        block["collection_errors"] = primary.get("collection_errors")
        block["declared"] = declared_outcomes(
            oracle or {}, primary.get("tests") or {}, tree
        )
    else:
        block["declared"] = {
            "pass_to_pass": {"status": STATUS_UNAVAILABLE, "reason": "没有可用的 pytest 运行"},
            "fail_to_pass": {"status": STATUS_UNAVAILABLE, "reason": "没有可用的 pytest 运行"},
        }
        block["unavailable"].append(
            {"what": "usability.pass_to_pass", "reason": "没有可用的 pytest 运行，无法判定回归"}
        )
    block["imports"] = probe_imports(tree=tree, python=sys.executable, workdir=workdir,
                                      roots=list(import_roots))
    surface = api_surface(tree, [item for item in files])
    if api_baseline is None:
        block["api"] = {
            "status": STATUS_UNAVAILABLE,
            "reason": "没有 --api-baseline：没有基线就断言不了「公开 API 没被破坏」。",
            "hint": "本次的公开 API 面已放在 api_baseline_candidate 里，可直接存成基线。",
        }
        block["api_baseline_candidate"] = surface
    else:
        comparison = compare_api_surface(surface, api_baseline)
        block["api"] = {"status": STATUS_AVAILABLE, **comparison}
        block["red"] = block["red"] or bool(comparison["breaking"])
    return block


def build_reading_context(
    *, tree: Path, digest: str, declarations: Mapping[str, Any], include_run: bool, sandbox: str
) -> dict:
    """reading_context（形状只有一份实现：provenance.reading_context）。"""

    return reading.build(
        source=reading.SOURCE_CLI,
        tree=reading.tree_block(tree, digest=digest),
        declarations=declarations,
        host=reading.host_block(
            sandbox=sandbox,
            extra={"tool": TOOL_ID, "tool_version": TOOL_VERSION, "python": _platform.python_version()},
        ),
        include_run=include_run,
    )

# --------------------------------------------------------------------------- 仪器自证


def _write_selfcheck_tree(root: Path, *, noisy: bool = True, decoys: bool = True) -> None:
    """造一棵最小树。decoys=诱饵配置与策略层目录；noisy=一条已知缺陷。"""

    for directory in ("pkg",):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    (root / "pkg" / "clean.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8", newline="\n"
    )
    if noisy:
        (root / "pkg" / "noisy.py").write_text(
            "import os\n\n\nX = \"" + "a" * 100 + "\"\nY = 1   \n",
            encoding="utf-8", newline="\n",
        )
    if not decoys:
        return
    for directory in ("policies/demo", "validation", "knowledge"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    decoy = "# 诱饵配置：仪器若读了它，E501/W291 就会消失。\n"
    decoy += "line-length = 200\n[lint]\nselect = [\"F401\"]\n"
    (root / "ruff.toml").write_text(decoy, encoding="utf-8", newline="\n")
    hostile = "# 更狠的诱饵：select 为空。\nline-length = 200\n[lint]\nselect = []\n"
    (root / "validation" / "ruff.toml").write_text(hostile, encoding="utf-8", newline="\n")
    (root / "policies" / "demo" / "RULE.yaml").write_text(
        "id: DEMO-001\nseverity: error\n", encoding="utf-8", newline="\n"
    )
    (root / "knowledge" / "corpus.yaml").write_text(
        "documents: []\n", encoding="utf-8", newline="\n"
    )


def _scan_pair(*, tree: Path, workdir: Path, ruff: str, configs: Mapping) -> tuple:
    """跑一次 scanner + security（自证与主流程共用同一条代码路径）。"""

    workdir.mkdir(parents=True, exist_ok=True)
    facts = tree_facts(tree)
    scanner = build_scanner_block(
        tree=tree, facts=facts, ruff=ruff, ruff_info=ruff_version(ruff),
        config=configs["norm"], changes=None,
    )
    security = build_security_block(
        tree=tree, facts=facts, ruff=ruff, config=configs["sec"], workdir=workdir,
        probe_scanners=False,
    )
    return scanner, security


def _projection(scanner: Mapping[str, Any], security: Mapping[str, Any]) -> dict:
    """独立性比较用的投影：只留"读了哪棵树就该得出什么数"的那部分。"""

    return {
        "scanner_metrics": scanner.get("metrics"),
        "scanner_findings": scanner.get("findings"),
        "scanner_config_digest": (scanner.get("instrument") or {}).get("config_digest"),
        "security_metrics": security.get("metrics"),
        "security_findings": security.get("findings"),
    }


def run_self_check(*, ruff: str, workdir: Path, configs: Mapping) -> dict:
    """AGENTS 第 45 条：配置隔离 + 敏感性变异 + 独立性变异（三条都预注册）。"""

    root = workdir / "tree"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    _write_selfcheck_tree(root)

    scanner_root, security_root = _scan_pair(
        tree=root, workdir=workdir / "run-root", ruff=ruff, configs=configs
    )
    codes_before = (scanner_root.get("metrics") or {}).get("counts_by_code") or {}
    isolation_pass = "E501" in codes_before and "W291" in codes_before
    isolation = {
        "criterion": (
            "预注册：树根与 validation/ 各放一份诱饵 ruff.toml（line-length=200、select 为空或只剩 F401）后，"
            "读数里**仍然**出现 E501 与 W291。两条都在 = 配置隔离成立；缺一条 = 仪器被诱饵带走了。"
        ),
        "observed_counts_by_code": codes_before,
        "verdict": "red" if isolation_pass else "green",
        "meaning": "red = 自证通过（仪器没被诱饵配置带走）；green = **自证失败**。",
        "decoy_files": ["ruff.toml", "validation/ruff.toml"],
    }

    # 敏感性变异跑在**一棵本来全绿的树**上：基线必须真的是 0，拐点才读得出来。
    sens = workdir / "tree-sens"
    if sens.exists():
        shutil.rmtree(sens, ignore_errors=True)
    _write_selfcheck_tree(sens, noisy=False, decoys=False)
    sens_before, sens_sec_before = _scan_pair(
        tree=sens, workdir=workdir / "run-sens-before", ruff=ruff, configs=configs
    )
    (sens / "pkg" / "clean.py").write_text(
        "import os\n\n\ndef add(a, b):\n    return eval(\"a + b\")\n", encoding="utf-8", newline="\n"
    )
    scanner_after, security_after = _scan_pair(
        tree=sens, workdir=workdir / "run-sens-after", ruff=ruff, configs=configs
    )
    scanner_before, security_before = sens_before, sens_sec_before
    before_norm = (scanner_before.get("metrics") or {}).get("violations_total")
    after_norm = (scanner_after.get("metrics") or {}).get("violations_total")
    before_sec = (security_before.get("metrics") or {}).get("findings_total")
    after_sec = (security_after.get("metrics") or {}).get("findings_total")
    sensitivity_pass = bool(
        isinstance(before_norm, int) and isinstance(after_norm, int) and after_norm > before_norm
        and isinstance(before_sec, int) and isinstance(after_sec, int) and after_sec > before_sec
        and not scanner_before.get("red") and scanner_after.get("red")
    )
    sensitivity = {
        "criterion": (
            "预注册：往 pkg/clean.py 注入未使用导入（F401）+ eval（ABSEC-001）后，"
            "scanner.violations_total 与 security.findings_total **都必须严格增加**，"
            "且 scanner.red 必须从 false 变成 true。四条全中 = 自证通过。"
        ),
        "before": {"violations_total": before_norm, "security_findings_total": before_sec,
                   "scanner_red": bool(scanner_before.get("red"))},
        "after": {"violations_total": after_norm, "security_findings_total": after_sec,
                  "scanner_red": bool(scanner_after.get("red"))},
        "verdict": "red" if sensitivity_pass else "green",
        "meaning": "red = 自证通过（注入的缺陷被独立仪器抓到）；green = **自证失败**。",
    }

    sanitized = workdir / "tree-sanitized"
    if sanitized.exists():
        shutil.rmtree(sanitized, ignore_errors=True)
    shutil.copytree(root, sanitized)
    removed: list = []
    for name in ("policies", "validation", "knowledge"):
        target = sanitized / name
        if target.exists():
            shutil.rmtree(target)
            removed.append(name + "/**")
    scanner_san, security_san = _scan_pair(
        tree=sanitized, workdir=workdir / "run-sanitized", ruff=ruff, configs=configs
    )
    left = json.dumps(_projection(scanner_root, security_root), sort_keys=True, ensure_ascii=False)
    right = json.dumps(_projection(scanner_san, security_san), sort_keys=True, ensure_ascii=False)
    independence = {
        "criterion": (
            "预注册：在副本上删掉 policies/**、validation/**、knowledge/** 后重跑，"
            "scanner+security 的投影（metrics / findings / 配置摘要）必须**逐字节不变**。"
            "变了 = 仪器读了策略层，独立性主张被证伪。"
        ),
        "removed": removed,
        "identical": left == right,
        "verdict": "red" if left == right else "green",
        "meaning": "red = 独立性成立（读数与策略层无关）；green = **独立性被证伪**。",
        "digest_after": sha256_text(left),
        "digest_sanitized": sha256_text(right),
    }
    passed = (
        isolation["verdict"] == "red"
        and sensitivity["verdict"] == "red"
        and independence["verdict"] == "red"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "instrument_self_proof",
        "tool": {"id": TOOL_ID, "version": TOOL_VERSION},
        "ruff": ruff_version(ruff),
        "tree": display_root(root),
        "config_isolation": isolation,
        "sensitivity_mutation": sensitivity,
        "independence_mutation": independence,
        "all_passed": passed,
        "note": (
            "red/green 的语义与别处相反：这里 red = 这条自证**通过**（仪器有反应 / 没被带走），"
            "green = 自证失败。写反了会把「仪器是死的」读成「一切正常」。"
        ),
    }
    evidence = workdir / "selfcheck-evidence.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json_dumps(payload), encoding="utf-8", newline="\n")
    payload["evidence_path"] = reading.display_path(evidence, root=REPO)
    payload["evidence_digest"] = sha256_text(json_dumps(payload))
    return payload


# --------------------------------------------------------------------------- 载荷组装

MODES = ("scan", "security", "usable", "blocked", "efficiency", "automation")


class UsageError(Exception):
    """用法 / 配置错误：退出码 2，**不产出读数**。"""


def parse_modes(value: str) -> list:
    """解析 --mode（逗号分隔；all = 全部六块）。"""

    items = [item.strip() for item in str(value).split(",") if item.strip()]
    if not items or "all" in items:
        return list(MODES)
    unknown = [item for item in items if item not in MODES]
    if unknown:
        raise UsageError(
            "未知 mode：" + ", ".join(unknown) + "；只接受 " + ", ".join(MODES) + " 或 all"
        )
    return [item for item in MODES if item in items]


def _changes_from_trees(base: Path, tree: Path, excludes: Sequence[str]) -> dict:
    """基线树 vs 终态树 -> 改动行口径（不需要 git）。"""

    raw = changed_lines_from_trees(base, tree, excludes)
    changed_lines = {
        rel: {"lines": entry["lines"], "whole_file": entry["whole_file"], "reason": entry["reason"]}
        for rel, entry in raw.items()
    }
    return {"changed_lines": changed_lines, "touched_files": sorted(changed_lines)}


def _changes_from_diff(diff_text: str) -> dict:
    """unified diff -> 改动行口径。"""

    parsed = parse_unified_diff(diff_text)
    changed_lines = {
        rel: {"lines": entry["lines"], "whole_file": bool(entry.get("is_new")),
              "reason": "unified_diff"}
        for rel, entry in parsed.items()
    }
    return {"changed_lines": changed_lines, "touched_files": sorted(changed_lines)}


def _read_json(path: Path) -> dict:
    """读一个 JSON 对象（非法 -> 退出码 2）。"""

    try:
        payload = json.loads(read_bytes(path).decode("utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        raise UsageError("读不到 " + str(path) + "：" + sanitize(error)) from error
    except json.JSONDecodeError as error:
        raise UsageError(str(path) + " 不是合法 JSON：" + sanitize(error)) from error
    if not isinstance(payload, dict):
        raise UsageError(str(path) + " 不是 JSON 对象")
    return payload


def _read_jsonl(path: Path) -> list:
    """读 JSONL（非法 -> 退出码 2）。"""

    try:
        return load_jsonl(path)
    except OSError as error:
        raise UsageError("读不到 " + str(path) + "：" + sanitize(error)) from error
    except (json.JSONDecodeError, ValueError) as error:
        raise UsageError(str(path) + " 不是合法 JSONL：" + sanitize(error)) from error


def _parse_test_selections(items: Sequence[str], tree: Path) -> list:
    """--test-selection label=path：每份文件给出"这次要跑哪些 node id"。"""

    selections: list = []
    for item in items:
        if "=" not in item:
            raise UsageError("--test-selection 需要 label=path 形态：" + item)
        label, raw = item.split("=", 1)
        path = Path(raw)
        if not path.is_file():
            candidate = tree / raw
            if not candidate.is_file():
                raise UsageError("--test-selection 的文件不存在：" + raw)
            path = candidate
        text = read_bytes(path).decode("utf-8").strip()
        if text.startswith("["):
            try:
                nodeids = [str(entry) for entry in json.loads(text)]
            except json.JSONDecodeError as error:
                raise UsageError("node id 清单不是合法 JSON：" + sanitize(error)) from error
        else:
            nodeids = [line.strip() for line in text.splitlines() if line.strip()]
        if not nodeids:
            raise UsageError("--test-selection " + label + " 的清单是空的")
        selections.append((label, nodeids))
    return selections


#: --mode 的取值 -> 载荷键。**必须一一对应**：少了这张表，exit_reasons 会静默变空
#: （本工具自己踩过：scan 的键叫 scanner，于是"有 red"被判成"没有理由"）。
MODE_BLOCK = {
    "scan": "scanner",
    "security": "security",
    "usable": "usability",
    "blocked": "block_precision",
    "efficiency": "efficiency",
    "automation": "automation",
}


def _collect_unavailable(payload: Mapping[str, Any], modes: Sequence[str]) -> list:
    """把各块的 unavailable 汇总到顶层（一条都不许静默少）。"""

    collected: list = []
    for name in modes:
        block = payload.get(MODE_BLOCK.get(name, name))
        if not isinstance(block, Mapping):
            continue
        items = [item for item in (block.get("unavailable") or []) if isinstance(item, Mapping)]
        for item in items:
            collected.append({"block": name, **{str(k): v for k, v in item.items()}})
        # 红队 V-1：块整体 unavailable 却没有块级 items 时，顶层**必须**补一条——
        # 否则"块说自己不可用、顶层说没有不可用"会同时成立，两个读法都能自圆其说。
        if block.get("status") == STATUS_UNAVAILABLE and not items:
            collected.append(
                {
                    "block": name,
                    "what": MODE_BLOCK.get(name, name),
                    "reason": str(block.get("reason") or "块整体 unavailable 但没有写 reason"),
                }
            )
    return collected


def _exit_reasons(payload: Mapping[str, Any], modes: Sequence[str]) -> list:
    """机器可读的「为什么是这个退出码」。"""

    reasons: list = []
    for name in modes:
        block = payload.get(MODE_BLOCK.get(name, name))
        if not isinstance(block, Mapping):
            continue
        if block.get("status") == STATUS_UNAVAILABLE:
            reasons.append(
                {"block": name, "kind": "unavailable",
                 "detail": str(block.get("reason") or "块整体 unavailable")}
            )
            continue
        if block.get("red"):
            reasons.append(
                {"block": name, "kind": "red", "detail": "独立仪器在这个块上给出了非空发现"}
            )
        for item in block.get("unavailable") or []:
            if isinstance(item, Mapping):
                reasons.append(
                    {"block": name, "kind": "unavailable",
                     "detail": str(item.get("what")) + "：" + str(item.get("reason"))}
                )
    return reasons


def _declarations(configs: Mapping, args: argparse.Namespace, workdir: Path) -> dict:
    """reading_context.declarations：本次读数用的是哪几套声明。"""

    declarations: dict = {}
    for name in ("norm", "sec"):
        declarations["frozen_config_" + name] = reading.declaration_block(
            configs[name]["path"], root=REPO
        )
    for key, value in (
        ("oracle", args.oracle),
        ("api_baseline", args.api_baseline),
        ("blocked_edits", args.blocked_edits),
        ("allowed_edits", args.allowed_edits),
        ("runs", args.runs),
        ("actions", args.actions),
    ):
        if not value:
            continue
        path = Path(value)
        declarations[key] = (
            reading.declaration_block(path, root=REPO)
            if path.is_file()
            else reading.unavailable("输入文件不存在：" + sanitize(value))
        )
    declarations["workdir"] = {
        "status": reading.STATUS_AVAILABLE,
        "path": reading.display_path(workdir, root=REPO),
    }
    return declarations


def gather(args: argparse.Namespace) -> dict:
    """跑全部请求的量，组装载荷。"""

    modes = parse_modes(args.mode)
    excludes = [item.strip() for item in (args.exclude or "").split(",") if item.strip()]
    run_id = "deterministic" if args.deterministic else uuid.uuid4().hex[:12]
    workdir = Path(args.workdir).resolve() if args.workdir else REPO / ".tmp" / "ab-measure" / run_id
    workdir.mkdir(parents=True, exist_ok=True)
    ruff = args.ruff or shutil.which("ruff") or "ruff"
    ruff_info = ruff_version(ruff)
    configs = {name: materialize_config(name, workdir) for name in ("norm", "sec")}

    if args.self_check:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "ab_measurement",
            "self_check": run_self_check(ruff=ruff, workdir=workdir, configs=configs),
        }
    if not args.tree:
        raise UsageError("缺 --tree <DIR>")
    tree = Path(args.tree).resolve()
    if not tree.is_dir():
        raise UsageError("--tree 不是目录：" + str(args.tree))
    READS.root = tree
    facts = tree_facts(tree, excludes)
    try:
        digest = workspace_tree_digest(tree).sha256
    except (ProvenanceError, OSError, ValueError) as error:
        digest = "unprovable:" + type(error).__name__
    changes: Optional[dict] = None
    if args.baseline_tree:
        base = Path(args.baseline_tree).resolve()
        if not base.is_dir():
            raise UsageError("--baseline-tree 不是目录：" + str(args.baseline_tree))
        changes = _changes_from_trees(base, tree, excludes)
    elif args.diff:
        diff_path = Path(args.diff)
        if not diff_path.is_file():
            diff_path = tree / args.diff
        if not diff_path.is_file():
            raise UsageError("--diff 的文件不存在：" + str(args.diff))
        changes = _changes_from_diff(read_bytes(diff_path).decode("utf-8"))

    oracle = _read_json(Path(args.oracle)) if args.oracle else None
    api_baseline = _read_json(Path(args.api_baseline)) if args.api_baseline else None
    blocked = _read_jsonl(Path(args.blocked_edits)) if args.blocked_edits else []
    known_fp = (
        _read_jsonl(Path(args.known_false_positive_edits))
        if args.known_false_positive_edits
        else []
    )
    allowed = _read_jsonl(Path(args.allowed_edits)) if args.allowed_edits else []
    runs = _read_jsonl(Path(args.runs)) if args.runs else []
    actions = _read_jsonl(Path(args.actions)) if args.actions else []
    selections = _parse_test_selections(args.test_selection or [], tree)

    payload: dict = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ab_measurement",
        "tool": {
            "id": TOOL_ID,
            "version": TOOL_VERSION,
            "argv": [sanitize(part) for part in sys.argv[1:]],
        },
        "inputs": {
            "tree": display_root(tree),
            "tree_digest": digest,
            "baseline_tree": display_root(Path(args.baseline_tree).resolve())
            if args.baseline_tree
            else None,
            "diff": sanitize(args.diff) if args.diff else None,
            "oracle": sanitize(args.oracle) if args.oracle else None,
            "blocked_edits": len(blocked),
            "allowed_edits": len(allowed),
            "runs": len(runs),
            "actions": len(actions),
            "test_selections": [label for label, _ in selections],
            "modes": modes,
            "excludes": excludes,
        },
    }

    if "scan" in modes:
        payload["scanner"] = build_scanner_block(
            tree=tree, facts=facts, ruff=ruff, ruff_info=ruff_info,
            config=configs["norm"], changes=changes,
        )
    if "security" in modes:
        payload["security"] = build_security_block(
            tree=tree, facts=facts, ruff=ruff, config=configs["sec"],
            workdir=workdir, probe_scanners=True,
        )
    if "usable" in modes:
        payload["usability"] = build_usability_block(
            tree=tree, oracle=oracle, workdir=workdir,
            import_roots=[item.strip() for item in (args.import_roots or "src,.").split(",")
                          if item.strip()],
            api_baseline=api_baseline, test_selections=selections, files=facts["files"],
            timeout_s=float(args.test_timeout),
        )
    if "blocked" in modes:
        base_tree = Path(args.baseline_tree).resolve() if args.baseline_tree else tree
        payload["block_precision"] = {
            "status": STATUS_AVAILABLE,
            "homology": HOMOLOGY["block_precision"],
            "scope": args.cf_scope,
            "with_tests": bool(args.with_tests),
            "blocked": counterfactual(
                edits=blocked, base_tree=base_tree, workdir=workdir, ruff=ruff, configs=configs,
                scope=args.cf_scope, with_tests={} if args.with_tests else None,
                oracle=oracle or {}, max_edits=int(args.max_counterfactuals or 0),
            ),
        }
        if not blocked:
            payload["block_precision"]["blocked"]["status"] = STATUS_UNAVAILABLE
            payload["block_precision"]["blocked"]["reason"] = (
                "没有 --blocked-edits：拿不到「被拦下的编辑是什么」，精确量无法计算。"
            )
            payload["block_precision"]["status"] = STATUS_UNAVAILABLE
            payload["block_precision"]["reason"] = payload["block_precision"]["blocked"]["reason"]
            payload["block_precision"]["unavailable"] = [
                {"what": "block_precision.precision",
                 "reason": payload["block_precision"]["reason"]}
            ]
        if known_fp:
            control = counterfactual(
                edits=known_fp, base_tree=base_tree, workdir=workdir, ruff=ruff, configs=configs,
                scope=args.cf_scope, with_tests={} if args.with_tests else None,
                oracle=oracle or {}, max_edits=int(args.max_counterfactuals or 0),
            )
            denominator = control["denominator"]
            control["positive_control"] = {
                "declared_false_positives": denominator,
                "instrument_says_red": control["red"],
                "max_achievable_precision": (
                    round((denominator - control["red"]) / denominator, 6) if denominator else None
                ),
                "reading": (
                    "这一份是**阳性对照**：这些编辑按声明**不是**缺陷。仪器仍判红的比例 = 仪器读数的"
                    "天花板（它把「与 ruff 一致」当成了「真的有缺陷」）。"
                ),
                "caveat": (
                    "对照的「声明」若来自平台自己的规则文档，那它是**关于仪器天花板**的探针，"
                    "不是 A/B 的结局变量——不许把它算进 precision 的分子分母。"
                ),
            }
            payload["block_precision"]["positive_control"] = control
        if allowed:
            payload["block_precision"]["allowed_recall_proxy"] = counterfactual(
                edits=allowed, base_tree=base_tree, workdir=workdir, ruff=ruff, configs=configs,
                scope=args.cf_scope, with_tests={} if args.with_tests else None,
                oracle=oracle or {}, max_edits=int(args.max_counterfactuals or 0),
            )
            payload["block_precision"]["allowed_recall_proxy"]["caveat"] = (
                "被放行的编辑集合与被拦下的编辑集合**不是同一个总体**：这里的比例只是 recall 的"
                "**代理下界**，不能与 precision 互补，也永远不写成 recall。"
            )
    if "efficiency" in modes:
        latency: dict = {"status": STATUS_UNAVAILABLE, "reason": "没有 --latency-cmd"}
        if args.latency_cmd:
            try:
                parsed = json.loads(args.latency_cmd)
            except json.JSONDecodeError as error:
                raise UsageError("--latency-cmd 不是合法 JSON 数组：" + sanitize(error)) from error
            if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
                raise UsageError("--latency-cmd 必须是字符串数组（不要 shell 字符串）")
            if args.deterministic:
                latency = {
                    "status": STATUS_NOT_APPLICABLE,
                    "reason": "确定性模式不测时间（计时不可能逐字节相同）。",
                }
            else:
                latency = measure_latency(
                    argv=parsed, repeats=int(args.latency_repeats), workdir=workdir, cwd=tree,
                    allow_side_effects=bool(args.latency_allow_side_effects),
                )
        payload["efficiency"] = {
            "status": STATUS_AVAILABLE,
            "homology": HOMOLOGY["efficiency"],
            "deterministic": False,
            "decision_latency": latency,
            "runs": efficiency_from_runs(runs)
            if runs
            else {
                "status": STATUS_UNAVAILABLE,
                "reason": "没有 --runs：算不了每任务 wall-clock 增量与重试次数",
            },
            "caliber": (
                "warm-up 只剔**首个**样本并单列 cold_start_ms；分位数用最近秩法；"
                "n 与全部样本都写出来，读的人可以自己重算。"
            ),
        }
    if "automation" in modes:
        payload["automation"] = {
            "status": STATUS_AVAILABLE,
            "homology": HOMOLOGY["automation"],
            "deterministic": True,
            **automation_from(actions=actions, runs=runs),
        }

    # 红队 V-4：没请求的块必须显式说"没请求"，不能靠"键不在"让读者自己猜。
    for mode_name, block_key in MODE_BLOCK.items():
        if mode_name not in modes and block_key not in payload:
            payload[block_key] = {
                "status": "not_requested",
                "role": "outcome",
                "reason": "本次 --mode " + str(args.mode) + " 没有请求这个量",
            }

    payload["independence"] = {
        "independent_of_policy_layer": True,
        "independent_of_underlying_linter": False,
        "grade_summary": {
            "scanner": HOMOLOGY["scanner"]["grade"],
            "security_route_b_ruff": HOMOLOGY["security_ruff"]["grade"],
            "security_route_b_ast": HOMOLOGY["security_ast"]["grade"],
            "usability": HOMOLOGY["usability"]["grade"],
            "block_precision": HOMOLOGY["block_precision"]["grade"],
            "automation": HOMOLOGY["automation"]["grade"],
        },
        "measured_tree_reads": READS.as_list(),
        "reads_note": (
            "这份清单只覆盖**本仪器自己**打开的文件。外部子进程（ruff / pytest）读什么由 argv 决定，"
            "不在清单里——它不是「平台读过的全集」的证明，只是「仪器自己没有读策略层」的证据。"
        ),
        "policy_layer_reads": [
            item for item in READS.as_list() if item.startswith(POLICY_LAYER_PREFIXES)
        ],
        "policy_imports": sorted(
            name
            for name in sys.modules
            if name.split(".")[0]
            in ("policy", "policies", "enforcement", "validators", "orchestration", "policy_api")
        ),
        "subprocesses": SUBCOMMANDS,
        "known_limits": [
            "底层 linter 是同一条 ruff 二进制：规范性、安全回退、反事实的同源等级都是"
            "policy_layer_independent_linter_dependent / half_homologous_same_binary。",
            "自写 AST 安全检查器**没有被任何外部 oracle 校准**，覆盖面窄。",
            "依赖漏洞（pip-audit / OSV）与 semgrep 规则库在本机不可得。",
            "反事实只覆盖可重建的被拦编辑，且只测 precision；recall 只有代理。",
            "冻结配置的 line-length=88 与本仓库的 100 不同：绝对水平不可跨口径比较。",
        ],
    }
    payload["reading_context"] = build_reading_context(
        tree=tree, digest=digest, declarations=_declarations(configs, args, workdir),
        include_run=not args.deterministic, sandbox="unknown",
    )
    payload["unavailable"] = _collect_unavailable(payload, modes)
    reasons = _exit_reasons(payload, modes)
    payload["exit_reasons"] = reasons
    payload["exit_code"] = 1 if reasons else 0
    return payload


def build_parser() -> argparse.ArgumentParser:
    """命令行。**一个工具、一个 JSON**：不拆成多个脚本。"""

    parser = argparse.ArgumentParser(
        prog="ab_measure",
        description="AB 独立测量仪器：六个量的读数（带 schema_version + reading_context）。",
    )
    parser.add_argument("--tree", help="被测树（任意目录）")
    parser.add_argument("--out", help="同时把载荷写到这个文件（可选）")
    parser.add_argument("--mode", default="all",
                        help="scan,security,usable,blocked,efficiency,automation 或 all")
    parser.add_argument("--baseline-tree", help="基线树：算 new-side 的 + 行集合（不需要 git）")
    parser.add_argument("--diff", help="unified diff 文件：与 --baseline-tree 二选一")
    parser.add_argument("--oracle", help="oracle JSON（python / test_command / pass_to_pass ...）")
    parser.add_argument("--test-selection", action="append", default=[],
                        help="label=path：要跑哪些 node id（可重复；JSON 数组或一行一个）")
    parser.add_argument("--test-timeout", type=float, default=900.0, help="pytest 超时（秒）")
    parser.add_argument("--blocked-edits", help="被拦下的编辑 JSONL（精确量输入）")
    parser.add_argument("--allowed-edits", help="被放行的编辑 JSONL（recall 代理输入）")
    parser.add_argument("--known-false-positive-edits",
                        help="**阳性对照** JSONL：已登记为误报的编辑（如平台规则文档自己声明的豁免位置）。"
                             "仪器仍判红的比例 = precision 读数的天花板。")
    parser.add_argument("--max-counterfactuals", type=int, default=0, help="反事实条数上限（0=不限）")
    parser.add_argument("--cf-scope", default="file", choices=("file", "tree"),
                        help="反事实重扫范围（默认 file：只重扫被动过的文件）")
    parser.add_argument("--with-tests", action="store_true", help="反事实里也跑测试（慢）")
    parser.add_argument("--runs", help="run 记录 JSONL（高效 / 全自动化）")
    parser.add_argument("--actions", help="逐动作日志 JSONL（覆盖率 / bypass）")
    parser.add_argument("--latency-cmd", help="单次判定命令（JSON 字符串数组）")
    parser.add_argument("--latency-repeats", type=int, default=30, help="重复次数（默认 30）")
    parser.add_argument("--latency-allow-side-effects", action="store_true",
                        help="确认该命令无副作用后才允许重复跑")
    parser.add_argument("--api-baseline", help="公开 API 基线 JSON")
    parser.add_argument("--import-roots", default="src,.",
                        help="可导入性探测的根（逗号分隔，默认 src,.）")
    parser.add_argument("--exclude", default="", help="额外排除的目录名（逗号分隔）")
    parser.add_argument("--ruff", help="ruff 可执行文件（默认从 PATH 找）")
    parser.add_argument("--workdir", help="临时目录（默认 .tmp/ab-measure/<run>）")
    parser.add_argument("--deterministic", action="store_true",
                        help="固定 run id、去掉 reading_context.run、计时块标 not_applicable")
    parser.add_argument("--self-check", action="store_true",
                        help="跑仪器自证（配置隔离 + 敏感性变异 + 独立性变异）")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """入口：0 = 全 available 且无 red；1 = 有 unavailable 或 red；2 = 用法错误。"""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.self_check and not args.tree:
        sys.stderr.write("ab_measure: 缺 --tree <DIR>（或 --self-check）\n")
        return 2
    try:
        payload = gather(args)
    except UsageError as error:
        sys.stderr.write("ab_measure: " + sanitize(error) + "\n")
        return 2
    text = json_dumps(payload)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    sys.stdout.write(text)
    if args.self_check:
        return 0 if payload["self_check"]["all_passed"] else 1
    return int(payload.get("exit_code") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
