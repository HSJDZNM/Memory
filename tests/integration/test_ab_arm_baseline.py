"""ab_arm 的基线边界：只收外部任务树，平台仓库自己按用法错误拒绝（退出码 2）。

为什么需要：clean 判据问的是「这棵臂树里能不能读到平台自己的规则集与产物」，而平台仓库必然
在自己的追溯语料里引用规则 ID——拿它当基线时 clean 段报红是**在问一个不该问的问题**。
不受支持的输入要失败关闭，不能产出一份看起来像缺陷的读数。判据是特征**组合**（规则本体 +
核心判定引擎 + 本机门禁三条同时成立），不是单一路径：外部任务树带一份 policies/ 是正常的。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import ab_arm

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


def test_platform_repo_as_baseline_is_a_usage_error(tmp_root: Path, capsys: pytest.CaptureFixture) -> None:
    """整棵平台仓库当基线 → 退出码 2 + 说清"要给外部任务树"。"""

    code = ab_arm.main(["--self-proof", "--baseline", str(REPO_ROOT), "--out", str(tmp_root / "arms")])

    captured = capsys.readouterr()
    assert code == 2
    assert "平台仓库自己" in captured.err
    assert "外部任务树" in captured.err
    assert "--baseline-fixture" in captured.err
    assert not (tmp_root / "arms").exists(), "被拒收的输入不许产出任何臂树"


def test_fixture_baseline_still_passes(tmp_root: Path) -> None:
    """夹具基线不受影响：变异自证照旧 pass。"""

    code = ab_arm.main(
        ["--self-proof", "--baseline-fixture", "shop", "--out", str(tmp_root / "arms")]
    )

    assert code == 0


def test_missing_baseline_is_a_usage_error(capsys: pytest.CaptureFixture) -> None:
    """既没给 --baseline 也没给 --baseline-fixture：用法错误，不是"默认平台仓库"。"""

    code = ab_arm.main(["--materialize"])

    captured = capsys.readouterr()
    assert code == 2
    assert "缺基线" in captured.err


def test_one_platform_feature_alone_does_not_refuse(tmp_root: Path) -> None:
    """只带一条特征的外部任务树不许误伤（判据是三条同时成立）。"""

    tree = tmp_root / "task"
    (tree / "policies" / "architecture").mkdir(parents=True)
    (tree / "policies" / "architecture" / "X-001.yaml").write_text(
        "id: X-001" + chr(10), encoding="utf-8", newline=chr(10)
    )

    assert ab_arm.platform_repo_features(tree) == [ab_arm.PLATFORM_REPO_FEATURES[0]]
    ab_arm.assert_supported_baseline(tree)  # 不抛就是通过
    assert len(ab_arm.platform_repo_features(REPO_ROOT)) == len(ab_arm.PLATFORM_REPO_FEATURES)
