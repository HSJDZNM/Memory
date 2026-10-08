"""provenance CLI 的封条路径：失败必须走文档写明的退出码，不许裸 traceback。

模块 docstring 的三条约定在 seal 路径上必须同时成立：2 = 用法错误、3 = 封条失效、
1 = 判据 fail（"跑完了、是红的"）。核验发现两个口子：--platform 读不到与判据命令
起不来都以 traceback + 退出码 1 结束，后者还跳过 _finish_seal（没有回执、没有
"seal state:" 行）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

pytestmark = pytest.mark.integration


def env() -> dict[str, str]:
    values = dict(os.environ)
    values["PYTHONPATH"] = str(REPO_ROOT / "src")
    values["PYTHONIOENCODING"] = "utf-8"
    return values


def run_cli(*args: str) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, "-m", "provenance.cli", *args],
        cwd=REPO_ROOT,
        env=env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.fixture()
def sealed_project(tmp_root: Path) -> Path:
    """一棵可以被封条的小树 + 一份能命中的声明；返回声明文件路径。"""

    project = tmp_root / "project"
    (project / "declared").mkdir(parents=True)
    (project / "declared" / "a.txt").write_text("a" + chr(10), encoding="utf-8")
    declaration = tmp_root / "declaration.txt"
    declaration.write_text("declared/*.txt" + chr(10), encoding="utf-8")
    return declaration


def test_a_sealed_run_reports_pass_and_writes_the_receipt(tmp_root: Path, sealed_project: Path) -> None:
    """正面控制：判据跑通时回执照写，形状不变（receipt_schema_version 仍是 1.0）。"""

    project = tmp_root / "project"
    receipt = tmp_root / "receipt.json"
    completed = run_cli(
        "seal",
        "--root", str(project),
        "--declaration", str(sealed_project),
        "--out", str(receipt),
        "--", sys.executable, "-c", "pass",
    )
    assert completed.returncode == 0, completed.stderr
    assert "seal state: pass" in completed.stderr
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["receipt_schema_version"] == "1.0"
    assert payload["state"] == "pass"
    assert payload["command"]["exit_code"] == 0


def test_platform_declaration_that_cannot_be_read_is_a_usage_error(
    tmp_root: Path, sealed_project: Path
) -> None:
    """--platform 读不到是用法错误（退出码 2），不是 traceback + 退出码 1。"""

    project = tmp_root / "project"
    completed = run_cli(
        "seal",
        "--root", str(project),
        "--declaration", str(sealed_project),
        "--platform", str(tmp_root / "missing-platform.txt"),
        "--", sys.executable, "-c", "pass",
    )
    assert completed.returncode == 2
    assert "Traceback" not in completed.stderr
    assert "用法错误" in completed.stderr


def test_a_command_that_cannot_be_launched_is_not_a_judgement_failure(
    tmp_root: Path, sealed_project: Path
) -> None:
    """判据命令起不来：退出码 2、说明判据没跑；并且不许写出一份看起来完成的回执。"""

    project = tmp_root / "project"
    receipt = tmp_root / "receipt.json"
    completed = run_cli(
        "seal",
        "--root", str(project),
        "--declaration", str(sealed_project),
        "--out", str(receipt),
        "--", "definitely-not-a-command-xyz",
    )
    assert completed.returncode == 2
    assert "Traceback" not in completed.stderr
    assert "判据命令无法启动" in completed.stderr
    assert "本轮没有结论" in completed.stderr
    assert not receipt.exists(), "判据没有运行：不许伪造一份封条回执"


def test_an_unprovable_declaration_still_exits_3_with_a_receipt(
    tmp_root: Path, sealed_project: Path
) -> None:
    """对照：封条本身证明不了（声明命中不到文件）仍然是 3 + 回执里的 unprovable。"""

    project = tmp_root / "project"
    receipt = tmp_root / "receipt.json"
    first = run_cli(
        "seal",
        "--root", str(project),
        "--declaration", str(sealed_project),
        "--out", str(receipt),
        "--", sys.executable, "-c", "pass",
    )
    assert first.returncode == 0, first.stderr

    # 声明的输入消失之后：封条证明不了，但报的是 3 + 一份写明 unprovable 的回执。
    (project / "declared" / "a.txt").unlink()
    (project / "declared").rmdir()
    second = run_cli(
        "seal",
        "--root", str(project),
        "--declaration", str(sealed_project),
        "--out", str(receipt),
        "--", sys.executable, "-c", "pass",
    )
    assert second.returncode == 3, second.stderr
    assert "seal state: unprovable" in second.stderr
    assert json.loads(receipt.read_text(encoding="utf-8"))["state"] == "unprovable"

def test_digest_and_seal_agree_on_the_same_declaration_failure(
    tmp_root: Path, sealed_project: Path
) -> None:
    """同一种"声明文件读不到"必须给出同一个退出码（复核发现：digest 是 3、seal 是 2）。"""

    project = tmp_root / "project"
    missing = tmp_root / "missing-declaration.txt"

    digested = run_cli("digest", "--root", str(project), "--declaration", str(missing))
    sealed = run_cli(
        "seal", "--root", str(project), "--declaration", str(missing),
        "--", sys.executable, "-c", "pass",
    )
    assert digested.returncode == 2, digested.stderr
    assert sealed.returncode == 2, sealed.stderr
    for completed in (digested, sealed):
        assert "Traceback" not in completed.stderr
        assert "用法错误" in completed.stderr


def test_platform_declaration_failure_is_a_usage_error_in_both_subcommands(
    tmp_root: Path, sealed_project: Path
) -> None:
    """--platform 读不到在 digest 与 seal 里同样是用法错误（2），不是 unprovable（3）。"""

    project = tmp_root / "project"
    missing = tmp_root / "missing-platform.txt"

    digested = run_cli(
        "digest", "--root", str(project), "--declaration", str(sealed_project),
        "--platform", str(missing),
    )
    sealed = run_cli(
        "seal", "--root", str(project), "--declaration", str(sealed_project),
        "--platform", str(missing), "--", sys.executable, "-c", "pass",
    )
    assert digested.returncode == 2, digested.stderr
    assert sealed.returncode == 2, sealed.stderr


def test_digest_still_reports_content_level_unprovable_as_seal_failure(
    tmp_root: Path, sealed_project: Path
) -> None:
    """对照：声明**内容**证明不了（命中不到文件）仍然是 3，不是用法错误。"""

    project = tmp_root / "project"
    (project / "declared" / "a.txt").unlink()
    (project / "declared").rmdir()

    completed = run_cli("digest", "--root", str(project), "--declaration", str(sealed_project))
    assert completed.returncode == 3
    assert "unprovable" in completed.stderr
    assert "Traceback" not in completed.stderr

def test_a_non_object_peer_evidence_is_a_usage_error(
    tmp_root: Path, sealed_project: Path
) -> None:
    """peer-evidence 必须是 JSON 对象：数组 / 字符串形态要走用法错误（2），不是 traceback+1。

    修复前：json.loads 照单收下，下游按映射取键时抛 AttributeError，进程以解释器默认的
    退出码 1 结束——而 1 的含义是"判据跑完且是红的"，这里连判据都还没跑。
    """

    project = tmp_root / "project"
    peer = tmp_root / "peer.json"
    peer.write_text(json.dumps(["这不是一个对象"]) + chr(10), encoding="utf-8")

    completed = run_cli(
        "seal",
        "--root", str(project),
        "--declaration", str(sealed_project),
        "--peer-evidence", str(peer),
        "--", sys.executable, "-c", "pass",
    )

    assert completed.returncode == 2, completed.stderr
    assert "JSON 对象" in completed.stderr
