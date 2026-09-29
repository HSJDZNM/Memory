"""台阶 3c：义务账跑一轮真流水线（先写测试 → 再写实现）。

判据（方案 §4 台阶 3 的 J1 结构判据）：

- **J1(c)**：`obligations_open > 0` 时 `check_volume.complete = false`；
- **J1(d)**：解除**只**由一次真实 pytest 运行判定 —— 补上实现、让 pytest 真的跑起来之后才归零。

按 **L5** 以 warn 形式上线：这一段不改变 decision、不改变退出码。唯一会让进程退 2 的是
「调用方声明了 `--obligations` 却读不懂那份账本」—— 那是配置错误（显式声明的输入读不了），
与义务本身无关。

为什么用**真流水线**而不是直接调 `record_pending`：账本的键里有一个 `target`、解除里
有一条"这次到底跑了哪些测试"，这两个事实只有真流水线（真 pytest 子进程、真选择）才产得出；
直接构造记录只能证明"记录能写进去"，证明不了"义务会在正确的时刻解除"。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import REPO_ROOT, copy_validator_project

pytestmark = pytest.mark.integration

RULES = ("TESTING-001.yaml", "TESTING-002.yaml")

# 「先写测试」：测试文件已经落地，它 import 的项目内名字还不存在 → 收集期失败 → 待实现。
PENDING_TEST = (
    '"""取消订单的用例（实现还没写，先写测试）。"""' + chr(10) + chr(10)
    + "from shop.order_service import OrderService, cancel_order" + chr(10) + chr(10) + chr(10)
    + "def test_cancel_returns_cancelled_status() -> None:" + chr(10)
    + '    """取消订单应当返回 cancelled 状态。"""' + chr(10) + chr(10)
    + '    assert cancel_order(None, "order-1")["status"] == "cancelled"' + chr(10)
)

# 「再写实现」：那个名字落地，测试能收集、能真的跑起来。
IMPLEMENTATION = (
    chr(10) + chr(10)
    + "def cancel_order(service: OrderService, order_id: str) -> dict:" + chr(10)
    + '    """取消订单：返回被取消的那一单（本夹具不碰真实存储）。"""' + chr(10) + chr(10)
    + '    return {"id": order_id, "status": "cancelled"}' + chr(10)
)


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_cli(*args: str):
    return subprocess.run(
        [sys.executable, "-m", "policy.check", *args],
        cwd=REPO_ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def narrow_rules(tmp_root: Path) -> Path:
    """把规则集收窄到两条测试规则：本用例要证的是"义务"，不是"43 条规则一起上"。

    跑的是**同一条真流水线**（真 pytest 子进程、真选择、同一套证据协议），收窄掉的只是
    与 Q7 无关的其它规则 —— 否则本机有没有 ruff、有没有 mypy 会决定这条用例的红绿，
    那是环境的性质，不是被测行为的性质（与 tests/integration/test_validator_pipeline.py 同一手法）。
    """

    target = tmp_root / "rules"
    target.mkdir(parents=True, exist_ok=True)
    for name in RULES:
        source = REPO_ROOT / "policies" / "testing" / name
        (target / name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8", newline=chr(10)
        )
    return target


def prepare_workspace(tmp_root: Path, *, with_implementation: bool) -> Path:
    """先写测试：测试文件落地（它 import 的名字还没落地）+ 生产文件上的一次改动。

    为什么必须同时动一次生产文件：测试选择器只在**变更集里有生产文件**时才去找相关测试
    （实测读数：`变更集里没有生产文件，测试选择不适用`），只改测试文件的话 pytest 根本不会被
    选起来，"待实现"因此无从产生 —— 那不是平台拦住了正确写法，而是这一步没有触发取证。
    """

    workspace = copy_validator_project(tmp_root, name="workspace")
    (workspace / "tests" / "test_order_service.py").write_text(
        PENDING_TEST, encoding="utf-8", newline=chr(10)
    )
    service = workspace / "src" / "shop" / "order_service.py"
    text = service.read_text(encoding="utf-8") + chr(10) + "# 本次变更：让测试选择器看见这个生产文件" + chr(10)
    if with_implementation:
        text += IMPLEMENTATION
    service.write_text(text, encoding="utf-8", newline=chr(10))
    return workspace


def check(
    workspace: Path, target: str, *, rules: Path, ledger, operation: str
) -> tuple:
    args = [
        target,
        "--rules",
        str(rules),
        "--language",
        "python",
        "--operation",
        operation,
        "--changed",
        target,
        "--workspace",
        str(workspace),
        "--json",
    ]
    if ledger is not None:
        args += ["--obligations", str(ledger)]
    completed = run_cli(*args)
    assert completed.stdout, completed.stderr
    return completed.returncode, json.loads(completed.stdout)


def load_state(path: Path):
    from policy.obligations import load

    return load(path)


def ledger_records(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_a_pending_write_opens_an_obligation_and_makes_the_volume_incomplete(tmp_root: Path) -> None:
    """J1(c)：先写测试 → 判定仍是 allow_with_warnings（不阻断），但账本多一条义务、
    `check_volume.complete` 变成 false，而且理由是义务 —— 不是"缺维度"。"""

    workspace = prepare_workspace(tmp_root, with_implementation=False)
    rules = narrow_rules(tmp_root)
    ledger = tmp_root / "obligations.jsonl"

    exit_code, body = check(
        workspace,
        "src/shop/order_service.py",
        rules=rules,
        ledger=ledger,
        operation="edit",
    )

    # 判定一字未变：待实现不阻断（这是台阶 3b 的结论，本台阶不许把它改回去）。
    assert exit_code == 1, body
    assert body["result"]["decision"] == "allow_with_warnings"
    assert body["result"]["violations"] == []
    assert body["result"]["pending_findings"], body["result"]

    volume = body["check_volume"]
    assert volume["obligations_open"] == 1, volume
    assert volume["complete"] is False, volume
    # 理由是义务，不是缺维度：两条轴必须分得开（complete 有两个成因）。
    assert volume["missing_dimensions"] == [], volume

    records = ledger_records(ledger)
    # pytest 这一次被选起来了、却**一个用例都没跑成**（收集失败）：账本把这次运行也记下来，
    # 但 `python_tests_executed=false` —— "没跑成"不许被读成"跑过了"（解除只认 true）。
    assert [item["kind"] for item in records] == ["pending", "test_run"]
    assert records[1]["python_tests_executed"] is False, records[1]
    assert records[0]["rule_id"] == "TESTING-002"
    assert records[0]["target"] == "src/shop/order_service.py"
    assert records[0]["test_module"] == "tests/test_order_service.py"
    assert records[0]["missing_target"] == "shop.order_service:cancel_order"
    assert records[0]["schema_version"] == "1.0"
    # 解除只由真实运行判定：账本里还没有任何 test_run，因此"0 条"此刻**不可声称**。
    assert load_state(ledger).last_real_test_run is None


def test_only_a_real_pytest_run_closes_the_obligation(tmp_root: Path) -> None:
    """J1(d)：补上实现、让 pytest 真的跑起来 → 义务归零，且账本里留下那次真运行。"""

    workspace = prepare_workspace(tmp_root, with_implementation=False)
    rules = narrow_rules(tmp_root)
    ledger = tmp_root / "obligations.jsonl"

    check(workspace, "src/shop/order_service.py", rules=rules, ledger=ledger, operation="edit")
    assert load_state(ledger).open, "第一步必须真的记下一次义务，否则第二步的归零没有意义"

    # 「再写实现」：**同一个工作区**补上 cancel_order，再走一次同一条 CLI 路径。
    service = workspace / "src" / "shop" / "order_service.py"
    service.write_text(
        service.read_text(encoding="utf-8") + IMPLEMENTATION,
        encoding="utf-8",
        newline=chr(10),
    )
    exit_code, body = check(
        workspace,
        "src/shop/order_service.py",
        rules=rules,
        ledger=ledger,
        operation="edit",
    )

    assert exit_code == 0, body
    assert body["result"]["decision"] == "allow"
    assert body["result"]["pending_findings"] == []

    volume = body["check_volume"]
    assert volume["obligations_open"] == 0, volume
    assert volume["complete"] is True, volume

    kinds = [item["kind"] for item in ledger_records(ledger)]
    assert kinds == ["pending", "test_run", "test_run"], kinds
    run = ledger_records(ledger)[-1]
    assert run["python_tests_executed"] is True, run
    assert "tests/test_order_service.py" in run["selected_tests"], run
    # 反例保证：解除的是**那条**义务（覆盖它的测试真的被选中了），而不是"新会话清零"。
    state = load_state(ledger)
    assert state.open == ()
    assert state.closed == 1
    assert state.last_real_test_run is not None


def test_without_a_ledger_the_volume_has_no_obligation_keys(tmp_root: Path) -> None:
    """没有 --obligations = **没有账本可读**，不是"0 条未结义务"：键不许出现。

    两个读法必须分得开（AGENTS 第 46/50 条）：缺键说"这次根本没读账本"，
    `obligations_open: 0` 说"读了，0 条，而且有真实运行背书"。把前者写成后者，
    等于用"没查"冒充"查了没问题"。
    """

    workspace = prepare_workspace(tmp_root, with_implementation=False)
    rules = narrow_rules(tmp_root)

    _exit_code, body = check(
        workspace, "src/shop/order_service.py", rules=rules, ledger=None, operation="edit"
    )

    assert "obligations_open" not in body["check_volume"], body["check_volume"]
    assert body["result"]["pending_findings"], body["result"]
