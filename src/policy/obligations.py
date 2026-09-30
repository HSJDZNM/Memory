"""义务账（台阶 3c / 方案 §3.3）：把「待实现」变成一条有账可查、**只由真实测试运行解除**的义务。

它解决的问题：Q7 的「先写测试」被放行之后，「覆盖它的测试还没能运行」这件事只活在**那一次**判定里。
下一次判定、下一个会话、本机门禁都读不到它 —— 一个拼错的 import 可以永久待实现下去，而每一次
判定都是 `allow_with_warnings`。义务账把这件事变成**跨会话持久化**的一行数据。

三条口径（与方案 §3.3 逐条对应；改任何一条都要先改方案）：

1. **会话内只记账，不判罚**：本模块只读写账本，**不产出也不修改**任何 decision —— 判定仍然只有
   `policy.engine.evaluate` 一条路径；判罚集中在本机门禁（`tools/obligations_gate.py`）。
2. **键 = (rule_id, target, missing_target)，不含 session_id**：带上会话标识，新会话就会把义务
   清零（评审 §2.1），而「这个目标还是没人覆盖」与是哪个会话发现的无关。
3. **解除只由一次真实 pytest 运行判定，不许由账本推断**：账本里只有 `test_run` 记录
   （且 `python_tests_executed=true`）能解除；门禁声称 `obligations_open == 0` 时
   **必须**同时给出「最近一次真实测试运行」——给不出就不许声称 0（那正是"跳过被读成通过"的老毛病）。

**L5 上线闸（台阶 5）**：本机制先以 **warn** 形式跑一轮 —— 记账失败不改判定、不阻断，但必须显式
写出来（调用点见 `policy/check.py` 与 `adapters/dsh/hooks.py`，门禁见
`tools/obligations_gate.py`）。升格判据是「跑过 N≥1 次且 0 命中」，且 0 命中必须来自
至少一次真实读数。

**账本是追加写 JSONL**：不删不改，解除是**折叠时算出来的**，不是把旧行划掉；因此"什么时候记的、
什么时候解除的"都能从同一份文件读出来。

**未结义务的 payload 形状**（`to_payload`）与本模块的键集合一起构成协议：新增键要递增
`OBLIGATIONS_LEDGER_SCHEMA_VERSION`（AGENTS 第 55 条）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

__all__ = [
    "KIND_PENDING",
    "KIND_TEST_RUN",
    "LEDGER_SCHEMA_VERSION",
    "OBLIGATIONS_KEYS",
    "Obligation",
    "ObligationKey",
    "ObligationsError",
    "TestRun",
    "book_pending_findings",
    "describe",
    "load",
    "real_pytest_run",
    "record_pending",
    "record_test_run",
    "summarize",
    "utc_now",
]

# 账本自己的协议版本（AGENTS 第 55 条：新增键或改语义都要动它）。
LEDGER_SCHEMA_VERSION = "1.0"

KIND_PENDING = "pending"
KIND_TEST_RUN = "test_run"

# 与 validators.models.ValidatorStatus 的取值同名。这里**不 import 验证器层**：
# 内核只依赖标准库 + pydantic + PyYAML（AGENTS 核心约束 1），调用方负责把枚举转成取值；
# 两份声明不许漂移，由 tests/unit/test_obligations.py 的契约断言钉住。
PYTEST_EXECUTED_STATUSES = ("ok", "findings")
FAILING_TESTS_CHECKER = "failing_tests"
PYTEST_VALIDATOR_ID = "tool.pytest"

_PENDING_KEYS = (
    "kind",
    "schema_version",
    "at",
    "rule_id",
    "rule_version",
    "target",
    "missing_target",
    "missing_targets",
    "test_module",
    "checker",
)
_TEST_RUN_KEYS = (
    "kind",
    "schema_version",
    "at",
    "target",
    "selected_tests",
    "python_tests_executed",
    "source",
)


# 记录键集合就是协议：这里把它公开出来，好让测试与门禁按同一份事实断言
# （新增键要按 AGENTS 第 55 条递增 `LEDGER_SCHEMA_VERSION`）。
OBLIGATIONS_KEYS = {KIND_PENDING: _PENDING_KEYS, KIND_TEST_RUN: _TEST_RUN_KEYS}


class ObligationsError(Exception):
    """账本不可用：读不到、坏行、版本不认识、键集合不认识。一律显式失败，不静默跳过。"""


def utc_now() -> str:
    """UTC 时间戳（秒级精度 + Z 后缀）：账本里只有墙钟，没有相对时间。"""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, order=True)
class ObligationKey:
    """义务的身份（方案 §3.3 的键）：`(rule_id, target, missing_target)`。

    - `rule_id` 不带版本：规则升版不该把同一条义务变成新义务（版本作为字段记在记录里）；
    - `target` 是**那次判定的受治理文件**（仓库相对路径）——义务说的是"这个目标的覆盖测试
      还跑不了"；
    - `missing_target` 是它等的那个项目内目标（例如 `shop.order_service:cancel_order`）。
    """

    rule_id: str
    target: str
    missing_target: str

    def canonical(self) -> str:
        return self.rule_id + "|" + self.target + "|" + self.missing_target


@dataclass(frozen=True)
class Obligation:
    """一条**未结**义务：同一把键被记过几次、第一次与最后一次是什么时候。"""

    key: ObligationKey
    rule_version: int
    test_module: str
    checker: str
    missing_targets: tuple
    count: int
    first_seen: str
    last_seen: str

    def to_payload(self) -> dict:
        return {
            "rule_id": self.key.rule_id,
            "rule_version": self.rule_version,
            "target": self.key.target,
            "missing_target": self.key.missing_target,
            "missing_targets": list(self.missing_targets),
            "test_module": self.test_module,
            "checker": self.checker,
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


@dataclass(frozen=True)
class TestRun:
    """一次**真实** pytest 运行（`python_tests_executed=true` 才有资格解除义务）。"""

    at: str
    target: str
    selected_tests: tuple
    source: str

    def to_payload(self) -> dict:
        return {
            "at": self.at,
            "target": self.target,
            "selected_tests": list(self.selected_tests),
            "source": self.source,
        }


@dataclass(frozen=True)
class LedgerState:
    """一份账本折叠之后的状态（只读）。"""

    records: int
    pending_records: int
    test_run_records: int
    open: tuple
    closed: int
    last_real_test_run: Optional[TestRun]


# --------------------------------------------------------------------------- 记账


def _append(path: Path, record: Mapping) -> None:
    """追加一行；写之前先确认已有内容能读懂（失败关闭，不往坏账本里续写）。"""

    path = Path(path)
    if path.exists() and path.stat().st_size:
        _check_existing(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")


def _check_existing(path: Path) -> None:
    """已知的第一行要能读懂：版本不认识 / 键集合不认识 → 拒绝续写（AGENTS 核心约束 3）。"""

    try:
        with path.open("r", encoding="utf-8") as handle:
            first = handle.readline()
    except OSError as error:  # pragma: no cover - 权限 / 竞态
        raise ObligationsError("义务账本读不到：" + str(error)) from error
    if not first.strip():
        raise ObligationsError("义务账本的第一行是空行：说不出它是什么协议，拒绝续写")
    _parse_record(first, path=path, line_number=1)


def _parse_record(text: str, *, path: Path, line_number: int) -> Mapping:
    try:
        record = json.loads(text)
    except json.JSONDecodeError as error:
        raise ObligationsError(
            "义务账本第 " + str(line_number) + " 行不是合法 JSON：" + str(error)
        ) from error
    if not isinstance(record, Mapping):
        raise ObligationsError("义务账本第 " + str(line_number) + " 行不是对象")
    if record.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise ObligationsError(
            "义务账本第 "
            + str(line_number)
            + " 行的 schema_version="
            + repr(record.get("schema_version"))
            + " 不是本实现认识的 "
            + repr(LEDGER_SCHEMA_VERSION)
            + "；协议不认识的账本一律不读（AGENTS 第 55 条）"
        )
    kind = record.get("kind")
    if kind == KIND_PENDING:
        expected = _PENDING_KEYS
    elif kind == KIND_TEST_RUN:
        expected = _TEST_RUN_KEYS
    else:
        raise ObligationsError(
            "义务账本第 " + str(line_number) + " 行的 kind=" + repr(kind) + " 是未知记录类型"
        )
    unknown = sorted(set(record) - set(expected))
    missing = sorted(set(expected) - set(record))
    if unknown or missing:
        raise ObligationsError(
            "义务账本第 "
            + str(line_number)
            + " 行的键集合与 "
            + str(LEDGER_SCHEMA_VERSION)
            + " 不一致：多 "
            + repr(unknown)
            + "、缺 "
            + repr(missing)
            + "（键集合是协议，改它要按第 55 条递增版本号）"
        )
    return record


def record_pending(
    path,
    *,
    rule_id: str,
    rule_version: int,
    target: str,
    missing_target: str,
    test_module: str,
    checker: str,
    missing_targets: Sequence = (),
    at: Optional[str] = None,
) -> None:
    """记一条义务（同一把键再记一次 = 计数 +1、年龄继续长）。"""

    for name, value in (
        ("rule_id", rule_id),
        ("target", target),
        ("missing_target", missing_target),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ObligationsError("义务记录的 " + name + " 不许为空：" + repr(value))
    snapshot = tuple(sorted({item for item in missing_targets if item})) or (missing_target,)
    _append(
        Path(path),
        {
            "kind": KIND_PENDING,
            "schema_version": LEDGER_SCHEMA_VERSION,
            "at": at or utc_now(),
            "rule_id": rule_id,
            "rule_version": int(rule_version),
            "target": target,
            "missing_target": missing_target,
            "missing_targets": list(snapshot),
            "test_module": test_module,
            "checker": checker,
        },
    )


def record_test_run(
    path,
    *,
    target: str,
    selected_tests: Sequence = (),
    python_tests_executed: bool,
    source: str,
    at: Optional[str] = None,
) -> None:
    """记一次验证器流水线里的 pytest 运行。

    `python_tests_executed=False`（退出码 5 的零收集 / 没有选中任何测试 / 待实现）也照样记，
    因为它是一条**读数**；只有 `True` 才会在折叠时解除义务 —— "没跑成"不许被读成"跑过了"。
    """

    if not isinstance(target, str) or not target.strip():
        raise ObligationsError("test_run 记录的 target 不许为空：" + repr(target))
    _append(
        Path(path),
        {
            "kind": KIND_TEST_RUN,
            "schema_version": LEDGER_SCHEMA_VERSION,
            "at": at or utc_now(),
            "target": target,
            "selected_tests": sorted({item for item in selected_tests if item}),
            "python_tests_executed": bool(python_tests_executed),
            "source": source,
        },
    )


def real_pytest_run(
    *,
    pytest_status: Optional[str],
    served_checkers: Sequence,
    selected_tests: Sequence,
) -> bool:
    """「这次真的跑了 pytest，且至少执行到一个用例」的**结构化**判据（不解析 reasons 文本）。

    三条同时成立：

    1. `tool.pytest` 的记录状态落在 `{ok, findings}`：`pending_implementation`
       （收集失败）与 `crashed` / `unavailable` 都不算跑成；
    2. `failing_tests` 在 `served_checkers` 里：退出码 5（选中了用例、一个都没
       收集到）时验证器只服务 `missing_tests`，failing_tests **不**进 served（台阶 1 / R-f）；
    3. `selected_tests` 非空：没有选中任何测试的早退分支同样没有执行证据。

    第 2、3 条缺一不可 —— 只按状态读会把"选了一堆用例却一个都没跑起来"记成跑过了。
    """

    if pytest_status not in PYTEST_EXECUTED_STATUSES:
        return False
    if FAILING_TESTS_CHECKER not in set(served_checkers):
        return False
    return bool([item for item in selected_tests if item])


def book_pending_findings(
    path,
    *,
    findings: Iterable,
    target: str,
    pending_snapshot: Sequence = (),
    at: Optional[str] = None,
) -> int:
    """把一次判定的 `pending_findings` 记进账本，返回**新记的条数**。

    - `findings` 是决策载荷里的 `Violation`（`rule_id` /
      `evidence.subject` / `evidence.value`）；
    - `pending_snapshot` 是验证器侧那份 `pending_implementation`（带全部
      `missing_targets`），用 `test_modules` 把两边接起来 —— 这样账本里的快照是
      完整的，而不是只留第一条；
    - `target` 是**本次判定的受治理文件**（仓库相对路径）。
    """

    snapshot_index: dict = {}
    for item in pending_snapshot:
        if not isinstance(item, Mapping):
            continue
        modules = item.get("test_modules") or ()
        misses = tuple(str(name) for name in (item.get("missing_targets") or ()) if name)
        for module in modules:
            snapshot_index.setdefault(str(module), misses)

    written = 0
    for finding in findings:
        evidence = getattr(finding, "evidence", None)
        subject = str(getattr(evidence, "subject", "") or "")
        value = str(getattr(evidence, "value", "") or "")
        snapshot = snapshot_index.get(subject, ())
        misses = tuple(dict.fromkeys([item for item in snapshot if item] or [value]))
        for missing in misses:
            record_pending(
                path,
                rule_id=str(getattr(finding, "rule_id", "")),
                rule_version=int(getattr(finding, "rule_version", 0) or 0),
                target=target,
                missing_target=missing,
                test_module=subject,
                checker=str(getattr(evidence, "kind", "") or ""),
                missing_targets=misses,
                at=at,
            )
            written += 1
    return written


# --------------------------------------------------------------------------- 折叠 / 读数


def load(path) -> LedgerState:
    """读一份账本并折叠。文件不存在 = **空账本**（不是错误）；坏行 = `ObligationsError`。"""

    path = Path(path)
    open_items: dict = {}
    closed = 0
    pending_records = 0
    test_run_records = 0
    last_run: Optional[TestRun] = None
    if not path.exists():
        return LedgerState(0, 0, 0, (), 0, None)
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ObligationsError("义务账本第 " + str(number) + " 行是空行")
            record = _parse_record(line, path=path, line_number=number)
            if record["kind"] == KIND_PENDING:
                pending_records += 1
                key = ObligationKey(
                    rule_id=str(record["rule_id"]),
                    target=str(record["target"]),
                    missing_target=str(record["missing_target"]),
                )
                previous = open_items.get(key)
                open_items[key] = Obligation(
                    key=key,
                    rule_version=int(record["rule_version"]),
                    test_module=str(record["test_module"]),
                    checker=str(record["checker"]),
                    missing_targets=tuple(str(item) for item in record["missing_targets"]),
                    count=1 if previous is None else previous.count + 1,
                    first_seen=str(record["at"]) if previous is None else previous.first_seen,
                    last_seen=str(record["at"]),
                )
                continue
            test_run_records += 1
            if not record["python_tests_executed"]:
                continue
            run = TestRun(
                at=str(record["at"]),
                target=str(record["target"]),
                selected_tests=tuple(str(item) for item in record["selected_tests"]),
                source=str(record["source"]),
            )
            last_run = run
            # 解除：`target` 相同，或**那次跑不起来的测试模块**这次真的被选中了。
            # 为什么是"或"：Q7 的真实推进次序是「先写测试（target = 测试文件）→ 再写实现
            # （target = 实现文件）」，只按 target 匹配会让义务永远挂着；而"覆盖它的测试这次
            # 真的跑了"才是这条义务要等的那个事实（评审 §2.1 的现场）。
            for key in [item for item in open_items if _covers(open_items[item], run)]:
                open_items.pop(key)
                closed += 1
    ordered = tuple(open_items[key] for key in sorted(open_items))
    return LedgerState(
        records=pending_records + test_run_records,
        pending_records=pending_records,
        test_run_records=test_run_records,
        open=ordered,
        closed=closed,
        last_real_test_run=last_run,
    )


def _covers(obligation: Obligation, run: TestRun) -> bool:
    if obligation.key.target == run.target:
        return True
    return obligation.test_module in set(run.selected_tests)


def summarize(path) -> dict:
    """门禁 / CLI 读的那一份摘要。**整数、不加权、不出现比例**（方案 §3.5）。"""

    path = Path(path)
    state = load(path)
    last = None if state.last_real_test_run is None else state.last_real_test_run.to_payload()
    if state.open:
        note = (
            "本次仍有未结义务：这些目标的覆盖测试还没能真的跑起来"
            "（obligations_open > 0 → check_volume.complete = false）"
        )
        claim_supported = False
    elif last is None:
        note = (
            "obligations_open == 0 **没有依据**：账本里没有任何一次真实 pytest 运行。"
            "解除只由一次真实测试运行判定，不许由账本推断（可能是账本从来没被写过）"
        )
        claim_supported = False
    else:
        note = "未结义务为 0，且账本里有最近一次真实 pytest 运行作为依据"
        claim_supported = True
    return {
        "ledger": str(path),
        "records": state.records,
        "pending_records": state.pending_records,
        "test_run_records": state.test_run_records,
        "obligations_open": len(state.open),
        "obligations_closed": state.closed,
        "obligations": [item.to_payload() for item in state.open],
        "last_real_test_run": last,
        "claim_supported": claim_supported,
        "note": note,
    }


def describe(summary: Mapping) -> str:
    """一行给人看的读数（CLI 与门禁共用同一份措辞，避免两处口径漂移）。"""

    open_count = int(summary["obligations_open"])
    if not open_count:
        last = summary.get("last_real_test_run")
        if last is None:
            return (
                "OPEN OBLIGATIONS: 0（**没有依据**：账本里没有一次真实 pytest 运行；"
                "解除只由真实运行判定）"
            )
        return "OPEN OBLIGATIONS: 0（最近一次真实 pytest 运行 " + str(last["at"]) + "）"
    items = "; ".join(
        item["rule_id"]
        + " "
        + item["target"]
        + " ← "
        + item["missing_target"]
        + "（×"
        + str(item["count"])
        + "，自 "
        + item["first_seen"]
        + "）"
        for item in summary["obligations"]
    )
    return (
        "OPEN OBLIGATIONS: "
        + str(open_count)
        + " 条未结义务 —— "
        + items
        + "；解除只由一次真实 pytest 运行判定，账本自己推断不出解除"
    )
