"""校验 v2 台账的形状与排序的命令行入口（composition 层）。"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from shop.ledger_migration import load_schema  # noqa: E402

SCHEMA_PATH = ROOT / "config" / "ledger_schema.yaml"


def _parser() -> argparse.ArgumentParser:
    """构造 --path 的参数解析器（必填）。"""
    parser = argparse.ArgumentParser(description="校验 v2 台账")
    parser.add_argument("--path", required=True)
    return parser


def _read_payload(path: Path) -> str:
    """读原始字节并做字节层校验，返回 UTF-8 文本。"""
    candidate = Path(path)
    try:
        raw = candidate.read_bytes()
    except OSError as exc:
        raise ValueError("ledger: cannot read " + candidate.name) from exc
    if not raw:
        raise ValueError("ledger: the file is empty")
    if b"\r" in raw:
        raise ValueError("ledger: the file contains CR")
    if not raw.endswith(b"\n"):
        raise ValueError("ledger: missing the trailing newline")
    if raw.endswith(b"\n\n"):
        raise ValueError("ledger: more than one trailing newline")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("ledger: the file is not UTF-8") from exc


def _check_type(name: str, value: object, spec: dict) -> None:
    """按字段声明校验类型：int 不接受 bool，str 不接受别的。"""
    if spec["type"] != "int":
        if not isinstance(value, str):
            raise ValueError("field " + name + " is not a string")
        return
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("field " + name + " is not an int")


def _check_bounds(name: str, value: object, spec: dict) -> None:
    """按字段声明校验取值范围：min / min_length / enum。"""
    if "min" in spec and value < spec["min"]:
        raise ValueError("field " + name + " is below min")
    if "min_length" in spec and len(value) < spec["min_length"]:
        raise ValueError("field " + name + " is shorter than min_length")
    if "enum" in spec and value not in spec["enum"]:
        raise ValueError("field " + name + " is not in enum")


def _check_value(name: str, value: object, spec: dict) -> None:
    """校验一个字段值：类型、常量与取值范围。"""
    _check_type(name, value, spec)
    if "const" in spec and value != spec["const"]:
        raise ValueError("field " + name + " is not the declared constant")
    _check_bounds(name, value, spec)


def _check_sorted(records: list[dict], schema: dict) -> None:
    """按 sort_by / sort_direction 校验严格有序（重复值也算乱序）。"""
    name = schema["sort_by"]
    values = [record[name] for record in records]
    if len(set(values)) != len(values):
        raise ValueError("ledger: records repeat the sort key " + name)
    if schema["sort_direction"] == "asc":
        ordered = values == sorted(values)
    else:
        ordered = values == sorted(values, reverse=True)
    if not ordered:
        raise ValueError("ledger: records are not ordered by " + name)


def _check_records(text: str, schema: dict) -> int:
    """逐行校验记录形状、键序与排序，返回记录数。"""
    lines = text.splitlines()
    key_order = list(schema["key_order"])
    records: list[dict] = []
    for number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("line " + str(number) + ": not valid JSON") from exc
        if not isinstance(record, dict):
            raise ValueError("line " + str(number) + ": not a JSON object")
        if list(record) != key_order:
            raise ValueError("line " + str(number) + ": key order differs")
        for name in key_order:
            _check_value(name, record[name], schema["fields"][name])
        records.append(record)
    if not records:
        raise ValueError("ledger: the file has no records")
    _check_sorted(records, schema)
    return len(records)


def main(argv: list[str] | None = None) -> int:
    """校验入口：合法时打印 VERIFIED <n> 并返回 0，否则返回 1。"""
    arguments = _parser().parse_args(argv)
    try:
        schema = load_schema(SCHEMA_PATH)
        count = _check_records(_read_payload(Path(arguments.path)), schema)
    except ValueError as exc:
        sys.stderr.write("VERIFY FAILED: " + str(exc) + "\n")
        return 1
    sys.stdout.write("VERIFIED " + str(count) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
