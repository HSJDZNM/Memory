"""lock_requirements.py 生成的锁文件必须让 pip 真的把 --hash 绑到依赖上。

对应审查结论 tools/lock_requirements.py:35：pin 行没有行尾反斜杠，缩进的 --hash 行被
pip 当成"没有依赖的选项行"丢弃（pip 只给一句 warning）——锁文件看起来带哈希，
`pip install -r` 一个都不校验，`--require-hashes` 直接报 hashes are missing。
"""

from __future__ import annotations

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


def test_a_package_without_hashes_stays_a_single_line():
    entries = lock_requirements.lock_entries(
        {"install": [{"metadata": {"name": "demo", "version": "1.0"}}]}
    )

    assert entries == [("demo", ["demo==1.0"])]


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
