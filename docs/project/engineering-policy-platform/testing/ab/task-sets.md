# AB-4 任务集：获取、钉死与本地可运行化（2026-10-07 实测）

> **这份文件是什么**：把 A/B 实验需要的"任务从哪来、怎么钉死、怎么在**本机**跑出外部判据"写成可执行的事实——
> 每条都带命令与真实字节数/耗时。工具在 `tools/ab_tasks.py`，锁在 `evaluation/ab/tasks.lock.json`。
>
> **它不是什么**：不是 A/B 协议本身（那是 `ab-protocol.md`）；不含任何"质量分"；也**不替实验判成败**——
> 它只回答"这个任务的外部 oracle 是什么、跑不跑得动"。
>
> **状态口径**：`【实测】` = 2026-10-07 在本机跑过并贴了输出；`【未验证】` = 没测到，写明原因；
> `【待对方确认】` = 依赖兄弟会话的接口，尚未回。

## 1 候选任务集核验【实测】

| 候选 | 入口 | revision（钉死） | 许可（核验方式） | 规模 | gated | 需要 clone 仓库？ | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **SWE-bench Verified** | `huggingface.co/datasets/princeton-nlp/SWE-bench_Verified` | `c104f840cc67f8b6eec6f759ebc8b2693d585d4a` | MIT：`gh api repos/princeton-nlp/SWE-bench --jq .license.spdx_id` = MIT；**数据集卡 tags 里没有 license:*** | 500 行 / 8,110,423 B | false | 否——用 `codeload` 按 `base_commit` 取 tarball | **主候选** |
| **BugsInPy** | `github.com/soarsmu/BugsInPy` | HEAD `11c5f1eea954a42132cfd06bf257766a7963e0fd` | `gh api repos/soarsmu/BugsInPy` → **license = null（未声明）** | 仓库 1,254 KB；`projects/` 下 17 个项目 | false | 是，且框架要 `pip install -e framework/`、每个项目还要独立环境 | **本机 needs_install**：PyPI 慢/可能受限 |
| SWE-smith（第三候选） | `huggingface.co/datasets/SWE-bench/SWE-smith` | `ea6d7173829c7ec8fa16c22055699ff2e9188091` | MIT（tags `license:mit`） | 59,136 行 | false | **是**：字段只有 `image_name`（Docker 镜像）与 `repo`，**没有 `base_commit`** | 更轻量**不成立**（59k 行 + 依赖 Docker） |

补充【实测】：`nebius/SWE-bench-extra`（CC-BY-4.0，sha `11dcbfb30e19552df2a2f8030bd764adc95c92a5`）在
datasets-server 上 `test` split 返回 **HTTP 500**，**没取到行**（未试其它 config）。

**SWE-bench Verified 的分布【实测】**（`python tools/ab_tasks.py --list`）：12 个仓库——
django/django 231、sympy/sympy 75、sphinx-doc/sphinx 44、matplotlib/matplotlib 34、scikit-learn 32、
astropy 22、xarray 22、pytest-dev/pytest 19、pylint-dev/pylint 10、psf/requests 8、seaborn 2、pallets/flask 1。
每个任务的 `FAIL_TO_PASS` / `PASS_TO_PASS` / `base_commit` / `environment_setup_commit` / `test_patch` / `difficulty`
**500/500 非空**【实测】。

**逐仓库许可【实测，`gh api repos/<repo>/contents/<LICENSE>` 读原文首行】**：django BSD、
sympy BSD 文本（GitHub 报 NOASSERTION）、**scikit-learn / astropy / seaborn / flask BSD-3**、
xarray / requests Apache-2.0、pytest MIT、**pylint GPL-2.0（10 个任务，不得随产物分发）**、
**sphinx 未取到（`LICENSE` 404，路径不对 → 【未验证】）**、**matplotlib 未核验（`LICENSE/LICENSE` 是自定义协议文本，需人工读）**。

## 2 外部判据（oracle）：逐字段样例

`python tools/ab_tasks.py --verify-oracle sympy__sympy-22456` 的**实测输出**（节选，字段名即契约）：

```json
{
  "task_id": "sympy__sympy-22456",
  "source": {"dataset": "swe-bench-verified", "revision": "c104f840cc67f8b6eec6f759ebc8b2693d585d4a",
             "license": "MIT（上游仓库 princeton-nlp/SWE-bench）", "language": "python"},
  "baseline": {"repo_url": "https://github.com/sympy/sympy",
               "repo_revision": "a3475b3f9ac662cd425157dd3bdb93ad7111c090",
               "base_tree_ref": {"url": "https://codeload.github.com/sympy/sympy/tar.gz/a3475b3f9ac662cd425157dd3bdb93ad7111c090",
                                 "sha256": "f862bed5b614aec17aec7582e7d2f2e8b8a8fd67aba484182f4c897ae2fb3983",
                                 "bytes": 7546164},
               "task_statement_ref": ".tmp/ab-tasks/sympy__sympy-22456/problem_statement.txt",
               "task_statement_sha256": "…"},
  "oracle": {"kind": "frozen_tests",
             "fail_to_pass": ["sympy/codegen/tests/test_ast.py::test_String"],
             "pass_to_pass": ["sympy/codegen/tests/test_ast.py::test_Assignment", "…共 29 条"],
             "collection_ok_on_base": true, "needs_deps": [], "runtime_s": 5.17},
  "cost": {"bytes_download": 7546164, "seconds_setup": 1.5, "seconds_oracle_run": 7.44},
  "reject": {"rejected": false, "reason": ""},
  "measured": {"fail_to_pass_all_red": true, "pass_to_pass_all_green": true,
               "fail_to_pass_total": 1, "fail_to_pass_red": 1, "fail_to_pass_green": 0,
               "pass_to_pass_total": 29, "pass_to_pass_green": 29, "pass_to_pass_red": 0,
               "collected_on_base": 31, "collection_exit_code": 0, "problems": []}
}
```

（上例是 `sympy__sympy-22456` 的**真实值**：`repo_revision` = `base_commit`，
tarball 的 sha256/bytes 来自 `--baseline` 当场算出的 `source.json`。
`task_statement_sha256` 与 29 条 `pass_to_pass` 太长，以 `--verify-oracle --json` 的输出为准——
本文档不手抄全部哈希，避免长出第二份真相。）

**三条硬要求怎么落的**（ab-protocol 2026-10-07 冻结）：

- **node id 而不是文件名/实例 id**：上游有些任务的 `FAIL_TO_PASS` 是**裸函数名**（sympy 的 `test_String`），
  照抄不能喂给 pytest。工具的做法是：先 `--collect-only -q` 拿**基线树上真实收集到的 node id 清单**，
  再按"末段名字相等 / 参数化前缀相等"解析；**唯一命中才采用**，多命中记 `ambiguous`、零命中记 `unresolved`，
  两者都进 `reject`（原因 `no_oracle`）。**不许猜**。
- **每个任务在基线树上实测"F2P 全红 / P2P 全绿"**：`--verify-oracle` 分别跑两组并解析 pytest 的 `-rA` 摘要，
  `measured.fail_to_pass_all_red` / `pass_to_pass_all_green` 是**布尔读数**，不是声明。
  实测 9 个任务里只有 **2 个**两项都为真（见 §3）。
- **`collection_ok_on_base` 实测数字**：`collected_on_base` + `collection_exit_code` 都在 `measured` 里；
  这正是 ab-protocol 冻结 `COMMON` 支撑集需要的输入。

## 3 最小可行子集【实测】

**探针（5 个不同仓库的任务，`--baseline --apply-test-patch` + `--probe` + `--run-oracle --phase baseline`）**：

| instance | 下载 | 解压文件数 | collect 读数 | 分类 | `status_reason`（照抄） |
| --- | --- | --- | --- | --- | --- |
| `sympy__sympy-22456` | 7,546,164 B / 1.50 s | 4,036 | 31 collected / exit 0 | **runnable** | collect-only 通过（可跑外部 oracle） |
| `psf__requests-5414` | 4,032,376 B / 1.89 s | 231 | exit 4 | needs_install | `ImportError: cannot import name 'SNIMissingWarning' from 'urllib3.exceptions'`（装的 urllib3 太新） |
| `pytest-dev__pytest-7324` | 1,048,989 B / 1.04 s | 1,109 | exit 4 | needs_install | `ImportError: cannot import name 'Testdir' from '_pytest.pytester'`（树是 pytest 5.4，跑在本机 pytest 9.1.1 上） |
| `matplotlib__matplotlib-22719` | 35,009,563 B / 3.24 s | 8,932 | exit 4 | needs_install | `ImportError: cannot import name '_c_internal_utils' from partially initialized module 'matplotlib'` |
| `pallets__flask-5014` | 692,792 B / 0.95 s | 570 | exit 4 | needs_install | `ModuleNotFoundError: No module named 'flask'` |

**判据（外部 oracle）验证【实测】**：`--verify-oracle` 跑 4 个 sympy 任务——

| instance | collected | F2P 红/总 | P2P 绿/总 | 判定 | 原因 |
| --- | --- | --- | --- | --- | --- |
| `sympy__sympy-22456` | 31 | 1/1 | 29/29 | **接受** | —— |
| `sympy__sympy-22714` | 13 | 1/1 | 11/11 | **接受** | —— |
| `sympy__sympy-14711` | 0（collect exit 4） | 0/0 | 0/0 | 拒收 | `no_oracle`：基线树上 collect 失败 + node id 解析不出来 |
| `sympy__sympy-19637` | 50 | 1/1 | **39/40** | 拒收 | `unrunnable_local`：基线树上 P2P 有 1 条红（上游 P2P 清单在这个 checkout 上不成立） |

**最小可行子集 = 2 个已验证任务**（`sympy__sympy-22456`、`sympy__sympy-22714`），
单任务成本：下载 7.5 MB / ~1.5 s；`--verify-oracle` 墙钟 5–12 s；解压后 4k 文件。
**"3–5 个"没做到**——本机在不安装依赖的前提下，9 个受测任务里只有 2 个满足"F2P 全红 + P2P 全绿"。
这是**环境的限制，不是任务集的限制**；补齐的办法是给每个仓库钉死的 venv（见 §7 缺口）。

## 4 拒收分类【实测分布】

`reject.reason` 取值（ab-protocol 冻结）：`gated | too_big | no_oracle | license_unverified | unrunnable_local | other`。

| 原因 | 触发判据（机器可判） | 本次实测命中 |
| --- | --- | --- |
| `gated` | 数据集 `gated=true` | 0（Verified 是 false） |
| `too_big` | 解压文件数或下载字节超过阈值（阈值待 ab-protocol 定） | 0（最大 35 MB / 8,932 文件） |
| `no_oracle` | collect 失败 / F2P 解析后为空 / node id unresolved 或 ambiguous | `sympy__sympy-14711` |
| `license_unverified` | 逐仓库许可没读到原文（sphinx 404、matplotlib 自定义文本） | 未用于拒收（**【未验证】**，见 §7） |
| `unrunnable_local` | collect 报缺依赖；或基线树上 P2P 有红 | requests / pytest / matplotlib / flask / `sympy__sympy-19637` |

**不许静默跳过**：每个拒收都带 `status_reason`/字符串原因，写进 `--probe` / `--verify-oracle` 的输出。

## 5 钉死与漂移

- 锁：`evaluation/ab/tasks.lock.json`（`schema_version: "1"`），含 `datasets.<id>.{revision,url,files{path:sha256}}`
  与 `baselines.<instance>.{url,sha256,bytes,record,record_sha256}`【实测已写入】。
- 校验：`python tools/ab_tasks.py --verify --json` → **`{"ok": true, "problems": [], "verify_scope": "lock_and_bytes", "upstream_recheck": false}`**【实测】；
  缺文件 / 哈希漂移 / 来源记录被改写 / 锁里有未登记数据集，都逐条报出并退出 1。
- **两个字段把「这次真的做了什么」写出来**（ab-protocol 2026-10-07 要求：不然"这次真的解开了归档"与
  "上次留下的目录还在"长得一样）：
  * `baseline_source ∈ {fresh_extract, reused, not_extracted}`——`--baseline` **本次调用**真实发生了什么；
    `source.json` 记的是**首次解压**（`fresh_extract` + `extracted_at`）；
    **没有该字段的老记录写 `unknown`，不 backfill**（实测：sympy__sympy-22456 的首次记录早于该字段，故 `recorded_source=unknown`）；
  * `verify_scope ∈ {lock_only, lock_and_bytes}` + `upstream_recheck: false`——本次 `--verify` 覆盖到哪一层。
    当前是 `lock_and_bytes`（锁记录 + 本地字节），**不重新下载**：上游 force-push 只能靠重跑 `--baseline` 发现。
- **三条残余限制（ab-protocol 2026-10-07 复核后的措辞，我原样采纳并在这里同步）**：
  ① `reused` + `recorded_source=unknown` ⇒ **那次首次解压是不是 fresh 查不出来**（不 backfill 是有意的：
    补写历史就是伪造证据）；本条只保证「本次没重新解压」；
  ② `upstream_recheck: false` ⇒ **锁防的是「本地被改」，不防「上游被改写」**——这两件事必须分开说；
  ③ `not_extracted` 是合法取值 ⇒ **「没解压」不等于「解压失败」**，读数里不许合并。

## 6 成本

| 项 | 实测 | 外推（500 条） |
| --- | --- | --- |
| 元数据 | 8,110,423 B / 13.85 s（500 行一次取全） | 同 |
| 基线树 | 0.7–35 MB / 1–3.3 s per task（12 个仓库共 12 份复制，不是 500 份） | 按仓库去重后 ~12 次下载 |
| oracle 验证 | 5.2–17.9 s per task（本机、无需安装时） | 2 个已验证；其余需先建环境 |
| 失败模式 | 5/5 非 sympy 任务在 collect 阶段就红（版本错配/缺包） | —— |

**先做哪一步最省**：先跑 `--verify-oracle` 的**collect 阶段**（`--probe`）筛掉 `needs_install`，
再对剩下的跑两组测试——这一步把 5 个候选筛成 1 个，成本不到 2 分钟。

## 7 已知缺口 / 我没验证什么

1. **没有 3–5 个任务**：只有 2 个通过全判据。原因是本机不装依赖（PyPI 慢/受限），
   旧版本树跑在装了新版本库的解释器上（requests/pytest/matplotlib 的 ImportError 都是这一类）。
   补齐需要**每仓库钉死 venv**——那是安装动作，不在本任务范围。
2. **`--baseline` 复用不校验**：目录已存在就直接用；若上游 force-push 或本地被改，`--verify` 发现不了。
   已用 `baseline_source` / `verify_scope` / `upstream_recheck` 把这件事**显式化**（读数里读得出来），
   但**没有**变成自动重校验——要重校验就重跑 `--baseline`（重新下载并与记录里的 sha256 比对）。
   另：`test_patch_applied` 只报**本次调用**做了什么，不报这棵树的补丁历史。
3. **只验了 sympy**：其余 11 个仓库一个任务都没通过全判据；**不代表它们不可用**，只代表"本机现状下不可用"。
4. **`license_unverified` 没用上**：sphinx 的 LICENSE 路径取错（404）、matplotlib 是自定义协议文本——
   **逐仓库许可尚未逐个核到原文**；pylint(GPL-2.0) 的 10 个任务按纪律不得随产物分发。
5. **500 条的 `needs_deps` 清单没有全量测**：只测了 9 个任务；全量的依赖可达性需要逐仓库试装。
6. **绝不做的事**：不把"用平台 Decision 判成败"写进任何一处；本文件所有判据都来自仓库自带测试。
7. `tools/README.md` 的登记由 lead 完成（不在我写域）。

## 8 命令速查

```powershell
python tools/ab_tasks.py --fetch swe-bench-verified          # 取 500 行元数据（实测 8,110,423 B / 13.85 s）
python tools/ab_tasks.py --list                              # 列出任务（前 80 条）
python tools/ab_tasks.py --oracle sympy__sympy-22456 --json  # 单条任务的外部 oracle
python tools/ab_tasks.py --baseline sympy__sympy-22456 --apply-test-patch
python tools/ab_tasks.py --probe sympy__sympy-22456          # collect-only：能不能跑
python tools/ab_tasks.py --verify-oracle sympy__sympy-22456  # 基线树上 F2P 全红 / P2P 全绿
python tools/ab_tasks.py --run-oracle sympy__sympy-22456 --phase baseline
python tools/ab_tasks.py --record-lock ; python tools/ab_tasks.py --verify
```

## 9 交流记录

- **2026-10-07 ab-instruments → 我**：要 6 处补/改：`patch` 只给路径、`test_command` 用 argv 数组 +
  `test_select_style`、`python` 必须显式给、`pass_to_pass`/`fail_to_pass` 要真实 node id、
  `status` 与 `needs_install` 分开存并加 `status_reason`、加 `source.{url,sha256}`；
  并声明"status ≠ runnable 时我仍会跑一次，declared vs measured 两边都记"。
  **我的回应：全部接受。** 已落进 §2 的字段块（`test_command.argv` 是**解释器之后**的参数；
  `python` 给的是本机实测可用的绝对路径）。**一处扩展并声明**：`test_select_style` 我加了第三个取值
  `by_keyword`——上游有裸函数名的任务（sympy），只能 `-k` 选；不认识的值请按 unavailable 处理。
- **2026-10-07 ab-protocol → 我**：要四组字段（身份/基线/oracle/成本）+ `reject`；三条硬要求（node id、
  基线实测 F2P 全红 P2P 全绿、`collection_ok_on_base` 数字）；并说净化树会让 pytest 收集报错
  （1832 collected / 12 errors vs 原始 2136 / 0）【他们实测】，所以要 `COMMON` 支撑集先冻结。
  **我的回应：接受**，已按 §2 实现；**一条反驳**："每个任务都实测 F2P 全红/P2P 全绿"在**全量 500 条**上做不到——
  本机没有 12 个仓库的环境；我只能给**已实测子集**，其余按 `reject.reason=other` 标注为"未实测"
  （宁可少给，不给"看起来能用"的）。**未解决的分歧保留在这里**：全量的 `collection_ok_on_base`
  需要先为 12 个仓库各建一个钉死环境，这是一次独立的、要花时间的动作。
- **2026-10-07 r3-applicability（ab-redteam）→ 我**：主张"改测试 = 作废"光靠 diff 判不出来，
  给了四条可执行检查（测试文件摘要、`--collect-only` node id 集合、AST 数 assert、**冻结测试重跑**）。
  **我的回应：接受，并且本任务能提供前两条的输入**——基线测试树的 sha256（`source.json` + lock）、
  以及基线 node id 清单（`--verify-oracle` 的 `collected_on_base` / `node_ids`）。
  第三条（AST 数 assert）与第四条（冻结测试重跑升为主结局）属协议层，**由 ab-protocol 裁定**，我不改。
- **2026-10-07 ab-protocol → 我（第二轮判决）**：接受字段表与真实样例（只回填**字段名**、不复制值）；
  接受"node id 现算"（认为比原要求更严）；接受 `by_keyword` 枚举扩展，**附带要求**——`-k` 的选择面必须与
  `collected_on_base` 一起报。**我照做**：`measured` 现在同时有 `select_style`、`selected_total`、`collected_on_base`。
  他另要两个可读字段（`baseline_source`、`verify_scope`），**我补了**（见 §5）；补之前他不引用那两条读数——
  这个先后关系照原样记在这里。他把"只有 2 个任务通过全判据"写成**结论**：按当前任务集 A/B 只能做可行性试点，
  主结局 U1 的预注册功效（n=42～48）在现有任务数下不可能达到；并**反对"再下 500 条就行"**——
  扩池的真实成本是给 12 个仓库各钉死一套可复现环境，而本机 PyPI 不可达 ⇒ 现在做不到。
  **我认同**：这与 §7 第 1 条是同一件事，我不反驳。
- **【待对方确认】**：`test_select_style` 的第三取值（`by_keyword`）ab-instruments 尚未回；
  全量 `needs_deps` 清单未定；`too_big` 的阈值未定（ab-protocol 未给）。

## 10 这份文件不能证明什么

- 不能证明"这个任务集适合测治理价值"——那是 A/B 协议（`ab-protocol.md`）的命题；
- 不能证明任务**难度**或**代表性**；SWE-bench Verified 的 12 个仓库是**成熟大仓**，
  与中小项目的分布不同（这一点在协议里要写进外推限制）；
- 不能把"跑不动的任务"读成"任务不好"：本文件的 `unrunnable_local` 只说明**本机没有它的环境**；
- 不能用本文件的任何数字当"平台有效性"的证据——这里没有一条判据来自平台。
