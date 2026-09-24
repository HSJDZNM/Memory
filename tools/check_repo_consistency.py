"""仓库一致性检查：把"文档写的一套、配置跑的另一套"这类漂移变成会失败的检查。

三类检查，全部是客观可判定的（不做措辞评审）：

1. 依赖锁：requirements.in / pyproject.toml / requirements.lock 三者的直接依赖必须一致，
   且锁文件里的固定版本确实满足声明区间；
2. 文档与配置：文档与 CI 里引用的 workflow 文件必须存在且互相覆盖；任何地方要求
   uv.lock 时它必须真的存在（uv sync 在没有锁文件时不是"锁定安装"）；pytest 的
   testpaths 与 README 提到的测试目录必须存在；
3. 工具清单：tools/README.md 里的脚本必须存在，磁盘上的脚本必须被登记。

用法：
    python tools/check_repo_consistency.py

退出码：0 一致；1 发现漂移；2 用法或环境错误。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOCS_WITH_CONFIG_CLAIMS = ("README.md", "AGENTS.md")
WORKFLOW_DIR = Path(".github/workflows")

# 这些脚本属于离线文档镜像流水线，tools/README.md 用一段散文而不是表格登记它们。
INVENTORY_EXEMPT = {"mirror_docs.py", "learn_site.py", "pep_site.py", "dora_site.py"}

_REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*([<>=!~][^;]*)?$")
_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][0-9A-Za-z.\-+]*)$")
_SPEC_RE = re.compile(r"^(>=|<=|==|!=|~=|>|<)?\s*([0-9][0-9A-Za-z.\-+]*)$")
_WORKFLOW_REF_RE = re.compile(r"\.github/workflows/([A-Za-z0-9._-]+\.ya?ml)")
_SCRIPT_RE = re.compile(r"([a-z0-9_]+\.py)")
_UV_SYNC_RE = re.compile(r"^\s*uv sync\b")
_INSTALL_RE = re.compile(r"\bpip install\s+(?:[^\n]*?)-r\s+([^\s#]+)")


def version_tuple(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in text.split("."):
        digits = re.match(r"^\d+", chunk)
        if digits is None:
            break
        parts.append(int(digits.group(0)))
    return tuple(parts)


def satisfies(pinned: str, specifier: str) -> bool:
    """锁文件里的固定版本是否满足依赖声明（支持逗号分隔的界定符组合）。"""

    specifier = specifier.strip()
    if not specifier:
        return True
    return all(_satisfies_one(pinned, item.strip()) for item in specifier.split(",") if item.strip())


def _satisfies_one(pinned: str, specifier: str) -> bool:
    match = _SPEC_RE.match(specifier)
    if match is None:
        return False
    operator = match.group(1) or "=="
    bound = version_tuple(match.group(2))
    current = version_tuple(pinned)
    if operator == ">=":
        return current >= bound
    if operator == "<=":
        return current <= bound
    if operator == ">":
        return current > bound
    if operator == "<":
        return current < bound
    if operator == "==":
        return current == bound
    if operator == "!=":
        return current != bound
    # ~=X.Y[.Z]：下界为 X.Y[.Z]，上界把倒数第二位加一
    if len(bound) < 2:
        return False
    upper = list(bound[:-2]) + [bound[-2] + 1]
    return current >= bound and current < tuple(upper)


def read_requirements_in() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (ROOT / "requirements.in").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = _REQ_RE.match(line)
        if match is None:
            raise SystemExit("requirements.in 里有无法解析的行: %r" % line)
        result[match.group(1).lower()] = (match.group(2) or "").strip()
    return result


def read_requirements_lock() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("--hash"):
            continue
        match = _PIN_RE.match(line)
        if match is None:
            continue
        result[match.group(1).lower()] = match.group(2)
    return result


def read_pyproject() -> dict[str, str]:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = document.get("project", {})
    result: dict[str, str] = {}
    for item in list(project.get("dependencies", [])) + list(
        project.get("optional-dependencies", {}).get("dev", [])
    ):
        match = _REQ_RE.match(str(item).strip())
        if match is None:
            raise SystemExit("pyproject.toml 里有无法解析的依赖: %r" % item)
        result[match.group(1).lower()] = (match.group(2) or "").strip()
    return result


def check_lock() -> list[str]:
    issues: list[str] = []
    declared = read_requirements_in()
    locked = read_requirements_lock()
    project = read_pyproject()

    for name in sorted(set(declared) - set(project)):
        issues.append("requirements.in 声明了 %s，pyproject.toml 里没有" % name)
    for name in sorted(set(project) - set(declared)):
        issues.append("pyproject.toml 声明了 %s，requirements.in 里没有" % name)
    for name in sorted(set(declared) & set(project)):
        if declared[name] != project[name]:
            issues.append(
                "%s 的版本区间不一致：requirements.in=%r，pyproject.toml=%r"
                % (name, declared[name], project[name])
            )

    for name, specifier in sorted(declared.items()):
        pinned = locked.get(name)
        if pinned is None:
            issues.append("requirements.lock 没有固定 %s（直接依赖必须全部锁定）" % name)
            continue
        if not satisfies(pinned, specifier):
            issues.append(
                "%s 锁定为 %s，不满足声明的 %r：锁文件与依赖声明已经漂移，"
                "请在验证过的环境重新生成 requirements.lock" % (name, pinned, specifier)
            )
    for name in sorted(set(locked) - set(declared)):
        issues.append("requirements.lock 固定了未声明的直接依赖 %s" % name)
    return issues


def check_docs_and_config() -> list[str]:
    issues: list[str] = []
    workflows = sorted(path.name for path in (ROOT / WORKFLOW_DIR).glob("*.y*ml"))
    if not workflows:
        issues.append(".github/workflows 下没有任何 workflow")

    referenced: dict[str, list[str]] = {}
    for name in DOCS_WITH_CONFIG_CLAIMS:
        text = (ROOT / name).read_text(encoding="utf-8")
        for match in _WORKFLOW_REF_RE.finditer(text):
            referenced.setdefault(match.group(1), []).append(name)
    for workflow, sources in sorted(referenced.items()):
        if workflow not in workflows:
            issues.append("%s 引用了不存在的 workflow %s" % (", ".join(sources), workflow))
    for workflow in workflows:
        if workflow not in referenced:
            issues.append("workflow %s 没有被 README.md / AGENTS.md 登记" % workflow)

    # 只认"命令形态"的安装指令：散文里提到某个锁文件名不算要求，否则解释性文字会被误判。
    sources = [*DOCS_WITH_CONFIG_CLAIMS, *(str(WORKFLOW_DIR / name) for name in workflows)]
    unresolved: list[str] = []
    uv_sync_lines: list[str] = []
    for relative in sources:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ">")):
                continue
            if _UV_SYNC_RE.search(stripped):
                uv_sync_lines.append("%s:%d" % (relative, number))
            for match in _INSTALL_RE.finditer(stripped):
                referenced = match.group(1).strip().strip('"').strip("'")
                if not (ROOT / referenced).is_file():
                    unresolved.append("%s:%d -> %s" % (relative, number, referenced))
    if uv_sync_lines and not (ROOT / "uv.lock").is_file():
        issues.append(
            "这些位置用 uv sync 安装，但仓库没有 uv.lock（uv sync 在没有锁文件时会重新解析，"
            "不是锁定安装）：" + ", ".join(uv_sync_lines[:5])
        )
    for item in unresolved:
        issues.append("安装指令引用了不存在的锁文件：%s" % item)

    pytest_ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    testpaths = re.search(r"^testpaths\s*=\s*(.+)$", pytest_ini, re.MULTILINE)
    if testpaths:
        for item in testpaths.group(1).split():
            if not (ROOT / item).is_dir():
                issues.append("pytest.ini 的 testpaths 指向不存在的目录 %s" % item)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for match in re.finditer(r"tests/([a-z_]+)\b", readme):
        candidate = ROOT / "tests" / match.group(1)
        if candidate.suffix:
            continue
        if not candidate.exists():
            issues.append("README.md 提到的 tests/%s 不存在" % match.group(1))
    return issues


def check_notebook_form() -> list[str]:
    """由生成器产出的 notebook 必须是规范形态（手写的不在检查范围）。

    在 Jupyter / VS Code 里"运行并保存"会把执行输出与 execution_count 写回 .ipynb，
    而生成器写出来的形态里这两样永远是空的，于是 CI 的"手册同步"步骤会逐字节比较失败。
    这里只做形态判断、不跑生成器（那个要几分钟），让问题在本地一秒暴露。
    """

    # 两类由生成器产出的 notebook：按阶段的学习手册，与按技术的讲解 notebook。
    # 新增第三类时加一行即可——但**必须**加：目录改层而检查器没跟着改，会让本检查"命中 0 个、
    # 判定一致"，静默失效正是本仓库最忌讳的失败形态（所以下面显式报错，不放过空集合）。
    groups = (
        (
            "docs/project/learning 下的 */walkthrough.ipynb",
            "*/walkthrough.ipynb",
            ROOT / "docs" / "project" / "learning",
            "python tools/build_learning_notebook.py",
        ),
        (
            "docs/project/architecture/tech-detail/notebooks 下的 *.ipynb",
            "*.ipynb",
            ROOT / "docs" / "project" / "architecture" / "tech-detail" / "notebooks",
            "python docs/project/architecture/tech-detail/notebooks/build_notebooks.py",
        ),
    )

    issues: list[str] = []
    for label, pattern, directory, regenerate in groups:
        notebooks = sorted(directory.glob(pattern))
        if not notebooks:
            issues.append(
                "%s 下没有找到任何 notebook：检查器路径与实际目录不一致（检查器不会静默通过一个空集合）"
                % label
            )
            continue
        for path in notebooks:
            relative = path.relative_to(ROOT).as_posix()
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                issues.append("%s 不可解析：%s" % (relative, error))
                continue
            for index, cell in enumerate(document.get("cells", [])):
                if cell.get("outputs"):
                    issues.append(
                        "%s 第 %d 个单元带执行输出：这份文件在 Jupyter 里跑过并保存了；"
                        "重新生成即可恢复（%s）" % (relative, index, regenerate)
                    )
                if cell.get("execution_count") is not None:
                    issues.append(
                        "%s 第 %d 个单元的 execution_count 不为空（同样是被编辑器写回的痕迹）"
                        % (relative, index)
                    )
    return issues


def check_tool_inventory() -> list[str]:
    """只认表格第一列的脚本名：散文里提到的别处脚本（例如 enforcement/audit.py）不是本目录的清单。"""

    issues: list[str] = []
    readme = (ROOT / "tools" / "README.md").read_text(encoding="utf-8")
    mentioned: set[str] = set()
    for line in readme.splitlines():
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        if first.startswith("`") and first.endswith("`"):
            name = first.strip("`")
            if name.endswith(".py"):
                mentioned.add(name)
    on_disk = {path.name for path in (ROOT / "tools").glob("*.py")}
    for name in sorted(mentioned - on_disk):
        issues.append("tools/README.md 登记了不存在的脚本 %s" % name)
    for name in sorted(on_disk - mentioned - INVENTORY_EXEMPT):
        issues.append("tools/%s 没有登记到 tools/README.md" % name)
    return issues


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        print(__doc__)
        return 2
    sections = (
        ("依赖锁", check_lock()),
        ("文档与配置", check_docs_and_config()),
        ("手册形态", check_notebook_form()),
        ("工具清单", check_tool_inventory()),
    )
    total = 0
    for label, issues in sections:
        if issues:
            print("[%s] %d 处漂移" % (label, len(issues)))
            for item in issues:
                print("  ! " + item)
            total += len(issues)
        else:
            print("[%s] 一致" % label)
    if total:
        print("\n共 %d 处漂移：先修配置或文档，不要靠放宽检查来变绿" % total)
        return 1
    print("\n仓库一致性检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
