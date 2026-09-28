# 第 15 轮 · 最终状态独立验证报告（被测 sha = 928df2a）

> 验证者：plan-verifier（task-22）。写域 `.tmp/round-15/verify-final/`（本文件 + 脚本 + `raw-*.txt`）。
> **被测顶端 sha = `928df2a5c97f06592f860d70935cf2631885139d`**（分支 `feat/rules-and-os-platform`，复核时 HEAD 即它）。
> **若 tip 再动，本报告即失效**——报告里所有读数都绑定这一棵树（`f7300fcf00c824d246fefa03cd9b70dfbb7597d5`）与它上面那 5 个提交。
> **只读**：只用 `git status/log/show/diff/rev-parse/ls-tree/cat-file/merge-base/fsck/for-each-ref/rev-list`；
> **没有任何 git 写操作**（add/commit/checkout/reset/stash/restore/rm/clean/branch/tag/push 全未执行）；
> 没有跑 `tools/ci_local.py`、没有跑全仓 pytest、没有起受治理会话；复核结束时 `git status --porcelain` 为空。
> 复核时刻：2026-09-28 22:1x +08:00。原始输出：`raw-final-check.txt`、`raw-boundary-final.txt`、`raw-reach-final.txt`、`raw-history-final.txt`；脚本：`final_check.py`、`boundary_final.py`、`reach_final.py`、`history_final.py`。

## §0 一句话结论

**拆分的内容与边界是成立的**：5 个提交的改动集并集恰好覆盖 `8b0be68..928df2a` 的全部 **103** 条路径（不漏不多）；
`pre→post` 的路径差异**恰等于**第 14 轮提交（11 条）；`post→80acbe9` 的差异 = 第 15 轮代码 48 条 + 6 条被忽略的 `*.egg-info/*`；
抽样三个文件与快照逐字节一致；检查点标签可检索；本地领先远端 5 个提交。
**但简报有两处基准标错**（不是拆分的问题，是复核说明的问题）：
① 第 2 项那条命令里的 `checkpoint/round-15` 指向**拆分前的混合态** `e235626c`，实测差异是 **9 处**，
   而「已知例外 2 处」只在基准为**旧拆分顶端** `661fd56 / 5fcdc27` 时成立；
② 第 5 项「post→检查点 == (b9d3b11+80acbe9)−egg-info」**不成立**（两个集合各 48 条但相差 12 条），
   成立的是 `post→80acbe9 = 54 = 48 + 6 egg-info`。

## §1 七项逐条

### 1) 最终历史 —— **通过（5 个提交，顺序正确）**

```
$ git log --oneline 8b0be68..feat/rules-and-os-platform
928df2a docs(reviews): 第 15 轮收口记录（按轮次拆分、门禁与基线）
80acbe9 docs(designs): 控制面重构方案 v2 + 评审批次 1 处置 + 证据归档
b9d3b11 fix(governance): 第 15 轮 · Q6 归因措辞、Q7 待实现状态、Q8 记录形态与诊断修复
c75886e fix(governance): 第 14 轮 · 沙箱闭环按被拒路径归因 + 适配器声明与宿主版本比对
b2c1255 fix(governance): 第 12+13 轮修复（M1–M5 / G3 / N13 / N14 与 P1–P9）

$ git rev-list --count 8b0be68..feat/rules-and-os-platform
5
$ git log --format='%h parent=%p %s' 8b0be68..feat/rules-and-os-platform
928df2a parent=80acbe9 …
80acbe9 parent=b9d3b11 …
b9d3b11 parent=c75886e …
c75886e parent=b2c1255 …
b2c1255 parent=8b0be68 …

每个提交的 A/M/D：c1 {M:51, A:22}；c2 {M:8, A:3}；c3 {M:35, A:4}；c4 {M:1, A:8}；c5 {A:1, M:1}
改动集大小：73 / 11 / 39 / 9 / 2；并集 = 103 = git diff --name-only 8b0be68 feat 的 103 条（覆盖=True，未覆盖/多余均为空）
算术自检：134 − 重复计入 31 = 103 ✓（29 条路径出现在 ≥2 个提交里，属跨轮文件）
```

判定：**5 个提交、顺序 b2c1255→c75886e→b9d3b11→80acbe9→928df2a、父链首尾相连、并集全覆盖** ⇒ 通过。
（简报最初写 4 个、随后更正为 5 个；实测支持更正后的 5 个。）

### 2) 树同一性（带已知例外）—— **内容一致；但简报给的基准标错**

实测三个基线（都指向同一个顶端 928df2a）：

```
$ git diff --numstat checkpoint/round-15 feat/rules-and-os-platform
2	1	docs/.../designs/README.md
233	164	docs/.../designs/控制面重构方案.md
68	0	docs/.../reviews/governance-capability/15-control-plane-design/01-hook-matrix-summary.md
46	0	…/02-independent-verification-deviations.md
95	0	…/03-test-paths-disagreement.md
101	0	…/04-deliberation-record.md
75	0	…/05-checkpoint-precheck.md
107	0	…/06-round-15-closeout.md
62	0	…/15-control-plane-design/README.md
→ 9 files changed, 789 insertions(+), 165 deletions(-)

$ git diff --stat 661fd56 80acbe9      → 1 file changed, 1 insertion(+), 1 deletion(-)   # 只有 designs/README.md
$ git diff --numstat 80acbe9 928df2a   → 06-round-15-closeout.md 107/0 ；15-control-plane-design/README.md 1/0
$ git rev-parse 'checkpoint/round-15^{commit}' → e235626c… ；tree = c5939c0a5d472f543e1ec5b000e0821b19687641
$ git rev-parse '80acbe9^{tree}'              → 202a417941212ad3a11f99678d580a7ece4a038e
$ git rev-parse '928df2a^{tree}'              → f7300fcf00c824d246fefa03cd9b70dfbb7597d5
```

**「末尾换行」这一处我逐字节验了**（不是看 diff 的措辞）：

```
5fcdc27 / 661fd56 的 designs/README.md：3294 B，末尾字节 = b'\x82'（不是 LF）
80acbe9 / 928df2a 的同文件：            3295 B，末尾字节 = b'\n'
两者「去掉结尾换行后」的 sha256[:16] 都是 59C31EB2903372ED  → 只差一个末尾换行
（另外：80acbe9 与 checkpoint 的同文件**不是**只差换行——index 行内容本身也变了，checkpoint 独有 1 行、80acbe9 独有 2 行）
```

**判定**：
- **拆分的内容一致**：树身份链条 `拆分前混合态 e235626c` →（5 个提交）→ `928df2a` 的差异**全部可解释**——
  2 个修改文件（`designs/README.md`、`控制面重构方案.md` v1→v2）+ 7 个新增文件（归档 01–06 与归档 README）。
- **简报「已知例外 2 处」的表述正确，但它对应的基准是旧拆分顶端 `661fd56`（= `5fcdc27` 的树 `0b0e8f69`），不是 `checkpoint/round-15`**：
  ① `661fd56→80acbe9` 恰好 1 个文件（`designs/README.md` 的末尾换行，+1/−1，已逐字节证实）；
  ② `80acbe9→928df2a` 恰好 2 个文件（`06-round-15-closeout.md` 新增、归档 `README.md` 加一行）。
  用简报给的那条命令（基准 = `checkpoint/round-15`）会得到 **9 处**，因为检查点是**拆分前的混合态**：它**没有**那 6 份归档、方案还是 v1。

### 3) 提交信息是否已准确 —— **通过（逐条核对）**

```
$ git log -1 --format='%P' 80acbe9        → b9d3b11e32ce4bf560d152d118b86f1c600af5d8   （= b9d3b11 ✓）
$ git log -1 --format='%P' 928df2a        → 80acbe925baee49e62d62d0f03254a744f3166da   （= 80acbe9，顶端已前移）
$ git merge-base --is-ancestor e235626c 80acbe9   → rc=1（**不是**祖先 ✓，与提交信息的「口径更正」一致）
$ git merge-base --is-ancestor e235626c 928df2a  → rc=1（不是祖先 ✓）
$ git merge-base --is-ancestor b9d3b11 80acbe9   → rc=0（是祖先 ✓）
$ git rev-parse '80acbe9^{tree}'          → 202a417941212ad3a11f99678d580a7ece4a038e（信息里写「树：202a4179」✓）
```

`80acbe9` 提交信息的「补充二（口径更正）」逐条核对：父提交 = b9d3b11 ✓；`e235626c` 不是它的祖先 ✓；
检查点由标签固定 ✓（见第 4 项）；内容清单「方案 v2 / 评审意见 / designs/README / 6 份证据归档」与 9 条改动（1 M + 8 A）一致 ✓。
`928df2a` 的信息（「拆分、门禁读数、独立验证六项与三条偏差、回滚手册与遗留项落到已跟踪目录 + 登记到归档索引」）
与它的 2 条改动（新增 06 收口记录、归档 README 加一行）一致 ✓。
**判定：通过**（唯一需要说明的是简报第 3 项问的是「tip 的父是否 = b9d3b11」——那在顶端还是 `80acbe9` 时成立；现在是 `928df2a`，父 = `80acbe9`）。

### 4) 可达性 —— **通过（检查点可由标签取回）**

```
$ git cat-file -t checkpoint/round-15          → tag
$ git cat-file -p checkpoint/round-15          → object e235626c6b66340bb6a099df3be1adfa0932886e / type commit /
                                                 tag checkpoint/round-15 / tagger HSJDZNM … 1790604569 +0800
                                                 「第 15 轮拆分前的原始混合检查点（96 文件；不代表任何验收结论）…」
$ git rev-parse 'checkpoint/round-15^{commit}' → e235626c6b66340bb6a099df3be1adfa0932886e（commit 可达 ✓）

$ git fsck --unreachable --no-progress    （默认把 reflog 当根）→ 7 个不可达 commit：
  05597c1（index on feat/…：stash）、5e5df15 / f33dead（dependabot bumps）、
  d74f3be / f2b285e / d7a46bb（main 的 stash 条目）、e7a13c8（WIP on feat/…）
  另有 24 个 tree、9 个 blob 不可达 —— 都不是本轮的拆分提交

$ git fsck --unreachable --no-reflogs --no-progress → 13 个不可达 commit，多出的是**被取代的旧顶端**：
  5fcdc27、661fd56、0560b90、a435198（连同上面 7 个 stash/WIP/bump）
```

判定：**通过**。检查点由附注标签固定、可从标签取回；删除两个分支后，旧拆分顶端 `661fd56/5fcdc27`
**只靠 reflog 保活**（一旦 reflog 过期/被清，它们将真正不可达）——这是"观察"，我没有删除任何对象。
口径提醒：`git tag -l --format='%(objectname:short)'` 对附注标签给的是**标签对象** `ff118be`，不是它指向的提交 `e235626c`——读标签请用 `^{commit}`。

### 5) 历史中间态的边界（自己重算，不看旧报告）—— **第 14 轮通过；第 15 轮的等式只在 80acbe9 上成立**

方法：磁盘快照 `pre/post` 的每个文件我**自己算 git blob sha1**（`sha1(b"blob <len>\0" + content)`），
与 `git ls-tree -r -z` 给出的 blob 对象哈希逐路径比对（同一个哈希函数，故为逐字节比较）。

```
文件数：pre=912 post=915 c1=906 c2=909 c3=913 c4=920+1=921 checkpoint=915 tip=922
changes：C1=73 C2=11 C3=39 C4=9 C5=2

pre  vs c1  全树差异 = 6，全部是 src/engineering_policy_platform.egg-info/*   → c1 与 pre 在 git 可跟踪路径上完全相同
post vs c2  全树差异 = 6，全部是 src/engineering_policy_platform.egg-info/*   → c2 与 post 同上
pre  -> post 差异集 = 11 ；== C2（第 14 轮改动 11）？ True ；两侧对称差为空

post -> checkpoint(e235626c) 差异集 = 48
(C3 ∪ C4) − egg-info                = 48
两者相等？ **False**
   只在 post->checkpoint：6 个 *.egg-info/*（post 有、检查点没有）
   只在 (C3∪C4)−egg-info：6 份归档（01/02/03/04/05 + 归档 README）——它们在 80acbe9 里，**不在**检查点里

post -> 80acbe9 差异集 = 54 ；只在 post->80acbe9 的额外项 = 只有那 6 个 egg-info（(C3∪C4) 一侧无剩余）
checkpoint 与 80acbe9 的差异 = 8 条（2 改：designs/README.md、方案 v1→v2；6 增：归档 01–05 + README）
tip(928df2a) 与 80acbe9 的差异 = 2 条（06-round-15-closeout.md、归档 README）
```

**判定（点名）**：
1. **第 14 轮边界完全真实**：`pre→post` 恰等于 `c75886e` 的 11 条改动，且两侧对称差为空。
2. **第 15 轮那条等式对「检查点」不成立**：`post→checkpoint` 与 `(C3∪C4)−egg-info` 虽然都是 48 条，
   但集合相差 **12 条**（6 个 egg-info 只在左侧、6 份归档只在右侧）。**成立的形式是**：
   `post→80acbe9 = 54 = 48 + 6（egg-info）`，即第 15 轮代码与文档的 48 条 + 6 条被 `.gitignore:92:*.egg-info/` 忽略、
   git 结构上无法跟踪的产物。用「检查点」当基准会同时差在两处：检查点是**拆分前混合态**（方案 v1、无归档）。

### 6) 抽样（`git cat-file` 的 blob 哈希 vs 快照树自算 blob）—— **通过**

| 文件 | 版本 | git blob（`git rev-parse <rev>:<path>`） | 快照侧（我自算 blob / sha256[:16]） | 判定 |
| --- | --- | --- | --- | --- |
| **跨轮** `tools/dsh_sandbox_loop.py` | base 8b0be68 | `63db15ef2faa4fa5075caab5f5916ed700dcf86d` | 无快照 | = c1（base 与 pre 相同） |
| | c1 b2c1255 | `63db15ef…` | pre `79D33A03FA5369E1` | **一致** |
| | c2 c75886e | `1436061eb94070ccc5e4a0a06a95cd49174e4e58` | post `1225EDF1F80C0EAD` | **一致** |
| | tip 928df2a | `137cfd2b9c48c3f29d8a73bd500d6e815464572f` | —— | 与 c1/c2 都不同（三个内容，见偏差 V5） |
| **只属第 14 轮** `adapters/approved.json` | base | `3cc2cceab93a1c1b2e03696bc6802e626a0935c1` | 无 | 与 c2 不同 |
| | c2 c75886e | `7d2164cbe9ebe7c74d1c91e6ef0a64cf1c69ffc5` | post `E0597897BDE1AE4D` / 1861 B | **一致** |
| | tip 928df2a | `7d2164cb…` | —— | 与 c2 相同（不再变化） |
| **只属第 15 轮** `.github/workflows/phase-8.yml` | base / c2 | `af312852ae71862758cd89a529a3abd73d5c74d9` | post `4589DF61E3F26F42` | **一致**（base=pre=post） |
| | c3 b9d3b11 | `6cc991360453c0478a10c7114a7b6bf89da310c6` | 无 | 第 15 轮改的 |
| | tip 928df2a | `6cc99136…` | —— | 与 c3 相同（第 15 轮后不再变化） |

判定：**通过**。三个样本的"应当来自哪棵树"都对得上，且跨轮文件在三个时间点上是三个不同内容。

### 7) 远端与本地的关系 —— **本地领先 5，未推送**

```
$ git for-each-ref --format='%(refname) -> %(objectname:short) %(subject)' refs/remotes
refs/remotes/origin/feat/rules-and-os-platform -> 8b0be68 perf(gate): 门禁耗时可见…
refs/remotes/origin/main -> 1494d09 docs(architecture): add the architecture diagrams…

$ git rev-parse origin/feat/rules-and-os-platform   → 8b0be688a7ec3a9e70fb5c3c04170321e67db999
$ git rev-list --count origin/feat/…..feat/…        → 5   （本地领先）
$ git rev-list --count feat/…..origin/feat/…        → 0   （远端不领先）
$ git log --oneline origin/feat/…..feat/…           → 928df2a / 80acbe9 / b9d3b11 / c75886e / b2c1255
```

判定：**远端仍停在 `8b0be68`（第 15 轮之前的最后一个上游提交），本地领先 5 个提交，落后 0**。
按纪律我**没有执行 push**（简报说推送因凭据失败，我没有复现也没有尝试）。

## §2 偏差清单（5 条；全部在"复核说明/预期"侧，拆分内容侧 0 条）

### V1 · 第 2 项的基准标错（必点名）
- **偏差**：命令写的是 `git diff --stat checkpoint/round-15 feat/...`，期望"恰好只有 designs/README.md 的 +1/−1"；
  实测是 **9 个文件、789 插入 / 165 删除**。
- **证据**：§1-2 的 numstat；`checkpoint/round-15^{commit} = e235626c`（tree `c5939c0a`，拆分前混合态，96 文件）；
  对照 `git diff --stat 661fd56 80acbe9` = 1 file（designs/README.md），`git diff --numstat 80acbe9 928df2a` = 2 files。
- **影响**：按字面复核的人会看到 9 处差异，进而怀疑拆分漏做/多做；而实际那 9 处 = 方案 v1→v2 + 6 份归档新增 + 两处索引/换行。
- **建议**：把基准写成「旧拆分顶端 `661fd56`（= `5fcdc27` 的树 `0b0e8f69`）」并拆成两段：
  ① `661fd56→80acbe9` = 1 处（末尾换行）；② `80acbe9→928df2a` = 2 处（06 新文件 + 归档 README +1）；
  若确实要写检查点，则必须列出全部 9 处（方案 v1→v2、6 份归档、两处索引/换行）。

### V2 · 第 5 项的快照边界等式对"检查点"不成立
- **偏差**：简报写「post 与检查点之间的差异 == (b9d3b11 + 80acbe9) 的改动集合减去 .gitignore 忽略的 egg-info」。
  实测两个集合各 48 条但**不相等**（对称差 12 条）。
- **证据**：§1-5 的集合差；只在 checkpoint 侧 = 6 个 `*.egg-info/*`；只在公式侧 = 6 份归档；
  `post→80acbe9` = 54 = 48 + 6 egg-info（这一形式两侧对称差只有 egg-info）。
- **影响**：等式不成立的原因不是"拆分错了"，而是**检查点是拆分前混合态**：它没有归档、方案是 v1。
  若照字面声称"成立"，就是把一个**集合不等式**写成了等式。
- **建议**：改成两条：① `post→80acbe9 = (C(b9d3b11) ∪ C(80acbe9)) ∪ (被忽略的 egg-info) = 48 + 6`；
  ② `checkpoint↔80acbe9 = 8 条（designs/README.md、方案 v1→v2、6 份归档）`——检查点只用于**取回**，不用于边界等式。

### V3 · 第 3 项问的「父提交」对象已随顶端前移
- **偏差**：简报问 `git log -1 --format='%P' feat/...` 是否等于 `b9d3b11`；现在顶端是 `928df2a`，其父是 `80acbe9`。
- **证据**：§1-3 的两条 `%P` 读数。
- **影响**：低。`b9d3b11` 是 `80acbe9` 的父（依旧成立）；提交信息里的"口径更正"也对（`e235626c` 确非祖先，rc=1）。
- **建议**：把该问写成「`80acbe9` 的父是否 = `b9d3b11`」（是），并另记一条「`928df2a` 的父 = `80acbe9`」。

### V4 · 任务号不一致（流程，非技术）
- **偏差**：派工消息写 `task-23`，板上的对应任务是 **`task-22`**（subject「最终状态独立验证（80acbe9）」、写域 `.tmp/round-15/verify-final`）。
- **证据**：`team_task_list` 只有到 task-22；`team_task_get(task-23)` 返回 not found；我 claim 的是 task-22。
- **影响**：低（我按 subject 与写域对齐了），但若有人按 task-23 去查账会查不到。
- **建议**：以 task-22 记账；或在消息里用 subject 而不是编号。

### V5 · 抽样预期"四个内容"实为三个（沿用 task-21 的 V3，本轮再次实测）
- **偏差**：`tools/dsh_sandbox_loop.py` 在 base/pre/post/tip 上是**三个**内容（base 与 pre 的 blob 完全相同 `63db15ef…`）。
- **证据**：§1-6 表；它不在 c1 的 73 条改动里（只在 c2、c3 被改）。
- **影响**：低——不影响拆分；但把"四内容"当验收条件会误判。
- **建议**：改述为"跨轮文件在三个时间点上 ≥3 个不同内容"。

## §3 我无法验证的部分（诚实边界）

1. **我验证的是「提交 == 那两棵快照树」，不是「快照树 == 当时的工作树」**。`pre/post` 是另一个会话冻结的副本；
   我逐字节比对了它们与提交，但无法独立证明这两棵树忠实于 2026-09-27 那一刻的仓库。
2. **`8b0be68` 及其之前的历史**没有第三方快照作锚点；我只能证明从它到 `928df2a` 的增量被完整、无重复地分到 5 个提交里。
3. **作者/时间意图无法从内容判定**：c1–c3 的时间戳落在同一秒（21:35:39–21:35:40）、c4 为 22:09:28、c5 为 22:11:19，
   说明前三个是脚本重建的；这既不构成造假证据，也不构成正确证据。顺序我只认父链。
4. **我没有跑门禁/测试**：简报说门禁 33/33 通过、`06-round-15-closeout.md` 里记了两次门禁读数——我**没有复核**这些读数。
5. **push 失败的具体原因我无法验证**（凭据）；我只读到 `origin/feat/rules-and-os-platform` 仍指向 `8b0be68`，且我没有尝试推送。
6. **旧拆分顶端 `661fd56/5fcdc27` 的存活依赖 reflog**：我能列出它们（`fsck --no-reflogs`），但无法保证它们明天还在；
   也没有验证 reflog 的过期策略。
7. **git 对象完整性未做全量校验**：只跑了 `fsck --unreachable`（两种口径）与逐路径 blob 比对；未跑 `fsck --full`，未验证哈希算法强度。
8. **`06-round-15-closeout.md` 的内容未逐条核对**：我只验证它在 `928df2a` 里、是新增文件、107 行（与其 diff 一致）。
9. **本报告的有效期**：绑定被测 sha `928df2a` 与树 `f7300fcf…`。**若 tip 再动，本报告即失效**，需要按新 sha 重采。
