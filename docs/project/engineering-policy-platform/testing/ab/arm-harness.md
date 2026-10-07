# AB-5 臂运行时与净化树（tools/ab_arm.py）

> 目的：让「控制臂真的读不到规则」从一句声明变成**一条命令就能证明**的事，并且证明**仪器自己会红**。
>
> 写域：本文件与 tools/ab_arm.py。协议与任务集由 ab-protocol 定义（见 ab-protocol.md），
> 六个量的测量由 ab-instruments 定义（tools/ab_measure.py）。

## 0 一句话结论

三臂能跑、对照是真的：**同一条编辑**在 off 臂被应用、在 advisory 臂被判 block 但**照样被应用**、
在 enforced 臂被判 block 且**没有落到树上**；而**独立的可用性 oracle**（项目自带测试）在 off/advisory 红、在 enforced 绿。
净化断言能红也能绿，并且**暴露了一条真实极限**：净化是路径删除，不是可达性控制。

## 1 复现命令（照抄即可）

    python tools/ab_arm.py --list-sanitization
    python tools/ab_arm.py --self-proof --baseline-fixture shop
    python tools/ab_arm.py --run --baseline-fixture shop --preset blocked --arm all
    python tools/ab_arm.py --run --baseline-fixture shop --preset allowed --arm all
    python tools/ab_arm.py --assert-clean --run-dir .tmp/ab-arms/<run-id> --arm off
    python tools/ab_arm.py --assert-clean --run-dir .tmp/ab-arms/<run-id> --arm off --probe-platform-path

退出码：0 = 全部成功；1 = 有失败（断言红 / 该拦的没拦 / 该过的没过 / 想要的读数取不到）；2 = 用法或配置错误。

## 2 目标树锚在平台之外（这条是裁定，不是偏好）

ab-protocol 在 git archive HEAD 的副本上实测：按需求原文删掉那 6 条路径之后，
pytest 从 2136 collected / 0 errors 变成 1832 collected / 12 errors——12 个测试模块因为
validation/validators.yaml 消失而在**收集期**失败；同一棵树上仍**有大量**文本文件含规则 ID 形态。
本工具自己也复现了同一件事：在本仓副本上做净化，内容扫描命中 1089 处，且「保留 tests/ 才能跑 oracle」
与「删 tests/ 才干净」直接冲突。

结论（lead 2026-10-07 裁定）：**任务树不与平台检出相交**，治理通过工作树之外的适配器配置施加。
本工具因此把「固定夹具项目」做成默认基线：

    --baseline-fixture shop      # 生成 .tmp/ab-arms/baseline-shop（最小三层项目 + 一个自带测试）
    --baseline <dir>             # 也可以用任意外部 checkout

在本仓副本（自举路线）上仍然能跑，但读数里 route = bootstrap_repo_copy，
且 vcs_dir_absent 那条断言按「自举路线的证伪断言」判——**不要用它当通用净化结论**。

**边界（lead 2026-10-08 裁定，写成结论而不是缺口）**：`--baseline` 的输入是**外部任务树**，
「拿平台仓库自己当基线」**不是一个受支持的用法**。clean 判据问的是「这棵臂树里能不能读到
平台自己的规则集与产物」，而平台仓库必然在自己的**追溯语料**里引用规则 ID
（`docs/project/rule-effects/**` 逐条点评规则、`docs/project/reviews/**` 是审查报告）。
因此 `--self-proof --baseline .` 的 clean 段报红**说明的是你在问一个不该问的问题**，
既不是扫描器误报，也不是净化清单漏了东西（清单**不为此改动**：改清单等于改 treatment 定义）。
修复后实测：模式收窄到本平台规则 ID 之后，平台副本路线仍命中 920 行 / 113 文件，
绝大多数来自上面两条路径；文档命令 `--self-proof --baseline-fixture shop` 一直是 pass。

## 3 净化清单（14 条，每条带理由）

    policies/**                              规则本体（43 条规则 YAML，含码与严重级别）
    AGENTS.md                                含大量规则 ID、判定口径与核心约束
    validation/**                            ruff.toml 的 select 表 + 码归属注释 + validators.yaml
    knowledge/**                             corpus.yaml 里的 rule_sources 登记
    docs/project/engineering-policy-platform/**  方案与门槛：含 GV 口径、规则清单、预注册预测
    docs/project/architecture/**             自查新增：转化覆盖报告逐条点评 43 条规则
    docs/mirrors/**                          自查新增：规则的上游原文（读得到就能反推规则）
    tests/fixtures/rules/**                  自查新增：正反例夹具（文件名即规则 ID）
    tests/fixtures/decisions/**              自查新增：决策快照带 rule_id / message / severity
    evaluation/**                            自查新增：门槛、语料锁与读数带规则清单与码
    registry/**                              自查新增：受控工具表——泄露「哪些动作被治理」= treatment 边界
    examples/dsh/**                          自查新增：钩子接线与 adapter 配置
    .dsh/**                                  钩子配置目录（存在就删）
    .policy/**                               钩子配置 / 审计 / 台账（臂运行时自己生成自己的，放在臂树之外）

红队 r3 的攻击点成立：docs/project/rule-effects/** 与 docs/project/reviews/** **不在**上面这张表里，
而它们确实含规则 ID。我**没有把它们加进清单**，理由是：在「树锚在平台之外」的新路线上，
这两条路径本来就不存在于任务树里，加进去只是在自举路线上补窟窿；而自举路线已被裁定降级为证伪对照。
**这是未解决的分歧**（见第 9.3 节），如果后续还要跑自举路线，这两条必须补。

## 4 --assert-clean：两条断言 + 一条行为探针

断言只有两条（lead 裁定），外加一条行为证据：

1. **任务树里不存在平台产物**（那 6 条路径是「平台产物」这个概念的可操作化）；
2. **平台检出不在任务树内**（rules_root 与向上回溯能找到的根都不在树里）；
3. **运行时探针**：从任务树里跑一次判定，看它够不够得着平台。

第 3 条的由来：r3 实测——**在本仓副本上删掉 policies/ 也照样加载 43 条规则**，
因为 policy.check 的 repo_root() 会从被检查文件向上回溯。所以路径删除证明不了可达性。

控制臂（期望绿）：

    净化断言 | clean=True | .tmp/ab-arms/20261007T122424Z-34df39
      off       clean=True  扫描=6 文件 命中=0 rules_root 在树内=False

正向对照：**故意**把平台挂上 PYTHONPATH，断言必须红——它红在「够得着平台」这条上：

    净化断言 | clean=False | .tmp/ab-arms/20261007T122424Z-34df39
      off       clean=False 扫描=6 文件 命中=0 rules_root 在树内=False
          ! 运行时探针够得着平台：加载到了 43 条规则（sha256:50202675b6ca40136）

对真实臂树的变异（往任务树里放一个平台产物）：

    净化断言 | clean=True  ... off 扫描=6 文件 命中=0      （CLEAN_GREEN=0）
    [plant .tmp/.../off/tree/policies/ARCH-001.yaml]
    净化断言 | clean=False ... off 扫描=7 文件 命中=1
          ! 净化不彻底：policies/** 还能找到 2 个路径
          ! 内容扫描命中 1 处规则身份形态                  （CLEAN_RED=1）
    [remove]
    净化断言 | clean=True  ... off 扫描=6 文件 命中=0      （CLEAN_GREEN_AGAIN=0）

## 5 三臂语义与实测对照

    off       不跑治理：改动一律应用。没有 entry，因此也没有判定记录。
    advisory  判定来自**真实入口**（同一条 dsh Hook 命令、同一份 adapter 配置），
              但臂不执行阻断动作：记录判定与诊断，改动**仍然应用**。
    enforced  判定来自真实入口；decision=block 时**不应用**改动，被拒时树逐字节不变。

真实入口的降级阶梯（绝不自造判定路径）：dsh 插件端到端 → 那条 Hook 命令本身
（python -m adapters.dsh.hooks --config ... --hooks-config ... --audit ...，喂真实 PreToolUse 载荷）→ 没有第三条。

判据：blocked 编辑在 enforced 下必须**两条同时成立**——audit.jsonl 里有 block，且文件哈希不变；
缺一条就记 unavailable（「跑不了」绝不被读成「拦住了」）。

blocked preset（同一条编辑：把 controller 的 import 换成 repository）：

    臂运行时 | run=20261007T122424Z-34df39
      off       entry=none          decision=not_governed action=applied     file_changed=True  wall_ms=None
      advisory  entry=dsh-hook-cli  decision=block       action=applied     file_changed=True  wall_ms=748
      enforced  entry=dsh-hook-cli  decision=block       action=refused     file_changed=False wall_ms=776

allowed preset（合规编辑：加一个方法）：

    臂运行时 | run=20261007T121234Z-fcb0ab
      off       entry=none          decision=not_governed action=applied     file_changed=True
      advisory  entry=dsh-hook-cli  decision=allow       action=applied     file_changed=True
      enforced  entry=dsh-hook-cli  decision=allow       action=applied     file_changed=True

## 6 可用性 oracle（外部判据，不是平台自评）

arm 的动作执行完之后，用**项目自带测试**当 oracle：声明的 node id 必须在 junit 报告里出现且 passed；
声明了却没被收集到 = missing，**不算通过**；pytest 跑不起来 = unavailable，绝不写「通过」。
oracle 用独立的空配置 + --rootdir 隔离宿主 pytest.ini（实测：不隔离会顺着 cwd 找到平台的 pytest.ini，
报 ImportError + Unknown config option: cache_dir，把 oracle 本身打坏）。

同一棵树、同一条编辑，三臂的 oracle 结果：

    off        {"tests/test_shop.py::test_controller_create": "failed"}   ran collected=1 exit=1
    advisory   {"tests/test_shop.py::test_controller_create": "failed"}   ran collected=1 exit=1
    enforced   {"tests/test_shop.py::test_controller_create": "passed"}   ran collected=1 exit=0

这就是本次仪器能提供的**独立于平台 Decision 的**结局读数：off 与 advisory 把项目改坏了，
enforced 因为拒了那次编辑而保住了 pass_to_pass。

## 7 一次 run 的产物（已与 ab-instruments 冻结）

每个 (臂, 任务) 一个目录，默认在 .tmp/ab-arms/<run-id>/<arm>/ 下：

    run.json                 本次运行完整读数（含 leak_assertions / isolation_level / oracle / unavailable）
    verdict.json             真实入口的判定（off 臂 available=false）
    audit.jsonl              真实入口写的审计（off 臂为空 + 在 run.json 里写明「没有 entry」）
    changes.json             declared_changed_files / changed_files / 前后哈希
    measurement_input.json   **给 ab_measure.py 的输入清单**（冻结格式，schema_version=1.0）
    oracle.json              可用性 oracle 的原始结果
    tree/                    该臂的工作树（enforced 被拒时与执行前逐字节相同）
    tree-before/             本次写动作触碰的文件（全树副本没必要）
    arm.json                 臂元数据（sanitization / rules_root / seeded_fixture）

measurement_input.json 的顶层键：schema_version、task_id、arm、run_dir、baseline_tree、arm_tree、
arm_tree_digest、tree_before、tree_after、declared_changed_files、changed_files、proposed_edits、
governance、timing、counts、oracle、unavailable。

ab-instruments 要的三组键都已加上：proposed_edits（被拒的编辑在 tree_after 里根本不存在，所以必须
由调用点导出提议内容——内容是本工具构造的工具调用，不是平台载荷，AUDIT_SCHEMA_VERSION 不动）、
declared_changed_files / changed_files 两个口径、oracle 声明块；
entry.side_effect_free 如实写 **false**（入口按设计写审计与台账），并给出 repeat_semantics：
重复测延迟必须每次一棵新臂树，否则第二次起会命中幂等台账变成 event_replay。

## 8 L1–L5 环境断言与 isolation_level

run.json 里每条 run 都带 leak_assertions（L1 路径不存在 / L2 无 .git / L3 内容扫描 0 命中 /
L4 运行时 [policy] 标记 / L5 宿主 .dsh 接线），以及 isolation_level。

**isolation_level = tree_only**：本工具只做树级隔离，不建文件系统命名空间，也不清理宿主 .dsh 里
既有的接线——不许默认成 fs_isolated。

实测（blocked run，20261007T122424Z，--arm off）：L1/L2/L3/L4 全部 pass（L4 是装置自检：
off 臂 marker_seen=false、treatment 臂 marker_seen=true），**L5 fail**。

**L5 的数字必须连口径一起读**（单位、针脚原文、后缀过滤器；这三样现在都进载荷）：

    针脚（默认 DSH_WIRING_NEEDLES）= 臂树绝对路径 + policy-hook.plugin.mjs
                                     + adapters.dsh.hooks + policy.check + policy_hook
    后缀过滤                       = .yml .yaml .json .js .mjs .ts
    结果                           = 67 个文件 / 181 次出现（files_with_hits / match_count）

换红队的针脚集（policy-hook / policy_hook / policy.check）同机实测 = 64 个文件 / 222 次出现；
红队自己量到 4 个文件（只扫 json/yaml）。**三个数互相不可印证，结论一致**：这台机器的用户级
dsh 配置本来就接着本平台的插件，所以「控制臂在宿主层面没有平台接线」**在本机不成立**。
按 ab-protocol 的约定，读数里 tree_isolation 与 host_wiring_isolation **分开写**：
本机 tree_isolation=true（夹具基线）、**host_wiring_isolation=false**。

⇒ 一句话结论（写死，别绕）：**本机在此配置下跑不出干净的控制臂**；要开跑必须换每次 run 独立的
dsh home，或换一台干净的实验机。**未解决，见第 10 节。**

## 9 交流记录

### 9.1 ab-instruments（测量仪器，task-12）

- 我提出：一次 run 的产物布局、run.json / measurement_input.json 的键集合、三臂语义，
  并请它确认 (a) 键够不够、(b) changed_files 口径、(c) 反事实要哪棵树。
- 它回复：**接受布局**；(b) 两个键都要；(c) 指出一个会让反事实白干的问题——
  enforced 臂 refused 时 tree_after == tree_before，被拦下的编辑在树里根本不存在，
  所以必须由我导出 proposed_edits。另要求 oracle 声明块、entry.side_effect_free、bypass_definition。
- 我的回应：**全部接受**，proposed_edits / declared_changed_files / oracle 声明块 /
  bypass_definition 都已实现；entry.side_effect_free 如实写 false（入口写审计与台账），
  并补 repeat_semantics。**未解决的分歧：无。**
- 它另外要求：counts 那一块只能当 **manipulation_check**、不能当结局变量——
  我同意，并在 measurement_input.json 的 counts.role 里写死这一点。

### 9.2 ab-protocol（协议，task-11）

- 它给出两条硬事实（净化打坏 oracle、176 个文件仍含规则 ID）并裁定：**树锚在本仓之外**，
  6 条路径降级为环境断言；给出 P1–P7 净化契约与 L1–L5 断言；问我三件事。
- 我的回应：
  (a) isolation_level = **tree_only**（进 run.json，不进默认更强的那一档）；
  (b) L4 行为探针由我做：跑真实 Hook 命令并在捕获的 stdout/stderr 里找 [policy] 标记，
      控制臂断言 false、treatment 臂断言 true（实测通过，见第 8 节）；
  (c) treatment 臂的 hooks.json 里 **matcher 留空**（匹配全部工具），
      写法见 write_hook_configs()，与 examples/dsh/hooks.json 同型。
- **未解决的分歧**：P4（PYTHONPATH 不含平台 src/）我只在 **oracle 与探针**上做到了
  （探针显式清掉 PYTHONPATH），但 **treatment 臂的 Hook 本身必须能 import 平台**
  （它就跑在平台检出上），所以「环境变量里没有平台配置路径」这条在 treatment 臂上**做不到**。
  我的口径：树级隔离成立，进程级隔离不成立，读数是 tree_only。

### 9.3 ab-redteam（= r3-applicability，task-13）

- 我请它攻击：正则漏报、间接泄露、净化不全、advisory 是否假 treatment、降级会不会把「跑不了」读成「拦住了」。
- 它回复 6 条（S1/S2），我逐条回应：
  1. **净化清单漏 docs/project/rule-effects/** 与 docs/project/reviews/**；正则断言在保留集上会变红** ——
     **接受一半**：这两条路径确实漏了；但在「树锚在平台之外」的新路线上它们本来就不在任务树里，
     所以我**暂不加入**，把它记为未解决分歧（第 3 节已写明）。正则的作用域我写死在 payload 里
     （leak_scan.patterns + limits），并给出「豁免 tests/ 之后还剩多少命中」的读数：
     夹具基线 6 个文件 0 命中；自举路线（本仓副本）**1089 命中**——这正是裁定要弃用自举路线的理由。
  2. **删掉 policies/ 也照样加载 43 条规则（repo_root 向上回溯）** —— **接受，已实现为断言**：
     runtime_probe + 正向对照（--probe-platform-path 必红），见第 4 节。
  3. **.git 是自举路线上的泄漏面** —— **接受**：vcs_dir_absent 作为「自举路线证伪断言」保留，
     新路线下记 not_applicable（复制时忽略 .git）。
  4. **advisory 的反馈必须真的到达 Agent** —— **部分接受**：本工具只保证「判定来自真实入口、
     臂不执行阻断」，它**不**负责把反馈送进 Agent 上下文（那是 dsh 侧插件与 A/B 任务集的事）。
     我在 run.json 里给出 decision 与 audit 引用作为可核对 marker；把「反馈到达」的断言留给 AB-1/AB-3。
     **这是未解决的分歧**：我认为反馈送达不属于臂运行时的职责，r3 认为不送达就不是反馈臂。
  5. **降级不许把「跑不了」读成「拦住了」** —— **接受**：判据已加强为「audit 有 block **且** 文件哈希不变」，
     并额外记录 exit_code 非 0/2 的情况为 unavailable。它要求的「block_class 分列
     policy_violation vs infrastructure_failure」**尚未实现**（记进第 10 节缺口）。
  6. **两臂反馈文本逐字相同要在都产生的前提下比** —— **接受**：run.json 里 L4 同时报
     marker_seen 与 expected，off 臂是 false（不产生）而不是「空 == 空」。

## 10 未验证 / 已知缺口（照实写）

1. **dsh 端到端（--dsh）未实测**：本机 dsh 0.1.6-alpha.2 存在，但受限沙箱下 Hook 可能起不来
   （spawn EPERM）。本次全部证据走的是同一条 Hook 命令（真实入口的第二档），
   **「dsh 会不会把插件的 deny 传到工具管线」这一段没有被覆盖**。
2. **L5 红着的**：宿主 .dsh 接线里 67 个文件 / 181 次出现（口径见第 8 节；换红队针脚集是 64 文件 / 222 次）。
   判据（红队 B8）：L5 命中 = 0 **且** 运行时探针看不到 [policy] 标记，两条都绿才允许开跑 ⇒ **本机不允许开跑**。
   本工具**不会**把这种情况写成"控制臂干净"。
3. **block_class 未分列**（r3 第 5 条）：infrastructure_failure 与 policy_violation 目前只在
   exit_code 与 audit 里可分辨，没有独立键。
4. **content 扫描是兜底不是证明**：中文意译、改名后的 YAML、编码过的规则它抓不到（payload 里写死了 limits）。
5. **自举路线（本仓副本）的读数不可用**：内容扫描 920 命中 / 113 文件（收窄到本平台规则 ID 之后；
   旧形态串口径是 1162 命中 / 150 文件，其中含 UTF-8 / AB-5 这类误报）、oracle 会被打坏；
   route=bootstrap_repo_copy 时不要把 clean 当结论。这条路线**不是受支持的用法**（见第 2 节的边界），
   拿平台仓库当基线时 clean 段报红是预期结果。
6. **P4/P6/P7 只做到一部分**：进程级隔离、每 (task, replicate) 全新会话、模型 revision_id 记录
   属于协议/编排层，本工具只保证每臂一棵新树。
7. **未跑**：tools/ci_local.py、任何 *_loop.py（按任务约束不跑）。

## 11 仪器自证（AGENTS 第 45 条）

    python tools/ab_arm.py --self-proof --baseline-fixture shop

    变异自证 | pass | 仪器会红=True
      clean              期望 clean=True  实测 clean=True  符合=True
      planted_path       期望 clean=False 实测 clean=False 符合=True
      planted_content    期望 clean=False 实测 clean=False 符合=True
      reverted           期望 clean=True  实测 clean=True  符合=True

两个变异体各打一层防线：往臂树里放回 policies/ARCH-001.yaml（只有路径删除能挡）、
放一个正文含规则身份串的 notes.md（只有内容扫描能挡）。产物在 .tmp/ab-arms/selfproof-*/self-proof.json。

## 12 冻结记录（本轮冻结版）

    tools/ab_arm.py      sha256:716a59c9c864af41253f0dfbc7f992c71ebde00e8e99d138805b74cd56cfe279
                         77433 字节

**本文件不能自指**（把自身哈希写进自身会让哈希立刻失效）：arm-harness.md 本轮冻结版的 sha256
连同上面的工具哈希一起报给 lead 留档。纪律（ab-protocol 反面清单第 11 条）：**改这两个文件里任何一个
字节，都要重新计算并重记哈希**——5 分钟内四个版本会让"更正"自己过期，读数也一样。
