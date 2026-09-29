"""台阶 2 集成读数：归因闭集与核验前置走**生产入口**（Hook CLI）与受控 Hook 装配。

它只回答一件事：失败理由现在带没带**可核验的结构化归因**，以及那条归因会不会越权去改判定。
四类读数各自要能失败：

1. 配置读不到 → ORIGIN 行的 origin 是 \`platform.config_unreadable\`，且核验真的读过磁盘；
2. 配置**好好的** → 核验证伪自己人，落 \`unknown_origin\`（这条是 R-g 的正面控制）；
3. 判定记录里带 \`origin\` 时，它只在**失败**记录里出现（放行的记录不许被编造归因）；
4. 归因不改判定：同一个失败码、同一个退出码 2。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from adapters.dsh.hooks import (
    EXIT_BLOCK,
    ORIGIN_PREFIX,
    DshPreExecuteHook,
    run_hook,
)
from conftest import POLICIES_DIR, REPO_ROOT, dsh_event, write_dsh_config
from adapters.dsh.adapter import DshEventError
from policy.loader import load_rule_set
from provenance.origin import (
    OBJECT_KINDS,
    OBSERVATION_METHODS,
    ORIGIN_OBJECT_KIND,
    ORIGIN_VALUES,
    is_known_origin,
    payload_is_well_formed,
)
from provenance.origin_runtime import origin_from_failure

pytestmark = pytest.mark.integration

# 绝对路径的"缺席断言"用**具体串**而不是宽泛正则：正则的边界一放宽就会把仓库相对路径
# （src/shop/order_service.py）判成绝对路径，那是本仓库反复踩过的"仪器假阳"。
# 这里断言的是"这条路径的两种写法都不在文本里"——含空格那一族（C:\Program Files\...）
# 因此不需要正则就能被钉住。
def leaked_paths(text: str, *absolute: Path | str) -> list[str]:
    """文本里还活着的绝对路径（原样与正斜杠两种写法）。空表 = 脱敏成立。"""

    found: list[str] = []
    for item in absolute:
        raw = str(item)
        if not raw:
            continue
        for variant in (raw, raw.replace("\\", "/")):
            if variant in text:
                found.append(variant)
    return found


def origin_lines(stderr: str) -> list[dict]:
    """把 stderr 里的 ORIGIN 行读成载荷（读不到就返回空表：这不是失败，是"没有归因"）。"""

    found: list[dict] = []
    for line in stderr.splitlines():
        if not line.startswith(ORIGIN_PREFIX):
            continue
        payload = json.loads(line[len(ORIGIN_PREFIX):])
        assert isinstance(payload, dict)
        found.append(payload)
    return found


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """生产入口：与真实 Hook 同一条命令行（\`python -m adapters.dsh.hooks\`）。"""

    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "adapters.dsh.hooks", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=json.dumps(dsh_event("pre-tool-use-edit-allow.json", cwd=str(cwd))),
        check=False,
    )


def test_a_config_that_is_really_missing_is_named_as_missing(tmp_root: Path):
    """配置族的第一种：路径不存在。核验前置给出 \`stat\` 观测，归因因此是 proven。"""

    missing = tmp_root / "config" / "dsh-adapter.yaml"
    completed = run_cli("--config", str(missing), cwd=tmp_root)
    assert completed.returncode == EXIT_BLOCK
    # 判定没变：仍然是 BLOCKED (startup_error)
    assert "BLOCKED (startup_error)" in completed.stderr

    payloads = origin_lines(completed.stderr)
    assert len(payloads) == 1, completed.stderr
    payload = payloads[0]
    assert payload_is_well_formed(payload), payload
    assert payload["origin"] == "platform.config_unreadable"
    assert payload["causal_link"] == "proven"
    assert payload["observation"]["verified"] is True
    assert payload["observation"]["method"] == "stat"
    assert payload["object"]["kind"] == "file"
    assert payload["object"]["value"] == "dsh-adapter.yaml"
    assert payload["fix"]
    # 核验是真的做过：理由里说出了"不存在"这个观测，而不是照抄错误原文
    assert "ENOENT" in payload["observation"]["result"]


def test_origin_payload_never_carries_an_absolute_path(tmp_root: Path):
    """台阶 3a：ORIGIN 行是**诊断**，但诊断里也不许留绝对路径（AGENTS 第 16 条）。

    为什么要专门钉这一条：本例的 `--config` 就是一个**绝对**路径，而它会被原样拼进
    `object.source`（`hooks.main` 的兜底分支）与 `observation.result`（失败原文）。
    改动前实测 stderr 里能读回本机绝对路径——这条用例在改动前**会红**，是本台阶的判据。
    """

    missing = tmp_root / "config" / "dsh-adapter.yaml"
    completed = run_cli("--config", str(missing), cwd=tmp_root)
    assert completed.returncode == EXIT_BLOCK

    payloads = origin_lines(completed.stderr)
    assert len(payloads) == 1, completed.stderr
    payload = payloads[0]
    # 形状与取值闭集不受脱敏影响：脱敏只动字符串，不动键与枚举。
    assert payload_is_well_formed(payload), payload
    assert payload["origin"] == "platform.config_unreadable"
    assert payload["observation"]["method"] == "stat"

    # 绝对路径的两种写法都不许在载荷里存活（Windows 反斜杠 / 正斜杠）。
    dumped = json.dumps(payload, ensure_ascii=False)
    assert not leaked_paths(dumped, tmp_root), dumped
    # 连"半截路径"也不许留：`<abs> Files\...` 这种形态正是本台阶修掉的缺陷——
    # 于是这里断言的正是**前缀之后那一截**还在不在。
    assert not leaked_paths(completed.stderr, str(tmp_root / "config")), completed.stderr
    # 脱敏不是"把整条诊断抹空"：对象末段名与观测方法仍然读得到。
    assert payload["object"]["value"] == "dsh-adapter.yaml"
    assert payload["fix"]


def test_a_config_that_loads_but_says_wrong_things_falsifies_the_claim(tmp_root: Path):
    """配置族的第二种：文件在、读得到，但内容让加载失败。

    这时"配置读不到"这条指控被**证伪**——按 §3.4 只能落 \`unknown_origin\`，
    绝不许把对象换成"配置里的某个字段"继续指控。
    """

    project = tmp_root / "demo-shop"
    (project / "src" / "shop").mkdir(parents=True, exist_ok=True)
    config = write_dsh_config(
        tmp_root / "config" / "dsh-adapter.yaml",
        project_root=project,
        rules=POLICIES_DIR,
        timeout_ms=-5,  # 合法 YAML、非法取值：加载期报错
    )
    completed = run_cli("--config", str(config), cwd=tmp_root)
    assert completed.returncode == EXIT_BLOCK
    assert "BLOCKED (startup_error)" in completed.stderr

    payloads = origin_lines(completed.stderr)
    assert len(payloads) == 1, completed.stderr
    payload = payloads[0]
    assert payload_is_well_formed(payload), payload
    # 这条理由（"值不对"）**没有**指名任何可核验的输入：原文里没有文件路径，--config 也
    # 不能拿来顶替（那份配置真的读得到）。所以结论只能是 unknown_origin——核验没有对象，
    # 归因就没有建立起来；**不许**拿"配置里的某个字段"当替身继续指控。
    assert payload["origin"] == "unknown_origin"
    assert payload["causal_link"] == "unproven"
    assert payload["observation"]["verified"] is False
    assert payload["observation"]["method"] == "none"
    assert "没有对象" in payload["observation"]["result"]

    # 同一棵树上的正面控制：把"配置自身读不到"那种理由交给同一条链路时，核验会真的执行，
    # 并且**证伪自己人**（文件在、读得到 → 落 unknown_origin 且写明"证伪"）。
    readable = origin_from_failure(
        reason_code="startup_error",
        detail="配置读不到",
        config_path=config,
        config_source="--config",
    )
    assert readable.origin == "unknown_origin"
    assert readable.causal_link == "unproven"
    assert readable.verified is False
    assert "证伪" in readable.result
    assert readable.object_value == "dsh-adapter.yaml"


def test_the_hook_record_carries_the_origin_only_when_it_fails(tmp_root: Path):
    """判定侧：失败记录带 \`origin\`（结构化）、放行记录不带（不许编造归因）。"""

    project = tmp_root / "demo-shop"
    (project / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (project / "docs").mkdir(parents=True, exist_ok=True)
    config = write_dsh_config(
        tmp_root / "config" / "good.yaml",
        project_root=project,
        rules=POLICIES_DIR,
    )
    audit = tmp_root / "audit.jsonl"

    # 放行：审计里不许出现 origin
    allowed = run_hook(
        dsh_event("pre-tool-use-edit-allow.json", cwd=str(project)),
        config_path=config,
        audit_path=audit,
    )
    assert allowed.exit_code == 0, allowed.stderr
    assert allowed.origin is None
    records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines() if line]
    assert records and all("origin" not in record for record in records), records

    # 失败（配置族）：库内调用**保持原有形状**——异常照旧抛出（生产入口 main() 把它
    # 翻成 startup_error），归因由同一个 origin_from_failure 算。这里断言两件事：
    # 判定语义没被这次改动碰过（异常类型不变），以及归因指着被点名的配置。
    gone = tmp_root / "config" / "gone.yaml"
    with pytest.raises(DshEventError) as failure:
        run_hook(
            dsh_event("pre-tool-use-edit-allow.json", cwd=str(project)),
            config_path=gone,
            audit_path=tmp_root / "audit-fail.jsonl",
        )
    assert "adapter 配置不存在" in str(failure.value)

    payload = origin_from_failure(
        reason_code="startup_error", detail=str(failure.value), config_path=gone
    ).to_payload()
    assert payload_is_well_formed(payload)
    assert payload["origin"] == "platform.config_unreadable"
    assert is_known_origin(payload["origin"])


def test_the_attribution_does_not_change_the_verdict(tmp_root: Path):
    """红线 R-b 的对照：归因是**诊断**，同一个失败码 + 同一个退出码 2 一个都不许变。

    做法是拿同一个输入跑两次，把 ORIGIN 行剥掉之后逐字节比较——归因只许"多一行"。
    """

    missing = tmp_root / "config" / "dsh-adapter.yaml"
    completed = run_cli("--config", str(missing), cwd=tmp_root)
    stripped = "\n".join(
        line for line in completed.stderr.splitlines() if not line.startswith(ORIGIN_PREFIX)
    )
    assert ORIGIN_PREFIX not in stripped
    assert "BLOCKED (startup_error)" in stripped
    assert VERDICT_LINE_IN(stripped), stripped


def VERDICT_LINE_IN(text: str) -> bool:  # noqa: N802 - 作为断言助手读起来更像一句话
    """判定行还在不在（\`[policy] VERDICT {...}\`）——归因多加一行不许把它挤掉。"""

    return any(line.startswith("[policy] VERDICT ") for line in text.splitlines())


# --------------------------------------------------------------- 跨语言契约（形状与闭集）


PLUGIN = REPO_ROOT / "src" / "adapters" / "dsh" / "policy-hook.plugin.mjs"


def _js_array(source: str, name: str) -> list[str]:
    """取 JS 里 `const NAME = [...]` 的字符串字面量（只解析这一种形状，解析不到就报错）。"""

    match = re.search(
        r"const " + name + r" = \[(?P<body>[^\]]*)\]", source, re.S
    )
    assert match is not None, f"插件里找不到 {name} 的数组字面量（契约已漂移）"
    return re.findall(r"'([^']+)'", match.group("body"))


def test_the_js_plugin_implements_the_same_closed_sets_as_the_python_side():
    """跨语言契约：两侧把自己那份闭集**写死在源码里**，所以最容易漂移。

    这条用例把 JS 的字面量与 Python 的常量逐项比对——一侧加了取值、另一侧没加，就红。
    它不做"读 JS 运行时"那种重活（那是 `tests/contract/test_policy_hook_chain.py` 的假 ctx
    探针）：这里问的是**声明**是否一致。
    """

    source = PLUGIN.read_text(encoding="utf-8")
    js_values = _js_array(source, "ORIGIN_VALUES")
    # 插件只实现 spawn 输入族那一半（配置族的核验在 Python 侧做），因此它是**子集**：
    # 每个 JS 取值都必须在 Python 的闭集里，而 Python 允许多出配置族的那几个。
    assert js_values, "插件里 ORIGIN_VALUES 是空的"
    for value in js_values:
        assert is_known_origin(value), f"插件用了一个 Python 侧不认识的 origin：{value}"
        assert value in ORIGIN_VALUES, value
    assert {
        "project.workdir_missing",
        "host.workdir_unreadable",
        "agent_runtime.spawn_denied",
        "agent_runtime.spawn_failed",
        "unknown_origin",
    } <= set(js_values)
    # 这两组是"完全相等的闭集"：任何一侧加一个观测方式 / 对象类别，另一侧必须同时加
    assert _js_array(source, "OBSERVATION_METHODS") == list(OBSERVATION_METHODS)
    assert _js_array(source, "OBJECT_KINDS") == list(OBJECT_KINDS)
    assert f"const ORIGIN_OBJECT_KIND = '{ORIGIN_OBJECT_KIND}'" in source
    # 注意：插件**不读** Python 写的那行 `[policy] ORIGIN`——它自己算 spawn 族的归因。
    # 两侧因此没有"共用一行文本"的耦合（也**不许**加）：插件对 Hook 失败的解释一字不改，
    # Python 的 ORIGIN 行只是审计与诊断。这条注释留在用例里，免得下一轮有人误加断言。


def test_a_payload_from_the_plugin_shape_is_well_formed_on_the_python_side():
    """把插件的六个拒绝场景**按它的形状**搬到 Python 侧，逐条过 `payload_is_well_formed`。

    这补上了 JS 执行者的一个明确缺口（他当时没有把这条判据写进自己的用例：不想让
    他的文件依赖未提交的 provenance 模块）。读数是形状判据，不是"插件真的产出了它"——
    后者由 `test_policy_hook_chain.py` 的真 node 探针负责；两条合起来才完整。
    """

    cases = [
        ("project.workdir_missing", "workdir", "stat", True, "proven", "missing-workdir"),
        ("project.workdir_missing", "workdir", "stat", True, "proven", "not-a-dir.txt"),
        ("project.workdir_missing", "workdir", "stat", True, "proven", "vanishing-workdir"),
        ("agent_runtime.spawn_failed", "command", "spawn", True, "proven", "python -m adapters.dsh.hooks"),
        ("agent_runtime.spawn_denied", "command", "spawn", True, "proven", "python -m adapters.dsh.hooks"),
        ("unknown_origin", "unknown", "none", False, "unproven", "unverified"),
    ]
    for origin_value, object_kind, method, verified, causal, value in cases:
        payload = {
            "kind": ORIGIN_OBJECT_KIND,
            "origin": origin_value,
            "owner": "platform.attribution",
            "object": {"kind": object_kind, "value": value, "source": "config.projectDir"},
            "observation": {
                "method": method,
                "result": "spawn 报错原文：spawn <node> ENOENT",
                "verified": verified,
                "verified_at": "2026-09-29T00:00:00Z",
                "run_scoped": True,
            },
            "fix": "创建它，或把 config.projectDir 指向真实存在的目录",
            "causal_link": causal,
        }
        assert payload_is_well_formed(payload), (origin_value, payload)
