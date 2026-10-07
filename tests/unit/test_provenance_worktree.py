"""控制面针脚的单测：四个名字、严格模式、封条比对与落地状态（方案 §3.1）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from provenance import worktree

pytestmark = pytest.mark.contract


def _tree(tmp_root: Path) -> Path:
    (tmp_root / "pkg").mkdir()
    (tmp_root / "pkg" / "one.py").write_text("one\n", encoding="utf-8")
    (tmp_root / "top.py").write_text("top\n", encoding="utf-8")
    return tmp_root


def _fail_reading(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """让某一个文件名读不出来——不必真去改文件权限（跨平台、且不碰 ACL）。"""

    real = worktree._read_bytes

    def reader(path: Path) -> bytes:
        if path.name == name:
            raise OSError(13, "Permission denied")
        return real(path)

    monkeypatch.setattr(worktree, "_read_bytes", reader)


def test_tree_digest_is_stable_and_content_sensitive(tmp_root: Path) -> None:
    tree = _tree(tmp_root)
    first = worktree.tree_digest(tree)
    second = worktree.tree_digest(tree)

    assert first == second, "相同输入必须得到逐字节相同的指纹"
    assert first.sha256.startswith("sha256:")
    assert first.files == 2

    (tree / "top.py").write_text("changed\n", encoding="utf-8")
    assert worktree.tree_digest(tree).sha256 != first.sha256


def test_workspace_digest_excludes_build_output(tmp_root: Path) -> None:
    tree = _tree(tmp_root)
    (tree / "__pycache__").mkdir()
    (tree / "__pycache__" / "x.pyc").write_text("x", encoding="utf-8")

    assert worktree.workspace_tree_digest(tree).files == 2
    assert worktree.tree_digest(tree).files == 3, "不带排除时它照样是这棵树的一部分"


def test_strict_mode_refuses_what_it_cannot_read(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_reading(monkeypatch, "top.py")

    with pytest.raises(worktree.UnprovableError):
        worktree.tree_digest(_tree(tmp_root))


def test_annotation_mode_counts_only_what_it_could_read(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_reading(monkeypatch, "top.py")

    digest = worktree.tree_digest(_tree(tmp_root), strict=False)

    assert digest.files == 1, "标注模式：读不到的不进指纹（Phase 5 既有口径）"


def test_tree_digest_refuses_a_missing_root(tmp_root: Path) -> None:
    with pytest.raises(worktree.UnprovableError):
        worktree.tree_digest(tmp_root / "nope")


def test_referenced_inputs_digest_covers_the_declaration_only(tmp_root: Path) -> None:
    tree = _tree(tmp_root)
    before = worktree.referenced_inputs_digest(tree, ["pkg/*.py"])

    (tree / "top.py").write_text("changed\n", encoding="utf-8")
    assert worktree.referenced_inputs_digest(tree, ["pkg/*.py"]).sha256 == before.sha256

    (tree / "pkg" / "one.py").write_text("changed\n", encoding="utf-8")
    assert worktree.referenced_inputs_digest(tree, ["pkg/*.py"]).sha256 != before.sha256


def test_referenced_inputs_digest_refuses_empty_and_unmatched(tmp_root: Path) -> None:
    tree = _tree(tmp_root)

    with pytest.raises(worktree.UnprovableError):
        worktree.referenced_inputs_digest(tree, [])
    with pytest.raises(worktree.UnprovableError):
        worktree.referenced_inputs_digest(tree, ["missing/**/*.py"])


def test_a_declaration_matching_only_excluded_files_is_unprovable(tmp_root: Path) -> None:
    """声明只命中被排除的文件时必须 unprovable，而不是"覆盖 0 个文件"的封条（复核发现）。

    排除项是声明的，不是看不见的默认值；但它必须同时约束"命中判据"——否则一份
    只声明 pkg/one.pyc 的声明会拿到空串的 sha256，看起来像一次可复核的封条。
    """

    tree = _tree(tmp_root)
    (tree / "pkg" / "one.pyc").write_text("bytecode", encoding="utf-8")

    # 对照：同一声明里的 .py 照常命中，被排除的 .pyc 不参与指纹。
    assert worktree.referenced_inputs_digest(tree, ["pkg/*"]).files == 1

    for declaration in (["pkg/one.pyc"], ["**/*.pyc"]):
        with pytest.raises(worktree.UnprovableError):
            worktree.referenced_inputs_digest(tree, declaration)
    with pytest.raises(worktree.UnprovableError):
        worktree.platform_revision(tree, ["**/*.pyc"])


def test_relative_paths_are_lexical_not_resolved(tmp_root: Path) -> None:
    """_relative 必须词法计算（复核发现）。

    resolve() 在链接指向根外时让 relative_to 失败，于是退回一个随调用方式变化的
    （可能绝对的）路径；同一棵树在不同挂载点/不同 root 写法下会算出不同指纹。
    """

    tree = tmp_root / "tree"
    tree.mkdir()
    _tree(tree)
    elsewhere = tmp_root / "elsewhere"  # 树**之外**的目录
    elsewhere.mkdir()
    (elsewhere / "x.py").write_text("x" + chr(10), encoding="utf-8")

    relative = worktree._relative(elsewhere / "x.py", tree)
    assert relative == "../elsewhere/x.py"
    assert not Path(relative).is_absolute()
    # 根内的取值与以前一致；根目录本身写成 "."。
    assert worktree._relative(tree / "pkg" / "one.py", tree) == "pkg/one.py"
    assert worktree._relative(tree, tree) == "."


def test_symlinks_are_recorded_as_themselves(tmp_root: Path) -> None:
    """根内的文件链接记录的是链接这一项，不是它的目标（否则制造重复键）。"""

    tree = _tree(tmp_root)
    link = tree / "pkg" / "alias.py"
    try:
        link.symlink_to(tree / "pkg" / "one.py")
    except (OSError, NotImplementedError):
        pytest.skip("本机不允许创建符号链接（Windows 需要特权）：该断言在 CI/Linux 上执行")

    assert worktree._relative(link, tree) == "pkg/alias.py"
    assert worktree.tree_digest(tree).files == 3  # top.py / pkg/one.py / pkg/alias.py


def test_platform_revision_scope_comes_from_the_declaration(tmp_root: Path) -> None:
    tree = _tree(tmp_root)
    before = worktree.platform_revision(tree, ["pkg/*.py"])

    (tree / "top.py").write_text("changed\n", encoding="utf-8")

    assert worktree.platform_revision(tree, ["pkg/*.py"]).sha256 == before.sha256


def test_seal_pair_passes_when_nothing_moves(tmp_root: Path) -> None:
    tree = _tree(tmp_root)
    declaration = ["pkg/*.py"]

    comparison = worktree.compare_seals(
        worktree.seal(tree, declaration, declaration),
        worktree.seal(tree, declaration, declaration),
    )

    assert comparison.state == "pass"
    assert comparison.differences == {"added": [], "modified": [], "removed": []}


def test_seal_pair_reports_an_external_write(tmp_root: Path) -> None:
    tree = _tree(tmp_root)
    declaration = ["pkg/*.py"]
    pre = worktree.seal(tree, declaration, declaration)

    (tree / "pkg" / "one.py").write_text("changed\n", encoding="utf-8")

    comparison = worktree.compare_seals(pre, worktree.seal(tree, declaration, declaration))

    assert comparison.state == "external_write"
    assert comparison.differences == {"added": [], "modified": ["pkg/one.py"], "removed": []}


def test_seal_pair_reports_added_and_removed(tmp_root: Path) -> None:
    tree = _tree(tmp_root)
    declaration = ["pkg/*.py"]
    pre = worktree.seal(tree, declaration, declaration)

    (tree / "pkg" / "two.py").write_text("two\n", encoding="utf-8")
    (tree / "pkg" / "one.py").unlink()

    comparison = worktree.compare_seals(pre, worktree.seal(tree, declaration, declaration))

    assert comparison.differences == {
        "added": ["pkg/two.py"],
        "modified": [],
        "removed": ["pkg/one.py"],
    }


def test_evidence_tree_digest_is_the_same_implementation(tmp_root: Path) -> None:
    tree = _tree(tmp_root)

    assert worktree.evidence_tree_digest(tree).sha256 == worktree.tree_digest(tree).sha256


def test_landing_states_are_not_collapsed() -> None:
    assert worktree.resolve_landing_state("landed_unverified") == "landed_unverified"

    with pytest.raises(worktree.LandingStateError):
        worktree.resolve_landing_state("verified")
    with pytest.raises(worktree.LandingStateError):
        worktree.resolve_landing_state("round_verified")
    with pytest.raises(worktree.LandingStateError):
        worktree.resolve_landing_state("landed_peer_verified")

    evidence = {"verifier": "peer-a", "artifact": "receipt.json", "sha256": "a" * 64}
    assert (
        worktree.resolve_landing_state("landed_peer_verified", peer_evidence=evidence)
        == "landed_peer_verified"
    )
    with pytest.raises(worktree.LandingStateError):
        worktree.resolve_landing_state(
            "landed_peer_verified", peer_evidence=dict(evidence, sha256="not-a-hash")
        )


def test_peer_evidence_must_carry_real_strings() -> None:
    """null / 数字都不是"给了一个值"：str(None) == "None" 会放行伪造的 peer 验收（复核发现）。"""

    good = {"verifier": "peer-a", "artifact": "receipt.json", "sha256": "a" * 64}
    assert (
        worktree.resolve_landing_state("landed_peer_verified", peer_evidence=good)
        == "landed_peer_verified"
    )
    for broken in (
        {"verifier": None, "artifact": None, "sha256": "a" * 64},
        {"verifier": "", "artifact": "receipt.json", "sha256": "a" * 64},
        {"verifier": "peer-a", "artifact": "   ", "sha256": "a" * 64},
        {"verifier": 7, "artifact": "receipt.json", "sha256": "a" * 64},
        {"verifier": "peer-a", "artifact": "receipt.json", "sha256": None},
        # 64 位十进制整数：str() 之后能骗过 sha256 的正则，但它不是摘要。
        {"verifier": "peer-a", "artifact": "receipt.json", "sha256": 10**63},
    ):
        with pytest.raises(worktree.LandingStateError):
            worktree.resolve_landing_state("landed_peer_verified", peer_evidence=broken)


def test_load_declaration_ignores_comments_and_blank_lines(tmp_root: Path) -> None:
    path = tmp_root / "declaration.txt"
    path.write_text("# 注释\n\nsrc/**/*.py\n   \ntools/*.py\n", encoding="utf-8")

    assert worktree.load_declaration(path) == ("src/**/*.py", "tools/*.py")

    with pytest.raises(worktree.UnprovableError):
        worktree.load_declaration(tmp_root / "missing.txt")
