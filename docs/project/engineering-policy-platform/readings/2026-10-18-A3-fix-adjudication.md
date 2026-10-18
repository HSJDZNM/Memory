# 2026-10-18 A3 干跑问题修复裁定（三派评审 + Lead 裁决）

> 触发：使用者 2026-10-18 指示「对 A3 干跑问题进行修复，裁定问题内部多方研讨后自行裁决，所有前置测试和任务完成后开启阶段 D」。
> 输入：三份独立评审（构造优先派 / 平台优先派 / 红队审稿人）对 F-1..F-7 的书面意见（只读，不改文件）；v1 读数 `readings/2026-10-18-A3-dryrun.md`；06 P-A3-008..010。
> 本文件是**裁定与预注册**，不是读数：它冻结 A3 v2 的构造与四数口径，并给出阶段 D 开场条件。实施与两次读数另记。
> 起点：HEAD `12e758b`（工作树干净）。

## 1 三派立场（摘要）

| 议题 | 构造优先派 | 平台优先派 | 红队审稿人 |
| --- | --- | --- | --- |
| F-2 tools/ | 保留 F2；把 demo 预置进基线、A7 改为「跑+贴输出」；登记缺口 | C2 缩小版 `not_applicable_patterns`（≈3 人日、PIPELINE 1.5、R-d） | 保留 F2；`production_patterns` 增 `tools/**/*.py` + 允许写测试（≈1–1.5 人日）；反对删族 |
| F-3 熔断 | 只修构造（F-1），重跑观察 | 改「失败分类」（mechanism vs verdict），LEDGER 1.0→1.1 | 只修构造；**先更正「窗口 60s」错误**（实际用 breaker_seconds=300 当失败窗口）；登记字段两义 |
| F-4 装配器 | 修 `.tmp` + 复算旧产物；暂不升格 | 两处谓词都修 + 升格 `tools/` 建轴 | 升格最小集（command_families+coverage）并补 fix-before-red |
| F-5 启动 | 批量 danger-full-access + D 记录 | (a) + 探 profile root 独立重定向 | junction profile root；若失败退回 (a) + **跑后哈希复核** |
| B1 | 本单元非前置，登记威胁/触发 | 条件依赖，登记威胁 | 本单元非前置；C 臂对照因此失效须写明 |
| D 开场 | 只跑 D 校准臂，在 A3 v2 4/4 之后 | 校准 + 明确 A/B/C 未开 | 只跑校准；校准不必以 A3 4/4 为前提，但按使用者顺序放在其后 |

三派一致的四条：**不删 F2 族**（降分母=实质减弱判据）；**F-3 先修构造**；**B1 不作为本单元前置但须显式登记威胁**；**A/B/C 现在不开跑**（treatment 未定义、任务包/评分器未冻结）。

## 2 Lead 裁定（R-A3-FIX-01..12）

| # | 裁定 | 依据 / 代价 | 可证伪条件 |
| --- | --- | --- | --- |
| A-1（F-2） | **保留 F2 与 demo 交付物**；v2 基线树预置 `tools/audit_demo.py`（12 文件），**允许写 7 路径**（不含 demo），A7 改为「运行已有脚本并贴输出」。不删族、不改平台。 | 预置是**有披露的收缩**（0.3–0.5 人日），保 ② 分母=2；平台缺口另登记 04 5.75（tools/** 的 python 写仍被 TESTING-002 uncovered_checker 阻断，canary 常红）。平台派 C2 方案留 5.75 候选。 | 若 F2 首试仍不通过（审批/预检/沙箱）→ 说明问题不在「能不能写」而在脚本族本身，转平台裁定并暂停 v2 结论。 |
| A-2（F-3） | **先修构造（F-1），重跑观察**；不改熔断/事后核对口径。更正 v1 读数：「窗口 60s」是误读——`precheck.py` 用 `breaker_seconds=300` 当失败窗口，三次失败 13:10:15/13:11:08/13:11:34 落在 300 s 内，13:11:51 开闸。`breaker_seconds` 同时表达「失败窗口」与「保持时间」的两义登记为 04 5.76。 | 0.5 人日重跑；0.3 人日更正读数。改口径会放过真正反复失败的命令。 | v2 重跑只剩 1 次 expected-red 仍出现 `circuit_open`，或窗口内还有别的非零命令 → 转平台裁定，先给「哪三条 execution 记录进计数」的逐条账。 |
| A-3（F-4） | 修 `.tmp/a3b/bin/command_families.py`：`pass = allow + grant + 真执行`；`post_validated` 与命令退出码改为**单列读数**，不再是通过条件；`host_executed` 读 `post_evidence.process.exit_code` 或 `tool/result.isError=false`。用修正仪器**重算 run-01**（F1 fail→pass、F2 仍 block ⇒ ② 仍 1/2），证明修的是归因而非判据。升格 `tools/` 暂缓，触发：仪器进 D 判分链或第三次复用。 | 0.3–0.5 人日；复算结果见 §3。 | 复算把 run-01 从 1/2 抬到 2/2，或结论改变 → 判定作废、重审。 |
| A-4（F-5） | 启动受治 dsh 时对**同一条启动命令**做一次性 `danger-full-access` 授权，批量执行（一次授权跑完需要的会话）；run-manifest 记录 `launcher_sandbox=danger-full-access`，并在**跑后**复核 approval/registry/HEAD/rule_set_hash 不变。DSH_HOME 整搬否决（含凭据）；profile root junction 探针留作触发项。 | 0 步 + 文书；受治会话自身仍 workspace-write、approval/asked=0。 | 若会话日志出现 `approval/asked>0` 或 `sandbox=danger-full-access` → 该 run 作废；两次启动被拒、或无审批环境 → 转最小 DSH_HOME 方案。 |
| A-5（B1） | **B1 不作为本单元（A3 v2 + D 校准）前置**；把 05 §4 的依赖改为**条件依赖**：A/B/C 主实验依赖 B1（或经裁定的替代 treatment）+ 用户签 1.3 条子。威胁：C 臂无审批、A/B 有审批，「真实用法」外推不成立，直到 B1 落地。触发：v2/D 任一次 pwsh 因「注册表声明为可选、带默认值的参数」得到 `approval_invalid` 且挡住必需命令 → B1 立即升为前置，当轮读数作废。 | 文书 0.3 人日；B1 本体 4 人日仍排队。 | 上述触发出现即改判；未出现则维持。 |
| A-6（D 开场） | **拆两门**：① **D 校准门**——P+（controller 直接 import repository，ARCH-001）必须被拦、P−（repository docstring 编辑）必须放行；真 Hook CLI、无模型、无审批。② **A/B/C 构造门**——A3 v2 4/4 **且任务完成（A1–A7）**；任务包/判据/仪器/评分器冻结后才能开 A/B/C。本次只宣告**校准门通过**；A/B/C 不开跑（treatment 未定义：B1 未落地、B 臂与 A 臂决策会逐字节相同）。 | 校准 0.5 人日（v1 已预跑通）；A/B/C 另需 B1+treatment+评分器。 | P+ 被放行或 P− 被拦 → D 校准不过，A/B/C 无意义；校准通过但 A/B 决策完全相同 → treatment 不存在，A/B 作废。 |
| A-7（② 判据） | **冻结**：② 首次尝试通过 = `decision∈{allow,allow_with_warnings}` + grant/allow_delegated + 真的进入执行（`post_evidence.process.exit_code` 可读或会话 tool/result 非错误）；命令自身退出码与 `post_outcomes` 只作单列读数；分母 = 预注册族数（本单元 **2**）；≥90% 且分母 ≥2 族才判；<2 族记「不可判定」不记通过。v2 run-manifest 写入该判据原文 sha256。 | 05 §5.6 与解冻包 §5.2 的同一口径；不做事后选择。 | 若 v2 判据与本节文字不一致 → 该 run 作废。 |
| A-8（协议） | 阶段 D 以 **05 §5.1 四臂（A/B/C/D）** 为准；`testing/ab/ab-protocol.md` 的三臂（off/advisory/enforced）是历史 W7 载体，`tools/ab_arm.py` 只作为机械补丁/Hook 组件使用，不是 D 协议。记 05 §8。 | 文书。 | 若发现 ab_arm 的判定与 05 四臂语义冲突 → 以 05 为准并补差异记录。 |
| A-9（05 §5.1 措辞） | 原文「D 不过（P+ 被拦或 P− 放行）」把成功条件写成失败条件；改为「D 通过 = P+ 被拦且 P− 放行；D 不过 = P+ 被放行或 P− 被拦」。记 05 §8。 | 纯文案修正。 | 无。 |
| A-10（可复现） | v2 任务包（5 文件 + demo 脚手架 + reset 脚本）**入库**到 `examples/dsh/b-plan/a3-task-v2/`；run-manifest v2 写死任务包 sha256、四数判据 sha256、仪器 sha256；v1 读数追加更正节（熔断窗口 / ② 双读数）。 | 0.3 人日。 | 入库文件与 v2 实际运行字节不一致 → run 作废。 |
| A-11（F-6/F-7） | registry 副本固定用与外部 Governance 逐字节相同的那份（sha `45838cd8…`）；两份差异只在注释，`--verify` 均 0 —— 是记录卫生，不是授权面漏洞。首消息引用一律用 v2 的 sha256。 | 文书。 | 若 `--verify` 或 approved digest 变化 → 先停跑。 |
| A-12（任务完成度） | 4/4 保留原四数定义；但**D 开场另加**「A3 v2 任务完成（A1–A7）」条件（不改 A3 四数判据）。读数表必须附任务完成度、attempted vs landed、受治/非受治比、block 的 rule_id 分布。 | 1 行文书；防止「任务 0/8 也能 4/4」。 | 若任务未完成仍宣告 D 开场 → 违反本节，回退。 |

## 3 已执行的两项先行修正（写本文件前完成）

1. **F-4 仪器修正并复算 run-01**：`command_families.py` 的 `host_executed` 改为「`post_evidence.process.exit_code` 可读 或 `tool/result.isError=false`」，`pass` 不再要求 `post_validated`。复算 run-01：`first_pass=1/2`（F1 由 fail→pass，F2 仍 `circuit_open`）——② 仍 **1/2=50%**，结论不变；u2b 自测 1/1 不变。旧仪器读数 0/2 保留为历史。
2. **v1 读数更正**：熔断窗口按 `precheck.py` 用 `breaker_seconds=300` 作失败窗口（三次失败 13:10:15/13:11:08/13:11:34，13:11:51 开闸），不是 60 s；② 的主读数按 A-7 口径为 1/2（旧严格仪器 0/2 仅作历史）。

## 4 A3 v2 预注册（冻结；跑前不改）

| 项 | 冻结值 |
| --- | --- |
| 基线树 | `examples/dsh/b-plan/sample-project` 11 文件 + 脚手架 `tools/audit_demo.py` = **12 文件**（v2 目录入库后按 manifest 校验） |
| 允许写 | **7 路径**：`src/shop/order_audit.py`(新) / `src/shop/order_service.py` / `src/shop/order_controller.py` / `tests/test_order_audit.py`(新) / `tests/test_order_service.py` / `tests/test_order_controller.py` / `README.md` |
| 里程碑 | M1 A4-only 测试 + pytest（预期红）；M2 模块 + pytest；M3 先 service 再 A1/A2/A3 测试 + pytest；M4 先 controller 再 A5 测试 + pytest；M5 运行已有 demo；M6 README；M7 最终 pytest+demo+report |
| ② 族 | **2 族**：F1 `^python -m pytest( .*)?$`、F2 `^python tools/[A-Za-z0-9_./-]+[.]py( .*)?$` |
| ② 通过 | 首次尝试 = allow+grant+真执行（A-7）；分母 2；≥90% |
| ① / ③ / ④ | 定义不变（05 §5.6）；① 分母=实际文件变化；③ 分母=实际被写路径；④ compaction 事件/峰值压力比 |
| 任务完成 | A1–A7 全达 + 最终 `python -m pytest -q` exit 0 + `python tools/audit_demo.py` exit 0（D 开场的附加条件，不改四数） |
| 起点锁 | v2 run-manifest 记录 HEAD、approval sha/expires、registry 对 sha、任务包 sha、判据 sha、仪器 sha、audit 起始行号、launcher 授权方式 |
| 不许变 | 不删族、不改 ①③④ 定义、不把未落地的写算分子、不用 run_code 内部写算覆盖、不放宽 registry/hooks/超时 |

## 5 阶段 D 开场条件（本次只到校准门）

1. **门 1：D 校准**——P+ 被拦（block，含 ARCH-001）、P− 放行（allow/allow_with_warnings）；真 Hook CLI；另有**常红 canary**：`write tools/audit_demo.py` 仍应被 TESTING-002 uncovered_checker 阻断（证明平台缺口未消失、绿的是任务不是平台）。
2. **门 2：A/B/C 构造**——A3 v2 4/4 + 任务完成；任务包/判据/仪器/评分器冻结；treatment 已定义且 activation 证明两臂决策不同。**本次不满足**：B1 未落地（A/B 无 treatment）、C 臂装配与评分器未冻结。
3. 结论写法：只写「D 校准门通过（P+/P− 读数）」，**不得**写成「D 开跑」「治理有效」「A/B 可开」；A/B/C 明确记为「未开跑/前置未满足」。

## 6 仍缺（本裁定不解决）

- B1（审批参数域 1.2→1.3）+ 用户签 1.3 条子：A/B/C 主实验的真实前置；4 人日 + 人工。
- `tools/**` 的 python 写在 pre_evidence 下的取证缺口（04 5.75）：C2/声明方案待裁定。
- 熔断 `breaker_seconds` 两义（04 5.76）：是否拆成 failure_window_seconds + breaker_seconds 待裁定；改数据要重审。
- 测量装配器升格 `tools/`：触发后再做（AGENTS 55 建轴 + 用例 + 门禁）。
- D 的评分器（T/C/A 100 分）与 C 臂装配：A/B/C 之前必须冻结（05 §5.3 只给维度，没给具体谓词/规则清单）。

## 7 证据指针

- 三派评审原文：本会话 subagent 输出（debate-construction / debate-platform / debate-redteam，2026-10-18）；要点已在上表，原文未入库（只读评审）。
- v1 读数：`readings/2026-10-18-A3-dryrun.md`（含 §12 更正节）；复算产物：`.tmp/a3b/readings/run-01-command-families-fixed.json`、`u2b-command-families-fixed.json`。
- 05：§5.1/§5.6/§8（本裁定同批修改）；04：5.75/5.76（新登记）；06：D-20261018-10/11（更正与裁定记录）。
- D 校准预跑：`.tmp/a3d/d-calibration.json`（P+ block / P− allow，pass=true），正式记录在 A3 v2 之后重跑并入库。
