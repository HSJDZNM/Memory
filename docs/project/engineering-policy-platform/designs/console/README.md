# 操作台静态原型（提案，尚未实现）

[可行性评估](../文档转规则操作平台-可行性评估.md) 的可点开版本：6 个静态页面，零构建、零依赖、零后端改动。
界面只保留标签与状态，说明性内容一律放进 **? 悬停提示**。

## 打开

```powershell
python -m http.server 8099 --directory docs/project/engineering-policy-platform/designs/console
# http://127.0.0.1:8099/index.html
```

也可以直接打开 [index.html](index.html)（本地文件）。

## 页面（按层合并）

| 页面 | 覆盖台阶 | 内容 |
| --- | --- | --- |
| [index.html](index.html) | 总览 | 阶段状态、KPI、修复状态、入口 |
| [data.html](data.html) | ① 镜像 ② 语料 ③ 索引与分块 | 三个标签页：镜像表 / 语料表 + 登记 / **chunk 列表 + 勾选** |
| [authoring.html](authoring.html) | ④ 提炼 ⑤ 规则文件 | 候选池（可勾选、可过滤）→ 起草面板 → 预演 → YAML 预览 → 候选规则表 |
| [gates.html](gates.html) | ⑥ 验证器覆盖 | 候选预演 / checker 覆盖 / 原子加载演示 / CLI |
| [activation.html](activation.html) | ⑦ 审批 · 生效 · 溯源 | 提交流程线框、生效状态、溯源登记、失败语义 |
| [system.html](system.html) | 系统 | 连接自检（真发请求）、路由表、实测结论、缺口 G1–G8、红线 R1–R12、反模式 |

## 主流程（可点）

1. **data.html** → ③ 索引与分块 → 勾选若干 chunk → 「加入候选池 →」
2. **authoring.html** → 候选池里点一行 → 选 checker / 填字段 / 填 message → 「预演门禁」→「加入候选」
3. **gates.html** → 候选预演（逐条）→ 勾选已有规则看原子加载语义
4. **activation.html** → 提交面（action_hash 由平台计算）→ 生效状态 → 溯源登记

## 交互约定

- **?**：鼠标悬停显示注解；所有解释都在这里，正文不再写说明段。
- 灰按钮：该操作今天**没有对应路由**（悬停可看缺口与替代命令）。
- 本地状态：勾选与候选存在 `localStorage`（键 `console.state`）；换浏览器/隐私模式下会重置。
- 预演只做字段形状与枚举合法性演示，**不产出 Decision**；真实结论必须调用 Policy API。

## 数据来源（真实读取）

| 数据 | 来源 |
| --- | --- |
| 规则集 / rule_set_hash | `policy.loader.load_rule_set([policies/])` |
| 数据集 | `knowledge/corpus.yaml` |
| 镜像清单 | `docs/*/manifest.json` |
| 验证器覆盖 | `validation/validators.yaml` + `policy.checkers.SUPPORTED_CHECKERS` |
| chunk 列表 | `.tmp/retrieval/index.sqlite3`（构建产物；缺索引时页面会标注） |
| 路由 | `policy_api.runtime.ROUTES` + 实测路径 |

## 重建

```powershell
$env:PYTHONPATH = "src"
python docs/project/engineering-policy-platform/designs/console/build_site.py
```

生成 6 个 HTML + `assets/data.js`；`assets/style.css`、`assets/app.js` 手写，不生成。
不要手改生成的 HTML：改生成器或数据后重跑。

## 边界

- 无写路径：提交必须走 Phase 4 受控执行链（新建 `orc.policy.write`、编辑 `orc.policy.edit`，均绑定 `action_hash` 并要求人工审批）。
- B1/B2/B3 已修复并有回归测试；静态原型仍未新增提交路由，不能把浏览器演示当成真实治理动作。
