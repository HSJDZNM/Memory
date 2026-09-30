r"""豁免到期检查（**只报告**）：控制面重构方案 §4 台阶 4 / §5.2 R-b 的到期读数。

用法：

    python tools/exemption_expiry.py [--json] [--today YYYY-MM-DD] [--lead-days 14]

读两处声明（都是**已经存在**的载体，本脚本不新造声明）：

1. `adapters/wiring-scope.yaml` 的边界声明——经 `provenance.wiring_scope.load_wiring_scope` 读，
   不自己解析 YAML：形状（含"不治理必须带 expires_at"）只有那一份实现；
2. `tools/ci_local.py` 的 `REPORT_ONLY_STEPS`——本机门禁的"只报告步骤"就是带到期日的豁免。

规则**只有这一份实现**（方案要求"不新增阻断步骤"）：

- 距到期 ≤ `--lead-days`（默认 14）天 → **提醒**（`DUE`）；
- 已过期 → **标红**（`RED`：这条豁免不再成立，请续期或升格）；
- 两者都**不计入门禁失败**：本脚本退出码**恒为 0**（用法错误除外），
  读不到就写 `unprovable`，绝不把"读不到"变成阻断，也不把它读成"没有到期日"。

**默认输出的机器行**：`HITS: <已过期条数> / declared=<n> due=<n> expired=<n> unprovable=<n>`
—— `tools/ci_local.py` 的「只报告」读数就是按这一行取命中数的（`report_only_hits()` 的文本回退，
这一步的 args 里没有 `--json`），所以这一行是**跨文件契约**、格式必须稳定：
`hits` **只数已过期**（`due` 是提醒、`unprovable` 是读不到，两者都另列、都不计入命中）。
`--json` 载荷本轮**一个键都没有加**：它没有版本轴，按 AGENTS 第 55 条，给载荷加键要先裁定
（是否给它建一条版本轴）——所以机器读数走文本行，不走改载荷。

为什么要有它：每一处"不治理 / 不阻断 / 只报告"都必须带到期日，否则就是一张**永不过期的
空白支票**（方案 §3.5 / §5.2 R-b）。这个脚本是那份到期日的读数；
它**不**改变任何 allow / block，也不改 `adapters/wiring-scope.yaml` 的加载结果
（`provenance.wiring_scope` 只校验日期格式，不做"今天到期了没有"的判断——所以在它之外读）。
"""

from __future__ import annotations

import argparse
import datetime as _datetime
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from provenance.wiring_scope import WiringScopeError, load_wiring_scope  # noqa: E402

DEFAULT_SCOPE = REPO / "adapters" / "wiring-scope.yaml"
DEFAULT_LEAD_DAYS = 14
STATE_OK = "ok"
STATE_DUE = "due"
STATE_EXPIRED = "expired"
STATE_UNPROVABLE = "unprovable"


def _parse_day(value: str) -> _datetime.date:
    return _datetime.date.fromisoformat(value)


def state_for(expires_at: str, *, today: _datetime.date, lead_days: int) -> dict:
    """一条豁免的到期状态：只有这一个实现（ci_local 与别处都不再算一遍）。"""

    expires = _parse_day(expires_at)
    days = (expires - today).days
    if days < 0:
        state = STATE_EXPIRED
    elif days <= lead_days:
        state = STATE_DUE
    else:
        state = STATE_OK
    return {"expires_at": expires_at, "days": days, "state": state}


def _unprovable(source: str, detail: str) -> dict:
    return {"source": source, "id": "<未读到>", "detail": detail, "state": STATE_UNPROVABLE}


def scope_entries(path: Path, *, today: _datetime.date, lead_days: int) -> list[dict]:
    """边界声明里的到期项（in_scope 的声明**不该**有过期日，由加载器拒绝，这里只见带日期的）。"""

    try:
        scope = load_wiring_scope(path)
    except WiringScopeError as error:
        return [_unprovable(_display(path), str(error))]
    entries: list[dict] = []
    for entry in scope.scope:
        if entry.expires_at is None:
            continue
        entries.append(
            {
                "source": _display(path),
                "id": entry.id,
                "decision": entry.decision,
                **state_for(entry.expires_at, today=today, lead_days=lead_days),
            }
        )
    return entries


def ci_local_entries(*, today: _datetime.date, lead_days: int) -> list[dict]:
    """`tools/ci_local.py` 的只报告步骤（= 本机门禁的带到期日豁免）。"""

    target = REPO / "tools" / "ci_local.py"
    try:
        spec = importlib.util.spec_from_file_location("ci_local_for_expiry", target)
        if spec is None or spec.loader is None:
            return [_unprovable(_display(target), "连模块规格都建不出来")]
        module = importlib.util.module_from_spec(spec)
        # 登记进 sys.modules 再 exec：这是 spec_from_file_location 的标准配方，
        # 也是"被加载的模块将来用 @dataclass / 相对导入"时的必要条件（本次实测过这个坑）。
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        steps = tuple(module.REPORT_ONLY_STEPS)
    except Exception as error:  # noqa: BLE001 - 只报告：读不到就写 unprovable，绝不阻断
        return [_unprovable(_display(target), type(error).__name__ + ": " + str(error))]
    return [
        {
            "source": _display(target),
            "id": step.name,
            "decision": "report_only",
            **state_for(step.expires_at, today=today, lead_days=lead_days),
        }
        for step in steps
    ]


def _display(path: Path) -> str:
    """读数里的路径一律仓库相对（AGENTS 第 19 条同一口径）。"""

    try:
        return path.resolve().relative_to(REPO).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python tools/exemption_expiry.py",
        description="豁免到期检查（只报告：退出码恒为 0，不改任何 allow / block）。",
    )
    parser.add_argument("--scope", default=str(DEFAULT_SCOPE), help="边界声明（默认 adapters/wiring-scope.yaml）")
    parser.add_argument("--lead-days", type=int, default=DEFAULT_LEAD_DAYS, help="提前提醒的天数（默认 14）")
    parser.add_argument("--today", default=None, help="把「今天」钉死（YYYY-MM-DD）；默认取本机日期")
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    return parser


def run(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    today = _datetime.date.today() if args.today is None else _parse_day(args.today)
    entries = scope_entries(Path(args.scope), today=today, lead_days=args.lead_days)
    entries.extend(ci_local_entries(today=today, lead_days=args.lead_days))

    due = [item for item in entries if item["state"] == STATE_DUE]
    expired = [item for item in entries if item["state"] == STATE_EXPIRED]
    unprovable = [item for item in entries if item["state"] == STATE_UNPROVABLE]
    payload = {
        "mode": "report-only",
        "note": "只报告：不改任何退出码、不影响任何判定；到期前 " + str(args.lead_days) + " 天提醒，过期标红",
        "today": today.isoformat(),
        "lead_days": args.lead_days,
        "entries": entries,
        "due": due,
        "expired": expired,
        "unprovable": unprovable,
        "counts": {
            "declared": len(entries),
            "due": len(due),
            "expired": len(expired),
            "unprovable": len(unprovable),
        },
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print("豁免到期检查（只报告：不改退出码、不影响判定）")
    print("  today: " + today.isoformat() + "（提前 " + str(args.lead_days) + " 天提醒）")
    for item in entries:
        if item["state"] == STATE_UNPROVABLE:
            print("  读不到: " + item["source"] + " —— " + str(item.get("detail")))
            continue
        print(
            "  ["
            + item["state"]
            + "] "
            + item["source"]
            + " / "
            + item["id"]
            + " expires_at="
            + item["expires_at"]
            + "（还有 "
            + str(item["days"])
            + " 天）"
        )
    for item in due:
        print(
            "  DUE: "
            + item["source"]
            + " / "
            + item["id"]
            + " 将在 "
            + str(item["days"])
            + " 天后到期（expires_at="
            + item["expires_at"]
            + "）—— 到期前提醒，请续期或升格"
        )
    for item in expired:
        print(
            "  RED: "
            + item["source"]
            + " / "
            + item["id"]
            + " 已过期 "
            + str(-item["days"])
            + " 天（expires_at="
            + item["expires_at"]
            + "）—— 这条豁免不再成立，请续期或升格（本步不阻断门禁）"
        )
    # 机器行（跨文件契约）：ci_local 的只报告读数按它取命中数。hits **只数已过期**；
    # due / unprovable 另列、不计入——"提醒"与"读不到"都不是"这张豁免已经不成立"。
    # 下面那行 counts 保留原样：第 16 轮的读数引用的是它的子串，删掉会让旧读数对不上。
    print(
        "  HITS: "
        + str(len(expired))
        + " / declared="
        + str(len(entries))
        + " due="
        + str(len(due))
        + " expired="
        + str(len(expired))
        + " unprovable="
        + str(len(unprovable))
    )
    print(
        "  counts: declared="
        + str(len(entries))
        + " due="
        + str(len(due))
        + " expired="
        + str(len(expired))
        + " unprovable="
        + str(len(unprovable))
    )
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
