"""bank-async-concurrency 隐藏验收 runner：T01-T23 + EN1-EN8 + I1-I7（38 条）。

用法::

    BANK_TASK_TREE=<被评树> python hidden/runner.py

契约（bank/README.md 4.3 与 hidden/PLAN.md 0）:

- 被评树只从环境变量 BANK_TASK_TREE 读入，**绝不写**：所有需要执行的动作（pytest / 冒烟脚本 /
  模块导入）都在树的副本里跑（临时目录，用完即删）；
- stdout 唯一载荷（UTF-8）::

      {"schema_version": "1.0", "tree": "<相对标签>",
       "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
       "summary": {"passed": 38, "total": 38}}

  载荷不含时戳 / run id / 绝对路径；同一棵树两次运行逐字节相同；
- 退出码：全过 0 / 有失败 1 / 跑不成 2（缺 BANK_TASK_TREE、树不存在、用例集合不完整、树复制不了）；
- 每条用例独立 try/except：一条异常只让该条 fail，detail = 异常类型 + 脱敏短消息；
- 反向用例（T04/T05/T06/T13/T18/T19/T20/T22）断言的是「期望失败 / 期望拒绝」。
"""
from __future__ import annotations

import ast
import asyncio
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
SCENARIO_TIMEOUT = 20

CASE_IDS = (
    ["T%02d" % index for index in range(1, 24)]
    + ["EN%d" % index for index in range(1, 9)]
    + ["I%d" % index for index in range(1, 8)]
)

# ---------------------------------------------------------------------------
# 树形状常数（包内 baseline/ 实算；组合摘要
# d12576d82488d3665ea38bacdb6b1a32e23b08caa979f316ca6ba07aadb581e8，与 scoring.yaml 同值）
# ---------------------------------------------------------------------------
BASELINE_SHA256 = {
    "AGENTS.md": "ef20cdca0d6c43dbb5038449c90a972d44837e4b9ddc17e074f994d5eed669a3",
    "README.md": "5b4313609e4a28b61b43cd7b58ead2b99866284e532c68b79983cd3698213a5a",
    "conftest.py": "edd7cea37c657fb322cdee3038ca9aed35f40c7657a0faacb6640d6de9b050e7",
    "pytest.ini": "fd1c0f9fadf99a0af117f9f17fd7276f06d577e80fd530652978a1ff54aa71cc",
    "src/shop/__init__.py": (
        "d7eef7b6e4db6622675782550c664ef2ef3c2ff9e8de8845cc0e9f4af4b44ad1"
    ),
    "src/shop/notification.py": (
        "b9407f8e0899b2cdd7688cdec139ccd40ff06b835eb032b194e896af1f8820b7"
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
    "tests/test_notification.py": (
        "628af2e21c268109d6ee9b665ea7b03786ebfad2b0d4b55e68654aed69dcf2db"
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
    {"README.md", "src/shop/notification.py", "tests/test_notification.py"}
)

# 冻结文件 = 基线 14 - 可改写 3 = 11（I6 逐字节校验这 11 个）。
FROZEN_BASELINE = {
    path: digest
    for path, digest in BASELINE_SHA256.items()
    if path not in MODIFIABLE_BASELINE
}

# 任务新建的 7 个文件（14 基线 并 7 = 21 文件；I7 用）。
NEW_PATHS = frozenset(
    {
        "docs/async.md",
        "src/shop/notify_model.py",
        "src/shop/notify_worker.py",
        "tests/test_notify_model.py",
        "tests/test_notify_smoke.py",
        "tests/test_notify_worker.py",
        "tools/notify_smoke.py",
    }
)

ALLOWED_WRITES = frozenset(MODIFIABLE_BASELINE) | NEW_PATHS
EXPECTED_PATHS = frozenset(BASELINE_SHA256) | NEW_PATHS

IGNORED_SEGMENTS = frozenset(
    {".policy", "__pycache__", ".pytest_cache", ".ruff_cache"}
)

DETERMINISTIC_FILES = (
    "src/shop/notify_model.py",
    "src/shop/notify_worker.py",
    "tools/notify_smoke.py",
    "tests/test_notify_model.py",
    "tests/test_notify_smoke.py",
    "tests/test_notify_worker.py",
)

BANNED_CALLS = (
    "time.sleep",
    "time.time",
    "time.monotonic",
    "time.perf_counter",
    "random.",
    "socket.",
    "requests.",
    "urllib.request.",
    "httpx.",
    "http.client.",
)

DOC_HEADINGS = ["## 队列语义", "## 幂等", "## 取消", "## 停机"]

README_STRUCTURE_CELLS = [
    "src/shop/notify_worker.py",
    "src/shop/order_controller.py",
    "src/shop/order_service.py",
    "src/shop/order_repository.py",
    "tests/",
]

SKIP_ATTRS = frozenset({"skip", "skipif", "xfail", "importorskip"})

SMOKE_EXPECTED = [
    {"key": "smoke-1", "order_id": 1, "kind": "email"},
    {"key": "smoke-2", "order_id": 2, "kind": "sms"},
]

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
    """所有「只读执行」共用的一份副本（pytest / 导入 / 冒烟脚本）。"""
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
    env["NO_COLOR"] = "1"
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
    if _SHARED_COPY is not None:
        roots.append(str(_SHARED_COPY))
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
def _read_bytes(rel: str) -> bytes:
    assert TREE is not None
    return (TREE / rel).read_bytes()


def _read_text(rel: str) -> str:
    return _read_bytes(rel).decode("utf-8")


def _digest(rel: str) -> str:
    return hashlib.sha256(_read_bytes(rel)).hexdigest()


def _parse_tree_file(rel: str) -> ast.Module:
    return ast.parse(_read_text(rel), filename=rel)


def _tree_module(name: str):
    """从副本导入被测树的一个模块（只 import，不在导入期实例化任何协作者）。"""
    copy = _shared_copy()
    root = str(copy)
    src = str(copy / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    if name.split(".")[0] == "tools" and root not in sys.path:
        sys.path.insert(0, root)
    import importlib

    return importlib.import_module(name)


def _arun(coro):
    """在独立事件循环里跑一个场景；场景有 20 秒预算（挂死判红，不挂死 runner）。"""

    async def guarded():
        return await asyncio.wait_for(coro, SCENARIO_TIMEOUT)

    return asyncio.run(guarded())


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


def _function_names(module: ast.Module) -> set[str]:
    return {
        node.name
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _banned_calls(module: ast.Module) -> list[str]:
    """所有调用的点分名里有没有时钟 / 随机 / 网络（a.b.c(...) 取 a.b.c）。"""
    hits: list[str] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        try:
            dotted = ast.unparse(node.func)
        except Exception:  # noqa: BLE001 - 反解析失败按裸名处理
            dotted = ""
        for banned in BANNED_CALLS:
            if dotted == banned or dotted.startswith(banned):
                hits.append(dotted[:60])
    return sorted(set(hits))


# ---------------------------------------------------------------------------
# 断言小工具
# ---------------------------------------------------------------------------
def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_all(checks: list[tuple[str, bool]]) -> None:
    failures = [label for label, ok in checks if not ok]
    _expect(not failures, "failed: " + ", ".join(failures))


def _expect_raise(action, label: str, kind: type[BaseException]) -> None:
    """action() 必须抛 kind：不抛、抛别的异常都算失败（反向用例的通过条件）。"""
    try:
        action()
    except kind:
        return
    except BaseException as exc:  # noqa: BLE001 - 反向用例：别的异常形态也算失败
        raise AssertionError(
            "%s: expected %s, got %s" % (label, kind.__name__, type(exc).__name__)
        ) from None
    raise AssertionError("%s: expected %s, got no exception" % (label, kind.__name__))


def _model():
    return _tree_module("shop.notify_model")


def _worker_module():
    return _tree_module("shop.notify_worker")


def _notification(key: str, order_id: int, kind: str) -> object:
    return _model().Notification(key, order_id, kind)


# ---------------------------------------------------------------------------
# T01-T08 记录模型
# ---------------------------------------------------------------------------
def _t01() -> tuple[bool, str]:
    """Notification 构造与三字段。"""
    Notification = _model().Notification
    record = Notification("k1", 7, "email")
    keyword = Notification(key="k2", order_id=0, kind="sms")
    _check_all(
        [
            ("key", record.key == "k1"),
            ("order_id", record.order_id == 7),
            ("order_id_is_int", type(record.order_id) is int),
            ("kind", record.kind == "email"),
            ("keyword_ctor", keyword.key == "k2"),
            ("zero_order_id", keyword.order_id == 0),
            ("keyword_kind", keyword.kind == "sms"),
        ]
    )
    return True, "ok"


def _t02() -> tuple[bool, str]:
    """frozen：构造后给字段赋值抛 FrozenInstanceError。"""
    cls = _model().Notification
    record = cls("k", 1, "email")
    _expect_raise(
        lambda: setattr(record, "key", "x"), "key", dataclasses.FrozenInstanceError
    )
    _expect_raise(
        lambda: setattr(record, "order_id", 2), "order_id", dataclasses.FrozenInstanceError
    )
    _expect_raise(
        lambda: setattr(record, "kind", "sms"), "kind", dataclasses.FrozenInstanceError
    )
    params = getattr(cls, "__dataclass_params__", None)
    _check_all(
        [
            ("dataclass", dataclasses.is_dataclass(cls)),
            ("frozen_param", bool(getattr(params, "frozen", False))),
            ("value_kept", record.key == "k"),
        ]
    )
    return True, "ok"


def _t03() -> tuple[bool, str]:
    """同值两次构造相等。"""
    cls = _model().Notification
    left = cls("k", 1, "email")
    right = cls("k", 1, "email")
    other = cls("k", 1, "sms")
    _check_all([("equal", left == right), ("different", left != other)])
    return True, "ok"


def _t04() -> tuple[bool, str]:
    """非法 key 一律 ValueError（反向）。"""
    cls = _model().Notification
    for bad in ("", 1, None, b"k", ["k"]):
        _expect_raise(lambda bad=bad: cls(bad, 1, "email"), "key=%r" % (bad,), ValueError)
    return True, "ok"


def _t05() -> tuple[bool, str]:
    """非法 kind 一律 ValueError（反向）。"""
    cls = _model().Notification
    for bad in ("", 1, None, b"x", {"kind": "email"}):
        _expect_raise(lambda bad=bad: cls("k", 1, bad), "kind=%r" % (bad,), ValueError)
    return True, "ok"


def _t06() -> tuple[bool, str]:
    """非法 order_id 一律 ValueError（反向；bool 冒充 int 也要拒）。"""
    cls = _model().Notification
    for bad in (-1, True, False, 1.0, "1", None):
        _expect_raise(
            lambda bad=bad: cls("k", bad, "email"), "order_id=%r" % (bad,), ValueError
        )
    return True, "ok"


def _t07() -> tuple[bool, str]:
    """to_dict 的键集合恰为三键，且每次返回新 dict。"""
    record = _model().Notification("k1", 7, "email")
    first = record.to_dict()
    second = record.to_dict()
    _check_all(
        [
            ("keys", set(first) == {"key", "order_id", "kind"}),
            ("key_value", first["key"] == "k1"),
            ("order_value", first["order_id"] == 7),
            ("kind_value", first["kind"] == "email"),
            ("fresh_dict", first is not second),
            ("same_values", first == second),
        ]
    )
    return True, "ok"


def _t08() -> tuple[bool, str]:
    """改 to_dict 的返回值不影响对象与后续读数。"""
    record = _model().Notification("k1", 7, "email")
    payload = record.to_dict()
    payload["key"] = "mutated"
    payload["order_id"] = 99
    again = record.to_dict()
    _check_all(
        [
            ("object_key", record.key == "k1"),
            ("object_order", record.order_id == 7),
            ("fresh_key", again["key"] == "k1"),
            ("fresh_order", again["order_id"] == 7),
        ]
    )
    return True, "ok"


# ---------------------------------------------------------------------------
# T09-T16 submit / 有界 / 排空 / 副本
# ---------------------------------------------------------------------------
def _t09() -> tuple[bool, str]:
    """submit 幂等：同 key 第二次 False，processed 只 1 条。"""

    async def scenario():
        worker = _worker_module().NotificationWorker()
        await worker.start()
        first = await worker.submit(_notification("k", 1, "email"))
        second = await worker.submit(_notification("k", 2, "sms"))
        await worker.stop()
        return first, second, worker.processed()

    first, second, records = _arun(scenario())
    _check_all(
        [
            ("first_true", first is True),
            ("second_false", second is False),
            ("one_record", len(records) == 1),
            ("kept_first", bool(records) and records[0].get("order_id") == 1),
            ("kept_key", bool(records) and records[0].get("key") == "k"),
        ]
    )
    return True, "ok"


def _t10() -> tuple[bool, str]:
    """submit 的返回值是 bool（不是 1/0/None/真值对象）。"""

    async def scenario():
        worker = _worker_module().NotificationWorker()
        await worker.start()
        first = await worker.submit(_notification("b1", 1, "email"))
        second = await worker.submit(_notification("b1", 2, "sms"))
        await worker.stop()
        return first, second

    first, second = _arun(scenario())
    _check_all(
        [
            ("first_is_true", first is True),
            ("second_is_false", second is False),
            ("first_type", type(first) is bool),
            ("second_type", type(second) is bool),
        ]
    )
    return True, "ok"


def _t11() -> tuple[bool, str]:
    """不同 key 全进、FIFO 顺序稳定。"""
    keys = ["a", "b", "c"]

    async def scenario():
        worker = _worker_module().NotificationWorker()
        await worker.start()
        results = []
        for index, key in enumerate(keys):
            results.append(await worker.submit(_notification(key, index, "email")))
        await worker.stop()
        return results, worker.processed()

    results, records = _arun(scenario())
    _check_all(
        [
            ("all_true", results == [True, True, True]),
            ("order", [record.get("key") for record in records] == keys),
        ]
    )
    return True, "ok"


def _t12() -> tuple[bool, str]:
    """有界：queue_size=2 第三次 submit 返回 False 且不入队。"""
    keys = ["a", "b", "c"]

    async def scenario():
        worker = _worker_module().NotificationWorker(queue_size=2)
        results = []
        for index, key in enumerate(keys):
            results.append(await worker.submit(_notification(key, index, "email")))
        await worker.start()
        await worker.stop()
        return results, worker.processed()

    results, records = _arun(scenario())
    _check_all(
        [
            ("results", results == [True, True, False]),
            ("two_records", len(records) == 2),
            ("kept_order", [record.get("key") for record in records] == ["a", "b"]),
        ]
    )
    return True, "ok"


def _t13() -> tuple[bool, str]:
    """submit 非 Notification 一律 ValueError 且不入队（反向）。"""
    bad_values = ({"key": "k", "order_id": 1, "kind": "email"}, None, "k", object())

    async def scenario():
        worker = _worker_module().NotificationWorker()
        caught = 0
        for bad in bad_values:
            try:
                await worker.submit(bad)
            except ValueError:
                caught += 1
        await worker.start()
        await worker.stop()
        return caught, worker.processed()

    caught, records = _arun(scenario())
    _check_all(
        [
            ("all_value_error", caught == len(bad_values)),
            ("nothing_queued", records == []),
        ]
    )
    return True, "ok"


def _t14() -> tuple[bool, str]:
    """stop 先排空：3 条都处理完、顺序稳定、队列无残留。"""
    keys = ["a", "b", "c"]

    async def scenario():
        shared = asyncio.Queue()
        worker = _worker_module().NotificationWorker(queue=shared)
        await worker.start()
        for index, key in enumerate(keys):
            await worker.submit(_notification(key, index, "email"))
        await worker.stop()
        return worker.processed(), shared.empty()

    records, empty = _arun(scenario())
    _check_all(
        [
            ("three_records", len(records) == 3),
            ("order", [record.get("key") for record in records] == keys),
            ("queue_empty", empty is True),
        ]
    )
    return True, "ok"


def _t15() -> tuple[bool, str]:
    """processed 返回副本（新 list + 每条新 dict）。"""

    async def scenario():
        worker = _worker_module().NotificationWorker()
        await worker.start()
        await worker.submit(_notification("k", 1, "email"))
        await worker.stop()
        return worker

    worker = _arun(scenario())
    first = worker.processed()
    second = worker.processed()
    mutated = worker.processed()
    mutated.append({"key": "extra", "order_id": 99, "kind": "sms"})
    mutated[0]["key"] = "mutated"
    third = worker.processed()
    _check_all(
        [
            ("new_list", first is not second),
            ("new_dict", first[0] is not second[0]),
            ("append_isolated", len(third) == 1),
            ("mutation_isolated", third[0].get("key") == "k"),
        ]
    )
    return True, "ok"


def _t16() -> tuple[bool, str]:
    """stop 幂等：第二次 stop 不抛、records 不变。"""

    async def scenario():
        worker = _worker_module().NotificationWorker()
        await worker.start()
        await worker.submit(_notification("k", 1, "email"))
        await worker.stop()
        await worker.stop()
        return worker.processed()

    records = _arun(scenario())
    _check_all([("one_record", len(records) == 1)])
    return True, "ok"


# ---------------------------------------------------------------------------
# T17-T23 未启动的 stop / 关闭语义 / 共享队列 / 取消 / 确定性
# ---------------------------------------------------------------------------
def _t17() -> tuple[bool, str]:
    """未 start 的 stop 立即返回、不排空。"""

    async def scenario():
        shared = asyncio.Queue()
        first = _worker_module().NotificationWorker(queue=shared)
        await first.submit(_notification("k", 1, "email"))
        await first.stop()
        pending = shared.qsize()
        empty = first.processed()
        second = _worker_module().NotificationWorker(queue=shared)
        await second.start()
        await second.stop()
        return pending, empty, second.processed()

    pending, empty, records = _arun(scenario())
    _check_all(
        [
            ("queue_kept", pending == 1),
            ("nothing_processed", empty == []),
            ("later_consumed", [record.get("key") for record in records] == ["k"]),
        ]
    )
    return True, "ok"


def _t18() -> tuple[bool, str]:
    """stop 之后 submit 抛 RuntimeError（反向）。"""

    async def scenario():
        worker = _worker_module().NotificationWorker()
        await worker.start()
        await worker.stop()
        try:
            await worker.submit(_notification("k", 1, "email"))
        except RuntimeError:
            return True
        return False

    raised = _arun(scenario())
    _check_all([("runtime_error", raised is True)])
    return True, "ok"


def _t19() -> tuple[bool, str]:
    """stop 之后 start 抛 RuntimeError（反向），且不新建消费任务。"""

    async def scenario():
        worker = _worker_module().NotificationWorker()
        await worker.start()
        await worker.stop()
        raised = False
        try:
            await worker.start()
        except RuntimeError:
            raised = True
        current = asyncio.current_task()
        extra = [task for task in asyncio.all_tasks() if task is not current]
        return raised, len(extra)

    raised, extra = _arun(scenario())
    _check_all([("runtime_error", raised is True), ("no_new_task", extra == 0)])
    return True, "ok"


def _t20() -> tuple[bool, str]:
    """构造器参数校验（反向）。"""
    cls = _worker_module().NotificationWorker
    for bad in (0, -1, True, "2", 2.0):
        _expect_raise(
            lambda bad=bad: cls(queue_size=bad), "queue_size=%r" % (bad,), ValueError
        )
    for bad_queue in ({}, [], "q"):
        _expect_raise(
            lambda bad_queue=bad_queue: cls(queue=bad_queue),
            "queue=%r" % (type(bad_queue).__name__,),
            ValueError,
        )

    async def scenario():
        small = cls(queue_size=1)
        injected = cls(queue=asyncio.Queue())
        return small is not None and injected is not None

    _check_all([("valid_ctor", _arun(scenario()))])
    return True, "ok"


def _t21() -> tuple[bool, str]:
    """两个 worker 共享同一 asyncio.Queue。"""

    async def scenario():
        shared = asyncio.Queue()
        left = _worker_module().NotificationWorker(queue=shared)
        right = _worker_module().NotificationWorker(queue=shared)
        await left.start()
        await right.start()
        first = await left.submit(_notification("s1", 1, "email"))
        second = await left.submit(_notification("s2", 2, "sms"))
        duplicate = await left.submit(_notification("s1", 3, "email"))
        await left.stop()
        await right.stop()
        aggregate = left.processed() + right.processed()
        return first, second, duplicate, aggregate, shared.empty()

    first, second, duplicate, aggregate, empty = _arun(scenario())
    keys = sorted(record.get("key") for record in aggregate)
    _check_all(
        [
            ("first_true", first is True),
            ("second_true", second is True),
            ("duplicate_false", duplicate is False),
            ("aggregate_two", len(aggregate) == 2),
            ("each_key_once", keys == ["s1", "s2"]),
            ("queue_empty", empty is True),
        ]
    )
    return True, "ok"


def _t22() -> tuple[bool, str]:
    """取消阻塞中的 stop 时 CancelledError 不吞，且不残留消费任务（反向）。"""
    NotificationWorker = _worker_module().NotificationWorker

    class StuckQueue(asyncio.Queue):
        """join() 永不返回的队列：把 stop() 确定性地卡在 pending 上。"""

        async def join(self) -> None:
            await asyncio.Event().wait()

    async def scenario():
        worker = NotificationWorker(queue=StuckQueue())
        await worker.start()
        task = asyncio.get_running_loop().create_task(worker.stop())
        for _ in range(5):
            await asyncio.sleep(0)
        blocked = not task.done()
        task.cancel()
        raised = False
        try:
            await task
        except asyncio.CancelledError:
            raised = True
        current = asyncio.current_task()
        leftover = [item for item in asyncio.all_tasks() if item is not current]
        for item in leftover:
            item.cancel()
        if leftover:
            await asyncio.gather(*leftover, return_exceptions=True)
        return blocked, raised, len(leftover)

    blocked, raised, leftover = _arun(scenario())
    _check_all(
        [
            ("scenario_reached_block", blocked is True),
            ("cancelled_error_raised", raised is True),
            ("no_leftover_task", leftover == 0),
        ]
    )
    return True, "ok"


def _t23() -> tuple[bool, str]:
    """同一场景两次运行逐字节一致。"""

    def scenario() -> str:
        async def inner():
            worker = _worker_module().NotificationWorker()
            await worker.start()
            for index, key in enumerate(["d1", "d2", "d1", "d3"]):
                await worker.submit(_notification(key, index, "email"))
            await worker.stop()
            return worker.processed()

        return json.dumps(_arun(inner()), sort_keys=True, ensure_ascii=False)

    first = scenario()
    second = scenario()
    keys = [record["key"] for record in json.loads(first)]
    _check_all(
        [
            ("identical", first == second),
            ("three_records", len(json.loads(first)) == 3),
            ("order", keys == ["d1", "d2", "d3"]),
        ]
    )
    return True, "ok"


# ---------------------------------------------------------------------------
# EN1-EN8 入口
# ---------------------------------------------------------------------------
def _smoke_runs() -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    cached = _CACHE.get("smoke")
    if isinstance(cached, tuple):
        return cached
    copy = _shared_copy()
    args = [sys.executable, "tools/notify_smoke.py"]
    first = _run(args, copy)
    second = _run(args, copy)
    result = (first, second)
    _CACHE["smoke"] = result
    return result


def _en1() -> tuple[bool, str]:
    """冒烟脚本退出码 0，stderr 无 Traceback。"""
    first, _second = _smoke_runs()
    _check_all(
        [
            ("exit_code", first.returncode == 0),
            ("no_traceback", "Traceback" not in (first.stderr or "")),
        ]
    )
    return True, "exit=%d" % first.returncode


def _en2() -> tuple[bool, str]:
    """冒烟脚本 stdout：单行 JSON、恰 2 条、顺序与值正确。"""
    first, _second = _smoke_runs()
    _expect(first.returncode == 0, "smoke script failed: " + _tail(first.stderr))
    lines = [line for line in (first.stdout or "").splitlines() if line.strip()]
    _expect(len(lines) == 1, "expected exactly 1 stdout line, got %d" % len(lines))
    payload = json.loads(lines[0])
    _expect(isinstance(payload, list), "stdout JSON is not a list")
    _expect(len(payload) == 2, "expected 2 records, got %d" % len(payload))
    records = [dict(item) if isinstance(item, dict) else {} for item in payload]
    _check_all(
        [
            ("record_keys", all(set(item) == {"key", "order_id", "kind"} for item in records)),
            ("records", records == SMOKE_EXPECTED),
        ]
    )
    return True, "ok"


def _en3() -> tuple[bool, str]:
    """冒烟脚本两次运行 stdout 逐字节相同。"""
    first, second = _smoke_runs()
    _check_all(
        [
            ("first_exit", first.returncode == 0),
            ("second_exit", second.returncode == 0),
            ("identical", first.stdout.encode("utf-8") == second.stdout.encode("utf-8")),
        ]
    )
    return True, "ok"


def _en4() -> tuple[bool, str]:
    """tests/test_notify_smoke.py 静态 import main 并调用、含 assert、无 skip。"""
    module = _parse_tree_file("tests/test_notify_smoke.py")
    imported = False
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module == "tools.notify_smoke":
            if any(alias.name == "main" for alias in node.names):
                imported = True
        elif isinstance(node, ast.Import):
            if any(alias.name == "tools.notify_smoke" for alias in node.names):
                imported = True
    called = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "main"
        for node in ast.walk(module)
    )
    _check_all(
        [
            ("static_import", imported),
            ("calls_main", called),
            ("has_assert", _assert_count(module) > 0),
            ("no_skip", _skip_markers(module) == []),
        ]
    )
    return True, "ok"


def _en5() -> tuple[bool, str]:
    """docs/async.md 的四个二级标题与正文。"""
    lines = _read_text("docs/async.md").splitlines()
    positions: list[int] = []
    for heading in DOC_HEADINGS:
        index = next(
            (line_no for line_no, line in enumerate(lines) if line.strip() == heading), None
        )
        _expect(index is not None, "missing heading: " + heading)
        positions.append(index)
    _expect(positions == sorted(positions), "headings are out of order")
    _expect(len(set(positions)) == len(positions), "duplicate heading")
    for heading, start in zip(DOC_HEADINGS, positions):
        body = False
        for line in lines[start + 1 :]:
            stripped = line.strip()
            if stripped.startswith("#"):
                break
            if stripped:
                body = True
                break
        _expect(body, "empty body under: " + heading)
    return True, "ok"


def _en6() -> tuple[bool, str]:
    """README 的「结构」表含 notify_worker 一行且基线行仍在。"""
    cells: list[str] = []
    for line in _read_text("README.md").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = stripped.split("|")
        if len(parts) < 3:
            continue
        cells.append(parts[1].strip().strip(chr(96)).strip())
    missing = [cell for cell in README_STRUCTURE_CELLS if cell not in cells]
    _check_all([("missing_cells", not missing)])
    if missing:
        raise AssertionError("missing table cells: " + ", ".join(missing))
    return True, "ok"


def _pytest_run() -> subprocess.CompletedProcess[str]:
    cached = _CACHE.get("pytest")
    if isinstance(cached, subprocess.CompletedProcess):
        return cached
    copy = _shared_copy()
    result = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--color=no",
            "-p",
            "no:cacheprovider",
        ],
        copy,
    )
    _CACHE["pytest"] = result
    return result


def _collect_run() -> subprocess.CompletedProcess[str]:
    cached = _CACHE.get("collect")
    if isinstance(cached, subprocess.CompletedProcess):
        return cached
    copy = _shared_copy()
    result = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--color=no",
            "-p",
            "no:cacheprovider",
        ],
        copy,
    )
    _CACHE["collect"] = result
    return result


def _en7() -> tuple[bool, str]:
    """全树 pytest 绿。"""
    result = _pytest_run()
    output = (result.stdout or "") + (result.stderr or "")
    _check_all(
        [
            ("exit_code", result.returncode == 0),
            ("passed_marker", " passed" in output),
            ("no_failed_marker", re.search(r"\b\d+ failed\b", output) is None),
            ("no_error_marker", re.search(r"\b\d+ error", output) is None),
        ]
    )
    return True, "exit=0"


def _en8() -> tuple[bool, str]:
    """收集数 >= 7 且 3 个新测试文件都被收集。"""
    result = _collect_run()
    lines = [line.strip() for line in (result.stdout or "").splitlines()]
    collected = [line for line in lines if "::" in line]
    prefixes = (
        "tests/test_notify_model.py::",
        "tests/test_notify_worker.py::",
        "tests/test_notify_smoke.py::",
    )
    missing = [
        prefix for prefix in prefixes if not any(line.startswith(prefix) for line in collected)
    ]
    _check_all(
        [
            ("at_least_seven", len(collected) >= 7),
            ("all_new_files_collected", not missing),
        ]
    )
    return True, "collected=%d" % len(collected)


# ---------------------------------------------------------------------------
# I1-I7 接口与树形状
# ---------------------------------------------------------------------------
def _i1() -> tuple[bool, str]:
    """模块形状：Notification 字段顺序、worker 的协程方法。"""
    model = _model()
    worker_module = _worker_module()
    cls = worker_module.NotificationWorker
    names = [field.name for field in dataclasses.fields(model.Notification)]
    _check_all(
        [
            ("is_dataclass", dataclasses.is_dataclass(model.Notification)),
            ("field_order", names == ["key", "order_id", "kind"]),
            ("worker_class", inspect.isclass(cls)),
            ("start_coroutine", inspect.iscoroutinefunction(cls.start)),
            ("submit_coroutine", inspect.iscoroutinefunction(cls.submit)),
            ("stop_coroutine", inspect.iscoroutinefunction(cls.stop)),
            ("processed_sync", not inspect.iscoroutinefunction(cls.processed)),
        ]
    )
    return True, "ok"


def _i2() -> tuple[bool, str]:
    """构造器签名：参数名顺序、默认值、位置参数形态可用。"""
    cls = _worker_module().NotificationWorker
    signature = inspect.signature(cls.__init__)
    names = [parameter.name for parameter in signature.parameters.values()]
    queue_size = signature.parameters.get("queue_size")
    queue = signature.parameters.get("queue")
    _check_all(
        [
            ("param_names", names == ["self", "queue_size", "queue"]),
            ("queue_size_default", queue_size is not None and queue_size.default == 4),
            ("queue_default", queue is not None and queue.default is None),
        ]
    )

    async def scenario():
        return cls() is not None and cls(2) is not None

    _check_all([("positional_ctor", _arun(scenario()))])
    return True, "ok"


def _i3() -> tuple[bool, str]:
    """AST 确定性：6 个新文件里没有时钟 / 随机 / 网络调用。"""
    found: dict[str, list[str]] = {}
    for relative in DETERMINISTIC_FILES:
        hits = _banned_calls(_parse_tree_file(relative))
        if hits:
            found[relative] = hits
    _check_all([("clean", not found)])
    if found:
        raise AssertionError("banned calls: " + json.dumps(found, sort_keys=True))
    return True, "ok"


def _i4() -> tuple[bool, str]:
    """旧队列保留 + docstring 弃用标注 + 行为不变。"""
    module = _tree_module("shop.notification")
    doc = module.__doc__ or ""
    queue = module.NotificationQueue()
    payload = {"key": "a", "order_id": 1, "kind": "email"}
    queue.append(payload)
    payload["key"] = "mutated"
    popped = queue.pop()
    empty = module.NotificationQueue()
    raised = False
    try:
        empty.pop()
    except IndexError:
        raised = True
    _check_all(
        [
            ("doc_mentions", "已弃用" in doc and "NotificationWorker" in doc),
            ("class_kept", hasattr(module, "NotificationQueue")),
            ("copy_semantics", popped == {"key": "a", "order_id": 1, "kind": "email"}),
            ("length", len(queue) == 0),
            ("empty_index_error", raised),
        ]
    )
    return True, "ok"


def _i5() -> tuple[bool, str]:
    """tests/test_notification.py 断言弃用说明且保留原用例。"""
    module = _parse_tree_file("tests/test_notification.py")
    asserts = [ast.unparse(node) for node in ast.walk(module) if isinstance(node, ast.Assert)]
    documented = any("已弃用" in text and "__doc__" in text for text in asserts)
    _check_all(
        [
            ("asserts_doc", documented),
            (
                "original_case_kept",
                "test_sync_queue_keeps_order_and_length" in _function_names(module),
            ),
            ("no_skip", _skip_markers(module) == []),
        ]
    )
    return True, "ok"


def _i6() -> tuple[bool, str]:
    """11 个冻结基线文件逐字节不变。"""
    changed = [
        path for path, expected in FROZEN_BASELINE.items() if _digest(path) != expected
    ]
    _check_all([("frozen_untouched", not changed)])
    if changed:
        raise AssertionError("frozen files changed: " + ", ".join(sorted(changed)))
    return True, "ok"


def _i7() -> tuple[bool, str]:
    """文件集恰为 21 个（14 基线 并 7 新建），改动集合 ⊆ 10 条允许写。"""
    actual = set(_tree_files())
    extras = sorted(actual - set(EXPECTED_PATHS))
    missing = sorted(set(EXPECTED_PATHS) - actual)
    changed = sorted(
        path
        for path, expected in BASELINE_SHA256.items()
        if path in actual and _digest(path) != expected
    )
    illegal = sorted(path for path in changed if path not in ALLOWED_WRITES)
    _check_all(
        [
            ("no_extra_file", not extras),
            ("no_missing_file", not missing),
            ("changed_allowed", not illegal),
        ]
    )
    return True, "files=%d changed=%d" % (len(actual), len(changed))


# ---------------------------------------------------------------------------
# 注册表 / 入口
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
    ("EN1", _en1),
    ("EN2", _en2),
    ("EN3", _en3),
    ("EN4", _en4),
    ("EN5", _en5),
    ("EN6", _en6),
    ("EN7", _en7),
    ("EN8", _en8),
    ("I1", _i1),
    ("I2", _i2),
    ("I3", _i3),
    ("I4", _i4),
    ("I5", _i5),
    ("I6", _i6),
    ("I7", _i7),
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
        return _cannot_run("case registry is not T01-T23 / EN1-EN8 / I1-I7")

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
