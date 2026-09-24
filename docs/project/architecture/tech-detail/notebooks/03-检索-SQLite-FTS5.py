"""检索：SQLite FTS5：tech-detail 讲解 notebook 的纯 Python 版本。

由 docs/project/architecture/tech-detail/notebooks/build_notebooks.py 生成，内容与同名的
.ipynb 逐字相同（那份里每段代码也是一个单元）。直接运行本文件即可复现全部输出：

    python docs/project/architecture/tech-detail/notebooks/03-检索-SQLite-FTS5.py

内容改动请修改 nb_cells/ 下对应的内容源后重新生成，不要直接编辑本文件。
"""

# ----------------------------------------------------------------------------
# # 03 检索：SQLite FTS5
#
# 这份 notebook 配合同名图 `03-检索-SQLite-FTS5.drawio`。图上有九个步骤，从"摄取清单"一路走到"三个显式状态"，
# 下面按同样的顺序把每一步**真的跑一遍**：语料用仓库里真实的那份清单，索引库建在本 notebook 自己的临时目录里。
#
# 读完应该能回答四件事：
#
# 1. 一条查询从原文走到 SQL，中间被改造成了什么？为什么"原始文本拼不进 SQL"？
# 2. 谁能看到哪些文档？权限是从哪来的，查询文本能不能把它撑大？
# 3. "没搜到"、"没权限"、"检索坏了"为什么必须是三个不同的状态？
# 4. 检索坏了的时候，平台会不会顺手拿"模型记忆里的规范"顶上？
#
# **预备知识**：会读 Python 函数调用就够了。本文只用仓库自带的检索层（标准库 `sqlite3`，不需要装任何东西）。
#
# **一个约定**：所有写操作（索引库、假的镜像仓库）都落在 `.tmp/tech-detail/03/` 下，跑完随手可删；
# 仓库里的 `knowledge/corpus.yaml` 与 `docs/mirrors/` 下的镜像只读不动。
# ----------------------------------------------------------------------------

# 先找到仓库根目录：notebook 可能从仓库根启动，也可能从本目录启动，两种都要能跑。
import hashlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def find_repo_root(start):
    """往上找：同时有 pyproject.toml 与 src/policy/ 的那一层就是仓库根。"""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "policy").is_dir():
            return candidate
    raise SystemExit("没有找到仓库根目录（需要 pyproject.toml 与 src/policy/）")


REPO_ROOT = find_repo_root(Path.cwd())
for extra in (REPO_ROOT / "src", REPO_ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

TEMP = REPO_ROOT / ".tmp" / "tech-detail" / "03"
# 每次运行都从空目录开始：本 notebook 会被"仓库根"与"本目录"各跑一遍，残留会让第二遍结果不一样。
shutil.rmtree(TEMP, ignore_errors=True)
TEMP.mkdir(parents=True, exist_ok=True)

TECH_DETAIL = REPO_ROOT / "docs" / "project" / "architecture" / "tech-detail"
print("仓库根目录:", REPO_ROOT.name)
print("当前工作目录:", Path.cwd().relative_to(REPO_ROOT).as_posix() or ".")
print("讲解目录:", (TECH_DETAIL / "notebooks").relative_to(REPO_ROOT).as_posix())
print("临时目录:", TEMP.relative_to(REPO_ROOT).as_posix())
print("Python:", sys.version.split()[0])

# 表格对齐用的小工具：中文（全角）字符在等宽字体里占 2 列，而 f"{文本:<10}"
# 数的是"字符个数"——中英混排时列会被挤歪。按显示宽度补空格才是对的。
import unicodedata


def display_width(text):
    """文本在等宽字体里占多少列：全角/宽字符算 2 列，其余算 1 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(text))


def pad(text, width, align="left"):
    """按显示宽度把文本补齐到 width 列，让每一列都从同一个位置开始。"""
    text = str(text)
    blanks = " " * max(0, width - display_width(text))
    if align == "right":
        return blanks + text
    if align == "center":
        left = len(blanks) // 2
        return blanks[:left] + text + blanks[left:]
    return text + blanks

# ----------------------------------------------------------------------------
# ## 1. 摄取清单：语料是数据，哈希是门禁（图上的 r1 → r2）
#
# `knowledge/corpus.yaml` 是"哪些文档值得告诉 Agent"的**数据**：数据集名、镜像目录、许可、
# 层级（tier）、可见性（visibility）、条目清单全写在那里，代码里没有硬编码的路径判断。
#
# 清单只声明"我想要哪些页"，真正的来源与哈希在**镜像自己的 `manifest.json`** 里。校验分三层：
#
# 1. 文件在不在；
# 2. 本地文件内容的 sha256 与 manifest 登记的 sha256 是否一致（**漂移**）；
# 3. 字节数是否一致、清单声明的许可文件是否存在。
#
# 漂移不是警告而是**门禁**：不一致会写进 document 行、写进索引 run 报告，并让
# `python -m retrieval.cli verify` 退出 1（CI 里直接拦下）。下面先用仓库真实清单跑一遍，
# 再在临时目录里造一个小镜像、故意改掉一个字节，看 `verify` 的退出码怎么变。
# ----------------------------------------------------------------------------

# ---- 1) 真实清单：仓库里的 knowledge/corpus.yaml（只读） ----
from retrieval.corpus import load_corpus

CORPUS = REPO_ROOT / "knowledge" / "corpus.yaml"
started = time.perf_counter()
corpus = load_corpus(CORPUS, repo_root=REPO_ROOT)
report = corpus.verification

print(pad("数据集", 26) + pad("tier", 10) + pad("visibility", 12) + pad("条目", 6) + "许可（自由文本放最后一列）")
print("-" * 100)
for dataset in corpus.manifest.datasets:
    print(
        pad(dataset.name, 26)
        + pad(dataset.tier.value, 10)
        + pad(dataset.visibility.value, 12)
        + pad(len(dataset.entries), 6)
        + dataset.license
    )
print()
print(
    "清单版本", report.corpus_version,
    "| 数据集", report.datasets,
    "| 条目", report.entries,
    "| 完全一致", report.ok,
    "| 加载加校验 %.2fs" % (time.perf_counter() - started),
)

# 这几条断言就是"清单加载不许静默"的可执行版本。
assert report.ok, [issue.model_dump() for issue in report.issues]
assert report.entries == sum(len(dataset.entries) for dataset in corpus.manifest.datasets)
assert all(entry.source_url and entry.license for entry in corpus.entries)
hashed = [entry for entry in corpus.entries if entry.manifest_sha256]
assert len(hashed) == len(corpus.entries), "每个条目都必须能从 manifest 拿到 sha256"
sample = hashed[0]
print()
print("样例条目:", pad(sample.dataset, 24) + sample.source_path)
print("      url:", sample.source_url)
print("      manifest sha256:", (sample.manifest_sha256 or "")[:28] + "…")

# ---- 2) 造一个小镜像，然后故意改掉一个字节，看 verify 的退出码 ----
FAKE_ROOT = TEMP / "fake-repo"
MIRROR = FAKE_ROOT / "docs" / "mirrors" / "demo-mirror"
MIRROR.mkdir(parents=True, exist_ok=True)
PAGE = MIRROR / "guide.md"
PAGE.write_text("# 指南\n\n评审要小步走。\n", encoding="utf-8", newline="\n")
digest = "sha256:" + hashlib.sha256(PAGE.read_bytes()).hexdigest()
(MIRROR / "manifest.json").write_text(
    json.dumps(
        {
            "fetched_at": "2026-01-01T00:00:00Z",
            "pages": [
                {
                    "local_path": "guide.md",
                    "source_url": "https://example.invalid/review-guide",
                    "title": "示例指南",
                    "sha256": digest,
                    "bytes": PAGE.stat().st_size,
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
    newline="\n",
)
(FAKE_ROOT / "knowledge").mkdir(parents=True, exist_ok=True)
FAKE_CORPUS = FAKE_ROOT / "knowledge" / "corpus.yaml"
FAKE_CORPUS.write_text(
    "version: 1\n"
    "policy:\n"
    "  top_k: 3\n"
    "datasets:\n"
    "  - name: demo\n"
    "    title: 演示数据集\n"
    "    mirror: docs/mirrors/demo-mirror\n"
    "    license: CC BY 4.0\n"
    "    tier: guidance\n"
    "    visibility: public\n"
    "    entries:\n"
    "      - guide.md\n",
    encoding="utf-8",
    newline="\n",
)


def cli_verify():
    """跑真正的 CLI（子进程）：退出码就是 CI 认的那一个。"""

    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"))
    return subprocess.run(
        [
            sys.executable, "-m", "retrieval.cli", "verify",
            "--root", str(FAKE_ROOT), "--corpus", str(FAKE_CORPUS),
        ],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )


clean = load_corpus(FAKE_CORPUS, repo_root=FAKE_ROOT)
clean_proc = cli_verify()
print()
print("镜像没被动过: 清单一致 =", clean.verification.ok, "| CLI 退出码 =", clean_proc.returncode)
print("  " + clean_proc.stdout.strip())

PAGE.write_text("# 指南\n\n评审要小步走。有人偷偷改了镜像。\n", encoding="utf-8", newline="\n")
drifted = load_corpus(FAKE_CORPUS, repo_root=FAKE_ROOT)
drift_proc = cli_verify()
kinds = {issue.kind for issue in drifted.verification.issues}
print()
print("镜像被改过: 清单一致 =", drifted.verification.ok, "| 问题类型 =", sorted(kinds),
      "| CLI 退出码 =", drift_proc.returncode)
for line in drift_proc.stdout.strip().splitlines():
    print("  " + line[:130])
print()
print("注意：CLI 的 verify 会在 load_corpus 已经校验过一次的基础上再校验一次，")
print("      所以同一条问题在上面列了两遍——退出码不受影响（依然是 1）；")
print("      而本 notebook 自己报告的问题数来自单次校验，那才是真实条数。")

assert clean.verification.ok and clean_proc.returncode == 0
assert not drifted.verification.ok and drift_proc.returncode == 1
assert kinds == {"hash_mismatch", "size_mismatch"}, kinds
assert len(drifted.verification.drift) == 1
assert "hash_mismatch" in drift_proc.stdout
print()
print("结论：镜像内容一改，sha256 立刻对不上，verify 退出 1 —— 漂移不会静默。")

# ----------------------------------------------------------------------------
# ## 2. 分块与索引库：一个 chunk 一个稳定身份（图上的 r3 → r4）
#
# **分块**按标题层级走：标题行本身不进正文，只进 `heading_path` / `heading_anchor`（用于溯源），
# 正文按预算打包，**原文一个字都不改写**。这一条是可断言的：把各章节正文拼起来，
# 与所有 chunk 的文本拼起来"去掉空白后"必须逐字相同。
#
# **索引库**是构建产物（真仓库里在 `.tmp/retrieval/index.sqlite3`，随时可重建），三张关键表：
#
# | 表 | 存什么 |
# | --- | --- |
# | `documents` | 来源路径、URL、许可、tier、visibility、内容哈希、manifest 哈希 |
# | `chunks` | 正文、`text_hash`、标题路径、字符数；被隔离（quarantined）的片段不参与检索 |
# | `chunks_fts` | FTS5 虚表：`chunk_id` + 正文 + 标题路径；中文按**逐字切分**（"代码评审"与"代 码 评 审"互相命中） |
#
# `chunk_id` 由 `document_id` + 章节锚点 + 片号算出来，所以内容没变时重复摄取**一行都不重写**——
# 下面会连着摄取两次，第二次的"未变"计数就是幂等的可验证证据。
# ----------------------------------------------------------------------------

# ---- 3) 分块：标题层级 + 预算打包，正文不许被改写 ----
from retrieval.chunker import blocks_are_preserved, chunk_document, find_sections, split_front_matter
from retrieval.models import (
    CorpusPolicy,
    DocumentRecord,
    Tier,
    Visibility,
    document_id_for,
    sha256_text,
)

FENCE = chr(96) * 3
DOC = (
    "# 评审指南\n\n前言：这份文档只用来演示分块与索引。\n\n"
    "## 小步提交\n\n一次变更只做一件事。评审者应在一天内给出反馈。\n\n"
    "## 权限\n\n" + FENCE + "python\n"
    "def can_review(user):\n    return user.has('repo.read')\n" + FENCE + "\n\n"
    "## 安全\n\n不要把密钥写进仓库。\n"
)

front, body = split_front_matter(DOC)
sections = find_sections(body)
body_text = "".join(section.body for section in sections)
DOCUMENT_ID = document_id_for("demo-zh", "guide.md")
front_matter, drafts = chunk_document(DOC, document_id=DOCUMENT_ID, max_chars=120, hard_max_chars=800)

print(pad("#", 4) + pad("heading_anchor", 28) + pad("kind", 8) + pad("字符", 6) + "text_hash")
print("-" * 76)
for draft in drafts:
    print(
        pad(draft.ordinal, 4)
        + pad(draft.heading_anchor, 28)
        + pad(draft.kind.value, 8)
        + pad(draft.char_count, 6)
        + draft.text_hash[:20] + "…"
    )
print()
print("章节数", len(sections), "| chunk 数", len(drafts),
      "| 正文逐字保留", blocks_are_preserved(body_text, [draft.text for draft in drafts]))

assert not front.removed, "本文档没有 front matter，不该被剔掉"
assert [draft.heading_anchor for draft in drafts] == [section.anchor for section in sections]
assert blocks_are_preserved(body_text, [draft.text for draft in drafts])
assert all(draft.text_hash == sha256_text(draft.text) for draft in drafts)
assert all(draft.char_count == len(draft.text) for draft in drafts)
assert all(not draft.text.startswith("#") for draft in drafts), "标题行只进 heading_path，不进正文"

# ---- 4) FTS5 索引库：只写到本 notebook 自己的临时目录 ----
from retrieval.store import ChunkStore

DB = TEMP / "index.sqlite3"
policy = CorpusPolicy(top_k=3, max_query_chars=200, max_query_terms=24)
store = ChunkStore(DB)
store.upsert_document(
    DocumentRecord(
        document_id=DOCUMENT_ID,
        dataset="demo-zh",
        source_path="guide.md",
        source_url="https://example.invalid/review-guide",
        title="示例评审指南",
        license="CC BY 4.0",
        license_source=None,
        tier=Tier.GUIDANCE,
        visibility=Visibility.PUBLIC,
        language="zh",
        content_hash=sha256_text(DOC),
        manifest_hash=None,
        byte_size=len(DOC.encode("utf-8")),
        mirror_revision="2026-01-01T00:00:00Z",
        ingested_at="2026-01-01T00:00:00Z",
    ),
    front_matter=(),
)
change = store.replace_chunks(DOCUMENT_ID, drafts)
stats = store.stats()

print()
print("索引库:", DB.relative_to(REPO_ROOT).as_posix())
print(pad("表", 14) + "行数")
print("-" * 32)
print(pad("documents", 14) + str(stats.documents))
print(pad("chunks", 14) + str(stats.chunks))
print(pad("chunks_fts", 14) + str(store.fts_row_count()))
print()
print("index_version:", store.index_version[:26] + "…", "| generation:", store.generation)
print("本次写入: 新建", len(change.created), "更新", len(change.updated), "未变", len(change.unchanged))

assert stats.documents == 1 and stats.chunks == len(drafts)
assert store.fts_row_count() == stats.chunks
assert len(change.created) == len(drafts) and not change.updated

again = store.replace_chunks(DOCUMENT_ID, drafts)
assert not again.created and not again.updated and len(again.unchanged) == len(drafts)
print("再摄取一次: 新建", len(again.created), "更新", len(again.updated), "未变", len(again.unchanged),
      "→ 内容没变就一行都不重写")

# ----------------------------------------------------------------------------
# ## 3. 查询规范化：先变成受控词项，再变成表达式（图上的 r5 → r6）
#
# 这是整张图**最安全的一步**。原始查询文本是**数据**：它永远不会出现在 SQL 字符串里，
# 也不会出现在 FTS5 表达式的语法位置。中间经历三段：
#
# 1. **规范化**：Unicode NFKC、剔除控制字符、空白折叠、按字符上限截断（超长显式记 `truncated`）；
# 2. **分词**：只保留"字母 / 数字 / 下划线 / 中日韩文字"连续段；单字符英文词与纯数字被丢掉（噪声大）；
# 3. **成表达式**：每个词项都被双引号包起来，只由 `OR` 连接——表达式里**再没有别的 FTS 语法**。
#
# 所以 `NEAR(...)`、`*`、`:`、`-`、引号、括号这些 FTS5 操作符在分词阶段就消失了；
# 就算某个词项里混进双引号，也会被加倍转义（`a"b` → `"a""b"`），关不掉引号。
# 最后表达式作为 `MATCH ?` 的**参数**传给 SQLite——下面会直接读源码核对这一点。
#
# 顺带看清一个风险：`; DROP TABLE chunks --` 这串文本会退化成几个普通词，
# 因为每个词都被单独引号包着，"drop table"这样的**短语结构**根本不存在。
# ----------------------------------------------------------------------------

# ---- 5) 原始文本 → 受控词项 → FTS 表达式 ----
from retrieval.query import fts_expression, fts_phrase, normalize_query_text, tokenize

RAW = '小步提交 NEAR("repo"*) OR secret:* ; DROP TABLE chunks -- 注入尝试'

normalized, truncated = normalize_query_text(RAW, max_chars=policy.max_query_chars)
terms = tokenize(normalized)
expression = fts_expression(terms)

print("原始文本  :", RAW)
print("规范化后  :", normalized)
print("受控词项  :", terms)
print("FTS 表达式:", expression)
print()

# FTS5 的语法字符一个都不许活到表达式里。
for operator in ("(", ")", "*", ":", ";", "^", "-"):
    assert operator not in expression, operator
assert "NEAR" not in expression, "NEAR 操作符必须已经被丢掉"
assert expression.count('"') == 2 * len(expression.split(" OR "))
print("表达式里只剩被双引号包住的词项与 OR；NEAR / 括号 / 星号 / 冒号 / 分号全部消失。")

# 注入字符串退化成普通词：不可能形成短语，更不可能形成第二条语句。
assert "drop table" not in expression
assert '"drop" OR "table"' in expression
assert RAW not in expression

# 词项里的双引号会被加倍，永远关不上引号。
assert fts_phrase('a"b') == '"a""b"'

# 上限：超长查询被截断并显式记 truncated，而不是整段送去匹配。
long_text = "评审 " * 300
clipped, was_clipped = normalize_query_text(long_text, max_chars=policy.max_query_chars)
assert was_clipped and len(clipped) <= policy.max_query_chars
print("超长查询:", len(long_text), "字符 →", len(clipped), "字符，truncated =", was_clipped)

# 控制字符被抹平；单字符英文词与纯数字被丢弃。
control_text = "a" + chr(0) + "b" + chr(7)
assert normalize_query_text(control_text, max_chars=50)[0] == "a b"
assert tokenize("a 12 bb 评审") == ("bb", "评审")
print("控制字符被中和；单字符英文词与纯数字被丢弃。")
print()

# 直接读源码核对"表达式是参数，不是拼进 SQL 的字符串"。
search_source = inspect.getsource(ChunkStore.search)
sql_block = search_source.partition("sql = (")[2]
assert "chunks_fts MATCH ?" in search_source
assert "expression" not in sql_block, "表达式变量不得出现在 SQL 拼接块里"
print("源码核对：ChunkStore.search 的 SQL 里写的是 chunks_fts MATCH ?，")
print("词项通过 parameters 传参；SQL 拼接块里没有出现 expression 变量。")

# ----------------------------------------------------------------------------
# ## 4. 参数化查询、权限过滤、结果带来源（图上的 r6 → r7 → r8）
#
# SQL 的形状是固定的：`chunks_fts MATCH ?` 加一串**参数化**的过滤条件
# （`d.dataset IN (?,?,…)`、`d.visibility = ?`、`d.tier IN (…)`）。它们是 `?`，不是字符串拼接。
#
# **权限只来自显式 `AccessScope`**，不来自查询文本、不来自文件路径：
#
# - 一个数据集都没授予 → 直接 `access_denied`，不是"没有结果"；
# - 授予了 A、查询里却写着 B → 取交集后为空，什么也拿不到；
# - `visibility: restricted` 的数据集必须由调用方**显式**打开 `allow_restricted`，默认看不见；
# - 相似度分数（`bm25`）只用于**内部排序**，不是授权信号——所以检索结果里根本没有"允许 / 拒绝"这类字段。
#
# 每个返回项都带齐：来源路径、URL、许可、层级、文本哈希。少任何一样，引用就没法追溯。
# ----------------------------------------------------------------------------

# ---- 6) 检索：参数化查询 + 权限过滤 + 结果带来源 ----
from retrieval.models import AccessScope, RetrievalQuery, RetrievalResult, RetrievalStatus, UnavailableReason
from retrieval.retriever import FtsRetriever

retriever = FtsRetriever(store, policy=policy)
scope = AccessScope(subject="agent:demo", datasets=frozenset({"demo-zh"}))
result = retriever.retrieve(RetrievalQuery(text="小步提交", limit=3, request_id="nb03-q1"), scope)

print("状态:", result.status.value, "| 受控词项:", result.plan.terms,
      "| index_version:", result.index_version[:20] + "…")
print(pad("排名", 6) + pad("来源路径", 14) + pad("许可", 12) + pad("tier", 10) + "text_hash")
print("-" * 82)
for hit in result.results:
    print(
        pad(hit.rank, 6) + pad(hit.source_path, 14) + pad(hit.license, 12)
        + pad(hit.tier.value, 10) + hit.text_hash[:22] + "…"
    )
    print("      url: " + hit.source_url)
print()
print("相似度分数只用于排序（这里的值是", round(result.results[0].score, 4), "），它不进任何授权判断。")

assert result.status is RetrievalStatus.OK and len(result.results) == 1
assert all(hit.source_path and hit.source_url and hit.license and hit.text_hash for hit in result.results)
assert [hit.rank for hit in result.results] == list(range(1, len(result.results) + 1))
# 检索结果里没有任何"授权"字段：分数不可能被当成放行依据。
auth_fields = [
    name for name in RetrievalResult.model_fields
    if "author" in name or "grant" in name or name.startswith("allow")
]
assert not auth_fields, auth_fields

# 查询文本不能扩权：数据集过滤条件只认 AccessScope，不认文本里出现的名字。
widened = retriever.retrieve(RetrievalQuery(text="小步提交 demo-internal", limit=3), scope)
assert widened.plan.filters.scope_datasets == ("demo-zh",)
assert widened.plan.filters.datasets == ()
assert all(hit.dataset == "demo-zh" for hit in widened.results)
print()
print("文本里写 demo-internal 也没用：过滤条件仍是 AccessScope 里的", widened.plan.filters.scope_datasets)

# 一个数据集都没授予 → access_denied（不是"没有结果"）。
denied = retriever.retrieve(
    RetrievalQuery(text="小步提交", limit=3),
    AccessScope(subject="agent:demo", datasets=frozenset()),
)
assert denied.status is RetrievalStatus.EMPTY
assert denied.reason is UnavailableReason.ACCESS_DENIED
assert denied.results == ()
print("未授予任何数据集:", denied.status.value, "/", denied.reason.value, "|", denied.detail)

# 只授予 A、却去请求 B：过滤在参数化 SQL 里取交集，结果同样是"没有命中"。
# 代码里的 access_denied 专门留给"一个数据集都没授予"这一种情形（见 retriever.retrieve）。
elsewhere = retriever.retrieve(
    RetrievalQuery(text="小步提交", datasets=("demo-internal",), limit=3), scope
)
print("只授予 demo-zh、却请求 demo-internal:", elsewhere.status.value, "/",
      None if elsewhere.reason is None else elsewhere.reason.value,
      "| 条数 =", len(elsewhere.results))
assert elsewhere.results == ()
assert elsewhere.status is RetrievalStatus.EMPTY

# restricted 数据集：默认看不见，必须显式打开 allow_restricted。
RESTRICTED_TEXT = "# 内部规范\n\n仅限内部评审者阅读的补充条款。\n"
RESTRICTED_ID = document_id_for("demo-internal", "secret.md")
store.upsert_document(
    DocumentRecord(
        document_id=RESTRICTED_ID,
        dataset="demo-internal",
        source_path="secret.md",
        source_url="https://example.invalid/internal",
        title="内部补充条款",
        license="内部资料",
        license_source=None,
        tier=Tier.POLICY,
        visibility=Visibility.RESTRICTED,
        language="zh",
        content_hash=sha256_text(RESTRICTED_TEXT),
        manifest_hash=None,
        byte_size=len(RESTRICTED_TEXT.encode("utf-8")),
        mirror_revision="2026-01-01T00:00:00Z",
        ingested_at="2026-01-01T00:00:00Z",
    ),
    front_matter=(),
)
_, restricted_drafts = chunk_document(
    RESTRICTED_TEXT, document_id=RESTRICTED_ID, max_chars=200, hard_max_chars=800
)
store.replace_chunks(RESTRICTED_ID, restricted_drafts)

granted = frozenset({"demo-zh", "demo-internal"})
public_only = retriever.retrieve(
    RetrievalQuery(text="补充条款", limit=5),
    AccessScope(subject="agent:demo", datasets=granted),
)
with_restricted = retriever.retrieve(
    RetrievalQuery(text="补充条款", limit=5),
    AccessScope(subject="agent:demo", datasets=granted, allow_restricted=True),
)
print()
print("restricted 可见性: public-only →", len(public_only.results), "条 | allow_restricted=True →",
      len(with_restricted.results), "条")

assert public_only.results == ()
assert public_only.reason is UnavailableReason.NO_RESULTS
assert len(with_restricted.results) == 1
assert with_restricted.results[0].visibility is Visibility.RESTRICTED

# ----------------------------------------------------------------------------
# ## 5. 三个显式状态，而且不可用时绝不"脑补"（图上的 r9 与红色节点）
#
# 检索只有这几种结局，每一种都有**名字**，不允许糊成一团：
#
# | 状态 | 什么时候 | 调用方该做什么 |
# | --- | --- | --- |
# | `ok` | 有命中 | 正常引用，带来源与哈希 |
# | `empty` + `no_results` | 查询合法，就是没命中 | 承认"这份规范里没写"，不要编 |
# | `empty` + `access_denied` | 一个数据集都没授予 | 去找授权，不要试着绕过 |
# | `unavailable` + `index_missing` / `retrieval_failed` | 索引缺失、损坏、执行失败 | 只输出 `knowledge_unavailable` |
#
# 最后一行是这张图的红色节点：**检索不可用时不回退到"模型记忆里的规范"**。
# 在组装出来的 Engineering Context 里，这条规矩有看得见的形态——不可用时渲染出的文本
# **根本没有参考区边界标记**（`<<<ENGINEERING-REFERENCE-BEGIN>>>`），只有一句"知识不可用"，
# 并明确写着"不得用模型记忆里的规范代替来源，也不得据此作出授权判断"。
# 有命中时才会出现带引用的参考区。
# ----------------------------------------------------------------------------

# ---- 7) 三个显式状态 + 不可用时只输出 knowledge_unavailable ----
from retrieval.context import (
    REFERENCE_BEGIN,
    REFERENCE_END,
    ContextBuilder,
    render_context,
)
from retrieval.models import ContextStatus

cases = (
    ("有命中", RetrievalQuery(text="小步提交", limit=3),
     AccessScope(subject="agent:demo", datasets=frozenset({"demo-zh"}))),
    ("无结果", RetrievalQuery(text="完全不存在的词xyzzy", limit=3),
     AccessScope(subject="agent:demo", datasets=frozenset({"demo-zh"}))),
    ("无权限", RetrievalQuery(text="小步提交", limit=3),
     AccessScope(subject="agent:demo", datasets=frozenset())),
)
print(pad("情形", 12) + pad("status", 14) + pad("reason", 16) + "结果条数")
print("-" * 60)
for label, query, item_scope in cases:
    outcome = retriever.retrieve(query, item_scope)
    print(
        pad(label, 12) + pad(outcome.status.value, 14)
        + pad("" if outcome.reason is None else outcome.reason.value, 16)
        + str(len(outcome.results))
    )

# 第三种：索引库根本用不了。这里用一个"没有建过表"的空库复现（真实场景是索引还没建或已损坏）。
empty_store = ChunkStore(TEMP / "empty.sqlite3", initialize=False)
unavailable = FtsRetriever(empty_store, policy=policy).retrieve(
    RetrievalQuery(text="小步提交", limit=3), scope
)
print(pad("检索不可用", 12) + pad(unavailable.status.value, 14)
      + pad(unavailable.reason.value, 16) + str(len(unavailable.results)))
print("      detail:", (unavailable.detail or "")[:70])

assert unavailable.status is RetrievalStatus.UNAVAILABLE
assert unavailable.reason is UnavailableReason.INDEX_MISSING
assert unavailable.results == ()

# 不可用时只输出 knowledge_unavailable：没有参考区、没有编造的规范。
builder = ContextBuilder.from_policy(policy)
context = builder.build(retrieval=unavailable, query="小步提交", request_id="nb03-req-1")
rendered = render_context(context)
print()
print(rendered.strip())

assert context.status is ContextStatus.KNOWLEDGE_UNAVAILABLE
assert context.reason is UnavailableReason.INDEX_MISSING
assert context.snippets == ()
assert REFERENCE_BEGIN not in rendered and REFERENCE_END not in rendered
assert "知识不可用" in rendered

# 对照：有命中时才有带来源的参考区。
ok_context = builder.build(retrieval=result, query="小步提交", request_id="nb03-req-2")
ok_rendered = render_context(ok_context)
print()
print("有命中时的引用:", [item.citation_id for item in ok_context.snippets],
      "| 状态:", ok_context.status.value,
      "| 用了", ok_context.used_chars, "/", ok_context.budget_chars, "字符")

assert ok_context.status is ContextStatus.OK
assert REFERENCE_BEGIN in ok_rendered and REFERENCE_END in ok_rendered
assert all(item.source_path and item.source_url and item.license and item.text_hash
           for item in ok_context.snippets)

store.close()
empty_store.close()
print()
print("索引库与空库都已关闭；本次全部产物都在", TEMP.relative_to(REPO_ROOT).as_posix())

# ----------------------------------------------------------------------------
# ## 小结
#
# - **语料是数据，哈希是门禁**：`knowledge/corpus.yaml` + 镜像 `manifest.json` 的 sha256 一改就对不上，
#   `python -m retrieval.cli verify` 退出 1（上面真的跑出了 0 → 1 的变化）；
# - **原始查询文本永不拼进 SQL / FTS 表达式**：先规范化成受控词项，表达式里只剩
#   `"词项" OR "词项"`，`NEAR` / `*` / `:` / `;` 全部消失，最后作为 `MATCH ?` 的参数传参
#   （源码里 `chunks_fts MATCH ?` 与 SQL 拼接块无 `expression` 变量，两处都做了断言）；
# - **权限只来自显式 `AccessScope`**：查询文本写多少个数据集名都不会变成过滤条件；
#   `restricted` 数据必须显式打开 `allow_restricted`；检索结果里没有任何授权字段，
#   相似度分数只用于排序；
# - **状态各有名字**：`no_results` / `access_denied` / `index_missing`；
#   不可用时 Context 只输出 `knowledge_unavailable`，连参考区边界标记都不出现——
#   绝不回退到"模型记忆里的规范"；
# - **索引库是构建产物**：`chunk_id` 与 `text_hash` 从稳定输入算出，重复摄取不重写一行，
#   随时可以删掉重建（本 notebook 就建在自己的 `.tmp/tech-detail/03/` 下）。
#
# 接着往下走：`04-受控执行.ipynb`（检索到的规范要变成动作时，谁在管副作用）、
# `05-代码验证器.ipynb`（验证器只产证据，不判定 allow / block）。
# ----------------------------------------------------------------------------
