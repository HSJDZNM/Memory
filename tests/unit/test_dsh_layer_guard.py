"""M1 的加载期检查：分层声明不得把测试文件卷进生产层。

形状来自实测（多规则开发轮 M1）：一份很自然的测试
`tests/test_shipment_controller.py` 因为文件名以 `_controller.py` 结尾，命中了 layers 里
排在 `**/*.py` 前面的 `**/*_controller.py`，于是被当成"入口层"，ARCH-001 把它阻断——
模型为了过规则，把测试从"真实装配对象图"改写成了"手写替身"。

分层是数据（改一行就换结论），但**顺序**能让生产层规则罩住测试文件。因此声明 test_paths
之后，加载期必须能证明"测试路径先命中测试层"；证明不了就拒绝启动，而不是等到运行期
把一条生产层规则套在测试文件上——那时账本上写的是"允许/阻断"，没有人看得出层判错了。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.dsh.adapter import DshEventError, config_from_mapping

PRODUCTION_LAYERS = [
    {"pattern": "**/*_controller.py", "layer": "controller"},
    {"pattern": "**/*_repository.py", "layer": "repository"},
    {"pattern": "**/*.py", "layer": "module"},
]
TEST_LAYER = {"pattern": "tests/**/*.py", "layer": "test"}


def _document(**overrides: object) -> dict:
    document: dict = {
        "project_root": ".",
        "rules": ["policies"],
        "layers": list(PRODUCTION_LAYERS),
        "test_paths": ["tests/**/*.py"],
        "test_layer": "test",
    }
    document.update(overrides)
    return document


def test_the_m1_declaration_is_rejected_at_load_time(tmp_root: Path) -> None:
    """没有测试层规则 = 加载期报错（修复前：一路加载，运行期把测试判成入口层）。"""

    with pytest.raises(DshEventError) as error:
        config_from_mapping(_document(), base_dir=tmp_root)

    message = str(error.value)
    assert "测试路径" in message
    assert "tests/**/*.py" in message
    assert "layer='module'" in message  # 明说它实际被解析成了哪一层
    assert "layers 顶部" in message


def test_one_extra_line_makes_the_same_layers_loadable(tmp_root: Path) -> None:
    """同一批 layers，只在顶部加一行测试层声明：从拒绝变成可用。"""

    config = config_from_mapping(
        _document(layers=[TEST_LAYER, *PRODUCTION_LAYERS]), base_dir=tmp_root
    )

    resolution = config.layer_resolution("tests/test_shipment_controller.py")
    assert resolution.layer == "test"
    assert resolution.matched_pattern == "tests/**/*.py"
    assert resolution.defaulted is False
    # 生产路径的结论一个字没变
    assert config.layer_resolution("src/shop/order_controller.py").layer == "controller"


def test_a_test_rule_placed_too_late_is_still_rejected(tmp_root: Path) -> None:
    """测试层规则存在但排在后面：仍然拒绝——顺序就是策略。"""

    with pytest.raises(DshEventError) as error:
        config_from_mapping(
            _document(
                layers=[PRODUCTION_LAYERS[0], TEST_LAYER, *PRODUCTION_LAYERS[1:]]
            ),
            base_dir=tmp_root,
        )

    assert "test_paths" in str(error.value)


def test_declaring_test_paths_without_a_test_layer_is_rejected(tmp_root: Path) -> None:
    """声明了 test_paths 却不声明 test_layer：证明不了，就拒绝。"""

    with pytest.raises(DshEventError) as error:
        config_from_mapping(_document(test_layer=None), base_dir=tmp_root)

    assert "test_layer" in str(error.value)


def test_an_absolute_or_escaping_test_path_is_rejected(tmp_root: Path) -> None:
    """test_paths 只接受仓库相对 glob：绝对路径与 .. 都不许出现。"""

    for pattern in ("/tests/**/*.py", "../tests/**/*.py"):
        with pytest.raises(DshEventError):
            config_from_mapping(_document(test_paths=[pattern]), base_dir=tmp_root)


def test_without_the_declaration_the_guard_is_inert(tmp_root: Path) -> None:
    """没声明 test_paths 的配置行为不变（向后兼容：缺声明 = 没有这项检查）。"""

    config = config_from_mapping(
        {"project_root": ".", "rules": ["policies"], "layers": list(PRODUCTION_LAYERS)},
        base_dir=tmp_root,
    )

    assert config.test_paths == ()
    assert config.test_layer is None
    assert config.layer_test_conflicts() == ()
    assert config.layer_resolution("tests/test_shipment_controller.py").layer == "controller"


def test_a_missing_default_layer_cannot_be_used_to_pass_the_check(tmp_root: Path) -> None:
    """默认层不是一条分层规则：测试路径落到默认层同样报错（defaulted 必须被看见）。"""

    document = _document(
        layers=[{"pattern": "**/*.md", "layer": "docs"}],
        default_layer="module",
    )
    with pytest.raises(DshEventError) as error:
        config_from_mapping(document, base_dir=tmp_root)

    message = str(error.value)
    assert "defaulted=True" in message
    assert "layer='module'" in message
