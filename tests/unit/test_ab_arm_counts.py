"""ab_arm 的写动作计数：三个计数必须与 counts.bypass_definition 的措辞一致。

审查结论（tools/ab_arm.py:588 附近）：入口不可用（decision=unavailable）时改动仍然应用，
旧实现把它记成 action=applied 并算进 governed_write_actions、bypass_actions 恒为 0——
与紧邻的 bypass_definition（"非 0 只可能来自入口没跑成但改动仍然应用"）自相矛盾。
"""

from __future__ import annotations

import ab_arm


def test_entry_unavailable_but_edit_applied_is_a_bypass() -> None:
    """入口没跑成、改动却落到树上：这正是 bypass_definition 说的那一类，必须计进 bypass。"""

    counts = ab_arm.write_action_counts(
        arm=ab_arm.ARM_ENFORCED, decision="unavailable", action=ab_arm.ACTION_APPLIED
    )
    assert counts == {"write_actions": 1, "governed_write_actions": 0, "bypass_actions": 1}


def test_entry_unavailable_and_apply_failed_is_not_a_bypass() -> None:
    """改动没能落盘：既没被治理、也没绕过去（树上什么都没发生）。"""

    counts = ab_arm.write_action_counts(
        arm=ab_arm.ARM_ENFORCED, decision="unavailable", action="apply_failed"
    )
    assert counts == {"write_actions": 1, "governed_write_actions": 0, "bypass_actions": 0}


def test_governed_allow_and_refusal_are_not_bypasses() -> None:
    allow = ab_arm.write_action_counts(
        arm=ab_arm.ARM_ADVISORY, decision="allow", action=ab_arm.ACTION_APPLIED
    )
    assert allow == {"write_actions": 1, "governed_write_actions": 1, "bypass_actions": 0}

    # 被拒也是"被治理地拒了"：治理计数为 1，但它不是写动作、更不是 bypass。
    refused = ab_arm.write_action_counts(
        arm=ab_arm.ARM_ENFORCED, decision="block", action=ab_arm.ACTION_REFUSED
    )
    assert refused == {"write_actions": 0, "governed_write_actions": 1, "bypass_actions": 0}


def test_off_arm_is_zero_by_construction() -> None:
    """off 臂按构造没有治理路径，不计 bypass（run.json 的 role_note 写明了这一点）。"""

    counts = ab_arm.write_action_counts(
        arm=ab_arm.ARM_OFF, decision=ab_arm.DECISION_NOT_GOVERNED, action=ab_arm.ACTION_APPLIED
    )
    assert counts == {"write_actions": 1, "governed_write_actions": 0, "bypass_actions": 0}


def test_sanitize_tree_does_not_report_children_of_removed_dirs_as_failures(tmp_root: Path) -> None:
    """`dir/**` 连目录本身一起命中：目录被 rmtree 后，子项不该记成"删除失败"。

    旧写法在 candidates 的**删除前快照**上逐个 unlink：父目录先被整棵删掉，子项随后必然
    FileNotFoundError，被 except OSError 收成 removed:false + error —— sanitization 与
    "删除 N 项"因此混进一堆假的失败读数。
    """

    (tmp_root / "policies" / "coding").mkdir(parents=True)
    (tmp_root / "policies" / "coding" / "STYLE-001.yaml").write_text("id: STYLE-001\n", encoding="utf-8")
    (tmp_root / "policies" / "README.md").write_text("# policies\n", encoding="utf-8")

    records = ab_arm.sanitize_tree(tmp_root)

    assert [item for item in records if item["removed"] is False] == []
    assert not (tmp_root / "policies").exists()
    assert any(item["path"] == "policies" and item["removed"] is True for item in records)
