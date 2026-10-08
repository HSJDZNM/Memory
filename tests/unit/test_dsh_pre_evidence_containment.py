"""pre_evidence 的读路径必须与写路径同一口径：目标逃出工作区就连基准内容都不读。"""

from __future__ import annotations

import pytest

from adapters.dsh import pre_evidence as module
from adapters.dsh.pre_evidence import PreEvidenceError


def test_a_target_outside_the_workspace_is_refused_before_reading(tmp_root):
    """越界目标不许被 stat、更不许被读进"改动前的基准内容"再交给验证器。

    写路径（_write_proposal）一直有这个校验，读路径（_read_current 与
    target_existed_before）过去直接 workspace / event.file：绝对路径、../ 或工作区内
    指向外面的符号链接目录都会让平台先读到工作区之外的文本。
    """

    workspace = tmp_root / "workspace"
    workspace.mkdir()
    (tmp_root / "outside.txt").write_text("secret", encoding="utf-8")

    with pytest.raises(PreEvidenceError) as error:
        module._contained(workspace, "../outside.txt")

    assert "逃出工作区" in str(error.value)

    # 反真空：工作区内的目标照常解析（闸门没有把正常路径一起关掉）。
    inside = workspace / "src"
    inside.mkdir()
    (inside / "x.py").write_text("VALUE = 1", encoding="utf-8")

    assert module._contained(workspace, "src/x.py").is_file()
    assert module._read_current(workspace, "src/x.py") == "VALUE = 1"
