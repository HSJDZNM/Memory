# 2026-10-22 题库 k≥3 · 可开跑前的签核请求（使用者）

> **性质**：§5.3 的签核请求读数（Lead 准备，使用者执行）；**不是**「可开跑」签字本身。
> 起点 HEAD `99f9637` + 未提交的 §5.3 机械件；不跑 27 run、不 push。
> **判据来源**：`readings/2026-10-22-bank-k3-deliberations.md` §3；05 §8 第 11 条；`bank/README.md` §4.8。

## 0 一句话

Gate 0 已通过；最终 3 题的判据已由 Lead 冻结；3 份 per-task 冻结清单、臂配置模板/物化脚本、
最小 run-record 采集器已就绪。**现在只差使用者两件事**：① 重签 4 条审批（每臂 2 条，TTL 7 天）；
② 为 1 臂 re-smoke 注入启动环境凭据。完成后再走 scaffold / 探针 / dry-run / re-smoke，
最后由使用者签「可开跑」。

## 1 已就绪的事实

| 项 | 值 / 指针 |
| --- | --- |
| Gate 0 | **通过**：async / docs 激活、crossmodule 负对照无激活、migration 无激活（2/3）——`readings/2026-10-22-bank-k3-gate0-rerun.md` |
| Lead 签字 | 3 题 `scoring.yaml` 的 `frozen_by = Lead`（2026-10-22）——`readings/2026-10-22-bank-k3-lead-frozen-by.md` |
| 3 份 per-task 冻结清单 | async `sha256:7caf8825a3fdd3d0e520394e7b04b9d8d996b82d9dbf9a5d3d8f1f239f50e1af`（120 条）；docs `sha256:bba785a8e5ea1495ad37d3b3ab5a7753b72d6c9c0b7095614aae6b9c500cba0f`（119 条）；crossmodule `sha256:da07a934e5b027a39cc9a1f987a2bb4ddaf98151ad0c0807725576cfb1668509`（119 条）；三份 `--check --strict` PASS |
| 臂配置模板 | A `cbece9bb…` / B `a579fdb7…`（`bank/arm-configs/{A,B}`，`${REPO_ROOT}` 占位，4 文件/臂）；物化副本 A `b24040ad…` / B `b8ec3544…`（`.tmp/k3/arm-configs/{A,B}`） |
| 最小 run-record | `bank/run-record/collect.py`，`BANK_RUN_RECORD_SCHEMA_VERSION = 1.0`；参考树上 async T 38/38·C 8/8·A 10/10、docs T 40/40·C 4/4·A 10/10，两次逐字节相同 |
| 审批 | **已签（2026-10-22 20:38 +08，TTL 7 天）**：每臂 2 条；A `approval.json` `282b4925…`、B `3c697d97…`；到期 `2026-10-29T12:38Z`（+08 20:38） |

## 2 使用者要做的两件事

### 2.1 重签 4 条审批（每臂 2 条；TTL 7 天）

在仓库根执行（把 `$name` 换成签发人；旧条子用的是 `dshznm`；脚本在 `.tmp/k3/sign-approvals.ps1`）：

```powershell
$name = "dshznm"   # 改成你的签发人名字
$env:PYTHONPATH = "src"
$py = ".venv\Scripts\python.exe"
$union = 'command=(?:(?:^python -m pytest( .*)?$)|(?:^uv run python -m pytest( .*)?$)|(?:^pytest( .*)?$)|(?:^python -m unittest( .*)?$)|(?:^python tools/[A-Za-z0-9_./-]+\.py( .*)?$)|(?:^python scripts/[A-Za-z0-9_./-]+[.]py( .*)?$)|(?:^python -m (policy\.check|retrieval\.cli|enforcement\.cli|adapters\.dsh\.hooks)( .*)?$)|(?:^git (status|diff|log|show|ls-files|rev-parse)( .*)?$)|(?:^Get-Content( .*)?$)|(?:^Select-String( .*)?$)|(?:^Test-Path( .*)?$)|(?:^Write-Output( .*)?$)|(?:^Get-ChildItem( .*)?$))'
foreach ($arm in @("A","B")) {
  $cfg = ".tmp/k3/arm-configs/$arm"
  $req = ".tmp/k3/approval-requests/$arm"
  & $py -m enforcement.cli approve --registry "$cfg/tool-registry.local.yaml" --approved "$cfg/tool-registry.approved.json" --request "$req/run-code-request.json" --out "$cfg/approval.json" --granted-by $name --roles reviewer --binding pattern --param-pattern 'code=(?s).*' --param-pattern 'description=.*' --max-uses 1000 --ttl 604800 --approval-id approval-run-code
  & $py -m enforcement.cli approve --registry "$cfg/tool-registry.local.yaml" --approved "$cfg/tool-registry.approved.json" --request "$req/shell-request-tests.json" --out "$cfg/approval.json" --granted-by $name --roles reviewer --binding pattern --param-pattern $union --param-pattern 'description=.*' --max-uses 1000 --ttl 604800 --approval-id approval-pwsh-all
  Write-Output "$arm last_exit=$LASTEXITCODE"
}
```

- **每臂 2 条**：`approval-run-code` + `approval-pwsh-all`（三族并成一条 union）；同一工具只保留一条记录，
  重签是取代（不要分三次签 tests/scripts/readonly）。
- **TTL**：`--ttl 604800`（7 天）；从重签时刻起覆盖 k≥3 窗口 + 1 天。批内重签会改
  `approval.sha256` → 换 `platform_generation`，前后 run 不可合并。
- 签完把两臂 `approval.json` 的 sha256 写进下面「回执」；Lead 会把它记入可开跑读数。
- **不要**在签字后重新物化臂配置（物化会覆盖四文件；签在物化副本上）。

### 2.2 为 1 臂 re-smoke 注入凭据

- `DEEPSEEK_API_KEY` 只从 `~/.dsh/.credentials.yaml` 的 `refs/` 取，**只注入启动环境**；
  不打印、不落盘、不写读数（`bank/harness/README.md` 与 04 5.90 的既有纪律）。
- 由使用者在本机启动环境里提供；Lead 不读取该文件。re-smoke 用 1 个臂（A 臂优先）验证
  run_session 1.1 的自动化路径（隔离 DSH_HOME / profile 沙箱覆盖 / TEMP 重定向），不计入 k。

## 3 预检状态（2026-10-22 20:5x，Lead）

- **9 树 scaffold exit 0**（3 题 × A/B/C；A/B 的 `.policy/approval.json` records=2、placeholders=0；C 无审批）。
- **3 份 freeze `--check --strict` PASS**（摘要见 §1）。
- `run_session` dry-run（async A）：freeze / arm-tree / dsh 0.2.1-rc.2 / sandbox `danger-full-access` 全绿；
  **唯一 blocker = `missing_credential`**（`DEEPSEEK_API_KEY` 不在 harness 进程环境）。

## 4 签完之后 Lead 会做（不需要使用者再操作）

1. `freeze_manifest --check --strict` ×3（确认签字没有改动被冻结的输入；审批不在冻结集里，按 run 记录）；
2. `scaffold_arms.py` 建 9 棵树（3 题 × 3 臂，每 run 一个父目录）；
3. P1–P6 探针 + dry-run（预期只剩「re-smoke 凭据」一项）；
4. **1 臂 re-smoke**（真机，不计入 k；核对 launch 块、审计条数、exit.code）；
5. 建「可开跑」读数：3 份 freeze 摘要 + 审批 sha + TTL + Gate 0 + H1 决定 + H2 计划；
   由**使用者**签「可开跑」，再由 Lead 跑 27 run。

## 5 回执（使用者填）

| 项 | 值 |
| --- | --- |
| A 臂 `approval.json` sha256 | `282b4925908ca1f378056cb28d647eea71d85e9c371a4c547876ccbbc8c45782` |
| B 臂 `approval.json` sha256 | `3c697d97c58476f2e3db6d557d1e4dd57e02f0e37c92ac4c0fa05839b91d47ab` |
| 签发时间 / TTL 到期 | 2026-10-22T12:38Z / 2026-10-29T12:38Z（+08 20:38） |
| 凭据已注入启动环境 | **否**（2026-10-22 20:5x 复核：`DEEPSEEK_API_KEY` 不在 harness 进程环境） |

## 6 边界

- 本读数**不是**「可开跑」签字；27 run 未跑、H1 复核未做、P1–P6/dry-run/re-smoke 未做。
- 若批内重签或 TTL 不覆盖窗口：该批 run 作废，不得与旧 run 合并。
- 任何「跑不成」记原因与复现指针，不记 pass。
