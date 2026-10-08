# -*- coding: utf-8 -*-

import asyncio, re, json, os, shutil
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy
from crawl4ai.async_configs import HTTPCrawlerConfig

BASE = "https://cheatsheetseries.owasp.org/"
SEED = BASE + "cheatsheets/Secure_Code_Review_Cheat_Sheet.html"
OUT, CONTENT = "_work/owasp-cheatsheets", "_work/owasp-cheatsheets/content"
os.makedirs(CONTENT, exist_ok=True)

tax = json.load(open(os.path.join(OUT, "taxonomy.json"), encoding="utf-8"))
SHEETS = tax["all_sheets"]
INDEXES = ["index.html","IndexASVS.html","IndexProactiveControls.html","IndexTopTen.html","IndexMASVS.html","Glossary.html"]
PERMALINK = re.compile(r"\[\u00b6\]\([^)]*\)")
BT = chr(96)

def clean_md(md):
    md = PERMALINK.sub("", md)
    md = re.sub(r"[ \t]+$", "", md, flags=re.M)
    return re.sub(r"\n{4,}", "\n\n\n", md).strip() + "\n"

def slug_of(url):
    return url.rstrip("/").split("/")[-1].replace(".html","")

def describe(md):
    out, started = [], False
    for ln in md.splitlines():
        s = ln.strip()
        if s.startswith("# "): started = True; continue
        if not started or s.startswith("#") or s.startswith("![") or s.startswith(">"): continue
        if not s:
            if out: break
            continue
        if s.startswith("*") or s.startswith("-"): continue
        out.append(s)
        if sum(len(x) for x in out) > 320: break
    txt = " ".join(out)
    txt = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", txt).replace("**","").replace(BT,"")
    return re.sub(r"\s+"," ",txt).strip()[:400]

def failure_entry(u, slug, kind, error):
    """一条页面的失败读数（与成功读数同一套键，缺的字段一律写空/0）。"""

    return {"url": u, "slug": slug, "kind": kind, "success": False, "status": None, "chars": 0,
            "words": 0, "saved": False, "error": error, "title": "", "desc": "", "h2": [], "links_out": []}

def reset_content():
    """每轮开跑前清空 content/：上一轮留下的 .md 不许与这一轮的 meta.json 混在一起。"""

    if os.path.isdir(CONTENT):
        shutil.rmtree(CONTENT)
    os.makedirs(CONTENT, exist_ok=True)

def write_atomic(path, text):
    """原子落盘：先写同目录临时文件，再 os.replace 换名——中断只会剩下旧的完整文件。"""

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)

def write_meta(meta):
    write_atomic(os.path.join(OUT, "meta.json"),
                 json.dumps(meta, ensure_ascii=False, indent=1))

async def main():
    strat = AsyncHTTPCrawlerStrategy(browser_config=HTTPCrawlerConfig(), max_connections=8)
    cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=45000,
                           css_selector="article.md-content__inner")
    # SEED 也在 SHEETS 里（index.html 的站内链接本身含种子页），不去重就会被抓两遍；
    # 而 `{u: k for u, k in jobs}` 让后写的 kind 覆盖前面的（seed 变成 sheet）。
    # setdefault = 先写优先：种子页保持 kind="seed"，其余按 sheet / index 归属。
    kinds = {}
    for url, kind in ([(SEED, "seed")] + [(u, "sheet") for u in SHEETS]
                      + [(BASE + u, "index") for u in INDEXES]):
        kinds.setdefault(url, kind)
    jobs = list(kinds.items())
    sem = asyncio.Semaphore(6)
    meta = {}
    reset_content()

    async def one(u):
        slug = slug_of(u)
        try:
            async with sem:
                r = await asyncio.wait_for(c.arun(u, config=cfg), timeout=90)
                md = clean_md(getattr(r.markdown, "raw_markdown", "") or str(r.markdown or ""))
                ok = bool(r.success) and len(md) > 300
                m = {"url": u, "slug": slug, "kind": kinds[u], "success": bool(r.success),
                     "status": r.status_code, "chars": len(md), "words": len(md.split()),
                     "title": "", "desc": "", "h2": [], "saved": ok, "links_out": []}
                if ok:
                    h1 = re.search(r"^# (.+)$", md, re.M)
                    m["title"] = h1.group(1).strip() if h1 else slug.replace("_", " ")
                    m["h2"] = [x.strip() for x in re.findall(r"^## (.+)$", md, re.M)][:40]
                    m["desc"] = describe(md)
                    internal = [(l.get("href") or "").split("#")[0] for l in (r.links or {}).get("internal", [])]
                    m["links_out"] = sorted(set(x for x in internal if x.startswith(BASE + "cheatsheets/")))
                    # 正文先落盘再记账：meta.json 里说 saved 的页面，正文一定已经写完
                    write_atomic(os.path.join(CONTENT, slug + ".md"), md)
                meta[u] = m
                print(("OK  " if ok else "BAD ") + slug + " " + str(len(md)) + "  " + m["title"][:70])
        except Exception as e:
            # 抓取、清洗、落盘，任何一步失败都只记这一页：不让一条页面吞掉整轮结果
            meta[u] = failure_entry(u, slug, kinds[u], type(e).__name__)
            print("ERR " + slug + " " + type(e).__name__)
        if len(meta) % 25 == 0:
            write_meta(meta)  # 逐段刷盘：进程被硬杀也不至于只剩上一轮的索引

    try:
        async with AsyncWebCrawler(crawler_strategy=strat, config=BrowserConfig(verbose=False)) as c:
            outcomes = await asyncio.gather(*[one(u) for u, _ in jobs], return_exceptions=True)
            for (u, _kind), outcome in zip(jobs, outcomes):
                if isinstance(outcome, BaseException) and u not in meta:
                    meta[u] = failure_entry(u, slug_of(u), kinds[u], type(outcome).__name__)
    finally:
        # 无论怎么结束（含 Ctrl-C）都留下与 content/ 同一轮的 meta.json
        write_meta(meta)
    print("")
    print("SAVED:", sum(1 for m in meta.values() if m["saved"]), "/", len(meta))

if __name__ == "__main__":
    asyncio.run(main())
