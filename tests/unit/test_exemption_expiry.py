"""豁免到期检查（tools/exemption_expiry.py）的回归：规则只有一份实现，且只报告。

口径（2026-09-30 裁定 R16-4）：到期前 14 天提醒、过期标红，**都不计入任何门禁失败**——
所以这里最要紧的两条断言是"过期也返回 0"与"读不到不算通过、也不算失败，只说 unprovable"。
"""

from __future__ import annotations

import datetime as _datetime
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPIRED_SCOPE = """schema_version: "1"
scope:
  - id: probe-out-of-scope
    decision: out_of_scope
    kind: agent_runtime
    owner: host
    reason: 回归用例：一条已经过期的"不治理"声明。
    consequence: 只报告，不签发任何 allow / block。
    expires_at: "2026-01-01"
    renewals: []
"""

DUE_SCOPE = EXPIRED_SCOPE.replace('"2026-01-01"', '"2026-10-05"')


def _load():
    spec = importlib.util.spec_from_file_location(
        "exemption_expiry_under_test",
        REPO_ROOT / "tools" / "exemption_expiry.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # 标准配方：exec 之前登记，模块内 dataclass / 相对导入才成立
    spec.loader.exec_module(module)
    return module


def test_state_boundaries_are_the_only_implementation():
    module = _load()
    today = _datetime.date(2026, 9, 30)

    assert module.state_for("2026-10-15", today=today, lead_days=14)["state"] == "ok"
    assert module.state_for("2026-10-14", today=today, lead_days=14)["state"] == "due"
    assert module.state_for("2026-09-30", today=today, lead_days=14)["state"] == "due"
    expired = module.state_for("2026-09-29", today=today, lead_days=14)
    assert expired["state"] == "expired"
    assert expired["days"] == -1


def test_an_expired_exemption_is_red_but_never_fails(tmp_root, capsys):
    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(EXPIRED_SCOPE, encoding="utf-8")
    module = _load()

    assert module.run(["--scope", str(scope), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "RED" in out
    assert "已过期" in out
    assert "本步不阻断门禁" in out


def test_a_due_exemption_is_reminded(tmp_root, capsys):
    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(DUE_SCOPE, encoding="utf-8")
    module = _load()

    assert module.run(["--scope", str(scope), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "DUE" in out
    assert "5 天后到期" in out


def test_read_failure_is_unprovable_not_a_failure(tmp_root, capsys):
    module = _load()

    assert module.run(["--scope", str(tmp_root / "missing.yaml"), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "读不到" in out
    assert "unprovable=1" in out


def test_json_payload_separates_the_two_lists(tmp_root, capsys):
    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(EXPIRED_SCOPE, encoding="utf-8")
    module = _load()

    assert module.run(["--scope", str(scope), "--today", "2026-09-30", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "report-only"
    assert payload["counts"]["expired"] == 1
    assert payload["counts"]["unprovable"] == 0
    assert [item["id"] for item in payload["expired"]] == ["probe-out-of-scope"]
    # ci_local 的两条只报告豁免也必须在读数里（账本/到期检查自己也在豁免表里）；
    # --scope 覆盖时读数里的来源就是那个被覆盖的文件（相对仓库渲染，不在仓库内则原样）。
    sources = {item["source"] for item in payload["entries"]}
    assert "tools/ci_local.py" in sources
    assert any(source.endswith("wiring-scope.yaml") for source in sources)


def test_the_repository_declarations_are_readable_today(capsys):
    """仓库自身的读数：今天没有到期项，且退出码为 0（这一步永远不阻断）。"""

    module = _load()
    assert module.run(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["unprovable"] == 0
    assert payload["counts"]["declared"] >= 4


# --- 第 18 轮：默认输出里的机器行（ci_local 按它取命中数） -------------------------------
#
# 第 17 轮门禁暴露的缺口：这一步的 args 里没有 --json，而 report_only_hits 只认 --json 的
# `hits` 或文本里的 `HITS:` 行 —— 于是读数打成"读不出命中数"。修法**只在这份实现里**：
# 默认输出多一行稳定的 `HITS:`（hits = 已过期条数，due / unprovable 另列），
# ci_local.py 一个字节都不改。


def _load_ci_local():
    """按文件路径加载 ci_local（与 test_ci_local_report_only.py 同一套配方）。"""

    spec = importlib.util.spec_from_file_location(
        "ci_local_for_expiry_contract",
        REPO_ROOT / "tools" / "ci_local.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _exemption_step(ci_local):
    """ci_local 里那一条豁免到期步骤——**真的那一条**，不是复刻一个。"""

    for step in ci_local.REPORT_ONLY_STEPS:
        if any("exemption_expiry.py" in argument for argument in step.args):
            return step
    raise AssertionError("ci_local 的 REPORT_ONLY_STEPS 里没有 exemption_expiry 那一条")


def test_ci_local_reads_the_hits_line_from_the_default_output(tmp_root, capsys):
    """跨侧契约：真的解析器读真的默认输出（这一步没有 --json，走的是文本行）。"""

    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(EXPIRED_SCOPE, encoding="utf-8")
    module = _load()
    assert module.run(["--scope", str(scope), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out

    ci_local = _load_ci_local()
    step = _exemption_step(ci_local)
    assert "--json" not in step.args, "这一步没有 --json：读数判据是文本行，不是载荷"
    reading = ci_local.report_only_hits(step, out)
    assert reading.startswith("HITS:"), reading
    assert "读不出命中数" not in reading
    assert "expired=1" in reading and "due=0" in reading and "unprovable=0" in reading
    assert int(reading.split(":", 1)[1].split("/", 1)[0].strip()) == 1, "hits 就是已过期条数"


def test_hits_counts_only_expired_and_lists_due_separately(tmp_root, capsys):
    """due 是提醒、不是命中：它在同一行里可读，但**不计进** hits。"""

    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(DUE_SCOPE, encoding="utf-8")
    module = _load()
    assert module.run(["--scope", str(scope), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    line = next(text.strip() for text in out.splitlines() if text.strip().startswith("HITS:"))
    assert line.startswith("HITS: 0 /"), line
    assert "due=1" in line and "expired=0" in line


def test_json_payload_key_set_and_its_version_axis(tmp_root, capsys):
    """谁给 --json 载荷加键，就得同时决定版本轴怎么走（AGENTS 第 55 条）。

    台阶 4 第二件做了这件事：这个载荷原先**没有版本轴**，第一次改键就按第 55 条**建轴**
    （`EXEMPTION_REPORT_SCHEMA_VERSION = "1.1"`），键集合与版本号在同一个提交里显式改。
    这条用例就是那次的钉子——**不是**"以后可以随便加键"的许可。
    """

    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(EXPIRED_SCOPE, encoding="utf-8")
    module = _load()
    assert module.run(["--scope", str(scope), "--today", "2026-09-30", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "report_schema_version",
        "reading_context",
        "mode",
        "note",
        "today",
        "lead_days",
        "entries",
        "due",
        "expired",
        "unprovable",
        "counts",
    }
    assert set(payload["counts"]) == {"declared", "due", "expired", "unprovable"}
    assert payload["report_schema_version"] == module.EXEMPTION_REPORT_SCHEMA_VERSION == "1.1"
    context = payload["reading_context"]
    assert context["source"] == "gate"
    assert context["tree"]["status"] == "available"
    assert context["tree"]["digest"].startswith("sha256:")
    declarations = context["declarations"]
    assert declarations["wiring_scope"]["path"].endswith("wiring-scope.yaml")
    assert not Path(declarations["wiring_scope"]["path"]).is_absolute()
    assert declarations["wiring_scope"]["digest"].startswith("sha256:")
    assert declarations["report_only_steps"]["path"] == "tools/ci_local.py"
    assert declarations["report_only_steps"]["digest"].startswith("sha256:")


def test_the_default_text_output_is_a_cross_file_contract_and_did_not_change(tmp_root, capsys):
    """台阶 4 只给 --json 加键：默认输出（`ci_local` 按前缀读的那条 HITS: 行）一个字符都不改。"""

    scope = tmp_root / "wiring-scope.yaml"
    scope.write_text(EXPIRED_SCOPE, encoding="utf-8")
    module = _load()
    assert module.run(["--scope", str(scope), "--today", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    assert "HITS: 1 / declared=" in out
    assert "reading_context" not in out
