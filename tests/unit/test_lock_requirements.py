"""lock_requirements.py 生成的锁文件必须让 pip 真的把 --hash 绑到依赖上。

对应审查结论 tools/lock_requirements.py:35：pin 行没有行尾反斜杠，缩进的 --hash 行被
pip 当成"没有依赖的选项行"丢弃（pip 只给一句 warning）——锁文件看起来带哈希，
`pip install -r` 一个都不校验，`--require-hashes` 直接报 hashes are missing。
"""

from __future__ import annotations

import hashlib
import json

import check_repo_consistency
import lock_requirements

REPORT = {
    "install": [
        {
            "metadata": {"name": "PyYAML", "version": "6.0.3"},
            "download_info": {"archive_info": {"hashes": {"sha256": "aa" * 32}}},
        },
        {
            "metadata": {"name": "pydantic", "version": "2.13.5"},
            "download_info": {
                "archive_info": {"hashes": {"sha256": "bb" * 32, "md5": "cc" * 16}}
            },
        },
    ]
}


def test_hash_lines_are_continuations_of_their_pin():
    entries = lock_requirements.lock_entries(REPORT)

    assert [name for name, _lines in entries] == ["pydantic", "pyyaml"], "按包名排序"
    for name, lines in entries:
        assert lines[0].lower().startswith(name + "=="), "排序键是小写，行内保留原大小写"
        assert len(lines) >= 2
        for line in lines[:-1]:
            assert line.endswith(" \\"), line
        assert not lines[-1].endswith("\\"), "最后一行不再续行"
        assert all(line.lstrip().startswith("--hash=") for line in lines[1:])


def test_a_package_without_hashes_is_refused_not_written_as_a_bare_pin():
    """没有哈希的条目**拒绝出锁**（2026-10-08 口径推翻，带证据）。

    旧用例断言"没有哈希就写成一条单行 pin"。但本文件产出的锁是给 `pip install --require-hashes`
    用的（头部就写着这条用法）：混进一条没有哈希的 pin，pip 会**整份拒绝**，而读文件的人看不出
    哪一条没被校验——"看起来带了哈希的锁"比没有锁更糟。因此该行为判为缺陷，改成显式报错。
    旧行为来自可编辑 / VCS / 本地安装在 pip 报告里带 `dir_info` / `vcs_info` 而不是
    `archive_info.hashes` 的真实形态，不是假设。
    """

    import pytest

    with pytest.raises(lock_requirements.LockError) as error:
        lock_requirements.lock_entries(
            {"install": [{"metadata": {"name": "demo", "version": "1.0"}}]}
        )

    assert "demo" in str(error.value)
    assert "没有哈希" in str(error.value)


def test_generated_lock_is_readable_by_the_repo_parser(tmp_root, monkeypatch):
    """跨文件契约：生成的锁文件必须能被 check_repo_consistency 读回同样的版本。"""

    output = tmp_root / "requirements.lock"
    report_path = tmp_root / "report.json"
    report_path.write_text(json.dumps(REPORT), encoding="utf-8", newline="\n")

    assert lock_requirements.main(["lock_requirements.py", str(report_path), str(output)]) == 0
    text = output.read_text(encoding="utf-8")
    assert "pydantic==2.13.5 \\" in text

    monkeypatch.setattr(check_repo_consistency, "ROOT", tmp_root)
    # 解析器的口径在 97f741b 之后是 (已锁定, 解析不了的行)：跨文件契约因此要同时钉两件事——
    # 版本逐项读回**并且**没有一行读不懂（后者正是那次修复引入的：不能静默丢掉再报"没有固定 X"）。
    locked, unparsed = check_repo_consistency.read_requirements_lock()

    assert locked == {"pyyaml": "6.0.3", "pydantic": "2.13.5"}
    assert unparsed == []


def test_requirements_in_is_anchored_to_the_repo(monkeypatch, tmp_root):
    """`requirements.in` 锚在仓库根：换 cwd 不能读不到、更不能读到别处的同名文件。

    旧写法是 `Path("requirements.in")`（相对 cwd）：从 tools/ 等目录跑会 FileNotFoundError，
    而 cwd 里恰好有另一份 requirements.in 时，锁文件头部记的摘要描述的是**错的那一份**。
    """

    monkeypatch.chdir(tmp_root)

    assert lock_requirements.REQUIREMENTS_IN.is_absolute()
    assert lock_requirements.REQUIREMENTS_IN.is_file()
    assert lock_requirements.requirements_digest() == hashlib.sha256(
        lock_requirements.REQUIREMENTS_IN.read_bytes()
    ).hexdigest()


def test_the_singular_archive_info_hash_is_understood():
    """老版本 pip 只给单数 `archive_info.hash`：认它，别当成「没有哈希」。"""

    report = {
        "install": [
            {
                "metadata": {"name": "PyYAML", "version": "6.0.3"},
                "download_info": {"archive_info": {"hash": "sha256=" + "aa" * 32}},
            }
        ]
    }

    entries = lock_requirements.lock_entries(report)

    assert [name for name, _lines in entries] == ["pyyaml"]
    assert any("--hash=sha256:" + "aa" * 32 in line for line in entries[0][1])
