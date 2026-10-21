# 2026-10-21 间接执行面裁定（`tools/**` 经 CI 调用、`.gitattributes`）

> 性质：**裁定**（不是实现）。对象 = 04 5.87 的两个残项：经 CI 调用的 `tools/**` 是间接执行面；
> `.gitattributes` 仍可被写类工具改。裁定问题：是否把它们纳入注册表的受保护前缀，或改按「规则 + 审批」。
> 依据：05 §4 C3 的接受边界、AGENTS 第 13/14/17 条、new-session-prompt §3.6。
> 本裁定**不改注册表**（因此不需要重审），只改文档与登记。

## 0 结论（三句话）

1. **`tools/**` 不纳入受保护前缀**，也不单独设「写 `tools/` 需审批」：它**关不住这个类**——CI 同样执行 `src/**`（pytest 与各模块 CLI）与 `tests/**`，而它们必须保持可写；
   单封 `tools/` 只会挡住仓库自己的日常维护（D 实验的 treatment 已经把 `tools/**` 定为**生产代码**，即正常开发对象），安全收益接近 0。
2. **`.gitattributes` 不纳入受保护前缀**：它是**证据面**（eol / binary / diff / linguist 属性），不改变运行时读到的内容，也不参与任何判定；
   改它的后果是"仓库里文件的存储与展示方式"，不是"执行什么代码"。
3. 这两个残项的正确定位是**已接受的残余风险 + 补偿控制**（提交面终检 C3、CI 全量跑、diff 人工可见），不是"再加一条前缀"。
   复审日 **2026-12-31**（与本轮其他到期项同日）；改动本裁定的触发条件见 §4。

## 1 事实取证（都读文件，不猜）

| 事实 | 证据 |
| --- | --- |
| CI 直接执行 14 个 `tools/*.py` | `.github/workflows/phase-8.yml` 的 `run:` 行：check_repo_consistency / secret_scan / check_text_conventions / validator_loop / dsh_sandbox_loop / retrieval_eval / enforcement_loop / agent_loop / api_loop / orchestration_loop / phase_evidence / check_notebook / policy_bench / governance_gap_probe |
| CI 同样执行 `src/**` 与 `tests/**` | 同文件：`python -m pytest tests/...`、`python -m policy.check`、`validators.cli`、`adapters.dsh.hooks`、`api.cli` 等 20+ 处 |
| CI **不引用任何仓库密钥**，令牌只读 | 同文件 `permissions: contents: read`；`secrets` 零命中（`grep secrets .github/workflows/phase-8.yml` 0 条） |
| 工作流文件本身已被前置阻断 | 注册表 1.4 的 `blocked_prefixes` 含 `.github/workflows`（`readings/2026-10-21-C3-git-surface-guard.md`：7 条翻面、20 条相等） |
| `.gitattributes` 只声明 eol / binary / diff / linguist | `* text=auto eol=lf`、`*.bat/cmd/ps1 eol=crlf`、二进制清单、`*.md linguist-documentation`；不改变任何运行期读取 |
| 写类工具的受保护前缀今天不含 `tools` | `registry/tool-registry.yaml` 四个写类工具的 `blocked_prefixes`：policies / registry / adapters / api / validation / .policy / .git / .github/workflows |
| 提交面终检是整树判定 | `tools/final_tree_gate.py`（C3 v1）：整树 43 条 + 真实验证器 + `RuleSet.identity` 钉住；退出码 0/1/2 |

## 2 三个选项与代价

| 选项 | 做法 | 关得住吗 | 代价 | 结论 |
| --- | --- | --- | --- | --- |
| A 纳入前缀 | `tools` 加进四个写类工具的 `blocked_prefixes`（注册表 1.4→1.5 + 重审） | **否**：`src/**`、`tests/**` 同样被 CI 执行；攻击者改 `src/policy/engine.py` 即可 | 日常维护（修工具）被自己的平台阻断；与 D treatment 的"tools 是生产代码"自相矛盾；需重审 + 读数 + 回退面 | **拒绝** |
| B 规则 + 审批（按路径改审批） | 让 `fs.edit` 对 `tools/**` 要求人工审批 | 否（同上），且审批**只覆盖写类工具**，覆盖不了"改 src 后 CI 执行" | 注册表审批模型是**按工具**不是按路径 ⇒ 新增"路径条件审批"语义 = 协议变更 + 重审 + 新增失败面；日常改工具每次都要签条子 | **拒绝** |
| **C 登记 + 补偿控制（选定）** | 在 04 5.87 与本裁定登记为**已接受残余**；补偿 = C3 终检（提交面）+ CI 全量（推送面）+ `permissions: contents: read` + 无密钥 + diff 可见 | 不承诺"关住"，承诺"**可看见、可复核、到期必复看**" | 残余风险仍在：单人有写权限者可在一次提交里改 `tools/` 或 `src/`，只有 CI 与人工 diff 能发现 | **选定** |

**为什么这是诚实的答案**：前缀黑名单描述的是"写类工具**能写哪些路径**"，它天然不适合表达"这段代码**将来会被谁执行**"——后者是**供应链/提权**问题，
需要的是运行时的文件系统/进程沙箱与分支保护，而本仓库**故意**不启用分支保护（AGENTS「工作方式」第 5 条：单人仓库的边际价值低于把检查前移到本机）。
把 `tools/` 单独封上，只会制造"看起来关住了"的假象——那正是 AGENTS 第 45 条要防的"跑了、是绿的当成覆盖"。

## 3 补偿控制与它仍不覆盖什么

| 控制 | 回答什么 | 仍不覆盖 |
| --- | --- | --- |
| C3 整树终检（`tools/final_tree_gate.py`） | 提交那一刻，整棵树过 43 条规则 + 真实验证器；规则集被改可发现 | 它**不判"这段代码将来会被 CI 执行"**；也不判"提交者是否有恶意" |
| CI 全量（`.github/workflows/phase-8.yml`） | 推送后 20 分钟量级的真跑；14 个工具脚本 + 四套件测试 | 它只证明"在这台 runner 上跑通"，不证明"没有人借工具脚本做别的事" |
| `permissions: contents: read` + 零密钥 | 工具脚本即使被改，也拿不到写权限令牌与仓库密钥 | 仍可篡改产物/证据文件的**内容**（例如伪造读数），但产物本身不进仓库 |
| `tools/secret_scan.py` + `check_repo_consistency.py` | 密钥与文档/配置一致性 | 不判行为意图 |
| diff + 单人对提交的自审（AGENTS 第 38 条） | 人能看到"这次改了哪个工具脚本" | 人可能不看——这是**组织**问题，不是平台能替的 |

## 4 这条裁定什么时候作废（必须重新裁定）

任一成立即重新裁定，**不许沿用本裁定的结论**：

1. CI 开始引用**任何仓库密钥**（`secrets.*`）或写权限令牌 —— 间接执行面从"供应链可见"升级为"可直接外泄/改远端"；
2. 启用分支保护/必需评审（AGENTS 第 5 条的现行决定被推翻）——那时"提交面人工复核"成为可依赖的控制，前缀方案的成本收益要重算；
3. 出现"经 `tools/` 或 `src/` 的改动在 CI 里做了与任务无关的事"的**真实案例**（读数，不是猜想）；
4. 引入运行时沙箱（进程/文件系统隔离）到 CI —— 那时真正的边界存在，前缀不再是唯一手段。

## 5 落点

- 注册表**不改**（无需重审）：`registry/tool-registry.yaml` 与 `registry/tool-registry.approved.json` 一个字节不动。
- 04 5.87 的这一残项转"**已裁定（2026-10-21）：不改注册表**"，并把复审日写在处置列。
- `.gitattributes` 同样不封：它是证据面；与 `tools/**` 同一条裁定，不同理由（见 §0 第 2 句）。

## 6 证据指针

- `.github/workflows/phase-8.yml`（`permissions: contents: read`；14 个 `tools/*.py` 调用点；无 `secrets`）
- `.gitattributes`（eol / binary / diff / linguist 声明）
- `registry/tool-registry.yaml`（四个写类工具的 `blocked_prefixes` 现值）
- `tools/final_tree_gate.py`（整树判定 + 规则集哈希钉住，C3 v1）
- `readings/2026-10-21-C3-git-surface-guard.md`（执行面 7/7 翻面、20 条相等）
- `docs/project/engineering-policy-platform/04-open-work.md` 5.87；AGENTS 第 13/17/45 条与「工作方式」第 5 条
