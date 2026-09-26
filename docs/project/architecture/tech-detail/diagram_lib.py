# -*- coding: utf-8 -*-
"""图规格的公共词汇：节点 / 连线 / 画布，以及 .drawio 与 .png 两种写出方式。

**一章一个目录**（`00-技术总览/` … `09-能不能成为规则/`）：每章的 `diagram.py` 定义一份 `SPEC`，
`build_diagrams.py` 收集这些 SPEC，在同目录写出同名的 `.drawio`（可编辑源）与 `.png`（渲染图）；
规格是唯一真相源，产物不手改——手改必然让两者脱钩。

为什么 PNG 不由 draw.io CLI 导出：本机沙箱下 draw.io 的 Electron 进程起不来
（mojo platform_channel 访问被拒），因此渲染走 Pillow，同一份规格算出同样的坐标。
"""
from __future__ import annotations

import xml.sax.saxutils as sax


FONT_REG = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"

# 颜色：白底 + 灰框是常态；黄 = 核心 / 门禁；红 = 失败关闭；蓝灰 = 外部进程
PALETTE = {
    "step": ("#FFFFFF", "#9AA0A6", "#1F2328"),
    "ext": ("#EEF2F7", "#9AA0A6", "#1F2328"),
    "data": ("#F3F6FB", "#9AA0A6", "#1F2328"),
    "gate": ("#FFF7DA", "#E0B400", "#1F2328"),
    "core": ("#FFE9A8", "#E0B400", "#1F2328"),
    "fail": ("#FDE7E7", "#D9534F", "#1F2328"),
    "human": ("#F3E8FD", "#A142F4", "#1F2328"),
    "note": ("#F8F9FA", "#DADCE0", "#3C4043"),
}
EDGE_COLOR = "#5F6368"
EDGE_MUTED = "#8AB4F8"


class Node:
    def __init__(self, nid, text, sub="", x=0, y=0, w=280, h=66, kind="step"):
        self.id, self.text, self.sub = nid, text, sub
        self.x, self.y, self.w, self.h, self.kind = x, y, w, h, kind

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def y2(self):
        return self.y + self.h

    @property
    def x2(self):
        return self.x + self.w


class Edge:
    def __init__(self, src, dst, label="", style="solid", points=None, mid_y=None,
                 from_anchor="bottom", to_anchor="top", from_dx=0, to_dx=0):
        self.src, self.dst, self.label, self.style = src, dst, label, style
        self.points, self.mid_y = points or [], mid_y
        self.from_anchor, self.to_anchor = from_anchor, to_anchor
        self.from_dx, self.to_dx = from_dx, to_dx


class Diagram:
    def __init__(self, name, title, subtitle, nodes, edges, width, height, footer="", legend=()):
        self.name, self.title, self.subtitle = name, title, subtitle
        self.nodes, self.edges = nodes, edges
        self.width, self.height = width, height
        self.footer, self.legend = footer, legend
        self.by_id = {n.id: n for n in nodes}


def anchor_point(node, side, dx=0):
    return {
        "bottom": (node.cx + dx, node.y2),
        "top": (node.cx + dx, node.y),
        "left": (node.x, node.y + node.h / 2),
        "right": (node.x2, node.y + node.h / 2),
    }[side]


def path_of(edge, diagram):
    s, d = diagram.by_id[edge.src], diagram.by_id[edge.dst]
    start = anchor_point(s, edge.from_anchor, edge.from_dx)
    end = anchor_point(d, edge.to_anchor, edge.to_dx)
    pts = [start]
    if edge.points:
        pts.extend(edge.points)
    elif abs(start[0] - end[0]) > 3:
        mid_y = edge.mid_y if edge.mid_y is not None else (start[1] + end[1]) / 2
        if edge.from_anchor in ("left", "right") or edge.to_anchor in ("left", "right"):
            mid_x = (start[0] + end[0]) / 2
            pts.extend([(mid_x, start[1]), (mid_x, end[1])])
        else:
            pts.extend([(start[0], mid_y), (end[0], mid_y)])
    pts.append(end)
    return pts


# ---------------------------------------------------------------- drawio 输出

def esc(text):
    return sax.escape(text, {'"': "&quot;"})


def html_label(node):
    # 返回**未转义**的 HTML：调用方再整串做一次 XML 转义。
    # 内层属性用单引号，整串转义后标签以 &lt;b&gt; 形式落在属性值里，draw.io 解回 HTML。
    label = "<b>%s</b>" % node.text
    if node.sub:
        label += "<br><font style='font-size:11px' color='#5F6368'>%s</font>" % node.sub
    return label


def drawio_style(node):
    fill, stroke, font = PALETTE[node.kind]
    return ("rounded=1;whiteSpace=wrap;html=1;fillColor=%s;strokeColor=%s;strokeWidth=2;"
            "fontSize=16;fontColor=%s;arcSize=14;" % (fill, stroke, font))


def write_drawio(diagram, path):
    out = ['<mxfile host="Electron" agent="dsh">',
           '  <diagram id="%s" name="%s">' % (diagram.name, esc(diagram.title)),
           '    <mxGraphModel dx="1200" dy="800" grid="0" gridSize="10" guides="1" tooltips="1"'
           ' connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="%d" pageHeight="%d"'
           ' math="0" shadow="0">' % (diagram.width, diagram.height),
           '      <root>',
           '        <mxCell id="0" />',
           '        <mxCell id="1" parent="0" />',
           '        <mxCell id="title" parent="1" style="text;html=1;align=left;verticalAlign=middle;'
           'fontSize=22;fontStyle=1" value="%s" vertex="1">' % esc(diagram.title),
           '          <mxGeometry height="30" width="%d" x="40" y="18" as="geometry" />'
           % (diagram.width - 80),
           '        </mxCell>',
           '        <mxCell id="subtitle" parent="1" style="text;html=1;align=left;verticalAlign=middle;'
           'fontSize=12;fontColor=#5F6368" value="%s" vertex="1">' % esc(diagram.subtitle),
           '          <mxGeometry height="24" width="%d" x="40" y="50" as="geometry" />'
           % (diagram.width - 80),
           '        </mxCell>']
    for node in diagram.nodes:
        out.append('        <mxCell id="%s" parent="1" style="%s" value="%s" vertex="1">'
                   % (node.id, drawio_style(node), esc(html_label(node))))
        out.append('          <mxGeometry height="%s" width="%s" x="%s" y="%s" as="geometry" />'
                   % (node.h, node.w, node.x, node.y))
        out.append('        </mxCell>')
    for i, edge in enumerate(diagram.edges):
        pts = path_of(edge, diagram)
        style = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=%s;strokeWidth=1.5;"
                 "endArrow=blockThin;endFill=1;labelBackgroundColor=#ffffff;fontSize=11;"
                 % (EDGE_MUTED if edge.style == "muted" else EDGE_COLOR))
        if edge.style == "dashed":
            style += "dashed=1;"
        out.append('        <mxCell id="edge%d" edge="1" parent="1" source="%s" target="%s" style="%s"'
                   ' value="%s">' % (i, edge.src, edge.dst, style, esc(edge.label)))
        out.append('          <mxGeometry relative="1" as="geometry">')
        out.append('            <Array as="points">')
        for px, py in pts[1:-1]:
            out.append('              <mxPoint x="%s" y="%s" />' % (round(px, 1), round(py, 1)))
        out.append('            </Array>')
        out.append('          </mxGeometry>')
        out.append('        </mxCell>')
    if diagram.legend:
        out.append('        <mxCell id="legend" parent="1" style="text;html=1;align=left;'
                   'verticalAlign=middle;fontSize=11;fontColor=#5F6368" value="%s" vertex="1">'
                   % esc(" ｜ ".join(diagram.legend)))
        out.append('          <mxGeometry height="20" width="%d" x="40" y="%d" as="geometry" />'
                   % (diagram.width - 80, diagram.height - 34))
        out.append('        </mxCell>')
    if diagram.footer:
        out.append('        <mxCell id="footer" parent="1" style="text;html=1;align=left;'
                   'verticalAlign=middle;fontSize=11;fontColor=#5F6368" value="%s" vertex="1">'
                   % esc(diagram.footer))
        out.append('          <mxGeometry height="20" width="%d" x="40" y="%d" as="geometry" />'
                   % (diagram.width - 80, diagram.height - 58))
        out.append('        </mxCell>')
    out.extend(['      </root>', '    </mxGraphModel>', '  </diagram>', '</mxfile>'])
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- PNG 渲染

SS = 2  # 超采样倍数：先按 2 倍画，再缩回，边缘更干净


def render_png(diagram, path):
    from PIL import Image, ImageDraw, ImageFont

    def font(bold, size):
        return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size * SS)

    w, h = diagram.width * SS, diagram.height * SS
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    f_title, f_sub = font(True, 22), font(False, 12)
    f_main, f_node_sub = font(True, 16), font(False, 11)
    f_edge, f_legend = font(False, 11), font(False, 11)

    d.text((40 * SS, 26 * SS), diagram.title, font=f_title, fill="#1F2328", anchor="lm")
    d.text((40 * SS, 54 * SS), diagram.subtitle, font=f_sub, fill="#5F6368", anchor="lm")

    def draw_arrow(pts, dashed, muted):
        color = EDGE_MUTED if muted else EDGE_COLOR
        width = 1.5 * SS
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if dashed:
                seg = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
                step, pos = 9 * SS, 0.0
                while pos < seg:
                    end = min(pos + step * 0.6, seg)
                    d.line([x0 + (x1 - x0) * pos / seg, y0 + (y1 - y0) * pos / seg,
                            x0 + (x1 - x0) * end / seg, y0 + (y1 - y0) * end / seg],
                           fill=color, width=int(width))
                    pos += step
            else:
                d.line([x0, y0, x1, y1], fill=color, width=int(width))
        (px, py), (qx, qy) = pts[-2], pts[-1]
        dx, dy = qx - px, qy - py
        norm = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        ux, uy = dx / norm, dy / norm
        size, half = 9 * SS, 4.2 * SS
        tip = (qx, qy)
        left = (qx - ux * size - uy * half, qy - uy * size + ux * half)
        right = (qx - ux * size + uy * half, qy - uy * size - ux * half)
        d.polygon([tip, left, right], fill=color)

    for edge in diagram.edges:
        pts = [(x * SS, y * SS) for x, y in path_of(edge, diagram)]
        draw_arrow(pts, edge.style == "dashed", edge.style == "muted")
        if edge.label:
            best, best_len = None, -1
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                seg = abs(x1 - x0) + abs(y1 - y0)
                if seg > best_len:
                    best, best_len = ((x0 + x1) / 2, (y0 + y1) / 2), seg
            box = d.textbbox((0, 0), edge.label, font=f_edge)
            bw, bh = box[2] - box[0] + 6 * SS, box[3] - box[1] + 4 * SS
            d.rectangle([best[0] - bw / 2, best[1] - bh / 2, best[0] + bw / 2, best[1] + bh / 2],
                        fill="white")
            d.text(best, edge.label, font=f_edge, fill="#3C4043", anchor="mm")

    warnings = []
    for node in diagram.nodes:
        fill, stroke, font_color = PALETTE[node.kind]
        d.rounded_rectangle([node.x * SS, node.y * SS, node.x2 * SS, node.y2 * SS],
                            radius=14 * SS, fill=fill, outline=stroke, width=int(2 * SS))
        cx = node.cx * SS
        if node.sub:
            d.text((cx, (node.y + node.h * 0.36) * SS), node.text, font=f_main,
                   fill=font_color, anchor="mm")
            d.text((cx, (node.y + node.h * 0.70) * SS), node.sub, font=f_node_sub,
                   fill="#5F6368", anchor="mm")
        else:
            d.text((cx, (node.y + node.h / 2) * SS), node.text, font=f_main,
                   fill=font_color, anchor="mm")
        for text, fnt in ((node.text, f_main), (node.sub, f_node_sub)):
            if text and d.textlength(text, font=fnt) > (node.w - 16) * SS:
                warnings.append("文字超出节点：%s → %r" % (node.id, text))

    for text, y in ((diagram.footer, diagram.height - 66), (" ｜ ".join(diagram.legend),
                                                           diagram.height - 40)):
        if text:
            d.text((40 * SS, y * SS), text, font=f_legend, fill="#5F6368", anchor="lm")

    img.resize((diagram.width, diagram.height), Image.LANCZOS).save(path)
    return warnings


def row(items, y, h, w, gap, canvas_w, default="step"):
    total = len(items) * w + (len(items) - 1) * gap
    x = (canvas_w - total) / 2
    out = []
    for item in items:
        nid, text, sub = item[0], item[1], item[2]
        kind = item[3] if len(item) > 3 else default
        out.append(Node(nid, text, sub, x=x, y=y, w=w, h=h, kind=kind))
        x += w + gap
    return out


def spine(items, center, y0, h, w, gap, default="step"):
    out, y = [], y0
    for item in items:
        nid, text, sub = item[0], item[1], item[2]
        kind = item[3] if len(item) > 3 else default
        out.append(Node(nid, text, sub, x=center - w / 2, y=y, w=w, h=h, kind=kind))
        y += h + gap
    return out


def chain(nodes, **kw):
    return [Edge(nodes[i].id, nodes[i + 1].id, **kw) for i in range(len(nodes) - 1)]
