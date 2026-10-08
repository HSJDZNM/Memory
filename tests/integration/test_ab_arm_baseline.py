"""ab_arm 的基线边界：只收外部任务树，平台仓库自己按用法错误拒绝（退出码 2）。

为什么需要：clean 判据问的是「这棵臂树里能不能读到平台自己的规则集与产物」，而平台仓库必然
在自己的追溯语料里引用规则 ID——拿它当基线时 clean 段报红是**在问一个不该问的问题**。
不受支持的输入要失败关闭，不能产出一份看起来像缺陷的读数。判据是特征**组合**（规则本体 +
核心判定引擎 + 本机门禁三条同时成立），不是单一路径：外部任务树带一份 policies/ 是正常的。
"""

from __future__ import annotations

import json
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

def test_baseline_digest_is_a_real_tree_digest(tmp_root: Path) -> None:
    """[3]：`baseline.digest` 必须是真摘要——旧实现走 `sha256_file(目录)`，恒为 null。

    取证（提交正文里也写了）：全仓 grep `baseline.*digest` 只有 ab_arm 自己那两处生产代码，
    `tools/ab_measure.py` 不读它、tests/ 无断言、evaluation/ 的 A/B 基线里也没有存过它——
    所以"从 null 变成摘要"在仓库内**没有可比性断裂**（没有比较点），如实记下即可。
    """

    code = ab_arm.main(
        ["--self-proof", "--baseline-fixture", "shop", "--out", str(tmp_root / "arms")]
    )
    assert code == 0

    digests: list[object] = []
    for path in sorted((tmp_root / "arms").rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        block = document.get("baseline") if isinstance(document, dict) else None
        if isinstance(block, dict) and "digest" in block:
            digests.append(block["digest"])

    assert digests, "自证/运行载荷里没有 baseline.digest——这条用例的前提不成立"
    # 形状以 tree_digest 的实际约定为准（`"sha256:" + sha256_bytes(...)`，见 tools/ab_arm.py:723），
    # 不是"我以为的 64 位裸 hex"——写不出来的约定不许拿断言钉。
    for item in digests:
        assert isinstance(item, str), digests
        assert item.startswith("sha256:"), digests
        assert len(item) == len("sha256:") + 64, digests
        assert all(character in "0123456789abcdef" for character in item[len("sha256:") :]), digests


def test_tree_digest_tracks_the_tree(tmp_root: Path) -> None:
    """阳性对照：同一份内容摘要相同、改一个字节即变——"有值"不等于"随便一个有值"。"""

    first = tmp_root / "first"
    second = tmp_root / "second"
    for tree in (first, second):
        (tree / "sub").mkdir(parents=True)
        (tree / "sub" / "x.py").write_text("value = 1" + chr(10), encoding="utf-8", newline=chr(10))

    assert ab_arm.tree_digest(first) == ab_arm.tree_digest(second)

    (second / "sub" / "x.py").write_text("value = 2" + chr(10), encoding="utf-8", newline=chr(10))

    assert ab_arm.tree_digest(first) != ab_arm.tree_digest(second)
