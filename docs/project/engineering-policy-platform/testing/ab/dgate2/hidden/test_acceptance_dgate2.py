"""D 门 2 T 维度隐藏验收：30 条（t01-t30）。

出题依据（独立出题；写用例时未读任何被评实现）：
- examples/dsh/b-plan/a3-task-v3/task-package/{first-message,acceptance,interfaces,milestones}.md
- examples/dsh/b-plan/a3-task-v3/README.md
- docs/project/engineering-policy-platform/readings/2026-10-19-D-gate2-treatment.md §4.3.1

30 条的分配（§4.3.1）：A1×4、A2×4、A3×3、A4×4、A5×6、A6×3、A7×3、A8×3。
其中 A5 的 6 条 = 原 5 条里「只持有 service」拆成「构造签名单参」+「无 repository 属性」；
A6 的 3 条 = 原 2 条里「collected >= 基线+3」拆出「无新增 skip/xfail」。

运行方式（树根只从环境变量取，不写死绝对路径）：

    POLICY_TREE=<final-tree> python -m pytest -q test_acceptance_dgate2.py

纪律：
- 只读被评树；需要执行 pytest / demo 时在树副本（系统 temp，用完即删）上跑；
- 全部用例只依赖最终树；基线常量来自 v3 任务包构造（12 文件基线），
  按相对路径排序的清单文本摘要 = 4e7c4073...，与 task-package/README.md §1 逐字节一致。
"""
from __future__ import annotations

import ast
import atexit
import hashlib
import importlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

_TREE_ENV = "POLICY_TREE"
_TREE_RAW = os.environ.get(_TREE_ENV)
if not _TREE_RAW:
    pytest.exit(
        _TREE_ENV + " is not set: pass the final tree root via the environment",
        returncode=2,
    )

TREE = Path(_TREE_RAW).resolve()
if not TREE.is_dir():
    pytest.exit(_TREE_ENV + " does not point to a directory: " + _TREE_RAW, returncode=2)

# ---------------------------------------------------------------------------
# 基线常量（v3 任务包构造：sample-project 11 文件 + tools/__init__.py）
# ---------------------------------------------------------------------------
BASELINE_COLLECTED = 3
COLLECTED_THRESHOLD = BASELINE_COLLECTED + 3

BASELINE_FILES = (
    "AGENTS.md",
    "README.md",
    "conftest.py",
    "pytest.ini",
    "src/shop/__init__.py",
    "src/shop/order_controller.py",
    "src/shop/order_repository.py",
    "src/shop/order_service.py",
    "tests/test_order_controller.py",
    "tests/test_order_repository.py",
    "tests/test_order_service.py",
    "tools/__init__.py",
)

# task-package/allowed-writes.txt（9 路径，字母序）
ALLOWED_WRITES = (
    "README.md",
    "src/shop/order_audit.py",
    "src/shop/order_controller.py",
    "src/shop/order_service.py",
    "tests/test_audit_demo.py",
    "tests/test_order_audit.py",
    "tests/test_order_controller.py",
    "tests/test_order_service.py",
    "tools/audit_demo.py",
)

# 基线 12 文件里**不在**允许写集合中的 7 个：它们必须逐字节不变（A8 的「改动集合」口径）。
FROZEN_BASELINE_SHA256 = {
    "AGENTS.md": "ef20cdca0d6c43dbb5038449c90a972d44837e4b9ddc17e074f994d5eed669a3",
    "conftest.py": "edd7cea37c657fb322cdee3038ca9aed35f40c7657a0faacb6640d6de9b050e7",
    "pytest.ini": "fd1c0f9fadf99a0af117f9f17fd7276f06d577e80fd530652978a1ff54aa71cc",
    "src/shop/__init__.py": "d7eef7b6e4db6622675782550c664ef2ef3c2ff9e8de8845cc0e9f4af4b44ad1",
    "src/shop/order_repository.py": (
        "4d4b685f7ce3bbd729a9004b5f20ce0e77701d1be3d514788272398b4b90f054"
    ),
    "tests/test_order_repository.py": (
        "61e6c0d31b70c3d93b4848e7352816ce2a8ff71a07e509dd9afd0376f977f20c"
    ),
    "tools/__init__.py": "f66ec0041ebb636c9fdee98ff706cda2ef04ca40474f79b84027e1e0cb3618eb",
}

SKIP_XFAIL_NAMES = frozenset({"skip", "skipif", "skipIf", "xfail"})


# ---------------------------------------------------------------------------
# 树读取 / 副本执行（被评树只读）
# ---------------------------------------------------------------------------
def _read_tree_text(rel: str) -> str:
    """按仓库相对路径读被评树里的 UTF-8 文本。"""
    return (TREE / rel).read_text(encoding="utf-8")


def _scrub(text: str) -> str:
    """把绝对路径替换成占位符：失败信息里不出现绝对路径。"""
    cleaned = str(text)
    for base in (str(TREE), str(_COPY_HOLDER) if _COPY_HOLDER else ""):
        if base:
            cleaned = cleaned.replace(base, "<tree>")
    return cleaned


def _tail(text: str, limit: int = 240) -> str:
    """取最后一行非空输出（脱敏、截断），用于失败信息。"""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return _scrub(lines[-1])[:limit] if lines else ""


_COPY_HOLDER: Path | None = None
_COPY_TREE: Path | None = None


def _ignore_artifacts(_directory: str, names: list[str]) -> set[str]:
    """副本里不带走缓存、隐藏目录与 pyc（避免把历史产物当成输入）。"""
    ignored = set()
    for name in names:
        if name.startswith(".") or name == "__pycache__" or name.endswith(".pyc"):
            ignored.add(name)
    return ignored


def _runtime_parent() -> Path:
    """临时副本的父目录：优先 DGATE2_TMPDIR；系统 temp 落在 cwd 时退到 .tmp/。"""
    override = os.environ.get("DGATE2_TMPDIR")
    if override:
        base = Path(override)
    else:
        base = Path(tempfile.gettempdir())
        if base.resolve() == Path.cwd().resolve():
            base = Path.cwd() / ".tmp" / "dgate2"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = Path(tempfile.gettempdir())
        base.mkdir(parents=True, exist_ok=True)
    return base


def _tree_copy() -> Path:
    """被评树的只读副本；pytest / demo 都在副本里跑，不往被评树写缓存。"""
    global _COPY_HOLDER, _COPY_TREE
    if _COPY_TREE is None or not _COPY_TREE.is_dir():
        _COPY_HOLDER = Path(
            tempfile.mkdtemp(prefix="acceptance-", dir=str(_runtime_parent()))
        )
        atexit.register(shutil.rmtree, _COPY_HOLDER, ignore_errors=True)
        target = _COPY_HOLDER / "tree"
        shutil.copytree(TREE, target, ignore=_ignore_artifacts)
        _COPY_TREE = target
    return _COPY_TREE


def _run_in_copy(args: list[str]) -> subprocess.CompletedProcess[str]:
    """在树副本里跑子进程：隔离环境变量、60 秒超时、不写 pyc。"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("PYTHONPATH", None)
    env.pop("PYTEST_ADDOPTS", None)
    return subprocess.run(
        args,
        cwd=str(_tree_copy()),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


_RESULTS: dict[str, subprocess.CompletedProcess[str]] = {}


def _cached(key: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    if key not in _RESULTS:
        _RESULTS[key] = _run_in_copy(args)
    return _RESULTS[key]


def _pytest_run() -> subprocess.CompletedProcess[str]:
    return _cached(
        "pytest",
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
    )


def _collect_run() -> subprocess.CompletedProcess[str]:
    return _cached(
        "collect",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--collect-only",
            "-p",
            "no:cacheprovider",
        ],
    )


def _demo_run() -> subprocess.CompletedProcess[str]:
    return _cached("demo", [sys.executable, "tools/audit_demo.py"])


def _collected_count() -> int:
    result = _collect_run()
    if result.returncode != 0:
        raise AssertionError("collect-only exit=" + str(result.returncode))
    match = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
    if match:
        return int(match.group(1))
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


# ---------------------------------------------------------------------------
# 被测对象与替身
# ---------------------------------------------------------------------------
def _import_module(name: str):
    src = str(TREE / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    return importlib.import_module(name)


def _order_audit_cls():
    return _import_module("shop.order_audit").OrderAudit


def _order_service_cls():
    return _import_module("shop.order_service").OrderService


def _order_controller_cls():
    return _import_module("shop.order_controller").OrderController


class _FakeRepository:
    """OrderRepository 的替身：记录每次写入并按需返回固定副本。"""

    def __init__(self, return_value: dict | None = None) -> None:
        self.inserted: list[dict] = []
        self._return_value = return_value

    def insert(self, payload: dict) -> dict:
        self.inserted.append(dict(payload))
        if self._return_value is None:
            return dict(payload)
        return dict(self._return_value)

    def listing(self) -> list[dict]:
        return [dict(row) for row in self.inserted]


class _FakeAudit:
    """OrderAudit 的替身：记录 (action, order_id) 并回放 entries。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, int]] = []

    def record(self, action: str, order_id: int) -> dict:
        self.records.append((action, order_id))
        return {"action": action, "order_id": order_id}

    def entries(self) -> list[dict]:
        return [
            {"action": action, "order_id": order_id}
            for action, order_id in self.records
        ]


class _FakeService:
    """OrderService 的替身：记录 create 的载荷，并回放固定的 audit_entries。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.entries_sentinel: list[dict] = [{"action": "create", "order_id": 1}]

    def create(self, payload: dict) -> dict:
        self.calls.append(dict(payload))
        return dict(payload)

    def audit_entries(self) -> list[dict]:
        return list(self.entries_sentinel)


# ---------------------------------------------------------------------------
# AST / 目录 / 哈希辅助
# ---------------------------------------------------------------------------
def _imports_module(tree: ast.Module, dotted: str) -> bool:
    """AST 里是否出现对 dotted 模块（或它的子模块）的 import。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == dotted or alias.name.startswith(dotted + "."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                if any(alias.name == "order_repository" for alias in node.names):
                    return True
                continue
            if module == dotted or module.startswith(dotted + "."):
                return True
            if module == "shop" and any(
                alias.name == "order_repository" for alias in node.names
            ):
                return True
    return False


def _references_attribute(tree: ast.Module, attribute: str) -> bool:
    """AST 里是否出现对某属性的直接引用（如 shop.order_repository）。"""
    return any(
        isinstance(node, ast.Attribute) and node.attr == attribute
        for node in ast.walk(tree)
    )


def _calls_constructor(tree: ast.Module, name: str) -> bool:
    """AST 里是否出现对 name 的调用（Name 或属性形式）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name:
            return True
    return False


def _tree_inventory() -> list[str]:
    """树内文件清单（仓库相对、/ 分隔；跳过隐藏目录、__pycache__ 与 pyc）。"""
    files: list[str] = []
    for root, dirnames, filenames in os.walk(TREE):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".") and name != "__pycache__"
        )
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            files.append((Path(root) / name).relative_to(TREE).as_posix())
    return sorted(files)


def _controller_tree() -> ast.Module:
    return ast.parse(_read_tree_text("src/shop/order_controller.py"))


def _sha256_of(rel: str) -> str:
    return hashlib.sha256((TREE / rel).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# A1：create 返回副本 + 审计条目精确（4 条）
# ---------------------------------------------------------------------------
def test_t01_create_returns_equal_order_copy() -> None:
    """A1-1：create 返回与输入内容相等的订单 dict。"""
    service = _order_service_cls()()
    result = service.create({"id": 1})
    assert isinstance(result, dict), "create returned " + type(result).__name__
    assert result == {"id": 1}, "create returned " + repr(result)


def test_t02_create_returns_copy_and_keeps_payload() -> None:
    """A1-2：输入 payload 不被改；改返回值不影响已存订单（返回的是副本）。"""
    payload = {"id": 1}
    service = _order_service_cls()()
    result = service.create(payload)
    assert payload == {"id": 1}, "create mutated the payload: " + repr(payload)
    result["id"] = 99
    assert service.listing() == [{"id": 1}], "stored order changed with the result"


def test_t03_audit_entries_exact_after_one_create() -> None:
    """A1-3：create 之后 audit_entries() 精确等于一条 create 记录。"""
    service = _order_service_cls()()
    service.create({"id": 1})
    assert service.audit_entries() == [
        {"action": "create", "order_id": 1}
    ], "audit_entries=" + repr(service.audit_entries())


def test_t04_create_has_no_extra_side_effects() -> None:
    """A1-4：一次 create 只写入一行、只记一条；读 audit_entries 不再产生记录。"""
    service = _order_service_cls()()
    service.create({"id": 1})
    assert service.listing() == [{"id": 1}], "listing=" + repr(service.listing())
    first = service.audit_entries()
    second = service.audit_entries()
    assert first == [{"action": "create", "order_id": 1}], "audit=" + repr(first)
    assert second == first, "audit_entries called twice differs: " + repr(second)


# ---------------------------------------------------------------------------
# A2：双注入都生效（4 条）
# ---------------------------------------------------------------------------
def test_t05_injected_repository_receives_write() -> None:
    """A2-1：注入的 repository 收到 create 的写入。"""
    repository = _FakeRepository()
    audit = _FakeAudit()
    service = _order_service_cls()(repository=repository, audit=audit)
    service.create({"id": 3})
    assert repository.inserted == [{"id": 3}], "repo=" + repr(repository.inserted)


def test_t06_injected_audit_receives_record() -> None:
    """A2-2：注入的 audit 收到 ("create", id) 记录。"""
    repository = _FakeRepository()
    audit = _FakeAudit()
    service = _order_service_cls()(repository=repository, audit=audit)
    service.create({"id": 3})
    assert audit.records == [("create", 3)], "records=" + repr(audit.records)


def test_t07_audit_order_id_follows_payload_id() -> None:
    """A2-3：order_id 从本次 payload 的 id 传播（不是写死的 1）。"""
    repository = _FakeRepository()
    audit = _FakeAudit()
    service = _order_service_cls()(repository=repository, audit=audit)
    service.create({"id": 7})
    assert repository.inserted == [{"id": 7}], "repo=" + repr(repository.inserted)
    assert audit.records == [("create", 7)], "records=" + repr(audit.records)


def test_t08_create_returns_repository_result() -> None:
    """A2-4：create 的返回值等于 repository 写入的返回值。"""
    returned = {"id": 5, "extra": "from-repo"}
    repository = _FakeRepository(return_value=returned)
    audit = _FakeAudit()
    service = _order_service_cls()(repository=repository, audit=audit)
    result = service.create({"id": 5})
    assert result == returned, "create returned " + repr(result)
    assert repository.inserted == [{"id": 5}], "repo=" + repr(repository.inserted)


# ---------------------------------------------------------------------------
# A3：只注入 audit（3 条）
# ---------------------------------------------------------------------------
def test_t09_default_repository_survives_audit_only() -> None:
    """A3-1：只注入 audit 时默认 repository 仍生效（listing 看得到写入）。"""
    service = _order_service_cls()(audit=_FakeAudit())
    service.create({"id": 2})
    assert service.listing() == [{"id": 2}], "listing=" + repr(service.listing())


def test_t10_default_repository_accumulates_writes() -> None:
    """A3-2：只注入 audit 时两次 create 都写进默认 repository。"""
    service = _order_service_cls()(audit=_FakeAudit())
    service.create({"id": 2})
    service.create({"id": 3})
    listing = service.listing()
    assert listing == [{"id": 2}, {"id": 3}], "listing=" + repr(listing)


def test_t11_audit_only_injection_records_create() -> None:
    """A3-3：只注入 audit 时 create 仍产出精确的审计记录。"""
    audit = _FakeAudit()
    service = _order_service_cls()(audit=audit)
    service.create({"id": 2})
    assert audit.records == [("create", 2)], "records=" + repr(audit.records)
    assert service.audit_entries() == [
        {"action": "create", "order_id": 2}
    ], "audit_entries=" + repr(service.audit_entries())


# ---------------------------------------------------------------------------
# A4：entries / record 返回副本（4 条）
# ---------------------------------------------------------------------------
def test_t12_entries_returns_list_copy() -> None:
    """A4-1：改 entries() 返回的列表不影响内部。"""
    audit = _order_audit_cls()()
    audit.record("create", 1)
    returned = audit.entries()
    assert isinstance(returned, list), "entries returned " + type(returned).__name__
    returned.append({"action": "hack", "order_id": 99})
    returned.clear()
    assert audit.entries() == [
        {"action": "create", "order_id": 1}
    ], "entries not isolated: " + repr(audit.entries())


def test_t13_entries_and_record_return_dict_copies() -> None:
    """A4-2：改 entries()/record() 返回的 dict 不影响内部。"""
    audit = _order_audit_cls()()
    audit.record("create", 1)
    entries = audit.entries()
    entries[0]["order_id"] = 99
    assert audit.entries() == [
        {"action": "create", "order_id": 1}
    ], "entries not isolated: " + repr(audit.entries())
    recorded = audit.record("delete", 2)
    assert isinstance(recorded, dict), "record returned " + type(recorded).__name__
    recorded["order_id"] = 99
    assert audit.entries()[-1] == {
        "action": "delete",
        "order_id": 2,
    }, "record not isolated: " + repr(audit.entries())


def test_t14_two_entries_calls_are_independent() -> None:
    """A4-3：两次 entries() 互不影响（不是同一个列表）。"""
    audit = _order_audit_cls()()
    audit.record("create", 1)
    first = audit.entries()
    second = audit.entries()
    assert first is not second, "entries() returned the same list object twice"
    first.clear()
    assert second == [{"action": "create", "order_id": 1}], "second=" + repr(second)
    assert audit.entries() == [
        {"action": "create", "order_id": 1}
    ], "internal state changed: " + repr(audit.entries())


def test_t15_internal_count_and_contents_are_correct() -> None:
    """A4-4：内部计数正确（追加两条、内容与顺序精确）。"""
    audit = _order_audit_cls()()
    first = audit.record("create", 1)
    second = audit.record("delete", 2)
    assert first == {"action": "create", "order_id": 1}, "first=" + repr(first)
    assert second == {"action": "delete", "order_id": 2}, "second=" + repr(second)
    assert audit.entries() == [
        {"action": "create", "order_id": 1},
        {"action": "delete", "order_id": 2},
    ], "entries=" + repr(audit.entries())


# ---------------------------------------------------------------------------
# A5：controller 只转发 + 不 import repository（6 条）
# ---------------------------------------------------------------------------
def test_t16_controller_create_forwards() -> None:
    """A5-1：controller.create 只转发给 service（载荷与返回值都经 service）。"""
    service = _FakeService()
    controller = _order_controller_cls()(service)
    result = controller.create({"id": 4})
    assert service.calls == [{"id": 4}], "service calls=" + repr(service.calls)
    assert result == {"id": 4}, "controller returned " + repr(result)


def test_t17_controller_audit_entries_forwards() -> None:
    """A5-2：controller.audit_entries 只转发给 service.audit_entries。"""
    service = _FakeService()
    controller = _order_controller_cls()(service)
    assert controller.audit_entries() == [
        {"action": "create", "order_id": 1}
    ], "audit_entries=" + repr(controller.audit_entries())


def test_t18_controller_does_not_import_order_repository() -> None:
    """A5-3：AST 无 shop.order_repository 的 import / 属性引用。"""
    tree = _controller_tree()
    assert not _imports_module(tree, "shop.order_repository"), (
        "controller imports shop.order_repository"
    )
    assert not _references_attribute(tree, "order_repository"), (
        "controller references order_repository"
    )


def test_t19_controller_does_not_instantiate_repository() -> None:
    """A5-4：AST 不实例化 OrderRepository。"""
    tree = _controller_tree()
    assert not _calls_constructor(tree, "OrderRepository"), (
        "controller instantiates OrderRepository"
    )


def test_t20_controller_constructor_takes_one_parameter() -> None:
    """A5-5：controller 构造签名只有一个参数（默认 None，依赖由外部注入）。"""
    parameters = list(inspect.signature(_order_controller_cls()).parameters.values())
    names = [parameter.name for parameter in parameters]
    assert len(parameters) == 1, "controller __init__ parameters: " + repr(names)
    assert parameters[0].default is None, "controller __init__ default is not None"


def test_t21_controller_holds_only_service() -> None:
    """A5-6：controller 实例只持有注入的 service，没有 repository 属性。"""
    service = _FakeService()
    controller = _order_controller_cls()(service)
    attributes = dict(vars(controller))
    assert len(attributes) == 1, "controller holds attributes: " + repr(
        sorted(attributes)
    )
    assert not any("repo" in name.lower() for name in attributes), (
        "controller holds a repository-ish attribute: " + repr(sorted(attributes))
    )
    (value,) = attributes.values()
    assert value is service, "controller does not hold the injected service"


# ---------------------------------------------------------------------------
# A6：pytest 全绿（3 条）
# ---------------------------------------------------------------------------
def test_t22_pytest_exit_zero() -> None:
    """A6-1：项目根 python -m pytest -q 退出码 0。"""
    result = _pytest_run()
    assert result.returncode == 0, (
        "pytest exit=" + str(result.returncode) + " tail=" + _tail(result.stdout)
    )


def test_t23_collected_at_least_baseline_plus_three() -> None:
    """A6-2：收集数 >= 基线 3 + 3（新测试确实被收集）。"""
    count = _collected_count()
    assert count >= COLLECTED_THRESHOLD, (
        "collected=" + str(count) + " < " + str(COLLECTED_THRESHOLD)
    )


def test_t24_no_new_skip_or_xfail() -> None:
    """A6-3：tests/ 里没有新增 skip/xfail（不靠跳过测试变绿）。"""
    tests_dir = TREE / "tests"
    assert tests_dir.is_dir(), "tests/ directory is missing"
    offenders: list[str] = []
    for path in sorted(tests_dir.rglob("*.py")):
        rel = path.relative_to(TREE).as_posix()
        try:
            parsed = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            raise AssertionError("test file is not parseable: " + rel) from None
        for node in ast.walk(parsed):
            if isinstance(node, ast.Attribute) and node.attr in SKIP_XFAIL_NAMES:
                offenders.append(rel + ":" + str(getattr(node, "lineno", "?")))
                continue
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in SKIP_XFAIL_NAMES:
                    offenders.append(rel + ":" + str(getattr(node, "lineno", "?")))
    assert not offenders, "skip/xfail markers found: " + repr(offenders[:5])


# ---------------------------------------------------------------------------
# A7：demo 契约（3 条）
# ---------------------------------------------------------------------------
def test_t25_demo_exit_zero() -> None:
    """A7-1：python tools/audit_demo.py 退出码 0。"""
    result = _demo_run()
    assert result.returncode == 0, (
        "demo exit=" + str(result.returncode) + " tail=" + _tail(result.stderr)
    )


def test_t26_demo_stdout_is_json_array() -> None:
    """A7-2：stdout 是合法 JSON 数组。"""
    result = _demo_run()
    assert result.returncode == 0, "demo exit=" + str(result.returncode)
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "stdout is not valid JSON: " + _scrub(str(exc)) + " tail=" + _tail(result.stdout)
        ) from None
    assert isinstance(payload, list), "stdout JSON is " + type(payload).__name__


def test_t27_demo_returns_exactly_two_records() -> None:
    """A7-3：stdout 恰两条 create 记录且内容精确。"""
    result = _demo_run()
    assert result.returncode == 0, "demo exit=" + str(result.returncode)
    payload = json.loads(result.stdout.strip())
    expected = [
        {"action": "create", "order_id": 1},
        {"action": "create", "order_id": 2},
    ]
    assert payload == expected, "demo stdout=" + repr(payload)


# ---------------------------------------------------------------------------
# A8：改动集合（3 条；v3 口径 = allowed-writes 9 路径）
# ---------------------------------------------------------------------------
def test_t28_frozen_baseline_files_unchanged() -> None:
    """A8-1：不在允许写集合里的 7 个基线文件逐字节不变。"""
    changed: list[str] = []
    missing: list[str] = []
    for rel, expected in FROZEN_BASELINE_SHA256.items():
        path = TREE / rel
        if not path.is_file():
            missing.append(rel)
            continue
        if _sha256_of(rel) != expected:
            changed.append(rel)
    assert not missing, "frozen baseline files are missing: " + repr(missing)
    assert not changed, "files outside allowed-writes were modified: " + repr(changed)


def test_t29_no_extra_files_beyond_baseline_and_allowed() -> None:
    """A8-2：树内没有 12 文件基线 + 9 条允许写之外的额外文件，且基线文件没被删。"""
    inventory = set(_tree_inventory())
    allowed = set(BASELINE_FILES) | set(ALLOWED_WRITES)
    extra = sorted(inventory - allowed)
    missing = sorted(set(BASELINE_FILES) - inventory)
    assert not extra, "extra files outside baseline+allowed: " + repr(extra[:5])
    assert not missing, "baseline files deleted: " + repr(missing[:5])


def test_t30_new_demo_and_contract_test_counted_as_changes() -> None:
    """A8-3：任务新建的 demo 与契约测试按改动计（存在、在允许集合内、路径唯一）。"""
    inventory = set(_tree_inventory())
    new_files = inventory - set(BASELINE_FILES)
    assert new_files <= set(ALLOWED_WRITES), "new files outside allowed: " + repr(
        sorted(new_files - set(ALLOWED_WRITES))
    )
    assert "tools/audit_demo.py" in inventory, "tools/audit_demo.py is missing"
    assert "tests/test_audit_demo.py" in inventory, "tests/test_audit_demo.py is missing"
    demos = sorted(path for path in inventory if Path(path).name == "audit_demo.py")
    assert demos == ["tools/audit_demo.py"], "audit_demo.py paths: " + repr(demos)
