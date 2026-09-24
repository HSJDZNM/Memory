# docs/：两类文档，两条规矩

这个目录只分两类，**先看类别再找文件**：

```text
docs/
├── mirrors/    第三方离线镜像：逐字复制上游原文，只读；既是追溯来源，也是检索语料（Raw Reference）
└── project/    本项目自己写、自己维护的文档：和代码一起评审、一起演进
```

分类的理由不是"谁写的"，而是**能不能改**：

| | `docs/mirrors/**` | `docs/project/**` |
| --- | --- | --- |
| 内容来源 | 上游站点原文（`tools/mirror_docs.py` 等流水线抓取） | 本项目作者手写或脚本生成 |
| 可否手改 | **不可以**。改了会在下次镜像同步时被覆盖，哈希门禁也会漂移 | 可以，且必须与相关代码/配置同步改 |
| 身份标识 | `dataset`（如 `owasp-cheatsheets`）+ 镜像内相对路径 | 仓库相对路径 |
| 谁在引用 | `knowledge/corpus.yaml`、`policies/**` 的 `source.path`、镜像流水线 | 生成器、文档内部链接、`README.md` / `AGENTS.md` |
| 文本约定 | 不按本仓库排版约定改写（行尾空白来自上游） | 必须过 `tools/check_text_conventions.py` |

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

## docs/project/：本项目文档

| 目录 | 内容 | 入口 |
| --- | --- | --- |
| project/architecture/ | 技术架构图（`.drawio` 两页 + tech-detail 十张）与说明三件套 + 术语与口径 + 规则转化覆盖报告 | [README.md](project/architecture/README.md) |
| project/engineering-policy-platform/ | 分阶段架构、契约、数据源、测试策略、验收矩阵与复核记录；设计提案含 [平台操作系统](project/engineering-policy-platform/designs/os/README.md) 与静态操作台原型 | [README.md](project/engineering-policy-platform/README.md) |
| project/learning/ | 面向人的学习手册，每阶段四件套（`note.md` / `walkthrough.ipynb` / `walkthrough.py` / `README.md`） | [README.md](project/learning/README.md) |
| project/rule-effects/ | 规则效果演示与多违规案例检测报告（本地产出，非镜像） | — |

其中 `project/learning/**/walkthrough.ipynb` 与 `walkthrough.py` 是**生成物**：
改内容要改 `tools/build_learning_notebook.py`（Phase 6–8 另见 `tools/phase{6,7,8}_cells.py`），
再运行 `python tools/build_learning_notebook.py`。手改 notebook 会在下次生成时丢失。

`project/architecture/tech-detail/notebooks/*.ipynb` 与同名的 `.py` 同样是生成物（每张编号图一份讲解）：
内容源在 `tech-detail/notebooks/nb_cells/nb<编号>.py`，由
`python docs/project/architecture/tech-detail/notebooks/build_notebooks.py` 生成并逐单元执行校验。

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

1. 该文档内部指向别处的相对 Markdown 链接（跨目录时层级会变）。
2. 生成器与校验器的路径常量：`tools/build_learning_notebook.py`、`tools/phase{6,7,8}_cells.py`、
   `docs/project/architecture/tech-detail/notebooks/build_notebooks.py`、`tools/check_arch_canon.py`（`ARCH`）、
   `tools/check_arch_style.py`、`tools/check_notebook.py`、
   `tools/run_notebook_in_kernel.py`、`tools/check_repo_consistency.py`（`check_notebook_form`）、
   `tools/ci_local.py`（`HANDBOOK_PREFIXES`）。
3. `.github/workflows/phase-8.yml` 里的手册路径、`README.md` 的目录树、`AGENTS.md` 的约定正文。

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
python tools/check_arch_canon.py          # docs/project/architecture 的图 / 文 / 口径表三处同口径
# 通配符由 shell 展开：PowerShell 5.1 不替原生程序展开，直接写 * 会得到"不是合法 JSON"的假失败，
# 因此这里显式列出路径（bash / CI 里可以直接写 docs/project/learning/*/walkthrough.ipynb）
python tools/check_notebook.py (Get-ChildItem docs/project/learning/*/walkthrough.ipynb).FullName
python tools/build_learning_notebook.py   # 重生成手册并逐单元执行校验
# tech-detail 的讲解 notebook：生成 + 逐单元执行；--check 是 CI 门禁（比对产物 + 结构校验）
python docs/project/architecture/tech-detail/notebooks/build_notebooks.py
python docs/project/architecture/tech-detail/notebooks/build_notebooks.py --check
# tech-detail 的图：重算 .drawio 与 .png（唯一规格源）
python docs/project/architecture/tech-detail/diagrams/build.py --png
```
