# D 门 2 受跟踪配置快照（treatment = production_patterns 增 tools/**/*.py）

本目录是 D 门 2 的 **A/B 两臂输入**：同一套平台代码、同一棵受评树，只差一份
`validation/` 配置——即 2026-10-19 D 门 2 裁定（见
`readings/2026-10-19-D-gate2-treatment.md` §8 第 1 条）的 treatment。

## 来源

| 目录 | 是什么 | 字节来源 |
| --- | --- | --- |
| `before/validation/` | treatment **之前**的 9 份受跟踪配置 | `git show HEAD:validation/<f>`（HEAD = `0208bee`）；逐文件 sha256 见下，9/9 与 HEAD 相等 |
| `after/validation/` | treatment **之后**的同一组文件 | 本次改动后的工作树 `validation/`（只改 `test-layout.yaml` 一个文件） |

## 用途

| 消费者 | 用哪一份 | 参数 |
| --- | --- | --- |
| A 臂（对照组） | `before/` | dsh-adapter 的 `pre_evidence.registry_root` = 本目录（**含 `validation/` 的那一层**） |
| B 臂（treatment 组） | `after/` | 同上 |
| 评分器 / 读数复算 | `after/` | `python -m policy.check ... --config-root <本目录>` |

`--config-root` 期望的是**包含 `validation/` 的目录**（与 `validators.registry.load_config(root=...)` 同口径），
不是 `validation/` 本身。

**运行期副作用**：验证器流水线的临时目录锚在 config root 下（`src/validators/pipeline.py` 的
`config.root/.tmp/validators/<run>`），用完即删；所以拿这两份当 `--config-root` 跑完会留下**空的**
`.tmp/validators/`。它不是配置、不进哈希、可随时删——快照的 9 个文件不受影响。

## 不许改

- 这两份快照是**冻结读数的一部分**：跑完再改快照 = 换了输入却沿用旧读数，该 run 作废
  （与 05 §5.4 的「冻结清单哈希不符即作废」同口径）。
- 两份必须保持"只差 `test-layout.yaml` 一个文件"（见下自证）；出现跨目录的差集就说明它们不再是一对
  可比输入。
- 配置要改，就**成对**更新（`validation/` 与快照同批改、重算本文件哈希、重跑 R-d），那是新一轮，
  不是本轮。
- `validation/` 里的 `.ruff_cache/` 是构建产物，**未**进快照（9 份受跟踪数据文件之外的东西都不是配置）。

## 逐文件 sha256

before（= HEAD `0208bee`，已逐文件与 `git show HEAD:validation/<f>` 比对，9/9 相同）：

| 文件 | sha256 |
| --- | --- |
| validation/validators.yaml | 1182a9c724ef073f5ba3dd7dff564d77d2d774e70bcf3f3daca7661fb5abe4dd |
| validation/project.yaml | 133743e10b0ad5198ee0d5ad36658d5fc376eac50380d2da59e33e5668dd9f9b |
| validation/test-layout.yaml | 69e9d4bbef6daf403ec090c59fbfda763cea5cf5894fa746b9f97ca03a63b3d3 |
| validation/ruff.toml | 2ac307f1352104331b35aa6120bd4dc6541bbc1eee1f833703afbb9640a2a33b |
| validation/mypy.ini | d579c3c445f1f35935d4fd6bbb42d84c74771b6e0d51ca23ef49ad80d6ea507a |
| validation/pytest.ini | 5b07bc2eeae46087dc5c3c52da519db4c20b9e9732b1f2b7139a34903d37c784 |
| validation/control-plane-facts.yaml | e514fa834142d224912f9952eed1fd429fba30c3d97b8c101d65ee4186d3ce78 |
| validation/channel-coverage.yaml | 21de65bfc410a257b0252148b7c1ad77a0e39219556f88a5f3fafb36633c8951 |
| validation/instrument-checks.yaml | 12c9b8bb1799c5fe76f3324a58542d1c3efc0a6c10b0d029bd45f0e5dcb0e1eb |

after：

| 文件 | sha256 |
| --- | --- |
| validation/validators.yaml | 1182a9c724ef073f5ba3dd7dff564d77d2d774e70bcf3f3daca7661fb5abe4dd |
| validation/project.yaml | 133743e10b0ad5198ee0d5ad36658d5fc376eac50380d2da59e33e5668dd9f9b |
| validation/test-layout.yaml | af70bee1bb8a886190cda33141d0ccf6d00acd0dde92383dddb0a30f37b9bf2a |
| validation/ruff.toml | 2ac307f1352104331b35aa6120bd4dc6541bbc1eee1f833703afbb9640a2a33b |
| validation/mypy.ini | d579c3c445f1f35935d4fd6bbb42d84c74771b6e0d51ca23ef49ad80d6ea507a |
| validation/pytest.ini | 5b07bc2eeae46087dc5c3c52da519db4c20b9e9732b1f2b7139a34903d37c784 |
| validation/control-plane-facts.yaml | e514fa834142d224912f9952eed1fd429fba30c3d97b8c101d65ee4186d3ce78 |
| validation/channel-coverage.yaml | 21de65bfc410a257b0252148b7c1ad77a0e39219556f88a5f3fafb36633c8951 |
| validation/instrument-checks.yaml | 12c9b8bb1799c5fe76f3324a58542d1c3efc0a6c10b0d029bd45f0e5dcb0e1eb |

每个目录下另有一份机器可读的 `sha256.txt`（格式 = 仓库既有的 `<sha256>  <relpath>`，按 relpath 排序、
UTF-8 / LF / 单尾换行；POSIX 上可直接 `sha256sum -c`）。

## 自证：两份只差 test-layout.yaml

| 检查 | 命令 | 读数 |
| --- | --- | --- |
| 逐文件比对 | 上表逐行比 | **8 个文件 sha256 相同、1 个不同**（`test-layout.yaml`） |
| 差异形态 | `git diff --no-index before/validation/test-layout.yaml after/validation/test-layout.yaml` | 退出码 1；**新增 6 行、删除 0 行**：取值 1 行（`- "tools/**/*.py"`）+ 注释 5 行 |
| 冻结字段 | 读 after 的 `version` / `schema_id` | `2` / `test-layout/2`（**未升版**：改的是 `production_patterns` 的**取值**，不是 schema；见读数的版本轴判断） |
| 与工作树一致 | 提交前重算 `validation/*` 的 sha256 | 与上表 after 列逐行相同（同一份配置） |
