"""--only 必须在调用探针工厂**之前**过滤；"id 从函数名推出"这条约定要静态守住。

审查结论（tools/governance_gap_probe.py:2198 附近）：过滤写在 factory(env) 之后，于是
--only G02 仍然把 13 个缺口全跑一遍（各自起子进程、G04 还有 time.sleep(2)），与 --help
的"只跑指定缺口"不符。过滤前移之后，正确性依赖"工厂函数名 == check_ + id 小写"这条约定，
所以这里用 AST 静态守住它（不执行任何探针）。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "governance_gap_probe_under_test", REPO_ROOT / "tools" / "governance_gap_probe.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["governance_gap_probe_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _declared_ids(source: str) -> dict[str, str]:
    """每个 check_gNN 里 Check(...) 的 id 字面量（关键字或第一个位置参数）。"""

    declared: dict[str, str] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("check_g"):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call) or getattr(call.func, "id", "") != "Check":
                continue
            value = None
            for keyword in call.keywords:
                if keyword.arg == "id":
                    value = keyword.value
            if value is None and call.args:
                value = call.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                declared[node.name] = value.value
    return declared


def test_factory_names_match_the_ids_they_declare() -> None:
    """_check_id_of 按函数名推 id：名字与声明的 id 不一致就会漏跑或错跑。"""

    source = (REPO_ROOT / "tools" / "governance_gap_probe.py").read_text(encoding="utf-8")
    declared = _declared_ids(source)
    assert len(declared) >= 13, declared
    for name, check_id in declared.items():
        assert name == "check_" + check_id.lower(), (
            f"{name} 里声明的 id 是 {check_id!r}：过滤前移后按函数名推 id，两者必须一致"
        )


def test_only_skips_factories_before_calling_them(tmp_root: Path, monkeypatch) -> None:
    """--only G02 时，G01 的工厂一次都不许被调用。"""

    module = _load_probe()
    calls: list[str] = []

    class StubEnv:
        def __init__(self, root, work, timeout=0):
            self.root = Path(root)
            self.work = Path(work)
            self.run_id = "stub"
            self.audit_dir = Path(work) / "audit"
            self.audit_dir.mkdir(parents=True, exist_ok=True)
            self.log: list[str] = []

        def setup(self) -> None:
            return None

    def check_g01(env):  # noqa: ANN001, ARG001 - 探针替身
        calls.append("check_g01")
        return module.Check(id="G01", title="stub", before={}, after={})

    def check_g02(env):  # noqa: ANN001, ARG001 - 探针替身
        calls.append("check_g02")
        return module.Check(id="G02", title="stub", before={}, after={})

    monkeypatch.setattr(module, "Env", StubEnv)
    monkeypatch.setattr(module, "CHECKS", (check_g01, check_g02))

    report = module._run_once(  # noqa: SLF001 - 这里要测的就是这条私有路径
        tmp_root, "after", tmp_root / "work", only=["G02"], timeout=1
    )
    assert calls == ["check_g02"], "过滤发生在调用之后：没点名的缺口也被跑了"
    assert [item["id"] for item in report["checks"]] == ["G02"]
    assert report["ok"] is True


def test_no_personal_absolute_path_is_hard_coded():
    """探针不许写死某人本机的路径。

    旧写法把第三方 dsh 实现包写死成作者的 Windows 路径，并用"这个文件存不存在"在运行期改写
    **评分预期表**（两条 `check.after[...] = True`）——于是在别人机器上那两条"修后声明"静默消失，
    同一棵树按不同契约评分、`--phase after` 不可复现。现在路径只从环境变量来。
    """

    source = (REPO_ROOT / "tools" / "governance_gap_probe.py").read_text(encoding="utf-8")

    assert "C:/Users/" not in source
    assert "C:\\Users\\" not in source


def test_dsh_impl_asar_comes_from_the_environment(monkeypatch):
    """实现包路径只认环境变量：没给 = None（如实记 absent），给了就用给的那条。"""

    module = _load_probe()
    monkeypatch.delenv(module.DSH_IMPL_ASAR_ENV, raising=False)
    assert module.dsh_impl_asar() is None

    monkeypatch.setenv(module.DSH_IMPL_ASAR_ENV, "C:/somewhere/app.asar")
    assert module.dsh_impl_asar() == Path("C:/somewhere/app.asar")

    monkeypatch.setenv(module.DSH_IMPL_ASAR_ENV, "   ")
    assert module.dsh_impl_asar() is None, "空白串等于没给（别把空白当路径）"
