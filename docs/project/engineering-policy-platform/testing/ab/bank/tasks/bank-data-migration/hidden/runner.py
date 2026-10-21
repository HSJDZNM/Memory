"""bank-data-migration 隐藏验收 runner：T01-T32 + EN1-EN4 + I1-I4（40 条）。

用法::

    BANK_TASK_TREE=<被评树> python hidden/runner.py

契约（hidden/PLAN.md §0 与 bank/README.md §4.3）:

- 被评树只从环境变量 BANK_TASK_TREE 读入，**绝不写**：所有需要执行的动作（pytest / 迁移 / 校验 /
  构造坏输入）都在树的副本里跑（临时目录，退出时删），副本绝不落在被评树内部；
- stdout 唯一载荷（UTF-8）::

      {"schema_version": "1.0", "tree": "<相对标签>",
       "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
       "summary": {"passed": 40, "total": 40}}

  载荷不含时戳 / run id / 绝对路径；同一 cwd + 同一棵树两次运行逐字节相同；
- 退出码：全过 0 / 有失败 1 / 跑不成 2（缺 BANK_TASK_TREE、树不存在、用例集合不完整、树复制不了）；
- 每条用例独立 try/except：一条异常只让该条 fail，detail = 异常类型 + 脱敏短消息；
- 反向用例（T02-T07、T09-T11、T14-T16、T19、T20、T22、T23、T26、T29-T32）断言的是
  「期望失败 / 期望拒绝」，落在异常类型、退出码、字节不变与文件集合上。
"""
from __future__ import annotations

import ast
import atexit
import contextlib
import hashlib
import importlib
import importlib.util
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
COLLECT_MIN = 6

CASE_IDS = (
    ["T%02d" % index for index in range(1, 33)]
    + ["EN1", "EN2", "EN3", "EN4"]
    + ["I1", "I2", "I3", "I4"]
)

# 13 个基线文件（逐字节起点）。来源：包内 baseline/ 的 13 个文件实算 sha256
# （2026-10 复核；组合摘要 eedac602c64c7dbd4633d01a481495fa489406ac08e3a85a2c1c4ac2e0c91fa3，
# 与任务 README §1、reset-arm.py 的 _manifest_sha256 同一算法）。运行时不读 baseline。
BASELINE_SHA256 = {
    "AGENTS.md": "ef20cdca0d6c43dbb5038449c90a972d44837e4b9ddc17e074f994d5eed669a3",
    "README.md": "5b4313609e4a28b61b43cd7b58ead2b99866284e532c68b79983cd3698213a5a",
    "config/ledger_schema.yaml": "5280f8481c30021b74d9a88430833df8df97dec9625122de1868a2f0ded378d6",
    "conftest.py": "edd7cea37c657fb322cdee3038ca9aed35f40c7657a0faacb6640d6de9b050e7",
    "data/ledger-v1.jsonl": "3fa14c2bf12fc75fc05b9ed4c48ba6d97c5ca2f2cf6668ccbef5716ee0babae1",
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

# 允许写 9 条 = 基线可改写 1（README.md）+ 新建 8。
MODIFIABLE_BASELINE = frozenset({"README.md"})

# 冻结文件 = 基线 13 - 可改写 1 = 12（T29 逐字节校验这 12 个）。
FROZEN_BASELINE = {
    path: digest
    for path, digest in BASELINE_SHA256.items()
    if path not in MODIFIABLE_BASELINE
}

NEW_PATHS = frozenset(
    {
        "data/ledger-v2.jsonl",
        "docs/migration.md",
        "src/shop/ledger_migration.py",
        "tests/test_ledger_migration.py",
        "tests/test_migrate_ledger.py",
        "tests/test_verify_ledger.py",
        "tools/migrate_ledger.py",
        "tools/verify_ledger.py",
    }
)

ALLOWED_WRITES = frozenset(MODIFIABLE_BASELINE) | NEW_PATHS
EXPECTED_PATHS = frozenset(BASELINE_SHA256) | NEW_PATHS

IGNORED_SEGMENTS = frozenset(
    {".policy", "__pycache__", ".pytest_cache", ".ruff_cache"}
)

KEY_ORDER = [
    "schema_version",
    "entry_id",
    "order_id",
    "amount_cents",
    "reason",
    "status",
]

V1_KEYS = ["id", "order", "cents", "why"]

# data/ledger-v1.jsonl 的 4 行（按文件顺序；id 3/1/4/2，其中 id=3 的 cents 为 0）。
V1_ROWS = [
    {"id": 3, "order": 102, "cents": 0, "why": "goodwill adjustment"},
    {"id": 1, "order": 101, "cents": 1250, "why": "damaged item"},
    {"id": 4, "order": 103, "cents": 480, "why": "late delivery"},
    {"id": 2, "order": 101, "cents": 990, "why": "wrong size"},
]

# 期望的 v2 产物（按 entry_id 升序；键序 = KEY_ORDER）。
V2_ROWS = [
    {
        "schema_version": 2,
        "entry_id": 1,
        "order_id": 101,
        "amount_cents": 1250,
        "reason": "damaged item",
        "status": "migrated",
    },
    {
        "schema_version": 2,
        "entry_id": 2,
        "order_id": 101,
        "amount_cents": 990,
        "reason": "wrong size",
        "status": "migrated",
    },
    {
        "schema_version": 2,
        "entry_id": 3,
        "order_id": 102,
        "amount_cents": 0,
        "reason": "goodwill adjustment",
        "status": "migrated",
    },
    {
        "schema_version": 2,
        "entry_id": 4,
        "order_id": 103,
        "amount_cents": 480,
        "reason": "late delivery",
        "status": "migrated",
    },
]

SCHEMA_EXPECTED = {
    "schema_id": "ledger-schema/2",
    "version": 2,
    "key_order": list(KEY_ORDER),
    "sort_by": "entry_id",
    "sort_direction": "asc",
    "fields": {
        "schema_version": {"type": "int", "const": 2},
        "entry_id": {"type": "int", "min": 0},
        "order_id": {"type": "int", "min": 0},
        "amount_cents": {"type": "int", "min": 0},
        "reason": {"type": "str", "min_length": 1},
        "status": {"type": "str", "enum": ["migrated"]},
    },
}

DOC_HEADINGS = ["## 字段映射", "## 幂等", "## 原子替换", "## 回滚", "## 命令"]
README_STRUCTURE_PATHS = [
    "src/shop/ledger_migration.py",
    "tools/migrate_ledger.py",
    "tools/verify_ledger.py",
]
README_BASELINE_ROWS = [
    "src/shop/order_controller.py",
    "src/shop/order_service.py",
    "src/shop/order_repository.py",
    "tests/",
]
MIGRATE_COMMAND = (
    "python tools/migrate_ledger.py --in data/ledger-v1.jsonl "
    "--out data/ledger-v2.jsonl"
)
SKIP_ATTRS = frozenset({"skip", "skipif", "xfail", "importorskip"})

TREE: Path | None = None
_TMP_ROOT: Path | None = None
_SHARED_COPY: Path | None = None
_SUBPROCESS_TMP: Path | None = None
_HOLDERS: list[Path] = []


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
    """临时副本的父目录：优先 <cwd>/.tmp，其次树旁 .tmp，最后系统 temp。

    任何候选都不得落在被评树内部（只读被评树）；每个候选都要真写一次才算可用。
    """
    global _TMP_ROOT
    if _TMP_ROOT is not None and _TMP_ROOT.is_dir():
        return _TMP_ROOT
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
            _TMP_ROOT = probe
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
    """临时目录：不用 mkdtemp（0700 目录在受限宿主上不可用）。"""
    root = _temp_root()
    for index in itertools.count(1):
        candidate = root / ("%s-%d-%d" % (prefix, os.getpid(), index))
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        _HOLDERS.append(candidate)
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
    """所有「只读执行」共用的一份副本（导入 / pytest / 命令的基座）。"""
    global _SHARED_COPY
    if _SHARED_COPY is None or not _SHARED_COPY.is_dir():
        assert TREE is not None
        target = _holder("shared") / "tree"
        shutil.copytree(TREE, target, ignore=_ignore_artifacts)
        _SHARED_COPY = target
        src = str(target / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        root = str(target)
        if root not in sys.path:
            sys.path.insert(0, root)
    return _SHARED_COPY


def _case_dir(prefix: str) -> Path:
    """一条用例自己的临时目录（在被评树之外）。"""
    return _holder(prefix)


def _subprocess_tmp() -> Path:
    """子进程的临时目录：继承来的 TEMP 可能被宿主沙箱拒绝，这里换成一个可写的。"""
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
    for name in ("PYTHONPATH", "PYTEST_ADDOPTS", "PYTHONSTARTUP", "PYTHONHOME"):
        env.pop(name, None)
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
    """脱敏：删掉被评树根、临时目录（含 holder 的 pid 段）、其余盘符绝对路径与耗时。"""
    cleaned = str(text)
    roots: list[str] = []
    if TREE is not None:
        roots.append(str(TREE))
    roots.extend(str(holder) for holder in _HOLDERS)
    if _SUBPROCESS_TMP is not None:
        roots.append(str(_SUBPROCESS_TMP))
    if _TMP_ROOT is not None:
        roots.append(str(_TMP_ROOT))
    for root in sorted(set(roots), key=len, reverse=True):
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
def _read_bytes(rel: str) -> bytes:
    assert TREE is not None
    return (TREE / rel).read_bytes()


def _read_text(rel: str) -> str:
    assert TREE is not None
    return (TREE / rel).read_text(encoding="utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _tree_sha256(rel: str) -> str:
    return _sha256_bytes(_read_bytes(rel))


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


def _migration():
    """从副本导入被测树的 model 模块（只 import，不实例化）。"""
    assert _shared_copy() is not None
    return importlib.import_module("shop.ledger_migration")


def _tool(name: str):
    """按路径加载被测树的工具脚本（tools/ 不是包，用 spec 加载最稳）。"""
    path = _shared_copy() / "tools" / (name + ".py")
    if not path.is_file():
        raise FileNotFoundError("tools/" + name + ".py is missing")
    spec = importlib.util.spec_from_file_location("bank_hidden_" + name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load tools/" + name + ".py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _parse_tree_file(rel: str) -> ast.Module:
    return ast.parse(_read_text(rel), filename=rel)


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


# ---------------------------------------------------------------------------
# 断言小工具 / schema 变体
# ---------------------------------------------------------------------------
def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_all(checks: list[tuple[str, bool]]) -> None:
    failures = [label for label, ok in checks if not ok]
    _expect(not failures, "failed: " + ", ".join(failures))


def _expect_value_error(action, label: str) -> None:
    """action() 必须抛 ValueError：不抛、抛别的异常都算失败。"""
    try:
        action()
    except ValueError:
        return
    except Exception as exc:  # noqa: BLE001 - 反向用例：别的异常形态也算失败
        raise AssertionError(
            label + ": raised " + type(exc).__name__ + " instead of ValueError"
        ) from exc
    raise AssertionError(label + ": was accepted")


def _schema_source() -> str:
    """基线 schema 的原文（只读被评树）。"""
    return _read_text("config/ledger_schema.yaml")


def _schema_variant(*replacements: tuple[str, str]) -> str:
    """对 schema 原文做逐条替换，产出一个坏形状的变体。"""
    text = _schema_source()
    for old, new in replacements:
        _expect(old in text, "schema text lost the fragment: " + old.strip()[:40])
        text = text.replace(old, new, 1)
    return text


def _write_case_file(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _ok(detail: str) -> tuple[bool, str]:
    return True, detail


# ---------------------------------------------------------------------------
# 1.1 schema 严格性（T01-T07）
# ---------------------------------------------------------------------------
def _capture_value_error(action, label: str) -> str:
    """action() 必须抛 ValueError，返回它的消息。"""
    try:
        action()
    except ValueError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 - 反向用例：别的异常形态也算失败
        raise AssertionError(
            label + ": raised " + type(exc).__name__ + " instead of ValueError"
        ) from exc
    raise AssertionError(label + ": was accepted")


def _schema_file(directory: Path, text: str) -> Path:
    return _write_case_file(directory, "ledger_schema.yaml", text)


def _t01() -> tuple[bool, str]:
    migration = _migration()
    before = _tree_sha256("config/ledger_schema.yaml")
    schema = migration.load_schema(TREE / "config" / "ledger_schema.yaml")
    after = _tree_sha256("config/ledger_schema.yaml")
    _expect(isinstance(schema, dict), "load_schema returned " + type(schema).__name__)
    _expect(
        set(schema) == set(SCHEMA_EXPECTED),
        "top-level keys = " + repr(sorted(schema)),
    )
    _expect(schema == SCHEMA_EXPECTED, "schema values differ from the declared shape")
    _expect(list(schema["key_order"]) == KEY_ORDER, "key_order order differs")
    _expect(before == after, "load_schema changed the schema file")
    return _ok("6 keys, exact values, schema file untouched")


def _t02() -> tuple[bool, str]:
    directory = _case_dir("t02")
    path = _schema_file(directory, _schema_source() + "\nextra: 1\n")
    _expect_value_error(lambda: _migration().load_schema(path), "extra top-level key")
    return _ok("extra top-level key rejected")


def _t03() -> tuple[bool, str]:
    directory = _case_dir("t03")
    path = _schema_file(
        directory, _schema_variant(("sort_direction: asc\n", ""))
    )
    _expect_value_error(lambda: _migration().load_schema(path), "missing top-level key")
    return _ok("missing top-level key rejected")


def _t04() -> tuple[bool, str]:
    directory = _case_dir("t04")
    mismatch = _schema_file(
        directory, _schema_variant(("  - reason\n", ""))
    )
    duplicated = directory / "duplicated.yaml"
    duplicated.write_text(
        _schema_variant(("  - status\n", "  - status\n  - status\n")),
        encoding="utf-8",
        newline="",
    )
    _expect_value_error(
        lambda: _migration().load_schema(mismatch), "key_order set mismatch"
    )
    _expect_value_error(
        lambda: _migration().load_schema(duplicated), "key_order duplicate entry"
    )
    return _ok("2/2 rejected (set mismatch, duplicate key)")


def _t05() -> tuple[bool, str]:
    directory = _case_dir("t05")
    bad_sort_by = directory / "sort_by.yaml"
    bad_sort_by.write_text(
        _schema_variant(("sort_by: entry_id", "sort_by: amount")),
        encoding="utf-8",
        newline="",
    )
    bad_direction = directory / "direction.yaml"
    bad_direction.write_text(
        _schema_variant(("sort_direction: asc", "sort_direction: up")),
        encoding="utf-8",
        newline="",
    )
    _expect_value_error(
        lambda: _migration().load_schema(bad_sort_by), "sort_by outside key_order"
    )
    _expect_value_error(
        lambda: _migration().load_schema(bad_direction), "unknown sort_direction"
    )
    return _ok("2/2 rejected (sort_by, sort_direction)")


def _t06() -> tuple[bool, str]:
    directory = _case_dir("t06")
    broken = _schema_file(directory, "key: [unclosed\n")
    message = _capture_value_error(
        lambda: _migration().load_schema(broken), "malformed yaml"
    )
    _expect(str(directory) not in message, "message leaks the absolute temp path")
    _expect(
        _ABSOLUTE_PATH.search(message) is None,
        "message carries a drive-letter absolute path",
    )
    before = broken.read_bytes()
    _expect(broken.read_bytes() == before, "malformed schema file changed")
    _expect_value_error(
        lambda: _migration().load_schema(directory / "missing.yaml"),
        "missing schema file",
    )
    _expect_value_error(
        lambda: _migration().load_schema(directory), "directory as schema path"
    )
    return _ok("3/3 rejected, message has no absolute path")


def _t07() -> tuple[bool, str]:
    directory = _case_dir("t07")
    variants = [
        ("extra-constraint.yaml", ("    const: 2\n", "    const: 2\n    max: 5\n")),
        (
            "bad-type.yaml",
            (
                "  reason:\n    type: str\n    min_length: 1",
                "  reason:\n    type: float\n    min_length: 1",
            ),
        ),
        (
            "not-a-dict.yaml",
            ("  reason:\n    type: str\n    min_length: 1\n", "  reason: str\n"),
        ),
        ("bad-schema-id.yaml", ("ledger-schema/2", "ledger-schema/3")),
        ("bad-version.yaml", ("version: 2", 'version: "2"')),
    ]
    failures = []
    for name, replacements in variants:
        path = directory / name
        path.write_text(
            _schema_variant(replacements), encoding="utf-8", newline=""
        )
        try:
            _migration().load_schema(path)
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001 - 反向用例
            failures.append(name + ":" + type(exc).__name__)
            continue
        failures.append(name + ":accepted")
    _expect(not failures, "not rejected: " + ", ".join(failures))
    return _ok("5/5 rejected (constraint, type, field shape, schema_id, version)")


# ---------------------------------------------------------------------------
# 1.2 v1 读取（T08-T11）
# ---------------------------------------------------------------------------
def _v1_line(**overrides) -> str:
    row = {"id": 1, "order": 101, "cents": 10, "why": "ok"}
    row.update(overrides)
    return json.dumps(row)


def _v1_rows(rows: list[dict]) -> str:
    return "".join(json.dumps(row) + "\n" for row in rows)


def _v1_row(entry_id: int = 1, order: int = 101, cents: int = 10,
            why: str = "ok") -> dict:
    return {"id": entry_id, "order": order, "cents": cents, "why": why}


def _t08() -> tuple[bool, str]:
    before = _tree_sha256("data/ledger-v1.jsonl")
    rows = _migration().read_v1(TREE / "data" / "ledger-v1.jsonl")
    after = _tree_sha256("data/ledger-v1.jsonl")
    _expect(isinstance(rows, list) and len(rows) == 4,
            "read_v1 returned " + repr(type(rows).__name__) + " of length "
            + str(len(rows) if isinstance(rows, list) else "n/a"))
    _expect(rows == V1_ROWS, "rows differ from the v1 file bytes")
    _expect([row["id"] for row in rows] == [3, 1, 4, 2], "file order not preserved")
    _expect(all(set(row) == set(V1_KEYS) for row in rows), "key set differs")
    rows[0]["id"] = 99
    _expect(_migration().read_v1(TREE / "data" / "ledger-v1.jsonl") == V1_ROWS,
            "returned rows share state with the reader")
    _expect(before == after, "read_v1 wrote the input file")
    return _ok("4 rows, file order, fresh dicts, input untouched")


def _t09() -> tuple[bool, str]:
    directory = _case_dir("t09")
    valid = json.dumps(V1_ROWS[0])
    variants = [
        ("non-object.jsonl", "[1, 2]\n"),
        ("broken-json.jsonl", valid[:-1] + "\n"),
        (
            "blank-line.jsonl",
            valid + "\n\n" + valid.replace('"id": 3', '"id": 4') + "\n",
        ),
        ("empty.jsonl", ""),
    ]
    for name, text in variants:
        path = _write_case_file(directory, name, text)
        _expect_value_error(lambda path=path: _migration().read_v1(path), name)
    return _ok("4/4 rejected (non-object, bad json, blank line, empty file)")


def _t10() -> tuple[bool, str]:
    directory = _case_dir("t10")
    missing = _write_case_file(
        directory, "missing.jsonl", _v1_line()[:-1] + ', "extra": 1}\n'
    )
    short = _write_case_file(directory, "short.jsonl", '{"id": 1, "order": 2, "cents": 3}\n')
    _expect_value_error(
        lambda: _migration().read_v1(missing), "extra key"
    )
    _expect_value_error(
        lambda: _migration().read_v1(short), "missing key"
    )
    return _ok("2/2 rejected (extra key, missing key)")


def _t11() -> tuple[bool, str]:
    directory = _case_dir("t11")
    variants = [
        ("bool-id.jsonl", '{"id": true, "order": 1, "cents": 3, "why": "a"}\n'),
        ("negative-cents.jsonl", _v1_rows([_v1_row(cents=-1)])),
        ("string-cents.jsonl", _v1_rows([_v1_row(cents="12")])),
        ("empty-why.jsonl", _v1_rows([_v1_row(why="")])),
        ("int-why.jsonl", _v1_rows([_v1_row(why=5)])),
    ]
    for name, text in variants:
        path = _write_case_file(directory, name, text)
        _expect_value_error(lambda path=path: _migration().read_v1(path), name)
    return _ok("5/5 rejected (bool, negative, str, empty, non-str)")


# ---------------------------------------------------------------------------
# 1.3 映射 / 排序 / 无损（T12-T16）
# ---------------------------------------------------------------------------
def _t12() -> tuple[bool, str]:
    rows = _migration().read_v1(TREE / "data" / "ledger-v1.jsonl")
    migrated = _migration().migrate_rows(rows)
    _expect(isinstance(migrated, list) and len(migrated) == 4,
            "migrate_rows returned " + repr(type(migrated).__name__))
    _expect(migrated == V2_ROWS, "records differ from the expected v2 shape")
    _expect(
        all(list(record) == KEY_ORDER for record in migrated),
        "key order differs from key_order",
    )
    _expect([record["entry_id"] for record in migrated] == [1, 2, 3, 4],
            "records are not sorted by entry_id ascending")
    _expect(
        any(record["amount_cents"] == 0 for record in migrated),
        "the cents=0 record was dropped",
    )
    return _ok("4 records, key order, ascending, cents=0 kept")


def _t13() -> tuple[bool, str]:
    rows = [dict(row) for row in V1_ROWS]
    migrated = _migration().migrate_rows(rows)
    _expect(migrated is not rows, "migrate_rows returned the input list itself")
    input_ids = {id(row) for row in rows}
    _expect(
        all(id(record) not in input_ids for record in migrated),
        "an output record is an input dict",
    )
    _expect([row["id"] for row in rows] == [3, 1, 4, 2],
            "input list was reordered in place")
    again = _migration().migrate_rows([dict(row) for row in V1_ROWS])
    _expect(again == migrated, "two calls with the same rows differ")
    migrated[0]["amount_cents"] = 999
    _expect(rows == V1_ROWS, "mutating the output changed the input")
    return _ok("new list and dicts, input untouched, stable")


def _t14() -> tuple[bool, str]:
    _expect_value_error(
        lambda: _migration().migrate_rows([_v1_row(1), _v1_row(1)]),
        "duplicate id",
    )
    return _ok("duplicate id rejected")


def _t15() -> tuple[bool, str]:
    variants = [
        ("negative cents", [_v1_row(cents=-1)]),
        ("missing why", [{"id": 1, "order": 2, "cents": 3}]),
        ("empty why", [_v1_row(why="")]),
        ("non-object element", ["x"]),
        ("negative order", [_v1_row(order=-1)]),
    ]
    for label, rows in variants:
        _expect_value_error(lambda rows=rows: _migration().migrate_rows(rows), label)
    return _ok("5/5 rejected (negative, missing, empty, non-object, order)")


def _t16() -> tuple[bool, str]:
    _expect_value_error(lambda: _migration().migrate_rows([]), "empty rows")
    return _ok("empty rows rejected (no partial migration)")


# ---------------------------------------------------------------------------
# 1.4 原子写与幂等（T17-T20）
# ---------------------------------------------------------------------------
def _canonical_bytes(records: list[dict]) -> bytes:
    return "".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in records
    ).encode("utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _t17() -> tuple[bool, str]:
    directory = _case_dir("t17")
    target = directory / "out.jsonl"
    _migration().write_v2(target, [dict(record) for record in V2_ROWS])
    raw = target.read_bytes()
    _expect(raw == _canonical_bytes(V2_ROWS), "bytes differ from the canonical LF form")
    _expect(b"\r" not in raw, "file contains CR")
    _expect(
        raw.endswith(b"\n") and not raw.endswith(b"\n\n"),
        "trailing newline is not exactly one",
    )
    records = [json.loads(line) for line in raw.split(b"\n")[:-1]]
    _expect(len(records) == 4, "line count = " + str(len(records)))
    _expect(all(list(record) == KEY_ORDER for record in records), "key order differs")
    return _ok("canonical LF bytes, 4 lines, exact key order")


def _t18() -> tuple[bool, str]:
    directory = _case_dir("t18")
    target = directory / "out.jsonl"
    migration = _migration()
    rows = [dict(record) for record in V2_ROWS]
    migration.write_v2(target, rows)
    first = target.read_bytes()
    migration.write_v2(target, rows)
    _expect(target.read_bytes() == first, "two writes of the same rows differ")
    target.write_bytes(b"SENTINEL\n")
    migration.write_v2(target, rows)
    _expect(target.read_bytes() == first, "an existing target was not replaced")
    _expect(
        sorted(os.listdir(directory)) == ["out.jsonl"],
        "temporary file left behind: " + repr(sorted(os.listdir(directory))),
    )
    return _ok("idempotent bytes, target replaced, no temp file left")


def _t19() -> tuple[bool, str]:
    directory = _case_dir("t19")
    target = directory / "out.jsonl"
    target.write_bytes(b"SENTINEL\n")
    bad = [dict(V2_ROWS[0])]
    bad[0]["entry_id"] = {1, 2}
    _expect_value_error(
        lambda: _migration().write_v2(target, bad), "unserializable record"
    )
    _expect(target.read_bytes() == b"SENTINEL\n", "target was replaced on failure")
    _expect(
        sorted(os.listdir(directory)) == ["out.jsonl"],
        "temporary file left behind: " + repr(sorted(os.listdir(directory))),
    )
    return _ok("serialization failure keeps the target and leaves no temp file")


def _t20() -> tuple[bool, str]:
    directory = _case_dir("t20")
    target = directory / "missing" / "out.jsonl"
    _expect_value_error(
        lambda: _migration().write_v2(target, [dict(record) for record in V2_ROWS]),
        "missing parent directory",
    )
    _expect(
        not (directory / "missing").exists(), "the parent directory was created"
    )
    return _ok("missing parent directory rejected and not created")


# ---------------------------------------------------------------------------
# 1.5 迁移 CLI（T21-T24）
# ---------------------------------------------------------------------------
MIGRATE_ARGS = [
    "tools/migrate_ledger.py",
    "--in",
    "data/ledger-v1.jsonl",
    "--out",
    "data/ledger-v2.jsonl",
]
VERIFY_ARGS = ["tools/verify_ledger.py", "--path", "data/ledger-v2.jsonl"]


def _cli(copy: Path, args: list[str], cwd: Path | None = None):
    return _run([sys.executable, *args], cwd=cwd or copy)


def _failure_problems(proc, prefix: str, forbidden: str) -> list[str]:
    """失败关闭的 CLI 读数：exit 1 + 一行 stderr + 不打印成功词 + 无绝对路径。"""
    problems: list[str] = []
    if proc.returncode != 1:
        problems.append("exit " + str(proc.returncode))
    lines = [line for line in proc.stderr.strip().splitlines() if line.strip()]
    if len(lines) != 1:
        problems.append("stderr lines " + str(len(lines)))
    elif not lines[0].startswith(prefix):
        problems.append("stderr prefix")
    if forbidden in proc.stdout:
        problems.append("stdout still prints " + forbidden)
    if _ABSOLUTE_PATH.search(proc.stderr):
        problems.append("stderr leaks an absolute path")
    return problems


def _t21() -> tuple[bool, str]:
    copy = _new_copy("t21")
    before = _file_sha256(copy / "data" / "ledger-v1.jsonl")
    proc = _cli(copy, list(MIGRATE_ARGS))
    _expect(
        proc.returncode == 0,
        "exit " + str(proc.returncode) + ": " + _tail(proc.stderr),
    )
    _expect(proc.stdout == "MIGRATED 4\n", "stdout = " + repr(proc.stdout[:80]))
    _expect(
        _file_sha256(copy / "data" / "ledger-v1.jsonl") == before,
        "the input ledger changed",
    )
    _expect(
        _read_jsonl(copy / "data" / "ledger-v2.jsonl") == V2_ROWS,
        "the product records differ",
    )
    return _ok("exit 0, stdout MIGRATED 4, product exact, input untouched")


def _t22() -> tuple[bool, str]:
    copy = _new_copy("t22")
    data = copy / "data"
    before = set(os.listdir(data))
    variants = {
        "bad-dup.jsonl": _v1_rows([_v1_row(1), _v1_row(1)]),
        "bad-negative.jsonl": _v1_rows([_v1_row(cents=-1)]),
        "bad-missing.jsonl": '{"id": 1, "order": 2, "cents": 3}\n',
        "bad-object.jsonl": "[1, 2]\n",
    }
    for name, text in variants.items():
        (data / name).write_text(text, encoding="utf-8", newline="")
    sentinel = b"SENTINEL\n"
    failures: list[str] = []
    for name in variants:
        out = data / "out-guard.jsonl"
        out.write_bytes(sentinel)
        proc = _cli(
            copy,
            [
                "tools/migrate_ledger.py",
                "--in",
                "data/" + name,
                "--out",
                "data/out-guard.jsonl",
            ],
        )
        problems = _failure_problems(proc, "MIGRATE FAILED:", "MIGRATED")
        if out.read_bytes() != sentinel:
            problems.append("sentinel changed")
        if problems:
            failures.append(name + ": " + ", ".join(problems))
    extra = set(os.listdir(data)) - before - set(variants) - {"out-guard.jsonl"}
    _expect(not extra, "leftover files: " + repr(sorted(extra)))
    _expect(not failures, "; ".join(failures))
    return _ok("4/4 rejected, sentinel kept, no temp residue")


def _t23() -> tuple[bool, str]:
    copy = _new_copy("t23")
    schema_path = copy / "config" / "ledger_schema.yaml"
    original = schema_path.read_text(encoding="utf-8")
    data = copy / "data"
    out = data / "out-guard.jsonl"
    sentinel = b"SENTINEL\n"
    subcases = [
        (
            "field removed",
            original.replace(
                "  status:\n    type: str\n    enum:\n      - migrated\n", ""
            ),
        ),
        ("key_order short", original.replace("  - status\n", "", 1)),
    ]
    failures: list[str] = []
    for label, text in subcases:
        _expect(text != original, "schema fragment not found for: " + label)
        schema_path.write_text(text, encoding="utf-8", newline="")
        out.write_bytes(sentinel)
        proc = _cli(
            copy,
            [
                "tools/migrate_ledger.py",
                "--in",
                "data/ledger-v1.jsonl",
                "--out",
                "data/out-guard.jsonl",
            ],
        )
        problems = _failure_problems(proc, "MIGRATE FAILED:", "MIGRATED")
        if out.read_bytes() != sentinel:
            problems.append("sentinel changed")
        if problems:
            failures.append(label + ": " + ", ".join(problems))
    schema_path.write_text(original, encoding="utf-8", newline="")
    out.write_bytes(sentinel)
    proc = _cli(
        copy,
        [
            "tools/migrate_ledger.py",
            "--in",
            "data/absent.jsonl",
            "--out",
            "data/out-guard.jsonl",
        ],
    )
    problems = _failure_problems(proc, "MIGRATE FAILED:", "MIGRATED")
    if out.read_bytes() != sentinel:
        problems.append("sentinel changed")
    if problems:
        failures.append("missing input: " + ", ".join(problems))
    _expect(not failures, "; ".join(failures))
    return _ok("3/3 rejected (bad schema x2, missing input)")


def _t24() -> tuple[bool, str]:
    copy = _new_copy("t24")
    script = copy / "tools" / "migrate_ledger.py"
    source = copy / "data" / "ledger-v1.jsonl"
    out = copy / "data" / "ledger-v2.jsonl"
    absolute = _cli(
        copy,
        [
            str(script),
            "--in",
            str(source),
            "--out",
            str(out),
        ],
        cwd=copy.parent,
    )
    _expect(
        absolute.returncode == 0,
        "cwd-independent exit " + str(absolute.returncode) + ": " + _tail(absolute.stderr),
    )
    _expect(absolute.stdout == "MIGRATED 4\n", "cwd-independent stdout differs")
    first = out.read_bytes()
    again = _cli(copy, list(MIGRATE_ARGS))
    _expect(again.returncode == 0, "second run exit " + str(again.returncode))
    _expect(out.read_bytes() == first, "second run differs byte for byte")
    out.unlink()
    regenerated = _cli(copy, list(MIGRATE_ARGS))
    _expect(regenerated.returncode == 0, "third run exit " + str(regenerated.returncode))
    _expect(out.read_bytes() == first, "regenerated product differs")
    return _ok("cwd independent, idempotent across runs and deletion")


# ---------------------------------------------------------------------------
# 1.6 校验 CLI（T25-T26）
# ---------------------------------------------------------------------------
def _tampered_payloads(records: list[dict]) -> list[tuple[str, bytes]]:
    """10 种篡改（结构 / 排序 / 类型 / 编码）。"""
    dump = _canonical_bytes
    variants: list[tuple[str, bytes]] = []
    missing = [dict(record) for record in records]
    missing[0] = {key: value for key, value in missing[0].items() if key != "reason"}
    variants.append(("missing-key", dump(missing)))
    swapped = [dict(record) for record in records]
    items = list(swapped[0].items())
    items[0], items[1] = items[1], items[0]
    swapped[0] = dict(items)
    variants.append(("key-order", dump(swapped)))
    variants.append(("record-order", dump([records[1], records[0], *records[2:]])))
    wrong_version = [dict(record) for record in records]
    wrong_version[0]["schema_version"] = 3
    variants.append(("schema-version", dump(wrong_version)))
    negative = [dict(record) for record in records]
    negative[0]["amount_cents"] = -1
    variants.append(("negative-amount", dump(negative)))
    variants.append(("crlf", dump(records).replace(b"\n", b"\r\n")))
    variants.append(("trailing-blank", dump(records) + b"\n"))
    variants.append(("empty", b""))
    lines = dump(records).split(b"\n")
    broken = list(lines)
    broken[0] = b'{"schema_version": 2, '
    variants.append(("broken-json", b"\n".join(broken)))
    non_object = list(lines)
    non_object[0] = b"[1, 2]"
    variants.append(("non-object", b"\n".join(non_object)))
    return variants


def _t25() -> tuple[bool, str]:
    copy = _new_copy("t25")
    migrated = _cli(copy, list(MIGRATE_ARGS))
    _expect(migrated.returncode == 0, "migrate exit " + str(migrated.returncode))
    target = copy / "data" / "ledger-v2.jsonl"
    before = _file_sha256(target)
    proc = _cli(copy, list(VERIFY_ARGS))
    _expect(
        proc.returncode == 0,
        "verify exit " + str(proc.returncode) + ": " + _tail(proc.stderr),
    )
    _expect(proc.stdout == "VERIFIED 4\n", "stdout = " + repr(proc.stdout[:80]))
    _expect(_file_sha256(target) == before, "verify wrote the checked file")
    return _ok("exit 0, stdout VERIFIED 4, checked file untouched")


def _t26() -> tuple[bool, str]:
    copy = _new_copy("t26")
    migrated = _cli(copy, list(MIGRATE_ARGS))
    _expect(migrated.returncode == 0, "migrate exit " + str(migrated.returncode))
    records = _read_jsonl(copy / "data" / "ledger-v2.jsonl")
    data = copy / "data"
    failures: list[str] = []
    for name, payload in _tampered_payloads(records):
        path = data / ("tampered-" + name + ".jsonl")
        path.write_bytes(payload)
        before = _file_sha256(path)
        proc = _cli(
            copy,
            ["tools/verify_ledger.py", "--path", "data/" + path.name],
        )
        problems = _failure_problems(proc, "VERIFY FAILED:", "VERIFIED")
        if _file_sha256(path) != before:
            problems.append("checked file changed")
        if problems:
            failures.append(name + ": " + ", ".join(problems))
    _expect(not failures, "; ".join(failures))
    return _ok("10/10 tampered payloads rejected, files untouched")


# ---------------------------------------------------------------------------
# 1.7 文档与 README（T27-T28）
# ---------------------------------------------------------------------------
def _section_body(text: str, heading: str) -> list[str] | None:
    """取某个二级标题到下个二级标题之间的正文行。"""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip().startswith(heading):
            start = index
            break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return body


def _t27() -> tuple[bool, str]:
    text = _read_text("docs/migration.md")
    bodies: dict[str, list[str]] = {}
    for heading in DOC_HEADINGS:
        body = _section_body(text, heading)
        _expect(body is not None, "missing heading: " + heading)
        _expect(any(line.strip() for line in body), "empty body after " + heading)
        bodies[heading] = body
    table_lines = [line for line in bodies["## 字段映射"] if line.count("|") >= 2]
    _expect(len(table_lines) >= 2, "the field mapping section has no markdown table")
    for key in V1_KEYS + KEY_ORDER:
        pattern = re.compile(
            r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?![A-Za-z0-9_])"
        )
        _expect(
            any(pattern.search(line) for line in table_lines),
            "the mapping table misses key: " + key,
        )
    rollback = " ".join(line.strip() for line in bodies["## 回滚"])
    _expect("v1" in rollback, "the rollback section does not mention v1")
    _expect("v2" in rollback, "the rollback section does not mention v2")
    _expect(
        any(word in rollback for word in ("没改", "未改", "不变", "一个字节")),
        "the rollback section does not say the v1 ledger is untouched",
    )
    _expect(
        any(word in rollback for word in ("删掉", "删除", "删去")),
        "the rollback section does not say to delete the v2 product",
    )
    _expect(
        any(word in rollback for word in ("重跑", "再跑", "重新跑", "重新生成")),
        "the rollback section does not say to rerun the migration",
    )
    return _ok("5 headings with bodies, mapping table 10 keys, rollback semantics")


def _t28() -> tuple[bool, str]:
    text = _read_text("README.md")
    problems: list[str] = []
    for path in README_STRUCTURE_PATHS:
        if path not in text:
            problems.append("missing structure row: " + path)
    if MIGRATE_COMMAND not in text:
        problems.append("missing the migrate command line")
    if "](docs/migration.md" not in text:
        problems.append("missing a markdown link to docs/migration.md")
    for row in README_BASELINE_ROWS:
        if row not in text:
            problems.append("lost a baseline structure row: " + row)
    _expect(not problems, "; ".join(problems))
    return _ok("3 new rows, command line, doc link, baseline rows kept")


# ---------------------------------------------------------------------------
# 1.8 树形状与测试强度（T29-T32）
# ---------------------------------------------------------------------------
def _t29() -> tuple[bool, str]:
    files = set(_tree_files())
    problems: list[str] = []
    for rel, digest in FROZEN_BASELINE.items():
        if rel not in files:
            problems.append("missing " + rel)
            continue
        if _tree_sha256(rel) != digest:
            problems.append("changed " + rel)
    for rel in sorted(files):
        if rel in BASELINE_SHA256:
            if rel not in ALLOWED_WRITES and _tree_sha256(rel) != BASELINE_SHA256[rel]:
                problems.append("changed " + rel)
            continue
        if rel not in NEW_PATHS:
            problems.append("extra " + rel)
    _expect(not problems, "; ".join(problems))
    return _ok("changes within the 9 allowed writes, 12 frozen files untouched")


def _t30() -> tuple[bool, str]:
    files = set(_tree_files())
    extra = sorted(files - EXPECTED_PATHS)
    _expect(not extra, "files outside the declared set: " + ", ".join(extra))
    _expect("data/ledger-v2.jsonl" in files, "data/ledger-v2.jsonl is missing")
    raw = _read_bytes("data/ledger-v2.jsonl")
    _expect(bool(raw.strip()), "data/ledger-v2.jsonl is empty")
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    _expect(records == V2_ROWS, "the product records differ from the expected 4")
    return _ok("file set within 21 paths, product exact")


def _t31() -> tuple[bool, str]:
    files = set(_tree_files())
    problems: list[str] = []
    for rel in (
        "tests/test_ledger_migration.py",
        "tests/test_migrate_ledger.py",
        "tests/test_verify_ledger.py",
    ):
        if rel not in files:
            problems.append("missing " + rel)
            continue
        module = _parse_tree_file(rel)
        markers = _skip_markers(module)
        if markers:
            problems.append(rel + " has " + ",".join(markers))
        if _assert_count(module) < 1:
            problems.append(rel + " has no assert")
    _expect(not problems, "; ".join(problems))
    return _ok("3 files, no skip/xfail, at least one assert each")


def _t32() -> tuple[bool, str]:
    files = set(_tree_files())
    problems: list[str] = []
    for rel in sorted(NEW_PATHS):
        if rel not in files:
            problems.append("missing " + rel)
            continue
        raw = _read_bytes(rel)
        if raw.startswith(b"\xef\xbb\xbf"):
            problems.append(rel + " has a BOM")
        if b"\r" in raw:
            problems.append(rel + " has CR")
        if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
            problems.append(rel + " does not end with exactly one newline")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(rel + " is not UTF-8")
    _expect(not problems, "; ".join(problems))
    return _ok("8 new files: UTF-8, LF, no BOM, single trailing newline")


# ---------------------------------------------------------------------------
# 2 入口（EN1-EN4）
# ---------------------------------------------------------------------------
def _en1() -> tuple[bool, str]:
    copy = _new_copy("en1")
    proc = _run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=copy
    )
    _expect(
        proc.returncode == 0,
        "pytest exit " + str(proc.returncode) + ": " + _tail(proc.stdout),
    )
    return _ok("pytest exit 0")


def _en2() -> tuple[bool, str]:
    copy = _new_copy("en2")
    proc = _cli(copy, list(MIGRATE_ARGS))
    _expect(
        proc.returncode == 0,
        "migrate exit " + str(proc.returncode) + ": " + _tail(proc.stderr),
    )
    target = copy / "data" / "ledger-v2.jsonl"
    _expect(
        target.is_file() and target.stat().st_size > 0,
        "data/ledger-v2.jsonl is missing or empty",
    )
    return _ok("migrate command exit 0, product non-empty")


def _en3() -> tuple[bool, str]:
    copy = _new_copy("en3")
    migrated = _cli(copy, list(MIGRATE_ARGS))
    _expect(migrated.returncode == 0, "migrate exit " + str(migrated.returncode))
    proc = _cli(copy, list(VERIFY_ARGS))
    _expect(
        proc.returncode == 0,
        "verify exit " + str(proc.returncode) + ": " + _tail(proc.stderr),
    )
    _expect("VERIFIED 4" in proc.stdout, "stdout does not say VERIFIED 4")
    return _ok("verify command exit 0 with VERIFIED 4")


def _en4() -> tuple[bool, str]:
    copy = _new_copy("en4")
    proc = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=copy,
    )
    _expect(
        proc.returncode == 0,
        "collect exit " + str(proc.returncode) + ": " + _tail(proc.stdout),
    )
    ids = [
        line.strip()
        for line in proc.stdout.splitlines()
        if "::" in line and not line.strip().startswith("=")
    ]
    _expect(
        len(ids) >= COLLECT_MIN,
        "collected " + str(len(ids)) + " cases (need >= " + str(COLLECT_MIN) + ")",
    )
    for name in (
        "test_ledger_migration.py",
        "test_migrate_ledger.py",
        "test_verify_ledger.py",
    ):
        _expect(
            any(name + "::" in item.replace("\\", "/") for item in ids),
            "not collected: " + name,
        )
    return _ok(str(len(ids)) + " cases collected, 3 new files present")


# ---------------------------------------------------------------------------
# 3 接口（I1-I4）
# ---------------------------------------------------------------------------
def _t01_signature_problems(migration) -> list[str]:
    expected = {
        "load_schema": ["path"],
        "read_v1": ["path"],
        "migrate_rows": ["rows"],
        "write_v2": ["path", "rows"],
    }
    problems: list[str] = []
    for name, params in expected.items():
        func = getattr(migration, name, None)
        if not callable(func):
            problems.append(name + " is not callable")
            continue
        actual = list(inspect.signature(func).parameters.values())
        if [parameter.name for parameter in actual] != params:
            problems.append(
                name + " parameters " + repr([parameter.name for parameter in actual])
            )
            continue
        for parameter in actual:
            if parameter.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD:
                problems.append(name + "." + parameter.name + " kind")
            if parameter.default is not inspect.Parameter.empty:
                problems.append(name + "." + parameter.name + " has a default")
    return problems


def _i1() -> tuple[bool, str]:
    migration = _migration()
    problems = _t01_signature_problems(migration)
    _expect(not problems, "; ".join(problems))
    rows = migration.migrate_rows([dict(row) for row in V1_ROWS])
    _expect(isinstance(rows, list), "migrate_rows returned " + type(rows).__name__)
    return _ok("4 functions with the declared parameter shapes")


def _i2() -> tuple[bool, str]:
    problems: list[str] = []
    for name in ("migrate_ledger", "verify_ledger"):
        module = _tool(name)
        main = getattr(module, "main", None)
        if not callable(main):
            problems.append(name + ".main is not callable")
            continue
        signature = inspect.signature(main)
        params = list(signature.parameters.values())
        if [parameter.name for parameter in params] != ["argv"]:
            problems.append(
                name + ".main parameters " + repr([parameter.name for parameter in params])
            )
        elif params[0].default is not None:
            problems.append(name + ".main argv has a non-None default")
        if signature.return_annotation not in (int, "int"):
            problems.append(name + ".main does not annotate int")
        try:
            main([])
        except SystemExit as exc:
            if exc.code != 2:
                problems.append(name + ".main usage exit " + repr(exc.code))
        except Exception as exc:  # noqa: BLE001 - 反向用例
            problems.append(name + ".main raised " + type(exc).__name__)
        else:
            problems.append(name + ".main did not exit on a usage error")
    _expect(not problems, "; ".join(problems))
    return _ok("main(argv=None) -> int, usage errors exit 2")


def _i3() -> tuple[bool, str]:
    records = _migration().migrate_rows([dict(row) for row in V1_ROWS])
    problems: list[str] = []
    if any(list(record) != KEY_ORDER for record in records):
        problems.append("key order differs")
    if any(len(record) != 6 for record in records):
        problems.append("record key count differs")
    for record in records:
        if record.get("status") != "migrated":
            problems.append("status = " + repr(record.get("status")))
        version = record.get("schema_version")
        if not isinstance(version, int) or isinstance(version, bool) or version != 2:
            problems.append("schema_version is not int 2")
        amount = record.get("amount_cents")
        if not isinstance(amount, int) or isinstance(amount, bool):
            problems.append("amount_cents is not int")
    _expect(not problems, "; ".join(sorted(set(problems))))
    return _ok("6 keys in order, status migrated, int types")


def _i4() -> tuple[bool, str]:
    directory = _case_dir("i4")
    migration = _migration()
    bad_rows = [dict(record) for record in V2_ROWS]
    bad_rows[0]["entry_id"] = {1, 2}
    broken_schema = _write_case_file(directory, "broken.yaml", "key: [x\n")
    broken_rows = _write_case_file(directory, "broken.jsonl", "[1, 2]\n")
    target = directory / "out.jsonl"
    actions = [
        ("load_schema", lambda: migration.load_schema(broken_schema)),
        ("read_v1", lambda: migration.read_v1(broken_rows)),
        ("migrate_rows", lambda: migration.migrate_rows([])),
        ("write_v2", lambda: migration.write_v2(target, bad_rows)),
    ]
    problems: list[str] = []
    for label, action in actions:
        try:
            action()
        except ValueError:
            continue
        except Exception as exc:  # noqa: BLE001 - 反向用例
            problems.append(label + " raised " + type(exc).__name__)
            continue
        problems.append(label + " accepted bad input")
    out = directory / "cli-out.jsonl"
    for name in ("migrate_ledger", "verify_ledger"):
        module = _tool(name)
        if name == "migrate_ledger":
            args = ["--in", str(broken_rows), "--out", str(out)]
        else:
            args = ["--path", str(broken_rows)]
        try:
            code = module.main(args)
        except Exception as exc:  # noqa: BLE001 - 反向用例
            problems.append(name + ".main raised " + type(exc).__name__)
            continue
        if code != 1:
            problems.append(name + ".main returned " + repr(code))
    if out.exists():
        problems.append("the migrate command created its output on failure")
    _expect(not problems, "; ".join(problems))
    return _ok("ValueError for the 4 functions, main returns 1, no output")


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
        return _cannot_run("case registry is not T01..T32 / EN1..EN4 / I1..I4")

    try:
        _shared_copy()
        _temp_root()
    except (OSError, RuntimeError) as exc:
        return _cannot_run("cannot copy the evaluated tree: " + type(exc).__name__)

    cases: list[dict] = []
    swallowed = io.StringIO()
    swallowed_err = io.StringIO()
    with contextlib.redirect_stdout(swallowed), contextlib.redirect_stderr(
        swallowed_err
    ):
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
