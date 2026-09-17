# -*- coding: utf-8 -*-
"""校验 docs/owasp-cheatsheets：链接完整性、编码、换行、manifest 校验和。

用法:
    python tools/owasp_cheatsheets/05_verify.py
退出码 0 表示全部通过。
"""
import hashlib
import json
import os
import re
import sys

OUT = "docs/owasp-cheatsheets"
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
        txt = INLINE.sub("", FENCE.sub("", open(p, encoding="utf-8").read()))
        for m in LINK.finditer(txt):
            t = m.group(2)
            if t.startswith(("http", "#", "mailto:")):
                continue
            rel_total += 1
            tgt = os.path.normpath(os.path.join(root, t.split("#")[0]))
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
man = json.load(open(os.path.join(OUT, "manifest.json"), encoding="utf-8"))
mismatch = []
for pg in man["pages"]:
    p = os.path.join(OUT, pg["local_path"])
    if not os.path.exists(p):
        mismatch.append((pg["local_path"], "文件缺失"))
        continue
    if os.path.getsize(p) != pg["bytes"]:
        mismatch.append((pg["local_path"], "字节数不符"))
    elif hashlib.sha256(open(p, "rb").read()).hexdigest() != pg["sha256"]:
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
print("manifest 页面: " + str(len(man["pages"])) + "  |  排除: " + str(man["pages_excluded"])
      + "  |  候选: " + str(man["pages_candidate"]))
if problems:
    print("")
    print("FAIL:")
    for p in problems:
        print("  - " + p)
    sys.exit(1)
print("")
print("PASS: 链接、编码、换行、manifest 校验和全部通过")
