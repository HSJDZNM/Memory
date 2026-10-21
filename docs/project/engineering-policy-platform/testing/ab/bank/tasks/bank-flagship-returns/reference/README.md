# 参考解要点（bank-flagship-returns）

> **用途**：给另一个子会话照此做出参考解（不是给它抄的成品代码）。参考解只用于
> ① 实测 A/T/C 三维天花板；② 校准 `interfaces.yaml` 的 A3 上限与 layers 的 A1 边。
> **保密**：写隐藏验收的子会话**不得**读本文件（独立出题）；本文件也不含任何隐藏用例的代码。
> **不写实现细节也可以**——下面给的是「必须做成什么样」的决策点 + 可执行的验收路径，
> 具体代码组织留给实现者。

## 1 文件清单（参考解要新增/修改的 19 个路径）

| 路径 | 角色 | 关键点 |
| --- | --- | --- |
| `src/shop/refund_model.py` | model | `REFUND_SCHEMA_VERSION = 2`；frozen dataclass；`to_dict` 只吐 8 键；`from_dict` 先做**键集合相等**再逐字段类型校验 |
| `src/shop/refund_policy.py` | model | `yaml.safe_load`；键集合相等校验；`fee_cents` 全整数；`is_eligible` 不抛异常 |
| `src/shop/refund_repository.py` | repository | 内存 + JSONL；读回时逐行 `json.loads` 且必须是 dict；副本语义 |
| `src/shop/refund_service.py` | service | 先校验后写入；idempotency 查已有记录；id 取最大 + 1 |
| `src/shop/refund_controller.py` | controller | 只 import service；构造器只收 service；无 repository 属性 |
| `tools/refund_demo.py` | composition | 唯一 new repository/service/controller 的地方；`__file__` 定位 config |
| `tools/migrate_refunds.py` | composition | 原子替换（同目录临时文件 + `os.replace`）；先校验全部行再写；排序 |
| `src/shop/order_repository.py`（改） | repository | 只加 `get`（返回副本或 None），其余方法逐字节不动 |
| `tests/test_refund_*.py` ×6 + `tests/test_migrate_refunds.py` | test | 与生产文件同名；覆盖 model/policy/repository/service/controller/demo/migrate |
| `tests/test_order_repository.py`（改） | test | 补 `get` 命中/未命中/返回副本三条 |
| `docs/refund.md` | docs | 5 个二级标题：模块 / 数据形状 / 迁移 / 幂等 / 命令 |
| `README.md`（改） | docs | 结构表 7 行 + 文末链接 |
| `data/refunds-v2.jsonl` | 产物 | 由迁移脚本生成；3 行、按 refund_id 升序 |

## 2 决策点（照这个做，别自由发挥）

1. **控制器不许有 repository**：`RefundController(service)` 只存 service。若让构造器默认
   `RefundService(OrderRepository(), RefundRepository(), load_policy(...))`，controller 就会 import repository →
   `ARCH-001`（error，block）且 A1 违规。默认装配放在 `tools/refund_demo.py`。
2. **先校验、后写入**：`create_refund` 的四步顺序固定（订单 → 金额 → 资格 → 幂等 → 写入）。
   「未知订单」「金额非正」「不合格」三种情况必须**一条记录都不写**（隐藏用例会数记录数）。
3. **幂等键是「查已有记录」而不是「去重表」**：用 `refunds.all()` 找 `idempotency_key` 相同的记录并原样返回。
   同一 key 返回同一 `refund_id`；不同 key 递增。
4. **整数算术**：`fee = amount * fee_bps // 10000`，再 `min(max(fee, min_fee), max_fee)`。
   不转 float，不四舍五入；基线 1000 分 → 25，500 分 → 12（向下取整）。
5. **资格判定用 `int(total_cents * max_refund_ratio)`**：`amount <= 这个值` 才算合格；订单缺失 / 没有
   `total_cents` / 金额非正一律 False。
6. **YAML 只走 `safe_load`**，异常统一包成 `ValueError`（消息不泄漏文件绝对路径）。
7. **仓储副本语义**：`add` 返回新 dict；`all` 返回新 list + 每条新 dict；`by_order` 同。
8. **迁移先全部校验再落盘**：读入所有行 → 校验（键集合/id 唯一/非负）→ 排序 → 生成字节 →
   写 `<out>.tmp` → `os.replace`。任何一步失败都返回 1 且不碰 `out`。
   同一输入两次运行的输出**逐字节相同**。
9. **工具脚本的 `sys.path` 处理**：`sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))`
   再 import，import 行加 `# noqa: E402`；不要用 `os.chdir` 或改 cwd。
10. **测试里不要 skip/xfail**，每个新测试文件至少一条 assert；demo 测试用 `tmp_path` 或
    `main(policy_path=...)` 注入，不依赖 cwd。

## 3 参考解应得到的读数（做完后实测并记进 run-record）

| 维度 | 期望 | 怎么测 |
| --- | --- | --- |
| 本地 pytest | 全绿；收集数 ≥ 10 | 项目根 `python -m pytest -q` |
| 演示 | exit 0；2 条记录 fee 25/12；两次逐字节相同 | `python tools/refund_demo.py` ×2 |
| 迁移 | exit 0；3 条 v2 记录；输入不变；两次相同 | 迁移命令 ×2 + sha256 |
| C（规则） | 19 个允许写里的 `.py` 改动面全部 `allow`、0 violation | `python -m policy.check <file> --workspace <ref-tree> --config-root <repo> --layer <layers.yaml> --operation edit --changed <改动集> --request-id ... --json` |
| A（结构） | `structure_metrics --layers layers.yaml --interfaces interfaces.yaml` 10/10 pass、A3 不超上限 | 同一棵树 |
| T（隐藏） | 48/48（T01–T38 + EN1–EN5 + I1–I5） | `hidden/runner.py --json`（由独立子会话实现） |

> 如果参考解在 A3 上超上限：**先改 `interfaces.yaml` 并说明理由**（那是声明，不是自动生成）；
> 不要为了让谓词变绿而改 `layers.yaml` 的层值——层是语义声明。

## 4 参考解不需要做的事

- 不要求写 `__all__`（A3 走 `declared_caps`，不是 `module_all`）。
- 不要求把 `order_controller` 接上退货入口（那会让既有文件多改一处；本任务只要求
  `OrderRepository.get` 一处对既有生产代码的改动）。
- 不要求改 `config/refund_policy.yaml` / `data/refunds-legacy.jsonl` / `AGENTS.md` / `pytest.ini` / `conftest.py`。
