# -*- coding: utf-8 -*-
"""检查 docs/project/architecture 的图 / 文 / 口径表是否三处同口径，以及图的包含关系是否成立。

用法：

    python tools/check_arch_canon.py

退出码：0 = 三处同口径且包含关系成立；1 = 有不一致（逐条打印）。
它对应 docs/project/architecture/README.md 的「改图 / 改文 / 改口径必须三处同改」硬规则。
"""
from __future__ import annotations

import html
import pathlib
import re
import urllib.parse
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCH = ROOT / "docs/project/architecture"

CANON_LAYERS = [
    ("① 消费方", "消费方"),
    ("② 接入与协议转换", "接入与协议转换"),
    ("③ 判定核心", "判定核心"),
    ("④ 能力层", "能力层"),
    ("⑤ 数据与契约", "数据与契约"),
    ("⑥ 证据与门禁", "证据与门禁"),
]
STEPS = ["台阶 1", "台阶 2", "台阶 3", "台阶 4", "台阶 5", "台阶 6", "台阶 7"]
NUMBERS = ["44", "535", "1109", "1111"]   # 1110 是历史值（曾临时多一个测试），不能留
FORBIDDEN = ["五个 *_loop", "五个 *_loop.py", "c3_3", "c4_3"]


def clean(value: str) -> str:
    value = urllib.parse.unquote(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&#xa;", " ").replace("&nbsp;", " ")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def read_pages(path: pathlib.Path):
    text = path.read_text(encoding="utf-8")
    for page in re.finditer(r'<diagram[^>]*name="([^"]*)"[^>]*>(.*?)</diagram>', text, re.S):
        payload = page.group(2)
        cells, kids = {}, defaultdict(list)
        for m in re.finditer(r"<mxCell\s([^>]*?)(?:/>|>)", payload):
            attrs = m.group(1)

            def get(key: str):
                hit = re.search(key + r'="([^"]*)"', attrs)
                return hit.group(1) if hit else None

            cid = get("id")
            if not cid:
                continue
            style = urllib.parse.unquote(get("style") or "")
            cells[cid] = {
                "parent": get("parent"),
                "label": clean(get("value")),
                "edge": get("edge") == "1",
                "container": "container=1" in style,
            }
            kids[get("parent") or ""].append(cid)
        yield page.group(1), cells, kids


def depth_of(cells, cid) -> int:
    depth, cursor, guard = 0, cid, 0
    while guard < 20:
        guard += 1
        parent = cells.get(cursor, {}).get("parent")
        if not parent or parent in ("0", "1"):
            return depth
        depth += 1
        cursor = parent
    return depth


def main() -> int:
    problems: list[str] = []
    print("=" * 20, "图侧：包含关系与文案")
    all_labels: list[str] = []
    for name in ("技术架构.drawio", "技术流程.drawio"):
        for page_name, cells, kids in read_pages(ARCH / name):
            visible = {cid: c for cid, c in cells.items() if not c["edge"] and c["label"]}
            all_labels.extend(c["label"] for c in visible.values())
            flat = [cid for cid in visible if depth_of(cells, cid) == 0 and not visible[cid]["container"]]
            containers = [cid for cid, c in visible.items() if c["container"]]
            nested = [cid for cid in visible if depth_of(cells, cid) > 0]
            print("-- %s / %s：可见节点 %d，容器 %d，有归属 %d，仍平铺 %d"
                  % (name, page_name, len(visible), len(containers), len(nested), len(flat)))
            for cid in flat:
                label = visible[cid]["label"][:60]
                if len(visible) > 12 and not re.match(r"^(Memory|规则是数据|颜色|Legend|依赖边界|Raw Reference|三层规范模型|判定侧)", label):
                    problems.append("图 %s/%s：节点未归属容器 → %s" % (name, page_name, label))
    blob = "\n".join(all_labels)
    for bad in FORBIDDEN:
        if bad in blob:
            problems.append("图文案仍含过期/坏标识：%r" % bad)

    print("=" * 20, "文侧与口径表")
    docs = {}
    for path in sorted(ARCH.glob("*.md")):
        docs[path.name] = path.read_text(encoding="utf-8")
    joined = "\n".join(docs.values())
    missing = [key for key, _ in CANON_LAYERS if key not in joined and key.split(" ")[1] not in joined]
    for key in missing:
        problems.append("文侧缺少层名或写法不一致：%s" % key)
    for step in STEPS:
        if step not in joined:
            problems.append("文侧缺少编号口径：%s" % step)
    for number in NUMBERS:
        if number not in joined and number not in blob:
            problems.append("图/文都未出现实测数字：%s" % number)
    canon_file = ARCH / "术语与口径.md"
    if not canon_file.is_file():
        problems.append("缺少口径表：docs/project/architecture/术语与口径.md")
    else:
        canon_text = canon_file.read_text(encoding="utf-8")
        for section in ("分层", "编号", "数字", "核对"):
            if section not in canon_text:
                problems.append("口径表缺少小节：%s" % section)
        for label in ("台阶 1", "台阶 7", "Phase 8", "allow_with_warnings"):
            if label not in canon_text:
                problems.append("口径表缺少关键口径：%s" % label)

    print("=" * 20, "结论")
    if problems:
        for item in problems:
            print("  ✗ " + item)
        print("共 %d 处不一致" % len(problems))
        return 1
    print("  图 / 文 / 口径表 三处同口径，包含关系成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
