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
from typing import Any

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
import { existsSync, rmSync } from 'node:fs';
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

// N16：退出事实必须从 result.value 转发进 PostToolUse 载荷。
// 形状取自 dsh 的规范化工具结果（dsh-tools 的 materializeFinalResult 返回
// {isError, content, ..., value}；pwsh 工具的 value 是 canonicalPwshResult()：
// kind / exitCode / signal / timedOut / aborted / timeoutMs / stdout / stderr）。
behaviour = { exitCode: 0, stderr: '' };
observations.post_exit_zero = await drivePost({
  isError: false,
  content: [{ type: 'text', text: '3 passed in 0.42s' }],
  value: {
    kind: 'foreground',
    exitCode: 0,
    signal: null,
    timedOut: false,
    aborted: false,
    timeoutMs: 60000,
    stdout: { text: '3 passed in 0.42s', truncated: false },
    stderr: { text: '', truncated: false },
  },
});
observations.post_exit_one = await drivePost({
  isError: false,
  content: [{ type: 'text', text: '1 failed' }],
  value: { kind: 'foreground', exitCode: 1, signal: null, timedOut: false, aborted: false },
});
observations.post_timed_out = await drivePost({
  isError: false,
  content: [],
  value: { kind: 'foreground', exitCode: 1, signal: null, timedOut: true, aborted: false },
});
observations.post_background = await drivePost({
  isError: false,
  content: [{ type: 'text', text: 'started job-1' }],
  value: { kind: 'background', jobId: 'job-1' },
});
observations.post_failed_result = await drivePost({
  isError: true,
  error: { message: 'boom' },
  content: [{ type: 'text', text: 'Error: boom' }],
});
observations.post_bad_shapes = await drivePost({
  isError: false,
  content: [],
  value: { kind: 'foreground', exitCode: '1', signal: 7, timedOut: 'yes', aborted: 1 },
});


// N18：Hook 阻断时会多写一行机读判定（hooks.py 的 verdict_line）。本机 dsh 会把 exit 2
// 压成 1，所以"策略阻断（原因码）"必须来自判定行，而不是退出码。
const verdictLine = (payload) =>
  '[policy] VERDICT ' + JSON.stringify(payload);
// 不写字面换行转义：本文件的 JS 是 Python 三引号字符串，转义会被 Python 先吃一层。
const nl = String.fromCharCode(10);
const policyVerdict = verdictLine({
  schema_version: '1.0',
  reason_code: 'policy_block',
  exit_code: 2,
  hook_event: 'PreToolUse',
});

behaviour = { exitCode: 2, stderr: 'blocked by ARCH-001' + nl + policyVerdict };
observations.pre_block_with_verdict = await drivePre();

behaviour = { exitCode: 1, stderr: 'blocked by ARCH-001' + nl + policyVerdict };
observations.pre_normalized_exit_with_verdict = await drivePre();

behaviour = { exitCode: 2, stderr: policyVerdict };
observations.pre_block_verdict_only = await drivePre();

behaviour = { exitCode: 1, stderr: '[policy] VERDICT not-json' };
observations.pre_broken_verdict = await drivePre();

behaviour = {
  exitCode: 1,
  stderr: verdictLine({
    schema_version: '9.9',
    reason_code: 'policy_block',
    exit_code: 2,
  }),
};
observations.pre_unknown_verdict_version = await drivePre();

behaviour = {
  exitCode: 1,
  stderr: 'post check failed: file unchanged' + nl + verdictLine({
    schema_version: '1.0',
    reason_code: 'post_repair_required',
    exit_code: 2,
    hook_event: 'PostToolUse',
  }),
};
observations.post_normalized_exit_with_verdict = await drivePost({ content: [] });

// 反向对照：判定行不会把 exit 0 变成拒绝
behaviour = { exitCode: 0, stderr: policyVerdict };
observations.pre_allow_with_stray_verdict = await drivePre();

// 本轮追加：post 阻断时除了策略理由，还要把原始输出作为**不可信数据**附给模型。
// （原因：exec.pwsh 声明了 post_checks=[exit_code_zero]，命令失败时模型只拿到一行策略错误，
//   连自己命令的输出都看不到 —— 而那正是失败时最需要的东西。）
behaviour = { exitCode: 2, stderr: 'post check failed: file unchanged' };
observations.post_block_with_output = await drivePost({
  isError: false,
  content: [{ type: 'text', text: '1 failed, 2 passed in 0.31s' }],
  value: { kind: 'foreground', exitCode: 1, signal: null, timedOut: false, aborted: false },
});
observations.post_block_empty_output = await drivePost({ isError: false, content: [] });
observations.post_block_long_output = await drivePost({
  content: [{ type: 'text', text: 'y'.repeat(9000) }],
});

// 反向对照：accept 分支不得多注入任何东西
behaviour = { exitCode: 0, stderr: '' };
observations.post_accept_with_output = await drivePost({
  content: [{ type: 'text', text: 'ok' }],
});

// ---------------------------------------------------------------- Q6：工作目录不可用时的归因
//
// 真机机制（14 号文档 §5 Q6）：Node 的 spawn 在 **cwd 不存在**时把 ENOENT 归给**可执行文件**
// （真机原文里的可执行文件是 node.exe 的绝对路径，而它存在且可执行）。所以下面这个假 ctx 的
// shell **照搬**这条 spawn 行为，而不是随便抛一个错：否则探针测不到真机上的那个机制，
// 「修前会红」也就无从谈起。
const WORKDIR_COMMAND = 'python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml';

function mountForWorkdir(projectDir, sessionCwd) {
  const state = { exitCode: 0, stderr: '', throwError: '', vanishWorkdir: false };
  const registrations = {};
  const calls = [];
  const localCtx = {
    on(name, handler) {
      registrations[name] = handler;
    },
    shell: {
      resolve(request) {
        return request;
      },
      async run(request) {
        calls.push(request);
        if (state.vanishWorkdir && request.workdir !== undefined) {
          // 竞态：预检时目录还在，spawn 之前没了。
          rmSync(request.workdir, { recursive: true, force: true });
        }
        if (state.throwError !== '') {
          throw new Error(state.throwError);
        }
        if (request.workdir !== undefined && !existsSync(request.workdir)) {
          // 真实 Node：cwd 不存在 → ENOENT，但报的是**可执行文件**。
          throw new Error('spawn ' + process.execPath + ' ENOENT');
        }
        return { exitCode: state.exitCode, stderr: { text: state.stderr } };
      },
    },
  };
  apply(localCtx, { command: WORKDIR_COMMAND, timeoutMs: 30000, projectDir });
  const exec = {
    name: 'edit',
    callId: 'call-workdir',
    arguments: { file_path: 'src/shop/order_controller.py', old_string: 'a', new_string: 'b' },
    signal: undefined,
    agent: { session: { header: { id: 'sess-workdir', cwd: sessionCwd } } },
  };
  const drive = async (event, result) => {
    let nextCalls = 0;
    const next = async () => {
      nextCalls += 1;
      return { kind: 'enter' };
    };
    const before = calls.length;
    const outcome =
      event === 'pre'
        ? await registrations['tools/pre-execute'](exec, next)
        : await registrations['tools/post-execute'](exec, result, next);
    return { outcome, nextCalls, spawnAttempts: calls.length - before };
  };
  return {
    state,
    drivePre: () => drive('pre', undefined),
    drivePost: (result) => drive('post', result),
  };
}

// argv[4]：保证不存在的目录；argv[5]：存在、但会被假 ctx 在 spawn 之前删掉的目录。
const missingWorkdir = process.argv[4];
const vanishingWorkdir = process.argv[5];

// (a) config.projectDir 指向不存在的目录 —— 真机症状的最小复现
const missingProjectDir = mountForWorkdir(missingWorkdir, process.argv[3]);
observations.workdir_missing_project_dir = await missingProjectDir.drivePre();
observations.workdir_missing_project_dir_post = await missingProjectDir.drivePost({
  content: [],
});

// (b) 没给 projectDir，会话 cwd 指向不存在的目录
const missingSessionCwd = mountForWorkdir(undefined, missingWorkdir);
observations.workdir_missing_session_cwd = await missingSessionCwd.drivePre();

// 反向对照：projectDir 存在时，不存在的会话 cwd 不该被当成工作目录（不许过度拒绝）
const projectDirWins = mountForWorkdir(process.argv[3], missingWorkdir);
observations.workdir_project_dir_wins = await projectDirWins.drivePre();

// (c) 工作目录存在，spawn 仍然抛错 —— 归因必须落在「要启动的命令」那一侧
const intactWorkdir = mountForWorkdir(process.argv[3], process.argv[3]);
intactWorkdir.state.throwError = 'spawn ' + process.execPath + ' ENOENT';
observations.workdir_intact_spawn_error = await intactWorkdir.drivePre();

// 竞态：预检通过之后目录被删掉（catch 分支必须重新看一眼工作目录）
const vanishedWorkdir = mountForWorkdir(vanishingWorkdir, vanishingWorkdir);
vanishedWorkdir.state.vanishWorkdir = true;
observations.workdir_vanished_before_spawn = await vanishedWorkdir.drivePre();

// (a2) config.projectDir 指向一个**文件**：同属"工作目录不可用"，但不是"不存在"
const projectDirIsAFile = mountForWorkdir(process.argv[6], process.argv[3]);
observations.workdir_project_dir_is_a_file = await projectDirIsAFile.drivePre();

// (c2) 目录正常，spawn 抛 EPERM（受限沙箱禁止管道 stdio）：不是目录那一侧的问题
const intactEperm = mountForWorkdir(process.argv[3], process.argv[3]);
intactEperm.state.throwError = 'spawn EPERM';
observations.workdir_intact_spawn_eperm = await intactEperm.drivePre();

process.stdout.write(JSON.stringify(observations));
'''


# 把 Python Hook 真实产出的 stderr 原样交给插件，观察它给模型的理由。
# argv: <plugin.mjs> <stderr-text> <exit-code> <projectDir>
HARNESS_CLASSIFY = '''
/**
 * 用真实 Hook 的 stderr 驱动插件：两侧各自演化是这条契约最容易坏的地方。
 * 它不做断言，只把插件给出的 outcome 打成 JSON 交给 Python 侧。
 */
import { pathToFileURL } from 'node:url';

const { apply } = await import(pathToFileURL(process.argv[2]).href);

let handler;
const ctx = {
  on(name, registered) {
    handler = registered;
  },
  shell: {
    resolve(request) {
      return request;
    },
    async run() {
      return {
        exitCode: Number(process.argv[4]),
        stderr: { text: process.argv[3] },
      };
    },
  },
};

apply(ctx, {
  command: 'python -m adapters.dsh.hooks',
  timeoutMs: 30000,
  projectDir: process.argv[5],
});

const exec = {
  name: 'pwsh',
  callId: 'call-1',
  arguments: {},
  signal: undefined,
  agent: { session: { header: { id: 's1', cwd: process.argv[5] } } },
};

const outcome = await handler(
  exec,
  { content: [{ type: 'text', text: 'x' }] },
  async () => ({ kind: 'enter' }),
);
process.stdout.write(JSON.stringify({ outcome }));
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

    找不到基线就是证据不足：事后阶段以 exit 2 结束（`post_error`），而不是"不需要事后核对"。
    被阻断的动作不在 pre 的放行集合里，所以 G2 的成对契约不受这条拒绝影响。
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

    assert post.exit_code == EXIT_BLOCK
    assert post.reason_code == "post_error"
    assert "找不到对应的 pre-check 记录" in post.stderr
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
    # Q6：工作目录一侧的事实由 Python 侧准备——一个**保证不存在**的路径、一个存在但会被假 ctx
    # 在 spawn 之前删掉的路径（竞态），以及一个"存在但不是目录"的路径。只供这条探针使用。
    missing = tmp_root / "missing-workdir"
    shutil.rmtree(missing, ignore_errors=True)
    vanishing = tmp_root / "vanishing-workdir"
    vanishing.mkdir(parents=True, exist_ok=True)
    not_a_dir = tmp_root / "not-a-dir.txt"
    not_a_dir.write_text("我是一个文件，不是目录" + chr(10), encoding="utf-8", newline="")
    completed = subprocess.run(
        [
            _require_node(),
            str(script),
            str(PLUGIN),
            str(tmp_root),
            str(missing),
            str(vanishing),
            str(not_a_dir),
        ],
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


# --------------------------------------------------------------------------- 插件侧契约（Q6）


WORKDIR_COMMAND = "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml"


def _denied_reason(observed: dict, key: str) -> str:
    """取插件给出的拒绝理由：Q6 的断言都落在这一句上。"""

    outcome = observed[key]["outcome"]
    assert outcome["kind"] == "deny", (key, outcome)
    return outcome["reason"]


def test_a_missing_project_dir_is_named_as_a_missing_directory_not_a_missing_node(tmp_root):
    """Q6：真机把「工作目录不存在」报成「找不到 node.exe」，这条用例钉住归因。

    真机原文（14 号文档 §5 Q6，两次会话各 10 次调用逐次一致）：

        policy-hook: Hook 无法执行（spawn <node.exe 的绝对路径> ENOENT），按失败关闭拒绝该工具调用

    而那个 node.exe 存在且可执行；真正不存在的是配置里的 projectDir。Node 的 spawn 在 cwd
    不存在时把 ENOENT 归给**可执行文件**——探针的假 ctx 照搬了这条行为（见 HARNESS），
    所以这里的读数就是真机读数，不是编出来的。
    """

    observed = run_harness(tmp_root)
    entry = observed["workdir_missing_project_dir"]
    reason = _denied_reason(observed, "workdir_missing_project_dir")

    # 前缀是 tools/dsh_sandbox_loop.py 的 SPAWN_DENIED_MARKERS 与集成测试依赖的形态，不许改
    assert reason.startswith("policy-hook: Hook 无法执行（")
    assert reason.endswith("），按失败关闭拒绝该工具调用")
    # 点名的是**目录**，而且真的把那个路径与它的来源写出来
    assert "工作目录不存在：" in reason
    assert "missing-workdir" in reason
    assert "config.projectDir" in reason
    # 「要启动什么」与「在哪个目录启动」分开写
    assert "要启动的命令：" + WORKDIR_COMMAND in reason
    # 明确说 Node 会把 cwd 的 ENOENT 归给可执行文件，且这条报错不能用来判断"命令 / 运行时缺失"
    assert "可执行文件" in reason
    assert "不要据此判断" in reason
    # 预检在 spawn **之前**：真机上那一次 spawn 正是误导的来源
    assert entry["spawnAttempts"] == 0
    assert entry["nextCalls"] == 0


def test_a_missing_session_cwd_is_named_the_same_way_without_project_dir(tmp_root):
    """Q6：(b) 未给 projectDir 时会话 cwd 就是工作目录，它不存在时报的是那个目录。

    同一条用例带一个反向对照：projectDir 存在时它就是工作目录，不存在的会话 cwd 不该
    把一次正常调用变成拒绝（修复不许过度拒绝）。
    """

    observed = run_harness(tmp_root)
    reason = _denied_reason(observed, "workdir_missing_session_cwd")

    assert "工作目录不存在：" in reason
    assert "missing-workdir" in reason
    # 来源要写对：这一次没有 config.projectDir，工作目录来自会话 cwd
    assert "会话 cwd" in reason
    assert observed["workdir_missing_session_cwd"]["spawnAttempts"] == 0

    control = observed["workdir_project_dir_wins"]
    assert control["outcome"] == {"kind": "enter"}
    assert control["nextCalls"] == 1
    assert control["spawnAttempts"] == 1


def test_the_catch_path_blames_the_command_side_when_the_workdir_is_intact(tmp_root):
    """Q6：(c) 工作目录没问题而 spawn 仍然抛错时，归因必须在「要启动的命令」那一侧。

    用的是真机原文里那个错误串（spawn 可执行文件 ENOENT）：**同一条报错**，工作目录的事实
    不同，理由的归因就必须不同——这正是这次修复要建立的东西。
    """

    observed = run_harness(tmp_root)
    entry = observed["workdir_intact_spawn_error"]
    reason = _denied_reason(observed, "workdir_intact_spawn_error")

    # 工作目录这一侧被**排除**（它真的存在），而不是被说成"找不到"
    assert "工作目录已确认存在" in reason
    assert "问题不在目录这一侧" in reason
    # 原始报错一个字都不许吞：定位要看得见原文
    assert "spawn " in reason
    assert "ENOENT" in reason
    # 这一次真的去 spawn 了（失败来自 spawn，不是预检）
    assert entry["spawnAttempts"] == 1

    # 竞态：预检通过之后目录被删掉——catch 分支必须重新看一眼，理由仍然点名那个目录
    vanished = _denied_reason(observed, "workdir_vanished_before_spawn")
    assert "工作目录不存在：" in vanished
    assert "vanishing-workdir" in vanished
    assert "spawn " in vanished
    assert observed["workdir_vanished_before_spawn"]["spawnAttempts"] == 1


def test_a_hook_that_cannot_name_its_workdir_is_still_fail_closed(tmp_root):
    """Q6：(d) 理由变准了，判定一点没松——pre 仍然 deny、post 仍然 block。"""

    observed = run_harness(tmp_root)
    pre = observed["workdir_missing_project_dir"]
    post = observed["workdir_missing_project_dir_post"]

    assert pre["outcome"]["kind"] == "deny"
    assert pre["nextCalls"] == 0  # 没有委托给下一个监听者 = 没有放行
    assert post["outcome"]["kind"] == "block"
    assert post["nextCalls"] == 0
    # post 阶段副作用已发生：理由交给模型，且不假装回滚
    assert "工作目录不存在" in post["outcome"]["feedback"][0]["text"]


# --------------------------------------------------------------------------- 跨侧契约（Q6：理由文本 ↔ 闭环分类器）


# 修前真机原文（14 号文档 §5 Q6；node.exe 存在且可执行，真正不存在的是工作目录）：
# 闭环必须把它判成"归不了因"——这段文本里**根本没有**目录这一侧的事实。
BEFORE_FIX_REASON = (
    "policy-hook: Hook 无法执行（spawn C:\\Program Files\\nodejs\\node.exe ENOENT），"
    "按失败关闭拒绝该工具调用"
)


def _loop_classify(loop: Any, logs: Path, reason: str) -> tuple[str | None, str | None]:
    """把一条理由写进闭环的日志目录并驱动它的分类入口，返回 (kind, workdir)。"""

    for stale in logs.glob("*.txt"):
        stale.unlink()
    (logs / "hook-log.txt").write_text(
        "dsh 的原始日志行" + chr(10) + reason + chr(10), encoding="utf-8", newline=""
    )
    failure = loop.hook_spawn_failure()
    if failure is None:
        return None, None
    return failure.kind, failure.workdir


def test_the_hook_failure_reason_is_classified_by_the_sandbox_loop(tmp_root, monkeypatch):
    """Q6 跨侧契约：插件的**真实理由文本**必须被 tools/dsh_sandbox_loop.py 正确分类。

    为什么必须有这条：两侧各自的用例都用自家夹具——插件侧断言自己的措辞，闭环侧拿**手抄**的
    措辞当夹具。措辞一改，两边都还绿，接缝却断了，而断掉的方向最坏是"配置错误被读成环境限制
    → 环境跳过"。所以这里：真 node 驱动真插件拿到**真实理由**，再喂给闭环的分类入口
    （只读 import；`LOGS` 用 monkeypatch 注入临时目录，与
    tests/integration/test_dsh_sandbox_loop.py 同一手法）。

    三类处置不同，归错类就是新的误导：工作目录不可用 = 接线/配置错（按真失败收场）；
    `spawn EPERM` = 受限沙箱禁止管道 stdio（**唯一**允许环境跳过的一类）；
    其余一律"归不了因"——不能猜。
    """

    observed = run_harness(tmp_root)
    # 函数内导入：闭环是另一侧的产物，收集期硬依赖会让"这条契约缺失"与"别的用例带崩"分不开
    # （与读 VERDICT_PREFIX 的那条用例同一考虑）。
    import dsh_sandbox_loop as loop

    logs = tmp_root / "loop-logs"
    logs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(loop, "LOGS", logs)

    # ① 工作目录不可用（三类）→ 工作目录类，而且闭环要把**那个目录**解出来（不是只给个类别）
    for label, key, expected_name in (
        ("projectDir 不存在", "workdir_missing_project_dir", "missing-workdir"),
        ("projectDir 是个文件", "workdir_project_dir_is_a_file", "not-a-dir.txt"),
        ("未给 projectDir、会话 cwd 不存在", "workdir_missing_session_cwd", "missing-workdir"),
    ):
        reason = _denied_reason(observed, key)
        kind, workdir = _loop_classify(loop, logs, reason)
        assert kind == "hook_workdir_unusable", (label, reason, kind)
        assert workdir is not None, (label, reason)
        assert Path(workdir).name == expected_name, (label, workdir)

    # ② 目录正常 + spawn EPERM → 沙箱类（唯一允许环境跳过的一类）
    reason = _denied_reason(observed, "workdir_intact_spawn_eperm")
    kind, _ = _loop_classify(loop, logs, reason)
    assert kind == "sandbox_pipe_stdio_denied", (reason, kind)

    # ③ 归不了因：目录正常 + ENOENT，以及**修前那句真机原文**。
    #    修前那句里没有目录这一侧的事实，被读成"工作目录不可用"就是回到修前的误导。
    for label, reason in (
        ("目录正常 + spawn ENOENT", _denied_reason(observed, "workdir_intact_spawn_error")),
        ("修前真机原文", BEFORE_FIX_REASON),
    ):
        kind, _ = _loop_classify(loop, logs, reason)
        assert kind is None, (label, reason, kind)

    # ④ 变异（只在测试内改字符串，不改仓库源码）：措辞一改，分类必须落到"归不了因"——
    #    既不静默通过、也不猜成任何一类。这是文本契约被改动时的**安全**失败方向。
    tampered = _denied_reason(observed, "workdir_missing_project_dir").replace(
        "工作目录不存在", "目标目录不可用"
    )
    kind, _ = _loop_classify(loop, logs, tampered)
    assert kind is None, tampered


def test_the_plugin_forwards_the_exit_facts_from_the_tool_result_value(tmp_root):
    """N16：退出码一直在 result.value 里，插件必须把它转发进 PostToolUse 载荷。

    修前插件只把 result.content 折成文本，Python 侧永远拿不到退出码，
    于是 exit_code_zero 必然判 False、命令输出被策略错误替换。
    形状不认、拿不到、不是整数时**一个字段都不带**：不带不等于填一个假值。
    """

    observed = run_harness(tmp_root)

    zero = observed["post_exit_zero"]["payload"]
    assert zero["tool_exit_code"] == 0
    assert zero["tool_timed_out"] is False
    assert zero["tool_aborted"] is False
    assert zero["tool_result_kind"] == "foreground"
    # signal=null 不是字符串：形状不认就不带这个字段
    assert "tool_signal" not in zero
    # 结果文本仍然照旧转发（退出事实是追加的，不是替换）
    assert zero["tool_response"] == "3 passed in 0.42s"

    assert observed["post_exit_one"]["payload"]["tool_exit_code"] == 1
    assert observed["post_timed_out"]["payload"]["tool_timed_out"] is True
    assert observed["post_timed_out"]["payload"]["tool_exit_code"] == 1

    # 后台任务在 PostToolUse 时刻还没有退出码：一个都不许编
    background = observed["post_background"]["payload"]
    assert background["tool_result_kind"] == "background"
    assert "tool_exit_code" not in background
    assert "tool_timed_out" not in background

    # isError 的结果没有 value
    failed = observed["post_failed_result"]["payload"]
    assert "tool_exit_code" not in failed
    assert "tool_result_kind" not in failed

    # 形状不认（字符串退出码、数字 signal、字符串布尔）一律不带
    bad = observed["post_bad_shapes"]["payload"]
    for key in ("tool_exit_code", "tool_timed_out", "tool_aborted", "tool_signal"):
        assert key not in bad, key
    assert bad["tool_result_kind"] == "foreground"


def test_the_plugin_classifies_a_block_from_the_machine_readable_verdict(tmp_root):
    """N18：理由分类不再依赖退出码保真；任何非 0 退出仍然一律拒绝。

    修前：本机 dsh 把 Hook 的 exit 2 压成 1，插件只能写"Hook 退出码 1，未知状态按失败关闭
    拒绝"——模型看到的是"未知状态"而不是"策略阻断"。判定行是 Hook 自己写的策略事实，
    把两者分开之后措辞恢复可诊断；读不到 / 读不懂 / 版本不认识仍然回到未知状态（拒绝不变）。
    """

    observed = run_harness(tmp_root)

    # exit 2 + 判定行：策略阻断 + 原因码，且判定行本身不进给模型的理由正文
    blocked = observed["pre_block_with_verdict"]["outcome"]
    assert blocked["kind"] == "deny"
    assert blocked["reason"].startswith("策略阻断（policy_block）")
    assert "blocked by ARCH-001" in blocked["reason"]
    assert "VERDICT" not in blocked["reason"]
    assert observed["pre_block_with_verdict"]["nextCalls"] == 0

    # 本机真实情形：dsh 把 2 压成 1 —— 判定行让理由仍然是"策略阻断"
    normalized = observed["pre_normalized_exit_with_verdict"]["outcome"]
    assert normalized["kind"] == "deny"
    assert "策略阻断（policy_block）" in normalized["reason"]
    assert "与判定行不一致" in normalized["reason"]
    assert observed["pre_normalized_exit_with_verdict"]["nextCalls"] == 0

    # 只有判定行、没有正文：理由仍然是策略阻断
    only = observed["pre_block_verdict_only"]["outcome"]
    assert only["reason"] == "策略阻断（policy_block）"

    # 判定行坏掉 / 版本不认识 = 没有判定 → 未知状态，仍然拒绝
    broken = observed["pre_broken_verdict"]["outcome"]
    assert broken["kind"] == "deny"
    assert "未知状态" in broken["reason"]
    unknown = observed["pre_unknown_verdict_version"]["outcome"]
    assert unknown["kind"] == "deny"
    assert "未知状态" in unknown["reason"]
    assert "策略阻断" not in unknown["reason"]

    # post 阶段同一套分类；副作用已发生，所以只能是 block + feedback
    post = observed["post_normalized_exit_with_verdict"]["outcome"]
    assert post["kind"] == "block"
    assert "策略阻断（post_repair_required）" in post["feedback"][0]["text"]

    # 反向对照：判定行不会把 exit 0 变成拒绝
    assert observed["pre_allow_with_stray_verdict"]["outcome"] == {"kind": "enter"}
    assert observed["pre_allow_with_stray_verdict"]["nextCalls"] == 1


def test_the_plugin_classifies_the_real_hook_stderr(dsh_config_path, dsh_project, tmp_root):
    """N18：拿**真实 Hook 产出的 stderr** 驱动插件，理由必须是「策略阻断 + 原因码」。

    这条契约跨两种语言：Python 侧改判定行格式、插件侧改前缀，各自单测都会绿，接缝却断了。
    所以这里跑真 CLI 拿 stderr，再喂给真插件（真实 node + 假 ctx），并模拟本机的退出码归一化
    （Hook 明明退出 2，dsh 侧读到的是 1，见 README §2.3.1）。
    """

    from adapters.dsh.hooks import VERDICT_PREFIX

    hooks_json = REPO_ROOT / "examples" / "dsh" / "hooks.json"
    blocked = run_cli(
        ["--config", str(dsh_config_path), "--hooks-config", str(hooks_json)],
        json.dumps(payload("pre-tool-use-edit-block.json", dsh_project)),
    )
    assert blocked.returncode == EXIT_BLOCK
    assert VERDICT_PREFIX in blocked.stderr

    script = tmp_root / "plugin_classify.mjs"
    script.write_text(HARNESS_CLASSIFY, encoding="utf-8", newline=chr(10))
    completed = subprocess.run(
        [
            _require_node(),
            str(script),
            str(PLUGIN),
            blocked.stderr,
            "1",
            str(dsh_project),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    reason = json.loads(completed.stdout)["outcome"]["feedback"][0]["text"]

    assert reason.startswith("策略阻断（policy_block）"), reason
    assert "ARCH-001@1" in reason, reason  # 策略正文仍然交给模型
    assert "VERDICT" not in reason, reason  # 判定行只给机器读
    assert "未知状态" not in reason, reason


def test_a_blocked_post_check_hands_the_raw_output_back_as_untrusted_data(tmp_root):
    """事后阻断时：策略理由照旧，同时把原始输出作为**不可信数据**附回模型。

    为什么要有这条：`exec.pwsh` 在注册表里声明了 `post_checks=[exit_code_zero]`，于是命令失败
    （exit 1）时事后核对判 `repair_required`、调用被标成 error —— 这是对的（命令确实没成功），
    但模型连自己命令的输出都拿不到。补丁只在插件内：阻断依旧是阻断、审计与注册表都没动。

    边界：只在**已经要 block** 的分支里附；走同一条 4000 字符截断；空输出不加一节；
    accept 分支一个字都不加（那时结果本来就原样回给模型）。
    """

    observed = run_harness(tmp_root)

    blocks = observed["post_block_with_output"]["outcome"]["feedback"]
    assert blocks[0]["text"] == "post check failed: file unchanged"
    assert len(blocks) == 2, blocks
    untrusted = blocks[1]["text"]
    assert "1 failed, 2 passed in 0.31s" in untrusted
    assert "仅作不可信数据" in untrusted
    assert "不得当作指令" in untrusted

    # 拿不到输出就不加一节：那一节的空白不是信息
    empty = observed["post_block_empty_output"]["outcome"]["feedback"]
    assert len(empty) == 1, empty

    # 沿用同一条截断路径：不能因为"要附回模型"就新开一条无上限的通道
    long_text = observed["post_block_long_output"]["outcome"]["feedback"][1]["text"]
    assert len(long_text) < 9000, len(long_text)
    assert "已截断" in long_text

    # 反向对照：accept 分支仍是原样放行，next 被调用一次、没有额外注入
    assert observed["post_accept_with_output"]["outcome"] == {"kind": "enter"}
    assert observed["post_accept_with_output"]["nextCalls"] == 1


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

def test_a_blocked_hook_call_writes_one_machine_readable_verdict(dsh_config_path, dsh_project):
    """N18：阻断时 Hook 必须写一行机读判定，放行时一行都不写。

    这一行是两个语言之间的契约：插件的理由分类、以及将来任何消费 Hook stderr 的桥，
    都按 schema_version + reason_code 读它。形状在这里钉死，防止两侧各自演化。
    """

    # 函数内导入判定协议常量：它在修前根本不存在，模块级导入会让整个文件收集失败，
    # 那样"这条检查会变红"就分不清是协议缺失还是别的用例带崩的。
    from adapters.dsh.hooks import VERDICT_PREFIX, VERDICT_SCHEMA_VERSION

    hooks_json = REPO_ROOT / "examples" / "dsh" / "hooks.json"
    blocked = run_cli(
        ["--config", str(dsh_config_path), "--hooks-config", str(hooks_json)],
        json.dumps(payload("pre-tool-use-edit-block.json", dsh_project)),
    )

    assert blocked.returncode == EXIT_BLOCK
    lines = [line for line in blocked.stderr.splitlines() if line.startswith(VERDICT_PREFIX)]
    assert len(lines) == 1, blocked.stderr
    verdict = json.loads(lines[0][len(VERDICT_PREFIX):])
    assert verdict == {
        "schema_version": VERDICT_SCHEMA_VERSION,
        "reason_code": "policy_block",
        "exit_code": EXIT_BLOCK,
        "hook_event": "PreToolUse",
    }

    allowed = run_cli(
        ["--config", str(dsh_config_path), "--hooks-config", str(hooks_json)],
        json.dumps(payload("pre-tool-use-edit-allow.json", dsh_project)),
    )
    assert allowed.returncode == EXIT_ALLOW, allowed.stderr
    assert VERDICT_PREFIX not in allowed.stderr


# ------------------------------------------------------------------- 台阶 2：归因闭集与核验前置
#
# Q6 修好的是**理由文本**（给模型读的一句中文）。文本有两个弱点：消费方只能写正则去解析它，
# 而且它说不出"这条归因凭什么成立"。台阶 2 把同一批事实升格成结构化的 `origin`
# （设计《控制面重构方案》§3.4）：闭集 + 核验前置 + 写不出 fix 的 origin 不许存在。
#
# 下面这个探针与 HARNESS 的 Q6 段落同一手法（真 node 驱动真插件、假 ctx 只观察不断言），
# 差别只有一个：它把 outcome —— 连同新增的 origin —— 整份打成 JSON 交给 Python 侧。
ORIGIN_FAMILIES = ("platform", "agent_runtime", "host", "project", "unknown_origin")
ORIGIN_KEYS = {"kind", "origin", "owner", "object", "observation", "fix", "causal_link"}
ORIGIN_OBJECT_KEYS = {"kind", "value", "source"}
ORIGIN_OBSERVATION_KEYS = {"method", "result", "verified", "verified_at", "run_scoped"}
ORIGIN_METHODS = {"stat", "load", "spawn", "read", "none"}

# 场景 → 期望取值（六个拒绝场景，逐条断言；⑦ 反向对照单列一条用例）。
ORIGIN_SCENARIOS = (
    ("projectDir 不存在", "origin_missing_project_dir", "project.workdir_missing", "stat"),
    ("projectDir 是个文件", "origin_project_dir_is_a_file", "project.workdir_missing", "stat"),
    (
        "未给 projectDir、会话 cwd 不存在",
        "origin_missing_session_cwd",
        "project.workdir_missing",
        "stat",
    ),
    ("目录正常 + spawn ENOENT", "origin_intact_spawn_error", "agent_runtime.spawn_failed", "spawn"),
    ("竞态：预检后被删", "origin_vanished_before_spawn", "project.workdir_missing", "stat"),
    ("目录正常 + spawn EPERM", "origin_intact_spawn_eperm", "agent_runtime.spawn_denied", "spawn"),
)

HARNESS_ORIGIN = '''/**
 * 台阶 2 探针：用真 node 驱动真插件，观察**结构化归因**（origin）。
 *
 * 与 HARNESS 的 Q6 段落同一手法：假 ctx 只观察、不断言，断言全在 Python 侧。
 * 差别只有一个——它把 outcome（连同新增的 origin）整份打成 JSON 交给 Python。
 * argv: <plugin.mjs> <存在的目录> <不存在的目录> <会被删掉的目录> <一个文件>
 */
import { existsSync, rmSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const { apply, createRunHook } = await import(pathToFileURL(process.argv[2]).href);

const WORKDIR_COMMAND = 'python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml';

function mountForWorkdir(projectDir, sessionCwd) {
  const state = { exitCode: 0, stderr: '', throwError: '', vanishWorkdir: false };
  const registrations = {};
  const calls = [];
  const localCtx = {
    on(name, handler) {
      registrations[name] = handler;
    },
    shell: {
      resolve(request) {
        return request;
      },
      async run(request) {
        calls.push(request);
        if (state.vanishWorkdir && request.workdir !== undefined) {
          // 竞态：预检时目录还在，spawn 之前没了。
          rmSync(request.workdir, { recursive: true, force: true });
        }
        if (state.throwError !== '') {
          throw new Error(state.throwError);
        }
        if (request.workdir !== undefined && !existsSync(request.workdir)) {
          // 真实 Node：cwd 不存在 → ENOENT，但报的是**可执行文件**。
          throw new Error('spawn ' + process.execPath + ' ENOENT');
        }
        return { exitCode: state.exitCode, stderr: { text: state.stderr } };
      },
    },
  };
  const config = { command: WORKDIR_COMMAND, timeoutMs: 30000, projectDir };
  apply(localCtx, config);
  // runHook 的返回值里带着 origin，而 dsh 只认 handler 转译出来的 deny / block：
  // 这里用同一个假 ctx 再装配一次，直接观察那条返回值（插件为此导出了 createRunHook）。
  const runHook = createRunHook(localCtx, config);
  const exec = {
    name: 'edit',
    callId: 'call-origin',
    arguments: { file_path: 'src/shop/order_controller.py', old_string: 'a', new_string: 'b' },
    signal: undefined,
    agent: { session: { header: { id: 'sess-origin', cwd: sessionCwd } } },
  };
  const drive = async (event, result) => {
    let nextCalls = 0;
    const next = async () => {
      nextCalls += 1;
      return { kind: 'enter' };
    };
    const before = calls.length;
    const outcome =
      event === 'pre'
        ? await registrations['tools/pre-execute'](exec, next)
        : await registrations['tools/post-execute'](exec, result, next);
    return { outcome, nextCalls, spawnAttempts: calls.length - before };
  };
  const driveHook = async () => {
    const before = calls.length;
    const outcome = await runHook(exec, { hookEvent: 'PreToolUse', fields: {} });
    return { outcome, spawnAttempts: calls.length - before };
  };
  return {
    state,
    drivePre: () => drive('pre', undefined),
    drivePost: (result) => drive('post', result),
    driveHook,
  };
}

const existingWorkdir = process.argv[3];
const missingWorkdir = process.argv[4];
const vanishingWorkdir = process.argv[5];
const notADir = process.argv[6];

const observations = {};

// ① projectDir 不存在 → 目录这一侧（证据必须是那次真执行的 stat）
const missingProjectDir = mountForWorkdir(missingWorkdir, existingWorkdir);
observations.origin_missing_project_dir = await missingProjectDir.driveHook();

// ② projectDir 是个文件：同属"工作目录不可用"，但不是"不存在"
observations.origin_project_dir_is_a_file = await mountForWorkdir(
  notADir,
  existingWorkdir,
).driveHook();

// ③ 未给 projectDir、会话 cwd 不存在：来源必须写明是会话 cwd
observations.origin_missing_session_cwd = await mountForWorkdir(
  undefined,
  missingWorkdir,
).driveHook();

// ④ 目录正常 + spawn 抛 ENOENT（真机上那个会把人带偏的报错）→ 指控不许指向目录
const intactSpawnError = mountForWorkdir(existingWorkdir, existingWorkdir);
intactSpawnError.state.throwError = 'spawn ' + process.execPath + ' ENOENT';
observations.origin_intact_spawn_error = await intactSpawnError.driveHook();

// ⑤ 竞态：预检通过之后目录被删掉 → catch 分支复查后仍然归到目录这一侧
const vanished = mountForWorkdir(vanishingWorkdir, vanishingWorkdir);
vanished.state.vanishWorkdir = true;
observations.origin_vanished_before_spawn = await vanished.driveHook();

// ⑥ 目录正常 + spawn 抛 EPERM（受限沙箱禁止管道 stdio）：不是目录那一侧的问题
const intactEperm = mountForWorkdir(existingWorkdir, existingWorkdir);
intactEperm.state.throwError = 'spawn EPERM';
observations.origin_intact_spawn_eperm = await intactEperm.driveHook();

// ⑦ 反向对照：一切正常（放行）→ **不许**给放行的调用编造归因
observations.origin_allowed_control = await mountForWorkdir(
  existingWorkdir,
  existingWorkdir,
).driveHook();

// 接线形状：dsh 真正读到的是 handler 的两种形状（deny / block），它与 runHook 的返回值分开观察。
observations.wire_deny = await mountForWorkdir(missingWorkdir, existingWorkdir).drivePre();
observations.wire_block = await mountForWorkdir(missingWorkdir, existingWorkdir).drivePost({
  content: [],
});
observations.wire_allow_pre = await mountForWorkdir(existingWorkdir, existingWorkdir).drivePre();
observations.wire_allow_post = await mountForWorkdir(
  existingWorkdir,
  existingWorkdir,
).drivePost({ content: [{ type: 'text', text: 'ok' }] });

// ⑧ 空串 projectDir 与「没写」同义：应当回落到会话 cwd 并照常 spawn（而不是把 "" 当成
//    声明过的目录，落进 inspectWorkdir 的 unknown_origin 且 spawn 0 次）。
observations.origin_blank_project_dir = await mountForWorkdir('', existingWorkdir).driveHook();

process.stdout.write(JSON.stringify(observations));
'''


def run_origin_harness(tmp_root: Path, plugin: Path | None = None) -> dict:
    """驱动 origin 探针：真 node + 真插件（plugin 参数用来喂一棵变异过的临时副本）。"""

    script = tmp_root / "plugin_origin_harness.mjs"
    script.write_text(HARNESS_ORIGIN, encoding="utf-8", newline=chr(10))
    missing = tmp_root / "missing-workdir"
    shutil.rmtree(missing, ignore_errors=True)
    vanishing = tmp_root / "vanishing-workdir"
    vanishing.mkdir(parents=True, exist_ok=True)
    not_a_dir = tmp_root / "not-a-dir.txt"
    not_a_dir.write_text("我是一个文件，不是目录" + chr(10), encoding="utf-8", newline="")
    completed = subprocess.run(
        [
            _require_node(),
            str(script),
            str(PLUGIN if plugin is None else plugin),
            str(tmp_root),
            str(missing),
            str(vanishing),
            str(not_a_dir),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _origin_of(observed: dict, key: str) -> dict:
    """取 runHook 那条返回值里的 origin：台阶 2 的断言都落在它上面。

    为什么不是 handler 那条：dsh 只认 deny / block 两种形状，handler 也只转译 reason——
    origin 只能在 runHook 的返回值上观察。插件为此导出了 createRunHook 这个显式接缝
    （apply 的返回值与两种形状都没变）。
    """

    outcome = observed[key]["outcome"]
    assert outcome["allowed"] is False, (key, outcome)
    # runHook 的返回值只多一个 origin 键；origin 不许混进 reason 里冒充别的东西
    assert set(outcome) == {"allowed", "reason", "origin"}, sorted(outcome)
    return outcome["origin"]


def _assert_origin_shape(origin: dict) -> None:
    """形状是跨语言契约：多一个键、少一个键都算违约（与 Python 侧同一份判据）。"""

    import datetime

    assert isinstance(origin, dict), origin
    assert set(origin) == ORIGIN_KEYS, sorted(origin)
    assert origin["kind"] == "platform.attribution"
    assert isinstance(origin["owner"], str) and origin["owner"] != ""
    assert set(origin["object"]) == ORIGIN_OBJECT_KEYS, sorted(origin["object"])
    observation = origin["observation"]
    assert set(observation) == ORIGIN_OBSERVATION_KEYS, sorted(observation)
    assert observation["method"] in ORIGIN_METHODS, observation
    assert isinstance(observation["result"], str) and observation["result"] != ""
    assert observation["run_scoped"] is True
    # verified_at 必须来自真实调用 new Date().toISOString()：能解析、带时区、而且是"刚刚"
    parsed = datetime.datetime.fromisoformat(str(observation["verified_at"]).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, observation["verified_at"]
    now = datetime.datetime.now(datetime.timezone.utc)
    assert abs((now - parsed).total_seconds()) < 600, observation["verified_at"]
    # 闭集：unknown_origin，或者"族.后缀"（族必须是五族之一、后缀非空）
    value = origin["origin"]
    if value != "unknown_origin":
        family, _, suffix = value.partition(".")
        assert family in ORIGIN_FAMILIES and suffix != "", value
    # fix 非空，而且必须是可执行的**具体**动作（"请联系管理员"不是修复动作）
    assert isinstance(origin["fix"], str) and origin["fix"].strip() != "", origin
    assert "联系管理员" not in origin["fix"]
    assert origin["causal_link"] in {"proven", "unproven"}


def test_a_blank_project_dir_behaves_like_an_undeclared_one(tmp_root) -> None:
    """`projectDir: ""`（或非字符串）与「没写」同义：回落到会话 cwd，而不是声明了一个空目录。

    头部文档写的是「不填则用会话工作目录」，而 `config.projectDir ?? cwd` 只兜 null/undefined：
    空串会被当成「声明过了」——会话 cwd 永不被采纳、cwdSource 谎报成 config.projectDir、
    `workdir: ""` 一路传给 spawn，最后连"这次在哪个目录启动"都归因不出来。
    """

    observed = run_origin_harness(tmp_root)
    outcome = observed["origin_blank_project_dir"]

    # 回落成功：真的 spawn 了一次、决策是放行，而且**没有**给它编一条归因
    assert outcome["spawnAttempts"] == 1, outcome
    assert outcome["outcome"]["allowed"] is True, outcome
    assert set(outcome["outcome"]) == {"allowed", "reason"}, outcome


def test_every_workdir_denial_carries_a_verified_origin_from_the_closed_set(tmp_root):
    """台阶 2：六个工作目录场景各带一条 origin——形状、闭集、核验与因果链逐条对上。

    修前这些事实只活在一句中文理由里：消费方要写正则去解析它，解析出来也不知道
    "这条归因凭什么成立"。这里断言的是同一批事实的机读形态。
    """

    observed = run_origin_harness(tmp_root)

    for label, key, expected, method in ORIGIN_SCENARIOS:
        origin = _origin_of(observed, key)
        _assert_origin_shape(origin)
        assert origin["origin"] == expected, (label, origin)
        assert origin["observation"]["method"] == method, (label, origin)
        # 每条指控都真的核验过（stat / spawn 真执行），而且因果链是建立起来的
        assert origin["observation"]["verified"] is True, (label, origin)
        assert origin["causal_link"] == "proven", (label, origin)
        assert origin["fix"].strip() != "", (label, origin)


def test_a_missing_project_dir_origin_is_earned_by_a_stat_before_it_is_alleged(tmp_root):
    """Q6 的文本归因升格：说"目录不存在"之前先 statSync 它，证据进 observation。"""

    observed = run_origin_harness(tmp_root)
    origin = _origin_of(observed, "origin_missing_project_dir")

    assert origin["origin"] == "project.workdir_missing"
    assert origin["observation"]["method"] == "stat"
    assert origin["observation"]["verified"] is True
    assert "ENOENT" in origin["observation"]["result"], origin
    assert origin["object"]["kind"] == "workdir", origin
    assert origin["object"]["value"] == "missing-workdir", origin
    assert origin["object"]["source"] == "config.projectDir", origin
    # 预检就拦下了：真机上那一次 spawn 只会给出误导的 ENOENT
    assert observed["origin_missing_project_dir"]["spawnAttempts"] == 0


def test_a_project_dir_that_is_a_file_is_the_same_side_with_a_different_observation(tmp_root):
    """同属"工作目录不可用"（usable=false），但观测结果不同：路径在、只是不是目录。"""

    observed = run_origin_harness(tmp_root)
    origin = _origin_of(observed, "origin_project_dir_is_a_file")

    assert origin["origin"] == "project.workdir_missing"
    assert origin["observation"]["method"] == "stat"
    assert "不是一个目录" in origin["observation"]["result"], origin
    assert origin["object"]["value"] == "not-a-dir.txt", origin
    assert observed["origin_project_dir_is_a_file"]["spawnAttempts"] == 0


def test_a_missing_session_cwd_names_the_session_cwd_as_the_source(tmp_root):
    """来源必须写对：这一次没有 config.projectDir，工作目录来自会话 cwd。"""

    observed = run_origin_harness(tmp_root)
    origin = _origin_of(observed, "origin_missing_session_cwd")

    assert origin["origin"] == "project.workdir_missing"
    assert "会话 cwd" in origin["object"]["source"], origin
    assert origin["object"]["value"] == "missing-workdir", origin
    assert observed["origin_missing_session_cwd"]["spawnAttempts"] == 0


def test_an_intact_workdir_never_gets_blamed_for_a_spawn_error(tmp_root):
    """核验前置：目录这一侧被证伪之后，指控只能落在「要启动的命令」这一侧。"""

    observed = run_origin_harness(tmp_root)
    origin = _origin_of(observed, "origin_intact_spawn_error")

    assert origin["origin"] == "agent_runtime.spawn_failed"
    assert origin["observation"]["method"] == "spawn"
    assert origin["observation"]["verified"] is True
    assert "ENOENT" in origin["observation"]["result"], origin
    # 被指控的对象是**命令**，不是目录——照抄 spawn 的 ENOENT 就会指错对象
    assert origin["object"]["kind"] == "command", origin
    assert origin["object"]["value"] == WORKDIR_COMMAND, origin
    assert origin["object"]["source"] == "config.command", origin
    assert observed["origin_intact_spawn_error"]["spawnAttempts"] == 1


def test_a_workdir_that_vanishes_after_the_precheck_is_re_verified(tmp_root):
    """竞态：预检通过之后目录被删掉，catch 分支复查一次，归因仍然指向那个目录。"""

    observed = run_origin_harness(tmp_root)
    origin = _origin_of(observed, "origin_vanished_before_spawn")

    assert origin["origin"] == "project.workdir_missing"
    assert origin["observation"]["method"] == "stat"
    assert origin["observation"]["verified"] is True
    assert origin["object"]["value"] == "vanishing-workdir", origin
    # 这一次真的去 spawn 了：是 catch 分支复查出来的，不是预检
    assert observed["origin_vanished_before_spawn"]["spawnAttempts"] == 1


def test_spawn_eperm_is_attributed_to_the_sandbox_not_to_the_workdir(tmp_root):
    """受限沙箱禁止管道 stdio：EPERM 属于 agent_runtime 那一侧，不是目录的毛病。"""

    observed = run_origin_harness(tmp_root)
    origin = _origin_of(observed, "origin_intact_spawn_eperm")

    assert origin["origin"] == "agent_runtime.spawn_denied"
    assert "EPERM" in origin["observation"]["result"], origin
    assert origin["object"]["kind"] == "command", origin
    assert observed["origin_intact_spawn_eperm"]["spawnAttempts"] == 1


def test_an_allowed_call_carries_no_origin_at_all(tmp_root):
    """反向对照：不许给放行的调用编造归因——"没有失败"不等于"有一条归因"。"""

    observed = run_origin_harness(tmp_root)

    control = observed["origin_allowed_control"]
    assert control["outcome"] == {"allowed": True, "reason": ""}
    assert "origin" not in control["outcome"]
    assert control["spawnAttempts"] == 1

    # handler 路径同样一个字没多：pre 委托给下一个监听者，post 原样放行
    allow_pre = observed["wire_allow_pre"]
    assert allow_pre["outcome"] == {"kind": "enter"}
    assert allow_pre["nextCalls"] == 1
    assert allow_pre["spawnAttempts"] == 1
    allow_post = observed["wire_allow_post"]
    assert allow_post["outcome"] == {"kind": "enter"}
    assert allow_post["nextCalls"] == 1


def test_deny_and_block_keep_their_wire_shape_without_origin(tmp_root):
    """接线只多一个键：runHook 的返回值多 origin，dsh 认的 deny / block 形状一个字不改。"""

    observed = run_origin_harness(tmp_root)

    # pre：拒绝，handler 交回给 dsh 的仍然是 {kind:'deny', reason}
    deny = observed["wire_deny"]["outcome"]
    assert set(deny) == {"kind", "reason"}, sorted(deny)
    assert deny["kind"] == "deny"
    assert deny["reason"].startswith("policy-hook: Hook 无法执行（")
    assert observed["wire_deny"]["nextCalls"] == 0
    assert observed["wire_deny"]["spawnAttempts"] == 0

    # post：副作用已发生，只能是 {kind:'block', feedback:[...]}，origin 不许塞进去
    block = observed["wire_block"]["outcome"]
    assert set(block) == {"kind", "feedback"}, sorted(block)
    assert block["kind"] == "block"
    assert block["feedback"][0]["type"] == "text"
    assert "工作目录不存在" in block["feedback"][0]["text"]
    assert observed["wire_block"]["nextCalls"] == 0


def _tampered_plugin(tmp_root: Path, filename: str, needle: str, replacement: str) -> Path:
    """在**临时副本**上做变异：仓库源码一个字不动（与既有那条"措辞变异"用例同一纪律）。"""

    source = PLUGIN.read_text(encoding="utf-8")
    assert needle in source, needle
    mutated = source.replace(needle, replacement)
    assert mutated != source, needle
    target = tmp_root / filename
    target.write_text(mutated, encoding="utf-8", newline=chr(10))
    return target


def test_an_origin_without_an_executable_fix_falls_back_to_unknown_origin(tmp_root):
    """硬规则的自证：fix 为空时插件**不许**产出那条指控，只能落 unknown_origin。

    证明方式是显式变异：把 FIX_WORKDIR_MISSING 清空（只在临时副本上），同一个探针重跑。
    对照是未变异那一次的读数——它必须是 project.workdir_missing。
    """

    import re

    observed = run_origin_harness(tmp_root)
    control = _origin_of(observed, "origin_missing_project_dir")
    assert control["origin"] == "project.workdir_missing"

    source = PLUGIN.read_text(encoding="utf-8")
    assert "const FIX_WORKDIR_MISSING = " in source
    tampered_source, count = re.subn(
        r"^const FIX_WORKDIR_MISSING = .*$",
        "const FIX_WORKDIR_MISSING = '';",
        source,
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1, "变异没有生效：FIX_WORKDIR_MISSING 的写法变了？"
    tampered = tmp_root / "policy-hook.plugin.no-fix.mjs"
    tampered.write_text(tampered_source, encoding="utf-8", newline=chr(10))

    mutated = run_origin_harness(tmp_root, plugin=tampered)
    origin = _origin_of(mutated, "origin_missing_project_dir")
    _assert_origin_shape(origin)
    assert origin["origin"] == "unknown_origin", origin
    # 作废是整体的：因果链、核验、fix 一起降级，fix 仍然是一条**具体动作**
    assert origin["causal_link"] == "unproven", origin
    assert origin["observation"]["verified"] is False, origin
    assert "修复动作" in origin["fix"], origin
    # 文字契约不受影响：机读孪生降级了，给模型的那句话一个字没变
    assert (
        mutated["origin_missing_project_dir"]["outcome"]["reason"]
        == observed["origin_missing_project_dir"]["outcome"]["reason"]
    )


def test_an_origin_value_outside_the_closed_set_falls_back_to_unknown_origin(tmp_root):
    """闭集的自证：把取值改成一个闭集外的字符串，插件**不许**把它原样吐出来。"""

    tampered = _tampered_plugin(
        tmp_root,
        "policy-hook.plugin.out-of-set.mjs",
        "origin: 'project.workdir_missing',",
        "origin: 'project.workdir_who_knows',",
    )
    observed = run_origin_harness(tmp_root, plugin=tampered)
    origin = _origin_of(observed, "origin_missing_project_dir")

    _assert_origin_shape(origin)
    assert origin["origin"] == "unknown_origin", origin
    assert "who_knows" not in json.dumps(origin, ensure_ascii=False), origin


# ------------------------------------------------------------------- 跨语言：空值 / null
#
# `payload_is_well_formed` 后来收紧成与 `Origin.__post_init__` 同口径（owner / object.value /
# object.source / observation.result / observation.verified_at 必须是非空字符串）。JS 侧
# `buildOrigin` 是插件里唯一的 origin 产出点，但它**没有导出**：下面在真源码的临时副本上
# 补一行导出，再在真 node 里喂它空串 / null / undefined / 非字符串——测的仍是仓库里那份实现。
HARNESS_BUILD_ORIGIN = '''/**
 * 跨语言核实：直接喂 buildOrigin 空值 / null / undefined / 非字符串，看它产出什么。
 *
 * buildOrigin 不在导出面上（插件只导出 name / inject / createRunHook / apply）：
 * 副本上补的那一行 export 是唯一改动，函数体一个字不动。
 * argv: <plugin.mjs>
 */
import { pathToFileURL } from 'node:url';

const { buildOrigin } = await import(pathToFileURL(process.argv[2]).href);

const CASES = [
  {
    label: 'empty_strings',
    fields: {
      origin: 'project.workdir_missing',
      owner: '',
      objectKind: 'workdir',
      objectValue: '',
      objectSource: '',
      method: 'stat',
      result: '',
      verified: true,
      fix: '创建这个目录，然后重跑这次调用',
      causalLink: 'proven',
    },
  },
  {
    label: 'nulls',
    fields: {
      origin: 'project.workdir_missing',
      owner: null,
      objectKind: 'workdir',
      objectValue: null,
      objectSource: null,
      method: 'stat',
      result: null,
      verified: true,
      fix: null,
      causalLink: 'proven',
    },
  },
  {
    label: 'missing_fields',
    fields: { origin: 'project.workdir_missing', fix: '创建这个目录，然后重跑这次调用' },
  },
  {
    label: 'non_strings',
    fields: {
      origin: 'project.workdir_missing',
      owner: 7,
      objectKind: 'workdir',
      objectValue: ['a'],
      objectSource: { nested: true },
      method: 'stat',
      result: 0,
      verified: true,
      fix: '创建这个目录，然后重跑这次调用',
      causalLink: 'proven',
    },
  },
  {
    label: 'invalid_everything',
    fields: {
      origin: 'not.in.the.set',
      owner: '',
      objectKind: 'bogus',
      objectValue: null,
      objectSource: '',
      method: 'bogus',
      result: '',
      verified: false,
      fix: '',
      causalLink: 'bogus',
    },
  },
  {
    label: 'valid_control',
    fields: {
      origin: 'project.workdir_missing',
      owner: 'platform.attribution',
      objectKind: 'workdir',
      objectValue: 'missing-workdir',
      objectSource: 'config.projectDir',
      method: 'stat',
      result: 'ENOENT',
      verified: true,
      fix: '创建这个目录，然后重跑这次调用',
      causalLink: 'proven',
    },
  },
];

const observed = {};
for (const item of CASES) {
  observed[item.label] = buildOrigin(item.fields);
}
process.stdout.write(JSON.stringify(observed));
'''


def run_build_origin_harness(tmp_root: Path) -> dict:
    """在真 node 里调用真插件的 buildOrigin：临时副本只多一行导出。"""

    tampered = _tampered_plugin(
        tmp_root,
        "policy-hook.plugin.build-origin.mjs",
        "export function createRunHook(ctx, config) {",
        "export { buildOrigin };\n\nexport function createRunHook(ctx, config) {",
    )
    script = tmp_root / "plugin_build_origin.mjs"
    script.write_text(HARNESS_BUILD_ORIGIN, encoding="utf-8", newline=chr(10))
    completed = subprocess.run(
        [_require_node(), str(script), str(tampered)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_the_js_builder_and_the_python_validator_agree_on_empty_and_null(tmp_root):
    """跨语言：JS 侧的空值 / null 兜底必须让载荷仍然通过**更严**的 Python 校验器。

    收紧后的 `payload_is_well_formed` 要求 owner / object.value / object.source /
    observation.result / observation.verified_at 是非空字符串。若插件把这些空值原样吐出来，
    同一份契约的另一侧今天就会拒绝它——这条用例逐条喂 hostile 输入（空串 / null /
    undefined / 非字符串 / 闭集外取值），断言产出的每一份载荷都仍然通过。
    """

    from provenance.origin import payload_is_well_formed

    observed = run_build_origin_harness(tmp_root)
    assert set(observed) == {
        "empty_strings",
        "nulls",
        "missing_fields",
        "non_strings",
        "invalid_everything",
        "valid_control",
    }

    for label, payload in observed.items():
        assert payload_is_well_formed(payload), (label, payload)

    # 反真空：兜底真的发生过（不是"输入本来就合法"）
    assert observed["empty_strings"]["owner"] == "platform.attribution"
    assert observed["empty_strings"]["object"]["value"] == "unknown"
    assert observed["empty_strings"]["object"]["source"] == "unknown"
    assert observed["empty_strings"]["observation"]["result"] == "没有可读的取证结果"
    assert observed["nulls"]["observation"]["result"] != ""
    assert observed["missing_fields"]["object"]["value"] == "unknown"
    assert observed["non_strings"]["object"]["source"] == "unknown"
    assert observed["invalid_everything"]["origin"] == "unknown_origin"
    assert observed["invalid_everything"]["causal_link"] == "unproven"


# ------------------------------------------------------------------- 调用标识（配对键）


def test_call_action_id_never_fabricates_a_partial_identifier() -> None:
    """载荷缺字段时返回 None，不许拼「半个 id」。

    docstring 承诺「载荷缺字段时返回 None：编出来的标识会让事后核对接错动作」。旧实现却把
    缺了 tool_use_id 的载荷折叠成裸 session_id：同一会话里所有这样的调用共用同一个
    action_id，pre / post 于是按错误的键配对——正是那句承诺要避免的事。裸 tool_use_id
    则丢掉会话维度，跨会话撞键。
    """

    from adapters.dsh.hooks import call_action_id

    assert call_action_id({"session_id": "s", "tool_use_id": "call-1"}) == "s:call-1"
    assert call_action_id({"session_id": "s"}) is None
    assert call_action_id({"tool_use_id": "call-1"}) is None
    assert call_action_id({}) is None
    assert call_action_id({"session_id": "   ", "tool_use_id": "call-1"}) is None
    assert call_action_id("not-a-mapping") is None


def test_a_payload_without_a_tool_use_id_leaves_the_audit_action_id_unset(
    dsh_config_path, dsh_project
) -> None:
    """审计里读到的必须是「没有标识」，不是编出来的那一个。"""

    audit = dsh_project.parent / "audit.jsonl"
    document = payload("pre-tool-use-edit-block.json", dsh_project)
    document.pop("tool_use_id")

    outcome = run_hook(document, config_path=dsh_config_path, audit_path=audit)

    assert outcome.exit_code == EXIT_BLOCK
    record = load_jsonl(audit)[0]
    assert record["reason_code"] == "context_error"
    assert "action_id" not in record
