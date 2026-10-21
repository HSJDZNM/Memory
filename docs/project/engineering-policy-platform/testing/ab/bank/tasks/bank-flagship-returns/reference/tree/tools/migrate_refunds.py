"""v1 退货数据迁移到 v2：原子替换、坏输入失败关闭。"""

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from shop.refund_model import RefundRecord  # noqa: E402

_LEGACY_KEYS = frozenset({"id", "order", "cents", "why"})


def _require_int(name: str, value: object, number: int) -> int:
    """旧记录里的编号与金额必须是非负 int。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("line " + str(number) + ": " + name + " must be an int")
    if value < 0:
        raise ValueError("line " + str(number) + ": " + name + " must not be negative")
    return value


def _parse_legacy_line(line: str, number: int) -> dict:
    """解析并校验一行旧记录（键集合、类型、非空 why）。"""
    if not line.strip():
        raise ValueError("line " + str(number) + ": blank line")
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError("line " + str(number) + ": not JSON") from exc
    if not isinstance(data, dict) or set(data) != _LEGACY_KEYS:
        raise ValueError("line " + str(number) + ": keys must be exactly id/order/cents/why")
    for name in ("id", "order", "cents"):
        _require_int(name, data[name], number)
    why = data["why"]
    if not isinstance(why, str) or not why.strip():
        raise ValueError("line " + str(number) + ": why must be a non-empty string")
    return data


def _read_legacy(path: Path) -> list[dict]:
    """读入旧记录；重复 id 与格式问题一律 ValueError。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("legacy input is not readable") from exc
    rows: list[dict] = []
    seen: set[int] = set()
    for number, line in enumerate(text.splitlines(), 1):
        data = _parse_legacy_line(line, number)
        if data["id"] in seen:
            raise ValueError("line " + str(number) + ": duplicate id " + str(data["id"]))
        seen.add(data["id"])
        rows.append(data)
    return rows


def _to_v2(rows: list[dict]) -> list[RefundRecord]:
    """旧记录 → v2 记录，按 refund_id 升序。"""
    ordered = sorted(rows, key=lambda row: row["id"])
    return [
        RefundRecord(
            refund_id=row["id"],
            order_id=row["order"],
            amount_cents=row["cents"],
            fee_cents=0,
            reason=row["why"],
            status="migrated",
            idempotency_key=None,
        )
        for row in ordered
    ]


def _write_atomic(target: Path, records: list[RefundRecord]) -> None:
    """同目录临时文件 + os.replace；失败时不留半成品。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name("." + target.name + ".tmp")
    payload = "".join(
        json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    try:
        temp.write_bytes(payload.encode("utf-8"))
        os.replace(temp, target)
    except OSError:
        temp.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    """迁移入口：成功打印 MIGRATED <n> 并返回 0，坏输入返回 1。"""
    parser = argparse.ArgumentParser(description="migrate refunds v1 JSONL to v2")
    parser.add_argument("--in", dest="source", required=True)
    parser.add_argument("--out", dest="target", required=True)
    args = parser.parse_args(argv)
    try:
        rows = _read_legacy(Path(args.source))
    except ValueError as exc:
        print("migrate: " + str(exc), file=sys.stderr)
        return 1
    records = _to_v2(rows)
    try:
        _write_atomic(Path(args.target), records)
    except OSError:
        print("migrate: cannot write the output file", file=sys.stderr)
        return 1
    print("MIGRATED " + str(len(records)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
