"""tools/structure_metrics.py（A 维度 10 条结构谓词）的回归：口径、稳定字节与变异自证。

判据来自 readings/2026-10-19-D-gate2-treatment.md §4.2 与 AGENTS 第 19/45/55 条：

- 每条谓词必须**能红也能绿**：变异自证 = 在夹具树副本上制造缺陷 → 该谓词变红（并断言**具体的**
  证据条目）→ 撤回变异 → 全绿（第 45 条：自己的仪器也要能失败，且"修复前会红"要有实际断言）；
- --json 载荷是**输入的纯函数**：两次运行逐字节相同、无绝对路径、无时戳（第 19 条）；
- 版本轴 STRUCTURE_METRICS_SCHEMA_VERSION = "1.1"（第 55 条；1.0 = 首次建轴，1.1 = A4 口径修订）。

夹具树在 tests/fixtures/structure_metrics/clean（7 个 .py + layers.yaml + interfaces.yaml）：
一个三层订单样例，10 条谓词全绿。夹具文件刻意不叫 test_*.py——pytest 的 testpaths 是 tests/，
文件名匹配的模块才会被 import，而夹具只是被解析的样本。
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "structure_metrics" / "clean"


def _load():
    """按路径加载被测脚本（tools/ 不在包内）。"""

    spec = importlib.util.spec_from_file_location(
        "structure_metrics_under_test", REPO_ROOT / "tools" / "structure_metrics.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # 标准配方：exec 之前登记
    spec.loader.exec_module(module)
    return module


def _run(module, capsys, *argv):
    """跑一次 CLI，返回 (退出码, stdout, stderr)。"""

    code = module.run([str(item) for item in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _json_run(module, capsys, tree, *extra):
    """跑 --json 形态；成功路径不写 stderr。"""

    code, out, err = _run(
        module,
        capsys,
        "--workspace",
        tree,
        "--layers",
        Path(tree) / "layers.yaml",
        "--json",
        *extra,
    )
    assert err == "", err
    return code, out, json.loads(out)


def _by_id(payload):
    return {item["id"]: item for item in payload["predicates"]}


def _status(payload, identifier):
    return _by_id(payload)[identifier]["status"]


def _detail(payload, identifier):
    return _by_id(payload)[identifier]["detail"]


def _items(payload, identifier):
    return _detail(payload, identifier)["items"]


def _copy(tmp):
    """把干净的夹具树复制到临时目录：变异只改副本，夹具树本身逐字节不变。"""

    target = Path(tmp) / "tree"
    shutil.copytree(FIXTURE, target)
    return target


def _append(tree, relative, text):
    path = Path(tree) / relative
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8", newline="\n")


def _replace(tree, relative, old, new):
    path = Path(tree) / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, (relative, old)
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def _write(root, relative, text):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _synthetic(tmp, name, files):
    """写一棵合成的树（键 = 仓库相对路径，值 = 内容）；返回树根。"""

    root = Path(tmp) / name
    for relative, text in files.items():
        _write(root, relative, text)
    return root


def _if_chain(count):
    """一个含 count 个 if 的函数（圈复杂度 = 1 + count）。"""

    rows = ["def _chain(value: int) -> int:", '    """按阈值累加。"""', "", "    score = 0"]
    for index in range(count):
        rows.extend(["    if value > %d:" % index, "        score += 1"])
    rows.append("    return score")
    return "\n".join(rows) + "\n"


def _function_of(lines):
    """一个恰好 lines 行的函数（def + docstring + 若干 pass）。"""

    body = "\n".join(["    pass"] * (lines - 2))
    return 'def short_function() -> None:\n    """占位。"""\n' + body + "\n"


def _layers(*entries):
    return "".join("%s: %s\n" % (path, layer) for path, layer in entries)


# --------------------------------------------------------------------------- 稳定字节与形状


def test_the_same_input_is_byte_identical_and_has_no_absolute_path(capsys):
    """两次运行的 --json 逐字节相同；载荷里没有绝对路径、时戳与 run 标识（AGENTS 第 19 条）。"""

    module = _load()
    code, first, err = _run(
        module, capsys, "--workspace", FIXTURE, "--layers", FIXTURE / "layers.yaml", "--json"
    )
    assert (code, err) == (0, "")
    code, second, _err = _run(
        module, capsys, "--workspace", FIXTURE, "--layers", FIXTURE / "layers.yaml", "--json"
    )
    assert code == 0
    assert first == second
    payload = json.loads(first)
    # 键序稳定 = json.dumps(sort_keys=True) 的字节：这是"相同输入逐字节相同"的一半。
    assert first == json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    for forbidden in (str(REPO_ROOT), "C:\\", "\\\\", "generated_at", '"run"'):
        assert forbidden not in first
    scope = payload["workspace_scope"]
    assert scope["root"] == "."
    assert scope["files_digest"].startswith("sha256:")
    assert scope["layers"]["digest"].startswith("sha256:")
    assert payload["schema_version"] == module.STRUCTURE_METRICS_SCHEMA_VERSION == "1.1"
    assert list(payload) == ["predicates", "schema_version", "summary", "workspace_scope"]


def test_the_clean_fixture_tree_passes_all_ten_predicates(capsys):
    """干净夹具树上 10 条全绿、退出码 0，且每条谓词的计数是能看懂的（不是空壳）。"""

    module = _load()
    code, _out, payload = _json_run(module, capsys, FIXTURE)

    assert code == module.EXIT_PASS == 0
    assert payload["summary"] == {"passed": 10, "failed": 0}
    assert [(item["id"], item["name"]) for item in payload["predicates"]] == [
        ("A1", "分层方向"),
        ("A2", "依赖无环"),
        ("A3", "公开符号最小面"),
        ("A4", "组合根唯一"),
        ("A5", "函数复杂度"),
        ("A6", "文件/函数长度"),
        ("A7", "docstring 覆盖"),
        ("A8", "依赖扇出"),
        ("A9", "测试对应完备"),
        ("A10", "无动态执行"),
    ]
    assert all(item["status"] == "pass" for item in payload["predicates"])
    # 每条谓词都真的看到了东西：全绿不等于什么都没查。
    assert _detail(payload, "A1")["counts"]["edges_internal"] == 12
    assert _detail(payload, "A2")["counts"]["nodes"] == 7
    assert _detail(payload, "A3")["basis"] == "module_all"
    assert _detail(payload, "A4")["counts"]["root_instantiations"] == 6
    assert _detail(payload, "A5")["counts"]["functions"] == 12
    assert _detail(payload, "A7")["counts"]["definitions"] == 16
    assert _detail(payload, "A9")["counts"] == {
        "covered": 6,
        "production_files": 6,
        "test_files": 1,
        "violations": 0,
    }
    assert payload["workspace_scope"]["files_by_layer"] == {
        "composition": 1,
        "controller": 1,
        "model": 1,
        "other": 1,
        "repository": 1,
        "service": 1,
        "test": 1,
    }


# --------------------------------------------------------------------------- 变异自证（第 45 条）


def test_mutation_cycle_turns_a2_red_then_reverting_turns_it_green(tmp_root, capsys):
    """A2：给 repository 加一条指向 service 的 import ⇒ 出现环 ⇒ 红；撤回 ⇒ 绿。"""

    module = _load()
    tree = _copy(tmp_root)
    code, _out, payload = _json_run(module, capsys, tree)
    assert (code, _status(payload, "A2")) == (0, "pass")

    path = tree / "src/shop/order_repository.py"
    original = path.read_bytes()
    _append(tree, "src/shop/order_repository.py", "from shop.order_service import OrderService\n")

    code, _out, payload = _json_run(module, capsys, tree)
    assert code == module.EXIT_FAIL == 1
    assert _status(payload, "A2") == "fail"
    assert _items(payload, "A2") == [
        {"cycle": ["src/shop/order_repository.py", "src/shop/order_service.py"]}
    ]
    assert _detail(payload, "A2")["counts"]["cycles"] == 1

    path.write_bytes(original)
    code, _out, payload = _json_run(module, capsys, tree)
    assert code == 0
    assert payload["summary"] == {"passed": 10, "failed": 0}


def test_mutation_long_function_turns_a6_red_then_reverting_turns_it_green(tmp_root, capsys):
    """A6：加一个 55 行的函数 ⇒ 超 50 行 ⇒ 红；撤回 ⇒ 绿。"""

    module = _load()
    tree = _copy(tmp_root)
    code, _out, payload = _json_run(module, capsys, tree)
    assert (code, _status(payload, "A6")) == (0, "pass")
    assert _detail(payload, "A6")["counts"]["over_length_functions"] == 0

    path = tree / "src/shop/models.py"
    original = path.read_bytes()
    block = (
        "\n\ndef _mutation_long_function() -> int:\n"
        '    """变异：55 行的函数。"""\n\n'
        + "".join(["    total = 0\n" for _ in range(55)])
        + "    return 0\n"
    )
    _append(tree, "src/shop/models.py", block)

    code, _out, payload = _json_run(module, capsys, tree)
    assert code == module.EXIT_FAIL
    assert _status(payload, "A6") == "fail"
    items = _items(payload, "A6")
    assert len(items) == 1
    assert items[0]["path"] == "src/shop/models.py"
    assert items[0]["kind"] == "function"
    assert items[0]["qualified"] == "_mutation_long_function"
    # 行数口径：def 1 + docstring 1 + 空行 1 + 55 + return 1 = 59 行（> 50 才判红）。
    assert items[0]["lines"] == 59
    assert items[0]["lines"] > module.MAX_FUNCTION_LINES == 50
    assert _detail(payload, "A6")["counts"]["over_length_files"] == 0

    path.write_bytes(original)
    code, _out, payload = _json_run(module, capsys, tree)
    assert code == 0
    assert _status(payload, "A6") == "pass"


def test_mutation_missing_docstring_turns_a7_red_then_reverting_turns_it_green(tmp_root, capsys):
    """A7：删掉 OrderService.create 的 docstring ⇒ 红；撤回 ⇒ 绿。"""

    module = _load()
    tree = _copy(tmp_root)
    code, _out, payload = _json_run(module, capsys, tree)
    assert (code, _status(payload, "A7")) == (0, "pass")
    assert _detail(payload, "A7")["counts"]["missing"] == 0

    path = tree / "src/shop/order_service.py"
    original = path.read_bytes()
    _replace(
        tree,
        "src/shop/order_service.py",
        '        """建单并落库，返回建好的模型。"""\n\n',
        "",
    )

    code, _out, payload = _json_run(module, capsys, tree)
    assert code == module.EXIT_FAIL
    assert _status(payload, "A7") == "fail"
    assert _items(payload, "A7") == [
        {
            "kind": "method",
            "line": 19,
            "path": "src/shop/order_service.py",
            "qualified": "OrderService.create",
        }
    ]
    assert _detail(payload, "A7")["counts"]["missing"] == 1

    path.write_bytes(original)
    code, _out, payload = _json_run(module, capsys, tree)
    assert code == 0
    assert _status(payload, "A7") == "pass"


def test_mutation_dynamic_import_turns_a10_red_then_reverting_turns_it_green(tmp_root, capsys):
    """A10：加一处进程内动态 import ⇒ 红；撤回 ⇒ 绿。"""

    module = _load()
    tree = _copy(tmp_root)
    code, _out, payload = _json_run(module, capsys, tree)
    assert (code, _status(payload, "A10")) == (0, "pass")
    assert _detail(payload, "A10")["counts"]["dynamic_imports"] == 0

    path = tree / "src/shop/composition.py"
    original = path.read_bytes()
    _append(
        tree,
        "src/shop/composition.py",
        "\n\nimport importlib\n\n\ndef _mutation_dynamic(name: str) -> object:\n"
        '    """变异：进程内动态 import。"""\n\n    return importlib.import_module(name)\n',
    )

    code, _out, payload = _json_run(module, capsys, tree)
    assert code == module.EXIT_FAIL
    assert _status(payload, "A10") == "fail"
    items = _items(payload, "A10")
    assert [(item["path"], item["kind"], item["expression"]) for item in items] == [
        ("src/shop/composition.py", "dynamic_import", "importlib.import_module(name)")
    ]
    assert _detail(payload, "A10")["counts"]["dynamic_imports"] == 1

    path.write_bytes(original)
    code, _out, payload = _json_run(module, capsys, tree)
    assert code == 0
    assert payload["summary"] == {"passed": 10, "failed": 0}


def test_a_wildcard_import_is_an_a10_violation(tmp_root, capsys):
    """A10 的另一半：from X import * 也是 0 处。"""

    module = _load()
    tree = _copy(tmp_root)
    _append(tree, "src/shop/order_service.py", "from shop.models import *\n")

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A10") == "fail"
    items = _items(payload, "A10")
    assert [(item["path"], item["kind"], item["expression"]) for item in items] == [
        ("src/shop/order_service.py", "wildcard_import", "from shop.models import *")
    ]


# --------------------------------------------------------------------------- 其余 6 条谓词的「会红」


def test_a1_flags_controller_importing_repository(tmp_root, capsys):
    """A1：controller → repository 是白名单外的方向，必须给出这条边。"""

    module = _load()
    tree = _copy(tmp_root)
    _append(
        tree,
        "src/shop/order_controller.py",
        "from shop.order_repository import OrderRepository\n",
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A1") == "fail"
    assert _items(payload, "A1") == [
        {
            "rule": "forbidden_direction",
            "source": "src/shop/order_controller.py",
            "source_layer": "controller",
            "target": "src/shop/order_repository.py",
            "target_layer": "repository",
        }
    ]


def test_a1_flags_production_importing_a_test_module(tmp_root, capsys):
    """A1 的另一半：生产 → test 一律违规。"""

    module = _load()
    tree = _copy(tmp_root)
    _append(
        tree,
        "src/shop/order_service.py",
        "from tests.checks_order_flow import test_model_returns_a_copy\n",
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A1") == "fail"
    items = _items(payload, "A1")
    assert len(items) == 1
    assert items[0]["rule"] == "production_to_test"
    assert items[0]["source_layer"] == "service"
    assert items[0]["target"] == "tests/checks_order_flow.py"


def test_a4_flags_a_service_building_its_own_repository(tmp_root, capsys):
    """A4：生产模块自己 new 具象仓库 ⇒ 红，并指出是哪个类的哪个文件。"""

    module = _load()
    tree = _copy(tmp_root)
    _append(
        tree,
        "src/shop/order_service.py",
        "\n\ndef _build_repository() -> OrderRepository:\n"
        '    """变异：service 自己 new 仓库。"""\n\n    return OrderRepository()\n',
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A4") == "fail"
    items = _items(payload, "A4")
    assert len(items) == 1
    assert items[0]["path"] == "src/shop/order_service.py"
    assert items[0]["class"] == "OrderRepository"
    assert items[0]["class_path"] == "src/shop/order_repository.py"
    assert items[0]["class_layer"] == "repository"
    # 新口径：条目要说出调用点所在函数，并给出违规类别（载荷 1.1 起）。
    assert items[0]["enclosing"] == "_build_repository"
    assert items[0]["reason"] == "concrete_collaborator_in_business_method"
    # 组合根里的同一批实例化仍然允许（root_instantiations 证明谓词真的在看它们）。
    assert _detail(payload, "A4")["counts"]["root_instantiations"] == 6


def test_a4_default_wiring_in_init_is_not_a_violation(tmp_root, capsys):
    """A4 的 __init__ 豁免：参考树形态（x or ConcreteX()）不判违规，只进证据计数。

    Lead 2026-10-19 裁定：本题接口契约（interfaces.md）要求
    OrderService(repository=None, audit=None) 这类**构造器默认装配**，baseline 的 sample-project
    本身就写成 x or ConcreteX()。照 §4.2 的原始字形算违规，任何合法解都会在 A4 上失分。
    """

    module = _load()
    tree = _copy(tmp_root)
    _replace(
        tree,
        "src/shop/order_service.py",
        "    def __init__(self, repository: OrderRepository) -> None:\n"
        '        """注入仓库。"""\n\n'
        "        self._repository = repository\n",
        "    def __init__(self, repository: OrderRepository | None = None) -> None:\n"
        '        """注入仓库；不给就默认装一个（本题接口契约要求的默认参数语义）。"""\n\n'
        "        self._repository = repository or OrderRepository()\n",
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == 0
    assert _status(payload, "A4") == "pass"
    assert _items(payload, "A4") == []
    assert _detail(payload, "A4")["counts"]["violations"] == 0
    assert _detail(payload, "A4")["counts"]["default_wiring_instantiations"] == 1


def test_a4_business_method_instantiating_a_repository_is_red_then_green(tmp_root, capsys):
    """变异自证（A4 新口径）：业务方法里 new 具象仓库 ⇒ 红（带 enclosing / reason）；撤回 ⇒ 绿。"""

    module = _load()
    tree = _copy(tmp_root)
    code, _out, payload = _json_run(module, capsys, tree)
    assert (code, _status(payload, "A4")) == (0, "pass")
    assert _detail(payload, "A4")["counts"]["default_wiring_instantiations"] == 0

    path = tree / "src/shop/order_service.py"
    original = path.read_bytes()
    _append(
        tree,
        "src/shop/order_service.py",
        "\n    def rebuild(self) -> OrderRepository:\n"
        '        """变异：业务方法里自己 new 具象仓库。"""\n\n'
        "        return OrderRepository()\n",
    )

    code, _out, payload = _json_run(module, capsys, tree)
    assert code == module.EXIT_FAIL
    assert _status(payload, "A4") == "fail"
    items = _items(payload, "A4")
    assert len(items) == 1
    assert items[0]["path"] == "src/shop/order_service.py"
    assert items[0]["class"] == "OrderRepository"
    assert items[0]["class_path"] == "src/shop/order_repository.py"
    assert items[0]["enclosing"] == "OrderService.rebuild"
    assert items[0]["reason"] == "concrete_collaborator_in_business_method"

    path.write_bytes(original)
    code, _out, payload = _json_run(module, capsys, tree)
    assert code == 0
    assert payload["summary"] == {"passed": 10, "failed": 0}


def test_a3_declared_caps_pass_then_over_cap_turns_red(tmp_root, capsys):
    """A3 的 declared_caps 口径：给了 --interfaces 就按声明的接口数判，多一个公开方法就红。"""

    module = _load()
    tree = _copy(tmp_root)
    code, _out, payload = _json_run(module, capsys, tree, "--interfaces", tree / "interfaces.yaml")
    assert (code, _status(payload, "A3")) == (0, "pass")
    assert _detail(payload, "A3")["basis"] == "declared_caps"
    assert payload["workspace_scope"]["interfaces"]["status"] == "available"

    _append(
        tree,
        "src/shop/models.py",
        "\n    def total(self) -> int:\n"
        '        """合计（变异：第 3 个公开定义，上限是 2）。"""\n\n'
        "        return self.amount\n",
    )

    code, _out, payload = _json_run(module, capsys, tree, "--interfaces", tree / "interfaces.yaml")
    assert code == module.EXIT_FAIL
    assert _status(payload, "A3") == "fail"
    assert _items(payload, "A3") == [
        {
            "cap": 2,
            "names": ["Order", "to_dict", "total"],
            "path": "src/shop/models.py",
            "public_definitions": 3,
            "reason": "over_cap",
        }
    ]


def test_a3_module_all_basis_flags_an_undeclared_export(tmp_root, capsys):
    """A3 的 module_all 口径（没给 --interfaces）：模块级公开定义不在 __all__ 里就红。"""

    module = _load()
    tree = _copy(tmp_root)
    _append(
        tree,
        "src/shop/models.py",
        '\n\ndef extra_helper() -> int:\n    """变异：多导出一个模块级公开函数。"""\n\n    return 1\n',
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A3") == "fail"
    assert _items(payload, "A3") == [
        {
            "names": ["extra_helper"],
            "path": "src/shop/models.py",
            "public_definitions": 3,
            "reason": "undeclared_export",
        }
    ]


def test_a9_flags_a_production_module_no_test_imports(tmp_root, capsys):
    """A9：测试不再 import repository ⇒ 该模块判 no_test_import。"""

    module = _load()
    tree = _copy(tmp_root)
    _replace(
        tree,
        "tests/checks_order_flow.py",
        "from shop.order_repository import OrderRepository\n",
        "",
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A9") == "fail"
    assert _items(payload, "A9") == [
        {"line": None, "path": "src/shop/order_repository.py", "reason": "no_test_import"}
    ]
    # src/shop/__init__.py 仍然被"import 子模块会连带 import 它的包"这条语义覆盖。
    assert _detail(payload, "A9")["counts"]["covered"] == 5


# --------------------------------------------------------------------------- 阈值边界（合成树）


def test_a5_complexity_boundary_is_ten(tmp_root, capsys):
    """A5 的阈值是「> 10 才红」：复杂度 10 的函数留在绿的一侧，11 的判红。"""

    module = _load()
    tree = _synthetic(
        tmp_root,
        "complexity",
        {
            "layers.yaml": _layers(("plain.py", "other"), ("braided.py", "other")),
            "plain.py": '"""复杂度恰好 10。"""\n\n' + _if_chain(9),
            "braided.py": '"""复杂度 11。"""\n\n' + _if_chain(10),
        },
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A5") == "fail"
    items = _items(payload, "A5")
    assert [(item["path"], item["qualified"], item["complexity"]) for item in items] == [
        ("braided.py", "_chain", 11)
    ]
    assert _detail(payload, "A5")["counts"] == {
        "functions": 2,
        "over_threshold": 1,
        "violations": 1,
    }


def test_a6_length_boundaries(tmp_root, capsys):
    """A6 的两条阈值是「> 200 行文件 / > 50 行函数」：边界值本身留在绿的一侧。"""

    module = _load()
    tree = _synthetic(
        tmp_root,
        "lengths",
        {
            "layers.yaml": _layers(
                ("file_200.py", "other"),
                ("file_201.py", "other"),
                ("function_50.py", "other"),
                ("function_51.py", "other"),
            ),
            "file_200.py": '"""200 行。"""\n' + "x = 1\n" * 199,
            "file_201.py": '"""201 行。"""\n' + "x = 1\n" * 200,
            "function_50.py": '"""函数恰好 50 行。"""\n\n' + _function_of(50),
            "function_51.py": '"""函数 51 行。"""\n\n' + _function_of(51),
        },
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A6") == "fail"
    items = _items(payload, "A6")
    assert [(item["path"], item["kind"], item.get("qualified")) for item in items] == [
        ("file_201.py", "file", None),
        ("function_51.py", "function", "short_function"),
    ]
    assert items[0]["lines"] == 201
    assert items[1]["lines"] == 51
    assert _detail(payload, "A6")["counts"]["over_length_files"] == 1
    assert _detail(payload, "A6")["counts"]["over_length_functions"] == 1


def test_a8_fan_out_over_five_is_red(tmp_root, capsys):
    """A8：一个模块 6 条项目内出边（阈值 5）判红，其余模块不陪绑。"""

    module = _load()
    files = {
        "layers.yaml": _layers(
            ("hub.py", "other"),
            ("leaf_b.py", "other"),
            ("leaf_c.py", "other"),
            ("leaf_d.py", "other"),
            ("leaf_e.py", "other"),
            ("leaf_f.py", "other"),
            ("leaf_g.py", "other"),
        ),
        "hub.py": '"""扇出 6。"""\n\n' + "".join("import leaf_%s\n" % name for name in "bcdefg"),
    }
    for name in "bcdefg":
        files["leaf_%s.py" % name] = '"""叶子。"""\n'
    tree = _synthetic(tmp_root, "fanout", files)

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A8") == "fail"
    assert _items(payload, "A8") == [{"in": 0, "out": 6, "path": "hub.py"}]


# --------------------------------------------------------------------------- 失败关闭与用法错误


@pytest.mark.parametrize(
    "layers_text, fragment",
    [
        ("src/shop/models.py: modelx\n", "不在闭集里"),
        ("C:/outside/models.py: model\n", "不接受绝对路径"),
        ("src/../shop/models.py: model\n", "不许出现 . 或 .. 段"),
        ("- just a list\n", "顶层必须是映射"),
    ],
    ids=["unknown-layer", "absolute-key", "dotdot-key", "not-a-mapping"],
)
def test_a_declaration_error_exits_two(tmp_root, capsys, layers_text, fragment):
    """声明读不懂就是用法错误（退出 2）：不静默当成 other，也不降级成"没有声明"。"""

    module = _load()
    tree = _copy(tmp_root)
    (tree / "layers.yaml").write_text(layers_text, encoding="utf-8", newline="\n")

    code, out, err = _run(module, capsys, "--workspace", tree, "--layers", tree / "layers.yaml")

    assert code == module.EXIT_USAGE == 2
    assert out == ""
    assert "structure_metrics:" in err
    assert fragment in err


def test_a_missing_layers_file_is_a_usage_error(tmp_root, capsys):
    """--layers 读不到 = 退出 2（"没有声明"不是"没有违规"）。"""

    module = _load()
    tree = _copy(tmp_root)

    code, out, err = _run(module, capsys, "--workspace", tree, "--layers", tree / "missing.yaml")

    assert code == module.EXIT_USAGE
    assert out == ""
    assert "文件不存在" in err


def test_an_undeclared_python_file_makes_a1_red(tmp_root, capsys):
    """声明漏掉一个 .py：A1 判 fail 并点名那些边（"路径族声明 100%"不能靠没查过变成绿）。"""

    module = _load()
    tree = _copy(tmp_root)
    (tree / "layers.yaml").write_text(
        _layers(("src/shop/models.py", "model")), encoding="utf-8", newline="\n"
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert _status(payload, "A1") == "fail"
    assert payload["workspace_scope"]["undeclared"] == [
        "src/shop/__init__.py",
        "src/shop/composition.py",
        "src/shop/order_controller.py",
        "src/shop/order_repository.py",
        "src/shop/order_service.py",
        "tests/checks_order_flow.py",
    ]
    assert {item["rule"] for item in _items(payload, "A1")} == {"undeclared_layer"}
    assert _detail(payload, "A1")["counts"]["violations"] == 12


def test_a_syntax_error_fails_all_ten_predicates(tmp_root, capsys):
    """解析失败 ≠ 没有依赖（AGENTS 第 20 条）：一个坏文件让 10 条全部 fail 并写明 blocked_by。"""

    module = _load()
    tree = _copy(tmp_root)
    _write(tree, "src/shop/models.py", "def broken(\n")

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    assert payload["summary"] == {"passed": 0, "failed": 10}
    assert all(item["status"] == "fail" for item in payload["predicates"])
    assert {item["detail"]["blocked_by"] for item in payload["predicates"]} == {
        "unmeasurable_files"
    }
    assert payload["workspace_scope"]["unmeasurable"] == [
        {
            "line": 1,
            "message": "'(' was never closed",
            "path": "src/shop/models.py",
            "reason": "syntax_error",
        }
    ]


def test_an_empty_workspace_is_a_usage_error(tmp_root, capsys):
    """「没有可测对象」是用法错误（退出 2），不是「10 条都通过」。"""

    module = _load()
    tree = _synthetic(tmp_root, "empty", {"layers.yaml": "{}\n"})

    code, out, err = _run(module, capsys, "--workspace", tree, "--layers", tree / "layers.yaml")

    assert code == module.EXIT_USAGE
    assert out == ""
    assert "没有 .py 文件" in err


def test_out_writes_the_same_bytes_as_json_and_the_machine_line_is_stable(tmp_root, capsys):
    """--out 的字节与 --json 相同；人类输出最后一行是稳定机器行（门禁读得出来）。"""

    module = _load()
    tree = _copy(tmp_root)
    target = Path(tmp_root) / "payload.json"

    code, out, err = _run(
        module,
        capsys,
        "--workspace",
        tree,
        "--layers",
        tree / "layers.yaml",
        "--json",
        "--out",
        target,
    )
    assert (code, err) == (0, "")
    assert target.read_bytes() == out.encode("utf-8")

    code, human, err = _run(module, capsys, "--workspace", tree, "--layers", tree / "layers.yaml")
    assert (code, err) == (0, "")
    assert human.rstrip("\n").splitlines()[-1] == "STRUCTURE_METRICS: passed=10 failed=0"
    assert human.startswith("structure_metrics: workspace=. files=7")
    assert "A10 PASS 无动态执行" in human


def test_the_human_output_lists_failing_items_within_the_limit(tmp_root, capsys):
    """失败时人类输出点名超阈值项，条目数受 --limit 约束；载荷里仍然是全量计数。"""

    module = _load()
    tree = _synthetic(
        tmp_root,
        "limits",
        {
            "layers.yaml": _layers(("braided.py", "other")),
            "braided.py": '"""复杂度 11 与 12 两个函数。"""\n\n' + _if_chain(10) + "\n" + _if_chain(11),
        },
    )

    code, human, _err = _run(
        module, capsys, "--workspace", tree, "--layers", tree / "layers.yaml", "--limit", "1"
    )

    assert code == module.EXIT_FAIL
    assert "（其余超阈值项见 --json）" in human
    code, _out, payload = _json_run(module, capsys, tree)
    assert _detail(payload, "A5")["counts"]["violations"] == 2
    assert len(_items(payload, "A5")) == 2


def test_an_unresolved_dependency_fails_a1_a2_a8(tmp_root, capsys):
    """依赖图不完整就不许判方向 / 无环 / 扇出：from . import <名字> 解析不了就必须判 fail。

    这正是仓库既有口径（validators 的 unresolved 一律阻断，AGENTS 第 20 条）：
    三个谓词都报 violations=0，但 unresolved=1 让它们 fail——"看不到的边"不是"没有违规"。
    """

    module = _load()
    tree = _synthetic(
        tmp_root,
        "unresolved",
        {
            "layers.yaml": _layers(
                ("pkg/__init__.py", "other"),
                ("pkg/models.py", "model"),
                ("pkg/service.py", "service"),
            ),
            "pkg/__init__.py": '"""包。"""\n',
            "pkg/models.py": '"""model。"""\n',
            "pkg/service.py": '"""service。"""\n\nfrom . import missing_name\n',
        },
    )

    code, _out, payload = _json_run(module, capsys, tree)

    assert code == module.EXIT_FAIL
    for identifier in ("A1", "A2", "A8"):
        assert _status(payload, identifier) == "fail"
        assert _detail(payload, identifier)["counts"]["violations"] == 0
        assert _detail(payload, identifier)["counts"]["unresolved"] == 1
        assert len(_detail(payload, identifier)["unresolved"]) == 1
        assert _detail(payload, identifier)["unresolved"][0]["module"] == "pkg.missing_name"
