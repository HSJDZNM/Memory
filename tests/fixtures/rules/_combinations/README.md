# 规则**组合**语料：条目的形状与读数

这里回答的问题与上一层的正反例语料**不是同一个**：

| 语料 | 它回答的问题 | 它答不了的问题 |
| --- | --- | --- |
| `tests/fixtures/rules/<RULE-ID>/{good,bad}.py` | 这条规则**单独**判不判得出来？ | 多条规则叠加在**同一次变更**上时会怎样？ |
| `tests/fixtures/rules/_combinations/`（本目录） | 这一次变更（目标 + 操作 + 变更集 + 层 + 语言）判成什么？产出了哪些证据？ | 单条规则的正反例（那由上一层覆盖） |

为什么必须有这一层：正反例语料的上下文是固定的（`layer="fixture"`、**不声明 `operation`**），
带 `operation` 维度的规则（`TESTING-001@1` / `TESTING-002@1`）在那一层**恒进 `skipped_rules`**
——那道门禁从没执行过它们，「谁来验组合」因此没有答案（见
[04-open-work.md](../../../../docs/project/engineering-policy-platform/04-open-work.md) 的 5.68）。
`test_combination_corpus_exercises_every_operation_scoped_rule` 现在把这件事**变成会失败的检查**：
只要有一条声明了 `operation` 的规则在全部条目里一次都没参与判定，门禁就红。

## 谁在跑它

唯一消费者是 `tests/integration/test_rule_combinations.py`。链路与 CLI / Hook 完全相同：

1. 把条目声明的项目树**复制**到临时目录（`.tmp/tests/<随机>`），判定读的就是这次那棵树；
2. `validators.pipeline.run_pipeline`：按命中的规则选验证器，真调 Ruff、真跑 pytest（不 mock）；
3. `policy.engine.evaluate`：唯一判定入口，证据包进去，决策出来。

本机没有可用的 Ruff 时用例 `pytest.skip`（写明原因），绝不伪装成通过。

## 条目契约

一个条目 = `cases/<条目 id>.yaml`（**文件名就是条目 id**，不再另写 `name`——两处写同一个东西
迟早会对不上）。键是**闭集**：多一个键就报错，不静默忽略。

| 键 | 必填 | 含义 |
| --- | --- | --- |
| `project` | 是 | 这次判定读的项目树（仓库相对路径，必须存在）。当前是 `project/` |
| `target` | 是 | 本次动作要写的那个文件（仓库相对路径，**必须在 `project` 树里真的存在**） |
| `operation` | 是 | `create` / `edit`（`policy.models.Operation` 的取值，本语料不猜默认值） |
| `changed` | 是 | 变更集（非空列表，仓库相对路径；可以包含还没落盘的「本次要新建的文件」） |
| `layer` | 是 | 部署侧声明的层名（当前条目用 `test`，与 `examples/dsh/b-plan/dsh-adapter.yaml` 的 `test_layer` 同口径） |
| `language` | 是 | 语言（当前条目用 `python`；不声明语言 = 没有证据，规则会进 `skipped_rules`） |
| `expected_decision` | 是 | `allow` / `allow_with_warnings` / `block` |
| `expected_served_checkers` | 是 | 本次**真的服务过**的 checker（按字母序；没有证据写 `[]`）。**逐字相等**，不是子集 |
| `note` | 否 | 一句话给人看的说明，不参与断言 |

### 条目是棘轮，不是「期望行为」的许愿池

条目的读数**照实记录**（真跑一遍、把看到的写下来）。其中允许记录**已知是坏的**行为：
`conftest-alone` 就是一条——它记的是 5.66 的死锁（改测试支撑文件被拦死），文件头写着为什么、
什么时候该翻面。等 5.68 的方案 C / A 落地，那条条目要**显式改成** `allow` 并重采
`expected_served_checkers`；那是一次可评审的修改，不是「为了让门禁变绿」而放宽断言。

`expected_served_checkers` 用**逐字相等**也是这个意思：证据集合变了（哪怕只是多了一条 checker）
就是一次需要人看一眼的变化。失败信息会把 `selection`、全部 `violations` 与 `skipped_rules`
一起打出来。

### `changed[]` 是**声明**出来的形状

真实 Hook 每次只报一个文件（`pre_evidence` 里 `changed_files=(event.file,)`），而 `changed[]`
这个键存在，是为了表达「批次 / 意图粒度」——那正是 5.68 里「方案 A」要做的事（决定性读数 R5：
同一个动作、同一棵树，只换批次，`block` 变 `allow`）。`conftest-with-implementation` 条目记的就是
R5，它**不表示今天 Hook 能跑出这个形状**。

## 怎么加一条

1. 想清楚「这一次变更」的形状：目标、操作、变更集、层、语言——**能不能用现有 `project/` 表达**；
   不能就先扩 `project/`（它是一棵被复制的小项目树，不是规则夹具）；
2. 跑一遍真链路（临时脚本或直接加条目再跑用例），**照实**抄下 `decision` 与 `served_checkers`；
3. 写 `cases/<条目 id>.yaml`：形状 + 读数 + 一句 `note`（若记录的是已知坏行为，写清翻面条件）；
4. 跑 `python -m pytest tests/integration/test_rule_combinations.py -q`，绿了再提交。

新增一条**会命中某个组合**的规则时，本门禁会红：照实重采并写明为什么变化，不要放宽断言。
新增一条**声明了 `operation`** 的规则而没有任何条目命中它，也会红——那就补一条条目。

## 本地复跑

```powershell
# 全部条目
python -m pytest tests/integration/test_rule_combinations.py -q

# 只看某一条
python -m pytest "tests/integration/test_rule_combinations.py::test_combination_matches_its_declared_reading[conftest-alone]" -q

# 用 CLI 看同一份判定的证据（--json 里有 blockers、evidence 与决策）
$env:PYTHONPATH = "src"
python -m policy.check tests/conftest.py --workspace tests/fixtures/rules/_combinations/project --operation edit --changed tests/conftest.py --json
```

## 不覆盖什么（别读成「组合全查过了」）

- 只跑**验证器路径**：没有 Hook、没有 Phase 4 受控执行、没有审批、没有事后核对；
- `changed[]` 是条目声明的，不是 Hook 的真实形状（见上）；
- 只钉**决策**与 **served_checkers** 两件事；「哪条规则报了违规」只在失败信息里打印，不参与断言；
- 条目引用的是 `project/` 这棵**固定的小树**：真实仓库里的其他文件（同一批的其他改动、
  工作区里的历史状态）不在读数范围内。
