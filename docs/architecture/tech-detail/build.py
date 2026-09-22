# -*- coding: utf-8 -*-
"""生成 docs/architecture/tech-detail/ 下的技术关系图与单技术内部流程图。

一个规格源，两种产物：

- <name>.drawio：可编辑源（draw.io 桌面版可直接打开继续调整）；
- <name>.png：渲染图（Pillow 绘制，供快速查看与评审）。

为什么 PNG 不由 draw.io CLI 导出：本机沙箱下 draw.io 的 Electron 进程起不来
（mojo platform_channel 访问被拒），因此渲染走 Pillow，同一份规格算出同样的坐标。

用法（PNG 需要 Pillow）：

    python docs/architecture/tech-detail/build.py            # 只写 .drawio
    python docs/architecture/tech-detail/build.py --png      # 同时渲染 .png

规格里每个节点只有两行文字：短标题（≤14 字）+ 精确锚点（模块 / 函数 / 文件）。
箭头只有一种含义：依赖或调用方向。一个节点只讲一件事。
"""
from __future__ import annotations

import argparse
import pathlib
import xml.sax.saxutils as sax

HERE = pathlib.Path(__file__).resolve().parent

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


# ---------------------------------------------------------------- 规格

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


def build_overview():
    W, H = 1680, 800
    t1 = row([("dshHooks", "dsh Hooks", "外部命令 Hook（exit 0 / 2）", "ext"),
              ("httpc", "HTTP 客户端", "Bearer 令牌 → Policy API", "ext"),
              ("lg", "LangGraph 1.2", "src/orchestration/（消费者）", "ext"),
              ("cli", "CLI / CI", "policy.check · tools/*_loop.py", "ext")],
             90, 62, 250, 100, W)
    t2 = row([("hookaddr", "Hook 线协议", "src/adapters/dsh/hooks.py"),
              ("api", "FastAPI + uvicorn", "src/policy_api/app.py"),
              ("enf", "受控执行", "src/enforcement/"),
              ("val", "代码验证器", "src/validators/（ast · Ruff）"),
              ("ret", "规范检索", "src/retrieval/（SQLite FTS5）")],
             235, 68, 240, 60, W)
    core = Node("core", "Policy Engine", "policy.engine.evaluate（唯一判定路径）",
                530, 470, 620, 88, "core")
    base = Node("base", "pydantic 2 + PyYAML 6", "不可变模型 · policies/ registry/ knowledge/",
                430, 620, 820, 70, "data")
    edges = [
        Edge("dshHooks", "hookaddr", mid_y=165),
        Edge("httpc", "api", "HTTP", "dashed", mid_y=155),
        Edge("lg", "api", "HTTP /v1/…", "dashed", mid_y=178),
        Edge("lg", "enf", "受控写入", "dashed", mid_y=200),
        Edge("cli", "core", "同进程直连", points=[(1620, 152), (1620, 514)],
             to_anchor="right"),
        Edge("hookaddr", "core", mid_y=372, to_dx=-220),
        Edge("api", "core", mid_y=386, to_dx=-110),
        Edge("enf", "core", mid_y=400, to_dx=0),
        Edge("val", "core", "证据协议", mid_y=414, to_dx=110),
        Edge("ret", "core", "decision_ref", mid_y=428, to_dx=220),
        Edge("core", "base", "模型与数据"),
    ]
    return Diagram("00-技术总览", "技术总览：谁依赖谁",
                   "箭头 = 依赖或调用方向；一个方框 = 一项技术；黄色 = 唯一判定核心",
                   t1 + t2 + [core, base], edges, W, H,
                   footer="省略的连线：FastAPI 另装配检索与验证器（见 06 图）；"
                          "受控执行 / 验证器 / 检索 同样加载 YAML 数据。",
                   legend=["实线 = 同进程 import 依赖", "虚线 = 进程 / HTTP 边界",
                           "黄 = 判定核心与门禁", "红 = 失败关闭"])


def build_engine():
    W, H = 1240, 1010
    core = spine([("rs", "规则集就绪", "RuleSet.identity（与加载顺序无关）"),
                  ("ctx", "上下文规范化", "normalize_context · 只接受显式字段"),
                  ("match", "范围匹配", "matching_rules · 同维 OR / 跨维 AND"),
                  ("skip", "跳过要写原因", "skipped_rules（skipped ≠ 通过）", "gate"),
                  ("ev", "证据门禁", "blocker_for / serves(checker)", "gate"),
                  ("disp", "checker 分派", "checker_handler(checker)"),
                  ("sort", "违规稳定排序", "violations.sort(rule_id)"),
                  ("appr", "审批标记", "requires_approval → RequiredAction"),
                  ("dec", "三值判定", "allow / allow_with_warnings / block", "core")],
                 420, 100, 64, 600, 26)
    extra = [Node("nocov", "无证据不判通过", "验证器不可用 / 未覆盖 → critical",
                  950, 500, 280, 76, "fail"),
             Node("needappr", "高风险要人批", "RequiredAction.APPROVAL",
                  950, 692, 280, 76, "fail")]
    edges = chain(core) + [
        Edge("disp", "nocov", "证据缺失", "dashed", from_anchor="right", to_anchor="left"),
        Edge("appr", "needappr", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("01-判定核心-Policy-Engine", "单技术：Policy Engine 内部流程",
                   "唯一入口 policy.engine.evaluate；相同输入必须得到相同结论",
                   core + extra, edges, W, H,
                   footer="规则加载在 loader.py（任一文件失败即整体不加载）；"
                          "证据由 Phase 5 验证器产出，engine 只消费。",
                   legend=["黄 = 门禁与判定", "红 = 失败关闭路径"])


def build_dsh():
    W, H = 1240, 1010
    core = spine([("h1", "dsh 调用 Hook", "PreToolUse · stdin JSON"),
                  ("h2", "接线自检", "内部预算 5000ms < hooks.json 超时 30s"),
                  ("h3", "事件映射", "adapter.py → AgentEvent（未知一律拒绝）"),
                  ("h4", "工具表白名单", "未登记 / mcp__ 前缀 → 阻断", "gate"),
                  ("h5", "路径范围校验", "归一化后必须落在受控项目内", "gate"),
                  ("h6", "平台判定", "policy.engine.evaluate（+ Phase 5 证据）"),
                  ("h7", "exit 0 放行 / exit 2 阻断", "发生在工具执行之前", "core"),
                  ("h8", "审计写回", "JSONL 摘要链；不可写 → 失败关闭"),
                  ("h9", "PostToolUse", "只做 post-check，不再调 callback", "ext")],
                 420, 100, 64, 600, 26)
    extra = [Node("failclosed", "失败关闭靠自己", "超时 / 崩溃 / 异常一律转 exit 2",
                  950, 340, 280, 86, "fail")]
    edges = chain(core) + [
        Edge("h2", "failclosed", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("02-dsh-Hook-内部流程", "单技术：dsh Hook 内部流程",
                   "dsh 只作为外部进程与线协议存在；适配器不导入 dsh 的任何类型",
                   core + extra, edges, W, H,
                   footer="能力上限由 adapters/dsh/manifest.yaml 声明，"
                          "与 adapters/approved.json 的已审核哈希不一致即拒绝接入。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


def build_retrieval():
    W, H = 1240, 1010
    core = spine([("r1", "摄取清单", "knowledge/corpus.yaml", "data"),
                  ("r2", "镜像哈希校验", "manifest.json sha256（漂移 → verify 退出 1）", "gate"),
                  ("r3", "分块", "chunker：标题层级 + 预算打包（原文不改写）"),
                  ("r4", "FTS5 索引库", "documents / chunks / chunks_fts（CJK 逐字切分）", "core"),
                  ("r5", "查询规范化", "query.py：受控词项 + 术语桥接", "gate"),
                  ("r6", "参数化查询", "MATCH ?（原始文本永不拼进 SQL）"),
                  ("r7", "权限过滤", "AccessScope（查询文本不能扩权）", "gate"),
                  ("r8", "结果带来源", "路径 / URL / 许可 / 文本哈希"),
                  ("r9", "三个显式状态", "no_results / 无权限 / knowledge_unavailable",
                   "core")],
                 420, 100, 64, 600, 26)
    extra = [Node("nofallback", "绝不回退模型记忆", "不可用时只输出 knowledge_unavailable",
                  950, 596, 280, 86, "fail")]
    edges = chain(core) + [
        Edge("r7", "nofallback", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("03-检索-SQLite-FTS5", "单技术：离线规范检索（SQLite FTS5）",
                   "先有可解释的词法基线；向量检索是端口，未进默认链路",
                   core + extra, edges, W, H,
                   footer="索引库是构建产物（.tmp/retrieval/index.sqlite3），可随时重建；"
                          "相似度分数只用于排序，不是授权信号。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


def build_enforcement():
    W, H = 1340, 1010
    core = spine([("e1", "动作请求", "ActionRequest + 规范化参数"),
                  ("e2", "注册表审核", "approved.json 哈希比对（漂移 → 不可用）", "gate"),
                  ("e3", "授权指纹", "action_hash（schema+参数+主体+权限+上下文）"),
                  ("e4", "执行前检查", "precheck：规则 / 权限 / 白名单 / 限流 / 审计", "gate"),
                  ("e5", "高风险审批", "destructive / external / privileged → 人工", "gate"),
                  ("e6", "短时效 grant", "有效期 60s · 单次使用"),
                  ("e7", "执行一次", "driver；重复 action_id 绝不执行第二次"),
                  ("e8", "事后验证", "前后哈希 / diff 摘要 / 退出码"),
                  ("e9", "审计链 + 台账", "追加写 JSONL（不可写 → 不执行）", "core")],
                 420, 100, 64, 600, 26)
    extra = [Node("blocked", "结构性阻断", "command_composition_blocked / fragment_blocked",
                  950, 404, 360, 86, "fail"),
             Node("repair", "证据不足", "repair_required；回滚声明不了 → unsupported",
                  950, 692, 360, 86, "fail")]
    edges = chain(core) + [
        Edge("e4", "blocked", "", "dashed", from_anchor="right", to_anchor="left"),
        Edge("e8", "repair", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("04-受控执行", "单技术：受控执行（Phase 4）",
                   "授权只认结构化记录：注册表是数据，模型不能自己声明动作类别",
                   core + extra, edges, W, H,
                   footer="风险级别 / 参数白名单 / 审批门禁 / 事后验证器都在 "
                          "registry/tool-registry.yaml；审计链是摘要链，不是防篡改日志。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


def build_validators():
    W, H = 1240, 1010
    core = spine([("v1", "变更集", "git diff / 显式文件列表"),
                  ("v2", "读取 + 内容哈希", "source.py（超大 / 非 UTF-8 → 失败关闭）", "gate"),
                  ("v3", "验证器注册表", "validation/validators.yaml", "data"),
                  ("v4", "最小相关测试", "selection：related → package → suite"),
                  ("v5", "标准库 AST", "python_ast / depgraph（解析失败 ≠ 没有依赖）"),
                  ("v6", "外部工具探针", "Ruff / pytest（mypy 端口就绪，未启用）"),
                  ("v7", "按模板调用", "allowlist / 白名单 env / 超时杀进程树 / 输出脱敏"),
                  ("v8", "证据包", "EvidenceBundle：ID+版本+行列+配置哈希", "core"),
                  ("v9", "交回判定核心", "验证器只产证据，不判 allow / block")],
                 420, 100, 64, 600, 26)
    extra = [Node("critical", "没证据就阻断", "工具缺失 / 版本不符 / 超时 / 未覆盖 → critical",
                  950, 596, 280, 96, "fail")]
    edges = chain(core) + [
        Edge("v6", "critical", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("05-代码验证器", "单技术：代码验证器（Phase 5）",
                   "验证器只产证据；allow / block 仍由 Policy Engine 决定",
                   core + extra, edges, W, H,
                   footer="外部工具不是包依赖：由探针发现，缺失即失败关闭；"
                          "证据里不得出现绝对路径、耗时或凭据。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


def build_api():
    W, H = 1340, 1010
    core = spine([("a1", "HTTP 请求", "Bearer 令牌 + JSON DTO"),
                  ("a2", "体积与字段守卫", "超限 / 未知字段 → 结构化错误", "gate"),
                  ("a3", "认证", "令牌 sha256 → 租户（租户只来自令牌）", "gate"),
                  ("a4", "预算与限流", "超时 → 504，绝不 allow"),
                  ("a5", "幂等台账", "重放返回原响应；换请求体 → 409"),
                  ("a6", "服务装配", "规则集 / 检索 / 验证器流水线"),
                  ("a7", "平台判定", "policy.engine.evaluate（唯一路径）", "core"),
                  ("a8", "版本化响应", "API_SCHEMA_VERSION 与决策协议各自演进"),
                  ("a9", "观测与锚定", "请求级 JSONL 摘要 + seal / verify")],
                 420, 100, 64, 600, 26)
    extra = [Node("apierr", "结构化错误码", "未认证 / 跨租户 / 依赖不可用（不泄露资源是否存在）",
                  950, 292, 360, 96, "fail")]
    edges = chain(core) + [
        Edge("a3", "apierr", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("06-Policy-API", "单技术：Policy API（FastAPI 传输边界）",
                   "API 只做协议 → 领域模型 → 协议；判定仍只有一条路径",
                   core + extra, edges, W, H,
                   footer="Web 框架只在 policy_api 包内；核心层导入 Web 框架会被契约测试拒绝；"
                          "错误码到 HTTP 状态由 errors.STATUS_BY_CODE 推导。",
                   legend=["黄 = 门禁", "红 = 失败关闭"])


def build_orchestration():
    W, H = 1400, 1120
    core = spine([("o1", "需求分析", "requirement_analysis"),
                  ("o2", "策略检索", "policy_retrieval（检索必须可用）"),
                  ("o3", "架构规划", "architecture_planning"),
                  ("o4", "实施", "implementation（副作用前先写意图）"),
                  ("o5", "验证", "validation（读结构化 Decision）", "gate"),
                  ("o6", "修复", "repair（轮次硬上限）"),
                  ("o7", "测试", "testing"),
                  ("o8", "收尾", "review → 终态", "core")],
                 540, 110, 66, 560, 30)
    side = [Node("platform", "平台判定（Policy API）", "每次动手前要一个 Decision；不可用 → blocked",
                 900, 300, 380, 76, "gate"),
            Node("enforce", "受控执行（Phase 4）", "写入走受控执行链，不绕过平台台账",
                 900, 400, 380, 76, "step"),
            Node("ckpt", "checkpoint", "单文件 + 原子替换 + 兼容性凭据", 120, 900, 520, 76, "data"),
            Node("term", "终态三值", "blocked / needs_human / failed（由失败码决定）",
                 760, 900, 520, 76, "fail")]
    edges = [Edge("o1", "o2"), Edge("o2", "o3"), Edge("o3", "o4"), Edge("o4", "o5"),
             Edge("o5", "o7", "allow"), Edge("o7", "o8"),
             Edge("o5", "o6", "block / 需修复", mid_y=616),
             Edge("o6", "o4", "带上限的修复循环", points=[(180, 623), (180, 431)],
                  from_anchor="left", to_anchor="left"),
             Edge("o4", "platform", "要 allow", "dashed", from_anchor="right", to_anchor="left"),
             Edge("o5", "platform", "", "dashed", from_anchor="right", to_anchor="left",
                  points=[(840, 527), (840, 338)]),
             Edge("platform", "enforce", "Decision", "dashed"),
             Edge("o5", "ckpt", "每步落盘 / 可恢复", "dashed",
                  points=[(90, 527), (90, 938)], from_anchor="left", to_anchor="left"),
             Edge("o8", "term", "终态", from_anchor="bottom", to_anchor="top")]
    return Diagram("07-LangGraph-编排", "单技术：LangGraph 编排（平台消费者）",
                   "编排只回答下一步做什么；判定仍回平台，删掉本层平台照常独立运行",
                   core + side, edges, W, H,
                   footer="图状态里不放正文（只有摘要与引用）；恢复时与当前凭据比对，"
                          "规则集 / 索引 / 工具 schema 变了就清掉旧 allow 重评。",
                   legend=["黄 = 门禁与核心", "红 = 失败终态", "虚线 = 跨进程调用"])




def build_one_rule():
    W, H = 1440, 1050
    def sy(i):
        return 110 + i * 86
    items = [("d1", "上游官方文档", "PEP 257（public domain）", "ext"),
             ("d2", "镜像落盘", "docs/python-pep-code-style/pep-257-docstrings/index.md", "data"),
             ("d3", "语料登记", "dataset: python-pep-code-style · tier: guidance", "data"),
             ("d4", "分块与索引", "chunk：heading_path + text_hash", "ext"),
             ("d5", "提炼判据", "「公开对象必须有 docstring」= 可判定", "human"),
             ("d6", "选 checker", "missing_docstring（已知 6 个之一）", "human"),
             ("d7", "写规则文件", "policies/coding/DOC-001.yaml · severity: warning", "human"),
             ("d8", "声明证据来源", "validation/validators.yaml → py.docstring", "ext"),
             ("d9", "判定", "证据 rule_id == DOC-001 → allow_with_warnings", "core"),
             ("d10", "溯源登记（约定，当前未做）", "rule_sources 为空 → cli rules 退出 1", "fail")]
    core_nodes = [Node(nid, text, sub, 300, sy(i), 700, 62, kind)
                  for i, (nid, text, sub, kind) in enumerate(items)]
    side = [Node("gap", "已知落差（如实写）",
                 "source.path 不校验文件是否存在；rule_sources 登记非强制", 1040, sy(6), 360, 86, "note")]
    edges = chain(core_nodes) + [
        Edge("d7", "gap", "", "dashed", from_anchor="right", to_anchor="left"),
    ]
    return Diagram("08-单条规则-从文档到判定", "实走：一条规则从文档到判定（PEP 257 → DOC-001）",
                   "整条链路逐段可追：文档 → 语料 → 分块 → 提炼 → checker → 规则 → 证据 → 判定",
                   core_nodes + side, edges, W, H,
                   footer="溯源登记是约定不是门禁：登记了却解析不到 chunk 会让索引 run 失败，"
                          "不登记则没有任何报错——当前仓库就是后者。",
                   legend=["紫 = 人工", "黄 = 判定核心", "红 = 现状落差"])


def build_rule_gate():
    W, H = 1400, 900
    def qy(i):
        return 130 + i * 118
    core_nodes = [Node("q0", "文档里的一段要求", "上游原文里的「必须 / 不得 / 至少」", 190, qy(0), 620, 66, "data"),
                  Node("q1", "① 本地来源？", "source.kind ∈ {project-policy, standard}", 190, qy(1), 620, 66, "gate"),
                  Node("q2", "② 可确定性判定？", "deterministic + checker 已实现 + 有验证器产证据", 190, qy(2), 620, 66, "gate"),
                  Node("q3", "③ 范围可枚举？", "只用 6 个已知维度表达得出来", 190, qy(3), 620, 66, "gate"),
                  Node("q4", "④ 结论落在决策表？", "severity ∈ 四值枚举（error / critical → block）", 190, qy(4), 620, 66, "gate"),
                  Node("ok", "Project Policy：可阻断", "policies/<domain>/<ID>.yaml → 进决策载荷", 190, qy(5), 620, 66, "core")]
    side = [Node("guide", "否则：停在 Curated Guidance", "进语料，供检索与解释；不产生 allow / block",
                 900, qy(2) - 40, 420, 76, "note"),
            Node("never", "明确禁止：不做成规则", "共享对话 / 外部 URL / 模型记忆 / 未知 checker",
                 900, qy(4), 420, 76, "fail")]
    edges = chain(core_nodes) + [
        Edge("q1", "guide", "否", "dashed", from_anchor="right", to_anchor="left"),
        Edge("q2", "guide", "否", "dashed", from_anchor="right", to_anchor="left"),
        Edge("q3", "guide", "否", "dashed", from_anchor="right", to_anchor="left"),
        Edge("q4", "guide", "否", "dashed", from_anchor="right", to_anchor="left"),
        Edge("q4", "ok", "四条都满足", mid_y=qy(4) + 78),
    ]
    return Diagram("09-能不能成为规则", "判定：一段文档要求能不能成为规则",
                   "四条必要条件缺一条，就只能停在 Curated Guidance——绝不写一条「看起来在管、其实没查」的规则",
                   core_nodes + side, edges, W, H,
                   footer="代码强制的是枚举、形状、checker 一致性与批量原子性；"
                          "「语义真的匹配」「来源指向真实文件」靠评审，不靠代码。",
                   legend=["黄 = 必要条件", "灰 = 正确的降级去向", "红 = 明确禁止"])


# 台阶 1–7 的操作总览不在这里：它与 技术架构.drawio 第 2 页同题（七级台阶 + 三道门禁），
# 已在整理文件夹时删除重复图；操作步骤与命令见 docs/architecture/规则文档转化为规则.md §7。
DIAGRAMS = [build_overview, build_engine, build_dsh, build_retrieval, build_enforcement,
            build_validators, build_api, build_orchestration,
            build_one_rule, build_rule_gate]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成技术关系图与单技术内部流程图")
    parser.add_argument("--png", action="store_true", help="同时用 Pillow 渲染 PNG")
    args = parser.parse_args()

    problems = []
    for factory in DIAGRAMS:
        diagram = factory()
        drawio = HERE / (diagram.name + ".drawio")
        write_drawio(diagram, drawio)
        print("写入 %s（%d 节点 / %d 连线）"
              % (drawio.relative_to(HERE.parent.parent), len(diagram.nodes), len(diagram.edges)))
        if args.png:
            png = HERE / (diagram.name + ".png")
            problems.extend("%s：%s" % (diagram.name, w) for w in render_png(diagram, png))
            print("      渲染 %s" % png.relative_to(HERE.parent.parent))
    if problems:
        print("文字适配告警：")
        for item in problems:
            print("  - " + item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
