# -*- coding: utf-8 -*-
"""生成「文档 → 规则」操作界面的静态原型（按层合并页面）。

页面：
  index.html       操作台（状态、待处理、入口）
  data.html        数据层（① 镜像 ② 语料 ③ 索引与分块；含 chunk 列表与勾选）
  authoring.html   提炼与审查（候选池 + 起草 + 候选规则表）
  gates.html       门禁与证据（候选预演 + checker 覆盖 + 原子加载）
  activation.html  审批 · 生效 · 溯源
  system.html      系统（连接自检 / 路由 / 缺口 / 红线 / 反模式）

界面文案只保留标签与状态；解释性内容一律放进 ? 悬停提示。
数据来自仓库真实文件，重建：python docs/project/engineering-policy-platform/designs/console/build_site.py
"""
from __future__ import annotations

import html
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PAGES = [
    ("index.html", "操作台", "index"),
    ("data.html", "数据层", "data"),
    ("authoring.html", "提炼与审查", "authoring"),
    ("gates.html", "门禁与证据", "gates"),
    ("activation.html", "审批与生效", "activation"),
    ("system.html", "系统", "system"),
]

SEVERITIES = ["info", "warning", "error", "critical"]
CHECKER_FIELDS = {
    "forbidden_dependency": [
        {"name": "packages", "label": "禁止依赖的包 / 模块", "kind": "enum-list", "required": True,
         "hint": "证据来自 AST / 依赖图；解析失败不等于没有依赖（C29）"},
    ],
    "missing_docstring": [
        {"name": "targets", "label": "检查对象", "kind": "enum-list", "required": True,
         "values": ["module", "class", "function", "method"], "hint": "只能是这四个之一（C19）"},
        {"name": "include_private", "label": "包含私有对象", "kind": "bool", "required": False},
    ],
    "style_lint": [
        {"name": "tool", "label": "外部工具", "kind": "text", "required": True, "placeholder": "ruff"},
        {"name": "codes", "label": "规则码", "kind": "enum-list", "required": True, "placeholder": "E501, F401",
         "hint": "必须大写且去重（C19）"},
    ],
    "type_check": [
        {"name": "tool", "label": "外部工具", "kind": "text", "required": True, "placeholder": "mypy"},
        {"name": "codes", "label": "规则码", "kind": "enum-list", "required": False},
    ],
    "missing_tests": [
        {"name": "changed_only", "label": "只看变更集", "kind": "bool", "required": False},
    ],
    "failing_tests": [
        {"name": "tool", "label": "测试工具", "kind": "text", "required": True, "placeholder": "pytest"},
    ],
}

ROUTE_PATHS = {
    "evaluate": ("POST", "/v1/policy/evaluate"),
    "retrieve": ("POST", "/v1/knowledge/retrieve"),
    "validate": ("POST", "/v1/validation/evaluate"),
    "health": ("GET", "/v1/health/live"),
    "readiness": ("GET", "/v1/health/ready"),
    "metrics": ("GET", "/v1/ops/metrics"),
}

GAPS = [
    ("G1", "镜像 / 语料状态", "GET /v1/corpus/status", "缺"),
    ("G2", "分块与溯源读取", "GET /v1/corpus/chunks", "缺"),
    ("G3", "草稿校验", "POST /v1/rules/draft", "缺"),
    ("G4", "规则集加载预演", "POST /v1/rules/preview", "缺"),
    ("G5", "门禁聚合", "POST /v1/gates/run", "缺"),
    ("G6", "会话身份", "GET /v1/session", "缺"),
    ("G7", "提交与审批", "不在 policy_api 内（走 Phase 4）", "提案"),
    ("G8", "作业模型", "暂不立项（索引重建实测 149ms）", "不做"),
]

REDLINES = [
    ("R1", "判定只有一条路径", "AGENTS.md 30"),
    ("R2", "证据只由服务端产出", "AGENTS.md 32"),
    ("R3", "租户只来自令牌", "AGENTS.md 33"),
    ("R4", "生效写入必须人工审批", "AGENTS.md 38/39"),
    ("R5", "规则集加载原子", "C22 / C23"),
    ("R6", "skipped_rules ≠ 通过", "规则文档 §1"),
    ("R7", "关键验证器不可用即阻断", "C27 / C28"),
    ("R8", "超时 / 503 / 504 ≠ allow", "AGENTS.md 33"),
    ("R9", "哈希漂移不许静默", "C6 / AGENTS.md 12"),
    ("R10", "观测只记摘要", "AGENTS.md 34"),
    ("R11", "审计身份 = rule_id@version", "C30"),
    ("R12", "不引入 LLM 判定", "功能清单 253"),
]

ANTIPATTERNS = [
    ("AI 一键生成规则", "台阶 4 无自动化且不引入 LLM；来源必须本地（C20）"),
    ("忽略门禁 / 强制启用", "C23 一条坏 = 整批不加载；空集也拒绝替换"),
    ("改已发布规则不升 version", "审计身份 = rule_id@version（C30）"),
    ("把建议写成规则", "代码挡不住把建议挂在 style_lint 上"),
    ("跨租户查看 / 提交", "租户只来自令牌，越权即拒绝"),
    ("客户端自带证据 / 决策", "证据只由服务端流水线产出"),
    ("自由文本 YAML 编辑", "未知字段 / 枚举 / checker 一律报错（C17、C21）"),
    ("保存即生效", "生效须人工审批且绑 action_hash"),
    ("审批当通用许可", "审批绑 action_hash，短时效、单次使用"),
    ("摘要链当防篡改日志", "删尾或整链重写发现不了"),
]

DEFECTS = [
    ("B1", "受保护写入已修复", "orc.policy.write / orc.policy.edit 均 approval: required；普通写工具阻断五个信任根",
     "回归：test_generic_orchestrator_writes_cannot_touch_trust_roots"),
    ("B2", "HTTP 面漂移已修复", "runtime.index.hash_drift 读取 LoadedCorpus.verification.drift",
     "回归：test_retrieve_reports_real_corpus_hash_drift"),
    ("B3", "幂等超限已修复", "响应无法完整保存时返回 503 idempotency_unavailable",
     "回归：test_oversized_idempotent_response_fails_explicitly_without_a_false_replay"),
]

CONNECTION_FACTS = [
    ("CORS", "app.user_middleware == []；预检 OPTIONS → 405，无 ACAO", "实测"),
    ("静态托管", "/、/index.html、/console 全 404 not_found", "实测"),
    ("认证", "无令牌 / 错令牌 → 401；多租户未声明 tenant → 403 token_scope_mismatch", "实测"),
    ("租户 404", "enabled: false → retryable: false；装配失败 → retryable: true", "实测"),
    ("幂等", ">8192 字节响应显式返回 503 idempotency_unavailable，不写残缺重放记录", "实测"),
    ("预算", "evaluate / retrieve 2000ms，validate 10000ms；并发 8", "实测"),
    ("失败关闭", "未配索引 503；超预算 503；验证器失败 → 200 但 block", "实测"),
    ("静态挂载", "app.mount 不进 OpenAPI paths → 不需要 openapi --write", "实测"),
    ("挂载点", "挂到 / 后未知 POST 404→405、错方法 405→404", "评审实测"),
    ("响应形状", "无 response_model，不受契约快照保护", "评审实测"),
]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def q(tip: str) -> str:
    return '<span class="q" data-tip="' + esc(tip) + '">?</span>'


def chip(kind: str, text: str, tip: str = "") -> str:
    extra = ' data-tip="' + esc(tip) + '"' if tip else ""
    return '<span class="chip ' + kind + '"' + extra + ">" + esc(text) + "</span>"


def table(headers, rows, tip: str = "") -> str:
    head = "".join("<th>" + esc(h) + (q(tip) if (tip and index == len(headers) - 1) else "") + "</th>"
                   for index, h in enumerate(headers))
    body = "".join("<tr>" + "".join("<td>" + cell + "</td>" for cell in row) + "</tr>" for row in rows)
    return "<table><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table>"


def load_data() -> dict:
    data: dict = {"meta": {}, "rules": [], "datasets": [], "mirrors": [], "validators": [],
                  "checkers": [], "chunks": [], "routes": [], "index": {}}
    try:
        from policy.loader import load_rule_set
        rule_set = load_rule_set([ROOT / "policies"], repo_root=ROOT)
        data["meta"]["rule_set_hash"] = str(getattr(rule_set, "identity", ""))
        for rule in getattr(rule_set, "rules", ()):  # type: ignore[attr-defined]
            dump = rule.model_dump(mode="json") if hasattr(rule, "model_dump") else dict(rule)  # type: ignore[arg-type]
            data["rules"].append({
                "id": dump.get("id"), "version": dump.get("version"), "severity": dump.get("severity"),
                "scope": dump.get("scope") or {}, "checker": (dump.get("enforcement") or {}).get("checker"),
                "body": dump.get("rule") or {}, "message": dump.get("message"), "source": dump.get("source") or {},
                "requires_approval": (dump.get("enforcement") or {}).get("requires_approval"),
            })
    except Exception as error:  # noqa: BLE001
        data["meta"]["rules_error"] = "%s: %s" % (type(error).__name__, error)

    try:
        document = yaml.safe_load((ROOT / "knowledge/corpus.yaml").read_text(encoding="utf-8")) or {}
        for dataset in document.get("datasets") or []:
            data["datasets"].append({
                "name": dataset.get("name"), "tier": dataset.get("tier"), "visibility": dataset.get("visibility"),
                "license": dataset.get("license"), "mirror": dataset.get("mirror"),
                "entries": len(dataset.get("entries") or []),
            })
        data["meta"]["rule_sources"] = len(document.get("rule_sources") or [])
    except Exception as error:  # noqa: BLE001
        data["meta"]["corpus_error"] = "%s: %s" % (type(error).__name__, error)

    for manifest in sorted(ROOT.glob("docs/mirrors/*/manifest.json")):
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
            pages = doc.get("pages") or []
            data["mirrors"].append({
                "dir": manifest.parent.name, "pages": len(pages),
                "fetched_at": str(doc.get("fetched_at") or "—")[:19],
                "bytes": sum(int(item.get("bytes") or 0) for item in pages if isinstance(item, dict)),
            })
        except Exception:  # noqa: BLE001
            data["mirrors"].append({"dir": manifest.parent.name, "pages": "?", "fetched_at": "读取失败", "bytes": 0})

    try:
        registry_doc = yaml.safe_load((ROOT / "validation/validators.yaml").read_text(encoding="utf-8")) or {}
        for item in registry_doc.get("validators") or []:
            tool = item.get("tool") or {}
            data["validators"].append({
                "id": item.get("id"), "kind": item.get("kind"), "stage": item.get("stage"),
                "critical": bool(item.get("critical")), "checkers": item.get("checkers") or [],
                "requires": item.get("requires") or [], "config": tool.get("config") if isinstance(tool, dict) else None,
            })
    except Exception as error:  # noqa: BLE001
        data["meta"]["registry_error"] = "%s: %s" % (type(error).__name__, error)

    try:
        from policy.checkers import SUPPORTED_CHECKERS
        supported = list(SUPPORTED_CHECKERS)
    except Exception:  # noqa: BLE001
        supported = ["forbidden_dependency", "missing_docstring", "style_lint", "type_check", "missing_tests", "failing_tests"]
    for checker in supported:
        data["checkers"].append({"id": checker, "validators": [v for v in data["validators"] if checker in v["checkers"]]})
    data["checker_fields"] = CHECKER_FIELDS

    index_path = ROOT / ".tmp/retrieval/index.sqlite3"
    if index_path.is_file():
        try:
            conn = sqlite3.connect(str(index_path))
            counts = {}
            for (name,) in conn.execute("select name from sqlite_master where type='table'"):
                try:
                    counts[name] = int(conn.execute("select count(*) from " + name).fetchone()[0])
                except Exception:  # noqa: BLE001
                    counts[name] = -1
            data["index"] = {"exists": True, "counts": counts,
                             "built_at": datetime.fromtimestamp(index_path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
            columns = [row[1] for row in conn.execute("pragma table_info(chunks)")]
            if columns:
                picked = [c for c in ("chunk_id", "document_id", "document", "dataset", "heading_path", "text", "text_hash", "source_url", "license") if c in columns]
                for row in conn.execute("select " + ", ".join(picked) + " from chunks order by chunk_id"):
                    record = dict(zip(picked, row))
                    heading = record.get("heading_path")
                    if isinstance(heading, str):
                        try:
                            heading = " › ".join(json.loads(heading))
                        except Exception:  # noqa: BLE001
                            pass
                    text = str(record.get("text") or "")
                    data["chunks"].append({
                        "chunk_id": record.get("chunk_id"), "document": record.get("document_id") or record.get("document"),
                        "dataset": record.get("dataset"), "heading": heading or "—", "hash": record.get("text_hash"),
                        "text": text, "url": record.get("source_url"), "license": record.get("license"),
                    })
            conn.close()
        except Exception as error:  # noqa: BLE001
            data["index"] = {"exists": True, "error": "%s: %s" % (type(error).__name__, error), "counts": {}}
    else:
        data["index"] = {"exists": False, "counts": {}, "hint": "python -m retrieval.cli index"}

    try:
        from policy_api.runtime import ROUTES
        names = list(ROUTES)
    except Exception:  # noqa: BLE001
        names = list(ROUTE_PATHS)
    for name in names:
        method, path = ROUTE_PATHS.get(name, ("?", "?"))
        data["routes"].append({"name": name, "method": method, "path": path})

    data["severities"] = SEVERITIES
    data["gaps"] = [{"id": g[0], "title": g[1], "design": g[2], "status": g[3]} for g in GAPS]
    data["redlines"] = [{"id": r[0], "rule": r[1], "basis": r[2]} for r in REDLINES]
    data["antipatterns"] = [{"title": a[0], "why": a[1]} for a in ANTIPATTERNS]
    data["defects"] = [{"id": d[0], "title": d[1], "evidence": d[2], "fix": d[3]} for d in DEFECTS]
    data["connection"] = [{"title": c[0], "fact": c[1], "source": c[2]} for c in CONNECTION_FACTS]
    data["meta"]["built_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return data


NAV = "".join(
    '<a href="' + slug + '">' + esc(label) + "</a>" for slug, label, _key in PAGES
)


_STAMP = "dev"


def stamp() -> str:
    return _STAMP


def layout(key: str, title: str, body: str, built_at: str) -> str:
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>" + esc(title) + " · 文档 → 规则 操作台</title>\n"
        '<link rel="stylesheet" href="assets/style.css?v=' + stamp() + '">\n</head>\n'
        '<body data-page="' + key + '">\n'
        '<header class="top">\n  <div class="brand">文档 → 规则 操作台\n'
        '    <span class="meta">原型 v' + stamp() + " · " + esc(built_at) + " · " + q("静态原型：只读 + 预演；没有写路径。数据取自仓库真实文件快照。") + "</span>\n  </div>\n"
        '  <nav class="nav">' + NAV + "</nav>\n</header>\n"
        '<main>\n  <h1>' + esc(title) + "</h1>\n  " + body + "\n</main>\n"
        '<script src="assets/data.js?v=' + stamp() + '"></script>\n<script src="assets/app.js?v=' + stamp() + '"></script>\n</body>\n</html>\n'
    )


def page_index(data: dict) -> str:
    meta = data["meta"]
    counts = data["index"].get("counts", {})
    chunks = counts.get("chunks", len(data["chunks"]))
    stages = [
        ("1 数据层", "data.html", str(len(data["mirrors"])) + " 镜像 · " + str(len(data["datasets"])) + " 语料 · " + str(chunks) + " chunk", "gap"),
        ("2 提炼与审查", "authoring.html", str(len(data["chunks"])) + " 个候选点可勾选", "gap"),
        ("3 门禁与证据", "gates.html", str(len(data["checkers"])) + " checker · " + str(len(data["validators"])) + " 验证器", "ok"),
        ("4 审批与生效", "activation.html", "1 个待审批动作", "no"),
    ]
    strip = "".join(
        '<a class="panel" style="display:block" href="' + slug + '">'
        '<div class="small">' + chip(kind, "第 " + name.split(" ")[0] + " 步") + "</div>"
        "<div style='margin-top:6px;font-weight:600'>" + esc(name.split(" ", 1)[1]) + "</div>"
        '<div class="small">' + esc(info) + "</div></a>"
        for name, slug, info, kind in stages
    )
    kpis = [
        (str(len(data["rules"])), "规则", "真实加载 policies/"),
        (str(chunks), "chunk", "检索索引中的片段数"),
        (str(len(data["datasets"])), "语料数据集", "knowledge/corpus.yaml"),
        (str(len(data["validators"])), "验证器", "validation/validators.yaml"),
    ]
    kpi_html = "".join(
        '<div class="panel kpi"><b>' + esc(v) + "</b><span>" + esc(label) + q(tip) + "</span></div>" for v, label, tip in kpis
    )
    blockers = (
        '<div class="toolbar" style="margin:0">'
        + "".join(chip("no", d["id"] + " " + d["title"], d["evidence"] + " ｜ 修法：" + d["fix"]) for d in data["defects"])
        + '<a class="small" href="system.html">详情 →</a></div>'
    )
    return (
        '<div class="row c4">' + strip + "</div>\n"
        '<div class="row c4" style="margin-top:12px">' + kpi_html + "</div>\n"
        "<h2>阻塞</h2>\n"
        '<div class="panel">' + blockers + "</div>\n"
        '<h2>系统状态</h2>\n'
        '<div class="panel">'
        '<div class="small">rule_set_hash' + q("RuleSet.identity：规则内容变化即变化，传播到检索缓存、Phase 7 观测摘要、Phase 8 checkpoint 兼容性判定") + "</div>"
        '<div class="mono">' + esc(meta.get("rule_set_hash") or meta.get("rules_error") or "—") + "</div>"
        '<div class="small" style="margin-top:8px">rule_sources' + q("由镜像文档提炼的规则应在此登记溯源；当前为 0 条，所以 DOC-001 查不回原文 chunk（CLI 退出 1）") + "</div>"
        "<div>" + chip("gap" if not meta.get("rule_sources") else "ok", str(meta.get("rule_sources", 0)) + " 条") + "</div>"
        "</div>\n"
    )


def page_data(data: dict) -> str:
    mirror_rows = [
        ['<span class="mono">' + esc(m["dir"]) + "</span>", esc(m["pages"]),
         ("%.0f KiB" % (m["bytes"] / 1024)) if m["bytes"] else "—", esc(m["fetched_at"]),
         chip("gap", "未核对", "未请求检索或租户检索不可用时显示未核对；有检索响应后展示服务端真实 hash_drift")]
        for m in data["mirrors"]
    ]
    corpus_rows = [
        ['<span class="mono">' + esc(d["name"]) + "</span>", esc(d["tier"]), esc(d["visibility"]),
         esc(d["license"]), esc(d["entries"]), '<span class="mono">' + esc(d["mirror"] or "—") + "</span>"]
        for d in data["datasets"]
    ]
    index = data["index"]
    counts = index.get("counts", {})
    idx_chips = (
        chip("ok", "索引 " + esc(index.get("built_at", "?")))
        + " " + chip("n", "documents " + str(counts.get("documents", "—")))
        + " " + chip("n", "chunks " + str(counts.get("chunks", len(data["chunks"]))))
        + " " + chip("n", "rule_sources 表 " + str(counts.get("rule_sources", 0)))
    ) if index.get("exists") else chip("gap", "索引未建", index.get("hint", ""))
    chunk_rows = "".join(
        "<tr>"
        '<td><input type="checkbox" data-chunk="' + esc(c["chunk_id"]) + '"></td>'
        '<td class="mono">' + esc(c["chunk_id"]) + "</td>"
        "<td>" + esc(c["dataset"]) + "</td>"
        "<td>" + esc(c["heading"]) + "</td>"
        "<td>" + esc(c["text"][:60]) + "…</td>"
        '<td class="mono">' + esc((c["hash"] or "")[:10]) + "…</td>"
        "</tr>"
        for c in data["chunks"]
    )
    return (
        '<div class="tabs">'
        '<button data-tab="mirror">① 镜像</button>'
        '<button data-tab="corpus">② 语料</button>'
        '<button data-tab="chunks">③ 索引与分块</button>'
        "</div>\n"
        '<section data-panel="mirror">\n'
        '<div class="toolbar">'
        + chip("gap", "哈希状态：未核对", "G1 未落地前不能显示「一致」或「无漂移」")
        + '<button class="btn" disabled' + ' data-tip="' + esc("没有对应路由（G1）；今天用 PATH=src python -m retrieval.cli verify") + '">运行校验</button>'
        + "</div>\n"
        + table(["镜像目录", "页数", "体积", "抓取时间", "哈希状态"], mirror_rows) + "\n</section>\n"
        '<section data-panel="corpus" class="hide">\n'
        + table(["dataset", "tier", "visibility", "许可", "条目", "镜像"], corpus_rows) + "\n"
        '<div class="row c2" style="margin-top:12px">\n'
        '<div class="panel">\n'
        '<label class="f">数据集' + q("只能从已声明的 dataset 里选（C1）") + "</label>"
        '<select>' + "".join("<option>" + esc(d["name"]) + "</option>" for d in data["datasets"]) + "</select>\n"
        '<label class="f">镜像页 local_path' + q("必须能在该镜像 manifest.json 的 local_path 里找到（C3）") + "</label>"
        '<input type="text" placeholder="pep-257-docstrings/index.md">\n'
        '<label class="f">license' + q("必填；缺失即清单校验失败、退出码 2（C5）") + "</label>"
        '<input type="text" placeholder="public domain / CC BY-SA 4.0">\n'
        '<div class="toolbar"><button class="btn" disabled'
        + ' data-tip="' + esc("没有语料写入路由（G1/G2）；今天改 knowledge/corpus.yaml 后跑 CLI") + '">保存并预检</button></div>\n'
        "</div>\n"
        '<div class="panel">\n'
        + table(["预检条件", "不满足时"], [
            ["C1 数据集名唯一 / 镜像目录存在", "CorpusError"],
            ["C2 镜像含 manifest.pages", "CorpusError"],
            ["C3 条目在 manifest.local_path 中", "CorpusError"],
            ["C4 source_url 非空", "CorpusError"],
            ["C5 license 必填", "退出码 2"],
            ["C6 sha256 / bytes 与 manifest 一致", "verify 退出 1"],
        ]) + "\n</div>\n</div>\n</section>\n"
        '<section data-panel="chunks" class="hide">\n'
        '<div class="toolbar">' + idx_chips
        + '<input type="text" id="chunk-filter" placeholder="过滤 chunk / 文档 / 标题" style="max-width:280px">'
        + '<span class="spacer"></span>'
        + '<span class="small">已选 <b id="sel-count">0</b></span>'
        + '<button class="btn" id="add-picks">加入候选池 →</button>'
        + q("勾选只是建候选池：一条规则可登记多个 chunk（heading_path 前缀匹配），一个 chunk 可以有 0..N 条要求；纳入规则要逐条审查")
        + "</div>\n"
        '<div class="scroll"><table><thead><tr><th style="width:36px"></th><th>chunk_id</th><th>dataset</th><th>标题路径</th><th>正文</th><th>text_hash</th></tr></thead>'
        '<tbody id="chunk-body"></tbody></table></div>\n'
        '<div class="small" style="margin-top:6px">共 ' + str(len(data["chunks"])) + " 个 chunk" + q("chunk = 文档按标题层级切出的片段；id 由「文档 + 锚点 + 序号」决定，重建索引后同一段原文仍是同一个 id")
        + "</div>\n</section>\n"
        '<script>window.__ROWS__ = ' + json.dumps([c["chunk_id"] for c in data["chunks"]], ensure_ascii=False) + ";</script>\n"
    )


def page_authoring(data: dict) -> str:
    checker_options = "".join(
        '<option value="' + esc(c["id"]) + '">' + esc(c["id"]) + "（" + str(len(c["validators"])) + " 验证器）</option>"
        for c in data["checkers"]
    )
    return (
        '<div class="row side">\n'
        '<div class="panel">\n'
        '<div class="toolbar"><b>候选池</b>'
        + q("来自数据层的勾选；点击行载入起草面板")
        + '<input type="text" id="queue-filter" placeholder="过滤" style="max-width:180px">'
        + '<span class="spacer"></span><span class="small">已选 <b id="picked-count">0</b></span>'
        + '<button class="btn ghost" id="clear-picks">清空</button></div>\n'
        '<div class="scroll" style="max-height:460px"><table><thead><tr><th style="width:36px"></th><th>chunk_id</th><th>标题路径</th><th>状态</th></tr></thead>'
        '<tbody id="queue-body"></tbody></table></div>\n'
        "</div>\n"
        '<div class="stack">\n'
        '<div class="panel">\n'
        '<div class="toolbar"><b>起草</b>'
        + q("台阶 4 是整条链路唯一的人工步骤；字段受控，形状错误当场暴露")
        + "</div>\n"
        '<label class="f">来源 chunk' + q("来源必须是本地镜像文件；共享对话与外部 URL 不能作为可执行来源（C20）") + "</label>"
        '<input type="text" id="source-path" placeholder="docs/mirrors/<mirror>/<page>/index.md">\n'
        '<div class="small" id="chunk-ref">未选择</div>\n'
        '<label class="f">checker' + q("只有已实现的 checker 能被判定；没有验证器供证的 checker 会让注册表加载失败（C25）") + "</label>"
        '<select id="checker">' + checker_options + "</select>\n"
        "<div id=\"body-fields\"></div>\n"
        '<label class="f">severity' + q("四值枚举；这里只校验字段合法性，最终 Decision 必须来自 Policy API（C15）") + "</label>"
        '<select id="severity"><option>warning</option><option>error</option><option>critical</option><option>info</option></select>\n'
        '<label class="f">message' + q("命中时给人看的解释，必填") + "</label>"
        '<input type="text" id="message">\n'
        '<div class="toolbar"><button class="btn" id="dry-run">预演门禁</button>'
        '<button class="btn ghost" id="add-candidate" disabled>加入候选</button>'
        + q("候选只存在浏览器本地：草稿没有存储路由（G3），加入候选只是演示流程状态机")
        + "</div>\n"
        '<div id="result"></div>\n'
        "</div>\n"
        '<div class="panel"><b>YAML 预览</b>' + q("界面只生成预览；真正的加载由 policy.loader 原子完成") + '<div id="yaml-preview"></div></div>\n'
        "</div>\n</div>\n"
        "<h2>候选规则</h2>\n"
        '<table><thead><tr><th>#</th><th>checker</th><th>severity</th><th>来源 chunk</th><th>状态</th><th></th></tr></thead><tbody id="cand-body"></tbody></table>\n'
        "<h2>已有规则</h2>\n"
        + table(["审计身份", "severity", "checker", "规则体", "来源"], [
            ['<span class="mono nowrap">' + esc(r["id"]) + "@" + esc(r["version"]) + "</span>", esc(r["severity"]),
             '<span class="mono">' + esc(r["checker"]) + "</span>",
             '<span class="mono">' + esc(json.dumps(r["body"], ensure_ascii=False)) + "</span>",
             '<span class="mono">' + esc((r.get("source") or {}).get("path") or "—") + "</span>"]
            for r in data["rules"]
        ])
    )


def page_gates(data: dict) -> str:
    coverage_rows = []
    for checker in data["checkers"]:
        providers = checker["validators"]
        if providers:
            detail = "；".join(v["id"] + ("（critical）" if v["critical"] else "") for v in providers)
            status = chip("ok", "已覆盖")
        else:
            detail = "无验证器供证 → 注册表加载失败（C25）"
            status = chip("no", "不可用")
        coverage_rows.append(['<span class="mono">' + esc(checker["id"]) + "</span>", status, esc(detail)])
    rule_rows = "".join(
        '<tr><td><input type="checkbox" data-rule="' + esc(r["id"]) + '"></td>'
        '<td class="mono">' + esc(r["id"]) + "</td><td>" + esc(r["severity"]) + "</td>"
        '<td class="mono">' + esc(r["checker"]) + "</td></tr>"
        for r in data["rules"]
    )
    return (
        "<h2>候选预演</h2>\n"
        '<table><thead><tr><th>#</th><th>checker</th><th>severity</th><th>结果</th><th></th></tr></thead><tbody id="cand-gate-body"></tbody></table>\n'
        "<h2>验证器覆盖</h2>\n"
        + table(["checker", "覆盖", "供证者"], coverage_rows) + "\n"
        "<h2>原子加载</h2>\n"
        '<div class="toolbar" id="gate-summary"></div>\n'
        '<div class="scroll" style="max-height:260px"><table id="gate-table"><thead><tr><th style="width:60px">坏</th><th>规则</th><th>severity</th><th>checker</th></tr></thead>'
        "<tbody>" + rule_rows + "</tbody></table></div>\n"
        '<div class="toolbar"><span class="small">坏规则 → 整批不加载（C23）'
        + q("原子语义：任一文件失败，现有规则集不被替换；空集同样拒绝替换") + "</span></div>\n"
        "<h2>CLI</h2>\n"
        "<pre><code>python -m policy.check --check-rules\npython -m validators.cli registry\npython -m validators.cli probe\npython tools/check_text_conventions.py\npython tools/check_repo_consistency.py</code></pre>\n"
        '<div class="toolbar">' + chip("gap", "G4 无加载预演路由", "今天只能在本地跑上面的命令；控制台要做「点一下预演」必须新增 shadow load 路由，锚点为 repo_root") + "</div>\n"
    )


def page_activation(data: dict) -> str:
    meta = data["meta"]
    return (
        "<h2>提交</h2>\n"
        '<table><tbody id="submit-body"></tbody></table>\n'
        '<div class="toolbar">'
        '<button class="btn" disabled' + ' data-tip="' + esc("原型没有写路径；真实提交必须走 Phase 4 受控执行链（新建 orc.policy.write / 编辑 orc.policy.edit，审批绑 action_hash）") + '">提交审批</button>'
        '<button class="btn ghost" disabled data-tip="' + esc("驳回同样属于审批动作，需要平台记录") + '">驳回</button>'
        + chip("gap", "P-1 已修：规则写入工具均需审批", "新建规则选择 orc.policy.write，编辑选择 orc.policy.edit；普通编排写工具拒绝信任根")
        + "</div>\n"
        "<h2>生效</h2>\n"
        '<div class="panel">\n'
        '<div class="small">rule_set_hash' + q("生效后它会变，并传播到检索缓存、Phase 7 观测摘要、Phase 8 checkpoint 兼容性判定") + "</div>"
        '<div class="mono">' + esc(meta.get("rule_set_hash") or "—") + "</div>\n"
        '<div class="toolbar" style="margin-top:10px">'
        + chip("n", "已生效") + chip("n", "未生效") + chip("no", "生效失败（503 rule_set_unavailable）") + "</div>\n"
        "</div>\n"
        "<h2>溯源</h2>\n"
        '<div class="toolbar">' + chip("gap", "rule_sources " + str(meta.get("rule_sources", 0)) + " 条",
                                        "登记位与校验逻辑已就位，缺的是数据；登记后解析不到 chunk 会让索引 run 失败（C10/C33）")
        + "</div>\n"
        + table(["登记项", "取值"], [
            ["rule_id / rule_version", '<span class="mono">DOC-001 / 1</span>'],
            ["dataset", '<span class="mono">python-pep-code-style</span>'],
            ["source_path", '<span class="mono">pep-257-docstrings/index.md</span>'],
            ["heading_path", '<span class="mono">["Docstring Conventions", "…"]</span>'],
        ]) + "\n"
        "<h2>失败语义</h2>\n"
        + table(["情况", "结果"], [
            ["不登记", chip("gap", "无报错") + " （约定非强制，C33）"],
            ["登记但 chunk 解析不到", chip("no", "索引 run 失败") + "（C10/C33）"],
            ["chunk 内容变化（text_hash 不一致）", chip("no", "阻断") + "（C9）"],
        ])
    )


def page_system(data: dict) -> str:
    route_rows = [['<span class="mono">' + esc(r["name"]) + "</span>", esc(r["method"]),
                   '<span class="mono">' + esc(r["path"]) + "</span>"] for r in data["routes"]]
    gap_rows = [[chip("gap" if g["status"] == "缺" else "prop", g["id"]), esc(g["title"]),
                 '<span class="mono">' + esc(g["design"]) + "</span>", esc(g["status"])] for g in data["gaps"]]
    conn_rows = [[esc(c["title"]), esc(c["fact"]), chip("n", c["source"])] for c in data["connection"]]
    return (
        '<div class="tabs">'
        '<button data-tab="conn">连接</button>'
        '<button data-tab="routes">路由</button>'
        '<button data-tab="gaps">缺口</button>'
        '<button data-tab="rules">红线 · 反模式</button>'
        "</div>\n"
        '<section data-panel="conn">\n'
        '<div class="panel"><div class="toolbar" style="margin-top:0">'
        '<button class="btn" id="probe-btn">GET /v1/health/live</button>'
        '<span class="small">目标 http://127.0.0.1:8088</span>'
        + q("独立源页面读不到响应：服务端没有 CORS 中间件（app.user_middleware == []），预检 OPTIONS 返回 405 且无 ACAO")
        + '</div><div id="probe-out"></div></div>\n'
        + table(["项", "内容", "来源"], conn_rows) + "\n</section>\n"
        '<section data-panel="routes" class="hide">\n' + table(["name", "method", "path"], route_rows) + "\n</section>\n"
        '<section data-panel="gaps" class="hide">\n' + table(["#", "能力", "最小设计", "状态"], gap_rows) + "\n</section>\n"
        '<section data-panel="rules" class="hide">\n'
        + table(["#", "不变量", "依据"], [
            [chip("n", r["id"]), esc(r["rule"]), '<span class="mono">' + esc(r["basis"]) + "</span>"] for r in data["redlines"]
        ]) + "\n"
        + table(["禁止项", "原因"], [[chip("no", a["title"]), esc(a["why"])] for a in data["antipatterns"]]) + "\n</section>\n"
    )


BUILDERS = {
    "index": (page_index, "操作台"),
    "data": (page_data, "数据层（① 镜像 ② 语料 ③ 索引与分块）"),
    "authoring": (page_authoring, "提炼与审查（④ 候选池与起草 ⑤ 规则文件）"),
    "gates": (page_gates, "门禁与证据（⑥）"),
    "activation": (page_activation, "审批 · 生效 · 溯源（⑦）"),
    "system": (page_system, "系统"),
}

STALE = ["mirror.html", "corpus.html", "chunks.html", "extract.html", "approval.html",
         "activate.html", "connection.html", "redlines.html"]


def write_page(slug: str, content: str) -> None:
    cleaned = "\n".join(line.rstrip() for line in content.splitlines()) + "\n"
    (HERE / slug).write_text(cleaned, encoding="utf-8", newline="\n")


def main() -> int:
    data = load_data()
    built = data["meta"]["built_at"]
    global _STAMP
    _STAMP = "".join(ch for ch in built if ch.isdigit())[:12]
    for slug, title, key in PAGES:
        builder, page_title = BUILDERS[key]
        write_page(slug, layout(key, page_title, builder(data), built))
    write_page("assets/data.js", "window.CONSOLE_DATA = " + json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + ";\n")
    for stale in STALE:
        target = HERE / stale
        if target.is_file():
            target.unlink()
    print("生成 %d 页；删除旧页 %d 个；chunk %d 条；规则 %d 条"
          % (len(PAGES), len(STALE), len(data["chunks"]), len(data["rules"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
