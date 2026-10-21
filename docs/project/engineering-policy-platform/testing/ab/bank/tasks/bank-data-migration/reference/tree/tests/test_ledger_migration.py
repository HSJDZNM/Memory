"""ledger_migration 的用例：schema / v1 / 映射 / 原子写。"""

import json
from pathlib import Path

import pytest

from shop.ledger_migration import load_schema, migrate_rows, read_v1, write_v2

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "config" / "ledger_schema.yaml"
LEDGER = ROOT / "data" / "ledger-v1.jsonl"


def _schema_text() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def test_load_schema_reads_the_commented_yaml() -> None:
    """带注释的 YAML 能读出 6 个顶层键与有序 key_order。"""
    schema = load_schema(SCHEMA)
    assert set(schema) == {
        "schema_id",
        "version",
        "key_order",
        "sort_by",
        "sort_direction",
        "fields",
    }
    assert schema["key_order"] == [
        "schema_version",
        "entry_id",
        "order_id",
        "amount_cents",
        "reason",
        "status",
    ]


def test_load_schema_rejects_an_extra_key(tmp_path: Path) -> None:
    """多一个顶层键就是坏 schema。"""
    path = tmp_path / "schema.yaml"
    path.write_text(_schema_text() + "\nextra: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_schema(path)


def test_load_schema_rejects_a_mismatched_key_order(tmp_path: Path) -> None:
    """key_order 与 fields 的键集合不一致就是坏 schema。"""
    path = tmp_path / "schema.yaml"
    path.write_text(_schema_text().replace("  - reason\n", "", 1), encoding="utf-8")
    with pytest.raises(ValueError):
        load_schema(path)


def test_read_v1_keeps_the_file_order() -> None:
    """4 行按文件顺序读入，id 不是升序。"""
    rows = read_v1(LEDGER)
    assert [row["id"] for row in rows] == [3, 1, 4, 2]
    assert all(set(row) == {"id", "order", "cents", "why"} for row in rows)


def test_read_v1_rejects_a_bool_id(tmp_path: Path) -> None:
    """True 冒充 int 必须被拒。"""
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        '{"id": true, "order": 1, "cents": 2, "why": "a"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError):
        read_v1(path)


def test_migrate_rows_maps_sorts_and_keeps_zero() -> None:
    """6 键按 key_order、status 固定、按 entry_id 升序，cents=0 保留。"""
    records = migrate_rows(read_v1(LEDGER))
    key_order = list(load_schema(SCHEMA)["key_order"])
    assert [record["entry_id"] for record in records] == [1, 2, 3, 4]
    assert all(list(record) == key_order for record in records)
    assert records[2]["amount_cents"] == 0
    assert {record["status"] for record in records} == {"migrated"}


def test_migrate_rows_rejects_a_duplicate_id() -> None:
    """同一个 id 出现两次必须被拒（不做部分迁移）。"""
    row = {"id": 1, "order": 101, "cents": 10, "why": "a"}
    with pytest.raises(ValueError):
        migrate_rows([dict(row), dict(row)])


def test_write_v2_is_atomic_and_idempotent(tmp_path: Path) -> None:
    """两次写出的字节相同，已存在目标被替换，且不留临时文件。"""
    target = tmp_path / "ledger-v2.jsonl"
    records = migrate_rows(read_v1(LEDGER))
    write_v2(target, records)
    first = target.read_bytes()
    write_v2(target, records)
    assert target.read_bytes() == first
    assert first.endswith(b"\n") and not first.endswith(b"\n\n")
    assert b"\r" not in first
    assert sorted(path.name for path in tmp_path.iterdir()) == ["ledger-v2.jsonl"]
    assert json.loads(first.splitlines()[0])["entry_id"] == 1


def test_write_v2_rejects_a_missing_parent(tmp_path: Path) -> None:
    """父目录不存在就是 ValueError，不替调用方建目录。"""
    target = tmp_path / "missing" / "ledger-v2.jsonl"
    with pytest.raises(ValueError):
        write_v2(target, migrate_rows(read_v1(LEDGER)))
    assert not (tmp_path / "missing").exists()
