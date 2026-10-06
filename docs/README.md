# docs/：三类文档，三条规矩

这个目录只分三类，**先看类别再找文件**：

```text
docs/
├── mirrors/    第三方离线镜像：逐字复制上游原文，只读；既是追溯来源，也是检索语料（Raw Reference）
├── project/    本项目自己写、自己维护的文档：和代码一起评审、一起演进
└── 生成物      由内容源重新生成的产物（架构讲解 notebook 及其 .py 版本）：改内容源，不改产物
```

分类的理由不是"谁写的"，而是**能不能改**：

| | `docs/mirrors/**` | `docs/project/**` | 生成物 |
| --- | --- | --- | --- |
| 内容来源 | 上游站点原文（`tools/mirror_docs.py` 等流水线抓取） | 本项目作者手写 | 由 `cells.py` 内容源生成 |
| 可否手改 | **不可以**。改了会在下次镜像同步时被覆盖，哈希门禁也会漂移 | 可以，且必须与相关代码/配置同步改 | **不可以**。手改会在下次生成时丢失 |
| 身份标识 | `dataset`（如 `owasp-cheatsheets`）+ 镜像内相对路径 | 仓库相对路径 | 章节目录 + 同编号的 `cells.py` |
| 谁在引用 | `knowledge/corpus.yaml`、`policies/**` 的 `source.path`、镜像流水线 | 生成器、文档内部链接、`README.md` / `AGENTS.md` | 生成器与 `--check` 门禁 |
| 文本约定 | 不按本仓库排版约定改写（行尾空白来自上游） | 必须过 `tools/check_text_conventions.py` | 同 project：产物也要过文本约定门禁 |

## docs/mirrors/：6 套镜像

| 目录 | dataset 名（**不要改名**） | 内容 | 文档数 |
| --- | --- | --- | --- |
| mirrors/google-eng-practices/ | `google-eng-practices` | Google 工程实践（代码评审） | 14 |
| mirrors/gitlab-code-review/ | `gitlab-code-review` | GitLab 代码评审规范 | 20 |
| mirrors/python-pep-code-style/ | `python-pep-code-style` | PEP 8 / PEP 257 及配套 PEP | 12 |
| mirrors/dotnet-design-guidelines/ | `dotnet-design-guidelines` | .NET Framework 设计准则 | 49 |
| mirrors/dora-capabilities/ | `dora-capabilities` | DORA 软件交付能力模型 | 37 |
| mirrors/owasp-cheatsheets/ | `owasp-cheatsheets` | OWASP Cheat Sheet Series | 124 |

文档数 = 镜像内 `.md` 文件去掉镜像自带的 `README.md` / `STRUCTURE.md`。

每个镜像自带三件索引，**都是相对镜像根**的，移动镜像目录不影响它们：

- `manifest.json`：逐页 `local_path` / `source_url` / `title` / `sha256` / `bytes` / `fetched_at`；
- `README.md`：来源、抓取时间、许可、收录范围与取舍；
- `STRUCTURE.md`：层级、归属与交叉引用关系。

## docs/project/：本项目现状与提案

| 目录 | 内容 | 入口 |
| --- | --- | --- |
| project/architecture/ | 技术架构说明三件套（术语与口径 / 功能清单 / 使用说明）+ 规则文档转化为规则 + 规则转化覆盖报告 + tech-detail 十份可执行讲解 | [README.md](project/architecture/README.md) |
| project/engineering-policy-platform/ | **平台现状**（00–03 愿景 / 架构 / 数据源 / 技术选型）、**未完成工作与复审清单**（`04-open-work.md`）、测试策略与验收矩阵；设计提案见 [设计提案索引](project/engineering-policy-platform/designs/README.md) | [README.md](project/engineering-policy-platform/README.md) |
| project/rule-effects/ | 规则效果演示与多违规案例检测报告（本地产出，非镜像） | — |
| project/reviews/ | 与外部同类项目的对比复核记录（带证据等级与降级清单）。**已纳入版本库跟踪** | [open-code-review-对比报告.md](project/reviews/open-code-review-对比报告.md) |

按阶段与按轮次的**过程记录已下线**（Phase 0–9 的实施记录、复核与修复轮记录、学习手册）。
仍然影响未来开发的结论、缺口与复审时间全部收在
[project/engineering-policy-platform/04-open-work.md](project/engineering-policy-platform/04-open-work.md)，
历史编号的含义见它的附录对照表。

## 生成物

`project/architecture/tech-detail/<编号>-<名称>/*.ipynb` 与同名的 `.py` 是**生成物**——
那里**一章一个目录**，每章一份图 + 一份同编号的讲解：内容源在同一章的 `cells.py`，由
`python docs/project/architecture/tech-detail/build_notebooks.py` 生成并逐单元执行校验
（`--check` 是 CI 门禁）。手改 notebook 会在下次生成时丢失。

按阶段的学习手册与它的生成管线（`docs/project/learning/**`、`tools/build_learning_notebook.py`、
`tools/phase{6,7,8}_cells.py`、`tools/run_notebook_in_kernel.py`）已于 2026-10-06 一并下线；
`tools/check_notebook.py` 保留，现在只服务上面这套 tech-detail 讲解 notebook。

## 改路径时的连带清单（迁移后最容易漏的地方）

**动一个镜像目录**（`docs/mirrors/<镜像名>/`）时，必须同步：

1. `knowledge/corpus.yaml` 里该 dataset 的 `mirror:` 与 `license_source:`。
   `entries` 是**镜像内相对路径**，不要动；`dataset` 名是权限与溯源的稳定标识，**不要改名**。
2. `policies/**/*.yaml` 里 `source.path`（由该镜像提炼的规则）——它必须指向真实存在的文件。
3. 镜像流水线的输出目录：`tools/mirror_docs.py` 的 `SITES[*]["out"]`、
   `tools/owasp_cheatsheets/{03_build,04_index,05_verify}.py` 的 `OUT`。
4. 两个扫描器的镜像跳过前缀：`tools/check_text_conventions.py` 与 `tools/secret_scan.py` 的 `MIRRORED_PREFIXES`。
5. 重建索引与评测：`.tmp/retrieval/` 是构建产物，改完重跑下面的命令即可。

**不动**的东西：镜像内部的所有相对链接、`manifest.json` 的 `local_path`、dataset 名、
`tests/fixtures/retrieval_eval/*.json` 的基线（它记的是 `dataset:镜像内相对路径`，与 docs 层级无关）。

**动一个本项目文档目录**时，必须同步：

1. 该文档内部指向别处的相对 Markdown 链接（跨目录时层级会变），以及
   `README.md` / `AGENTS.md` 里指向它的引用；**不要留下指向已删除文件的链接**。
2. 生成器与校验器的路径常量：`docs/project/architecture/tech-detail/build_notebooks.py`、
   `tools/check_arch_style.py`、`tools/check_notebook.py`、`tools/check_repo_consistency.py`。
3. `.github/workflows/phase-8.yml` 里的文档路径、根 `README.md` 的目录树、`AGENTS.md` 的约定正文。
4. `docs/project/engineering-policy-platform/04-open-work.md` 的附录对照表（历史编号 → 现状文档），
   以及 `docs/project/architecture/功能清单.md` 里对文档位置的描述。

## 维护命令

```powershell
# 镜像语料：清单 ↔ 镜像 manifest、许可、sha256 是否一致（漂移即退出 1）
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m retrieval.cli verify
.venv\Scripts\python.exe -m retrieval.cli index
.venv\Scripts\python.exe tools/retrieval_eval.py --method both   # 基线是否仍达标

# 文档与文本约定
python tools/check_text_conventions.py    # 排版约定（镜像默认跳过，--all 连镜像一起查）
python tools/secret_scan.py               # 凭据扫描（镜像默认跳过）
python tools/check_arch_style.py          # docs/project/architecture 的文风自检（当前不在门禁步骤表里）
# tech-detail 的讲解 notebook：生成 + 逐单元执行；--check 是 CI 门禁（比对产物 + 结构校验）
python docs/project/architecture/tech-detail/build_notebooks.py
python docs/project/architecture/tech-detail/build_notebooks.py --check
python tools/check_notebook.py (Get-ChildItem docs/project/architecture/tech-detail/*/*.ipynb).FullName
```

通配符由 shell 展开：PowerShell 5.1 不替原生程序展开，直接写 `*` 会得到"不是合法 JSON"的假失败，
因此上面显式列出路径（bash / CI 里可以直接写 `docs/project/architecture/tech-detail/*/*.ipynb`）。
