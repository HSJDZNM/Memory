# AACR-Bench（`Alibaba-Aone/aacr-bench`）数据集核验

- 核验对象：<https://huggingface.co/datasets/Alibaba-Aone/aacr-bench>
- 核验日期 / 访问日期：**2026-10-07**
- **标记约定**：【已核验】= 我在 2026-10-07 真的取到了该记录，URL/命令与原文摘录见 §8 证据索引的对应编号（[E01]…[E27]）；【待核验】= 没取到、或论文里确实没有，写法与试过的位置见 §9。**本文不使用「估计」这类措辞**——凡我没有实测的数字，都会写明它只是 GitHub / 论文报告的值。
- 核验通道：HuggingFace API（`huggingface.co/api/datasets/...`）、datasets-server（`/splits` `/size` `/info` `/parquet` `/first-rows` `/rows`）、原始文件（`resolve/main/dataset.json`）、arXiv HTML 全文（v1 与 v3）、GitHub API 与 `gh` CLI
- 取到的原文与脚本全部落在 `.tmp/aacr-bench/raw/`（临时目录，命令可重放；正文给出每条结论的确切命令）
- **口径**：以实际取到的记录为准。数据集卡与仓库 README 的宣传语只作为"被检验的声明"引用，不与记录混同。

---

## 0. 结论先行

1. 【已核验】**数据集真实存在、公开、非 gated、非私有，且可钉死 revision。** main 分支 targetCommit = `47be1d6df1e7faf222cf531587772d92f79fe6b2`；该仓库共 5 个 commit，全部发生在 2026-02-02 当天，此后未再更新。[E01][E02]
2. 【已核验】**规模与卡上声明一致。** `/size` 实测：`num_rows = 2145`、`num_columns = 16`、`num_bytes_original_files = 2101497`、`num_bytes_parquet_files = 539972`；唯一 config `default`、唯一 split `train`。逐条解析 `dataset.json` 得到 2145 条记录，label=1 有 1505 条、label=0 有 640 条——与数据集卡"2,145 条 / 1,505 正确 / 640 错误"**逐个数字吻合**。[E03][E04][E05]
3. 【已核验】**它既不是"检出式规则"数据集，也不是"给 diff 让模型产出评论再打分"的数据集。** 它是**评论级二分类**：给定一条已有的评审意见（`note`）加上它的位置（`path` / `from_line` / `to_line`），判断这条意见是"正确"（label=1）还是"错误"（label=0）。**数据集里没有任何代码、diff/patch 字段**：没有 `diff`、没有 `hunk`、没有 `code`、没有 `content`。要看到被评审的代码，必须自己按 `pr_url` + 两个 commit 去 clone 上游仓库。[E04][E06]
4. 【已核验】**标签的来源（第 4 问，重点）**：论文明确写了"AI 辅助、人工专家核验"的三轮标注流程——80 余名工程师、前两轮 double-blind 双人独立标注、第三轮由 6 人核心专家组裁决冲突。**但论文 v1 与 v3 全文都没有任何标注者间一致性系数**：检索 `kappa` / `IAA` / `inter-annotator` / `agreement` / `Cohen` / `Fleiss`，命中数均为 **0**。[E07][E08][E09]
5. 【已核验】**数值对账证明：HF 的 label=1 就是论文的 1505 条 Ground Truth。** 论文 Table 1 的上下文分布 Diff 754 / File 518 / Repo 233 与 HF `label=1` 的 `context` 分布**完全相等**；论文 Table 7 的四类目 53 / 709 / 626 / 117 与 HF `label=1` 的 `category` 分布**完全相等**；论文"391 条来自人工、1,114 条由 LLM 生成"与 HF `label=1` 的 `is_ai_comment`（False 391 / True 1114）**完全相等**。[E09][E10][E11]
6. 【已核验】**640 条"错误"标签在论文里没有对应的标注流程描述。** v3 全文检索 `reflection`、`huggingface`、`negative`、`640` 命中数均为 **0**；论文只描述了最终留下的 1505 条正例如何被标注，没有描述"被判错因而被拦下的评论"是否保留、以及"错"是如何裁决的。数据集卡的"640 incorrect comments"目前只有卡片与 README 的声明支撑。[E08][E12]
7. 【已核验】**judge（评分的裁判）在本数据集上不存在。** HF 数据集本身只有 `dataset.json`，没有任何评分脚本。仓库 `evaluation/judge.py` 是**给另一份数据**（GitHub 仓库里的 `dataset/positive_samples.json`，200 个 PR）用的 LLM judge，且它在**没有配 `JUDGE_API_KEY` 时会静默退回本地 `difflib` 字符串相似度**（阈值 `sequence_ratio >= 0.4` 或 `jaccard >= 0.3`）。[E13][E14]
8. 【已核验】**同源风险（第 7 问）：不同源，而且没有连接键。** 2145 条 `note` 中，CWE 编号 **0** 条、Bandit `S{三位数}` 码 **0** 条、pydocstyle `D{三位数}` 码 **0** 条、`OWASP` / `Bandit` / `pycodestyle` / `PEP 8` 提及 **0** 条。因此**一致率高也不能读成"我们的规则对"**——判据对象不同、且没有可对齐的键。[E15]
9. 【已核验】**可运行性上有两个实测缺陷（这是"以记录为准"最硬的部分）：**
   - **标签跨产物冲突（恰好 1 条）**：上游 GitHub 仓库在 2026-08-24 的 commit `dae8647` 里把 dbeaver PR #37564 的一条**人工评论从"负例"挪进了"正例"**；HF 快照停在 2026-02-02，没有跟随。集合比对结果是：HF 的 640 条 label=0 中有 **1 条**恰好是仓库正例集里的记录。[E16][E17]
   - **上游声明的 sha256 与实际内容不符**：`evaluation/benchmark/AACR-Bench/positive_samples.meta.json` 声明 `positive_samples.json` 的 sha256 为 `d8683cb2...`，而实际（已用 git blob sha1 认证过的）字节的 sha256 是 `7a4a0e70...`。该 meta 写于 2026-08-03、数据文件改于 2026-08-24，此后再未同步。仓库自带的 converter 在自动下载路径上**会因此直接 `SystemExit`**（`下载内容校验失败`）。[E17][E18][E19]
10. 【已核验】**能否入库**：许可只有数据集卡 frontmatter 里的 `license: apache-2.0` 与 HF API 的 `cardData.license`；**HF 数据集仓库里没有 LICENSE 文件**（`/resolve/main/LICENSE` 返回 404，仓库全量清单只有 4 个文件）；上游 GitHub 仓库有 Apache-2.0 的 `LICENSE`（11357 字节，blob `261eeb9e...`）。按本仓 `eval-datasets.yaml` 的口径，`license_verified: false` 时"不得入仓、不得分发"，所以**入仓前必须先拿到许可原文**。[E02][E20][E21][E22]

---

## 1. 存在性与元数据（第 1 问）

### 1.1 元数据表

下表每一行都是【已核验】，访问日期 **2026-10-07**；URL/命令与原文摘录见 §8 的对应编号。

| 项 | 取到的值 | 来源 |
| --- | --- | --- |
| dataset id | `Alibaba-Aone/aacr-bench` | HF API `id` |
| **revision（钉死）** | `47be1d6df1e7faf222cf531587772d92f79fe6b2` | HF API `sha`、`/refs` 的 `branches[0].targetCommit`、`/info` 的 `download_checksums` 键 |
| 创建方 | `author: Alibaba-Aone`；卡片：provided by the Alibaba Aone team；论文署名含 TRE, Alibaba Inc. 与南京大学软件学院 | HF API `author`、卡片第 20 行、arXiv v3 作者单位 |
| 创建时间 | `2026-02-02T06:47:02.000Z` | HF API `createdAt` |
| 最后修改 | `2026-02-02T06:59:14.000Z`（此后无新 commit） | HF API `lastModified`、`/commits/main` |
| 可见性 | `private: false`、`gated: false`、`disabled: false` | HF API |
| 行数 / 列数 | 2145 行 / 16 列 | `/size` |
| 字节 | 原始文件 2101497；parquet 539972；内存展开 1469552 | `/size` |
| config / split | 只有 `default` / 只有 `train`（`pending: []`，`failed: []`） | `/splits` |
| parquet 产物 | 1 个：`0000.parquet`（539972 字节），分支 `refs/convert/parquet` @ `ae77a0f779890faa929323dada85de5f0e4475bc` | `/parquet`、`/refs` |
| 自然语言 | 卡片 `language: [en]`，HF tag `language:en`；数据里的 10 个值是**编程语言**（`project_main_language`），两者不是同一个东西 | 卡片 frontmatter、`dataset.json` |
| 大小档 | `size_categories:1K<n<10K`` | HF tag |
| 论文关联 | tag `arxiv:2601.19494`；卡片给出 BibTeX（arXiv 2601.19494，2026） | HF tag、卡片第 52-59 行 |
| 热度（取样时） | `downloads: 916`，`likes: 13` | HF API |
| 数据文件内容哈希 | `dataset.json` 2101497 字节，sha256 `0804505f0a474765ce2840c832cfeaa6c4f0250dd6ccb169fe73c6758b245a86` | 本地对取到的字节计算 |

**⚠ 引用 arXiv HTML 时的数字陷阱**：arXiv 的 HTML 会同时渲染正文与 MathML 备选文本，导致数字被"打印两遍"。例如论文正文的 `391` 在 HTML 抽取文本里是 `391391`、`1,505` 是 `15051505`、`over 80` 是 `over 8080`、`6` 是 `66`。本文引用论文数字时按语义还原，凡出现此类重复串以此说明为准。

### 1.2 许可（原文）

- 卡片 frontmatter（`README.md` 第 10 行）：`license: apache-2.0`
- HF API `tags` 含 `license:apache-2.0`；`cardData.license = "apache-2.0"`
- **但数据集文件自身不含任何许可元数据**：`/info` 返回的 `dataset_info.default` 里 `license` / `citation` / `description` 三个字段都是空字符串，`download_checksums` 的 `checksum` 是 `null`。
- **HF 数据集仓库里没有 LICENSE 文件**：HF 的文件清单接口（`/api/datasets/Alibaba-Aone/aacr-bench/tree/main?recursive=true&expand=true`）**恰好返回 4 个文件**——`.gitattributes` / `README.md` / `dataset.json` / `readme_cn.md`，其中没有 LICENSE（对照：上游 GitHub 仓库的同类全量清单是 53 项，见 §5.3）；直接请求 `/resolve/main/LICENSE` 与 `/raw/main/LICENSE` 均返回 **404 `Entry not found`**。
- 上游 GitHub 仓库（`alibaba/aacr-bench`）**有** Apache-2.0 许可：API `license.spdx_id = "Apache-2.0"`，`LICENSE` 文件 11357 字节、blob `261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`，文件首行 `Apache License / Version 2.0, January 2004`。

**结论**：许可声明是 Apache-2.0，但它只存在于卡片文本与 GitHub 仓库；**HF 上的数据副本没有 LICENSE 文件兜底**。这一点必须在入仓前向上游确认（是"数据沿用项目 Apache-2.0"，还是"只有代码是 Apache-2.0"）。

### 1.3 数据集卡原文（英文）

卡片共 61 行，关键句（第 18、20 行）：

> This is a test set designed for automated code review reflection models, primarily aiming to evaluate the extent to which a model can intercept low-quality review comments. The dataset contains 2,145 code review comments, consisting of 1,505 expert-verified correct comments and 640 incorrect comments.

> This data is part of the [AACR-Bench](https://github.com/alibaba/aacr-bench) project and is provided by the Alibaba Aone team.

中文卡 `readme_cn.md`（第 5 行）同义："这是一个专为自动化代码评审反思模型设计的测试集……包含 2,145 条代码评审意见，其中包括 1,505 条经专家验证的正确意见和 640 条错误意见。"

---

## 2. 字段结构与样例记录（第 2 问）

### 2.1 字段表（`/first-rows` 的 `features` 原文）【已核验】

`https://datasets-server.huggingface.co/first-rows?dataset=Alibaba-Aone%2Faacr-bench&config=default&split=train` 返回 16 个字段（`truncated: true`，一页 100 行，`row_idx` 0..99），类型取自响应的 `features[].type.dtype`：

| # | 字段 | 类型 | 含义（卡片原文，中文卡译文） | 全量 2145 条实测分布 |
| --- | --- | --- | --- | --- |
| 0 | `project_main_language` | string | 项目主要编程语言 | 10 个值：C++ 508 / TypeScript 422 / Java 272 / Go 245 / C 206 / Python 151 / JavaScript 141 / Rust 92 / PHP 56 / C# 52 |
| 1 | `pr_url` | string | PR 的 GitHub 链接 | 200 个不同 PR，来自 **50** 个不同仓库 |
| 2 | `pr_source_commit` | string | PR 的源提交 | 全为 40 位 sha |
| 3 | `pr_target_commit` | string | PR 中选定修订版本的提交 | 全为 40 位 sha |
| 4 | `pr_change_line_count` | int64 | PR 的总变更行数 | min 4 / max 971 / 合计 790772 |
| 5 | `pr_category` | string | PR 的问题领域类别 | 9 个值（New Feature Additions 565 / Bug Fix 500 / Code Refactoring 369 / Performance 155 / Test Suite 151 / Documentation 132 / Security Patches 114 / Code Style 114 / Dependency 45） |
| 6 | `is_ai_comment` | bool | 该评论是否来自 AI 模型 | True 1597 / False 548 |
| 7 | `note` | string | **评审意见的具体内容** | 无空串 |
| 8 | `path` | string | 被评审文件的路径 | 与 `pr_url` 组合共 808 个不同 (PR, 文件) 对 |
| 9 | `side` | string | 评论在 diff 的左侧还是右侧 | right 2134 / left 11 |
| 10 | `source_model` | string | 生成该评论的 AI 模型，人工评论为空 | 7 个取值：GPT-5.2 575 / `""`（人工）548 / Claude-Code/Claude-4.5-Sonnet 279 / Qwen-Coder-480B 254 / GLM-4.7 229 / Deepseek-V3.2 136 / Gemini-3-Pro 124 |
| 11 | `from_line` | int64 | 被评审代码起始行号 | min 1 / max 29386 |
| 12 | `to_line` | int64 | 被评审代码结束行号 | min 1 / max 29386 |
| 13 | `category` | string | 评论指出的问题类型 | 4 个值：Code Defect 1022 / Maintainability and Readability 905 / Performance 144 / Security Vulnerability 74 |
| 14 | `context` | string | 该评论所需的上下文级别 | 3 个值：Diff Level 1017 / File Level 744 / Repo Level 384 |
| 15 | `label` | int64 | **这条评论是否正确，1 正确、0 错误** | 1 → 1505 / 0 → 640 |

补充实测（逐条解析 `dataset.json`，2145 条）：

- 除 `source_model`（548 条为空串，即人工评论）外，**其余 15 个字段没有空串也没有 null**。
- 文件**按 label 降序排列**：索引 0..1504 全部是 label=1，索引 1505..2144 全部是 label=0。这解释了一个容易被误读的现象——`/first-rows` 的前 100 行 label **全是 1**，只看第一页会以为数据集没有负例。
- 6 个生成侧模型名与论文 v3 §3.2 列的 generation matrix 名单**逐个对上**（Claude-4.5-Sonnet / Qwen3-Coder-480B-A35B-Instruct / GPT-5.2 / Deepseek-V3.2 / GLM-4.7 / Gemini-3-Pro）。

### 2.2 样例记录（截断）

第 0 行（label=1）：

```json
{
  "project_main_language": "C++",
  "pr_url": "https://github.com/FreeCAD/FreeCAD/pull/19411",
  "pr_source_commit": "0c65673a6fd2421be8fbe613116077120adea068",
  "pr_target_commit": "a050e422e23ce3eaee960b75ceff236b34f369b9",
  "pr_change_line_count": 862,
  "pr_category": "Code Refactoring / Architectural Improvement",
  "is_ai_comment": true,
  "note": "Optimization suggestion: `getDirsFromFront(t)` is currently called for every view in the loop.
           If multiple views share the same `ProjDirection` `t`, this results in redundant calculations. …
           Consider checking if `t` is already in `saveVals` before calling `getDirsFromFront`.",
  "path": "src/Mod/TechDraw/App/DrawProjGroup.cpp",
  "side": "right",
  "source_model": "Gemini-3-Pro",
  "from_line": 1123,
  "to_line": 1126,
  "category": "Performance",
  "context": "File Level",
  "label": 1
}
```

第 1505 行（第一条 label=0，注意它与上一条是同一个 PR、同一个文件，只是位置与来源不同）：

```json
{
  "project_main_language": "C++",
  "pr_url": "https://github.com/FreeCAD/FreeCAD/pull/19411",
  "pr_source_commit": "0c65673a6fd2421be8fbe613116077120adea068",
  "pr_target_commit": "a050e422e23ce3eaee960b75ceff236b34f369b9",
  "pr_change_line_count": 862,
  "pr_category": "Code Refactoring / Architectural Improvement",
  "is_ai_comment": false,
  "note": "The refactored code removes error handling for invalid projection types without implementing
           alternative validation. …",
  "path": "src/Mod/TechDraw/App/DrawProjGroup.cpp",
  "side": "right",
  "source_model": "",
  "from_line": 1127,
  "to_line": 1132,
  "category": "Code Defect",
  "context": "Diff Level",
  "label": 0
}
```

### 2.3 题面里问到的字段，逐个回答"有没有"

| 题面问的 | 有没有 | 说明 |
| --- | --- | --- |
| diff / patch | **没有** | 16 个字段里没有任何承载代码或 diff 的列。要拿到代码只能按 `pr_url` + `pr_source_commit` + `pr_target_commit` 自己 clone |
| 仓库名 | **没有独立字段** | 只能从 `pr_url` 正则解析 `owner/name`（上游 converter 就是这么做的） |
| 语言 | **有，但是项目级** | `project_main_language` 是"项目主要语言"，不是"被评审文件的语言" |
| 期望输出 | **有，是一条自然语言评论** | `note` 是评论正文。注意：这里**没有**"改写后的正确评论"这类目标文本 |
| 严重级别 | **没有** | 无 `severity` 字段。上游 Codex reviewer 的 MCP server 有 `severity`，但框架 README 写明它"archived only, not used in evaluation" |
| 行号 | **有** | `from_line` / `to_line` 是闭区间 |
| 解释 | **没有独立解释字段** | `note` 本身就是"意见"，没有"为什么错"的标注理由 |

---

## 3. 它评测的是什么对象（第 3 问）

【已核验】**它是「评论正确性判别」（reflection），不是"检出式规则"，也不是"生成式 code review"。**

三条判据，都来自取到的记录：

1. **数据集里没有代码**（§2.3）：没有 diff 就无法做"给 diff → 产出评论"的生成式评测，也无法做"给代码 → 判定规则命中"的检出式评测。
2. **卡片自己说得很清楚**（第 18 行原文）：`designed for automated code review reflection models, primarily aiming to evaluate the extent to which a model can intercept low-quality review comments`——评测目标是"拦截低质量评审意见"的能力。
3. **label 的定义**（卡片第 43 行原文）：`"Whether the review comment is correct or not, 1 for correct and 0 for incorrect"`——监督信号是**评论本身的正确性**。

对照上游论文：论文评的是**生成侧**（给 PR 生成评审意见，再与 Ground Truth 匹配算 P/R/F1，200 个 PR 为评测单位），而 HF 上这一份是**判别侧**的子产物（2145 条评论 + 正确性标签）。**两者不是同一个任务，不能互相代替。**

**这决定它能不能喂进我们（门禁型）的平台：不能直接喂。** 我们平台的判定入口是"文件 + 显式上下文 → Decision（哪条规则命中/是否阻断）"，而这份数据集的每个样本要回答的是"这条已经写好的人类/模型评论对不对"。输入形态（缺代码载体）与输出语义（评论级二分类）**两头都不对接**。

---

## 4. 标签怎么来的（第 4 问，重点）

### 4.1 论文原文（整段，Appendix B.1 【已核验】 "Review Completion and Expert Annotation"）

来源：arXiv HTML **v3**（最新版，2026-01-30），段首 `Subsequently, we submitted this set to over 80 senior software engineers...`：

> Subsequently, we submitted this set to over 80 senior software engineers with more than two years of experience for rigorous Human Annotation. The annotation process covered three core dimensions: verifying the correctness of the review comments, categorizing issue types according to Table 7, and defining the scope of context dependency. The annotation workforce consisted of a Core Expert Team of 6 members and a General Annotation Pool comprising the remaining participants. The annotation process was divided into three rounds: The first two rounds were conducted by the General Annotation Pool using a double-blind mechanism, where each comment was independently annotated by two different individuals, and task allocation was strictly matched to the annotators' programming language expertise. The third round was conducted by the Core Expert Team, which was responsible for discussing and adjudicating conflicting results from the first two rounds and determining the final annotations. Through this "human-machine collaborative" multi-round annotation workflow, we ensured that the final evaluation benchmark possesses both high coverage and high accuracy.

同段前半（候选集是怎么造出来的）：

> ... we employed LLM generation techniques to comprehensively augment the review comments. To mitigate single-model bias and ensure diversity, we constructed a generation matrix comprising six mainstream open-source and proprietary models. These models generated review comments in parallel through two heterogeneous frameworks: an Internal Review System and an Open-Source Agent System (Claude Code). All generated comments underwent semantic de-duplication before being merged with the previously augmented human review comments, forming a candidate set for verification. This semantic de-duplication was performed using **Qwen3-235B-A22B-Thinking-2507**. Specifically, all review comments were first grouped based on their repository, Pull Request (PR), file path, and the specific Diff Hunk addressed. Within each group, comments underwent pairwise comparison via the LLM, and duplicates were removed based on the comparison results. ... We use the election of results running 5 times of judgement.

正文 §3.2 的对应段（v3）：

> ... we enlisted 80 senior software engineers (each with over two years of experience) to perform rigorous Human Annotation. Annotators validated the correctness of the comments and categorized the issue types. ... This step yielded a total of 1,505 review comments, including 391 augmented from original reviews and 1,114 generated by LLMs, representing a 285% increase in problem coverage.

**逐条回答题面的四个小问：**

| 小问 | 答案 | 依据 |
| --- | --- | --- |
| 几个人标？ | 候选集交给 **80 余名**有 2 年以上经验的工程师；组织上分 **6 人核心专家组** + 其余"通用标注池"。每条评论第一、二轮各由 **2 个不同的人**独立标注 | 上面原文 |
| 是不是 LLM 生成？ | **候选内容部分是**：6 个模型 + 两套框架（内部评审系统 / Claude Code）生成，去重用的也是 LLM（Qwen3-235B-A22B-Thinking-2507）；**最终 label 不是 LLM 判的**，是人工裁决 | 上面原文 |
| 有没有人工复核？ | **有，三轮**：前两轮双盲、双人独立；第三轮核心专家组讨论并裁决前两轮的冲突，定最终标注 | 上面原文 |
| 有没有 IAA / κ？ | **没有。** 论文 v1 与 v3 全文中 `kappa` / `IAA` / `inter-annotator` / `agreement` / `Cohen` / `Fleiss` 的命中数**都是 0**。有"双人独立 + 第三人裁决"的流程描述，但**没有报告任何一致性系数，也没有报告冲突率** | 全文检索，见 E07/E08 |

**这是一条重要的负面结论**：流程描述支持"做过交叉标注"，但**没有任何可核验的数字**说明两个标注者的分歧有多大。引用这篇数据集时必须把"有双盲流程"与"报告了一致性"分开写。

### 4.2 640 条"错误"标签：论文里没有流程描述

- 论文 v3 全文检索：`reflection` 0 次、`huggingface` 0 次、`negative` 0 次、`640` 0 次、`positive sample` 0 次。`incorrect` 出现 7 次，全部在"模型的错误评论"这类案例分析语境里（Appendix D: `case studies illustrating correct and incorrect review comments generated by models`），**不是在讲一套把评论判为"错误"并保留下来的标注协议**。
- 论文只描述了"最终得到 1,505 条"，没有说被淘汰的候选评论是否保留、以什么标准判为"错"、由谁裁决。
- 因此：**HF 数据集里 640 条 label=0 的构造方法，目前只有数据集卡与仓库 README 的声明，没有可追溯的流程文档。** 这一条按本仓证据纪律记 **【待核验】**。（找过的位置：arXiv abs 页与 HTML v1/v3 全文、HF 卡片与中文卡、GitHub 仓库 README / README.zh-CN / CONTRIBUTING / CONTRIBUTORS / docs/metrics.md / evaluation/README.md、仓库全量文件树。）

### 4.3 数值对账：HF 的 label=1 就是论文的 1505 条 Ground Truth【已核验】

这不是"看起来一致"，是三个分布**逐个数字相等**：

| 维度 | 论文（v3 原文） | HF `label=1` 实测（n=1505） |
| --- | --- | --- |
| 上下文级别（Table 1） | Diff 754 / File 518 / Repo 233 | Diff Level 754 / File Level 518 / Repo Level 233 |
| 问题类目（Table 7） | Security 53 / Code Defect 709 / Maintainability 626 / Performance 117 | Security Vulnerability 53 / Code Defect 709 / Maintainability and Readability 626 / Performance 117 |
| 来源 | 391 augmented from original reviews + 1,114 generated by LLMs | `is_ai_comment=false` 391 + `is_ai_comment=true` 1114 |

label=0 一侧（n=640）的分布，供对照：上下文 Diff 263 / Repo 151 / File 226；类目 Code Defect 313 / Maintainability 279 / Security 21 / Performance 27；`is_ai_comment` False 157 / True 483。**其中 483 条（75.5%）是 AI 生成的评论被判为"错误"。**

### 4.4 judge 是什么

- **HF 数据集本身没有 judge**：仓库里只有 `dataset.json` 与两份 README，没有评分脚本。
- **上游仓库里的 judge 是给另一份数据用的**：`evaluation/judge.py` 服务于 `dataset/positive_samples.json`（200 个 PR 的 Ground Truth），做法是四阶段匹配 `path → side → line(k=1) → semantic`：
  - 前三个阶段是确定性规则（路径字符串相等、side 相等、行号区间重叠或距离 ≤ k）；
  - 第四阶段 `match_semantic()` 是 **LLM judge**：用 OpenAI 兼容客户端调 `JUDGE_MODEL`，prompt 只问 `Determine whether two given review comments express the same concern or suggestion`，**不引用任何标准、不给 CWE、不给规则码**，判定方式是从回复文本里找 `yes/similar/same/identical/equivalent` 关键字。
  - **缺 `JUDGE_API_KEY` 或 `JUDGE_USE_MOCK=true` 时静默切到 Mock**：`difflib.SequenceMatcher(...).ratio() >= 0.4` 或 词集合 `jaccard >= 0.3` 就算"语义相同"。mock 与 LLM 两种模式的结论会被记进同一个指标字段，只有控制台会打印用的是哪种模式。
  - 单条裁判调用失败被 catch 住并**当作"不相似"**（`return {"is_similar": False, ...}`），即裁判不可用会把分数往下压，而不是失败关闭。
- 另一处"judge"是**去重**用的：论文 §B.1 的 LLM 两两比较 prompt（Figure 9），模型 Qwen3-235B-A22B-Thinking-2507，跑 5 次取多数（原文 `We use the election of results running 5 times of judgement`）。它是"两条评论是不是同一个问题"的去重裁判，**不是**正确性裁判。

---

## 5. 指标（第 5 问）【已核验】

### 5.1 论文口径（生成侧，200 个 PR 为评测单位）

论文 §4.1：`We evaluate the performance of various ACR approaches against AACR-Bench using the common three matrics, i.e., Precision, Recall and F1-score.` 流程见 §C.1：clone 仓库、同步 base 与 target 两版、用 GitPython 抽全部 diff hunk、逐个 hunk 生成评论、再与 Ground Truth 匹配。所有模型 `Temperature=0.7`、`Top_p=0.95`、`Top_k=20`。

论文 Table 3 的分数区间（5 个模型 × 4 种上下文/检索设置，20 行全表）：

| 指标 | 最小值 | 最大值 | 取到极值的行 |
| --- | --- | --- | --- |
| Recall (%) | **2.99** | **47.24** | GPT-5.2 Agent / GPT-5.2 Embedding |
| Precision (%) | **5.10** | **39.90** | Deepseek-V3.2 Embedding / Claude-4.5-Sonnet Agent |
| F1 (%) | **4.59** | **16.12** | GPT-5.2 Agent / Claude-4.5-Sonnet Agent |

另外三种口径（论文 Table 4/5/6）按上下文级别、语言、方法拆 Recall，以及 Appendix C.2 的附加统计；我没有复算这些数字，只登记它们存在于论文正文。

**注意量纲**：这些 Precision/Recall 的分母是"1,505 条 Ground Truth"，匹配靠 judge（LLM 或 mock）——**它不是规则的精确率/召回率**。

### 5.2 仓库自带框架的口径

`evaluation/README.md` 的指标定义（`docs/metrics.md`）：`positive_match_rate = positive_matches / total_generated`（称 Precision）、`positive_recall_rate = positive_matches / positive_expected_nums`（称 Recall）、`unmatched_rate = unmatched_count / total_generated`（Noise Rate），另有 line-level 的两个同形指标。框架同时输出 semantic 与 line-based 两套 P/R/F1，并把"没有结果文件的样本"计入 `missing_instances` 且**排除出分母**。

### 5.3 榜单

- **没有公开 leaderboard。** GitHub 仓库全量文件树（53 项，`truncated: false`）里没有榜单文件；对仓库做 `leaderboard` 的代码搜索命中 **0**；`LEADERBOARD.md`、`docs/leaderboard.md` 均 404。
- 现有分数**只有论文里的表**（§5.1）。没有"榜单上现有分数区间"这种东西可引——本文不编。
- HF 数据集页面侧也没有评估结果字段（`/info` 的 `description` / `citation` 都是空串）。

---

## 6. 可否直接用（第 6 问）

### 6.1 许可与规模

| 项 | 结论 | 依据 |
| --- | --- | --- |
| 运行期取用 | **可以**（公开、非 gated、非私有，直接 HTTPS 就能拿到） | HF API `private/gated/disabled` 均为 false |
| 入库（提交进本仓） | **暂不可以**：许可只有卡片声明，HF 侧无 LICENSE 文件 | §1.2；本仓 `eval-datasets.yaml` 的口径是 `license_verified: false` 时不得入仓、不得分发 |
| 数据下载成本 | **很小**：`dataset.json` 2,101,497 字节（2.00 MiB），HF 转好的 parquet 539,972 字节（527 KiB） | `/size`、`/parquet`、实测下载 |
| 真正的成本 | **在代码侧**：2145 条评论来自 200 个 PR、50 个仓库。用 `gh api repos/<r> --jq .size` 逐个取 GitHub 报告的仓库大小，50 个仓库合计 **43,150,387 KB ≈ 41.15 GiB**（最大 ClickHouse 13.2 GB、nextcloud 7.3 GB、FreeCAD 2.9 GB）。这是全量克隆的量级；浅克隆/部分克隆会小得多，但我**没有实测克隆耗时**，此处只登记量级 | gh CLI 逐仓库查询，50/50 成功 |
| revision 钉得住吗 | **钉得住**：数据集侧用 revision `47be1d6d...`；代码侧用每条记录自带的两个 commit sha。抽样 4 个 PR（FreeCAD / typescript-go / PowerShell / SDL）的 8 个 commit 全部可解析（HTTP 200，带提交时间），说明引用的 commit 仍在 | GitHub API `/commits/<sha>`，8/8 通过 |

### 6.2 两个实测缺陷（库内必须先知道）【已核验】

**缺陷 A：跨产物标签冲突（恰好 1 条）**

把 HF `dataset.json` 与上游仓库的 `dataset/positive_samples.json`（正例）/ `dataset/negative_samples.json`（负例）按 `(pr_url, note.strip(), path, from_line, to_line)` 做集合比对：

| 比对 | HF 独有 | 上游独有 | 交集 |
| --- | --- | --- | --- |
| HF label=1（1505）vs 正例文件（1506 条评论 / 1506 个键） | 0 | 1 | 1505 |
| HF label=0（640）vs 负例文件（639 条评论 / 639 个键） | 1 | 0 | 639 |

即：**上游正例集里那条 HF 没有的评论，恰好以 label=0 出现在 HF 里**。定位到具体记录：

> `https://github.com/dbeaver/dbeaver/pull/37564` · `plugins/org.jkiss.dbeaver.model.rcp/src/org/jkiss/dbeaver/model/navigator/DBNResource.java` · 428-428 · "Throwing `RuntimeException` on `CoreException` in the `InputStream` adapter handling violates `IAdaptable`'s contract. ..."（人工评论，`is_ai_comment=false`，`source_model=""`，Code Defect，Repo Level）

原因由上游 commit 历史直接给出：

- `665a815`（2026-08-05，"feat: add comment in dbeaver pr 37564"）：往正例文件**新增**一条 GLM-5.2 生成的评论（+12/−1），位置正是 DBNResource.java:428。
- `dae8647`（2026-08-24，"feat: remove negative comment in dbeaver pr 37564 and adjust content in positive comment"）：从**负例**文件删掉上面那条人工评论（−11 行），同时在**正例**文件里把 GLM-5.2 那条**替换**成这条人工评论（`is_ai_comment` true→false、`source_model` GLM-5.2→""、`context` File Level→Repo Level）。
- HF 快照停在 2026-02-02，没有跟随这次挪动：HF 里既没有那条 GLM-5.2 评论（全文 0 条命中），那条人工评论仍然是 label=0。

**也就是说：同一条评论，在上游当前正例集里是"正确"，在 HF 快照里是"错误"。** 谁要用这份数据，必须先决定信哪一侧。（顺带说明：这不是我比对口径造成的假象——两个文件都已用 git blob sha1 认证过字节来源。）

**缺陷 B：上游声明的 sha256 与实际内容不符，且会让自带 converter 直接失败**

- `evaluation/benchmark/AACR-Bench/positive_samples.meta.json`（322 字节，blob `c7718e00...`，唯一一次提交 `9db9966` @ 2026-08-03）内容：
  `{"filename": "positive_samples.json", "url": "https://raw.githubusercontent.com/alibaba/aacr-bench/main/dataset/positive_samples.json", "sha256": "d8683cb240249bc4e0aff6428802bdffa7b7573ace600552cab1cd0cb7e905c9", ...}`
- 实际文件：1,101,548 字节、git blob `62d1b570c74022b5dbbadc54547cfd7ea8f5fa4e`（我用 `sha1("blob <len>\0" + bytes)` 复算并与 tree API 的 blob id 对齐，**逐字节确认我下载的就是仓库内容**），sha256 = `7a4a0e7046ffd1b8f41f951480bbb618d23d38d9f67364f38aabcda121a50be3`。
- 声明的值与实际值**不相等**。我另外试了 7 种可能的规范化（去行尾换行、去全部行尾空白、CRLF 归一、JSON 紧凑序列化、indent=2、indent=2+换行、indent=4），**没有一种能复现声明的哈希**。
- 时间线解释了原因：meta 写于 2026-08-03，数据文件最后改于 2026-08-24（`dae8647`），meta **从未跟随更新**。
- **后果是硬的**：`evaluation/converters/aacr_bench.py` 的 `ensure_raw_file()` 在本地缓存缺失或校验不过时按 meta 的 url 下载，然后比对 sha256，不等就 `raise SystemExit("下载内容校验失败：...")`。所以照 README 的"一键跑"流程走，第一步就会停在下载校验。

### 6.3 要接上我们的平台，具体缺什么

我们平台的判定入口是"**文件 + 显式上下文 → Decision**"（`policy.engine.evaluate`），规则集 43 条、checker 5 类、外部工具证据来自 `tool.ruff` / `tool.mypy` / `tool.pytest`。把这份数据集接上去，缺的是下面这些**具体**东西，不是"需要适配"：

1. **缺代码载体**（最根本）。数据集没有 diff hunk、没有文件内容、没有 PR 标题/描述。要判定必须先：按 `pr_url` 解析 `owner/name` → clone → checkout `pr_source_commit` 与 `pr_target_commit` → 抽出对应 diff hunk 与 `path` 指向的整份文件 → 归一成我们判定器要的工作区树。**这一步是上游 converter 之外我们完全要自己写的东西**，而且它必须能在 200 组 commit 上重放。
2. **缺"评论 → 规则"的连接键**。我们的 Decision 说的是"哪条规则命中"，而这份数据集只有 4 个粗类目（Code Defect / Maintainability / Performance / Security）与自由文本 `note`。**没有 CWE、没有 Ruff/Bandit 码、没有规则 ID、没有 severity**（§7 有实测的 0 命中）。要接就得先写一张**人工映射表**，而这张表本身没有外部依据——按本仓纪律，它只能算"声明"，不能算证据。
3. **缺判定对象的同一性**。label 说的是"这条**评论**对不对"，不是"这段**代码**有没有这个缺陷"。一条被判"正确"的评论，不意味着我们的某条规则应该命中；一条被判"错误"的评论，也不意味着规则不该命中。要算一致率，先得裁定把 label 当作什么——**目前没有一个自然的读法**。
4. **缺额度同构**。我们一次调用产出一个 Decision（allow / allow_with_warnings / block …），这份数据集一个样本产出一个二分类。两者只有在"把 `note` 当成待判证据喂给平台"的人造构造下才可比，而那不是这份数据集设计的用法。
5. **缺评测器**。仓库里没有任何代码消费 `negative_samples.json`（对 `alibaba/aacr-bench` 做 `negative_samples` 代码搜索命中 **0**；全量文件树里只有 `positive_samples.meta.json`，**没有** `negative_samples.meta.json`，该 URL 实测 404）。也就是说 **HF 这份"反思集"没有配套评分脚本**，640 条负例目前是"有标签、无评测"的状态。
6. **缺许可原文**（§1.2）。
7. **缺漂移处置**：上游已改、HF 未跟（缺陷 A），而我们如果要跑，必须先钉住"用哪一侧的哪一版"。

### 6.4 如果还想用：可成立的弱用法（明确标注为建议，不是核验结论）

> 以下是我的**建议**，不是从数据里读出来的事实。

- 把 53 条 label=1 的 Security Vulnerability 评论当作**"人写的安全类问题描述"语料**（不是检出标注），用来检查我们 SEC 规则的 message/解释是否覆盖到同类问题——但必须显式人工映射，且**不得进 GV-01/GV-02 的分母**（本仓 `eval-datasets.yaml` 第 4 条纪律：片段级/非行级标注不得进这两个指标的分母）。
- 640 条负例可以作为"**难负例**"灵感来源（真实 PR 上模型说错的话长什么样），但同样不能当检出标签。

---

## 7. 同源风险（第 7 问）【已核验】

**结论：不同源，而且没有可对齐的连接键；即使算出一致率也不能读成"规则对"。**

### 7.1 我们这一侧的规则来源（本仓可核验）

- `knowledge/corpus.yaml` 登记的镜像数据集：`owasp-cheatsheets`（CC BY-SA 4.0）、`python-pep-code-style`（PEP 8 / PEP 257）、`dotnet-design-guidelines`、`google-eng-practices`、`gitlab-code-review`、`dora-capabilities`。
- `policies/**` 共 43 条规则，`checker` 分布：`style_lint` 39、`missing_docstring` 1、`failing_tests` 1、`missing_tests` 1、`forbidden_dependency` 1。
- 证据工具：`validation/validators.yaml` 声明 `tool.ruff` / `tool.mypy` / `tool.pytest`；`validation/ruff.toml` 的 `select` 把 Ruff 的 E/F/D/S 码逐条绑到规则（例：`E501 → STYLE-001`、`S105/S106/S107 → SEC-004`、`S608 → SEC-008`）。
- 所以我们的"标签"本质是：**PEP 8 / PEP 257 与 OWASP Cheat Sheet 的条文 + Ruff/Bandit 系码的具体实现**。

### 7.2 AACR-Bench 这一侧的标签来源

- 标签是人工对"评论是否正确"的裁决（§4.1），类目是 4 个问题域，**不绑定任何规则集或标准**。
- 评论内容是 6 个 LLM 与真实 PR 评审意见（§2.1、§4.3）。

### 7.3 实测：两边没有连接键【已核验】

对 2145 条 `note` 做正则扫描（脚本 `.tmp/aacr-bench/codescan.py`）：

| 模式 | 命中条数 | 说明 |
| --- | --- | --- |
| `CWE[-\s]?\d{1,4}` | **0** | 没有任何 CWE 编号 |
| `\bS\d{3}\b`（Bandit 系） | **0** | 没有任何 Bandit 码 |
| `\bD\d{3}\b`（pydocstyle 系） | **0** | 没有任何 docstring 码 |
| `OWASP` / `bandit` / `pycodestyle` / `PEP[-\s]?8` | **0** | 没有任何标准名 |
| `\bE\d{3}\b` | 5（label=1 中 4、label=0 中 1） | **都是被评审源码片段里的 `# noqa: E501` 之类内容**，不是标签 |
| `\bF\d{3}\b` | 1（label=1） | 是一条评论在讨论 `F401/F841` 这两条 Ruff 规则本身，不是标签 |
| `\bruff\b` | 2（各 1） | 同样是在讨论源码里的 Ruff 配置，不是标签 |

对应的 `category` 只有 4 个粗类目，与我们的码集合**没有映射**。

### 7.4 所以"一致率高 = 规则对"不成立，三条理由

1. **判据对象不同**：它判"这条评论对不对"，我们判"这段代码违反了哪条已声明规则"。两者可以同时都对又互不蕴含。
2. **没有连接键**：任何映射都是人写的，映射本身没有外部依据；用一张自造的映射表算出一致率，再用这个一致率去证明规则对，是**自证**（本仓 `eval-datasets.yaml` 第 1 条纪律：不许自证）。
3. **可能的"反向同源"**（**推论，不是数据**）：label=1 的 1505 条里有 1114 条本身就是 LLM 生成的评论；label=0 的 640 条里 483 条也是。如果我们拿某个模型去做这个判别、或者拿它来校准我们规则的解释文本，一致率高有可能只反映"我们和那几个生成模型共享同一套常见说法"，而不是"规则被独立验证了"。**这一条是从来源分布推出的风险提示，我没有做实验去验证它。**

---

## 8. 证据索引

全部条目访问日期 **2026-10-07**。原始响应落在 `.tmp/aacr-bench/raw/`。

| 编号 | 命令 / URL | 关键原文摘录 |
| --- | --- | --- |
| E01 | `https://huggingface.co/api/datasets/Alibaba-Aone/aacr-bench` | `"id":"Alibaba-Aone/aacr-bench","sha":"47be1d6df1e7faf222cf531587772d92f79fe6b2","private":false,"gated":false,"disabled":false"`；`"downloads":916,"likes":13`；`"siblings":[... ".gitattributes","README.md","dataset.json","readme_cn.md"]` |
| E02 | `https://huggingface.co/api/datasets/Alibaba-Aone/aacr-bench/refs` 与 `/commits/main`、`/tree/main?recursive=true` | `"branches":[{"name":"main","targetCommit":"47be1d6df1e7faf222cf531587772d92f79fe6b2"]`；5 个 commit 全部 2026-02-02；文件清单 4 项 |
| E03 | `https://datasets-server.huggingface.co/splits?dataset=Alibaba-Aone%2Faacr-bench` | `{"splits":[{"config":"default","split":"train"}],"pending":[],"failed":[]}` |
| E04 | `https://datasets-server.huggingface.co/size?dataset=Alibaba-Aone%2Faacr-bench` | `"num_bytes_original_files":2101497,"num_bytes_parquet_files":539972,"num_bytes_memory":1469552,"num_rows":2145,"num_columns":16` |
| E05 | `https://huggingface.co/datasets/Alibaba-Aone/aacr-bench/resolve/main/dataset.json`；本地解析 | 顶层 JSON **数组**，2145 个元素，所有记录键集合相同；`label=1 → 1505`，`label=0 → 640`；sha256 `0804505f...a86` |
| E06 | `.../first-rows?dataset=...&config=default&split=train` | `"features"` 16 项（见 §2.1）；`"truncated":true`，100 行，`row_idx` 0..99；首页 100 行 label 全为 1 |
| E07 | arXiv v1 HTML `https://arxiv.org/html/2601.19494v1`（2026-01-27）→ 纯文本后全文计数 | `kappa/IAA/inter-annotator/agreement/Cohen/Fleiss` 命中各 **0**；`review completion and expert annotation` 段见 §4.1 |
| E08 | arXiv v3 HTML `https://arxiv.org/html/2601.19494v3`（2026-01-30） | 同上：`kappa` 0 / `IAA` 0 / `inter-annotator` 0 / `agreement` 0 / `Cohen` 0 / `Fleiss` 0；`reflection` 0 / `huggingface` 0 / `negative` 0 / `640` 0 |
| E09 | arXiv v3 正文 §B.1 | "…over 80 senior software engineers… Core Expert Team of 6 members… first two rounds… double-blind… each comment was independently annotated by two different individuals… third round… adjudicating conflicting results…"（全文见 §4.1） |
| E10 | arXiv v3 Table 1 / Table 7 | Table 1：Diff 754 / File 518 / Repo 233；Table 7：Security Vulnerability 53 / Code Defect 709 / Maintainability & Readability 626 / Performance Issue 117 |
| E11 | 本地对 `dataset.json` 的 `label` 分组统计 | label=1：context File 518 / Diff 754 / Repo 233；category 53 / 709 / 626 / 117；`is_ai_comment` False 391 / True 1114 |
| E12 | HF 卡片 `.../raw/main/README.md`（2422 字节，61 行）与 `readme_cn.md`（2107 字节） | 第 18 行："…2,145 code review comments, consisting of 1,505 expert-verified correct comments and 640 incorrect comments."；第 43 行 label 定义原文 |
| E13 | `https://raw.githubusercontent.com/alibaba/aacr-bench/main/evaluation/judge.py`（10621 字节，266 行） | `USE_MOCK_LLM = os.getenv(...)=="true" or not os.getenv(config.JUDGE_API_KEY_VAR)`；`_mock_semantic_match` 的 `sequence_ratio >= 0.4 or jaccard >= 0.3`；`except Exception ... return {"is_similar": False}` |
| E14 | `.../evaluation/README.md`（21123 字节） | 第 317-321 行：四阶段匹配 `path → side → line(k) → semantic`；"Samples with missing result files are counted in `missing_instances` and excluded from metric denominators" |
| E15 | 本地正则扫描 `.tmp/aacr-bench/codescan.py` | CWE 0 / `S\d{3}` 0 / `D\d{3}` 0 / OWASP 0 / bandit 0 / pycodestyle 0；`E\d{3}` 5 条、`F\d{3}` 1 条均是源码片段内容 |
| E16 | 集合比对 `.tmp/aacr-bench/xcheck2.py`、`conflict.py` | label=1 vs 正例：HF 独有 0 / 上游独有 1 / 交集 1505；label=0 vs 负例：HF 独有 1 / 上游独有 0 / 交集 639；冲突键 = dbeaver#37564 DBNResource.java:428-428 |
| E17 | GitHub API `/commits/dae8647`、`665a815`；`?path=...` 历史 | `dae8647`（2026-08-24）"feat: remove negative comment in dbeaver pr 37564 and adjust content in positive comment"，负例 −11 行、正例 +4/−4；`665a815`（2026-08-05）"feat: add comment in dbeaver pr 37564" 正例 +12/−1 |
| E18 | `.../evaluation/benchmark/AACR-Bench/positive_samples.meta.json` | `"sha256":"d8683cb240249bc4e0aff6428802bdffa7b7573ace600552cab1cd0cb7e905c9"`；该文件历史只有 1 个 commit `9db9966` @ 2026-08-03 |
| E19 | `.../dataset/positive_samples.json` 实测 + git blob 认证 | 1,101,548 字节；`sha1("blob <len>\0"+bytes) = 62d1b570...` 与 tree API 的 blob id 相等；sha256 = `7a4a0e70...be3` ≠ 声明的 `d8683cb2...`；8 种规范化均无法复现声明值 |
| E20 | `https://huggingface.co/datasets/Alibaba-Aone/aacr-bench/resolve/main/LICENSE` 与 `/raw/main/LICENSE` | 两个 URL 均 **404 `Entry not found`** |
| E21 | `https://api.github.com/repos/alibaba/aacr-bench`；`LICENSE` blob `261eeb9e...` | `"license":{"spdx_id":"Apache-2.0"}`；LICENSE 11357 字节，首行 `Apache License / Version 2.0, January 2004`；仓库 ★238，push 于 2026-08-24T08:20:46Z |
| E22 | `https://datasets-server.huggingface.co/info?dataset=Alibaba-Aone%2Faacr-bench` | `"license":"","citation":"","description":""`；`"download_checksums":{"hf://datasets/Alibaba-Aone/aacr-bench@47be1d6.../dataset.json":{"num_bytes":2101497,"checksum":null}}` |
| E23 | `https://datasets-server.huggingface.co/parquet?dataset=...` | `"url":".../resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet","size":539972` |
| E24 | GitHub API `/commits/<sha>` 抽样 4 个 PR 的 8 个 commit | 8/8 返回 200（例：FreeCAD `0c65673a...` 2025-03-02、`a050e422...` 2025-02-05；typescript-go `15def023...` 2025-07-03、`ae447d3b...` 2025-07-03） |
| E25 | `gh api repos/<r> --jq .size` × 50 个仓库 | 合计 43,150,387 KB；最大 ClickHouse/ClickHouse 13,197,448 KB |
| E26 | 代码搜索 `search/code?q=negative_samples+repo:alibaba/aacr-bench` | `total_count = 0`；`huggingface` 命中 2，都只在 README.md / README.zh-CN.md |
| E27 | arXiv abs 页 `https://arxiv.org/abs/2601.19494` | 三个版本 [v1] 2026-01-27 / [v2] 2026-01-29 / [v3] 2026-01-30；`License: CC BY 4.0` |

---

## 9. 【待核验】清单（试过的位置与返回码）

| 事项 | 状态 | 试过的位置与结果 |
| --- | --- | --- |
| 640 条 label=0 的标注流程（谁判的、几人、有无复核、有无一致性） | **【待核验】** | arXiv v3/v1 全文（`negative`/`640`/`reflection` 命中 0）；HF 卡片与中文卡（只声明数量）；仓库 `README.md` / `CONTRIBUTING.md` / `CONTRIBUTORS.md` / `docs/metrics.md` / `evaluation/README.md`（均只讲正例与贡献流程）；**上游 GitHub 仓库**全量文件树 53 项（`truncated:false`）——**没有**找到描述 |
| 标注者间一致性系数（κ / Fleiss / IAA） | **论文中不存在（负面结论已核验）** | arXiv v1 与 v3 全文计数均为 0；这不是"没取到"，是**取到了全文且里面没有** |
| 公开 leaderboard / 榜单现有分数区间 | **不存在（已核验）** | 仓库全量文件树无榜单文件；`search/code?q=leaderboard` = 0；`LEADERBOARD.md` 与 `docs/leaderboard.md` 均 404；HF `/info` 无评估结果字段 |
| `negative_samples.meta.json` | **不存在** | `https://raw.githubusercontent.com/alibaba/aacr-bench/main/dataset/negative_samples.meta.json` → **404 Not Found**；文件树里也只有 `positive_samples.meta.json` |
| HF 侧 LICENSE 文件 | **不存在** | `/resolve/main/LICENSE` → 404；`/raw/main/LICENSE` → 404；文件树只有 4 个文件 |
| `README_cn.md`（大写 CN） | **不存在** | `.../raw/main/README_cn.md` → **404 `Entry not found`**；实际文件名是 `readme_cn.md`（200，2107 字节） |
| 非 train 的 split | **不存在** | `/first-rows?...&config=test&split=test` → 404 `{"error":"Not found."}`；`/splits` 只列 `default/train` |
| 50 个仓库的实际克隆耗时/浅克隆体积 | **【待核验】** | 只取到 GitHub API 报告的仓库大小（合计 ≈41.15 GiB），**没有实测克隆**；浅克隆会显著更小但未测 |
| `pr_source_commit` / `pr_target_commit` 与 base/head 的严格对应关系 | **【待核验】** | 上游 converter 把 `source_commit → base_commit`、`target_commit → head_commit`；但我抽样 4 个 PR 里 FreeCAD 一条的 source commit 提交时间（2025-03-02）**晚于** target（2025-02-05），与"source=base/target=head"的朴素读法不符。4 个样本不足以定性，故不作结论 |

**工具面说明**：本机 PowerShell 的 `Invoke-WebRequest` / .NET HTTP 不可用，全部 HTTP 取证走 Python `urllib`；GitHub 侧另用已认证的 `gh` CLI。

---

## 10. 这份分析不能证明什么

1. **没有证明 640 条"错误"标签是对的**。相反，已证明其中**至少 1 条**在上游当前版本里被改判为"正确"（dbeaver#37564）。其余 639 条我**没有**逐条复核，也没有能力复核（需要人工读代码）。
2. **没有证明 1505 条"正确"标签是对的**。我只证明了它与论文 Table 1/Table 7/来源分布三个数字吻合——**数字吻合不等于标注正确**，也不等于我复核过任何一条评论的技术内容。
3. **没有验证论文的 P/R/F1 分数**。§5.1 的区间只是"论文表里写了这些数"，我没有重跑任何模型，也没有复算任何一行。
4. **没有评测过 `evaluation/` 这套框架能不能跑起来**。我只读了它的源码与 README，发现了声明的 sha256 与实际不符会让自动下载校验失败（静态推理 + 哈希实测），**没有真去执行它**（它需要 openai 依赖与 API key，且不属于本任务写域）。同理，我没有真正 clone 过那 50 个仓库。
5. **没有证明许可不可用**。我只证明了"HF 侧没有 LICENSE 文件、许可只在卡片声明里"。Apache-2.0 声明本身是否覆盖这份数据副本，需要与上游确认，我不能替它回答。
6. **没有证明"标签与我们的规则不同源"之外的东西**。§7 的 0 命中是对 `note` 文本的正则扫描结果，它只说明**文本里没有这些标识符**；它不能排除"某些评论在语义上正好对应我们某条规则"——只是没有连接键可以证明这件事。
7. **没有证明数据集有偏或无偏**。我给出了实测分布（语言、类目、上下文、来源模型），但没有做任何代表性分析：50 个仓库是按论文自述的"星标 + 关闭 PR 排名前 2000 里取每语言新增星标前 5"选的，我没有独立复核这个抽样过程，也没有拿它和 GitHub 总体分布比过。
8. **没有证明它"不适合"我们的平台**。§3 与 §6.3 说的是"输入形态与输出语义不对接、且缺连接键"，这是**接口层面的结论**；如果愿意承担人工映射的成本，弱用法仍然可能（§6.4），只是那已经不是"用这份数据集验证我们的规则"了。
9. **没有穷尽上游**。我只看了仓库 `main` 的当前状态、6 个相关文件的提交历史、以及 HF 侧的全部公开端点；仓库的非默认分支、issue/讨论区、以及未公开的论文附录我没有查。
10. **HF 侧只有一份快照**。该数据集仓自 2026-02-02 起没有新 commit，所以"HF 与上游不一致"这个判断的有效期到下一次 HF 更新为止；引用时请连带引用本文的 revision `47be1d6d...`。
