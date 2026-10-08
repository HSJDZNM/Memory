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
    monkeypatch.setattr(module, "read_requirements_lock", lambda: ({"demo": "1.0beta"}, []))

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

def test_lock_pins_with_extras_and_markers_are_parsed(tmp_path, monkeypatch):
    """`pkg[extra]==1.2` 与 `pkg==1.2 ; python_version >= "3.8"` 都是固定行，不许被丢掉。"""

    lock = tmp_path / "requirements.lock"
    lock.write_text(
        "pkg[extra]==1.2" + chr(10)
        + 'other==2.0 ; python_version >= "3.8"' + chr(10)
        + "third==3.0 \\" + chr(10)
        + "    --hash=sha256:abc" + chr(10),
        encoding="utf-8",
        newline="",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    pins, unparsed = module.read_requirements_lock()

    assert pins == {"pkg": "1.2", "other": "2.0", "third": "3.0"}
    assert unparsed == []


def test_unparsable_lock_lines_are_reported_not_dropped(tmp_path, monkeypatch):
    """解析不了的固定行必须带行号入账（旧实现 `continue` 一句话都不说）。"""

    (tmp_path / "requirements.lock").write_text("这是畸形固定行" + chr(10), encoding="utf-8", newline="")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    pins, unparsed = module.read_requirements_lock()

    assert pins == {}
    assert unparsed and "requirements.lock:1" in unparsed[0]


def test_check_lock_surfaces_unparsable_lines(monkeypatch):
    """锁文件里的畸形行要变成一条漂移，而不是"requirements.lock 没有固定 X"这种错误理由。"""

    monkeypatch.setattr(module, "read_requirements_in", lambda: {})
    monkeypatch.setattr(module, "read_pyproject", lambda: {})
    monkeypatch.setattr(
        module, "read_requirements_lock", lambda: ({}, ["requirements.lock:7: '畸形行'"])
    )

    issues = module.check_lock()

    assert any("无法解析的固定行" in issue for issue in issues), issues

def _lock_of(name: str, version: str):
    return lambda: ({name: version}, [])


def test_specifier_whitespace_is_not_drift(monkeypatch):
    """`>=2.9,<3` 与 `>=2.9, <3` 是同一个区间：空白差异不许判成漂移。"""

    monkeypatch.setattr(module, "read_requirements_in", lambda: {"demo": ">=2.9,<3"})
    monkeypatch.setattr(module, "read_pyproject", lambda: {"demo": ">=2.9, <3"})
    monkeypatch.setattr(module, "read_requirements_lock", _lock_of("demo", "2.9.1"))

    issues = module.check_lock()

    assert not any("版本区间不一致" in issue for issue in issues), issues


def test_different_ranges_are_still_drift(monkeypatch):
    """阳性对照：真的不同区间照旧报（规范化不许把差异也吃掉）。"""

    monkeypatch.setattr(module, "read_requirements_in", lambda: {"demo": ">=2.9,<3"})
    monkeypatch.setattr(module, "read_pyproject", lambda: {"demo": ">=2.9,<4"})
    monkeypatch.setattr(module, "read_requirements_lock", _lock_of("demo", "2.9.1"))

    issues = module.check_lock()

    assert any("版本区间不一致" in issue for issue in issues), issues

def test_readme_test_file_mentions_are_not_treated_as_directories():
    """`tests/test_cli.py` 是文件：不许（像旧实现那样）报成"tests/test_cli 不存在"。"""

    readme = (
        "跑 tests/unit 与 tests/security，另见 tests/test_cli.py、tests/unit/test_x.py 与 tests/fixtures/decisions/block.json"
    )

    assert module.mentioned_test_dirs(readme) == ["fixtures", "security", "unit"]


def test_readme_directory_mentions_are_kept():
    """阳性对照：真目录照旧认出来（这次收口不许把目录也吃掉）。"""

    assert module.mentioned_test_dirs("`tests/contract` 与 `tests/integration`") == [
        "contract",
        "integration",
    ]

def _repo_with(tmp_path, *, requirement: str, project: str, lock: str) -> None:
    (tmp_path / "requirements.in").write_text(requirement + chr(10), encoding="utf-8", newline="")
    (tmp_path / "pyproject.toml").write_text(
        chr(10).join(["[project]", 'name = "demo"', 'dependencies = ["' + project + '"]']) + chr(10),
        encoding="utf-8",
        newline="",
    )
    (tmp_path / "requirements.lock").write_text(lock + chr(10), encoding="utf-8", newline="")


def test_extras_declarations_are_parsed_on_both_sides(tmp_path, monkeypatch):
    """正例：两侧都写 `httpx[http2]>=0.27` 时必须判"一致"，而不是让工具退 2。"""

    _repo_with(
        tmp_path,
        requirement="httpx[http2]>=0.27",
        project="httpx[http2]>=0.27",
        lock="httpx[http2]==0.27.0",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    assert module.read_requirements_in() == {"httpx": ">=0.27"}
    assert module.read_pyproject() == {"httpx": ">=0.27"}
    assert module.check_lock() == [], module.check_lock()


def test_extras_are_stripped_to_the_package_name(tmp_path, monkeypatch):
    """extras 只影响声明形态：包名取第一段（`httpx[cli,http2]>=0.27` → httpx）。"""

    (tmp_path / "requirements.in").write_text(
        "httpx[cli,http2]>=0.27" + chr(10), encoding="utf-8", newline=""
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    assert module.read_requirements_in() == {"httpx": ">=0.27"}


@pytest.mark.parametrize("line", ["[http2]>=0.27", ">=0.27", "httpx[http2"])
def test_genuinely_unparsable_declarations_still_exit_two(tmp_path, monkeypatch, line):
    """负例：放宽 extras 不等于"什么都收"——真解析不了的行照旧退 2。"""

    (tmp_path / "requirements.in").write_text(line + chr(10), encoding="utf-8", newline="")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    with pytest.raises(module.EnvironmentProblem):
        module.read_requirements_in()

def test_trailing_garbage_after_specifier_becomes_drift_not_exit_two(tmp_path, monkeypatch):
    """边界读数：`httpx>=0.27 这不是声明` 会被界定符段收下，随后在锁比对时判成漂移（可见），
    而不是环境错误退 2——这条写下来是为了说明放宽 extras 之后"什么算解析得了"的边界在哪。"""

    _repo_with(
        tmp_path,
        requirement="httpx>=0.27 这不是声明",
        project="httpx>=0.27 这不是声明",
        lock="httpx==0.27.0",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)

    issues = module.check_lock()

    assert any("不满足声明" in issue for issue in issues), issues
