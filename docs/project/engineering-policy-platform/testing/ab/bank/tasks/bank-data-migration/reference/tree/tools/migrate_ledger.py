"""把 v1 台账迁移成 v2 的命令行入口（composition 层）。"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from shop.ledger_migration import load_schema, migrate_rows, read_v1, write_v2  # noqa: E402

SCHEMA_PATH = ROOT / "config" / "ledger_schema.yaml"


def _parser() -> argparse.ArgumentParser:
    """构造 --in / --out 的参数解析器（两个选项都必填）。"""
    parser = argparse.ArgumentParser(description="把 v1 台账迁移成 v2")
    parser.add_argument("--in", dest="source", required=True)
    parser.add_argument("--out", dest="target", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """迁移入口：成功打印 MIGRATED <n> 并返回 0，坏数据返回 1。"""
    arguments = _parser().parse_args(argv)
    try:
        load_schema(SCHEMA_PATH)
        rows = read_v1(Path(arguments.source))
        records = migrate_rows(rows)
        write_v2(Path(arguments.target), records)
    except ValueError as exc:
        sys.stderr.write("MIGRATE FAILED: " + str(exc) + "\n")
        return 1
    sys.stdout.write("MIGRATED " + str(len(records)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
