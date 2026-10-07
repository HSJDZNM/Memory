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

def crawl_failed(r):
    """失败原因原文；没有就写"无 error_message"，不猜。"""
    return getattr(r, "error_message", "") or "无 error_message"

def markdown_of(r, name):
    """一次抓取的正文。抓取失败 / 正文取不到一律显式报错：

    失败的 crawl 会给出空正文（旧写法 `str(r.markdown)` 还会把它变成字符串 "None"），
    parse_sections 于是返回 0 个 section，而流程照旧写出一份 indexes 全空、UNMAPPED 一长串的
    taxonomy.json——"没抓到"被读成了"没有内容"。
    """
    if not getattr(r, "success", False):
        raise RuntimeError(name + " 抓取失败：" + crawl_failed(r))
    markdown = getattr(r, "markdown", None)
    raw = getattr(markdown, "raw_markdown", "") if markdown is not None else ""
    if not raw:
        raise RuntimeError(name + " 抓取成功但正文为空（markdown 没有 raw_markdown）")
    return raw

def internal_links(r, name):
    """站内链接：抓取失败显式报错；`links` 为 None 时按"没有链接"处理，不 AttributeError。"""

    if not getattr(r, "success", False):
        raise RuntimeError(name + " 抓取失败：" + crawl_failed(r))
    return (getattr(r, "links", None) or {}).get("internal", []) or []

async def main():
    strat = AsyncHTTPCrawlerStrategy(browser_config=HTTPCrawlerConfig())
    async with AsyncWebCrawler(crawler_strategy=strat, config=BrowserConfig(verbose=False)) as c:
        cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=45000)
        pages = {}
        for name in ["index.html","IndexASVS.html","IndexProactiveControls.html","IndexTopTen.html","IndexMASVS.html","Glossary.html"]:
            r = await c.arun(BASE+name, config=cfg)
            pages[name] = markdown_of(r, name)
        r_seed = await c.arun(SEED, config=cfg)
        s_seed = set(sheet_urls(internal_links(r_seed, "seed")))
        r_index = await c.arun(BASE+"index.html", config=cfg)
        s_idx  = set(sheet_urls(internal_links(r_index, "index.html")))
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

if __name__ == "__main__":
    asyncio.run(main())
