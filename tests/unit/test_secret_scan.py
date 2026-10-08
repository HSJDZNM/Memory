"""secret_scan：读不出来的文件不许被当作"干净"（发布门禁里的假阴性）。

为什么需要：`git ls-files` 保证路径存在，所以 OSError 通常意味着扫描器真的没能检查这个文件，
而 UnicodeDecodeError 意味着一个后缀不在 BINARY_SUFFIXES 里的非 UTF-8 / 二进制文件从未被扫过。
旧实现 `except (OSError, UnicodeDecodeError): return []` 让两者都以"没有发现疑似凭据"收场、
退出 0——凭据藏在这种文件里就能过门禁。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import secret_scan


def _relative(target: Path) -> str:
    return target.relative_to(secret_scan.ROOT).as_posix()


def test_undecodable_file_raises_environment_error(tmp_root: Path) -> None:
    """latin-1 正文（后缀不在二进制清单里）：读不出来 ⇒ 环境错误，不是"干净"。"""

    target = tmp_root / "latin1.py"
    target.write_bytes(b"# -*- coding: latin-1 -*-" + bytes([10]) + b"secret = 'caf\xe9'" + bytes([10]))

    with pytest.raises(secret_scan.ScanEnvironmentError) as error:
        secret_scan.scan(_relative(target), secret_scan.secret_patterns())

    assert "读不出来" in str(error.value)
    assert "UnicodeDecodeError" in str(error.value)


def test_main_exits_2_when_a_file_cannot_be_read(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI 层：有文件读不出来 → 退出码 2（不是 0，也不是"发现凭据"的 1）。"""

    monkeypatch.setattr(secret_scan, "tracked_files", lambda include_mirrors: ["demo.py"])

    def boom(path: str, patterns: Any) -> list[str]:
        raise secret_scan.ScanEnvironmentError("%s 读不出来（PermissionError: denied）" % path)

    monkeypatch.setattr(secret_scan, "scan", boom)

    code = secret_scan.main(["secret_scan.py"])

    captured = capsys.readouterr()
    assert code == 2
    assert "读不出来" in captured.err
    assert "不等于干净" in captured.err
    assert "没有发现疑似凭据" not in captured.out


def test_main_reports_git_failure_as_environment_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """git 起不来 / 不在仓库里：同样是环境错误（2），不是"发现凭据"（1）。"""

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(secret_scan.subprocess, "run", boom)

    code = secret_scan.main(["secret_scan.py"])

    captured = capsys.readouterr()
    assert code == 2
    assert "环境不可用" in captured.err

def test_gate_patterns_are_a_superset_of_the_runtime_definition() -> None:
    """条目 [63]：门禁的模式集必须**包含**运行期定义，且多出来的部分确实存在。

    模块 docstring 曾经写成"两者共用同一份定义"——那会让人以为门禁拦下的东西运行期也认，
    而 `EXTRA_PATTERNS`（AKIA/ASIA/JWT）只在门禁这一侧。这里把真实关系（超集）钉住：
    运行期那一条被删掉、或门禁少用一条，用例都会红。
    """

    from enforcement.audit import SECRET_VALUE_PATTERNS

    gate = {pattern.pattern for pattern in secret_scan.secret_patterns()}
    runtime = {pattern.pattern for pattern in SECRET_VALUE_PATTERNS}
    extras = {pattern.pattern for pattern in secret_scan.EXTRA_PATTERNS}

    assert runtime <= gate, "门禁少了运行期定义里的这些模式：" + repr(sorted(runtime - gate))
    assert extras <= gate, "门禁自己的补充模式没生效：" + repr(sorted(extras - gate))
    assert not extras <= runtime, "补充模式若已进运行期定义，docstring 的「超集」说法要一起改"
