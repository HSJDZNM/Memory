"""check_repo_consistency.py 的版本比较：PEP 440 口径，不截断、不长度敏感。

对应审查结论 tools/check_repo_consistency.py:66：version_tuple 在第一个非数字段截断
（1.0rc1 → (1, 0)），元组比较又是长度敏感的（(1, 4) >= (1, 4, 0) 为 False）。
两个方向都错：预发布版被当成正式版满足 ==1.0 / >=1.0；而完全合法的 1.4 会被
>=1.4.0 / !=1.4.0 误判成漂移。这是检查器的核心判断，不能"近似"。
"""

from __future__ import annotations

import pytest

import check_repo_consistency as module  # type: ignore[import-not-found]


@pytest.mark.parametrize(
    ("pinned", "specifier", "expected"),
    [
        # 补零对齐：1.4 与 1.4.0 相等（旧实现两个方向都错）
        ("1.4", ">=1.4.0", True),
        ("1.4", "!=1.4.0", False),
        ("1.4", "<=1.4.0", True),
        ("1.4.0", ">=1.4", True),
        # 预发布 < 正式（旧实现把 1.0rc1 截成 (1, 0)）
        ("1.0rc1", "==1.0", False),
        ("1.0rc1", ">=1.0", False),
        ("1.0", ">=1.0rc1", True),
        ("1.0rc1", ">=1.0rc1", True),
        ("1.0a9", "<1.0b1", True),
        ("1.0b1", "<1.0rc1", True),
        ("1.0rc1", "<1.0", True),
        # dev < 预发布 < 正式 < post
        ("1.0.dev1", "<1.0a1", True),
        ("1.0.post1", ">1.0", True),
        ("1.0.post1", "==1.0", False),
        # local 段不参与大小（PEP 440：1.0+local == 1.0）
        ("1.0+local", "==1.0", True),
        # ~= 兼容区间：>=X.Y[.Z] 且把倒数第二段加一
        ("1.5", "~=1.4", True),
        ("2.0", "~=1.4", False),
        ("1.4.9", "~=1.4.5", True),
        ("1.5", "~=1.4.5", False),
        ("1.4", "~=1.4.0", True),
        # 逗号组合
        ("1.5", ">=1.4,<2.0", True),
        ("2.1", ">=1.4,<2.0", False),
    ],
)
def test_version_semantics(pinned, specifier, expected):
    assert module.satisfies(pinned, specifier) is expected


@pytest.mark.parametrize("version", ["1.0beta", "1.0.rc1", "abc", ""])
def test_unknown_version_shapes_are_rejected_not_truncated(version):
    """认不出的形态必须抛 ValueError：截断成"看起来可比"的数字是最坏的一种静默。"""

    with pytest.raises(ValueError):
        module.compare_versions(version, "1.0")


def test_check_lock_reports_uncomparable_versions_instead_of_crashing(monkeypatch):
    """锁文件里出现认不出的版本 → 记成漂移（退出 1），而不是抛异常。"""

    monkeypatch.setattr(module, "read_requirements_in", lambda: {"demo": ">=1.0"})
    monkeypatch.setattr(module, "read_pyproject", lambda: {"demo": ">=1.0"})
    monkeypatch.setattr(module, "read_requirements_lock", lambda: {"demo": "1.0beta"})

    issues = module.check_lock()

    assert any("无法比较" in issue for issue in issues), issues

def test_environment_errors_exit_two_not_one(tmp_path, monkeypatch):
    """读不到配置文件 = 环境错误（退出码 2），不许与"发现漂移"（1）撞码。"""

    monkeypatch.setattr(module, "ROOT", tmp_path)  # 空目录：requirements.in 不存在

    with pytest.raises(module.EnvironmentProblem) as error:
        module.read_requirements_in()

    assert "requirements.in" in str(error.value)


def test_unparsable_requirements_line_is_an_environment_error(tmp_path, monkeypatch):
    """requirements.in 里有解析不了的行：环境错误（旧实现 raise SystemExit 字符串 = 退出码 1）。"""

    (tmp_path / "requirements.in").write_text("这不是依赖声明" + chr(10), encoding="utf-8", newline="")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    with pytest.raises(module.EnvironmentProblem):
        module.read_requirements_in()


def test_main_returns_two_for_environment_problems(monkeypatch, capsys):
    """main 把环境错误翻成退出码 2（旧行为：SystemExit 字符串 = 1）。"""

    def boom():
        raise module.EnvironmentProblem("requirements.in 读不出来")

    monkeypatch.setattr(module, "check_lock", boom)

    assert module.main(["check_repo_consistency.py"]) == 2
    assert "ERROR" in capsys.readouterr().err


def test_main_returns_one_for_drift(monkeypatch):
    """阳性对照：真漂移仍然退 1（两个码不许合并）。"""

    monkeypatch.setattr(module, "check_lock", lambda: ["漂移一条"])
    monkeypatch.setattr(module, "check_docs_and_config", lambda: [])
    monkeypatch.setattr(module, "check_notebook_form", lambda: [])
    monkeypatch.setattr(module, "check_tool_inventory", lambda: [])

    assert module.main(["check_repo_consistency.py"]) == 1
