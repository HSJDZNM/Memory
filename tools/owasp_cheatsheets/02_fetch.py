# -*- coding: utf-8 -*-

import asyncio, re, json, os
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

async def main():
    strat = AsyncHTTPCrawlerStrategy(browser_config=HTTPCrawlerConfig(), max_connections=8)
    cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=45000,
                           css_selector="article.md-content__inner")
    jobs = [(SEED, "seed")] + [(u, "sheet") for u in SHEETS] + [(BASE+u, "index") for u in INDEXES]
    kinds = {u: k for u, k in jobs}
    sem = asyncio.Semaphore(6)
    meta = {}

    async with AsyncWebCrawler(crawler_strategy=strat, config=BrowserConfig(verbose=False)) as c:
        async def one(u):
            async with sem:
                try:
                    r = await asyncio.wait_for(c.arun(u, config=cfg), timeout=90)
                except Exception as e:
                    meta[u] = {"url": u, "slug": slug_of(u), "kind": kinds[u], "success": False,
                               "status": None, "chars": 0, "saved": False, "error": type(e).__name__,
                               "title": "", "desc": "", "h2": [], "links_out": []}
                    print("ERR " + slug_of(u) + " " + type(e).__name__)
                    return
                slug = slug_of(u)
                md = clean_md(getattr(r.markdown, "raw_markdown", "") or str(r.markdown or ""))
                ok = bool(r.success) and len(md) > 300
                m = {"url": u, "slug": slug, "kind": kinds[u], "success": bool(r.success),
                     "status": r.status_code, "chars": len(md), "words": len(md.split()),
                     "title": "", "desc": "", "h2": [], "saved": ok, "links_out": []}
                if ok:
                    open(os.path.join(CONTENT, slug + ".md"), "w", encoding="utf-8").write(md)
                    h1 = re.search(r"^# (.+)$", md, re.M)
                    m["title"] = h1.group(1).strip() if h1 else slug.replace("_", " ")
                    m["h2"] = [x.strip() for x in re.findall(r"^## (.+)$", md, re.M)][:40]
                    m["desc"] = describe(md)
                    internal = [(l.get("href") or "").split("#")[0] for l in (r.links or {}).get("internal", [])]
                    m["links_out"] = sorted(set(x for x in internal if x.startswith(BASE + "cheatsheets/")))
                meta[u] = m
                print(("OK  " if ok else "BAD ") + slug + " " + str(len(md)) + "  " + m["title"][:70])

        await asyncio.gather(*[one(u) for u, _ in jobs])
    json.dump(meta, open(os.path.join(OUT,"meta.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print("")
    print("SAVED:", sum(1 for m in meta.values() if m["saved"]), "/", len(meta))

asyncio.run(main())
