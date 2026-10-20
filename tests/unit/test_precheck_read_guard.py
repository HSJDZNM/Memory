"""B3 只读命令族读面闸门（注册表 1.2 的 `read_guard` 数据）的用例。

05 §4 B3 的三条门与三条反例都钉在这里：

1. **越界形态被拦**：`git show HEAD:.policy/approval.json`、
   `git log -p -- .policy/audit.jsonl`、`git show HEAD:../Free/README.md` 的同型
   （`git show HEAD:..`——**没有** `../` 子串，所以命令片段层表达不了它，只有读面谓词能）；
2. **合法只读命令 0 误伤**：`git status` / `git diff` / `git log` 普通用法照常通过；
3. **不扩大拦截面**：只读族以外的命令（脚本族 / 测试族）读面闸门显式 `SKIPPED`；
   白名单外命令仍是 `command_not_allowlisted`，被禁片段仍是 `command_fragment_blocked`；
   **`read_guard` 与 `command_fragment_blocked` 是两个码**，不许混成一个。

另外两条"数据面"性质：`read_guard` 进 `schema_hash`（改读面边界 = 重新审核），加载期
拒绝半截声明（空集合 / 未知形态 / 未知字段 / 点名不存在的族 / 非命令类驱动）。

读面闸门的**已知缺口**不在这里假装覆盖：选项取值（`--output=<路径>`）由片段清单管、
被引号包裹且含空格的路径会被空白切段、git 配置与别名展开不在视野里——结构性检查不是沙箱。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from enforcement_support import (
    EnforcementPaths,
    make_action,
    registry_document,
    write_registry,
)

from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import CheckStatus, Decision, ReasonCode, ToolSpec
from enforcement.precheck import pre_execute

pytestmark = pytest.mark.contract

# 生产注册表同形的片段清单（`../` 也在里面）：用来证明"先命中者定码"不会把
# 读面的结论偷换成片段层的结论，也证明片段层**没有**吞掉 `.policy/` 那一类。
PRODUCTION_FRAGMENTS = ("../", "..\\", "--output", "--ext-diff", "--no-index")
# 故意**去掉** `../`：用来证明读面闸门自己就能拦住跨出受治项目的形态，
# 而不是靠片段清单顺带拦下来的。
NO_TRAVERSAL_FRAGMENTS = ("--output", "--ext-diff", "--no-index")

READ_GUARD = {
    "families": ["readonly"],
    "path_forms": ["positional", "revision_path"],
    "forbidden_path_prefixes": [".policy"],
    "forbidden_forms": ["parent_escape", "absolute_path"],
}

ALLOWED_COMMANDS = [
    "^print[(]'ok'[)]$",
    "^git (status|diff|log|show)( .*)?$",
    "^echo( .*)?$",
]

FAMILIES = [
    {
        "id": "readonly",
        "patterns": ["^git (status|diff|log|show)( .*)?$", "^echo( .*)?$"],
    },
    {"id": "probe", "patterns": ["^print[(]'ok'[)]$"]},
]


def tool_payload(
    *,
    read_guard: dict | None = READ_GUARD,
    fragments: tuple[str, ...] = PRODUCTION_FRAGMENTS,
) -> dict:
    """一个受读面闸门约束的命令工具（shell 前缀里的 @PYTHON@ 由 registry_document 替换）。"""

    payload: dict = {
        "id": "exec.guarded",
        "title": "test guarded shell",
        "agent": "dsh",
        "tool_name": "pwsh",
        "schema_version": "1.0",
        "risk": "privileged_execution",
        "effect": "process",
        "driver": "shell_command",
        "shell": ["@PYTHON@", "-c"],
        "command_param": "command",
        "required_permissions": ["shell.exec"],
        "approval": "required",
        "post_checks": ["exit_code_zero"],
        "timeout_ms": 20000,
        "allowed_commands": list(ALLOWED_COMMANDS),
        "forbidden_command_fragments": list(fragments),
        "command_families": [dict(item) for item in FAMILIES],
        "parameters": [
            {"name": "command", "type": "string", "required": True, "max_chars": 400},
            {"name": "description", "type": "string", "required": True, "max_chars": 200},
        ],
    }
    if read_guard is not None:
        payload["read_guard"] = {key: list(value) for key, value in read_guard.items()}
    return payload


def guarded_paths(root: Path, **kwargs) -> EnforcementPaths:
    """写一份**只含**受闸门工具的注册表并完成审核（审核仍走生产代码路径）。"""

    paths = EnforcementPaths(root)
    document = registry_document(
        tools=(tool_payload(**kwargs),), registry_schema_version="1.2"
    )
    write_registry(root, document=document)
    return paths


def run_pre(paths: EnforcementPaths, command: str, *, action_id: str = "read-guard-1"):
    registry = paths.registry_object()
    request = make_action(
        registry,
        paths,
        "exec.guarded",
        {"command": command, "description": "b3 read guard"},
        roles=("owner",),
        action_id=action_id,
    )
    return pre_execute(
        request,
        registry=registry,
        ledger=EnforcementLedger(paths.ledger),
        sink=FileAuditSink(paths.audit, workspace=paths.workspace),
        approval=None,
        dry_run=True,
    )


def read_guard_check(outcome):
    check = outcome.decision.check("read_guard")
    assert check is not None, "每次判定都必须留下 read_guard 检查项（含 SKIPPED）"
    return check


# --------------------------------------------------------------------------- 三条门：越界被拦


CROSSINGS = [
    ("git show HEAD:.policy/approval.json", "revision_path 读信任根"),
    ("git log -p -- .policy/audit.jsonl", "positional 读信任根"),
    # 04 号 5.70 第三种形态的**同型**：一样是跨出受治项目，但**不含** `../` 子串，
    # 因此命令片段层看不见它——这正是"读面闸门不是片段清单的复述"的证据。
    ("git show HEAD:..", "revision_path 跨出受治项目（片段层表达不了）"),
]


@pytest.mark.parametrize("command,note", CROSSINGS)
def test_the_documented_crossings_are_blocked_with_the_read_guard_code(
    tmp_root: Path, command: str, note: str
):
    """片段清单里**没有** `../` 时，三条越界形态仍必须被读面闸门拦下（独立闸门）。"""

    paths = guarded_paths(tmp_root, fragments=NO_TRAVERSAL_FRAGMENTS)
    outcome = run_pre(paths, command)

    assert outcome.decision.decision is Decision.BLOCK, note
    assert outcome.decision.reason_code is ReasonCode.READ_GUARD_BLOCKED, note
    check = read_guard_check(outcome)
    assert check.status is CheckStatus.FAILED
    assert check.reason_code is ReasonCode.READ_GUARD_BLOCKED
    # 拒绝理由必须说清"改成什么形态就能过"（AGENTS 第 50 条）
    assert "改成受控项目内的相对路径" in check.detail


@pytest.mark.parametrize(
    "command,expected",
    [
        # 片段层看得见的两种：仍然是 command_fragment_blocked（先命中者定码，口径不变）
        ("git show HEAD:../Free/README.md", ReasonCode.COMMAND_FRAGMENT_BLOCKED),
        ("git diff --output=x.txt", ReasonCode.COMMAND_FRAGMENT_BLOCKED),
        # 片段层看不见的那一种：读面闸门自己定码
        ("git show HEAD:.policy/approval.json", ReasonCode.READ_GUARD_BLOCKED),
    ],
)
def test_fragments_keep_their_code_and_the_read_guard_keeps_its_own(
    tmp_root: Path, command: str, expected: ReasonCode
):
    """生产片段清单下两个 reason code **互不替代**：谁先命中谁定码，两条检查都留痕。"""

    paths = guarded_paths(tmp_root)
    outcome = run_pre(paths, command)

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is expected
    assert ReasonCode.READ_GUARD_BLOCKED is not ReasonCode.COMMAND_FRAGMENT_BLOCKED
    if expected is ReasonCode.COMMAND_FRAGMENT_BLOCKED:
        assert outcome.decision.check("command_fragments").status is CheckStatus.FAILED
    else:
        assert outcome.decision.check("command_fragments").status is CheckStatus.PASSED
        assert outcome.decision.check("read_guard").status is CheckStatus.FAILED


@pytest.mark.parametrize(
    "command",
    [
        # 同一目标换拼写：naive 的 ".policy/" 子串匹配会漏掉下面三种里的两种
        "git log -p -- ./.policy/audit.jsonl",
        "git show HEAD:.POLICY/approval.json",
        "git show HEAD:./.policy/approval.json",
        "git diff -- .policy",
        "git show HEAD:.policy",
    ],
)
def test_spelling_variants_of_the_trust_root_are_normalized(tmp_root: Path, command: str):
    """受保护前缀按"归一化 + 大小写不敏感 + 路径分段边界"比对，不是字面子串。"""

    paths = guarded_paths(tmp_root)
    outcome = run_pre(paths, command)

    assert outcome.decision.reason_code is ReasonCode.READ_GUARD_BLOCKED, command


def test_a_lookalike_prefix_is_not_a_hit(tmp_root: Path):
    """路径分段边界：`.policyx/...` 不是 `.policy` 下面的文件，不许被前缀闸误伤。"""

    paths = guarded_paths(tmp_root)
    outcome = run_pre(paths, "git log -p -- .policyx/audit.jsonl")

    assert read_guard_check(outcome).status is CheckStatus.PASSED
    assert outcome.decision.reason_code is not ReasonCode.READ_GUARD_BLOCKED


# --------------------------------------------------------------------------- 反例：0 误伤


LEGAL = [
    "git status",
    "git status --short",
    "git diff",
    "git diff --stat",
    "git log --oneline -5",
    "git log -p -- src/enforcement/precheck.py",
    "git log --format=%H",
    "git diff -- src/enforcement/models.py",
    "git show HEAD:src/enforcement/models.py",
    # git 语义：`<rev>:/x` 是**仓库根**下的 x，不是宿主绝对路径——不许误伤
    "git show HEAD:/README.md",
]


@pytest.mark.parametrize("command", LEGAL)
def test_legal_read_only_commands_are_not_flagged(tmp_root: Path, command: str):
    """合法只读命令的 read_guard 必须 PASSED（它们仍可能缺审批，那不是读面闸门的事）。"""

    paths = guarded_paths(tmp_root)
    outcome = run_pre(paths, command)

    check = read_guard_check(outcome)
    assert check.status is CheckStatus.PASSED, command
    assert outcome.decision.reason_code is not ReasonCode.READ_GUARD_BLOCKED, command


# --------------------------------------------------------------------------- 不扩大拦截面


@pytest.mark.parametrize(
    "command",
    [
        # 脚本族 / 测试族：不在 read_guard.families 里
        "print('ok')",
        # 白名单外命令：仍然是原来的 reason_code
        "Remove-Item -Recurse .",
    ],
)
def test_commands_outside_the_declared_read_families_are_skipped(
    tmp_root: Path, command: str
):
    """读面闸门只认 `read_guard.families` 点名的族：其它命令的拦截面一个字不动。"""

    paths = guarded_paths(tmp_root)
    outcome = run_pre(paths, command)

    assert read_guard_check(outcome).status is CheckStatus.SKIPPED
    if command.startswith("Remove-Item"):
        assert outcome.decision.reason_code is ReasonCode.COMMAND_NOT_ALLOWLISTED
        assert outcome.decision.check("read_guard").detail.startswith(
            "该命令不在 read_guard 声明的只读族"
        )
    else:
        assert outcome.decision.reason_code is not ReasonCode.READ_GUARD_BLOCKED


def test_a_tool_without_read_guard_is_explicitly_skipped(tmp_root: Path):
    """旧注册表（1.0 / 1.1、不带 read_guard）照常加载：跳过必须是**显式**状态。"""

    paths = guarded_paths(tmp_root, read_guard=None)
    outcome = run_pre(paths, "git show HEAD:.policy/approval.json")

    check = read_guard_check(outcome)
    assert check.status is CheckStatus.SKIPPED
    assert "未声明 read_guard 数据" in check.detail
    # 没有数据 = 没有这道闸门（保持旧行为），但结论里不许出现"查过且干净"的假象
    assert outcome.decision.reason_code is not ReasonCode.READ_GUARD_BLOCKED


# --------------------------------------------------------------------------- 数据面：加载期校验


def _spec(**overrides) -> ToolSpec:
    payload = tool_payload()
    payload.update(overrides)
    return ToolSpec(**payload)


def test_read_guard_enters_the_reviewed_schema_hash():
    """读面边界是被审核数据：改一个前缀就让 schema_hash 变化（必须重新 approve）。"""

    base = _spec()
    wider = _spec(
        read_guard={**READ_GUARD, "forbidden_path_prefixes": [".policy", "registry"]}
    )
    assert base.schema_hash != wider.schema_hash
    assert base.read_guard is not None and base.read_guard.forbidden_path_prefixes == (".policy",)


@pytest.mark.parametrize(
    "overrides,needle",
    [
        # 空集合：半截闸门看起来像门，放走的正是另一半
        ({"read_guard": {**READ_GUARD, "families": []}}, "at least"),
        ({"read_guard": {**READ_GUARD, "path_forms": []}}, "at least"),
        ({"read_guard": {**READ_GUARD, "forbidden_path_prefixes": []}}, "at least"),
        ({"read_guard": {**READ_GUARD, "forbidden_forms": []}}, "at least"),
        # 未知形态 / 未知字段：闭集之外的声明一律拒（AGENTS 第 3 条）
        ({"read_guard": {**READ_GUARD, "path_forms": ["regex"]}}, "未知形态"),
        ({"read_guard": {**READ_GUARD, "forbidden_forms": ["symlink_escape"]}}, "未知形态"),
        ({"read_guard": {**READ_GUARD, "note": "x"}}, "Extra"),
        # 点名未声明的命令族：闸门永远不会触发，等于一份没人读的声明
        ({"read_guard": {**READ_GUARD, "families": ["readonly", "nope"]}}, "未声明的命令族"),
        # 没有族数据就没有可生效的范围
        ({"command_families": [], "read_guard": READ_GUARD}, "command_families"),
        # 非命令类驱动：没有命令文本，声明了也永远不会被执行
        ({"driver": "file_edit", "shell": [], "command_param": None}, "shell_command"),
        # 前缀必须真的落在受控项目内
        ({"read_guard": {**READ_GUARD, "forbidden_path_prefixes": [".."]}}, "相对路径"),
        ({"read_guard": {**READ_GUARD, "forbidden_path_prefixes": ["/etc"]}}, "相对路径"),
        ({"read_guard": {**READ_GUARD, "forbidden_path_prefixes": [".policy", ".POLICY"]}}, "重复"),
        # 重复的族 / 形态同样是数据错误
        ({"read_guard": {**READ_GUARD, "families": ["readonly", "readonly"]}}, "重复"),
        ({"read_guard": {**READ_GUARD, "path_forms": ["positional", "positional"]}}, "重复"),
    ],
)
def test_half_declared_read_guards_are_refused_at_load_time(overrides, needle):
    with pytest.raises(Exception) as error:
        _spec(**overrides)
    assert needle in str(error.value), str(error.value)


def test_the_new_reason_code_is_its_own_value():
    """新增原因码只加值、不改既有值：按 reason_code 聚合的历史读数不受影响。"""

    assert ReasonCode.READ_GUARD_BLOCKED.value == "read_guard_blocked"
    assert ReasonCode.COMMAND_FRAGMENT_BLOCKED.value == "command_fragment_blocked"
    assert ReasonCode.COMMAND_COMPOSITION_BLOCKED.value == "command_composition_blocked"
