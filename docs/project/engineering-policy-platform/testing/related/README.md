# related/：本轮两份外部研究的入口与复核

> **这份 README 是什么**：同目录两份研究文档的入口、适用面与复核命令。它回答四件事——
> 这两份**是什么**、**谁写的**、**能证明什么 / 不能证明什么**、**怎么自己复核一遍**。
>
> **裁定不在本目录**：「能不能用、用在哪一层」的结论只有一处——
> [`../governance-value-eval-plan.md`](../governance-value-eval-plan.md) 的 **§4.7 适配性判定**；
> 数据集登记在 [`../eval-datasets.yaml`](../eval-datasets.yaml) 的 `aacr-bench` 条目（`tier: B`）。
> 这两份文档是**证据与原文的汇集，不是结论**；引用它们时必须给「文件 + 小节号」。

## 1 两份研究是什么、谁写的

| 文档 | 对象与快照 | 回答什么 | 谁写的 |
| --- | --- | --- | --- |
| [`alibaba-open-code-review-测试方法.md`](alibaba-open-code-review-测试方法.md)（下称 **OCR 文档**） | `github.com/alibaba/open-code-review`，main = `182898cf522da3d04157b422752d028417974e19`（= 最新 tag v1.12.12，2026-10-05） | 它的测试怎么组织、指标与门槛是什么、标签从哪来、**没有多个资深工程师时它用什么替代**（§7.1 的六条） | 本轮会话的 teammate `ocr-repo`（task-8），访问日期 **2026-10-07**；通道 `gh api` / codeload tarball / Python `urllib` / bestpractices.dev JSON；原始件在 `.tmp/ocr*`（临时） |
| [`aacr-bench-数据集核验.md`](aacr-bench-数据集核验.md)（下称 **核验文档**） | HF `Alibaba-Aone/aacr-bench` @ `47be1d6df1e7faf222cf531587772d92f79fe6b2`；上游 `github.com/alibaba/aacr-bench` | 规模 / 字段 / 许可 / 标签怎么来的 / 与我们有没有连接键 / 能不能直接用 | 本轮会话的 teammate `aacr-bench`（task-9），访问日期 **2026-10-07**；通道 HF API 与 datasets-server、`gh` CLI、arXiv HTML v1/v3；原始件在 `.tmp/aacr-bench/raw/`（临时） |

**「谁写的」要说清楚**：两份文档由本轮会话里的两个 AI teammate 产出（task-8 / task-9），**不是上游仓库的一部分**。
它们的可信度来自**可重放的命令与原文摘录**（每份都有证据索引：OCR 文档 §8 的 [E01]…[E62]、核验文档 §8 的 E01–E27），
不来自作者身份；判定者（task-10，即本 README 的作者）另外自己复核了其中几条，见第 3 节。

## 2 能证明什么 / 不能证明什么

### 2.1 OCR 文档

- **能证明**：它写的每一条都给了文件路径、命令或原文摘录（§8 的证据索引），可以逐条对回上游。可核对的例子：
  「覆盖率 90% 在两套范围上是两个数」（§2.4）、「评测工具链不在开源仓库里」（§3）、
  「评论过滤器 fail-open、且把误杀代价不对称写进提示词」（§6.1 / §6.2）、「六条替代方案」（§7.1）。
- **不能证明**：它的数字**不是我们的数字**——OCR 文档 §8 自己写明「借用的是机制，不是它的数字」；
  它**没有验证** branch protection（§7.0 明确标【待核验】），也**没有**证明它的评审结论质量
  （§2.3：仓库里**没有**针对「评审结论正确性」的自动门槛）。
- 用法：只借**机制**，逐条落点见方案 §4.7.2 的 **OCR-R1…OCR-R10**。

### 2.2 核验文档

- **能证明**：数据集存在且可钉死 revision、规模与字段（§1 / §2）、标签构造流程的论文原文（§4.1）、
  许可状态（§1.2：HF 侧**没有** LICENSE 文件，只有卡片声明）、**与我们没有连接键**（§7.3：
  CWE / Bandit `S###` / pydocstyle `D###` / `OWASP` / `bandit` / `pycodestyle` / `PEP 8` 命中全为 0），
  以及两个实测缺陷（§6.2 缺陷 A：1 条记录在 HF 快照与上游当前版上标签相反；缺陷 B：上游声明的 sha256 与实际不符，
  会让自带 converter 直接 `SystemExit`）。
- **不能证明**：见它自己的 §10（八条）与 §9 的【待核验】清单——
  640 条「错误」标签的标注流程没找到；论文里**不存在**任何一致性系数（是「取到全文且里面没有」的负面结论）；
  没有复跑任何模型分数；**没有真正 clone 过那 50 个仓库**（41.15 GiB 只是 `gh api` 报告的仓库大小合计）；
  没有执行过上游 `evaluation/` 那套框架。

### 2.3 两份都证明不了的（也是本次判定的起点）

- **不能证明我们的规则准不准**：那是 L2 的事；而这份数据集**当不了 L2 的标签源**——
  评论级标签与检出级判定不同构，错位既不能算 FP 也不能算 FN（方案 §4.7.3 逐条论证）。
- **不能证明「人工验证」可靠**：两份文档独立确认论文**没有报告 κ / IAA / 分歧率**
  （核验文档 §4.1、OCR 文档 §4.2）——「有双盲流程」与「报告了一致性」必须分开写。
- **不能证明同源与否**：一致率高不能读成「规则对」（核验文档 §7.4）；映射表若由我们写，就是自证。

## 3 复核命令（2026-10-07 在本机实测可跑）

> 环境约束：本机 **PowerShell 的 `Invoke-WebRequest` / .NET HTTP 不可用**，HTTP 必须走 Python `urllib`；
> GitHub 侧用已认证的 `gh` CLI。`.tmp/` 是临时目录（`tools/cleanup.py` 会清），
> 所以**能重放的只是命令，不是文件**。下面每条后面的「实测」就是本次跑出来的输出。

```text
# 数据集本体 → 实测 2101497 B / sha256 0804505f0a474765ce2840c832cfeaa6c4f0250dd6ccb169fe73c6758b245a86
python -c "import urllib.request,hashlib;b=urllib.request.urlopen('https://huggingface.co/datasets/Alibaba-Aone/aacr-bench/resolve/main/dataset.json').read();print(len(b),hashlib.sha256(b).hexdigest())"

# 许可：HF 侧两个 URL → 实测 404 / 404（所以 license_verified 只能是 false）
python -c "import urllib.request,urllib.error
for u in ('https://huggingface.co/datasets/Alibaba-Aone/aacr-bench/resolve/main/LICENSE','https://huggingface.co/datasets/Alibaba-Aone/aacr-bench/raw/main/LICENSE'):
    try: print(u, urllib.request.urlopen(u).status)
    except urllib.error.HTTPError as e: print(u, e.code)"

# 上游许可与最小子集仓库大小 → 实测 Apache-2.0 / 37043 KB
gh api repos/alibaba/aacr-bench --jq .license.spdx_id
gh api repos/browser-use/browser-use --jq .size

# 两个 commit 的关系与 PR diff → 实测 3 个 PR 里 2 个 diverged（所以「source = base」不成立）
gh api repos/browser-use/browser-use/compare/<source>...<target> --jq "{status,ahead_by,behind_by}"
gh api repos/browser-use/browser-use/compare/<source>...<target> -H "Accept: application/vnd.github.v3.diff"

# OCR 侧：文件树是否被截断、抽样 PR 的评审记录数 → 实测 false / 15
gh api "repos/alibaba/open-code-review/git/trees/HEAD?recursive=1" --jq ".truncated"
gh api repos/alibaba/open-code-review/pulls/1056/reviews --jq "length"
```

R3 自己的适配性探针（数据集索引、位置连接可行性、连接键扫描、平台自洽性检查）在方案 **§4.7.4** 的命令清单里，
脚本本身写在 `.tmp/r3-probe/`（临时，不入仓）。

## 4 引用纪律（三条）

1. **给小节号**：引用别人的结论一律「文件 + §小节」（例：核验文档 §6.2 缺陷 A）。
   本目录**不承载结论**，它是证据入口。
2. **数字不跨文档搬运**：`R1…R10` 在 OCR 文档里是「可复用清单」，在方案 §2 里是「三条纪律」——**同名不同义**，
   引用时必须写 **OCR-R1…OCR-R10**；41.15 GiB 是**报告的仓库大小合计**，不是实测克隆量
   （实测最小可行子集 ≈ 2.4 MiB，方案 §4.7.4）。
3. **不得改写成结论**：这两份文档与这份 README 都不承载「能不能用」的裁定；
   裁定只有一处——方案 §4.7；数据集能不能采信只有一处——`eval-datasets.yaml` 的条目字段。
