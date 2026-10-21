"""check_config 的用例：退出码 0 / 1、输出形态与只读。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_config import main  # noqa: E402

VALID_TEXT = """\
app_name: demo-shop
retry_policy:
  max_attempts: 3
  backoff_ms: 100
  jitter: true
feature_flags:
  - checkout
"""

V1_TEXT = "app_name: demo-shop\nretry: 3\nfeature_flags: []\n"
UNKNOWN_TEXT = VALID_TEXT + "timeout: 5\n"


def _write(tmp_path: Path, text: str, name: str = "app.yaml") -> Path:
    """把一段 YAML 文本写成临时配置文件（不碰仓库里的 config/app.yaml）。"""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_main_returns_zero_for_valid_config(tmp_path: Path, capsys) -> None:
    """合法配置：返回 0，stdout 恰一行，stderr 为空。"""
    code = main(["--config", str(_write(tmp_path, VALID_TEXT))])
    captured = capsys.readouterr()
    assert code == 0
    assert len(captured.out.strip().splitlines()) == 1
    assert captured.err == ""


def test_main_returns_one_for_v1_config(tmp_path: Path, capsys) -> None:
    """v1 配置：返回 1，stderr 恰一行并含 retry_policy，stdout 为空。"""
    code = main(["--config", str(_write(tmp_path, V1_TEXT, "v1.yaml"))])
    captured = capsys.readouterr()
    assert code == 1
    errors = captured.err.strip().splitlines()
    assert len(errors) == 1
    assert "retry_policy" in errors[0]
    assert captured.out == ""


def test_main_returns_one_for_unknown_key(tmp_path: Path, capsys) -> None:
    """未知键：返回 1，stderr 恰一行。"""
    code = main(["--config", str(_write(tmp_path, UNKNOWN_TEXT, "unknown.yaml"))])
    captured = capsys.readouterr()
    assert code == 1
    assert len(captured.err.strip().splitlines()) == 1
    assert captured.out == ""


def test_main_is_read_only(tmp_path: Path) -> None:
    """运行前后被校验的文件字节不变。"""
    path = _write(tmp_path, VALID_TEXT)
    before = path.read_bytes()
    assert main(["--config", str(path)]) == 0
    assert path.read_bytes() == before
