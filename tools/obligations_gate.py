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

退出码：

- `0` = 所有账本都没有命中；
- `1` = 有命中（有未结义务，或"声称 0 却没有真实运行"这种没有依据的读数）；
- `2` = 用法错误 / 账本读不懂（协议不认识的账本一律不读，AGENTS 第 55 条）。

**L5 试用期：它不是任何门禁的阻断步**（`tools/ci_local.py` 的步骤表里没有它）。
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

WARN_NOTE = (
    "L5 试用期：本次读数以 warn 形式给出（非零退出只报告，不阻断任何东西）；"
    "升格判据是「跑过 N≥1 次且 0 命中」，且 0 命中必须来自至少一次真实读数"
)


def tree_digest(root: Path) -> str:
    """树摘要：读不到就写 `unprovable`，绝不静默少算（方案 §3.1 的严格模式）。"""

    try:
        from provenance.worktree import ProvenanceError, workspace_tree_digest

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


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    tree = Path(args.tree)
    digest = tree_digest(tree)

    reports = []
    hits = 0
    for item in args.ledger:
        try:
            summary = summarize(Path(item))
        except ObligationsError as error:
            print("义务账本读不懂：" + str(error), file=sys.stderr)
            return 2
        hit = summary["obligations_open"] > 0 or not summary["claim_supported"]
        hits += 1 if hit else 0
        reports.append({**summary, "tree": str(tree), "tree_digest": digest, "hit": hit})

    payload = {
        "mode": "warn",
        "note": WARN_NOTE,
        "tree": str(tree),
        "tree_digest": digest,
        "ledgers": reports,
        "ledger_count": len(reports),
        "hits": hits,
        "exit_code": 1 if hits else 0,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("义务账门禁（L5 试用期 · warn：非零退出只报告，不阻断）")
        print("  tree_digest: " + digest)
        for index, report in enumerate(reports, start=1):
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
        print("  HITS: " + str(hits) + " / " + str(len(reports)) + " 个账本" + ("（有命中）" if hits else "（0 命中）"))
    return 1 if hits else 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
