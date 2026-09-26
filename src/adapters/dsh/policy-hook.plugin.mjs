/**
 * dsh 进程内 Hook 插件：把 tools/pre-execute 与 tools/post-execute 转发给同一个 Python 策略 Hook。
 *
 * 它只做三件事，不含任何策略逻辑：
 *   1) 把 dsh 的工具调用组装成 PreToolUse / PostToolUse 载荷（与 Claude Code 方言同形）；
 *   2) 用 ctx.shell 运行 Hook 命令，payload 走 stdin；
 *   3) exit 2 → 阻断（pre 阶段 deny；post 阶段 block + feedback），其余非 0 退出码与
 *      "起不来 / 被杀"一律按失败关闭处理。
 *
 * 为什么需要它：dsh 0.1.5-rc.1 自带的 @deepseek-ai/dsh-hooks-claude-code 桥在本机
 * 实测「外部命令确实被调用了，但它的 exit 2 没有变成 deny」（证据见
 * src/adapters/dsh/README.md 第 8 节）。这个插件用同一条线协议补上那一步，
 * Python 侧的 adapter/hook/CLI 一行都不用改。
 *
 * 为什么 post 也必须注册（治理缺口 G2）：Python 侧早就实现了事后核对
 * （hooks.py 的 post_execute_outcome、enforcement.py 的 handle_post / 注册表的 post_checks），
 * 但进程内插件只注册了 pre，于是注册表里声明的 post_checks 从来没被执行过——
 * 实测 26 次受治理动作的事后台账是 0 条。注册 pre 却不注册 post 不会让任何测试变红，
 * 所以这里两个事件名必须成对出现，并由 tests/contract/test_policy_hook_chain.py 断言。
 *
 * 真实 API（已核对 @deepseek-ai/dsh 的 dsh-hooks-claude-code/lib/index.js:251-294）
 *   ctx.on('tools/pre-execute',  async (exec, next) => …)
 *   ctx.on('tools/post-execute', async (exec, result, next) => …)
 * pre 阶段返回 {kind:'deny', reason}；post 阶段副作用已发生，只能返回
 * {kind:'block', feedback:[{type:'text', text}]} 把这次工具结果标成错误。
 *
 * 配置（profile patch 的 config 字段）：
 *   command:   要执行的 Hook 命令（PowerShell 语法，dsh 在 Windows 上用 pwsh 执行）
 *   timeoutMs: 单次 Hook 的墙钟上限（必须大于 adapter 配置里的 timeout_ms）
 *   projectDir: Hook 的工作目录；不填则用会话工作目录
 */

export const name = 'policy-hook';
export const inject = ['shell'];

const DEFAULT_TIMEOUT_MS = 30000;

// 工具返回值只作不可信数据：只转发足以定位问题的前缀，避免把大段输出塞进 Hook 载荷
// 与台账（事后核对要的是"这次执行发生了什么"的摘要，不是全文）。
const MAX_TOOL_RESPONSE_CHARS = 4000;

/** 把 dsh 的 content blocks 折叠成文本（与官方桥 blocksToText 同口径）。 */
function blocksToText(content) {
  if (typeof content === 'string') {
    return content;
  }
  if (!Array.isArray(content)) {
    return '';
  }
  return content
    .filter((block) => block && block.type === 'text')
    .map((block) => String(block.text ?? ''))
    .join('');
}

function truncate(text, limit) {
  if (text.length <= limit) {
    return text;
  }
  return text.slice(0, limit) + '\n[policy-hook] tool_response 已截断（原始长度 ' + String(text.length) + ' 字符）';
}

export function apply(ctx, config) {
  const command = config.command;
  if (typeof command !== 'string' || command.trim() === '') {
    throw new Error('policy-hook: config.command is required');
  }
  const timeoutMs = typeof config.timeoutMs === 'number' ? config.timeoutMs : DEFAULT_TIMEOUT_MS;
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1) {
    throw new Error('policy-hook: config.timeoutMs must be a positive integer');
  }

  /**
   * 运行一次 Hook 命令并把退出码翻译成"放行 / 按失败关闭拒绝"。
   *
   * 失败关闭的三个来源（G12）：起不来 / 被杀 / 被沙箱拒绝（catch 分支）、
   * exit 2（策略阻断）、其余非 0 退出码（未知状态）。**只有 exit 0 是放行。**
   */
  const runHook = async (exec, { hookEvent, fields }) => {
    const cwd = config.projectDir ?? exec.agent?.session?.header?.cwd;
    const payload = JSON.stringify({
      session_id: exec.agent?.session?.header?.id ?? '',
      transcript_path: '',
      cwd: cwd ?? '',
      hook_event_name: hookEvent,
      tool_name: exec.name,
      tool_input: exec.arguments,
      tool_use_id: exec.callId,
      ...fields,
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
      // 起不来、被杀、被沙箱拒绝——都不能静默放行：按失败关闭阻断。
      return {
        allowed: false,
        reason:
          'policy-hook: Hook 无法执行（' +
          String(error && error.message ? error.message : error) +
          '），按失败关闭拒绝该工具调用',
      };
    }

    const exitCode = result.exitCode;
    const stderr = String(result.stderr?.text ?? '').trim();
    if (exitCode === 2) {
      return { allowed: false, reason: stderr || 'blocked by policy hook' };
    }
    if (exitCode !== 0) {
      return {
        allowed: false,
        reason:
          'policy-hook: Hook 退出码 ' +
          String(exitCode) +
          '，未知状态按失败关闭拒绝' +
          (stderr ? '：' + stderr : ''),
      };
    }
    return { allowed: true, reason: '' };
  };

  ctx.on('tools/pre-execute', async (exec, next) => {
    const outcome = await runHook(exec, { hookEvent: 'PreToolUse', fields: {} });
    if (!outcome.allowed) {
      // 参数已解析、尚未执行：拒绝这次调用即可。
      return { kind: 'deny', reason: outcome.reason };
    }
    return next();
  });

  ctx.on('tools/post-execute', async (exec, result, next) => {
    const outcome = await runHook(exec, {
      hookEvent: 'PostToolUse',
      fields: {
        // 兼容两种形状：dsh 给的是带 content 的结果对象；拿不到 content 时退回结果本身，
        // 避免把"结果形状变了"静默变成"空结果"（事后核对会因此看不到任何偏差）。
        tool_response: truncate(
          blocksToText(result?.content ?? result),
          MAX_TOOL_RESPONSE_CHARS,
        ),
      },
    });
    if (!outcome.allowed) {
      // PostToolUse 阶段副作用已经发生：这里**只能**把结果标成错误并把理由交给模型，
      // 语义是"这次执行的结果不可信 / 需要修复"，绝不是"回滚成功"（与 hooks.py 的
      // exit 2 语义、README 第 8 节一致）。
      return { kind: 'block', feedback: [{ type: 'text', text: outcome.reason }] };
    }
    return next();
  });
}
