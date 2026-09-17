# -*- coding: utf-8 -*-

import json, os, re, shutil, datetime, collections

BT = chr(96); FENCE = BT * 3
SRC = "_work/owasp-cheatsheets/content"
OUT = "docs/owasp-cheatsheets"
TODAY = datetime.date.today().isoformat()

meta = json.load(open("_work/owasp-cheatsheets/meta.json", encoding="utf-8"))
tax  = json.load(open("_work/owasp-cheatsheets/taxonomy.json", encoding="utf-8"))
by_slug = {m["slug"]: m for m in meta.values()}
sheets_saved = {s: m for s, m in by_slug.items() if m.get("saved") and m.get("kind") == "sheet"}
indexes_saved = {s: m for s, m in by_slug.items() if m.get("saved") and m.get("kind") == "index"}

def chap(t):
    m = re.match(r"^(V\d+)", t)
    return m.group(1) if m else None

asvs_ch = collections.defaultdict(set); asvs_sub = collections.defaultdict(set)
pc = collections.defaultdict(set); t10 = collections.defaultdict(set); mas = collections.defaultdict(set)
for name, key in [("IndexASVS.html","asvs"),("IndexProactiveControls.html","pc"),
                  ("IndexTopTen.html","t10"),("IndexMASVS.html","mas")]:
    for s in tax["indexes"][name]:
        for u in s["sheets"]:
            if key == "asvs":
                c = chap(s["title"])
                if c: asvs_ch[u].add(c)
                asvs_sub[u].add(s["title"].split()[0])
            elif key == "pc": pc[u].add(s["title"].split(".")[0])
            elif key == "t10": t10[u].add(s["title"].split(":")[0])
            else: mas[u].add(s["title"].split()[0])

# ---------------- 层级划分 ----------------
# value = (一级目录, 二级目录 or None)
P = {}
def put(folder, sub, *slugs):
    for s in slugs: P[s] = (folder, sub)

put("01_安全需求、架构与治理", None,
    "Abuse_Case_Cheat_Sheet","Attack_Surface_Analysis_Cheat_Sheet","Threat_Modeling_Cheat_Sheet",
    "Secure_Product_Design_Cheat_Sheet","Security_Terminology_Cheat_Sheet",
    "Microservices_based_Security_Arch_Doc_Cheat_Sheet","Secure_Code_Review_Cheat_Sheet",
    "Legacy_Application_Management_Cheat_Sheet","Vulnerability_Disclosure_Cheat_Sheet",
    "Virtual_Patching_Cheat_Sheet","Third_Party_Payment_Gateway_Integration_Cheat_Sheet")
put("02_输入验证、注入与文件处理", None,
    "Input_Validation_Cheat_Sheet","Injection_Prevention_Cheat_Sheet","Query_Parameterization_Cheat_Sheet",
    "SQL_Injection_Prevention_Cheat_Sheet","OS_Command_Injection_Defense_Cheat_Sheet",
    "LDAP_Injection_Prevention_Cheat_Sheet","NoSQL_Security_Cheat_Sheet","XML_Security_Cheat_Sheet",
    "XML_External_Entity_Prevention_Cheat_Sheet","Deserialization_Cheat_Sheet","Bean_Validation_Cheat_Sheet",
    "Cross_Site_Scripting_Prevention_Cheat_Sheet","DOM_based_XSS_Prevention_Cheat_Sheet",
    "XSS_Filter_Evasion_Cheat_Sheet","File_Upload_Cheat_Sheet","Mass_Assignment_Cheat_Sheet",
    "Prototype_Pollution_Prevention_Cheat_Sheet","Server_Side_Request_Forgery_Prevention_Cheat_Sheet")
put("03_Web前端与浏览器安全", None,
    "Content_Security_Policy_Cheat_Sheet","HTTP_Headers_Cheat_Sheet","Clickjacking_Defense_Cheat_Sheet",
    "HTML5_Security_Cheat_Sheet","DOM_Clobbering_Prevention_Cheat_Sheet",
    "Cross-Site_Request_Forgery_Prevention_Cheat_Sheet","XS_Leaks_Cheat_Sheet",
    "Securing_Cascading_Style_Sheets_Cheat_Sheet","AJAX_Security_Cheat_Sheet",
    "Third_Party_Javascript_Management_Cheat_Sheet","HTTP_Strict_Transport_Security_Cheat_Sheet",
    "Unvalidated_Redirects_and_Forwards_Cheat_Sheet","Browser_Extension_Vulnerabilities_Cheat_Sheet")
put("04_API、微服务与Web服务安全", None,
    "REST_Security_Cheat_Sheet","REST_Assessment_Cheat_Sheet","GraphQL_Cheat_Sheet","gRPC_Security_Cheat_Sheet",
    "WebSocket_Security_Cheat_Sheet","Web_Service_Security_Cheat_Sheet","Microservices_Security_Cheat_Sheet")
put("05_身份认证与会话管理", None,
    "Authentication_Cheat_Sheet","Password_Storage_Cheat_Sheet","Multifactor_Authentication_Cheat_Sheet",
    "Forgot_Password_Cheat_Sheet","Choosing_and_Using_Security_Questions_Cheat_Sheet",
    "Credential_Stuffing_Prevention_Cheat_Sheet","Email_Validation_and_Verification_Cheat_Sheet",
    "JAAS_Cheat_Sheet","Session_Management_Cheat_Sheet","Cookie_Theft_Mitigation_Cheat_Sheet")
put("06_授权与访问控制", None,
    "Authorization_Cheat_Sheet","Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet",
    "Transaction_Authorization_Cheat_Sheet","Multi_Tenant_Security_Cheat_Sheet",
    "Authorization_Testing_Automation_Cheat_Sheet","Authorization_Regression_Testing_Cheat_Sheet")
put("07_令牌、联合身份与密码学", None,
    "JSON_Web_Token_Cheat_Sheet","SAML_Security_Cheat_Sheet","OAuth2_Cheat_Sheet",
    "Cryptographic_Storage_Cheat_Sheet","Key_Management_Cheat_Sheet","Secrets_Management_Cheat_Sheet")
put("08_传输层、网络与数据保护", None,
    "Transport_Layer_Security_Cheat_Sheet","Pinning_Cheat_Sheet","Network_Segmentation_Cheat_Sheet",
    "User_Privacy_Protection_Cheat_Sheet","Database_Security_Cheat_Sheet")
put("09_供应链与依赖安全", None,
    "Software_Supply_Chain_Security_Cheat_Sheet","Dependency_Graph_SBOM_Cheat_Sheet",
    "Vulnerable_Dependency_Management_Cheat_Sheet","NPM_Security_Cheat_Sheet")
put("10_日志、监控与错误处理", None,
    "Logging_Cheat_Sheet","Logging_Vocabulary_Cheat_Sheet","Error_Handling_Cheat_Sheet")
put("11_业务逻辑与反自动化", None,
    "Business_Logic_Security_Cheat_Sheet","Denial_of_Service_Cheat_Sheet",
    "Bot_Management_and_Anti-Automation_Cheat_Sheet")
put("12_编程语言与框架专项", "Java与C系",
    "Java_Security_Cheat_Sheet","C-Based_Toolchain_Hardening_Cheat_Sheet")
put("12_编程语言与框架专项", ".NET", "DotNet_Security_Cheat_Sheet")
put("12_编程语言与框架专项", "JavaScript与TypeScript",
    "Nodejs_Security_Cheat_Sheet","Nextjs_Security_Cheat_Sheet")
put("12_编程语言与框架专项", "Python",
    "Django_Security_Cheat_Sheet","Django_REST_Framework_Cheat_Sheet")
put("12_编程语言与框架专项", "PHP与Ruby",
    "PHP_Configuration_Cheat_Sheet","Laravel_Cheat_Sheet","Symfony_Cheat_Sheet","Ruby_on_Rails_Cheat_Sheet")
put("13_云原生、容器与基础设施", "容器与编排",
    "Docker_Security_Cheat_Sheet","NodeJS_Docker_Cheat_Sheet","Kubernetes_Security_Cheat_Sheet")
put("13_云原生、容器与基础设施", "CI-CD与IaC",
    "CI_CD_Security_Cheat_Sheet","GitHub_Actions_Security_Cheat_Sheet",
    "Infrastructure_as_Code_Security_Cheat_Sheet")
put("13_云原生、容器与基础设施", "云架构与零信任",
    "Secure_Cloud_Architecture_Cheat_Sheet","Zero_Trust_Architecture_Cheat_Sheet",
    "Serverless_FaaS_Security_Cheat_Sheet","Subdomain_Takeover_Prevention_Cheat_Sheet")
put("14_AI与LLM应用安全", None,
    "LLM_Prompt_Injection_Prevention_Cheat_Sheet","RAG_Security_Cheat_Sheet","MCP_Security_Cheat_Sheet",
    "AI_Agent_Security_Cheat_Sheet","AI-Powered_Advertising_Systems_Security_Cheat_Sheet",
    "AML_Sanctions_AI_Agent_Payments_Cheat_Sheet","Secure_AI_Model_Ops_Cheat_Sheet",
    "Secure_Coding_with_AI_Cheat_Sheet")
put("15_移动与嵌入式安全", None,
    "Mobile_Application_Security_Cheat_Sheet","Automotive_Security_Cheat_Sheet","Drone_Security_Cheat_Sheet")

# --------- 校验 ---------
missing = sorted(set(sheets_saved) - set(P))
extra   = sorted(set(P) - set(sheets_saved))
print("PLACED:", len(P), "SAVED SHEETS:", len(sheets_saved))
print("MISSING (saved but unplaced):", missing)
print("EXTRA (placed but not saved):", extra)
assert not missing and not extra, "placement mismatch"

INDEX_FILES = {
    "index": ("00_索引与标准", "00_OWASP-Cheat-Sheet-Series-总览.md"),
    "IndexASVS": ("00_索引与标准", "01_索引-OWASP-ASVS-5.0.md"),
    "IndexProactiveControls": ("00_索引与标准", "02_索引-OWASP-Proactive-Controls-2018.md"),
    "IndexTopTen": ("00_索引与标准", "03_索引-OWASP-Top-10-2021.md"),
    "IndexMASVS": ("00_索引与标准", "04_索引-MASVS.md"),
    "Glossary": ("00_索引与标准", "05_索引-字母顺序总索引.md"),
}

def dest_of(slug):
    if slug in P:
        f, sub = P[slug]
        d = os.path.join(OUT, f, sub) if sub else os.path.join(OUT, f)
        return os.path.join(d, slug + ".md")
    if slug in INDEX_FILES:
        f, name = INDEX_FILES[slug]
        return os.path.join(OUT, f, name)
    return None

url2path = {}
for s, m in sheets_saved.items():
    d = dest_of(s)
    if d: url2path[m["url"]] = d
for s, m in indexes_saved.items():
    d = dest_of(s)
    if d: url2path[m["url"]] = d
# 站点根与首页
url2path["https://cheatsheetseries.owasp.org/"] = dest_of("index")
url2path["https://cheatsheetseries.owasp.org/index.html"] = dest_of("index")

LINKRE = re.compile(r'\[([^\]]*)\]\(\s*(https?://cheatsheetseries\.owasp\.org/[^)\s]+?)(\s+"[^"]*")?\s*\)')

def rewrite(md, src_path):
    src_dir = os.path.dirname(src_path)
    def repl(m):
        url = m.group(2)
        base, _, anchor = url.partition("#")
        tgt = url2path.get(base)
        if not tgt: return m.group(0)
        rel = os.path.relpath(tgt, src_dir).replace("\\", "/")
        return "[" + m.group(1) + "](" + rel + (("#" + anchor) if anchor else "") + ")"
    return LINKRE.sub(repl, md)

def tags(m):
    a = sorted(asvs_ch.get(m["url"], set()), key=lambda x: int(x[1:]))
    out = []
    if a: out.append("ASVS " + " ".join(a))
    if pc.get(m["url"]): out.append("PC " + " ".join(sorted(pc[m["url"]])))
    if t10.get(m["url"]): out.append("Top10 " + " ".join(sorted(t10[m["url"]])))
    if mas.get(m["url"]): out.append("MASVS " + " ".join(sorted(mas[m["url"]])))
    return " | ".join(out) if out else "未收录于 OWASP 四大索引"

if os.path.isdir(OUT): shutil.rmtree(OUT)
os.makedirs(OUT)

written = []
for slug, m in sorted(sheets_saved.items()):
    dst = dest_of(slug); os.makedirs(os.path.dirname(dst), exist_ok=True)
    raw = open(os.path.join(SRC, slug + ".md"), encoding="utf-8").read()
    body = rewrite(raw, dst)
    folder = P[slug][0] + (os.sep + P[slug][1] if P[slug][1] else "")
    hdr = ("<!--\n" + "source: " + m["url"] + "\nfetched: " + TODAY +
           "\nsite: OWASP Cheat Sheet Series (https://cheatsheetseries.owasp.org/)\n" +
           "category: " + folder.replace(os.sep, "/") + "\n" +
           "title: " + m["title"] + "\n" +
           "crosswalk: " + tags(m) + "\n-->\n\n")
    open(dst, "w", encoding="utf-8").write(hdr + body)
    written.append((slug, dst, m))

for slug, m in sorted(indexes_saved.items()):
    dst = dest_of(slug); os.makedirs(os.path.dirname(dst), exist_ok=True)
    body = rewrite(open(os.path.join(SRC, slug + ".md"), encoding="utf-8").read(), dst)
    hdr = ("<!--\nsource: " + m["url"] + "\nfetched: " + TODAY + "\nkind: site-index\n-->\n\n")
    open(dst, "w", encoding="utf-8").write(hdr + body)

json.dump({"placement": {k: list(v) for k, v in P.items()},
           "url2path": url2path,
           "index_files": INDEX_FILES,
           "fetched": TODAY},
          open("_work/owasp-cheatsheets/build_state.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written docs:", len(written))
print("BUILD OK")
