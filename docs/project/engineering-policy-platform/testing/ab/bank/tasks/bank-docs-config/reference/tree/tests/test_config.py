"""config.load_config 的用例：v2 合法 / v1 拒绝 / 未知键 / 缺键 / 类型错。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from shop.config import load_config  # noqa: E402

V2_TEXT = """\
app_name: demo-shop
retry_policy:
  max_attempts: 3
  backoff_ms: 100
  jitter: true
feature_flags:
  - checkout
  - search
"""


def _write(tmp_path: Path, text: str, name: str = "app.yaml") -> Path:
    """把一段 YAML 文本写成临时配置文件（不碰仓库里的 config/app.yaml）。"""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_config_reads_v2(tmp_path: Path) -> None:
    """v2 合法配置逐键返回，类型严格。"""
    data = load_config(_write(tmp_path, V2_TEXT))
    assert set(data) == {"app_name", "retry_policy", "feature_flags"}
    assert data["app_name"] == "demo-shop"
    assert data["retry_policy"] == {"max_attempts": 3, "backoff_ms": 100, "jitter": True}
    assert type(data["retry_policy"]["max_attempts"]) is int
    assert type(data["retry_policy"]["jitter"]) is bool
    assert data["feature_flags"] == ["checkout", "search"]


def test_load_config_accepts_boundaries(tmp_path: Path) -> None:
    """边界取值（1 / 0 / false / 空列表）与注释都通过。"""
    text = (
        "# v2 配置\n"
        "app_name: demo-shop\n"
        "retry_policy:\n"
        "  max_attempts: 1\n"
        "  backoff_ms: 0\n"
        "  jitter: false\n"
        "feature_flags: []\n"
    )
    data = load_config(_write(tmp_path, text))
    assert data["retry_policy"]["max_attempts"] == 1
    assert data["retry_policy"]["backoff_ms"] == 0
    assert data["retry_policy"]["jitter"] is False
    assert data["feature_flags"] == []


def test_load_config_rejects_v1_retry(tmp_path: Path) -> None:
    """v1 的 retry 被拒，消息里给出迁移目标名 retry_policy。"""
    text = "app_name: demo-shop\nretry: 3\nfeature_flags: []\n"
    with pytest.raises(ValueError, match="retry_policy"):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_unknown_key(tmp_path: Path) -> None:
    """未知顶层键被拒。"""
    text = V2_TEXT + "timeout: 5\n"
    with pytest.raises(ValueError, match="未知"):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_missing_key(tmp_path: Path) -> None:
    """缺顶层键与缺 retry_policy 子键都被拒。"""
    without_flags = V2_TEXT.replace("feature_flags:\n  - checkout\n  - search\n", "")
    with pytest.raises(ValueError, match="缺"):
        load_config(_write(tmp_path, without_flags, "missing-top.yaml"))
    without_jitter = V2_TEXT.replace("  jitter: true\n", "")
    with pytest.raises(ValueError, match="缺"):
        load_config(_write(tmp_path, without_jitter, "missing-sub.yaml"))


@pytest.mark.parametrize(
    "text",
    [
        "app_name: demo-shop\nretry_policy:\n  max_attempts: true\n"
        "  backoff_ms: 100\n  jitter: true\nfeature_flags: []\n",
        "app_name: demo-shop\nretry_policy:\n  max_attempts: 3\n"
        '  backoff_ms: "100"\n  jitter: true\nfeature_flags: []\n',
        "app_name: demo-shop\nretry_policy:\n  max_attempts: 3\n"
        "  backoff_ms: 100\n  jitter: 1\nfeature_flags: []\n",
        "app_name: 3\nretry_policy:\n  max_attempts: 3\n"
        "  backoff_ms: 100\n  jitter: true\nfeature_flags: []\n",
    ],
)
def test_load_config_rejects_type_errors(tmp_path: Path, text: str) -> None:
    """类型错（含 bool 冒充 int）一律 ValueError。"""
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, text))


def test_load_config_rejects_broken_yaml(tmp_path: Path) -> None:
    """YAML 语法错误也是 ValueError。"""
    with pytest.raises(ValueError):
        load_config(_write(tmp_path, "app_name: [unclosed\n"))


def test_load_config_returns_fresh_dicts(tmp_path: Path) -> None:
    """两次调用互不共享：改返回值不影响下一次读取。"""
    path = _write(tmp_path, V2_TEXT)
    first = load_config(path)
    second = load_config(path)
    assert first == second
    assert first is not second
    first["app_name"] = "mutated"
    assert load_config(path)["app_name"] == "demo-shop"
