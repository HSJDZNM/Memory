"""bank-docs-config 隐藏验收 runner：T01-T26 + EN1-EN7 + I1-I7（40 条）。

用法::

    BANK_TASK_TREE=<被评树> python hidden/runner.py

契约（bank/README.md 4.3 与 hidden/PLAN.md 0）：

- 被评树只从环境变量 BANK_TASK_TREE 读入，**绝不写**：pytest / 校验脚本 / 模块导入都在树的副本里跑
  （临时目录，用完即删）；
- stdout 唯一载荷（UTF-8）::

      {"schema_version": "1.0", "tree": "<相对标签>",
       "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
       "summary": {"passed": 40, "total": 40}}

  载荷不含时戳 / run id / 绝对路径；同一 cwd + 同一棵树两次运行逐字节相同；
- 退出码：全过 0 / 有失败 1 / 跑不成 2（缺 BANK_TASK_TREE、树不存在、用例集合不完整、
  树复制失败、PyYAML 不可用）；
- 每条用例独立 try/except：一条异常只让该条 fail，detail = 异常类型 + 脱敏短消息；
- 反向用例（T04-T18、T21、T25、T26、EN4-EN7、I5）断言的是「期望失败 / 期望拒绝」。
"""
from __future__ import annotations

import ast
import atexit
import contextlib
import copy
import hashlib
import inspect
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 跑不成，不是 0 分
    yaml = None

sys.dont_write_bytecode = True

SCHEMA_VERSION = "1.0"
TIMEOUT_SECONDS = 60
COLLECTED_MIN = 10

CASE_IDS = (
    ["T%02d" % index for index in range(1, 27)]
    + ["EN%d" % index for index in range(1, 8)]
    + ["I%d" % index for index in range(1, 8)]
)

# 13 个基线文件（逐字节起点）。来源：包内 baseline/ 的 13 个文件实算 sha256
# （组合摘要 e259e2440044781413cb1d04bd0a4c4926898be7372126a66f79b5316d2eb8de）。
BASELINE_SHA256 = {
    "AGENTS.md": "ef20cdca0d6c43dbb5038449c90a972d44837e4b9ddc17e074f994d5eed669a3",
    "README.md": "5b4313609e4a28b61b43cd7b58ead2b99866284e532c68b79983cd3698213a5a",
    "config/app.yaml": "47d10319f7497c6a7c6aeb245a1bac3a81c326ec5444aff2cdafbf26c98377e8",
    "conftest.py": "edd7cea37c657fb322cdee3038ca9aed35f40c7657a0faacb6640d6de9b050e7",
    "docs/config.md": "1cd1f0cc3fcec89acd7ff4233d89333f95e1b836d06025f4dc2532fe9b939976",
    "pytest.ini": "fd1c0f9fadf99a0af117f9f17fd7276f06d577e80fd530652978a1ff54aa71cc",
    "src/shop/__init__.py": "d7eef7b6e4db6622675782550c664ef2ef3c2ff9e8de8845cc0e9f4af4b44ad1",
    "src/shop/order_controller.py": (
        "e017c95714e14973bde434902dac0aa33025a73c5b78e4a0a23318f0b3755a6c"
    ),
    "src/shop/order_repository.py": (
        "4d4b685f7ce3bbd729a9004b5f20ce0e77701d1be3d514788272398b4b90f054"
    ),
    "src/shop/order_service.py": (
        "080664ff694aad5cb1f50842ae715d72698e40031b97512ddf7328110700fcbe"
    ),
    "tests/test_order_controller.py": (
        "4ac351e0ce611989044e74f2909c856de1e199e921602ab4fe6a874cecc7d069"
    ),
    "tests/test_order_repository.py": (
        "61e6c0d31b70c3d93b4848e7352816ce2a8ff71a07e509dd9afd0376f977f20c"
    ),
    "tests/test_order_service.py": (
        "91fa0e15a1bfaf74827bd11e77dbbef0490841205cd67ab6e4b00056c57aaf5f"
    ),
}

# 基线里允许改写的 3 个既有文件（allowed-writes 与 baseline 的交集）。
MODIFIABLE_BASELINE = frozenset({"README.md", "config/app.yaml", "docs/config.md"})

# 冻结文件 = 基线 13 - 可改写 3 = 10（T26 逐字节校验这 10 个）。
FROZEN_BASELINE = {
    path: digest for path, digest in BASELINE_SHA256.items() if path not in MODIFIABLE_BASELINE
}

# 任务新建的 5 个文件（13 基线 ∪ 5 新建 = 18 文件；T25 用）。
NEW_PATHS = frozenset(
    {
        "docs/config-migration.md",
        "src/shop/config.py",
        "tests/test_check_config.py",
        "tests/test_config.py",
        "tools/check_config.py",
    }
)

# 允许写 8 条 = 基线可改写 3 + 新建 5。
ALLOWED_WRITES = frozenset(MODIFIABLE_BASELINE) | NEW_PATHS

EXPECTED_PATHS = frozenset(BASELINE_SHA256) | NEW_PATHS

# 基线 README 的归一化摘要（行尾空白去掉、连续空行压成一个、去首尾空行）。
# T24 用它判「除了新增的 ## 配置 一节，其它小节逐字保留」，不把基线文件读进运行时。
BASELINE_README_NORMALIZED_SHA256 = (
    "6d0dd52a0e75f2a6c49d174bbabc17a27dd14e855d650126a01992ee2ae3741c"
)

V2_CONFIG = {
    "app_name": "demo-shop",
    "retry_policy": {"max_attempts": 3, "backoff_ms": 100, "jitter": True},
    "feature_flags": ["checkout", "search"],
}

V1_CONFIG = {"app_name": "demo-shop", "retry": 3, "feature_flags": ["checkout", "search"]}

V2_TOP_KEYS = ("app_name", "retry_policy", "feature_flags")
V2_RETRY_KEYS = ("max_attempts", "backoff_ms", "jitter")

DOC_V2_HEADING = "## 配置键（v2）"
DOC_V1_HEADING = "## 配置键（v1）"
DOC_TABLE_HEADER = ["键", "类型", "默认值", "迁移注"]
DOC_TABLE_ROWS = [
    ("app_name", "str"),
    ("retry_policy.max_attempts", "int (>= 1)"),
    ("retry_policy.backoff_ms", "int (>= 0)"),
    ("retry_policy.jitter", "bool"),
    ("feature_flags", "list[str]"),
]
DOC_DEFAULT_CELL = "无默认（必填）"

MIGRATION_HEADINGS = ["## 键映射", "## 回滚", "## 校验"]
MIGRATION_COMMAND = "python tools/check_config.py --config config/app.yaml"

README_HEADINGS = ["## 结构", "## 跑测试", "## 配置", "## 这份项目为什么长这样"]

SKIP_ATTRS = frozenset({"skip", "skipif", "xfail", "importorskip"})

IGNORED_SEGMENTS = frozenset({".policy", "__pycache__", ".pytest_cache", ".ruff_cache"})
CACHE_PREFIXES = ("pytest-cache-files-",)

SCRIPT_PATH = "tools/check_config.py"
LOADER_PATH = "src/shop/config.py"
NEW_TEST_SPECS = (("tests/test_config.py", 5), ("tests/test_check_config.py", 2))

TREE = None
_SHARED_HOLDER = None
_SHARED_COPY = None
_FIXTURE_HOLDER = None
_SUBPROCESS_TMP = None
_SCRUB_ROOTS = []


# ---------------------------------------------------------------------------
# 树标签 / 临时目录 / 副本 / 子进程
# ---------------------------------------------------------------------------
def _tree_label(raw):
    """载荷里的树标签：永远不是绝对路径。"""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            relative = os.path.relpath(candidate, Path.cwd())
        except ValueError:
            return candidate.name
        label = Path(relative).as_posix()
        if label == ".." or label.startswith("../"):
            return candidate.name
        return label
    label = Path(os.path.normpath(raw)).as_posix()
    if label == ".." or label.startswith("../"):
        return candidate.name
    return label


def _is_inside(path, root):
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _temp_root():
    """临时副本的父目录：优先 <cwd>/.tmp（工作区可写），退到树旁与系统 temp。

    任何候选都不得落在被评树内部（只读被评树）；每个候选都要真写一次才算可用：
    有的沙箱允许 mkdir 但拒绝写入，只探测 mkdir 会把「写不了」当成可用。
    """
    override = os.environ.get("BANK_TASK_TMPDIR")
    candidates = []
    if override:
        candidates.append(Path(override))
    else:
        candidates.append(Path.cwd() / ".tmp")
        if TREE is not None:
            candidates.append(Path(TREE).parent / ".tmp")
        candidates.append(Path(tempfile.gettempdir()))
    for candidate in candidates:
        # 进程唯一的探测目录：同一 .tmp 下可能有别的 runner（别的题 / 别的会话）在跑，
        # 共用 subprocess-tmp 会让 pytest 的 basetemp 轮转互相删除（实测过一次假红）。
        probe = candidate / ("bank-hidden-runner-%d" % os.getpid())
        if TREE is not None and (_is_inside(probe, TREE) or _is_inside(candidate, TREE)):
            continue
        try:
            probe.mkdir(parents=True, exist_ok=True)
            handle = probe / ".write-probe"
            handle.write_text("ok", encoding="utf-8")
            handle.unlink()
            return probe
        except OSError:
            continue
    raise RuntimeError("no writable temporary directory outside the evaluated tree")


def _ignore_artifacts(_directory, names):
    """副本里不带走缓存、隐藏目录与 pyc。"""
    ignored = set()
    for name in names:
        if name.startswith(".") or name == "__pycache__" or name.endswith(".pyc"):
            ignored.add(name)
    return ignored


def _holder(prefix):
    """临时目录：不用 mkdtemp（它建 0700 目录，受限宿主会拒绝随后写入）。"""
    root = _temp_root()
    for index in itertools.count(1):
        candidate = root / ("%s-%d-%d" % (prefix, os.getpid(), index))
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        atexit.register(shutil.rmtree, candidate, ignore_errors=True)
        _SCRUB_ROOTS.append(str(candidate))
        return candidate
    raise RuntimeError("cannot create a temporary holder")


def _new_copy(prefix):
    """被评树的一个新副本；退出时整棵删掉。"""
    assert TREE is not None
    target = _holder(prefix) / "tree"
    shutil.copytree(TREE, target, ignore=_ignore_artifacts)
    return target


def _shared_copy():
    """所有「只读执行」共用的一份副本（pytest / 导入 / 脚本第一次）。"""
    global _SHARED_HOLDER, _SHARED_COPY
    if _SHARED_COPY is None or not _SHARED_COPY.is_dir():
        assert TREE is not None
        _SHARED_HOLDER = _holder("shared")
        target = _SHARED_HOLDER / "tree"
        shutil.copytree(TREE, target, ignore=_ignore_artifacts)
        _SHARED_COPY = target
    return _SHARED_COPY


def _fixtures():
    """用例自己构造的 YAML 夹具目录（在被评树之外）。"""
    global _FIXTURE_HOLDER
    if _FIXTURE_HOLDER is None or not _FIXTURE_HOLDER.is_dir():
        _FIXTURE_HOLDER = _holder("fixtures") / "data"
        _FIXTURE_HOLDER.mkdir()
    return _FIXTURE_HOLDER


def _fixture_text(name, text):
    path = _fixtures() / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _write_yaml(name, payload):
    assert yaml is not None
    return _fixture_text(name, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))


def _subprocess_tmp():
    """子进程的临时目录：继承来的 TEMP 可能被宿主的文件沙箱拒绝，这里换成一个可写的。"""
    global _SUBPROCESS_TMP
    if _SUBPROCESS_TMP is None or not _SUBPROCESS_TMP.is_dir():
        root = _holder("subprocess") / "tmp"
        root.mkdir()
        _SUBPROCESS_TMP = root
    return _SUBPROCESS_TMP


def _base_env():
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("PYTHONPATH", None)
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTHONSTARTUP", None)
    scratch = str(_subprocess_tmp())
    env["TMP"] = scratch
    env["TEMP"] = scratch
    env["TMPDIR"] = scratch
    return env


def _run(args, cwd, env=None):
    """在副本里跑一条命令；解释器 = 运行 runner 的 sys.executable。"""
    return subprocess.run(
        args,
        cwd=str(cwd),
        env=dict(env) if env is not None else _base_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


_ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]*")
_DURATION = re.compile(r"\d+\.\d+s")


def _scrub(text):
    """脱敏：删掉被评树根、临时目录根、其余盘符绝对路径与耗时。"""
    cleaned = str(text)
    roots = []
    if TREE is not None:
        roots.append(str(TREE))
    roots.extend(_SCRUB_ROOTS)
    if _SUBPROCESS_TMP is not None:
        roots.append(str(_SUBPROCESS_TMP))
    for root in sorted(set(roots), key=len, reverse=True):
        for variant in (root, root.replace("\\", "/"), root.replace("/", "\\")):
            cleaned = cleaned.replace(variant, "<tmp>")
    cleaned = _ABSOLUTE_PATH.sub("<path>", cleaned)
    cleaned = _DURATION.sub("<t>s", cleaned)
    return cleaned


def _tail(text, limit=240):
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return _scrub(lines[-1])[:limit] if lines else ""


def _non_blank_lines(text):
    return [line.strip() for line in str(text).splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 树内读取 / 模块导入 / AST
# ---------------------------------------------------------------------------
def _read_text(rel):
    assert TREE is not None
    return (TREE / rel).read_text(encoding="utf-8")


def _sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path):
    return _sha256_bytes(path.read_bytes())


def _sha256_text(text):
    return _sha256_bytes(text.encode("utf-8"))


def _tree_module(name):
    """从副本导入被测树的模块（只 import，不执行被测树里的动作）。"""
    root = _shared_copy()
    for extra in (str(root), str(root / "src")):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    import importlib

    return importlib.import_module(name)


def _parse_tree_file(rel):
    return ast.parse(_read_text(rel), filename=rel)


def _tree_files():
    assert TREE is not None
    found = []
    for path in TREE.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(TREE).parts
        if any(_ignored_segment(part) for part in parts):
            continue
        if path.name.endswith(".pyc"):
            continue
        found.append("/".join(parts))
    return sorted(found)


def _ignored_segment(part):
    if part.startswith("."):
        return True
    if part in IGNORED_SEGMENTS or part == "__pycache__":
        return True
    return any(part.startswith(prefix) for prefix in CACHE_PREFIXES)


def _dotted(node):
    """把 a.b.c 形态的表达式还原成点号字符串；还原不出来返回空串。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return prefix + "." + node.attr if prefix else node.attr
    return ""


def _call_names(module):
    return [_dotted(node.func) for node in ast.walk(module) if isinstance(node, ast.Call)]


def _import_names(module):
    names = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if module_name:
                names.add(module_name)
            for alias in node.names:
                names.add(module_name + "." + alias.name if module_name else alias.name)
    return names


def _string_constants(module):
    return {
        node.value
        for node in ast.walk(module)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _find_function(module, name):
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _skip_markers(module):
    hits = []
    for node in ast.walk(module):
        if isinstance(node, ast.Attribute) and node.attr in SKIP_ATTRS:
            hits.append(ast.unparse(node)[:60])
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"skip", "xfail"}
        ):
            hits.append(ast.unparse(node.func)[:60])
    return sorted(set(hits))


def _assert_count(module):
    return sum(1 for node in ast.walk(module) if isinstance(node, ast.Assert))


def _test_function_count(module):
    return sum(
        1
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _has_main_guard(module):
    for node in ast.walk(module):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.Compare) and len(test.comparators) == 1):
            continue
        left, right = test.left, test.comparators[0]
        name_left = isinstance(left, ast.Name) and left.id == "__name__"
        name_right = isinstance(right, ast.Name) and right.id == "__name__"
        main_left = isinstance(left, ast.Constant) and left.value == "__main__"
        main_right = isinstance(right, ast.Constant) and right.value == "__main__"
        if not ((name_left and main_right) or (main_left and name_right)):
            continue
        if _exits_with_main(node.body):
            return True
    return False


def _exits_with_main(statements):
    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                if _dotted(node.exc.func) in {"SystemExit", "builtins.SystemExit"}:
                    if any(_calls_main(arg) for arg in node.exc.args):
                        return True
            if isinstance(node, ast.Call) and _dotted(node.func) in {"sys.exit", "exit"}:
                if any(_calls_main(arg) for arg in node.args):
                    return True
    return False


def _calls_main(node):
    return isinstance(node, ast.Call) and _dotted(node.func) == "main"


# ---------------------------------------------------------------------------
# Markdown / 表格 / 断言小工具
# ---------------------------------------------------------------------------
def _normalize_markdown(text):
    """行尾空白去掉、连续空行压成一个、去首尾空行（CRLF 归一成 LF）。"""
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.rstrip()
        if stripped == "" and (not lines or lines[-1] == ""):
            continue
        lines.append(stripped)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _markdown_sections(text):
    """二级标题分段：[{heading, body, index}]（### 三级标题算正文）。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections = []
    current = None
    for index, line in enumerate(lines):
        if line.strip().startswith("## "):
            current = {"heading": line.strip(), "body": [], "index": index}
            sections.append(current)
        elif current is not None:
            current["body"].append(line)
    return sections


def _section_body_text(section):
    return "\n".join(section["body"])


def _has_body(section):
    for line in section["body"]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return True
    return False


def _normalize_cell(cell):
    return re.sub(r"\s+", " ", cell.replace("\x60", "")).strip()


def _table_cells(line):
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [_normalize_cell(cell) for cell in inner.split("|")]


def _is_separator_row(cells):
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _expect(condition, message):
    if not condition:
        raise AssertionError(message)


def _check_all(checks):
    failures = [label for label, ok in checks if not ok]
    _expect(not failures, "failed: " + ", ".join(failures))


def _expect_value_error(action, label):
    """action() 必须抛 ValueError：不抛或抛别的异常都算失败；返回消息文本。"""
    try:
        action()
    except ValueError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - 反向用例：别的异常形态也算失败
        raise AssertionError(
            label + ": raised " + type(exc).__name__ + " instead of ValueError"
        ) from exc
    raise AssertionError(label + ": was accepted")


def _assert_no_absolute_path(message, path):
    forms = [str(path), path.as_posix(), str(path.parent), path.parent.as_posix()]
    for form in forms:
        if form and form in message:
            raise AssertionError("error message contains an absolute path")
    if re.search(r"[A-Za-z]:[\\/]", message):
        raise AssertionError("error message contains a drive-letter path")


def _v2(**top):
    data = copy.deepcopy(V2_CONFIG)
    data.update(top)
    return data


def _v2_retry(**sub):
    data = copy.deepcopy(V2_CONFIG)
    data["retry_policy"].update(sub)
    return data


def _v2_drop_top(key):
    data = copy.deepcopy(V2_CONFIG)
    data.pop(key, None)
    return data


def _v2_drop_retry(key):
    data = copy.deepcopy(V2_CONFIG)
    data["retry_policy"].pop(key, None)
    return data


def _loader():
    module = _tree_module("shop.config")
    load = getattr(module, "load_config", None)
    _expect(callable(load), "shop.config has no callable load_config")
    return load


def _script_module():
    return _tree_module("tools.check_config")


def _pytest_base_args():
    return [sys.executable, "-m", "pytest"]


# ---------------------------------------------------------------------------
# 1.1 加载器语义（T01-T18）
# ---------------------------------------------------------------------------
def _t01():
    load = _loader()
    data = load(_write_yaml("v2-valid.yaml", _v2()))
    _expect(isinstance(data, dict), "returned " + type(data).__name__)
    _expect(set(data) == set(V2_TOP_KEYS), "top keys = " + repr(sorted(data)))
    _expect(type(data["app_name"]) is str, "app_name is not str")
    _expect(data["app_name"] == "demo-shop", "app_name = " + repr(data["app_name"]))
    policy = data["retry_policy"]
    _expect(isinstance(policy, dict), "retry_policy is " + type(policy).__name__)
    _expect(set(policy) == set(V2_RETRY_KEYS), "retry keys = " + repr(sorted(policy)))
    _expect(type(policy["max_attempts"]) is int, "max_attempts is not int")
    _expect(policy["max_attempts"] == 3, "max_attempts = " + repr(policy["max_attempts"]))
    _expect(type(policy["backoff_ms"]) is int, "backoff_ms is not int")
    _expect(policy["backoff_ms"] == 100, "backoff_ms = " + repr(policy["backoff_ms"]))
    _expect(type(policy["jitter"]) is bool, "jitter is not bool")
    _expect(policy["jitter"] is True, "jitter = " + repr(policy["jitter"]))
    flags = data["feature_flags"]
    _expect(isinstance(flags, list), "feature_flags is " + type(flags).__name__)
    _expect(flags == ["checkout", "search"], "feature_flags = " + repr(flags))
    _expect(all(type(item) is str for item in flags), "feature_flags holds non-str items")
    return True, "v2 keys / values / types exact"


def _t02():
    load = _loader()
    text = (
        "# 应用配置（v2）。\n"
        "app_name: demo-shop  # 行内注释也要能读\n"
        "retry_policy:\n"
        "  max_attempts: 1\n"
        "  backoff_ms: 0\n"
        "  jitter: false\n"
        "feature_flags: []\n"
    )
    data = load(_fixture_text("v2-boundary.yaml", text))
    policy = data["retry_policy"]
    _check_all(
        [
            ("max_attempts=1", policy.get("max_attempts") == 1),
            ("backoff_ms=0", policy.get("backoff_ms") == 0),
            ("jitter=false", policy.get("jitter") is False),
            ("feature_flags=[]", data.get("feature_flags") == []),
        ]
    )
    return True, "boundary values and comments accepted"


def _t03():
    load = _loader()
    path = _write_yaml("v2-copy.yaml", _v2())
    first = load(path)
    second = load(path)
    _expect(first == second, "two loads differ")
    _expect(first is not second, "two loads return the same top-level dict")
    _expect(
        first["retry_policy"] is not second["retry_policy"],
        "two loads share the retry_policy dict",
    )
    first["app_name"] = "mutated"
    first["retry_policy"]["max_attempts"] = 99
    third = load(path)
    _expect(third == second, "mutating a result leaked into the next load")
    return True, "each call returns fresh dicts"


def _t04():
    load = _loader()
    path = _write_yaml("v1-retry.yaml", V1_CONFIG)
    message = _expect_value_error(lambda: load(path), "v1 retry")
    _expect("retry_policy" in message, "message lacks the retry_policy hint")
    return True, "v1 retry rejected with migration hint"


def _t05():
    load = _loader()
    path = _write_yaml("v1-and-v2.yaml", _v2(retry=3))
    _expect_value_error(lambda: load(path), "retry next to retry_policy")
    return True, "retry rejected even when retry_policy exists"


def _t06():
    load = _loader()
    path = _write_yaml("unknown-top.yaml", _v2(timeout=5))
    _expect_value_error(lambda: load(path), "unknown top-level key")
    return True, "unknown top-level key rejected"


def _t07():
    load = _loader()
    for label, payload in (
        ("missing feature_flags", _v2_drop_top("feature_flags")),
        ("missing app_name", _v2_drop_top("app_name")),
    ):
        path = _write_yaml("missing-top-" + label.split()[1] + ".yaml", payload)
        _expect_value_error(lambda p=path: load(p), label)
    return True, "missing top-level keys rejected"


def _t08():
    load = _loader()
    path = _write_yaml("unknown-retry.yaml", _v2_retry(max_retries=3))
    _expect_value_error(lambda: load(path), "unknown retry_policy key")
    return True, "unknown retry_policy key rejected"


def _t09():
    load = _loader()
    for key in ("backoff_ms", "jitter"):
        path = _write_yaml("missing-retry-" + key + ".yaml", _v2_drop_retry(key))
        _expect_value_error(lambda p=path: load(p), "missing retry_policy key " + key)
    return True, "missing retry_policy keys rejected"


def _t10():
    load = _loader()
    for label, payload in (
        ("app_name int", _v2(app_name=3)),
        ("app_name empty", _v2(app_name="")),
    ):
        path = _write_yaml("app-name-" + label.split()[1] + ".yaml", payload)
        _expect_value_error(lambda p=path: load(p), label)
    return True, "app_name type and emptiness rejected"


def _t11():
    load = _loader()
    for label, value in (
        ("bool", True),
        ("zero", 0),
        ("negative", -1),
        ("str", "3"),
    ):
        path = _write_yaml("max-attempts-" + label + ".yaml", _v2_retry(max_attempts=value))
        _expect_value_error(lambda p=path: load(p), "max_attempts " + label)
    return True, "max_attempts bool / 0 / -1 / str rejected"


def _t12():
    load = _loader()
    payloads = (
        ("backoff_ms-1", _v2_retry(backoff_ms=-1)),
        ("backoff_ms-str", _v2_retry(backoff_ms="100")),
        ("backoff_ms-bool", _v2_retry(backoff_ms=True)),
        ("jitter-int", _v2_retry(jitter=1)),
        ("jitter-str", _v2_retry(jitter="true")),
        ("jitter-zero", _v2_retry(jitter=0)),
    )
    for label, payload in payloads:
        path = _write_yaml("bad-" + label + ".yaml", payload)
        _expect_value_error(lambda p=path: load(p), label)
    return True, "backoff_ms / jitter types and ranges rejected"


def _t13():
    load = _loader()
    payloads = (
        ("flags-str", _v2(feature_flags="checkout")),
        ("flags-int-item", _v2(feature_flags=["checkout", 1])),
        ("flags-empty-item", _v2(feature_flags=[""])),
        ("flags-null", _v2(feature_flags=None)),
    )
    for label, payload in payloads:
        path = _write_yaml("bad-" + label + ".yaml", payload)
        _expect_value_error(lambda p=path: load(p), label)
    return True, "feature_flags shape rejected"


def _t14():
    load = _loader()
    fixtures = (
        ("top-list", _write_yaml("bad-top-list.yaml", ["a", "b"])),
        ("top-scalar", _write_yaml("bad-top-scalar.yaml", "just-a-string")),
        ("empty-file", _fixture_text("bad-empty.yaml", "")),
    )
    for label, path in fixtures:
        _expect_value_error(lambda p=path: load(p), label)
    return True, "non-mapping top level rejected"


def _t15():
    load = _loader()
    path = _fixture_text("bad-syntax.yaml", "app_name: [unclosed\nretry_policy: {\n")
    _expect_value_error(lambda: load(path), "yaml syntax error")
    return True, "yaml syntax error becomes ValueError"


def _t16():
    load = _loader()
    missing = _fixtures() / "definitely-missing.yaml"
    _expect_value_error(lambda: load(missing), "missing file")
    _expect_value_error(lambda: load(_fixtures()), "directory as path")
    return True, "missing file and directory both rejected"


def _t17():
    load = _loader()
    fixtures = (
        ("v1 retry", _write_yaml("t17-v1.yaml", V1_CONFIG)),
        ("unknown key", _write_yaml("t17-unknown.yaml", _v2(timeout=5))),
        ("missing key", _write_yaml("t17-missing-key.yaml", _v2_drop_top("feature_flags"))),
        ("app_name", _write_yaml("t17-app-name.yaml", _v2(app_name=""))),
        ("max_attempts", _write_yaml("t17-max-attempts.yaml", _v2_retry(max_attempts=True))),
        ("feature_flags", _write_yaml("t17-flags.yaml", _v2(feature_flags="checkout"))),
        ("missing file", _fixtures() / "t17-missing.yaml"),
    )
    for label, path in fixtures:
        message = _expect_value_error(lambda p=path: load(p), label)
        _assert_no_absolute_path(message, path)
    return True, "7 error messages carry no absolute path"


def _t18():
    module = _parse_tree_file(LOADER_PATH)
    calls = _call_names(module)
    safe_calls = [name for name in calls if name in {"yaml.safe_load", "safe_load"}]
    _expect(bool(safe_calls), "no yaml.safe_load call in the loader")
    unsafe_calls = [
        name for name in calls if name in {"yaml.load", "yaml.full_load", "yaml.unsafe_load"}
    ]
    _expect(not unsafe_calls, "unsafe loader call: " + ", ".join(sorted(set(unsafe_calls))))
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            _expect(keyword.arg != "Loader", "Loader= keyword used in the loader")
    dynamic = [
        name
        for name in calls
        if name in {"eval", "exec", "compile", "__import__", "importlib.import_module"}
    ]
    _expect(not dynamic, "dynamic execution call: " + ", ".join(sorted(set(dynamic))))
    return True, "yaml.safe_load only, no unsafe loader, no dynamic execution"


def _t19():
    assert yaml is not None
    tree_copy = _shared_copy()
    config_path = tree_copy / "config/app.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _expect(isinstance(data, dict), "config/app.yaml is not a mapping")
    _expect(set(data) == set(V2_TOP_KEYS), "top keys = " + repr(sorted(data)))
    _expect("retry" not in data, "top-level retry is still present")
    _expect(data["app_name"] == "demo-shop", "app_name = " + repr(data["app_name"]))
    policy = data["retry_policy"]
    _expect(isinstance(policy, dict), "retry_policy is " + type(policy).__name__)
    _expect(set(policy) == set(V2_RETRY_KEYS), "retry keys = " + repr(sorted(policy)))
    _expect(
        type(policy["max_attempts"]) is int and policy["max_attempts"] == 3,
        "max_attempts = " + repr(policy.get("max_attempts")),
    )
    _expect(
        type(policy["backoff_ms"]) is int and policy["backoff_ms"] == 100,
        "backoff_ms = " + repr(policy.get("backoff_ms")),
    )
    _expect(
        type(policy["jitter"]) is bool and policy["jitter"] is True,
        "jitter = " + repr(policy.get("jitter")),
    )
    _expect(
        data["feature_flags"] == ["checkout", "search"],
        "feature_flags = " + repr(data["feature_flags"]),
    )
    loaded = _loader()(config_path)
    _expect(loaded == data, "load_config disagrees with the yaml on disk")
    _expect(set(loaded) == set(V2_TOP_KEYS), "load_config top keys differ")
    return True, "config/app.yaml migrated and readable"


# ---------------------------------------------------------------------------
# 1.2 文档与 README（T20-T24）
# ---------------------------------------------------------------------------
def _t20():
    text = _read_text("docs/config.md")
    section = None
    for item in _markdown_sections(text):
        if item["heading"] == DOC_V2_HEADING:
            section = item
            break
    _expect(section is not None, "missing heading " + DOC_V2_HEADING)
    rows = [line.strip() for line in section["body"] if line.strip().startswith("|")]
    _expect(len(rows) >= 2, "no markdown table under the v2 heading")
    cells = [_table_cells(row) for row in rows]
    _expect(cells[0] == DOC_TABLE_HEADER, "header = " + " | ".join(cells[0]))
    data_rows = [row for row in cells[1:] if not _is_separator_row(row)]
    _expect(len(data_rows) == len(DOC_TABLE_ROWS), "data rows = " + str(len(data_rows)))
    for index, (key, type_name) in enumerate(DOC_TABLE_ROWS):
        row = data_rows[index]
        _expect(len(row) >= 4, "row " + str(index + 1) + " has " + str(len(row)) + " cells")
        _expect(row[0] == key, "key cell " + str(index + 1) + " = " + row[0])
        _expect(row[1] == type_name, "type cell for " + key + " = " + row[1])
        _expect(row[2] == DOC_DEFAULT_CELL, "default cell for " + key + " = " + row[2])
        _expect(bool(row[3]), "migration note for " + key + " is empty")
    _expect("retry" in data_rows[1][3], "migration note for max_attempts lacks retry")
    return True, "5-row v2 table exact"


def _t21():
    text = _read_text("docs/config.md")
    headings = [item["heading"] for item in _markdown_sections(text)]
    _expect(DOC_V1_HEADING not in headings, "v1 heading is still present")
    for section in _markdown_sections(text):
        for line in section["body"]:
            if not line.strip().startswith("|"):
                continue
            cells = _table_cells(line)
            if _is_separator_row(cells):
                continue
            _expect(cells[0] != "retry", "a table row still documents the v1 retry key")
    return True, "v1 table replaced"


def _t22():
    text = _read_text("docs/config-migration.md")
    sections = _markdown_sections(text)
    headings = [item["heading"] for item in sections]
    for heading in MIGRATION_HEADINGS:
        _expect(headings.count(heading) == 1, heading + " count = " + str(headings.count(heading)))
    positions = [headings.index(heading) for heading in MIGRATION_HEADINGS]
    _expect(positions == sorted(positions), "migration headings out of order")
    by_heading = {item["heading"]: item for item in sections}
    for heading in MIGRATION_HEADINGS:
        _expect(_has_body(by_heading[heading]), "section " + heading + " has no body")
    mapping = _section_body_text(by_heading["## 键映射"])
    for literal in (
        "retry",
        "retry_policy.max_attempts",
        "retry_policy.backoff_ms",
        "retry_policy.jitter",
    ):
        _expect(literal in mapping, "mapping section lacks " + literal)
    rollback = _section_body_text(by_heading["## 回滚"])
    for literal in ("retry_policy", "retry", "config/app.yaml"):
        _expect(literal in rollback, "rollback section lacks " + literal)
    verify = _section_body_text(by_heading["## 校验"])
    _expect(MIGRATION_COMMAND in verify, "verify section lacks the full command")
    return True, "3 migration sections complete"


def _t23():
    text = _read_text("README.md")
    sections = _markdown_sections(text)
    headings = [item["heading"] for item in sections]
    for heading in README_HEADINGS:
        _expect(headings.count(heading) == 1, heading + " count = " + str(headings.count(heading)))
    positions = [headings.index(heading) for heading in README_HEADINGS]
    _expect(positions == sorted(positions), "heading order = " + " | ".join(headings))
    body = _section_body_text(sections[positions[2]])
    for literal in ("docs/config.md", "docs/config-migration.md", "config/app.yaml"):
        _expect(literal in body, "config section lacks " + literal)
    return True, "config section placed and linked"


def _t24():
    text = _read_text("README.md").replace("\r\n", "\n").replace("\r", "\n")
    sections = _markdown_sections(text)
    headings = [item["heading"] for item in sections]
    _expect(headings.count("## 配置") == 1, "## 配置 count = " + str(headings.count("## 配置")))
    index = headings.index("## 配置")
    start = sections[index]["index"]
    end = sections[index + 1]["index"] if index + 1 < len(sections) else None
    lines = text.split("\n")
    remainder = "\n".join(lines[:start] + (lines[end:] if end is not None else []))
    digest = _sha256_text(_normalize_markdown(remainder))
    _expect(
        digest == BASELINE_README_NORMALIZED_SHA256,
        "README outside the config section differs from baseline",
    )
    return True, "README remainder matches baseline"


# ---------------------------------------------------------------------------
# 1.3 树形状（T25-T26）
# ---------------------------------------------------------------------------
def _t25():
    expected = set(EXPECTED_PATHS)
    actual = set(_tree_files())
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    _expect(not missing, "missing paths: " + ", ".join(missing))
    _expect(not extra, "unexpected paths: " + ", ".join(extra))
    return True, str(len(actual)) + " files"


def _t26():
    assert TREE is not None
    for rel, digest in sorted(FROZEN_BASELINE.items()):
        path = TREE / rel
        _expect(path.is_file(), "missing frozen file " + rel)
        _expect(_sha256_file(path) == digest, "frozen file changed: " + rel)
    return True, str(len(FROZEN_BASELINE)) + " frozen files byte-identical"


# ---------------------------------------------------------------------------
# 2 入口命令（EN1-EN7）
# ---------------------------------------------------------------------------
def _en1():
    tree_copy = _new_copy("pytest")
    result = _run(_pytest_base_args() + ["-q", "-p", "no:cacheprovider"], tree_copy)
    _expect(
        result.returncode == 0,
        "pytest exit " + str(result.returncode) + ": " + _tail(result.stdout + result.stderr),
    )
    output = result.stdout + "\n" + result.stderr
    summary = _tail(output)
    _expect(re.search(r"\d+ passed", summary) is not None, "no passed summary: " + summary)
    _expect(re.search(r"\d+ (failed|error)", output) is None, "pytest reported failures")
    _expect(
        not any(line.startswith("ERROR ") for line in output.splitlines()),
        "pytest reported collection errors",
    )
    return True, summary


def _en2():
    tree_copy = _new_copy("collect")
    result = _run(
        _pytest_base_args() + ["--collect-only", "-q", "-p", "no:cacheprovider"], tree_copy
    )
    _expect(
        result.returncode == 0,
        "collect exit " + str(result.returncode) + ": " + _tail(result.stdout + result.stderr),
    )
    output = result.stdout + "\n" + result.stderr
    match = re.search(r"(\d+) tests? collected", output)
    _expect(match is not None, "cannot read the collected count: " + _tail(output))
    count = int(match.group(1))
    _expect(count >= COLLECTED_MIN, "collected " + str(count) + " tests")
    return True, str(count) + " tests collected"


def _en3():
    tree_copy = _new_copy("script-valid")
    result = _run([sys.executable, SCRIPT_PATH, "--config", "config/app.yaml"], tree_copy)
    _expect(
        result.returncode == 0,
        "exit " + str(result.returncode) + ": " + _tail(result.stdout + result.stderr),
    )
    _expect(len(_non_blank_lines(result.stdout)) == 1, "stdout is not exactly one line")
    _expect(not _non_blank_lines(result.stderr), "stderr is not empty")
    return True, "valid config: exit 0, one stdout line"


def _en4():
    path = _write_yaml("en4-v1.yaml", V1_CONFIG)
    tree_copy = _new_copy("script-v1")
    result = _run([sys.executable, SCRIPT_PATH, "--config", str(path)], tree_copy)
    _expect(
        result.returncode == 1,
        "exit " + str(result.returncode) + ": " + _tail(result.stdout + result.stderr),
    )
    errors = _non_blank_lines(result.stderr)
    _expect(len(errors) == 1, "stderr has " + str(len(errors)) + " non-blank lines")
    _expect("retry_policy" in errors[0], "stderr lacks the retry_policy hint")
    _expect(not _non_blank_lines(result.stdout), "stdout is not empty on failure")
    _expect("Traceback" not in result.stderr, "stderr contains a traceback")
    _expect(
        re.search(r"[A-Za-z]:[\\/]", result.stderr) is None,
        "stderr contains an absolute path",
    )
    return True, "v1 config: exit 1, one stderr line with the hint"


def _en5():
    tree_copy = _new_copy("script-bad")
    probes = (
        ("unknown key", _write_yaml("en5-unknown.yaml", _v2(timeout=5))),
        ("missing file", _fixtures() / "en5-missing.yaml"),
    )
    for label, path in probes:
        result = _run([sys.executable, SCRIPT_PATH, "--config", str(path)], tree_copy)
        _expect(result.returncode == 1, label + ": exit " + str(result.returncode))
        _expect(len(_non_blank_lines(result.stderr)) == 1, label + ": stderr line count")
        _expect("Traceback" not in result.stderr, label + ": stderr contains a traceback")
    return True, "unknown key and missing file: exit 1 with one line"


def _en6():
    tree_copy = _new_copy("script-readonly")
    config_path = tree_copy / "config/app.yaml"
    before = _sha256_file(config_path)
    result = _run([sys.executable, SCRIPT_PATH, "--config", "config/app.yaml"], tree_copy)
    _expect(result.returncode == 0, "exit " + str(result.returncode))
    _expect(_sha256_file(config_path) == before, "the script rewrote config/app.yaml")
    fixture = _write_yaml("en6-v1.yaml", V1_CONFIG)
    fixture_before = _sha256_file(fixture)
    result = _run([sys.executable, SCRIPT_PATH, "--config", str(fixture)], tree_copy)
    _expect(result.returncode == 1, "v1 exit " + str(result.returncode))
    _expect(_sha256_file(fixture) == fixture_before, "the script rewrote the checked file")
    return True, "checked files stay byte-identical"


def _en7():
    tree_copy = _new_copy("script-usage")
    _expect((tree_copy / SCRIPT_PATH).is_file(), "tools/check_config.py is missing")
    result = _run([sys.executable, SCRIPT_PATH], tree_copy)
    _expect(result.returncode == 2, "exit " + str(result.returncode))
    errors = " ".join(_non_blank_lines(result.stderr))
    _expect(bool(errors), "argparse error is silent")
    _expect("usage" in errors.lower(), "stderr is not an argparse usage message")
    return True, "missing --config: exit 2"


# ---------------------------------------------------------------------------
# 3 接口契约（I1-I7）
# ---------------------------------------------------------------------------
def _i1():
    load = _loader()
    _expect(inspect.isfunction(load), "load_config is " + type(load).__name__)
    parameters = list(inspect.signature(load).parameters.values())
    _expect(
        [parameter.name for parameter in parameters] == ["path"],
        "parameters = " + repr([parameter.name for parameter in parameters]),
    )
    parameter = parameters[0]
    _expect(parameter.default is inspect.Parameter.empty, "path has a default")
    _expect(
        parameter.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY),
        "path kind = " + str(parameter.kind),
    )
    return True, "load_config(path)"


def _i2():
    load = _loader()
    text = (
        "app_name: 演示店\n"
        "retry_policy:\n"
        "  max_attempts: 2\n"
        "  backoff_ms: 50\n"
        "  jitter: true\n"
        "feature_flags:\n"
        "  - 结算\n"
    )
    path = _fixture_text("utf8-unicode.yaml", text)
    before = _sha256_file(path)
    data = load(path)
    _expect(data["app_name"] == "演示店", "app_name = " + repr(data["app_name"]))
    _expect(data["feature_flags"] == ["结算"], "feature_flags = " + repr(data["feature_flags"]))
    _expect(_sha256_file(path) == before, "the loader rewrote the config file")
    return True, "UTF-8 config read without writes"


def _i3():
    module = _script_module()
    main = getattr(module, "main", None)
    _expect(callable(main), "tools.check_config has no callable main")
    parameters = list(inspect.signature(main).parameters.values())
    _expect(len(parameters) == 1, "main takes " + str(len(parameters)) + " parameters")
    _expect(parameters[0].name == "argv", "parameter = " + parameters[0].name)
    _expect(parameters[0].default is None, "argv default is not None")
    valid = _write_yaml("i3-valid.yaml", _v2())
    v1 = _write_yaml("i3-v1.yaml", V1_CONFIG)
    ok = main(["--config", str(valid)])
    _expect(
        isinstance(ok, int) and not isinstance(ok, bool) and ok == 0,
        "main(valid) = " + repr(ok),
    )
    bad = main(["--config", str(v1)])
    _expect(
        isinstance(bad, int) and not isinstance(bad, bool) and bad == 1,
        "main(v1) = " + repr(bad),
    )
    tree = _parse_tree_file(SCRIPT_PATH)
    _expect(_has_main_guard(tree), "no __main__ guard calling main()")
    return True, "main(argv=None) -> int, __main__ guard present"


def _i4():
    tree = _parse_tree_file(SCRIPT_PATH)
    imports = _import_names(tree)
    _expect(
        any(name == "shop.config" or name.startswith("shop.config.") for name in imports),
        "the script does not import shop.config",
    )
    calls = _call_names(tree)
    _expect(
        any(name == "load_config" or name.endswith(".load_config") for name in calls),
        "the script never calls load_config",
    )
    _expect(
        any(name in {"sys.path.insert", "sys.path.append"} for name in calls),
        "the script does not put <project>/src on sys.path",
    )
    constants = _string_constants(tree)
    for key in ("max_attempts", "backoff_ms", "jitter"):
        _expect(key not in constants, "the script rewrote the key set: " + key)
    return True, "validation goes through shop.config.load_config"


def _i5():
    for rel, minimum in NEW_TEST_SPECS:
        module = _parse_tree_file(rel)
        count = _test_function_count(module)
        _expect(count >= minimum, rel + " has " + str(count) + " test functions")
        _expect(_assert_count(module) >= 1, rel + " has no assert")
        markers = _skip_markers(module)
        _expect(not markers, rel + " uses skip/xfail: " + ", ".join(markers))
    config_tests = _parse_tree_file("tests/test_config.py")
    offending = sorted(
        name
        for name in _import_names(config_tests)
        if name == "tools" or name.startswith("tools.")
    )
    _expect(not offending, "tests/test_config.py imports tools: " + ", ".join(offending))
    return True, "new tests: counts, asserts, no skips, no tools import"


def _i6():
    loader_module = _parse_tree_file(LOADER_PATH)
    _expect(bool(ast.get_docstring(loader_module)), LOADER_PATH + " has no module docstring")
    load = _find_function(loader_module, "load_config")
    _expect(load is not None, LOADER_PATH + " has no load_config")
    _expect(bool(ast.get_docstring(load)), "load_config has no docstring")
    script_module = _parse_tree_file(SCRIPT_PATH)
    _expect(bool(ast.get_docstring(script_module)), SCRIPT_PATH + " has no module docstring")
    main = _find_function(script_module, "main")
    _expect(main is not None, SCRIPT_PATH + " has no main")
    _expect(bool(ast.get_docstring(main)), "main has no docstring")
    return True, "module and public docstrings present"


def _i7():
    module = _parse_tree_file(LOADER_PATH)
    forbidden = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            forbidden.extend(
                alias.name
                for alias in node.names
                if alias.name == "shop" or alias.name.startswith("shop.")
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                forbidden.append("." * node.level + (node.module or ""))
            module_name = node.module or ""
            if module_name == "shop" or module_name.startswith("shop."):
                forbidden.append(module_name)
    _expect(
        not forbidden,
        "the model layer imports shop modules: " + ", ".join(sorted(set(forbidden))),
    )
    return True, "src/shop/config.py imports no shop module"


# ---------------------------------------------------------------------------
# 用例表 / 单条包装 / main
# ---------------------------------------------------------------------------
CASES = [
    ("T01", _t01),
    ("T02", _t02),
    ("T03", _t03),
    ("T04", _t04),
    ("T05", _t05),
    ("T06", _t06),
    ("T07", _t07),
    ("T08", _t08),
    ("T09", _t09),
    ("T10", _t10),
    ("T11", _t11),
    ("T12", _t12),
    ("T13", _t13),
    ("T14", _t14),
    ("T15", _t15),
    ("T16", _t16),
    ("T17", _t17),
    ("T18", _t18),
    ("T19", _t19),
    ("T20", _t20),
    ("T21", _t21),
    ("T22", _t22),
    ("T23", _t23),
    ("T24", _t24),
    ("T25", _t25),
    ("T26", _t26),
    ("EN1", _en1),
    ("EN2", _en2),
    ("EN3", _en3),
    ("EN4", _en4),
    ("EN5", _en5),
    ("EN6", _en6),
    ("EN7", _en7),
    ("I1", _i1),
    ("I2", _i2),
    ("I3", _i3),
    ("I4", _i4),
    ("I5", _i5),
    ("I6", _i6),
    ("I7", _i7),
]


def _run_case(case_id, func):
    """一条用例失败不能终止整轮；detail 只留异常类型 + 脱敏短消息。"""
    try:
        passed, detail = func()
    except KeyboardInterrupt:
        raise
    except subprocess.TimeoutExpired:
        return {"id": case_id, "pass": False, "detail": "timeout"}
    except BaseException as exc:  # noqa: BLE001 - 单条失败不能终止整轮
        detail = _scrub(type(exc).__name__ + ": " + str(exc))[:400]
        return {"id": case_id, "pass": False, "detail": detail or type(exc).__name__}
    return {"id": case_id, "pass": bool(passed), "detail": _scrub(str(detail))[:400]}


def _cannot_run(message):
    sys.stderr.write("runner: cannot run: " + message + "\n")
    return 2


def main():
    global TREE
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    raw = os.environ.get("BANK_TASK_TREE")
    if not raw:
        return _cannot_run("BANK_TASK_TREE is not set")
    TREE = Path(raw).resolve()
    if not TREE.is_dir():
        return _cannot_run("BANK_TASK_TREE does not point to a directory")
    if yaml is None:
        return _cannot_run("PyYAML is unavailable")
    if [case_id for case_id, _func in CASES] != CASE_IDS:
        return _cannot_run("case registry is not T01..T26 / EN1..EN7 / I1..I7")

    try:
        _shared_copy()
        _temp_root()
    except (OSError, RuntimeError) as exc:
        return _cannot_run("cannot copy the evaluated tree: " + type(exc).__name__)

    cases = []
    swallowed = io.StringIO()
    with contextlib.redirect_stdout(swallowed), contextlib.redirect_stderr(swallowed):
        for case_id, func in CASES:
            cases.append(_run_case(case_id, func))

    passed = sum(1 for case in cases if case["pass"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "tree": _tree_label(raw),
        "cases": cases,
        "summary": {"passed": passed, "total": len(cases)},
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
