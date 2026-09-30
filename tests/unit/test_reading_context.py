"""provenance.reading_context 的回归：统一形状只有一份实现，而且它只加旁注、不改判定。

三条最容易走样的纪律各有用例钉住：

1. 路径一律仓库相对，工作区之外折叠成 <outside-workspace>，没给写 <unset>（**不放绝对路径**）；
2. 读不到 = status=unavailable + reason（**不写一个"看起来像"的常量**）；
   "不适用"（not_applicable）与"读不到"是两件事；
3. 它是**旁注**：除了编程错误（未知 source / 未知 sandbox），本模块不抛异常——
   一份读数不该因为附注写不出来就整份写不出来。
"""

from __future__ import annotations

import json
import platform
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from provenance import reading_context as reading  # noqa: E402


def _strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def test_display_path_is_repo_relative_and_never_absolute(tmp_root):
    inside = tmp_root / "nested" / "file.yaml"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text("x: 1\n", encoding="utf-8")

    assert reading.display_path(inside, root=REPO_ROOT).startswith(".tmp/")
    assert reading.display_path(REPO_ROOT, root=REPO_ROOT) == "."
    assert reading.display_path(Path.home() / "elsewhere", root=REPO_ROOT) == reading.OUTSIDE_WORKSPACE
    assert reading.display_path(None, root=REPO_ROOT) == reading.UNSET
    assert reading.display_path("   ", root=REPO_ROOT) == reading.UNSET


def test_declaration_block_separates_unavailable_from_not_applicable(tmp_root):
    target = tmp_root / "validators.yaml"
    target.write_text("validators: []\n", encoding="utf-8")

    block = reading.declaration_block(target, root=REPO_ROOT)
    assert block["status"] == reading.STATUS_AVAILABLE
    assert block["path"].startswith(".tmp/")
    assert block["digest"] == reading.declaration_digest(target)
    assert block["digest"].startswith("sha256:")

    missing = reading.declaration_block(tmp_root / "nope.yaml", root=REPO_ROOT)
    assert missing["status"] == reading.STATUS_UNAVAILABLE
    assert "读不到" in missing["reason"]

    assert reading.not_applicable() == {"status": reading.STATUS_NOT_APPLICABLE}
    assert reading.declaration_digest(None) is None


def test_tree_block_names_the_tree_and_degrades_instead_of_raising(tmp_root, monkeypatch):
    block = reading.tree_block(tmp_root)
    assert block["status"] == reading.STATUS_AVAILABLE
    assert block["scope"] == reading.SCOPE_WORKSPACE
    assert block["digest"].startswith("sha256:")
    assert len(block["revision"]) == 40, "修订号是 git rev-parse HEAD 的原文"

    # 调用方已经算过的摘要原样沿用（义务门禁走的就是这条路），不另算一遍。
    reused = reading.tree_block(tmp_root, digest="sha256:" + "0" * 64)
    assert reused["digest"] == "sha256:" + "0" * 64

    unprovable = reading.tree_block(tmp_root, digest="unprovable:ImportError:boom")
    assert unprovable["status"] == reading.STATUS_UNAVAILABLE
    assert "unprovable" in unprovable["reason"]
    assert "digest" not in unprovable, "读不到就不许留下一个像摘要的字符串"

    monkeypatch.setattr(reading, "git_revision", lambda root: None)
    no_revision = reading.tree_block(tmp_root)
    assert no_revision["status"] == reading.STATUS_UNAVAILABLE
    assert "git" in no_revision["reason"]
    assert no_revision["digest"].startswith("sha256:"), "取到的那部分照旧写出来"

    gone = reading.tree_block(tmp_root / "missing")
    assert gone["status"] == reading.STATUS_UNAVAILABLE
    assert "树摘要读不到" in gone["reason"]


def test_host_block_reports_facts_and_rejects_unknown_enum():
    block = reading.host_block()
    assert block["sandbox"] == reading.SANDBOX_UNKNOWN
    assert block["python"] == platform.python_version()
    assert block["platform"].startswith(platform.system())

    extra = reading.host_block(sandbox=reading.SANDBOX_RESTRICTED, extra={"isolated_home": True})
    assert extra["sandbox"] == "restricted"
    assert extra["isolated_home"] is True

    with pytest.raises(ValueError):
        reading.host_block(sandbox="sandboxed")


def test_run_block_is_volatile_by_design():
    first = reading.run_block()
    second = reading.run_block()
    assert first["id"] != second["id"]
    uuid.UUID(first["id"])
    assert first["started_at"].endswith("Z")

    pinned = reading.run_block(started_at="2026-09-30T00:00:00Z", run_id="fixed")
    assert pinned == {"id": "fixed", "started_at": "2026-09-30T00:00:00Z"}


def test_build_has_exactly_the_five_keys(tmp_root):
    block = reading.build(
        source=reading.SOURCE_CLI,
        tree=reading.tree_block(tmp_root),
        declarations={"registry": reading.not_applicable()},
        host=reading.host_block(),
        run=reading.run_block(started_at="2026-09-30T00:00:00Z", run_id="fixed"),
    )
    assert sorted(block) == ["declarations", "host", "run", "source", "tree"]
    assert block["source"] == "cli"

    with pytest.raises(ValueError):
        reading.build(source="guess")

    with pytest.raises(ValueError):
        reading.host_block(sandbox="nope")


def test_no_value_in_the_context_is_an_absolute_path(tmp_root):
    target = tmp_root / "validators.yaml"
    target.write_text("validators: []\n", encoding="utf-8")

    block = reading.build(
        source=reading.SOURCE_GATE,
        tree=reading.tree_block(tmp_root),
        declarations={
            "registry": reading.declaration_block(target, root=REPO_ROOT),
            "must_not_apply": reading.not_applicable(),
        },
        host=reading.host_block(
            sandbox=reading.SANDBOX_RESTRICTED,
            extra={"dsh_home": reading.display_path(Path.home(), root=REPO_ROOT)},
        ),
    )
    values = list(_strings(block))
    assert values, "空载荷也能通过这条断言，那不是我们要的"
    for value in values:
        assert not Path(value).is_absolute(), value
    assert reading.OUTSIDE_WORKSPACE in values, "工作区之外的根必须折叠成显式标记"
    assert str(REPO_ROOT) not in json.dumps(block, ensure_ascii=False)
