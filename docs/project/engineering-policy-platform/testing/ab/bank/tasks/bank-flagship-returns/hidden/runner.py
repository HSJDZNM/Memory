"""bank-flagship-returns 隐藏验收 runner：T01-T38 + EN1-EN5 + I1-I5（48 条）。

用法::

    BANK_TASK_TREE=<被评树> python hidden/runner.py

契约（bank/README.md 4.3 与 hidden/PLAN.md 0）:

- 被评树只从环境变量 BANK_TASK_TREE 读入，**绝不写**：所有需要执行的动作（pytest / demo /
  migrate / 导入）都在树的副本里跑（临时目录，用完即删）；
- stdout 唯一载荷（UTF-8）::

      {"schema_version": "1.0", "tree": "<相对标签>",
       "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
       "summary": {"passed": 48, "total": 48}}

  载荷不含时戳 / run id / 绝对路径；同一棵树两次运行逐字节相同；
- 退出码：全过 0 / 有失败 1 / 跑不成 2（缺 BANK_TASK_TREE、树不存在、用例集合不完整、树复制不了）；
- 每条用例独立 try/except：一条异常只让该条 fail，detail = 异常类型 + 脱敏短消息；
- 反向用例（T04/T05/T07/T14/T16/T17/T31/T35/T38）断言的是「期望失败 / 期望拒绝」。
"""
from __future__ import annotations

import ast
import atexit
import contextlib
import dataclasses
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
COLLECTED_MIN = 10

CASE_IDS = (
    ["T%02d" % index for index in range(1, 39)]
    + ["EN1", "EN2", "EN3", "EN4", "EN5"]
    + ["I1", "I2", "I3", "I4", "I5"]
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
    "src/shop/__init__.py": (
        "d7eef7b6e4db6622675782550c664ef2ef3c2ff9e8de8845cc0e9f4af4b44ad1"
    ),
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

# 基线里允许改写的 3 个既有文件（allowed-writes 与 baseline 的交集）。
MODIFIABLE_BASELINE = frozenset(
    {"README.md", "src/shop/order_repository.py", "tests/test_order_repository.py"}
)

# 冻结文件 = 基线 14 - 可改写 3 = 11（T35 逐字节校验这 11 个）。
FROZEN_BASELINE = {
    path: digest for path, digest in BASELINE_SHA256.items()
    if path not in MODIFIABLE_BASELINE
}

# 任务新建的 16 个文件（14 基线 ∪ 16 = 30 文件；T36 用）。
NEW_PATHS = frozenset(
    {
        "data/refunds-v2.jsonl",
        "docs/refund.md",
        "src/shop/refund_controller.py",
        "src/shop/refund_model.py",
        "src/shop/refund_policy.py",
        "src/shop/refund_repository.py",
        "src/shop/refund_service.py",
        "tests/test_migrate_refunds.py",
        "tests/test_refund_controller.py",
        "tests/test_refund_demo.py",
        "tests/test_refund_model.py",
        "tests/test_refund_policy.py",
        "tests/test_refund_repository.py",
        "tests/test_refund_service.py",
        "tools/migrate_refunds.py",
        "tools/refund_demo.py",
    }
)

# 允许写 19 条 = 基线可改写 3 + 新建 16。
ALLOWED_WRITES = frozenset(MODIFIABLE_BASELINE) | NEW_PATHS

EXPECTED_PATHS = frozenset(BASELINE_SHA256) | NEW_PATHS

IGNORED_SEGMENTS = frozenset({".policy", "__pycache__", ".pytest_cache", ".ruff_cache"})

POLICY_BASE = {
    "version": 1,
    "currency": "CNY",
    "fee_bps": 250,
    "min_fee_cents": 0,
    "max_fee_cents": 500,
    "max_refund_ratio": 1.0,
}

RECORD_KEYS = [
    "refund_id",
    "order_id",
    "amount_cents",
    "fee_cents",
    "reason",
    "status",
    "idempotency_key",
]

T01_EXPECTED = {
    "schema_version": 2,
    "refund_id": 1,
    "order_id": 2,
    "amount_cents": 1000,
    "fee_cents": 25,
    "reason": "damaged",
    "status": "recorded",
    "idempotency_key": None,
}

DEMO_EXPECTED = [
    {
        "schema_version": 2,
        "refund_id": 1,
        "order_id": 1,
        "amount_cents": 1000,
        "fee_cents": 25,
        "reason": "damaged",
        "status": "recorded",
        "idempotency_key": "demo-1",
    },
    {
        "schema_version": 2,
        "refund_id": 2,
        "order_id": 2,
        "amount_cents": 500,
        "fee_cents": 12,
        "reason": "late",
        "status": "recorded",
        "idempotency_key": "demo-2",
    },
]

MIGRATED_EXPECTED = [
    {
        "schema_version": 2,
        "refund_id": 1,
        "order_id": 1,
        "amount_cents": 1000,
        "fee_cents": 0,
        "reason": "damaged",
        "status": "migrated",
        "idempotency_key": None,
    },
    {
        "schema_version": 2,
        "refund_id": 2,
        "order_id": 1,
        "amount_cents": 300,
        "fee_cents": 0,
        "reason": "wrong-size",
        "status": "migrated",
        "idempotency_key": None,
    },
    {
        "schema_version": 2,
        "refund_id": 3,
        "order_id": 2,
        "amount_cents": 500,
        "fee_cents": 0,
        "reason": "late-delivery",
        "status": "migrated",
        "idempotency_key": None,
    },
]

NEW_TEST_FILES = [
    "tests/test_migrate_refunds.py",
    "tests/test_refund_controller.py",
    "tests/test_refund_demo.py",
    "tests/test_refund_model.py",
    "tests/test_refund_policy.py",
    "tests/test_refund_repository.py",
    "tests/test_refund_service.py",
]

DOC_HEADINGS = ["## 模块", "## 数据形状", "## 迁移", "## 幂等", "## 命令"]

README_LITERALS = [
    "src/shop/refund_model.py",
    "src/shop/refund_policy.py",
    "src/shop/refund_repository.py",
    "src/shop/refund_service.py",
    "src/shop/refund_controller.py",
    "tools/refund_demo.py",
    "tools/migrate_refunds.py",
    "docs/refund.md",
]

SKIP_ATTRS = frozenset({"skip", "skipif", "xfail", "importorskip"})
CONSTRUCTOR_NAMES = frozenset({"OrderRepository", "RefundRepository"})
REPOSITORY_MODULES = frozenset({"shop.order_repository", "shop.refund_repository"})

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
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _temp_root() -> Path:
    """临时副本的父目录：优先 <cwd>/.tmp（工作区可写），退到树旁与系统 temp。

    任何候选都不得落在被评树内部（只读被评树）；每个候选都要**真写一次**才算可用：
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


def _new_copy(prefix: str) -> Path:
    """被评树的一个新副本；退出时整棵删掉。"""
    assert TREE is not None
    target = _holder(prefix) / "tree"
    shutil.copytree(TREE, target, ignore=_ignore_artifacts)
    return target


def _shared_copy() -> Path:
    """所有「只读执行」共用的一份副本（pytest / 导入 / demo 第一次）。"""
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
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return _scrub(lines[-1])[:limit] if lines else ""


# ---------------------------------------------------------------------------
# 树内读取 / 模块导入 / AST
# ---------------------------------------------------------------------------
def _read_text(rel: str) -> str:
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
    assert TREE is not None
    return ast.parse(_read_text(rel), filename=rel)


def _tree_files() -> list[str]:
    assert TREE is not None
    found: list[str] = []
    for path in TREE.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(TREE).parts
        if any(part in IGNORED_SEGMENTS for part in parts):
            continue
        if path.name.endswith(".pyc"):
            continue
        found.append("/".join(parts))
    return sorted(found)


def _imported_modules(module: ast.Module) -> set[str]:
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


def _constructor_calls(module: ast.Module, names: frozenset[str]) -> list[str]:
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


def _skip_markers(module: ast.Module) -> list[str]:
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


def _assert_count(module: ast.Module) -> int:
    return sum(1 for node in ast.walk(module) if isinstance(node, ast.Assert))


def _calls_get_method(module: ast.Module) -> bool:
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "get"
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# 断言小工具
# ---------------------------------------------------------------------------
def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_all(checks: list[tuple[str, bool]]) -> None:
    failures = [label for label, ok in checks if not ok]
    _expect(not failures, "failed: " + ", ".join(failures))


def _expect_value_error(action, label: str) -> None:
    """action() 必须抛 ValueError：不抛或抛别的异常都算失败。"""
    try:
        action()
    except ValueError:
        return
    except Exception as exc:  # noqa: BLE001 - 反向用例：别的异常形态也算失败
        raise AssertionError(
            label + ": raised " + type(exc).__name__ + " instead of ValueError"
        ) from exc
    raise AssertionError(label + ": was accepted")


def _polarity(passed: bool, detail: str) -> tuple[bool, str]:
    return passed, detail


# ---------------------------------------------------------------------------
# 1.1 记录模型（T01-T05）
# ---------------------------------------------------------------------------
def _record_class():
    return _tree_module("shop.refund_model").RefundRecord


def _t01() -> tuple[bool, str]:
    record = _record_class()(1, 2, 1000, 25, "damaged", "recorded", None)
    payload = record.to_dict()
    _expect(isinstance(payload, dict), "to_dict returned " + type(payload).__name__)
    _expect(len(payload) == 8, "to_dict has " + str(len(payload)) + " keys")
    _expect(payload.get("schema_version") == 2, "schema_version is not 2")
    _expect(
        payload == T01_EXPECTED,
        "to_dict = " + json.dumps(payload, ensure_ascii=False, sort_keys=True)[:240],
    )
    return _polarity(True, "8 keys, schema_version=2, values exact")


def _t02() -> tuple[bool, str]:
    record = _record_class()(1, 2, 1000, 25, "damaged", "recorded", None)
    first = record.to_dict()
    first["amount_cents"] = 1
    first["reason"] = "tampered"
    second = record.to_dict()
    _expect(record.to_dict() is not second, "to_dict returns the same object twice")
    _expect(second == T01_EXPECTED, "internal state changed after mutating to_dict()")
    try:
        record.amount_cents = 7
    except dataclasses.FrozenInstanceError:
        pass
    except Exception as exc:  # noqa: BLE001 - 冻结性必须由 frozen dataclass 保证
        raise AssertionError(
            "setattr raised " + type(exc).__name__ + " instead of FrozenInstanceError"
        ) from exc
    else:
        raise AssertionError("record is not frozen: amount_cents was assignable")
    _expect(record.amount_cents == 1000, "record.amount_cents changed")
    return _polarity(True, "returns a fresh dict, record stays frozen")


def _t03() -> tuple[bool, str]:
    record_cls = _record_class()
    record = record_cls(3, 4, 777, 19, "late", "recorded", "k-9")
    payload = record.to_dict()
    again = record_cls.from_dict(payload)
    _expect(isinstance(again, record_cls), "from_dict returned " + type(again).__name__)
    _expect(again == record, "round trip is not equal")
    _expect(again.to_dict() == payload, "second to_dict differs from the first")
    return _polarity(True, "from_dict(to_dict()) round trips without loss")


def _t04() -> tuple[bool, str]:
    record_cls = _record_class()
    good = dict(T01_EXPECTED)
    bad_payloads = [
        ("missing reason", {key: value for key, value in good.items() if key != "reason"}),
        ("extra key", {**good, "extra": 1}),
        ("schema_version=1", {**good, "schema_version": 1}),
        ("refund_id=True", {**good, "refund_id": True}),
        ("amount_cents=-1", {**good, "amount_cents": -1}),
        ("status empty", {**good, "status": ""}),
    ]
    for label, payload in bad_payloads:
        _expect_value_error(lambda payload=payload: record_cls.from_dict(payload), label)
    return _polarity(True, "6/6 malformed payloads raise ValueError")


def _t05() -> tuple[bool, str]:
    record_cls = _record_class()
    without = record_cls(1, 2, 1000, 25, "damaged", "recorded", None)
    _expect(without.to_dict()["idempotency_key"] is None, "None was not kept as None")
    with_key = record_cls(1, 2, 1000, 25, "damaged", "recorded", "k-1")
    _expect(
        with_key.to_dict()["idempotency_key"] == "k-1", "str idempotency_key not kept"
    )
    _expect_value_error(
        lambda: record_cls(1, 2, 1000, 25, "damaged", "recorded", 1), "idempotency_key=1"
    )
    return _polarity(True, "str or None accepted, int rejected")


# ---------------------------------------------------------------------------
# 1.2 策略（T06-T10）
# ---------------------------------------------------------------------------
def _policy_module():
    return _tree_module("shop.refund_policy")


def _policy_dict() -> dict:
    assert TREE is not None
    return _policy_module().load_policy(TREE / "config" / "refund_policy.yaml")


def _scratch_dir(prefix: str) -> Path:
    return _holder(prefix)


def _write_yaml(directory: Path, name: str, payload: object) -> Path:
    path = directory / name
    path.write_bytes(json.dumps(payload).encode("utf-8"))
    return path


def _t06() -> tuple[bool, str]:
    assert TREE is not None
    policy = _policy_module().load_policy(TREE / "config" / "refund_policy.yaml")
    _expect(isinstance(policy, dict), "load_policy returned " + type(policy).__name__)
    _expect(
        policy == POLICY_BASE,
        "policy = " + json.dumps(policy, ensure_ascii=False, sort_keys=True)[:240],
    )
    return _polarity(True, "base policy read with the 6 documented keys")


def _t07() -> tuple[bool, str]:
    load_policy = _policy_module().load_policy
    directory = _scratch_dir("bad-policy")
    cases = [
        ("extra key", {**POLICY_BASE, "fee_bps_max": 1}),
        (
            "missing key",
            {key: value for key, value in POLICY_BASE.items() if key != "currency"},
        ),
        ("fee_bps as str", {**POLICY_BASE, "fee_bps": "250"}),
        ("max_refund_ratio=0", {**POLICY_BASE, "max_refund_ratio": 0}),
        ("min_fee > max_fee", {**POLICY_BASE, "min_fee_cents": 600, "max_fee_cents": 500}),
    ]
    for index, (label, payload) in enumerate(cases):
        path = _write_yaml(directory, "policy-%d.yaml" % index, payload)
        _expect_value_error(lambda path=path: load_policy(path), label)
    return _polarity(True, "5/5 malformed policies raise ValueError")


def _t08() -> tuple[bool, str]:
    module = _policy_module()
    policy = _policy_dict()
    results = [
        ("10000->250", module.fee_cents(10000, policy), 250),
        ("500->12", module.fee_cents(500, policy), 12),
        ("1->0", module.fee_cents(1, policy), 0),
        ("100000->500", module.fee_cents(100000, policy), 500),
    ]
    checks = [
        (label, value == expected and type(value) is int)
        for label, value, expected in results
    ]
    custom = {**policy, "min_fee_cents": 100}
    clamped = module.fee_cents(100, custom)
    checks.append(("min 100 -> 100", clamped == 100 and type(clamped) is int))
    _check_all(checks)
    return _polarity(True, "5/5 integer clamps, no float")


def _t09() -> tuple[bool, str]:
    is_eligible = _policy_module().is_eligible
    policy = _policy_dict()
    half = {**policy, "max_refund_ratio": 0.5}
    checks = [
        ("exactly total", is_eligible({"total_cents": 1000}, 1000, policy) is True),
        ("one cent over", is_eligible({"total_cents": 1000}, 1001, policy) is False),
        ("zero amount", is_eligible({"total_cents": 1000}, 0, policy) is False),
        ("negative amount", is_eligible({"total_cents": 1000}, -5, policy) is False),
        ("order None", is_eligible(None, 1000, policy) is False),
        ("missing total_cents", is_eligible({}, 1000, policy) is False),
        ("ratio 0.5 exact", is_eligible({"total_cents": 1000}, 500, half) is True),
        ("ratio 0.5 over", is_eligible({"total_cents": 1000}, 501, half) is False),
    ]
    _check_all(checks)
    return _polarity(True, "8/8 eligibility boundaries")


def _t10() -> tuple[bool, str]:
    load_policy = _policy_module().load_policy
    directory = _scratch_dir("policy-io")
    broken = directory / "broken.yaml"
    broken.write_bytes(b"version: 1\ncurrency: [CNY\n")
    before = hashlib.sha256(broken.read_bytes()).hexdigest()
    _expect_value_error(lambda: load_policy(broken), "broken YAML")
    after = hashlib.sha256(broken.read_bytes()).hexdigest()
    _expect(before == after, "load_policy rewrote the YAML file")
    commented = directory / "commented.yaml"
    commented.write_bytes(
        b"# comment line\n"
        b"version: 1\n"
        b"currency: CNY\n"
        b"fee_bps: 250\n"
        b"min_fee_cents: 0\n"
        b"max_fee_cents: 500\n"
        b"max_refund_ratio: 1.0\n"
    )
    _expect(load_policy(commented) == POLICY_BASE, "commented YAML did not load")
    return _polarity(True, "syntax error raises ValueError, bytes untouched")


# ---------------------------------------------------------------------------
# 1.3 仓储（T11-T14）
# ---------------------------------------------------------------------------
def _repository_class():
    return _tree_module("shop.refund_repository").RefundRepository


def _make_record(refund_id: int, order_id: int, amount_cents: int = 100) -> object:
    return _record_class()(
        refund_id, order_id, amount_cents, 5, "damaged", "recorded", None
    )


def _t11() -> tuple[bool, str]:
    repository = _repository_class()()
    expected = _make_record(1, 1).to_dict()
    returned = repository.add(_make_record(1, 1))
    _expect(returned == expected, "add did not return the record payload")
    returned["amount_cents"] = 999
    returned["extra"] = 1
    rows = repository.all()
    _expect(rows == [expected], "mutating add() result changed the repository")
    rows.append({"refund_id": 99})
    rows[0]["amount_cents"] = 7
    again = repository.all()
    _expect(again == [expected], "all() does not return copies")
    _expect(repository.all() is not repository.all(), "all() returns the same list")
    return _polarity(True, "add/all hand out copies")


def _t12() -> tuple[bool, str]:
    repository = _repository_class()()
    repository.add(_make_record(1, 1, 100))
    repository.add(_make_record(2, 2, 200))
    repository.add(_make_record(3, 1, 300))
    first = repository.by_order(1)
    _expect([row["refund_id"] for row in first] == [1, 3], "by_order(1) filtered wrong")
    _expect([row["order_id"] for row in first] == [1, 1], "by_order(1) mixed orders")
    first.append({"refund_id": 99})
    first[0]["amount_cents"] = 1
    _expect(
        [row["refund_id"] for row in repository.by_order(1)] == [1, 3],
        "by_order() does not return copies",
    )
    _expect(repository.by_order(99) == [], "unknown order id did not return []")
    return _polarity(True, "by_order filters exactly and returns copies")


def _t13() -> tuple[bool, str]:
    directory = _scratch_dir("repo-file")
    path = directory / "refunds.jsonl"
    repository = _repository_class()(path)
    repository.add(_make_record(1, 1, 100))
    repository.add(_make_record(2, 2, 200))
    reopened = _repository_class()(path)
    rows = reopened.all()
    _expect([row["refund_id"] for row in rows] == [1, 2], "reopened repo lost order")
    _expect(rows[0]["amount_cents"] == 100, "reopened repo lost values")
    lines = path.read_text(encoding="utf-8").splitlines()
    _expect(len(lines) == 2, "file has " + str(len(lines)) + " lines")
    for number, line in enumerate(lines, 1):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError("line " + str(number) + " is not JSON") from exc
        _expect(isinstance(parsed, dict), "line " + str(number) + " is not an object")
    return _polarity(True, "JSONL add + reload keeps 2 records in order")


def _t14() -> tuple[bool, str]:
    repository_cls = _repository_class()
    directory = _scratch_dir("repo-bad")
    cases = [
        ("bad json", b'{bad json\n'),
        ("not an object", b"[1,2]\n"),
    ]
    for name, payload in cases:
        path = directory / (name.replace(" ", "-") + ".jsonl")
        path.write_bytes(payload)
        _expect_value_error(lambda path=path: repository_cls(path), name)
    return _polarity(True, "2/2 corrupt lines raise ValueError")


# ---------------------------------------------------------------------------
# 1.4 服务（T15-T20）
# ---------------------------------------------------------------------------
class _FakeOrders:
    """最小订单替身：只实现 RefundService 用到的 get。"""

    def __init__(self, rows: dict[int, int]) -> None:
        self._rows = dict(rows)
        self.calls: list[int] = []

    def get(self, order_id: int):
        self.calls.append(order_id)
        total = self._rows.get(order_id)
        if total is None:
            return None
        return {"id": order_id, "total_cents": total}


class _FakeRefunds:
    """最小退款仓储替身：add / all / by_order 三个方法。"""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.added = 0

    def add(self, record: object) -> dict:
        self.added += 1
        payload = record.to_dict()
        self.rows.append(dict(payload))
        return dict(payload)

    def all(self) -> list[dict]:
        return [dict(row) for row in self.rows]

    def by_order(self, order_id: int) -> list[dict]:
        return [dict(row) for row in self.rows if row.get("order_id") == order_id]


def _service_class():
    return _tree_module("shop.refund_service").RefundService


def _service(orders: dict[int, int] | None = None):
    return (
        _service_class()(
            _FakeOrders(orders if orders is not None else {7: 1000}),
            _FakeRefunds(),
            _policy_dict(),
        ),
        None,
    )


def _t15() -> tuple[bool, str]:
    service, _unused = _service({7: 1000})
    result = service.create_refund(7, 1000, "damaged")
    expected = {
        "schema_version": 2,
        "refund_id": 1,
        "order_id": 7,
        "amount_cents": 1000,
        "fee_cents": 25,
        "reason": "damaged",
        "status": "recorded",
        "idempotency_key": None,
    }
    _expect(
        result == expected,
        "create_refund = " + json.dumps(result, ensure_ascii=False, sort_keys=True)[:240],
    )
    return _polarity(True, "refund_id=1, fee_cents=25, status=recorded")


def _t16() -> tuple[bool, str]:
    service, _unused = _service({})
    _expect_value_error(lambda: service.create_refund(7, 1000, "damaged"), "unknown order")
    _expect(service.refunds.all() == [], "unknown order wrote a record")
    return _polarity(True, "unknown order raises ValueError, nothing written")


def _t17() -> tuple[bool, str]:
    service, _unused = _service({7: 1000})
    for amount in (0, -1, 1001):
        _expect_value_error(
            lambda amount=amount: service.create_refund(7, amount, "damaged"),
            "amount " + str(amount),
        )
    _expect(service.refunds.all() == [], "rejected amounts wrote records")
    return _polarity(True, "3/3 bad amounts raise ValueError, nothing written")


def _t18() -> tuple[bool, str]:
    service, _unused = _service({7: 1000})
    ids = [
        service.create_refund(7, 500, "damaged", "k1")["refund_id"],
        service.create_refund(7, 500, "damaged", "k1")["refund_id"],
        service.create_refund(7, 400, "late", "k2")["refund_id"],
    ]
    _expect(ids == [1, 1, 2], "refund ids = " + repr(ids))
    _expect(len(service.refunds.all()) == 2, "record count is not 2")
    return _polarity(True, "idempotency key reuses id 1, new key gets id 2")


def _t19() -> tuple[bool, str]:
    service, _unused = _service({1: 1000, 2: 1000})
    service.create_refund(1, 300, "a")
    service.create_refund(1, 200, "b")
    service.create_refund(2, 100, "c")
    everything = service.list_refunds()
    _expect(len(everything) == 3, "list_refunds() length = " + str(len(everything)))
    filtered = service.list_refunds(1)
    _expect(len(filtered) == 2, "list_refunds(1) length = " + str(len(filtered)))
    _expect(
        [row["refund_id"] for row in filtered] == [1, 2],
        "list_refunds(1) ids = " + repr([row["refund_id"] for row in filtered]),
    )
    return _polarity(True, "unfiltered 3 / filtered 2")


def _t20() -> tuple[bool, str]:
    service, _unused = _service({7: 1000})
    service.create_refund(7, 1000, "damaged")
    _expect(service.orders.calls == [7], "orders.get calls = " + repr(service.orders.calls))
    parsed = _parse_tree_file("src/shop/refund_service.py")
    hits = _constructor_calls(parsed, CONSTRUCTOR_NAMES)
    _expect(not hits, "service instantiates a repository: " + "; ".join(hits[:3]))
    return _polarity(True, "collaborators injected; 0 repository constructions in AST")


# ---------------------------------------------------------------------------
# 1.5 控制器（T21-T24）
# ---------------------------------------------------------------------------
class _RecordingService:
    """记录调用参数的 service 替身；签名就是契约，传错立刻 TypeError。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.sentinel: dict = {"refund_id": 42}
        self.listing: list[dict] = [{"refund_id": 42}]

    def create_refund(
        self,
        order_id: int,
        amount_cents: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> dict:
        self.calls.append(("create_refund", order_id, amount_cents, reason, idempotency_key))
        return self.sentinel

    def list_refunds(self, order_id: int | None = None) -> list[dict]:
        self.calls.append(("list_refunds", order_id))
        return self.listing


def _controller_class():
    return _tree_module("shop.refund_controller").RefundController


def _t21() -> tuple[bool, str]:
    service = _RecordingService()
    controller = _controller_class()(service)
    result = controller.create_refund(1, 2, "x", "k")
    _expect(result is service.sentinel, "return value is not forwarded as the same dict")
    _expect(len(service.calls) == 1, "service received " + str(len(service.calls)) + " calls")
    _expect(
        service.calls[0] == ("create_refund", 1, 2, "x", "k"),
        "service received " + repr(service.calls[0]),
    )
    return _polarity(True, "args forwarded verbatim, return value passed through")


def _t22() -> tuple[bool, str]:
    service = _RecordingService()
    controller = _controller_class()(service)
    result = controller.list_refunds(7)
    _expect(result is service.listing, "list is not forwarded as the same list")
    _expect(len(service.calls) == 1, "service received " + str(len(service.calls)) + " calls")
    _expect(
        service.calls[0] == ("list_refunds", 7),
        "service received " + repr(service.calls[0]),
    )
    return _polarity(True, "order_id forwarded, list passed through")


def _t23() -> tuple[bool, str]:
    parsed = _parse_tree_file("src/shop/refund_controller.py")
    imports = sorted(_imported_modules(parsed) & REPOSITORY_MODULES)
    _expect(not imports, "controller imports " + ", ".join(imports))
    hits = _constructor_calls(parsed, CONSTRUCTOR_NAMES)
    _expect(not hits, "controller constructs a repository: " + "; ".join(hits[:3]))
    return _polarity(True, "0 repository imports, 0 repository constructions")


def _t24() -> tuple[bool, str]:
    controller_cls = _controller_class()
    parameters = list(inspect.signature(controller_cls.__init__).parameters.values())[1:]
    _expect(len(parameters) == 1, "constructor takes " + str(len(parameters)) + " parameters")
    parameter = parameters[0]
    _expect(
        parameter.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY),
        "first parameter kind = " + str(parameter.kind),
    )
    _expect(parameter.default is inspect.Parameter.empty, "service parameter is optional")
    controller = controller_cls(_RecordingService())
    _expect(not hasattr(controller, "repository"), "controller exposes .repository")
    _expect(not hasattr(controller, "refunds"), "controller exposes .refunds")
    return _polarity(True, "constructor takes exactly one required service")


# ---------------------------------------------------------------------------
# 1.6 演示（T25-T27）
# ---------------------------------------------------------------------------
def _pytest_run() -> subprocess.CompletedProcess[str]:
    if "pytest" not in _CACHE:
        _CACHE["pytest"] = _run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            _shared_copy(),
        )
    return _CACHE["pytest"]


def _collect_run() -> subprocess.CompletedProcess[str]:
    if "collect" not in _CACHE:
        _CACHE["collect"] = _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--collect-only",
                "-p",
                "no:cacheprovider",
            ],
            _shared_copy(),
        )
    return _CACHE["collect"]


def _collected_count() -> int:
    result = _collect_run()
    if result.returncode != 0:
        raise AssertionError(
            "collect-only exit=" + str(result.returncode) + " tail=" + _tail(result.stdout)
        )
    match = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
    if match:
        return int(match.group(1))
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


def _demo_run() -> tuple[Path, subprocess.CompletedProcess[str]]:
    if "demo" not in _CACHE:
        copy_root = _new_copy("demo")
        _CACHE["demo"] = (
            copy_root,
            _run([sys.executable, "tools/refund_demo.py"], copy_root),
        )
    return _CACHE["demo"]


def _demo_payload(result: subprocess.CompletedProcess[str]) -> list:
    _expect(result.returncode == 0, "demo exit=" + str(result.returncode))
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError("stdout is not JSON: " + _tail(result.stdout)) from exc
    _expect(isinstance(payload, list), "stdout JSON is " + type(payload).__name__)
    return payload


def _t25() -> tuple[bool, str]:
    _copy_root, result = _demo_run()
    payload = _demo_payload(result)
    _expect(len(payload) == 2, "demo printed " + str(len(payload)) + " records")
    fees = [row.get("fee_cents") for row in payload if isinstance(row, dict)]
    _expect(fees == [25, 12], "fee_cents = " + repr(fees))
    ids = [row.get("refund_id") for row in payload if isinstance(row, dict)]
    _expect(ids == [1, 2], "refund_id = " + repr(ids))
    _expect(
        all(row.get("status") == "recorded" for row in payload if isinstance(row, dict)),
        "status is not recorded",
    )
    return _polarity(True, "demo exit=0, 2 records, fee 25/12, id 1/2")


def _t26() -> tuple[bool, str]:
    copy_root, first = _demo_run()
    _demo_payload(first)
    second = _run([sys.executable, "tools/refund_demo.py"], copy_root)
    _expect(second.returncode == 0, "second demo exit=" + str(second.returncode))
    _expect(
        second.stdout == first.stdout,
        "two demo runs printed different bytes",
    )
    return _polarity(True, "two runs are byte-identical")


def _t27() -> tuple[bool, str]:
    copy_root = _new_copy("demo-config")
    config = copy_root / "config" / "refund_policy.yaml"
    config.write_bytes(
        b"version: 1\ncurrency: CNY\nfee_bps: 0\nmin_fee_cents: 0\n"
        b"max_fee_cents: 500\nmax_refund_ratio: 1.0\n"
    )
    result = _run([sys.executable, "tools/refund_demo.py"], copy_root)
    payload = _demo_payload(result)
    fees = [row.get("fee_cents") for row in payload if isinstance(row, dict)]
    _expect(fees == [0, 0], "fee_cents with fee_bps=0 = " + repr(fees))
    return _polarity(True, "config change reaches the demo (fee 0/0)")


# ---------------------------------------------------------------------------
# 1.7 迁移（T28-T32）
# ---------------------------------------------------------------------------
def _prepared_copy(prefix: str, remove_output: bool = True) -> Path:
    """新副本，清掉 data/refunds-v2.jsonl，让「输出是不是脚本写的」可判。"""
    copy_root = _new_copy(prefix)
    output = copy_root / "data" / "refunds-v2.jsonl"
    if remove_output:
        output.unlink(missing_ok=True)
    return copy_root


def _migrate(copy_root: Path, source: str, target: str) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            sys.executable,
            "tools/migrate_refunds.py",
            "--in",
            source,
            "--out",
            target,
        ],
        copy_root,
    )


def _migrate_output(copy_root: Path) -> bytes:
    path = copy_root / "data" / "refunds-v2.jsonl"
    _expect(path.is_file(), "data/refunds-v2.jsonl was not created")
    return path.read_bytes()


def _t28() -> tuple[bool, str]:
    copy_root = _prepared_copy("migrate")
    result = _migrate(copy_root, "data/refunds-legacy.jsonl", "data/refunds-v2.jsonl")
    _expect(result.returncode == 0, "migrate exit=" + str(result.returncode))
    _expect("MIGRATED 3" in result.stdout, "stdout has no MIGRATED 3: " + _tail(result.stdout))
    source = copy_root / "data" / "refunds-legacy.jsonl"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    _expect(
        digest == FROZEN_BASELINE["data/refunds-legacy.jsonl"],
        "the migration input file was modified",
    )
    _migrate_output(copy_root)
    return _polarity(True, "exit=0, MIGRATED 3, input bytes unchanged, output exists")


def _t29() -> tuple[bool, str]:
    copy_root = _prepared_copy("migrate-records")
    result = _migrate(copy_root, "data/refunds-legacy.jsonl", "data/refunds-v2.jsonl")
    _expect(result.returncode == 0, "migrate exit=" + str(result.returncode))
    raw = _migrate_output(copy_root).decode("utf-8")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    _expect(len(rows) == 3, "output has " + str(len(rows)) + " records")
    _expect(
        rows == MIGRATED_EXPECTED,
        "records = " + json.dumps(rows, ensure_ascii=False, sort_keys=True)[:300],
    )
    return _polarity(True, "3 v2 records, ascending refund_id, status=migrated")


def _t30() -> tuple[bool, str]:
    copy_root = _prepared_copy("migrate-idempotent")
    first = _migrate(copy_root, "data/refunds-legacy.jsonl", "data/refunds-v2.jsonl")
    _expect(first.returncode == 0, "first migrate exit=" + str(first.returncode))
    first_bytes = _migrate_output(copy_root)
    (copy_root / "data" / "refunds-v2.jsonl").unlink()
    second = _migrate(copy_root, "data/refunds-legacy.jsonl", "data/refunds-v2.jsonl")
    _expect(second.returncode == 0, "second migrate exit=" + str(second.returncode))
    _expect(
        _migrate_output(copy_root) == first_bytes,
        "two migration runs produced different bytes",
    )
    return _polarity(True, "delete + rerun is byte-identical")


def _t31() -> tuple[bool, str]:
    copy_root = _prepared_copy("migrate-bad")
    sentinel = b"SENTINEL\n"
    bad_inputs = [
        (
            "duplicate id",
            b'{"id": 1, "order": 1, "cents": 100, "why": "a"}\n'
            b'{"id": 1, "order": 2, "cents": 200, "why": "b"}\n',
        ),
        ("negative cents", b'{"id": 1, "order": 1, "cents": -5, "why": "a"}\n'),
        ("missing why", b'{"id": 1, "order": 1, "cents": 100}\n'),
    ]
    output = copy_root / "data" / "refunds-v2.jsonl"
    for index, (label, payload) in enumerate(bad_inputs):
        source = copy_root / "data" / ("bad-input-%d.jsonl" % index)
        source.write_bytes(payload)
        output.write_bytes(sentinel)
        result = _migrate(copy_root, "data/" + source.name, "data/refunds-v2.jsonl")
        _expect(result.returncode == 1, label + ": exit=" + str(result.returncode))
        _expect(
            output.read_bytes() == sentinel,
            label + ": the output file was replaced",
        )
    return _polarity(True, "3/3 bad inputs exit 1 and keep the sentinel output")


def _t32() -> tuple[bool, str]:
    copy_root = _prepared_copy("migrate-format")
    result = _migrate(copy_root, "data/refunds-legacy.jsonl", "data/refunds-v2.jsonl")
    _expect(result.returncode == 0, "migrate exit=" + str(result.returncode))
    raw = _migrate_output(copy_root)
    _expect(b"\r" not in raw, "output contains CR")
    _expect(raw.endswith(b"\n"), "output does not end with a newline")
    _expect(not raw.endswith(b"\n\n"), "output ends with more than one newline")
    text = raw.decode("utf-8")
    lines = text.splitlines()
    _expect(len(lines) == 3, "output has " + str(len(lines)) + " lines")
    checks = []
    for number, line in enumerate(lines, 1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError("line " + str(number) + " is not JSON") from exc
        checks.append(("line %d keys sorted" % number, list(payload) == sorted(payload)))
    _check_all(checks)
    return _polarity(True, "LF only, single trailing newline, 3 sorted-key JSON lines")


# ---------------------------------------------------------------------------
# 1.8 文档（T33-T34）
# ---------------------------------------------------------------------------
def _doc_bodies(text: str) -> dict[str, str]:
    lines = text.splitlines()
    bodies: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
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


def _t33() -> tuple[bool, str]:
    bodies = _doc_bodies(_read_text("docs/refund.md"))
    missing = [heading for heading in DOC_HEADINGS if heading not in bodies]
    _expect(not missing, "missing headings: " + ", ".join(missing))
    empty = [heading for heading in DOC_HEADINGS if not bodies[heading]]
    _expect(not empty, "headings without body: " + ", ".join(empty))
    return _polarity(True, "5/5 headings with non-empty bodies")


def _t34() -> tuple[bool, str]:
    readme = _read_text("README.md")
    missing = [literal for literal in README_LITERALS if literal not in readme]
    _expect(not missing, "README lacks: " + ", ".join(missing))
    return _polarity(True, "8/8 literal paths in README.md")


# ---------------------------------------------------------------------------
# 1.9 树形状（T35-T38）
# ---------------------------------------------------------------------------
def _t35() -> tuple[bool, str]:
    problems: list[str] = []
    assert TREE is not None
    for rel, expected in sorted(FROZEN_BASELINE.items()):
        path = TREE / rel
        if not path.is_file():
            problems.append(rel + " missing")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            problems.append(rel + " changed")
    for rel in sorted(MODIFIABLE_BASELINE):
        if not (TREE / rel).is_file():
            problems.append(rel + " missing")
    for rel in _tree_files():
        if rel in BASELINE_SHA256:
            continue
        if rel not in ALLOWED_WRITES:
            problems.append(rel + " not in allowed-writes")
    _expect(not problems, "out of bounds: " + "; ".join(problems[:6]))
    return _polarity(True, "11/11 frozen unchanged, change set within 19 allowed paths")


def _t36() -> tuple[bool, str]:
    files = set(_tree_files())
    extra = sorted(files - EXPECTED_PATHS)
    _expect(not extra, "extra files: " + ", ".join(extra[:6]))
    _expect(
        (TREE / "data" / "refunds-v2.jsonl").is_file() if TREE else False,
        "data/refunds-v2.jsonl is missing",
    )
    return _polarity(True, str(len(files)) + " files, subset of the 30 declared paths")


def _t37() -> tuple[bool, str]:
    result = _pytest_run()
    _expect(
        result.returncode == 0,
        "pytest exit=" + str(result.returncode) + " tail=" + _tail(result.stdout),
    )
    collected = _collected_count()
    _expect(collected >= COLLECTED_MIN, "collected=" + str(collected) + " < 10")
    return _polarity(True, "pytest exit=0, collected=" + str(collected) + " >= 10")


def _t38() -> tuple[bool, str]:
    scan = NEW_TEST_FILES + ["tests/test_order_repository.py"]
    skipped: list[str] = []
    for rel in scan:
        markers = _skip_markers(_parse_tree_file(rel))
        if markers:
            skipped.append(rel + " -> " + ", ".join(markers[:2]))
    _expect(not skipped, "skip/xfail markers: " + "; ".join(skipped[:4]))
    without_assert = [
        rel for rel in NEW_TEST_FILES if _assert_count(_parse_tree_file(rel)) < 1
    ]
    _expect(not without_assert, "no assert in: " + ", ".join(without_assert))
    _expect(
        _calls_get_method(_parse_tree_file("tests/test_order_repository.py")),
        "tests/test_order_repository.py never calls .get(...)",
    )
    return _polarity(True, "0 skip markers, 7/7 test files assert, get() covered")


# ---------------------------------------------------------------------------
# 2 入口 5 条（EN1-EN5）
# ---------------------------------------------------------------------------
def _en1() -> tuple[bool, str]:
    result = _pytest_run()
    _expect(
        result.returncode == 0,
        "pytest exit=" + str(result.returncode) + " tail=" + _tail(result.stdout),
    )
    return _polarity(True, "pytest exit=0")


def _en2() -> tuple[bool, str]:
    _copy_root, result = _demo_run()
    _expect(
        result.returncode == 0,
        "demo exit=" + str(result.returncode) + " tail=" + _tail(result.stderr),
    )
    return _polarity(True, "demo exit=0")


def _en3() -> tuple[bool, str]:
    _copy_root, result = _demo_run()
    payload = _demo_payload(result)
    _expect(
        payload == DEMO_EXPECTED,
        "stdout = " + json.dumps(payload, ensure_ascii=False, sort_keys=True)[:300],
    )
    return _polarity(True, "stdout is a JSON array of the 2 exact records")


def _en4() -> tuple[bool, str]:
    copy_root = _prepared_copy("entry-migrate")
    result = _migrate(copy_root, "data/refunds-legacy.jsonl", "data/refunds-v2.jsonl")
    _expect(
        result.returncode == 0,
        "migrate exit=" + str(result.returncode) + " tail=" + _tail(result.stderr),
    )
    raw = _migrate_output(copy_root).decode("utf-8")
    lines = [line for line in raw.splitlines() if line.strip()]
    _expect(len(lines) == 3, "output has " + str(len(lines)) + " records")
    return _polarity(True, "migrate exit=0 with 3 records")


def _en5() -> tuple[bool, str]:
    collected = _collected_count()
    _expect(collected >= COLLECTED_MIN, "collected=" + str(collected) + " < 10")
    return _polarity(True, "collected=" + str(collected) + " >= 10")


# ---------------------------------------------------------------------------
# 3 接口 5 条（I1-I5）
# ---------------------------------------------------------------------------
def _i1() -> tuple[bool, str]:
    record_cls = _record_class()
    field_names = [field.name for field in dataclasses.fields(record_cls)]
    _expect(field_names == RECORD_KEYS, "fields = " + repr(field_names))
    parameters = list(inspect.signature(record_cls).parameters.values())
    _expect([parameter.name for parameter in parameters] == RECORD_KEYS,
            "signature = " + repr([parameter.name for parameter in parameters]))
    for parameter in parameters[:6]:
        _expect(parameter.default is inspect.Parameter.empty,
                parameter.name + " has a default")
    _expect(parameters[6].default is None, "idempotency_key default is not None")
    record = record_cls(1, 2, 3, 4, "r", "s")
    checks = [
        ("refund_id int", isinstance(record.refund_id, int)),
        ("order_id int", isinstance(record.order_id, int)),
        ("amount_cents int", isinstance(record.amount_cents, int)),
        ("fee_cents int", isinstance(record.fee_cents, int)),
        ("reason str", isinstance(record.reason, str)),
        ("status str", isinstance(record.status, str)),
        ("idempotency_key None", record.idempotency_key is None),
    ]
    _check_all(checks)
    return _polarity(True, "7 fields in order, 6 required + idempotency_key=None")


def _i2() -> tuple[bool, str]:
    record_cls = _record_class()
    from_dict = getattr(record_cls, "from_dict", None)
    to_dict = getattr(record_cls, "to_dict", None)
    _expect(callable(to_dict), "to_dict is not callable")
    _expect(callable(from_dict), "from_dict is not callable")
    _expect(
        [parameter.name for parameter in inspect.signature(to_dict).parameters.values()]
        == ["self"],
        "to_dict parameters = "
        + repr([p.name for p in inspect.signature(to_dict).parameters.values()]),
    )
    _expect(
        [parameter.name for parameter in inspect.signature(from_dict).parameters.values()]
        == ["data"],
        "from_dict parameters = "
        + repr([p.name for p in inspect.signature(from_dict).parameters.values()]),
    )
    record = record_cls(1, 2, 1000, 25, "damaged", "recorded", "k")
    payload = to_dict(record)
    _expect(isinstance(payload, dict), "to_dict returned " + type(payload).__name__)
    _expect(from_dict(payload).to_dict() == payload, "round trip changed the payload")
    return _polarity(True, "to_dict(self) / from_dict(data) exist and round trip")


def _i3() -> tuple[bool, str]:
    service_cls = _service_class()
    parameters = list(
        inspect.signature(service_cls.__init__).parameters.values()
    )[1:]
    names = [parameter.name for parameter in parameters]
    _expect(names == ["orders", "refunds", "policy"], "parameters = " + repr(names))
    for parameter in parameters:
        _expect(parameter.default is inspect.Parameter.empty,
                parameter.name + " is optional")
        _expect(parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD,
                parameter.name + " kind = " + str(parameter.kind))
    return _polarity(True, "RefundService(orders, refunds, policy) all required")


def _i4() -> tuple[bool, str]:
    service_cls = _service_class()
    parameters = list(
        inspect.signature(service_cls.create_refund).parameters.values()
    )[1:]
    names = [parameter.name for parameter in parameters]
    expected = ["order_id", "amount_cents", "reason", "idempotency_key"]
    _expect(names == expected, "parameters = " + repr(names))
    for parameter in parameters[:3]:
        _expect(parameter.default is inspect.Parameter.empty,
                parameter.name + " has a default")
    _expect(parameters[3].default is None, "idempotency_key default is not None")
    return _polarity(True, "create_refund(order_id, amount_cents, reason, "
                           "idempotency_key=None)")


def _i5() -> tuple[bool, str]:
    controller_cls = _controller_class()
    parameters = list(
        inspect.signature(controller_cls.__init__).parameters.values()
    )[1:]
    names = [parameter.name for parameter in parameters]
    _expect(names == ["service"], "parameters = " + repr(names))
    _expect(parameters[0].default is inspect.Parameter.empty, "service is optional")
    _expect(
        parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD,
        "service kind = " + str(parameters[0].kind),
    )
    return _polarity(True, "RefundController(service) takes one required service")


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
    ("T27", _t27),
    ("T28", _t28),
    ("T29", _t29),
    ("T30", _t30),
    ("T31", _t31),
    ("T32", _t32),
    ("T33", _t33),
    ("T34", _t34),
    ("T35", _t35),
    ("T36", _t36),
    ("T37", _t37),
    ("T38", _t38),
    ("EN1", _en1),
    ("EN2", _en2),
    ("EN3", _en3),
    ("EN4", _en4),
    ("EN5", _en5),
    ("I1", _i1),
    ("I2", _i2),
    ("I3", _i3),
    ("I4", _i4),
    ("I5", _i5),
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
    sys.stderr.write("runner: cannot run: " + message + "\n")
    return 2


def main() -> int:
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
        return _cannot_run("case registry is not T01..T38 / EN1..EN5 / I1..I5")

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
