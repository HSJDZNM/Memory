"""契约：能力声明的 agent_version 必须**可核对**，而「删掉核对」本身要过审核。

背景（本轮缺陷 2）：agent_version 的字段说明是「已实测的 Agent 产品版本」，
但在本轮之前没有任何地方把它与宿主实际版本比过——宿主升到 0.1.6-alpha.2 之后，
一致性套件、事件 fixture 重放与支持矩阵全部照常通过。

三条各自独立的事实（缺一条就退回"声明与事实无关"）：

1. 声明里的宿主版本读法必须**结构良好**，而且版本正则要认得真实的版本行；
2. 能力上限是 full 的 Adapter 必须声明读法——否则那条检查对它什么都查不到；
3. host_version 参与 manifest 哈希：删掉或改写它 = 与已审核哈希不一致 = 拒绝接入。

第 3 条是本文件的重点：它把「把检查绕空」这条路也变成一次必须过审的动作。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from adapters.base import AdapterRegistry, AdapterSpec, RegistryError, manifest_digest
from adapters.cli import build_parser, main, run_host_version
from adapters.host_version import HOST_VERSION_RECORD_SCHEMA_VERSION
from adapters.loader import load_registry_from_repo
from adapters.models import AdapterManifest, EnforcementLevel

from conftest import REPO_ROOT

pytestmark = pytest.mark.contract

ADAPTERS_ROOT = REPO_ROOT / "adapters"
APPROVED_PATH = ADAPTERS_ROOT / "approved.json"


def manifest_documents() -> dict[str, dict]:
    documents: dict[str, dict] = {}
    for path in sorted(ADAPTERS_ROOT.glob("*/manifest.yaml")):
        documents[path.parent.name] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return documents


def load_manifest(agent_id: str) -> AdapterManifest:
    """按仓库的真实磁盘文档加载一份 manifest（走 AdapterSpec，未知字段一律报错）。"""

    path = ADAPTERS_ROOT / agent_id / "manifest.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AdapterSpec.model_validate(document).to_manifest(path=path)


# --------------------------------------------------------------------------- 1. 读法本身


def test_every_declared_host_probe_is_structurally_sound():
    """声明了 host_version 的 Adapter：读法不许带路径、不许带 shell 组合、正则恰好一个捕获组。"""

    seen: list[str] = []
    for agent_id, document in manifest_documents().items():
        manifest = AdapterSpec.model_validate(document).to_manifest(
            path=ADAPTERS_ROOT / agent_id / "manifest.yaml"
        )
        probe = manifest.host_version
        if probe is None:
            continue
        seen.append(agent_id)
        assert probe.executable == probe.executable.strip()
        assert "/" not in probe.executable and "\\" not in probe.executable
        for argument in probe.args:
            assert argument.strip() == argument and argument
            for token in (";", "|", "&", ">", "<", "\n"):
                assert token not in argument, (agent_id, argument)
        compiled = re.compile(probe.version_pattern)
        assert compiled.groups == 1, agent_id
    # 对照测试必须非空转：至少有一个 Adapter 真的声明了读法（否则上面全是空循环）。
    assert seen, "没有任何 manifest 声明 host_version：这条契约什么都没覆盖"


def test_dsh_probe_parses_the_real_version_line_shapes():
    """dsh 的读法必须认得真实输出：升级前的 rc 号与升级后的 alpha 号都算合格样本。"""

    probe = load_manifest("dsh").host_version
    assert probe is not None
    assert probe.executable == "dsh"
    assert list(probe.args) == ["--version"]

    for line, expected in (
        ("0.1.5-rc.1\n", "0.1.5-rc.1"),
        ("0.1.6-alpha.2\n", "0.1.6-alpha.2"),
        ("v0.2.0\n", "0.2.0"),
    ):
        match = re.search(probe.version_pattern, line)
        assert match is not None, line
        assert match.group(1) == expected, line


# --------------------------------------------------------------------------- 2. 不许绕空


def test_full_enforcement_adapters_declare_a_host_version_probe():
    """能力上限是 full 却没有读法 = 那条检查对它静默失效（幸存者偏差）。"""

    registry = load_registry_from_repo(REPO_ROOT)
    rows = [
        row
        for row in registry.as_list().descriptors
        if row.enforcement is EnforcementLevel.FULL
    ]
    assert rows, "一个 full 的 Adapter 都没有：这条契约是空的"
    for row in rows:
        manifest = registry.manifest(row.agent_id)
        assert manifest.host_version is not None, (
            f"{row.agent_id} 的能力上限是 full，却没有声明 host_version："
            "python -m adapters.cli host-version --check 对它什么都查不到"
        )


def test_protocol_version_does_not_carry_the_host_version():
    """两条轴解耦：`protocol_version` 命名载荷方言，不是宿主产品版本（2026-10-10 裁定，README §14）。

    混轴的后果是写出一个**不存在的产品版本**：0.2.x 的安装里已经没有 `@deepseek-ai/dsh-hooks-*`
    包，把它写成 `dsh-hooks-claude-code@0.2.x` 比留着旧值更假。所以这条检查断言"声明的
    protocol_version 里不出现声明的 agent_version"——要打破它必须是一次显式裁定。
    """

    seen: list[str] = []
    for agent_id, document in manifest_documents().items():
        manifest = AdapterSpec.model_validate(document).to_manifest(
            path=ADAPTERS_ROOT / agent_id / "manifest.yaml"
        )
        seen.append(agent_id)
        assert manifest.agent_version not in manifest.protocol_version, (
            agent_id,
            manifest.agent_version,
            manifest.protocol_version,
        )
    # 对照：这条检查必须真的走过所有声明（空循环不算覆盖）。
    assert seen, "没有任何 manifest 被检查"


def test_the_drift_check_entry_point_exists():
    """检查入口是契约的一部分：CI 没有 dsh 也能证明这个入口在。"""

    args = build_parser().parse_args(["host-version", "--check", "--json"])
    assert args.func is run_host_version
    assert args.check is True
    assert args.require_runtime is False


# --------------------------------------------------------------------------- 3. 删掉要过审


def test_removing_the_probe_declaration_breaks_the_approved_hash():
    """删掉 host_version 块不是"悄悄少做一件事"：哈希一变，整次装配就拒绝。"""

    registry = AdapterRegistry.load(ADAPTERS_ROOT, approved_path=APPROVED_PATH)
    manifest = registry.manifest("dsh")
    approved = json.loads(APPROVED_PATH.read_text(encoding="utf-8"))
    assert manifest.host_version is not None

    stripped = AdapterManifest.model_validate(
        {**manifest.model_dump(mode="json"), "host_version": None}
    )

    assert manifest_digest(stripped) != manifest_digest(manifest)
    tampered = AdapterRegistry([stripped], approved=approved)
    with pytest.raises(RegistryError):
        tampered.check_approved()
    assert not tampered.as_list().get("dsh").approved


def test_approved_record_repeats_the_declared_version():
    """已审核清单里的 agent_version 必须跟着声明走（重新审核之后不许两边不同）。"""

    registry = AdapterRegistry.load(ADAPTERS_ROOT, approved_path=APPROVED_PATH)
    approved = json.loads(APPROVED_PATH.read_text(encoding="utf-8"))["adapters"]

    for agent_id in sorted(registry.manifests):
        assert approved[agent_id]["agent_version"] == registry.manifest(agent_id).agent_version


# --------------------------------------------------------------------------- 4. 观测记录（CI 形态）

# 修复轮 14 的尾巴（Q8）：--check 在**没装 dsh 的机器**上读不到宿主版本 → unavailable → 退出 0，
# 于是"声明与实测"这条检查在 CI 上谁都不会为它红。这里加的是一条**不依赖宿主**的比对：
# 仓库里提交一份观测记录（adapters/host-versions.observed.json，只能由 host-version --record
# 写入），CI 比对「声明 vs 记录」并且校验记录钉住的 manifest 哈希与当前声明一致。
#
# 由此产生一条新的维护纪律：**改了 adapters/<agent>/manifest.yaml 就必须重跑 --record**，
# 否则 CI 会红在"记录过期"上（这正是"改声明必须重新审核"的延伸，不是误报）。

RECORD_PATH = ADAPTERS_ROOT / "host-versions.observed.json"


def test_the_committed_record_makes_the_check_work_without_a_host(capsys):
    """CI 形态：不探测宿主，读仓库里的记录即可核对声明（这条就是 workflow 里那一步）。"""

    code = main(["--root", str(REPO_ROOT), "host-version", "--record-check", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0, payload
    assert payload["result"] == "pass"
    assert payload["mode"] == "record"
    assert payload["covered"] >= 1


def test_the_committed_record_pins_every_declared_probe():
    """记录必须逐条覆盖"声明了读法"的 Agent，并各自钉住当前的 manifest 哈希与读法。"""

    registry = load_registry_from_repo(REPO_ROOT)
    document = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    assert document["schema_version"] == HOST_VERSION_RECORD_SCHEMA_VERSION
    entries = {entry["agent_id"]: entry for entry in document["entries"]}
    assert len(entries) == len(document["entries"]), "记录里有重复的 agent_id"

    declared = [
        row.agent_id
        for row in registry.as_list().descriptors
        if registry.manifest(row.agent_id).host_version is not None
    ]
    assert declared, "没有任何 manifest 声明 host_version：这份记录什么都没覆盖"
    assert sorted(entries) == sorted(declared)

    for agent_id in declared:
        manifest = registry.manifest(agent_id)
        probe = manifest.host_version
        entry = entries[agent_id]
        assert entry["manifest_digest"] == manifest_digest(manifest), agent_id
        assert entry["observed_version"] == manifest.agent_version, agent_id
        assert entry["executable"] == probe.executable, agent_id
        assert list(entry["args"]) == list(probe.args), agent_id
        assert entry["version_pattern"] == probe.version_pattern, agent_id
