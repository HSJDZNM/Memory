"""v1 -> v2 台账迁移的纯函数模块（model 层）。"""

import json
import os
import tempfile
from pathlib import Path

import yaml

SCHEMA_KEYS = frozenset(
    {"schema_id", "version", "key_order", "sort_by", "sort_direction", "fields"})
FIELD_CONSTRAINTS = frozenset({"type", "const", "min", "min_length", "enum"})
FIELD_TYPES = frozenset({"int", "str"})
SORT_DIRECTIONS = frozenset({"asc", "desc"})
V1_KEYS = frozenset({"id", "order", "cents", "why"})
V2_KEYS = ("schema_version", "entry_id", "order_id", "amount_cents", "reason", "status")
SCHEMA_ID = "ledger-schema/2"


def load_schema(path: Path) -> dict:
    """读取并严格校验 v2 形状声明，原样返回读到的 dict。"""
    try:
        schema = yaml.safe_load(_read_text(path, "schema"))
    except yaml.YAMLError as exc:
        raise ValueError("schema: not valid YAML") from exc
    if not isinstance(schema, dict):
        raise ValueError("schema: the document is not a mapping")
    if set(schema) != SCHEMA_KEYS:
        raise ValueError("schema: top-level keys are not the declared six")
    if schema["schema_id"] != SCHEMA_ID:
        raise ValueError("schema: schema_id is not " + SCHEMA_ID)
    if not _is_int(schema["version"]) or schema["version"] != 2:
        raise ValueError("schema: version is not the integer 2")
    if not isinstance(schema["fields"], dict):
        raise ValueError("schema: fields is not a mapping")
    _check_layout(schema)
    return schema


def _check_layout(schema: dict) -> None:
    """key_order / sort_by / sort_direction 与逐字段约束的校验。"""
    key_order = schema["key_order"]
    _check_key_order(key_order, schema["fields"])
    if tuple(key_order) != V2_KEYS:
        raise ValueError("schema: key_order is not the v2 record key order")
    if schema["sort_by"] not in key_order:
        raise ValueError("schema: sort_by is not in key_order")
    if schema["sort_direction"] not in SORT_DIRECTIONS:
        raise ValueError("schema: sort_direction is not asc or desc")
    for name, spec in schema["fields"].items():
        _check_field(name, spec)


def read_v1(path: Path) -> list[dict]:
    """按文件顺序读取 v1 台账；任何坏行都抛 ValueError，不跳过。"""
    text = _read_text(path, "ledger")
    rows: list[dict] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise ValueError(_line(number) + "empty line")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(_line(number) + "not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(_line(number) + "not a JSON object")
        if set(payload) != V1_KEYS:
            raise ValueError(_line(number) + "key set is not the v1 four")
        _check_v1_row(payload, number)
        rows.append(dict(payload))
    if not rows:
        raise ValueError("ledger: the file is empty")
    return rows


def migrate_rows(rows: list[dict]) -> list[dict]:
    """把 v1 行映射成 v2 记录：校验、映射、按 entry_id 升序返回新 list。"""
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows: the v1 rows are empty")
    records, seen = [], set()
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(_line(number) + "not an object")
        if set(row) != V1_KEYS:
            raise ValueError(_line(number) + "key set is not the v1 four")
        _check_v1_row(row, number)
        entry_id = row["id"]
        if entry_id in seen:
            raise ValueError(_line(number) + "duplicate id")
        seen.add(entry_id)
        records.append(_to_v2(row))
    records.sort(key=lambda record: record["entry_id"])
    return records


def write_v2(path: Path, rows: list[dict]) -> None:
    """原子写入 v2 台账：同目录临时文件 + flush + os.replace。"""
    target = Path(path)
    parent = target.parent
    if not parent.is_dir():
        raise ValueError("target: the parent directory does not exist")
    payload = _serialize(rows)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".ledger-", suffix=".tmp", dir=str(parent))
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(target))
        temporary = None
    except OSError as exc:
        raise ValueError("target: cannot write the v2 ledger") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _read_text(path: Path, label: str) -> str:
    """读 UTF-8 文本；读不到或不是 UTF-8 一律转成 ValueError（消息不带绝对路径）。"""
    candidate = Path(path)
    try:
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(label + ": cannot read " + candidate.name) from exc


def _line(number: int) -> str:
    return "line " + str(number) + ": "


def _is_int(value: object) -> bool:
    """int 且不是 bool（bool 是 int 的子类，必须单独排除）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_key_order(key_order: object, fields: dict) -> None:
    """key_order 必须是互不相同的字符串，且与 fields 的键集合相等。"""
    if not isinstance(key_order, list) or not all(
            isinstance(name, str) for name in key_order):
        raise ValueError("schema: key_order is not a list of strings")
    if len(set(key_order)) != len(key_order):
        raise ValueError("schema: key_order has duplicate entries")
    if set(key_order) != set(fields):
        raise ValueError("schema: key_order and fields disagree")


def _check_field(name: str, spec: object) -> None:
    """单个字段声明：只允许已声明的约束键，type 必须在闭集里。"""
    if not isinstance(spec, dict):
        raise ValueError("schema: field " + name + " is not a mapping")
    if spec.get("type") not in FIELD_TYPES:
        raise ValueError("schema: field " + name + " has no valid type")
    if set(spec) - FIELD_CONSTRAINTS:
        raise ValueError("schema: field " + name + " uses an unknown constraint")
    if not _is_int(spec.get("min", 0)):
        raise ValueError("schema: field " + name + " has a non-integer min")
    if not _is_int(spec.get("min_length", 0)):
        raise ValueError("schema: field " + name + " has a non-integer min_length")
    values = spec.get("enum", ["migrated"])
    if not isinstance(values, list) or not values:
        raise ValueError("schema: field " + name + " has an empty enum")


def _check_v1_row(row: dict, number: int) -> None:
    """一条 v1 行的取值约束：三个非负 int（bool 不算）与一个非空 str。"""
    for key in ("id", "order", "cents"):
        value = row[key]
        if not _is_int(value):
            raise ValueError(_line(number) + key + " is not an int")
        if value < 0:
            raise ValueError(_line(number) + key + " is negative")
    reason = row["why"]
    if not isinstance(reason, str) or not reason:
        raise ValueError(_line(number) + "why is not a non-empty string")


def _to_v2(row: dict) -> dict:
    """按 v2 键序把一条 v1 行映射成新记录。"""
    return {
        "schema_version": 2,
        "entry_id": row["id"],
        "order_id": row["order"],
        "amount_cents": row["cents"],
        "reason": row["why"],
        "status": "migrated",
    }


def _serialize(rows: list[dict]) -> bytes:
    """把记录序列化成 UTF-8 + LF 的字节；不可序列化转成 ValueError。"""
    try:
        text = "".join(
            json.dumps(record, ensure_ascii=False) + "\n" for record in rows
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("rows: a record is not JSON serializable") from exc
    return text.encode("utf-8")
