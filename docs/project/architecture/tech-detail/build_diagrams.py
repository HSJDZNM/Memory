# -*- coding: utf-8 -*-
"""生成 docs/project/architecture/tech-detail/ 下 10 章的技术关系图与单技术内部流程图。

**一章一个目录**（`00-技术总览/` … `09-能不能成为规则/`）：每章的 `diagram.py` 定义这一章图的规格
（一份 `SPEC`），本脚本收集这 10 份 SPEC，在章节目录里写出同名的两种产物：

- `<章>/<名称>.drawio`：可编辑源（draw.io 桌面版可直接打开继续调整）；
- `<章>/<名称>.png`：渲染图（Pillow 绘制，供快速查看与评审）。

规格的公共词汇（节点 / 连线 / 画布 / 两种写出方式）在 `diagram_lib.py`；**规格是唯一真相源，
产物不手改**。章节目录名与产物名必须逐字相同，不一致就报错退出——那样才谈得上"打开一个目录
看全这一章"。

用法（PNG 需要 Pillow）：

    python docs/project/architecture/tech-detail/build_diagrams.py              # 只写 .drawio
    python docs/project/architecture/tech-detail/build_diagrams.py --png        # 同时渲染 .png
    python docs/project/architecture/tech-detail/build_diagrams.py --only 03 --png

退出码：0 正常（文字适配告警只打印，不当失败）；2 用法或环境错误。
"""
from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
from typing import Sequence

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from diagram_lib import Diagram, render_png, write_drawio  # noqa: E402


def chapter_dirs() -> list[pathlib.Path]:
    """磁盘上真实存在的章节目录：名字形如 `00-技术总览`，且里面有 `diagram.py`。"""

    return sorted(
        path
        for path in HERE.glob("[0-9][0-9]-*")
        if path.is_dir() and (path / "diagram.py").is_file()
    )


def load_spec(number: str) -> tuple[pathlib.Path, Diagram]:
    """按编号加载这一章的规格模块。只加载被选中的那一个，改一半的邻居不会拖累本次生成。"""

    directories = {path.name[:2]: path for path in chapter_dirs()}
    directory = directories.get(number)
    if directory is None:
        raise SystemExit(f"没有编号 {number} 的章节目录（需要 {number}-*/diagram.py）")
    module_name = f"tech_detail_diagram_{number}"
    module_spec = importlib.util.spec_from_file_location(module_name, directory / "diagram.py")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    module_spec.loader.exec_module(module)
    diagram = getattr(module, "SPEC", None)
    if not isinstance(diagram, Diagram):
        raise SystemExit(f"{directory.name}/diagram.py 没有定义 SPEC（Diagram 实例）")
    if diagram.name != directory.name:
        raise SystemExit(
            f"章节目录与产物名必须逐字相同：目录 {directory.name!r}，SPEC.name {diagram.name!r}"
        )
    return directory, diagram


def main(argv: Sequence[str] | None = None) -> int:
    numbers = sorted(path.name[:2] for path in chapter_dirs())
    parser = argparse.ArgumentParser(description="生成 tech-detail 的技术关系图")
    parser.add_argument("--png", action="store_true", help="同时用 Pillow 渲染 PNG")
    parser.add_argument("--only", action="append", default=None, help="只处理指定编号（可重复），如 --only 03")
    args = parser.parse_args(list(argv) if argv is not None else None)

    selected = args.only or numbers
    unknown = [item for item in selected if item not in numbers]
    if unknown:
        print(f"未知编号 {unknown}；可选：{numbers}", file=sys.stderr)
        return 2

    problems: list[str] = []
    for number in selected:
        directory, diagram = load_spec(number)
        drawio = directory / (diagram.name + ".drawio")
        write_drawio(diagram, drawio)
        print("写入 %s（%d 节点 / %d 连线）"
              % (drawio.relative_to(HERE).as_posix(), len(diagram.nodes), len(diagram.edges)))
        if args.png:
            png = directory / (diagram.name + ".png")
            problems.extend("%s：%s" % (diagram.name, item) for item in render_png(diagram, png))
            print("      渲染 %s" % png.relative_to(HERE).as_posix())
    if problems:
        print("文字适配告警：")
        for item in problems:
            print("  - " + item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
