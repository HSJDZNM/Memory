r"""义务账门禁（台阶 3c / 方案 §3.3，按 **L5 上线闸**以 warn 形式跑一轮）。

用法：

    python tools/obligations_gate.py --ledger <账本> [--ledger <账本> ...] [--json]

读数（每个账本一组）：

- `records` / `pending_records` / `test_run_records`：账本里有什么；
- `obligations_open` / `obligations_closed`：折叠之后的未结 / 已解除条数（整数）；
- `last_real_test_run`：最近一次**真实** pytest 运行 —— 门禁声称 `obligations_open == 0`
  时必须给出它；给不出就不许声称 0（`claim_supported=false` 也算命中）；
- `tree_digest`：这份读数属于**哪棵树**（方案 §3.1 的针脚；读不到就写 `unprovable`，
  不静默少算）。

**适用性（`applicable`）**：账本文件**不存在** = 这次**没有账本可读** —— 该账本报
`applicable=false`、给出**不适用**的措辞，**不算命中**；它连读数键（`obligations_open` /
`claim_supported` / `last_real_test_run`）都没有，因为那些键一旦出现就等于"读到了一份账本"。
反过来，账本**存在**（哪怕是个空文件）却拿不出「最近一次真实测试运行」，仍然是**没有依据**、
**按命中处理**（AGENTS 第 56 条，本口径未改）。`applicable_ledgers` /
`not_applicable_ledgers` 把两种情形分开数。

退出码：

- `0` = 所有**可读**账本都没有命中（账本全都不适用时也是 0：不适用不是失败，也不是通过）；
- `1` = 有命中（有未结义务，或"声称 0 却没有真实运行"这种没有依据的读数）；
- `2` = 用法错误 / 账本读不懂（协议不认识的账本一律不读，AGENTS 第 55 条）。

**"不适用"不许冒充"0 命中"**：升格判据是「跑过 N≥1 次且 0 命中」，而 0 命中必须来自
至少一次**真实读数** —— `applicable_ledgers == 0` 的那一次没有任何账本被读到，凑不了这个判据。

**载荷版本**：本报告的键集合按 AGENTS 第 55 条自带版本轴 `REPORT_SCHEMA_VERSION`
（1.0 = 台阶 3c 的形状：账本不存在也按"没有依据"记成命中；1.1 = 不适用单独成档；
1.2 = 现形状：顶层多一份 `reading_context`——哪棵树 / 哪个宿主 / 读的是哪个账本）。

**`reading_context` 只是旁注**（台阶 4 / 21 号 §3）：它不进任何判定，也不决定 `hits` /
`applicable` / `exit_code`；账本不存在时它写 `declarations.obligations_ledger.status =
"not_applicable"`，与报告里 `applicable=false` 同一口径。

**L5 试用期：它不是任何门禁的阻断步** —— `tools/ci_local.py` 把它登记成**只报告步骤**
（`REPORT_ONLY_STEPS`，带到期日 2026-10-31）：本机门禁会跑它、会打印命中数，
但**非零退出不计入门禁失败**（2026-09-30 裁定：本轮不新增任何阻断步骤）。
这里的非零退出只表示"这次读到了命中"，供评审与下一轮的升格判据使用；
升格判据是「跑过 N≥1 次且 0 命中」，而 **0 命中必须来自至少一次真实读数**。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from policy.obligations import ObligationsError, describe, summarize  # noqa: E402
from provenance import reading_context as reading  # noqa: E402

# 本报告的载荷版本（AGENTS 第 55 条：新增键或改语义都要动它）。
# 1.0 = 台阶 3c 的形状（账本不存在时也按"没有依据"给出命中，报告里没有"不适用"这一档）；
# 1.1 = 账本不存在 = `applicable=false` + 不适用（不算命中），
#       并新增 `applicable_ledgers` / `not_applicable_ledgers` 两个整数；
# 1.2 = 现形状（台阶 4 第二件）：顶层多一份 `reading_context`（21 号 §3 的统一形状）——
#       这份读数属于哪棵树、哪个宿主、**读的是哪个账本**。它只加旁注：
#       `hits` / `applicable` / `exit_code` 一个都不由它决定（21 号 §0）。
REPORT_SCHEMA_VERSION = "1.2"

WARN_NOTE = (
    "L5 试用期：本次读数以 warn 形式给出（非零退出只报告，不阻断任何东西）；"
    "升格判据是「跑过 N≥1 次且 0 命中」，且 0 命中必须来自至少一次真实读数"
)

NOT_APPLICABLE_NOTE = (
    "账本文件不存在：这次没有账本可读 —— 不适用（不是 0 条义务，也不是命中；"
    "不适用那次不算读到过账本，凑不了升格判据里的 0 命中）"
)


def tree_digest(root: Path) -> str:
    """树摘要：读不到就写 `unprovable`，绝不静默少算（方案 §3.1 的严格模式）。"""

    try:
        # 只导入真正要用的名字：多导入一个 `ProvenanceError`，会让"provenance.worktree 不再导出它"
        # 这种与本次无关的变化也变成 ImportError，把树摘要记成 unprovable（下面的 except Exception
        # 本来就能兜住它，所以那个名字既没用、又制造了脆弱耦合）。
        from provenance.worktree import workspace_tree_digest

        return workspace_tree_digest(root).sha256
    except ImportError as error:  # pragma: no cover - 只有 src 不在路径上时
        return "unprovable:ImportError:" + str(error)
    except Exception as error:  # noqa: BLE001 - 读不到 = unprovable，不是"没有不一致"
        return "unprovable:" + type(error).__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python tools/obligations_gate.py",
        description="义务账门禁（L5 试用期：warn + 非零退出，不阻断）。",
    )
    parser.add_argument(
        "--ledger",
        action="append",
        required=True,
        metavar="PATH",
        help="义务账本（JSONL），可重复；仓库内实例与 .tmp 实例各给一条即可对照",
    )
    parser.add_argument("--tree", default=str(REPO), help="树摘要的根（默认仓库根）")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    return parser


def ledger_declaration(item: str, *, index: int) -> tuple[str, dict]:
    """账本在 `reading_context.declarations` 里的那一块（第 1 个叫 obligations_ledger，
    第 2 个起加下标——**账本路径本身就是"读的是哪一份输入"**，所以它记在这里，不记在 tree 里）。

    账本文件不存在 = **不适用**（与报告里 `applicable=false` 同一口径，AGENTS 第 56 条）：
    这不是"读不到"，是"这次没有账本可读"。
    """

    path = Path(item)
    name = reading.DECLARATION_OBLIGATIONS_LEDGER
    if index > 1:
        name = name + "_" + str(index)
    if not path.is_file():
        return name, reading.not_applicable()
    return name, reading.declaration_block(path, root=REPO)


def build_reading_context(*, tree: Path, digest: str, ledgers: Sequence[str]) -> dict:
    """这份读数属于哪里（21 号 §2.3 第 a 行）：树 / 账本 / 宿主 / 本次运行。

    `digest` 是**调用方已经算过的那个值**（本文件上面那次 `tree_digest()`）——不另算一遍，
    免得同一份报告里出现两个"树摘要"。其余子块取不到一律降级（provenance.reading_context
    的设计：旁注不该让整份读数写不出来）。
    """

    declarations = dict(
        ledger_declaration(item, index=index) for index, item in enumerate(ledgers, start=1)
    )
    return reading.build(
        source=reading.SOURCE_GATE,
        tree=reading.tree_block(tree, digest=digest),
        declarations=declarations,
        host=reading.host_block(),
    )


def ledger_report(item: str, *, tree: Path, digest: str) -> dict:
    """一个账本一行读数。

    键按"这次有没有账本可读"出现或缺失（第 46/50 条：不许用同一个键的两种取值表示两件事）：
    账本不存在时**不产出** `obligations_open` / `claim_supported` 这类读数键 —— 它们一旦
    出现就等于"读到了一份账本"。
    """

    path = Path(item)
    if not path.exists():
        return {
            "ledger": str(path),
            "applicable": False,
            "hit": False,
            "note": NOT_APPLICABLE_NOTE,
        }
    summary = summarize(path)
    hit = summary["obligations_open"] > 0 or not summary["claim_supported"]
    return {
        **summary,
        "tree": str(tree),
        "tree_digest": digest,
        "applicable": True,
        "hit": hit,
    }


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    tree = Path(args.tree)
    digest = tree_digest(tree)

    reports = []
    hits = 0
    not_applicable = 0
    for item in args.ledger:
        path = Path(item)
        if path.exists() and not path.is_file():
            print("义务账本不是一个文件：" + str(path), file=sys.stderr)
            return 2
        try:
            report = ledger_report(item, tree=tree, digest=digest)
        except ObligationsError as error:
            print("义务账本读不懂：" + str(error), file=sys.stderr)
            return 2
        if not report["applicable"]:
            not_applicable += 1
        elif report["hit"]:
            hits += 1
        reports.append(report)

    payload = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "mode": "warn",
        "note": WARN_NOTE,
        "tree": str(tree),
        "tree_digest": digest,
        "ledgers": reports,
        "ledger_count": len(reports),
        "applicable_ledgers": len(reports) - not_applicable,
        "not_applicable_ledgers": not_applicable,
        "hits": hits,
        "exit_code": 1 if hits else 0,
        # 台阶 4：旁注（哪棵树 / 哪个宿主 / 读的是哪个账本）。升格判据要读的
        # "这次读数算不算一次真实读数"就靠它说清归属；它**不改**上面的 hits / exit_code。
        "reading_context": build_reading_context(
            tree=tree, digest=digest, ledgers=args.ledger
        ),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("义务账门禁（L5 试用期 · warn：非零退出只报告，不阻断）")
        print("  tree_digest: " + digest)
        for index, report in enumerate(reports, start=1):
            if not report["applicable"]:
                print("  [" + str(index) + "] " + report["ledger"] + " 不适用：" + report["note"])
                continue
            print(
                "  ["
                + str(index)
                + "] "
                + report["ledger"]
                + " records="
                + str(report["records"])
                + " pending="
                + str(report["pending_records"])
                + " test_run="
                + str(report["test_run_records"])
                + " closed="
                + str(report["obligations_closed"])
                + " hit="
                + ("YES" if report["hit"] else "no")
            )
            print("      " + describe(report))
            if report["last_real_test_run"] is not None:
                print("      最近一次真实 pytest 运行：" + str(report["last_real_test_run"]["at"]))
        verdict = "（有命中）" if hits else "（0 命中）"
        suffix = (
            ""
            if not not_applicable
            else "；不适用 " + str(not_applicable) + " 个（没有账本可读，不计入命中）"
        )
        print("  HITS: " + str(hits) + " / " + str(len(reports)) + " 个账本" + verdict + suffix)
    return 1 if hits else 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
