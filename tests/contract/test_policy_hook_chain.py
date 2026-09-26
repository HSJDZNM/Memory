"""dsh Hook 链路的成对契约与失败关闭契约（G2 / G12）。

为什么单独一个文件：这两条契约跨"两种语言 + 两个进程"——JavaScript 侧的进程内插件注册了
哪些事件、Python 侧的 Hook 写出了哪几个阶段的记录——而"注册了 pre 却漏了 post"不会让任何
单侧测试变红。本文件把两侧钉在一起：

1. **插件侧**：tools/pre-execute 与 tools/post-execute 必须同时注册；转发逻辑在真实 node 里用
   **可注入的假 ctx** 跑一遍（exit 2 → 阻断；exit 非 0 非 2 → 阻断；Hook 起不来 / 被杀 → 阻断）。
   假 ctx 只观察、不断言，断言全在 Python 侧。
2. **产物侧**：任一**被放行的受治理动作**必须同时留下 pre 与 post 两段记录。判定读的是真实
   产物（audit.jsonl + enforcement-ledger.jsonl），不是源码字符串。
3. **CLI 侧**：没有 --hooks-config 时接线自检缺席 —— 这是失败关闭，不是"通过"；唯一的出路
   是显式命名的 --allow-unverified-wiring。

说得清哪条检查会因此变红才算修好：test_the_pairing_check_itself_can_fail 与
test_self_check_without_hooks_config_is_fail_closed 就是那两条会变红的检查。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import REPO_ROOT, dsh_event, write_dsh_config

from adapters.dsh.hooks import EXIT_ALLOW, EXIT_BLOCK, run_hook

pytestmark = pytest.mark.contract

PLUGIN = REPO_ROOT / "src" / "adapters" / "dsh" / "policy-hook.plugin.mjs"
NODE = shutil.which("node")

# 审计里**放行**的原因码：只有这些动作才应当有事后阶段。被阻断的动作没有执行，
# 也就不会、也不该有 PostToolUse。
ALLOWED_REASON_CODES = frozenset(
    {"allow", "allow_with_warnings", "allow_delegated", "enforcement_allow"}
)

HARNESS = '''/**
 * 假 ctx 探针：在真实 node 里驱动 policy-hook.plugin.mjs 的转发逻辑。
 * 它不做任何断言，只把观察到的原始事实打成 JSON 交给 Python 侧。
 */
import { pathToFileURL } from 'node:url';

const { apply } = await import(pathToFileURL(process.argv[2]).href);

const registrations = {};
const calls = [];
let behaviour = { exitCode: 0, stderr: '' };

const ctx = {
  on(name, handler) {
    registrations[name] = handler;
  },
  shell: {
    resolve(request) {
      return request;
    },
    async run(request) {
      calls.push(request);
      if (behaviour.throwError) {
        throw new Error(behaviour.throwError);
      }
      return { exitCode: behaviour.exitCode, stderr: { text: behaviour.stderr } };
    },
  },
};

apply(ctx, {
  command:
    'python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml ' +
    '--hooks-config .policy/hooks.json',
  timeoutMs: 30000,
  projectDir: process.argv[3],
});

const exec = {
  name: 'edit',
  callId: 'call-edit-allow',
  arguments: { file_path: 'src/shop/order_controller.py', old_string: 'a', new_string: 'b' },
  signal: undefined,
  agent: { session: { header: { id: 'sess-1', cwd: process.argv[3] } } },
};

let nextCalls = 0;
const next = async () => {
  nextCalls += 1;
  return { kind: 'enter' };
};
const lastPayload = () => JSON.parse(calls[calls.length - 1].stdin);

const observations = { registered: Object.keys(registrations) };

async function drivePre() {
  nextCalls = 0;
  const outcome = await registrations['tools/pre-execute'](exec, next);
  return { outcome, nextCalls, payload: lastPayload() };
}

async function drivePost(result) {
  nextCalls = 0;
  const outcome = await registrations['tools/post-execute'](exec, result, next);
  return { outcome, nextCalls, payload: lastPayload() };
}

observations.pre_allow = await drivePre();

behaviour = { exitCode: 2, stderr: 'blocked by ARCH-001' };
observations.pre_block = await drivePre();

behaviour = { exitCode: 1, stderr: 'ImportError: no module named policy' };
observations.pre_unknown_exit = await drivePre();

behaviour = { throwError: 'spawn EPERM' };
observations.pre_spawn_failure = await drivePre();

behaviour = { exitCode: 0, stderr: '' };
observations.post_allow = await drivePost({
  content: [
    { type: 'text', text: 'line-1' },
    { type: 'tool_use', id: 'z' },
    { type: 'text', text: 'line-2' },
  ],
});
observations.post_allow_string = await drivePost('plain text result');
observations.post_truncated = await drivePost({
  content: [{ type: 'text', text: 'x'.repeat(9000) }],
});

behaviour = { exitCode: 2, stderr: 'post check failed: file unchanged' };
observations.post_block = await drivePost({ content: [] });

behaviour = { exitCode: 1, stderr: '' };
observations.post_unknown_exit = await drivePost({ content: [] });

behaviour = { throwError: 'spawn EPERM' };
observations.post_spawn_failure = await drivePost({ content: [] });

process.stdout.write(JSON.stringify(observations));
'''


# --------------------------------------------------------------------------- 产物侧契约（G2）


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def unpaired_actions(audit_records: list[dict], ledger_records: list[dict]) -> list[str]:
    """G2 契约：返回"放行了却没有事后阶段"的 action_id（空列表 = 契约成立）。

    口径全部来自真实产物：

    - pre：审计里 hook_event=PreToolUse 且 reason_code 属于放行集合的动作；
    - post：审计里 hook_event=PostToolUse 的记录，或 Phase 4 的 post_evidence /
      final_decision 阶段记录，或台账里该动作的 execution 终态。

    被阻断的动作**不参与**判定：它没有执行，也就没有、也不该有 PostToolUse。
    """

    allowed: set[str] = set()
    for record in audit_records:
        if record.get("hook_event") != "PreToolUse":
            continue
        if record.get("reason_code") not in ALLOWED_REASON_CODES:
            continue
        action_id = record.get("action_id")
        if isinstance(action_id, str) and action_id:
            allowed.add(action_id)

    paired: set[str] = set()
    for record in audit_records:
        action_id = record.get("action_id")
        if not isinstance(action_id, str) or not action_id:
            continue
        stage = record.get("stage")
        # Phase 4 的 post_evidence 有两种：真的做完事后核对，和"找不到 pre 基线"的占位
        # （payload.stage_note = post_without_pre）。**占位不算配对完成**——否则
        # "事后阶段空转"会被读成"事后核对通过"。
        placeholder = isinstance(record.get("payload"), dict) and bool(
            record["payload"].get("stage_note")
        )
        if record.get("hook_event") == "PostToolUse" or (
            stage in {"post_evidence", "final_decision"} and not placeholder
        ):
            paired.add(action_id)
    for record in ledger_records:
        if record.get("kind") != "execution":
            continue
        action_id = record.get("action_id")
        if isinstance(action_id, str) and action_id:
            paired.add(action_id)
    return sorted(allowed - paired)


def test_the_pairing_check_itself_can_fail():
    """契约检查器自己必须会失败：只有 pre、没有 post 的动作必须被点出来。"""

    only_pre = [
        {"hook_event": "PreToolUse", "action_id": "s:1", "reason_code": "allow"},
        # 被阻断的动作不该被要求有事后阶段
        {"hook_event": "PreToolUse", "action_id": "s:2", "reason_code": "policy_block"},
        {"hook_event": "PostToolUse", "action_id": "s:2", "reason_code": "post_validated"},
    ]
    assert unpaired_actions(only_pre, []) == ["s:1"]

    completed = only_pre + [
        {"hook_event": "PostToolUse", "action_id": "s:1", "reason_code": "post_validated"}
    ]
    assert unpaired_actions(completed, []) == []

    # 台账里的 execution 终态同样算事后阶段（Phase 4 的链路证据）
    assert unpaired_actions(only_pre, [{"kind": "execution", "action_id": "s:1"}]) == []

    # "post 事件跑过"不等于"事后核对完成"：找不到 pre 基线的占位记录不能算配对。
    # （否则这条契约会因为"被阻断的调用也会经过 post"而恒真——见下面那条用例。）
    # 真实产物里这种占位记录长这样：Phase 4 的 stage 记录 + stage_note，没有 hook_event。
    placeholder_only = only_pre + [
        {
            "action_id": "s:1",
            "stage": "post_evidence",
            "payload": {"stage_note": "post_without_pre"},
        }
    ]
    assert unpaired_actions(placeholder_only, []) == ["s:1"]


def payload(name: str, project_root: Path, **overrides: object) -> dict[str, object]:
    return dsh_event(name, cwd=str(project_root), **overrides)


def test_an_allowed_governed_edit_leaves_both_pre_and_post_stages(dsh_config_path, dsh_project):
    """真实产物的成对契约：一次放行的写类动作必须同时留下 pre 与 post。"""

    audit = dsh_project.parent / "audit.jsonl"
    ledger = audit.with_name(f"{audit.stem}.enforcement-ledger{audit.suffix}")
    source = dsh_project / "src" / "shop" / "order_controller.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("from service import OrderService" + chr(10), encoding="utf-8", newline="")

    pre = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_ALLOW, pre.stderr

    # 模拟 Agent 运行时执行这次编辑（内容与请求参数一致）
    source.write_text(
        "from service import OrderService" + chr(10) + "from util import clock" + chr(10),
        encoding="utf-8",
        newline="",
    )

    post = run_hook(
        payload("post-tool-use-edit.json", dsh_project, tool_use_id="call-edit-allow"),
        config_path=dsh_config_path,
        audit_path=audit,
    )
    assert post.exit_code == EXIT_ALLOW, post.stderr

    audit_records = load_jsonl(audit)
    ledger_records = load_jsonl(ledger)
    events = [record.get("hook_event") for record in audit_records]
    assert "PreToolUse" in events, events
    assert "PostToolUse" in events, events

    # 事后阶段不是"有个字段就算"：它必须真的跑到 post-check 的终态。
    post_records = [record for record in audit_records if record.get("hook_event") == "PostToolUse"]
    assert post_records[-1]["reason_code"] == "post_validated", post_records[-1]
    assert post_records[-1]["action_id"] == "sess-demo-0001:call-edit-allow"
    assert any(record.get("stage") == "post_evidence" for record in audit_records)
    assert [record for record in ledger_records if record.get("kind") == "execution"]

    # 成对契约本身
    assert unpaired_actions(audit_records, ledger_records) == []

    # 阻断的动作不产生事后阶段，也不该被要求有
    blocked_audit = dsh_project.parent / "blocked-audit.jsonl"
    blocked = run_hook(
        payload("pre-tool-use-edit-block.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=blocked_audit,
    )
    assert blocked.exit_code == EXIT_BLOCK
    assert unpaired_actions(load_jsonl(blocked_audit), []) == []
    assert all(record.get("hook_event") != "PostToolUse" for record in load_jsonl(blocked_audit))


def test_a_blocked_call_that_still_reaches_post_is_not_reported_as_validated(
    dsh_config_path, dsh_project
):
    """被 pre 阻断的调用**同样会经过** tools/post-execute（dsh 官方文档口径）。

    因此"有 post 记录"本身不能证明"事后核对通过"：这类调用在事后阶段找不到执行前基线，
    只写一条 stage_note=post_without_pre 的占位记录，且**不得**产生 final_decision/validated。
    本用例把"真实执行成功"与"被 pre 阻断"两类分开断言（前者见上一条用例）。
    """

    audit = dsh_project.parent / "audit.jsonl"
    ledger = audit.with_name(f"{audit.stem}.enforcement-ledger{audit.suffix}")
    source = dsh_project / "src" / "shop" / "order_controller.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("from service import OrderService" + chr(10), encoding="utf-8", newline="")

    pre = run_hook(
        payload("pre-tool-use-edit-block.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_BLOCK
    assert pre.reason_code == "policy_block"

    # 真实运行时：被拒绝的调用之后仍会来一条 PostToolUse
    post = run_hook(
        payload("post-tool-use-edit.json", dsh_project, tool_use_id="call-edit-block"),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert post.exit_code == EXIT_ALLOW
    assert post.reason_code == "post_not_required"
    audit_records = load_jsonl(audit)
    placeholders = [
        record
        for record in audit_records
        if record.get("stage") == "post_evidence"
        and isinstance(record.get("payload"), dict)
        and record["payload"].get("stage_note") == "post_without_pre"
    ]
    assert placeholders, audit_records
    # 没有 final_decision：事后阶段没有编造"这次执行有效/无效"的结论
    assert not [record for record in audit_records if record.get("stage") == "final_decision"]
    assert not [record for record in load_jsonl(ledger) if record.get("kind") == "execution"]
    # 被阻断的动作不进入配对要求（否则这条契约会因为"post 一定会来"而恒真）
    assert unpaired_actions(audit_records, load_jsonl(ledger)) == []


# --------------------------------------------------------------------------- 插件侧契约（G2 / G12）


def test_the_plugin_registers_pre_and_post_together():
    """源码级契约：两个事件名必须成对出现（R1 就是"只注册了 pre"）。"""

    source = PLUGIN.read_text(encoding="utf-8")
    assert "ctx.on('tools/pre-execute'" in source
    assert "ctx.on('tools/post-execute'" in source
    # post 阶段只能把结果标成错误（副作用已发生），不能假装回滚
    assert "kind: 'block'" in source
    assert "feedback" in source


def _require_node() -> str:
    if NODE is not None:
        return NODE
    reason = "node 不可用：插件转发行为未在本机验证（源码级契约仍然生效）"
    if os.environ.get("POLICY_REQUIRE_NODE") == "1":
        pytest.fail(reason + "；POLICY_REQUIRE_NODE=1 要求它必须真的跑起来")
    pytest.skip(reason)


def run_harness(tmp_root: Path) -> dict:
    script = tmp_root / "plugin_harness.mjs"
    script.write_text(HARNESS, encoding="utf-8", newline=chr(10))
    completed = subprocess.run(
        [_require_node(), str(script), str(PLUGIN), str(tmp_root)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_the_plugin_forwards_post_execute_with_the_tool_response(tmp_root):
    observed = run_harness(tmp_root)

    assert observed["registered"] == ["tools/pre-execute", "tools/post-execute"]

    # pre：放行要委托给下一个监听者；载荷是 PreToolUse 且不带工具结果
    assert observed["pre_allow"]["outcome"] == {"kind": "enter"}
    assert observed["pre_allow"]["nextCalls"] == 1
    pre_payload = observed["pre_allow"]["payload"]
    assert pre_payload["hook_event_name"] == "PreToolUse"
    assert pre_payload["tool_name"] == "edit"
    assert pre_payload["tool_use_id"] == "call-edit-allow"
    assert pre_payload["session_id"] == "sess-1"
    assert "tool_response" not in pre_payload

    # post：转发 PostToolUse，带 tool_use_id 与工具结果摘要（content blocks 折叠成文本）
    assert observed["post_allow"]["outcome"] == {"kind": "enter"}
    assert observed["post_allow"]["nextCalls"] == 1
    post_payload = observed["post_allow"]["payload"]
    assert post_payload["hook_event_name"] == "PostToolUse"
    assert post_payload["tool_use_id"] == "call-edit-allow"
    assert post_payload["tool_response"] == "line-1line-2"

    # 结果形状变化（直接给字符串）不能静默变成空结果
    assert observed["post_allow_string"]["payload"]["tool_response"] == "plain text result"

    # 超长结果只留前缀，且明确标注截断
    truncated = observed["post_truncated"]["payload"]["tool_response"]
    assert len(truncated) < 9000
    assert "已截断" in truncated


def test_the_plugin_denies_every_non_zero_non_two_exit_code_and_every_spawn_failure(tmp_root):
    observed = run_harness(tmp_root)

    # pre：exit 2 用 stderr 作为理由；其他非 0 与"起不来"一律按失败关闭拒绝
    assert observed["pre_block"]["outcome"] == {"kind": "deny", "reason": "blocked by ARCH-001"}
    assert observed["pre_block"]["nextCalls"] == 0
    assert observed["pre_unknown_exit"]["outcome"]["kind"] == "deny"
    assert "退出码 1" in observed["pre_unknown_exit"]["outcome"]["reason"]
    assert observed["pre_unknown_exit"]["nextCalls"] == 0
    assert observed["pre_spawn_failure"]["outcome"]["kind"] == "deny"
    assert "spawn EPERM" in observed["pre_spawn_failure"]["outcome"]["reason"]

    # post：副作用已经发生，所以是 block + feedback（把结果标成错误），语义是"结果不可信"
    assert observed["post_block"]["outcome"]["kind"] == "block"
    assert (
        observed["post_block"]["outcome"]["feedback"][0]["text"]
        == "post check failed: file unchanged"
    )
    assert observed["post_block"]["nextCalls"] == 0
    assert observed["post_unknown_exit"]["outcome"]["kind"] == "block"
    assert "退出码 1" in observed["post_unknown_exit"]["outcome"]["feedback"][0]["text"]
    assert observed["post_spawn_failure"]["outcome"]["kind"] == "block"
    assert "spawn EPERM" in observed["post_spawn_failure"]["outcome"]["feedback"][0]["text"]


# --------------------------------------------------------------------------- CLI 契约（G12）


def cli_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_cli(args: list[str], stdin_text: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "adapters.dsh.hooks", *args],
        cwd=str(REPO_ROOT),
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=cli_env(),
        check=False,
    )


def test_self_check_without_hooks_config_is_fail_closed(dsh_config_path):
    """G12：自检缺席 = 失败关闭。"不提供 hooks 配置就当通过"正是缺口本身。"""

    completed = run_cli(["--config", str(dsh_config_path), "--self-check"])

    assert completed.returncode == EXIT_BLOCK
    assert "接线自检缺席" in completed.stderr


def test_the_only_way_out_is_the_named_waiver(dsh_config_path):
    completed = run_cli(
        ["--config", str(dsh_config_path), "--self-check", "--allow-unverified-wiring"]
    )

    assert completed.returncode == EXIT_ALLOW
    assert "self-check ok" in completed.stderr


def test_a_hook_call_without_hooks_config_blocks_instead_of_allowing(dsh_config_path, dsh_project):
    """生产路径同样失败关闭：没有接线证据时，工具调用必须被阻断（exit 2）。"""

    completed = run_cli(
        ["--config", str(dsh_config_path)],
        json.dumps(payload("pre-tool-use-edit-allow.json", dsh_project)),
    )

    assert completed.returncode == EXIT_BLOCK
    assert completed.stdout == ""
    assert "接线自检缺席" in completed.stderr


def test_a_hook_call_with_wiring_evidence_still_works(dsh_config_path, dsh_project, tmp_root):
    """反向对照：提供 --hooks-config 后放行路径不被这条契约误伤。"""

    config_path = write_dsh_config(
        tmp_root / "config" / "dsh-adapter.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
    )
    hooks_json = tmp_root / "hooks.json"
    hooks_json.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": (
                                        "python -m adapters.dsh.hooks "
                                        "--config .policy/dsh-adapter.yaml "
                                        "--hooks-config .policy/hooks.json"
                                    ),
                                    "timeout": 30,
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    completed = run_cli(
        ["--config", str(config_path), "--hooks-config", str(hooks_json)],
        json.dumps(payload("pre-tool-use-edit-allow.json", dsh_project)),
    )

    assert completed.returncode == EXIT_ALLOW, completed.stderr
