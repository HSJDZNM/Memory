"""M1 的契约面：仓库自己发出去的示例配置必须让测试路径落在测试层。

示例配置（`examples/dsh/dsh-adapter.yaml`）是受治理项目 `.policy/dsh-adapter.yaml` 的模板：
它的分层声明会**原样**变成别人的运行期声明。因此这里对真数据做两条断言：

1. 每条测试路径都解析到声明的测试层（且不是兜底来的）；
2. 把那一行测试层声明删掉，同一份配置在加载期就红——证明检查对着真数据是活的，
   而不是只在合成的单元测试里成立。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from adapters.dsh.adapter import DshEventError, config_from_mapping, load_config
from validators.globs import glob_match
# 别名导入：模块里名为 TestLayout 的类会被 pytest 当成测试类收集（PytestCollectionWarning）。
from validators.models import TestLayout as PlatformTestLayout
from validators.registry import load_test_layout

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "dsh" / "dsh-adapter.yaml"
# 平台级"哪些路径算测试"的那份声明所在的仓库根：P4 起 policy.check 缺 --layer 时也读它。
REPO_ROOT = EXAMPLE.parents[2]


def _test_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix() for path in (root / "tests").rglob("*.py")
    )


def test_the_shipped_example_declares_the_test_layer_first() -> None:
    config = load_config(EXAMPLE)

    # 第一行仍是"整棵 tests/ 树"；第二行是 B2 新加的**测试支撑**声明：项目根的 conftest.py
    # 不在 tests/** 之下，只声明第一行会让它在两条路径上拿到两个层（见下面那条用例）。
    assert config.test_paths == ("tests/**/*.py", "**/conftest.py")
    assert config.test_layer == "test"
    assert config.layers[0] == type(config.layers[0])(pattern="tests/**/*.py", layer="test")
    assert config.layers[1] == type(config.layers[1])(pattern="**/conftest.py", layer="test")


def test_the_shipped_example_declares_the_same_agent_version_as_the_manifest() -> None:
    """示例配置是发给别人的模板：它的 agent_version 必须与适配器声明的实测版本一致。

    修复轮 14 的背景：示例与 manifest 各自写着版本号，谁也没比对过（缺陷 2 的同族问题）。
    这条检查不做版本语义判断，只要求这两处**同一口径**；真正的「声明 vs 宿主」比对在
    python -m adapters.cli host-version --check 里。
    """

    manifest = yaml.safe_load(
        (REPO_ROOT / "adapters" / "dsh" / "manifest.yaml").read_text(encoding="utf-8")
    )
    example = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))

    assert example["agent_version"] == manifest["agent_version"]

def test_every_test_file_in_this_repository_resolves_to_the_test_layer() -> None:
    config = load_config(EXAMPLE)
    assert config.test_layer is not None
    files = _test_files(config.project_root)
    assert len(files) > 50, "没扫到测试文件：这条检查会变成空转"

    wrong = {
        name: config.layer_resolution(name)
        for name in files
        if config.layer_resolution(name).layer != config.test_layer
    }
    assert wrong == {}, f"这些测试文件没有落在测试层：{sorted(wrong)}"


def test_a_test_file_named_like_a_production_file_is_no_longer_captured() -> None:
    """M1 的原形：测试文件名以 _controller.py 结尾时，不许再被判成入口层。"""

    config = load_config(EXAMPLE)
    resolution = config.layer_resolution("tests/test_shipment_controller.py")

    assert resolution.layer == "test"
    assert resolution.matched_pattern == "tests/**/*.py"
    assert resolution.defaulted is False


def test_removing_the_test_layer_declaration_from_the_shipped_example_is_rejected() -> None:
    document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    document["layers"] = [row for row in document["layers"] if row["layer"] != "test"]

    with pytest.raises(DshEventError) as error:
        config_from_mapping(document, base_dir=EXAMPLE.parent)

    assert "测试路径" in str(error.value)

# ----------------------------------------------------------------- P4：两条路径共用一份测试路径声明


def _witness_segments(pattern: str) -> str:
    """把一条 glob 的每一段实例化成一个确定的见证路径。"""

    segments: list[str] = []
    for segment in pattern.split("/"):
        if segment == "**":
            segments.append("witness")
            continue
        segments.append(
            segment.replace("**", "witness").replace("*", "witness").replace("?", "x")
        )
    return "/".join(segments)


def _witnesses(pattern: str) -> tuple[str, ...]:
    """把一条 glob 变成确定的见证路径（只处理目录段与段内通配）。

    见证路径必须**自证**：调用方随后会用 glob_match(pattern, path) 复查，
    生成错了就当场红，而不是悄悄拿一条不匹配的路径去测别的规则。

    开头是 "**/" 的模式多给一条"零个目录"的见证："**/" 的语义是零个或多个目录，
    项目根的 conftest.py 命中的就是零目录那一种形态。少了它，这类真实路径永远进不了
    检查——见证路径法**可能漏**，这里把已知会漏的那一形态补上（它不是特例，是语义之一）。
    """

    candidates = [_witness_segments(pattern)]
    if pattern.startswith("**/"):
        candidates.append(_witness_segments(pattern[3:]))
    return tuple(candidates)


def _uncovered_patterns(patterns: tuple[str, ...], config: object) -> dict[str, str]:
    """平台声明里没能落到示例配置 test_layer 的那些 pattern（test 与 support 共用一份判据）。

    返回 {pattern: 原因}；空字典表示"两份声明解得通"。两个失败方向都要查：

    1. 见证路径不在示例配置 `test_paths` 的覆盖范围内（声明漂移，例如平台把测试路径
       扩到 `spec/**` 而 Adapter 还只认 `tests/**`）；
    2. 它落在层次表里被解析成别的层（通配顺序把测试路径罩住了——M1 的原形，只是换了个方向）。
    """

    assert config.test_layer is not None
    uncovered: dict[str, str] = {}
    for pattern in patterns:
        problems: list[str] = []
        for path in _witnesses(pattern):
            assert glob_match(pattern, path), f"见证路径 {path!r} 不匹配平台 pattern {pattern!r}"
            if not any(glob_match(item, path) for item in config.test_paths):
                problems.append(f"{path}: 不在示例配置的 test_paths 覆盖范围内")
                continue
            resolution = config.layer_resolution(path)
            if resolution.layer != config.test_layer or resolution.defaulted:
                problems.append(f"{path}: 解析成 {resolution.layer}（应为 {config.test_layer}）")
        if problems:
            uncovered[pattern] = "；".join(problems)
    return uncovered


def _uncovered_test_patterns(layout: PlatformTestLayout, config: object) -> dict[str, str]:
    return _uncovered_patterns(layout.test_patterns, config)


def test_every_platform_test_pattern_lands_on_the_declared_test_layer() -> None:
    """平台声明的每条测试 pattern，在示例 Adapter 配置下都必须落到声明的测试层。

    "哪些路径算测试"只能有**一份平台级声明**（validation/test-layout.yaml 的 test_patterns）：
    验证器路径用它做测试选择，policy.check 缺 --layer 时用它定 layer（P4），
    示例 Adapter 配置用它自证 test_layer。两边各写一份必然漂移——
    这条检查让漂移变红，而不是等某个测试文件在两条路径上拿到相反结论。
    """

    layout = load_test_layout(root=REPO_ROOT)
    config = load_config(EXAMPLE)

    assert _uncovered_test_patterns(layout, config) == {}


def test_a_platform_test_pattern_the_example_does_not_cover_is_reported() -> None:
    """变异：给平台数据加一条示例配置覆盖不到的测试 pattern -> 检查必须报出来。"""

    layout = load_test_layout(root=REPO_ROOT)
    mutated = layout.model_copy(
        update={"test_patterns": (*layout.test_patterns, "spec/**/test_*.py")}
    )

    uncovered = _uncovered_test_patterns(mutated, load_config(EXAMPLE))

    assert "spec/**/test_*.py" in uncovered
    assert "不在示例配置的 test_paths 覆盖范围内" in uncovered["spec/**/test_*.py"]


def test_dropping_the_example_test_layer_row_is_reported() -> None:
    """变异：把示例配置里的测试层那一行拿掉 -> 同一批平台 pattern 立刻变红。

    为什么不用一份删掉 test 层行的 YAML 直接加载：那样的配置在**加载期**就被
    `layer_test_conflicts` 拒绝了（那正是 M1 的修复）。这里要单独验证"这条新检查
    自己会不会红"，所以只变异已加载配置的层次表。
    """

    layout = load_test_layout(root=REPO_ROOT)
    config = load_config(EXAMPLE)
    # AdapterConfig 是 frozen dataclass（不是 pydantic 模型）：变异用 dataclasses.replace。
    production_only = replace(
        config,
        layers=tuple(row for row in config.layers if row.layer != config.test_layer),
    )

    uncovered = _uncovered_test_patterns(layout, production_only)

    assert set(uncovered) == set(layout.test_patterns)
    assert all("解析成" in reason for reason in uncovered.values())


# ---------------------------------------------------- B2：测试支撑路径也共用同一份声明


def test_every_platform_test_support_pattern_lands_on_the_declared_test_layer() -> None:
    """B2 / 5.66：平台声明的**测试支撑**路径也必须落在示例配置的 test_layer。

    同一份声明要同时服务两条路径：验证器层按 test_support_patterns 做 support 选择，
    policy.check 缺 --layer 时按它定 test 层。示例 Adapter 配置是发给别人的模板——
    它漏掉一条支撑声明，那个文件就会在 Hook 路径上是生产层、在验证器路径上是 test
    （AGENTS 第 49 条禁止的"同一个文件两个层"）。
    """

    layout = load_test_layout(root=REPO_ROOT)
    config = load_config(EXAMPLE)

    assert layout.test_support_patterns, "v2 必须声明测试支撑路径，否则这条检查空转"
    assert _uncovered_patterns(layout.test_support_patterns, config) == {}


def test_a_root_conftest_is_the_test_layer_in_the_shipped_example() -> None:
    """具体的那个文件：项目根 conftest.py 必须解析到 test_layer，且不是默认层兜底。

    上一条通用检查按见证路径跑，而 `**/` 的零目录形态（就是项目根的 conftest.py）
    另有专门的见证（见 `_witnesses`）；这一条把"真文件、真声明"的读数也钉住。
    """

    config = load_config(EXAMPLE)
    resolution = config.layer_resolution("conftest.py")

    assert resolution.layer == "test"
    assert resolution.matched_pattern == "**/conftest.py"
    assert resolution.defaulted is False


def test_a_platform_test_support_pattern_the_example_does_not_cover_is_reported() -> None:
    """变异：平台数据加一条示例配置覆盖不到的支撑 pattern -> 检查必须报出来。"""

    uncovered = _uncovered_patterns(("spec/**/support_*.py",), load_config(EXAMPLE))

    assert "spec/**/support_*.py" in uncovered
    assert "不在示例配置的 test_paths 覆盖范围内" in uncovered["spec/**/support_*.py"]
