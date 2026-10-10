# B 方案：受治工作区的「命令自动执行 + 写文件仍走规则」配置

这是 2026-10-10 按使用者选定方案（**B**）实测通过的配置，用于
`C:/Users/ZNM/Downloads/Comparison-test/Governance` 这类**受治工作区**。

## 它解决什么

受治工作区里 AI 要能**自动**跑测试 / 跑项目脚本 / 只读查看（**不需要逐条人工点头**），
同时**能写文件的命令保持结构性拒绝**，改代码仍然只有「编辑文件」一条受规则约束的路。

## 它改了什么 / 没改什么

| 项 | 处置 |
| --- | --- |
| `exec.pwsh.allowed_commands` | **加**：unittest、uv-run-pytest、裸 pytest、`python scripts/*.py`、`python tools/*.py`、`python -m policy.check/retrieval.cli/enforcement.cli/adapters.dsh.hooks`、`git status/diff/log/show`、`Get-Content`、`Select-String`、`Test-Path`、`Write-Output`、`Get-ChildItem`（原有 7 条一字未改） |
| 角色表 | **加**一个最小执行身份 `governed-dev: [repo.read, repo.write, shell.exec]`——有执行权，**没有** `repo.approve` / `sandbox.escalate` |
| `approval: required` | **未动**——「高权限动作必须人工审批」这条不变量保留：这里用**一次** `binding=pattern` 放行覆盖整类调用（1000 次 / 24 小时），不是每条命令点头 |
| 结构性拒绝 | **未动**：分号、竖线、与号、反引号、`$(`、`${`、`>`、`<`、换行，以及路径穿越、`--output`、`--ext-diff`、`--no-index` |
| 仓库对外声明的姿态 | **未动**：`registry/tool-registry.yaml`、`registry/tool-registry.approved.json`、`adapters/**` 一个字节都没改；本目录是**本地副本**，由受治项目自己引用 |

## 2026-10-10 对比测试版的两处加固（`dsh-adapter.yaml`）

| 加固 | 为什么 |
| --- | --- |
| 分层判定加 `test` 层 + `test_paths` / `test_layer` | 分层按声明顺序取**第一个命中的 glob**：没有这一条时 `tests/test_x_controller.py` 会被 `**/*_controller.py` 命中、当成生产层的 controller（M1 那个缺陷） |
| 启用 `pre_evidence`（G3 动手前取证） | 不声明时**只有上下文类 checker 参与判定**，其余 42 条进 `skipped_rules`——「没查」和「查了没问题」必须分得开。启用后每次写类动作在**影子副本**（用完必删）上跑真实验证器：43 条规则全部参与判定。预算不等式 20000 + 5000 < hooks.json 的 30000；实测每次编辑约 2 秒 |

## 实测（真 Hook，2026-10-10）

| 场景 | 读数 |
| --- | --- |
| 正常改代码（三层同时改、测试仍绿） | exit 0 **放行**，`matched=43`、`skipped=0` |
| 违规改代码（入口层直接依赖数据层） | exit 2 `policy_block`，violations = `ARCH-001@1` + `TESTING-002@1`（后者是这次改动**打断了入口层已有的测试**，同一次取证一起抓到） |
| 跑测试 `python -m pytest -q` | exit 0 **放行**（不需要人点头） |
| 未声明的命令 | exit 2 `command_not_allowlisted`（清单是数据；要加就改本地注册表并**重新审核**） |
| 重定向写文件 `Get-Content a.txt > b.txt` | exit 2 `command_composition_blocked` |
| 把放行文件拿掉、再跑同一条测试命令 | exit 2 `approval_required`——证明「能跑」是**你那次放行**给的，不是没人管 |

## 三条已知限制（2026-10-10 实测，都在 open-work 里登记）

| # | 限制 | 读数 / 条目 |
| --- | --- | --- |
| 1 | **改测试文件会被拦**：改动集里只有测试文件时选不出任何测试，`failing_tests` 拿不到证据 → 失败关闭 | 第 5.58 条 |
| 2 | **跑终端命令会被拦**：一个 approval 文件只放一条记录、`approval_file` 是单值（第 5.21 条），而本机 GUI 的每个动作都经过 `run_code` 传输工具 → 名额只能给它，`exec.pwsh` 拿不到审批（`approval_invalid`） | 第 5.21 条 + 第 5.59 条 |
| 3 | **`run_code` 本身声明为不可结构化治理**：宿主执行 TypeScript，平台唯一的结构化检查是 Python 解析器；套用会把**每一次**工具调用都拦死。声明进审计（`ungoverned_declared`），子工具调用仍逐次判定 | 第 5.20 条 + 本地注册表的注释 |

命令白名单与结构性阻断本身**没有失效**——用真 Hook 单独压过：`python -m pytest -q` 放行、
`Get-Content a.txt > b.txt` 拦下。缺的是"在 GUI 会话里走到那条路"。

## 怎么用（在普通 PowerShell 里，逐条执行）

```powershell
cd C:/Users/ZNM/Downloads/Memory
$g = "C:/Users/ZNM/Downloads/Comparison-test/Governance"
$f = "C:/Users/ZNM/Downloads/Comparison-test/Free"

# 1) 两个工作区各放一份完全相同的样例项目（对比的起点）
Copy-Item -Recurse -Force examples/dsh/b-plan/sample-project/* $g/
Copy-Item -Recurse -Force examples/dsh/b-plan/sample-project/* $f/

# 2) 更新受治侧的本地配置（对比测试版：test 层 + pre_evidence）
Copy-Item -Force examples/dsh/b-plan/dsh-adapter.yaml "$g/.policy/"

# 3) 更新本地注册表与审批（2026-10-10 实测修订：run_code 改 ungoverned 声明；审批名额给它）
Copy-Item -Force examples/dsh/b-plan/tool-registry.local.yaml "$g/.policy/"
Copy-Item -Force examples/dsh/b-plan/run-code-request.json "$g/.policy/"
$env:PYTHONPATH = "src"
python -m enforcement.cli registry --registry "$g/.policy/tool-registry.local.yaml" --approved "$g/.policy/tool-registry.approved.json" --approve --reviewer dshznm
python -m enforcement.cli approve --registry "$g/.policy/tool-registry.local.yaml" --approved "$g/.policy/tool-registry.approved.json" --request "$g/.policy/run-code-request.json" --out "$g/.policy/approval.json" --granted-by dshznm --roles reviewer --binding pattern --param-pattern "code=(?s).*" --param-pattern "description=.*" --max-uses 1000 --ttl 86400

# 4) 装桥（写 $DSH_HOME，必须你自己跑；已装过且命令没变就不必重跑）
python tools/dsh_bridge.py --install --profile desktop --project "$g"

# 5) 复核：受治通道的「接线事实」应为 wired
python -m adapters.cli wiring
```

> 放行模式必须写成 `code=(?s).*`（**带 DOTALL**）：`.*` 不匹配换行，而 run_code 的 code 参数
> 天然是多行的——实测用 `code=.*` 签出来的条子对任何多行代码都是 `approval_invalid`。

**如果还没有做过审核与放行**（`$g/.policy/` 里缺 `tool-registry.approved.json` 或
`approval.json`），用上面第 3 步那两条命令即可（审核注册表 + 给 `run_code` 签一次性放行）。

放行是 **1000 次 / 24 小时**的；到期后动作会重新被拦住（不是坏了），重签一次即可。

`shell-request.json` 是 **exec.pwsh** 的请求样例，本次不用它：审批名额给了 `run_code`（见上面第 2 条限制）。
要恢复"跑命令也走审批"的姿态，得等审批协议支持按工具分文件（open-work 5.21 / 5.59）。

`Free` 那个工作区**什么都不用做**——作用域感知保证它不受影响（受治账本里不会出现它的记录，
它自己的痕迹在 `<temp>/dsh-policy/out-of-scope.jsonl`，写明「这次没管」）。

## 装完之后怎么跑对比

见 [comparison-task.md](comparison-task.md)：两个工作区各开一个会话，粘贴**同一段**任务正文。
