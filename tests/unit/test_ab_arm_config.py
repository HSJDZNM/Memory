"""`materialize_arm_config.py` 的回归：占位符替换、模板拒绝、退出码、确定性、载荷无绝对路径。

判据来源：`ab/bank/arm-configs/README.md`、`materialize_arm_config.py` 的模块 docstring、
AGENTS 第 3 / 45 / 55 条。所有临时件都落在 `tmp_path`（函数级、唯一），**不碰** `.tmp/` 下的
共享路径，也不依赖 `.tmp/bank/arm-configs` 里那次一次性现场配置。

两条用例直接扫**受跟踪的模板**：模板漏进绝对路径时物化脚本自己查不出来（它只查替换前的文本），
所以"模板是机器中立的"必须是仓库里那份文件的断言，不是脚本的自我声明。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BANK = REPO_ROOT / "docs" / "project" / "engineering-policy-platform" / "testing" / "ab" / "bank"
HARNESS = BANK / "harness"
TEMPLATES = BANK / "arm-configs"
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import materialize_arm_config as materialize  # noqa: E402

PLACEHOLDER = "${REPO_ROOT}"

#: 受跟踪模板 / 物化副本**都只有**这四个文件；approval.json 由使用者按 run 签发，不在模板里。
ARM_FILES = (
    "dsh-adapter.yaml",
    "hooks.json",
    "tool-registry.local.yaml",
    "tool-registry.approved.json",
)

ADAPTER_TEMPLATE = (
    "agent_version: \"0.1.0\"",
    "project_root: ..",
    "rules:",
    "  - ${REPO_ROOT}/policies",
    "rules_root: ${REPO_ROOT}",
    "pre_evidence:",
    "  enabled: true",
    "  registry_root: ${REPO_ROOT}/configs/before",
    "",
)
HOOKS_JSON = "{\n  \"hooks\": {\"PreToolUse\": []}\n}\n"
REGISTRY_YAML = "registry_schema_version: \"1.4\"\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _digest(root: Path, names: Sequence[str]) -> str:
    """独立于被测实现重算组合摘要：按**路径**升序，<sha256> + 两个空格 + 相对路径。"""

    lines: List[str] = []
    for name in sorted(names):
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        lines.append("%s  %s" % (digest, name))
    return "sha256:" + hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def _read_payload(target: Path) -> Dict[str, Any]:
    return json.loads((target / "materialized.json").read_text(encoding="utf-8"))


def _string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _string_values(key)
            yield from _string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_values(child)


def _looks_absolute(value: str) -> bool:
    return value.startswith("/") or re.match("^[A-Za-z]:", value) is not None


def _run(template: Path, target: Path, repo_root: Path, *extra: str) -> int:
    argv = ["--template", str(template), "--target", str(target), "--repo-root", str(repo_root)]
    return materialize.main(argv + list(extra))


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """一个带 .git 的最小仓库根：`--repo-root` 的检查只认 `.git` 是否存在。"""

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    return repo


@pytest.fixture()
def template(fake_repo: Path) -> Path:
    """一份最小模板：dsh-adapter.yaml（三个占位）+ hooks.json + 一个原样复制的文件。"""

    path = fake_repo / "templates" / "A"
    _write(path / "dsh-adapter.yaml", "\n".join(ADAPTER_TEMPLATE))
    _write(path / "hooks.json", HOOKS_JSON)
    _write(path / "tool-registry.local.yaml", REGISTRY_YAML)
    return path


# --------------------------------------------------------------------------- 成功路径


def test_materialize_replaces_token_and_copies_every_file(
    fake_repo: Path, template: Path
) -> None:
    target = fake_repo / "out" / "A"
    assert _run(template, target, fake_repo) == 0

    rendered = (target / "dsh-adapter.yaml").read_text(encoding="utf-8")
    assert "${" not in rendered
    assert rendered == "\n".join(ADAPTER_TEMPLATE).replace(PLACEHOLDER, fake_repo.as_posix())
    assert (target / "hooks.json").read_bytes() == (template / "hooks.json").read_bytes()
    assert (target / "tool-registry.local.yaml").read_bytes() == (
        template / "tool-registry.local.yaml"
    ).read_bytes()

    payload = _read_payload(target)
    assert payload["schema_version"] == "1.0"
    assert payload["tokens"] == {PLACEHOLDER: 3}
    assert payload["template"]["path"] == "templates/A"
    assert payload["target"]["path"] == "out/A"
    assert payload["template"]["file_count"] == 3
    names = [entry["path"] for entry in payload["files"]]
    assert names == sorted(names)
    assert names == ["dsh-adapter.yaml", "hooks.json", "tool-registry.local.yaml"]
    tokens_by_file = {entry["path"]: entry["tokens_replaced"] for entry in payload["files"]}
    assert tokens_by_file["dsh-adapter.yaml"] == {PLACEHOLDER: 3}
    assert tokens_by_file["hooks.json"] == {PLACEHOLDER: 0}

    # 两条摘要都能独立重算出来；记录自身不在摘要里（否则第二次物化必然不同）。
    assert payload["template"]["combined_digest"] == _digest(template, names)
    assert payload["target"]["combined_digest"] == _digest(target, names)


def test_json_output_is_the_record_bytes(fake_repo: Path, template: Path, capsys) -> None:
    target = fake_repo / "out"
    assert _run(template, target, fake_repo, "--json") == 0
    printed = capsys.readouterr().out
    assert printed.encode("utf-8") == (target / "materialized.json").read_bytes()


# --------------------------------------------------------------------------- 模板非法（退出 1）


def test_unknown_placeholder_is_rejected(
    fake_repo: Path, template: Path, tmp_path: Path, capsys
) -> None:
    _write(template / "dsh-adapter.yaml", "\n".join(ADAPTER_TEMPLATE) + "extra: ${HOME}\n")
    target = tmp_path / "out"
    assert _run(template, target, fake_repo) == 1
    assert "HOME" in capsys.readouterr().err
    assert not target.exists()


def test_residual_token_after_substitution_is_rejected(tmp_path: Path, capsys) -> None:
    # 仓库根自己的路径里带占位符形状：替换之后文本里仍有 ${，那是**模板非法**而不是"替换成功"。
    repo = tmp_path / "${R}" / "repo"
    (repo / ".git").mkdir(parents=True)
    template = repo / "templates" / "A"
    _write(template / "dsh-adapter.yaml", "rules_root: ${REPO_ROOT}\n")
    _write(template / "hooks.json", HOOKS_JSON)
    target = tmp_path / "out"
    assert _run(template, target, repo) == 1
    assert "仍含" in capsys.readouterr().err
    assert not target.exists()


@pytest.mark.parametrize(
    "marker", ["C:/Users/someone/project", "/Users/someone/project", "/home/someone"]
)
def test_absolute_path_in_template_is_rejected(
    fake_repo: Path, template: Path, tmp_path: Path, capsys, marker: str
) -> None:
    _write(template / "dsh-adapter.yaml", "\n".join(ADAPTER_TEMPLATE) + "x: " + marker + "\n")
    target = tmp_path / "out"
    assert _run(template, target, fake_repo) == 1
    assert "绝对路径" in capsys.readouterr().err
    assert not target.exists()


@pytest.mark.parametrize("missing", ["dsh-adapter.yaml", "hooks.json"])
def test_missing_required_file_is_rejected(
    fake_repo: Path, template: Path, tmp_path: Path, capsys, missing: str
) -> None:
    (template / missing).unlink()
    target = tmp_path / "out"
    assert _run(template, target, fake_repo) == 1
    err = capsys.readouterr().err
    assert "缺必需文件" in err
    assert missing in err
    assert not target.exists()


def test_non_utf8_template_file_is_rejected(
    fake_repo: Path, template: Path, tmp_path: Path
) -> None:
    (template / "tool-registry.local.yaml").write_bytes(b"\xff\xfe\x00binary")
    assert _run(template, tmp_path / "out", fake_repo) == 1


# ------------------------------------------------------------------------ 参数 / 前置错（退出 2）


@pytest.mark.parametrize("nested", ["", "out/nested"])
def test_target_inside_or_equal_to_template_is_usage_error(
    fake_repo: Path, template: Path, nested: str
) -> None:
    target = template / nested if nested else template
    assert _run(template, target, fake_repo) == 2


def test_missing_template_directory_is_usage_error(fake_repo: Path, tmp_path: Path) -> None:
    assert _run(tmp_path / "nope", tmp_path / "out", fake_repo) == 2


def test_target_that_is_an_existing_file_is_usage_error(
    fake_repo: Path, template: Path, tmp_path: Path
) -> None:
    target = tmp_path / "out"
    _write(target, "x\n")
    assert _run(template, target, fake_repo) == 2


def test_repo_root_without_git_is_usage_error(template: Path, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert _run(template, tmp_path / "out", plain) == 2


# --------------------------------------------------------------------------- 确定性 / 载荷


def test_two_materializations_are_byte_identical(fake_repo: Path, template: Path) -> None:
    target = fake_repo / "out" / "A"
    assert _run(template, target, fake_repo) == 0
    produced = ARM_FILES[:3] + ("materialized.json",)
    first = {name: (target / name).read_bytes() for name in produced}
    assert _run(template, target, fake_repo) == 0
    second = {name: (target / name).read_bytes() for name in produced}
    for name in produced:
        assert first[name] == second[name]

    # 换一个目标目录：四个副本逐字节相同，只有读数里的 target.path 不同（那是目标的事实）。
    other = fake_repo / "out" / "B"
    assert _run(template, other, fake_repo) == 0
    for name in ARM_FILES[:3]:
        assert (target / name).read_bytes() == (other / name).read_bytes()
    assert _read_payload(other)["target"]["path"] == "out/B"
    assert _read_payload(target)["files"] == _read_payload(other)["files"]


def test_payload_has_no_absolute_paths_outside_workspace(
    fake_repo: Path, template: Path, tmp_path: Path
) -> None:
    target = tmp_path / "outside" / "A"
    assert _run(template, target, fake_repo) == 0
    payload = _read_payload(target)
    assert payload["target"]["path"] == "<outside-workspace>"
    assert payload["template"]["path"] == "templates/A"
    for value in _string_values(payload):
        assert not _looks_absolute(value), value


def test_stale_file_in_target_is_named_but_kept(
    fake_repo: Path, template: Path, capsys
) -> None:
    target = fake_repo / "out"
    _write(target / "approval.json", "{\"records\": []}\n")
    assert _run(template, target, fake_repo) == 0
    assert "approval.json" in capsys.readouterr().err
    assert (target / "approval.json").read_text(encoding="utf-8") == "{\"records\": []}\n"


# --------------------------------------------------------------------------- 受跟踪的模板


def test_tracked_templates_are_complete_and_machine_neutral() -> None:
    for arm in ("A", "B"):
        directory = TEMPLATES / arm
        assert sorted(item.name for item in directory.iterdir()) == sorted(ARM_FILES)
        assert not (directory / "approval.json").exists()
        for name in ARM_FILES:
            data = (directory / name).read_bytes()
            data.decode("utf-8")
            assert b"C:/" not in data
            assert b"/Users/" not in data
            assert b"/home/" not in data
            assert b"\r\n" not in data
            assert data.endswith(b"\n")
        adapter = (directory / "dsh-adapter.yaml").read_text(encoding="utf-8")
        assert adapter.count(PLACEHOLDER) == 3
        assert "${" in adapter


def test_tracked_templates_materialize_to_four_files(tmp_path: Path) -> None:
    for arm, marker in (("A", "configs/before"), ("B", "configs/after")):
        target = tmp_path / arm
        assert _run(TEMPLATES / arm, target, REPO_ROOT) == 0
        assert sorted(item.name for item in target.iterdir()) == sorted(
            list(ARM_FILES) + ["materialized.json"]
        )
        payload = _read_payload(target)
        assert payload["tokens"] == {PLACEHOLDER: 3}
        assert payload["template"]["path"].endswith("arm-configs/" + arm)
        rendered = (target / "dsh-adapter.yaml").read_text(encoding="utf-8")
        assert "${" not in rendered
        assert marker in rendered
        assert REPO_ROOT.as_posix() + "/policies" in rendered
