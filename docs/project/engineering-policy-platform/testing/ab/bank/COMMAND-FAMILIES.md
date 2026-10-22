# 命令族清单（题库 6 题 × exec.pwsh）

> **用途**：给 Lead 生成使用者签的**审批条子**（`python -m enforcement.cli approve --family ...`）时，
> 逐题列出 `exec.pwsh` 的 `tests` / `scripts` / `readonly` 三族需要覆盖的**完整命令形态**。
> 所有形态都必须在注册表 `allowed_commands` 的**完整匹配**白名单内（注册表 1.4：
> `registry/tool-registry.yaml` 的 `exec.pwsh` 段）；不在白名单里的命令**不许靠改题面绕过**，
> 要么改注册表（并 `registry --approve` 重新审核），要么换一种写法。
> 结构性阻断（AGENTS 第 17 条）：命令里出现 `;` `|` `&` 反引号、`$(`、`${`、`>`、`<` 或换行
> 一律 `command_composition_blocked`；出现 `../` `..\` `--output` `--ext-diff` `--no-index`
> 一律 `command_fragment_blocked`。**逐条执行，不拼管道/重定向/分号。**

## 0 注册表 1.4 的三族（`registry/tool-registry.yaml` 的 `exec.pwsh.command_families`）

| 族 | 覆盖的完整形态（逐字） |
| --- | --- |
| `tests` | `^python -m pytest( .*)?$`、`^uv run python -m pytest( .*)?$` |
| `readonly` | `^git (status\|diff\|log\|show)( .*)?$`、`^Write-Output( .*)?$`、`^Get-ChildItem( .*)?$` |
| `scripts` | `^python tools/[A-Za-z0-9_./-]+\.py( .*)?$`、`^python -m (policy\.check\|retrieval\.cli\|enforcement\.cli\|adapters\.dsh\.hooks)( .*)?$` |

> 上表引号内的正则与注册表逐字相同（完整匹配，不是包含匹配）。
> **不在**仓库 1.4 白名单里的常见写法：`python -c`、`python -m <自定义模块>`、`python scripts/*.py`、
> `Get-Content`、`Select-String`、`Test-Path`、`Get-FileHash`、`New-Item`、`Copy-Item`、`Remove-Item`。
> 题面因此只依赖 7 条白名单（`pytest` / `tools/*.py` / `git status|diff|log|show` / `Write-Output` / `Get-ChildItem`）；
> 模型要看文件内容用**文件读取工具**，不要用 `Get-Content`。
> `examples/dsh/b-plan/tool-registry.local.yaml` 是 13 条的本地副本（多 `Get-Content`/`Select-String`/`Test-Path`/`scripts/*.py`）；
> 若 Lead 选它，必须用**它自己的** `approved.json` 重新审核（不要拿仓库的已审核哈希），并在 run-manifest 记注册表哈希。

## 1 旗舰题 `bank-flagship-returns`

工作目录 = 任务树根（`.tmp/bank-flagship/tree`）。

| 族 | 必须覆盖的完整命令形态 | 何时用 |
| --- | --- | --- |
| `tests` | `python -m pytest -q` | M1–M14 每次跑测试（首消息写死这一条） |
| `scripts` | `python tools/refund_demo.py` | M12/M14 演示脚本 |
| `scripts` | `python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl` | M12/M14 数据迁移（产 `data/refunds-v2.jsonl`） |
| `readonly` | `git status --porcelain`、`git diff --stat` | （可选）自查改动面；不得用 `git diff --output` |
| `readonly` | `Get-ChildItem -Recurse` | （可选）看目录；不得用 `Get-Content` 读文件 |

**不需要**：`python -m policy.check`（判定由会话的 PreToolUse 自动做；隐藏 runner 另跑）。
**不许出现**：`python -m pytest -q > out.txt`（重定向）、`python -m pytest -q; python tools/refund_demo.py`（分号）、
`python -c "..."`（不在白名单）。

## 2 跨模块重构 `bank-crossmodule-refactor`

工作目录 = 任务树根。

| 族 | 必须覆盖的完整命令形态 | 何时用 |
| --- | --- | --- |
| `tests` | `python -m pytest -q` | 每步回归 |
| `tests` | `python -m pytest -q tests/test_order_repository.py tests/test_order_service.py tests/test_order_controller.py` | 重构后定向回归（可重复 `--changed`） |
| `scripts` | `python tools/show_api_usage.py`（若 SPEC 采用该脚本；否则**空族**） | 打印旧 API 调用点 |
| `readonly` | `git diff --stat`、`git status --porcelain` | 自查「旧 API 还有没有残留」 |

**不需要** `scripts` 的前提：SPEC 里的兼容门面由测试覆盖、不引入新脚本；若引入，命令必须落在
`python tools/<name>.py` 形态（不能用 `python -m shop.order_api`）。

## 3 修 bug（先有失败测试）`bank-bugfix-first-failing-test`

| 族 | 必须覆盖的完整命令形态 | 何时用 |
| --- | --- | --- |
| `tests` | `python -m pytest -q` | 第 1 步观察失败、修复后转绿（同一条命令） |
| `tests` | `python -m pytest -q tests/test_order_service.py` | 只看目标测试的失败细节 |
| `readonly` | `git diff --stat`、`git status --porcelain` | 确认只改了允许写集合 |

**不需要** `scripts`（本题只修实现 + 补测试/文档）。**特别提醒**：基线自带红测试时，
「改一半」的提议会被 `TESTING-002` 阻断——这是**预期读数**，不是命令族问题（见 `bank/README.md` §6 决策 2）。

## 4 数据迁移 `bank-data-migration`

| 族 | 必须覆盖的完整命令形态 | 何时用 |
| --- | --- | --- |
| `tests` | `python -m pytest -q` | 每步回归 |
| `scripts` | `python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl` | 迁移（原子替换 + 幂等） |
| `scripts` | `python tools/verify_ledger.py --path data/ledger-v2.jsonl` | 迁移后自检（只读校验，退出码 0/1） |
| `readonly` | `git status --porcelain`、`git diff --stat` | 确认输入文件没被就地改 |

**不需要**：`python -m json.tool`（不在白名单；用 `python tools/verify_ledger.py` 代替）。

## 5 并发 / 异步 `bank-async-concurrency`

| 族 | 必须覆盖的完整命令形态 | 何时用 |
| --- | --- | --- |
| `tests` | `python -m pytest -q` | 异步用例（`asyncio.run`，不用插件） |
| `tests` | `python -m pytest -q tests/test_notify_worker.py` | 定向复跑（确定性调度失败时） |
| `scripts` | `python tools/notify_smoke.py` | 冒烟脚本（跑一个确定性队列、打印 JSON） |
| `readonly` | `git status --porcelain` | 确认没有新增依赖/锁文件 |

**不需要**：任何后台执行（`run_in_background=true` 在注册表层**显式拒绝**，AGENTS 第 17 条 + 04 5.35）。

## 6 文档 / 配置 `bank-docs-config`

| 族 | 必须覆盖的完整命令形态 | 何时用 |
| --- | --- | --- |
| `tests` | `python -m pytest -q` | 加载器/校验脚本用例 |
| `scripts` | `python tools/check_config.py --config config/app.yaml` | 配置校验（未知键失败关闭、退出码 0/1） |
| `readonly` | `git diff --stat`、`git status --porcelain` | 看文档/配置改动面 |

**不需要**：`python -m policy.check`（判定自动）；`Get-Content` 读配置（用文件工具 + `check_config`）。

## 7 审批条子怎么签（Lead 用；每工具一条记录，重签是取代）

以旗舰题为例（`$g` = 任务树根；注册表与已审核哈希在 `$g/.policy/`；实例化路径以实际装配为准）：

**先记住一条约束**：一个 `approval.json` 里**每个 `tool_id` 只保留一条记录**，同一工具再签是**取代**（`--replace` 才是清空已有记录）。所以 `exec.pwsh` 的 `tests` / `scripts` / `readonly` 三族**不能分开签成三条**——后一条会把前一条覆盖；正确做法是**一条 `exec.pwsh` 的 `command` 模式（b-plan 本地注册表 13 条 `allowed_commands` 的三族并集，仍是 `allowed_commands` 的子集）+ 一条 `exec.run_code`**，共两条记录。

```powershell
# 0) 先审核本地注册表（若用了副本）并核对
python -m enforcement.cli registry --registry "$g/.policy/tool-registry.yaml" --approved "$g/.policy/tool-registry.approved.json" --approve --reviewer <name>
python -m enforcement.cli registry --registry "$g/.policy/tool-registry.yaml" --approved "$g/.policy/tool-registry.approved.json" --verify

# 1) exec.run_code（code 是整段 Python，用 (?s) 让 . 跨行；description 通配）
python -m enforcement.cli approve --registry "$g/.policy/tool-registry.yaml" --approved "$g/.policy/tool-registry.approved.json" --request "$g/.policy/run-code-request.json" --out "$g/.policy/approval.json" --granted-by <name> --roles reviewer --binding pattern --max-uses 1000 --ttl 604800 --param-pattern 'code=(?s).*' --param-pattern 'description=.*' --approval-id approval-run-code

# 2) exec.pwsh：一条记录，command = b-plan 本地注册表 13 条的并集（仍是该 allowed_commands 的子集）
#    并集逐条来自 examples/dsh/b-plan/tool-registry.local.yaml 的 13 条 allowed_commands
#    （tests 4 条 + readonly 6 条 + scripts 3 条 = 13 条）；题库题面用到 Get-Content /
#    Select-String / Test-Path，仓库 1.4 的 7 条覆盖不到。外层 (?:...) 与 --family 的
#    union_pattern 并法相同，可用 resolve_family 复核；命令族权威仍以注册表 command_families 为准。
$union = 'command=(?:(?:^python -m pytest( .*)?$)|(?:^uv run python -m pytest( .*)?$)|(?:^pytest( .*)?$)|(?:^python -m unittest( .*)?$)|(?:^python tools/[A-Za-z0-9_./-]+\.py( .*)?$)|(?:^python scripts/[A-Za-z0-9_./-]+[.]py( .*)?$)|(?:^python -m (policy\.check|retrieval\.cli|enforcement\.cli|adapters\.dsh\.hooks)( .*)?$)|(?:^git (status|diff|log|show|ls-files|rev-parse)( .*)?$)|(?:^Get-Content( .*)?$)|(?:^Select-String( .*)?$)|(?:^Test-Path( .*)?$)|(?:^Write-Output( .*)?$)|(?:^Get-ChildItem( .*)?$))'
python -m enforcement.cli approve --registry "$g/.policy/tool-registry.yaml" --approved "$g/.policy/tool-registry.approved.json" --request "$g/.policy/shell-request.json" --out "$g/.policy/approval.json" --granted-by <name> --roles reviewer --binding pattern --max-uses 1000 --ttl 604800 --param-pattern $union --param-pattern 'description=.*' --approval-id approval-pwsh-all
```

**反例（原来的三步写法；错在把一个工具签成三条记录）**：

```powershell
# 下面三条都指向 exec.pwsh：第 1 条 tests 被第 2 条 scripts 取代，再被第 3 条 readonly 取代；
# 最终文件里只剩 readonly 一条记录，tests / scripts 的命令会 approval_invalid。
# --family 本身没问题，错的是对同一个 tool_id 分开签三次。
python -m enforcement.cli approve --registry "$g/.policy/tool-registry.yaml" --approved "$g/.policy/tool-registry.approved.json" --request "$g/.policy/shell-request.json" --out "$g/.policy/approval.json" --granted-by <name> --roles reviewer --binding pattern --max-uses 1000 --ttl 86400 --family exec.pwsh:tests --param-pattern "description=.*" --approval-id approval-tests
python -m enforcement.cli approve --registry "$g/.policy/tool-registry.yaml" --approved "$g/.policy/tool-registry.approved.json" --request "$g/.policy/shell-request.json" --out "$g/.policy/approval.json" --granted-by <name> --roles reviewer --binding pattern --max-uses 1000 --ttl 86400 --family exec.pwsh:scripts --param-pattern "description=.*" --approval-id approval-scripts
python -m enforcement.cli approve --registry "$g/.policy/tool-registry.yaml" --approved "$g/.policy/tool-registry.approved.json" --request "$g/.policy/shell-request.json" --out "$g/.policy/approval.json" --granted-by <name> --roles reviewer --binding pattern --max-uses 1000 --ttl 86400 --family exec.pwsh:readonly --param-pattern "description=.*" --approval-id approval-readonly
```

**三条纪律**：
1. **逐格覆盖**：条子只声明 `description` 与命令；`timeoutMs` / `workdir` / `run_in_background` 由审批协议 1.3 的**默认值**覆盖（省略 = 只接受默认值）。
   模型若带非默认值，条子会 `approval_invalid`，拒绝理由会点名缺的参数——照抄重签同一 `--approval-id` 是**取代**。
2. **命令参数手写并集，族数据仍是权威**：三族并成一条 `command` 是审批层的写法；命令形态仍由注册表 `command_families` / `allowed_commands` 定义，
   改族 = 改注册表 = 必须重新审核并重签这条 `exec.pwsh` 记录。族与白名单的一致性由
   `python tools/approval_allowlist_audit.py --check --registry <副本> --approved <已审核>` 双向比对（0 命中才算齐）。
3. **审批绑上下文摘要**：每条 `approval.json` 必须按**这棵树**签发；换树 = 重签。run-manifest 记
   `approval_sha256` 与两条记录的 id（`approval-run-code` / `approval-pwsh-all`）。

## 8 一页速查：每题需要的族

| 任务 | tests | scripts | readonly |
| --- | --- | --- | --- |
| 旗舰-returns | `python -m pytest -q` | `python tools/refund_demo.py`、`python tools/migrate_refunds.py --in ... --out ...` | `git status --porcelain`、`Get-ChildItem -Recurse` |
| 跨模块重构 | pytest 全集 + 三个定向文件 | （可选）`python tools/show_api_usage.py` | `git diff --stat`、`git status --porcelain` |
| 修 bug | pytest 全集 + 目标测试 | —（空族） | `git diff --stat`、`git status --porcelain` |
| 数据迁移 | pytest 全集 | `python tools/migrate_ledger.py ...`、`python tools/verify_ledger.py --path ...` | `git status --porcelain`、`git diff --stat` |
| 并发/异步 | pytest 全集 + 目标测试 | `python tools/notify_smoke.py` | `git status --porcelain` |
| 文档/配置 | pytest 全集 | `python tools/check_config.py --config config/app.yaml` | `git diff --stat`、`git status --porcelain` |
