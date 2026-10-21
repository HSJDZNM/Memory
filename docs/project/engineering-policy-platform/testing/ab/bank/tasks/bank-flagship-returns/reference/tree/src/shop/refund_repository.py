"""退货记录存储层：内存与 JSONL 两种形态。"""

import json
from pathlib import Path

from shop.refund_model import RefundRecord


class RefundRepository:
    """退款表的追加式存取。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._rows: list[dict] = []
        if self._path is not None:
            self._rows = self._read_existing()

    def _read_existing(self) -> list[dict]:
        """读回已有行；非法 JSON 行 / 非对象行一律 ValueError（不静默跳过）。"""
        assert self._path is not None
        if not self._path.is_file():
            return []
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError("refunds file is not readable") from exc
        rows: list[dict] = []
        for number, line in enumerate(text.splitlines(), 1):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("refunds file line " + str(number) + " is not JSON") from exc
            if not isinstance(payload, dict):
                raise ValueError(
                    "refunds file line " + str(number) + " is not a JSON object"
                )
            rows.append(payload)
        return rows

    def add(self, record: RefundRecord) -> dict:
        """追加一条记录，返回它的新副本；给了 path 时同步追加一行 JSON。"""
        payload = record.to_dict()
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
            with self._path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line)
        self._rows.append(dict(payload))
        return dict(payload)

    def all(self) -> list[dict]:
        """全部记录的副本。"""
        return [dict(row) for row in self._rows]

    def by_order(self, order_id: int) -> list[dict]:
        """该订单的记录副本，保持写入顺序。"""
        return [dict(row) for row in self._rows if row.get("order_id") == order_id]
