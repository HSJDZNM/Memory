"""声明版本 vs 宿主实际版本：把「静默漂移」变成一条能失败的检查。

修复对象（修复轮 14 的缺陷 2）：adapters/<agent>/manifest.yaml 的 agent_version 字段说明写着
「**已实测**的 Agent 产品版本」，但在那次修复之前，全仓库没有任何地方把这份声明与
**宿主实际版本**比对过。宿主升到 0.1.6-alpha.2 之后，声明仍然写着 0.1.5-rc.1，
而一致性套件、事件 fixture 重放与支持矩阵**全部照常通过**——声明与事实不一致，
所有绿灯都不受影响。这是一条静默漂移。

本模块回答两个问题，它们**互不代替**：

1. **这台机器上**：声明里那个版本，和真正装着的宿主版本，是不是同一个？
   python -m adapters.cli host-version --check（活体探测）；
2. **任何一台机器上（含没有宿主的 CI）**：提交进仓库的观测记录，与声明是不是一致？
   python -m adapters.cli host-version --record-check（记录比对，不探测宿主）。

为什么需要第 2 条（修复轮 15；来源 14 号文档 §5 Q8 的尾巴）：第 1 条修好之后，在没有 dsh 的
机器上它读不到宿主 → unavailable → 退出 0，等于「修了一条会红的检查，却没有任何地方会为它红」。
记录形态把「声明与实测」变成 CI 上的**硬门禁**，代价是新增一条维护纪律：
改了 adapters/<agent>/manifest.yaml 就必须重跑 --record（否则 CI 红在「记录过期」上）。

三条设计约束（每条都对应一个测试）：

1. **它不是拦截判定**（AGENTS.md 第 24 / 29 条管的是能力上限，不是版本号）：
   版本不一致不改变任何 allow / block，只让这条**显式调用**的检查退出 1。
   把版本号变成放行条件会把「宿主升级」直接封成「平台不可用」——那是把正常工作封死；
2. **状态互不折叠**：match / drift / not_declared / unavailable / recording_stale。
   「这台机器上读不到宿主版本」「读到且一致」「记录过期」是三件不同的事，谁也不许折成通过；
3. **不是「跑不了就算过」**：活体形态里只有 drift（以及能力上限 full 却声明不出读法）是失败，
   --require-runtime 才把「这台机器上根本读不到」也算失败——与 tools/dsh_sandbox_loop.py 的
   --require-dsh 同一套口径；记录形态（CI）里**记录缺失 / 不完整一律退出 1**：有门禁就必须有数据。

报告里不出现绝对路径（AGENTS.md 第 19 条同一口径）：只给声明里的裸命令名、解析后的**文件名**
与记录的**仓库相对路径**。记录文件里同样不出现本机布局——它只存**声明的读法**，不存解析结果。

这条检查**不覆盖**什么（必须写下来）：

- 它读的是宿主二进制**自报的版本**（或这份自报值在当时留下的记录），不是"这个二进制真的在
  治理这条链路"：接线事实归 adapters.cli wiring，能力上限归 manifest + 已审核哈希；
- 记录形态比对的是**提交进仓库的那份记录**：它能发现"声明改了没重录"（manifest 哈希不一致），
  不能发现"记录本身是在错误的机器上写的"——那要靠 --record 当时的人工核对与评审；
- 它不核对 Hook 包的版本，也不改变任何 allow / block。
"""

from __future__ import annotations

import datetime as clock
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)

from .base import manifest_digest
from .models import AdapterManifest, EnforcementLevel, HostVersionProbe

__all__ = [
    "DEFAULT_OBSERVED_PATH",
    "DEFAULT_PROBE_TIMEOUT_MS",
    "FIX_HINT",
    "HOST_VERSION_RECORD_SCHEMA_VERSION",
    "HOST_VERSION_SCHEMA_VERSION",
    "READING_GUIDE",
    "RECORD_FIX_HINT",
    "RECORD_DRIFT_FIX_HINT",
    "HostVersionError",
    "HostVersionFinding",
    "HostVersionRecordError",
    "HostVersionReport",
    "HostVersionStatus",
    "ObservedHostVersionEntry",
    "ObservedHostVersions",
    "ProbeOutcome",
    "build_observed_record",
    "check_declared_versions",
    "check_recorded_versions",
    "load_observed_record",
    "parse_observed_record",
    "probe_host_version",
    "record_failure_report",
    "record_refusal_report",
    "write_observed_record",
]

# 报告载荷的版本：新增了 recording_stale 状态与记录来源字段（recorded_at / manifest_digest 等），
# 按协议自己的规则显式递增（AGENTS.md 第 50 条同一口径：改载荷键必须递增版本号）。
HOST_VERSION_SCHEMA_VERSION = "1.1"
# 提交进仓库的观测记录（adapters/host-versions.observed.json）自己的版本。
HOST_VERSION_RECORD_SCHEMA_VERSION = "1.0"
DEFAULT_OBSERVED_PATH = "adapters/host-versions.observed.json"
DEFAULT_PROBE_TIMEOUT_MS = 10_000

READING_GUIDE = (
    "agent_version 是「已实测的产品版本」：它必须等于这台机器上真正装着的宿主版本。"
    "match = 声明与宿主（或记录）一致；drift = 不一致（宿主升级后没重跑 fixture / 声明写错了）；"
    "not_declared = 没有声明 host_version（没有宿主二进制的合成协议消费者；能力上限是 full 的"
    "Adapter 声明不出来就是失败）；unavailable = 声明了但这次读不到（二进制不在 / 非零退出 /"
    "输出解析不出 / 超时）——它既不是通过也不是失败，要显式加 --require-runtime 才会变红；"
    "recording_stale = 提交进仓库的观测记录过期（manifest 哈希对不上 / 记录里的版本与活体不一致 /"
    "记录缺条目）——记录过期就不是「已核对」，退出 1，重跑 --record 并把 diff 送评审。"
)

# 漂移的修复动作必须写进拒绝理由（AGENTS.md 第 50 条：拒绝理由要给出「改成什么形态就能过」）。
FIX_HINT = (
    "升级宿主后必须：重跑 python -m adapters.cli check 与 python -m adapters.cli events"
    "（以及真实会话闭环），把 adapters/<agent>/manifest.yaml 的 agent_version 改成实测值，"
    "再跑 python -m adapters.cli approve --reviewer <name> 重新审核"
)
# 记录过期 / 缺失时的修复动作：先重录，再评审。CI 硬门禁红在这里时，这一句就是"怎么才能过"。
RECORD_FIX_HINT = (
    "记录过期/缺失的修复动作：在装着真实宿主的机器上重跑"
    " python -m adapters.cli host-version --record，把 adapters/host-versions.observed.json 的"
    " diff 送评审（记录里的 manifest 哈希必须与当前 adapters/<agent>/manifest.yaml 一致）；"
    "改过声明就先跑 python -m adapters.cli approve --reviewer <name> 重新审核"
)
# 记录的实测值与声明不一致时的修复动作：分两种情况，两边都要说清楚"怎么才能过"。
RECORD_DRIFT_FIX_HINT = (
    "修复动作：先确认这台宿主上真正装的是哪个版本——若记录是对的，把 manifest 的 agent_version"
    " 改成记录值并重跑 python -m adapters.cli approve --reviewer <name>；若声明是对的，"
    "说明记录被改过或来自别的机器，重跑 python -m adapters.cli host-version --record 覆盖它"
)

# 报告里不出现绝对路径：先按"像路径"的形态替换掉，再截断。
_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/][^\s\"'|;]+")
_POSIX_PATH = re.compile(r"(?<![\w.])/(?:[^\s\"'|;/]+/)*[^\s\"'|;/]+")
_MANIFEST_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_READING_LABEL_LIMIT = 120

Runner = Callable[..., Any]


class HostVersionError(ValueError):
    """探测或记录写入本身不合法（CLI 参数错误、拒写观测记录等）。"""


class HostVersionRecordError(ValueError):
    """提交进仓库的观测记录缺失 / 不完整 / 不符合格式（CI 硬门禁据此退出 1）。"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message

    def __str__(self) -> str:  # pragma: no cover - 直接继承 message
        return self.message


class HostVersionStatus(str, Enum):
    """一次比对可能落在的五种状态。五种互不折叠，各自可读。"""

    MATCH = "match"
    DRIFT = "drift"
    NOT_DECLARED = "not_declared"
    UNAVAILABLE = "unavailable"
    RECORDING_STALE = "recording_stale"


@dataclass(frozen=True)
class ProbeOutcome:
    """一次探测的结果：成功就有版本，失败必须有理由。"""

    ok: bool
    version: Optional[str]
    executable_name: Optional[str]
    detail: str


@dataclass(frozen=True)
class HostVersionFinding:
    """一个 Adapter 的比对结论。"""

    agent_id: str
    declared_version: str
    status: HostVersionStatus
    enforcement: str
    observed_version: Optional[str] = None
    probe: Optional[str] = None
    executable: Optional[str] = None
    resolved_name: Optional[str] = None
    detail: str = ""
    # 这条结论来自哪一路事实：host = 这次活体探测；record = 提交进仓库的观测记录。
    source: str = "host"
    # 记录参与比对时留下的证据（活体形态里没参与就是 None）。
    recorded_at: Optional[str] = None
    recorded_digest: Optional[str] = None
    manifest_digest: Optional[str] = None

    @property
    def is_failure(self) -> bool:
        """drift 与 recording_stale 一律是失败；能力上限 full 却声明不出探测，也是失败。"""

        if self.status in (HostVersionStatus.DRIFT, HostVersionStatus.RECORDING_STALE):
            return True
        return (
            self.status is HostVersionStatus.NOT_DECLARED
            and self.enforcement == EnforcementLevel.FULL.value
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "declared_version": self.declared_version,
            "enforcement": self.enforcement,
            "status": self.status.value,
            "source": self.source,
            "observed_version": self.observed_version,
            "probe": self.probe,
            "executable": self.executable,
            "resolved_name": self.resolved_name,
            "recorded_at": self.recorded_at,
            "recorded_digest": self.recorded_digest,
            "manifest_digest": self.manifest_digest,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HostVersionReport:
    """一次完整比对：逐条结论 + 失败清单 + 「到底覆盖了几个」的计数。"""

    findings: Tuple[HostVersionFinding, ...]
    result: str
    failures: Tuple[str, ...]
    notes: Tuple[str, ...]
    covered: int
    total: int
    # "live" = 活体探测；"record" = 对提交进仓库的观测记录做比对（CI 形态）。
    mode: str = "live"
    record_path: Optional[str] = None
    record_recorded_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        counts = {item.value: 0 for item in HostVersionStatus}
        for finding in self.findings:
            counts[finding.status.value] += 1
        return {
            "schema_version": HOST_VERSION_SCHEMA_VERSION,
            "reading_guide": READING_GUIDE,
            "mode": self.mode,
            "result": self.result,
            "covered": self.covered,
            "total": self.total,
            "counts": counts,
            "findings": [item.to_dict() for item in self.findings],
            "failures": list(self.failures),
            "notes": list(self.notes),
            "record_path": self.record_path,
            "record_recorded_at": self.record_recorded_at,
        }


# --------------------------------------------------------------------------- 观测记录（数据）


class ObservedHostVersionEntry(BaseModel):
    """观测记录里的一条：一次真实探测看到的版本 + 当时按什么读法看 + 当时是哪一份声明。

    三条都要有，缺一条这条门禁就会被绕空：
    observed_version 少了就没有"实测值"；读法少了就不知道记录描述的是哪一次观测；
    manifest_digest 少了就发现不了"声明改了却没重录"。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str = Field(min_length=1)
    observed_version: str = Field(min_length=1, description="这次探测真实读到的版本")
    executable: str = Field(min_length=1, description="声明的裸命令名（不是解析后的路径）")
    args: Tuple[str, ...] = Field(default=(), description="声明的 argv（不经 shell）")
    version_pattern: str = Field(min_length=1, description="声明的版本正则")
    manifest_digest: str = Field(min_length=1, description="观测时 manifest 的 sha256")
    recorded_at: str = Field(min_length=1, description="这一条观测的时间戳（ISO8601，UTC）")

    @field_validator("agent_id", "observed_version", "executable", "version_pattern")
    @classmethod
    def _check_compact_text(cls, value: str, info: ValidationInfo) -> str:
        if value != value.strip() or not value:
            raise ValueError(f"记录的 {info.field_name} 必须是非空的单行文本，得到 {value!r}")
        return value

    @field_validator("observed_version")
    @classmethod
    def _check_version_shape(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError(
                f"记录的 observed_version 里出现空白字符：{value!r}；"
                "它是探测读到的版本号，不是一段说明文字"
            )
        return value

    @field_validator("args")
    @classmethod
    def _check_args(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        for item in value:
            if not isinstance(item, str) or not item or item != item.strip():
                raise ValueError(f"记录的 args 只能是非空单行字符串，得到 {item!r}")
        return tuple(value)

    @field_validator("manifest_digest")
    @classmethod
    def _check_digest(cls, value: str) -> str:
        if not _MANIFEST_DIGEST_PATTERN.match(value):
            raise ValueError(
                f"记录的 manifest_digest 必须是 sha256:<64 位小写十六进制>，得到 {value!r}；"
                "它由 adapters.base.manifest_digest 算出，不要手写"
            )
        return value

    @field_validator("recorded_at")
    @classmethod
    def _check_recorded_at(cls, value: str) -> str:
        if _parse_timestamp(value) is None:
            raise ValueError(
                f"记录的 recorded_at 不是 ISO8601 时间：{value!r}；"
                "记录必须说得出「什么时候观测的」"
            )
        return value

    @property
    def reading(self) -> Tuple[str, Tuple[str, ...], str]:
        return (self.executable, tuple(self.args), self.version_pattern)

    @property
    def probe_text(self) -> str:
        return reading_text(self.executable, self.args)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "observed_version": self.observed_version,
            "executable": self.executable,
            "args": list(self.args),
            "version_pattern": self.version_pattern,
            "manifest_digest": self.manifest_digest,
            "recorded_at": self.recorded_at,
        }


class ObservedHostVersions(BaseModel):
    """提交进仓库的观测记录（adapters/host-versions.observed.json）。

    它**只能**由 python -m adapters.cli host-version --record 写入：手写/半写的记录不是证据。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(min_length=1)
    recorded_at: str = Field(min_length=1, description="整次记录的运行时间戳（ISO8601，UTC）")
    entries: Tuple[ObservedHostVersionEntry, ...] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        if value != HOST_VERSION_RECORD_SCHEMA_VERSION:
            raise ValueError(
                f"记录的 schema_version 是 {value!r}，本模块只认 "
                f"{HOST_VERSION_RECORD_SCHEMA_VERSION!r}；未知协议版本一律拒绝"
            )
        return value

    @field_validator("recorded_at")
    @classmethod
    def _check_recorded_at(cls, value: str) -> str:
        if _parse_timestamp(value) is None:
            raise ValueError(f"记录的 recorded_at 不是 ISO8601 时间：{value!r}")
        return value

    @field_validator("entries")
    @classmethod
    def _check_entries(
        cls, value: Tuple[ObservedHostVersionEntry, ...]
    ) -> Tuple[ObservedHostVersionEntry, ...]:
        seen: set[str] = set()
        for entry in value:
            if entry.agent_id in seen:
                raise ValueError(
                    f"记录里出现重复的 agent_id {entry.agent_id!r}："
                    "同一个 Adapter 只能有一条实测值"
                )
            seen.add(entry.agent_id)
        return tuple(value)

    def get(self, agent_id: str) -> Optional[ObservedHostVersionEntry]:
        for entry in self.entries:
            if entry.agent_id == agent_id:
                return entry
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "recorded_at": self.recorded_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _parse_timestamp(value: str) -> Optional[clock.datetime]:
    """解析 ISO8601；带时区才算合格（记录必须说得出"什么时候"，且不依赖本机时区）。"""

    text = value.strip()
    if not text:
        return None
    try:
        parsed = clock.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def reading_text(executable: str, args: Sequence[str]) -> str:
    """把读法压成一行：报告与记录里只出现**声明的**读法，不出现解析后的路径。"""

    text = " ".join((executable, *args)).strip()
    if len(text) > _READING_LABEL_LIMIT:
        text = text[:_READING_LABEL_LIMIT] + "..."
    return text


def _describe_reading(executable: str, args: Sequence[str], pattern: str) -> str:
    return f"{reading_text(executable, args)}（version_pattern {pattern}）"


def parse_observed_record(document: Any, *, source: str) -> ObservedHostVersions:
    """把**不可信**的记录文档解析成模型；任何未知字段 / 未知版本 / 不完整一律报错。

    "记录缺失"与"记录不完整"是两件事，但都不许被读成通过：调用方按 kind 区分
    （record_missing / record_invalid）并退出 1。
    """

    if not isinstance(document, dict):
        raise HostVersionRecordError(
            "record_invalid",
            f"{source}：观测记录的顶层必须是 JSON 对象，得到 {type(document).__name__}",
        )
    try:
        return ObservedHostVersions.model_validate(document)
    except ValidationError as error:
        detail = _first_validation_message(error)
        raise HostVersionRecordError(
            "record_invalid", f"{source}：观测记录不符合格式：{detail}"
        ) from error


def _first_validation_message(error: ValidationError) -> str:
    """只留第一条：记录不完整时读者要的是「怎么改」，不是一整份 pydantic 报错。"""

    issues = error.errors()
    if not issues:
        return str(error)
    first = issues[0]
    location = ".".join(str(item) for item in first.get("loc", ()))
    message = str(first.get("msg", "")).strip()
    return f"{location}：{message}" if location else message


def load_observed_record(path: Path | str, *, label: Optional[str] = None) -> ObservedHostVersions:
    """读一份提交进仓库的观测记录；读不到就按 record_missing / record_invalid 分类失败。

    label 是给报告用的**仓库相对路径**：这个模块的任何输出都不许出现本机绝对路径。
    """

    target = Path(path)
    where = label or target.name
    if not target.is_file():
        raise HostVersionRecordError(
            "record_missing",
            f"观测记录不存在：{where}（有门禁就必须有数据，缺失不是「跳过」）",
        )
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise HostVersionRecordError(
            "record_invalid", f"{where}：观测记录读不出来：{type(error).__name__}: {error}"
        ) from error
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise HostVersionRecordError(
            "record_invalid", f"{where}：观测记录不是合法 JSON：{error}"
        ) from error
    return parse_observed_record(document, source=where)


def dump_observed_record(record: ObservedHostVersions) -> str:
    """稳定的序列化形态：排序键 + 两条空格缩进 + 单换行结尾（文本约定）。"""

    return (
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + chr(10)
    )


def write_observed_record(record: ObservedHostVersions, path: Path | str) -> Path:
    """原子写入观测记录：先自检"写得出的读得回来"，再落到目标路径。

    先写临时文件再 os.replace：写到一半崩溃不会留下半份记录（半份记录比没有更坏——
    它看起来像证据）。
    """

    target = Path(path)
    text = dump_observed_record(record)
    # 自检：写出去的那份文本必须能被同一个解析器读成同一个记录（格式与内容都钉死）。
    parse_observed_record(json.loads(text), source=target.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline=chr(10))
        os.replace(temporary, target)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - 清理失败不该盖住原始错误
            pass
        raise HostVersionError(f"观测记录写入失败：{type(error).__name__}: {error}") from error
    return target


def build_observed_record(
    manifests: Mapping[str, AdapterManifest],
    report: HostVersionReport,
    *,
    recorded_at: str,
) -> ObservedHostVersions:
    """把一次**全部 match** 的活体比对固化成观测记录；有任何不确定就拒绝写入。

    记录是「核对过的证据」，不是「这次探测的输出」：drift / unavailable 都不许进记录
    （它们说明这次没有可提交的实测值），一个条目都没有更不许写（那就是"有门禁、没数据"）。
    """

    if report.result != "pass":
        raise HostVersionError(
            f"这次活体比对的结果是 {report.result}，不是 pass："
            "记录只能装「已核对过」的证据，先把上面这份比对里的漂移/读不到修好再重录"
        )
    by_agent = {item.agent_id: item for item in report.findings}
    entries: list[ObservedHostVersionEntry] = []
    for agent_id in sorted(manifests):
        manifest = manifests[agent_id]
        probe = manifest.host_version
        if probe is None:
            continue
        finding = by_agent.get(agent_id)
        if (
            finding is None
            or finding.status is not HostVersionStatus.MATCH
            or not finding.observed_version
        ):
            seen_status = "无 finding" if finding is None else finding.status.value
            raise HostVersionError(
                f"{agent_id} 这次没有拿到可提交的实测值（{seen_status}）："
                "记录不完整就不许写——半份记录看起来像证据，比没有更坏"
            )
        entries.append(
            ObservedHostVersionEntry(
                agent_id=agent_id,
                observed_version=finding.observed_version,
                executable=probe.executable,
                args=probe.args,
                version_pattern=probe.version_pattern,
                manifest_digest=manifest_digest(manifest),
                recorded_at=recorded_at,
            )
        )
    if not entries:
        raise HostVersionError(
            "这次记录一个条目都没有：没有任何 Adapter 声明 host_version 读法。"
            "有门禁就必须有数据——先声明读法（executable / args / version_pattern），"
            "或如实说明为什么这个 Adapter 不需要这条检查"
        )
    return ObservedHostVersions(
        schema_version=HOST_VERSION_RECORD_SCHEMA_VERSION,
        recorded_at=recorded_at,
        entries=tuple(entries),
    )


def record_failure_report(
    error: HostVersionRecordError, *, record_label: str
) -> HostVersionReport:
    """记录缺失 / 不完整时的报告：它既不是"通过"也不是"跳过"，而是门禁没有数据。"""

    return HostVersionReport(
        findings=(),
        result=error.kind,
        failures=(f"{error.message}。{RECORD_FIX_HINT}",),
        notes=(
            "记录形态（--record-check）不探测宿主：它比对的是提交进仓库的观测记录与当前声明。",
        ),
        covered=0,
        total=0,
        mode="record",
        record_path=record_label,
    )


def record_refusal_report(
    report: HostVersionReport, error: HostVersionError
) -> HostVersionReport:
    """拒写观测记录时的报告：退出码 1 必须能**从载荷里读出来**（不许 exit 1 而 result=pass）。

    "拒写"是一个结论，不是一个异常：把理由写进 failures，并给一个可读的结果名
    （record_refused），让 JSON 消费方不需要去看 stderr 才知道发生了什么。
    """

    return replace(
        report,
        result="record_refused",
        failures=tuple(report.failures) + (str(error),),
        notes=tuple(report.notes)
        + ("本次没有写入观测记录：记录只装「已核对过」的证据（全部 match 且至少一条）。",),
    )


def redact(text: Any, *, limit: int = 240) -> str:
    """把不可信文本压成一行、抹掉绝对路径、截断：报告里不留本机布局与超长载荷。"""

    collapsed = " ".join(str(text).split())
    collapsed = _WINDOWS_PATH.sub("<path>", collapsed)
    collapsed = _POSIX_PATH.sub("<path>", collapsed)
    if len(collapsed) > limit:
        collapsed = collapsed[:limit] + "..."
    return collapsed


def resolve_executable(
    name: str, override: Optional[Path | str] = None
) -> Tuple[Optional[str], str]:
    """把声明里的裸命令名解析成可执行文件；返回 (路径或 None, 说明)。

    override（CLI 的 --probe-binary）是**操作员**给的，不走"裸命令名"约束；
    它只影响这一次探测，不改变声明本身。
    """

    if override is not None:
        candidate = Path(override)
        if candidate.is_file():
            return str(candidate), "由 --probe-binary 显式指定"
        return None, f"--probe-binary 指定的文件不存在：{candidate.name}"
    found = shutil.which(name)
    if found is None:
        return None, f"PATH 上找不到可执行文件 {name}：宿主版本无从读取"
    return found, "PATH 命中"


def probe_host_version(
    probe: HostVersionProbe,
    *,
    executable_override: Optional[Path | str] = None,
    timeout_ms: int = DEFAULT_PROBE_TIMEOUT_MS,
    runner: Optional[Runner] = None,
) -> ProbeOutcome:
    """按**声明**的读法跑一次宿主版本探测。

    失败一律分类成 unavailable 并给出理由：找不到二进制 / 非零退出 / 输出解析不出 /
    超时 / 执行被拒。绝不返回"装作读到了"的空版本。
    """

    resolved, note = resolve_executable(probe.executable, executable_override)
    name = probe.executable if resolved is None else Path(resolved).name
    if resolved is None:
        return ProbeOutcome(ok=False, version=None, executable_name=name, detail=note)

    argv = [resolved, *probe.args]
    run = runner if runner is not None else subprocess.run
    try:
        completed = run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=max(int(timeout_ms), 1) / 1000.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ProbeOutcome(
            ok=False,
            version=None,
            executable_name=name,
            detail=f"探测超时（{int(timeout_ms)} ms）：{name} {' '.join(probe.args)}".strip(),
        )
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return ProbeOutcome(
            ok=False,
            version=None,
            executable_name=name,
            detail=redact(f"探测无法执行：{type(error).__name__}: {error}"),
        )

    returncode = getattr(completed, "returncode", None)
    stdout = getattr(completed, "stdout", "") or ""
    stderr = getattr(completed, "stderr", "") or ""
    if returncode != 0:
        return ProbeOutcome(
            ok=False,
            version=None,
            executable_name=name,
            detail=redact(f"{name} 退出码 {returncode}：" + (stderr or stdout or "（无输出）")),
        )
    match = re.search(probe.version_pattern, stdout + "\n" + stderr)
    if match is None:
        return ProbeOutcome(
            ok=False,
            version=None,
            executable_name=name,
            detail=redact(f"输出里解析不出声明正则匹配的版本：{stdout or stderr or '（无输出）'}"),
        )
    # 声明正则允许"恰好一个捕获组"，但那个组可以**不参与匹配**（可选组）：group(1) 这时是
    # None，直接 .strip() 会抛 AttributeError，破坏"读不出来 = unavailable"的契约。
    version = (match.group(1) or "").strip()
    if not version:
        return ProbeOutcome(
            ok=False,
            version=None,
            executable_name=name,
            detail="输出里匹配到的版本是空字符串：声明正则要求一个非空捕获组",
        )
    return ProbeOutcome(
        ok=True, version=version, executable_name=name, detail=f"{name} 报告 {version}"
    )


def _staleness_reason(
    entry: Optional[ObservedHostVersionEntry],
    *,
    digest: str,
    probe: HostVersionProbe,
    live_version: str,
) -> Optional[str]:
    """记录与活体读数/当前声明不一致时的理由；一致返回 None。"""

    if entry is None:
        return "记录里没有它的条目（记录不完整）"
    if entry.manifest_digest != digest:
        return (
            f"记录钉住的 manifest 哈希 {entry.manifest_digest} 与当前声明 {digest} 不一致"
            "（声明改过但没重录）"
        )
    if entry.reading != (probe.executable, tuple(probe.args), probe.version_pattern):
        recorded = _describe_reading(entry.executable, entry.args, entry.version_pattern)
        declared = _describe_reading(probe.executable, probe.args, probe.version_pattern)
        return f"记录里的探测读法 {recorded} 与当前声明 {declared} 不一致"
    if entry.observed_version != live_version:
        return f"记录里写着 {entry.observed_version}（记录于 {entry.recorded_at}）"
    return None


def check_declared_versions(
    manifests: Mapping[str, AdapterManifest],
    *,
    enforcement_by_agent: Mapping[str, str],
    overrides: Optional[Mapping[str, Path | str]] = None,
    timeout_ms: int = DEFAULT_PROBE_TIMEOUT_MS,
    runner: Optional[Runner] = None,
    record: Optional[ObservedHostVersions] = None,
    record_label: Optional[str] = None,
    record_error: Optional[str] = None,
) -> HostVersionReport:
    """逐个 Adapter 比对「声明版本」与「宿主实际版本」（活体形态）。

    manifests 是 agent_id -> 已加载的能力声明（未审核的声明不在这里：装配处已经拒绝它们）。
    enforcement_by_agent 由调用方从支持矩阵给出，用来判定 not_declared 是不是失败：
    能力上限是 full 的 Adapter 必须说得出来它的宿主版本从哪读。

    record / record_label / record_error：本机形态里**顺带**核对提交进仓库的观测记录
    （活体与记录不一致 = recording_stale，退出 1）。记录缺失 / 读不了**不改变**活体四状态语义，
    它只写进 notes 并指向 CI 形态（--record-check）；那条硬门禁才是"记录必须有数据"的地方。
    """

    override_map = dict(overrides or {})
    findings: list[HostVersionFinding] = []

    for agent_id in sorted(manifests):
        manifest = manifests[agent_id]
        enforcement = str(enforcement_by_agent.get(agent_id, "") or "").strip() or "unknown"
        digest = manifest_digest(manifest)
        probe = manifest.host_version
        if probe is None:
            findings.append(
                HostVersionFinding(
                    agent_id=agent_id,
                    declared_version=manifest.agent_version,
                    status=HostVersionStatus.NOT_DECLARED,
                    enforcement=enforcement,
                    detail="manifest 没有声明 host_version：没有可探测的宿主版本读法",
                    manifest_digest=digest,
                )
            )
            continue

        probe_text = reading_text(probe.executable, probe.args)
        outcome = probe_host_version(
            probe,
            executable_override=override_map.get(agent_id),
            timeout_ms=timeout_ms,
            runner=runner,
        )
        if not outcome.ok:
            findings.append(
                HostVersionFinding(
                    agent_id=agent_id,
                    declared_version=manifest.agent_version,
                    status=HostVersionStatus.UNAVAILABLE,
                    enforcement=enforcement,
                    probe=probe_text,
                    executable=probe.executable,
                    resolved_name=outcome.executable_name,
                    detail=outcome.detail,
                    manifest_digest=digest,
                )
            )
            continue

        observed = outcome.version
        recorded_at: Optional[str] = None
        recorded_digest: Optional[str] = None
        if observed != manifest.agent_version:
            status = HostVersionStatus.DRIFT
            detail = (
                f"声明 {manifest.agent_version} 不等于宿主 {observed}（探测 {probe_text}）"
            )
        else:
            entry = None if record is None else record.get(agent_id)
            stale = (
                None
                if record is None
                else _staleness_reason(
                    entry, digest=digest, probe=probe, live_version=str(observed)
                )
            )
            if stale is not None:
                status = HostVersionStatus.RECORDING_STALE
                detail = (
                    f"活体探测读到 {observed}，但记录过期：{stale}。"
                    "记录过期就不是「已核对」——重跑 python -m adapters.cli host-version --record"
                    " 并把 adapters/host-versions.observed.json 的 diff 送评审"
                )
                recorded_at = None if entry is None else entry.recorded_at
                recorded_digest = None if entry is None else entry.manifest_digest
            else:
                status = HostVersionStatus.MATCH
                detail = f"声明 {manifest.agent_version} = 宿主 {observed}（探测 {probe_text}）"
                if entry is not None:
                    detail += (
                        f"，且与观测记录一致（记录于 {entry.recorded_at}，"
                        f"记录里的 manifest 哈希 {entry.manifest_digest}）"
                    )
                    recorded_at = entry.recorded_at
                    recorded_digest = entry.manifest_digest
        findings.append(
            HostVersionFinding(
                agent_id=agent_id,
                declared_version=manifest.agent_version,
                status=status,
                enforcement=enforcement,
                observed_version=observed,
                probe=probe_text,
                executable=probe.executable,
                resolved_name=outcome.executable_name,
                detail=detail,
                recorded_at=recorded_at,
                recorded_digest=recorded_digest,
                manifest_digest=digest,
            )
        )

    failures: list[str] = []
    for finding in findings:
        if finding.status is HostVersionStatus.DRIFT:
            failures.append(
                f"{finding.agent_id}：声明 {finding.declared_version} 不等于宿主 "
                f"{finding.observed_version}（探测 {finding.probe}）。{FIX_HINT}"
            )
        elif finding.status is HostVersionStatus.RECORDING_STALE:
            failures.append(
                f"{finding.agent_id}：观测记录过期——{finding.detail}。{RECORD_FIX_HINT}"
            )
        elif finding.is_failure:
            failures.append(
                f"{finding.agent_id}：能力上限是 full，却没有声明 host_version——"
                "这条检查对它什么都查不到。请补上宿主版本的读法"
                "（executable / args / version_pattern），或如实把上限降为 read_only。"
            )

    unavailable = tuple(
        item.agent_id for item in findings if item.status is HostVersionStatus.UNAVAILABLE
    )
    compared_statuses = (
        HostVersionStatus.MATCH,
        HostVersionStatus.DRIFT,
        HostVersionStatus.RECORDING_STALE,
    )
    compared = tuple(
        item.agent_id for item in findings if item.status in compared_statuses
    )
    # RECORDING_STALE 也算「真的比对过」：活体探测成功、版本与声明一致，只是提交进仓库的
    # 观测记录过期了——它确实参与了与宿主的比对。此前把它排除在 covered 之外，于是一次全是
    # stale 的运行会同时打印「本次没有任何 Adapter 真正参与比对（covered 0/N）」与
    # 「观测记录…参与了比对」两句互相打脸的话，覆盖数也低估了实际比过的条数。
    covered = len(compared)
    if failures:
        result = "fail"
    elif unavailable:
        result = "unavailable"
    else:
        result = "pass"

    notes: list[str] = []
    if covered == 0:
        # 幸存者偏差要写在报告里：result=pass 而 covered=0 意味着这条检查什么都没覆盖。
        notes.append(
            f"本次没有任何 Adapter 真正参与比对（covered {covered}/{len(findings)}）："
            "这条检查什么都没有覆盖，请读 counts 而不是只看 result"
        )
    if unavailable and not failures:
        notes.append(
            "读不到宿主版本的通道不是通过：加 --require-runtime 可以让它退出 1"
            "（理由与复现命令都在 findings 里）"
        )
    if record is not None:
        if compared:
            notes.append(
                f"观测记录 {record_label}（记录于 {record.recorded_at}）参与了比对："
                "活体读数与记录逐条核对（不一致即 recording_stale）"
            )
        if unavailable:
            notes.append(
                "有 Adapter 读不到宿主：观测记录没有参与那几条的比对"
                "（记录只与活体读数比，读不到不等于记录过期）"
            )
    elif record_error is not None:
        notes.append(
            f"观测记录暂时不可用（{record_label}）：{record_error}；"
            "本次只做了活体比对。CI 形态（--record-check）会因此退出 1；"
            "修记录用 python -m adapters.cli host-version --record"
        )
    elif record_label is not None:
        notes.append(
            f"没有找到观测记录（{record_label}）：本次只做了活体比对；"
            "CI 形态（--record-check）会因记录缺失退出 1，"
            "生成记录用 python -m adapters.cli host-version --record"
        )
    if not notes:
        notes.append(
            f"实际比对 {covered}/{len(findings)} 个 Adapter；"
            "not_declared 的条目逐条列在 findings 里，不计入「已比对」"
        )

    return HostVersionReport(
        findings=tuple(findings),
        result=result,
        failures=tuple(failures),
        notes=tuple(notes),
        covered=covered,
        total=len(findings),
        mode="live",
        record_path=record_label,
        record_recorded_at=None if record is None else record.recorded_at,
    )


def check_recorded_versions(
    manifests: Mapping[str, AdapterManifest],
    *,
    enforcement_by_agent: Mapping[str, str],
    record: ObservedHostVersions,
    record_label: str,
) -> HostVersionReport:
    """CI 形态：不探测宿主，只比对「声明 vs 提交进仓库的观测记录」。

    逐条比对三件事，任一条不一致都退出 1（调用方按 result != "pass" 判定）：

    1. 声明的 agent_version 与记录里的 observed_version；
    2. 记录钉住的 manifest 哈希与当前声明的 manifest 哈希（声明改了没重录 = 记录过期）；
    3. 记录的探测读法与当前声明的读法（读法变了，记录描述的不是同一次观测）。

    另外两条"记录与注册表脱节"也算失败：声明了读法却没有条目的（记录不完整）、
    记录里有当前注册表没有的 Agent（记录没跟着改）。
    """

    findings: list[HostVersionFinding] = []
    entries = {entry.agent_id: entry for entry in record.entries}

    for agent_id in sorted(manifests):
        manifest = manifests[agent_id]
        enforcement = str(enforcement_by_agent.get(agent_id, "") or "").strip() or "unknown"
        digest = manifest_digest(manifest)
        probe = manifest.host_version
        entry = entries.get(agent_id)
        if probe is None:
            findings.append(
                HostVersionFinding(
                    agent_id=agent_id,
                    declared_version=manifest.agent_version,
                    status=HostVersionStatus.NOT_DECLARED,
                    enforcement=enforcement,
                    detail="manifest 没有声明 host_version：没有可探测的宿主版本读法",
                    source="record",
                    manifest_digest=digest,
                )
            )
            continue

        probe_text = reading_text(probe.executable, probe.args)
        if entry is None:
            findings.append(
                HostVersionFinding(
                    agent_id=agent_id,
                    declared_version=manifest.agent_version,
                    status=HostVersionStatus.RECORDING_STALE,
                    enforcement=enforcement,
                    probe=probe_text,
                    executable=probe.executable,
                    detail="记录里没有它的条目：记录不完整，这次没有任何实测值可核对",
                    source="record",
                    manifest_digest=digest,
                )
            )
            continue

        base = {
            "agent_id": agent_id,
            "declared_version": manifest.agent_version,
            "enforcement": enforcement,
            "observed_version": entry.observed_version,
            "probe": probe_text,
            "executable": probe.executable,
            "source": "record",
            "recorded_at": entry.recorded_at,
            "recorded_digest": entry.manifest_digest,
            "manifest_digest": digest,
        }
        if entry.manifest_digest != digest:
            findings.append(
                HostVersionFinding(
                    status=HostVersionStatus.RECORDING_STALE,
                    detail=(
                        f"记录钉住的 manifest 哈希 {entry.manifest_digest} 与当前声明 {digest}"
                        " 不一致：声明改过但没重录"
                    ),
                    **base,
                )
            )
            continue
        if entry.reading != (probe.executable, tuple(probe.args), probe.version_pattern):
            findings.append(
                HostVersionFinding(
                    status=HostVersionStatus.RECORDING_STALE,
                    # 记录文档按不可信加载：它里面的 executable / args / version_pattern
                    # 必须与活体探测那条路径同口径过 redact()，否则手改记录就能把绝对路径
                    # 带回报告（本模块的口径是报告里不出现机器布局）。
                    detail=(
                        "记录里的探测读法 "
                        + _describe_reading(entry.executable, entry.args, entry.version_pattern)
                        + " 与当前声明 "
                        + _describe_reading(probe.executable, probe.args, probe.version_pattern)
                        + " 不一致"
                    ),
                    **base,
                )
            )
            continue
        if entry.observed_version != manifest.agent_version:
            findings.append(
                HostVersionFinding(
                    status=HostVersionStatus.DRIFT,
                    detail=(
                        f"声明 {manifest.agent_version} 不等于记录里的实测值 "
                        f"{entry.observed_version}（记录于 {entry.recorded_at}，探测 {probe_text}）"
                    ),
                    **base,
                )
            )
            continue
        findings.append(
            HostVersionFinding(
                status=HostVersionStatus.MATCH,
                detail=(
                    f"声明 {manifest.agent_version} = 记录里的实测值 {entry.observed_version}"
                    f"（记录于 {entry.recorded_at}，探测 {probe_text}，"
                    f"记录钉住的 manifest 哈希 {entry.manifest_digest}）"
                ),
                **base,
            )
        )

    failures: list[str] = []
    for finding in findings:
        if finding.status is HostVersionStatus.DRIFT:
            seen = (
                f"{finding.observed_version}（记录于 {finding.recorded_at}，"
                f"探测 {finding.probe}）"
            )
            failures.append(
                f"{finding.agent_id}：声明 {finding.declared_version} 不等于记录里的实测值 "
                f"{seen}。{RECORD_DRIFT_FIX_HINT}"
            )
        elif finding.status is HostVersionStatus.RECORDING_STALE:
            failures.append(f"{finding.agent_id}：记录过期——{finding.detail}。{RECORD_FIX_HINT}")
        elif finding.is_failure:
            failures.append(
                f"{finding.agent_id}：能力上限是 full，却没有声明 host_version——"
                "这条检查对它什么都查不到。请补上宿主版本的读法"
                "（executable / args / version_pattern），或如实把上限降为 read_only。"
            )
    # 记录与注册表脱节：多出来的条目不是"无所谓"，它是"记录没跟着声明改"。
    for agent_id in sorted(entries):
        if agent_id not in manifests:
            failures.append(
                f"{agent_id}：记录里有它的条目，但当前注册表里没有这个 Agent——"
                f"记录与声明已经不同步。{RECORD_FIX_HINT}"
            )
        elif manifests[agent_id].host_version is None:
            failures.append(
                f"{agent_id}：记录里有它的条目，但当前声明没有 host_version 读法——"
                f"记录与声明已经不同步。{RECORD_FIX_HINT}"
            )

    covered = sum(
        1 for item in findings if item.status is HostVersionStatus.MATCH
    )
    if not failures and covered == 0:
        # 防御性的一条：条目非空却一个都没比对上，说明这条门禁什么都没覆盖（不许静默通过）。
        failures.append(
            "本次没有任何 Adapter 真正参与比对（记录里的条目一条都没用上）："
            "这条检查什么都没有覆盖。请核对记录与 adapters/*/manifest.yaml 是否一一对应"
        )
    result = "fail" if failures else "pass"

    notes: list[str] = []
    if not failures:
        notes.append(
            f"CI 形态：不探测宿主，逐条比对「声明 vs 观测记录」（记录 {record_label}，"
            f"记录于 {record.recorded_at}）；covered {covered}/{len(findings)}"
        )
        notes.append(
            "记录只能由 python -m adapters.cli host-version --record 写入；"
            "改了 adapters/<agent>/manifest.yaml 必须重跑它，否则这里会红在「记录过期」上"
        )
    return HostVersionReport(
        findings=tuple(findings),
        result=result,
        failures=tuple(failures),
        notes=tuple(notes),
        covered=covered,
        total=len(findings),
        mode="record",
        record_path=record_label,
        record_recorded_at=record.recorded_at,
    )
