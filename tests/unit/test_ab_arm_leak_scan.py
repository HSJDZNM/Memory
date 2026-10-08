"""ab_arm 的内容扫描：只认**本平台自己的规则 ID**，且不把扫描器自己的声明当证据。

为什么需要：旧模式（大写字母组 + 数字的形态串）会把 UTF-8 / SHA-256 / ISO-8601 / AB-5 /
R16-4 这类标准写法与章节号一并算成"规则身份"，而 tools/ab_arm.py（会被原样复制进臂树）
自己就写着模式串、载荷键名与自证要植入的 ARCH-001——实测一棵只有这个文件的树命中 15 行，
于是一棵真正干净的臂树也会被报 dirty。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import ab_arm

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tree(tmp_root: Path) -> Path:
    tree = tmp_root / "tree"
    (tree / "tools").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "tools" / "ab_arm.py", tree / "tools" / "ab_arm.py")
    return tree


def test_benign_tokens_and_the_scanner_source_do_not_hit(tmp_root: Path) -> None:
    """标准写法与扫描器自身都不算泄露：命中 0。"""

    tree = _tree(tmp_root)
    (tree / "notes.md").write_text(
        "标准写法：UTF-8 / SHA-256 / ISO-8601 / AB-5 / R16-4" + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )

    reading = ab_arm.leak_scan(tree)

    assert reading["hit_count"] == 0, reading["hits"][:5]
    assert reading["files_with_hits"] == 0
    assert ab_arm.SELF_SOURCE in reading["excludes"]


def test_a_real_rule_identity_still_hits(tmp_root: Path) -> None:
    """阳性对照：写一条本平台真实规则 ID 必须命中（这次收窄不是把扫描关掉）。"""

    identity = ab_arm.rule_identities()[0]
    tree = _tree(tmp_root)
    (tree / "notes.md").write_text(
        "评审备注：这条改动会命中 " + identity + "@1。" + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )

    reading = ab_arm.leak_scan(tree)

    assert reading["hit_count"] >= 1
    assert any(hit["path"] == "notes.md" for hit in reading["hits"])


def test_patterns_name_their_source_of_truth() -> None:
    """读数里必须说得出规则 ID 是从哪儿取的（可评审），而不是一个形态串。"""

    patterns = ab_arm.leak_patterns()
    head_regex, head_label = patterns[0]

    assert "policies/*/*.yaml" in head_label
    assert re.escape(ab_arm.rule_identities()[0]) in head_regex
    assert len(ab_arm.rule_identities()) > 0, "本仓库的 policies/ 里应当有规则"
