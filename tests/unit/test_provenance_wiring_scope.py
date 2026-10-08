"""边界声明 adapters/wiring-scope.yaml 的加载与校验（方案 §3.5 的最小形态）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import REPO_ROOT

from provenance.wiring_scope import WiringScopeError, load_wiring_scope

pytestmark = pytest.mark.contract

IN_SCOPE = """  - id: governed-session-hook
    decision: in_scope
    kind: agent_runtime
    owner: platform
    reason: 受控会话由本仓库治理。
    consequence: 接不上就不放行。
"""

OUT_OF_SCOPE = """  - id: desktop-entry-points
    decision: out_of_scope
    kind: agent_runtime
    owner: host
    reason: 桌面通道是主机配置。
    consequence: 只报告，不签发 allow / block。
    expires_at: "2026-12-31"
    renewals: []
"""


def _document(*entries: str) -> str:
    return 'schema_version: "1"\nscope:\n' + "".join(entries)


def _write(tmp_root: Path, text: str) -> Path:
    path = tmp_root / "wiring-scope.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_repository_declaration_is_valid() -> None:
    scope = load_wiring_scope(REPO_ROOT / "adapters" / "wiring-scope.yaml")
    summary = scope.as_json()

    assert summary["schema_version"] == "2"
    assert summary["declared"] == 6
    assert summary["by_decision"] == {
        "in_scope": 1,
        "out_of_scope": 4,
        "expected_absent": 1,
    }
    # schema "2" 的数据侧：发现侧 kind → 声明侧 kind 的映射（24 号 §2.1 规则 2）。
    assert summary["channel_kinds"] == {"dsh-profile": "agent_runtime"}
    # 2026-10-01 第 25 轮（裁定⑤，24 号 §8.4）：12 条被发现的通道**每一条**都有显式 covers，
    # 因此这份读数不再是空的——它现在是「声明 × 发现」的连接键本身。
    # 2026-10-03 第 27 轮（评审裁定①②，23 号 §17 / 24 号 §8.5）：评审方**二次更正**——
    # verify-bc / verify-dead / verify-exit2 / verify-gov / verify-manual 是治理能力验证轮的
    # **实验 profile**，不是受控会话；使用者已把这 5 个 profile 移出本机，所以撤回第 26 轮并入的
    # 三条 covers，并删除 dsh-verify-profiles / dsh-verify-dead-channel 两条声明。
    # **decision 一个都没改**；这份期望钉住的是「覆盖关系与声明条目随宿主同批收尾」。
    assert summary["covers"] == {
        "governed-session-hook": [
            "dsh:governed",
            "dsh:governed-*",
        ],
        "desktop-entry-points": ["dsh:desktop"],
        "dsh-web-channel": ["dsh:web"],
        "dsh-headless-channel": ["dsh:headless"],
    }
    # governs_tree 只列**写了**的那些（裁定④：没写 = 读取侧的 unknown，不进摘要）。
    assert summary["governs_tree"] == {"governed-session-hook": "other"}


def test_two_decisions_load_and_are_counted(tmp_root: Path) -> None:
    scope = load_wiring_scope(_write(tmp_root, _document(IN_SCOPE, OUT_OF_SCOPE)))

    assert scope.as_json()["by_decision"] == {
        "in_scope": 1,
        "out_of_scope": 1,
        "expected_absent": 0,
    }


def test_unknown_keys_are_rejected(tmp_root: Path) -> None:
    top_level = 'schema_version: "1"\nscope: []\nextra: 1\n'
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, top_level))

    entry = IN_SCOPE + "    secret: 1\n"
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, _document(entry)))


def test_unknown_decision_is_rejected(tmp_root: Path) -> None:
    entry = IN_SCOPE.replace("decision: in_scope", "decision: maybe")
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, _document(entry)))

    assert "decision" in str(failure.value)


def test_empty_reason_is_rejected(tmp_root: Path) -> None:
    entry = IN_SCOPE.replace("reason: 受控会话由本仓库治理。", 'reason: "   "')
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, _document(entry)))


def test_in_scope_must_not_carry_an_expiry(tmp_root: Path) -> None:
    entry = IN_SCOPE + '    expires_at: "2026-12-31"\n'
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, _document(entry)))

    assert "过期日" in str(failure.value)


def test_out_of_scope_must_carry_an_expiry(tmp_root: Path) -> None:
    entry = OUT_OF_SCOPE.replace('    expires_at: "2026-12-31"\n', "")
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, _document(entry)))

    assert "expires_at" in str(failure.value)


def test_a_bad_date_is_rejected(tmp_root: Path) -> None:
    entry = OUT_OF_SCOPE.replace('"2026-12-31"', '"2026-13-99"')
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, _document(entry)))


def test_duplicate_ids_are_rejected(tmp_root: Path) -> None:
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, _document(IN_SCOPE, IN_SCOPE)))

    assert "重复" in str(failure.value)


def test_unknown_schema_version_is_rejected(tmp_root: Path) -> None:
    text = _document(IN_SCOPE).replace('schema_version: "1"', 'schema_version: "3"')
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, text))


def test_a_schema_1_declaration_still_loads(tmp_root: Path) -> None:
    """裁定①：加载器**同时接受 "1" 和 "2"**，新字段一律可选——"2" 不是一次破坏性变更。"""

    scope = load_wiring_scope(_write(tmp_root, _document(IN_SCOPE, OUT_OF_SCOPE)))

    assert scope.schema_version == "1"
    assert scope.channel_kinds == {}
    # 没写的新字段落在各自的默认值上：covers 空、governs_tree **没写**（None）、tree_ref 无。
    assert scope.scope[0].covers == ()
    assert scope.scope[0].governs_tree is None
    assert scope.scope[0].tree_ref is None
    # 裁定④（2026-10-01）：没写 = **读取侧**的 unknown，不是 self。
    assert scope.scope[0].declared_governs_tree() == "unknown"
    assert scope.as_json()["governs_tree"] == {}


def test_schema_2_optional_fields_load_and_unknown_values_are_rejected(tmp_root: Path) -> None:
    """新字段能读；但**未知取值**仍按核心约束 3 报错（与 decision 同类的 FATAL，不静默忽略）。"""

    text = (
        'schema_version: "2"\n'
        "channel_kinds:\n  dsh-profile: agent_runtime\n"
        "scope:\n"
        + IN_SCOPE
        + '    covers: ["dsh:gov*"]\n'
        + "    governs_tree: other\n"
        + "    tree_ref: <outside-workspace>\n"
    )
    scope = load_wiring_scope(_write(tmp_root, text))

    assert scope.scope[0].covers == ("dsh:gov*",)
    assert scope.scope[0].governs_tree == "other"
    assert scope.scope[0].tree_ref == "<outside-workspace>"
    assert scope.channel_kinds == {"dsh-profile": "agent_runtime"}
    assert scope.as_json()["governs_tree"] == {"governed-session-hook": "other"}

    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, text.replace("governs_tree: other", "governs_tree: othr")))


def test_covers_without_governs_tree_reads_as_unknown(tmp_root: Path) -> None:
    """裁定④（2026-10-01，24 号 §8.4）：**写了 covers 但没写 governs_tree** → 读取侧 unknown。

    为什么不是锦上添花：按 24 号 §2.1 的边界，「`relation=other` 而 `tree.declared != other`」
    **不进五个差集**——默认 `self` 会让这对矛盾**静默存在**。
    """

    text = (
        'schema_version: "2"\n'
        "channel_kinds:\n  dsh-profile: agent_runtime\n"
        "scope:\n"
        + IN_SCOPE
        + '    covers: ["dsh:governed", "dsh:governed-*"]\n'
    )
    scope = load_wiring_scope(_write(tmp_root, text))

    assert scope.scope[0].covers == ("dsh:governed", "dsh:governed-*")
    assert scope.scope[0].governs_tree is None
    assert scope.scope[0].declared_governs_tree() == "unknown"
    # 摘要只列**写了**的那些：没写的不出现（「没有人写」与「写空了」分得开）。
    assert scope.as_json()["governs_tree"] == {}


def test_an_explicit_self_is_reported_while_an_omission_is_not(tmp_root: Path) -> None:
    """写了 `self` 与没写分得开：前者进摘要（那是**有人写过的声明值**），后者不进。"""

    text = (
        'schema_version: "2"\n'
        "scope:\n"
        + IN_SCOPE
        + "    governs_tree: self\n"
        + OUT_OF_SCOPE
    )
    scope = load_wiring_scope(_write(tmp_root, text))

    assert scope.scope[0].declared_governs_tree() == "self"
    assert scope.scope[1].declared_governs_tree() == "unknown"
    assert scope.as_json()["governs_tree"] == {"governed-session-hook": "self"}


def test_unknown_is_not_a_writable_governs_tree_value(tmp_root: Path) -> None:
    """`unknown` 是读取侧的翻译，**不是可写取值**：显式写它在加载期就报错（不静默接受）。"""

    text = 'schema_version: "2"\nscope:\n' + IN_SCOPE + "    governs_tree: unknown\n"
    with pytest.raises(WiringScopeError) as failure:
        load_wiring_scope(_write(tmp_root, text))

    assert "governs_tree" in str(failure.value)


def test_missing_file_and_broken_yaml_are_rejected(tmp_root: Path) -> None:
    with pytest.raises(WiringScopeError):
        load_wiring_scope(tmp_root / "missing.yaml")
    with pytest.raises(WiringScopeError):
        load_wiring_scope(_write(tmp_root, "scope: [unclosed\n"))

# —— 加载期校验（L8 low #8/#9/#10）：三条都是"注释里承诺了、模型里没查"的形态，
#    用例必须证明它们在加载期真的失败，而不是被静默收下。

def _entry_with(**overrides: str) -> str:
    fields = {
        "id": "case-entry",
        "decision": "out_of_scope",
        "kind": "agent_runtime",
        "owner": "host",
        "reason": "实验通道，不在治理范围。",
        "consequence": "只报告。",
        "expires_at": '"2026-12-31"',
    }
    fields.update(overrides)
    return "  - " + "\n    ".join(f"{key}: {value}" for key, value in fields.items()) + "\n"

def test_non_canonical_dates_are_refused(tmp_root):
    """#8：YYYYMMDD / 周日期这类 ISO 变体不许进声明文件（口径必须与仓库其余数据一致）。

    修复前 _require_date 只调 date.fromisoformat，它把这些写法一并收下并原样回显进报告。
    """

    for bad in ("20261231", "2026-W40-1", "2026-12-31T00:00:00"):
        with pytest.raises(WiringScopeError) as error:
            load_wiring_scope(
                _write(tmp_root, _document(_entry_with(expires_at=f"'{bad}'")))
            )
        assert "YYYY-MM-DD" in str(error.value), error.value

    # 反真空：规范形态照常加载。
    scope = load_wiring_scope(
        _write(tmp_root, _document(_entry_with(expires_at="'2026-12-31'")))
    )
    assert scope.as_json()["declared"] == 1

def test_tree_ref_must_be_a_pointer_or_outside_marker(tmp_root):
    """#9：tree_ref 只放指针（仓库相对路径 / <outside-workspace>），且与 governs_tree 不矛盾。

    修复前这一条只写在注释里：绝对路径、路径穿越、一段说明文字、以及
    governs_tree=self + tree_ref 的自相矛盾声明都能原样加载。
    """

    for bad in ("/etc/passwd", "../../etc/passwd", "docs/../etc/passwd", "这是一段说明文字", "has space/x"):
        with pytest.raises(WiringScopeError) as error:
            load_wiring_scope(
                _write(tmp_root, _document(_entry_with(tree_ref=f"'{bad}'", governs_tree="other")))
            )
        assert "tree_ref" in str(error.value), error.value

    with pytest.raises(WiringScopeError) as error:
        load_wiring_scope(
            _write(tmp_root, _document(_entry_with(tree_ref="'docs/x.md'", governs_tree="self")))
        )
    assert "governs_tree" in str(error.value), error.value

    # 反真空：合法指针（仓库相对路径 / 工作区外标记）照常加载。
    for good in ("docs/policies/x.md", "<outside-workspace>"):
        scope = load_wiring_scope(
            _write(tmp_root, _document(_entry_with(tree_ref=f"'{good}'", governs_tree="other")))
        )
        assert scope.as_json()["declared"] == 1

def test_channel_kinds_must_be_non_empty(tmp_root):
    """#10：channel_kinds 的空键 / 空值会静默落到 undeclared，必须加载期拒绝。

    修复前这个字段没有任何形状校验：空值不会报错，只会让该通道被判成"没有声明覆盖"。
    """

    for bad in ('{dsh-profile: ""}', '{"": agent_runtime}'):
        text = _document(_entry_with()) + f"channel_kinds: {bad}\n"
        with pytest.raises(WiringScopeError) as error:
            load_wiring_scope(_write(tmp_root, text))
        assert "channel_kinds" in str(error.value), error.value

    # 反真空：合法映射照常加载（值可以与任何已声明的 kind 不同——那是"映射存在但暂无匹配
    # 条目"的已承认状态，不在本用例的判据里）。
    good = _document(_entry_with()) + "channel_kinds:\n  dsh-profile: agent_runtime\n"
    scope = load_wiring_scope(_write(tmp_root, good))
    assert scope.as_json()["channel_kinds"] == {"dsh-profile": "agent_runtime"}
