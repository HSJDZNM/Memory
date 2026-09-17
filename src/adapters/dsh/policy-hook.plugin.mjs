/**
 * dsh 进程内 Hook 插件：把 tools/pre-execute 转发给 Python 策略 Hook。
 *
 * 它只做三件事，不含任何策略逻辑：
 *   1) 把 dsh 的工具调用组装成 PreToolUse 载荷（与 Claude Code 方言同形）；
 *   2) 用 ctx.shell 运行 Hook 命令，payload 走 stdin；
 *   3) exit 2 → {kind:'deny', reason: stderr}，其余退出码 → 交给下一个监听者。
 *
 * 为什么需要它：dsh 0.1.5-rc.1 自带的 @deepseek-ai/dsh-hooks-claude-code 桥在本机
 * 实测「外部命令确实被调用了，但它的 exit 2 没有变成 deny」（证据见
 * src/adapters/dsh/README.md 第 8 节）。这个 30 行的插件用同一条线协议补上那一步，
 * Python 侧的 adapter/hook/CLI 一行都不用改。
 *
 * 配置（profile patch 的 config 字段）：
 *   command:   要执行的 Hook 命令（PowerShell 语法，dsh 在 Windows 上用 pwsh 执行）
 *   timeoutMs: 单次 Hook 的墙钟上限（必须大于 adapter 配置里的 timeout_ms）
 *   projectDir: Hook 的工作目录；不填则用会话工作目录
 */

import { readFileSync } from 'node:fs';

export const name = 'policy-hook';
export const inject = ['shell'];

const DEFAULT_TIMEOUT_MS = 30000;

export function apply(ctx, config) {
  const command = config.command;
  if (typeof command !== 'string' || command.trim() === '') {
    throw new Error('policy-hook: config.command is required');
  }
  const timeoutMs = typeof config.timeoutMs === 'number' ? config.timeoutMs : DEFAULT_TIMEOUT_MS;
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1) {
    throw new Error('policy-hook: config.timeoutMs must be a positive integer');
  }

  ctx.on('tools/pre-execute', async (exec, next) => {
    const cwd = config.projectDir ?? exec.agent?.session?.header?.cwd;
    const payload = JSON.stringify({
      session_id: exec.agent?.session?.header?.id ?? '',
      transcript_path: '',
      cwd: cwd ?? '',
      hook_event_name: 'PreToolUse',
      tool_name: exec.name,
      tool_input: exec.arguments,
      tool_use_id: exec.callId,
    }) + '\n';

    const request = {
      command,
      timeoutMs,
      stdin: payload,
      signal: exec.signal,
      ...(cwd !== undefined ? { workdir: cwd } : {}),
    };

    let result;
    try {
      result = await ctx.shell.run(ctx.shell.resolve(request));
    } catch (error) {
      // 起不来、被杀、被沙箱拒绝——都不能静默放行：按失败关闭阻断写操作。
      return {
        kind: 'deny',
        reason: 'policy-hook: Hook 无法执行（' + String(error && error.message ? error.message : error) + '），按失败关闭拒绝该工具调用',
      };
    }

    const exitCode = result.exitCode;
    const stderr = String(result.stderr?.text ?? '').trim();
    if (exitCode === 2) {
      return { kind: 'deny', reason: stderr || 'blocked by policy hook' };
    }
    if (exitCode !== 0) {
      return {
        kind: 'deny',
        reason: 'policy-hook: Hook 退出码 ' + String(exitCode) + '，未知状态按失败关闭拒绝' + (stderr ? '：' + stderr : ''),
      };
    }
    return next();
  });
}
