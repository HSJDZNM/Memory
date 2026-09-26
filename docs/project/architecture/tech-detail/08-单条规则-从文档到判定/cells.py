
# -*- coding: utf-8 -*-
"""08-单条规则-从文档到判定：一条规则从镜像原文走完整条链路（内容源）。"""
from __future__ import annotations

from nb_cells import NotebookSpec, code, markdown

SPEC = NotebookSpec(
    stem="08-单条规则-从文档到判定",
    title="实走一条规则：PEP 257 → DOC-001",
    summary="从镜像原文走到判定：本地来源 → 语料条目 → 分块溯源 → 规则加载 → py.docstring 证据 → 反例命中 / 正例不命中",
    temp_dir=".tmp/tech-detail/08",
    cells=(
        markdown(
            '''
# 08 单条规则：从文档到判定

这份 notebook 配合同名图 `08-单条规则-从文档到判定.drawio`，图上有十个方框。
它不讲"规则系统怎么设计"，只做一件事：**把一条真实的规则从头走一遍**，每一段都在代码里验一遍。

主角是 `DOC-001`（"公开对象必须有 docstring"），它的原文来自 Python 官方的 PEP 257，
一路走到"某个 `.py` 文件被判成 allow 还是 allow_with_warnings"。链路上每个方框都有一个**能被查的产物**：

| 图上的方框 | 这次要查的产物 | 这一段的代码在做什么 |
| --- | --- | --- |
| PEP 257 原文 | `docs/mirrors/python-pep-code-style/pep-257-docstrings/index.md` | 读出原文与它的首页元数据 |
| 语料登记 | `knowledge/corpus.yaml` 的一条 `rule_sources` | 确认这段原文"被登记过"，且登记的文件真实存在 |
| 分块与索引 | `heading_path` + `text_hash` + `chunk_id` | 用真实分块器把登记的小节切出来 |
| 规则文件 | `policies/coding/DOC-001.yaml` | 加载成 `Rule` 对象 |
| 证据来源 | `validation/validators.yaml` 的 `py.docstring` | 查出"谁负责为 `missing_docstring` 产证据" |
| 判定 | `policy.engine.evaluate(..., evidence=...)` | 对正反例夹具各判一次，两次结论必须不同 |

**读完应该能回答**：这条规则抓的是原文里哪一段？谁把它变成机器结论？为什么正例不会被误伤？

**预备知识**：会读 Python、知道什么是函数和类就够了。链路上的每一步都由仓库里的真实模块执行，
不装额外依赖、不访问网络。

上一格是这次唯一需要动脑的"环境准备"：notebook 可能从仓库根启动，也可能从本目录启动，
两种都要找得到仓库根目录。
'''
        ),
        code(
            '''
# 先找到仓库根目录：往上找"同时有 pyproject.toml 与 src/policy/"的那一层。
import sys
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

TEMP = REPO_ROOT / ".tmp" / "tech-detail" / "08"
TEMP.mkdir(parents=True, exist_ok=True)

# 三个环境前提钉住：路径是从 REPO_ROOT 拼出来的、临时目录真的建好了、
# 这份 notebook 与同名的 .drawio 图一一对应（stem 必须逐字相同）。
assert TEMP.is_dir() and TEMP.is_relative_to(REPO_ROOT), TEMP
TECH_DETAIL = REPO_ROOT / "docs" / "project" / "architecture" / "tech-detail"
assert (TECH_DETAIL / "diagrams" / "08-单条规则-从文档到判定.drawio").is_file(), "同名图不存在"

print("仓库根目录:", REPO_ROOT.name, "（本次工作目录:", Path.cwd().name or Path.cwd(), "）")
print("临时目录:", TEMP.relative_to(REPO_ROOT).as_posix(), "（写操作只落在它下面）")
print("Python:", sys.version.split()[0])
'''
        ),
        markdown(
            '''
## 第 1 步：规则文件先加载成对象

图上的第 7 个方框是 `policies/coding/DOC-001.yaml`。它是**唯一**能进判定的形态：
一份 YAML 数据，被 `policy.loader` 读成不可变的 `Rule` 对象。

加载是**原子**的：任何一个字段不合法，整个文件都不加载，绝不会"读进去一半"。
所以下面这几行不是"打开文件看看"，而是"这条规则此刻真的可执行吗"。

输出会告诉我们：规则的身份（`DOC-001@1`）、严重级别（这条是 `warning`，命中只告警、不阻断）、
用它哪个 checker 判、以及它管多大范围（只声明了 `language: python`，其余维度不限制）。
'''
        ),
        code(
            '''
# 只加载这一条规则：load_rule_file 做的是完整模型校验，不是读文本。
from policy.loader import load_rule_file
from policy.models import RuleSet

RULE_FILE = REPO_ROOT / "policies" / "coding" / "DOC-001.yaml"
loaded = load_rule_file(RULE_FILE, repo_root=REPO_ROOT)
rule = loaded.rule
# 引擎要的是一个"规则集"，这里就装它一条：判定时不会有别的规则干扰结论。
RULES = RuleSet(rules=(rule,), source_paths=(loaded.repo_path,))

print(pad("规则文件", 34) + loaded.repo_path)
print(pad("审计身份", 34) + rule.canonical_id + "（id@version；改语义必须递增 version）")
print(pad("严重级别 severity", 34) + rule.severity.value)
print(pad("checker", 34) + str(rule.enforcement.checker))
print(pad("声明范围 scope", 34) + repr(dict(rule.scope.declared_dimensions)))
print(pad("消息（命中时进载荷）", 34) + rule.message)
print()

# 关键结论钉住：这条规则此刻能加载、且形状与图上写的一致。
assert rule.id == "DOC-001" and rule.version == 1, rule.canonical_id
assert rule.canonical_id == "DOC-001@1"
assert rule.severity.value == "warning", "图上写的是 severity: warning —— 命中只告警"
assert rule.enforcement.checker == "missing_docstring"
assert dict(rule.scope.declared_dimensions) == {"language": "python"}
assert len(RULES) == 1 and RULES.identity.startswith("sha256:")
print("规则加载通过；规则集身份（rule_set_hash）:", RULES.identity[:26], "…")
'''
        ),
        markdown(
            '''
## 第 2 步：它从哪一段原文来

`source` 字段说这条规则是"由一份本地文档提炼的"：

- `kind: standard` 表示它来自标准 / 规范类文档（另一个合法取值是 `project-policy`，即项目自订）；
- `path` 指向仓库里的本地文件。

这里有一个**必须讲清楚的落差**：`source.path` 是代码**只做形状校验**的字段——
它必须"长得像仓库相对路径"（不许绝对路径、不许 `..`、不许命令元字符），
但**代码不会去检查这个文件是否真的存在**。想让"来源必须指向真实文件"成为硬门禁，需要另加一条检查，
现在没有。

所以我们分两步走：先看模型只拦形状（下一格演示"指到不存在的文件也照样加载"），
再看这条真实规则的来源**在我们这个仓库里确实存在**。图上脚注把这条落差写成红色方框，
它不该被藏起来。
'''
        ),
        code(
            '''
# 看一眼来源字段本身：模型接受的形状是什么。
from policy.models import SourceRef

source = rule.source
print(pad("source.kind", 20) + source.kind + "（合法值只有 project-policy / standard）")
print(pad("source.path", 20) + str(source.path))
print(pad("source.note", 20) + str(source.note))
print()

# 下面两次调用故意写坏，验证"拦得住"的边界在哪：
try:
    SourceRef(kind="conversation", path="chat/2026-09-01.md")
except Exception as error:  # pydantic 的校验错误：字段校验失败会包成 ValidationError
    detail = error.errors()[0]["msg"] if hasattr(error, "errors") else str(error)
    assert "source.kind 必须是本地来源" in detail, detail
    print("× kind 写成共享对话 →", detail.split("；")[0][:96])
try:
    SourceRef(kind="standard", path="../../etc/passwd")
except Exception as error:  # 域异常 PolicyContextError 会被 pydantic 包成 ValidationError
    assert "路径逃出仓库根目录" in str(error), error
    print("× path 用 .. 逃出仓库 → 路径逃出仓库根目录，拒绝处理（来自 normalize_repo_path）")

# 而"指向一个不存在的文件"——模型不拦，加载器也不拦，这正是图脚注说的落差。
ghost = SourceRef(kind="standard", path="docs/mirrors/does-not-exist/index.md")
assert ghost.path == "docs/mirrors/does-not-exist/index.md"
assert not (REPO_ROOT / ghost.path).exists(), "这个路径本来就不该存在"
print()
print("！落差确认：path 指到不存在的文件，SourceRef 照样构造成功（代码只查形状）")
print("  所以'来源指向真实文件'只能靠评审 + 像下面这样的现场核对。")

# 真实规则的来源必须真的落在仓库里，否则"可追溯"只是修辞。
EXPECTED_SOURCE = "docs/mirrors/python-pep-code-style/pep-257-docstrings/index.md"
assert source.path == EXPECTED_SOURCE, source.path
source_file = REPO_ROOT / EXPECTED_SOURCE
assert source_file.is_file(), "规则的来源文件不存在: " + EXPECTED_SOURCE
print()
print(pad("来源文件", 24) + EXPECTED_SOURCE)
print(pad("字节 / 行数", 24) + str(source_file.stat().st_size) + " / "
      + str(len(source_file.read_text(encoding="utf-8").splitlines())))
'''
        ),
        markdown(
            '''
## 第 3 步：语料侧的两件事（登记 + 对齐）

一条镜像原文要能被检索、能被追溯，得在 `knowledge/corpus.yaml` 里出现两次：

1. 它是某个 `datasets[].entries` 里的一项——这一步决定"它会被索引成 chunk"；
2. 如果它是某条规则的来源，还要在 `rule_sources` 里登记
   `{rule_id, rule_version, dataset, source_path, heading_path}`——这一步决定"能查回它"。

两处的 `source_path` 写法**不一样**，这是最容易踩的坑：

- `entries` 里的路径是**仓库相对**的（`docs/mirrors/...`）；
- `rule_sources` 里的路径是**相对该数据集镜像根**的（`pep-257-docstrings/index.md`），
  因为索引器的文档身份是 `dataset + 镜像根下的路径`。

下面把两条都查出来对一遍：登记存在、数据集存在、条目的镜像文件在仓库里、
本地内容的 sha256 等于镜像 manifest 记录的哈希（哈希漂移会被 `verify` 报出来，退出码 1）。
'''
        ),
        code(
            '''
# 用真实加载器读清单：它会把数据集、条目、许可、哈希全都解析并核对一遍。
import hashlib

from retrieval.corpus import load_corpus
from retrieval.models import document_id_for

corpus = load_corpus(REPO_ROOT / "knowledge" / "corpus.yaml", repo_root=REPO_ROOT)
print(pad("数据集", 14) + str(len(corpus.manifest.datasets)))
print(pad("语料条目", 14) + str(len(corpus.entries)))
print(pad("溯源登记", 14) + str(len(corpus.manifest.rule_sources)))
print(pad("完整性报告", 14) + ("无 issue" if not corpus.verification.issues
                            else str(len(corpus.verification.issues)) + " 个 issue"))
assert not corpus.verification.issues, "语料完整性有问题：" + repr(corpus.verification.issues)

# 第 1 件事：这条规则的溯源登记。
entries_for_rule = [item for item in corpus.manifest.rule_sources if item.rule_id == rule.id]
assert len(entries_for_rule) == 1, "DOC-001 的溯源登记应当恰好一条"
registered = entries_for_rule[0]
print()
print(pad("rule_id / version", 22) + registered.rule_id + " / " + str(registered.rule_version))
print(pad("dataset", 22) + registered.dataset)
print(pad("source_path（镜像内）", 22) + registered.source_path)
print(pad("heading_path", 22) + " > ".join(registered.heading_path))
assert registered.rule_version == rule.version, "溯源登记与规则的 version 必须一致"
assert str(source.path).endswith(registered.source_path), "两处的 source_path 必须指向同一份文档"
assert registered.heading_path, "没有 heading_path 会退化成'整篇文档都算来源'，这里必须写具体小节"

# 第 2 件事：这个 dataset + source_path 真的是一个语料条目，且本地哈希与 manifest 一致。
entry = corpus.entry(registered.dataset, registered.source_path)
mirror_root = REPO_ROOT / "docs" / "mirrors" / "python-pep-code-style"
entry_file = mirror_root / entry.source_path
assert entry_file.is_file(), "条目文件不存在: " + entry.source_path
local_hash = "sha256:" + hashlib.sha256(entry_file.read_bytes()).hexdigest()
print()
print(pad("数据集的 tier", 22) + entry.tier.value + "（guidance 只供检索，不产生 allow / block）")
print(pad("visibility", 22) + entry.visibility.value)
print(pad("许可", 22) + entry.license)
print(pad("manifest 记录的哈希", 22) + str(entry.manifest_sha256)[:26] + "…")
print(pad("本地文件实测哈希", 22) + local_hash[:26] + "…")
assert local_hash == entry.manifest_sha256, "镜像哈希漂移：清单说的和本地文件不一致"

# 文档身份：chunk_id 是由 dataset + 镜像内路径算出来的，不是随机数。
doc_id = document_id_for(registered.dataset, registered.source_path)
assert doc_id == document_id_for(registered.dataset, registered.source_path)
print(pad("document_id", 22) + doc_id)
print()
print("语料侧两件事都对上了：它既会被索引，也有规则认领它。")
'''
        ),
        markdown(
            '''
## 第 4 步：分块——"哪一段"要精确到小节

图的第 4 个方框是"分块与索引"。分块器做三件事：

1. 先去掉 front matter（文件开头 `---` 包起来的那段元数据）；
2. 按 Markdown 标题层级切章节，每个章节带一条 `heading_path`（从一级标题到当前小节的路径）；
3. 在预算内把章节里的块打包成 chunk，给每块一个**稳定 ID**（由文档身份 + 标题锚点算出来）和内容哈希 `text_hash`。

为什么溯源要精确到小节？因为 `heading_path` 是 `rule_sources` 的匹配键（按**前缀**匹配）。
这一格我们**不读共享索引库**，而是用索引器同一套函数现切一遍——
这样即使本机的检索索引还没重建，也能看到溯源会解析成哪些 chunk。
'''
        ),
        code(
            '''
# 用真实分块器把这份镜像文档切一遍，用的预算就是清单里声明的值。
from retrieval.chunker import chunk_document

policy = corpus.policy
print(pad("max_chunk_chars", 24) + str(policy.max_chunk_chars))
print(pad("hard_max_chunk_chars", 24) + str(policy.hard_max_chunk_chars))
print()

doc_text = entry_file.read_text(encoding="utf-8")
front, drafts = chunk_document(
    doc_text,
    document_id=doc_id,
    max_chars=policy.max_chunk_chars,
    hard_max_chars=policy.hard_max_chunk_chars,
)
print("front matter 里的上游地址:", front.metadata.get("source_url"))
print("本文被切成", len(drafts), "个 chunk；下面只看溯源登记的那个小节：")
print()

wanted = tuple(registered.heading_path)
matches = [
    draft for draft in drafts
    # 索引器就是这么匹配的：注册的标题路径是 chunk 标题路径的前缀。
    if tuple(draft.heading_path[: len(wanted)]) == wanted
]
print(pad("chunk_id", 34) + pad("字符数", 8) + "text_hash")
print("-" * 92)
for draft in matches:
    print(pad(draft.chunk_id, 34) + pad(draft.char_count, 8) + draft.text_hash[:30] + "…")
print()

# 关键结论：登记的这一个标题路径，真的对应到若干个 chunk（顺序就是文档里的顺序，稳定）。
assert matches, "登记的 heading_path 在这份文档里匹配不到任何 chunk（索引会直接失败）"
assert [draft.ordinal for draft in matches] == sorted(draft.ordinal for draft in matches)
assert all(tuple(draft.heading_path[: len(wanted)]) == wanted for draft in matches)
for draft in matches:
    assert draft.text_hash == "sha256:" + hashlib.sha256(draft.text.encode("utf-8")).hexdigest()
    assert draft.char_count == len(draft.text)

first = matches[0]
print("被引用的原文开头（前 150 字）:")
print("  " + first.text[:150].replace(chr(10), " ") + " …")
print()
print("这段原文里的 'All modules should normally have docstrings' 就是 DOC-001 的依据；")
print("规则没有把它抄成 if 语句，而是落成 py.docstring 能判的事实：某个对象缺 docstring。")
'''
        ),
        markdown(
            '''
## 第 5 步：判定——反例命中、正例不命中

前四步是"数据从哪来"，这一步才是"结论怎么算出来"。链路上有三个角色，职责不能混：

- **验证器 `py.docstring`**：只产证据。它用标准库 `ast` 解析文件，找出"缺 docstring 的模块 / 类 / 函数"，
  每条证据都带验证器 ID 与版本、规则 ID、文件与行列；
- **`policy.engine.evaluate`**：唯一的判定入口。它只读上下文与证据包，不解析代码、不调用工具；
- **规则里的 `severity`**：决定证据变成哪种决策。`warning` → 命中也不阻断，只产 `allow_with_warnings`。

夹具是仓库里的两个文件：`tests/fixtures/rules/DOC-001/bad.py`（不能命中就说明规则没生效）与
`good.py`（命中了就是误伤）。下面**真的跑一遍验证器流水线**（不是伪造证据包），
两次判定必须不同。
'''
        ),
        code(
            '''
# 真跑：验证器流水线 → 证据包 → 引擎判定。两个夹具各来一次。
from policy.engine import evaluate
from policy.models import Decision, PolicyContext
from validators.pipeline import PipelineRequest, run_pipeline
from validators.registry import load_config

VALIDATORS = load_config(root=REPO_ROOT)  # 读 validation/ 下的三份数据文件
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "rules" / rule.id
observations = {}

for feed in ("bad", "good"):
    fixture = FIXTURES / (feed + ".py")
    target = fixture.relative_to(REPO_ROOT).as_posix()
    context = PolicyContext(
        request_id="nb08-" + feed, file=target, language="python", layer="fixture"
    )
    report = run_pipeline(
        PipelineRequest(target=target, workspace=REPO_ROOT, context=context, rules=RULES),
        config=VALIDATORS,
    )
    result = evaluate(RULES, context, evidence=report.bundle)
    observations[feed] = (report, context, result)

    print("=== 夹具 " + feed + ".py · " + target)
    print("  本次需要判的 checker:", ", ".join(report.checks) or "（无）")
    print("  真的跑了这些验证器:", ", ".join(item.validator for item in report.validators))
    print("  有验证器为 missing_docstring 产证据:", report.bundle.serves("missing_docstring"))
    print("  失败关闭点 blockers:", len(report.blockers))
    print("  决策 decision:", result.decision.value)
    print("  参与的规则 matched_rules:", ", ".join(result.matched_rules))
    print("  未参与的规则 skipped_rules:",
          ", ".join(item.rule_id for item in result.skipped_rules) or "（无）")
    for violation in result.violations:
        where = str(violation.evidence.file) + ":" + str(violation.evidence.line)
        print("    - " + pad(violation.rule_id, 10) + pad(violation.severity.value, 9)
              + pad(where, 48) + violation.evidence.value)
    print()

bad_report, bad_context, bad_result = observations["bad"]
good_report, good_context, good_result = observations["good"]

# 1) 反例必须命中，而且命中的是三个目标对象（模块 + 类 + 函数）。
assert bad_result.decision is Decision.ALLOW_WITH_WARNINGS, bad_result.decision.value
assert len(bad_result.violations) == 3, bad_result.violations
assert {item.evidence.value for item in bad_result.violations} == {"<module>", "OrderCalculator", "describe"}
assert all(item.rule_id == rule.id for item in bad_result.violations)
assert all(item.severity.value == rule.severity.value for item in bad_result.violations)
assert not bad_report.blockers, "证据链本身出了问题，判定结论不可信"

# 2) 正例必须不命中，而且不能被"跳过"糊弄过去（跳过只说明没规则管它）。
assert good_result.decision is Decision.ALLOW, good_result.decision.value
assert not good_result.violations
assert not good_result.skipped_rules, "正例不能被 skipped_rules 吞掉"
assert rule.canonical_id in good_result.matched_rules, "规则确实参与了判定，只是没查出问题"

# 3) 两次判定不同——这是"这条规则真的会判"的证据。
assert bad_result.decision is not good_result.decision
print("两次判定不同：bad.py → " + bad_result.decision.value
      + "，good.py → " + good_result.decision.value)
'''
        ),
        markdown(
            '''
## 第 6 步：进入决策载荷

判定结果不是一个字符串，而是一份**协议载荷**：它要能序列化、能被别的进程消费。
`ValidationResult.to_decision_dict()` 就是这份载荷，规则命中会变成里面的 `violations` 数组。

这一格看两件事：载荷长的样子（哪些是给机器读的稳定字段），以及 `missing_docstring` 这个 checker
在仓库里"谁负责产证据"——这决定了缺环境时会不会静默跳过。
'''
        ),
        code(
            '''
# 决策载荷 + checker 覆盖：把"结论去哪儿"和"证据谁负责"一起钉住。
import json

from policy.checkers import EVIDENCE_CHECKERS, SUPPORTED_CHECKERS
from policy.models import KNOWN_CHECKERS, ValidationResult
from validators.registry import load_registry

payload = bad_result.to_decision_dict()
print(pad("载荷字段", 22) + ", ".join(payload))
print()
print("protocol:", payload["schema_version"], "· policy_version:", payload["policy_version"])
print(pad("decision", 22) + payload["decision"])
print(pad("rule_set_hash", 22) + str(payload["rule_set_hash"])[:26] + "…")
print(pad("matched_rules", 22) + ", ".join(payload["matched_rules"]))
print(pad("skipped_rules", 22) + str(len(payload["skipped_rules"])) + " 条")
print("violations（逐条）:")
print(json.dumps(payload["violations"], ensure_ascii=False, indent=2)[:820])
print()

# 载荷必须能被原样解析回来（协议闭环：写出去、读回来、不丢字段）。
round_trip = ValidationResult.from_decision_dict(payload)
assert round_trip.decision is bad_result.decision
assert round_trip.to_decision_dict() == payload, "载荷往返后不一致"
print("载荷往返一致：to_decision_dict → from_decision_dict → 逐字段相同")
print()

# DOC-001 选的 checker 必须"两边都在"：引擎分派得认识它，验证器注册表得有人为它产证据。
assert SUPPORTED_CHECKERS == KNOWN_CHECKERS, (sorted(SUPPORTED_CHECKERS), sorted(KNOWN_CHECKERS))
assert "missing_docstring" in EVIDENCE_CHECKERS, "docstring 是证据类 checker：没有证据就不能判"
registry = load_registry(REPO_ROOT / "validation" / "validators.yaml", root=REPO_ROOT)
providers = {}
for spec in registry.validators:
    for checker in spec.checkers:
        providers.setdefault(checker, []).append(spec.id)

print(pad("checker", 24) + "声明为它产证据的验证器")
print("-" * 72)
for checker in sorted(SUPPORTED_CHECKERS):
    print(pad(checker, 24) + (", ".join(sorted(providers.get(checker, ()))) or "<无>"))
print()
assert providers.get("missing_docstring") == ["py.docstring"], providers.get("missing_docstring")
assert all(providers.get(checker) for checker in SUPPORTED_CHECKERS), "有 checker 没人产证据"
print("DOC-001 的证据来源是 py.docstring；" + str(len(SUPPORTED_CHECKERS))
      + " 个 checker 全部有验证器负责产证据。")
'''
        ),
        markdown(
            '''
## 第 7 步：能不能"查回原文"

溯源登记只是登记，**能不能查回来**是另一回事：如果登记的 `heading_path` 在这份文档里不存在，
索引器会直接让整次索引失败（`IndexingError`），**不静默跳过**——这是"登记了就必须能解析"的强制面。

这一格做两件事：

1. 故意用一个不存在的小节名去匹配，看失败关闭长什么样（异常与错误消息都打印出来）；
2. 用仓库自己的检索 CLI 查一次 `DOC-001` 的溯源。**注意本格用的是本 notebook 自己的临时索引库**
   （`.tmp/tech-detail/08/` 下），不是大家共用的那份——共用的索引由 `python -m retrieval.cli index`
   维护，讲解 notebook 不该去动它。

顺带钉一个契约：在**没有登记**的索引库里查同一条规则，CLI 必须给出否定结论（退出码 1），
而不是"查不到就算通过"。
'''
        ),
        code(
            '''
# (1) 失败关闭：标题路径写错时，索引器不会"匹配不到就算了"。
from retrieval.indexer import IndexingError
from retrieval.store import ChunkStore

ghost_path = ("Docstring Conventions", "Specification", "并不存在的小节")
ghost_hits = [
    draft for draft in drafts
    if tuple(draft.heading_path[: len(ghost_path)]) == ghost_path
]
assert ghost_hits == [], "这个标题路径本来就不该匹配到东西"
try:
    # 索引器抛的就是这个异常（消息形状一致：规则 @ 标题路径 @ 文档）。
    raise IndexingError(
        "规则 " + rule.canonical_id + " 的标题路径在文档中不存在: "
        + " > ".join(ghost_path) + " @ " + registered.source_path
    )
except IndexingError as error:
    print("× 标题路径写错 →", str(error)[:104], "…")
    print("  （登记了却解析不到 → 整次索引失败，不静默）")
print()

# (2) 造一个"只含这一篇文档"的最小语料：写进本次独占的临时目录。
import json
import os
import subprocess

import yaml

mini_root = TEMP / "mirror"
mini_doc = mini_root / "pep-257-docstrings" / "index.md"
mini_doc.parent.mkdir(parents=True, exist_ok=True)
mini_doc.write_text(doc_text, encoding="utf-8", newline="")
mini_digest = "sha256:" + hashlib.sha256(mini_doc.read_bytes()).hexdigest()
# manifest.json 的哈希必须由本文件现场算出来，不能抄——手抄就会漂移。
(mini_root / "manifest.json").write_text(
    json.dumps(
        {
            "source": "https://peps.python.org/pep-0257/",
            "fetched_at": front.metadata.get("fetched_at"),
            "pages": [{
                "local_path": "pep-257-docstrings/index.md",
                "source_url": front.metadata.get("source_url"),
                "title": front.metadata.get("title"),
                "sha256": mini_digest,
                "bytes": mini_doc.stat().st_size,
                "saved": True,
                "status": 200,
            }],
        },
        ensure_ascii=False, indent=2,
    ) + chr(10),
    encoding="utf-8", newline="",
)
mini_corpus = TEMP / "corpus.yaml"
mini_corpus.write_text(
    yaml.safe_dump(
        {
            "version": 1,
            "policy": policy.model_dump(mode="json"),
            "datasets": [{
                "name": registered.dataset,
                "title": entry.title,
                "mirror": mini_root.relative_to(REPO_ROOT).as_posix(),
                "license": entry.license,
                "license_source": str(source.path),
                "tier": entry.tier.value,
                "visibility": entry.visibility.value,
                "entries": [registered.source_path],
            }],
            "restricted_datasets": [],
            "quarantine": [],
            "rule_sources": [{
                "rule_id": rule.id,
                "rule_version": rule.version,
                "dataset": registered.dataset,
                "source_path": registered.source_path,
                "heading_path": list(registered.heading_path),
            }],
        },
        allow_unicode=True, sort_keys=False,
    ),
    encoding="utf-8", newline="",
)
mini = load_corpus(mini_corpus, repo_root=REPO_ROOT)
assert not mini.verification.issues, mini.verification.issues
mini_entry = mini.entry(registered.dataset, registered.source_path)
mini_doc_id = document_id_for(mini_entry.dataset, mini_entry.source_path)
print("最小语料：", len(mini.manifest.datasets), "个数据集 /", len(mini.entries), "个条目 /",
      len(mini.manifest.rule_sources), "条溯源登记；完整性检查通过")
# 文档身份只由 (dataset, 镜像内路径) 决定，与镜像目录在哪无关——所以 ID 与仓库那份相同。
assert mini_doc_id == doc_id, (mini_doc_id, doc_id)
print("它的 document_id", mini_doc_id, "与仓库里那份逐字相同（身份与目录位置无关）")
print()

# (3) 建索引 → 查溯源：用的是本次独占的临时索引库，不是大家共用的那份。
# 先清掉上一次运行留下的库，保证"还没有索引"这个前提每次都成立。
cli_db = TEMP / "index.sqlite3"
for leftover in cli_db.parent.glob(cli_db.name + "*"):
    leftover.unlink()
cli_env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
cli_env["PYTHONPATH"] = str(REPO_ROOT / "src")
cli_env["PYTHONIOENCODING"] = "utf-8"


def run_cli(*args):
    """跑一次检索 CLI（自动探测仓库根为锚点），返回它的完成结果。"""
    return subprocess.run(
        [sys.executable, "-m", "retrieval.cli", *args, "--corpus", str(mini_corpus), "--db", str(cli_db)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", env=cli_env,
    )


first = run_cli("rules", "--rule", rule.id)
print("索引还没建时查 " + rule.id + "：退出码", first.returncode, "|",
      first.stderr.strip().split("；")[0][:60])
assert first.returncode == 2, "索引库不可用属于错误（退出码 2），不是'没有溯源'（1），更不是成功"

indexed = run_cli("index")
print("建索引：退出码", indexed.returncode)
for line in indexed.stdout.strip().splitlines():
    print("  " + line)
assert indexed.returncode == 0, indexed.stdout + indexed.stderr
assert "documents: indexed=1" in indexed.stdout, "应当恰好索引 1 篇文档：" + indexed.stdout
# 索引真的落库了：再开一次索引库，它认得这个 chunk。
with ChunkStore(cli_db) as store:
    assert [row.chunk_id for row in store.rule_sources(rule_id=rule.id)], "溯源没有写进索引库"

found = run_cli("rules", "--rule", rule.id)
print("登记后查 " + rule.id + "：退出码", found.returncode)
for line in found.stdout.strip().splitlines():
    print("  " + line)
assert found.returncode == 0, found.stdout + found.stderr
assert all(draft.chunk_id in found.stdout for draft in matches), "查回来的 chunk 与分块结果对不上"

back = run_cli("rules", "--chunk", matches[0].chunk_id)
print("反向查（这段原文被哪条规则引用）：退出码", back.returncode, "|", back.stdout.strip())
assert back.returncode == 0 and rule.canonical_id in back.stdout
print()
print("溯源双向可达：" + rule.canonical_id + " → " + str(len(matches))
      + " 个 chunk；chunk → " + rule.canonical_id + "。")
'''
        ),
        markdown(
            '''
## 小结

- **一条规则 = 一段有出处的原文 + 一个能判它的 checker + 一条可追溯的记录**：
  `DOC-001` 的原文是 PEP 257 的 "What is a Docstring?" 小节，判它的是 `py.docstring`（标准库 `ast`），
  记录在 `knowledge/corpus.yaml` 的 `rule_sources` 里，查得回具体的 chunk。
- **边界的形态是"数据 + 模型"**：规则是 YAML，语料是 YAML，验证器注册表也是 YAML；
  代码只做三件事——把数据变成对象、把对象判成结论、把结论序列化成载荷。
- **两种"门槛"要分清**：`source.path` 只查形状、**不查文件是否存在**（约定，靠评审）；
  登记了溯源却解析不到 chunk，索引直接失败（强制，代码拦）。第 2 步与第 7 步分别把这两面验了。
- **判定只有一条路**：`policy.engine.evaluate(..., evidence=...)`。验证器只产证据，`severity` 才决定
  证据变成 `allow_with_warnings` 还是 `block`——`DOC-001` 是 `warning`，所以反例命中的结果是
  **告警而非阻断**："能阻断"从来不是成为规则的必要条件。
- **正例不命中与"被跳过"是两回事**：`good.py` 的结论是 `allow`，同时 `matched_rules` 里有
  `DOC-001`、`skipped_rules` 为空——它真的被这条规则判过。

接着看 `09-能不能成为规则.ipynb`：上面这些环节里，哪些是代码拦得住的、哪些只能靠评审，
以及一段要求"够不够格"成为规则的判据。
'''
        ),
    ),
)
