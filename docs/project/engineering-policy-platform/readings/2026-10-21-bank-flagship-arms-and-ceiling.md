# 2026-10-21 旗舰题评分器、T/C/A 天花板与 A/B/C 臂装配

> **性质**：实现 + 实测读数（Lead）。起点 HEAD `d9ede05`（工作树新增 `scoring.yaml` 与 `.tmp` 装配现场）。
> **范围**：只动题库旗舰题与 `.tmp` 装配目录；**不改** `src/**`、`examples/**`、`registry/**`、dgate2 冻结件。
> **依据**：`readings/2026-10-21-bank-seven-adjudications.md` §1（每题独立 `scoring.yaml`、T 记通过数/48 + 加权分、
> C 从 12 个直接点冻结 8 条、A=10×3、冻结顺序 PLAN→隐藏→参考解→天花板→签「可开跑」）；`bank/README.md` §4。

## 0 一句话

旗舰题有了**自己的评分器** `scoring.yaml`（bank-scoring/1，version 1），参考解实测 **T 48/48、C 30/30、A 30/30**；
实验冻结集 37 条（组合摘要 `95e93f9f…`，**reference/ 不冻结**；签名后重冻结会换值），A/B/C 三臂已装配（基线 `b6d6d2f7…`），
两臂注册表已自审（`da2d34f5…`）。**当前卡在只能由使用者做的两步**：签审批条子、提供启动环境的凭据。

## 1 `scoring.yaml`（本题独立冻结；不复制 dgate2 字节）

| 维度 | 取值 | 与 dgate2 的关系 |
| --- | --- | --- |
| T（40） | `hidden/runner.py` 的 48 条；记 passed/total + `round(40 × passed / 48)`；exit 2 = 跑不成（不记 0 分） | 形态相同（通过数 + 加权），分母与条目由本题冻结 |
| C（30） | 16 个改动 `.py` 逐个 `policy.check`；8 条规则 × 3（24）+ 11 个冻结文件未改（3）+ 无旁路 B1/B2/B3（各 1） | **同一组 8 条规则**（ARCH-001 / TESTING-001 / TESTING-002 / STYLE-002 / STYLE-018 / DOC-001 / STYLE-001 / STYLE-010），跨题可比；本题另外 4 个直接点只进过程读数 |
| A（30） | `structure_metrics 1.1` 的 A1–A10，pass=3 / fail=0 | 同一工具与阈值；`layers.yaml`/`interfaces.yaml` 是本题自己的声明 |

- `frozen_inputs` 钉住 10 个摘要（任务包 manifest、基线组合摘要、首消息、允许写、hidden PLAN/runner、layers、interfaces、命令族、reset-arm）；
  `scoring.yaml` 自身摘要由 freeze set 现场计算（避免自指）。
- `invalidation` 12 条：任务包/基线/hidden/scoring/layers/interfaces 漂移、规则集、工具版本、起点不干净、非确定性、
  外部写者、预算截断、作废超 1/3。
- **没有**伪造 T 的逐条权重：本题 48 条等权（决策原文就是「通过数/48 + 加权分 `round(40×pass/48)`」）。

## 2 天花板实测（参考解，不是模型 run）

方法：`reference/tree` 复制到 `.tmp/bank/ref-ceiling`；T 用 hidden runner；C 对 16 个改动 `.py` 逐个跑
`policy.check`（`--config-root .`、`--layer` 取 `layers.yaml`、19 个 `--changed`、固定 `--request-id`）；
A 用 `structure_metrics --layers/--interfaces`；B1/B2/B3 与 11 个冻结文件哈希独立算。

| 维度 | 读数 | 说明 |
| --- | --- | --- |
| T | **48/48**，exit 0 | 38 T + 5 EN + 5 I；失败 0 |
| C | **30/30** | 8 条规则各 3（24）+ 冻结 3 + B1/B2/B3 各 1；16 次判定全部 `allow`，`check_volume.complete=true` |
| A | **30/30** | A1–A10 全 pass（`declared_caps`，10 谓词 × 3） |
| 树 | 30 文件；改动 19 条（16 新建 + 3 改写）；11 个冻结文件逐字节不变；pytest 收集 29 | B3 与 C 的冻结 3 分 |

**校准过程（不是判据放宽）**：首次 A = 24/30，A5 红在 `tools/migrate_refunds.py::_read_legacy`（圈复杂度 11），
A8 红在 `src/shop/refund_model.py`（入边 6 > 5）。处理：**改参考解**——`_read_legacy` 拆成
`_parse_legacy_line` + 循环；`tests/test_refund_service.py` 只把替身的 `record` 注解成 `Any`（不再 import 模型）→
模型入边 5。重测 A 10/10、T 仍 48/48、pytest 29 passed。**阈值一条没改，声明一条没改。**

## 3 冻结集与三臂

- **冻结集**（`.tmp/bank/exp-set.json`，37 条，组合摘要 `95e93f9f608a0a3e49f07ec805f9e6ed2219724b0a9a79953bd58f8be3de87f7`；这是**未签名**臂配置的现场值，签审批后会重冻结）：
  任务目录（**按声明 ignore 排除 `reference/**`**：参考解是读数对象，不是 run 输入）、A/B 臂配置、首消息。
  `--check --strict` PASS。
- **A/B 臂配置**：从 `examples/dsh/b-plan/dsh-adapter.yaml` 生成，`agent_version` 改 `0.2.1-rc.2`、加 `batch_ledger`（T3）；
  **唯一差异 = `pre_evidence.registry_root`** → `dgate2/configs/before`（A）vs `configs/after`（B），即 treatment 的
  `production_patterns`（tools/**/*.py）。其余字段逐字节相同。
- **三臂脚手架**：A/B 各 19 文件（14 基线 + 5 策略）、C 15 文件（14 + NOT-GOVERNED.md）；基线组合摘要三臂同为
  `b6d6d2f72575d56ce8507ad188c75e6e795c80965106be83bef09d00261d2e91`。
- **注册表自审**（Lead，单人仓库自审、不假装第三方）：两臂各 10 工具 ok，`registry_digest`
  `sha256:da2d34f5e077b8a965ca44d3b1d7717e3f44baef497a1403a1805d43e14c48b4`；`approval_allowlist_audit` 0 命中。
- **前置 dry-run**（A 臂）：freeze PASS、arm-tree PASS、dsh `0.2.1-rc.2`（app）、sandbox danger-full-access；
  blocker 恰为 `approvals_unsigned` 与 `missing_credential` —— **其余构造项已齐**。

## 4 只能由使用者做的两步

1. **签审批条子**：每臂 4 条（`exec.run_code` + `exec.pwsh` 的 tests/scripts/readonly 三族），合并进该臂
   `approval.json`；命令与 TTL 24h 见 `.tmp/bank/approval-commands.ps1`（一次性现场）。代理不得自签。
2. **启动环境的凭据**：`DEEPSEEK_API_KEY` 只从 `~/.dsh/.credentials.yaml` 的 `refs/` 取（已确认该键是字符串），
   注入 dsh 启动环境；不打印、不落盘、不写读数。

> **审批 CLI 的一个事实（2026-10-21 实测）**：一个审批文件里**每个工具只保留一条记录**，同工具重签是**取代**
> （`src/enforcement/cli.py:802-819`）。所以 `--family tests/scripts/readonly` 不能分开签成三条——后一条会把前一条覆盖。
> 正确做法：用注册表的族模式并成**一条** `command` 模式（仍是 `allowed_commands` 的子集），连同 `run_code` 共两条记录。

签完后：重跑 `freeze_manifest --write/--check`（签名改臂配置字节）→ 重建 A/B/C 臂 → dry-run（应只剩凭据项）→
真机冒烟（五条判据）。

## 5 边界（引用本读数前先看）

- **C 的 config root = 仓库根**：A/B 两臂的 C 读数用同一个 config root，treatment 只从 Hook 的 `pre_evidence` 进入；
  这与 dgate2 用 `configs/after` 当 C 的冻结 config root 是同一类选择。
- **A8 的阈值对共享模型很紧**：一个模型模块被 6 个模块 import 就 fail。本题参考解已调到 5；这不是放宽，
  是「扇入纪律」这条谓词真在起作用（它也会打到模型的解上，属可区分面）。
- **T 的树标签随调用 cwd 变**（相对标签）；正式读数从仓库根调用，标签即仓库相对路径。
- 天花板只在**参考树**上量过，不代表模型可达；k≥3 之前仍只作案例。
- 审批 TTL 24 小时；到期必须重签 + 重冻结 + 重脚手架（不静默续期）。

## 6 证据指针

- `tasks/bank-flagship-returns/scoring.yaml`（本题评分器）、`hidden/runner.py`、`reference/tree`
- `.tmp/bank/freeze.json` / `exp-set.json` / `arm-configs/{A,B}` / `run1/{A,B,C}`（一次性现场，`cleanup` 会删）
- `.tmp/bank/ceiling.json`（T/C/A 逐文件读数）与 `.tmp/bank/approval-commands.ps1`
- `readings/2026-10-21-bank-seven-adjudications.md` §1；`bank/README.md` §4/§5
