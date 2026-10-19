"""D 门 2 T 维度测量器：30 条隐藏验收 + 入口 5 + 接口 5。

用法（树根只从环境变量取）::

    POLICY_TREE=<final-tree> python runner.py [--json]

- 30 条隐藏验收：进程内直接调用 test_acceptance_dgate2.py 的 test_t01..test_t30；
- 入口 EN1-EN5：pytest / demo / 模块导入 / 收集数；
- 接口 I1-I5：inspect.signature 与行为；
- 需要子进程时在被评树的副本（系统 temp，用完即删）里跑，不写回被评树；
- 退出码：全过 0 / 有失败 1 / 跑不成 2。

载荷（RUNNER_SCHEMA_VERSION = "1.0"，无时戳、无绝对路径）::

    {"schema_version": "1.0", "tree": "<relative label>",
     "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
     "summary": {"passed": 40, "total": 40}}
"""
from __future__ import annotations

import argparse
import atexit
import contextlib
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

RUNNER_SCHEMA_VERSION = "1.0"
HIDDEN_FILENAME = "test_acceptance_dgate2.py"
HIDDEN_CASE_COUNT = 30
BASELINE_COLLECTED = 3
COLLECTED_THRESHOLD = BASELINE_COLLECTED + 3
TIMEOUT_SECONDS = 60

TREE: Path | None = None
_HIDDEN_MODULE = None
_COPY_HOLDER: Path | None = None
_COPY_TREE: Path | None = None
_RESULTS: dict[str, subprocess.CompletedProcess[str]] = {}


# ---------------------------------------------------------------------------
# 树标签 / 副本 / 子进程
# ---------------------------------------------------------------------------
def _tree_label(raw: str) -> str:
    """环境变量给的相对标签：载荷里绝不出现绝对路径。"""
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


def _ignore_artifacts(_directory: str, names: list[str]) -> set[str]:
    """副本里不带走缓存、隐藏目录与 pyc。"""
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
    """被评树的只读副本。"""
    global _COPY_HOLDER, _COPY_TREE
    if _COPY_TREE is None or not _COPY_TREE.is_dir():
        assert TREE is not None
        _COPY_HOLDER = Path(
            tempfile.mkdtemp(prefix="runner-", dir=str(_runtime_parent()))
        )
        atexit.register(shutil.rmtree, _COPY_HOLDER, ignore_errors=True)
        target = _COPY_HOLDER / "tree"
        shutil.copytree(TREE, target, ignore=_ignore_artifacts)
        _COPY_TREE = target
    return _COPY_TREE


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("PYTHONPATH", None)
    env.pop("PYTEST_ADDOPTS", None)
    return env


def _run(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        env=env if env is not None else _base_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


def _scrub(text: str) -> str:
    """删掉绝对路径（被评树根与临时副本根）。"""
    cleaned = str(text)
    roots = []
    if TREE is not None:
        roots.append(str(TREE))
    if _COPY_HOLDER is not None:
        roots.append(str(_COPY_HOLDER))
    for root in roots:
        cleaned = cleaned.replace(root, "<tree>")
    return cleaned


def _tail(text: str, limit: int = 240) -> str:
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    return _scrub(lines[-1])[:limit] if lines else ""


def _pytest_run() -> subprocess.CompletedProcess[str]:
    if "pytest" not in _RESULTS:
        _RESULTS["pytest"] = _run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            _tree_copy(),
        )
    return _RESULTS["pytest"]


def _collect_run() -> subprocess.CompletedProcess[str]:
    if "collect" not in _RESULTS:
        _RESULTS["collect"] = _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--collect-only",
                "-p",
                "no:cacheprovider",
            ],
            _tree_copy(),
        )
    return _RESULTS["collect"]


def _demo_run() -> subprocess.CompletedProcess[str]:
    if "demo" not in _RESULTS:
        _RESULTS["demo"] = _run(
            [sys.executable, "tools/audit_demo.py"], _tree_copy()
        )
    return _RESULTS["demo"]


def _collected_count() -> int:
    result = _collect_run()
    if result.returncode != 0:
        raise AssertionError("collect-only exit=" + str(result.returncode))
    match = re.search(r"(\d+)\s+tests?\s+collected", result.stdout)
    if match:
        return int(match.group(1))
    return sum(1 for line in result.stdout.splitlines() if "::" in line)


# ---------------------------------------------------------------------------
# 隐藏验收模块
# ---------------------------------------------------------------------------
def _load_hidden():
    path = Path(__file__).resolve().with_name(HIDDEN_FILENAME)
    if not path.is_file():
        raise RuntimeError("hidden test file not found next to runner.py")
    spec = importlib.util.spec_from_file_location("dgate2_hidden_acceptance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load hidden test file")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hidden_test_functions(module) -> list:
    names: list[tuple[int, str]] = []
    for name in dir(module):
        match = re.fullmatch(r"test_t(\d{2})_\w+", name)
        if match:
            names.append((int(match.group(1)), name))
    names.sort()
    indexes = [index for index, _name in names]
    if indexes != list(range(1, HIDDEN_CASE_COUNT + 1)):
        raise RuntimeError(
            "hidden test set is not t01..t30: found " + repr(indexes)
        )
    return [getattr(module, name) for _index, name in names]


def _run_case(case_id: str, func) -> dict:
    try:
        func()
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - 单条失败不能终止整轮
        detail = _scrub(type(exc).__name__ + ": " + str(exc))[:400]
        return {"id": case_id, "pass": False, "detail": detail or type(exc).__name__}
    return {"id": case_id, "pass": True, "detail": "ok"}


# ---------------------------------------------------------------------------
# 入口 5 条
# ---------------------------------------------------------------------------
def _case_en1() -> tuple[bool, str]:
    result = _pytest_run()
    if result.returncode == 0:
        return True, "pytest exit=0"
    return False, "pytest exit=" + str(result.returncode) + " tail=" + _tail(
        result.stdout
    )


def _case_en2() -> tuple[bool, str]:
    result = _demo_run()
    if result.returncode == 0:
        return True, "demo exit=0"
    return False, "demo exit=" + str(result.returncode) + " tail=" + _tail(
        result.stderr
    )


def _case_en3() -> tuple[bool, str]:
    result = _demo_run()
    if result.returncode != 0:
        return False, "demo exit=" + str(result.returncode)
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as exc:
        return False, "stdout is not JSON: " + _scrub(str(exc))
    expected = [
        {"action": "create", "order_id": 1},
        {"action": "create", "order_id": 2},
    ]
    if not isinstance(payload, list):
        return False, "stdout JSON is " + type(payload).__name__
    if payload != expected:
        return False, "stdout=" + _scrub(repr(payload))[:200]
    return True, "stdout is a JSON array of 2 exact records"


def _case_en4() -> tuple[bool, str]:
    tree = _tree_copy()
    env = _base_env()
    env["PYTHONPATH"] = str(tree / "src")
    result = _run(
        [
            sys.executable,
            "-c",
            "import shop.order_audit, shop.order_service, shop.order_controller",
        ],
        tree,
        env=env,
    )
    if result.returncode == 0:
        return True, "three modules imported"
    return False, "import exit=" + str(result.returncode) + " tail=" + _tail(
        result.stderr
    )


def _case_en5() -> tuple[bool, str]:
    count = _collected_count()
    if count >= COLLECTED_THRESHOLD:
        return True, "collected=" + str(count) + " >= " + str(COLLECTED_THRESHOLD)
    return False, "collected=" + str(count) + " < " + str(COLLECTED_THRESHOLD)


# ---------------------------------------------------------------------------
# 接口 5 条
# ---------------------------------------------------------------------------
def _tree_module(name: str):
    assert TREE is not None
    src = str(TREE / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import importlib

    return importlib.import_module(name)


class _FakeService:
    """I5 用的 service 替身：只回放 audit_entries。"""

    def __init__(self) -> None:
        self.entries_sentinel: list[dict] = [{"action": "create", "order_id": 1}]

    def create(self, payload: dict) -> dict:
        return dict(payload)

    def audit_entries(self) -> list[dict]:
        return list(self.entries_sentinel)


def _case_i1() -> tuple[bool, str]:
    order_audit = _tree_module("shop.order_audit").OrderAudit
    audit = order_audit()
    parameters = list(inspect.signature(audit.record).parameters.values())
    names = [parameter.name for parameter in parameters]
    if names != ["action", "order_id"]:
        return False, "record parameters=" + repr(names)
    for parameter in parameters:
        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return False, "record parameter kind=" + str(parameter.kind)
    result = audit.record("create", 1)
    if not isinstance(result, dict) or result != {"action": "create", "order_id": 1}:
        return False, "record returned " + repr(result)
    return True, "record(action, order_id) -> dict"


def _case_i2() -> tuple[bool, str]:
    order_audit = _tree_module("shop.order_audit").OrderAudit
    audit = order_audit()
    audit.record("create", 1)
    parameters = list(inspect.signature(audit.entries).parameters.values())
    if parameters:
        return False, "entries parameters=" + repr(
            [parameter.name for parameter in parameters]
        )
    returned = audit.entries()
    if not isinstance(returned, list):
        return False, "entries returned " + type(returned).__name__
    returned.append({"action": "hack", "order_id": 99})
    returned.clear()
    if audit.entries() != [{"action": "create", "order_id": 1}]:
        return False, "entries does not return a copy"
    return True, "entries() -> list[dict] copy"


def _case_i3() -> tuple[bool, str]:
    service_cls = _tree_module("shop.order_service").OrderService
    parameters = list(inspect.signature(service_cls).parameters.values())
    names = [parameter.name for parameter in parameters]
    if names != ["repository", "audit"]:
        return False, "OrderService parameters=" + repr(names)
    for parameter in parameters:
        if parameter.default is not None:
            return False, parameter.name + " default is not None"
        if parameter.kind is not inspect.Parameter.POSITIONAL_OR_KEYWORD:
            return False, parameter.name + " is not a keyword parameter"
    service_cls(repository=None, audit=None)
    return True, "OrderService(repository=None, audit=None)"


def _case_i4() -> tuple[bool, str]:
    service_cls = _tree_module("shop.order_service").OrderService
    service = service_cls()
    parameters = list(inspect.signature(service.create).parameters.values())
    names = [parameter.name for parameter in parameters]
    if names != ["payload"]:
        return False, "create parameters=" + repr(names)
    result = service.create({"id": 5})
    if result != {"id": 5}:
        return False, "create returned " + repr(result)
    if service.audit_entries()[-1] != {"action": "create", "order_id": 5}:
        return False, "create did not write the audit entry"
    return True, "create(payload) keeps its signature and writes audit"


def _case_i5() -> tuple[bool, str]:
    hidden = _HIDDEN_MODULE
    if hidden is None:
        raise RuntimeError("hidden acceptance module is not loaded")
    controller_cls = _tree_module("shop.order_controller").OrderController
    fake = _FakeService()
    controller = controller_cls(fake)
    parameters = list(inspect.signature(controller.audit_entries).parameters.values())
    if parameters:
        return False, "audit_entries parameters=" + repr(
            [parameter.name for parameter in parameters]
        )
    source = hidden._read_tree_text("src/shop/order_controller.py")
    parsed = hidden.ast.parse(source)
    if hidden._imports_module(parsed, "shop.order_repository"):
        return False, "controller imports shop.order_repository"
    if hidden._references_attribute(parsed, "order_repository"):
        return False, "controller references order_repository"
    if hidden._calls_constructor(parsed, "OrderRepository"):
        return False, "controller instantiates OrderRepository"
    if controller.audit_entries() != fake.entries_sentinel:
        return False, "audit_entries does not forward"
    return True, "audit_entries() -> list[dict], forwards only"


def _case(func) -> dict:
    try:
        passed, detail = func()
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - 单条失败不能终止整轮
        passed = False
        detail = _scrub(type(exc).__name__ + ": " + str(exc))[:400]
    return {"pass": passed, "detail": detail}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _cannot_run(message: str) -> int:
    sys.stderr.write("runner: cannot run: " + message + "\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    global TREE
    parser = argparse.ArgumentParser(
        description="D gate 2 T-dimension runner (30 hidden + 5 entry + 5 interface)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the machine-readable payload (deterministic)",
    )
    parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    raw = os.environ.get("POLICY_TREE")
    if not raw:
        return _cannot_run("POLICY_TREE is not set")
    TREE = Path(raw).resolve()
    if not TREE.is_dir():
        return _cannot_run("POLICY_TREE does not point to a directory")

    global _HIDDEN_MODULE
    try:
        hidden = _load_hidden()
        _HIDDEN_MODULE = hidden
        hidden_tests = _hidden_test_functions(hidden)
    except BaseException as exc:  # noqa: BLE001 - 跑不成 => 退出码 2
        return _cannot_run("hidden acceptance could not be loaded: " + _scrub(
            type(exc).__name__ + ": " + str(exc)
        ))

    cases: list[dict] = []
    entry_cases = (
        ("EN1", _case_en1),
        ("EN2", _case_en2),
        ("EN3", _case_en3),
        ("EN4", _case_en4),
        ("EN5", _case_en5),
        ("I1", _case_i1),
        ("I2", _case_i2),
        ("I3", _case_i3),
        ("I4", _case_i4),
        ("I5", _case_i5),
    )
    # 被测模块在 import 期打印的任何东西都不能污染 JSON 载荷（stdout 只留最终载荷）。
    swallowed = io.StringIO()
    with contextlib.redirect_stdout(swallowed):
        for index, func in enumerate(hidden_tests, start=1):
            cases.append(_run_case("T%02d" % index, func))
        for case_id, func in entry_cases:
            result = _case(func)
            cases.append(
                {"id": case_id, "pass": result["pass"], "detail": result["detail"]}
            )

    passed = sum(1 for case in cases if case["pass"])
    payload = {
        "schema_version": RUNNER_SCHEMA_VERSION,
        "tree": _tree_label(raw),
        "cases": cases,
        "summary": {"passed": passed, "total": len(cases)},
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
