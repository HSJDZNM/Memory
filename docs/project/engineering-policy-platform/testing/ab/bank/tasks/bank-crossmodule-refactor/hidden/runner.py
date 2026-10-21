"""bank-crossmodule-refactor 隐藏验收 runner：T01-T26 + EN1-EN4 + I1-I4（34 条）。

用法::

    BANK_TASK_TREE=<被评树> python hidden/runner.py

契约（bank/README.md 4.3 与 hidden/PLAN.md 0）:

- 被评树只从环境变量 BANK_TASK_TREE 读入，绝不写：所有需要执行的动作（pytest / 模块导入）
  都在树的副本里跑（临时目录，用完即删）；进程内 sys.dont_write_bytecode = True，
  子进程 PYTHONDONTWRITEBYTECODE=1 与 -p no:cacheprovider；子进程超时 60 秒，
  解释器 = 运行 runner 的 sys.executable；
- stdout 唯一载荷（UTF-8）::

      {"schema_version": "1.0", "tree": "<相对调用 cwd 的标签>",
       "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
       "summary": {"passed": 34, "total": 34}}

  载荷不含时戳 / run id / 绝对路径 / 耗时；同一 cwd + 同一棵树两次运行逐字节相同；
- 退出码：全过 0 / 有失败 1 / 跑不成 2（缺 BANK_TASK_TREE、树不是目录、用例集合不完整、
  树副本建不出来）；2 = 判不了，不是 0 分；
- 每条用例独立 try/except：一条异常只让该条 fail，detail = 异常类型 + 脱敏短消息；
- 反向用例（T01-T05 / T09 / T15 / T17 / T23-T25）断言的是「期望失败 / 期望拒绝 / 期望不存在」。
"""
from __future__ import annotations

import ast
import atexit
import contextlib
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

sys.dont_write_bytecode = True

SCHEMA_VERSION = "1.0"
TIMEOUT_SECONDS = 60
COLLECTED_MIN = 4
FENCE = chr(96) * 3

CASE_IDS = (
    ["T%02d" % index for index in range(1, 27)]
    + ["EN1", "EN2", "EN3", "EN4"]
    + ["I1", "I2", "I3", "I4"]
)

# 14 个基线文件（逐字节起点）。来源：包内 baseline/ 的 14 个文件实算 sha256
# （2026-10 复核；组合摘要 b6d6d2f72575d56ce8507ad188c75e6e795c80965106be83bef09d00261d2e91）。
BASELINE_SHA256 = {
    "AGENTS.md": "ef20cdca0d6c43dbb5038449c90a972d44837e4b9ddc17e074f994d5eed669a3",
    "README.md": "5b4313609e4a28b61b43cd7b58ead2b99866284e532c68b79983cd3698213a5a",
    "config/refund_policy.yaml": (
        "8c8198bb460a06fc3603435a5ff4131632a6aa1664e168d2dfbacd10bd3cf078"
    ),
    "conftest.py": "edd7cea37c657fb322cdee3038ca9aed35f40c7657a0faacb6640d6de9b050e7",
    "data/refunds-legacy.jsonl": (
        "3988a403df144afbe742ede5edbfcc6fe37c2382a976acc67b81df0a89de6a66"
    ),
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
    "tools/__init__.py": "f66ec0041ebb636c9fdee98ff706cda2ef04ca40474f79b84027e1e0cb3618eb",
}

# 允许写 ∩ 基线 = 可改写的 7 个既有文件（其余 7 个是冻结文件）。
MODIFIABLE_BASELINE = frozenset(
    {
        "README.md",
        "src/shop/order_controller.py",
        "src/shop/order_repository.py",
        "src/shop/order_service.py",
        "tests/test_order_controller.py",
        "tests/test_order_repository.py",
        "tests/test_order_service.py",
    }
)

# 冻结文件 = 基线 14 - 可改写 7 = 7（T24 逐字节校验这 7 个）。
FROZEN_BASELINE = {
    path: digest
    for path, digest in BASELINE_SHA256.items()
    if path not in MODIFIABLE_BASELINE
}

# 任务新建的 3 个文件（14 基线 ∪ 3 = 17 文件；T25 用）。
NEW_PATHS = frozenset(
    {
        "docs/api.md",
        "src/shop/order_api.py",
        "tests/test_order_api.py",
    }
)

# 允许写 10 条 = 可改写 7 + 新建 3。
ALLOWED_WRITES = frozenset(MODIFIABLE_BASELINE) | NEW_PATHS

EXPECTED_PATHS = frozenset(BASELINE_SHA256) | NEW_PATHS

OLD_NAMES = ("insert", "listing")

EXISTING_TEST_FILES = [
    "tests/test_order_controller.py",
    "tests/test_order_repository.py",
    "tests/test_order_service.py",
]

TEST_FILES = EXISTING_TEST_FILES + ["tests/test_order_api.py"]

DOC_HEADINGS = ("## 对照表", "## 废弃期限", "## 迁移示例")

T10_EXPECTED = {
    "error": "TypeError",
    "listing1": [{"id": 1}, {"id": 2, "note": "x"}],
    "listing2": [{"id": 1}, {"id": 2, "note": "x"}, {"id": 3}],
    "listing3": [{"id": 1}, {"id": 2, "note": "x"}, {"id": 3}],
    "rows": [{"id": 1}, {"id": 2, "note": "x"}, {"id": 99}],
}

IGNORED_SEGMENTS = frozenset(
    {".policy", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
)
CACHE_PREFIXES = ("pytest-cache-files-",)
SKIP_ATTRS = frozenset({"skip", "skipif", "xfail", "importorskip"})

TREE: Path | None = None
_COPY_HOLDER: Path | None = None
_SHARED_COPY: Path | None = None
_SUBPROCESS_TMP: Path | None = None
_CACHE: dict[str, object] = {}


# ---------------------------------------------------------------------------
# 树标签 / 临时目录 / 副本 / 子进程
# ---------------------------------------------------------------------------
def _tree_label(raw: str) -> str:
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


def _is_inside(path: Path, root: Path) -> bool:
    """path 是否落在 root 里（解析符号链接后判断）。"""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _temp_root() -> Path:
    """临时副本的父目录：优先 <cwd>/.tmp，退到树旁与系统 temp。

    任何候选都不得落在被评树内部（只读被评树）；每个候选都要真写一次才算可用：
    有的沙箱允许 mkdir 但拒绝写入，只探测 mkdir 会把「写不了」当成可用。
    """
    override = os.environ.get("BANK_TASK_TMPDIR")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    else:
        candidates.append(Path.cwd() / ".tmp")
        if TREE is not None:
            candidates.append(Path(TREE).parent / ".tmp")
        candidates.append(Path(tempfile.gettempdir()))
    for candidate in candidates:
        probe = candidate / "bank-hidden-runner"
        if TREE is not None and (
            _is_inside(probe, TREE) or _is_inside(candidate, TREE)
        ):
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


def _ignore_artifacts(_directory: str, names: list[str]) -> set[str]:
    """副本里不带走缓存、隐藏目录与 pyc。"""
    ignored = set()
    for name in names:
        if name.startswith(".") or name == "__pycache__" or name.endswith(".pyc"):
            ignored.add(name)
        elif name.startswith(CACHE_PREFIXES):
            ignored.add(name)
    return ignored


def _holder(prefix: str) -> Path:
    """临时目录：不用 mkdtemp（它建 0700 目录，受限宿主会拒绝随后写入）。"""
    root = _temp_root()
    for index in itertools.count(1):
        candidate = root / ("%s-%d-%d" % (prefix, os.getpid(), index))
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        atexit.register(shutil.rmtree, candidate, ignore_errors=True)
        return candidate
    raise RuntimeError("cannot create a temporary holder")


def _shared_copy() -> Path:
    """所有「只读执行」共用的一份副本（pytest / 导入第一次）。"""
    global _COPY_HOLDER, _SHARED_COPY
    if _SHARED_COPY is None or not _SHARED_COPY.is_dir():
        assert TREE is not None
        _COPY_HOLDER = _holder("shared")
        target = _COPY_HOLDER / "tree"
        shutil.copytree(TREE, target, ignore=_ignore_artifacts)
        _SHARED_COPY = target
    return _SHARED_COPY


def _subprocess_tmp() -> Path:
    """子进程的临时目录：继承来的 TEMP 可能被宿主的文件沙箱拒绝，这里换成一个可写的。"""
    global _SUBPROCESS_TMP
    if _SUBPROCESS_TMP is None or not _SUBPROCESS_TMP.is_dir():
        root = _temp_root() / "subprocess-tmp"
        root.mkdir(parents=True, exist_ok=True)
        atexit.register(shutil.rmtree, root, ignore_errors=True)
        _SUBPROCESS_TMP = root
    return _SUBPROCESS_TMP


def _base_env() -> dict[str, str]:
    """子进程环境：不继承 PYTHONPATH/PYTEST_ADDOPTS，临时目录换到可写位置。"""
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


def _run(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """在副本里跑一条命令；解释器 = 运行 runner 的 sys.executable，超时 60 秒。"""
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


_ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/][^\s]*")
_DURATION = re.compile(r"\d+\.\d+s")


def _scrub(text: str) -> str:
    """脱敏：删掉被评树根、临时副本根、其余盘符绝对路径与耗时。"""
    cleaned = str(text)
    roots: list[str] = []
    if TREE is not None:
        roots.append(str(TREE))
    if _COPY_HOLDER is not None:
        roots.append(str(_COPY_HOLDER))
    if _SUBPROCESS_TMP is not None:
        roots.append(str(_SUBPROCESS_TMP))
    for root in roots:
        for variant in (root, root.replace("\\", "/"), root.replace("/", "\\")):
            cleaned = cleaned.replace(variant, "<tree>")
    cleaned = _ABSOLUTE_PATH.sub("<path>", cleaned)
    cleaned = _DURATION.sub("<t>s", cleaned)
    return cleaned


def _tail(text: str, limit: int = 200) -> str:
    """取最后一行非空输出（脱敏后截断）。"""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return _scrub(lines[-1])[:limit] if lines else ""



# ---------------------------------------------------------------------------
# 树内读取 / 模块导入 / AST
# ---------------------------------------------------------------------------
def _read_text(rel: str) -> str:
    """读树里的一个文件（UTF-8）。"""
    assert TREE is not None
    return (TREE / rel).read_text(encoding="utf-8")


def _tree_module(name: str):
    """从副本导入被测树的公开模块（只 import，不实例化任何协作者）。"""
    src = str(_shared_copy() / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import importlib

    return importlib.import_module(name)


def _parse_tree_file(rel: str) -> ast.Module:
    """把树里的一个 .py 解析成 AST。"""
    return ast.parse(_read_text(rel), filename=rel)


def _tree_files() -> list[str]:
    """树内全部文件的相对路径（POSIX），忽略 .policy / 缓存 / 以点开头的目录与文件。"""
    assert TREE is not None
    found: list[str] = []
    for path in TREE.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(TREE).parts
        if any(part in IGNORED_SEGMENTS or part.startswith(".") for part in parts):
            continue
        if path.name.endswith(".pyc"):
            continue
        found.append("/".join(parts))
    return sorted(found)


def _imported_modules(module: ast.Module) -> set[str]:
    """模块里 import 的模块名集合（from shop import x 记 shop 与 shop.x）。"""
    names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            if node.module == "shop":
                for alias in node.names:
                    names.add("shop." + alias.name)
    return names


def _star_imports(module: ast.Module) -> list[str]:
    """通配 import 的位置（有就是违规）。"""
    hits: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    hits.append("line " + str(node.lineno))
    return hits


def _class_node(module: ast.Module, class_name: str) -> ast.ClassDef | None:
    """顶层类定义。"""
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _class_function(module: ast.Module, class_name: str, func_name: str):
    """类里的方法定义（没有就是 None）。"""
    owner = _class_node(module, class_name)
    if owner is None:
        return None
    for node in owner.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return node
    return None


def _calls_chain(function_node, chain: tuple[str, ...]) -> int:
    """数 function_node 里形如 self.<chain[0]>.<chain[1]>...(...) 的调用。"""
    count = 0
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        matched = True
        for attr in reversed(chain):
            if not isinstance(target, ast.Attribute) or target.attr != attr:
                matched = False
                break
            target = target.value
        if not matched:
            continue
        if isinstance(target, ast.Name) and target.id == "self":
            count += 1
    return count


def _constructor_calls(module: ast.Module, names: frozenset[str]) -> list[str]:
    """模块里对给定类名/属性名的调用（例：OrderRepository()）。"""
    hits: list[str] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in names:
            hits.append("line " + str(node.lineno) + ": " + func.id + "()")
        elif isinstance(func, ast.Attribute) and func.attr in names:
            hits.append("line " + str(node.lineno) + ": ." + func.attr + "()")
    return hits


def _test_function_names(module: ast.Module) -> list[str]:
    """模块里的 test_* 函数名。"""
    return [
        node.name
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _assert_count(module: ast.Module) -> int:
    """模块里 assert 语句的条数。"""
    return sum(1 for node in ast.walk(module) if isinstance(node, ast.Assert))


def _skip_markers(module: ast.Module) -> list[str]:
    """skip / skipif / xfail / importorskip 的引用（有就是违规）。"""
    hits: list[str] = []
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


def _identifier_hits(text: str) -> list[tuple[str, int]]:
    """文本里旧名的独立单词命中：(名字, 行号)。"""
    hits: list[tuple[str, int]] = []
    for number, line in enumerate(text.splitlines(), 1):
        for name in OLD_NAMES:
            if re.search(r"(?<![A-Za-z0-9_])" + name + r"(?![A-Za-z0-9_])", line):
                hits.append((name, number))
    return hits


def _ast_hits(module: ast.Module) -> list[tuple[str, int]]:
    """AST 里旧名的标识符命中：(名字, 行号)；docstring 不在 AST 口径内，由文本口径兜。"""
    hits: list[tuple[str, int]] = []
    for node in ast.walk(module):
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.arg):
            name = node.arg
        elif isinstance(node, ast.keyword):
            name = node.arg
        elif isinstance(node, ast.alias):
            name = node.name if node.asname is None else node.asname
        if name in OLD_NAMES:
            hits.append((name, getattr(node, "lineno", 0)))
    return hits


def _old_name_hits(rel: str) -> list[str]:
    """一个文件里旧名的全部命中（AST + 文本两种读法）。"""
    problems = [
        "%s:%d: %s" % (rel, line, name)
        for name, line in _identifier_hits(_read_text(rel))
    ]
    problems += [
        "%s:%d: %s" % (rel, line, name) for name, line in _ast_hits(_parse_tree_file(rel))
    ]
    return problems


# ---------------------------------------------------------------------------
# 断言小工具
# ---------------------------------------------------------------------------
def _expect(condition: bool, message: str) -> None:
    """条件不成立就抛 AssertionError（detail 只用脱敏短消息）。"""
    if not condition:
        raise AssertionError(message)


def _has_word(text: str, word: str) -> bool:
    """text 里有没有独立单词 word。"""
    return re.search(
        r"(?<![A-Za-z0-9_])" + re.escape(word) + r"(?![A-Za-z0-9_])", text
    ) is not None


def _is_deprecated_note(text: str) -> bool:
    """弃用说明：含「弃用」或 deprecated（大小写不敏感）。"""
    return "弃用" in text or "deprecated" in text.lower()


# ---------------------------------------------------------------------------
# 替身（只实现新名；旧名一调就抛 AssertionError）
# ---------------------------------------------------------------------------
class _FakeRepository:
    """只实现 add / list_all 的替身：记录收到的对象，返回预先给定的对象。"""

    def __init__(self, add_error=None, list_error=None) -> None:
        self.add_calls: list[object] = []
        self.list_all_calls = 0
        self.returned_row: dict = {"id": 99}
        self.returned_rows: list[dict] = [{"id": 99}]
        self.add_error = add_error
        self.list_error = list_error

    def add(self, payload: dict) -> dict:
        """记录参数并返回预先给定的行对象。"""
        self.add_calls.append(payload)
        if self.add_error is not None:
            raise self.add_error
        return self.returned_row

    def list_all(self) -> list[dict]:
        """记录调用次数并返回预先给定的列表对象。"""
        self.list_all_calls += 1
        if self.list_error is not None:
            raise self.list_error
        return self.returned_rows

    def insert(self, payload: dict) -> dict:
        """旧名：门面 / service 不该再调它。"""
        raise AssertionError("insert must not be called")

    def listing(self) -> list[dict]:
        """旧名：门面 / service 不该再调它。"""
        raise AssertionError("listing must not be called")


class _FakeService:
    """只实现 create / list_all 的替身：旧名一调就抛 AssertionError。"""

    def __init__(self) -> None:
        self.create_calls: list[object] = []
        self.list_all_calls = 0
        self.returned_row: dict = {"id": 7}
        self.returned_rows: list[dict] = [{"id": 7}]

    def create(self, payload: dict) -> dict:
        """记录参数并返回预先给定的行对象。"""
        self.create_calls.append(payload)
        return self.returned_row

    def list_all(self) -> list[dict]:
        """记录调用次数并返回预先给定的列表对象。"""
        self.list_all_calls += 1
        return self.returned_rows

    def insert(self, payload: dict) -> dict:
        """旧名：入口层不该再调它。"""
        raise AssertionError("insert must not be called")

    def listing(self) -> list[dict]:
        """旧名：入口层不该再调它。"""
        raise AssertionError("listing must not be called")



# ---------------------------------------------------------------------------
# 1 T 组：旧名清零（T01-T05）
# ---------------------------------------------------------------------------
def _t01() -> tuple[bool, str]:
    """repository 的旧名 0 处（AST + 文本）。"""
    problems = _old_name_hits("src/shop/order_repository.py")
    _expect(not problems, "old names: " + "; ".join(problems[:4]))
    return True, "repository: 0 old-name hits (AST + text)"


def _t02() -> tuple[bool, str]:
    """service 的旧名 0 处，且 create / list_all 都经 repository 新名。"""
    rel = "src/shop/order_service.py"
    problems = _old_name_hits(rel)
    _expect(not problems, "old names: " + "; ".join(problems[:4]))
    module = _parse_tree_file(rel)
    create = _class_function(module, "OrderService", "create")
    list_all = _class_function(module, "OrderService", "list_all")
    _expect(create is not None, "OrderService.create is missing")
    _expect(list_all is not None, "OrderService.list_all is missing")
    _expect(
        _calls_chain(create, ("repository", "add")) >= 1,
        "create does not call self.repository.add(...)",
    )
    _expect(
        _calls_chain(list_all, ("repository", "list_all")) >= 1,
        "list_all does not call self.repository.list_all()",
    )
    _expect(
        _calls_chain(create, ("repository", "insert")) == 0,
        "create still calls self.repository.insert(...)",
    )
    _expect(
        _calls_chain(list_all, ("repository", "listing")) == 0,
        "list_all still calls self.repository.listing()",
    )
    return True, "service: 0 old names, create -> repository.add, list_all -> repository.list_all"


def _t03() -> tuple[bool, str]:
    """controller 的旧名 0 处，且 create / list_all 都经 service。"""
    rel = "src/shop/order_controller.py"
    problems = _old_name_hits(rel)
    _expect(not problems, "old names: " + "; ".join(problems[:4]))
    module = _parse_tree_file(rel)
    create = _class_function(module, "OrderController", "create")
    list_all = _class_function(module, "OrderController", "list_all")
    _expect(create is not None, "OrderController.create is missing")
    _expect(list_all is not None, "OrderController.list_all is missing")
    _expect(
        _calls_chain(create, ("service", "create")) >= 1,
        "create does not call self.service.create(...)",
    )
    _expect(
        _calls_chain(list_all, ("service", "list_all")) >= 1,
        "list_all does not call self.service.list_all()",
    )
    _expect(
        _calls_chain(create, ("service", "insert")) == 0,
        "create still calls self.service.insert(...)",
    )
    _expect(
        _calls_chain(list_all, ("service", "listing")) == 0,
        "list_all still calls self.service.listing()",
    )
    return True, "controller: 0 old names, create -> service.create, list_all -> service.list_all"


def _t04() -> tuple[bool, str]:
    """三个既有测试文件：旧名 0 处，且各有 case 与 assert。"""
    problems: list[str] = []
    for rel in EXISTING_TEST_FILES:
        problems += _old_name_hits(rel)
        module = _parse_tree_file(rel)
        if not _test_function_names(module):
            problems.append(rel + ": no test_* function")
        if _assert_count(module) < 1:
            problems.append(rel + ": no assert")
    _expect(not problems, "; ".join(problems[:6]))
    return True, "3/3 existing tests: 0 old names, tests and asserts kept"


def _t05() -> tuple[bool, str]:
    """可改写的 .py：旧名只出现在门面与它的契约测试里，且两处都真的有。

    冻结的基线文件不在扫描范围：conftest.py 里那句 sys.path.insert(0, ...) 是标准库调用，
    不是被废弃的 OrderRepository API；它逐字节由 T24 钉住，改一个字节就会红，不能用来藏旧名。
    """
    hits: dict[str, list[str]] = {}
    for rel in _tree_files():
        if not rel.endswith(".py"):
            continue
        if rel in FROZEN_BASELINE:
            continue
        found = _old_name_hits(rel)
        if found:
            hits[rel] = found
    allowed = {"src/shop/order_api.py", "tests/test_order_api.py"}
    extra = sorted(set(hits) - allowed)
    _expect(not extra, "old names outside the facade and its test: " + ", ".join(extra))
    missing = sorted(allowed - set(hits))
    _expect(not missing, "no old-name usage in: " + ", ".join(missing))
    return True, "old names only in the facade and its contract test"


# ---------------------------------------------------------------------------
# 2 T 组：行为等价（T06-T10）
# ---------------------------------------------------------------------------
def _repository():
    """从副本导入新的 OrderRepository 类。"""
    return _tree_module("shop.order_repository").OrderRepository


def _t06() -> tuple[bool, str]:
    """add 返回副本：值相等、不是入参对象、改返回值不影响内部。"""
    repository = _repository()()
    payload = {"id": 1, "note": "a"}
    row = repository.add(payload)
    _expect(isinstance(row, dict), "add() returned " + type(row).__name__)
    _expect(row == payload, "add() returned " + json.dumps(row, sort_keys=True)[:120])
    _expect(row is not payload, "add() returned the argument object")
    row["id"] = 2
    row["note"] = "b"
    _expect(
        repository.list_all() == [{"id": 1, "note": "a"}],
        "mutating the returned row changed stored data",
    )
    return True, "add() returns an equal, separate copy"


def _t07() -> tuple[bool, str]:
    """入参隔离与写入顺序。"""
    repository = _repository()()
    payload = {"id": 1, "note": "a"}
    repository.add(payload)
    payload["id"] = 99
    payload["extra"] = 1
    _expect(
        repository.list_all() == [{"id": 1, "note": "a"}],
        "mutating the argument changed stored data",
    )
    repository.add({"id": 2})
    repository.add({"id": 3})
    ids = [row["id"] for row in repository.list_all()]
    _expect(ids == [1, 2, 3], "stored order = " + repr(ids))
    return True, "arguments are copied; three adds keep 1,2,3 order"


def _t08() -> tuple[bool, str]:
    """list_all 每次返回新 list、每行新 dict；改返回值不影响内部。"""
    repository = _repository()()
    repository.add({"id": 1})
    repository.add({"id": 2})
    first = repository.list_all()
    second = repository.list_all()
    _expect(isinstance(first, list), "list_all() returned " + type(first).__name__)
    _expect(first is not second, "list_all() returned the same list object twice")
    _expect(first[0] is not second[0], "two list_all() results share row objects")
    first.append({"id": 3})
    first[0]["id"] = 42
    first.clear()
    _expect(
        repository.list_all() == [{"id": 1}, {"id": 2}],
        "mutating list_all() output changed stored data",
    )
    return True, "list_all() returns fresh lists and fresh row dicts"


def _t09() -> tuple[bool, str]:
    """非映射入参：与基线同形的 TypeError，且失败不落行。"""
    repository = _repository()()
    for bad in (None, 42, {1, 2}):
        label = type(bad).__name__
        try:
            repository.add(bad)
        except TypeError:
            pass
        except Exception as exc:  # noqa: BLE001 - 异常形态不对也算失败
            raise AssertionError(
                "add(" + label + ") raised " + type(exc).__name__ + " instead of TypeError"
            ) from exc
        else:
            raise AssertionError("add(" + label + ") was accepted")
    _expect(repository.list_all() == [], "a failed add() still stored a row")
    return True, "3/3 non-mapping payloads raise TypeError and store nothing"


def _t10() -> tuple[bool, str]:
    """controller 层同一操作序列与基线逐字节等价。"""
    controller = _tree_module("shop.order_controller").OrderController()
    rows = [controller.create({"id": 1}), controller.create({"id": 2, "note": "x"})]
    listing1 = controller.list_all()
    listing1_snapshot = json.loads(json.dumps(listing1, sort_keys=True))
    rows.append(controller.create({"id": 3}))
    rows[2]["id"] = 99
    listing2 = controller.list_all()
    listing1[0]["id"] = 42
    listing3 = controller.list_all()
    try:
        controller.create(None)
    except TypeError:
        error = "TypeError"
    except Exception as exc:  # noqa: BLE001 - 异常类型要和基线一致
        error = type(exc).__name__
    else:
        error = "no error"
    actual = {
        "error": error,
        "listing1": listing1_snapshot,
        "listing2": listing2,
        "listing3": listing3,
        "rows": rows,
    }
    expected = json.dumps(T10_EXPECTED, ensure_ascii=False, sort_keys=True)
    got = json.dumps(actual, ensure_ascii=False, sort_keys=True)
    _expect(got == expected, "sequence = " + got[:300])
    return True, "controller sequence is byte-identical to the baseline semantics"


# ---------------------------------------------------------------------------
# 3 T 组：兼容门面的转发（T11-T17）
# ---------------------------------------------------------------------------
def _api_class():
    """从副本导入门面类。"""
    return _tree_module("shop.order_api").OrderApi


def _t11() -> tuple[bool, str]:
    """门面 insert 原样透传（参数是同一个对象、返回值是同一个对象）。"""
    fake = _FakeRepository()
    api = _api_class()(fake)
    payload = {"id": 1}
    result = api.insert(payload)
    _expect(result is fake.returned_row, "insert() did not return the repository object")
    _expect(len(fake.add_calls) == 1, "add() was called " + str(len(fake.add_calls)) + " times")
    _expect(fake.add_calls[0] is payload, "insert() did not forward the argument object")
    _expect(payload == {"id": 1}, "insert() mutated the payload")
    _expect(fake.list_all_calls == 0, "insert() also called list_all()")
    return True, "insert() forwards the argument and returns the repository object"


def _t12() -> tuple[bool, str]:
    """门面 listing 原样透传（返回同一个 list 对象）。"""
    fake = _FakeRepository()
    api = _api_class()(fake)
    result = api.listing()
    _expect(result is fake.returned_rows, "listing() did not return the repository object")
    _expect(
        fake.list_all_calls == 1,
        "list_all() was called " + str(fake.list_all_calls) + " times",
    )
    _expect(fake.add_calls == [], "listing() also called add()")
    return True, "listing() returns the repository list object, list_all() once"


def _t13() -> tuple[bool, str]:
    """门面不复制：透传对象的 id() 保持不变。"""
    fake = _FakeRepository()
    api = _api_class()(fake)
    payload = {"id": 1}
    _expect(id(api.insert(payload)) == id(fake.returned_row), "insert() returned a copy")
    _expect(fake.add_calls[0] is payload, "insert() copied the argument")
    _expect(id(api.listing()) == id(fake.returned_rows), "listing() returned a copy")
    return True, "both facade methods keep object identity"


def _t14() -> tuple[bool, str]:
    """构造器恰一个必填位置参数 repository，且不自己 new repository。"""
    api_class = _api_class()
    parameters = list(inspect.signature(api_class.__init__).parameters.values())[1:]
    _expect(len(parameters) == 1, "constructor takes " + str(len(parameters)) + " parameters")
    parameter = parameters[0]
    _expect(parameter.name == "repository", "parameter name is " + repr(parameter.name))
    _expect(parameter.default is inspect.Parameter.empty, "repository has a default value")
    _expect(
        parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD,
        "repository kind = " + str(parameter.kind),
    )
    fake = _FakeRepository()
    api = api_class(repository=fake)
    _expect(api.repository is fake, "the constructor did not keep the given repository")
    try:
        api_class()
    except TypeError:
        pass
    else:
        raise AssertionError("OrderApi() without a repository was accepted")
    return True, "OrderApi(repository) takes exactly one required positional argument"


def _t15() -> tuple[bool, str]:
    """AST：门面只 import shop.order_repository，且不实例化 OrderRepository。"""
    module = _parse_tree_file("src/shop/order_api.py")
    imports = _imported_modules(module)
    allowed = {"shop.order_repository"}
    extra = sorted(imports - allowed)
    _expect(not extra, "unexpected imports: " + ", ".join(extra))
    _expect(
        "shop.order_repository" in imports,
        "order_api.py does not import shop.order_repository",
    )
    _expect(not _star_imports(module), "order_api.py uses a star import")
    calls = _constructor_calls(module, frozenset({"OrderRepository"}))
    _expect(not calls, "OrderRepository() instantiated: " + "; ".join(calls))
    return True, "imports limited to shop.order_repository, no OrderRepository() call"


def _t16() -> tuple[bool, str]:
    """模块 / 类 / 两个方法的弃用说明齐备，且各写出对应新名。"""
    module = _tree_module("shop.order_api")
    api_class = module.OrderApi
    module_doc = (getattr(module, "__doc__", None) or "").strip()
    class_doc = (getattr(api_class, "__doc__", None) or "").strip()
    insert_doc = (getattr(api_class.insert, "__doc__", None) or "").strip()
    listing_doc = (getattr(api_class.listing, "__doc__", None) or "").strip()
    _expect(module_doc, "module docstring is missing")
    _expect(class_doc, "class docstring is missing")
    _expect(insert_doc, "insert docstring is missing")
    _expect(listing_doc, "listing docstring is missing")
    _expect(_is_deprecated_note(insert_doc), "insert docstring does not mark the API deprecated")
    _expect(_is_deprecated_note(listing_doc), "listing docstring does not mark the API deprecated")
    _expect(_has_word(insert_doc, "add"), "insert docstring does not name add")
    _expect(_has_word(listing_doc, "list_all"), "listing docstring does not name list_all")
    return True, "module, class and both methods carry the deprecation note and the new name"


def _t17() -> tuple[bool, str]:
    """门面不吞、不包装异常：同一个异常实例原样穿出。"""
    value_error = ValueError("boom")
    api = _api_class()(_FakeRepository(add_error=value_error))
    try:
        api.insert({"id": 1})
    except ValueError as exc:
        _expect(exc is value_error, "insert() wrapped the ValueError")
    except Exception as exc:  # noqa: BLE001 - 换类型也算失败
        raise AssertionError("insert() raised " + type(exc).__name__) from exc
    else:
        raise AssertionError("insert() did not raise")
    key_error = KeyError("missing")
    api = _api_class()(_FakeRepository(list_error=key_error))
    try:
        api.listing()
    except KeyError as exc:
        _expect(exc is key_error, "listing() wrapped the KeyError")
    except Exception as exc:  # noqa: BLE001 - 换类型也算失败
        raise AssertionError("listing() raised " + type(exc).__name__) from exc
    else:
        raise AssertionError("listing() did not raise")
    return True, "both facade methods re-raise the very same exception instance"


# ---------------------------------------------------------------------------
# 4 T 组：调用链（T18-T20）
# ---------------------------------------------------------------------------
def _t18() -> tuple[bool, str]:
    """service.create 只经 repository.add 一次（替身记录）。"""
    fake = _FakeRepository()
    service = _tree_module("shop.order_service").OrderService(repository=fake)
    payload = {"id": 1}
    result = service.create(payload)
    _expect(len(fake.add_calls) == 1, "add() was called " + str(len(fake.add_calls)) + " times")
    _expect(fake.add_calls[0] is payload, "create() did not forward the argument object")
    _expect(result is fake.returned_row, "create() did not return add()'s value")
    return True, "create() goes through exactly one repository.add()"


def _t19() -> tuple[bool, str]:
    """service.list_all 转发 repository.list_all。"""
    fake = _FakeRepository()
    service = _tree_module("shop.order_service").OrderService(repository=fake)
    result = service.list_all()
    _expect(result is fake.returned_rows, "list_all() did not return the repository object")
    _expect(
        fake.list_all_calls == 1,
        "list_all() was called " + str(fake.list_all_calls) + " times",
    )
    return True, "list_all() returns the repository list object"


def _t20() -> tuple[bool, str]:
    """controller 只经 service：AST 无 repository，行为上转发替身 service。"""
    module = _parse_tree_file("src/shop/order_controller.py")
    imports = _imported_modules(module)
    _expect(
        imports <= {"shop.order_service"},
        "unexpected imports: " + ", ".join(sorted(imports - {"shop.order_service"})),
    )
    _expect(
        "shop.order_service" in imports,
        "order_controller.py does not import shop.order_service",
    )
    names = {node.id for node in ast.walk(module) if isinstance(node, ast.Name)}
    attrs = {node.attr for node in ast.walk(module) if isinstance(node, ast.Attribute)}
    _expect("OrderRepository" not in names, "order_controller.py references OrderRepository")
    _expect("OrderRepository" not in attrs, "order_controller.py references OrderRepository")
    calls = _constructor_calls(module, frozenset({"OrderRepository"}))
    _expect(not calls, "OrderRepository() instantiated: " + "; ".join(calls))
    fake = _FakeService()
    controller = _tree_module("shop.order_controller").OrderController(service=fake)
    _expect(controller.list_all() is fake.returned_rows, "list_all() did not reach the service")
    _expect(
        fake.list_all_calls == 1,
        "service.list_all() was called " + str(fake.list_all_calls) + " times",
    )
    _expect(fake.create_calls == [], "controller.list_all() also called service.create()")
    return True, "controller reaches the repository only through the service"



# ---------------------------------------------------------------------------
# 5 T 组：测试、文档与树形状（T21-T26）
# ---------------------------------------------------------------------------
def _pytest(copy_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """在副本里跑一次 pytest（禁缓存与字节码；解释器 = runner 的解释器）。"""
    return _run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        copy_root,
    )


def _whole_pytest() -> subprocess.CompletedProcess[str]:
    """整树 pytest（结果缓存，T21 之外的整树执行共用一次）。"""
    hit = _CACHE.get("pytest")
    if hit is None:
        hit = _pytest(_shared_copy(), [])
        _CACHE["pytest"] = hit
    return hit


def _collected_count() -> int:
    """收集到的 nodeid 数（--collect-only -q 里含 :: 的行）。"""
    hit = _CACHE.get("collected")
    if hit is None:
        result = _pytest(_shared_copy(), ["--collect-only"])
        _expect(
            result.returncode == 0,
            "collect exit=" + str(result.returncode) + " tail=" + _tail(result.stdout),
        )
        count = sum(1 for line in result.stdout.splitlines() if "::" in line)
        _CACHE["collected"] = count
        hit = count
    return int(hit)


def _has_deprecation_assert(module: ast.Module) -> bool:
    """有没有对弃用说明的断言：__doc__ 属性，或含 deprecated / 弃用的字符串常量。"""
    for node in ast.walk(module):
        if isinstance(node, ast.Attribute) and node.attr == "__doc__":
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if "弃用" in text or "deprecated" in text.lower():
                return True
    return False


def _t21() -> tuple[bool, str]:
    """门面契约测试单独可跑（不依赖别的测试文件的顺序与夹具）。"""
    result = _pytest(_shared_copy(), ["tests/test_order_api.py"])
    _expect(
        result.returncode == 0,
        "pytest exit=" + str(result.returncode) + " tail=" + _tail(result.stdout),
    )
    return True, "tests/test_order_api.py passes on its own"


def _t22() -> tuple[bool, str]:
    """tests/test_order_api.py >=3 条用例，且覆盖转发 / 副本语义 / 弃用说明。"""
    module = _parse_tree_file("tests/test_order_api.py")
    names = _test_function_names(module)
    _expect(len(names) >= 3, "test functions = " + str(len(names)) + " < 3")
    attrs = {node.attr for node in ast.walk(module) if isinstance(node, ast.Attribute)}
    missing = [name for name in ("insert", "listing") if name not in attrs]
    _expect(not missing, "facade methods never called: " + ", ".join(missing))
    identifiers = {node.id for node in ast.walk(module) if isinstance(node, ast.Name)}
    _expect("OrderRepository" in identifiers, "the real OrderRepository is never used")
    _expect(
        _has_deprecation_assert(module),
        "no deprecation assertion (__doc__ or deprecated text)",
    )
    return True, ">=3 tests, both facade methods, real repository, deprecation assertion"


def _t23() -> tuple[bool, str]:
    """4 个测试文件：0 处 skip/xfail，每个至少 1 条 assert。"""
    problems: list[str] = []
    for rel in TEST_FILES:
        module = _parse_tree_file(rel)
        markers = _skip_markers(module)
        if markers:
            problems.append(rel + " -> " + ", ".join(markers[:2]))
        if _assert_count(module) < 1:
            problems.append(rel + ": no assert")
    _expect(not problems, "; ".join(problems[:6]))
    return True, "4/4 test files: no skip markers, at least one assert each"


def _t24() -> tuple[bool, str]:
    """7 个冻结文件逐字节不变。"""
    assert TREE is not None
    problems: list[str] = []
    for rel, expected in sorted(FROZEN_BASELINE.items()):
        path = TREE / rel
        if not path.is_file():
            problems.append(rel + " missing")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            problems.append(rel + " changed")
    _expect(not problems, "frozen files: " + "; ".join(problems[:6]))
    return True, "7/7 frozen baseline files are byte-identical"


def _t25() -> tuple[bool, str]:
    """树内文件集恰为 17 个期望路径：无多余、无缺失。"""
    files = set(_tree_files())
    extra = sorted(files - EXPECTED_PATHS)
    missing = sorted(EXPECTED_PATHS - files)
    problems: list[str] = []
    if extra:
        problems.append("extra: " + ", ".join(extra[:6]))
    if missing:
        problems.append("missing: " + ", ".join(missing[:6]))
    _expect(not problems, "; ".join(problems))
    return True, str(len(files)) + " files, exactly the 14 baseline + 3 new paths"


def _section_bodies(text: str) -> dict[str, str]:
    """把 markdown 按给定的二级标题切段（到下一个二级标题为止）。"""
    bodies: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in DOC_HEADINGS:
            current = stripped
            bodies[current] = []
            continue
        if current is not None and stripped.startswith("## "):
            current = None
            continue
        if current is not None:
            bodies[current].append(line)
    return {heading: "\n".join(body).strip() for heading, body in bodies.items()}


def _t26() -> tuple[bool, str]:
    """docs/api.md 的标题与词；README.md 的结构表行与链接。"""
    text = _read_text("docs/api.md")
    bodies = _section_bodies(text)
    missing = [heading for heading in DOC_HEADINGS if heading not in bodies]
    _expect(not missing, "missing headings: " + ", ".join(missing))
    empty = [heading for heading in DOC_HEADINGS if not bodies[heading]]
    _expect(not empty, "empty sections: " + ", ".join(empty))
    words = [
        word for word in ("insert", "listing", "add", "list_all", "v2.0") if word not in text
    ]
    _expect(not words, "docs/api.md lacks: " + ", ".join(words))
    example = bodies["## 迁移示例"]
    _expect(FENCE in example, "## 迁移示例 has no fenced code block")
    _expect("OrderApi" in example, "## 迁移示例 never mentions OrderApi")
    _expect("add(" in example, "## 迁移示例 never shows add(")
    _expect("list_all(" in example, "## 迁移示例 never shows list_all(")
    readme = _read_text("README.md")
    rows = [
        line
        for line in readme.splitlines()
        if line.lstrip().startswith("|")
        and "src/shop/order_api.py" in line
        and line.count("|") >= 2
    ]
    _expect(rows, "README.md has no structure-table row for src/shop/order_api.py")
    _expect(
        re.search(r"\]\([^)]*docs/api\.md\)", readme) is not None,
        "README.md does not link docs/api.md",
    )
    return True, "docs/api.md 3 sections + 5 tokens + example; README row + link"


# ---------------------------------------------------------------------------
# 6 EN 组：树副本里真跑命令（EN1-EN4）
# ---------------------------------------------------------------------------
def _en1() -> tuple[bool, str]:
    """整树 pytest 退出 0。"""
    result = _whole_pytest()
    _expect(
        result.returncode == 0,
        "pytest exit=" + str(result.returncode) + " tail=" + _tail(result.stdout),
    )
    return True, "pytest exit=0"


def _en2() -> tuple[bool, str]:
    """收集数 >= 4（基线 3 + 门面测试 >=1）。"""
    collected = _collected_count()
    _expect(
        collected >= COLLECTED_MIN,
        "collected=" + str(collected) + " < " + str(COLLECTED_MIN),
    )
    return True, "collected=" + str(collected) + " >= " + str(COLLECTED_MIN)


def _en3() -> tuple[bool, str]:
    """三个既有测试文件的定向回归退出 0。"""
    result = _pytest(_shared_copy(), list(EXISTING_TEST_FILES))
    _expect(
        result.returncode == 0,
        "pytest exit=" + str(result.returncode) + " tail=" + _tail(result.stdout),
    )
    return True, "targeted regression on the 3 existing test files exits 0"


def _en4() -> tuple[bool, str]:
    """同一棵树两次 pytest 输出（脱敏后）逐字节相同。"""
    first = _whole_pytest()
    second = _pytest(_shared_copy(), [])
    _expect(first.returncode == 0, "pytest exit=" + str(first.returncode))
    _expect(second.returncode == 0, "pytest exit=" + str(second.returncode))
    left = _scrub(first.stdout + first.stderr)
    right = _scrub(second.stdout + second.stderr)
    _expect(left == right, "two pytest runs produced different output")
    return True, "two runs produce byte-identical output after path/duration scrubbing"


# ---------------------------------------------------------------------------
# 7 I 组：签名与公开面（I1-I4）
# ---------------------------------------------------------------------------
def _parameters(function) -> list[inspect.Parameter]:
    """function 去掉 self 之后的参数表。"""
    return list(inspect.signature(function).parameters.values())[1:]


def _i1() -> tuple[bool, str]:
    """OrderRepository.add(self, payload) / list_all(self) 的签名与返回形。"""
    module = _parse_tree_file("src/shop/order_repository.py")
    add = _class_function(module, "OrderRepository", "add")
    list_all = _class_function(module, "OrderRepository", "list_all")
    _expect(add is not None, "OrderRepository.add is missing")
    _expect(list_all is not None, "OrderRepository.list_all is missing")
    _expect(
        [argument.arg for argument in add.args.args] == ["self", "payload"],
        "add parameters = " + repr([argument.arg for argument in add.args.args]),
    )
    _expect(not add.args.defaults and not add.args.kw_defaults, "add has default values")
    _expect(add.returns is not None, "add has no return annotation")
    _expect("dict" in ast.unparse(add.returns), "add returns " + ast.unparse(add.returns))
    _expect(
        [argument.arg for argument in list_all.args.args] == ["self"],
        "list_all parameters = " + repr([argument.arg for argument in list_all.args.args]),
    )
    _expect(
        not list_all.args.defaults and not list_all.args.kw_defaults,
        "list_all has default values",
    )
    _expect(list_all.returns is not None, "list_all has no return annotation")
    _expect(
        "list" in ast.unparse(list_all.returns),
        "list_all returns " + ast.unparse(list_all.returns),
    )
    repository = _repository()()
    _expect(isinstance(repository.add({"id": 1}), dict), "add() did not return a dict")
    _expect(isinstance(repository.list_all(), list), "list_all() did not return a list")
    return True, "add(self, payload)->dict, list_all(self)->list"


def _i2() -> tuple[bool, str]:
    """OrderApi.__init__(self, repository) 恰一个必填位置参数。"""
    api_class = _api_class()
    parameters = _parameters(api_class.__init__)
    _expect(
        [parameter.name for parameter in parameters] == ["repository"],
        "signature = " + repr([parameter.name for parameter in parameters]),
    )
    _expect(parameters[0].default is inspect.Parameter.empty, "repository has a default value")
    _expect(
        parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD,
        "repository kind = " + str(parameters[0].kind),
    )
    try:
        api_class()
    except TypeError:
        pass
    else:
        raise AssertionError("OrderApi() without a repository was accepted")
    return True, "OrderApi(repository) takes one required positional repository"


def _i3() -> tuple[bool, str]:
    """OrderApi.insert(self, payload) / listing(self) 的签名与返回注解。"""
    module = _parse_tree_file("src/shop/order_api.py")
    insert = _class_function(module, "OrderApi", "insert")
    listing = _class_function(module, "OrderApi", "listing")
    _expect(insert is not None, "OrderApi.insert is missing")
    _expect(listing is not None, "OrderApi.listing is missing")
    _expect(
        [argument.arg for argument in insert.args.args] == ["self", "payload"],
        "insert parameters = " + repr([argument.arg for argument in insert.args.args]),
    )
    _expect(not insert.args.defaults and not insert.args.kw_defaults, "insert has default values")
    _expect(insert.returns is not None, "insert has no return annotation")
    _expect(
        "dict" in ast.unparse(insert.returns),
        "insert returns " + ast.unparse(insert.returns),
    )
    _expect(
        [argument.arg for argument in listing.args.args] == ["self"],
        "listing parameters = " + repr([argument.arg for argument in listing.args.args]),
    )
    _expect(
        not listing.args.defaults and not listing.args.kw_defaults,
        "listing has default values",
    )
    _expect(listing.returns is not None, "listing has no return annotation")
    _expect(
        "list" in ast.unparse(listing.returns),
        "listing returns " + ast.unparse(listing.returns),
    )
    return True, "insert(self, payload)->dict, listing(self)->list"


def _i4() -> tuple[bool, str]:
    """service / controller：create + list_all 在、旧名不在、构造器保持基线形态。"""
    pairs = [
        (_tree_module("shop.order_service").OrderService, "OrderService", "repository"),
        (_tree_module("shop.order_controller").OrderController, "OrderController", "service"),
    ]
    for cls, label, constructor_name in pairs:
        _expect(callable(getattr(cls, "create", None)), label + ".create is missing")
        _expect(callable(getattr(cls, "list_all", None)), label + ".list_all is missing")
        _expect(not hasattr(cls, "insert"), label + ".insert still exists")
        _expect(not hasattr(cls, "listing"), label + ".listing still exists")
        constructor = _parameters(cls.__init__)
        _expect(
            [parameter.name for parameter in constructor] == [constructor_name],
            label
            + " constructor parameters = "
            + repr([parameter.name for parameter in constructor]),
        )
        _expect(constructor[0].default is None, label + " constructor default is not None")
        create = _parameters(cls.create)
        _expect(
            [parameter.name for parameter in create] == ["payload"],
            label + ".create parameters = " + repr([parameter.name for parameter in create]),
        )
        _expect(
            create[0].default is inspect.Parameter.empty,
            label + ".create payload has a default",
        )
    return True, "service and controller keep create + list_all and drop the old names"


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
    ("I1", _i1),
    ("I2", _i2),
    ("I3", _i3),
    ("I4", _i4),
]


def _run_case(case_id: str, func) -> dict:
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


def _cannot_run(message: str) -> int:
    """跑不成（2）：stdout 不出载荷，原因写 stderr 一行。"""
    sys.stderr.write("runner: cannot run: " + message + "\n")
    return 2


def main() -> int:
    """入口：读 BANK_TASK_TREE，跑 34 条，打印唯一 JSON 载荷。"""
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

    if [case_id for case_id, _func in CASES] != CASE_IDS:
        return _cannot_run("case registry is not T01..T26 / EN1..EN4 / I1..I4")

    try:
        _shared_copy()
        _temp_root()
    except (OSError, RuntimeError) as exc:
        return _cannot_run("cannot copy the evaluated tree: " + type(exc).__name__)

    cases: list[dict] = []
    swallowed = io.StringIO()
    with contextlib.redirect_stdout(swallowed):
        for case_id, func in CASES:
            cases.append(_run_case(case_id, func))

    passed = sum(1 for case in cases if case["pass"])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "tree": _tree_label(raw),
        "cases": cases,
        "summary": {"passed": passed, "total": len(cases)},
    }
    sys.stdout.write(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
