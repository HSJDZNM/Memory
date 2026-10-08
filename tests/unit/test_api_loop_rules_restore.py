"""api_loop 恢复规则目录：目标位置又被建出来时，旧写法会把备份搬进它里面。

审查结论（tools/api_loop.py:560 附近）：finally 里 shutil.move(backup, rules_dir) 在
rules_dir 已存在时会把 backup 整个搬进 rules_dir **里面**（rules_dir/rules-backup），
规则集其实没恢复，而调用方看不出区别——后面的场景静默跑在错的状态上。
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_api_loop():
    spec = importlib.util.spec_from_file_location(
        "api_loop_under_test", REPO_ROOT / "tools" / "api_loop.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["api_loop_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _moved_aside(tmp_root: Path) -> tuple[Path, Path]:
    rules_dir = tmp_root / "workspace" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "coding.yaml").write_text("rule: 1" + chr(10), encoding="utf-8")
    backup = tmp_root / "rules-backup"
    shutil.move(str(rules_dir), str(backup))
    return rules_dir, backup


def test_restore_puts_the_rules_back(tmp_root: Path) -> None:
    module = _load_api_loop()
    rules_dir, backup = _moved_aside(tmp_root)

    module.restore_rules_dir(backup, rules_dir)

    assert (rules_dir / "coding.yaml").read_text(encoding="utf-8") == "rule: 1" + chr(10)
    assert not backup.exists()


def test_restore_wins_over_a_recreated_target(tmp_root: Path) -> None:
    """目标位置又被建出来（readiness / 别的场景 / 外部进程）：必须清掉再搬，不许嵌套。"""

    module = _load_api_loop()
    rules_dir, backup = _moved_aside(tmp_root)
    rules_dir.mkdir(parents=True)
    (rules_dir / "leftover.txt").write_text("stale" + chr(10), encoding="utf-8")

    module.restore_rules_dir(backup, rules_dir)

    assert (rules_dir / "coding.yaml").is_file(), "规则集没有回到原位"
    assert not (rules_dir / "rules-backup").exists(), "旧写法会把备份整个搬进 rules_dir 里面"
    assert not (rules_dir / "leftover.txt").exists()
    assert not backup.exists()
