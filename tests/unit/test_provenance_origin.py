"""归因闭集与核验前置（方案 §3.4 / §4 台阶 2 · 判据 R-g）。

两条检查分别问两个问题，缺一条这条机制就只剩一半：

- **形状**：origin 是闭集吗？写不出 fix 的 origin 真的会被拒吗？（`test_*` 前半）
- **会失败**：核验真的会**证伪自己人**吗？——报「配置读不到」而配置其实好好的时候，
  结论必须落 `unknown_origin`，**不许**把对象换成"配置里的某个字段"继续指控。
  （`test_verification_falsifies_itself_*`）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from provenance.origin import (
    CAUSAL_LINKS,
    OBJECT_KINDS,
    OBSERVATION_METHODS,
    ORIGIN_FAMILIES,
    ORIGIN_OBJECT_KIND,
    ORIGIN_VALUES,
    Origin,
    OriginError,
    build_origin,
    config_path_in,
    family_of,
    is_known_origin,
    payload_is_well_formed,
    unknown_origin,
)
from provenance.origin_runtime import (
    ORIGIN_BY_REASON_CODE,
    origin_from_failure,
    verification_of_config,
)


def _good(**overrides: object) -> Origin:
    """一条形状完备的归因（每个用例只改自己要测的那一项）。"""

    values: dict = {
        "origin": "project.workdir_missing",
        "owner": "platform.attribution",
        "object_kind": "workdir",
        "object_value": "C:/probe/missing",
        "object_source": "config.projectDir",
        "method": "stat",
        "result": "stat 观测：该路径不存在（ENOENT）",
        "verified": True,
        "fix": "创建它，或把 config.projectDir 指向真实存在的目录",
        "causal_link": "proven",
    }
    values.update(overrides)
    return build_origin(**values)


# --------------------------------------------------------------------- 形状（闭集）


def test_the_closure_is_exactly_five_families():
    assert ORIGIN_FAMILIES == ("platform", "agent_runtime", "host", "project", "unknown_origin")
    assert family_of("unknown_origin") == "unknown_origin"
    assert family_of("platform.config_unreadable") == "platform"
    for value in ORIGIN_VALUES:
        assert family_of(value) in ORIGIN_FAMILIES, value


def test_an_unknown_origin_value_is_rejected_not_defaulted():
    """未知取值一律报错：不许悄悄落成 unknown_origin —— 那是"静默放宽"的另一种写法。"""

    with pytest.raises(OriginError):
        _good(origin="platform.someone_invented_this")
    with pytest.raises(OriginError):
        _good(origin="kernel")
    assert is_known_origin("unknown_origin") is True
    assert is_known_origin("platform.config_unreadable") is True
    assert is_known_origin("platform.invented") is False
    assert is_known_origin(None) is False
    assert is_known_origin(7) is False


def test_every_closed_field_rejects_an_unknown_value():
    for field, bad in (
        ("object_kind", "folder"),
        ("method", "guess"),
        ("causal_link", "maybe"),
    ):
        with pytest.raises(OriginError):
            _good(**{field: bad})
    assert set(OBSERVATION_METHODS) == {"stat", "load", "spawn", "read", "none"}
    assert set(CAUSAL_LINKS) == {"proven", "unproven"}
    assert "workdir" in OBJECT_KINDS and "command" in OBJECT_KINDS


def test_an_origin_without_a_fix_cannot_exist():
    """方案 §3.4 的原话：**写不出 fix 的 origin 不许存在**。空串、空白、None 都算写不出。"""

    for empty in ("", "   ", chr(10)):
        with pytest.raises(OriginError):
            _good(fix=empty)
    with pytest.raises(OriginError):
        _good(fix=None)


def test_the_required_fields_must_be_non_empty():
    for field in ("owner", "object_value", "object_source", "result"):
        with pytest.raises(OriginError):
            _good(**{field: ""})
    for field in ("verified", "run_scoped"):
        with pytest.raises(OriginError):
            _good(**{field: "true"})


def test_the_payload_is_exactly_the_contract_shape():
    payload = _good().to_payload()
    assert payload_is_well_formed(payload)
    assert payload["kind"] == ORIGIN_OBJECT_KIND
    assert set(payload) == {
        "kind", "origin", "owner", "object", "observation", "fix", "causal_link",
    }
    assert set(payload["object"]) == {"kind", "value", "source"}
    assert set(payload["observation"]) == {
        "method", "result", "verified", "verified_at", "run_scoped",
    }
    # verified_at 必须来自真实调用：形如 2026-09-29T…Z，而不是空串
    assert payload["observation"]["verified_at"].endswith("Z")
    # JSON 可序列化 + 中文不转义（审计里读得出来）
    assert "\\u" not in json.dumps(payload, ensure_ascii=False)

    # "恰好"是故意严的：多一个键、少一个键、嵌套少一个键都算违约
    extra = dict(payload)
    extra["severity"] = "warning"
    assert payload_is_well_formed(extra) is False
    missing = {key: value for key, value in payload.items() if key != "fix"}
    assert payload_is_well_formed(missing) is False
    broken_object = dict(payload)
    broken_object["object"] = {"kind": "path", "value": "x"}
    assert payload_is_well_formed(broken_object) is False
    broken_verified = json.loads(json.dumps(payload))
    broken_verified["observation"]["verified"] = "yes"
    assert payload_is_well_formed(broken_verified) is False


def test_the_cross_language_validator_matches_the_python_hard_rules():
    """形状对不等于值合法：payload_is_well_formed 必须与 Origin 的硬规则同口径（复核发现）。

    否则一份 owner="" / object.value=null / observation.result=null 的 JS 载荷能过校验，
    却在 Python 侧重建成 Origin 时才炸——那正是这个跨语言校验器要拦下的东西。
    """

    payload = _good().to_payload()
    assert payload_is_well_formed(payload)

    def mutations():
        yield lambda item: item.update({"owner": ""})
        yield lambda item: item.update({"owner": None})
        yield lambda item: item["object"].update({"value": None})
        yield lambda item: item["object"].update({"value": ""})
        yield lambda item: item["object"].update({"source": None})
        yield lambda item: item["observation"].update({"result": None})
        yield lambda item: item["observation"].update({"result": ""})
        yield lambda item: item["observation"].update({"verified_at": ""})
        yield lambda item: item["observation"].update({"verified_at": None})
        yield lambda item: item["observation"].update({"verified_at": 7})

    for mutate in mutations():
        candidate = json.loads(json.dumps(payload))
        mutate(candidate)
        assert payload_is_well_formed(candidate) is False, candidate

    # 与构造器同口径：这些取值连 Origin 都构造不出来（同一个判据的两侧）。
    for field, value in (("owner", ""), ("object_value", None), ("result", "")):
        with pytest.raises(OriginError):
            _good(**{field: value})


def test_unknown_origin_cannot_claim_a_proven_causal_link():
    """unknown_origin 是"归因没有建立起来"：verified / causal_link 不许自相矛盾（复核发现）。

    只有 unknown_origin() 助手按这条纪律写；直接构造（或未来某个调用方）能绕过它，
    而这样一条记录在审计里会被读成"已证明的另一侧"。
    """

    with pytest.raises(OriginError):
        _good(origin="unknown_origin")  # causal_link 仍是 proven
    with pytest.raises(OriginError):
        _good(origin="unknown_origin", causal_link="unproven")  # verified 仍是 True
    with pytest.raises(OriginError):
        _good(origin="unknown_origin", causal_link="proven", verified=False)

    consistent = _good(origin="unknown_origin", causal_link="unproven", verified=False)
    assert consistent.origin == "unknown_origin"
    assert payload_is_well_formed(consistent.to_payload())


def test_unknown_origin_is_the_only_landing_place_when_verification_fails():
    origin = unknown_origin(reason="核验判据不成立：没有指名任何输入")
    assert origin.origin == "unknown_origin"
    assert origin.verified is False
    assert origin.causal_link == "unproven"
    # 它不是"没有归因"：它必须说得出下一步做什么才算核验过
    assert "重新归因" in origin.fix
    assert payload_is_well_formed(origin.to_payload())


def test_config_path_is_recovered_from_the_failure_text_or_not_at_all():
    assert config_path_in("adapter 配置不存在: dsh-adapter.yaml") == "dsh-adapter.yaml"
    assert config_path_in("hooks.json 不可解析（JSONDecodeError）") == "hooks.json"
    assert (
        config_path_in("pre_evidence.registry_root 下找不到平台验证器数据（validation/validators.yaml）")
        == "validation/validators.yaml"
    )
    # 取不到就取不到：不许凭空拼一个路径出来指控别的对象
    assert config_path_in("某处出错了，但没点名任何文件") is None
    assert config_path_in("") is None


# --------------------------------------------------------------------- 核验前置（运行期）


def test_verification_proves_the_claim_when_the_config_is_really_missing(tmp_root: Path):
    origin = verification_of_config(tmp_root / "nope" / "dsh-adapter.yaml", source="--config")
    assert origin.origin == "platform.config_unreadable"
    assert origin.method == "stat"
    assert origin.verified is True
    assert origin.causal_link == "proven"
    assert origin.object_kind == "file"
    assert origin.object_value == "dsh-adapter.yaml"
    assert origin.fix


def test_verification_names_the_shape_when_the_config_is_a_directory(tmp_root: Path):
    directory = tmp_root / "adapter-config-dir"
    directory.mkdir(parents=True, exist_ok=True)
    origin = verification_of_config(directory, source="--config")
    assert origin.origin == "platform.config_unreadable"
    assert origin.object_kind == "path"
    assert "目录" in origin.result
    assert origin.causal_link == "proven"


def test_verification_falsifies_itself_when_the_config_is_fine(tmp_root: Path):
    """R-g 的正面控制：配置好好的时候，「配置读不到」这条指控**必须被证伪**。

    证伪的落点是 `unknown_origin`，而且对象**不许**被换成旁的东西：
    object.value 仍然是那份被点名的配置，"换一个对象继续指控"在这里就会红。
    """

    config = tmp_root / "dsh-adapter.yaml"
    config.write_text("agent_version: '1.0'" + chr(10), encoding="utf-8", newline="")
    origin = verification_of_config(config, source="--config")
    assert origin.origin == "unknown_origin"
    assert origin.verified is False
    assert origin.causal_link == "unproven"
    assert origin.object_value == "dsh-adapter.yaml"
    assert "证伪" in origin.result
    assert origin.method == "load"


def test_verification_says_which_kind_of_unreadable_it_is(tmp_root: Path):
    """「不存在」与「在、但读不出来」是两个结论，理由必须说得出是哪一种。"""

    bad = tmp_root / "bad-encoding.yaml"
    bad.write_bytes(b"\xff\xfe\x00 not utf-8")
    origin = verification_of_config(bad, source="--config")
    assert origin.origin == "platform.config_unreadable"
    assert origin.method == "read"
    assert "UnicodeDecodeError" in origin.result
    assert "在，但" in origin.result
    assert origin.causal_link == "proven"


def test_without_an_object_there_is_no_verification(tmp_root: Path):
    origin = verification_of_config(None, source="--config 未提供")
    assert origin.origin == "unknown_origin"
    assert origin.method == "none"
    assert origin.verified is False
    assert "没有对象" in origin.result


def test_the_config_family_is_a_closed_table():
    """只有这张表里的原因码走配置核验；其余一律 unknown_origin（并写明**为什么**）。"""

    assert ORIGIN_BY_REASON_CODE == {
        "startup_error": "platform.config_unreadable",
        "config_error": "platform.config_unreadable",
        # 接线族：对象是 hooks.json（调用方必须把**那一个**路径交进来）
        "wiring_error": "platform.config_unreadable",
        "evidence_unavailable": "platform.evidence_unavailable",
    }
    unlisted = origin_from_failure(reason_code="event_replay", detail="重放一律阻断")
    assert unlisted.origin == "unknown_origin"
    assert "没有可执行的证伪判据" in unlisted.result
    assert unlisted.object_value == "event_replay"


def test_origin_from_failure_uses_the_named_config_and_falls_back_to_the_text(tmp_root: Path):
    missing = tmp_root / "dsh-adapter.yaml"
    named = origin_from_failure(
        reason_code="config_error", detail="adapter 配置不存在", config_path=missing
    )
    assert named.origin == "platform.config_unreadable"
    assert named.object_source.startswith("--config")

    recovered = origin_from_failure(
        reason_code="config_error", detail="adapter 配置不存在: dsh-adapter.yaml"
    )
    assert recovered.origin == "platform.config_unreadable"
    assert recovered.object_value == "dsh-adapter.yaml"
    assert "从失败原文里取回" in recovered.object_source


def test_evidence_unavailable_is_proven_only_after_a_real_observation(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """被点名不等于已核验：必须真的去 stat / read 那份输入（复核发现）。

    旧实现只凭"理由里出现了一个路径"就写 method=stat / verified=True / proven，而且
    调用方传进来的 config_path（adapter 配置）会被当成取证对象——两者都不是观测，
    于是审计里出现一条与真实 stat 无法区分的"已证明"记录。
    """

    monkeypatch.chdir(tmp_root)
    adapter_config = tmp_root / "dsh-adapter.yaml"
    adapter_config.write_text("agent_version: '1.0'" + chr(10), encoding="utf-8")
    (tmp_root / "present").mkdir()
    (tmp_root / "present" / "validators.yaml").write_text(
        "validators: []" + chr(10), encoding="utf-8"
    )

    # (1) 原文点名的输入真的不存在：stat 过之后才有资格写 proven。
    missing = origin_from_failure(
        reason_code="evidence_unavailable",
        detail="pre_evidence 的验证器数据读不到（missing/validators.yaml）",
        config_path=adapter_config,
        config_source="--config",
    )
    assert missing.origin == "platform.evidence_unavailable"
    assert missing.method == "stat"
    assert missing.verified is True
    assert missing.causal_link == "proven"
    # 对象是失败原文点名的那份输入，不是调用方给的 adapter 配置。
    assert missing.object_value == "validators.yaml"
    assert "dsh-adapter" not in missing.object_value
    assert "不存在" in missing.result

    # (2) 点名的那份输入读得到：这条指控被证伪，落 unknown_origin（规则 2）。
    readable = origin_from_failure(
        reason_code="evidence_unavailable",
        detail="取证失败：present/validators.yaml 读不到",
        config_path=adapter_config,
        config_source="--config",
    )
    assert readable.origin == "unknown_origin"
    assert readable.verified is False
    assert readable.causal_link == "unproven"
    assert "证伪" in readable.result
    assert readable.object_value == "validators.yaml"
    assert "dsh-adapter" not in readable.object_value + readable.result

    # (3) 没有点名任何输入：没有对象就没有核验。
    unnamed = origin_from_failure(reason_code="evidence_unavailable", detail="取证失败")
    assert unnamed.origin == "platform.evidence_unavailable"
    assert unnamed.method == "none"
    assert unnamed.verified is False
    assert unnamed.causal_link == "unproven"
    assert unnamed.object_value == "<未指名>"

    # (4) 读不出来的那份输入（不是 UTF-8）同样是"不可用"，理由要说得出是哪一种。
    broken = tmp_root / "broken" / "validators.yaml"
    broken.parent.mkdir()
    broken.write_bytes(b"\xff\xfe not utf-8")
    unreadable = origin_from_failure(
        reason_code="evidence_unavailable",
        detail="取证输入读不出来（broken/validators.yaml）",
    )
    assert unreadable.origin == "platform.evidence_unavailable"
    assert unreadable.method == "read"
    assert unreadable.verified is True
    assert unreadable.causal_link == "proven"
    assert "UnicodeDecodeError" in unreadable.result


def test_the_origin_payload_survives_a_jsonl_round_trip():
    """归因也会进审计（AGENTS 第 16 条的一条推论）：它必须**一条记录一行**、可回读。

    载荷里的换行会被 json.dumps 转义成 \\n（不会真的断行），因此这里断言的是
    "序列化之后没有裸换行 + 反序列化后取值不变"——那是审计能读回它的充分条件。
    """

    origin = unknown_origin(reason="两行" + chr(10) + "理由")
    payload = origin.to_payload()
    line = json.dumps(payload, ensure_ascii=False)
    assert chr(10) not in line and chr(13) not in line
    assert json.loads(line) == payload
    assert payload_is_well_formed(json.loads(line))
