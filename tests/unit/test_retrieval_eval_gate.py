"""retrieval_eval 的门槛必须落在真的评测过的方法上（失败关闭，不是空列表上的 all()）。

为什么需要：`gated` 是"--gate 点名的方法"与"--method 跑过的方法"的交集；交集为空时
`all([]) == True`，于是 result=pass、退出码 0，而载荷里的 gated_methods 照样写着那个
**一次都没跑**的方法——门槛工具在"没评测"与"通过了"之间失明。

实测（HEAD 版，.tmp/repro-retrieval-eval.py）：`--method fts5 --gate vector --record ...`
退 0、result=pass、gated_methods=['vector']，而 methods 里只有 fts5。
修复后：建库之前就以用法错误拒收（退出码 2），不产出任何读数。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import retrieval_eval


def test_gate_coverage_reports_methods_that_were_not_evaluated() -> None:
    assert retrieval_eval._gate_coverage("vector", "fts5") == ["vector"]
    assert retrieval_eval._gate_coverage("both", "fts5") == ["vector"]
    assert retrieval_eval._gate_coverage("fts5", "vector") == ["fts5"]
    # 合法组合：门槛只落在跑过的方法上
    assert retrieval_eval._gate_coverage("fts5", "both") == []
    assert retrieval_eval._gate_coverage("both", "both") == []
    assert retrieval_eval._gate_coverage("fts5", "fts5") == []


@pytest.mark.parametrize(
    "gate,method",
    [("vector", "fts5"), ("both", "fts5"), ("fts5", "vector")],
)
def test_disjoint_gate_is_rejected_before_any_work(
    gate: str, method: str, tmp_root: Path, capsys: pytest.CaptureFixture
) -> None:
    """没有受门槛约束的评测 = 自相矛盾的调用：退出码 2，且不建库、不产出读数。"""

    db = tmp_root / "index.sqlite3"
    out = tmp_root / "out.json"

    with pytest.raises(SystemExit) as excinfo:
        retrieval_eval.main(
            ["--method", method, "--gate", gate, "--db", str(db), "--out", str(out)]
        )

    assert excinfo.value.code == 2
    assert "没有评测" in capsys.readouterr().err
    assert not out.exists(), "被拒收的调用不许留下读数"
    assert not db.exists(), "校验在建库之前，不该动索引库"
