"""adapters CLI：显式给的开关要么生效，要么显式拒绝——不许静默忽略。"""

from __future__ import annotations

from adapters.cli import EXIT_OK, EXIT_USAGE, main
from conftest import REPO_ROOT


def test_matrix_refuses_a_custom_approved_path_instead_of_ignoring_it(capsys):
    """matrix 固定读默认清单：用户给了别的 --approved 时必须报错，而不是照旧读默认。"""

    code = main(
        ["--approved", str(REPO_ROOT / "adapters" / "definitely-not-approved.json"), "matrix"]
    )

    assert code == EXIT_USAGE
    assert "不支持 --approved" in capsys.readouterr().err


def test_matrix_without_an_explicit_approved_path_is_the_default_path(capsys):
    """**没给** --approved 是默认行为：必须照常跑通，不能被上面那条拒绝逻辑误伤。

    回归背景（7ff49f8 的形态，Lead 在 7a432e2 修掉）：第一版写成
    Path(args.approved).resolve() != Path(DEFAULT_APPROVED_PATH).resolve()，而没给这个
    参数时 args.approved 是 None → Path(None) 抛 TypeError，门禁第 20 步
    "python -m adapters.cli matrix"（不带任何参数）整步红。把"静默忽略"改成"显式拒绝"时，
    「参数没给」与「给了但值不同」是两种形态，用例必须各有一条。
    """

    code = main(["matrix"])

    assert code == EXIT_OK, capsys.readouterr().err
    assert "adapter support matrix" in capsys.readouterr().out
