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


class EnvironmentProblem(Exception):
    """用法或环境错误：退出码 2。

    与"发现漂移"（退出码 1）必须能分开——两者都退 1 时，CI 读不出"这次到底检查了没有"。
    旧实现在两处用 `raise SystemExit("...")` 表达环境错误：字符串参数的 SystemExit 退出码是 1，
    而读不到 pytest.ini / README.md / AGENTS.md / tools/README.md 时抛的是裸 FileNotFoundError。
    """


def _read_text(relative: str) -> str:
    """读仓库内文本文件：读不出来是**环境错误**（退出 2），不是"文档漂移"。"""

    try:
        return (ROOT / relative).read_text(encoding="utf-8")
    except OSError as error:
        raise EnvironmentProblem(
            "%s 读不出来（%s: %s）——这是环境错误，不是文档漂移"
            % (relative, type(error).__name__, error)
        ) from error

DOCS_WITH_CONFIG_CLAIMS = ("README.md", "AGENTS.md")
WORKFLOW_DIR = Path(".github/workflows")

# 这些脚本属于离线文档镜像流水线，tools/README.md 用一段散文而不是表格登记它们。
INVENTORY_EXEMPT = {"mirror_docs.py", "learn_site.py", "pep_site.py", "dora_site.py"}

# 依赖声明：包名 + **可选** extras 段（`httpx[http2]>=0.27`）+ 可选的界定符。
# 旧正则不认 extras：合法声明直接走 EnvironmentProblem（退出 2 = "查不了"），于是 CI 红在一个
# **正确**的声明上，人只能改声明来迁就工具——"把自己的局限说成对方的问题"。包名仍取第一段
# （extras 不改变依赖身份）。
_REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\s*\[[^\]]*\])?\s*([<>=!~][^;]*)?$")
# 锁文件里的固定行：可选 extras（pkg[extra]==1.2）与可选环境标记（pkg==1.2 ; python_version >= "3.8"）。
# 旧正则只认"光秃秃的 pkg==1.2"：带 extras 或标记的行会被**静默丢掉**，随后报成"没有固定 X"
# ——明明固定了，只是没解析出来。
_PIN_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([0-9][0-9A-Za-z.\-+]*)(?:\s*;.*)?$"
)
_SPEC_RE = re.compile(r"^(>=|<=|==|!=|~=|>|<)?\s*([0-9][0-9A-Za-z.\-+]*)$")
_WORKFLOW_REF_RE = re.compile(r"\.github/workflows/([A-Za-z0-9._-]+\.ya?ml)")
_SCRIPT_RE = re.compile(r"([a-z0-9_]+\.py)")
_UV_SYNC_RE = re.compile(r"^\s*uv sync\b")
# README 里提到的测试**目录**：`tests/<名字>` 后面不能再跟 `.` 或名字字符——`tests/test_cli.py`
# 是文件不是目录（旧写法 `tests/([a-z_]+)\b` 在点号前也成立，于是把文件名报成"目录不存在"）。
README_TEST_DIR_RE = re.compile(r"tests/([a-z_]+)(?![a-z_0-9_.])")
_INSTALL_RE = re.compile(r"\bpip install\s+(?:[^\n]*?)-r\s+([^\s#]+)")


# PEP 440 的一个**显式子集**：release 段 + 预发布(a/b/rc) / post / dev / local。
# 认不出的形态抛 ValueError —— 由调用方记成"无法比较"的漂移，而不是静默截断成可比的数。
_VERSION_RE = re.compile(
    r"^(?P<release>\d+(?:\.\d+)*)"
    r"(?:(?P<pre>a|b|rc)(?P<pre_n>\d*))?"
    r"(?:\.post(?P<post>\d+))?"
    r"(?:\.dev(?P<dev>\d+))?"
    r"(?:\+[0-9A-Za-z.]+)?$"
)
_PRE_LETTER_RANK = {"a": 0, "b": 1, "rc": 2}
# 阶段秩：dev < 预发布 < 正式 < post（PEP 440 的大小顺序）
_STAGE_DEV, _STAGE_PRE, _STAGE_FINAL, _STAGE_POST = -1, 0, 1, 2


def _version_key(text: str) -> tuple[tuple[int, ...], int, int]:
    """把版本号压成 (release 段, 阶段秩, 阶段号)；不认识的形态抛 ValueError。"""

    match = _VERSION_RE.match(text.strip())
    if match is None:
        raise ValueError("无法按 PEP 440 比较的版本号: %r" % text)
    release = tuple(int(part) for part in match.group("release").split("."))
    if match.group("dev") is not None:
        return release, _STAGE_DEV, int(match.group("dev"))
    if match.group("pre") is not None:
        number = int(match.group("pre_n") or 0)
        return release, _STAGE_PRE, _PRE_LETTER_RANK[match.group("pre")] * 1000 + number
    if match.group("post") is not None:
        return release, _STAGE_POST, int(match.group("post"))
    return release, _STAGE_FINAL, 0


def compare_versions(left: str, right: str) -> int:
    """PEP 440 口径的三向比较：release 段右侧补零对齐（1.4 == 1.4.0），再比阶段。"""

    left_release, left_stage, left_number = _version_key(left)
    right_release, right_stage, right_number = _version_key(right)
    width = max(len(left_release), len(right_release))
    padded_left = left_release + (0,) * (width - len(left_release))
    padded_right = right_release + (0,) * (width - len(right_release))
    if padded_left != padded_right:
        return 1 if padded_left > padded_right else -1
    if left_stage != right_stage:
        return 1 if left_stage > right_stage else -1
    if left_number != right_number:
        return 1 if left_number > right_number else -1
    return 0


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
    bound = match.group(2)
    if operator == "~=":
        return _compatible_release(pinned, bound)
    order = compare_versions(pinned, bound)
    if operator == ">=":
        return order >= 0
    if operator == "<=":
        return order <= 0
    if operator == ">":
        return order > 0
    if operator == "<":
        return order < 0
    if operator == "==":
        return order == 0
    if operator == "!=":
        return order != 0
    return False


def _compatible_release(pinned: str, bound: str) -> bool:
    """~=X.Y[.Z]：下界 X.Y[.Z]，上界把倒数第二段加一（PEP 440 的兼容版本区间）。"""

    release, stage, _number = _version_key(bound)
    if len(release) < 2 or stage != _STAGE_FINAL:
        raise ValueError("~= 的下界必须是至少两段的正式版本，得到 %r" % bound)
    if compare_versions(pinned, bound) < 0:
        return False
    upper = release[:-2] + (release[-2] + 1,)
    candidate, _stage, _number = _version_key(pinned)
    width = max(len(candidate), len(upper))
    return candidate + (0,) * (width - len(candidate)) < upper + (0,) * (width - len(upper))


def _normalize_specifier(specifier: str) -> str:
    """比较用的规范化形式：去掉全部空白（界定符之间的空白不改变区间语义）。"""

    return re.sub(r"\s+", "", specifier)


def read_requirements_in() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in _read_text("requirements.in").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = _REQ_RE.match(line)
        if match is None:
            raise EnvironmentProblem("requirements.in 里有无法解析的行: %r" % line)
        result[match.group(1).lower()] = (match.group(2) or "").strip()
    return result


def read_requirements_lock() -> tuple[dict[str, str], list[str]]:
    """(固定版本表, 解析不了的行)。

    解析不了的行**不再静默丢弃**：丢了之后它要么让一个真被固定的包报成"没有固定"（误导），
    要么连报都不报（畸形固定行永远看不见）。返回值带着它们，由 check_lock 记成漂移。
    """

    result: dict[str, str] = {}
    unparsed: list[str] = []
    for number, raw in enumerate(_read_text("requirements.lock").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("--hash"):
            continue
        # 生成的锁文件用行尾反斜杠续行（pip 的 --hash 必须与依赖在同一条逻辑行上）：
        # 解析时先去掉续行符，否则每条固定版本都会被判成"没有锁定"。
        line = line.removesuffix("\\").strip()
        if not line:
            continue
        match = _PIN_RE.match(line)
        if match is None:
            unparsed.append("requirements.lock:%d: %r" % (number, line))
            continue
        result[match.group(1).lower()] = match.group(2)
    return result, unparsed


def read_pyproject() -> dict[str, str]:
    """pyproject 的依赖口径：**必装依赖 + 全部 extras**（自引用除外）。

    为什么不是"dependencies + dev"：核心层只需要 pydantic 与 PyYAML，HTTP 栈与编排框架住在
    `api` / `orchestration` 两个 extra 里（`dev` 通过自引用把它们一起装上）。
    只读 dev 的话，这两个 extra 里的声明对检查器就等于不存在，`requirements.in` 与 pyproject
    的对照会立刻失真——而这份对照正是"锁文件与声明不许漂移"的闸门。
    """

    document = tomllib.loads(_read_text("pyproject.toml"))
    project = document.get("project", {})
    own_name = str(project.get("name", "")).lower()
    items = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        items.extend(group)
    result: dict[str, str] = {}
    for item in items:
        text = str(item).strip()
        # 自引用（`本包[api,orchestration]`）不是"另一个依赖"，跳过：它只是"把这两组装上"。
        if text.lower().startswith(own_name):
            continue
        match = _REQ_RE.match(text)
        if match is None:
            raise EnvironmentProblem("pyproject.toml 里有无法解析的依赖: %r" % item)
        result[match.group(1).lower()] = (match.group(2) or "").strip()
    return result


def check_lock() -> list[str]:
    issues: list[str] = []
    declared = read_requirements_in()
    locked, unparsed = read_requirements_lock()
    project = read_pyproject()

    # 先报解析不了的行：否则它们会以"没有固定 X"这种错误理由出现（或者根本不出现）。
    for item in unparsed:
        issues.append("requirements.lock 里有无法解析的固定行（解析不了就不能当成没锁定）：%s" % item)

    for name in sorted(set(declared) - set(project)):
        issues.append("requirements.in 声明了 %s，pyproject.toml 里没有" % name)
    for name in sorted(set(project) - set(declared)):
        issues.append("pyproject.toml 声明了 %s，requirements.in 里没有" % name)
    for name in sorted(set(declared) & set(project)):
        # 比的是**区间语义**，不是字符串：`>=2.9,<3` 与 `>=2.9, <3` 描述同一个区间，
        # 旧实现逐字符比较，于是任何一处空白调整都会把 CI 判红（并诱导人去"改回原样"）。
        if _normalize_specifier(declared[name]) != _normalize_specifier(project[name]):
            issues.append(
                "%s 的版本区间不一致：requirements.in=%r，pyproject.toml=%r"
                % (name, declared[name], project[name])
            )

    for name, specifier in sorted(declared.items()):
        pinned = locked.get(name)
        if pinned is None:
            issues.append("requirements.lock 没有固定 %s（直接依赖必须全部锁定）" % name)
            continue
        try:
            ok = satisfies(pinned, specifier)
        except ValueError as error:
            # 比不了 ≠ 满足：认不出的版本形态记成漂移，绝不静默当成"通过"。
            issues.append(
                "%s 的版本无法比较（%s）：拒绝把「比不了」当成「满足」" % (name, error)
            )
            continue
        if not ok:
            issues.append(
                "%s 锁定为 %s，不满足声明的 %r：锁文件与依赖声明已经漂移，"
                "请在验证过的环境重新生成 requirements.lock" % (name, pinned, specifier)
            )
    for name in sorted(set(locked) - set(declared)):
        issues.append("requirements.lock 固定了未声明的直接依赖 %s" % name)
    return issues


def mentioned_test_dirs(readme: str) -> list[str]:
    """README 里提到的 tests/<目录名>：去重、稳定排序。

    纯函数，便于用例直接喂文本（`check_docs_and_config` 读的是真 README）。
    """

    return sorted(set(README_TEST_DIR_RE.findall(readme)))


def check_docs_and_config() -> list[str]:
    issues: list[str] = []
    workflows = sorted(path.name for path in (ROOT / WORKFLOW_DIR).glob("*.y*ml"))
    if not workflows:
        issues.append(".github/workflows 下没有任何 workflow")

    referenced: dict[str, list[str]] = {}
    for name in DOCS_WITH_CONFIG_CLAIMS:
        text = _read_text(name)
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
        text = _read_text(relative)
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

    pytest_ini = _read_text("pytest.ini")
    testpaths = re.search(r"^testpaths\s*=\s*(.+)$", pytest_ini, re.MULTILINE)
    if testpaths:
        for item in testpaths.group(1).split():
            if not (ROOT / item).is_dir():
                issues.append("pytest.ini 的 testpaths 指向不存在的目录 %s" % item)
    readme = _read_text("README.md")
    for name in mentioned_test_dirs(readme):
        if not (ROOT / "tests" / name).is_dir():
            issues.append("README.md 提到的 tests/%s 不存在" % name)
    return issues


def check_notebook_form() -> list[str]:
    """由生成器产出的 notebook 必须是规范形态（手写的不在检查范围）。

    在 Jupyter / VS Code 里"运行并保存"会把执行输出与 execution_count 写回 .ipynb，
    而生成器写出来的形态里这两样永远是空的，于是 CI 的"手册同步"步骤会逐字节比较失败。
    这里只做形态判断、不跑生成器（那个要几分钟），让问题在本地一秒暴露。
    """

    # 由生成器产出的 notebook 目前只有一类：docs/project/architecture/tech-detail 各章的讲解。
    # （按阶段的学习手册已随文档管理下线，连同它的生成器一起删除——少了一类就删一行，
    # 别留下一段指向不存在目录的声明：那是"检查器还在、对象没了"的静默失效形态。）
    # 新增一类时加一行即可——但**必须**加：目录改层而检查器没跟着改，会让本检查"命中 0 个、
    # 判定一致"，静默失效正是本仓库最忌讳的失败形态（所以下面显式报错，不放过空集合）。
    groups = (
        (
            "docs/project/architecture/tech-detail 各章节目录下的 *.ipynb",
            "*/*.ipynb",
            ROOT / "docs" / "project" / "architecture" / "tech-detail",
            "python docs/project/architecture/tech-detail/build_notebooks.py",
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
    readme = _read_text("tools/README.md")
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
    # 环境错误统一在这里翻成退出码 2：与"发现漂移"（1）分开，CI 才读得出"检查跑了没有"。
    try:
        sections = (
            ("依赖锁", check_lock()),
            ("文档与配置", check_docs_and_config()),
            ("手册形态", check_notebook_form()),
            ("工具清单", check_tool_inventory()),
        )
    except EnvironmentProblem as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 2
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
