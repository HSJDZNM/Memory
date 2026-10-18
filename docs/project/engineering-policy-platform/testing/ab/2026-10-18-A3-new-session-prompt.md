# 新会话提示词 · 执行 A3 干跑（2026-10-18 授权，尚未执行）

> 用法：把下面代码块整段粘贴到**新会话**的首条消息。起点：仓库当前 HEAD（执行前先 `git status` + `git log -1` 核对），工作树应干净。
> 使用者已授权跑 A3，但要求在**新会话**执行；审批条子已签、有效期到 2026-10-25。

```
你是这个仓库的 Lead（主会话）。工作目录 C:/Users/ZNM/Downloads/Memory，git main，工作树干净（执行前用 git status / git log -1 核对起点，不要假设某个哈希）。
先读这些文件再动手（不要凭记忆）：
1) AGENTS.md（尤其第 14/49/51/55 条与「工作方式」）；
2) docs/project/engineering-policy-platform/05-implementation-plan.md（§4 的 A3 行、§5.2/§5.6、§2.3 冻结令、§8 变更控制）；
3) docs/project/engineering-policy-platform/06-plan-progress.md（§7.1 的 P-A3-002..006、§7.5 的 P-B2-*、R-A-GATE-01/02）；
4) docs/project/engineering-policy-platform/04-open-work.md 的 5.71/5.72/5.73/5.74；
5) docs/project/engineering-policy-platform/testing/ab/2026-10-18-A3-unblock.md（**必须读 §10 的更正**：.policy 路径改裸名、approval_file 必填、参数只传 command+description）；
6) docs/project/engineering-policy-platform/readings/2026-10-18-A3-single-action-probe.md 与 2026-10-18-A3-U2b.md（U1/U2/U3/U2-b 的结论与限制）；
7) docs/project/engineering-policy-platform/readings/2026-10-18-B2-gate.md（B2 已落地，不要重做）。

任务：执行 A3「干跑四数」。使用者已明确授权（2026-10-18），但要求在新会话执行；审批条子已签：
.tmp/a3b/task-project/.policy/approval.json（approval-pwsh-a3，schema 1.2、exec.pwsh、两族 pattern、
7 天、expires 2026-10-25T10:45:03Z、sha256 9abd73a3…）。**你不得签发或修改审批**；若必须重签，
停下来向使用者报告并请求，不要自批。

硬约束（逐条遵守）：
- 受治臂启动的 cwd **必须是任务树根**（U1/D2：在子目录或项目外启动时，判定按 projectDir、写入按会话 cwd，判的不是同一个文件）。
- .policy 配置里的路径必须用**裸名**（audit.jsonl / tool-registry.yaml / tool-registry.approved.json /
  enforcement-ledger.jsonl / approval.json），并显式写 approval_file；模板的 .policy/… 前缀会解析成
  .policy/.policy/…（U2-b §10 实测 5 条 exists=False）。
- 受治命令只传 command + description；timeoutMs/workdir/run_in_background/sandbox_permissions/justification
  任一出现都会 approval_invalid（U2-b C 格实证）。
- 不签审批、不放宽 registry/hooks/超时、不改任何 allow/block 规则；只有「构造」确有需要才改产品代码，
  且必须单独提交 + 用例 + 走本机门禁。
- B1/B3 未解冻，不要做；B2 已落地（47fa325），不要重做；阶段 D 不开跑（A3 是它的前置）。
- 本地提交、不推送；同一工作树只跑一个 ci_local；临时产物只写 .tmp/a3b/；进度写 06（追加式），
  结论读数写受跟踪的 docs/.../readings/（不要指向 .tmp）。
- 用 Agent Teams 提高效率：可派 1–2 个 teammate（任务包物化 / 四数装配器），写区分开、不要重叠；
  受治会话本身与最终记录由 Lead 负责。

执行顺序（建议）：
1) 复核起点：git HEAD/工作树、approval.json 的 sha256 与 expires；读上面 7 份文档；与本文不一致就先记差异。
2) 物化任务包（解冻包 §1/§2）：从 examples/dsh/b-plan/sample-project 复制到 .tmp/a3b/task-project；
   生成 first-message.txt / interfaces.md / acceptance.md / allowed-writes.txt（A3-T1「订单审计台账」，
   8 文件 5 层，首条消息逐字节固定）；不要复制旧 .policy 的审计/台账。
3) 装配受治臂（解冻包 §3 + §10 更正）：.policy 四文件、插件 patch、预算 20000+5000<30000；
   核对 U1/U2/U3/U2-b 前置（尤其 cwd=任务树根）。
4) 正式干跑：headless + --patch 启动受治臂，cwd=任务树根，首条消息逐字节使用 first-message.txt；
   保存会话、审计、台账与产物到 .tmp/a3b。
5) 量四数（解冻包 §5）：①写动作治理覆盖率（分母=任务实际文件变化；缺的标 unmeasured；run_code 内部写不算覆盖）
   ②命令族成功率（首次通过；失败按 approval_invalid / command_not_allowlisted / 其他分类）
   ③路径族 layer 声明（每个触碰路径族都有 layer）④上下文触顶（阈值随窗口，记 reading_context）。
   装配器放 .tmp/a3b/；若复用再升格 tools/ 必须按 AGENTS 第 55 条建轴。
6) 判定与记录：4/4 通过 ⇒ 阶段 D 前置成立（**不要**开跑 D，等使用者）；任一不过 ⇒ 记「不符合/跑不成」
   + 触发条件 + 复现，并按解冻包 §6 列最小修复清单。证据落
   docs/project/engineering-policy-platform/readings/2026-10-18-A3-dryrun.md（跨日按实际日期），
   06 追加 P-A3-007 与读数/变更记录，04 的 5.73 状态同步。
7) 收口：工作树干净；若改了产品代码，跑 python tools/ci_local.py 且 26/26 才算绿；
   报告不许写「平均/提升 X%/显著」，n=1 只写案例与过程读数。

给你的简报（≤40 行）：四数逐条读数与三态、门是否 4/4、证据指针、下一步（D 或修构造）、
仍需人工做的事（重签/裁定的项）。
```

## 为什么这些约束非写不可（给新会话的备注）

- **cwd=任务树根**：a7 的 D2 实测——启动 cwd 与任务树不一致时，目标归一化按 projectDir、工具真实写入按会话 cwd，出现 `post_inconsistent` / `evidence_unavailable`，A3 的 ① 会直接失真。
- **裸名 + approval_file**：U2-b §10 实测模板路径会解析成 `.policy/.policy/…`（注册表装载失败关闭）；缺 `approval_file` 时条子永远不被加载。
- **只传 command+description**：条子只覆盖这两格；多一个参数就是 `approval_invalid`（U2-b C 格），会把 ② 的失败全部误算成"平台治理不成功"。
- **不得自签**：AGENTS 第 14 条；代理签的审批等于伪造授权。需要重签时停下来找使用者。
- **阶段 D 不开跑**：05 §4 规定 A3 的 4/4 只是 D 的**前置**，开跑 D 还需使用者另行确认。
