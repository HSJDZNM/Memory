"""声明版本 vs 宿主实际版本：把「静默漂移」变成一条能失败的检查。

修复对象（本轮缺陷 2）：adapters/<agent>/manifest.yaml 的 agent_version 字段说明写着
「**已实测**的 Agent 产品版本」，但在本轮修复之前，全仓库没有任何地方把这份声明与
**宿主实际版本**比对过。宿主升到 0.1.6-alpha.2 之后，声明仍然写着 0.1.5-rc.1，
而一致性套件、事件 fixture 重放与支持矩阵**全部照常通过**——声明与事实不一致，
所有绿灯都不受影响。这是一条静默漂移。

本模块只回答一个问题：**声明里那个版本，和这台机器上真正装着的版本，是不是同一个？**

三条设计约束（每条都对应一个测试）：

1. **它不是拦截判定**（AGENTS.md 第 24 / 29 条管的是能力上限，不是版本号）：
   版本不一致不改变任何 allow / block，只让这条**显式调用**的检查退出 1。
   把版本号变成放行条件会把「宿主升级」直接封成「平台不可用」——那是把正常工作封死；
2. **四种状态互不折叠**：match / drift / not_declared / unavailable。
   「这台机器上读不到宿主版本」与「读到且一致」是两件事（与 wiring.py 的接线 / 留痕
   两根事实轴同一条思路）：读不到一律是 unavailable，绝不折叠成通过；
3. **不是「跑不了就算过」**：--check 只对 drift 退出 1，--require-runtime 才把
   「这台机器上根本读不到」也算失败——与 tools/dsh_sandbox_loop.py 的 --require-dsh
   同一套口径：环境跳过必须能被**显式要求**成红灯，但它默认不是红灯，
   否则在没有 dsh 的机器上这条检查会永远红，红着红着就被忽略了。

报告里不出现绝对路径（AGENTS.md 第 19 条同一口径）：只给声明里的裸命令名与解析后的
**文件名**；CLI 的 --probe-binary 覆盖值同样只以文件名出现。

这条检查**不覆盖**什么（必须写下来，见 .tmp/round-10/b/REPORT.md）：
它读的是**宿主二进制自报的版本**，不是"这个二进制真的在治理这条链路"。接线事实由
adapters.cli wiring 负责；能力上限由 manifest + 已审核哈希负责。三件事互不代替。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Tuple

from .models import AdapterManifest, EnforcementLevel, HostVersionProbe

__all__ = [
    "DEFAULT_PROBE_TIMEOUT_MS",
    "FIX_HINT",
    "HOST_VERSION_SCHEMA_VERSION",
    "READING_GUIDE",
    "HostVersionError",
    "HostVersionFinding",
    "HostVersionReport",
    "HostVersionStatus",
    "ProbeOutcome",
    "check_declared_versions",
    "probe_host_version",
]

HOST_VERSION_SCHEMA_VERSION = "1.0"
DEFAULT_PROBE_TIMEOUT_MS = 10_000

READING_GUIDE = (
    "agent_version 是「已实测的产品版本」：它必须等于这台机器上真正装着的宿主版本。"
    "match = 声明与宿主一致；drift = 不一致（宿主升级后没重跑 fixture / 声明写错了）；"
    "not_declared = 没有声明 host_version（没有宿主二进制的合成协议消费者；能力上限是 full 的"
    "Adapter 声明不出来就是失败）；unavailable = 声明了但这次读不到（二进制不在 / 非零退出 /"
    "输出解析不出 / 超时）——它既不是通过也不是失败，要显式加 --require-runtime 才会变红。"
)

# 漂移的修复动作必须写进拒绝理由（AGENTS.md 第 50 条：拒绝理由要给出「改成什么形态就能过」）。
FIX_HINT = (
    "升级宿主后必须：重跑 python -m adapters.cli check 与 python -m adapters.cli events"
    "（以及真实会话闭环），把 adapters/<agent>/manifest.yaml 的 agent_version 改成实测值，"
    "再跑 python -m adapters.cli approve --reviewer <name> 重新审核"
)

# 报告里不出现绝对路径：先按"像路径"的形态替换掉，再截断。
_WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/][^\s\"'|;]+")
_POSIX_PATH = re.compile(r"(?<![\w.])/(?:[^\s\"'|;/]+/)*[^\s\"'|;/]+")

Runner = Callable[..., Any]


class HostVersionError(ValueError):
    """探测用法本身不合法（CLI 参数错误等）。"""


class HostVersionStatus(str, Enum):
    """一次比对可能落在的四种状态。四种互不折叠，各自可读。"""

    MATCH = "match"
    DRIFT = "drift"
    NOT_DECLARED = "not_declared"
    UNAVAILABLE = "unavailable"


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

    @property
    def is_failure(self) -> bool:
        """drift 一律是失败；能力上限 full 却声明不出探测，也是失败（否则检查被绕空）。"""

        if self.status is HostVersionStatus.DRIFT:
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
            "observed_version": self.observed_version,
            "probe": self.probe,
            "executable": self.executable,
            "resolved_name": self.resolved_name,
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

    def to_dict(self) -> dict[str, Any]:
        counts = {item.value: 0 for item in HostVersionStatus}
        for finding in self.findings:
            counts[finding.status.value] += 1
        return {
            "schema_version": HOST_VERSION_SCHEMA_VERSION,
            "reading_guide": READING_GUIDE,
            "result": self.result,
            "covered": self.covered,
            "total": self.total,
            "counts": counts,
            "findings": [item.to_dict() for item in self.findings],
            "failures": list(self.failures),
            "notes": list(self.notes),
        }


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
    version = match.group(1).strip()
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


def check_declared_versions(
    manifests: Mapping[str, AdapterManifest],
    *,
    enforcement_by_agent: Mapping[str, str],
    overrides: Optional[Mapping[str, Path | str]] = None,
    timeout_ms: int = DEFAULT_PROBE_TIMEOUT_MS,
    runner: Optional[Runner] = None,
) -> HostVersionReport:
    """逐个 Adapter 比对「声明版本」与「宿主实际版本」。

    manifests 是 agent_id -> 已加载的能力声明（未审核的声明不在这里：装配处已经拒绝它们）。
    enforcement_by_agent 由调用方从支持矩阵给出，用来判定 not_declared 是不是失败：
    能力上限是 full 的 Adapter 必须说得出来它的宿主版本从哪读。
    """

    override_map = dict(overrides or {})
    findings: list[HostVersionFinding] = []

    for agent_id in sorted(manifests):
        manifest = manifests[agent_id]
        enforcement = str(enforcement_by_agent.get(agent_id, "") or "").strip() or "unknown"
        probe = manifest.host_version
        if probe is None:
            findings.append(
                HostVersionFinding(
                    agent_id=agent_id,
                    declared_version=manifest.agent_version,
                    status=HostVersionStatus.NOT_DECLARED,
                    enforcement=enforcement,
                    detail="manifest 没有声明 host_version：没有可探测的宿主版本读法",
                )
            )
            continue

        probe_text = " ".join((probe.executable, *probe.args)).strip()
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
                )
            )
            continue

        observed = outcome.version
        status = (
            HostVersionStatus.MATCH
            if observed == manifest.agent_version
            else HostVersionStatus.DRIFT
        )
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
                detail=(
                    f"声明 {manifest.agent_version} = 宿主 {observed}（探测 {probe_text}）"
                    if status is HostVersionStatus.MATCH
                    else f"声明 {manifest.agent_version} 不等于宿主 {observed}（探测 {probe_text}）"
                ),
            )
        )

    failures: list[str] = []
    for finding in findings:
        if finding.status is HostVersionStatus.DRIFT:
            failures.append(
                f"{finding.agent_id}：声明 {finding.declared_version} 不等于宿主 "
                f"{finding.observed_version}（探测 {finding.probe}）。{FIX_HINT}"
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
    covered = sum(
        1
        for item in findings
        if item.status in (HostVersionStatus.MATCH, HostVersionStatus.DRIFT)
    )
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
    )
