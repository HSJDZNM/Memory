"""adapters CLI：显式给的开关要么生效，要么显式拒绝——不许静默忽略。"""

from __future__ import annotations

from adapters.cli import EXIT_USAGE, main
from conftest import REPO_ROOT


def test_matrix_refuses_a_custom_approved_path_instead_of_ignoring_it(capsys):
    """matrix 固定读默认清单：用户给了别的 --approved 时必须报错，而不是照旧读默认。"""

    code = main(
        ["--approved", str(REPO_ROOT / "adapters" / "definitely-not-approved.json"), "matrix"]
    )

    assert code == EXIT_USAGE
    assert "不支持 --approved" in capsys.readouterr().err
