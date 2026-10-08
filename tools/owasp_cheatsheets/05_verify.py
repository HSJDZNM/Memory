# -*- coding: utf-8 -*-
"""校验 docs/mirrors/owasp-cheatsheets：链接完整性、编码、换行、manifest 校验和。

用法:
    python tools/owasp_cheatsheets/05_verify.py
退出码 0 表示全部通过。
"""
import hashlib
import json
import os
import re
import sys

OUT = "docs/mirrors/owasp-cheatsheets"
BT = chr(96)
LINK = re.compile(r"\[([^\]]*)\]\(\s*([^)\s]+?)(\s+\"[^\"]*\")?\s*\)")
FENCE = re.compile("(?ms)^" + BT * 3 + r".*?^" + BT * 3)
INLINE = re.compile(BT + r"[^" + BT + r"]*" + BT)
TEXT_EXT = (".md", ".json", ".txt", ".py")

problems = []

# ---- 1. 链接完整性 ----
md_count = rel_total = 0
broken = []
for root, dirs, files in os.walk(OUT):
    for fn in files:
        if not fn.endswith(".md"):
            continue
        md_count += 1
        p = os.path.join(root, fn)
        try:
            with open(p, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            # 非 UTF-8 / 读不出来的文件正是第 2 节要报的「编码异常」：这里跳过它，
            # 让第 2 节把它报出来，而不是让整个校验带 UnicodeDecodeError 崩在第 1 节。
            continue
        txt = INLINE.sub("", FENCE.sub("", text))
        for m in LINK.finditer(txt):
            t = m.group(2)
            if t.startswith(("http", "#", "mailto:")):
                continue
            rel_total += 1
            target = t.split("#")[0]
            if target.startswith("/"):
                # 根相对链接指的是**镜像根**，不是文件系统根：os.path.join(root, "/x") 会
                # 直接丢掉 root，于是它被拿去和文件系统根拼，永远判成断链（或更糟：命中了
                # 宿主机上恰好存在的同名路径）。
                tgt = os.path.normpath(os.path.join(OUT, target.lstrip("/")))
            else:
                tgt = os.path.normpath(os.path.join(root, target))
            if not os.path.exists(tgt):
                broken.append((os.path.relpath(p, OUT), t))
if broken:
    problems.append("断链 " + str(len(broken)) + " 条")
    for rel, t in broken[:20]:
        print("   BROKEN " + rel + " -> " + t)

# ---- 2. 编码 / 换行 / 结尾换行 ----
bad_enc, bad_eol, bad_tail = [], [], []
text_files = 0
for root, dirs, files in os.walk(OUT):
    for fn in files:
        if not fn.lower().endswith(TEXT_EXT):
            continue
        text_files += 1
        p = os.path.join(root, fn)
        rel = os.path.relpath(p, OUT)
        raw = open(p, "rb").read()
        if raw.startswith(b"\xef\xbb\xbf"):
            bad_enc.append(rel)
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            bad_enc.append(rel + "(非 UTF-8)")
            continue
        if b"\r" in raw:
            bad_eol.append(rel)
        if not txt.endswith("\n") or txt.endswith("\n\n"):
            bad_tail.append(rel)
if bad_enc:
    problems.append("编码异常 " + str(len(bad_enc)) + " 个: " + ", ".join(bad_enc[:10]))
if bad_eol:
    problems.append("非 LF 换行 " + str(len(bad_eol)) + " 个: " + ", ".join(bad_eol[:10]))
if bad_tail:
    problems.append("结尾换行异常 " + str(len(bad_tail)) + " 个: " + ", ".join(bad_tail[:10]))

# ---- 3. manifest 校验和 ----
# 读不出来 / 形状不对都进问题清单：直接 man["pages"] 取值会让畸形 manifest 变成一段栈回溯，
# 而这个脚本的全部价值就是把"哪里不对"逐条说出来。
man = None
manifest_path = os.path.join(OUT, "manifest.json")
try:
    with open(manifest_path, encoding="utf-8") as handle:
        man = json.load(handle)
except (OSError, ValueError) as error:
    problems.append("manifest.json 读不出来（" + type(error).__name__ + ": " + str(error) + "）")
if man is not None and (not isinstance(man, dict) or not isinstance(man.get("pages"), list)):
    problems.append("manifest.json 形状不对：顶层必须是对象且 pages 是数组（得到 "
                    + type(man).__name__ + "）")
    man = None
mismatch = []
if man is not None:
    for index, pg in enumerate(man["pages"]):
        if not isinstance(pg, dict) or not isinstance(pg.get("local_path"), str):
            mismatch.append(("pages[" + str(index) + "]", "条目形状不对（缺 local_path）"))
            continue
        p = os.path.join(OUT, pg["local_path"])
        if not os.path.exists(p):
            mismatch.append((pg["local_path"], "文件缺失"))
            continue
        if os.path.getsize(p) != pg.get("bytes"):
            mismatch.append((pg["local_path"], "字节数不符"))
        elif hashlib.sha256(open(p, "rb").read()).hexdigest() != pg.get("sha256"):
            mismatch.append((pg["local_path"], "sha256 不符"))
if mismatch:
    problems.append("manifest 校验失败 " + str(len(mismatch)) + " 项")
    for a, b in mismatch[:10]:
        print("   MANIFEST " + a + " " + b)

# ---- 4. 收尾约束 ----
for fn in ["README.md", "STRUCTURE.md", "manifest.json", "LICENSE.txt"]:
    if not os.path.exists(os.path.join(OUT, fn)):
        problems.append("缺少 " + fn)

print("")
print("Markdown 文件: " + str(md_count) + "  |  相对链接: " + str(rel_total)
      + "  |  文本文件: " + str(text_files))
if man is None:
    print("manifest 页面: 读不出来（见上面的问题清单）")
else:
    print("manifest 页面: " + str(len(man["pages"]))
          + "  |  排除: " + str(man.get("pages_excluded", "未声明"))
          + "  |  候选: " + str(man.get("pages_candidate", "未声明")))
if problems:
    print("")
    print("FAIL:")
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print("")
print("PASS: 链接、编码、换行、manifest 校验和全部通过")
