"""bank-bugfix-first-failing-test 隐藏验收 runner：T01-T19 + EN1-EN6 + I1-I13（38 条）。

用法::

    BANK_TASK_TREE=<被评树> python hidden/runner.py

契约（hidden/PLAN.md 0 与 bank/README.md 4.3、旗舰题 hidden/README.md 同形）：

- 被评树只从环境变量 BANK_TASK_TREE 读入，**绝不写**：所有需要执行的动作（pytest / 导入被测模块 /
  变异副本）都在树的副本里跑（临时目录，用完即删，且绝不落在被评树内）；
- stdout 唯一载荷（UTF-8）::

      {"schema_version": "1.0", "tree": "<相对标签>",
       "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
       "summary": {"passed": 38, "total": 38}}

  载荷不含时戳 / run id / 绝对路径；同一 cwd + 同一棵树两次运行逐字节相同；
- 退出码：全过 0 / 有失败 1 / 跑不成 2（缺 BANK_TASK_TREE、树不存在、用例注册表不完整、树复制不出来）；
- 每条用例独立 try/except：一条异常只让该条 fail，detail = 异常类型 + 脱敏短消息；
- 反向用例（I8-I13）断言的是「同款探针必须在这个歪法上失败」；
  EN5 / EN6 断言的是**基线构造**（基线树是红的），与被评树无关。

基线常数（BASELINE_SHA256 与 BASELINE_SOURCES）来源 = 包内 baseline/ 的 11 个文件实算实抄
（组合摘要 b9bb24d16937783dabfa13b3baddb027cdffad4af32bf0e8610685ac8aa1cafd）。运行时不读 baseline/。
"""
from __future__ import annotations

import ast
import atexit
import contextlib
import hashlib
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
COLLECTED_MIN = 8
PASSED_MIN = 8
ASSERT_MIN = 6
TEST_FUNCS_MIN = 3
SERVICE_TEST_FUNCS_MIN = 2

CASE_IDS = (
    ["T%02d" % index for index in range(1, 20)]
    + ["EN%d" % index for index in range(1, 7)]
    + ["I%d" % index for index in range(1, 14)]
)

# 11 个基线文件（逐字节起点）。来源：包内 baseline/ 实算；组合摘要 b9bb24d1...（见模块 docstring）。
BASELINE_SHA256 = {
    "AGENTS.md": "ef20cdca0d6c43dbb5038449c90a972d44837e4b9ddc17e074f994d5eed669a3",
    "README.md": "5b4313609e4a28b61b43cd7b58ead2b99866284e532c68b79983cd3698213a5a",
    "conftest.py": "edd7cea37c657fb322cdee3038ca9aed35f40c7657a0faacb6640d6de9b050e7",
    "pytest.ini": "fd1c0f9fadf99a0af117f9f17fd7276f06d577e80fd530652978a1ff54aa71cc",
    "src/shop/__init__.py": "d7eef7b6e4db6622675782550c664ef2ef3c2ff9e8de8845cc0e9f4af4b44ad1",
    "src/shop/order_controller.py": (
        "e017c95714e14973bde434902dac0aa33025a73c5b78e4a0a23318f0b3755a6c"
    ),
    "src/shop/order_repository.py": (
        "035bf0b5e5697e140c9fb17bf6352543d4b81811efc5d4c2ba07d59e139e8afe"
    ),
    "src/shop/order_service.py": (
        "080664ff694aad5cb1f50842ae715d72698e40031b97512ddf7328110700fcbe"
    ),
    "tests/test_order_controller.py": (
        "4ac351e0ce611989044e74f2909c856de1e199e921602ab4fe6a874cecc7d069"
    ),
    "tests/test_order_repository.py": (
        "da03e49dcda46d1ccb8a053fc3a2815db48b7f0f76a55a2150e20ec2f4e3f668"
    ),
    "tests/test_order_service.py": (
        "91fa0e15a1bfaf74827bd11e77dbbef0490841205cd67ab6e4b00056c57aaf5f"
    ),
}

# 基线里允许改写的 3 个既有文件（allowed-writes 与 baseline 的交集）。
MODIFIABLE_BASELINE = frozenset(
    {"README.md", "src/shop/order_repository.py", "tests/test_order_repository.py"}
)

# 冻结文件 = 基线 11 - 可改写 3 = 8（I5 逐字节校验这 8 个）。
FROZEN_BASELINE = {
    rel: digest for rel, digest in BASELINE_SHA256.items() if rel not in MODIFIABLE_BASELINE
}

# 任务要创建（基线里必须没有）的 2 个文件。
NEW_PATHS = frozenset({"docs/fix-notes.md", "tests/test_order_service_copy.py"})

# 允许写 5 条 = 基线可改写 3 + 新建 2。
ALLOWED_WRITES = frozenset(MODIFIABLE_BASELINE) | NEW_PATHS

# 最终树的 13 个声明路径 = 11 基线 + 2 新建。
EXPECTED_PATHS = frozenset(BASELINE_SHA256) | NEW_PATHS

IGNORED_SEGMENTS = frozenset({".policy", "__pycache__", ".pytest_cache", ".ruff_cache"})
IGNORED_PREFIXES = ("pytest-cache-files-",)

FIX_NOTES_HEADINGS = ("## 根因", "## 修法", "## 验证")
README_SECTION = "## 跑测试"

# 内嵌的 10 个基线文件源码（除 AGENTS.md）：EN5 / EN6 用其中 9 个重建基线树，
# README.md 供 T19 比对「跑测试」一节；AGENTS.md 与执行无关，不嵌（I5 / I7 用逐字节摘要判）。
_BASELINE_SOURCES_JSON = r"""{
  "README.md": "# demo-shop\n\n订单示例项目：用于「受治工作区 vs 自由工作区」对比测试的**同一份起点**。\n\n## 结构\n\n| 路径 | 层 | 职责 |\n| --- | --- | --- |\n| `src/shop/order_controller.py` | 入口 | 只转发，不直接访问数据层 |\n| `src/shop/order_service.py` | 业务 | 入口层到数据层之间唯一的通道 |\n| `src/shop/order_repository.py` | 数据 | 只管存取 |\n| `tests/` | 测试 | 每个生产文件一个同名测试 |\n\n## 跑测试\n\n```powershell\npython -m pytest -q\n```\n\n（`conftest.py` 把 `src` 加进导入路径，因此不必安装这个项目。）\n\n## 这份项目为什么长这样\n\n- 它是**三层贯通**的结构，改动一个功能通常要动三个文件——于是\"受治\"与\"不受治\"的差别\n  会在同一次任务里反复出现，而不是只出现一次；\n- 每个生产文件都有同名测试：测试验证器按\"相关测试\"选择要跑哪些用例，没有测试的文件会被\n  `TESTING-001` 判成\"缺少对应测试\"；\n- 所有文件都符合规则要求（docstring、lint、分层）——**起点是干净的**，所以在它上面被拦下的\n  改动一定是这次改动带来的，不是历史欠账。\n",
  "conftest.py": "\"\"\"把 src 加入导入路径，让 tests/ 能 import shop。\"\"\"\n\nimport sys\nfrom pathlib import Path\n\nSRC = Path(__file__).resolve().parent / \"src\"\nif str(SRC) not in sys.path:\n    sys.path.insert(0, str(SRC))\n",
  "pytest.ini": "; 这个文件让\"在项目根目录跑 pytest\"有确定含义：rootdir 就是本项目，\n; testpaths 是本项目的 tests/，导入路径里有 src/。\n; conftest.py 同时保留：验证器路径用 -c <平台的 validation/pytest.ini> 调 pytest，\n; 那份配置不会读到这里，导入路径只能靠 conftest.py。\n[pytest]\ntestpaths = tests\npythonpath = src\n",
  "src/shop/__init__.py": "\"\"\"订单示例包。\"\"\"\n",
  "src/shop/order_controller.py": "\"\"\"订单入口层。\"\"\"\n\nfrom shop.order_service import OrderService\n\n\nclass OrderController:\n    \"\"\"订单入口。\"\"\"\n\n    def __init__(self, service: OrderService | None = None) -> None:\n        self.service = service or OrderService()\n\n    def create(self, payload: dict) -> dict:\n        \"\"\"创建订单。\"\"\"\n        return self.service.create(payload)\n\n    def listing(self) -> list[dict]:\n        \"\"\"列出订单。\"\"\"\n        return self.service.listing()\n",
  "src/shop/order_repository.py": "\"\"\"订单存储层。\"\"\"\n\n\nclass OrderRepository:\n    \"\"\"内存订单表。\"\"\"\n\n    def __init__(self) -> None:\n        self._rows: list[dict] = []\n\n    def insert(self, payload: dict) -> dict:\n        \"\"\"写入一条订单，返回副本。\"\"\"\n        self._rows.append(payload)\n        return payload\n\n    def listing(self) -> list[dict]:\n        \"\"\"返回全部订单的副本。\"\"\"\n        return [dict(row) for row in self._rows]\n",
  "src/shop/order_service.py": "\"\"\"订单业务层。\"\"\"\n\nfrom shop.order_repository import OrderRepository\n\n\nclass OrderService:\n    \"\"\"订单用例。\"\"\"\n\n    def __init__(self, repository: OrderRepository | None = None) -> None:\n        self.repository = repository or OrderRepository()\n\n    def create(self, payload: dict) -> dict:\n        \"\"\"创建一条订单。\"\"\"\n        return self.repository.insert(payload)\n\n    def listing(self) -> list[dict]:\n        \"\"\"列出全部订单。\"\"\"\n        return self.repository.listing()\n",
  "tests/test_order_controller.py": "\"\"\"order_controller 的用例。\"\"\"\n\nfrom shop.order_controller import OrderController\n\n\ndef test_controller_delegates_to_service() -> None:\n    \"\"\"入口层只做转发。\"\"\"\n    controller = OrderController()\n    assert controller.create({\"id\": 7}) == {\"id\": 7}\n    assert controller.listing() == [{\"id\": 7}]\n",
  "tests/test_order_repository.py": "\"\"\"order_repository 的用例。\"\"\"\n\nfrom shop.order_repository import OrderRepository\n\n\ndef test_insert_returns_a_copy() -> None:\n    \"\"\"写入返回副本：改它不影响已存的行。\"\"\"\n    repository = OrderRepository()\n    row = repository.insert({\"id\": 1})\n    row[\"id\"] = 2\n    assert repository.listing() == [{\"id\": 1}]\n\n\ndef test_listing_returns_copies() -> None:\n    \"\"\"listing 返回副本：改入参、改返回的列表都不影响已存的行。\"\"\"\n    repository = OrderRepository()\n    payload = {\"id\": 1}\n    repository.insert(payload)\n    payload[\"id\"] = 2\n    first = repository.listing()\n    first[0][\"id\"] = 3\n    second = repository.listing()\n    assert second == [{\"id\": 1}]\n    assert second is not first\n",
  "tests/test_order_service.py": "\"\"\"order_service 的用例。\"\"\"\n\nfrom shop.order_service import OrderService\n\n\ndef test_create_goes_through_repository() -> None:\n    \"\"\"create 把订单交给 repository。\"\"\"\n    service = OrderService()\n    assert service.create({\"id\": 1}) == {\"id\": 1}\n    assert service.listing() == [{\"id\": 1}]\n"
}"""

# 只读语义探针：在树副本里由子进程执行，输出 {"checks": {name: {ok, detail}}}。
# C01-C13 判「修复后的副本语义」，A01-A03 判「基线别名 bug 还在（构造证明）」。
PROBE_SOURCE = r'''"""Read-only semantics probe for the bank-bugfix task tree."""
import json
import sys
from pathlib import Path


def main() -> int:
    """Run every probe check and print one JSON object."""
    root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root / "src"))
    checks = {}

    def record(name):
        def wrapper(function):
            try:
                function()
            except AssertionError as exc:
                checks[name] = {"ok": False, "detail": str(exc)[:200]}
            except BaseException as exc:  # noqa: BLE001 - 单条失败不能终止整轮
                checks[name] = {
                    "ok": False,
                    "detail": type(exc).__name__ + ": " + str(exc)[:160],
                }
            else:
                checks[name] = {"ok": True, "detail": "ok"}
            return function

        return wrapper

    from shop.order_controller import OrderController
    from shop.order_repository import OrderRepository
    from shop.order_service import OrderService

    @record("C01")
    def _c01() -> None:
        payload = {"id": 1}
        row = OrderRepository().insert(payload)
        assert isinstance(row, dict), "insert did not return a dict: %r" % (row,)
        assert row == payload, "insert return value differs from the payload: %r" % (row,)
        assert row is not payload, "insert returned the caller's dict itself"

    @record("C02")
    def _c02() -> None:
        repository = OrderRepository()
        row = repository.insert({"id": 1})
        row["id"] = 2
        assert repository.listing() == [{"id": 1}], (
            "mutating insert()'s return value changed listing(): %r"
            % (repository.listing(),)
        )

    @record("C03")
    def _c03() -> None:
        repository = OrderRepository()
        payload = {"id": 1}
        repository.insert(payload)
        payload["id"] = 2
        assert repository.listing() == [{"id": 1}], (
            "mutating the payload after insert changed listing(): %r"
            % (repository.listing(),)
        )

    @record("C04")
    def _c04() -> None:
        repository = OrderRepository()
        payload = {"id": 1}
        row = repository.insert(payload)
        rows = getattr(repository, "_rows", None)
        assert isinstance(rows, list), "internal list _rows is missing (declared interface)"
        assert rows, "internal list _rows is empty after one insert"
        assert rows[-1] == payload, "stored row content differs: %r" % (rows[-1],)
        assert row is not rows[-1], "insert returned the internal row itself"

    @record("C05")
    def _c05() -> None:
        repository = OrderRepository()
        repository.insert({"id": 1})
        first = repository.listing()
        second = repository.listing()
        assert first == second, "two listing() calls are not equal: %r vs %r" % (first, second)
        assert first is not second, "listing() returned the same list object twice"
        assert first[0] is not second[0], "listing() returned the same element dict twice"

    @record("C06")
    def _c06() -> None:
        repository = OrderRepository()
        repository.insert({"id": 1})
        first = repository.listing()
        first[0]["id"] = 9
        assert repository.listing() == [{"id": 1}], (
            "mutating a listing() element changed the store: %r" % (repository.listing(),)
        )

    @record("C07")
    def _c07() -> None:
        repository = OrderRepository()
        first_input = {"id": 1}
        second_input = {"id": 1}
        repository.insert(first_input)
        repository.insert(second_input)
        rows = getattr(repository, "_rows", None)
        assert isinstance(rows, list), "internal list _rows is missing (declared interface)"
        assert len(rows) == 2, "_rows does not hold 2 rows after 2 inserts: %r" % (rows,)
        assert rows[0] == rows[1] == {"id": 1}, "row content differs: %r" % (rows,)
        assert rows[0] is not rows[1], "two inserts share the same internal dict"
        first_input["id"] = 2
        second_input["id"] = 3
        assert repository.listing() == [{"id": 1}, {"id": 1}], (
            "mutating the inputs changed the store: %r" % (repository.listing(),)
        )

    @record("C08")
    def _c08() -> None:
        repository = OrderRepository()
        expected = [{"id": index} for index in (1, 2, 3)]
        returned = [repository.insert(dict(item)) for item in expected]
        assert repository.listing() == expected, (
            "listing() differs from the inserted rows: %r" % (repository.listing(),)
        )
        rows = getattr(repository, "_rows", None)
        assert isinstance(rows, list), "internal list _rows is missing (declared interface)"
        assert len(rows) == 3, "_rows does not hold 3 rows: %r" % (rows,)
        for index, item in enumerate(expected):
            assert rows[index] == item, "internal row %d content differs" % index
        for left in range(3):
            assert returned[left] is not rows[left], (
                "insert #%d returned the internal row itself" % left
            )
            for right in range(left + 1, 3):
                assert rows[left] is not rows[right], (
                    "rows %d and %d share one dict" % (left, right)
                )

    @record("C09")
    def _c09() -> None:
        repository = OrderRepository()
        payload = {"id": 5, "note": "x", "amount": 100}
        row = repository.insert(payload)
        assert row == payload, "insert return value differs: %r" % (row,)
        assert set(row) == set(payload), "insert added or removed keys: %r" % (sorted(row),)
        rows = getattr(repository, "_rows", None)
        assert isinstance(rows, list) and rows, "internal list _rows is missing or empty"
        assert rows[-1] == payload, "stored row content differs: %r" % (rows[-1],)

    @record("C10")
    def _c10() -> None:
        repository = OrderRepository()
        rows = getattr(repository, "_rows", None)
        assert isinstance(rows, list), "internal list _rows is missing (declared interface)"
        assert rows == [], "internal list is not empty at construction: %r" % (rows,)
        first = repository.listing()
        second = repository.listing()
        assert first == [] and second == [], "empty listing() is not []: %r / %r" % (first, second)
        assert first is not second, "empty listing() returned the same list object twice"

    @record("C11")
    def _c11() -> None:
        service = OrderService()
        result = service.create({"id": 1})
        assert isinstance(result, dict), "create did not return a dict: %r" % (result,)
        assert result == {"id": 1}, "create return value differs: %r" % (result,)
        result["id"] = 2
        assert service.listing() == [{"id": 1}], (
            "mutating create()'s result changed listing(): %r" % (service.listing(),)
        )

    @record("C12")
    def _c12() -> None:
        service = OrderService()
        service.create({"id": 1})
        first = service.listing()
        second = service.listing()
        assert first == second, "two service listing() calls are not equal: %r vs %r" % (
            first,
            second,
        )
        assert first is not second, "service listing() returned the same list object twice"
        assert first[0] is not second[0], "service listing() returned the same element dict twice"

    @record("C13")
    def _c13() -> None:
        controller = OrderController()
        result = controller.create({"id": 7})
        assert result == {"id": 7}, "controller create return value differs: %r" % (result,)
        result["id"] = 8
        assert controller.listing() == [{"id": 7}], (
            "mutating the controller result changed listing(): %r" % (controller.listing(),)
        )
        first = controller.listing()
        second = controller.listing()
        assert first == second and first is not second, "controller listing() is not a fresh list"

    @record("A01")
    def _a01() -> None:
        payload = {"id": 1}
        row = OrderRepository().insert(payload)
        assert row is payload, "insert did not return the caller's dict (no alias on return)"

    @record("A02")
    def _a02() -> None:
        repository = OrderRepository()
        payload = {"id": 1}
        repository.insert(payload)
        payload["id"] = 2
        assert repository.listing() == [{"id": 2}], (
            "mutating the payload after insert did not reach the store"
        )

    @record("A03")
    def _a03() -> None:
        repository = OrderRepository()
        row = repository.insert({"id": 1})
        row["id"] = 3
        assert repository.listing() == [{"id": 3}], (
            "mutating insert()'s return value did not reach the store"
        )

    sys.stdout.write(json.dumps({"checks": checks}, ensure_ascii=False, sort_keys=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

# 变异体：I8-I11 在树副本上把实现改成歪法，断言同款探针必须报 fail。
# 形态 = (方法名, 方法体源码行；缩进由 _method_body 统一加 4 空格)。
MUTATIONS = {
    "original": (
        "insert",
        [
            '"""写入一条订单，返回副本。"""',
            "self._rows.append(payload)",
            "return payload",
        ],
    ),
    "half": (
        "insert",
        [
            '"""写入一条订单，返回副本。"""',
            "self._rows.append(payload)",
            "return dict(payload)",
        ],
    ),
    "clear": (
        "insert",
        [
            '"""写入一条订单，返回副本。"""',
            "self._rows.clear()",
            "row = dict(payload)",
            "self._rows.append(row)",
            "return dict(row)",
        ],
    ),
    "listing": (
        "listing",
        [
            '"""返回全部订单的副本。"""',
            "return self._rows",
        ],
    ),
}

TREE: "Path | None" = None
_SCRUB_ROOTS: "list[Path]" = []
_COPY_HOLDER: "Path | None" = None
_SHARED_COPY: "Path | None" = None
_SUBPROCESS_TMP: "Path | None" = None
_PROBE_PATH: "Path | None" = None
_PROBE_CHECKS: "dict[str, dict] | None" = None
_PYTEST_FULL: "subprocess.CompletedProcess[str] | None" = None
_COLLECT_RUN: "subprocess.CompletedProcess[str] | None" = None
_BASELINE_TREE: "Path | None" = None
_BASELINE_PROBE: "dict[str, dict] | None" = None


def _baseline_sources() -> "dict[str, str]":
    """内嵌的 9 个基线文件源码（EN5/EN6 的重建材料）。"""
    return json.loads(_BASELINE_SOURCES_JSON)


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
    """临时副本的父目录：优先 <cwd>/.tmp，退到树旁与系统 temp；绝不落在被评树内。

    每个候选都**真写一次**才算可用：有的沙箱允许 mkdir 但拒绝写入，
    只探测 mkdir 会把「写不了」当成可用。
    """
    override = os.environ.get("BANK_TASK_TMPDIR")
    candidates: "list[Path]" = []
    if override:
        candidates.append(Path(override))
    else:
        candidates.append(Path.cwd() / ".tmp")
        if TREE is not None:
            candidates.append(Path(TREE).parent / ".tmp")
        candidates.append(Path(tempfile.gettempdir()))
    for candidate in candidates:
        probe = candidate / "bank-bugfix-hidden-runner"
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


def _ignore_artifacts(_directory: str, names: "list[str]") -> "set[str]":
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
        _SCRUB_ROOTS.append(candidate)
        return candidate
    raise RuntimeError("cannot create a temporary holder")


def _new_copy(prefix: str) -> Path:
    """被评树的一个新副本；退出时整棵删掉。"""
    assert TREE is not None
    target = _holder(prefix) / "tree"
    shutil.copytree(TREE, target, ignore=_ignore_artifacts)
    return target


def _shared_copy() -> Path:
    """所有「只读执行」共用的一份副本（pytest / 探针）。"""
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


def _base_env() -> "dict[str, str]":
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
    args: "list[str]", cwd: Path, env: "dict[str, str] | None" = None
) -> "subprocess.CompletedProcess[str]":
    """在副本里跑一条命令；解释器 = 运行 runner 的 sys.executable；超时 60 秒。"""
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
_COUNT = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed|deselected)")
_COLLECTED = re.compile(r"(\d+)\s+tests?\s+collected")


def _scrub(text: str) -> str:
    """脱敏：删掉被评树根、临时副本根、其余盘符绝对路径与耗时。"""
    cleaned = str(text)
    roots: "list[str]" = []
    if TREE is not None:
        roots.append(str(TREE))
    for root in _SCRUB_ROOTS:
        roots.append(str(root))
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


def _counts(text: str) -> "dict[str, int]":
    """从 pytest 输出里抽 summary 计数（-q 只有一行 summary）。"""
    counts: "dict[str, int]" = {}
    for match in _COUNT.finditer(text):
        key = "error" if match.group(2) == "errors" else match.group(2)
        counts[key] = counts.get(key, 0) + int(match.group(1))
    return counts


def _summary_text(counts: "dict[str, int]") -> str:
    keys = ("passed", "failed", "error", "skipped", "xfailed")
    return ", ".join("%d %s" % (counts[key], key) for key in keys if counts.get(key))


def _collected_count(text: str) -> int:
    match = _COLLECTED.search(text)
    if match:
        return int(match.group(1))
    return sum(1 for line in text.splitlines() if "::" in line and line.strip())


# ---------------------------------------------------------------------------
# 树内读取 / AST / 探针
# ---------------------------------------------------------------------------
def _read_text(rel: str) -> str:
    assert TREE is not None
    path = TREE / rel
    if not path.is_file():
        raise AssertionError(rel + " is missing from the tree")
    return path.read_text(encoding="utf-8")


def _parse_tree_file(rel: str) -> ast.Module:
    return ast.parse(_read_text(rel), filename=rel)


def _tree_files() -> "list[str]":
    assert TREE is not None
    found: "list[str]" = []
    for path in TREE.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(TREE).parts
        if any(part in IGNORED_SEGMENTS or part.startswith(IGNORED_PREFIXES) for part in parts):
            continue
        if path.name.endswith(".pyc"):
            continue
        found.append("/".join(parts))
    return sorted(found)


def _find_class(module: ast.Module, name: str) -> "ast.ClassDef | None":
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _find_function(module: ast.Module, name: str) -> "ast.FunctionDef | None":
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _find_method(module: ast.Module, class_name: str, method: str) -> "ast.FunctionDef | None":
    node = _find_class(module, class_name)
    if node is None:
        return None
    for child in node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method:
            return child
    return None


def _is_docstring(stmt: "ast.stmt") -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _statements(module: ast.Module, name: str) -> "list[ast.stmt] | None":
    """顶层函数的语句序列（去掉函数 docstring）。"""
    function = _find_function(module, name)
    if function is None:
        return None
    body = list(function.body)
    if body and _is_docstring(body[0]):
        body = body[1:]
    return body


def _dump(statements: "list[ast.stmt]") -> "list[str]":
    return [ast.dump(stmt, annotate_fields=True, include_attributes=False) for stmt in statements]


_BASELINE_TEST_MODULE: "ast.Module | None" = None


def _baseline_test_module() -> ast.Module:
    global _BASELINE_TEST_MODULE
    if _BASELINE_TEST_MODULE is None:
        _BASELINE_TEST_MODULE = ast.parse(_baseline_sources()["tests/test_order_repository.py"])
    return _BASELINE_TEST_MODULE


def _prefix_ok(module: ast.Module, name: str, baseline_name: str) -> "tuple[bool, str]":
    """基线函数的语句序列是不是新函数体的有序前缀（原断言逐字仍在）。"""
    base = _statements(_baseline_test_module(), baseline_name)
    if base is None:
        raise RuntimeError("baseline test function %s is missing" % baseline_name)
    current = _statements(module, name)
    if current is None:
        return False, "test function %s is missing" % name
    if len(current) < len(base):
        return False, "%s has %d statement(s), the baseline has %d (an original statement was removed)" % (
            name,
            len(current),
            len(base),
        )
    for index, (wanted, actual) in enumerate(zip(_dump(base), _dump(current))):
        if wanted != actual:
            return False, "%s: statement %d differs from the baseline" % (name, index + 1)
    return True, "%s: baseline statements 1..%d preserved verbatim" % (name, len(base))


_SKIP_TEXT = re.compile(r"(^|\.)(mark\.)?(skip|skipif|xfail)($|\.|\()")


def _skip_markers(module: ast.Module) -> "list[str]":
    """测试文件里的 skip / skipif / xfail 标记（装饰器与调用两种形态）。"""
    markers: "list[str]" = []
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                text = ast.unparse(decorator)
                if _SKIP_TEXT.search(text):
                    markers.append(node.name + " -> " + text)
        elif isinstance(node, ast.Call):
            text = ast.unparse(node.func)
            if _SKIP_TEXT.search(text):
                markers.append("call " + text)
    return markers


def _assert_count(module: ast.Module) -> int:
    return sum(1 for node in ast.walk(module) if isinstance(node, ast.Assert))


def _inside_assert_count(function: "ast.FunctionDef") -> int:
    return sum(1 for node in ast.walk(function) if isinstance(node, ast.Assert))


def _test_functions(module: ast.Module) -> "list[ast.FunctionDef]":
    return [
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ]


def _method_body(lines: "list[str]") -> "list[ast.stmt]":
    source = "def _method():\n" + "".join("    " + line + "\n" for line in lines)
    return ast.parse(source).body[0].body


def _mutated_copy(prefix: str, mutation: str) -> Path:
    """把树副本里的 OrderRepository 改成一种歪法（I8-I11 用）。"""
    method, lines = MUTATIONS[mutation]
    root = _new_copy(prefix)
    target = root / "src" / "shop" / "order_repository.py"
    module = ast.parse(target.read_text(encoding="utf-8"))
    function = _find_method(module, "OrderRepository", method)
    if function is None:
        raise AssertionError("OrderRepository.%s is missing in the tree copy" % method)
    function.body = _method_body(lines)
    ast.fix_missing_locations(module)
    target.write_text(ast.unparse(module) + "\n", encoding="utf-8", newline="\n")
    return root


def _probe_script() -> Path:
    global _PROBE_PATH
    if _PROBE_PATH is None or not _PROBE_PATH.is_file():
        root = _holder("probe")
        script = root / "probe.py"
        script.write_text(PROBE_SOURCE, encoding="utf-8", newline="\n")
        _PROBE_PATH = script
    return _PROBE_PATH


def _probe(root: Path) -> "dict[str, dict]":
    """在 root 上跑语义探针；返回 {check: {ok, detail}}。"""
    result = _run([sys.executable, str(_probe_script()), str(root)], cwd=root)
    if result.returncode != 0:
        raise RuntimeError(
            "semantics probe exited with %d: %s" % (result.returncode, _tail(result.stderr))
        )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("semantics probe printed nothing")
    return json.loads(lines[-1])["checks"]


def _semantics() -> "dict[str, dict]":
    """被评树副本上的探针结果（只跑一次）。"""
    global _PROBE_CHECKS
    if _PROBE_CHECKS is None:
        _PROBE_CHECKS = _probe(_shared_copy())
    return _PROBE_CHECKS


def _check(name: str) -> "tuple[bool, str]":
    checks = _semantics()
    item = checks.get(name)
    if item is None:
        raise AssertionError("probe check %s is missing (the module did not import)" % name)
    return bool(item["ok"]), str(item["detail"])


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _polarity(passed: bool, detail: str) -> "tuple[bool, str]":
    return bool(passed), detail


# ---------------------------------------------------------------------------
# pytest 入口
# ---------------------------------------------------------------------------
def _pytest_args(extra: "list[str]") -> "list[str]":
    return [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"] + extra


def _pytest_full() -> "subprocess.CompletedProcess[str]":
    global _PYTEST_FULL
    if _PYTEST_FULL is None:
        _PYTEST_FULL = _run(_pytest_args(["-q"]), cwd=_shared_copy())
    return _PYTEST_FULL


def _collect_run() -> "subprocess.CompletedProcess[str]":
    global _COLLECT_RUN
    if _COLLECT_RUN is None:
        _COLLECT_RUN = _run(_pytest_args(["-q", "--collect-only"]), cwd=_shared_copy())
    return _COLLECT_RUN


def _baseline_tree() -> Path:
    """EN5/EN6：用内嵌的 9 个基线文件重建一棵临时基线树。"""
    global _BASELINE_TREE
    if _BASELINE_TREE is None or not _BASELINE_TREE.is_dir():
        root = _holder("baseline")
        for rel, text in sorted(_baseline_sources().items()):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        _BASELINE_TREE = root
    return _BASELINE_TREE


def _baseline_probe() -> "dict[str, dict]":
    global _BASELINE_PROBE
    if _BASELINE_PROBE is None:
        _BASELINE_PROBE = _probe(_baseline_tree())
    return _BASELINE_PROBE


# ---------------------------------------------------------------------------
# 1 T 组：最终树上的行为（19 条）
# ---------------------------------------------------------------------------
def _t01() -> "tuple[bool, str]":
    return _check("C01")


def _t02() -> "tuple[bool, str]":
    return _check("C02")


def _t03() -> "tuple[bool, str]":
    return _check("C03")


def _t04() -> "tuple[bool, str]":
    return _check("C04")


def _t05() -> "tuple[bool, str]":
    return _check("C05")


def _t06() -> "tuple[bool, str]":
    return _check("C06")


def _t07() -> "tuple[bool, str]":
    return _check("C07")


def _t08() -> "tuple[bool, str]":
    return _check("C08")


def _t09() -> "tuple[bool, str]":
    return _check("C09")


def _t10() -> "tuple[bool, str]":
    return _check("C10")


def _t11() -> "tuple[bool, str]":
    return _check("C11")


def _t12() -> "tuple[bool, str]":
    return _check("C12")


def _t13() -> "tuple[bool, str]":
    return _check("C13")


def _t14() -> "tuple[bool, str]":
    module = _parse_tree_file("tests/test_order_repository.py")
    passed, detail = _prefix_ok(module, "test_insert_returns_a_copy", "test_insert_returns_a_copy")
    _expect(passed, detail)
    return _polarity(True, detail)


def _t15() -> "tuple[bool, str]":
    module = _parse_tree_file("tests/test_order_repository.py")
    passed, detail = _prefix_ok(module, "test_listing_returns_copies", "test_listing_returns_copies")
    _expect(passed, detail)
    return _polarity(True, detail)


def _t16() -> "tuple[bool, str]":
    module = _parse_tree_file("tests/test_order_repository.py")
    asserts = _assert_count(module)
    functions = _test_functions(module)
    base_names = frozenset(
        node.name
        for node in _baseline_test_module().body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )
    fresh = [node.name for node in functions if node.name not in base_names]
    _expect(
        asserts >= ASSERT_MIN,
        "tests/test_order_repository.py has %d assert(s), needs >= %d" % (asserts, ASSERT_MIN),
    )
    _expect(
        len(functions) >= TEST_FUNCS_MIN,
        "tests/test_order_repository.py has %d test function(s), needs >= %d"
        % (len(functions), TEST_FUNCS_MIN),
    )
    _expect(bool(fresh), "no new test function was added to tests/test_order_repository.py")
    return _polarity(
        True,
        "%d asserts, %d test functions, new: %s" % (asserts, len(functions), ", ".join(sorted(fresh))),
    )


def _t17() -> "tuple[bool, str]":
    module = _parse_tree_file("tests/test_order_service_copy.py")
    functions = _test_functions(module)
    _expect(
        len(functions) >= SERVICE_TEST_FUNCS_MIN,
        "tests/test_order_service_copy.py has %d test function(s), needs >= %d"
        % (len(functions), SERVICE_TEST_FUNCS_MIN),
    )
    empty = [node.name for node in functions if _inside_assert_count(node) < 1]
    _expect(not empty, "test function(s) without any assert: " + ", ".join(empty))
    markers = _skip_markers(module)
    _expect(not markers, "skip/xfail markers: " + "; ".join(markers[:4]))
    return _polarity(True, "%d test functions, each asserting, no skip markers" % len(functions))


def _doc_sections(text: str) -> "dict[str, list[str]]":
    """按二级标题切分 markdown；返回 {标题行: 正文行}。"""
    sections: "dict[str, list[str]]" = {}
    current: "str | None" = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line.rstrip()
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def _t18() -> "tuple[bool, str]":
    text = _read_text("docs/fix-notes.md")
    sections = _doc_sections(text)
    problems: "list[str]" = []
    for heading in FIX_NOTES_HEADINGS:
        body = sections.get(heading)
        if body is None:
            problems.append("missing heading " + heading)
            continue
        if not any(line.strip() for line in body):
            problems.append("empty section " + heading)
    _expect(not problems, "docs/fix-notes.md: " + "; ".join(problems))
    return _polarity(True, "3/3 headings present and non-empty")


def _t19() -> "tuple[bool, str]":
    baseline = _doc_sections(_baseline_sources()["README.md"])
    current = _doc_sections(_read_text("README.md"))
    problems: "list[str]" = []
    if README_SECTION not in current:
        problems.append("README.md lost the %r section" % README_SECTION)
    else:
        if " ".join(current[README_SECTION]) == " ".join(baseline[README_SECTION]):
            problems.append("README.md's %r section was not updated" % README_SECTION)
        body = "\n".join(current[README_SECTION])
        red = any(word in body for word in ("红", "失败", "failed", "FAILED"))
        green = any(word in body for word in ("绿", "通过", "passed", "PASSED"))
        if not red:
            problems.append("README.md's %r section does not mention the red starting point"
                            % README_SECTION)
        if not green:
            problems.append("README.md's %r section does not mention the expected green result"
                            % README_SECTION)
    for heading, body in baseline.items():
        if heading == README_SECTION:
            continue
        if heading not in current:
            problems.append("README.md lost section " + heading)
        elif " ".join(current[heading]) != " ".join(body):
            problems.append("README.md section %s was changed" % heading)
    _expect(not problems, "; ".join(problems))
    return _polarity(True, "%r updated, other baseline sections untouched" % README_SECTION)


# ---------------------------------------------------------------------------
# 2 EN 组：树执行（6 条）
# ---------------------------------------------------------------------------
def _en1() -> "tuple[bool, str]":
    result = _pytest_full()
    _expect(
        result.returncode == 0,
        "pytest exit=%d tail=%s" % (result.returncode, _tail(result.stdout)),
    )
    return _polarity(True, "pytest exit=0")


def _en2() -> "tuple[bool, str]":
    result = _run(
        _pytest_args(
            [
                "-q",
                "tests/test_order_repository.py::test_insert_returns_a_copy",
                "tests/test_order_repository.py::test_listing_returns_copies",
            ]
        ),
        cwd=_shared_copy(),
    )
    counts = _counts(result.stdout)
    _expect(
        result.returncode == 0,
        "pytest exit=%d summary=(%s) tail=%s"
        % (result.returncode, _summary_text(counts), _tail(result.stdout)),
    )
    _expect(
        counts.get("passed", 0) == 2 and not counts.get("failed") and not counts.get("error"),
        "the two original tests did not both pass: (%s)" % _summary_text(counts),
    )
    return _polarity(True, "both original test ids passed")


def _en3() -> "tuple[bool, str]":
    result = _collect_run()
    _expect(
        result.returncode == 0,
        "collect-only exit=%d tail=%s" % (result.returncode, _tail(result.stdout)),
    )
    collected = _collected_count(result.stdout)
    _expect(
        collected >= COLLECTED_MIN,
        "collected=%d < %d" % (collected, COLLECTED_MIN),
    )
    return _polarity(True, "collected=%d >= %d" % (collected, COLLECTED_MIN))


def _en4() -> "tuple[bool, str]":
    result = _pytest_full()
    counts = _counts(result.stdout)
    _expect(
        result.returncode == 0,
        "pytest exit=%d summary=(%s) tail=%s"
        % (result.returncode, _summary_text(counts), _tail(result.stdout)),
    )
    _expect(not counts.get("failed"), "failed=%d" % counts.get("failed", 0))
    _expect(not counts.get("error"), "error=%d" % counts.get("error", 0))
    passed = counts.get("passed", 0)
    _expect(passed >= PASSED_MIN, "passed=%d < %d" % (passed, PASSED_MIN))
    return _polarity(True, "summary=(%s)" % _summary_text(counts))


def _en5() -> "tuple[bool, str]":
    result = _run(_pytest_args(["-q", "--tb=no"]), cwd=_baseline_tree())
    counts = _counts(result.stdout)
    _expect(
        result.returncode == 1,
        "the reconstructed baseline exited %d (expected 1); summary=(%s)"
        % (result.returncode, _summary_text(counts)),
    )
    _expect(
        counts.get("failed") == 2 and counts.get("passed") == 2,
        "reconstructed baseline summary=(%s), expected 2 failed, 2 passed"
        % _summary_text(counts),
    )
    missing = [
        name
        for name in ("test_insert_returns_a_copy", "test_listing_returns_copies")
        if "FAILED tests/test_order_repository.py::" + name not in result.stdout
    ]
    _expect(not missing, "not reported as FAILED: " + ", ".join(missing))
    return _polarity(True, "reconstructed baseline: 2 failed, 2 passed")


def _en6() -> "tuple[bool, str]":
    checks = _baseline_probe()
    problems: "list[str]" = []
    for name in ("A01", "A02", "A03"):
        item = checks.get(name)
        if item is None:
            problems.append(name + " missing")
        elif not item["ok"]:
            problems.append(name + " -> " + str(item["detail"]))
    _expect(not problems, "the reconstructed baseline shows no alias bug: " + "; ".join(problems))
    return _polarity(True, "baseline alias bug observable on all 3 probes")


# ---------------------------------------------------------------------------
# 3 I 组：接口 / 树形状 / 反向构造（13 条）
# ---------------------------------------------------------------------------
def _annotation(node: "ast.arg | ast.FunctionDef") -> str:
    """参数或函数签名的注解文本（FunctionDef 的返回注解在 returns 上）。"""
    annotation = node.annotation if isinstance(node, ast.arg) else node.returns
    return "" if annotation is None else ast.unparse(annotation)


def _i1() -> "tuple[bool, str]":
    module = _parse_tree_file("src/shop/order_repository.py")
    cls = _find_class(module, "OrderRepository")
    _expect(cls is not None, "class OrderRepository is missing")
    problems: "list[str]" = []
    init = _find_method(module, "OrderRepository", "__init__")
    if init is None:
        problems.append("__init__ is missing")
    else:
        if [arg.arg for arg in init.args.args] != ["self"]:
            problems.append("__init__ signature changed")
        if _annotation(init) != "None":
            problems.append("__init__ return annotation is %r, expected 'None'" % _annotation(init))
    insert = _find_method(module, "OrderRepository", "insert")
    if insert is None:
        problems.append("insert is missing")
    else:
        if [arg.arg for arg in insert.args.args] != ["self", "payload"]:
            problems.append("insert signature changed: %r"
                            % ([arg.arg for arg in insert.args.args],))
        if insert.args.args and _annotation(insert.args.args[-1]) != "dict":
            problems.append("insert payload annotation changed: %r"
                            % _annotation(insert.args.args[-1]))
        if _annotation(insert) != "dict":
            problems.append("insert return annotation is %r, expected 'dict'" % _annotation(insert))
    listing = _find_method(module, "OrderRepository", "listing")
    if listing is None:
        problems.append("listing is missing")
    else:
        if [arg.arg for arg in listing.args.args] != ["self"]:
            problems.append("listing signature changed: %r"
                            % ([arg.arg for arg in listing.args.args],))
        if _annotation(listing) != "list[dict]":
            problems.append("listing return annotation is %r, expected 'list[dict]'"
                            % _annotation(listing))
    _expect(not problems, "; ".join(problems))
    return _polarity(True, "OrderRepository / insert(self, payload: dict) -> dict / listing(self) -> list[dict]")


def _i2() -> "tuple[bool, str]":
    module = _parse_tree_file("src/shop/order_repository.py")
    problems: "list[str]" = []
    if not (ast.get_docstring(module) or "").strip():
        problems.append("module docstring is missing")
    for label, node in (
        ("class OrderRepository", _find_class(module, "OrderRepository")),
        ("insert", _find_method(module, "OrderRepository", "insert")),
        ("listing", _find_method(module, "OrderRepository", "listing")),
    ):
        if node is None:
            problems.append(label + " is missing")
        elif not (ast.get_docstring(node) or "").strip():
            problems.append(label + " docstring is missing")
    _expect(not problems, "; ".join(problems))
    return _polarity(True, "module / class / insert / listing docstrings present")


def _i3() -> "tuple[bool, str]":
    module = _parse_tree_file("src/shop/order_repository.py")
    problems: "list[str]" = []
    for method in ("insert", "listing"):
        function = _find_method(module, "OrderRepository", method)
        if function is None:
            problems.append(method + " is missing")
            continue
        for node in ast.walk(function):
            if isinstance(node, ast.Try):
                problems.append(method + " grew a try/except block")
            elif isinstance(node, ast.Raise):
                problems.append(method + " grew a raise statement")
    _expect(not problems, "; ".join(problems))
    return _polarity(True, "insert / listing have no new exception branches")


def _i4() -> "tuple[bool, str]":
    module = _parse_tree_file("src/shop/order_repository.py")
    problems: "list[str]" = []
    for node in module.body:
        if isinstance(node, ast.ImportFrom):
            if node.level:
                problems.append("relative import (level=%d)" % node.level)
                continue
            root = (node.module or "").split(".")[0]
            if root in {"shop"}:
                problems.append("project import: " + str(node.module))
            elif root not in sys.stdlib_module_names:
                problems.append("non-stdlib import: " + str(node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in {"shop"}:
                    problems.append("project import: " + alias.name)
                elif root not in sys.stdlib_module_names:
                    problems.append("non-stdlib import: " + alias.name)
    _expect(not problems, "; ".join(problems))
    return _polarity(True, "order_repository.py imports only the standard library")


def _i5() -> "tuple[bool, str]":
    problems: "list[str]" = []
    assert TREE is not None
    for rel, expected in sorted(FROZEN_BASELINE.items()):
        path = TREE / rel
        if not path.is_file():
            problems.append(rel + " missing")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            problems.append(rel + " changed")
    _expect(not problems, "frozen files: " + "; ".join(problems[:6]))
    return _polarity(True, "%d/%d frozen files unchanged" % (len(FROZEN_BASELINE), len(FROZEN_BASELINE)))


def _i6() -> "tuple[bool, str]":
    files = set(_tree_files())
    extra = sorted(files - EXPECTED_PATHS)
    _expect(not extra, "files outside the 13 declared paths: " + ", ".join(extra[:6]))
    problems: "list[str]" = []
    assert TREE is not None
    for rel in sorted(set(BASELINE_SHA256) & files):
        if rel in MODIFIABLE_BASELINE:
            continue
        digest = hashlib.sha256((TREE / rel).read_bytes()).hexdigest()
        if digest != BASELINE_SHA256[rel]:
            problems.append(rel + " changed but is not in allowed-writes")
    changed = sorted(
        rel
        for rel in MODIFIABLE_BASELINE
        if rel in files and hashlib.sha256((TREE / rel).read_bytes()).hexdigest()
        != BASELINE_SHA256[rel]
    )
    _expect(not problems, "; ".join(problems[:6]))
    _expect(len(files) <= len(EXPECTED_PATHS), "%d files, expected at most %d" % (len(files), len(EXPECTED_PATHS)))
    return _polarity(
        True,
        "%d files, change set %s within the 5 allowed writes" % (len(files), changed),
    )


def _i7() -> "tuple[bool, str]":
    missing = []
    assert TREE is not None
    for rel in sorted(BASELINE_SHA256) + sorted(NEW_PATHS):
        if not (TREE / rel).is_file():
            missing.append(rel)
    _expect(not missing, "missing files: " + ", ".join(missing))
    files = set(_tree_files())
    _expect(
        files == EXPECTED_PATHS,
        "the final tree is %d file(s), expected the 13 declared paths (off by %d)"
        % (len(files), len(files) - len(EXPECTED_PATHS)),
    )
    return _polarity(True, "11 baseline + 2 created = 13 files")


def _reverse(problems: "list[str]", detail: str) -> "tuple[bool, str]":
    _expect(not problems, "; ".join(problems))
    return _polarity(True, detail)


def _i8() -> "tuple[bool, str]":
    checks = _probe(_mutated_copy("mutation-original", "original"))
    problems = [
        name + " did not fail (" + str(checks.get(name, {}).get("detail", "missing")) + ")"
        for name in ("C01", "C02", "C03", "C04")
        if checks.get(name, {}).get("ok") is not False
    ]
    return _reverse(problems, "the original alias bug is rejected by C01-C04")


def _i9() -> "tuple[bool, str]":
    checks = _probe(_mutated_copy("mutation-half", "half"))
    problems: "list[str]" = []
    if checks.get("C03", {}).get("ok") is not False:
        problems.append("C03 did not fail on the half fix (payload aliasing is not caught)")
    if checks.get("C02", {}).get("ok") is not True:
        problems.append("C02 failed on the half fix (the probe is not discriminating)")
    return _reverse(problems, "half fix -> C03 fails, C02 still holds")


def _i10() -> "tuple[bool, str]":
    checks = _probe(_mutated_copy("mutation-clear", "clear"))
    problems: "list[str]" = []
    for name in ("C07", "C08"):
        if checks.get(name, {}).get("ok") is not False:
            problems.append(name + " did not fail on the clear-then-write mutation")
    if checks.get("C02", {}).get("ok") is not True:
        problems.append("C02 failed on the clear-then-write mutation (probe not discriminating)")
    return _reverse(problems, "clear-then-write -> C07/C08 fail, C02 still holds")


def _i11() -> "tuple[bool, str]":
    checks = _probe(_mutated_copy("mutation-listing", "listing"))
    problems = [
        name + " did not fail on 'listing returns the internal list'"
        for name in ("C05", "C06", "C10")
        if checks.get(name, {}).get("ok") is not False
    ]
    return _reverse(problems, "listing() returning the internal list is rejected by C05/C06/C10")


def _weakened_test_module() -> "tuple[ast.Module, str]":
    """删掉某个用例里的全部 assert 的源码（I12 的削弱样本）。"""
    module = _parse_tree_file("tests/test_order_repository.py")
    target = _find_function(module, "test_insert_returns_a_copy")
    if target is None:
        candidates = [node for node in _test_functions(module) if _inside_assert_count(node) > 0]
        if not candidates:
            raise AssertionError("tests/test_order_repository.py has no asserting test to weaken")
        target = candidates[0]
    before = len(target.body)
    target.body = [stmt for stmt in target.body if not isinstance(stmt, ast.Assert)]
    _expect(len(target.body) < before, "the weakened sample still has the same body")
    ast.fix_missing_locations(module)
    return ast.parse(ast.unparse(module)), target.name


def _i12() -> "tuple[bool, str]":
    module, name = _weakened_test_module()
    passed, detail = _prefix_ok(module, name, "test_insert_returns_a_copy")
    _expect(not passed, "a weakened %s was accepted by the verbatim-prefix check" % name)
    return _polarity(True, "weakened %s rejected: %s" % (name, detail))


def _i13() -> "tuple[bool, str]":
    module = _parse_tree_file("tests/test_order_repository.py")
    functions = _test_functions(module)
    _expect(bool(functions), "tests/test_order_repository.py has no test function")
    decorator = ast.parse("pytest.mark.skip", mode="eval").body
    functions[0].decorator_list.insert(0, decorator)
    ast.fix_missing_locations(module)
    sample = ast.parse(ast.unparse(module))
    markers = _skip_markers(sample)
    _expect(bool(markers), "a @pytest.mark.skip decorator was not detected")
    return _polarity(True, "skip marker detected: " + markers[0])


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
    ("EN1", _en1),
    ("EN2", _en2),
    ("EN3", _en3),
    ("EN4", _en4),
    ("EN5", _en5),
    ("EN6", _en6),
    ("I1", _i1),
    ("I2", _i2),
    ("I3", _i3),
    ("I4", _i4),
    ("I5", _i5),
    ("I6", _i6),
    ("I7", _i7),
    ("I8", _i8),
    ("I9", _i9),
    ("I10", _i10),
    ("I11", _i11),
    ("I12", _i12),
    ("I13", _i13),
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
    """跑完 38 条并打印唯一 JSON 载荷；0 全过 / 1 有失败 / 2 跑不成。"""
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
        return _cannot_run("case registry is not T01..T19 / EN1..EN6 / I1..I13")

    try:
        _shared_copy()
        _temp_root()
    except (OSError, RuntimeError) as exc:
        return _cannot_run("cannot copy the evaluated tree: " + type(exc).__name__)

    cases: "list[dict]" = []
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
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
