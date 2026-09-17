# -*- coding: utf-8 -*-

import json, os, re, collections, datetime, shutil
BT = chr(96); F = BT*3
def c(x): return BT + str(x) + BT
OUT = "docs/owasp-cheatsheets"
st = json.load(open("_work/owasp-cheatsheets/build_state.json", encoding="utf-8"))
meta = json.load(open("_work/owasp-cheatsheets/meta.json", encoding="utf-8"))
tax = json.load(open("_work/owasp-cheatsheets/taxonomy.json", encoding="utf-8"))
by_slug = {m["slug"]: m for m in meta.values()}
sheets = {s: m for s, m in by_slug.items() if m.get("saved") and m.get("kind") == "sheet"}
P = {k: tuple(v) for k, v in st["placement"].items()}
TODAY = st["fetched"]

asvs_sub = collections.defaultdict(list); pc = collections.defaultdict(set)
t10 = collections.defaultdict(set); mas = collections.defaultdict(set)
for name, key in [("IndexASVS.html","asvs"),("IndexProactiveControls.html","pc"),
                  ("IndexTopTen.html","t10"),("IndexMASVS.html","mas")]:
    for s in tax["indexes"][name]:
        for u in s["sheets"]:
            if key == "asvs": asvs_sub[u].append(s["title"].split()[0])
            elif key == "pc": pc[u].add(s["title"].split(".")[0])
            elif key == "t10": t10[u].add(s["title"].split(":")[0])
            else: mas[u].add(s["title"].split()[0])

SCOPE = {
 "01_安全需求、架构与治理": "开发早期的安全需求、威胁建模、攻击面分析、安全设计、安全术语，以及遗留系统、漏洞披露、虚拟补丁、第三方支付集成等治理类指南。",
 "02_输入验证、注入与文件处理": "所有「不可信输入 → 危险汇聚点」类缺陷的防御：输入校验，SQL／命令／LDAP／NoSQL／XML 注入，XSS 输出编码，反序列化，文件上传，批量赋值，原型污染，SSRF。",
 "03_Web前端与浏览器安全": "浏览器侧安全控制：CSP、安全响应头、点击劫持、HTML5、DOM 冲突、CSRF、XS-Leaks、CSS 安全、AJAX、第三方 JS 管理、HSTS、开放重定向、浏览器扩展。",
 "04_API、微服务与Web服务安全": "服务间与对外接口的安全：REST、GraphQL、gRPC、WebSocket、Web Service（SOAP）、微服务架构安全。",
 "05_身份认证与会话管理": "身份认证与会话全生命周期：认证、口令存储、多因素认证、忘记密码、安全问题、撞库防护、邮箱验证、JAAS、会话管理、Cookie 窃取缓解。",
 "06_授权与访问控制": "授权模型与访问控制实现：通用授权、IDOR、事务授权、多租户隔离，以及授权的自动化测试与回归测试。",
 "07_令牌、联合身份与密码学": "自包含令牌与联邦身份（JWT、SAML、OAuth 2.0／OIDC），以及加密存储、密钥管理、机密信息管理。",
 "08_传输层、网络与数据保护": "传输层与网络层防护（TLS、证书／公钥固定、网络分段），以及数据库安全配置与用户隐私保护。",
 "09_供应链与依赖安全": "软件供应链、SBOM、易受攻击依赖管理，以及 NPM 包管理安全最佳实践。",
 "10_日志、监控与错误处理": "安全日志记录、日志词汇规范、日志保护与错误处理。",
 "11_业务逻辑与反自动化": "业务逻辑缺陷、拒绝服务，以及机器人流量与自动化滥用治理。",
 "12_编程语言与框架专项": "面向具体语言／框架的落地清单；二级目录按技术栈划分。",
 "13_云原生、容器与基础设施": "容器与编排、CI/CD 与基础设施即代码、云架构与零信任；二级目录按平台划分。",
 "14_AI与LLM应用安全": "LLM 提示注入、RAG、MCP、AI Agent、AI 模型运维，以及「用 AI 写代码」的安全指南。",
 "15_移动与嵌入式安全": "移动应用、汽车、无人机等终端与嵌入式场景的安全指南。",
}
def tagstr(m):
    a = sorted(set(asvs_sub.get(m["url"], [])), key=lambda x: [int(y) for y in re.findall(r"\d+", x)])
    o = []
    if a: o.append("ASVS " + " ".join(a))
    if pc.get(m["url"]): o.append("PC " + " ".join(sorted(pc[m["url"]])))
    if t10.get(m["url"]): o.append("Top10 " + " ".join(sorted(t10[m["url"]])))
    if mas.get(m["url"]): o.append("MASVS " + " ".join(sorted(mas[m["url"]])))
    return " · ".join(o) if o else "—"

groups = collections.OrderedDict()
for slug, m in sorted(sheets.items()):
    folder, sub = P[slug]
    groups.setdefault(folder, collections.OrderedDict()).setdefault(sub, []).append((slug, m))

G = sorted(groups.items(), key=lambda kv: kv[0])
def subsorted(subs):
    return sorted(subs.items(), key=lambda kv: (kv[0] is not None, kv[0] or ""))

for folder, subs in G:
    lines = ["# " + folder, "", "> 本目录属于 [OWASP 代码安全指南文档库](../README.md)。", "",
             "**收录范围**：" + SCOPE[folder], "",
             "**文档数**：" + str(sum(len(v) for v in subs.values())), ""]
    for sub, items in subsorted(subs):
        if sub: lines += ["## " + sub, ""]
        for slug, m in items:
            rel = (sub + "/" if sub else "") + slug + ".md"
            lines.append("- [" + m["title"] + "](" + rel + ")")
            lines.append("  - " + c(tagstr(m)))
            if m["desc"]:
                d = m["desc"].replace("\n", " ")
                lines.append("  - " + (d[:200] + ("…" if len(d) > 200 else "")))
            lines.append("")
    lines += ["---", "", "抓取时间：" + TODAY + " · 来源：<https://cheatsheetseries.owasp.org/>", ""]
    open(os.path.join(OUT, folder, "README.md"), "w", encoding="utf-8").write("\n".join(lines))

# 00_索引与标准 的目录 README
IDX_DESC = {
    "index": "OWASP Cheat Sheet Series 站点首页",
    "IndexASVS": "ASVS 5.0 章节索引：每篇 cheat sheet 归属的 V1–V17 子章节",
    "IndexProactiveControls": "OWASP Top 10 Proactive Controls 2018 索引（C1–C10）",
    "IndexTopTen": "OWASP Top 10 2021 索引（A01–A11）",
    "IndexMASVS": "MASVS 索引（STORAGE／CRYPTO／AUTH／NETWORK／PLATFORM／CODE／RESILIENCE／PRIVACY）",
    "Glossary": "字母顺序总索引，并标注每篇文档涉及的语言／技术标签",
}
L = ["# 00_索引与标准", "",
     "> 本目录属于 [OWASP 代码安全指南文档库](../README.md)。", "",
     "**收录范围**：OWASP Cheat Sheet Series 站点自带的索引页，非指南正文。"
     "本库的层级划分与全部交叉引用均由这几页推导而来。", "",
     "**文档数**：" + str(len(st["index_files"])), ""]
IDX_TITLE = {"index": "OWASP Cheat Sheet Series 总览"}
for slug, (folder, name) in sorted(st["index_files"].items(), key=lambda kv: kv[1][1]):
    m = by_slug.get(slug, {})
    ttl = IDX_TITLE.get(slug) or re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", m.get("title", slug)).strip() or slug
    L.append("- [" + ttl + "](" + name + ")")
    L.append("  - " + IDX_DESC.get(slug, ""))
    L.append("  - 来源：<" + m.get("url", "") + ">")
    L.append("")
L += ["---", "", "抓取时间：" + TODAY + " · 来源：<https://cheatsheetseries.owasp.org/>", ""]
open(os.path.join(OUT, "00_索引与标准", "README.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L))

total = len(sheets)
R = []; A = R.append
A("# OWASP 代码安全指南文档库（本地层级化存档）"); A("")
A("从 OWASP Cheat Sheet Series 的 **Secure Code Review Cheat Sheet** 出发，沿页面内的超链接爬取，"
  "并逐篇阅读正文后判定取舍，最终保留的「代码安全指南」文档，按安全领域做了层级化归档。"); A("")
A("| 项目 | 内容 |"); A("| --- | --- |")
A("| 种子页 | <https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html> |")
A("| 站点 | OWASP Cheat Sheet Series（<https://cheatsheetseries.owasp.org/>） |")
A("| 抓取工具 | Crawl4AI 0.9.3，" + c("AsyncHTTPCrawlerStrategy") + " 纯 HTTP 策略（站点为静态 MkDocs，无需浏览器） |")
A("| 抓取时间 | " + TODAY + " |")
A("| 候选文档 | 122 篇（种子页导航与正文中出现的全部 cheatsheet 链接） |")
A("| 保留 | **" + str(total) + " 篇** |")
A("| 排除 | 4 篇（已废弃的跳转占位页，内容已迁移） |")
A("| 另附 | " + c("00_索引与标准/") + " 下 6 个站点索引页，用于导航与交叉引用 |")
A(""); A("---"); A("")
A("## 一、层级总览"); A("")
A(F + "text")
A("owasp-cheatsheets/")
A("├── README.md            ← 本文件（库总览与逐篇索引）")
A("├── STRUCTURE.md         ← 层级依据、完整对照表、引用关系")
A("├── manifest.json        ← 机器可读清单（含 sha256）")
A("├── 00_索引与标准/                  ← 站点自带的 6 个索引页（非指南正文）")
for folder, subs in G:
    A("├── " + folder + "/")
    for sub, _it in subsorted(subs):
        if sub: A("│   ├── " + sub + "/")
A("└── LICENSE.txt          ← CC BY-SA 4.0")
A(F); A(""); A("---"); A("")
A("## 二、文档索引（按层级）"); A("")
for folder, subs in G:
    A("### " + folder + "（" + str(sum(len(v) for v in subs.values())) + " 篇）"); A("")
    A("> " + SCOPE[folder]); A("")
    for sub, items in subsorted(subs):
        if sub: A("#### " + sub); A("")
        for slug, m in items:
            rel = folder + "/" + (sub + "/" if sub else "") + slug + ".md"
            A("- **[" + m["title"] + "](" + rel + ")**")
            A("  - 交叉引用：" + tagstr(m))
            A("  - 来源：<" + m["url"] + ">")
        A("")
A("---"); A("")
A("## 三、层级划分依据"); A("")
A("划分以 **OWASP ASVS 5.0 的验证章节（V1–V17）** 为主干——安全代码评审本身就是按 ASVS 逐条核对代码的过程——"
  "并针对 ASVS 未覆盖的技术栈、平台与新兴领域增设专项分支："); A("")
A("- **01–11 类**：对应 ASVS 的通用安全控制维度（需求与设计 V15.1；输入与注入 V1–V2；前端 V3；API V4；文件 V5；"
  "认证 V6；会话 V7；授权 V8；令牌 V9–V10；密码学 V11；传输 V12；数据保护 V14；供应链 V15.2；日志 V16）。")
A("- **12–15 类**：ASVS 未覆盖的领域——编程语言与框架、云原生与基础设施、AI/LLM、移动与嵌入式。")
A("- 每篇文档**只归档一次**（主分类）；它在 ASVS／Top 10／Proactive Controls／MASVS 中的**全部归属**记录在文首元数据与各目录 README 中，"
  "完整对照表见 " + c("STRUCTURE.md") + "，机器可读版本见 " + c("manifest.json") + "。")
A("")
A("> 说明：OWASP 的 ASVS 索引会把同一篇 cheat sheet 映射到多个子章节（例如 Session Management 同时属于 V3、V7、V8、V16）。"
  "本库取「最能代表该文档主题」的单一主分类，而非机械取最小章节号，以避免 Logging 被归入 V10（OAuth）、"
  "Transport Layer Security 被归入 V3（Web 前端）这类明显失真的归档。")
A(""); A("---"); A("")
A("## 四、判定与排除记录"); A("")
A("爬取全部 122 个候选链接后逐篇阅读正文，**排除 4 篇**：它们不是安全指南正文，而是指向新位置的废弃占位页。"); A("")
A("| 已废弃文档 | 抓取到的内容 | 迁移去向 | 处理 |"); A("| --- | --- | --- | --- |")
u2p = {k: v.replace("docs/owasp-cheatsheets" + os.sep, "").replace(os.sep, "/") for k, v in st["url2path"].items()}
A("| Access Control Cheat Sheet | 「DEPRECATED: The Access Control cheatsheet has been deprecated.」（约 220 字符） | [Authorization Cheat Sheet](" +
  u2p["https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html"] + ") | 不保存 |")
A("| TLS Cipher String Cheat Sheet | 「DEPRECATED: ... Please visit the Transport Layer Security Cheat Sheet instead.」（约 250 字符） | [Transport Layer Security Cheat Sheet](" +
  u2p["https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html"] + ") | 不保存 |")
A("| Transport Layer Protection Cheat Sheet | 同上（约 270 字符） | [Transport Layer Security Cheat Sheet](" +
  u2p["https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html"] + ") | 不保存 |")
A("| Injection Prevention in Java Cheat Sheet | 「This information has been moved to the dedicated Java Security CheatSheet」（约 230 字符） | [Java Security Cheat Sheet](" +
  u2p["https://cheatsheetseries.owasp.org/cheatsheets/Java_Security_Cheat_Sheet.html"] + ") | 不保存 |")
A("")
A("保留的 " + str(total) + " 篇均具备完整正文。文档正文中指向上述废弃页的链接保留为 OWASP 线上地址，便于溯源。")
A(""); A("---"); A("")
A("## 五、未纳入范围的外部链接"); A("")
seed = open("_work/owasp-cheatsheets/content/Secure_Code_Review_Cheat_Sheet.md", encoding="utf-8").read()
ext = sorted(set(u.rstrip(".,)") for u in re.findall(r"\]\((https?://[^)\s]+)\)", seed)
                 if "cheatsheetseries.owasp.org" not in u))
A("种子页还指向以下**站外**资源；它们不属于 OWASP Cheat Sheet Series 的 cheat sheet，故未抓取，仅登记备查："); A("")
for u in ext: A("- <" + u + ">")
A(""); A("---"); A("")
A("## 六、使用与复核"); A("")
A("- 每篇文档文首带有 HTML 注释形式的元数据（source／fetched／category／crosswalk），在渲染视图中不可见，但可被 grep 检索。")
A("- 文档之间的 OWASP 站内链接已重写为**相对路径**，离线状态下可直接互跳；站外链接保持原样。")
A("- 复现方式见下文「七、复现」，或直接运行 " + c("python tools/owasp_cheatsheets/pipeline.py all") + "。")
A(""); A("---"); A("")
A("## 七、复现"); A("")
A("本库由仓库内的 " + c("tools/owasp_cheatsheets/") + " 流水线生成，全部脚本使用 crawl4ai 的纯 HTTP 策略（不启动浏览器）：")
A("")
A(F + "text")
A("python tools/owasp_cheatsheets/pipeline.py all")
A("")
A("  01_analyze.py   解析站点四个索引页 -> _work/owasp-cheatsheets/taxonomy.json")
A("  02_fetch.py     抓取 122 篇文档 + 6 个索引页 -> _work/owasp-cheatsheets/{content/,meta.json}")
A("  03_build.py     按层级写入 -> docs/owasp-cheatsheets/（并改写站内链接为相对路径）")
A("  04_index.py     生成 README/STRUCTURE/manifest/LICENSE，并统一换行与编码")
A("  05_verify.py    校验链接完整性、编码、换行与 manifest 校验和")
A(F)
A("")
A("中间产物位于 " + c("_work/owasp-cheatsheets/") + "，可随时删除后重跑。")
A(""); A("---"); A("")
A("抓取时间：" + TODAY + " · 内容版权归 OWASP Foundation 所有（CC BY-SA 4.0）。")
open(os.path.join(OUT, "README.md"), "w", encoding="utf-8", newline="\n").write("\n".join(R) + "\n")

# ---------- 主题索引（每个分类的 README 已完成），收尾：STRUCTURE / manifest / LICENSE ----------
import hashlib

REPO_MAP = {
    "index": "master/Index.md",
    "IndexASVS": "master/IndexASVS.md",
    "IndexProactiveControls": "master/IndexProactiveControls.md",
    "IndexTopTen": "master/IndexTopTen.md",
    "IndexMASVS": "master/IndexMASVS.md",
    "Glossary": None,          # 站点该页由 mkdocs 生成，仓库无对应 .md（已验证 404）
}
EXCLUDED = [
    ("Access_Control_Cheat_Sheet", "Access Control Cheat Sheet",
     "DEPRECATED：正文仅一句废弃声明（约 220 字符）",
     "https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html"),
    ("TLS_Cipher_String_Cheat_Sheet", "TLS Cipher String Cheat Sheet",
     "DEPRECATED：正文仅一句废弃声明（约 250 字符）",
     "https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html"),
    ("Transport_Layer_Protection_Cheat_Sheet", "Transport Layer Protection Cheat Sheet",
     "DEPRECATED：正文仅一句废弃声明（约 270 字符）",
     "https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html"),
    ("Injection_Prevention_in_Java_Cheat_Sheet", "Injection Prevention in Java Cheat Sheet",
     "内容已并入 Java Security（约 230 字符）",
     "https://cheatsheetseries.owasp.org/cheatsheets/Java_Security_Cheat_Sheet.html"),
]

def rel_of(folder, sub, slug):
    return folder + "/" + (sub + "/" if sub else "") + slug + ".md"

def normalize_text(t):
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    return t.rstrip("\n") + "\n"

def normalize_tree(root):
    """统一为 UTF-8（无 BOM）+ LF + 单个结尾换行，符合 .editorconfig / .gitattributes。"""
    changed = 0
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith((".md", ".json", ".txt", ".py")):
                continue
            p = os.path.join(dirpath, fn)
            raw = open(p, "rb").read()
            txt = raw.decode("utf-8-sig")
            new = normalize_text(txt)
            if new != txt or raw.startswith(b"\xef\xbb\xbf"):
                open(p, "w", encoding="utf-8", newline="\n").write(new)
                changed += 1
    return changed

# --- 引用热度：正文相对链接构成的实际引用关系 ---
LINKREL = re.compile(r"\]\(([^)\s#]+\.md)(?:#[^)\s]*)?\)")
refs = collections.Counter()
titles = {}
for folder, subs in G:
    for sub, items in subsorted(subs):
        for slug, m in items:
            titles[rel_of(folder, sub, slug)] = m["title"]
for folder, subs in G:
    for sub, items in subsorted(subs):
        for slug, m in items:
            rel = rel_of(folder, sub, slug)
            src = os.path.join(OUT, rel)
            if not os.path.exists(src):
                continue
            txt = open(src, encoding="utf-8").read()
            src_dir = os.path.dirname(src)
            for tgt in LINKREL.findall(txt):
                if tgt.startswith("http"):
                    continue
                rp = os.path.normpath(os.path.join(src_dir, tgt))
                key = os.path.relpath(rp, OUT).replace(os.sep, "/")
                if key != rel:
                    refs[key] += 1
never = sorted(t for t in titles if refs[t] == 0)

S = []
B = S.append
B("# 文档关系与层级")
B("")
B("本目录收录 OWASP Cheat Sheet Series 中与安全代码评审相关的 **" + str(total) + " 篇指南**，"
  "外加站点自带的 " + str(len(st["index_files"])) + " 个索引页。层级划分的结论来自 OWASP 站点自身公布的四个索引页，不含人工臆测：")
B("")
B("- IndexASVS -> OWASP ASVS 5.0 章节（V1–V17）")
B("- IndexProactiveControls -> OWASP Top 10 Proactive Controls 2018（C1–C10）")
B("- IndexTopTen -> OWASP Top 10 2021（A01–A11）")
B("- IndexMASVS -> MASVS（STORAGE／CRYPTO／AUTH／NETWORK／PLATFORM／CODE／RESILIENCE／PRIVACY）")
B("")
B("## 1. 层级结构")
B("")
B(F + "text")
B("owasp-cheatsheets/")
B("├── README.md            # 库总览与逐篇索引")
B("├── STRUCTURE.md         # 本文件：层级依据、完整对照表、引用关系")
B("├── manifest.json        # 机器可读清单（local_path / source_url / crosswalk / sha256）")
B("├── LICENSE.txt          # CC BY-SA 4.0")
B("├── 00_索引与标准/")
for folder, subs in G:
    B("├── " + folder + "/")
    for sub, _it in subsorted(subs):
        if sub: B("│   ├── " + sub + "/")
B(F)
B("")
B("## 2. 与上游 URL 路径的关系")
B("")
B("仓库内既有的两份镜像（" + c("docs/google-eng-practices") + "、" + c("docs/gitlab-code-review") + "）遵循"
  "「本地目录与 URL 路径严格一一对应」。**本库是有意的例外**：本任务要求按安全领域做层级划分，"
  "因此物理目录按主题重排，不再等于上游 URL 路径。")
B("")
B("代价与补偿：")
B("")
B("- URL 与本地路径的对应关系不再能从路径直接读出，改由 " + c("manifest.json") + " 的 "
  + c("source_url") + " / " + c("local_path") + " 逐页维护。")
B("- 文档之间的站内链接已在正文中改写为相对路径，重排不影响离线浏览；" + c("05_verify.py") + " 会逐条校验。")
B("- 站点自身的 6 个索引页保留在 " + c("00_索引与标准/") + "，用于回溯上游分类。")
B("- 上游 Markdown 源文件路径记录在 " + c("source_repo_path") + "（已抽查验证："
  + c("cheatsheets/<Name>_Cheat_Sheet.md") + " 与四个 Index 页返回 200；"
  + c("Glossary") + " 由站点生成，无对应源文件，记为 null）。")
B("")
B("## 3. 分类范围与文档数")
B("")
B("| 分类 | 文档数 | 收录范围 |")
B("| --- | --- | --- |")
for folder, subs in G:
    B("| " + folder + " | " + str(sum(len(v) for v in subs.values())) + " | " + SCOPE[folder] + " |")
B("| 00_索引与标准 | " + str(len(st["index_files"])) + " | 站点自带的索引页，非指南正文 |")
B("")
B("## 4. 完整对照表")
B("")
B("「主分类／二级分类」为本库归档位置，其余列为 OWASP 官方索引中的归属（同一篇常归属多个 ASVS 子章节）。"
  "机器可读版本见 " + c("manifest.json") + "。")
B("")
B("| # | 文档 | 主分类 | 二级分类 | ASVS 子章节 | Proactive Controls | Top 10 2021 | MASVS | 原始 URL |")
B("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
n = 0
for folder, subs in G:
    for sub, items in subsorted(subs):
        for slug, m in items:
            n += 1
            a = " ".join(dict.fromkeys(asvs_sub.get(m["url"], []))) or "—"
            B("| " + str(n) + " | [" + m["title"] + "](" + rel_of(folder, sub, slug) + ") | " + folder + " | "
              + (sub or "—") + " | " + a + " | " + (" ".join(sorted(pc.get(m["url"], []))) or "—") + " | "
              + (" ".join(sorted(t10.get(m["url"], []))) or "—") + " | "
              + (" ".join(sorted(mas.get(m["url"], []))) or "—") + " | " + m["url"] + " |")
B("")
B("## 5. 被引用最多的文档")
B("")
B("统计口径：本库 " + str(total) + " 篇正文与 " + str(len(st["index_files"])) + " 个索引页之间的相对链接。")
B("")
B("| 文档 | 主分类 | 被引次数 |")
B("| --- | --- | --- |")
for key, cnt in refs.most_common(15):
    ttl = titles.get(key)
    if not ttl:
        continue
    B("| [" + ttl + "](" + key + ") | " + key.split("/")[0] + " | " + str(cnt) + " |")
B("")
B("从未被其他正文引用的文档（" + str(len(never)) + " 篇）。其中多数是技术栈专项、AI 与嵌入式类"
  "（彼此独立、只被索引页列出），以及种子文档本身，属正常：")
B("")
for t in never:
    B("- " + t)
B("")
B("## 6. 排除的文档")
B("")
B("抓取到的 122 个候选链接中，以下 4 篇不是指南正文，而是指向新位置的废弃占位页，故不保存：")
B("")
B("| 文档 | 抓取到的内容 | 迁移去向 |")
B("| --- | --- | --- |")
for slug, title, reason, target in EXCLUDED:
    tgt_rel = st["url2path"].get(target)
    tgt_md = "[" + titles.get(os.path.splitext(os.path.relpath(tgt_rel, OUT))[0].replace(os.sep, "/") + ".md", "后继文档") + "](" + os.path.relpath(tgt_rel, OUT).replace(os.sep, "/") + ")" if tgt_rel else "<" + target + ">"
    B("| " + title + " | " + reason + " | " + tgt_md + " |")
B("")
B("## 7. 建议阅读顺序")
B("")
B("1. 先读 [Secure Code Review Cheat Sheet](" + rel_of(*P["Secure_Code_Review_Cheat_Sheet"], "Secure_Code_Review_Cheat_Sheet")
  + ")（种子文档），了解评审方法论与 checklist。")
B("2. 再按 [01_安全需求、架构与治理](01_安全需求、架构与治理/README.md) → [02_输入验证、注入与文件处理](02_输入验证、注入与文件处理/README.md) "
  "→ [03_Web前端与浏览器安全](03_Web前端与浏览器安全/README.md) 的顺序覆盖通用控制。")
B("3. 之后按技术栈进入 [12_编程语言与框架专项](12_编程语言与框架专项/README.md)、"
  "[13_云原生、容器与基础设施](13_云原生、容器与基础设施/README.md)。")
B("4. 需要对齐合规口径时，直接查 " + c("00_索引与标准/") + " 下的 ASVS／Top 10／Proactive Controls／MASVS 索引。")
B("")
B("---")
B("")
B("生成时间：" + TODAY + " · 内容版权归 OWASP Foundation 所有（CC BY-SA 4.0）")
open(os.path.join(OUT, "STRUCTURE.md"), "w", encoding="utf-8", newline="\n").write(normalize_text("\n".join(S)))

# --- LICENSE ---
lic_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CC-BY-SA-4.0.txt")
shutil.copyfile(lic_src, os.path.join(OUT, "LICENSE.txt"))

# --- 统一换行/编码 ---
changed = normalize_tree(OUT)

# --- manifest.json（sha256 取最终字节） ---
def sha256_of(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

pages = []
for folder, subs in G:
    for sub, items in subsorted(subs):
        for slug, m in items:
            rel = rel_of(folder, sub, slug)
            p = os.path.join(OUT, rel)
            pages.append({
                "local_path": rel,
                "guide": folder,
                "guide_name": SCOPE[folder],
                "role": "cheat-sheet",
                "parent": folder + "/README.md",
                "source_url": m["url"],
                "title": m["title"],
                "source_repo_path": "master/cheatsheets/" + slug + ".md",
                "status": m["status"],
                "bytes": os.path.getsize(p),
                "sha256": sha256_of(p),
                "saved": True,
                "category": folder,
                "subcategory": sub or "",
                "crosswalk": {
                    "asvs": list(dict.fromkeys(asvs_sub.get(m["url"], []))),
                    "proactive_controls": sorted(pc.get(m["url"], [])),
                    "top10_2021": sorted(t10.get(m["url"], [])),
                    "masvs": sorted(mas.get(m["url"], [])),
                },
            })
for slug, (folder, name) in sorted(st["index_files"].items()):
    rel = folder + "/" + name
    p = os.path.join(OUT, rel)
    m = by_slug.get(slug, {})
    pages.append({
        "local_path": rel,
        "guide": "index",
        "guide_name": "站点索引页",
        "role": "site-index",
        "parent": "00_索引与标准/README.md",
        "source_url": m.get("url", ""),
        "title": IDX_TITLE.get(slug)
                 or re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", m.get("title", slug)).strip() or slug,
        "source_repo_path": REPO_MAP.get(slug),
        "status": m.get("status"),
        "bytes": os.path.getsize(p),
        "sha256": sha256_of(p),
        "saved": True,
        "category": "00_索引与标准",
        "subcategory": "",
        "crosswalk": {"asvs": [], "proactive_controls": [], "top10_2021": [], "masvs": []},
    })

manifest = {
    "source": "https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html",
    "site": "https://cheatsheetseries.owasp.org/",
    "fetched_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "crawler": "crawl4ai 0.9.3 / AsyncHTTPCrawlerStrategy",
    "scope": "种子页导航与正文中出现的全部 /cheatsheets/*.html 链接",
    "taxonomy": "OWASP ASVS 5.0 章节（V1-V17）+ 技术栈／平台／AI／嵌入式专项（主题重排，见 STRUCTURE.md）",
    "pages_candidate": 122,
    "pages_saved": len(pages),
    "pages_excluded": len(EXCLUDED),
    "pages": pages,
    "excluded": [
        {"source_url": "https://cheatsheetseries.owasp.org/cheatsheets/" + slug + ".html",
         "title": title, "reason": reason, "superseded_by": target, "saved": False}
        for slug, title, reason, target in EXCLUDED
    ],
}
open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8", newline="\n").write(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

print("OK docs=" + str(total) + " folders=" + str(len(groups))
      + " pages=" + str(len(pages)) + " normalized=" + str(changed))
