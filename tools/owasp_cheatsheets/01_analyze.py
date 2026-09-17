# -*- coding: utf-8 -*-

import asyncio, os, re, json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy
from crawl4ai.async_configs import HTTPCrawlerConfig

BASE = "https://cheatsheetseries.owasp.org/"
SEED = BASE + "cheatsheets/Secure_Code_Review_Cheat_Sheet.html"
BT = chr(96)
LINKRE = re.compile(r"\((https://cheatsheetseries\.owasp\.org/cheatsheets/[^)\s]+\.html)\)")
HEADRE = re.compile(r"^(#{2,4})\s+(.+?)\[\u00b6\]")

def clean(t):
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = t.replace("**", "").replace(BT, "")
    return re.sub(r"\s+", " ", t).strip()

def parse_sections(md):
    secs = []
    for line in md.splitlines():
        h = HEADRE.match(line)
        if h:
            secs.append({"level": len(h.group(1)), "title": clean(h.group(2)), "sheets": []})
            continue
        if secs:
            for m in LINKRE.finditer(line):
                u = m.group(1)
                if u not in secs[-1]["sheets"]:
                    secs[-1]["sheets"].append(u)
    return secs

def sheet_urls(links):
    out = []
    for l in links or []:
        h = (l.get("href") or "").split("#")[0]
        if h.startswith(BASE + "cheatsheets/") and h.endswith(".html"):
            out.append(h)
    return out

async def main():
    strat = AsyncHTTPCrawlerStrategy(browser_config=HTTPCrawlerConfig())
    async with AsyncWebCrawler(crawler_strategy=strat, config=BrowserConfig(verbose=False)) as c:
        cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=45000)
        pages = {}
        for name in ["index.html","IndexASVS.html","IndexProactiveControls.html","IndexTopTen.html","IndexMASVS.html","Glossary.html"]:
            r = await c.arun(BASE+name, config=cfg)
            pages[name] = getattr(r.markdown,"raw_markdown","") or str(r.markdown)
        r_seed = await c.arun(SEED, config=cfg)
        s_seed = set(sheet_urls(r_seed.links.get("internal")))
        s_idx  = set(sheet_urls((await c.arun(BASE+"index.html", config=cfg)).links.get("internal")))
        all_sheets = sorted(s_seed | s_idx)
        print("union sheets:", len(all_sheets))

        out = {"all_sheets": all_sheets, "indexes": {}}
        for name in ["IndexASVS.html","IndexProactiveControls.html","IndexTopTen.html","IndexMASVS.html"]:
            secs = parse_sections(pages[name])
            keep = [s for s in secs if s["sheets"]]
            out["indexes"][name] = keep
            print("")
            print("====", name, "sections with sheets:", len(keep))
            for s in keep:
                print("  " * (s["level"] - 2) + "[L" + str(s["level"]) + "] " + s["title"] + "  -> " + str(len(s["sheets"])))

        asvs = out["indexes"]["IndexASVS.html"]
        mapped = set()
        for s in asvs:
            mapped |= set(s["sheets"])
        print("")
        print("ASVS-mapped:", len(mapped), "unmapped:", len(set(all_sheets) - mapped))
        print("UNMAPPED:", sorted(u.rsplit("/",1)[-1].replace("_Cheat_Sheet.html","") for u in set(all_sheets) - mapped))
        os.makedirs("_work/owasp-cheatsheets", exist_ok=True)
        json.dump(out, open("_work/owasp-cheatsheets/taxonomy.json","w",encoding="utf-8"), indent=1)
        print("saved taxonomy.json")

asyncio.run(main())
